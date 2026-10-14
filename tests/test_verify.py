import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.verify import main, run_logic_checks


class VerificationTests(unittest.TestCase):
    def test_logic_only_produces_isolated_reports_without_camera_or_models(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "验收结果"
            with patch("driver_monitor.runtime._open_capture", side_effect=AssertionError("camera forbidden")) as capture:
                for _ in range(2):
                    self.assertEqual(main(["--logic-only", "--output-dir", str(output)]), 0)
            capture.assert_not_called()
            reports = list(output.glob("*/report.json"))
            self.assertEqual(len(reports), 2)
            report = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(report["scope"], "synthetic_logic_only")
            self.assertTrue(report["video_smoke"]["skipped"])
            self.assertFalse(report["camera_accessed"])
            self.assertEqual(len(report["logic_checks"]), 8)
            self.assertTrue(all(case["ok"] for case in report["logic_checks"]))
            states = [json.loads(line)["state"] for line in
                      (reports[0].parent / "sustained_closure_and_recovery.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(states, ["NORMAL", "WARNING", "DANGER", "NORMAL"])

    def test_environment_failure_skips_inference_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}", encoding="utf-8")
            with patch("driver_monitor.doctor.build_report", return_value={"ok": False, "errors": ["missing model"]}), \
                 patch("driver_monitor.verify.run_video_smoke") as smoke:
                status = main(["--config", str(config), "--output-dir", directory])
            smoke.assert_not_called()
            self.assertEqual(status, 1)
            report = json.loads(next(Path(directory).glob("*/report.json")).read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertTrue(report["video_smoke"]["skipped"])

    def test_logging_failure_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("driver_monitor.verify.JsonlEventWriter.write_if_changed", side_effect=OSError("disk full")):
                checks = run_logic_checks(Path(directory))
            self.assertTrue(any(not case["ok"] for case in checks))
            self.assertIn("disk full", checks[0]["error"])

    def test_inference_failure_is_saved_in_report_and_returns_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text("{}", encoding="utf-8")
            with patch("driver_monitor.doctor.build_report", return_value={"ok": True}), \
                 patch("driver_monitor.verify.run_video_smoke", side_effect=RuntimeError("decoder failed")):
                status = main(["--config", str(config), "--output-dir", directory])
            self.assertEqual(status, 1)
            report = json.loads(next(Path(directory).glob("*/report.json")).read_text(encoding="utf-8"))
            self.assertEqual(report["video_smoke"]["error"], "decoder failed")


if __name__ == "__main__":
    unittest.main()
