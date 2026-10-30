"""Exact (full-enumeration) portfolio probability calculation.

A portfolio's tickets share the same draw (and may share numbers), so their win events are
correlated and the naive "add up the single-ticket odds" formula is wrong. Instead we enumerate
all C(45,6) = 8,145,060 possible main draws (as 45-bit masks, popcount for match counts) and,
for each draw, find the best result any ticket achieves. The bonus ball is handled exactly too:
given a main draw, the bonus is uniform over the 39 numbers not drawn, so a draw where some
ticket matches 5 gives tier 2 with probability |B| / 39, where B is the set of "missing sixth
numbers" of the tickets that matched 5. Nothing here is sampled -- it is exact.
"""
from functools import lru_cache

import numpy as np

from lotto_quant_v3.config.settings import NUM_MAX, NUM_MIN, PICK_SIZE
from lotto_quant_v3.portfolio.generator import Ticket
from lotto_quant_v3.probability.engine import TOTAL_COMBINATIONS

POOL = NUM_MAX - NUM_MIN + 1
N_NON_DRAWN = POOL - PICK_SIZE  # 39 candidates for the bonus ball


@lru_cache(maxsize=1)
def all_draw_masks() -> np.ndarray:
    """All C(45,6) draws as int64 bitmasks (bit i = number i+1), built combinatorially in numpy."""
    masks = np.left_shift(np.int64(1), np.arange(POOL, dtype=np.int64))
    last = np.arange(POOL, dtype=np.int64)
    for _ in range(PICK_SIZE - 1):
        nxt_counts = POOL - 1 - last          # numbers greater than the current largest
        rep = np.repeat(np.arange(len(masks)), nxt_counts)
        offs = np.arange(len(rep)) - np.repeat(np.cumsum(nxt_counts) - nxt_counts, nxt_counts)
        new_last = last[rep] + 1 + offs
        masks = masks[rep] | np.left_shift(np.int64(1), new_last)
        last = new_last
    assert len(masks) == TOTAL_COMBINATIONS
    masks.setflags(write=False)
    return masks


def ticket_mask(ticket) -> int:
    m = 0
    for n in ticket:
        m |= 1 << (int(n) - NUM_MIN)
    return m


def exact_portfolio_distribution(tickets: list[Ticket]) -> dict:
    """Exact distribution of the portfolio's best match count AND best prize tier (incl. bonus)."""
    draws = all_draw_masks()
    total = len(draws)
    tmasks = [ticket_mask(t) for t in tickets]
    match = np.stack([np.bitwise_count(draws & np.int64(m)).astype(np.int8) for m in tmasks])  # (T, N)
    best_match = match.max(axis=0)

    counts = np.bincount(best_match, minlength=PICK_SIZE + 1)
    at_least = counts[::-1].cumsum()[::-1]

    # best tier per draw, with the bonus ball integrated out exactly
    p_tier = np.zeros(6)  # index = tier, 0 = nothing
    p_tier[1] = counts[6] / total
    p_tier[4] = counts[4] / total
    p_tier[5] = counts[3] / total
    p_tier[0] = counts[:3].sum() / total
    five = np.flatnonzero(best_match == 5)
    tier2_weight = 0.0
    if len(five):
        sub = match[:, five] == 5  # (T, n5)
        for col, d in enumerate(draws[five]):
            missing = {tmasks[i] & ~int(d) for i in np.flatnonzero(sub[:, col])}
            tier2_weight += len(missing) / N_NON_DRAWN
    p_tier[2] = tier2_weight / total
    p_tier[3] = (len(five) - tier2_weight) / total

    p_at_least_tier = {k: float(p_tier[1:k + 1].sum()) for k in range(1, 6)}
    return {
        "n_tickets": len(tickets),
        "total_draws": total,
        "exact_counts": {k: int(counts[k]) for k in range(PICK_SIZE + 1)},
        "exact_probability_exactly": {k: float(counts[k] / total) for k in range(PICK_SIZE + 1)},
        "exact_probability_at_least": {k: float(at_least[k] / total) for k in range(PICK_SIZE + 1)},
        "best_tier_probability": {k: float(p_tier[k]) for k in range(6)},
        "at_least_tier_probability": p_at_least_tier,
        "any_prize_probability": p_at_least_tier[5],
        # per-ticket wins add up linearly, so the expected number of winning games is exact & simple
        "expected_winning_games": float(len(tickets) * _single_any_prize()),
        "jackpot_ways": int(counts[PICK_SIZE]),
        "jackpot_probability": float(counts[PICK_SIZE] / total),
        "jackpot_probability_naive_sum": len(tickets) / total,
        "overlap_loss": float(len(tickets) * _single_any_prize() - p_at_least_tier[5]),
    }


@lru_cache(maxsize=1)
def _single_any_prize() -> float:
    from lotto_quant_v3.probability import engine
    return float(sum(t.probability for t in engine.build_prize_table()))
