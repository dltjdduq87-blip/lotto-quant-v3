"""Strategy lab: finer-grained, money-based simulations.

1. strategy_walkforward  -- several number-picking strategies replayed over the real draw
   history, each round using ONLY earlier draws, repeated with many random seeds so a lucky
   seed can't decide the result. Scored by official prize tier (incl. the bonus number) and
   by money (won / spent), with a paired bootstrap CI against the uniform-random baseline.
2. lifetime_simulation   -- "if I buy N games every week for Y years" Monte Carlo using the
   exact tier probabilities: distribution of money spent / won, chance of each tier.

Prize amounts for tiers 1-3 are pari-mutuel: they come from probability.prize_model (50% of sales,
fixed 4th/5th first, 75/12.5/12.5 split, shared by co-winners) and Korean lottery tax is applied for
the after-tax ("net") figures. Tiers 4 and 5 are fixed by rule and tax-free.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lotto_quant_v3.config.settings import NUM_MAX, NUM_MIN, PICK_SIZE
from lotto_quant_v3.optimization import optimizer
from lotto_quant_v3.portfolio import generator
from lotto_quant_v3.probability import engine, prize_model
from lotto_quant_v3.statistics import analysis

TICKET_PRICE = prize_model.TICKET_PRICE
_PM = prize_model.PrizeModel()
# Expected payout of one winning ticket per tier from the pari-mutuel model (sales ~119 billion won/round).
DEFAULT_PRIZES = {k: round(v) for k, v in _PM.prizes(net=False).items()}
DEFAULT_PRIZES_NET = {k: round(v) for k, v in _PM.prizes(net=True).items()}
POOL = np.arange(NUM_MIN, NUM_MAX + 1)


def prize_tier(ticket, main, bonus) -> int:
    """Official tier for one ticket (0 = no prize)."""
    m = len(set(ticket) & set(main))
    if m == 6:
        return 1
    if m == 5:
        return 2 if bonus in ticket else 3
    if m == 4:
        return 4
    if m == 3:
        return 5
    return 0


# --------------------------------------------------------------------------- history features
class History:
    """Number statistics for draws[:idx], precomputed once so each round is O(45) instead of O(N)."""

    def __init__(self, df: pd.DataFrame):
        n = len(df)
        x = np.zeros((n, NUM_MAX), dtype=np.int32)
        for i, nums in enumerate(df["numbers"]):
            x[i, np.asarray(nums) - NUM_MIN] = 1
        self.cum = np.vstack([np.zeros((1, NUM_MAX), np.int32), np.cumsum(x, axis=0)])
        last = np.full((n + 1, NUM_MAX), -10**9, dtype=np.int64)  # last[i] = last index < i where drawn
        for i in range(n):
            last[i + 1] = np.where(x[i] == 1, i, last[i])
        self.last = last

    def freq(self, idx: int, window: int | None = None) -> np.ndarray:
        lo = 0 if window is None else max(idx - window, 0)
        return (self.cum[idx] - self.cum[lo]).astype(float)

    def gaps(self, idx: int, cap: int = 200) -> np.ndarray:
        """Rounds since each number last appeared (0 = in the latest draw), capped like the old tail(200)."""
        return np.minimum(idx - 1 - self.last[idx], cap).astype(float)


# --------------------------------------------------------------------------- strategies
# Each strategy returns sampling weights for 1..45 (None = uniform) or a ready portfolio.
def _weighted(weights, size, rng):
    return generator.generate_portfolio(size=size, weights=None if weights is None else np.asarray(weights, float),
                                        seed=int(rng.integers(0, 2**31 - 1)))


def strat_uniform(h: History, idx: int, size: int, rng):
    return _weighted(None, size, rng)


def strat_hot_all(h, idx, size, rng):
    return _weighted(h.freq(idx) + 1, size, rng)


def strat_hot_recent(h, idx, size, rng, window=100):
    return _weighted(h.freq(idx, window) + 1, size, rng)


def strat_cold_recent(h, idx, size, rng, window=100):
    f = h.freq(idx, window)
    return _weighted(f.max() - f + 1, size, rng)


def strat_overdue(h, idx, size, rng):
    return _weighted(h.gaps(idx) + 1, size, rng)


def strat_diversified(h, idx, size, rng):
    return optimizer.optimize_portfolio(weights=None, size=size, candidate_pool=60,
                                        seed=int(rng.integers(0, 2**31 - 1)))


def strat_no_overlap(h, idx, size, rng):
    """Up to 7 games with zero shared numbers (a random partition of 1..45), then random games."""
    perm = rng.permutation(POOL)
    port = [tuple(sorted(int(v) for v in perm[i * PICK_SIZE:(i + 1) * PICK_SIZE]))
            for i in range(min(size, NUM_MAX // PICK_SIZE))]
    while len(port) < size:
        t = generator.sample_ticket(rng, None)
        if t not in port:
            port.append(t)
    return port


STRATEGIES = {
    "무작위(기준)": strat_uniform,
    "많이 나온 번호(전체)": strat_hot_all,
    "최근 100회 많이 나온 번호": strat_hot_recent,
    "최근 100회 덜 나온 번호": strat_cold_recent,
    "오래 안 나온 번호": strat_overdue,
    "번호 분산(겹침 최소)": strat_diversified,
    "완전 분산(겹침 0)": strat_no_overlap,
}


def strategy_walkforward(draws: list[dict], n_repeats: int = 10, games: int = 5, min_history: int = 52,
                         strategies: dict | None = None, prizes: dict | None = None, seed: int = 0,
                         last_n_rounds: int | None = None, progress=None) -> dict:
    strategies = strategies or STRATEGIES
    prizes_gross = DEFAULT_PRIZES if prizes is None else prizes
    prizes_net = DEFAULT_PRIZES_NET if prizes is None else {k: prize_model.after_tax(v) for k, v in prizes.items()}
    df = analysis.draws_to_frame(draws).sort_values("round").reset_index(drop=True)
    hist = History(df)
    idxs = list(range(min_history, len(df)))
    if last_n_rounds:
        idxs = idxs[-last_n_rounds:]
    names = list(strategies)
    rng = np.random.default_rng(seed)
    R = len(idxs)
    won = {s: np.zeros(R) for s in names}
    won_net = {s: np.zeros(R) for s in names}
    best = {s: np.zeros(R) for s in names}
    win_rate = {s: np.zeros(R) for s in names}  # per round: share of games with any prize
    tiers = {s: np.zeros(6, dtype=np.int64) for s in names}
    overlap = {s: 0.0 for s in names}
    total_steps = R * n_repeats
    step = 0
    rounds = df["round"].to_numpy()
    for r in range(n_repeats):
        for k, idx in enumerate(idxs):
            assert rounds[:idx].max() < rounds[idx], "data leakage"
            row = df.iloc[idx]
            main, bonus = set(row["numbers"]), row["bonus"]
            for s in names:
                port = strategies[s](hist, idx, games, rng)
                overlap[s] += (games * PICK_SIZE - len(set().union(*map(set, port)))) / total_steps
                w = wn = 0.0
                bm = 0
                for t in port:
                    tier = prize_tier(t, main, bonus)
                    tiers[s][tier] += 1
                    win_rate[s][k] += (tier > 0) / (games * n_repeats)
                    w += prizes_gross.get(tier, 0)
                    wn += prizes_net.get(tier, 0)
                    bm = max(bm, len(set(t) & main))
                won[s][k] += w / n_repeats
                won_net[s][k] += wn / n_repeats
                best[s][k] += bm / n_repeats
            step += 1
            if progress and step % 200 == 0:
                progress(step / total_steps)
    cost_per_round = games * TICKET_PRICE
    base = names[0]
    boot_rng = np.random.default_rng(seed + 1)
    p_th = float(sum(t.probability for t in engine.build_prize_table()))
    # Several strategies are compared against the baseline at once -> Bonferroni-widened intervals,
    # so "different from random" is not declared just because one of many comparisons got lucky.
    m_cmp = max(len(names) - 1, 1)
    alpha = 0.05 / m_cmp
    boot_idx = boot_rng.integers(0, R, (2000, R))
    rows = []
    for s in names:
        n_tickets = R * games * n_repeats
        diff = best[s] - best[base]
        wdiff = win_rate[s] - win_rate[base]
        if s == base:
            ci = wci = (0.0, 0.0)
        else:
            bs = diff[boot_idx].mean(axis=1)
            ci = (float(np.percentile(bs, 100 * alpha / 2)), float(np.percentile(bs, 100 * (1 - alpha / 2))))
            bw = wdiff[boot_idx].mean(axis=1)
            wci = (float(np.percentile(bw, 100 * alpha / 2)), float(np.percentile(bw, 100 * (1 - alpha / 2))))
        # Games in the same round share one draw (and seeds reuse the same draws), so they are not
        # independent: use the round as the unit and take the standard error across rounds.
        wr = win_rate[s]
        se = wr.std(ddof=1) / np.sqrt(len(wr)) if len(wr) > 1 else np.nan
        z_win = (wr.mean() - p_th) / se if se and se > 0 else 0.0
        rows.append({
            "전략": s,
            "게임 간 겹친 번호 수": float(overlap[s]),
            "5등 이상 당첨률 z(이론 대비)": float(z_win),
            "평균 최고 일치 개수": float(best[s].mean()),
            "기준 대비 차이": float(diff.mean()),
            "차이 95% 구간": ci,
            "당첨률 차이 구간": wci,
            "기준과 다르다고 볼 수 있음": bool(s != base and (wci[0] > 0 or wci[1] < 0)),
            "5등 이상 당첨률(게임당)": float(tiers[s][1:].sum() / n_tickets),
            "4등 이상 당첨률(게임당)": float(tiers[s][1:5].sum() / n_tickets),
            "등수별 횟수": {int(i): int(tiers[s][i]) for i in range(1, 6)},
            "회수율": float(won[s].sum() / (cost_per_round * R)),
            "회수율(세후)": float(won_net[s].sum() / (cost_per_round * R)),
        })
    return {"n_rounds": R, "round_range": (int(rounds[idxs[0]]), int(rounds[idxs[-1]])),
            "n_repeats": n_repeats, "games": games, "rows": rows, "ci_level": 1 - alpha,
            "theory_5th_or_better": p_th,
            "theory_return": float(expected_return(prizes)),
            "theory_return_net": float(expected_return(prizes, net=True)),
            "prizes": prizes_gross, "prizes_net": prizes_net}


# --------------------------------------------------------------------------- lifetime
def tier_probabilities() -> np.ndarray:
    """p[0]=no prize, p[1..5] = tier 1..5 (exact)."""
    return prize_model.tier_probabilities()


def expected_return(prizes: dict | None = None, net: bool = False, model: prize_model.PrizeModel | None = None) -> float:
    """Expected payout per ticket as a fraction of its price. prizes=None -> pari-mutuel prize model."""
    if prizes is None:
        return (model or _PM).expected_return(net)
    p = tier_probabilities()
    val = (lambda v: prize_model.after_tax(v)) if net else (lambda v: v)
    return float(sum(p[k] * val(prizes.get(k, 0)) for k in range(1, 6)) / TICKET_PRICE)


def lifetime_simulation(games_per_week: int = 5, years: int = 30, n_paths: int = 100_000,
                        prizes: dict | None = None, seed: int | None = 0, net: bool = False,
                        sales_per_round: float | None = None) -> dict:
    """prizes=None -> each 1st-3rd win pays a random pari-mutuel share (co-winners ~ Poisson),
    from the prize model; net=True applies lottery tax per winning ticket."""
    model = prize_model.PrizeModel(sales_per_round) if sales_per_round else _PM
    rng = np.random.default_rng(seed)
    n_games = games_per_week * 52 * years
    p = tier_probabilities()
    counts = rng.multinomial(n_games, p, size=n_paths)  # (paths, 6)
    won = np.zeros(n_paths)
    for k in range(1, 6):
        c = counts[:, k]
        if prizes is not None:
            v = prizes.get(k, 0)
            won += c * (prize_model.after_tax(v) if net else v)
        elif k >= 4:
            won += c * model.prize_per_ticket(k, net)
        else:
            tot = int(c.sum())
            if tot:
                amounts = model.sample_prizes(k, tot, rng, net)
                won += np.bincount(np.repeat(np.arange(n_paths), c), weights=amounts, minlength=n_paths)
    spent = n_games * TICKET_PRICE
    net_pl = won - spent
    pct = lambda q: float(np.percentile(net_pl, q))
    exp_rate = expected_return(prizes, net, model)
    return {
        "games": n_games, "spent": spent, "after_tax": net,
        "p_net_positive": float((net_pl > 0).mean()),
        # "tier k or better at least once" -- exact, no sampling noise
        "p_tier": {k: float(1 - (1 - p[1:k + 1].sum()) ** n_games) for k in range(1, 6)},
        "expected_return_rate": exp_rate,
        "expected_net": float(spent * (exp_rate - 1)),
        "mean_won": float(won.mean()), "median_net": pct(50), "p10_net": pct(10), "p90_net": pct(90),
        "median_return_rate": float(np.median(won) / spent),
        "sample_mean_return_rate": float(won.mean() / spent), "mean_return_rate": float(won.mean() / spent),
        "net_samples": net_pl[:20000],
    }
