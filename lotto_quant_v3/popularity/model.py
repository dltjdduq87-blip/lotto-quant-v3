"""Co-winner ("popularity") model: how many OTHER people are likely to share a prize with a ticket.

No way of choosing numbers changes the chance of winning -- every combination is drawn with the
same probability. What a choice does change is how many other tickets carry the same numbers, and
the 1st-3rd prizes are pools split equally between winners. So two tickets with identical odds can
have different expected payouts.

How it is measured (all from published round results, data.results_feed):
  1. Number effects. For each round, 4th-prize winners / (tickets sold x exact 4-match probability)
     says whether that round's numbers were over- or under-chosen. A log-linear regression on
     which numbers were drawn gives one effect per number (beta, centred on 0). The 4th tier is
     used because it has ~100,000 winners a round, so the estimate is tight.
  2. 1st-prize sharing. Published 1st-prize winners are split into automatic and manual picks.
     Automatic picks are uniform, so they must NOT depend on the numbers drawn (checked: they
     do not); manual winners are fitted as  tickets x p x manual_share x exp(slope x score).
     The multiplier of a combination is therefore
         auto_share + manual_share x exp(slope x score)          (normalised to average 1)
     and can never fall below the automatic share -- unpopular numbers only remove the manual
     co-winners, never the automatic ones.

`holdout_validation` refits step 1 on the early rounds only and checks the prediction on later,
unseen rounds, so the effect shown in the dashboard is out-of-sample, not a fitted curve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import comb

import numpy as np
from scipy import stats

from lotto_quant_v3.config.settings import NUM_MAX, PICK_SIZE
from lotto_quant_v3.probability import prize_model as pm

# Tickets cost 2,000원 up to round 87; winner counts are only comparable from round 88 on.
MIN_ROUND = 88
TOTAL = comb(NUM_MAX, PICK_SIZE)
P_TIER = {1: 1 / TOTAL, 3: 6 * 38 / TOTAL, 4: comb(6, 4) * comb(39, 2) / TOTAL}

Ticket = tuple[int, ...]


def _design(rows: list[dict]) -> np.ndarray:
    x = np.zeros((len(rows), NUM_MAX))
    for i, r in enumerate(rows):
        x[i, [r[f"n{k}"] - 1 for k in range(1, 7)]] = 1.0
    return x


def _usable(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["round"] >= MIN_ROUND and r.get("sales") and r.get("w4")]


def _number_effects(rows: list[dict]) -> np.ndarray:
    """Per-number log popularity (centred), from 4th-prize winner counts."""
    x = _design(rows)
    tickets = np.array([r["sales"] for r in rows], float) / pm.TICKET_PRICE
    y = np.log(np.array([r["w4"] for r in rows], float) / (tickets * P_TIER[4]))
    a = np.c_[np.ones(len(rows)), x]
    coef, *_ = np.linalg.lstsq(a, y, rcond=1e-10)   # min-norm: rows of x always sum to 6
    beta = coef[1:]
    return beta - beta.mean()


def _poisson_glm(count: np.ndarray, exposure: np.ndarray, score: np.ndarray | None):
    """count ~ Poisson(exposure * exp(a + b*score)). Returns (params, log-likelihood)."""
    z = np.ones((len(count), 1)) if score is None else np.c_[np.ones(len(count)), score]
    params = np.zeros(z.shape[1])
    params[0] = np.log(max(count.sum(), 1e-9) / exposure.sum())
    for _ in range(100):
        mu = exposure * np.exp(z @ params)
        step = np.linalg.solve(z.T @ (z * mu[:, None]), z.T @ (count - mu))
        params = params + step
        if np.abs(step).max() < 1e-10:
            break
    mu = exposure * np.exp(z @ params)
    return params, float(np.sum(count * np.log(mu) - mu))


def _slope_test(count, exposure, score):
    """Fit count ~ score and test the slope. Returns (params, p-value).

    Winner counts vary more from round to round than a pure Poisson count would (sales mix,
    pattern picks), which would make a plain likelihood-ratio test overconfident. The statistic
    is therefore divided by the Pearson dispersion (quasi-Poisson), never by less than 1."""
    full, ll_full = _poisson_glm(count, exposure, score)
    _, ll_null = _poisson_glm(count, exposure, None)
    mu = exposure * np.exp(np.c_[np.ones(len(count)), score] @ full)
    dispersion = max(float(np.sum((count - mu) ** 2 / mu) / (len(count) - 2)), 1.0)
    return full, float(stats.chi2.sf(max(2 * (ll_full - ll_null), 0.0) / dispersion, 1))


def _mean_exp_over_all_tickets(weights: np.ndarray) -> float:
    """Exact mean over all C(45,6) combinations of prod(weights[i] for i in combination)
    (6th elementary symmetric polynomial / C(45,6))."""
    e = np.zeros(PICK_SIZE + 1)
    e[0] = 1.0
    for w in weights:
        e[1:] = e[1:] + w * e[:-1]
    return float(e[PICK_SIZE] / TOTAL)


@dataclass
class PopularityModel:
    beta: np.ndarray                 # 45 number effects (log scale, mean 0); + = chosen more often
    auto_share: float                # share of 1st-prize winners that are automatic picks
    manual_share: float
    slope: float                     # manual 1st-prize winners vs score
    slope3: float                    # all 3rd-prize winners vs score
    p_manual: float                  # p-value: manual winners depend on score
    p_auto: float                    # p-value: automatic winners depend on score (should be large)
    n_rounds: int
    round_range: tuple[int, int]
    n_rounds_split: int              # rounds with the auto/manual breakdown
    _norm: float = field(default=1.0, repr=False)
    _norm3: float = field(default=1.0, repr=False)
    _ref: np.ndarray | None = field(default=None, repr=False)

    # --- scores -----------------------------------------------------------------------------
    def score(self, ticket) -> float:
        return float(self.beta[np.asarray(ticket, int) - 1].sum())

    def multiplier(self, ticket) -> float:
        """Expected 1st-prize co-winners relative to an average combination (1.0 = average)."""
        return float((self.auto_share + self.manual_share * np.exp(self.slope * self.score(ticket))) / self._norm)

    def multipliers(self, tickets: np.ndarray) -> np.ndarray:
        s = self.beta[np.asarray(tickets, int) - 1].sum(axis=1)
        return (self.auto_share + self.manual_share * np.exp(self.slope * s)) / self._norm

    @property
    def floor(self) -> float:
        """Lowest multiplier any combination can have (only automatic co-winners left)."""
        return float(self.auto_share / self._norm)

    def prize_factor3(self, ticket) -> float:
        """2nd/3rd-prize amount relative to average when THIS ticket wins that tier.

        A 3rd-prize draw holds 5 of the ticket's numbers and one other; its co-winner count
        follows the draw's own score, so the factor is averaged over those draws."""
        t = np.asarray(ticket, int) - 1
        others = np.setdiff1d(np.arange(NUM_MAX), t)
        s = self.beta[t].sum()
        draw_scores = (s - self.beta[t])[:, None] + self.beta[others][None, :]
        return float(np.exp(-self.slope3 * draw_scores).mean() / self._norm3)

    def reference(self, n: int = 200_000, seed: int = 0) -> np.ndarray:
        """Sorted multipliers of n random combinations (for percentiles)."""
        if self._ref is None or len(self._ref) != n:
            rng = np.random.default_rng(seed)
            tickets = np.argsort(rng.random((n, NUM_MAX)), axis=1)[:, :PICK_SIZE] + 1
            self._ref = np.sort(self.multipliers(tickets))
        return self._ref

    def percentile(self, ticket) -> float:
        """Share of all combinations that are LESS shared than this one (0 = least shared)."""
        ref = self.reference()
        return float(np.searchsorted(ref, self.multiplier(ticket)) / len(ref))

    def number_index(self) -> np.ndarray:
        """Popularity of each number, 100 = average (how often people include it)."""
        return 100.0 * np.exp(self.beta)

    # --- money ------------------------------------------------------------------------------
    def ticket_value(self, ticket, prize: pm.PrizeModel | None = None) -> dict:
        """Expected prizes and return for one ticket, next to an average combination."""
        prize = prize or pm.PrizeModel()
        mult = self.multiplier(ticket)
        f3 = self.prize_factor3(ticket)
        ks, pmf, lam = prize._share_pmf(1)

        def jackpot(m: float, net: bool) -> float:
            w = stats.poisson.pmf(ks, lam * m)
            amounts = prize.tier_pool(1) / (1 + ks)
            if net:
                amounts = np.vectorize(pm.after_tax)(amounts)
            return float(np.sum(w * amounts) / w.sum())

        def total(m: float, f: float, net: bool) -> float:
            ev = prize.p[1] * jackpot(m, net)
            for k in (2, 3):
                amount = prize.prize_per_ticket(k) * f
                ev += prize.p[k] * (pm.after_tax(amount) if net else amount)
            for k in (4, 5):
                ev += prize.p[k] * prize.prize_per_ticket(k, net)
            return float(ev / pm.TICKET_PRICE)

        return {
            "multiplier": mult,
            "percentile": self.percentile(ticket),
            "factor3": f3,
            "jackpot_gross": jackpot(mult, False), "jackpot_net": jackpot(mult, True),
            "jackpot_gross_avg": jackpot(1.0, False), "jackpot_net_avg": jackpot(1.0, True),
            "return_gross": total(mult, f3, False), "return_net": total(mult, f3, True),
            "return_gross_avg": total(1.0, 1.0, False), "return_net_avg": total(1.0, 1.0, True),
        }


def fit(rows: list[dict]) -> PopularityModel:
    """Fit on rows from db.get_all_stats()."""
    rows = _usable(rows)
    if len(rows) < 200:
        raise ValueError("need at least 200 rounds with sales and winner counts")
    beta = _number_effects(rows)
    score = _design(rows) @ beta
    tickets = np.array([r["sales"] for r in rows], float) / pm.TICKET_PRICE

    split = np.array([r.get("auto") is not None and r.get("manual") is not None for r in rows])
    if split.sum() < 100:
        raise ValueError("need at least 100 rounds with the automatic/manual winner breakdown")
    auto = np.array([r.get("auto") or 0 for r in rows], float)[split]
    manual = np.array([(r.get("manual") or 0) + (r.get("semi_auto") or 0) for r in rows], float)[split]
    exposure = tickets[split] * P_TIER[1]
    (a_man, slope), p_manual = _slope_test(manual, exposure, score[split])
    _, p_auto = _slope_test(auto, exposure, score[split])
    (a_auto,), _ = _poisson_glm(auto, exposure, None)

    w3 = np.array([r.get("w3") or 0 for r in rows], float)
    (_, slope3), _ = _slope_test(w3, tickets * P_TIER[3], score)

    auto_share, manual_share = float(np.exp(a_auto)), float(np.exp(a_man))
    norm = auto_share + manual_share * _mean_exp_over_all_tickets(np.exp(slope * beta))
    norm3 = _mean_exp_over_all_tickets(np.exp(-slope3 * beta))
    return PopularityModel(
        beta=beta, auto_share=auto_share, manual_share=manual_share, slope=float(slope), slope3=float(slope3),
        p_manual=p_manual, p_auto=p_auto, n_rounds=len(rows),
        round_range=(rows[0]["round"], rows[-1]["round"]), n_rounds_split=int(split.sum()),
        _norm=float(norm), _norm3=float(norm3),
    )


def holdout_validation(rows: list[dict], train_frac: float = 0.7, groups: int = 5) -> dict:
    """Learn number effects on the early rounds only, then check them on later unseen rounds.

    Test rounds are grouped by the predicted score of the numbers that were actually drawn; for
    each group we report real 1st-prize winners / expected and the real average payout per winner.
    """
    rows = _usable(rows)
    cut = int(len(rows) * train_frac)
    train, test = rows[:cut], rows[cut:]
    beta = _number_effects(train)
    score = _design(test) @ beta
    tickets = np.array([r["sales"] for r in test], float) / pm.TICKET_PRICE
    w1 = np.array([r.get("w1") or 0 for r in test], float)
    p1 = np.array([r.get("p1") or 0 for r in test], float)
    exposure = tickets * P_TIER[1]
    (_, slope), p_value = _slope_test(w1, exposure, score)

    order = np.argsort(score, kind="stable")
    table = []
    for g, idx in enumerate(np.array_split(order, groups)):
        winners = w1[idx].sum()
        table.append({
            "group": g + 1,
            "rounds": int(len(idx)),
            "winner_ratio": float(winners / exposure[idx].sum()),
            "avg_prize": float((p1[idx] * w1[idx]).sum() / winners) if winners else float("nan"),
        })
    return {
        "train_rounds": (train[0]["round"], train[-1]["round"]),
        "test_rounds": (test[0]["round"], test[-1]["round"]),
        "n_test": len(test), "slope": float(slope), "p_value": p_value, "groups": table,
    }


def pattern_flags(ticket, last_draw=None) -> list[str]:
    """Shapes many people mark by hand that a per-number model cannot see."""
    t = sorted(int(n) for n in ticket)
    gaps = np.diff(t)
    flags = []
    if len(set(gaps.tolist())) == 1:
        flags.append("같은 간격으로 늘어선 번호예요 (예: 5, 10, 15…). 용지에 줄 맞춰 찍는 사람이 많은 모양이에요.")
    run = longest = 1
    for g in gaps:
        run = run + 1 if g == 1 else 1
        longest = max(longest, run)
    if longest >= 4:
        flags.append(f"연속 번호가 {longest}개 이어져요. 일부러 이렇게 찍는 사람이 꽤 있어요.")
    if max(t) <= 31:
        flags.append("6개 모두 31 이하예요. 생일로 고르는 사람들과 겹치기 쉬워요.")
    if last_draw is not None and len(set(t) & set(int(n) for n in last_draw)) >= 5:
        flags.append("지난 회차 당첨번호와 거의 같아요. 지난 번호를 그대로 사는 사람이 많아요.")
    return flags


def suggest_portfolio(model: PopularityModel, games: int = 5, seed: int | None = None,
                      pool: int = 40_000, keep: float = 0.03, max_shared: int = 2) -> list[Ticket]:
    """Random tickets drawn from the least-shared `keep` fraction of combinations.

    Still random on purpose: the choice is made among tens of thousands of low-sharing
    combinations, and tickets in one portfolio share at most `max_shared` numbers."""
    rng = np.random.default_rng(seed)
    tickets = np.sort(np.argsort(rng.random((pool, NUM_MAX)), axis=1)[:, :PICK_SIZE] + 1, axis=1)
    mult = model.multipliers(tickets)
    cand = tickets[mult <= np.quantile(mult, keep)]
    rng.shuffle(cand)
    for limit in range(max_shared, PICK_SIZE):
        chosen: list[Ticket] = []
        for row in cand:
            t = tuple(int(n) for n in row)
            if all(len(set(t) & set(c)) <= limit for c in chosen):
                chosen.append(t)
                if len(chosen) == games:
                    return sorted(chosen)
    raise RuntimeError("could not build a low-sharing portfolio")
