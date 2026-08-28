"""Core correctness tests (stdlib unittest -- no extra test-runner dependency).

Run with:  python -m unittest lotto_quant_v3.tests.test_core -v
(from the project root)
"""
import unittest
from datetime import date

import numpy as np
import pandas as pd

from lotto_quant_v3.data import news_search
from lotto_quant_v3.data.excel_import import round_to_date
from lotto_quant_v3.portfolio import generator, probability
from lotto_quant_v3.probability import engine
from lotto_quant_v3.simulation import monte_carlo
from lotto_quant_v3.statistics import randomness_tests


class TestProbabilityEngine(unittest.TestCase):
    def test_total_combinations(self):
        self.assertEqual(engine.TOTAL_COMBINATIONS, 8_145_060)

    def test_prize_tier_odds_match_official(self):
        summary = engine.summarize()
        tiers = summary["tiers"]
        # Officially published odds (rounded), used as a sanity anchor.
        self.assertEqual(tiers[1]["ways"], 1)
        self.assertAlmostEqual(tiers[2]["odds_1_in"], 1_357_510, delta=1)
        self.assertAlmostEqual(tiers[3]["odds_1_in"], 35_724, delta=1)
        self.assertAlmostEqual(tiers[4]["odds_1_in"], 733, delta=1)
        self.assertAlmostEqual(tiers[5]["odds_1_in"], 45, delta=1)

    def test_ways_sum_less_than_total(self):
        # tiers are disjoint match-count buckets; their ways must not exceed total combos
        summary = engine.summarize()
        total_ways = sum(t["ways"] for t in summary["tiers"].values())
        self.assertLess(total_ways, engine.TOTAL_COMBINATIONS)


class TestPortfolioGenerator(unittest.TestCase):
    def test_portfolio_is_valid_and_distinct(self):
        tickets = generator.generate_portfolio(size=5, seed=123)
        self.assertEqual(len(tickets), 5)
        generator.validate_portfolio(tickets)  # raises on any violation

    def test_reproducible_with_seed(self):
        a = generator.generate_portfolio(size=5, seed=99)
        b = generator.generate_portfolio(size=5, seed=99)
        self.assertEqual(a, b)


class TestPortfolioProbabilityExact(unittest.TestCase):
    def test_jackpot_probability_equals_n_over_total(self):
        tickets = generator.generate_portfolio(size=5, seed=1)
        result = probability.exact_portfolio_distribution(tickets)
        self.assertEqual(result["jackpot_ways"], 5)
        self.assertAlmostEqual(result["jackpot_probability"], 5 / 8_145_060, places=12)
        # For the jackpot tier specifically, tickets are mutually exclusive
        # (only one combo is drawn), so exact == naive sum -- this equality
        # is a genuine identity here, not evidence that independent-event
        # math is valid for the other tiers (it is not; see monte carlo vs
        # exact-enumeration cross-check in simulation/monte_carlo.py).
        self.assertEqual(result["jackpot_probability"], result["jackpot_probability_naive_sum"])


class TestRoundToDate(unittest.TestCase):
    def test_known_anchor_round_1236(self):
        # Independently confirmed via 3 sources: user's Excel export,
        # lottolyzer.com/pyony.com scraping, and Google News search.
        self.assertEqual(round_to_date(1236), "2026-08-08")

    def test_round_1_is_first_draw_date(self):
        self.assertEqual(round_to_date(1), "2002-12-07")


class TestNewsSearchParsing(unittest.TestCase):
    def test_extracts_comma_separated_numbers_and_bonus(self):
        title = "1236회 로또 1등 12, 18, 21, 29, 34, 38…보너스 10 - 뉴시스"
        tickets, bonus = news_search._extract_candidates(title)
        self.assertIn((12, 18, 21, 29, 34, 38), tickets)
        self.assertEqual(bonus, 10)

    def test_extracts_middle_dot_separated_numbers_unordered(self):
        title = "[속보] 로또 1236회 당첨번호, '18·12·29·38·21·34'...보너스 '10'"
        tickets, bonus = news_search._extract_candidates(title)
        self.assertIn((12, 18, 21, 29, 34, 38), tickets)  # sorted regardless of source order
        self.assertEqual(bonus, 10)

    def test_ignores_titles_without_six_valid_numbers(self):
        title = "1236회 로또 1등 11명…당첨금 각 24억4천만원(종합) - 연합뉴스"
        tickets, bonus = news_search._extract_candidates(title)
        self.assertEqual(tickets, [])

    def test_most_recent_draw_round_matches_known_anchor(self):
        # 2026-08-08 (Saturday) was round 1236; the following Saturday
        # (2026-08-15) is round 1237.
        self.assertEqual(news_search.most_recent_draw_round(date(2026, 8, 8)), 1236)
        self.assertEqual(news_search.most_recent_draw_round(date(2026, 8, 10)), 1236)
        self.assertEqual(news_search.most_recent_draw_round(date(2026, 8, 15)), 1237)


def _synthetic_uniform_df(n=2000, seed=0):
    """Genuinely random draws -- the tests should NOT flag these."""
    rng = np.random.default_rng(seed)
    rows = [tuple(sorted(rng.choice(range(1, 46), size=6, replace=False))) for _ in range(n)]
    return pd.DataFrame({"numbers": rows})


def _synthetic_biased_df(n=500, seed=0):
    """Number 1 forced into every draw -- wildly non-uniform on purpose, so
    the chi-square/entropy tests MUST flag it. This is the power check: a
    test suite that never rejects anything, even on rigged data, is useless."""
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(n):
        rest = sorted(rng.choice(range(2, 46), size=5, replace=False))
        rows.append(tuple([1] + rest))
    return pd.DataFrame({"numbers": rows})


def _synthetic_trending_df(n=200):
    """Monotonically increasing draw-sum -- a deterministic trend, the
    opposite of memoryless. The runs test MUST flag this (far too few runs)."""
    rows = [(1, 2, 3, 4, 5, 6 + i) for i in range(n) if 6 + i <= 45]
    return pd.DataFrame({"numbers": rows})


class TestRandomnessTestsPower(unittest.TestCase):
    """Sanity checks that the hypothesis tests actually have statistical
    power -- i.e. they can and do reject the null on rigged synthetic data,
    not just rubber-stamp everything as random."""

    def test_chi_square_passes_true_uniform_data(self):
        df = _synthetic_uniform_df(n=3000, seed=1)
        result = randomness_tests.chi_square_uniformity(df)
        self.assertFalse(result["reject_null_at_0.05"])

    def test_chi_square_flags_biased_data(self):
        df = _synthetic_biased_df(n=500, seed=2)
        result = randomness_tests.chi_square_uniformity(df)
        self.assertTrue(result["reject_null_at_0.05"])
        self.assertLess(result["p_value"], 1e-10)

    def test_entropy_lower_for_biased_data(self):
        uniform = randomness_tests.entropy_analysis(_synthetic_uniform_df(n=3000, seed=3))
        biased = randomness_tests.entropy_analysis(_synthetic_biased_df(n=500, seed=4))
        self.assertGreater(uniform["ratio_to_max"], biased["ratio_to_max"])

    def test_runs_test_flags_monotonic_trend(self):
        df = _synthetic_trending_df(n=100)
        result = randomness_tests.runs_test(df)
        self.assertTrue(result["reject_null_at_0.05"])
        self.assertLess(result["observed_runs"], result["expected_runs"])

    def test_summarize_runs_without_error_on_real_shaped_data(self):
        df = _synthetic_uniform_df(n=500, seed=5)
        summary = randomness_tests.summarize_randomness(df)
        self.assertEqual(summary["n_draws_tested"], 500)
        self.assertIn("overall_conclusion", summary)


class TestMonteCarloCompareCandidates(unittest.TestCase):
    def test_means_converge_to_theoretical_value(self):
        candidates = generator.generate_portfolio(size=20, seed=10)
        result = monte_carlo.compare_candidates(candidates, n_draws=500_000, seed=11)
        self.assertAlmostEqual(result["mean_across_candidates"], result["theoretical_mean"], delta=0.01)

    def test_no_ticket_beats_another_beyond_noise_in_expectation(self):
        # Every ticket has the same theoretical mean by symmetry -- with a
        # reasonable candidate count and draw count, no z-score should blow
        # past a generous sanity bound (this isn't a tight statistical
        # claim, just a smoke test that the scorer isn't systematically
        # biased toward any particular ticket).
        candidates = generator.generate_portfolio(size=15, seed=20)
        result = monte_carlo.compare_candidates(candidates, n_draws=500_000, seed=21)
        self.assertLess(result["max_abs_z"], 5.0)

    def test_ranked_output_covers_all_candidates_exactly_once(self):
        candidates = generator.generate_portfolio(size=10, seed=30)
        result = monte_carlo.compare_candidates(candidates, n_draws=200_000, seed=31)
        ranks = sorted(r["rank"] for r in result["ranked"])
        self.assertEqual(ranks, list(range(1, 11)))
        tickets_seen = {r["ticket"] for r in result["ranked"]}
        self.assertEqual(tickets_seen, set(candidates))


if __name__ == "__main__":
    unittest.main()
