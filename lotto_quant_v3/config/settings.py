"""Central configuration for LOTTO 6/45 QUANT V3."""
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "lotto.db"
REPORTS_DIR = ROOT_DIR / "reports"

NUM_MIN = 1
NUM_MAX = 45
PICK_SIZE = 6

PORTFOLIO_SIZE = 5

# Known-broken as of 2026-01 site redesign (confirmed: redirects to homepage
# regardless of client/headers/cookies). Kept only for documentation/retry.
DHLOTTERY_OFFICIAL_API = "https://www.dhlottery.co.kr/common.do?method=getLottoNumber&drwNo={round}"

# Working third-party structured sources used for cross-validation.
LOTTOLYZER_HISTORY_URL = (
    "https://en.lottolyzer.com/history/south-korea/6_slash_45-lotto/"
    "page/{page}/per-page/{per_page}/summary"
)
LOTTOLYZER_PAGE_SIZE = 50  # server-enforced cap observed empirically
PYONY_ROUND_URL = "https://pyony.com/lotto/rounds/{round}/"

REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (LottoQuantV3 research collector)"}
REQUEST_TIMEOUT = 15

# First draw was 2002-12-07 (round 1), weekly on Saturdays.
FIRST_DRAW_DATE = "2002-12-07"
