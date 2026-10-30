"""Strategy lab: finer-grained, money-based simulations.

1. strategy_walkforward  -- several number-picking strategies replayed over the real draw
   history, each round using ONLY earlier draws, repeated with many random seeds so a lucky
   seed can't decide the result. Scored by official prize tier (incl. the bonus number) and
   by money (won / spent), with a paired bootstrap CI against the uniform-random baseline.
2. lifetime_simulation   -- "if I buy N games every week for Y years" Monte Carlo using the
   exact tier probabilities: distribution of money spent / won, chance of each tier.

Prize amounts for tiers 1-3 are pari-mutuel (they change every round); the defaults below are
round typical values and can be overridden. Tiers 4 and 5 are fixed by rule.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from lotto_quant_v3.config.settings import NUM_MAX, NUM_MIN, PICK_SIZE
from lotto_quant_v3.optimization import optimizer
from lotto_quant_v3.portfolio import generator
from lotto_quant_v3.probability import engine
from lotto_quant_v3.statistics import analysis

TICKET_PRICE = 1_000
DEFAULT_PRIZES = {1: 2_000_000_000, 2: 60_000_000, 3: 1_500_000, 4: 50_000, 5: 5_000}
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


# --------------------------------------------------------------------------- strategies
def _weighted(weights, size, rng):
    return generator.generate_portfolio(size=size, weights=np.asarray(weights, float),
                                        seed=int(rng.integers(0, 2**31 - 1)))


def strat_uniform(hist: pd.DataFrame, size: int, rng):
    return generator.generate_portfolio(size=size, weights=None, seed=int(rng.integers(0, 2**31 - 1)))


def strat_hot_all(hist, size, rng):
    return _weighted(analysis.number_frequency(hist).values + 1, size, rng)


def strat_hot_recent(hist, size, rng, window=100):
    return _weighted(analysis.number_frequency(hist.tail(window)).values + 1, size, rng)


def strat_cold_recent(hist, size, rng, window=100):
    f = analysis.number_frequency(hist.tail(window)).values
    return _weighted(f.max() - f + 1, size, rng)


def strat_overdue(hist, size, rng):
    gaps = analysis.gap_since_last_seen(hist.tail(200)).fillna(200).values.astype(float)
    return _weighted(gaps + 1, size, rng)


def strat_diversified(hist, size, rng):
    return optimizer.optimize_portfolio(weights=None, size=size, candidate_pool=60,
                                        seed=int(rng.integers(0, 2**31 - 1)))


STRATEGIES = {
    "무작위(기준)": strat_uniform,
    "많이 나온 번호(전체)": strat_hot_all,
    "최근 100회 많이 나온 번호": strat_hot_recent,
    "최근 100회 덜 나온 번호": strat_cold_recent,
    "오래 안 나온 번호": strat_overdue,
    "번호 분산(겹침 최소)": strat_diversified,
}


def strategy_walkforward(draws: list[dict], n_repeats: int = 10, games: int = 5, min_history: int = 52,
                         strategies: dict | None = None, prizes: dict | None = None, seed: int = 0,
                         last_n_rounds: int | None = None, progress=None) -> dict:
    strategies = strategies or STRATEGIES
    prizes = prizes or DEFAULT_PRIZES
    df = analysis.draws_to_frame(draws).sort_values("round").reset_index(drop=True)
    idxs = list(range(min_history, len(df)))
    if last_n_rounds:
        idxs = idxs[-last_n_rounds:]
    names = list(strategies)
    rng = np.random.default_rng(seed)
    # per strategy, per round: average over repeats of money won and best match
    won = {s: np.zeros(len(idxs)) for s in names}
    best = {s: np.zeros(len(idxs)) for s in names}
    tiers = {s: np.zeros(6, dtype=np.int64) for s in names}
    overlap = {s: 0.0 for s in names}
    total_steps = len(idxs) * n_repeats
    step = 0
    for r in range(n_repeats):
        for k, idx in enumerate(idxs):
            hist = df.iloc[:idx]
            row = df.iloc[idx]
            assert hist["round"].max() < row["round"], "data leakage"
            main, bonus = row["numbers"], row["bonus"]
            for s in names:
                port = strategies[s](hist, games, rng)
                overlap[s] += (games * PICK_SIZE - len(set().union(*map(set, port)))) / (len(idxs) * n_repeats)
                w, bm = 0, 0
                for t in port:
                    tier = prize_tier(t, main, bonus)
                    tiers[s][tier] += 1
                    w += prizes.get(tier, 0)
                    bm = max(bm, len(set(t) & set(main)))
                won[s][k] += w / n_repeats
                best[s][k] += bm / n_repeats
            step += 1
            if progress and step % 200 == 0:
                progress(step / total_steps)
    cost_per_round = games * TICKET_PRICE
    base = names[0]
    boot_rng = np.random.default_rng(seed + 1)
    rows = []
    for s in names:
        n_tickets = len(idxs) * games * n_repeats
        diff = best[s] - best[base]
        if s == base:
            ci = (0.0, 0.0)
        else:
            bs = [diff[boot_rng.integers(0, len(diff), len(diff))].mean() for _ in range(2000)]
            ci = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
        p_win = tiers[s][1:].sum() / n_tickets
        p_th = float(sum(t.probability for t in engine.build_prize_table()))
        z_win = (p_win - p_th) / np.sqrt(p_th * (1 - p_th) / n_tickets)
        rows.append({
            "전략": s,
            "게임 간 겹친 번호 수": float(overlap[s]),
            "5등 이상 당첨률 z(이론 대비)": float(z_win),
            "평균 최고 일치 개수": float(best[s].mean()),
            "기준 대비 차이": float(diff.mean()),
            "차이 95% 구간": ci,
            "기준과 다르다고 볼 수 있음": bool(s != base and (ci[0] > 0 or ci[1] < 0)),
            "5등 이상 당첨률(게임당)": float(tiers[s][1:].sum() / n_tickets),
            "4등 이상 당첨률(게임당)": float(tiers[s][1:5].sum() / n_tickets),
            "등수별 횟수": {int(i): int(tiers[s][i]) for i in range(1, 6)},
            "회수율": float(won[s].sum() / (cost_per_round * len(idxs))),
        })
    return {"n_rounds": len(idxs), "round_range": (int(df.iloc[idxs[0]]["round"]), int(df.iloc[idxs[-1]]["round"])),
            "n_repeats": n_repeats, "games": games, "rows": rows,
            "theory_5th_or_better": float(sum(t.probability for t in engine.build_prize_table())),
            "theory_return": float(expected_return(prizes))}


# --------------------------------------------------------------------------- lifetime
def tier_probabilities() -> np.ndarray:
    """p[0]=no prize, p[1..5] = tier 1..5 (exact)."""
    p = np.zeros(6)
    for t in engine.build_prize_table():
        p[t.tier] = t.probability
    p[0] = 1 - p[1:].sum()
    return p


def expected_return(prizes: dict | None = None) -> float:
    prizes = prizes or DEFAULT_PRIZES
    p = tier_probabilities()
    return float(sum(p[k] * prizes.get(k, 0) for k in range(1, 6)) / TICKET_PRICE)


def lifetime_simulation(games_per_week: int = 5, years: int = 30, n_paths: int = 100_000,
                        prizes: dict | None = None, seed: int | None = 0) -> dict:
    prizes = prizes or DEFAULT_PRIZES
    rng = np.random.default_rng(seed)
    n_games = games_per_week * 52 * years
    counts = rng.multinomial(n_games, tier_probabilities(), size=n_paths)  # (paths, 6)
    prize_vec = np.array([0] + [prizes.get(k, 0) for k in range(1, 6)], dtype=float)
    won = counts @ prize_vec
    spent = n_games * TICKET_PRICE
    net = won - spent
    pct = lambda q: float(np.percentile(net, q))
    return {
        "games": n_games, "spent": spent,
        "p_net_positive": float((net > 0).mean()),
        "p_tier": {k: float((counts[:, k] > 0).mean()) for k in range(1, 6)},
        "mean_won": float(won.mean()), "median_net": pct(50), "p10_net": pct(10), "p90_net": pct(90),
        "median_return_rate": float(np.median(won) / spent), "mean_return_rate": float(won.mean() / spent),
        "net_samples": net[:20000],
    }
