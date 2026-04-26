"""RARL Power-Law Cost Function — reward system for claim verification.

Cost function:
    J(q, status) = -(α·log(q) - β·q^γ + r₀)

Where:
    q  = confidence score [0.0–1.0]
    α  = reward coefficient for correct high-confidence claims (default 1.0)
    β  = penalty coefficient — power-law punishes confident hallucinations (default 2.0)
    γ  = power exponent (γ≈2 makes penalty exponential for high-confidence wrongs)
    r₀ = abstention reward — +0.20 for saying "I don't know" honestly

Interpretation:
    verified   high q  → large negative cost (big reward)
    verified   low q   → small negative cost (modest reward)
    contradicted high q → large POSITIVE cost (huge penalty — confident hallucination)
    contradicted low q  → small positive cost (less penalty — uncertain claim)
    unverifiable       → flat −r₀ (abstention reward regardless of confidence)
"""
import math
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_EPSILON = 1e-6


class RewardSystem:
    def __init__(
        self,
        alpha: float = 1.0,
        beta: float = 2.0,
        gamma: float = 2.0,
        r0: float = 0.20,
    ) -> None:
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.r0 = r0

    # ------------------------------------------------------------------
    # Single claim
    # ------------------------------------------------------------------

    def cost(self, confidence: float, status: str) -> float:
        """Cost J for one (confidence, status) pair. Lower cost = better outcome."""
        q = max(_EPSILON, min(1.0 - _EPSILON, confidence))

        if status == "unverifiable":
            return -self.r0

        if status == "verified":
            return -(self.alpha * math.log(q))

        if status == "contradicted":
            return self.beta * (q ** self.gamma)

        if status == "partially_supported":
            return -(self.alpha * math.log(q) * 0.5)

        return 0.0

    def reward(self, confidence: float, status: str) -> float:
        """Reward = -cost. Higher is better."""
        return -self.cost(confidence, status)

    # ------------------------------------------------------------------
    # Sequence
    # ------------------------------------------------------------------

    def score_sequence(
        self,
        scores: List[float],
        statuses: List[str],
    ) -> dict:
        """Score a full claim sequence. Returns aggregate reward/cost stats."""
        if not scores:
            return {
                "total_reward": 0.0,
                "total_cost": 0.0,
                "avg_reward": 0.0,
                "per_claim": [],
                "alpha": self.alpha,
                "beta": self.beta,
                "gamma": self.gamma,
                "r0": self.r0,
            }

        per_claim = [
            {
                "confidence": round(q, 3),
                "status": s,
                "cost": round(self.cost(q, s), 4),
                "reward": round(self.reward(q, s), 4),
            }
            for q, s in zip(scores, statuses)
        ]

        total_reward = sum(p["reward"] for p in per_claim)
        total_cost = sum(p["cost"] for p in per_claim)

        return {
            "total_reward": round(total_reward, 4),
            "total_cost": round(total_cost, 4),
            "avg_reward": round(total_reward / len(per_claim), 4),
            "per_claim": per_claim,
            "alpha": self.alpha,
            "beta": self.beta,
            "gamma": self.gamma,
            "r0": self.r0,
        }

    # ------------------------------------------------------------------
    # MPC candidate selection
    # ------------------------------------------------------------------

    def select_best_candidate(
        self,
        candidates: List[str],
        scores_and_statuses: List[Tuple[float, str]],
    ) -> Tuple[Optional[str], float, int]:
        """
        Pick the candidate with the lowest cost (best reward).
        Returns (best_text, best_cost, best_index).
        """
        if not candidates:
            return None, float("inf"), -1

        costs = [self.cost(q, s) for q, s in scores_and_statuses]
        best_idx = min(range(len(costs)), key=lambda i: costs[i])
        return candidates[best_idx], costs[best_idx], best_idx


_instance: Optional[RewardSystem] = None


def get_reward_system() -> RewardSystem:
    global _instance
    if _instance is None:
        _instance = RewardSystem()
    return _instance
