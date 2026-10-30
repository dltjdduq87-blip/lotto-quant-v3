"""Prize model for Lotto 6/45: how much a winning ticket actually pays, before and after tax.

Rules (복권 및 복권기금법 / 동행복권 배분 규칙):
  * About 50% of round sales is paid out as prizes.
  * 4th (50,000원) and 5th (5,000원) are fixed and paid first.
  * The rest is split 75% / 12.5% / 12.5% into the 1st / 2nd / 3rd tier pools, and each pool is
    shared equally by that tier's winning tickets (pari-mutuel).
Tax (기타소득, 분리과세): a prize of 2,000,000원 or less is tax-free. Above that, the prize minus the
1,000원 ticket cost is taxed 22% up to 300,000,000원 and 33% on the part above it.

Because pools are shared, the expected amount a winning ticket receives is
    pool_k * E[1 / (1 + K)],  K ~ Poisson(lambda_k = other tickets * p_k)
(the other players' winning tickets), which equals pool_k * (1 - e^-lambda) / lambda.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp

import numpy as np
from scipy import stats

from lotto_quant_v3.probability import engine

TICKET_PRICE = 1_000
PAYOUT_RATIO = 0.50
FIXED_PRIZES = {4: 50_000, 5: 5_000}
POOL_SHARE = {1: 0.75, 2: 0.125, 3: 0.125}
TAX_FREE_LIMIT = 2_000_000
TAX_BRACKET = 300_000_000
# 2025 annual sales were about 6.2 trillion won (Yonhap, 2026-02) -> about 119.2 billion won per weekly round.
DEFAULT_SALES_PER_ROUND = 119_000_000_000


def after_tax(prize: float) -> float:
    """Net amount received for one winning ticket."""
    if prize <= TAX_FREE_LIMIT:
        return float(prize)
    taxable = prize - TICKET_PRICE
    tax = 0.22 * min(taxable, TAX_BRACKET) + 0.33 * max(taxable - TAX_BRACKET, 0.0)
    return float(prize - tax)


def tier_probabilities() -> np.ndarray:
    """p[0] = no prize, p[1..5] = tier 1..5 (exact, per ticket)."""
    p = np.zeros(6)
    for t in engine.build_prize_table():
        p[t.tier] = t.probability
    p[0] = 1 - p[1:].sum()
    return p


@dataclass
class PrizeModel:
    sales_per_round: float = DEFAULT_SALES_PER_ROUND
    payout_ratio: float = PAYOUT_RATIO
    p: np.ndarray = field(default_factory=tier_probabilities)

    @property
    def n_tickets(self) -> float:
        return self.sales_per_round / TICKET_PRICE

    @property
    def total_pool(self) -> float:
        return self.sales_per_round * self.payout_ratio

    @property
    def fixed_payout(self) -> float:
        return sum(self.n_tickets * self.p[k] * v for k, v in FIXED_PRIZES.items())

    def tier_pool(self, k: int) -> float:
        return max(self.total_pool - self.fixed_payout, 0.0) * POOL_SHARE[k]

    def expected_winners(self, k: int) -> float:
        return self.n_tickets * self.p[k]

    def _share_pmf(self, k: int):
        """Poisson pmf of OTHER winning tickets for tier k, truncated where the tail is negligible."""
        lam = max((self.n_tickets - 1) * self.p[k], 1e-12)
        hi = int(stats.poisson.ppf(1 - 1e-12, lam)) + 2
        ks = np.arange(hi + 1)
        return ks, stats.poisson.pmf(ks, lam), lam

    def prize_per_ticket(self, k: int, net: bool = False) -> float:
        """Expected amount ONE winning ticket of tier k receives (net = after tax)."""
        if k in FIXED_PRIZES:
            v = FIXED_PRIZES[k]
            return after_tax(v) if net else float(v)
        pool = self.tier_pool(k)
        ks, pmf, lam = self._share_pmf(k)
        if not net:
            return float(pool * (1 - exp(-lam)) / lam)
        amounts = pool / (1 + ks)
        return float(np.sum(pmf * np.vectorize(after_tax)(amounts)))

    def sample_prizes(self, k: int, n: int, rng: np.random.Generator, net: bool = False) -> np.ndarray:
        """Random payouts for n independent winning tickets of tier k (share depends on co-winners)."""
        if n == 0:
            return np.zeros(0)
        if k in FIXED_PRIZES:
            return np.full(n, self.prize_per_ticket(k, net))
        lam = (self.n_tickets - 1) * self.p[k]
        amounts = self.tier_pool(k) / (1 + rng.poisson(lam, n))
        return np.vectorize(after_tax)(amounts) if net else amounts

    def prizes(self, net: bool = False) -> dict[int, float]:
        return {k: self.prize_per_ticket(k, net) for k in range(1, 6)}

    def expected_return(self, net: bool = False) -> float:
        """Expected payout per 1,000원 ticket, as a fraction of the price."""
        pr = self.prizes(net)
        return float(sum(self.p[k] * pr[k] for k in range(1, 6)) / TICKET_PRICE)

    def table(self) -> list[dict]:
        gross, net = self.prizes(False), self.prizes(True)
        rows = []
        for k in range(1, 6):
            rows.append({
                "tier": k,
                "probability": float(self.p[k]),
                "expected_winners": float(self.expected_winners(k)),
                "prize_gross": float(gross[k]),
                "prize_net": float(net[k]),
                "ev_gross": float(self.p[k] * gross[k]),
                "ev_net": float(self.p[k] * net[k]),
            })
        return rows
