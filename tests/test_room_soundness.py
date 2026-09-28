"""The judging room matches the name, and a rebuild cannot change the question.

Two soundness properties, both found by the 2026-09-22 cross-family reading
(research/audits/2026-09-22-cross-family-essence-and-soundness.md):

Finding A: at format 3 producer guidance is stripped from the root preimage,
so it must also be absent from the room a gate judges in -- otherwise a gate
that reads its own recipe can accept differently for the same root, and words
outside the identity decide acceptance. The room receives the recipe the root
was computed from; formats 1 and 2, which hash the whole recipe, receive the
whole file unchanged.

Finding B: a rebuild reproduces a claim. A producer that alters a pinned
input or the recipe makes the destination seal to a different root -- a
self-consistent claim that is not this one -- and that is a failure of the
rebuild, not a success with a surprising root.

Confidence, not identity: these are the witness until the kernel suite pins
the properties at a keyholder transition.
"""
import json
import os
import sys
import tomllib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "src"))
from reticuli import kernel
from reticuli._kernel import build as _build
from reticuli._kernel import identity as _identity

# A gate that reads its own recipe's guidance: the exact vector from the
# cross-family reading. If the room carried the raw recipe, the verdict would
# follow the guidance wording -- same root, different acceptance.
_READER = (
    "python3 -c \"import tomllib; "
    "g = tomllib.load(open('reticuli.toml','rb'))['step'][0].get('guidance',''); "
    "exit(0 if g == 'yes' else 1)\" && printf v > V")


def _guided(d, guidance, gate_run):
    d.mkdir(parents=True, exist_ok=True)
    (d / "reticuli.toml").write_text(
        f'[claim]\nname = "g"\nformat = 3\ninputs = ["c.txt"]\n\n'
        f'[[step]]\nkind = "produce"\noutput = "g.txt"\nclass = "generated"\n'
        f'guidance = "{guidance}"\n\n'
        f'[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\n'
        f'run = {json.dumps(gate_run)}\n')
    (d / "c.txt").write_text("the criterion\n")
    (d / "g.txt").write_text("hi there\n")
    (d / "V").write_text("v")
    kernel.seal(str(d))
    return str(d)


def test_guidance_cannot_decide_acceptance(tmp_path):
    # Two claims differing only in guidance share one root, so they must
    # share one verdict. A gate that tries to read the guidance finds the
    # stripped recipe in the room and answers the same way for both.
    yes = _guided(tmp_path / "yes", "yes", _READER)
    no = _guided(tmp_path / "no", "no", _READER)
    assert kernel.verify(yes)["root"] == kernel.verify(no)["root"], \
        "the two claims are one claim: only guidance differs"
    a, b = kernel.audit(yes), kernel.audit(no)
    assert a["ok"] == b["ok"], "one root, one verdict"
    assert not a["ok"], "words outside the identity no longer decide acceptance"


def test_the_room_holds_the_recipe_the_root_names(tmp_path):
    src = _guided(tmp_path / "src", "some helpful hint",
                  "grep -qi hi g.txt && printf v > V")
    recipe = kernel.load_recipe(src)
    room = tmp_path / "room"
    _build._materialize(src, recipe, str(room))
    with open(room / "reticuli.toml", "rb") as f:
        seen = tomllib.load(f)
    assert seen == _identity._preimage_recipe(recipe), \
        "the room's recipe is exactly the preimage recipe"
    assert "guidance" not in seen["step"][0], "the hint never enters the room"


def test_format1_rooms_receive_the_whole_file(tmp_path):
    # Formats 1 and 2 hash the whole recipe: guidance is identity there, so
    # the room receives the file byte for byte, comments and all.
    d = tmp_path / "old"
    d.mkdir()
    text = ('# a comment a copy preserves\n[claim]\nname = "g"\n\n'
            '[[step]]\nkind = "produce"\noutput = "g.txt"\n'
            'class = "generated"\nrequest = "the old spelling"\n\n'
            '[[step]]\nkind = "gate"\noutput = "V"\nclass = "validated"\n'
            'run = "grep -qi hi g.txt && printf v > V"\n')
    (d / "reticuli.toml").write_text(text)
    (d / "g.txt").write_text("hi\n")
    (d / "V").write_text("v")
    room = tmp_path / "room"
    _build._materialize(str(d), kernel.load_recipe(str(d)), str(room))
    assert (room / "reticuli.toml").read_text() == text, \
        "a format-1 room carries the raw recipe: its root covers every byte"


def test_a_blind_rebuild_is_blind_to_the_recipe_too(tmp_path):
    # The corollary: a guidance-blind rebuild used to leave the hint readable
    # in the room's recipe. Now a producer that goes looking finds nothing.
    src = _guided(tmp_path / "src", "hi there",
                  "grep -qi hi g.txt && printf v > V")
    steal = ("python3 -c \"import tomllib; "
             "g = tomllib.load(open('reticuli.toml','rb'))['step'][0]"
             ".get('guidance','no lock was ever cut'); "
             "open('g.txt','w').write(g)\"")
    with pytest.raises(kernel.ClaimError):
        kernel.rebuild(src, steal, str(tmp_path / "m3"), guidance=False)


def test_a_guided_rebuild_still_hands_the_hint_over_the_environment(tmp_path):
    # Guidance reaches a producer through RETICULI_REQUEST, never through the
    # room's recipe: the sanctioned channel survives the stripping.
    src = _guided(tmp_path / "src", "hi there",
                  "grep -qi hi g.txt && printf v > V")
    out = kernel.rebuild(src, 'printf "%s\\n" "$RETICULI_REQUEST" > g.txt',
                         str(tmp_path / "m3"))
    assert out["root"] == kernel.verify(src)["root"]


def test_a_rebuild_that_alters_a_pinned_input_fails(tmp_path):
    src = _guided(tmp_path / "src", "hi there",
                  "grep -qi hi g.txt && printf v > V")
    tamper = 'printf "hi there\\n" > g.txt && printf "moved\\n" > c.txt'
    with pytest.raises(kernel.ClaimError) as err:
        kernel.rebuild(src, tamper, str(tmp_path / "m3"))
    assert "c.txt" in str(err.value) and "pinned" in str(err.value), \
        "the failure names what happened: the producer changed the question"


def test_a_rebuild_that_edits_the_recipe_fails(tmp_path):
    src = _guided(tmp_path / "src", "hi there",
                  "grep -qi hi g.txt && printf v > V")
    tamper = ('printf "hi there\\n" > g.txt && '
              'printf "\\n# a new criterion\\n" >> reticuli.toml')
    with pytest.raises(kernel.ClaimError) as err:
        kernel.rebuild(src, tamper, str(tmp_path / "m3"))
    assert "reticuli.toml" in str(err.value), \
        "rewriting the recipe is changing the question, and it is refused"


def test_a_threaded_input_is_still_a_deliberate_substitution(tmp_path):
    # The caller may thread a different input (the composition path); the
    # snapshot is taken after threading, so only the PRODUCER is barred from
    # touching pinned bytes. A different input is a different claim, sealed
    # and said so -- exactly what the kernel suite pins.
    src = _guided(tmp_path / "src", "hi there",
                  "grep -qi hi g.txt && printf v > V")
    fresh = tmp_path / "fresh.txt"
    fresh.write_text("the criterion, revised by a rebuilt component\n")
    out = kernel.rebuild(src, 'printf "hi there\\n" > g.txt',
                         str(tmp_path / "m3"), input_from={"c.txt": str(fresh)})
    assert out["root"] != kernel.verify(src)["root"], \
        "a different input is a different claim, visibly"


def test_an_honest_rebuild_still_lands_the_root(tmp_path):
    src = _guided(tmp_path / "src", "hi there",
                  "grep -qi hi g.txt && printf v > V")
    out = kernel.rebuild(src, 'printf "hi there\\n" > g.txt',
                         str(tmp_path / "m3"))
    assert out["root"] == kernel.verify(src)["root"], \
        "a producer that writes only generated outputs reproduces the claim"
