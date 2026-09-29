"""Render a claim root as a deterministic SVG constellation."""
import math


def render(root: str) -> str:
    """Return an SVG whose stars and ring encode the 32-byte hex root."""
    if not isinstance(root, str) or len(root) != 64:
        raise ValueError("root must be a 64-character lowercase hex string")
    if any(ch not in "0123456789abcdef" for ch in root):
        raise ValueError("root must be a 64-character lowercase hex string")

    data = bytes.fromhex(root)
    count = 8 + data[31] % 5
    stars = [
        (20 + data[2 * k] * 216 / 255,
         20 + data[2 * k + 1] * 216 / 255)
        for k in range(count)
    ]
    center_x = sum(x for x, _ in stars) / count
    center_y = sum(y for _, y in stars) / count
    ring = sorted(
        stars,
        key=lambda p: (math.atan2(p[1] - center_y, p[0] - center_x), p[0], p[1]),
    )

    parts = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">']
    for i, (x1, y1) in enumerate(ring):
        x2, y2 = ring[(i + 1) % count]
        parts.append(f'<line x1="{x1:.12g}" y1="{y1:.12g}" x2="{x2:.12g}" y2="{y2:.12g}" stroke="#526"/>')
    for x, y in stars:
        parts.append(f'<circle cx="{x:.12g}" cy="{y:.12g}" r="2" fill="#ffd86b"/>')
    parts.append('</svg>')
    return ''.join(parts)
