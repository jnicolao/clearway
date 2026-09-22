"""Generate bundles.

uv run python -m clearway.corpus.generate --seed 7 --count 3 --out out/
"""

import argparse
import json
import pathlib
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from random import Random

from clearway.corpus import bill_of_lading, invoice, packing_list
from clearway.corpus.model import Shipment
from clearway.corpus.seeds import build_shipment

DEFAULT_AIS_DB = "data/ais.sqlite3"

# One entry per document type. Adding a template here is all it takes for it
# to be generated and, more importantly, for the bounding-box verification in
# the test suite to cover it — that parametrisation is deliberate, so a new
# template cannot quietly ship without its boxes being checked.
DOCUMENTS = {
    "invoice": ("commercial_invoice", invoice.render),
    "packing_list": ("packing_list", packing_list.render),
    "bill_of_lading": ("bill_of_lading", bill_of_lading.render),
}


def _jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"not serialisable: {type(value).__name__}")


def shipment_dict(shipment: Shipment) -> dict:
    data = asdict(shipment)
    data["subtotal"] = shipment.subtotal
    data["total"] = shipment.total
    data["total_net_weight"] = shipment.total_net_weight
    data["total_cartons"] = shipment.total_cartons
    for raw, item in zip(data["items"], shipment.items, strict=True):
        raw["amount"] = item.amount
    return data


def write_bundle(shipment: Shipment, out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "shipment.json").write_text(
        json.dumps(shipment_dict(shipment), indent=2, default=_jsonable, sort_keys=True) + "\n"
    )
    for slug, (document, render) in DOCUMENTS.items():
        canvas, fields = render(shipment)
        # optimize=False keeps PNG bytes a pure function of the pixels, which
        # is what determinism across machines rests on.
        canvas.image.save(out / f"{slug}.png", format="PNG", optimize=False, compress_level=6)
        (out / f"{slug}.json").write_text(
            json.dumps(
                {"document": document, "fields": [f.as_dict() for f in fields]},
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate shipment document bundles.")
    ap.add_argument("--seed", type=int, required=True, help="RNG seed; same seed, same corpus")
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--out", type=pathlib.Path, default=pathlib.Path("out"))
    ap.add_argument("--ais-db", default=DEFAULT_AIS_DB, help="vessel names; falls back to seeds")
    args = ap.parse_args()

    rng = Random(args.seed)
    for n in range(args.count):
        shipment = build_shipment(rng, ais_db=args.ais_db)
        target = args.out / f"{args.seed}-{n:04d}"
        write_bundle(shipment, target)
        summary = f"{len(shipment.items)} items  {shipment.currency} {shipment.total:,.2f}"
        print(f"{target}  {shipment.invoice_no}  {len(DOCUMENTS)} docs  {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
