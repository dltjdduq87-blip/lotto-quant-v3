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


def compare_candidates(
    candidates: list[Ticket],
    n_draws: int = 5_000_000,
    seed: int | None = None,
    batch_size: int = 1_000_000,
) -> dict:
    """Score many single-ticket candidates against the SAME large batch of
    simulated draws to test whether any one of them has a real edge over
    the others. Uses a matmul-based scorer (draw-indicator @ candidate-mask.T)
    instead of a per-candidate Python loop, so it scales to tens of millions
    of draws interactively (~2M draws x 100 candidates in a few seconds).

    Every ticket has an IDENTICAL theoretical expected match count
    (PICK_SIZE^2 / pool_size, i.e. 0.8 for 6/45) by symmetry -- a fair draw
    cannot favor one combination over another. Any observed spread across
    candidates should be fully explained by sampling noise (~1/sqrt(n_draws)).
    This function reports that comparison directly (z-score vs the
    theoretical mean, using each candidate's own empirical standard error)
    instead of just asserting "it's noise" without showing the check.
    """
    pool_size = NUM_MAX - NUM_MIN + 1
    n_candidates = len(candidates)
    cand_mask = np.zeros((n_candidates, pool_size), dtype=np.float32)
    for i, tk in enumerate(candidates):
        for n in tk:
            cand_mask[i, n - 1] = 1.0

    rng = np.random.default_rng(seed)
    sum_x = np.zeros(n_candidates, dtype=np.float64)
    sum_x2 = np.zeros(n_candidates, dtype=np.float64)

    done = 0
    while done < n_draws:
        this_batch = min(batch_size, n_draws - done)
        rand_keys = rng.random((this_batch, pool_size), dtype=np.float32)
        idx = np.argpartition(rand_keys, PICK_SIZE, axis=1)[:, :PICK_SIZE]
        draw_ind = np.zeros((this_batch, pool_size), dtype=np.float32)
        rows = np.repeat(np.arange(this_batch), PICK_SIZE)
        draw_ind[rows, idx.ravel()] = 1.0
        m = draw_ind @ cand_mask.T  # (this_batch, n_candidates)
        sum_x += m.sum(axis=0)
        sum_x2 += (m.astype(np.float64) ** 2).sum(axis=0)
        done += this_batch

    means = sum_x / n_draws
    variances = np.maximum(sum_x2 / n_draws - means ** 2, 0.0)
    sems = np.sqrt(variances / n_draws)
    theoretical_mean = PICK_SIZE * PICK_SIZE / pool_size
    safe_sems = np.where(sems > 0, sems, 1.0)
    z_scores = (means - theoretical_mean) / safe_sems

    order = np.argsort(-means)
    ranked = [
        {
            "rank": rank + 1,
            "ticket": candidates[i],
            "mean_matches": float(means[i]),
            "z_vs_theoretical": float(z_scores[i]),
        }
        for rank, i in enumerate(order)
    ]

    max_abs_z = float(np.max(np.abs(z_scores)))
    return {
        "n_draws": n_draws,
        "n_candidates": n_candidates,
        "theoretical_mean": theoretical_mean,
        "mean_across_candidates": float(means.mean()),
        "std_across_candidates": float(means.std()),
        "expected_noise_std": float(np.sqrt(variances.mean() / n_draws)),
        "spread": float(means.max() - means.min()),
        "max_abs_z": max_abs_z,
        "ranked": ranked,
        "verdict": (
            "관측된 순위 차이가 전부 표본오차(노이즈) 범위 안에 있음 -- "
            "통계적으로 유의한 승자 없음"
            if max_abs_z < 3.0 else
            f"|z|={max_abs_z:.2f}로 3-시그마를 넘는 후보가 있음 -- 후보 수가 많으면 "
            "다중검정으로 우연히 발생할 수 있으므로, 시드를 바꿔도 같은 후보가 "
            "1위를 유지하는지 반드시 재현 확인할 것 (통상 재현 안 됨)"
        ),
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
