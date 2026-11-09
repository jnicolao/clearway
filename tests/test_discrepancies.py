"""Discrepancy injection tests.

The one that earns its keep is test_no_unlabelled_inconsistency_exists: it
independently re-derives which cross-document invariants a bundle violates
and asserts that set matches the recorded labels exactly. An unlabelled
defect would make the false-positive rate meaningless — a reconciler would be
penalised for finding something genuinely wrong.
"""

import json
from decimal import Decimal
from random import Random

import pytest
from PIL import ImageChops

from clearway.corpus.discrepancies import INJECTORS, Injection, inject
from clearway.corpus.generate import DOCUMENTS, write_bundle
from clearway.corpus.seeds import build_shipment

SEEDS = [1, 3, 7, 11, 42, 99, 256, 1024]
TOLERANCE = 1


def rendered(slug: str, shipment, injection: Injection) -> dict[str, str]:
    _, fields = DOCUMENTS[slug][1](shipment, overrides=injection.for_document(slug))
    return {f.name: f.value for f in fields}


def violations(shipment, injection: Injection) -> set[str]:
    """Independently re-derive which invariants this bundle breaks.

    Deliberately does not consult the labels — it reads the pages the way a
    reconciler would and reports what disagrees.
    """
    found: set[str] = set()
    present = {s for s in DOCUMENTS if s not in injection.omitted}
    if len(present) < len(DOCUMENTS):
        found.add("missing_document")

    docs = {slug: rendered(slug, shipment, injection) for slug in present}

    if {"invoice", "packing_list"} <= present:
        inv, pl = docs["invoice"], docs["packing_list"]
        for i in range(len(shipment.items)):
            if inv[f"item_{i}_quantity"] != pl[f"item_{i}_quantity"]:
                found.add("quantity_mismatch")

    if {"packing_list", "bill_of_lading"} <= present:
        if (
            docs["packing_list"]["total_gross_weight"]
            != docs["bill_of_lading"]["total_gross_weight"]
        ):
            found.add("weight_mismatch")

    if {"invoice", "bill_of_lading"} <= present:
        if docs["invoice"]["buyer_name"] != docs["bill_of_lading"]["consignee_name"]:
            found.add("party_mismatch")
        if docs["bill_of_lading"]["bl_date"] != f"{shipment.bl_date:%d %b %Y}":
            found.add("date_inconsistency")

    if "invoice" in present:
        inv = docs["invoice"]
        stated_total = Decimal(inv["total"].replace(",", ""))
        if stated_total != shipment.total:
            found.add("value_mismatch")
        for i, item in enumerate(shipment.items):
            if inv[f"item_{i}_hts"] != item.hts:
                found.add("hs_code_mismatch")
    return found


# ── the central guarantee ───────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("count", [0, 1, 2, 3])
def test_no_unlabelled_inconsistency_exists(seed, count):
    rng = Random(seed)
    shipment = build_shipment(rng)
    injection = inject(rng, shipment, count)
    assert violations(shipment, injection) == {d.type for d in injection.discrepancies}


@pytest.mark.parametrize("seed", SEEDS)
def test_clean_bundles_are_actually_clean(seed):
    rng = Random(seed)
    shipment = build_shipment(rng)
    injection = inject(rng, shipment, 0)
    assert injection.discrepancies == []
    assert injection.omitted == []
    assert violations(shipment, injection) == set()


# ── labels describe reality ─────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(INJECTORS))
def test_each_injector_lands_its_stated_value_on_the_page(name):
    rng = Random(17)
    shipment = build_shipment(rng)
    injection = INJECTORS[name](rng, shipment)
    assert injection is not None

    for slug, fields in injection.overrides.items():
        page = rendered(slug, shipment, injection)
        for field_name, expected in fields.items():
            assert page[field_name] == expected, f"{slug}/{field_name}"

    for d in injection.discrepancies:
        assert d.truth != d.stated, f"{name}: a defect that changes nothing is not a defect"
        assert d.note, f"{name}: needs a human-readable note"


@pytest.mark.parametrize("name", sorted(INJECTORS))
def test_every_injector_is_recorded_with_the_documents_it_touches(name):
    rng = Random(23)
    shipment = build_shipment(rng)
    injection = INJECTORS[name](rng, shipment)
    assert injection is not None
    for d in injection.discrepancies:
        assert d.documents, "a discrepancy must name the documents involved"
        assert d.scope in {"cross_document", "within_document"}


def test_injections_never_mutate_the_shipment():
    """shipment.json is the truth. Documents diverge from it, it never moves."""
    rng = Random(5)
    shipment = build_shipment(rng)
    before = json.dumps(
        {
            "total": str(shipment.total),
            "buyer": shipment.buyer.name,
            "bl_date": shipment.bl_date.isoformat(),
            "gross": str(shipment.total_gross_weight),
            "hts": [i.hts for i in shipment.items],
        },
        sort_keys=True,
    )
    inject(rng, shipment, len(INJECTORS))
    after = json.dumps(
        {
            "total": str(shipment.total),
            "buyer": shipment.buyer.name,
            "bl_date": shipment.bl_date.isoformat(),
            "gross": str(shipment.total_gross_weight),
            "hts": [i.hts for i in shipment.items],
        },
        sort_keys=True,
    )
    assert before == after


def test_two_defects_never_edit_the_same_field():
    """Overlapping edits make it ambiguous which label a detection belongs to."""
    for seed in SEEDS:
        rng = Random(seed)
        shipment = build_shipment(rng)
        injection = inject(rng, shipment, len(INJECTORS))
        claimed = [
            (slug, f) for d in injection.discrepancies for slug, fs in d.fields.items() for f in fs
        ]
        assert len(claimed) == len(set(claimed)), f"seed {seed}"


# ── the bundle on disk ──────────────────────────────────────────────────────


@pytest.mark.parametrize("seed", SEEDS[:4])
def test_bundle_records_truth_documents_and_labels_separately(seed, tmp_path):
    rng = Random(seed)
    shipment = build_shipment(rng)
    injection = inject(rng, shipment, 2)
    write_bundle(shipment, tmp_path, injection)

    labels = json.loads((tmp_path / "discrepancies.json").read_text())
    assert labels["clean"] is (not injection.discrepancies)
    assert len(labels["discrepancies"]) == len(injection.discrepancies)

    truth = json.loads((tmp_path / "shipment.json").read_text())
    assert Decimal(truth["total"]) == shipment.total, "truth must survive injection"

    for slug in DOCUMENTS:
        should_exist = slug not in injection.omitted
        assert (tmp_path / f"{slug}.png").exists() is should_exist
        assert (tmp_path / f"{slug}.json").exists() is should_exist


def test_missing_document_removes_it_from_disk(tmp_path):
    rng = Random(2)
    shipment = build_shipment(rng)
    injection = INJECTORS["missing_document"](rng, shipment)
    write_bundle(shipment, tmp_path, injection)
    (omitted,) = injection.omitted
    assert not (tmp_path / f"{omitted}.png").exists()
    assert not (tmp_path / f"{omitted}.json").exists()
    assert (tmp_path / "invoice.png").exists(), "the invoice is never the missing one"


def test_injection_is_deterministic(tmp_path):
    for run in ("a", "b"):
        rng = Random(31)
        shipment = build_shipment(rng)
        write_bundle(shipment, tmp_path / run, inject(rng, shipment, 2))
    for name in ("shipment.json", "discrepancies.json", "invoice.png", "invoice.json"):
        a, b = tmp_path / "a" / name, tmp_path / "b" / name
        if a.exists() or b.exists():
            assert a.read_bytes() == b.read_bytes(), name


# ── injection must not break what #2 and #3 established ─────────────────────


@pytest.mark.parametrize("name", sorted(INJECTORS))
def test_bounding_boxes_still_bound_the_ink_under_injection(name):
    """An override changes a string's width, so its box must be re-measured.

    Driven from the injectors rather than the documents so every override
    actually gets checked — a skip here would hide exactly the regression
    this is for.
    """
    rng = Random(13)
    shipment = build_shipment(rng)
    injection = INJECTORS[name](rng, shipment)
    assert injection is not None

    if not injection.overrides:
        assert injection.omitted, f"{name} changes neither fields nor documents"
        return

    for slug, overrides in injection.overrides.items():
        render = DOCUMENTS[slug][1]
        full, fields = render(shipment, overrides=overrides)
        checked = 0
        for f in fields:
            if f.name not in overrides or not f.value.strip():
                continue
            partial, _ = render(shipment, skip=frozenset({f.name}), overrides=overrides)
            diff = ImageChops.difference(full.image, partial.image).getbbox()
            assert diff is not None, f"{slug}/{f.name}"
            x0, y0, x1, y1 = f.bbox
            dx0, dy0, dx1, dy1 = diff
            assert dx0 >= x0 - TOLERANCE and dy0 >= y0 - TOLERANCE, f"{slug}/{f.name}"
            assert dx1 <= x1 + TOLERANCE and dy1 <= y1 + TOLERANCE, f"{slug}/{f.name}"
            checked += 1
        assert checked == len(overrides), f"{slug}: only checked {checked}/{len(overrides)}"
