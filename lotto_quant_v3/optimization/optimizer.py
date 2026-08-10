"""Portfolio optimization: coverage diversification, not prediction.

Lotto draws are IID uniform random (confirmed by the backtest/significance
modules finding no historically-weighted edge). What a portfolio CAN
meaningfully optimize for is board coverage: given a fixed number of tickets,
spread them across the 1-45 range and avoid redundant number overlap between
tickets, so the portfolio covers more of the number space and avoids
clustering in statistically atypical sum/odd-even bands. This does not
change the portfolio's exact jackpot probability (still n_tickets /
C(45,6), see portfolio.probability) -- it only shapes which numbers are
covered.
"""
import numpy as np

from lotto_quant_v3.config.settings import PORTFOLIO_SIZE
from lotto_quant_v3.portfolio.generator import Ticket, sample_ticket, validate_portfolio


def _overlap_penalty(candidate: Ticket, chosen: list[Ticket]) -> int:
    return sum(len(set(candidate) & set(t)) for t in chosen)


def _sum_band_penalty(candidate: Ticket, target_mean: float, target_std: float) -> float:
    s = sum(candidate)
    return abs(s - target_mean) / max(target_std, 1e-6)


def optimize_portfolio(
    weights: np.ndarray | None = None,
    size: int = PORTFOLIO_SIZE,
    target_sum_mean: float = 138.0,  # theoretical mean of 6 draws from 1..45
    target_sum_std: float = 30.0,
    candidate_pool: int = 500,
    seed: int | None = None,
) -> list[Ticket]:
    """Greedy diversification: build a large candidate pool (optionally
    frequency-weighted), then greedily pick `size` tickets that minimize
    number overlap with already-chosen tickets while staying near the
    historically-typical sum band."""
    rng = np.random.default_rng(seed)
    candidates: set[Ticket] = set()
    guard = 0
    while len(candidates) < candidate_pool and guard < candidate_pool * 20:
        candidates.add(sample_ticket(rng, weights))
        guard += 1
    candidates = list(candidates)

    chosen: list[Ticket] = []
    remaining = candidates[:]
    while len(chosen) < size and remaining:
        scored = sorted(
            remaining,
            key=lambda c: (
                _overlap_penalty(c, chosen),
                _sum_band_penalty(c, target_sum_mean, target_sum_std),
            ),
        )
        pick = scored[0]
        chosen.append(pick)
        remaining.remove(pick)

    while len(chosen) < size:  # candidate pool exhausted (shouldn't happen normally)
        t = _sample_ticket(rng, weights)
        if t not in chosen:
            chosen.append(t)

    validate_portfolio(chosen)
    return sorted(chosen)


def coverage_stats(tickets: list[Ticket]) -> dict:
    all_numbers = [n for t in tickets for n in t]
    unique_numbers = set(all_numbers)
    return {
        "n_tickets": len(tickets),
        "unique_numbers_covered": len(unique_numbers),
        "coverage_ratio": len(unique_numbers) / 45,
        "max_possible_unique": min(len(tickets) * 6, 45),
    }
