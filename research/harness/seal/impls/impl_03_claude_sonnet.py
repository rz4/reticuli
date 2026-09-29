"""Render a claim root as a small constellation (SVG).

render(root) turns a 64-character lowercase hex claim root into a
deterministic SVG: n stars placed from the root's bytes, joined into a
closed ring in angular order around their centroid. See check_seal.py
for the pinned geometry this must reproduce exactly.
"""
import math


def render(root: str) -> str:
    b = bytes.fromhex(root)
    n = 8 + (b[31] % 5)
    stars = [(20 + b[2 * k] * 216 / 255, 20 + b[2 * k + 1] * 216 / 255)
             for k in range(n)]

    cx = sum(x for x, _ in stars) / len(stars)
    cy = sum(y for _, y in stars) / len(stars)
    ring = sorted(stars, key=lambda p: (math.atan2(p[1] - cy, p[0] - cx),
                                         p[0], p[1]))
    edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
        '<rect x="0" y="0" width="256" height="256" fill="#0b1020"/>',
    ]
    for (x1, y1), (x2, y2) in edges:
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="#3a5" stroke-width="1"/>'
        )
    for x, y in stars:
        parts.append(f'<circle cx="{x}" cy="{y}" r="2" fill="#fff"/>')
    parts.append('</svg>')
    return "".join(parts)
