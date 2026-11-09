"""Turn an AISStream envelope into a row we can store.

Pure functions only — no network, no database. Everything here is directly
testable against recorded fixtures, which is what makes CI on this package
worth running.

AISStream's documentation describes MetaData as free-form and is inconsistent
about its casing (`Latitude` in one place, `latitude` in another), so lookups
are case-insensitive and stay that way.

Confirmed against live traffic on 2026-09-21: `time_utc` is present and
carries the server's own timestamp, so rows record when the server saw a
vessel rather than when we happened to read the socket. Only genuinely
distinct spellings are listed below now — `_first` already lowercases both
sides, so passing "Latitude" and "latitude" was the same lookup twice.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from clearway.ais.ports import Port, port_for

POSITION_REPORT = "PositionReport"


@dataclass(frozen=True)
class PositionReport:
    mmsi: int
    ship_name: str | None
    lat: float
    lon: float
    sog: float | None
    cog: float | None
    port: Port
    received_at: str


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    """Value of the first key present, case-insensitively."""
    lowered = {k.lower(): v for k, v in mapping.items()}
    for key in keys:
        if (value := lowered.get(key.lower())) is not None:
            return value
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def parse_position_report(envelope: dict[str, Any]) -> PositionReport | None:
    """Parse one AISStream envelope, or None if it isn't a usable position.

    Returns None — never raises — for anything malformed, off-schema, or
    outside our port boxes. A collector that dies on one odd frame is a
    collector that loses a weekend of data.
    """
    if not isinstance(envelope, dict):
        return None
    if envelope.get("MessageType") != POSITION_REPORT:
        return None

    meta = envelope.get("MetaData")
    if not isinstance(meta, dict):
        return None

    lat = _as_float(_first(meta, "latitude"))
    lon = _as_float(_first(meta, "longitude"))
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None

    port = port_for(lat, lon)
    if port is None:
        return None

    mmsi = _first(meta, "mmsi", "UserID")
    if not isinstance(mmsi, int) or isinstance(mmsi, bool):
        return None

    body = envelope.get("Message")
    report = body.get(POSITION_REPORT) if isinstance(body, dict) else None
    report = report if isinstance(report, dict) else {}

    name = _first(meta, "shipname")
    name = name.strip() or None if isinstance(name, str) else None

    return PositionReport(
        mmsi=mmsi,
        ship_name=name,
        lat=lat,
        lon=lon,
        sog=_as_float(_first(report, "sog")),
        cog=_as_float(_first(report, "cog")),
        port=port,
        received_at=_first(meta, "time_utc", "timeutc") or datetime.now(UTC).isoformat(),
    )
