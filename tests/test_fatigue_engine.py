import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.config import FatigueConfig
from driver_monitor.domain import RiskLevel
from driver_monitor.fatigue_engine import FatigueEngine


class FatigueEngineTests(unittest.TestCase):
    def make_engine(self, **overrides):
        values = dict(
            eye_warning_seconds=1.5,
            eye_danger_seconds=3.0,
            yawn_min_seconds=1.0,
            yawn_warning_count=2,
            perclos_window_seconds=10.0,
            perclos_min_coverage_seconds=5.0,
            perclos_warning_threshold=0.20,
            perclos_danger_threshold=0.50,
            recovery_seconds=0.0,
        )
        values.update(overrides)
        return FatigueEngine(FatigueConfig(**values))

    def test_short_blink_does_not_warn(self):
        engine = self.make_engine()
        engine.update(0.0, True, 0.30, 0.20)
        engine.update(1.0, True, 0.10, 0.20)
        snapshot = engine.update(1.2, True, 0.30, 0.20)
        self.assertEqual(snapshot.state, RiskLevel.NORMAL)

    def test_sustained_closure_moves_from_warning_to_danger(self):
        engine = self.make_engine()
        engine.update(0.0, True, 0.10, 0.20)
        warning = engine.update(1.6, True, 0.10, 0.20)
        danger = engine.update(3.1, True, 0.10, 0.20)
        self.assertEqual(warning.state, RiskLevel.WARNING)
        self.assertIn("eyes_closed", warning.reasons)
        self.assertEqual(danger.state, RiskLevel.DANGER)
        self.assertIn("eyes_closed_too_long", danger.reasons)

    def test_one_yawn_is_registered_only_once(self):
        engine = self.make_engine(yawn_warning_count=5)
        engine.update(0.0, True, 0.30, 0.80)
        first = engine.update(1.1, True, 0.30, 0.80)
        second = engine.update(2.0, True, 0.30, 0.80)
        self.assertEqual(first.recent_yawn_count, 1)
        self.assertEqual(second.recent_yawn_count, 1)

    def test_perclos_is_time_weighted_not_frame_weighted(self):
        def simulate(step):
            engine = self.make_engine(
                eye_warning_seconds=100.0,
                eye_danger_seconds=101.0,
                perclos_danger_threshold=0.80,
            )
            snapshot = None
            step_count = int(round(10.0 / step))
            for step_index in range(step_count + 1):
                timestamp = step_index * step
                closed = 4.0 <= timestamp < 6.0
                snapshot = engine.update(
                    timestamp,
                    True,
                    0.10 if closed else 0.30,
                    0.20,
                )
            return snapshot

        slow = simulate(0.1)
        fast = simulate(1.0 / 30.0)
        self.assertAlmostEqual(slow.perclos, 0.20, places=2)
        self.assertAlmostEqual(fast.perclos, 0.20, places=2)
        self.assertAlmostEqual(slow.perclos, fast.perclos, places=2)

    def test_state_recovery_has_hold_time(self):
        engine = self.make_engine(recovery_seconds=2.0)
        engine.update(0.0, True, 0.10, 0.20)
        warning = engine.update(1.6, True, 0.10, 0.20)
        held = engine.update(1.7, True, 0.30, 0.20)
        recovered = engine.update(3.8, True, 0.30, 0.20)
        self.assertEqual(warning.state, RiskLevel.WARNING)
        self.assertEqual(held.state, RiskLevel.WARNING)
        self.assertIn("recovering", held.reasons)
        self.assertEqual(recovered.state, RiskLevel.NORMAL)

    def test_non_monotonic_timestamp_is_rejected(self):
        engine = self.make_engine()
        engine.update(2.0, True, 0.30, 0.20)
        with self.assertRaisesRegex(ValueError, "monotonic"):
            engine.update(1.0, True, 0.30, 0.20)

    def test_sustained_head_down_warns_without_counting_false_eye_closure(self):
        engine = self.make_engine(head_pose_warning_seconds=2.0)
        engine.update(0.0, True, 0.30, 0.20, pitch=20.0, yaw=0.0)
        snapshot = engine.update(2.1, True, 0.08, 0.20, pitch=20.0, yaw=0.0)

        self.assertEqual(snapshot.state, RiskLevel.WARNING)
        self.assertIn("head_down", snapshot.reasons)
        self.assertNotIn("eyes_closed", snapshot.reasons)
        self.assertEqual(snapshot.eye_closed_seconds, 0.0)
        self.assertEqual(snapshot.perclos_coverage_seconds, 0.0)

    def test_sustained_side_look_warns(self):
        engine = self.make_engine(head_pose_warning_seconds=2.0)
        engine.update(0.0, True, 0.30, 0.20, pitch=0.0, yaw=-35.0)
        snapshot = engine.update(2.1, True, 0.30, 0.20, pitch=0.0, yaw=-35.0)

        self.assertEqual(snapshot.state, RiskLevel.WARNING)
        self.assertIn("looking_away", snapshot.reasons)

    def test_phone_must_persist_before_warning(self):
        engine = self.make_engine(phone_warning_seconds=2.0)
        first = engine.update(
            0.0, True, 0.30, 0.20, phone_detected=True, phone_confidence=0.8
        )
        warning = engine.update(
            2.1, True, 0.30, 0.20, phone_detected=True, phone_confidence=0.8
        )

        self.assertEqual(first.state, RiskLevel.NORMAL)
        self.assertEqual(warning.state, RiskLevel.WARNING)
        self.assertIn("phone_detected", warning.reasons)
        self.assertAlmostEqual(warning.phone_seen_seconds, 2.1)

    def test_phone_timer_resets_when_phone_disappears(self):
        engine = self.make_engine(phone_warning_seconds=2.0)
        engine.update(0.0, True, 0.30, 0.20, phone_detected=True)
        engine.update(1.0, True, 0.30, 0.20, phone_detected=False)
        snapshot = engine.update(2.0, True, 0.30, 0.20, phone_detected=True)

        self.assertEqual(snapshot.state, RiskLevel.NORMAL)
        self.assertEqual(snapshot.phone_seen_seconds, 0.0)

    def test_invalid_or_duplicate_timestamps_do_not_change_state(self):
        engine = self.make_engine()
        engine.update(1.0, True, 0.10, 0.20)
        for timestamp in (float("nan"), float("inf"), 1.0):
            with self.subTest(timestamp=timestamp), self.assertRaises(ValueError):
                engine.update(timestamp, False, None, None)
        snapshot = engine.update(2.0, True, 0.10, 0.20)
        self.assertEqual(snapshot.eye_closed_seconds, 1.0)

    def test_unreliable_frame_does_not_extend_previous_eye_interval(self):
        cases = (
            dict(face_detected=False, ear=None, mar=None),
            dict(face_detected=True, ear=0.08, mar=0.8, pitch=20.0),
            dict(face_detected=True, ear=0.08, mar=0.8, yaw=35.0),
            dict(face_detected=True, ear=float("nan"), mar=0.2),
        )
        for values in cases:
            with self.subTest(values=values):
                engine = self.make_engine()
                engine.update(0.0, True, 0.10, 0.20)
                snapshot = engine.update(5.0, **values)
                self.assertEqual(snapshot.perclos_coverage_seconds, 0.0)
                self.assertNotIn("very_high_perclos", snapshot.reasons)
                returned = engine.update(6.0, True, 0.10, 0.20)
                self.assertEqual(returned.eye_closed_seconds, 0.0)
                self.assertEqual(returned.perclos_coverage_seconds, 0.0)
                resumed = engine.update(6.5, True, 0.10, 0.20)
                self.assertEqual(resumed.eye_closed_seconds, 0.5)
                self.assertEqual(resumed.perclos_coverage_seconds, 0.5)

    def test_lost_face_cannot_complete_recovery_from_danger(self):
        engine = self.make_engine(recovery_seconds=2.0, perclos_min_coverage_seconds=10.0)
        engine.update(0.0, True, 0.10, 0.20)
        engine.update(3.1, True, 0.10, 0.20)
        engine.update(3.2, True, 0.30, 0.20)
        missing = engine.update(4.0, False, None, None)
        self.assertEqual(missing.state, RiskLevel.DANGER)
        returned = engine.update(6.0, True, 0.30, 0.20)
        self.assertEqual(returned.state, RiskLevel.DANGER)
        recovered = engine.update(8.1, True, 0.30, 0.20)
        self.assertEqual(recovered.state, RiskLevel.NORMAL)


if __name__ == "__main__":
    unittest.main()
