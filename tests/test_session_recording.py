import csv
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.calibration import CalibrationResult
from driver_monitor.config import AppConfig
from driver_monitor.face_landmarks import FaceSignals
from driver_monitor.fatigue_engine import FatigueEngine
from driver_monitor.phone_detection import PhoneBox, PhoneObservation
from driver_monitor.runtime import RuntimeFrame
from driver_monitor.session_recording import COLUMNS, SessionRecorder


def make_frame(timestamp, config, engine=None, phone=None, face=True, yaw=0.0, ear=0.3, mar=0.2):
    signals = FaceSignals(ear=ear, mar=mar, landmarks=(), pitch=0.0, yaw=yaw, roll=0.0) if face else None
    snapshot = engine.update(timestamp, face, ear if face else None, mar if face else None,
                             pitch=0.0 if face else None, yaw=yaw if face else None,
                             phone_detected=phone.detected if phone else False,
                             phone_confidence=phone.confidence if phone and phone.detected else None) if engine else None
    return RuntimeFrame(None, signals, snapshot, 30.0, 5.0 if engine is None else 0,
                        1 if engine is None else 0, None, phone, timestamp)


class SessionRecordingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.config = AppConfig()
        self.recorder = SessionRecorder(Path(self.tmp.name), self.config, 0, "cpu")
        self.addCleanup(self.recorder.finish)
        self.recorder.recalibrate()

    def rows(self, exported):
        return [json.loads(line) for line in
                (Path(exported["directory"]) / "逐帧原始数据.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_all_frames_calibration_and_unavailable_values_are_preserved(self):
        self.recorder.record(make_frame(0, self.config), self.config.fatigue)
        self.recorder.record(make_frame(1, self.config, face=False), self.config.fatigue)
        engine = FatigueEngine(self.config.fatigue)
        frame = make_frame(5, self.config, engine)
        frame = replace(frame, calibration_result=CalibrationResult(0.3, 0.2, 0.216, 0.45, 30))
        self.recorder.record(frame, self.config.fatigue)
        self.recorder.finish()
        exported = self.recorder.info()["last_export"]
        rows = self.rows(exported)
        self.assertEqual(len(rows), 3)
        self.assertEqual([row["state"] for row in rows], ["CALIBRATING", "CALIBRATING", "NORMAL"])
        self.assertIsNone(rows[0]["phone_detected"])
        self.assertIsNone(rows[1]["ear"])
        self.assertEqual(rows[2]["perclos"], 0)
        self.assertFalse(rows[2]["perclos_ready"])
        with (Path(exported["directory"]) / "监测数据.csv").open(encoding="utf-8-sig", newline="") as handle:
            table = list(csv.reader(handle))
        self.assertEqual(len(table), 4)
        self.assertEqual(table[0], [label for _, label in COLUMNS])
        self.assertEqual(table[2][[key for key, _ in COLUMNS].index("ear")], "")
        with ZipFile(exported["archive_path"]) as archive:
            self.assertIn("监测报告.html", archive.namelist())
            self.assertIn("监测数据.csv", archive.namelist())
            self.assertIn("事件记录.csv", archive.namelist())

    def test_live_exports_are_immutable_and_finish_saves_new_complete_export(self):
        engine = FatigueEngine(self.config.fatigue)
        self.recorder.record(make_frame(0, self.config, engine), self.config.fatigue)
        first = self.recorder.export()
        self.recorder.record(make_frame(1, self.config, engine), self.config.fatigue)
        self.recorder.finish()
        final = self.recorder.info()["last_export"]
        self.assertNotEqual(first["directory"], final["directory"])
        self.assertEqual(len(self.rows(first)), 1)
        self.assertEqual(len(self.rows(final)), 2)
        self.assertEqual(first["status"], "recording")
        self.assertEqual(final["status"], "stopped")

    def test_cached_phone_results_do_not_count_as_new_inferences(self):
        engine = FatigueEngine(self.config.fatigue)
        phone = PhoneObservation(0, True, 0.76, (PhoneBox(1, 2, 3, 4, 0.76),), 23)
        for timestamp in (0, 0.1, 0.2):
            self.recorder.record(make_frame(timestamp, self.config, engine, phone), self.config.fatigue)
        exported = self.recorder.export()
        rows = self.rows(exported)
        self.assertEqual([row["phone_fresh"] for row in rows], [True, False, False])
        self.assertAlmostEqual(rows[-1]["phone_result_age_seconds"], 0.2)
        self.assertEqual(rows[0]["phone_boxes"][0]["confidence"], 0.76)
        summary = json.loads((Path(exported["directory"]) / "监测摘要.json").read_text())
        self.assertEqual(summary["fresh_phone_inferences"], 1)

    def test_time_statistics_use_input_intervals_not_frame_counts(self):
        engine = FatigueEngine(self.config.fatigue)
        for timestamp, ear in ((0, 0.1), (1.6, 0.1), (3.1, 0.1), (5.0, 0.3)):
            self.recorder.record(make_frame(timestamp, self.config, engine, ear=ear), self.config.fatigue)
        summary = json.loads((Path(self.recorder.export()["directory"]) / "监测摘要.json").read_text())
        self.assertAlmostEqual(summary["observed_seconds"], 5)
        self.assertAlmostEqual(summary["state_seconds"]["NORMAL"], 1.6)
        self.assertAlmostEqual(summary["state_seconds"]["WARNING"], 1.5)
        self.assertAlmostEqual(summary["state_seconds"]["DANGER"], 1.9)

    def test_reason_changes_are_recorded_even_if_risk_level_is_unchanged(self):
        engine = FatigueEngine(self.config.fatigue)
        for timestamp, yaw in ((0, 35), (2.1, 35), (2.2, 0)):
            self.recorder.record(make_frame(timestamp, self.config, engine, yaw=yaw), self.config.fatigue)
        exported = self.recorder.export()
        with (Path(exported["directory"]) / "事件记录.csv").open(encoding="utf-8-sig", newline="") as handle:
            events = list(csv.reader(handle))
        self.assertEqual(len(events), 4)
        self.assertIn("looking_away", events[2][3])
        self.assertIn("recovering", events[3][3])

    def test_recalibration_round_and_invalid_pose_are_visible(self):
        self.recorder.record(make_frame(0, self.config), self.config.fatigue)
        self.recorder.recalibrate()
        self.recorder.record(make_frame(1, self.config, yaw=35), self.config.fatigue)
        rows = self.rows(self.recorder.export())
        self.assertEqual([row["calibration_round"] for row in rows], [1, 2])
        self.assertFalse(rows[1]["calibration_valid"])

    def test_empty_session_and_repeated_finish_are_safe(self):
        with self.assertRaisesRegex(ValueError, "可导出"):
            self.recorder.export()
        self.recorder.finish(status="error", error="camera unavailable")
        self.recorder.finish()
        self.assertIsNone(self.recorder.info()["last_export"])
        information = json.loads((self.recorder.directory / "会话信息.json").read_text())
        self.assertEqual(information["error"], "camera unavailable")

    def test_failed_report_preserves_raw_data_and_can_be_retried(self):
        self.recorder.record(make_frame(0, self.config), self.config.fatigue)
        with patch("driver_monitor.session_recording.ZipFile", side_effect=OSError("disk full")):
            self.recorder.finish()
        self.assertEqual(self.recorder.info()["export_error"], "disk full")
        self.assertTrue((self.recorder.directory / "逐帧原始数据.jsonl").is_file())
        self.assertEqual(self.recorder.export()["frames"], 1)
        self.assertIsNone(self.recorder.info()["export_error"])

    def test_timestamp_errors_are_rejected_without_adding_records(self):
        self.recorder.record(make_frame(1, self.config), self.config.fatigue)
        for timestamp in (1, 0, float("nan")):
            with self.assertRaises(ValueError):
                self.recorder.record(make_frame(timestamp, self.config), self.config.fatigue)
        self.assertEqual(self.recorder.info()["frames"], 1)


if __name__ == "__main__":
    unittest.main()
