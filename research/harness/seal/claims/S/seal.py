import math


def _stars(root):
    b = bytes.fromhex(root)
    n = 8 + (b[31] % 5)
    return [(20 + b[2 * k] * 216 / 255, 20 + b[2 * k + 1] * 216 / 255)
            for k in range(n)]


def _ring(stars):
    cx = sum(x for x, _ in stars) / len(stars)
    cy = sum(y for _, y in stars) / len(stars)
    return sorted(stars, key=lambda p: (math.atan2(p[1] - cy, p[0] - cx),
                                        p[0], p[1]))


def render(root):
    stars = _stars(root)
    ring = _ring(stars)
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">',
        '<rect width="256" height="256" fill="#0b1020"/>',
    ]
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % len(ring)]
        parts.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="#7a8db0" stroke-width="0.6"/>')
    for x, y in stars:
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.2" fill="#f4f6fb"/>')
    parts.append("</svg>")
    return "\n".join(parts)
