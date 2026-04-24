"""
Audit Trail — append-only JSONL log of every request processed by the
hallucination detection pipeline.

Each line is a complete, self-contained JSON object so the log can be
streamed, tailed, or analysed with standard tools (jq, pandas, etc.).

Features:
  - Size-based rotation (default: 10MB per file)
  - Keeps last N rotated files (default: 5)
  - Compressed rotated files (.gz) to save disk space
"""
import gzip
import json
import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .models import HallucinationAudit

logger = logging.getLogger(__name__)

_STATS_TTL = 15.0  # seconds — re-read the JSONL at most once per 15s
_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB — rotate when file exceeds this
_MAX_BACKUPS = 5  # keep last 5 rotated files


class AuditTrail:
    def __init__(self, log_path: str = "", max_file_size: int = _MAX_FILE_SIZE,
                 max_backups: int = _MAX_BACKUPS) -> None:
        from .config import get_settings  # noqa: PLC0415 – avoid circular at module level

        settings = get_settings()
        path_str = log_path or settings.audit_log_path
        self._path = Path(path_str)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._stats_cache: Optional[Dict] = None
        self._stats_cache_at: float = 0.0
        self._max_file_size = max_file_size
        self._max_backups = max_backups

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def _rotate_if_needed(self) -> None:
        """Rotate the log file if it exceeds the maximum size."""
        if not self._path.exists():
            return

        try:
            file_size = self._path.stat().st_size
            if file_size < self._max_file_size:
                return

            logger.info("Rotating audit log (size: %.1fMB)", file_size / 1024 / 1024)

            # Delete oldest backup if we have too many
            oldest = self._path.parent / f"{self._path.name}.{self._max_backups}.gz"
            if oldest.exists():
                oldest.unlink()

            # Shift existing backups (audit_trail.jsonl.4.gz -> audit_trail.jsonl.5.gz, etc.)
            for i in range(self._max_backups, 1, -1):
                src = self._path.parent / f"{self._path.name}.{i - 1}.gz"
                dst = self._path.parent / f"{self._path.name}.{i}.gz"
                if src.exists():
                    src.rename(dst)

            # Compress current file to .1.gz
            backup_path = self._path.parent / f"{self._path.name}.1.gz"
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self._path, 'rb') as f_in:
                with gzip.open(backup_path, 'wb') as f_out:
                    # Add a header comment with rotation timestamp
                    header = f"# Rotated at {timestamp}\n".encode()
                    f_out.write(header)
                    shutil.copyfileobj(f_in, f_out)

            # Truncate the original file and invalidate stats cache
            self._path.write_text("")
            self._stats_cache = None
            self._stats_cache_at = 0.0

            logger.info("Audit log rotated to %s", backup_path)

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to rotate audit log: %s", exc)

    def log(self, audit: HallucinationAudit) -> None:
        """Append a single audit entry to the JSONL file."""
        try:
            record = audit.model_dump()
            record.pop("original_text", None)
            record.pop("annotated_text", None)
            # Store corrected_text as bool: True = was corrected, False = not corrected
            record["corrected_text"] = bool(record.get("corrected_text"))

            # Check if rotation is needed before writing
            self._rotate_if_needed()

            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
            self._stats_cache = None  # invalidate so next get_stats() re-reads
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to write audit log: %s", exc)

    # ------------------------------------------------------------------
    # Reading
    # ------------------------------------------------------------------

    def read_recent(self, n: int = 20) -> List[Dict]:
        """Return the *n* most recent audit entries (newest first) using binary seek."""
        if not self._path.exists():
            return []
        entries: List[Dict] = []
        try:
            with self._path.open("rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return []
                buf = b""
                pos = size
                lines_found = 0
                while pos > 0 and lines_found < n + 1:
                    step = min(4096, pos)
                    pos -= step
                    f.seek(pos)
                    chunk = f.read(step)
                    buf = chunk + buf
                    lines_found = buf.count(b"\n")
            lines = [ln for ln in buf.decode("utf-8", errors="replace").splitlines() if ln.strip()]
            lines = lines[-n:]
            for line in reversed(lines):
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read audit log: %s", exc)
        return entries

    def get_stats(self) -> Dict:
        """Aggregate statistics across the current log file only (streaming, O(1) memory).
        
        Note: For full historical stats including rotated files, use get_full_stats().
        """
        now = time.monotonic()
        if self._stats_cache is not None and (now - self._stats_cache_at) < _STATS_TTL:
            return self._stats_cache

        if not self._path.exists():
            return {"total_requests": 0}

        stats: Dict = {
            "total_requests": 0,
            "total_claims": 0,
            "total_verified": 0,
            "total_flagged": 0,
            "total_blocked": 0,
            "blocked_responses": 0,
            "flagged_responses": 0,
            "corrected_count": 0,
            "total_pass": 0,
            "total_annotate": 0,
            "total_partially_supported": 0,
            "total_unverifiable": 0,
            "total_contradicted": 0,
            "avg_confidence": 0.0,
            "avg_processing_ms": 0.0,
            "category_breakdown": {},
        }
        confidences: List[float] = []
        processing_times: List[float] = []

        try:
            with self._path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    stats["total_requests"] += 1
                    stats["total_claims"] += entry.get("total_claims", 0)
                    stats["total_verified"] += entry.get("verified_count", 0)
                    stats["total_flagged"] += entry.get("flagged_count", 0)
                    stats["total_blocked"] += entry.get("blocked_count", 0)
                    stats["total_pass"] += entry.get("pass_count", 0)
                    stats["total_annotate"] += entry.get("annotate_count", 0)
                    stats["total_partially_supported"] += entry.get("partially_supported_count", 0)
                    stats["total_unverifiable"] += entry.get("unverifiable_count", 0)
                    stats["total_contradicted"] += entry.get("contradicted_count", 0)

                    if entry.get("response_blocked"):
                        stats["blocked_responses"] += 1

                    if entry.get("flagged_count", 0) > 0:
                        stats["flagged_responses"] += 1

                    if entry.get("corrected_text") is True:
                        stats["corrected_count"] += 1

                    if (conf := entry.get("overall_confidence")) is not None:
                        confidences.append(float(conf))

                    if (ms := entry.get("processing_time_ms")) is not None:
                        processing_times.append(float(ms))

                    # Per-category breakdown
                    cb = stats["category_breakdown"]
                    for claim in entry.get("claims", []):
                        vc = claim.get("verified_claim", {}) or {}
                        c_obj = vc.get("claim", {}) or {}
                        cat = c_obj.get("category", "GENERAL")
                        action = claim.get("action", "pass")
                        if cat not in cb:
                            cb[cat] = {"total": 0, "blocked": 0, "flagged": 0, "verified": 0}
                        cb[cat]["total"] += 1
                        if action == "block":
                            cb[cat]["blocked"] += 1
                        elif action == "flag":
                            cb[cat]["flagged"] += 1
                        elif action in ("pass", "annotate"):
                            cb[cat]["verified"] += 1

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read audit log for stats: %s", exc)

        if confidences:
            stats["avg_confidence"] = round(sum(confidences) / len(confidences), 3)
        if processing_times:
            stats["avg_processing_ms"] = round(sum(processing_times) / len(processing_times), 1)

        self._stats_cache = stats
        self._stats_cache_at = time.monotonic()
        return stats

    def get_full_stats(self) -> Dict:
        """Aggregate statistics across current and all rotated log files."""
        stats: Dict = {
            "total_requests": 0,
            "total_claims": 0,
            "total_verified": 0,
            "total_flagged": 0,
            "total_blocked": 0,
            "blocked_responses": 0,
            "flagged_responses": 0,
            "corrected_count": 0,
            "total_pass": 0,
            "total_annotate": 0,
            "total_partially_supported": 0,
            "total_unverifiable": 0,
            "total_contradicted": 0,
            "avg_confidence": 0.0,
            "avg_processing_ms": 0.0,
            "category_breakdown": {},
        }
        confidences: List[float] = []
        processing_times: List[float] = []

        # Process current log file
        if self._path.exists():
            self._process_log_file(self._path, stats, confidences, processing_times)

        # Process rotated files
        for i in range(1, self._max_backups + 1):
            backup = self._path.parent / f"{self._path.name}.{i}.gz"
            if backup.exists():
                try:
                    with gzip.open(backup, 'rt', encoding="utf-8", errors="replace") as fh:
                        for line in fh:
                            line = line.strip()
                            if not line or line.startswith('#'):
                                continue
                            try:
                                entry = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            self._process_entry(entry, stats, confidences, processing_times)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to read rotated log %s: %s", backup, exc)

        if confidences:
            stats["avg_confidence"] = round(sum(confidences) / len(confidences), 3)
        if processing_times:
            stats["avg_processing_ms"] = round(sum(processing_times) / len(processing_times), 1)

        return stats

    def _process_log_file(self, path: Path, stats: Dict, confidences: List[float],
                          processing_times: List[float]) -> None:
        """Process a single log file and update stats."""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    self._process_entry(entry, stats, confidences, processing_times)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read log file %s: %s", path, exc)

    def _process_entry(self, entry: Dict, stats: Dict, confidences: List[float],
                       processing_times: List[float]) -> None:
        """Process a single audit entry and update stats."""
        stats["total_requests"] += 1
        stats["total_claims"] += entry.get("total_claims", 0)
        stats["total_verified"] += entry.get("verified_count", 0)
        stats["total_flagged"] += entry.get("flagged_count", 0)
        stats["total_blocked"] += entry.get("blocked_count", 0)
        stats["total_pass"] += entry.get("pass_count", 0)
        stats["total_annotate"] += entry.get("annotate_count", 0)
        stats["total_partially_supported"] += entry.get("partially_supported_count", 0)
        stats["total_unverifiable"] += entry.get("unverifiable_count", 0)
        stats["total_contradicted"] += entry.get("contradicted_count", 0)

        if entry.get("response_blocked"):
            stats["blocked_responses"] += 1

        if entry.get("flagged_count", 0) > 0:
            stats["flagged_responses"] += 1

        if entry.get("corrected_text") is True:
            stats["corrected_count"] += 1

        if (conf := entry.get("overall_confidence")) is not None:
            confidences.append(float(conf))

        if (ms := entry.get("processing_time_ms")) is not None:
            processing_times.append(float(ms))

        # Per-category breakdown
        cb = stats["category_breakdown"]
        for claim in entry.get("claims", []):
            vc = claim.get("verified_claim", {}) or {}
            c_obj = vc.get("claim", {}) or {}
            cat = c_obj.get("category", "GENERAL")
            action = claim.get("action", "pass")
            if cat not in cb:
                cb[cat] = {"total": 0, "blocked": 0, "flagged": 0, "verified": 0}
            cb[cat]["total"] += 1
            if action == "block":
                cb[cat]["blocked"] += 1
            elif action == "flag":
                cb[cat]["flagged"] += 1
            elif action in ("pass", "annotate"):
                cb[cat]["verified"] += 1

    def get_rotation_info(self) -> Dict:
        """Return information about log rotation status."""
        info = {
            "current_file": str(self._path),
            "current_size_bytes": 0,
            "current_size_mb": "0.0",
            "max_file_size_bytes": self._max_file_size,
            "max_file_size_mb": self._max_file_size / 1024 / 1024,
            "max_backups": self._max_backups,
            "rotated_files": [],
        }

        if self._path.exists():
            info["current_size_bytes"] = self._path.stat().st_size
            info["current_size_mb"] = f"{info['current_size_bytes'] / 1024 / 1024:.1f}"

        for i in range(1, self._max_backups + 1):
            backup = self._path.parent / f"{self._path.name}.{i}.gz"
            if backup.exists():
                size = backup.stat().st_size
                info["rotated_files"].append({
                    "file": str(backup),
                    "size_bytes": size,
                    "size_mb": f"{size / 1024 / 1024:.1f}",
                })

        info["total_size_bytes"] = info["current_size_bytes"] + sum(
            f["size_bytes"] for f in info["rotated_files"]
        )
        info["total_size_mb"] = f"{info['total_size_bytes'] / 1024 / 1024:.1f}"

        return info
