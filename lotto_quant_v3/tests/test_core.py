"""Core correctness tests (stdlib unittest -- no extra test-runner dependency).

Run with:  python -m unittest lotto_quant_v3.tests.test_core -v
(from the project root)
"""
import unittest
from datetime import date

from lotto_quant_v3.data import news_search
from lotto_quant_v3.data.excel_import import round_to_date
from lotto_quant_v3.portfolio import generator, probability
from lotto_quant_v3.probability import engine


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


if __name__ == "__main__":
    unittest.main()
