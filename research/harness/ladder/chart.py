"""Render the ladder's survival curves as a small inline-able SVG.

Reads fingerprints.json (written by run_ladder.py --fingerprints) and emits
an SVG chart: generations on x, live intent bits on y, one line per chain,
blind controls as marks at the right edge. Stdlib only, colors chosen to
read on a dark or light ground.

    python3 chart.py > curves.svg
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

W, H = 640, 300
LEFT, RIGHT, TOP, BOT = 56, 96, 28, 44

STYLE = {
    "claude": ("#e07a5f", "faithful — claude"),
    "codex": ("#5b8dd6", "faithful — codex"),
    "claude-min": ("#e07a5f", "minimize — claude"),
    "codex-min": ("#5b8dd6", "minimize — codex"),
}
DASH = {"claude-min": "5 4", "codex-min": "5 4"}


def curve(rows: dict) -> list:
    pts = []
    for stem in sorted(rows):
        gen = int(stem.removeprefix("gen"))
        pts.append((gen, sum(rows[stem]["survived"].values())))
    return pts


def main() -> str:
    with open(HERE / "fingerprints.json", encoding="utf-8") as f:
        data = json.load(f)
    max_gen = max(g for rows in data["chains"].values()
                  for g, _ in curve(rows))

    def sx(g):
        return LEFT + g * (W - LEFT - RIGHT) / max_gen

    def sy(v):
        return TOP + (8 - v) * (H - TOP - BOT) / 8

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
           f'font-family="system-ui, sans-serif" font-size="11">']
    # axes and gridlines
    for v in range(0, 9, 2):
        y = sy(v)
        out.append(f'<line x1="{LEFT}" y1="{y:.1f}" x2="{W - RIGHT}" '
                   f'y2="{y:.1f}" stroke="#8888" stroke-width="0.5"/>')
        out.append(f'<text x="{LEFT - 8}" y="{y + 4:.1f}" text-anchor="end" '
                   f'fill="#888">{v}</text>')
    for g in range(0, max_gen + 1, 4):
        out.append(f'<text x="{sx(g):.1f}" y="{H - BOT + 16}" '
                   f'text-anchor="middle" fill="#888">{g}</text>')
    out.append(f'<text x="{(LEFT + W - RIGHT) / 2:.0f}" y="{H - 8}" '
               f'text-anchor="middle" fill="#888">generation</text>')
    out.append(f'<text x="14" y="{(TOP + H - BOT) / 2:.0f}" fill="#888" '
               f'text-anchor="middle" transform="rotate(-90 14 '
               f'{(TOP + H - BOT) / 2:.0f})">intent bits alive</text>')
    # chains
    for name, rows in sorted(data["chains"].items()):
        color, label = STYLE.get(name, ("#888", name))
        pts = curve(rows)
        path = " ".join(f"{'M' if i == 0 else 'L'}{sx(g):.1f},{sy(v):.1f}"
                        for i, (g, v) in enumerate(pts))
        dash = f' stroke-dasharray="{DASH[name]}"' if name in DASH else ""
        out.append(f'<path d="{path}" fill="none" stroke="{color}" '
                   f'stroke-width="2"{dash}/>')
        g_last, v_last = pts[-1]
        out.append(f'<text x="{sx(g_last) + 6:.1f}" y="{sy(v_last) + 4:.1f}" '
                   f'fill="{color}">{label}</text>')
    # blind controls at the right edge
    if data.get("controls"):
        for tag, row in sorted(data["controls"].items()):
            v = sum(row["survived"].values())
            fam = "codex" if "codex" in tag else "claude"
            color = STYLE[fam][0]
            out.append(f'<circle cx="{W - RIGHT + 14}" cy="{sy(v):.1f}" '
                       f'r="3.5" fill="none" stroke="{color}" '
                       f'stroke-width="1.5"/>')
        out.append(f'<text x="{W - RIGHT + 26}" y="{sy(1) + 4:.1f}" '
                   f'fill="#888">blind</text>')
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    sys.stdout.write(main())
