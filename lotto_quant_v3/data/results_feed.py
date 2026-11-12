"""Official-result feed: winning numbers PLUS per-tier winner counts, prizes and sales.

Source: https://smok95.github.io/lotto/results/ -- a public JSON mirror of the operator's
published round results (one object per round, refreshed every Saturday night). It is plain
static JSON, so it works from Streamlit Cloud where the operator's own site is not reachable.

Why this matters: the winner counts are what make the co-winner ("who else picked my numbers")
analysis possible. Winning numbers alone can only ever show that the draw is random.

Every record is validated before it is stored (6 distinct numbers in 1..45, a distinct bonus,
a Saturday-cadence date), and for rounds that are already in the DB from another source the
numbers must agree -- a disagreement is reported and never silently overwritten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import requests

from lotto_quant_v3.config.settings import FIRST_DRAW_DATE, NUM_MAX, NUM_MIN, REQUEST_HEADERS, REQUEST_TIMEOUT

FEED_ALL_URL = "https://smok95.github.io/lotto/results/all.json"
FEED_ROUND_URL = "https://smok95.github.io/lotto/results/{round}.json"
FEED_SOURCE = "smok95.github.io/lotto (official result mirror)"

_FIRST_DRAW = date.fromisoformat(FIRST_DRAW_DATE)


@dataclass(frozen=True)
class RoundResult:
    round: int
    draw_date: str
    numbers: tuple[int, ...]
    bonus: int
    sales: int | None
    winners: tuple[int | None, ...]   # tiers 1..5
    prizes: tuple[int | None, ...]    # per-winner amount, tiers 1..5
    auto: int | None                  # 1st-prize winners who used auto pick
    semi_auto: int | None
    manual: int | None


def expected_date(round_no: int) -> date:
    return _FIRST_DRAW + timedelta(weeks=round_no - 1)


def parse_record(rec: dict) -> RoundResult:
    """Validate one feed object and convert it. Raises ValueError on anything suspicious."""
    round_no = int(rec["draw_no"])
    numbers = tuple(sorted(int(n) for n in rec["numbers"]))
    bonus = int(rec["bonus_no"])
    if len(numbers) != 6 or len(set(numbers)) != 6:
        raise ValueError(f"round {round_no}: need 6 distinct numbers, got {numbers}")
    if not all(NUM_MIN <= n <= NUM_MAX for n in (*numbers, bonus)):
        raise ValueError(f"round {round_no}: number out of range")
    if bonus in numbers:
        raise ValueError(f"round {round_no}: bonus repeats a main number")
    draw_date = str(rec["date"])[:10]
    if date.fromisoformat(draw_date) != expected_date(round_no):
        raise ValueError(f"round {round_no}: date {draw_date} is off the weekly schedule")

    divisions = list(rec.get("divisions") or [])
    divisions += [{}] * (5 - len(divisions))

    def _int(v):
        return int(v) if v is not None else None

    winners = tuple(_int(d.get("winners")) for d in divisions[:5])
    prizes = tuple(_int(d.get("prize")) for d in divisions[:5])
    combo = rec.get("winners_combination") or {}
    return RoundResult(
        round=round_no, draw_date=draw_date, numbers=numbers, bonus=bonus,
        sales=_int(rec.get("total_sales_amount")), winners=winners, prizes=prizes,
        auto=_int(combo.get("auto")), semi_auto=_int(combo.get("semi_auto")), manual=_int(combo.get("manual")),
    )


def parse_feed(records: list[dict]) -> tuple[list[RoundResult], list[str]]:
    """Parse many records. Bad ones are skipped and described in the returned problem list."""
    good, problems = [], []
    for rec in records:
        try:
            good.append(parse_record(rec))
        except (KeyError, TypeError, ValueError) as exc:
            problems.append(str(exc))
    good.sort(key=lambda r: r.round)
    return good, problems


def fetch_all(session: requests.Session | None = None) -> list[dict]:
    http = session or requests
    resp = http.get(FEED_ALL_URL, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError("feed did not return a list of rounds")
    return data


def sync(db_module, records: list[dict] | None = None) -> dict:
    """Bring the DB up to date with the feed.

    New rounds are inserted (numbers + stats). Rounds already present keep their stored numbers;
    if the feed disagrees with them the round is listed under 'conflicts' and left untouched.
    Returns {'new_rounds': [...], 'stats_rows': n, 'conflicts': [...], 'problems': [...]}.
    """
    if records is None:
        records = fetch_all()
    results, problems = parse_feed(records)
    db_module.init_db()
    existing = {d["round"]: d for d in db_module.get_all_draws()}
    new_rounds, conflicts, stats_rows = [], [], []
    for r in results:
        have = existing.get(r.round)
        if have is None:
            db_module.upsert_draw(r.round, r.draw_date, list(r.numbers), r.bonus, source=FEED_SOURCE, verified=True)
            new_rounds.append(r.round)
        else:
            stored = tuple(have[f"n{i}"] for i in range(1, 7))
            if stored != r.numbers or have["bonus"] != r.bonus:
                conflicts.append(r.round)
                continue
        stats_rows.append(r)
    db_module.upsert_stats(stats_rows)
    return {"new_rounds": new_rounds, "stats_rows": len(stats_rows), "conflicts": conflicts, "problems": problems}
