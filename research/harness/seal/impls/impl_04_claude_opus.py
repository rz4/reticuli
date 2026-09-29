"""Render a claim root as a constellation.

The root's 32 bytes pick the stars and, through them, the closed ring that
joins them. That geometry is the whole contract: any renderer that reads the
same root must draw the same sky. Everything else here -- the colors, the
radii, the stroke widths, the backdrop -- is this renderer's own voice and
carries no meaning another renderer has to copy.
"""
import math

CANVAS = 256
MARGIN = 20
SPAN = CANVAS - 2 * MARGIN  # 216: the drawing area a byte is stretched over


def _bytes_of(root):
    """The 32 bytes named by a 64-character lowercase hex root."""
    if not isinstance(root, str):
        raise TypeError("root must be a string")
    if len(root) != 64 or any(c not in "0123456789abcdef" for c in root):
        raise ValueError("root must be 64 lowercase hex characters")
    return bytes.fromhex(root)


def stars(root):
    """The star positions of a root, in root order."""
    b = _bytes_of(root)
    n = 8 + (b[31] % 5)
    return [(MARGIN + b[2 * k] * SPAN / 255,
             MARGIN + b[2 * k + 1] * SPAN / 255)
            for k in range(n)]


def ring(points):
    """The stars sorted by angle around their centroid, ties by x then y."""
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    return sorted(points, key=lambda p: (math.atan2(p[1] - cy, p[0] - cx),
                                         p[0], p[1]))


def edges(points):
    """The closed ring: one edge per star, last joining back to the first."""
    order = ring(points)
    return [(order[i], order[(i + 1) % len(order)]) for i in range(len(order))]


def _num(value):
    """A coordinate written plainly, well inside the 0.05 tolerance."""
    return f"{value:.3f}"


def render(root):
    """The complete SVG document for a claim root."""
    points = stars(root)
    joins = edges(points)

    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {CANVAS} {CANVAS}" width="{CANVAS}" '
        f'height="{CANVAS}" role="img">',
        f'  <title>constellation {root}</title>',
        f'  <rect x="0" y="0" width="{CANVAS}" height="{CANVAS}" '
        f'fill="#0b1020"/>',
        '  <g stroke="#6f8bd0" stroke-width="0.8" stroke-linecap="round" '
        'fill="none">',
    ]
    for (x1, y1), (x2, y2) in joins:
        out.append(f'    <line x1="{_num(x1)}" y1="{_num(y1)}" '
                   f'x2="{_num(x2)}" y2="{_num(y2)}"/>')
    out.append('  </g>')
    out.append('  <g fill="#f4f7ff">')
    for x, y in points:
        out.append(f'    <circle cx="{_num(x)}" cy="{_num(y)}" r="2.4"/>')
    out.append('  </g>')
    out.append('</svg>')
    return "\n".join(out) + "\n"
