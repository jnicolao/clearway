"""Degradations, and the transforms that keep annotations attached to them.

This is also the robustness suite: one piece of code, two deliverables. Each
degradation is parameterised by a severity in [0, 1] so the eval can report a
curve per axis rather than one blended robustness number.

Two kinds, and the distinction is the whole design:

  * geometric — rotation, perspective, crop. These move pixels, so they
    return a real homography and every annotation is mapped through it.
  * photometric — blur, JPEG, brightness, speckle, bilevel, stamps. These
    change pixels without moving them, so their transform is the identity.

Annotations are mapped through the composed matrix, never re-measured from
the degraded image. Re-measuring would be circular: it would find whatever
ink survived rather than where the field actually went, and a corpus whose
labels drift from its images poisons every downstream number while looking
perfectly fine.
"""

import io
from dataclasses import dataclass, field
from random import Random
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from clearway.corpus import matrix as mx
from clearway.corpus.canvas import Field

Degraded = tuple[Image.Image, mx.Matrix]


# ── geometric ───────────────────────────────────────────────────────────────


def rotate(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """Skew, as a sheet sits crooked on a scanner bed.

    The canvas grows to hold the rotated page rather than clipping its
    corners, because a clipped corner can take an annotated field with it and
    a missing field is a different defect from a rotated one.
    """
    angle = rng.choice([-1, 1]) * severity * 12.0
    width, height = image.size
    spin = mx.rotation(angle, (width / 2, height / 2))
    corners = mx.map_quad(spin, mx.quad_of_bbox((0, 0, width, height)))
    x0, y0, x1, y1 = mx.bounds(corners)
    final = mx.compose(spin, mx.translation(-x0, -y0))
    out = image.transform(
        (x1 - x0, y1 - y0),
        Image.PERSPECTIVE,
        mx.pillow_coeffs(final),
        resample=Image.BICUBIC,
        fillcolor="white",
    )
    return out, final


def perspective(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """A photograph taken at an angle rather than a flat scan."""
    width, height = image.size
    reach = severity * 0.045
    src = mx.quad_of_bbox((0, 0, width, height))
    dst = tuple(
        (
            x + rng.uniform(-reach, reach) * width,
            y + rng.uniform(-reach, reach) * height,
        )
        for x, y in src
    )
    warp = mx.homography(src, dst)  # type: ignore[arg-type]
    out = image.transform(
        (width, height),
        Image.PERSPECTIVE,
        mx.pillow_coeffs(warp),
        resample=Image.BICUBIC,
        fillcolor="white",
    )
    return out, warp


def crop(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """An edge missed by the scanner or the camera frame."""
    width, height = image.size
    margin = severity * 0.05
    left = int(rng.uniform(0, margin) * width)
    top = int(rng.uniform(0, margin) * height)
    right = width - int(rng.uniform(0, margin) * width)
    bottom = height - int(rng.uniform(0, margin) * height)
    return image.crop((left, top, right, bottom)), mx.translation(-left, -top)


# ── photometric ─────────────────────────────────────────────────────────────


def blur(image: Image.Image, severity: float, rng: Random) -> Degraded:
    return image.filter(ImageFilter.GaussianBlur(radius=severity * 2.4)), mx.IDENTITY


def jpeg(image: Image.Image, severity: float, rng: Random) -> Degraded:
    quality = int(92 - severity * 80)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=max(4, quality))
    buffer.seek(0)
    return Image.open(buffer).convert("RGB"), mx.IDENTITY


def exposure(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """Low light or a washed-out flash."""
    direction = rng.choice([-1, 1])
    out = ImageEnhance.Brightness(image).enhance(1.0 + direction * severity * 0.45)
    out = ImageEnhance.Contrast(out).enhance(1.0 - severity * 0.45)
    return out, mx.IDENTITY


def speckle(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """Scanner dust and sensor noise."""
    out = image.copy()
    draw = ImageDraw.Draw(out)
    width, height = out.size
    for _ in range(int(severity * width * height * 0.0016)):
        x, y = rng.randrange(width), rng.randrange(height)
        shade = rng.randrange(0, 90)
        draw.point((x, y), fill=(shade, shade, shade))
    return out, mx.IDENTITY


def bilevel(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """A fax or a photocopier set too hard."""
    threshold = int(190 - severity * 60)
    grey = image.convert("L")
    out = grey.point(lambda v: 255 if v > threshold else 0, mode="L")
    return out.convert("RGB"), mx.IDENTITY


def stamp(image: Image.Image, severity: float, rng: Random) -> Degraded:
    """A customs or carrier stamp.

    Placed in the lower margin where real stamps land, rather than across the
    body. A stamp over a field is realistic but would occlude ink the
    annotation still claims, and occlusion is a different axis from marking.
    """
    out = image.copy()
    draw = ImageDraw.Draw(out, "RGBA")
    width, height = out.size
    radius = int(min(width, height) * (0.06 + severity * 0.04))
    cx = rng.randrange(int(width * 0.55), int(width * 0.9))
    cy = rng.randrange(int(height * 0.86), int(height * 0.95))
    alpha = int(70 + severity * 110)
    ink = (rng.choice([150, 30, 40]), rng.choice([20, 40, 90]), rng.choice([40, 120, 160]), alpha)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=ink, width=3)
    draw.ellipse(
        (cx - radius + 8, cy - radius + 8, cx + radius - 8, cy + radius - 8), outline=ink, width=2
    )
    draw.line((cx - radius + 14, cy, cx + radius - 14, cy), fill=ink, width=2)
    return out, mx.IDENTITY


DEGRADATIONS = {
    "rotate": rotate,
    "perspective": perspective,
    "crop": crop,
    "blur": blur,
    "jpeg": jpeg,
    "exposure": exposure,
    "speckle": speckle,
    "bilevel": bilevel,
    "stamp": stamp,
}

GEOMETRIC = frozenset({"rotate", "perspective", "crop"})


@dataclass(frozen=True)
class Step:
    name: str
    severity: float

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "severity": round(self.severity, 3)}


@dataclass
class Result:
    image: Image.Image
    matrix: mx.Matrix
    steps: list[Step] = field(default_factory=list)

    def map_fields(self, fields: list[Field]) -> list[dict[str, Any]]:
        """Carry annotations through the composed transform.

        Each field keeps its original axis-aligned box plus the quadrilateral
        it became. A rotated box is not a box, and flattening it back to one
        immediately would claim area the field never covered.
        """
        out = []
        for f in fields:
            quad = mx.map_quad(self.matrix, mx.quad_of_bbox(f.bbox))
            out.append(
                {
                    "name": f.name,
                    "value": f.value,
                    "bbox_original": list(f.bbox),
                    "quad": [[round(x, 2), round(y, 2)] for x, y in quad],
                    "bbox": list(mx.bounds(quad)),
                }
            )
        return out


def apply(image: Image.Image, steps: list[Step], rng: Random) -> Result:
    """Run a chain, composing transforms as it goes."""
    current = image
    composed = mx.IDENTITY
    for step in steps:
        current, m = DEGRADATIONS[step.name](current, step.severity, rng)
        composed = mx.compose(composed, m)
    return Result(image=current, matrix=composed, steps=list(steps))


def sample_chain(rng: Random, count: int, severity: float) -> list[Step]:
    """A random chain of distinct degradations at one severity."""
    names = rng.sample(sorted(DEGRADATIONS), min(count, len(DEGRADATIONS)))
    return [Step(name=n, severity=severity) for n in names]
