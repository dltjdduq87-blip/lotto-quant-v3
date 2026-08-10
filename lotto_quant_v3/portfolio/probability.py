"""Exact (full-enumeration) portfolio probability calculation.

Section 19 of the spec is explicit that a portfolio's win probability must
NOT be computed with a naive independent-events formula, because the 5
tickets' match-count events are correlated (they share the same draw, and
may share individual numbers with each other). The only fully correct
closed-form treatment requires inclusion-exclusion terms that depend on the
pairwise/triple/... overlaps between tickets -- fragile to get right by
hand. Instead we compute the EXACT answer by enumerating all
C(45,6) = 8,145,060 possible draws (cheap enough to brute-force with numpy)
and directly tallying, for each possible draw, the best result any ticket
in the portfolio would achieve. This is not an approximation.
"""
import itertools

import numpy as np

from lotto_quant_v3.config.settings import NUM_MIN, NUM_MAX, PICK_SIZE
from lotto_quant_v3.probability.engine import TOTAL_COMBINATIONS
from lotto_quant_v3.portfolio.generator import Ticket


def _all_combinations_array() -> np.ndarray:
    """All C(45,6) draws as an (N, 6) int8 array of numbers in [1,45]."""
    n = NUM_MAX - NUM_MIN + 1
    flat = np.fromiter(
        itertools.chain.from_iterable(itertools.combinations(range(NUM_MIN, NUM_MAX + 1), PICK_SIZE)),
        dtype=np.int8,
        count=TOTAL_COMBINATIONS * PICK_SIZE,
    )
    return flat.reshape(-1, PICK_SIZE)


def exact_portfolio_distribution(tickets: list[Ticket]) -> dict:
    """Return the exact distribution of "best ticket match count" over all
    possible draws, plus exact tier probabilities for the portfolio as a
    whole. O(C(45,6) * len(tickets)) time, ~a few seconds for 5 tickets."""
    combos = _all_combinations_array()  # (8145060, 6)
    best_match = np.zeros(combos.shape[0], dtype=np.int8)
    for ticket in tickets:
        ticket_arr = np.array(ticket, dtype=np.int8)
        match_count = np.isin(combos, ticket_arr).sum(axis=1)
        best_match = np.maximum(best_match, match_count)

    counts = {k: int((best_match == k).sum()) for k in range(0, PICK_SIZE + 1)}
    at_least = {k: int((best_match >= k).sum()) for k in range(0, PICK_SIZE + 1)}

    total = combos.shape[0]
    assert total == TOTAL_COMBINATIONS

    return {
        "n_tickets": len(tickets),
        "total_draws": total,
        "exact_counts": counts,
        "exact_probability_exactly": {k: v / total for k, v in counts.items()},
        "exact_probability_at_least": {k: v / total for k, v in at_least.items()},
        "jackpot_ways": counts[PICK_SIZE],
        "jackpot_probability": counts[PICK_SIZE] / total,
        "jackpot_probability_naive_sum": len(tickets) / total,
    }
