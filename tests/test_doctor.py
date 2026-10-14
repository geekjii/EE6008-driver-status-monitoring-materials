import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.doctor import build_report


class DoctorTests(unittest.TestCase):
    def test_missing_config_is_reported_without_camera_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = build_report(root, Path("configs/missing.yaml"))

        self.assertFalse(report["ok"])
        self.assertFalse(report["camera"]["checked"])
        self.assertTrue(any("配置读取失败" in item for item in report["errors"]))

    def test_current_project_report_has_stable_top_level_fields(self):
        root = Path(__file__).resolve().parents[1]
        report = build_report(root, Path("configs/default.yaml"))

        self.assertIn("platform", report)
        self.assertIn("packages", report)
        self.assertIn("inference_device", report)
        self.assertFalse(report["camera"]["checked"])


if __name__ == "__main__":
    unittest.main()
