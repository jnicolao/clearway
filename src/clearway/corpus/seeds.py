"""Build a Shipment from real public data plus a seeded RNG.

All randomness flows from the Random instance passed in. Nothing here calls
module-level `random` — an eval corpus that shifts between runs makes every
comparison between runs meaningless.
"""

import json
import pathlib
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from random import Random

from clearway.corpus.containers import make as make_container
from clearway.corpus.model import LineItem, Party, Port, Shipment

SEEDS = pathlib.Path(__file__).parent / "seeds"

# Used when the AIS database is empty, so the generator is never blocked on
# collector uptime. Real vessels calling at the ports we watch.
FALLBACK_VESSELS = (
    "MSC KALAMATA",
    "MAERSK CHENNAI",
    "EVER LOYAL",
    "CMA CGM NABUCCO",
    "ONE MODERN",
    "NORTHERN JAGUAR",
    "SEASPAN GUAYAQUIL",
    "KOTA NAGA",
)
INCOTERMS = ("FOB", "CIF", "CFR", "EXW", "DAP", "FCA")
CURRENCIES = ("USD", "EUR", "GBP")
FREIGHT_TERMS = ("FREIGHT PREPAID", "FREIGHT COLLECT")


def _load(name: str):
    return json.loads((SEEDS / name).read_text())


def vessels_from_ais(db_path: str | pathlib.Path) -> list[str]:
    """Distinct vessel names the collector has actually seen, newest first."""
    path = pathlib.Path(db_path)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        rows = conn.execute(
            "SELECT DISTINCT ship_name FROM position_report "
            "WHERE ship_name IS NOT NULL AND ship_name != '' "
            "ORDER BY received_at DESC LIMIT 200"
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    return [r[0].strip() for r in rows if r[0] and r[0].strip()]


DISTINCT_PREFIX = 40
MIN_LINE_ITEMS = 2


def _distinct_sample(rng: Random, pool: list[dict], k: int) -> list[dict]:
    """Pick up to k entries whose descriptions a reader could tell apart.

    Sibling HTS leaves often differ only in a trailing "Other", so a naive
    sample produces line items that render near-identically. That is faithful
    to the tariff schedule and useless as an extraction corpus: nothing says
    which extracted row belongs to which item.

    Returns fewer than k rather than padding with near-duplicates. A
    two-line invoice is realistic; two indistinguishable lines are not.
    """
    candidates = list(pool)
    rng.shuffle(candidates)
    chosen: list[dict] = []
    seen: set[str] = set()
    for entry in candidates:
        if len(chosen) >= k:
            break
        prefix = entry["description"][:DISTINCT_PREFIX]
        if prefix in seen:
            continue
        seen.add(prefix)
        chosen.append(entry)
    return chosen


def _party(rng: Random, parties: dict) -> Party:
    place = rng.choice(parties["cities"])
    name = " ".join(
        (
            rng.choice(parties["prefixes"]),
            rng.choice(parties["middles"]),
            rng.choice(parties["suffixes"]),
        )
    )
    return Party(
        name=name.upper(),
        street=f"{rng.randint(1, 240)} {rng.choice(parties['streets'])}",
        city=place["city"],
        country=place["country"],
    )


def _line_item(rng: Random, hs: dict, index: int) -> LineItem:
    quantity = rng.choice([12, 24, 48, 60, 100, 120, 240, 500, 1000, 1200])
    unit_price = Decimal(str(rng.randrange(150, 90_000) / 100)).quantize(Decimal("0.01"))
    per_unit_kg = Decimal(str(rng.randrange(20, 4_000) / 100))
    cartons = max(1, quantity // rng.choice([6, 12, 24]))
    return LineItem(
        description=hs["description"],
        hts=hs["hts"],
        quantity=quantity,
        unit=hs["unit"],
        unit_price=unit_price,
        net_weight_kg=(per_unit_kg * quantity).quantize(Decimal("0.001")),
        cartons=cartons,
        tare_per_carton_kg=Decimal(str(rng.randrange(30, 250) / 100)),
        carton_cm=(rng.randrange(20, 61), rng.randrange(20, 51), rng.randrange(15, 41)),
        marks=f"{rng.choice('ABCDEFGHJKLMN')}{rng.randrange(100, 999)}/{index + 1}",
    )


def build_shipment(rng: Random, *, ais_db: str | pathlib.Path | None = None) -> Shipment:
    hs_codes = _load("hs_codes.json")
    ports = [Port(**p) for p in _load("ports.json")]
    parties = _load("parties.json")

    seen = vessels_from_ais(ais_db) if ais_db else []
    vessel = rng.choice(seen) if seen else rng.choice(FALLBACK_VESSELS)

    loading, discharge = rng.sample(ports, 2)
    # One chapter per shipment: a container of cut flowers and gearboxes
    # together is not a shipment anyone would file.
    wanted = rng.randint(2, 5)
    chapters = sorted({h["chapter"] for h in hs_codes})
    rng.shuffle(chapters)
    chosen: list[dict] = []
    for chapter in chapters:
        pool = [h for h in hs_codes if h["chapter"] == chapter]
        candidate = _distinct_sample(rng, pool, wanted)
        if len(candidate) >= MIN_LINE_ITEMS:
            chosen = candidate
            break
    if not chosen:
        raise RuntimeError("no chapter in the seed can supply two distinct line items")
    items = [_line_item(rng, h, i) for i, h in enumerate(chosen)]

    invoice_date = date(2026, 1, 1) + timedelta(days=rng.randint(0, 250))
    serial = rng.randint(1000, 9999)
    # Goods are invoiced before they are loaded. A bill of lading dated
    # earlier than its invoice is one of the injected discrepancies later,
    # so it must not happen by accident here.
    bl_date = invoice_date + timedelta(days=rng.randint(1, 14))
    subtotal = sum((i.amount for i in items), Decimal("0.00"))

    return Shipment(
        reference=f"CW-{invoice_date:%Y%m}-{serial}",
        invoice_no=f"INV-{invoice_date:%Y}-{serial}",
        invoice_date=invoice_date,
        bl_no=f"{rng.choice(('MSCU', 'MAEU', 'CMDU', 'HLCU'))}{rng.randrange(10**8, 10**9)}",
        bl_date=bl_date,
        seller=_party(rng, parties),
        buyer=_party(rng, parties),
        notify_party=_party(rng, parties),
        port_of_loading=loading,
        port_of_discharge=discharge,
        vessel=vessel,
        voyage=f"{rng.randint(1, 399):03d}{rng.choice('ANEWS')}",
        incoterms=rng.choice(INCOTERMS),
        currency=rng.choice(CURRENCIES),
        freight=(subtotal * Decimal(str(rng.randrange(150, 900) / 10000))).quantize(
            Decimal("0.01")
        ),
        insurance=(subtotal * Decimal(str(rng.randrange(20, 150) / 10000))).quantize(
            Decimal("0.01")
        ),
        freight_terms=rng.choice(FREIGHT_TERMS),
        containers=[make_container(rng) for _ in range(rng.randint(1, 3))],
        items=items,
    )
