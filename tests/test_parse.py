"""Fixtures follow the envelope shape in the AISStream docs.

The two MetaData casings are both exercised deliberately: the published docs
disagree with each other, so the parser has to tolerate either.
"""

from clearway.ais.parse import parse_position_report

MOMBASA = (-4.05, 39.65)


def envelope(lat, lon, *, meta_case="upper", **meta_extra):
    upper = meta_case == "upper"
    lat_key, lon_key = ("Latitude", "Longitude") if upper else ("latitude", "longitude")
    meta = {"MMSI": 368207620, "ShipName": "EXAMPLE VESSEL", lat_key: lat, lon_key: lon}
    meta.update(meta_extra)
    return {
        "MessageType": "PositionReport",
        "MetaData": meta,
        "Message": {"PositionReport": {"MessageID": 1, "Sog": 12.4, "Cog": 86.7}},
    }


def test_parses_upper_case_metadata():
    report = parse_position_report(envelope(*MOMBASA))
    assert report is not None
    assert report.mmsi == 368207620
    assert report.ship_name == "EXAMPLE VESSEL"
    assert report.port.code == "KEMBA"
    assert report.sog == 12.4


def test_parses_lower_case_metadata():
    report = parse_position_report(envelope(*MOMBASA, meta_case="lower"))
    assert report is not None
    assert report.port.code == "KEMBA"


def test_uses_server_timestamp_when_present():
    stamp = "2026-09-11 12:00:00.000000000 +0000 UTC"
    report = parse_position_report(envelope(*MOMBASA, time_utc=stamp))
    assert report is not None and report.received_at == stamp


def test_falls_back_to_local_timestamp():
    report = parse_position_report(envelope(*MOMBASA))
    assert report is not None and report.received_at.startswith("20")


def test_drops_positions_outside_every_port_box():
    assert parse_position_report(envelope(51.5, -0.1)) is None


def test_drops_other_message_types():
    other = envelope(*MOMBASA) | {"MessageType": "ShipStaticData"}
    assert parse_position_report(other) is None


def test_survives_malformed_input():
    assert parse_position_report({}) is None
    assert parse_position_report({"MessageType": "PositionReport"}) is None
    assert parse_position_report({"MessageType": "PositionReport", "MetaData": []}) is None
    assert parse_position_report(envelope("not-a-number", 39.65)) is None
    assert parse_position_report(envelope(999.0, 39.65)) is None


def test_tolerates_missing_message_body():
    bare = {k: v for k, v in envelope(*MOMBASA).items() if k != "Message"}
    report = parse_position_report(bare)
    assert report is not None and report.sog is None


def test_parses_a_live_shaped_envelope():
    """Shape observed from real AISStream traffic on 2026-09-21.

    Durban, a berthed vessel reporting zero speed — which is the case that
    matters, since dwell time is measured from stationary vessels.
    """
    envelope = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 371987000,
            "ShipName": "GARNET ACE",
            "latitude": -29.8705,
            "longitude": 31.0348,
            "time_utc": "2026-09-21 11:05:54.186489655 +0000 UTC",
        },
        "Message": {"PositionReport": {"MessageID": 1, "Sog": 0.0, "Cog": 219.4}},
    }
    report = parse_position_report(envelope)
    assert report is not None
    assert report.ship_name == "GARNET ACE"
    assert report.port.code == "ZADUR"
    assert report.sog == 0.0
    assert report.received_at.endswith("+0000 UTC"), "server time, not our fallback"
