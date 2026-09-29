"""Blind cross-family regrowth of the seal renderer.

The seal claim pins the geometry — the root-to-constellation mapping any
conforming renderer must agree on — and deliberately leaves the styling
free. Regrowing the renderer blind from its check alone is the stage-2
protocol on a visual subject: every reconstruction must draw the SAME sky
for the same root (pinned), and how each family dresses that sky (colors,
radii, stroke widths, decoration) is the unpinned surface, made visible.

    python3 research/harness/seal/run_seal.py             # rebuild + report
    python3 research/harness/seal/run_seal.py --report    # report only
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO / "src"))
from reticuli import kernel  # noqa: E402

VENV_PY = str(REPO / ".venv" / "bin" / "python")
S, IMPLS, SCRATCH = HERE / "claims/S", HERE / "impls", HERE / "scratch"

PLAN = [
    ("codex", "reticuli.producers.codex", "gpt-6-luna"),
    ("codex", "reticuli.producers.codex", "gpt-6-sol"),
    ("codex", "reticuli.producers.codex", "gpt-6-astra"),
    ("claude", "reticuli.producers.claude", "sonnet"),
    ("claude", "reticuli.producers.claude", "opus"),
    ("claude", "reticuli.producers.claude", "haiku"),
]

QUOTA = re.compile(r"usage limit|rate limit|try again|quota|429", re.IGNORECASE)

#: the sky every reconstruction is asked to draw for the report
SUBJECT_ROOT = "16297fb004733bfc2cb218aaa15086dfb1731ecaead3cdacec206126a77bbe90"


def rebuild_all() -> None:
    import os
    IMPLS.mkdir(exist_ok=True)
    SCRATCH.mkdir(exist_ok=True)
    for idx, (family, module, model) in enumerate(PLAN):
        tag = f"{idx:02d}_{family}_{model.replace('-', '_')}"
        dest = IMPLS / f"impl_{tag}.py"
        if dest.exists():
            print(f"[{tag}] already ingested", flush=True)
            continue
        out = SCRATCH / f"rebuild_{tag}"
        if out.exists():
            shutil.rmtree(out)
        print(f"[{tag}] rebuilding blind...", flush=True)
        os.environ["RETICULI_MODEL"] = model
        os.environ["RETICULI_VENDOR"] = family
        producer = f"{VENV_PY} -P -m {module}"
        try:
            r = kernel.rebuild(str(S), producer, str(out), guidance=False,
                               producer_env={"RETICULI_MODEL": model})
        except kernel.ClaimError as exc:
            text = str(exc)
            if QUOTA.search(text):
                print(f"[{tag}] QUOTA — stopping; re-run to resume.", flush=True)
                break
            print(f"[{tag}] did not converge: {text[-300:]}", flush=True)
            continue
        assert r["root"] == kernel.verify(str(S))["root"]
        shutil.copy(out / "seal.py", dest)
        print(f"[{tag}] converged -> {dest.name}", flush=True)


def _render_with(impl: Path, root: str) -> str:
    """Render in a subprocess: generated code stays out of this process."""
    code = (
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('seal', {str(impl)!r})\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        f"sys.stdout.write(m.render({root!r}))\n")
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, timeout=60, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def _styling(svg: str) -> dict:
    """The unpinned surface of one rendering, reduced to comparable tokens."""
    return {
        "fills": sorted(set(re.findall(r'fill="([^"]+)"', svg))),
        "strokes": sorted(set(re.findall(r'stroke="([^"]+)"', svg))),
        "widths": sorted(set(re.findall(r'stroke-width="([^"]+)"', svg))),
        "radii": sorted(set(re.findall(r'\br="([^"]+)"', svg))),
        "extra_elements": sorted(set(re.findall(r"<(\w+)", svg))
                                 - {"svg", "circle", "line"}),
    }


def report() -> None:
    rows = {}
    reference = S / "seal.py"
    for impl in [reference] + sorted(IMPLS.glob("impl_*.py")):
        svg = _render_with(impl, SUBJECT_ROOT)
        name = "reference" if impl == reference else impl.stem
        rows[name] = _styling(svg)
        (SCRATCH / f"sky_{name}.svg").write_text(svg, encoding="utf-8")
    with open(HERE / "styling.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, sort_keys=True)
    print(f"\nseal regrowth — one root ({SUBJECT_ROOT[:12]}), "
          f"{len(rows)} renderers, same sky, each family's own weather:\n")
    for name, style in rows.items():
        print(f"  {name}")
        for key, values in style.items():
            if values:
                print(f"    {key:15} {', '.join(values)}")


if __name__ == "__main__":
    if "--report" not in sys.argv:
        rebuild_all()
    report()
