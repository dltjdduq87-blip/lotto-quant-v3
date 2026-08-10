"""Descriptive statistics and number-relationship analysis over historical draws."""
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from lotto_quant_v3.config.settings import NUM_MIN, NUM_MAX


def draws_to_frame(draws: list[dict]) -> pd.DataFrame:
    rows = []
    for d in draws:
        rows.append({
            "round": d["round"],
            "date": d["draw_date"],
            "numbers": (d["n1"], d["n2"], d["n3"], d["n4"], d["n5"], d["n6"]),
            "bonus": d["bonus"],
        })
    return pd.DataFrame(rows).sort_values("round").reset_index(drop=True)


def number_frequency(df: pd.DataFrame) -> pd.Series:
    counts = Counter()
    for nums in df["numbers"]:
        counts.update(nums)
    freq = pd.Series({n: counts.get(n, 0) for n in range(NUM_MIN, NUM_MAX + 1)})
    return freq.sort_index()


def gap_since_last_seen(df: pd.DataFrame) -> pd.Series:
    """Rounds elapsed since each number last appeared (0 = appeared in the
    most recent draw), relative to the most recent round in df."""
    last_seen: dict[int, int] = {}
    for _, row in df.iterrows():
        for n in row["numbers"]:
            last_seen[n] = row["round"]
    latest_round = df["round"].max()
    gaps = {
        n: (latest_round - last_seen[n]) if n in last_seen else None
        for n in range(NUM_MIN, NUM_MAX + 1)
    }
    return pd.Series(gaps).sort_index()


def pair_cooccurrence(df: pd.DataFrame) -> pd.DataFrame:
    """Symmetric matrix counting how often each pair of numbers appeared
    together in the same draw."""
    matrix = np.zeros((NUM_MAX, NUM_MAX), dtype=int)
    for nums in df["numbers"]:
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                a, b = nums[i] - 1, nums[j] - 1
                matrix[a, b] += 1
                matrix[b, a] += 1
    return pd.DataFrame(matrix, index=range(NUM_MIN, NUM_MAX + 1),
                         columns=range(NUM_MIN, NUM_MAX + 1))


def sum_distribution(df: pd.DataFrame) -> pd.Series:
    return df["numbers"].apply(sum)


def odd_even_ratio(df: pd.DataFrame) -> pd.Series:
    return df["numbers"].apply(lambda nums: sum(1 for n in nums if n % 2 == 1))


def low_high_ratio(df: pd.DataFrame, threshold: int = 23) -> pd.Series:
    """Count of numbers <= threshold (default: bottom half of 1-45) per draw."""
    return df["numbers"].apply(lambda nums: sum(1 for n in nums if n <= threshold))


def summary_report(df: pd.DataFrame) -> dict:
    freq = number_frequency(df)
    gaps = gap_since_last_seen(df)
    sums = sum_distribution(df)
    odds = odd_even_ratio(df)
    return {
        "n_draws": len(df),
        "round_range": (int(df["round"].min()), int(df["round"].max())),
        "hottest": freq.sort_values(ascending=False).head(6).to_dict(),
        "coldest": freq.sort_values(ascending=True).head(6).to_dict(),
        "longest_absent": gaps.dropna().sort_values(ascending=False).head(6).to_dict(),
        "sum_mean": float(sums.mean()),
        "sum_std": float(sums.std()),
        "odd_count_mean": float(odds.mean()),
    }
