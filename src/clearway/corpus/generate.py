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
from clearway.corpus.discrepancies import Injection, inject
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


def write_bundle(shipment: Shipment, out: pathlib.Path, injection: Injection | None = None) -> None:
    injection = injection or Injection()
    out.mkdir(parents=True, exist_ok=True)

    # The shipment is the truth and is written unmodified. Injections live in
    # the documents and in discrepancies.json, never here.
    (out / "shipment.json").write_text(
        json.dumps(shipment_dict(shipment), indent=2, default=_jsonable, sort_keys=True) + "\n"
    )
    (out / "discrepancies.json").write_text(
        json.dumps(
            {
                "clean": not injection.discrepancies,
                "discrepancies": [d.as_dict() for d in injection.discrepancies],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    for slug, (document, render) in DOCUMENTS.items():
        if slug in injection.omitted:
            continue
        canvas, fields = render(shipment, overrides=injection.for_document(slug))
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
    ap.add_argument(
        "--discrepancy-rate",
        type=float,
        default=0.6,
        help=(
            "fraction of bundles carrying at least one defect. The remainder are "
            "clean, and clean bundles are not filler — without them the "
            "false-positive rate is unmeasurable."
        ),
    )
    ap.add_argument("--max-discrepancies", type=int, default=2)
    args = ap.parse_args()

    if not 0.0 <= args.discrepancy_rate <= 1.0:
        ap.error("--discrepancy-rate must be between 0 and 1")

    rng = Random(args.seed)
    clean = 0
    for n in range(args.count):
        shipment = build_shipment(rng, ais_db=args.ais_db)
        count = (
            rng.randint(1, args.max_discrepancies) if rng.random() < args.discrepancy_rate else 0
        )
        injection = inject(rng, shipment, count)
        clean += not injection.discrepancies
        target = args.out / f"{args.seed}-{n:04d}"
        write_bundle(shipment, target, injection)
        labels = (
            ", ".join(d.type for d in injection.discrepancies)
            if injection.discrepancies
            else "clean"
        )
        docs = len(DOCUMENTS) - len(injection.omitted)
        print(f"{target}  {shipment.invoice_no}  {docs} docs  {labels}")
    print(f"\n{args.count} bundles, {clean} clean, {args.count - clean} with defects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
