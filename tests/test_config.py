import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.config import AppConfig, FatigueConfig


class ConfigTests(unittest.TestCase):
    def test_defaults_are_valid(self):
        config = AppConfig.from_mapping({})
        self.assertEqual(config.camera.index, 0)
        self.assertEqual(config.phone.device, "auto")
        self.assertLess(
            config.fatigue.perclos_warning_threshold,
            config.fatigue.perclos_danger_threshold,
        )

    def test_invalid_eye_durations_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "must exceed"):
            FatigueConfig(eye_warning_seconds=3.0, eye_danger_seconds=2.0).validate()

    def test_nested_values_override_defaults(self):
        config = AppConfig.from_mapping(
            {"camera": {"index": 2}, "fatigue": {"ear_closed_threshold": 0.18}}
        )
        self.assertEqual(config.camera.index, 2)
        self.assertAlmostEqual(config.fatigue.ear_closed_threshold, 0.18)

    def test_invalid_phone_device_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "phone device"):
            AppConfig.from_mapping({"phone": {"device": "tpu"}})


if __name__ == "__main__":
    unittest.main()
