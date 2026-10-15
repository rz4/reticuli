"""Automatic policy successors must improve and preserve their replayable lineage."""

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HARNESS = Path(__file__).resolve().parents[1] / "research" / "harness" / "improvement"
sys.path.insert(0, str(HARNESS))
import evolve


class EvolutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / "lineage"
        cls.result = evolve.run(cls.output, rounds=3, seeds=1, probes=8, seconds=2)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def tampered(self, change, expected):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "copy"
            shutil.copytree(self.output, out)
            lineage = json.loads((out / "lineage.json").read_text())
            change(lineage, out)
            evolve.save(out / "lineage.json", lineage)
            with self.assertRaisesRegex(ValueError, expected):
                evolve.replay(out)

    def test_three_successors_improve_over_frozen_investigator(self):
        self.assertEqual(self.result["accepted_generations"], 3)
        self.assertGreater(self.result["final_minus_frozen"], 0.4)
        self.assertEqual(self.result["frozen_recall"], 0)
        self.assertEqual(evolve.replay(self.output), self.result)
        self.assertGreater(self.result["total_search_target_calls"], 0)

    def test_each_successor_inherits_and_proposes_next_generation(self):
        lineage = json.loads((self.output / "lineage.json").read_text())
        for index, record in enumerate(lineage["rounds"]):
            self.assertEqual(record["parent"], f"generation-{index}.py")
            self.assertEqual(len(record["proposal"]["parent_policy"]), index)
            for item in record["proposal"]["candidates"]:
                self.assertEqual(item["policy"][:-1], record["proposal"]["parent_policy"])

    def test_fabricated_decision_does_not_reearn(self):
        def change(lineage, out):
            lineage["rounds"][0]["decision"]["accepted"] = False
        self.tampered(change, "decision")

    def test_source_tampering_is_detected_before_running_child(self):
        def change(lineage, out):
            path = out / lineage["rounds"][0]["winner"]
            path.write_text(path.read_text() + "\nraise RuntimeError('tampered')\n")
        self.tampered(change, "source")

    def test_valid_witness_cannot_be_assigned_to_a_different_policy(self):
        def change(lineage, out):
            row = lineage["initial"]["runs"][0]
            row["probes"][0] = evolve.subjects.evaluate_probe(row["target"], "a=12")
            row["score"] = evolve.campaign.score(row)
            lineage["initial"]["metrics"] = evolve.metrics(lineage["initial"]["runs"])
        self.tampered(change, "claimed investigator")

    def test_missing_search_candidate_does_not_reearn(self):
        def change(lineage, out):
            lineage["rounds"][0]["attempts"].pop()
        self.tampered(change, "search evidence")

    def test_regression_or_failed_run_blocks_adoption(self):
        parent = {"recall": 0.25, "per_target": {"a": 0.5, "b": 0.0}, "failed": 0}
        child = {"recall": 0.5, "per_target": {"a": 0.0, "b": 1.0}, "failed": 0}
        self.assertFalse(evolve.decision(parent, child, parent, child, 0.05)["accepted"])
        improved = copy.deepcopy(child)
        improved["per_target"]["a"] = 0.5
        improved["failed"] = 1
        self.assertFalse(evolve.decision(parent, improved, parent, improved, 0.05)["accepted"])

    def test_high_threshold_leaves_parent_active(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "rejected"
            result = evolve.run(out, rounds=2, seeds=1, probes=8, minimum_gain=1)
            self.assertEqual(result["accepted_generations"], 0)
            self.assertEqual(result["active"], "generation-0.py")
            self.assertEqual(result["final_minus_frozen"], 0)
            self.assertEqual(evolve.replay(out), result)

    def test_invalid_policy_and_budgets_are_refused(self):
        source = (HARNESS / "policy_template.py").read_text()
        for policy in (["duplicate", "duplicate"], ["unknown"]):
            with self.assertRaises(ValueError):
                evolve.compile_policy(source, policy)
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            evolve.run(Path(directory) / "invalid", rounds=0)


if __name__ == "__main__":
    unittest.main()
