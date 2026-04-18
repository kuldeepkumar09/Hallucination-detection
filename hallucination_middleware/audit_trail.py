"""
Audit Trail — append-only JSONL log of every request processed by the
hallucination detection pipeline.

Each line is a complete, self-contained JSON object so the log can be
streamed, tailed, or analysed with standard tools (jq, pandas, etc.).
"""
import json
import logging
from pathlib import Path
from typing import Dict, List

from .models import HallucinationAudit

logger = logging.getLogger(__name__)


class AuditTrail:
    def __init__(self, log_path: str = "") -> None:
        from .config import get_settings  # noqa: PLC0415 – avoid circular at module level

        settings = get_settings()
        path_str = log_path or settings.audit_log_path
        self._path = Path(path_str)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def log(self, audit: HallucinationAudit) -> None:
        """Append a single audit entry to the JSONL file."""
        try:
            record = audit.model_dump()
            record.pop("original_text", None)
            record.pop("annotated_text", None)

            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, default=str) + "\n")
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
        """Aggregate statistics across the entire log file (streaming, O(1) memory)."""
        if not self._path.exists():
            return {"total_requests": 0}

        stats: Dict = {
            "total_requests": 0,
            "total_claims": 0,
            "total_verified": 0,
            "total_flagged": 0,
            "total_blocked": 0,
            "blocked_responses": 0,
            "total_pass": 0,
            "total_annotate": 0,
            "total_partially_supported": 0,
            "total_unverifiable": 0,
            "total_contradicted": 0,
            "avg_confidence": 0.0,
            "avg_processing_ms": 0.0,
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

                    if (conf := entry.get("overall_confidence")) is not None:
                        confidences.append(float(conf))

                    if (ms := entry.get("processing_time_ms")) is not None:
                        processing_times.append(float(ms))
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to read audit log for stats: %s", exc)

        if confidences:
            stats["avg_confidence"] = round(sum(confidences) / len(confidences), 3)
        if processing_times:
            stats["avg_processing_ms"] = round(sum(processing_times) / len(processing_times), 1)

        return stats
