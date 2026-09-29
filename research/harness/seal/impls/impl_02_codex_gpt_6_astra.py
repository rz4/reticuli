"""Render a claim root as a deterministic SVG constellation."""

import math


def render(root: str) -> str:
    """Return the constellation for a 64-character lowercase hex root."""
    if not isinstance(root, str) or len(root) != 64 or any(
        char not in "0123456789abcdef" for char in root
    ):
        raise ValueError("root must be 64 lowercase hexadecimal characters")

    data = bytes.fromhex(root)
    count = 8 + data[31] % 5
    stars = [
        (20 + data[2 * k] * 216 / 255,
         20 + data[2 * k + 1] * 216 / 255)
        for k in range(count)
    ]
    cx = sum(x for x, _ in stars) / count
    cy = sum(y for _, y in stars) / count
    ring = sorted(
        stars,
        key=lambda point: (
            math.atan2(point[1] - cy, point[0] - cx), point[0], point[1]
        ),
    )

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">']
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % count]
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            'stroke="#64748b" stroke-width="1" />'
        )
    for x, y in stars:
        parts.append(f'<circle cx="{x}" cy="{y}" r="3" fill="#0f172a" />')
    parts.append('</svg>')
    return '\n'.join(parts)
