"""The seal check: a claim root rendered as a small constellation.

The claim: `seal.py` in this directory defines

    render(root: str) -> str

taking a 64-character lowercase hex claim root and returning a complete SVG
document. The constellation IS the root made visible, so the geometry is the
contract — any two conforming renderers must draw the same sky for the same
root — while everything visual beyond the geometry (colors, radii, stroke
widths, background, decoration) is the renderer's own.

The pinned mapping, computed independently below from the same words:

  bytes    the 32 bytes of the root
  count    n = 8 + (bytes[31] % 5) stars (8..12)
  star k   x = 20 + bytes[2k]   * 216 / 255
           y = 20 + bytes[2k+1] * 216 / 255       for k in 0..n-1
  edges    stars sorted by angle around their centroid (ties by x, then y),
           joined in a closed ring: n edges
  canvas   viewBox "0 0 256 256"

The SVG must carry exactly one <circle> per star (cx, cy within 0.05) and
exactly one <line> per edge (endpoints within 0.05, either direction), and
nothing else that is a circle or a line — extra elements of other kinds are
styling and stay free. Same root, same sky; different roots, different sky.
"""
import math
import xml.etree.ElementTree as ET

import seal

VECTORS = [
    # sha256(b"reticuli"), sha256(b"constellation"), sha256(b"")
    "acc64e429d8ebfb2fd6f761bf26168ef49c6aa3d286498c51e9c4446b127db4e",
    "9a258f0a0a2c0191fabc12bd114366f3743db65e7ab01ccb77fbdb67b1228f09",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
]


def expected_stars(root: str) -> list:
    b = bytes.fromhex(root)
    n = 8 + (b[31] % 5)
    return [(20 + b[2 * k] * 216 / 255, 20 + b[2 * k + 1] * 216 / 255)
            for k in range(n)]


def expected_edges(stars: list) -> list:
    cx = sum(x for x, _ in stars) / len(stars)
    cy = sum(y for _, y in stars) / len(stars)
    ring = sorted(stars, key=lambda p: (math.atan2(p[1] - cy, p[0] - cx),
                                        p[0], p[1]))
    return [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]


def close(a, b, tol=0.05):
    return abs(a[0] - b[0]) <= tol and abs(a[1] - b[1]) <= tol


def match_off(wanted, got, same):
    """One-to-one matching within tolerance; both lists consumed exactly."""
    remaining = list(got)
    for w in wanted:
        hit = next((g for g in remaining if same(w, g)), None)
        assert hit is not None, f"missing {w!r}; have {remaining!r}"
        remaining.remove(hit)
    assert not remaining, f"unexpected extras: {remaining!r}"


def check_one(root: str) -> set:
    svg = seal.render(root)
    assert isinstance(svg, str) and svg == seal.render(root), \
        "render must be deterministic"
    doc = ET.fromstring(svg)
    assert doc.tag.rsplit("}", 1)[-1] == "svg", f"not an svg root: {doc.tag}"
    assert doc.get("viewBox") == "0 0 256 256", doc.get("viewBox")

    circles, lines = [], []
    for el in doc.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "circle":
            circles.append((float(el.get("cx")), float(el.get("cy"))))
        elif tag == "line":
            lines.append(((float(el.get("x1")), float(el.get("y1"))),
                          (float(el.get("x2")), float(el.get("y2")))))

    stars = expected_stars(root)
    match_off(stars, circles, close)
    edges = expected_edges(stars)
    match_off(edges, lines,
              lambda w, g: (close(w[0], g[0]) and close(w[1], g[1]))
              or (close(w[0], g[1]) and close(w[1], g[0])))
    return {(round(x, 1), round(y, 1)) for x, y in circles}


skies = [check_one(root) for root in VECTORS]
for i in range(len(skies)):
    for j in range(i + 1, len(skies)):
        assert skies[i] != skies[j], \
            f"vectors {i} and {j} drew the same sky: different roots must differ"
print("seal-ok")
