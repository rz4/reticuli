"""Format 3: producer guidance leaves the root.

A hint that helps a producer find a realization cannot decide whether one is
accepted, so at format 3 it is not part of identity. Two claims that differ
only in how they instruct a producer get one root; a claim that changes a
criterion gets another. Formats 1 and 2 are unchanged, so every claim sealed
under them keeps its root. The two identity implementations must agree on all
of this, or format 3 has widened the gap it was meant to close.

Confidence, not identity: the kernel suite pins this at adoption (the v2.4
revision); until then these tests are the witness that the capability works.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel, reference


def _producer_event(claimdir):
    with open(os.path.join(claimdir, kernel.LEDGER)) as f:
        events = [json.loads(x) for x in f if x.strip()]
    return [e for e in events if e.get("event") == "producer"][-1]

GATE = ('\n\n[[step]]\nkind = "gate"\noutput = "V"\n'
        'class = "validated"\nrun = "grep -qi hi g.txt && printf v > V"\n')


def _write(d, recipe):
    d.mkdir(parents=True, exist_ok=True)
    (d / "reticuli.toml").write_text(recipe)
    (d / "g.txt").write_text("hi there\n")
    (d / "V").write_text("v")
    return str(d)


def _roots(d):
    return kernel.root(kernel.load_recipe(d), d), reference.root(d)


def _f3(guidance):
    return (f'[claim]\nname = "g"\nformat = 3\n\n[[step]]\nkind = "produce"\n'
            f'output = "g.txt"\nclass = "generated"\nguidance = "{guidance}"' + GATE)


def test_guidance_does_not_move_a_format3_root(tmp_path):
    a = _write(tmp_path / "a", _f3("say hi politely"))
    b = _write(tmp_path / "b", _f3("ANY completely different instruction"))
    ka, ra = _roots(a)
    kb, rb = _roots(b)
    assert ka == kb, "differently-worded guidance is the same format-3 claim"
    assert ka == ra and kb == rb, "the two implementations agree at format 3"


def test_the_request_spelling_and_the_guidance_spelling_agree(tmp_path):
    g = _write(tmp_path / "g", _f3("do the thing"))
    r = _write(tmp_path / "r", (
        '[claim]\nname = "g"\nformat = 3\n\n[[step]]\nkind = "produce"\n'
        'output = "g.txt"\nclass = "generated"\nrequest = "do the thing"' + GATE))
    assert _roots(g)[0] == _roots(r)[0], \
        "request and guidance are the same key; at format 3 both are stripped"


def test_a_criterion_still_moves_a_format3_root(tmp_path):
    a = _write(tmp_path / "a", _f3("x"))
    b = _write(tmp_path / "b", _f3("x").replace('grep -qi hi', 'grep -qi bye'))
    assert _roots(a)[0] != _roots(b)[0], "the gate command is a criterion; it decides"


def test_format1_and_2_still_hash_guidance(tmp_path):
    # the promise: formats 1 and 2 are unchanged, so their roots still move
    # when the request text changes -- guidance was in-root before format 3
    one = _write(tmp_path / "one", (
        '[claim]\nname = "g"\n\n[[step]]\nkind = "produce"\noutput = "g.txt"\n'
        'class = "generated"\nrequest = "first wording"' + GATE))
    two = _write(tmp_path / "two", (
        '[claim]\nname = "g"\n\n[[step]]\nkind = "produce"\noutput = "g.txt"\n'
        'class = "generated"\nrequest = "second wording"' + GATE))
    assert _roots(one)[0] != _roots(two)[0], \
        "format 1 hashes the whole recipe, guidance included -- unchanged"


def test_guidance_blind_rebuild_lands_the_same_root(tmp_path):
    # the payoff: with guidance out of the root, a rebuild that never saw the
    # hint targets the same root a guided one would
    src = _write(tmp_path / "src", _f3("write the exact bytes: hi there"))
    kernel.seal(src)
    m3 = tmp_path / "m3"
    out = kernel.rebuild(src, "printf 'hi there\\n' > g.txt", str(m3),
                         guidance=False)
    assert out["root"] == kernel.verify(src)["root"], \
        "a guidance-blind rebuild lands the claim's root"
    assert _producer_event(str(m3))["guidance"] is False, \
        "the ledger records that guidance was withheld"


def test_a_producer_run_records_guidance_true_by_default(tmp_path):
    src = _write(tmp_path / "src", _f3("hint"))
    kernel.seal(src)
    m3 = tmp_path / "m3"
    kernel.rebuild(src, "printf 'hi\\n' > g.txt", str(m3))
    assert _producer_event(str(m3))["guidance"] is True
