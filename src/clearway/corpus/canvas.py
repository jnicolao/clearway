"""A drawing surface that records a bounding box for every field it draws.

The whole point of drawing documents rather than rendering HTML and
recovering coordinates: a field's bounding box *is* the rectangle we drew
into. No inference, no drift.

`skip` exists for verification. A field named in `skip` is recorded and
laid out exactly as normal but its ink is not drawn, so a caller can render
the same page twice — once whole, once missing one field — and diff them.
Layout is computed from the shipment data, never from what has been drawn,
so omitting a field moves nothing else on the page.

`overrides` is how a discrepancy reaches the page. A named field renders the
override instead of the shipment's value, and the annotation records what was
drawn rather than what was true. The Shipment itself is never mutated: it
stays the canonical record, the document diverges from it, and
discrepancies.json says exactly where. Putting this on the canvas rather than
in each template means every document supports injection the moment it exists.
"""

from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFont

BBox = tuple[int, int, int, int]


@dataclass(frozen=True)
class Field:
    name: str
    value: str
    bbox: BBox

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "bbox": list(self.bbox)}


def font(size: int) -> ImageFont.FreeTypeFont:
    """Pillow's bundled Aileron, at a given size.

    Deliberately not a system font. Aileron ships inside Pillow under the SIL
    Open Font License, so every machine renders identical pixels — which is
    what makes byte-identical output across a laptop and CI achievable at all.
    """
    return ImageFont.load_default(size=size)


class RecordingCanvas:
    def __init__(
        self,
        width: int,
        height: int,
        *,
        background: str = "white",
        skip: frozenset[str] = frozenset(),
        overrides: dict[str, str] | None = None,
    ) -> None:
        self.image = Image.new("RGB", (width, height), background)
        self.draw = ImageDraw.Draw(self.image)
        self.width = width
        self.height = height
        self.skip = skip
        self.overrides = overrides or {}
        self.fields: list[Field] = []

    # ── recorded content ────────────────────────────────────────────────────
    def text(
        self,
        name: str,
        xy: tuple[int, int],
        value: str,
        *,
        size: int = 13,
        fill: str = "black",
        anchor: str = "la",
    ) -> Field:
        """Draw a field and record where it landed.

        An override replaces the value before anything is measured, so the
        recorded bounding box bounds the text actually on the page.
        """
        value = self.overrides.get(name, value)
        f = font(size)
        box = self.draw.textbbox(xy, value, font=f, anchor=anchor)
        bbox: BBox = (int(box[0]), int(box[1]), int(box[2]), int(box[3]))
        if name not in self.skip:
            self.draw.text(xy, value, font=f, fill=fill, anchor=anchor)
        field = Field(name=name, value=value, bbox=bbox)
        self.fields.append(field)
        return field

    # ── decoration: never recorded, never skipped ───────────────────────────
    def label(self, xy: tuple[int, int], value: str, *, size: int = 10, fill: str = "#666") -> None:
        """Static chrome — column headings, captions. Not a field."""
        self.draw.text(xy, value, font=font(size), fill=fill)

    def rule(self, x0: int, y: int, x1: int, *, fill: str = "#999", width: int = 1) -> None:
        self.draw.line([(x0, y), (x1, y)], fill=fill, width=width)

    def box(self, bbox: BBox, *, outline: str = "#999", fill: str | None = None) -> None:
        self.draw.rectangle(bbox, outline=outline, fill=fill)

    def measure(self, value: str, size: int) -> tuple[int, int]:
        box = self.draw.textbbox((0, 0), value, font=font(size))
        return int(box[2] - box[0]), int(box[3] - box[1])
