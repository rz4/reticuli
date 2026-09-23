"""The substitution demonstrator (stage 1, no producers).

The quirkcalc curve showed a dependency's basin contracts to a behavioral point
on a frozen probe set. This shows the property that matters one level up, the
one astra called the real ground floor: **a dependency that passes its own gate
is not thereby safe to substitute under a consumer.** Consumer-relative
sufficiency is a distinct, stronger property, and the ratchet has to reach it.

Setup: a config parser `D` with a deliberately partial boundary `C_0`, three
hand-written implementations that all pass `C_0` but diverge on the open surface
(duplicate keys, numeric coercion), and a consumer `P` whose correctness depends
on that surface. We measure downstream failure — does a gate-passing `D` break
`P`? — then close the missing obligation and re-judge.

Stage 2 (not here) replaces the hand-written `D`s with blind cross-family
rebuilds, to show the divergence arises on its own.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name):
    p = HERE / "parsers" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse


# --- D's boundary. C_0 pins only non-numeric, single-key behavior, so it says
# nothing about coercion or duplicate keys — the surface where D's diverge. ---
def gate(parse, cases) -> bool:
    for text, want in cases:
        try:
            if parse(text) != want:
                return False
        except Exception:  # noqa: BLE001 — a broken dependency simply fails
            return False
    return True


C0 = [
    ("name = alice", {"name": "alice"}),
    ("a = x\nb = y", {"a": "x", "b": "y"}),
    ("", {}),
]

# C_1 = C_0 + the two obligations the consumer turns out to need, pinned after
# adjudication (numeric values coerce to int; duplicate keys are last-wins).
C1 = C0 + [
    ("n = 42", {"n": 42}),
    ("k = a\nk = b", {"k": "b"}),
]


# --- The consumer P. Its correctness depends on D's open behavior: it reads a
# config with a duplicate, numeric key and does arithmetic on it. ---
CONSUMER_CONFIG = "port = 21\nport = 80"
CONSUMER_EXPECTED = 160  # last-wins (80) coerced to int, doubled


def consume(text, parse):
    cfg = parse(text)
    return cfg["port"] * 2


def p_passes(parse) -> bool:
    try:
        return consume(CONSUMER_CONFIG, parse) == CONSUMER_EXPECTED
    except Exception:  # noqa: BLE001 — a broken dependency simply fails
        return False


def main() -> int:
    names = ["d1_lastwins_int", "d2_firstwins_str", "d3_lastwins_str"]
    impls = {n: load(n) for n in names}

    print("substitution demonstrator (stage 1, hand-written dependencies)\n")
    print(f"  {'dependency':20} {'passes C_0':>11} {'consumer P':>12} {'passes C_1':>11}")
    for n in names:
        parse = impls[n]
        c0 = gate(parse, C0)
        pp = p_passes(parse)
        c1 = gate(parse, C1)
        print(f"  {n:20} {('yes' if c0 else 'no'):>11} "
              f"{('ok' if pp else 'BREAKS'):>12} {('yes' if c1 else 'no'):>11}")

    c0_ok = [n for n in names if gate(impls[n], C0)]
    p_ok = [n for n in names if p_passes(impls[n])]
    c1_ok = [n for n in names if gate(impls[n], C1)]

    print(f"\n  under C_0: {len(c0_ok)}/3 dependencies pass their own gate, "
          f"but only {len(p_ok)}/3 keep the consumer working.")
    print(f"  the {len(c0_ok) - len(p_ok)} gate-passing-but-breaking "
          f"dependenc{'y' if len(c0_ok)-len(p_ok)==1 else 'ies'} expose missing "
          f"obligations (numeric coercion, duplicate-key resolution) that P "
          f"relied on silently.")
    print(f"\n  close the obligations -> C_1. Now {len(c1_ok)}/3 pass, and every "
          f"C_1-passing dependency keeps P working: "
          f"{set(c1_ok) == set(p_ok) and len(c1_ok) > 0}")

    ok = (len(c0_ok) == 3 and len(p_ok) < 3 and set(c1_ok) == set(p_ok)
          and len(c1_ok) >= 1)
    print(f"\n  demonstrator: {'PASS' if ok else 'CHECK'} — a gate-passing "
          f"dependency broke its consumer under C_0; closing the obligation to "
          f"C_1 made substitution safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
