"""The improvement instrument must detect consumer failures and reject bad evidence."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "research" / "harness" / "improvement"
sys.path.insert(0, str(HARNESS))
spec = importlib.util.spec_from_file_location("improvement_campaign", HARNESS / "campaign.py")
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)
subjects = campaign.subjects


class ImprovementTests(unittest.TestCase):
    def candidate(self, source, *, target="config-shared", probes=2, seconds=5):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worker.py"
            path.write_text(source)
            return campaign.run_candidate(target, campaign.candidate_command(path, None), 0,
                                          {"probes": probes, "seconds": seconds})

    def test_all_realizations_pass_disclosed_gate(self):
        for target in subjects.TARGETS:
            subjects.check_population(target)

    def test_shared_failures_are_not_hidden_by_agreement(self):
        row = subjects.evaluate_probe("config-shared", "a=12")
        self.assertFalse(row["differential"])
        self.assertEqual(row["omissions"], ["numeric-coercion"])
        self.assertEqual(len(row["broken_realizations"]), 2)

    def test_negative_control_has_no_findings(self):
        for value in ("a=12", "a=red\na=blue", "# comment\na=7", "malformed"):
            row = subjects.evaluate_probe("config-control", value)
            self.assertEqual(row["omissions"], [])
            self.assertFalse(row["differential"])

    def test_duplicate_witnesses_count_once(self):
        evidence = subjects.evaluate_probe("config-shared", "a=12")
        row = {"target": "config-shared", "status": "completed", "probes": [evidence] * 7}
        self.assertEqual(campaign.score(row)["recall"], 0.5)
        self.assertEqual(campaign.score(row)["credited"], ["numeric-coercion"])

    def test_candidate_feedback_does_not_include_omission_labels(self):
        source = '''import json, sys
start = json.loads(sys.stdin.readline())
assert 'omissions' not in str(start)
print(json.dumps({'op': 'probe', 'input': 'a=12'}), flush=True)
reply = json.loads(sys.stdin.readline())
assert set(reply) == {'event', 'observations'}
print(json.dumps({'op': 'finish'}), flush=True)
'''
        self.assertEqual(self.candidate(source)["status"], "completed")

    def test_excess_probe_request_stops_at_budget(self):
        source = '''import json, sys
sys.stdin.readline()
while True:
    print(json.dumps({'op': 'probe', 'input': 'a=12'}), flush=True)
    if not sys.stdin.readline(): break
'''
        row = self.candidate(source)
        self.assertEqual(row["status"], "budget_exhausted")
        self.assertEqual(len(row["probes"]), 2)

    def test_crash_retains_witness_but_receives_no_credit(self):
        source = '''import json, sys
sys.stdin.readline()
print(json.dumps({'op': 'probe', 'input': 'a=12'}), flush=True)
sys.stdin.readline()
raise RuntimeError('failed after discovery')
'''
        row = self.candidate(source)
        self.assertEqual(row["status"], "failed")
        self.assertEqual(row["score"]["found"], ["numeric-coercion"])
        self.assertEqual(row["score"]["recall"], 0)

    def test_timeout_is_an_assigned_failed_run(self):
        row = self.candidate("import time\ntime.sleep(20)\n", seconds=0.1)
        self.assertEqual(row["status"], "timeout")
        self.assertLess(row["elapsed_seconds"], 2)

    def test_invalid_protocol_and_oversized_responses(self):
        for source in ("print('[]', flush=True)", "print('x' * 70000, flush=True)",
                       "print('{bad json}', flush=True)"):
            self.assertEqual(self.candidate(source)["status"], "failed")

    def test_campaign_replays_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "campaign"
            result = campaign.run_campaign(out, seeds=2, probes=8, seconds=2)
            self.assertEqual(result["arms"]["candidate"]["mean_target_recall"], 1)
            self.assertEqual(result["arms"]["baseline"]["target_calls"],
                             result["arms"]["candidate"]["target_calls"])
            self.assertEqual(campaign.replay(out)["replayed_runs"], 4 * len(subjects.TARGETS))
            self.assertTrue((out / "reticuli.toml").exists())
            summary = json.loads((out / "summary.json").read_text())
            summary["candidate_minus_baseline"] = 999
            (out / "summary.json").write_text(json.dumps(summary))
            with self.assertRaisesRegex(ValueError, "summary"):
                campaign.replay(out)

    def test_deleted_run_is_not_silently_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "campaign"
            campaign.run_campaign(out, seeds=1, probes=4, seconds=2)
            manifest = json.loads((out / "manifest.json").read_text())
            manifest["run_files"].pop()
            (out / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "missing"):
                campaign.replay(out)

    def test_changed_realization_observation_fails_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "campaign"
            campaign.run_campaign(out, seeds=1, probes=4, seconds=2)
            manifest = json.loads((out / "manifest.json").read_text())
            item = manifest["run_files"][0]
            path = out / item["file"]
            record = json.loads(path.read_text())
            record["probes"][0]["consumer_expected"] = {"kind": "value", "value": "fabricated"}
            path.write_text(json.dumps(record))
            # Even updating the checksum cannot make a false observation re-earn.
            item["digest"] = campaign.file_digest(path)
            (out / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "witness"):
                campaign.replay(out)

    def test_existing_output_and_nonfinite_budget_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileExistsError):
                campaign.run_campaign(directory, seeds=1, probes=1, seconds=1)
            with self.assertRaises(ValueError):
                campaign.run_campaign(Path(directory) / "invalid", seeds=1, probes=1,
                                      seconds=float("nan"))

    def test_evidence_recipe_pins_candidates_and_reearns_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "campaign"
            campaign.run_campaign(out, seeds=1, probes=4, seconds=2)
            recipe = tomllib.loads((out / "reticuli.toml").read_text())
            self.assertIn("candidate.py", recipe["claim"]["inputs"])
            self.assertIn("summary.json", recipe["claim"]["inputs"])
            # Execute the self-contained retained evaluator, not the working tree.
            result = subprocess.run([sys.executable, str(out / "check_replay.py")],
                                    cwd=out, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((out / "EVIDENCE_OK").read_text(), "ok\n")


if __name__ == "__main__":
    unittest.main()
