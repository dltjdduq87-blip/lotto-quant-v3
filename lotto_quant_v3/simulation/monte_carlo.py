"""Monte Carlo draw simulation for a portfolio of tickets."""
import numpy as np

from lotto_quant_v3.config.settings import NUM_MIN, NUM_MAX, PICK_SIZE
from lotto_quant_v3.portfolio.generator import Ticket


def simulate_portfolio(tickets: list[Ticket], n_draws: int = 100_000, seed: int | None = None) -> dict:
    """Draw `n_draws` random 6-number combinations and, for each, record the
    best (max) match count achieved by any ticket in the portfolio."""
    rng = np.random.default_rng(seed)
    pool = np.arange(NUM_MIN, NUM_MAX + 1)
    tickets_arr = np.array(tickets, dtype=np.int16)  # (n_tickets, 6)

    best_match = np.zeros(n_draws, dtype=np.int8)
    batch = min(n_draws, 200_000)
    done = 0
    while done < n_draws:
        this_batch = min(batch, n_draws - done)
        # Vectorized sampling-without-replacement: rank random keys per row,
        # take the lowest PICK_SIZE indices. Far faster than per-row rng.choice.
        rand_keys = rng.random((this_batch, pool.size))
        idx = np.argpartition(rand_keys, PICK_SIZE, axis=1)[:, :PICK_SIZE]
        draws = pool[idx]  # (this_batch, 6)

        batch_best = np.zeros(this_batch, dtype=np.int8)
        for t in tickets_arr:
            match_count = np.isin(draws, t).sum(axis=1)
            batch_best = np.maximum(batch_best, match_count)
        best_match[done:done + this_batch] = batch_best
        done += this_batch

    counts = {k: int((best_match == k).sum()) for k in range(0, PICK_SIZE + 1)}
    at_least = {k: int((best_match >= k).sum()) for k in range(0, PICK_SIZE + 1)}
    return {
        "n_draws": n_draws,
        "counts": counts,
        "probability_exactly": {k: v / n_draws for k, v in counts.items()},
        "probability_at_least": {k: v / n_draws for k, v in at_least.items()},
        "max_hit_ever": int(best_match.max()),
    }


def compare_to_exact(mc_result: dict, exact_result: dict) -> dict:
    """Sanity-check the Monte Carlo estimate against the exact enumeration
    (portfolio.probability.exact_portfolio_distribution)."""
    diffs = {}
    for k in range(0, PICK_SIZE + 1):
        mc_p = mc_result["probability_at_least"][k]
        exact_p = exact_result["exact_probability_at_least"][k]
        diffs[k] = {
            "monte_carlo": mc_p,
            "exact": exact_p,
            "abs_diff": abs(mc_p - exact_p),
        }
    return diffs
