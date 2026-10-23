from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

from research_agent.experiments import ExperimentError, load_spec, run_experiment


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.spec = self.root / "spec.json"
        self.out = self.root / "runs"

    def tearDown(self):
        self.temp.cleanup()

    def write_spec(self, script: str, **kwargs):
        data = {"argv": [sys.executable, "-c", script], "cwd": ".", "timeout_s": 5}
        data.update(kwargs)
        self.spec.write_text(json.dumps(data), encoding="utf-8")

    def test_success_records_metrics_but_not_scientific_success(self):
        (self.root / "eval.py").write_text("fixed evaluator")
        self.write_spec(
            "import json; print('finished'); json.dump({'accuracy':0.4},open('metrics.json','w'))",
            metrics_file="metrics.json", protected_files=["eval.py"],
        )
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["execution_status"], "succeeded")
        self.assertEqual(result["scientific_status"], "unreviewed")
        self.assertEqual(result["integrity_status"], "unchanged")
        self.assertTrue(result["metrics_valid"])
        self.assertEqual(result["metrics"], {"accuracy": 0.4})
        self.assertEqual(Path(result["stdout_path"]).read_text().strip(), "finished")
        self.assertEqual(json.loads(Path(result["report_path"]).read_text()), result)

    def test_timeout_does_not_accept_partial_metrics(self):
        self.write_spec(
            "import time; open('metrics.json','w').write('{\"score\":1}'); time.sleep(10)",
            metrics_file="metrics.json", timeout_s=0.2,
        )
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["execution_status"], "timed_out")
        self.assertLess(result["duration_s"], 3)
        self.assertFalse(result["metrics_valid"])
        self.assertEqual(result["metrics"], {})

    def test_modified_evaluator_invalidates_metrics(self):
        (self.root / "eval.py").write_text("original")
        self.write_spec(
            "open('eval.py','w').write('changed'); open('metrics.json','w').write('{\"score\":1}')",
            protected_files=["eval.py"], metrics_file="metrics.json",
        )
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["execution_status"], "succeeded")
        self.assertEqual(result["integrity_status"], "changed")
        self.assertEqual(result["metrics_status"], "integrity_violation")
        self.assertFalse(result["metrics_valid"])
        self.assertEqual(result["scientific_status"], "unreviewed")

    def test_stale_metrics_are_not_reused(self):
        (self.root / "metrics.json").write_text('{"score":99}')
        self.write_spec("print('no new metrics')", metrics_file="metrics.json")
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["metrics_status"], "stale")
        self.assertFalse(result["metrics_valid"])
        self.assertEqual(result["metrics"], {})

    def test_failed_command_is_not_scientific_failure(self):
        self.write_spec("import sys; sys.exit(3)")
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["execution_status"], "failed")
        self.assertEqual(result["returncode"], 3)
        self.assertEqual(result["scientific_status"], "unreviewed")

    def test_missing_protected_file_fails_before_launch(self):
        self.write_spec("open('launched','w').write('bad')", protected_files=["missing.py"])
        with self.assertRaises(ExperimentError):
            run_experiment(self.spec, self.out)
        self.assertFalse((self.root / "launched").exists())
        self.assertFalse(self.out.exists())

    def test_metrics_path_cannot_escape_cwd(self):
        self.write_spec("print('unsafe path')", metrics_file="../metrics.json")
        with self.assertRaises(ExperimentError):
            load_spec(self.spec)

    def test_unknown_environment_override_rejected(self):
        self.write_spec("print('unused')", env={"TOKEN": "secret"})
        with self.assertRaises(ExperimentError):
            load_spec(self.spec)

    def test_nan_metrics_rejected(self):
        self.write_spec("open('metrics.json','w').write('{\"score\":NaN}')", metrics_file="metrics.json")
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["metrics_status"], "invalid")
        self.assertFalse(result["metrics_valid"])

    def test_overflowed_json_number_is_rejected(self):
        self.write_spec("open('metrics.json','w').write('{\"score\":1e999}')", metrics_file="metrics.json")
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["metrics_status"], "invalid")
        self.assertEqual(result["metrics"], {})

    def test_missing_executable_creates_failed_report(self):
        self.write_spec("unused", argv=[str(self.root / "nonexistent")])
        result = run_experiment(self.spec, self.out)
        self.assertEqual(result["execution_status"], "failed")
        self.assertIsNone(result["returncode"])
        self.assertTrue(result["errors"])

    def test_each_run_gets_unique_artifacts(self):
        self.write_spec("print('run')")
        first = run_experiment(self.spec, self.out)
        second = run_experiment(self.spec, self.out)
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(Path(first["report_path"]).is_file())


if __name__ == "__main__":
    unittest.main()
