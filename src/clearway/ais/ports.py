"""Ports we collect vessel traffic for.

Bounding boxes are deliberately tight around each harbour: AISStream bills
nothing, but a wide box floods the stream with transiting vessels that never
call at the port, which is noise for dwell-time work.

Each box is (south, west, north, east) in decimal degrees.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Port:
    code: str
    name: str
    south: float
    west: float
    north: float
    east: float

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def as_bounding_box(self) -> list[list[float]]:
        """AISStream wants [[lat, lon], [lat, lon]] corner pairs."""
        return [[self.south, self.west], [self.north, self.east]]


PORTS: tuple[Port, ...] = (
    Port("KEMBA", "Mombasa", -4.15, 39.55, -3.95, 39.75),
    Port("TZDAR", "Dar es Salaam", -6.90, 39.25, -6.75, 39.45),
    Port("ZADUR", "Durban", -29.95, 31.00, -29.83, 31.10),
)


def port_for(lat: float, lon: float) -> Port | None:
    """First port whose box contains this position, or None."""
    for port in PORTS:
        if port.contains(lat, lon):
            return port
    return None


def bounding_boxes() -> list[list[list[float]]]:
    return [p.as_bounding_box() for p in PORTS]
