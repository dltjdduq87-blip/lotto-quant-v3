"""SQLite storage for historical Lotto 6/45 draws."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from lotto_quant_v3.config.settings import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS draws (
    round INTEGER PRIMARY KEY,
    draw_date TEXT NOT NULL,
    n1 INTEGER NOT NULL, n2 INTEGER NOT NULL, n3 INTEGER NOT NULL,
    n4 INTEGER NOT NULL, n5 INTEGER NOT NULL, n6 INTEGER NOT NULL,
    bonus INTEGER NOT NULL,
    source TEXT NOT NULL,
    verified INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS draw_stats (
    round INTEGER PRIMARY KEY,
    sales INTEGER,
    w1 INTEGER, w2 INTEGER, w3 INTEGER, w4 INTEGER, w5 INTEGER,
    p1 INTEGER, p2 INTEGER, p3 INTEGER, p4 INTEGER, p5 INTEGER,
    auto INTEGER, semi_auto INTEGER, manual INTEGER
);
"""


@contextmanager
def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(SCHEMA)


def upsert_draw(round_no: int, draw_date: str, numbers: list[int], bonus: int,
                 source: str, verified: bool):
    n = sorted(numbers)
    with connect() as conn:
        conn.execute(
            """INSERT INTO draws (round, draw_date, n1, n2, n3, n4, n5, n6,
                                   bonus, source, verified)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(round) DO UPDATE SET
                 draw_date=excluded.draw_date,
                 n1=excluded.n1, n2=excluded.n2, n3=excluded.n3,
                 n4=excluded.n4, n5=excluded.n5, n6=excluded.n6,
                 bonus=excluded.bonus,
                 source=excluded.source,
                 verified=excluded.verified""",
            (round_no, draw_date, *n, bonus, source, int(verified)),
        )


def get_all_draws() -> list[dict]:
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM draws ORDER BY round ASC").fetchall()
        return [dict(r) for r in rows]


def get_latest_round() -> int | None:
    with connect() as conn:
        row = conn.execute("SELECT MAX(round) FROM draws").fetchone()
        return row[0] if row and row[0] is not None else None


def count_draws() -> int:
    with connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM draws").fetchone()[0]


def upsert_stats(results) -> None:
    """Store per-round sales / winner counts / prizes (objects from data.results_feed)."""
    rows = [
        (r.round, r.sales, *r.winners, *r.prizes, r.auto, r.semi_auto, r.manual)
        for r in results
    ]
    if not rows:
        return
    with connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO draw_stats (round, sales, w1, w2, w3, w4, w5, p1, p2, p3, p4, p5, "
            "auto, semi_auto, manual) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )


def get_all_stats() -> list[dict]:
    """Draws joined with their sales / winner statistics (only rounds that have statistics)."""
    with connect() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT d.round, d.draw_date, d.n1, d.n2, d.n3, d.n4, d.n5, d.n6, d.bonus, s.sales, "
            "s.w1, s.w2, s.w3, s.w4, s.w5, s.p1, s.p2, s.p3, s.p4, s.p5, s.auto, s.semi_auto, s.manual "
            "FROM draws d JOIN draw_stats s ON s.round = d.round ORDER BY d.round ASC"
        ).fetchall()
        return [dict(r) for r in rows]
