"""Automated future-round discovery via Google News search (no API key).

Google News publishes a public, unauthenticated RSS search feed
(news.google.com/rss/search) that is not the lotto operator's site and is
not bot-gated. For a given round, many independent Korean news outlets
publish the winning numbers directly in their article TITLE (e.g. "1236회
로또 1등 12, 18, 21, 29, 34, 38...보너스 10 - 뉴시스"), in varying
separator styles (comma, middle-dot '·'). We parse every title returned for
a round, tally which 6-number combination is reported and by how many
DISTINCT outlets, and only accept a result once at least `min_sources`
distinct outlets agree. Disagreement -> rejected, not guessed.

This is the mechanism used to extend the dataset past whatever the user's
authoritative Excel/DB import already covers, going forward as new draws
happen (weekly, Saturdays).
"""
import re
from collections import Counter
from datetime import date, timedelta
from urllib.parse import quote

import requests

from lotto_quant_v3.config.settings import FIRST_DRAW_DATE, REQUEST_HEADERS, REQUEST_TIMEOUT
from lotto_quant_v3.data.collector import DrawResult

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

_FIRST_DRAW = date.fromisoformat(FIRST_DRAW_DATE)

_TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S)
_NUMBER_RUN_RE = re.compile(r"(?:[0-9]{1,2}\s*[·,]\s*){5}[0-9]{1,2}")
_SPLIT_RE = re.compile(r"\s*[·,]\s*")
_BONUS_RE = re.compile(r"보너스\D{0,6}?([0-9]{1,2})")


def most_recent_draw_round(today: date | None = None) -> int:
    """Which round number was (or will be, if today IS a Saturday before the
    8:45pm KST draw -- we don't try to be that precise) most recently drawn,
    based on the fixed weekly Saturday cadence since round 1."""
    today = today or date.today()
    days_since_first = (today - _FIRST_DRAW).days
    return max(1, days_since_first // 7 + 1)


def _parse_titles(xml_text: str) -> list[str]:
    return [t for t in _TITLE_RE.findall(xml_text)]


def _outlet_of(title: str) -> str:
    return title.rsplit(" - ", 1)[-1].strip() if " - " in title else title


def _extract_candidates(title: str) -> tuple[list[tuple[int, ...]], int | None]:
    tickets = []
    for m in _NUMBER_RUN_RE.finditer(title):
        nums = [int(x) for x in _SPLIT_RE.split(m.group())]
        if len(nums) == 6 and len(set(nums)) == 6 and all(1 <= n <= 45 for n in nums):
            tickets.append(tuple(sorted(nums)))
    bonus = None
    bm = _BONUS_RE.search(title)
    if bm:
        b = int(bm.group(1))
        if 1 <= b <= 45:
            bonus = b
    return tickets, bonus


def fetch_round_via_news(round_no: int, min_sources: int = 2) -> DrawResult | None:
    """Search Google News for `{round}회 당첨번호`, and only return a result
    if >= min_sources DISTINCT outlets independently report the same 6
    numbers. Returns None (not a guess) if there's no quorum yet."""
    query = quote(f"로또 {round_no}회 당첨번호")
    url = GOOGLE_NEWS_RSS.format(query=query)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    titles = _parse_titles(resp.text)

    round_markers = (f"{round_no}회", f"{round_no:,}회")
    ticket_sources: dict[tuple[int, ...], set[str]] = {}
    bonus_sources: dict[int, set[str]] = {}

    for title in titles:
        if not any(marker in title for marker in round_markers):
            continue
        outlet = _outlet_of(title)
        tickets, bonus = _extract_candidates(title)
        for t in tickets:
            ticket_sources.setdefault(t, set()).add(outlet)
        if bonus is not None:
            bonus_sources.setdefault(bonus, set()).add(outlet)

    if not ticket_sources:
        return None
    best_ticket, best_outlets = max(ticket_sources.items(), key=lambda kv: len(kv[1]))
    if len(best_outlets) < min_sources:
        return None

    best_bonus = None
    if bonus_sources:
        best_bonus, bonus_outlets = max(bonus_sources.items(), key=lambda kv: len(kv[1]))
        if len(bonus_outlets) < 1 or best_bonus in best_ticket:
            best_bonus = None

    if best_bonus is None:
        return None  # need both main numbers AND bonus confirmed

    draw_date = (_FIRST_DRAW + timedelta(weeks=round_no - 1)).isoformat()
    result = DrawResult(round_no, draw_date, best_ticket, best_bonus)
    return result if result.is_structurally_valid() else None


def discover_new_rounds(latest_known_round: int, min_sources: int = 2) -> list[DrawResult]:
    """Fetch every round after `latest_known_round` up through the most
    recently-drawn round, via news search. Stops at the first round it
    can't confirm (rounds are drawn in order; no point guessing ahead)."""
    target = most_recent_draw_round()
    found = []
    for round_no in range(latest_known_round + 1, target + 1):
        result = fetch_round_via_news(round_no, min_sources=min_sources)
        if result is None:
            break
        found.append(result)
    return found
