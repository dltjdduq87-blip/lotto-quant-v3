"""Statistical significance testing for backtest results.

Lotto 6/45 draws are (by design and regulation) IID uniform random. The
honest null hypothesis for any "smart" portfolio strategy is that it
performs no better than a uniform-random baseline. This module tests
whether a backtest's observed difference is large enough to reject that
null, rather than just reporting a raw mean difference.
"""
import numpy as np
from scipy import stats


def compare_strategies(v3_hits: list[int] | np.ndarray, baseline_hits: list[int] | np.ndarray) -> dict:
    v3 = np.asarray(v3_hits, dtype=float)
    base = np.asarray(baseline_hits, dtype=float)
    assert len(v3) == len(base), "paired comparison requires equal-length samples"

    diff = v3 - base
    t_stat, t_p = stats.ttest_rel(v3, base)
    try:
        w_stat, w_p = stats.wilcoxon(v3, base)
    except ValueError:
        # all-zero differences etc.
        w_stat, w_p = float("nan"), float("nan")

    return {
        "n": len(v3),
        "v3_mean": float(v3.mean()),
        "baseline_mean": float(base.mean()),
        "mean_diff": float(diff.mean()),
        "paired_ttest": {"statistic": float(t_stat), "p_value": float(t_p)},
        "wilcoxon_signed_rank": {"statistic": float(w_stat), "p_value": float(w_p)},
        "significant_at_0.05": bool(t_p < 0.05),
        "interpretation": (
            "Statistically significant difference from random baseline (p<0.05)."
            if t_p < 0.05 else
            "No statistically significant edge over random baseline (p>=0.05) - "
            "consistent with Lotto draws being IID uniform random."
        ),
    }
