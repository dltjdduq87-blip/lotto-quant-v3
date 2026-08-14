"""Rigorous randomness/uniformity hypothesis testing for the draw history.

This module does NOT predict anything. It tests the null hypothesis that
Lotto 6/45 draws are i.i.d. uniform random -- the same hypothesis the
walk-forward backtest (backtest/walkforward.py) already supports empirically
by finding no exploitable edge. These tests interrogate the *mechanism*
more directly: is the marginal distribution over 1-45 uniform, are
consecutive draws independent, is there detectable structure (runs,
autocorrelation) at all. A statistically literate reader should expect
every test here to fail to reject the null -- that is the CORRECT and
EXPECTED outcome for a fair draw, not a limitation of the analysis.
"""
import numpy as np
from scipy import stats

from lotto_quant_v3.config.settings import NUM_MIN, NUM_MAX, PICK_SIZE
from lotto_quant_v3.statistics.analysis import number_frequency, sum_distribution

ALPHA = 0.05


def chi_square_uniformity(df) -> dict:
    """H0: every number 1-45 is equally likely to be drawn.
    Expected count per number over N draws of 6 numbers each = N*6/45."""
    freq = number_frequency(df)
    n_draws = len(df)
    expected = n_draws * PICK_SIZE / (NUM_MAX - NUM_MIN + 1)
    chi2, p = stats.chisquare(freq.values, f_exp=[expected] * len(freq))
    return {
        "test": "Chi-square goodness-of-fit (uniformity)",
        "statistic": float(chi2),
        "dof": len(freq) - 1,
        "p_value": float(p),
        "reject_null_at_0.05": bool(p < ALPHA),
        "interpretation": (
            "번호별 출현 빈도가 균등분포에서 통계적으로 유의하게 벗어남 (p<0.05)"
            if p < ALPHA else
            "번호별 출현 빈도가 균등분포와 통계적으로 다르다고 볼 근거 없음 (귀무가설 기각 안 됨)"
        ),
    }


def runs_test(df, statistic: str = "sum") -> dict:
    """Wald-Wolfowitz runs test: binarize each draw's `statistic` (default:
    sum of its 6 numbers) above/below the median, then test whether the
    number of runs (consecutive same-side streaks) across rounds matches
    what pure randomness predicts. Too few runs -> clustering; too many ->
    excessive alternation. Either would indicate the draw mechanism is not
    memoryless."""
    if statistic == "sum":
        series = sum_distribution(df).to_numpy()
    else:
        raise ValueError(f"unknown statistic: {statistic}")

    median = np.median(series)
    binary = series > median
    binary = binary[series != median]  # drop ties, standard practice
    n1 = int(binary.sum())
    n2 = int((~binary).sum())
    n = n1 + n2

    runs = 1 + int(np.sum(binary[1:] != binary[:-1]))

    mu = 2 * n1 * n2 / n + 1
    var = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n ** 2 * (n - 1))
    z = (runs - mu) / np.sqrt(var)
    p = 2 * (1 - stats.norm.cdf(abs(z)))

    return {
        "test": "Wald-Wolfowitz runs test (above/below median draw-sum)",
        "n_rounds": n,
        "observed_runs": runs,
        "expected_runs": float(mu),
        "z_statistic": float(z),
        "p_value": float(p),
        "reject_null_at_0.05": bool(p < ALPHA),
        "interpretation": (
            "회차 간 패턴(연속/교대 편향)이 통계적으로 유의하게 존재함 (p<0.05)"
            if p < ALPHA else
            "회차 간 무작위성을 기각할 근거 없음 (연속/교대 편향 없음)"
        ),
    }


def autocorrelation_test(df, max_lag: int = 3) -> dict:
    """Pearson correlation between draw-sum at round t and round t+lag, for
    lag = 1..max_lag. A truly memoryless process has zero autocorrelation
    at every lag (up to sampling noise)."""
    series = sum_distribution(df).to_numpy()
    results = {}
    for lag in range(1, max_lag + 1):
        r, p = stats.pearsonr(series[:-lag], series[lag:])
        results[f"lag_{lag}"] = {
            "correlation": float(r),
            "p_value": float(p),
            "reject_null_at_0.05": bool(p < ALPHA),
        }
    any_significant = any(v["reject_null_at_0.05"] for v in results.values())
    return {
        "test": "Autocorrelation of draw-sum (lag 1-{})".format(max_lag),
        "lags": results,
        "interpretation": (
            "적어도 한 지연(lag)에서 유의한 자기상관 존재 (p<0.05) -- 다중검정 보정 필요"
            if any_significant else
            "모든 지연에서 유의한 자기상관 없음 (회차 간 독립성과 일치)"
        ),
    }


def entropy_analysis(df) -> dict:
    """Shannon entropy of the empirical number-frequency distribution vs.
    the theoretical maximum (perfectly uniform over 45 numbers). Ratio close
    to 1 means the empirical distribution is close to maximally uncertain
    (i.e. indistinguishable from uniform), which is what a fair draw
    predicts."""
    freq = number_frequency(df)
    total = freq.sum()
    p = freq.values / total
    p_nonzero = p[p > 0]
    h = float(-np.sum(p_nonzero * np.log2(p_nonzero)))
    h_max = float(np.log2(len(freq)))
    return {
        "test": "Shannon entropy of number-frequency distribution",
        "entropy_bits": h,
        "max_entropy_bits": h_max,
        "ratio_to_max": h / h_max,
        "interpretation": (
            f"엔트로피 비율 {h/h_max:.4f} (1.0 = 완전 균등분포). "
            + ("1에 매우 근접 -- 균등분포와 구분 불가" if h / h_max > 0.995
               else "1에서 다소 벗어남 -- 표본 크기 대비 재검토 필요")
        ),
    }


def summarize_randomness(df) -> dict:
    chi2 = chi_square_uniformity(df)
    runs = runs_test(df)
    autocorr = autocorrelation_test(df)
    entropy = entropy_analysis(df)

    tests_rejecting_null = sum([
        chi2["reject_null_at_0.05"],
        runs["reject_null_at_0.05"],
        any(v["reject_null_at_0.05"] for v in autocorr["lags"].values()),
    ])

    return {
        "n_draws_tested": len(df),
        "chi_square_uniformity": chi2,
        "runs_test": runs,
        "autocorrelation": autocorr,
        "entropy": entropy,
        "tests_rejecting_null_of_3": tests_rejecting_null,
        "overall_conclusion": (
            "모든 정밀 검정을 통과 -- i.i.d. 균등분포 가설과 완전히 일치. "
            "예측 가능한 구조가 존재한다는 증거 없음."
            if tests_rejecting_null == 0 else
            f"{tests_rejecting_null}개 검정에서 귀무가설 기각 (p<0.05) -- "
            "다중검정 시 5%는 우연히 기각될 수 있으므로 (multiple testing), "
            "단일 결과만으로 비무작위성을 결론짓지 말 것. Bonferroni 등 보정 후 재검토 권장."
        ),
    }
