"""Corpus generator tests.

The central one is test_every_field_bbox_contains_its_ink: it renders the
page twice, once with a field and once without, and asserts the pixels that
changed lie inside that field's recorded box. That proves the annotation
actually bounds the field rather than merely being plausible, which is the
property every downstream extraction metric rests on.
"""

import json
from decimal import Decimal
from random import Random

import pytest
from PIL import ImageChops

from clearway.corpus.canvas import RecordingCanvas
from clearway.corpus.containers import is_valid
from clearway.corpus.generate import DOCUMENTS, shipment_dict, write_bundle
from clearway.corpus.seeds import FALLBACK_VESSELS, build_shipment, vessels_from_ais

# Antialiasing can tint the pixel just outside a glyph's reported extent.
TOLERANCE = 1


@pytest.fixture(scope="module")
def shipment():
    return build_shipment(Random(11))


def test_generates_a_plausible_shipment(shipment):
    assert 2 <= len(shipment.items) <= 5
    assert shipment.port_of_loading != shipment.port_of_discharge
    # One chapter per shipment — a container of flowers and gearboxes is not
    # a shipment anyone would file.
    assert len({i.hts[:2] for i in shipment.items}) == 1


def test_totals_are_internally_consistent(shipment):
    assert shipment.subtotal == sum((i.amount for i in shipment.items), Decimal("0.00"))
    assert shipment.total == shipment.subtotal + shipment.freight + shipment.insurance


@pytest.mark.parametrize("slug", sorted(DOCUMENTS))
def test_every_field_bbox_contains_its_ink(shipment, slug):
    render = DOCUMENTS[slug][1]
    full, fields = render(shipment)
    assert len(fields) > 25, f"{slug} should record a substantial field set"

    for field in fields:
        if not field.value.strip():
            continue
        partial, _ = render(shipment, skip=frozenset({field.name}))
        diff = ImageChops.difference(full.image, partial.image).getbbox()

        assert diff is not None, f"{slug}/{field.name}: skipping it changed nothing — is it drawn?"

        x0, y0, x1, y1 = field.bbox
        dx0, dy0, dx1, dy1 = diff
        assert dx0 >= x0 - TOLERANCE, f"{slug}/{field.name}: ink starts left of its box"
        assert dy0 >= y0 - TOLERANCE, f"{slug}/{field.name}: ink starts above its box"
        assert dx1 <= x1 + TOLERANCE, f"{slug}/{field.name}: ink runs right of its box"
        assert dy1 <= y1 + TOLERANCE, f"{slug}/{field.name}: ink runs below its box"


@pytest.mark.parametrize("slug", sorted(DOCUMENTS))
def test_skipping_a_field_moves_nothing_else(shipment, slug):
    """Layout must come from the data, never from what has been drawn."""
    render = DOCUMENTS[slug][1]
    _, full_fields = render(shipment)
    _, partial_fields = render(shipment, skip=frozenset({"document_title"}))
    assert [f.bbox for f in full_fields] == [f.bbox for f in partial_fields]
    assert [f.name for f in full_fields] == [f.name for f in partial_fields]


@pytest.mark.parametrize("slug", sorted(DOCUMENTS))
def test_field_names_are_unique(shipment, slug):
    _, fields = DOCUMENTS[slug][1](shipment)
    names = [f.name for f in fields]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("slug", sorted(DOCUMENTS))
def test_fields_do_not_overlap(shipment, slug):
    _, fields = DOCUMENTS[slug][1](shipment)
    boxes = [(f.name, f.bbox) for f in fields if f.value.strip()]
    for i, (name_a, a) in enumerate(boxes):
        for name_b, b in boxes[i + 1 :]:
            overlap = (
                a[0] < b[2] - TOLERANCE
                and b[0] < a[2] - TOLERANCE
                and a[1] < b[3] - TOLERANCE
                and b[1] < a[3] - TOLERANCE
            )
            assert not overlap, f"{name_a} overlaps {name_b}"


def test_same_seed_is_byte_identical(tmp_path):
    for run in ("a", "b"):
        write_bundle(build_shipment(Random(3)), tmp_path / run)
    names = ["shipment.json"] + [f"{slug}.{ext}" for slug in DOCUMENTS for ext in ("png", "json")]
    for name in names:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_different_seeds_differ(tmp_path):
    write_bundle(build_shipment(Random(3)), tmp_path / "a")
    write_bundle(build_shipment(Random(4)), tmp_path / "b")
    assert (tmp_path / "a" / "invoice.png").read_bytes() != (
        tmp_path / "b" / "invoice.png"
    ).read_bytes()


def test_bundle_json_is_serialisable(shipment, tmp_path):
    write_bundle(shipment, tmp_path)
    data = json.loads((tmp_path / "shipment.json").read_text())
    assert data["invoice_no"] == shipment.invoice_no
    assert Decimal(data["total"]) == shipment.total
    annotations = json.loads((tmp_path / "invoice.json").read_text())
    assert annotations["document"] == "commercial_invoice"
    assert all(len(f["bbox"]) == 4 for f in annotations["fields"])


def test_shipment_dict_exposes_derived_totals(shipment):
    data = shipment_dict(shipment)
    assert Decimal(str(data["subtotal"])) == shipment.subtotal
    assert data["total_cartons"] == shipment.total_cartons


def test_ais_vessels_fall_back_when_db_is_absent(tmp_path):
    assert vessels_from_ais(tmp_path / "nope.sqlite3") == []
    shipment = build_shipment(Random(5), ais_db=tmp_path / "nope.sqlite3")
    assert shipment.vessel in FALLBACK_VESSELS


def test_canvas_skip_is_recorded_but_not_drawn():
    drawn = RecordingCanvas(200, 60)
    a = drawn.text("x", (10, 10), "HELLO", size=16)
    hidden = RecordingCanvas(200, 60, skip=frozenset({"x"}))
    b = hidden.text("x", (10, 10), "HELLO", size=16)
    assert a.bbox == b.bbox
    assert ImageChops.difference(drawn.image, hidden.image).getbbox() is not None


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 256])
def test_line_items_are_tellable_apart(seed):
    """Sibling HTS leaves differ only by a trailing 'Other'.

    A bundle whose rows render identically is useless for extraction eval —
    nothing says which extracted row is which.
    """
    shipment = build_shipment(Random(seed))
    prefixes = [i.description[:40] for i in shipment.items]
    assert len(prefixes) == len(set(prefixes)), shipment.items[0].description[:60]


# ── cross-document consistency ──────────────────────────────────────────────
# Compared on the *rendered* values, not on the shipment model. The model
# agreeing with itself proves nothing: what a reconciler sees is the text on
# the page, so a template that formats a weight as "1254.56" where another
# writes "1,254.560" would produce a discrepancy nobody injected. These
# invariants have to hold before #4 starts injecting real ones.


def rendered(slug: str, shipment) -> dict[str, str]:
    _, fields = DOCUMENTS[slug][1](shipment)
    return {f.name: f.value for f in fields}


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 256])
def test_quantities_agree_between_invoice_and_packing_list(seed):
    shipment = build_shipment(Random(seed))
    inv = rendered("invoice", shipment)
    pl = rendered("packing_list", shipment)
    for i in range(len(shipment.items)):
        assert inv[f"item_{i}_quantity"] == pl[f"item_{i}_quantity"]


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 256])
def test_weights_and_packages_agree_between_packing_list_and_bl(seed):
    shipment = build_shipment(Random(seed))
    pl = rendered("packing_list", shipment)
    bl = rendered("bill_of_lading", shipment)
    assert pl["total_gross_weight"] == bl["total_gross_weight"]
    assert pl["total_volume"] == bl["total_measurement"]
    assert pl["total_cartons"] in bl["total_packages"]
    for i in range(len(shipment.items)):
        assert pl[f"item_{i}_gross_weight"] == bl[f"item_{i}_gross_weight"]


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 256])
def test_parties_agree_across_documents(seed):
    shipment = build_shipment(Random(seed))
    inv = rendered("invoice", shipment)
    pl = rendered("packing_list", shipment)
    bl = rendered("bill_of_lading", shipment)
    assert inv["seller_name"] == pl["seller_name"] == bl["shipper_name"]
    assert inv["buyer_name"] == pl["buyer_name"] == bl["consignee_name"]
    # The notify party appears only on the bill of lading. That asymmetry is
    # real and is why a reconciler cannot simply diff every field.
    assert "notify_name" in bl and "notify_name" not in inv


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 256])
def test_bill_of_lading_is_never_dated_before_its_invoice(seed):
    """Goods are invoiced before they are loaded.

    An out-of-order pair is one of the discrepancies #4 injects deliberately,
    so it must never arise by accident here.
    """
    shipment = build_shipment(Random(seed))
    assert shipment.bl_date >= shipment.invoice_date


@pytest.mark.parametrize("seed", [1, 7, 42, 99, 256])
def test_container_numbers_are_valid_iso_6346(seed):
    shipment = build_shipment(Random(seed))
    assert shipment.containers
    for number in shipment.containers:
        assert is_valid(number), number


def test_packing_list_carries_no_prices(shipment):
    """The separation is the document's purpose.

    If prices leaked onto the packing list, a value disagreement with the
    invoice would be detectable from one page and the reconciliation task
    would be easier than the real one.
    """
    values = rendered("packing_list", shipment)
    assert not any("price" in name or name in {"total", "subtotal"} for name in values)
    money_fields = {"unit_price", "amount", "subtotal", "freight", "insurance", "total"}
    assert money_fields.isdisjoint(set(values))
