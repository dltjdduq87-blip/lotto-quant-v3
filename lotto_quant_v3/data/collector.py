"""Fetch Lotto 6/45 draw results and cross-validate across two independent
structured sources.

NOTE on the official dhlottery.co.kr API:
The historically well-known endpoint
    https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={n}
was confirmed (2026-08-10, via curl and a real headless browser, with and
without referer/cookies) to 302-redirect to the homepage rather than return
JSON. Public reporting corroborates this changed as part of a January 2026
site redesign. We do not attempt to bypass this (bot-detection bypass is out
of scope). Instead this module cross-checks two independent third-party
sources that mirror the official broadcast results:
  - lottolyzer.com (international lottery stats aggregator)
  - pyony.com (Korean lotto stats site)
If the two disagree for a given round, that round is rejected rather than
silently trusted.
"""
import re
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from lotto_quant_v3.config.settings import (
    LOTTOLYZER_HISTORY_URL,
    LOTTOLYZER_PAGE_SIZE,
    PYONY_ROUND_URL,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
)


@dataclass(frozen=True)
class DrawResult:
    round: int
    draw_date: str
    numbers: tuple[int, int, int, int, int, int]
    bonus: int

    def is_structurally_valid(self) -> bool:
        if len(set(self.numbers)) != 6:
            return False
        if not all(1 <= n <= 45 for n in self.numbers):
            return False
        if not (1 <= self.bonus <= 45) or self.bonus in self.numbers:
            return False
        return True


class DataSourceError(RuntimeError):
    pass


def _fetch_lottolyzer_page(page: int) -> dict[int, DrawResult]:
    url = LOTTOLYZER_HISTORY_URL.format(page=page, per_page=LOTTOLYZER_PAGE_SIZE)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="summary-table")
    if table is None:
        raise DataSourceError("lottolyzer: summary-table not found (page layout changed)")
    tbody = table.find("tbody")
    results: dict[int, DrawResult] = {}
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        round_no = int(cells[0].get_text(strip=True))
        date_str = cells[1].get_text(strip=True)
        nums_str = cells[2].get_text(strip=True)
        bonus_str = cells[3].get_text(strip=True)
        numbers = tuple(int(x) for x in nums_str.split(","))
        bonus = int(bonus_str)
        results[round_no] = DrawResult(round_no, date_str, numbers, bonus)
    return results


def fetch_lottolyzer(rounds_wanted: int = 50) -> dict[int, DrawResult]:
    """Paginate through lottolyzer's history table until enough rounds are
    collected (or the source runs out of pages)."""
    results: dict[int, DrawResult] = {}
    page = 1
    while len(results) < rounds_wanted:
        page_results = _fetch_lottolyzer_page(page)
        if not page_results:
            break
        results.update(page_results)
        page += 1
        if page > 200:  # hard safety cap
            break
    return results


def fetch_pyony(round_no: int) -> DrawResult | None:
    url = PYONY_ROUND_URL.format(round=round_no)
    resp = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    date_match = re.search(r"(20\d{2})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", text)
    if not date_match:
        return None
    draw_date = f"{date_match.group(1)}-{int(date_match.group(2)):02d}-{int(date_match.group(3)):02d}"

    balls = soup.select(".numberCircle strong")
    nums = [int(el.get_text(strip=True)) for el in balls if el.get_text(strip=True).isdigit()]
    if len(nums) == 7:
        main6, bonus = tuple(sorted(nums[:6])), nums[6]
        return DrawResult(round_no, draw_date, main6, bonus)
    return None


def cross_validated_history(rounds_wanted: int = 50) -> list[DrawResult]:
    """Fetch from lottolyzer, spot-check a sample of rounds against pyony,
    and return only structurally-valid, cross-confirmed rows."""
    primary = fetch_lottolyzer(rounds_wanted=rounds_wanted)
    validated: list[DrawResult] = []
    rounds = sorted(primary.keys())
    # Spot-check the latest round plus every 5th round to bound request volume.
    check_set = set(rounds[-1:]) | set(rounds[::5])
    for round_no in rounds:
        draw = primary[round_no]
        if not draw.is_structurally_valid():
            continue
        if round_no in check_set:
            try:
                secondary = fetch_pyony(round_no)
            except (requests.RequestException, DataSourceError):
                secondary = None
            if secondary is not None:
                if sorted(secondary.numbers) != sorted(draw.numbers) or secondary.bonus != draw.bonus:
                    continue  # disagreement -> reject, do not trust silently
        validated.append(draw)
    return validated
