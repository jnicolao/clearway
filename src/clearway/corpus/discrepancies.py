"""Inject known inconsistencies into a bundle.

This is the reconciliation label set. Nothing here mutates the Shipment —
injections are render-time overrides, so shipment.json stays the canonical
truth, the documents diverge from it in recorded ways, and discrepancies.json
says exactly where. That triple is what makes the labels exact.

Two classes of defect, because a reconciler needs both:

  * cross-document — two papers disagree about the same fact. Only detectable
    by holding them side by side, which is the task this corpus exists for.
  * within-document — a paper contradicts itself. Detectable from one page,
    and worth catching because real filings do it constantly.

An injection keeps its own document internally consistent unless the defect
IS the internal inconsistency. Changing a bill of lading's total gross weight
without changing the line it sums from would create a second, unlabelled
defect — and an unlabelled defect poisons the false-positive rate.

`currency_confusion` from the scope doc is deliberately absent: it needs a
customs declaration, which is not one of the three documents yet. It comes
back when that document does, rather than being faked against the invoice.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from random import Random
from typing import Any

from clearway.corpus.model import Shipment

CROSS_DOCUMENT = "cross_document"
WITHIN_DOCUMENT = "within_document"


@dataclass(frozen=True)
class Discrepancy:
    type: str
    scope: str
    documents: list[str]
    fields: dict[str, list[str]]
    truth: str
    stated: str
    note: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "scope": self.scope,
            "documents": sorted(self.documents),
            "fields": {k: sorted(v) for k, v in sorted(self.fields.items())},
            "truth": self.truth,
            "stated": self.stated,
            "note": self.note,
        }


@dataclass
class Injection:
    """Overrides to apply, documents to omit, and the labels describing both."""

    overrides: dict[str, dict[str, str]] = field(default_factory=dict)
    omitted: list[str] = field(default_factory=list)
    discrepancies: list[Discrepancy] = field(default_factory=list)

    def for_document(self, slug: str) -> dict[str, str]:
        return self.overrides.get(slug, {})


def _values(slug: str, shipment: Shipment) -> dict[str, str]:
    """What a document says with nothing injected.

    Read from an actual render so a recorded `truth` is the exact string the
    clean document would have carried, not a re-derivation that might format
    differently.
    """
    from clearway.corpus.generate import DOCUMENTS

    _, fields = DOCUMENTS[slug][1](shipment)
    return {f.name: f.value for f in fields}


def _nudge(rng: Random, value: Decimal, places: str = "0.001") -> Decimal:
    """Change a number enough to be unambiguous, not so much it is absurd."""
    factor = Decimal(str(rng.choice([0.82, 0.9, 1.12, 1.25, 1.4])))
    return (value * factor).quantize(Decimal(places))


# ── injectors ───────────────────────────────────────────────────────────────
# Each returns an Injection contribution, or None when this shipment cannot
# carry that defect.


def quantity_mismatch(rng: Random, shipment: Shipment) -> Injection | None:
    index = rng.randrange(len(shipment.items))
    item = shipment.items[index]
    truth = _values("packing_list", shipment)[f"item_{index}_quantity"]
    stated_qty = max(1, int(item.quantity * rng.choice([0.75, 0.9, 1.2, 1.5])))
    stated = f"{stated_qty:,} {item.unit}"
    if stated == truth:
        return None
    return Injection(
        overrides={"packing_list": {f"item_{index}_quantity": stated}},
        discrepancies=[
            Discrepancy(
                type="quantity_mismatch",
                scope=CROSS_DOCUMENT,
                documents=["commercial_invoice", "packing_list"],
                fields={"packing_list": [f"item_{index}_quantity"]},
                truth=truth,
                stated=stated,
                note=f"packing list line {index + 1} disagrees with the invoice quantity",
            )
        ],
    )


def party_mismatch(rng: Random, shipment: Shipment) -> Injection | None:
    truth = shipment.buyer.name
    stated = truth.replace(" LTD", " TRADING LTD") if " LTD" in truth else f"{truth} (AGENT)"
    if stated == truth:
        return None
    return Injection(
        overrides={"bill_of_lading": {"consignee_name": stated}},
        discrepancies=[
            Discrepancy(
                type="party_mismatch",
                scope=CROSS_DOCUMENT,
                documents=["commercial_invoice", "bill_of_lading"],
                fields={"bill_of_lading": ["consignee_name"]},
                truth=truth,
                stated=stated,
                note="consignee on the bill of lading is not the invoice buyer",
            )
        ],
    )


def weight_mismatch(rng: Random, shipment: Shipment) -> Injection | None:
    index = rng.randrange(len(shipment.items))
    item = shipment.items[index]
    stated_item = _nudge(rng, item.gross_weight_kg)
    delta = stated_item - item.gross_weight_kg
    if delta == 0:
        return None
    stated_total = (shipment.total_gross_weight + delta).quantize(Decimal("0.001"))
    # The line and the total move together, so the bill of lading still adds
    # up. The only disagreement is with the packing list, which is the label.
    return Injection(
        overrides={
            "bill_of_lading": {
                f"item_{index}_gross_weight": f"{stated_item:,.3f}",
                "total_gross_weight": f"{stated_total:,.3f}",
                "goods_statement": (
                    f"{shipment.total_cartons:,} CARTONS, {stated_total:,.3f} KG GROSS"
                ),
            }
        },
        discrepancies=[
            Discrepancy(
                type="weight_mismatch",
                scope=CROSS_DOCUMENT,
                documents=["packing_list", "bill_of_lading"],
                fields={
                    "bill_of_lading": [
                        f"item_{index}_gross_weight",
                        "total_gross_weight",
                        "goods_statement",
                    ]
                },
                truth=f"{shipment.total_gross_weight:,.3f}",
                stated=f"{stated_total:,.3f}",
                note="bill of lading gross weight disagrees with the packing list",
            )
        ],
    )


def date_inconsistency(rng: Random, shipment: Shipment) -> Injection | None:
    from datetime import timedelta

    stated_date = shipment.invoice_date - timedelta(days=rng.randint(1, 20))
    stated = f"{stated_date:%d %b %Y}"
    truth = f"{shipment.bl_date:%d %b %Y}"
    place = f"{shipment.port_of_loading.name}, {stated}"
    return Injection(
        overrides={"bill_of_lading": {"bl_date": stated, "place_of_issue": place}},
        discrepancies=[
            Discrepancy(
                type="date_inconsistency",
                scope=CROSS_DOCUMENT,
                documents=["commercial_invoice", "bill_of_lading"],
                fields={"bill_of_lading": ["bl_date", "place_of_issue"]},
                truth=truth,
                stated=stated,
                note="bill of lading is dated before the invoice it ships against",
            )
        ],
    )


def value_mismatch(rng: Random, shipment: Shipment) -> Injection | None:
    truth = f"{shipment.total:,.2f}"
    stated_total = _nudge(rng, shipment.total, "0.01")
    stated = f"{stated_total:,.2f}"
    if stated == truth:
        return None
    return Injection(
        overrides={"invoice": {"total": stated}},
        discrepancies=[
            Discrepancy(
                type="value_mismatch",
                scope=WITHIN_DOCUMENT,
                documents=["commercial_invoice"],
                fields={"invoice": ["total"]},
                truth=truth,
                stated=stated,
                note="invoice total does not equal subtotal plus freight and insurance",
            )
        ],
    )


def hs_code_mismatch(rng: Random, shipment: Shipment) -> Injection | None:
    from clearway.corpus.seeds import _load

    index = rng.randrange(len(shipment.items))
    item = shipment.items[index]
    others = [h for h in _load("hs_codes.json") if h["chapter"] != item.hts[:2]]
    if not others:
        return None
    stated = rng.choice(others)["hts"]
    return Injection(
        overrides={"invoice": {f"item_{index}_hts": stated}},
        discrepancies=[
            Discrepancy(
                type="hs_code_mismatch",
                scope=WITHIN_DOCUMENT,
                documents=["commercial_invoice"],
                fields={"invoice": [f"item_{index}_hts"]},
                truth=item.hts,
                stated=stated,
                note=(
                    f"HS code names chapter {stated[:2]} but the goods described "
                    f"belong to chapter {item.hts[:2]}"
                ),
            )
        ],
    )


def missing_document(rng: Random, shipment: Shipment) -> Injection | None:
    # The invoice is never the one missing: without it there is no shipment to
    # reconcile against, which is a different problem from an incomplete file.
    slug = rng.choice(["packing_list", "bill_of_lading"])
    return Injection(
        omitted=[slug],
        discrepancies=[
            Discrepancy(
                type="missing_document",
                scope=CROSS_DOCUMENT,
                documents=[slug],
                fields={},
                truth="present",
                stated="absent",
                note=f"{slug.replace('_', ' ')} is missing from the bundle",
            )
        ],
    )


INJECTORS = {
    "quantity_mismatch": quantity_mismatch,
    "party_mismatch": party_mismatch,
    "weight_mismatch": weight_mismatch,
    "date_inconsistency": date_inconsistency,
    "value_mismatch": value_mismatch,
    "hs_code_mismatch": hs_code_mismatch,
    "missing_document": missing_document,
}


def inject(rng: Random, shipment: Shipment, count: int) -> Injection:
    """Apply `count` distinct defect types to one bundle.

    A defect type is used at most once per bundle, and two defects never touch
    the same field — overlapping edits would make it ambiguous which label a
    detection belongs to. Returns an empty Injection when count is zero, which
    is how clean bundles are produced.
    """
    result = Injection()
    if count <= 0:
        return result

    chosen = rng.sample(sorted(INJECTORS), min(count, len(INJECTORS)))
    touched: set[tuple[str, str]] = set()

    for name in chosen:
        contribution = INJECTORS[name](rng, shipment)
        if contribution is None:
            continue
        if any(slug in result.omitted for slug in contribution.overrides):
            continue
        claimed = {(slug, f) for slug, fields in contribution.overrides.items() for f in fields}
        if claimed & touched:
            continue
        for slug in contribution.omitted:
            result.overrides.pop(slug, None)
        touched |= claimed
        for slug, fields in contribution.overrides.items():
            result.overrides.setdefault(slug, {}).update(fields)
        result.omitted.extend(contribution.omitted)
        result.discrepancies.extend(contribution.discrepancies)

    return result
