"""Render a claim root as a deterministic constellation SVG."""

import math


def render(root: str) -> str:
    """Return the constellation defined by a 32-byte hexadecimal claim root."""
    data = bytes.fromhex(root)
    if len(root) != 64 or len(data) != 32 or root != root.lower():
        raise ValueError("root must be a 64-character lowercase hex string")

    count = 8 + data[31] % 5
    stars = [
        (20 + data[2 * k] * 216 / 255, 20 + data[2 * k + 1] * 216 / 255)
        for k in range(count)
    ]
    center_x = sum(x for x, _ in stars) / count
    center_y = sum(y for _, y in stars) / count
    ring = sorted(
        stars,
        key=lambda point: (
            math.atan2(point[1] - center_y, point[0] - center_x),
            point[0],
            point[1],
        ),
    )

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">']
    parts.append('<rect width="256" height="256" fill="#0b1022"/>')
    for index, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(index + 1) % count]
        parts.append(
            f'<line x1="{x1:.10f}" y1="{y1:.10f}" '
            f'x2="{x2:.10f}" y2="{y2:.10f}" '
            'stroke="#8aa8cc" stroke-width="1"/>'
        )
    for x, y in stars:
        parts.append(
            f'<circle cx="{x:.10f}" cy="{y:.10f}" r="2.5" fill="#fff4d6"/>'
        )
    parts.append('</svg>')
    return '\n'.join(parts)
