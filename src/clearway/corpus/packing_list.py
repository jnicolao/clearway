"""Packing list template.

Carries quantities, packages and weights but no prices — that separation is
the point of the document, and it is what makes a quantity disagreement
between this and the invoice a discrepancy worth detecting rather than a
formatting difference.
"""

from clearway.corpus.canvas import Field, RecordingCanvas
from clearway.corpus.model import Shipment
from clearway.corpus.text import wrap

WIDTH, HEIGHT = 1240, 1754
LEFT, RIGHT = 70, WIDTH - 70

COLUMNS = {
    "marks": LEFT,
    "desc": 200,
    "cartons": 690,
    "qty": 830,
    "net": 960,
    "gross": 1080,
    "volume": RIGHT,
}
ROW_HEIGHT = 62
DESC_WRAP = 44


def render(
    shipment: Shipment,
    *,
    skip: frozenset[str] = frozenset(),
    overrides: dict[str, str] | None = None,
) -> tuple[RecordingCanvas, list[Field]]:
    c = RecordingCanvas(WIDTH, HEIGHT, skip=skip, overrides=overrides)

    c.text("document_title", (LEFT, 64), "PACKING LIST", size=30)
    c.rule(LEFT, 112, RIGHT, fill="#222", width=2)

    c.label((RIGHT - 300, 66), "INVOICE NO.")
    c.text("invoice_no", (RIGHT, 64), shipment.invoice_no, size=15, anchor="ra")
    c.label((RIGHT - 300, 88), "DATE")
    c.text("invoice_date", (RIGHT, 86), f"{shipment.invoice_date:%d %b %Y}", size=15, anchor="ra")

    for prefix, party, x, heading in (
        ("seller", shipment.seller, LEFT, "SHIPPER / EXPORTER"),
        ("buyer", shipment.buyer, 660, "CONSIGNEE"),
    ):
        c.label((x, 148), heading)
        c.text(f"{prefix}_name", (x, 168), party.name, size=15)
        for i, line in enumerate(party.address_lines):
            c.text(f"{prefix}_address_{i}", (x, 194 + i * 22), line, size=12, fill="#333")

    c.rule(LEFT, 290, RIGHT, fill="#ccc")
    details = (
        ("vessel", "VESSEL", shipment.vessel),
        ("voyage", "VOYAGE", shipment.voyage),
        ("port_of_loading", "PORT OF LOADING", str(shipment.port_of_loading)),
        ("port_of_discharge", "PORT OF DISCHARGE", str(shipment.port_of_discharge)),
        ("containers", "CONTAINER NO.", ", ".join(shipment.containers)),
        ("reference", "SHIPMENT REFERENCE", shipment.reference),
    )
    for i, (name, label, value) in enumerate(details):
        x = LEFT + (i % 3) * 380
        y = 308 + (i // 3) * 52
        c.label((x, y), label)
        c.text(name, (x, y + 18), value, size=13)

    top = 430
    c.rule(LEFT, top, RIGHT, fill="#222", width=2)
    for key, heading, right in (
        ("marks", "MARKS", False),
        ("desc", "DESCRIPTION OF GOODS", False),
        ("cartons", "CTNS", True),
        ("qty", "QUANTITY", True),
        ("net", "NET KG", True),
        ("gross", "GROSS KG", True),
        ("volume", "CBM", True),
    ):
        x = COLUMNS[key] - (58 if right else 0)
        c.label((x, top + 10), heading)
    c.rule(LEFT, top + 32, RIGHT, fill="#ccc")

    y = top + 48
    for index, item in enumerate(shipment.items):
        lines = wrap(item.description, DESC_WRAP)
        c.text(f"item_{index}_marks", (COLUMNS["marks"], y), item.marks, size=13)
        c.text(f"item_{index}_description", (COLUMNS["desc"], y), lines[0], size=13)
        if len(lines) > 1:
            c.text(
                f"item_{index}_description_2",
                (COLUMNS["desc"], y + 20),
                lines[1],
                size=11,
                fill="#444",
            )
        c.text(
            f"item_{index}_dimensions",
            (COLUMNS["desc"], y + 40),
            item.dimensions,
            size=10,
            fill="#777",
        )
        c.text(
            f"item_{index}_cartons",
            (COLUMNS["cartons"], y),
            f"{item.cartons:,}",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_quantity",
            (COLUMNS["qty"], y),
            f"{item.quantity:,} {item.unit}",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_net_weight",
            (COLUMNS["net"], y),
            f"{item.net_weight_kg:,.3f}",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_gross_weight",
            (COLUMNS["gross"], y),
            f"{item.gross_weight_kg:,.3f}",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_volume",
            (COLUMNS["volume"], y),
            f"{item.volume_cbm:,.3f}",
            size=13,
            anchor="ra",
        )
        y += ROW_HEIGHT
        c.rule(LEFT, y - 14, RIGHT, fill="#eee")

    y += 12
    c.rule(600, y, RIGHT, fill="#222", width=2)
    y += 16
    c.label((620, y + 3), "TOTALS")
    c.text(
        "total_cartons",
        (COLUMNS["cartons"], y),
        f"{shipment.total_cartons:,}",
        size=14,
        anchor="ra",
    )
    c.text(
        "total_net_weight",
        (COLUMNS["net"], y),
        f"{shipment.total_net_weight:,.3f}",
        size=14,
        anchor="ra",
    )
    c.text(
        "total_gross_weight",
        (COLUMNS["gross"], y),
        f"{shipment.total_gross_weight:,.3f}",
        size=14,
        anchor="ra",
    )
    c.text(
        "total_volume",
        (COLUMNS["volume"], y),
        f"{shipment.total_volume_cbm:,.3f}",
        size=14,
        anchor="ra",
    )

    c.rule(LEFT, HEIGHT - 190, RIGHT, fill="#ccc")
    c.label((LEFT, HEIGHT - 176), "TOTAL PACKAGES")
    c.text(
        "packages_statement", (LEFT, HEIGHT - 156), f"{shipment.total_cartons:,} CARTONS", size=14
    )
    c.rule(860, HEIGHT - 100, RIGHT, fill="#999")
    c.label((860, HEIGHT - 92), "AUTHORISED SIGNATURE")

    return c, c.fields
