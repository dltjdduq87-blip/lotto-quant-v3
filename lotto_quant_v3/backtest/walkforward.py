"""Walk-forward backtest with an explicit no-leakage guarantee.

For each historical round i, the portfolio tested against that round is
generated using ONLY draws strictly before round i (draws[:idx], never
draws[idx] or later). This is asserted at runtime, not just by convention.
"""
import numpy as np

from lotto_quant_v3.config.settings import PORTFOLIO_SIZE
from lotto_quant_v3.portfolio import generator
from lotto_quant_v3.statistics import analysis


def _weights_from_history(history_df) -> np.ndarray:
    freq = analysis.number_frequency(history_df)
    # +1 Laplace smoothing so cold/unseen numbers keep nonzero sampling weight
    return (freq.values + 1).astype(float)


def _best_match(portfolio: list[tuple], actual: tuple) -> int:
    actual_set = set(actual)
    return max(len(set(t) & actual_set) for t in portfolio)


def walk_forward_backtest(
    draws: list[dict],
    min_history: int = 52,
    portfolio_size: int = PORTFOLIO_SIZE,
    seed: int | None = 0,
) -> dict:
    df = analysis.draws_to_frame(draws)
    df = df.sort_values("round").reset_index(drop=True)

    v3_hits, baseline_hits = [], []
    tested_rounds = []
    rng_seed_stream = np.random.default_rng(seed)

    for idx in range(len(df)):
        if idx < min_history:
            continue
        history_df = df.iloc[:idx]          # strictly before idx
        target_row = df.iloc[idx]

        # Leakage guard: every round used for weighting must predate the target.
        assert history_df["round"].max() < target_row["round"], (
            f"data leakage detected at round {target_row['round']}"
        )

        weights = _weights_from_history(history_df)
        draw_seed = int(rng_seed_stream.integers(0, 2**31 - 1))
        v3_portfolio = generator.generate_portfolio(
            size=portfolio_size, weights=weights, seed=draw_seed
        )
        baseline_portfolio = generator.random_baseline_portfolio(
            size=portfolio_size, seed=draw_seed + 1
        )

        actual = target_row["numbers"]
        v3_hits.append(_best_match(v3_portfolio, actual))
        baseline_hits.append(_best_match(baseline_portfolio, actual))
        tested_rounds.append(int(target_row["round"]))

    v3_hits = np.array(v3_hits)
    baseline_hits = np.array(baseline_hits)

    def dist(arr):
        return {k: int((arr == k).sum()) for k in range(0, 7)}

    return {
        "n_tested_rounds": len(tested_rounds),
        "round_range": (tested_rounds[0], tested_rounds[-1]) if tested_rounds else None,
        "tested_round_numbers": tested_rounds,
        # Raw per-round paired arrays (index i = same round for both) --
        # required for a valid paired significance test. Do NOT reconstruct
        # these from the aggregated distributions below; that discards the
        # round-to-round pairing and invalidates paired-test results.
        "v3_hits_by_round": v3_hits.tolist(),
        "baseline_hits_by_round": baseline_hits.tolist(),
        "v3_hit_distribution": dist(v3_hits),
        "baseline_hit_distribution": dist(baseline_hits),
        "v3_mean_best_match": float(v3_hits.mean()) if len(v3_hits) else None,
        "baseline_mean_best_match": float(baseline_hits.mean()) if len(baseline_hits) else None,
        "v3_hits_ge3": int((v3_hits >= 3).sum()),
        "baseline_hits_ge3": int((baseline_hits >= 3).sum()),
    }
