import math
import xml.etree.ElementTree as ET


def render(root: str) -> str:
    """Render a claim root as an SVG constellation.

    Takes a 64-character lowercase hex claim root and returns a complete SVG
    document. Stars are positioned based on the root bytes, sorted by angle
    around their centroid, and connected in a closed ring.
    """
    # Parse the root hex string to bytes
    b = bytes.fromhex(root)

    # Calculate number of stars: 8 + (bytes[31] % 5) = 8..12
    n = 8 + (b[31] % 5)

    # Calculate star positions using the pinned mapping
    stars = []
    for k in range(n):
        x = 20 + b[2 * k] * 216 / 255
        y = 20 + b[2 * k + 1] * 216 / 255
        stars.append((x, y))

    # Calculate centroid
    cx = sum(x for x, _ in stars) / len(stars)
    cy = sum(y for _, y in stars) / len(stars)

    # Sort stars by angle around centroid (ties broken by x, then y)
    ring = sorted(stars, key=lambda p: (math.atan2(p[1] - cy, p[0] - cx), p[0], p[1]))

    # Create edges as a closed ring
    edges = [(ring[i], ring[(i + 1) % len(ring)]) for i in range(len(ring))]

    # Create SVG document
    svg = ET.Element('svg')
    svg.set('viewBox', '0 0 256 256')
    svg.set('xmlns', 'http://www.w3.org/2000/svg')

    # Add circles for stars
    for x, y in stars:
        circle = ET.SubElement(svg, 'circle')
        circle.set('cx', str(x))
        circle.set('cy', str(y))
        circle.set('r', '2')

    # Add lines for edges
    for (x1, y1), (x2, y2) in edges:
        line = ET.SubElement(svg, 'line')
        line.set('x1', str(x1))
        line.set('y1', str(y1))
        line.set('x2', str(x2))
        line.set('y2', str(y2))
        line.set('stroke', 'black')

    # Convert to string
    return ET.tostring(svg, encoding='unicode')
