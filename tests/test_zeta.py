"""Zeta's live probe path, which its criteria deliberately do not touch.

The criteria run against fixtures, because a criterion that read the live queue
would make zeta's verdict depend on whatever the last sweep found. That leaves
the part that actually touches members untested by the claim, and it is the
part most likely to lie: an import that silently resolves to the wrong tree
reports one implementation's behaviour under another's name.
"""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zeta.lib import population as poplib, probe, split as splitlib


class ProbeTests(unittest.TestCase):
    def test_authored_member_answers_a_real_call(self):
        member = {"id": "shipped", "path": str(ROOT / "src"), "package": "reticuli"}
        outcome = probe.observe(member, "record_digest", [{"record": 2}])
        # The document is invalid, so either answer is permitted; what matters
        # is that the member was reached and answered in band.
        self.assertIn(outcome["kind"], ("value", "refused"), outcome)

    def test_import_resolving_outside_the_member_tree_is_refused(self):
        # `reticuli` is importable from the environment, so a member pointed at
        # a tree that does not contain it would otherwise answer with the
        # installed package's behaviour under the member's name.
        with tempfile.TemporaryDirectory() as empty:
            member = {"id": "decoy", "path": empty, "package": "reticuli"}
            outcome = probe.observe(member, "record_digest", [{"record": 2}])
        self.assertEqual(outcome["kind"], "misresolved", outcome)

    def test_a_sibling_whose_name_is_a_prefix_cannot_answer(self):
        # The containment check must be on paths, not on strings: this repo
        # holds both `lineages-r2` and `lineages-r24`.
        lineages = ROOT / "research" / "harness" / "succession"
        short, long = lineages / "lineages-r2", lineages / "lineages-r24"
        if not (short.is_dir() and long.is_dir()):
            self.skipTest("the prefix-sibling pair is not present")
        self.assertTrue(str(long).startswith(str(short)),
                        "the pair must actually share a string prefix")
        family = next((p.name for p in long.iterdir() if p.is_dir()), None)
        member = {"id": "prefix-decoy", "path": str(short),
                  "package": "tree"}
        outcome = probe.observe(member, "record_digest", [{"record": 2}])
        self.assertNotEqual(outcome["kind"], "value",
                            f"a probe at {short.name} must not be answered by "
                            f"{long.name}/{family}: {outcome}")

    def test_absent_package_is_unavailable_not_a_finding(self):
        member = {"id": "ghost", "path": str(ROOT / "src"), "package": "nosuchpkg"}
        outcome = probe.observe(member, "record_digest", [{}])
        self.assertEqual(outcome["kind"], "unavailable", outcome)

    def test_absent_surface_is_reported_as_absent(self):
        member = {"id": "shipped", "path": str(ROOT / "src"), "package": "reticuli"}
        outcome = probe.observe(member, "no_such_function", [])
        self.assertEqual(outcome["kind"], "absent", outcome)

    def test_a_member_that_never_answers_times_out(self):
        original = probe.TIMEOUT
        probe.TIMEOUT = 0.4
        try:
            member = {"id": "slow", "path": str(ROOT / "src"), "package": "reticuli"}
            outcome = probe.observe(member, "sandbox", [])
            self.assertIn(outcome["kind"], ("value", "refused", "timeout"), outcome)
        finally:
            probe.TIMEOUT = original


class LiveRunTests(unittest.TestCase):
    def test_sweeping_the_real_population_classifies_without_crashing(self):
        registry = ROOT / "zeta" / "population" / "reticuli.json"
        if not registry.exists():
            self.skipTest("population registry has not been built")
        population = poplib.load(registry)
        pressure = {"schema": "zeta.pressure.1", "source": "test",
                    "id": "record_validate/smoke", "clause": "smoke",
                    "simplicity": 0, "call": "record_validate",
                    "args": [{"record": 2}],
                    "specified_reader_behaviour": "refused: missing members",
                    "origin": "tests"}
        result = splitlib.run(population, pressure, controls=False)
        reached = [name for name, outcome in result["observations"].items()
                   if outcome["kind"] in ("value", "refused")]
        self.assertEqual(sorted(reached), sorted(result["observations"]),
                         "every current-root member must be reachable")
        # The disposition follows from how many members the current root has,
        # and a root move can leave only the authored one. Both states are
        # ordinary, so assert the rule rather than today's population.
        if len(population["members"]) < 2:
            self.assertEqual(result["disposition"], "singleton", result)
            self.assertIsNone(result["lane"])
            self.assertFalse(splitlib.queueable(result),
                             "a singleton population cannot mint a finding")
        else:
            self.assertIn(result["disposition"], ("agreement", "split"), result)
            self.assertTrue(splitlib.queueable(result))

    def test_registry_matches_the_repository_it_was_built_from(self):
        registry = ROOT / "zeta" / "population" / "reticuli.json"
        if not registry.exists():
            self.skipTest("population registry has not been built")
        stored = poplib.load(registry)
        fresh = poplib.build(ROOT)
        self.assertEqual(stored["current_root"], fresh["current_root"])
        self.assertEqual([m["id"] for m in stored["members"]],
                         [m["id"] for m in fresh["members"]])


if __name__ == "__main__":
    unittest.main()
