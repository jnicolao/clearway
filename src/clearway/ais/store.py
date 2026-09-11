"""SQLite sink for collected position reports.

SQLite rather than Postgres on purpose: this writes a few thousand rows a day
for six weeks and is read by one analysis job. Standing up a database server
for that is cost without benefit. Raw reports are stored as received — dwell
times get derived later, and you can always re-derive from raw.
"""

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from clearway.ais.parse import PositionReport

SCHEMA = """
CREATE TABLE IF NOT EXISTS position_report (
    id          INTEGER PRIMARY KEY,
    mmsi        INTEGER NOT NULL,
    ship_name   TEXT,
    lat         REAL    NOT NULL,
    lon         REAL    NOT NULL,
    sog         REAL,
    cog         REAL,
    port        TEXT    NOT NULL,
    received_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_port_time ON position_report (port, received_at);
CREATE INDEX IF NOT EXISTS idx_mmsi_time ON position_report (mmsi, received_at);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def insert_many(conn: sqlite3.Connection, reports: Iterable[PositionReport]) -> int:
    rows = [
        (r.mmsi, r.ship_name, r.lat, r.lon, r.sog, r.cog, r.port.code, r.received_at)
        for r in reports
    ]
    if not rows:
        return 0
    conn.executemany(
        "INSERT INTO position_report "
        "(mmsi, ship_name, lat, lon, sog, cog, port, received_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)
