"""Degradation tests.

The ones that matter prove annotations follow the pixels. Everything else in
the corpus is downstream of that: if a mapped box drifts off its ink, every
extraction metric computed against this corpus is quietly wrong while the
images still look fine.

Tolerances are split deliberately. Geometric transforms must be near exact —
that is the homography maths being correct. Blur and JPEG are allowed more
room because they physically spread ink beyond its original extent, which is
a property of the filter rather than an error in the mapping.
"""

import math
from random import Random

import pytest
from PIL import Image, ImageChops

from clearway.corpus import degrade
from clearway.corpus import matrix as mx
from clearway.corpus.invoice import render
from clearway.corpus.seeds import build_shipment

GEOMETRIC_TOLERANCE = 2
SPREAD_TOLERANCE = 12
PHOTOMETRIC = sorted(set(degrade.DEGRADATIONS) - degrade.GEOMETRIC)
PROBE = ("invoice_no", "seller_name", "total", "item_0_hts", "reference", "vessel")


@pytest.fixture(scope="module")
def page():
    shipment = build_shipment(Random(4))
    canvas, fields = render(shipment)
    return shipment, canvas.image, fields


def ink_after(shipment, image, name, steps, seed=9):
    """Where a field's ink actually ends up, found by omit-and-diff.

    The same chain is applied to both renders with the same seed, so any
    randomness inside a degradation is identical and the only difference left
    is the field itself.
    """
    partial, _ = render(shipment, skip=frozenset({name}))
    a = degrade.apply(image, steps, Random(seed))
    b = degrade.apply(partial.image, steps, Random(seed))
    return ImageChops.difference(a.image, b.image).getbbox(), a


def overflow(predicted, actual) -> int:
    px0, py0, px1, py1 = predicted
    dx0, dy0, dx1, dy1 = actual
    return max(px0 - dx0, py0 - dy0, dx1 - px1, dy1 - py1)


# ── the central guarantee ───────────────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(degrade.GEOMETRIC))
@pytest.mark.parametrize("severity", [0.3, 0.7, 1.0])
def test_geometric_transforms_carry_annotations_exactly(page, name, severity):
    shipment, image, fields = page
    steps = [degrade.Step(name, severity)]
    for f in [x for x in fields if x.name in PROBE]:
        actual, result = ink_after(shipment, image, f.name, steps)
        assert actual is not None, f"{name}: {f.name} vanished"
        predicted = mx.bounds(mx.map_quad(result.matrix, mx.quad_of_bbox(f.bbox)))
        assert overflow(predicted, actual) <= GEOMETRIC_TOLERANCE, (
            f"{name} s={severity} {f.name}: predicted {predicted} actual {actual}"
        )


@pytest.mark.parametrize("name", PHOTOMETRIC)
def test_photometric_degradations_never_move_pixels(page, name):
    _, image, _ = page
    result = degrade.apply(image, [degrade.Step(name, 0.9)], Random(2))
    assert result.matrix == mx.IDENTITY, f"{name} reported a transform but should not move ink"
    assert result.image.size == image.size


@pytest.mark.parametrize("name", ["blur", "jpeg"])
def test_ink_spread_stays_within_a_bounded_margin(page, name):
    """Blur and JPEG smear ink past its original extent.

    Bounded rather than exact: the margin is the filter's physical reach, and
    a regression that broke the mapping would blow past it immediately.
    """
    shipment, image, fields = page
    steps = [degrade.Step(name, 0.8)]
    for f in [x for x in fields if x.name in PROBE]:
        actual, result = ink_after(shipment, image, f.name, steps)
        assert actual is not None
        predicted = mx.bounds(mx.map_quad(result.matrix, mx.quad_of_bbox(f.bbox)))
        assert overflow(predicted, actual) <= SPREAD_TOLERANCE, f"{name} {f.name}"


@pytest.mark.parametrize("seed", [1, 5, 11])
def test_a_chain_composes_and_annotations_survive_it(page, seed):
    """Several degradations in sequence, transforms composed as it goes."""
    shipment, image, fields = page
    rng = Random(seed)
    steps = [
        degrade.Step("rotate", 0.6),
        degrade.Step("crop", 0.5),
        degrade.Step("perspective", 0.5),
        degrade.Step("blur", 0.4),
    ]
    for f in [x for x in fields if x.name in PROBE[:3]]:
        actual, result = ink_after(shipment, image, f.name, steps, seed=rng.randrange(1000))
        assert actual is not None, f"{f.name} vanished through the chain"
        predicted = mx.bounds(mx.map_quad(result.matrix, mx.quad_of_bbox(f.bbox)))
        assert overflow(predicted, actual) <= SPREAD_TOLERANCE, f"chain {f.name}"


def test_rotation_turns_a_box_into_a_real_quadrilateral(page):
    """A rotated box is not a box.

    Flattening it straight back to an axis-aligned rectangle would claim area
    the field never covered, so the mapped quad is kept alongside the bounds.
    """
    _, image, fields = page
    result = degrade.apply(image, [degrade.Step("rotate", 1.0)], Random(3))
    mapped = result.map_fields(fields[:1])[0]
    top_left, top_right = mapped["quad"][0], mapped["quad"][1]
    assert abs(top_right[1] - top_left[1]) > 1.0, "top edge should no longer be horizontal"
    assert mapped["bbox_original"] != mapped["bbox"], "bounds should have moved"


def test_mapped_fields_keep_value_and_original_box(page):
    _, image, fields = page
    result = degrade.apply(image, [degrade.Step("crop", 0.4)], Random(1))
    mapped = result.map_fields(fields)
    assert len(mapped) == len(fields)
    for original, m in zip(fields, mapped, strict=True):
        assert m["name"] == original.name
        assert m["value"] == original.value
        assert m["bbox_original"] == list(original.bbox)
        assert len(m["quad"]) == 4


def test_severity_zero_changes_almost_nothing(page):
    _, image, _ = page
    for name in sorted(degrade.DEGRADATIONS):
        result = degrade.apply(image, [degrade.Step(name, 0.0)], Random(7))
        assert result.image.size == image.size, name


@pytest.mark.parametrize("name", sorted(degrade.DEGRADATIONS))
def test_degradation_is_deterministic(page, name):
    _, image, _ = page
    steps = [degrade.Step(name, 0.7)]
    a = degrade.apply(image, steps, Random(21)).image
    b = degrade.apply(image, steps, Random(21)).image
    assert ImageChops.difference(a.convert("RGB"), b.convert("RGB")).getbbox() is None, name


def test_sample_chain_never_repeats_a_degradation():
    rng = Random(8)
    for _ in range(20):
        steps = degrade.sample_chain(rng, 5, 0.5)
        names = [s.name for s in steps]
        assert len(names) == len(set(names))


# ── the maths underneath ────────────────────────────────────────────────────


def test_inversion_round_trips():
    m = mx.compose(mx.rotation(17, (40, 90)), mx.translation(-12, 33))
    for point in [(0.0, 0.0), (123.0, 456.0), (-9.0, 4.0)]:
        back = mx.apply_point(mx.invert(m), mx.apply_point(m, point))
        assert all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(back, point, strict=True))


def test_composition_is_ordered_first_to_last():
    move, spin = mx.translation(10, 0), mx.rotation(90, (0, 0))
    assert mx.apply_point(mx.compose(move, spin), (0, 0)) == pytest.approx((0, 10), abs=1e-9)
    assert mx.apply_point(mx.compose(spin, move), (0, 0)) == pytest.approx((10, 0), abs=1e-9)


def test_homography_recovers_a_known_rotation():
    src = mx.quad_of_bbox((0, 0, 100, 50))
    spin = mx.rotation(12, (50, 25))
    recovered = mx.homography(src, mx.map_quad(spin, src))
    for point in [(0.0, 0.0), (100.0, 50.0), (37.0, 19.0)]:
        a, b = mx.apply_point(recovered, point), mx.apply_point(spin, point)
        assert a == pytest.approx(b, abs=1e-9)


def test_bounds_round_outwards():
    """Rounding to nearest can land inside the ink the box must contain."""
    assert mx.bounds(((0.4, 0.4), (9.6, 0.4), (9.6, 9.6), (0.4, 9.6))) == (0, 0, 10, 10)


def test_pillow_coefficients_are_the_inverse_mapping():
    """Pillow samples output back to input; points travel the other way.

    Getting this backwards rotates the image one way and the annotations the
    other, which is the silent failure the whole module exists to prevent.
    """
    spin = mx.rotation(30, (50, 50))
    mark = (50, 30)
    expected = mx.apply_point(spin, mark)
    assert 0 < expected[0] < 100 and 0 < expected[1] < 100, "probe must stay on canvas"

    image = Image.new("RGB", (100, 100), "white")
    for dx in range(-3, 4):
        for dy in range(-3, 4):
            image.putpixel((mark[0] + dx, mark[1] + dy), (0, 0, 0))

    out = image.transform((100, 100), Image.PERSPECTIVE, mx.pillow_coeffs(spin), fillcolor="white")
    found = ImageChops.difference(out, Image.new("RGB", (100, 100), "white")).getbbox()
    assert found is not None, "the mark should still be on the canvas"

    centre = ((found[0] + found[2]) / 2, (found[1] + found[3]) / 2)
    assert centre == pytest.approx(expected, abs=2), (
        f"ink landed at {centre}, transform predicts {expected} — "
        "coefficients are inverted the wrong way"
    )
