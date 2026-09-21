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

from clearway.corpus import invoice
from clearway.corpus.canvas import RecordingCanvas
from clearway.corpus.generate import shipment_dict, write_bundle
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


def test_every_field_bbox_contains_its_ink(shipment):
    full, fields = invoice.render(shipment)
    assert len(fields) > 25, "template should record a substantial field set"

    for field in fields:
        if not field.value.strip():
            continue
        partial, _ = invoice.render(shipment, skip=frozenset({field.name}))
        diff = ImageChops.difference(full.image, partial.image).getbbox()

        assert diff is not None, f"{field.name}: skipping it changed nothing — is it drawn?"

        x0, y0, x1, y1 = field.bbox
        dx0, dy0, dx1, dy1 = diff
        assert dx0 >= x0 - TOLERANCE, f"{field.name}: ink starts left of its box"
        assert dy0 >= y0 - TOLERANCE, f"{field.name}: ink starts above its box"
        assert dx1 <= x1 + TOLERANCE, f"{field.name}: ink runs right of its box"
        assert dy1 <= y1 + TOLERANCE, f"{field.name}: ink runs below its box"


def test_skipping_a_field_moves_nothing_else(shipment):
    """Layout must come from the data, never from what has been drawn."""
    _, full_fields = invoice.render(shipment)
    _, partial_fields = invoice.render(shipment, skip=frozenset({"invoice_no"}))
    assert [f.bbox for f in full_fields] == [f.bbox for f in partial_fields]
    assert [f.name for f in full_fields] == [f.name for f in partial_fields]


def test_field_names_are_unique(shipment):
    _, fields = invoice.render(shipment)
    names = [f.name for f in fields]
    assert len(names) == len(set(names))


def test_fields_do_not_overlap(shipment):
    _, fields = invoice.render(shipment)
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
    for name in ("invoice.png", "invoice.json", "shipment.json"):
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
