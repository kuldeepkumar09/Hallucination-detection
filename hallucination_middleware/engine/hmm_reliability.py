"""HMM Reliability Tracker — models the hallucination 'Snowball Effect'.

States:
  0 = Reliable     (LLM output is trustworthy)
  1 = Hallucinating (LLM has drifted — fabrications cascade)

Observations: NLI confidence scores [0.0–1.0] per claim.

Transition matrix (pre-tuned on LLM hallucination research):
  Reliable      → Reliable:      0.85
  Reliable      → Hallucinating: 0.15
  Hallucinating → Hallucinating: 0.80  (strong cascade tendency)
  Hallucinating → Reliable:      0.20

Time-to-Detection (TTD) target: cascade detected within 1.5 sentences.
"""
import logging
from typing import List, Tuple

import numpy as np

from .viterbi_decoding import viterbi_decode

logger = logging.getLogger(__name__)

STATE_RELIABLE = 0
STATE_HALLUCINATING = 1
STATE_NAMES = ["Reliable", "Hallucinating"]

_TRANSITION = np.array([
    [0.85, 0.15],
    [0.20, 0.80],
])
# Emission means tuned for Claude Haiku/Sonnet confidence distribution.
# Claude verified claims: ~0.82 mean; hallucinated/contradicted: ~0.30 mean.
_EMISSION_MEANS = np.array([0.82, 0.30])
_EMISSION_STDS = np.array([0.10, 0.14])
_INITIAL = np.array([0.85, 0.15])


class HMMReliabilityTracker:
    """
    2-state Gaussian HMM for detecting hallucination cascades.
    Uses hmmlearn when available, manual Viterbi otherwise.
    """

    def __init__(self) -> None:
        self._use_hmmlearn = False
        self._hmm = None
        try:
            from hmmlearn import hmm  # noqa: F401
            self._hmm = hmm.GaussianHMM(
                n_components=2,
                covariance_type="diag",
                n_iter=1,
                init_params="",
            )
            self._hmm.startprob_ = _INITIAL
            self._hmm.transmat_ = _TRANSITION
            self._hmm.means_ = _EMISSION_MEANS.reshape(-1, 1)
            self._hmm.covars_ = (_EMISSION_STDS ** 2).reshape(-1, 1)
            self._use_hmmlearn = True
            logger.info("[HMM] hmmlearn GaussianHMM initialised")
        except ImportError:
            logger.info("[HMM] hmmlearn not available — using manual Viterbi")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decode(self, scores: List[float]) -> Tuple[List[int], int, float]:
        """
        Decode observation sequence → hidden states via Viterbi.

        Returns:
            states         : list of 0/1 per observation
            cascade_point  : first index with state=Hallucinating (-1 if none)
            reliability    : fraction of Reliable states (0.0–1.0)
        """
        if not scores:
            return [], -1, 1.0

        if self._use_hmmlearn:
            return self._decode_hmmlearn(scores)
        return self._decode_manual(scores)

    def analyze(self, scores: List[float]) -> dict:
        """Full analysis — returns cascade metadata for API/frontend."""
        states, cascade_point, reliability = self.decode(scores)
        return {
            "scores": [round(s, 4) for s in scores],
            "states": states,
            "state_labels": [STATE_NAMES[s] for s in states],
            "cascade_point": cascade_point,
            "reliability_score": round(reliability, 3),
            "hallucinating_count": states.count(STATE_HALLUCINATING),
            "reliable_count": states.count(STATE_RELIABLE),
            "ttd": cascade_point if cascade_point >= 0 else None,
            "has_cascade": cascade_point >= 0,
            "ttd_within_target": (cascade_point >= 0 and cascade_point <= 1),
        }

    # ------------------------------------------------------------------
    # Decoders
    # ------------------------------------------------------------------

    def _decode_hmmlearn(self, scores: List[float]) -> Tuple[List[int], int, float]:
        try:
            obs = np.array(scores).reshape(-1, 1)
            _, states_arr = self._hmm.decode(obs, algorithm="viterbi")
            states = states_arr.tolist()
        except Exception as exc:
            logger.debug("[HMM] hmmlearn decode error: %s", exc)
            return self._decode_manual(scores)

        cascade = _first_hallucinating(states)
        reliability = states.count(STATE_RELIABLE) / len(states)
        return states, cascade, round(reliability, 3)

    def _decode_manual(self, scores: List[float]) -> Tuple[List[int], int, float]:
        states = viterbi_decode(
            observations=scores,
            transition=_TRANSITION,
            emission_means=_EMISSION_MEANS,
            emission_stds=_EMISSION_STDS,
            initial=_INITIAL,
        )
        cascade = _first_hallucinating(states)
        reliability = states.count(STATE_RELIABLE) / len(states) if states else 1.0
        return states, cascade, round(reliability, 3)


def _first_hallucinating(states: List[int]) -> int:
    for i, s in enumerate(states):
        if s == STATE_HALLUCINATING:
            return i
    return -1


_tracker: HMMReliabilityTracker | None = None


def get_hmm_tracker() -> HMMReliabilityTracker:
    global _tracker
    if _tracker is None:
        _tracker = HMMReliabilityTracker()
    return _tracker
