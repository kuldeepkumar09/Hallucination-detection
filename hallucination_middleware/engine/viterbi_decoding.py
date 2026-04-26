"""Viterbi Algorithm — decodes the most likely hidden state sequence from observations.

Used by HMMReliabilityTracker as fallback when hmmlearn is unavailable.
Implements forward-backward Viterbi for Gaussian emission HMM.
"""
import math
from typing import List
import numpy as np


def _gaussian_log_prob(x: float, mean: float, std: float) -> float:
    """Log-probability of x under N(mean, std²)."""
    return -0.5 * ((x - mean) / std) ** 2 - math.log(std * math.sqrt(2 * math.pi))


def viterbi_decode(
    observations: List[float],
    transition: np.ndarray,
    emission_means: np.ndarray,
    emission_stds: np.ndarray,
    initial: np.ndarray,
) -> List[int]:
    """
    Viterbi decoder for Gaussian HMM.

    Args:
        observations : sequence of float scores (e.g. NLI confidence)
        transition   : (n_states, n_states) row-stochastic transition matrix
        emission_means: (n_states,) Gaussian mean per state
        emission_stds : (n_states,) Gaussian std per state
        initial       : (n_states,) initial state probability vector

    Returns:
        List[int] — most probable hidden state index per timestep
    """
    n_states = len(initial)
    T = len(observations)

    if T == 0:
        return []

    log_trans = np.log(transition + 1e-10)
    log_init = np.log(initial + 1e-10)

    viterbi = np.full((T, n_states), -np.inf)
    backptr = np.zeros((T, n_states), dtype=int)

    # Initialise t=0
    for s in range(n_states):
        emit = _gaussian_log_prob(observations[0], emission_means[s], emission_stds[s])
        viterbi[0, s] = log_init[s] + emit

    # Forward pass
    for t in range(1, T):
        for s in range(n_states):
            emit = _gaussian_log_prob(observations[t], emission_means[s], emission_stds[s])
            candidates = viterbi[t - 1, :] + log_trans[:, s]
            best_prev = int(np.argmax(candidates))
            viterbi[t, s] = candidates[best_prev] + emit
            backptr[t, s] = best_prev

    # Backtrack
    states = [0] * T
    states[T - 1] = int(np.argmax(viterbi[T - 1, :]))
    for t in range(T - 2, -1, -1):
        states[t] = backptr[t + 1, states[t + 1]]

    return states
