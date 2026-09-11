from clearway.ais.parse import PositionReport
from clearway.ais.ports import PORTS
from clearway.ais.store import connect, insert_many


def report(mmsi: int) -> PositionReport:
    return PositionReport(
        mmsi=mmsi,
        ship_name="TEST",
        lat=-4.05,
        lon=39.65,
        sog=1.0,
        cog=2.0,
        port=PORTS[0],
        received_at="2026-09-11T00:00:00Z",
    )


def test_round_trips_reports(tmp_path):
    conn = connect(tmp_path / "nested" / "ais.sqlite3")
    assert insert_many(conn, [report(1), report(2)]) == 2
    rows = conn.execute("SELECT mmsi, port FROM position_report ORDER BY mmsi").fetchall()
    assert rows == [(1, "KEMBA"), (2, "KEMBA")]


def test_empty_insert_is_a_no_op(tmp_path):
    conn = connect(tmp_path / "ais.sqlite3")
    assert insert_many(conn, []) == 0
