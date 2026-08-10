"""Exact combinatorial probability engine for Lotto 6/45.

Prize tiers (Korean Lotto 6/45 official rules):
  1st: match all 6 main numbers
  2nd: match 5 main numbers + the bonus number
  3rd: match 5 main numbers (no bonus)
  4th: match 4 main numbers
  5th: match 3 main numbers
"""
from dataclasses import dataclass
from math import comb

from lotto_quant_v3.config.settings import NUM_MIN, NUM_MAX, PICK_SIZE

POOL_SIZE = NUM_MAX - NUM_MIN + 1  # 45
TOTAL_COMBINATIONS = comb(POOL_SIZE, PICK_SIZE)  # C(45,6) = 8,145,060


@dataclass(frozen=True)
class PrizeTier:
    tier: int
    label: str
    match_main: int
    match_bonus: bool
    ways: int

    @property
    def probability(self) -> float:
        return self.ways / TOTAL_COMBINATIONS


def _ways_tier5_or_4(match_main: int) -> int:
    """3rd/4th/5th-tier-style ways where the bonus number is NOT special-cased
    (it's folded into the 38 'other' numbers, i.e. treated as any non-winning
    number, per official rule: only tier 2 cares about the bonus number)."""
    other_pool = POOL_SIZE - PICK_SIZE  # 39 numbers (38 others + 1 bonus)
    remaining = PICK_SIZE - match_main
    return comb(PICK_SIZE, match_main) * comb(other_pool, remaining)


def build_prize_table() -> list[PrizeTier]:
    other_pool_excl_bonus = POOL_SIZE - PICK_SIZE - 1  # 38

    # Tier 1: all 6 main numbers, bonus irrelevant (there's exactly 1 way)
    tier1_ways = comb(PICK_SIZE, 6)

    # Tier 2: exactly 5 main numbers AND the bonus number
    tier2_ways = comb(PICK_SIZE, 5) * comb(1, 1)

    # Tier 3: exactly 5 main numbers, bonus NOT included
    tier3_ways = comb(PICK_SIZE, 5) * comb(other_pool_excl_bonus, 1)

    # Tier 4: exactly 4 main numbers (bonus number status doesn't matter,
    # remaining 2 picks come from the 39 non-tier-1 numbers, which includes
    # the bonus number as an ordinary number for this tier)
    tier4_ways = _ways_tier5_or_4(4)

    # Tier 5: exactly 3 main numbers
    tier5_ways = _ways_tier5_or_4(3)

    return [
        PrizeTier(1, "1st (6 main)", 6, False, tier1_ways),
        PrizeTier(2, "2nd (5 main + bonus)", 5, True, tier2_ways),
        PrizeTier(3, "3rd (5 main)", 5, False, tier3_ways),
        PrizeTier(4, "4th (4 main)", 4, False, tier4_ways),
        PrizeTier(5, "5th (3 main)", 3, False, tier5_ways),
    ]


def summarize() -> dict:
    table = build_prize_table()
    return {
        "total_combinations": TOTAL_COMBINATIONS,
        "tiers": {
            t.tier: {
                "label": t.label,
                "ways": t.ways,
                "probability": t.probability,
                "odds_1_in": TOTAL_COMBINATIONS / t.ways if t.ways else None,
            }
            for t in table
        },
    }


if __name__ == "__main__":
    assert TOTAL_COMBINATIONS == 8_145_060, TOTAL_COMBINATIONS
    for tier, info in summarize()["tiers"].items():
        print(f"Tier {tier} ({info['label']}): ways={info['ways']:,} "
              f"p={info['probability']:.10f} odds=1/{info['odds_1_in']:.1f}")
    print(f"C(45,6) = {TOTAL_COMBINATIONS:,}")
