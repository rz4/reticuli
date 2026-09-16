"""Turn a run's rows into the finding, including when the finding is negative.

The headline is a two-by-two count, not a correlation, because the question is
not "do these numbers move together" but "how often does self-verification say
yes when the answer is no". Those are different questions and only the second
one matters to somebody deciding whether to trust a green test suite.

    x high, y = 1     self-verification agreed with reality
    x high, y < 1     THE DANGEROUS CELL: thorough-looking tests over wrong
                      code. Mutation testing is structurally unable to see
                      this, since mutating an implementation can only measure
                      agreement between code and tests, and here they agree.
    x low,  y = 1     correct by luck, as far as the tests are concerned
    x low,  y < 1     honest failure: the suite looks weak and the code is wrong

The control matters as much as the headline. If counting `assert` statements
separates the same rows as well as a mutation score does, then a mutation
score is an expensive way to learn something cheap, and this report says so.

    python3 analyze.py results/claude-*.jsonl
"""
from __future__ import annotations

import json
import os
import statistics
import sys

#: What counts as a suite that LOOKS thorough. Arbitrary, stated, and varied
#: in the sensitivity line below so no conclusion rests on the choice.
X_HIGH = 0.80


def load(paths: list) -> list:
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            rows += [json.loads(line) for line in f if line.strip()]
    return rows


def spearman(pairs: list):
    """Rank correlation, written out because the stdlib only grew a `ranked`
    method in 3.12 and this repository supports 3.11."""
    if len(pairs) < 3:
        return None

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        ranks = [0.0] * len(values)
        i = 0
        while i < len(order):                    # average ties, or a column of
            j = i                                # identical values breaks it
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            shared = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[order[k]] = shared
            i = j + 1
        return ranks

    left, right = rank([p[0] for p in pairs]), rank([p[1] for p in pairs])
    if len(set(left)) < 2 or len(set(right)) < 2:
        return None                              # no variation: undefined
    return statistics.correlation(left, right)


def quadrants(rows: list, x_high: float = X_HIGH) -> dict:
    cells = {("high", "wrong"): [], ("high", "right"): [],
             ("low", "wrong"): [], ("low", "right"): []}
    for row in rows:
        side = "high" if row["x"] >= x_high else "low"
        truth = "right" if row["y"] >= 1.0 else "wrong"
        cells[(side, truth)].append(row["task_id"])
    return cells


def report(rows: list, label: str) -> str:
    out = [f"# Self-verification study — {label}", ""]

    attempted = len(rows)
    authored = [r for r in rows if r.get("authored")]
    measured = [r for r in authored
                if r.get("x") is not None and r.get("y") is not None]
    spend = sum((r.get("spend") or {}).get("usd", 0.0) for r in rows)
    tokens = sum((r.get("spend") or {}).get("tokens", 0) for r in rows)

    out += ["## The run", "",
            (f"- {attempted} tasks attempted, {len(authored)} produced an "
             f"implementation and a test suite that pass together"),
            f"- {len(measured)} of those could be measured on both axes"]
    if spend or tokens:
        out.append(f"- {tokens:,} tokens" + (f", ${spend:.2f}" if spend else ""))
    turns = [r["turns"] for r in authored if r.get("turns")]
    if turns:
        repaired = sum(1 for t in turns if t > 1)
        out.append(f"- {repaired} of {len(turns)} needed at least one repair "
                   f"turn after its own tests failed")
    unauthored = [r for r in rows if not r.get("authored")]
    for row in unauthored:
        out.append(f"  - {row['task_id']} never authored: "
                   f"{' '.join((row.get('why') or '?').split())[:110]}")
    out.append("")

    if not measured:
        out += ["Nothing was measured, so there is nothing to report.", ""]
        return "\n".join(out)

    correct = [r for r in measured if r["y"] >= 1.0]
    out += ["## Correctness, by an oracle the model never saw", "",
            (f"- {len(correct)} of {len(measured)} agree with the reference on "
             f"every input ({len(correct) / len(measured):.0%})")]
    base_only = [r for r in measured
                 if r.get("y_base") is not None and r["y_base"] >= 1.0 > r["y"]]
    out.append(f"- {len(base_only)} pass the task's ORIGINAL handful of test "
               f"inputs but fail the extended set — the weak-oracle effect, "
               f"and the reason a stored suite is not used as truth here")
    out.append("")

    cells = quadrants(measured)
    n = len(measured)
    out += ["## The headline", "",
            (f"Rows split at x ≥ {X_HIGH:.2f} (a suite that looks thorough) and "
             f"y = 1.000 (agrees with the reference everywhere)."), "",
            "| | code is right | code is wrong |", "|---|---|---|"]
    for side in ("high", "low"):
        right, wrong = len(cells[(side, "right")]), len(cells[(side, "wrong")])
        name = ("**tests look thorough**" if side == "high"
                else "tests look weak")
        mark = " ⟵ **the dangerous cell**" if side == "high" and wrong else ""
        out.append(f"| {name} | {right} ({right / n:.0%}) | "
                   f"{wrong} ({wrong / n:.0%}){mark} |")
    out.append("")
    dangerous = cells[("high", "wrong")]
    if dangerous:
        listed = ", ".join(dangerous[:12])
        if len(dangerous) > 12:
            listed += f" … and {len(dangerous) - 12} more"
        out += [(f"**{len(dangerous)} of {n} ({len(dangerous) / n:.0%}) are "
                 f"wrong code carrying a test suite that scores {X_HIGH:.2f} "
                 f"or better against itself.**"), "", "  " + listed, ""]
    else:
        out += [("No row landed in the dangerous cell. With this sample size "
                 "that is weak evidence of absence, not evidence of absence."), ""]

    # Sensitivity: the split point is arbitrary, so show it does not carry
    # the conclusion.
    line = []
    for bar in (0.6, 0.7, 0.8, 0.9, 1.0):
        cell = quadrants(measured, bar)[("high", "wrong")]
        line.append(f"x≥{bar:.1f}: {len(cell)}")
    out += ["Dangerous-cell count as the bar moves — " + ", ".join(line), ""]

    out += ["## Does the mutation score predict correctness?", ""]
    pairs = [(r["x"], r["y"]) for r in measured]
    rho = spearman(pairs)
    control = [(r["asserts"], r["y"]) for r in measured if r.get("asserts")]
    rho_control = spearman(control)
    shown = "undefined (no variation)" if rho is None else f"ρ = {rho:.2f}"
    shown_control = "undefined" if rho_control is None else f"ρ = {rho_control:.2f}"
    out.append(f"- mutation score vs correctness: {shown}")
    out.append(f"- assertion COUNT vs correctness (the control): {shown_control}")
    if rho is not None and rho_control is not None:
        verdict = ("the mutation score carries more signal than counting asserts"
                   if rho > rho_control + 0.1 else
                   "counting asserts does as well — on this sample the mutation "
                   "score is not earning its cost")
        out.append(f"- {verdict}")
    means = f"Mean mutation score {statistics.mean(p[0] for p in pairs):.2f}"
    wrong_x = [r["x"] for r in measured if r["y"] < 1.0]
    if wrong_x:
        means += (f"; among the implementations that are actually wrong, "
                  f"{statistics.mean(wrong_x):.2f}")
    out += ["", means, ""]

    kinds: dict = {}
    for row in measured:
        for kind, rate in (row.get("x_by_kind") or {}).items():
            kinds.setdefault(kind, []).append(rate)
    if kinds:
        out += ["## Where the suites are blind", "",
                ("Mean kill rate per fault kind, over every measured task. The "
                 "aggregate hides this, and this is the actionable part."), "",
                "| fault kind | mean kill rate | tasks |", "|---|---|---|"]
        for kind in sorted(kinds, key=lambda k: statistics.mean(kinds[k])):
            out.append(f"| {kind} | {statistics.mean(kinds[kind]):.2f} | "
                       f"{len(kinds[kind])} |")
        out.append("")
    return "\n".join(out)


def scatter(rows: list, path: str) -> None:
    """The plot, as hand-written SVG: this repository is standard library only."""
    width, height, pad = 520, 420, 56
    points = []
    for row in rows:
        px = pad + row["x"] * (width - 2 * pad)
        py = height - pad - row["y"] * (height - 2 * pad)
        wrong = row["y"] < 1.0
        points.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" '
                      f'fill="{"#c0392b" if wrong else "#2c7fb8"}" '
                      f'fill-opacity="0.65"><title>{row["task_id"]}: '
                      f'x={row["x"]:.2f} y={row["y"]:.3f}</title></circle>')
    ticks = []
    for t in (0.0, 0.25, 0.5, 0.75, 1.0):
        gx = pad + t * (width - 2 * pad)
        gy = height - pad - t * (height - 2 * pad)
        ticks.append(f'<line x1="{gx:.1f}" y1="{pad}" x2="{gx:.1f}" '
                     f'y2="{height - pad}" stroke="#eee"/>'
                     f'<line x1="{pad}" y1="{gy:.1f}" x2="{width - pad}" '
                     f'y2="{gy:.1f}" stroke="#eee"/>'
                     f'<text x="{gx:.1f}" y="{height - pad + 18}" font-size="11" '
                     f'text-anchor="middle" fill="#666">{t:.2f}</text>'
                     f'<text x="{pad - 8}" y="{gy + 4:.1f}" font-size="11" '
                     f'text-anchor="end" fill="#666">{t:.2f}</text>')
    danger = pad + X_HIGH * (width - 2 * pad)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif">
<rect width="{width}" height="{height}" fill="white"/>
{''.join(ticks)}
<rect x="{danger:.1f}" y="{pad + 8}" width="{width - pad - danger:.1f}" \
height="{height - 2 * pad - 8}" fill="#c0392b" fill-opacity="0.05"/>
<text x="{(danger + width - pad) / 2:.1f}" y="{height - pad - 8}" font-size="10" \
text-anchor="middle" fill="#c0392b">thorough-looking tests, wrong code</text>
<line x1="{pad}" y1="{height - pad}" x2="{width - pad}" y2="{height - pad}" stroke="#333"/>
<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height - pad}" stroke="#333"/>
{''.join(points)}
<text x="{width / 2}" y="{height - 12}" font-size="12" text-anchor="middle">\
mutation score of the model's own tests</text>
<text x="16" y="{height / 2}" font-size="12" text-anchor="middle" \
transform="rotate(-90 16 {height / 2})">agreement with the held-back reference</text>
</svg>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)


def main() -> int:
    paths = sys.argv[1:]
    if not paths:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    rows = load(paths)
    label = os.path.basename(paths[0]).removesuffix(".jsonl")
    text = report(rows, label)
    out = os.path.join(os.path.dirname(paths[0]) or ".", f"{label}.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    plottable = [r for r in rows
                 if r.get("x") is not None and r.get("y") is not None]
    if plottable:
        scatter(plottable, os.path.join(os.path.dirname(paths[0]) or ".",
                                        f"{label}.svg"))
    print(text)
    print(f"\n-> {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
