import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.calibration import CalibrationSession
from driver_monitor.config import CalibrationConfig


class CalibrationTests(unittest.TestCase):
    def test_waits_for_time_and_samples(self):
        session = CalibrationSession(
            CalibrationConfig(duration_seconds=2.0, min_samples=3)
        )
        self.assertIsNone(session.update(0.0, 0.20, 0.25))
        self.assertIsNone(session.update(1.0, 0.21, 0.24))
        result = session.update(2.0, 0.22, 0.26)
        self.assertIsNotNone(result)
        self.assertEqual(result.sample_count, 3)

    def test_personal_thresholds_are_derived_and_clamped(self):
        session = CalibrationSession(
            CalibrationConfig(duration_seconds=1.0, min_samples=2)
        )
        session.update(0.0, 0.16, 0.28)
        result = session.update(1.0, 0.17, 0.27)
        self.assertAlmostEqual(result.ear_closed_threshold, 0.1675 * 0.72)
        self.assertAlmostEqual(result.mar_open_threshold, 0.2725 * 2.2)

    def test_missing_face_does_not_start_calibration(self):
        session = CalibrationSession(CalibrationConfig(duration_seconds=1.0))
        self.assertIsNone(session.update(10.0, None, None))
        self.assertEqual(session.remaining_seconds(20.0), 1.0)

    def test_missing_face_pauses_valid_calibration_time(self):
        session = CalibrationSession(CalibrationConfig(duration_seconds=2.0, min_samples=3))
        session.update(0.0, 0.30, 0.20)
        session.update(0.5, 0.30, 0.20)
        session.update(1.0, None, None)
        self.assertEqual(session.remaining_seconds(10.0), 1.5)
        self.assertIsNone(session.update(10.0, 0.30, 0.20))
        self.assertEqual(session.remaining_seconds(10.0), 1.5)
        self.assertIsNone(session.update(11.0, 0.30, 0.20))
        self.assertIsNotNone(session.update(11.5, 0.30, 0.20))

    def test_invalid_measurements_do_not_count_as_samples(self):
        for ear, mar in ((float("nan"), 0.2), (0.3, float("inf")), (-0.1, 0.2)):
            with self.subTest(ear=ear, mar=mar):
                session = CalibrationSession(CalibrationConfig())
                self.assertIsNone(session.update(0.0, ear, mar))
                self.assertEqual(session.sample_count, 0)

    def test_invalid_or_duplicate_timestamps_are_rejected_without_adding_samples(self):
        session = CalibrationSession(CalibrationConfig())
        session.update(1.0, 0.3, 0.2)
        for timestamp in (float("nan"), float("inf"), 1.0, 0.0):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                session.update(timestamp, 0.3, 0.2)
        self.assertEqual(session.sample_count, 1)


if __name__ == "__main__":
    unittest.main()
