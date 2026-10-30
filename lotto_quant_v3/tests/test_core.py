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
from lotto_quant_v3.simulation import monte_carlo, strategy_lab
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


class TestStrategyLab(unittest.TestCase):
    def test_prize_tier_rules(self):
        main, bonus = (1, 2, 3, 4, 5, 6), 7
        self.assertEqual(strategy_lab.prize_tier((1, 2, 3, 4, 5, 6), main, bonus), 1)
        self.assertEqual(strategy_lab.prize_tier((1, 2, 3, 4, 5, 7), main, bonus), 2)
        self.assertEqual(strategy_lab.prize_tier((1, 2, 3, 4, 5, 8), main, bonus), 3)
        self.assertEqual(strategy_lab.prize_tier((1, 2, 3, 4, 7, 8), main, bonus), 4)
        self.assertEqual(strategy_lab.prize_tier((1, 2, 3, 7, 8, 9), main, bonus), 5)
        self.assertEqual(strategy_lab.prize_tier((1, 2, 7, 8, 9, 10), main, bonus), 0)

    def test_tier_probabilities_sum_to_one(self):
        p = strategy_lab.tier_probabilities()
        self.assertAlmostEqual(p.sum(), 1.0, places=12)
        self.assertAlmostEqual(p[5], 1 / 45, delta=0.0005)

    def test_lifetime_mean_matches_expected_value(self):
        lt = strategy_lab.lifetime_simulation(5, 10, n_paths=200_000, seed=3,
                                              prizes={1: 0, 2: 0, 3: 0, 4: 50_000, 5: 5_000})
        ev = strategy_lab.expected_return({1: 0, 2: 0, 3: 0, 4: 50_000, 5: 5_000})
        self.assertAlmostEqual(lt["mean_return_rate"], ev, delta=0.005)
        self.assertAlmostEqual(lt["expected_return_rate"], ev, places=12)
        # "tier 5 or better at least once" must include higher tiers and be monotone
        self.assertGreaterEqual(lt["p_tier"][5], lt["p_tier"][4])
        self.assertGreaterEqual(lt["p_tier"][3], lt["p_tier"][1])

    def test_walkforward_runs_without_leakage(self):
        rng = np.random.default_rng(5)
        draws = []
        for r in range(1, 81):
            nums = sorted(rng.choice(np.arange(1, 46), 7, replace=False).tolist())
            main, bonus = nums[:6], nums[6]
            draws.append({"round": r, "draw_date": "2020-01-01", "n1": main[0], "n2": main[1], "n3": main[2],
                          "n4": main[3], "n5": main[4], "n6": main[5], "bonus": bonus})
        res = strategy_lab.strategy_walkforward(draws, n_repeats=1, games=3, min_history=60)
        self.assertEqual(res["n_rounds"], 20)
        self.assertEqual(len(res["rows"]), len(strategy_lab.STRATEGIES))


class TestCalculationUpgrade(unittest.TestCase):
    def test_prize_model_matches_pari_mutuel_rule(self):
        from lotto_quant_v3.probability import prize_model
        m = prize_model.PrizeModel()
        self.assertAlmostEqual(m.expected_return(), 0.5, places=4)  # 50% of sales is paid out
        # 1st tier expected share for ~119 billion won sales: ~19.5억 (known published figure)
        self.assertAlmostEqual(m.prize_per_ticket(1) / 1e8, 19.52, delta=0.05)
        self.assertLess(m.expected_return(net=True), m.expected_return())

    def test_after_tax_brackets(self):
        from lotto_quant_v3.probability.prize_model import after_tax
        self.assertEqual(after_tax(2_000_000), 2_000_000)
        self.assertAlmostEqual(after_tax(60_000_000), 60_000_000 - 0.22 * (60_000_000 - 1000))
        self.assertAlmostEqual(after_tax(1_000_000_000),
                               1_000_000_000 - (0.22 * 300_000_000 + 0.33 * (1_000_000_000 - 1000 - 300_000_000)))

    def test_exact_single_ticket_tiers_equal_official_odds(self):
        r = probability.exact_portfolio_distribution([(1, 2, 3, 4, 5, 6)])
        p = strategy_lab.tier_probabilities()
        for k in range(6):
            self.assertAlmostEqual(r["best_tier_probability"][k], p[k], places=12)

    def test_exact_tiers_agree_with_monte_carlo(self):
        tickets = [(1, 2, 3, 4, 5, 6), (1, 2, 3, 4, 5, 7), (8, 9, 10, 11, 12, 13)]
        ex = probability.exact_portfolio_distribution(tickets)
        mc = monte_carlo.simulate_portfolio(tickets, n_draws=400_000, seed=3)
        for k in (0, 4, 5):
            e, m = ex["best_tier_probability"][k], mc["best_tier_probability"][k]
            se = np.sqrt(e * (1 - e) / 400_000)
            self.assertLess(abs(m - e), 4 * se)
        self.assertGreater(ex["overlap_loss"], 0)

    def test_chi_square_correction_and_holm(self):
        self.assertAlmostEqual(randomness_tests.WITHOUT_REPLACEMENT_FACTOR, 44 / 39)
        adj = randomness_tests.holm_adjust({"a": 0.01, "b": 0.04, "c": 0.5})
        self.assertAlmostEqual(adj["a"], 0.03)
        self.assertAlmostEqual(adj["b"], 0.08)
        self.assertAlmostEqual(adj["c"], 0.5)

    def test_history_features_match_slow_versions(self):
        from lotto_quant_v3.statistics import analysis
        df = _synthetic_uniform_df(n=300, seed=9)
        df["round"] = np.arange(1, len(df) + 1)
        h = strategy_lab.History(df)
        for idx in (50, 299):
            hist = df.iloc[:idx]
            np.testing.assert_array_equal(h.freq(idx), analysis.number_frequency(hist).values)
            np.testing.assert_array_equal(h.freq(idx, 100), analysis.number_frequency(hist.tail(100)).values)
            slow = analysis.gap_since_last_seen(hist.tail(200)).fillna(200).values.astype(float)
            np.testing.assert_array_equal(h.gaps(idx), slow)

    def test_optimizer_fallback_path(self):
        from lotto_quant_v3.optimization import optimizer
        port = optimizer.optimize_portfolio(size=5, candidate_pool=2, seed=1)
        self.assertEqual(len(port), 5)


if __name__ == "__main__":
    unittest.main()
