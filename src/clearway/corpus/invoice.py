"""Commercial invoice template.

Layout is computed entirely from the Shipment, never from what has already
been drawn. That is what lets `skip` omit a field's ink without moving
anything else — which is what the bounding-box verification depends on.
"""

from clearway.corpus.canvas import Field, RecordingCanvas
from clearway.corpus.model import Shipment
from clearway.corpus.text import money as _money
from clearway.corpus.text import wrap as _wrap

# A4 at 150 dpi.
WIDTH, HEIGHT = 1240, 1754
LEFT, RIGHT = 70, WIDTH - 70

COLUMNS = {"desc": LEFT, "hts": 640, "qty": 830, "unit_price": 980, "amount": RIGHT}
ROW_HEIGHT = 56
DESC_WRAP = 52


def render(
    shipment: Shipment, *, skip: frozenset[str] = frozenset()
) -> tuple[RecordingCanvas, list[Field]]:
    c = RecordingCanvas(WIDTH, HEIGHT, skip=skip)

    # ── header ──────────────────────────────────────────────────────────────
    c.text("document_title", (LEFT, 64), "COMMERCIAL INVOICE", size=30)
    c.rule(LEFT, 112, RIGHT, fill="#222", width=2)

    c.label((RIGHT - 300, 66), "INVOICE NO.")
    c.text("invoice_no", (RIGHT, 64), shipment.invoice_no, size=15, anchor="ra")
    c.label((RIGHT - 300, 88), "DATE")
    c.text("invoice_date", (RIGHT, 86), f"{shipment.invoice_date:%d %b %Y}", size=15, anchor="ra")

    # ── parties ─────────────────────────────────────────────────────────────
    for prefix, party, x in (("seller", shipment.seller, LEFT), ("buyer", shipment.buyer, 660)):
        c.label((x, 148), "SELLER / EXPORTER" if prefix == "seller" else "BUYER / CONSIGNEE")
        c.text(f"{prefix}_name", (x, 168), party.name, size=15)
        for i, line in enumerate(party.address_lines):
            c.text(f"{prefix}_address_{i}", (x, 194 + i * 22), line, size=12, fill="#333")

    # ── shipment details ────────────────────────────────────────────────────
    c.rule(LEFT, 290, RIGHT, fill="#ccc")
    details = (
        ("vessel", "VESSEL", shipment.vessel),
        ("voyage", "VOYAGE", shipment.voyage),
        ("port_of_loading", "PORT OF LOADING", str(shipment.port_of_loading)),
        ("port_of_discharge", "PORT OF DISCHARGE", str(shipment.port_of_discharge)),
        ("incoterms", "INCOTERMS", shipment.incoterms),
        ("currency", "CURRENCY", shipment.currency),
    )
    for i, (name, label, value) in enumerate(details):
        x = LEFT + (i % 3) * 380
        y = 308 + (i // 3) * 52
        c.label((x, y), label)
        c.text(name, (x, y + 18), value, size=13)

    # ── line items ──────────────────────────────────────────────────────────
    top = 430
    c.rule(LEFT, top, RIGHT, fill="#222", width=2)
    for key, heading, anchor in (
        ("desc", "DESCRIPTION OF GOODS", "la"),
        ("hts", "HS CODE", "la"),
        ("qty", "QTY", "ra"),
        ("unit_price", "UNIT PRICE", "ra"),
        ("amount", "AMOUNT", "ra"),
    ):
        x = COLUMNS[key] - (60 if anchor == "ra" else 0)
        c.label((x if anchor == "la" else COLUMNS[key] - 60, top + 10), heading)
    c.rule(LEFT, top + 32, RIGHT, fill="#ccc")

    y = top + 48
    for index, item in enumerate(shipment.items):
        lines = _wrap(item.description, DESC_WRAP)
        c.text(f"item_{index}_description", (COLUMNS["desc"], y), lines[0], size=13)
        if len(lines) > 1:
            c.text(
                f"item_{index}_description_2",
                (COLUMNS["desc"], y + 20),
                lines[1],
                size=11,
                fill="#444",
            )
        c.text(f"item_{index}_hts", (COLUMNS["hts"], y), item.hts, size=13)
        c.text(
            f"item_{index}_quantity",
            (COLUMNS["qty"], y),
            f"{item.quantity:,} {item.unit}",
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_unit_price",
            (COLUMNS["unit_price"], y),
            _money(item.unit_price),
            size=13,
            anchor="ra",
        )
        c.text(
            f"item_{index}_amount",
            (COLUMNS["amount"], y),
            _money(item.amount),
            size=13,
            anchor="ra",
        )
        y += ROW_HEIGHT
        c.rule(LEFT, y - 14, RIGHT, fill="#eee")

    # ── totals ──────────────────────────────────────────────────────────────
    y += 12
    c.rule(760, y, RIGHT, fill="#222", width=2)
    y += 14
    for name, label, value in (
        ("subtotal", "SUBTOTAL", shipment.subtotal),
        ("freight", "FREIGHT", shipment.freight),
        ("insurance", "INSURANCE", shipment.insurance),
    ):
        c.label((780, y + 3), label)
        c.text(name, (COLUMNS["amount"], y), _money(value), size=13, anchor="ra")
        y += 30

    c.rule(760, y + 2, RIGHT, fill="#ccc")
    y += 16
    c.label((780, y + 6), f"TOTAL {shipment.currency}")
    c.text("total", (COLUMNS["amount"], y), _money(shipment.total), size=19, anchor="ra")

    # ── footer ──────────────────────────────────────────────────────────────
    c.rule(LEFT, HEIGHT - 190, RIGHT, fill="#ccc")
    c.label((LEFT, HEIGHT - 176), "SHIPMENT REFERENCE")
    c.text("reference", (LEFT, HEIGHT - 158), shipment.reference, size=13)
    c.label((LEFT, HEIGHT - 108), "TOTAL NET WEIGHT")
    c.text("total_net_weight", (LEFT, HEIGHT - 90), f"{shipment.total_net_weight:,.3f} KG", size=13)
    c.label((660, HEIGHT - 108), "TOTAL PACKAGES")
    c.text("total_cartons", (660, HEIGHT - 90), f"{shipment.total_cartons:,} CTN", size=13)
    c.rule(860, HEIGHT - 100, RIGHT, fill="#999")
    c.label((860, HEIGHT - 92), "AUTHORISED SIGNATURE")

    return c, c.fields
