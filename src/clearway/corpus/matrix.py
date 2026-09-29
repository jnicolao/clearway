"""3x3 homographies, enough of them to track where a bounding box went.

Hand-rolled rather than pulled from numpy: this is forty lines of algebra
that the whole corpus's labelling correctness rests on, and owning it means
it is tested here rather than assumed.

A matrix maps input coordinates to output coordinates — the direction a point
travels when an image is degraded. Pillow's `Image.transform` wants the
opposite, the mapping from each output pixel back to the input it samples, so
callers pass `invert(m)` to Pillow and `m` to points. Getting that backwards
rotates the image one way and the annotations the other, which is exactly the
silent label drift this module exists to prevent.
"""

import math

Matrix = tuple[float, float, float, float, float, float, float, float, float]
Point = tuple[float, float]
Quad = tuple[Point, Point, Point, Point]

IDENTITY: Matrix = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


def multiply(a: Matrix, b: Matrix) -> Matrix:
    """a @ b — apply b first, then a."""
    out = []
    for row in range(3):
        for col in range(3):
            out.append(sum(a[row * 3 + k] * b[k * 3 + col] for k in range(3)))
    return tuple(out)  # type: ignore[return-value]


def compose(*matrices: Matrix) -> Matrix:
    """Left-to-right application order: compose(first, second, third)."""
    result = IDENTITY
    for m in matrices:
        result = multiply(m, result)
    return result


def invert(m: Matrix) -> Matrix:
    a, b, c, d, e, f, g, h, i = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise ValueError("matrix is not invertible")
    inv = (
        (e * i - f * h),
        (c * h - b * i),
        (b * f - c * e),
        (f * g - d * i),
        (a * i - c * g),
        (c * d - a * f),
        (d * h - e * g),
        (b * g - a * h),
        (a * e - b * d),
    )
    return tuple(v / det for v in inv)  # type: ignore[return-value]


def apply_point(m: Matrix, point: Point) -> Point:
    x, y = point
    denom = m[6] * x + m[7] * y + m[8]
    if abs(denom) < 1e-12:
        raise ValueError("point maps to infinity")
    return ((m[0] * x + m[1] * y + m[2]) / denom, (m[3] * x + m[4] * y + m[5]) / denom)


def translation(dx: float, dy: float) -> Matrix:
    return (1.0, 0.0, dx, 0.0, 1.0, dy, 0.0, 0.0, 1.0)


def rotation(degrees: float, about: Point) -> Matrix:
    theta = math.radians(degrees)
    cos, sin = math.cos(theta), math.sin(theta)
    cx, cy = about
    return compose(
        translation(-cx, -cy),
        (cos, -sin, 0.0, sin, cos, 0.0, 0.0, 0.0, 1.0),
        translation(cx, cy),
    )


def quad_of_bbox(bbox: tuple[int, int, int, int]) -> Quad:
    x0, y0, x1, y1 = bbox
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def map_quad(m: Matrix, quad: Quad) -> Quad:
    return tuple(apply_point(m, p) for p in quad)  # type: ignore[return-value]


def bounds(quad: Quad) -> tuple[int, int, int, int]:
    """Axis-aligned box enclosing a quad, rounded outwards.

    Rounding outwards matters: a box rounded to nearest can end a fraction of
    a pixel inside the ink it is supposed to bound, and every containment
    check downstream then fails by a hair.
    """
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    return (
        math.floor(min(xs)),
        math.floor(min(ys)),
        math.ceil(max(xs)),
        math.ceil(max(ys)),
    )


def pillow_coeffs(m: Matrix) -> tuple[float, ...]:
    """Coefficients for Image.transform, which wants the inverse mapping."""
    inverse = invert(m)
    return tuple(v / inverse[8] for v in inverse[:8])


def _solve(rows: list[list[float]]) -> list[float]:
    """Gaussian elimination with partial pivoting on an augmented matrix."""
    n = len(rows)
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("degenerate system")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        scale = rows[col][col]
        rows[col] = [v / scale for v in rows[col]]
        for r in range(n):
            if r == col:
                continue
            factor = rows[r][col]
            if factor:
                rows[r] = [v - factor * w for v, w in zip(rows[r], rows[col], strict=True)]
    return [row[n] for row in rows]


def homography(src: Quad, dst: Quad) -> Matrix:
    """The projective transform carrying each src corner onto its dst corner.

    Eight unknowns, eight equations — two per corner correspondence — with the
    bottom-right element fixed at 1.
    """
    rows: list[list[float]] = []
    for (x, y), (u, v) in zip(src, dst, strict=True):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y, u])
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y, v])
    a, b, c, d, e, f, g, h = _solve(rows)
    return (a, b, c, d, e, f, g, h, 1.0)
