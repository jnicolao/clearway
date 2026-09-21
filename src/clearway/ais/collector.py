"""Long-running AISStream collector.

Run this for six-plus weeks before the forecasting work needs it:

    uv run python -m clearway.ais.collector

Reconnects with exponential backoff. AISStream drops the connection if the
subscription doesn't arrive within three seconds of the socket opening, so
that write happens first thing.
"""

import asyncio
import fcntl
import json
import logging
import os
import pathlib
import signal
import sqlite3
from contextlib import suppress

import websockets

from clearway.ais.parse import parse_position_report
from clearway.ais.ports import PORTS, bounding_boxes
from clearway.ais.store import connect, insert_many

STREAM_URL = "wss://stream.aisstream.io/v0/stream"
FLUSH_EVERY = 50
FLUSH_SECONDS = 30.0
BACKOFF_START = 1.0
BACKOFF_MAX = 300.0

log = logging.getLogger("clearway.ais")


def subscription(api_key: str) -> str:
    return json.dumps(
        {
            "APIKey": api_key,
            "BoundingBoxes": bounding_boxes(),
            "FilterMessageTypes": ["PositionReport"],
        }
    )


async def _drain(ws, conn: sqlite3.Connection, stop: asyncio.Event) -> None:
    """Read frames until the socket closes, batching writes."""
    batch = []
    last_flush = asyncio.get_running_loop().time()

    def flush() -> None:
        nonlocal batch, last_flush
        if batch:
            log.info("wrote %d reports", insert_many(conn, batch))
            batch = []
        last_flush = asyncio.get_running_loop().time()

    async for frame in ws:
        if stop.is_set():
            break
        if isinstance(frame, bytes):
            frame = frame.decode("utf-8", errors="replace")
        try:
            envelope = json.loads(frame)
        except json.JSONDecodeError:
            log.warning("undecodable frame, skipping")
            continue

        if envelope.get("MessageType") == "Error":
            log.error("server error: %s", envelope.get("Message"))
            continue

        if (report := parse_position_report(envelope)) is not None:
            batch.append(report)

        now = asyncio.get_running_loop().time()
        if len(batch) >= FLUSH_EVERY or now - last_flush >= FLUSH_SECONDS:
            flush()

    flush()


async def run(api_key: str, db_path: str, stop: asyncio.Event) -> None:
    conn = connect(db_path)
    backoff = BACKOFF_START
    log.info("watching %s", ", ".join(p.name for p in PORTS))
    try:
        while not stop.is_set():
            try:
                async with websockets.connect(STREAM_URL) as ws:
                    await ws.send(subscription(api_key))
                    log.info("subscribed")
                    backoff = BACKOFF_START
                    await _drain(ws, conn, stop)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — must survive any transport fault
                if stop.is_set():
                    break
                log.warning("disconnected (%s); retrying in %.0fs", exc, backoff)
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
    finally:
        conn.close()
        log.info("collector stopped")


def acquire_lock(db_path: str):
    """Exclusive lock beside the database, held for the process lifetime.

    There are two ways to start this now — a terminal and a launchd agent —
    so two collectors writing the same rows is a real hazard rather than a
    theoretical one. The schema has no uniqueness constraint, so duplicates
    would land silently and skew every dwell-time figure derived from them.
    Returns None if another collector already holds the lock.
    """
    path = pathlib.Path(f"{db_path}.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    api_key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "AISSTREAM_API_KEY is not set. Get a free key at https://aisstream.io "
            "and put it in .env (see .env.example)."
        )

    db_path = os.environ.get("CLEARWAY_AIS_DB", "data/ais.sqlite3")
    lock = acquire_lock(db_path)
    if lock is None:
        raise SystemExit(
            f"another collector is already writing to {db_path}. "
            "Running two would put duplicate rows in the dataset."
        )

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop.set)

    try:
        await run(api_key, db_path, stop)
    finally:
        lock.close()


if __name__ == "__main__":
    asyncio.run(main())
