"""Bill of lading template.

Laid out as the boxed form real B/Ls use, because the boxes are the
document's structure: a model reading one has to associate a value with the
box it sits in, not just find it on the page. Flowing it as free text would
make extraction easier than the real task.

Carries gross weight where the invoice carries net, and names a notify party
the invoice never mentions — both are places where documents can disagree,
which is what makes them worth reconciling.
"""

from clearway.corpus.canvas import Field, RecordingCanvas
from clearway.corpus.model import Shipment
from clearway.corpus.text import wrap

WIDTH, HEIGHT = 1240, 1754
LEFT, RIGHT = 70, WIDTH - 70
MID = 640


def _party_box(c: RecordingCanvas, prefix: str, heading: str, party, x: int, y: int, w: int) -> int:
    c.box((x, y, x + w, y + 128), outline="#999")
    c.label((x + 10, y + 8), heading)
    c.text(f"{prefix}_name", (x + 10, y + 28), party.name, size=14)
    for i, line in enumerate(party.address_lines):
        c.text(f"{prefix}_address_{i}", (x + 10, y + 54 + i * 22), line, size=12, fill="#333")
    return y + 128


def _field_box(
    c: RecordingCanvas, name: str, heading: str, value: str, x: int, y: int, w: int, h: int = 64
) -> None:
    c.box((x, y, x + w, y + h), outline="#999")
    c.label((x + 10, y + 8), heading)
    c.text(name, (x + 10, y + 26), value, size=13)


def render(
    shipment: Shipment,
    *,
    skip: frozenset[str] = frozenset(),
    overrides: dict[str, str] | None = None,
) -> tuple[RecordingCanvas, list[Field]]:
    c = RecordingCanvas(WIDTH, HEIGHT, skip=skip, overrides=overrides)

    c.text("document_title", (LEFT, 60), "BILL OF LADING", size=28)
    c.label((MID + 10, 58), "B/L NUMBER")
    c.text("bl_no", (RIGHT, 56), shipment.bl_no, size=17, anchor="ra")
    c.rule(LEFT, 104, RIGHT, fill="#222", width=2)

    y = 120
    half = MID - LEFT - 10
    _party_box(c, "shipper", "SHIPPER", shipment.seller, LEFT, y, half)
    _party_box(c, "consignee", "CONSIGNEE", shipment.buyer, MID, y, RIGHT - MID)
    y += 138
    _party_box(c, "notify", "NOTIFY PARTY", shipment.notify_party, LEFT, y, half)

    _field_box(c, "vessel", "VESSEL", shipment.vessel, MID, y, (RIGHT - MID) // 2 - 5)
    _field_box(
        c,
        "voyage",
        "VOYAGE NO.",
        shipment.voyage,
        MID + (RIGHT - MID) // 2 + 5,
        y,
        (RIGHT - MID) // 2 - 5,
    )
    _field_box(
        c,
        "port_of_loading",
        "PORT OF LOADING",
        str(shipment.port_of_loading),
        MID,
        y + 64,
        RIGHT - MID,
    )
    y += 138

    quarter = (RIGHT - LEFT) // 4 - 6
    for i, (name, heading, value) in enumerate(
        (
            ("port_of_discharge", "PORT OF DISCHARGE", str(shipment.port_of_discharge)),
            ("bl_date", "DATE OF ISSUE", f"{shipment.bl_date:%d %b %Y}"),
            ("freight_terms", "FREIGHT", shipment.freight_terms),
            ("reference", "SHIPMENT REFERENCE", shipment.reference),
        )
    ):
        _field_box(c, name, heading, value, LEFT + i * (quarter + 8), y, quarter)
    y += 76

    # ── cargo grid ──────────────────────────────────────────────────────────
    top = y
    c.rule(LEFT, top, RIGHT, fill="#222", width=2)
    columns = {"marks": LEFT, "desc": 330, "packages": 810, "gross": 980, "measurement": RIGHT}
    for key, heading, right in (
        ("marks", "CONTAINER / MARKS", False),
        ("desc", "DESCRIPTION OF PACKAGES AND GOODS", False),
        ("packages", "PACKAGES", True),
        ("gross", "GROSS KG", True),
        ("measurement", "MEASUREMENT", True),
    ):
        c.label((columns[key] - (74 if right else 0), top + 10), heading)
    c.rule(LEFT, top + 32, RIGHT, fill="#ccc")

    row = top + 48
    for index, item in enumerate(shipment.items):
        container = shipment.containers[index % len(shipment.containers)]
        lines = wrap(item.description, 40)
        c.text(f"item_{index}_container", (columns["marks"], row), container, size=12)
        c.text(
            f"item_{index}_marks", (columns["marks"], row + 20), item.marks, size=11, fill="#555"
        )
        c.text(f"item_{index}_description", (columns["desc"], row), lines[0], size=13)
        if len(lines) > 1:
            c.text(
                f"item_{index}_description_2",
                (columns["desc"], row + 20),
                lines[1],
                size=11,
                fill="#444",
            )
        c.text(
            f"item_{index}_hts", (columns["desc"], row + 40), f"HS {item.hts}", size=10, fill="#777"
        )
        c.text(
            f"item_{index}_packages",
            (columns["packages"], row),
            f"{item.cartons:,} CTN",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_gross_weight",
            (columns["gross"], row),
            f"{item.gross_weight_kg:,.3f}",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_measurement",
            (columns["measurement"], row),
            f"{item.volume_cbm:,.3f}",
            size=13,
            anchor="ra",
        )
        row += 66
        c.rule(LEFT, row - 14, RIGHT, fill="#eee")

    row += 10
    c.rule(700, row, RIGHT, fill="#222", width=2)
    row += 16
    c.label((720, row + 3), "TOTALS")
    c.text(
        "total_packages",
        (columns["packages"], row),
        f"{shipment.total_cartons:,} CTN",
        size=14,
        anchor="ra",
    )
    c.text(
        "total_gross_weight",
        (columns["gross"], row),
        f"{shipment.total_gross_weight:,.3f}",
        size=14,
        anchor="ra",
    )
    c.text(
        "total_measurement",
        (columns["measurement"], row),
        f"{shipment.total_volume_cbm:,.3f}",
        size=14,
        anchor="ra",
    )

    c.rule(LEFT, HEIGHT - 210, RIGHT, fill="#ccc")
    c.label((LEFT, HEIGHT - 196), "SHIPPED ON BOARD IN APPARENT GOOD ORDER AND CONDITION")
    c.text(
        "goods_statement",
        (LEFT, HEIGHT - 174),
        f"{shipment.total_cartons:,} CARTONS, {shipment.total_gross_weight:,.3f} KG GROSS",
        size=13,
    )
    c.label((LEFT, HEIGHT - 120), "PLACE AND DATE OF ISSUE")
    c.text(
        "place_of_issue",
        (LEFT, HEIGHT - 100),
        f"{shipment.port_of_loading.name}, {shipment.bl_date:%d %b %Y}",
        size=13,
    )
    c.rule(860, HEIGHT - 100, RIGHT, fill="#999")
    c.label((860, HEIGHT - 92), "FOR THE CARRIER")

    return c, c.fields
