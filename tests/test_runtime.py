import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.config import AppConfig, CalibrationConfig, OutputConfig, PhoneConfig
from driver_monitor.face_landmarks import FaceSignals
from driver_monitor.phone_detection import PhoneObservation
from driver_monitor.runtime import FpsMeter, MonitorRuntime, RuntimeFrame


class FakeCapture:
    """In-memory frames only: these tests never open a camera or video file."""

    def __init__(self, positions, fps):
        self.positions = positions
        self.fps = fps
        self.index = -1
        self.release = Mock()

    def read(self):
        self.index += 1
        return (True, "synthetic-frame") if self.index < len(self.positions) else (False, None)

    def get(self, property_id):
        return self.fps if property_id == "fps" else self.positions[self.index]


class RuntimeTests(unittest.TestCase):
    def make_runtime(self, positions, fps=10.0, config=None, analyzer=None, **kwargs):
        config = config or AppConfig(
            phone=PhoneConfig(enabled=False),
            calibration=CalibrationConfig(enabled=False),
            output=OutputConfig(write_events=False),
        )
        capture = FakeCapture(positions, fps)
        analyzer = analyzer or Mock(analyze=Mock(return_value=None))
        cv2 = SimpleNamespace(
            CAP_PROP_FPS="fps", CAP_PROP_POS_MSEC="position",
            COLOR_BGR2RGB="rgb", cvtColor=Mock(side_effect=lambda frame, color: frame),
        )
        for context in (
            patch.dict(sys.modules, {"cv2": cv2}),
            patch("driver_monitor.runtime._open_capture", return_value=capture),
            patch("driver_monitor.runtime.MediaPipeFaceAnalyzer", return_value=analyzer),
        ):
            context.start()
            self.addCleanup(context.stop)
        runtime = MonitorRuntime(config, Path.cwd(), video_path=Path("synthetic.avi"), **kwargs)
        self.addCleanup(runtime.close)
        return runtime, capture, analyzer

    def test_fps_meter_uses_elapsed_time(self):
        meter = FpsMeter()
        self.assertEqual(meter.update(10.0), 0.0)
        self.assertAlmostEqual(meter.update(10.1), 10.0)

    def test_frame_is_calibrating_until_snapshot_exists(self):
        frame = RuntimeFrame(
            frame=None,
            signals=None,
            snapshot=None,
            fps=0.0,
            calibration_remaining_seconds=5.0,
            calibration_sample_count=0,
            calibration_result=None,
        )
        self.assertTrue(frame.calibrating)

    def test_video_uses_increasing_media_positions_even_if_fps_is_invalid(self):
        for fps in (0.0, -1.0, float("nan"), float("inf"), 30.0):
            with self.subTest(fps=fps):
                runtime, capture, analyzer = self.make_runtime([0.0, 100.0, 350.0], fps)
                timestamps = [runtime.read().snapshot.timestamp for _ in range(3)]
                self.assertEqual(timestamps, [0.0, 0.1, 0.35])
                self.assertEqual([call.args[1] for call in analyzer.analyze.call_args_list], [0, 100, 350])
                self.assertIsNone(runtime.read())
                runtime.close()
                capture.release.assert_called_once()
                analyzer.close.assert_called_once()

    def test_bad_video_positions_fall_back_to_finite_fps(self):
        runtime, _, _ = self.make_runtime([0.0, 0.0, -1.0, float("nan"), float("inf"), 550.0])
        timestamps = [runtime.read().snapshot.timestamp for _ in range(6)]
        for actual, expected in zip(timestamps, (0.0, 0.1, 0.2, 0.3, 0.4, 0.55)):
            self.assertAlmostEqual(actual, expected)

    def test_missing_video_timing_fails_and_releases_resources(self):
        runtime, capture, analyzer = self.make_runtime([0.0, 0.0], fps=float("nan"))
        runtime.read()
        with self.assertRaisesRegex(RuntimeError, "no reliable timing"):
            runtime.read()
        capture.release.assert_called_once()
        analyzer.close.assert_called_once()
        self.assertIsNone(runtime.read())

    def test_mediapipe_millisecond_rounding_does_not_change_fatigue_time(self):
        runtime, _, analyzer = self.make_runtime([0.0, 0.2, 0.4])
        timestamps = [runtime.read().snapshot.timestamp for _ in range(3)]
        self.assertEqual(timestamps, [0.0, 0.0002, 0.0004])
        self.assertEqual([call.args[1] for call in analyzer.analyze.call_args_list], [0, 1, 2])

    def test_processing_errors_release_resources_without_masking_error(self):
        for stage in ("capture", "conversion", "face", "phone", "logging"):
            with self.subTest(stage=stage):
                phone = Mock(detect=Mock(return_value=None))
                runtime, capture, analyzer = self.make_runtime([0.0], phone_detector=phone)
                error = RuntimeError("{} failed".format(stage))
                if stage == "capture":
                    capture.read = Mock(side_effect=error)
                elif stage == "conversion":
                    runtime._cv2.cvtColor.side_effect = error
                elif stage == "face":
                    analyzer.analyze.side_effect = error
                elif stage == "phone":
                    phone.detect.side_effect = error
                else:
                    runtime.writer = Mock(write_if_changed=Mock(side_effect=error))
                capture.release.side_effect = RuntimeError("cleanup failed")
                with self.assertRaisesRegex(RuntimeError, "{} failed".format(stage)):
                    runtime.read()
                capture.release.assert_called_once()
                analyzer.close.assert_called_once()
                self.assertIsNone(runtime.read())

    def test_constructor_failure_releases_resources(self):
        runtime, capture, analyzer = self.make_runtime([0.0])
        runtime.close()
        capture.release.reset_mock()
        analyzer.close.reset_mock()
        for stage in ("face", "phone", "metadata", "calibration"):
            with self.subTest(stage=stage):
                config = runtime.config
                target = "driver_monitor.runtime.MediaPipeFaceAnalyzer"
                if stage == "phone":
                    config = replace(config, phone=PhoneConfig(enabled=True))
                    target = "driver_monitor.runtime.PhoneDetector"
                elif stage == "metadata":
                    target = "tests-unused-placeholder"
                elif stage == "calibration":
                    config = replace(config, calibration=CalibrationConfig(min_samples=0))
                if stage == "metadata":
                    context = patch.object(capture, "get", side_effect=RuntimeError("metadata failed"))
                elif stage == "calibration":
                    context = patch("driver_monitor.runtime.CalibrationSession", side_effect=ValueError("calibration failed"))
                else:
                    context = patch(target, side_effect=RuntimeError("{} failed".format(stage)))
                with context, self.assertRaisesRegex((RuntimeError, ValueError), "failed"):
                    MonitorRuntime(config, Path.cwd(), video_path=Path("synthetic.avi"))
                capture.release.assert_called_once()
                if stage != "face":
                    analyzer.close.assert_called_once()
                else:
                    analyzer.close.assert_not_called()
                capture.release.reset_mock()
                analyzer.close.reset_mock()

    def test_calibration_excludes_head_away_time_and_samples(self):
        config = AppConfig(
            phone=PhoneConfig(enabled=False),
            calibration=CalibrationConfig(duration_seconds=2.0, min_samples=3),
            output=OutputConfig(write_events=False),
        )
        forward = FaceSignals(ear=0.3, mar=0.2, landmarks=(), pitch=0.0, yaw=0.0)
        away = replace(forward, ear=0.08, mar=0.8, yaw=35.0)
        analyzer = Mock(analyze=Mock(side_effect=[forward, away, forward, forward, forward]))
        runtime, _, _ = self.make_runtime([0.0, 1000.0, 5000.0, 6000.0, 7000.0], config=config, analyzer=analyzer)
        runtime.read()
        runtime.read()
        resumed = runtime.read()
        self.assertTrue(resumed.calibrating)
        self.assertEqual(resumed.calibration_sample_count, 2)
        self.assertEqual(resumed.calibration_remaining_seconds, 2.0)
        runtime.read()
        calibrated = runtime.read()
        self.assertFalse(calibrated.calibrating)
        self.assertAlmostEqual(calibrated.calibration_result.open_eye_baseline, 0.3)

    def test_reset_calibration_discards_cached_phone_observation(self):
        observation = PhoneObservation(0.0, True, 0.8, (), 0.0)
        phone = Mock(detect=Mock(return_value=observation))
        runtime, _, _ = self.make_runtime([0.0, 100.0], phone_detector=phone)
        runtime.read()
        runtime.reset_calibration()
        self.assertIsNone(runtime.phone_observation)
        runtime.read()
        self.assertEqual(phone.detect.call_count, 2)


if __name__ == "__main__":
    unittest.main()
