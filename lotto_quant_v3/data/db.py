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
        conn.execute(SCHEMA)


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
