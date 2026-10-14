import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.domain import FatigueSnapshot, RiskLevel
from driver_monitor.events import JsonlEventWriter


def snapshot(state):
    return FatigueSnapshot(
        timestamp=1.2345,
        state=state,
        raw_state=state,
        reasons=("eyes_closed",) if state != RiskLevel.NORMAL else (),
        face_detected=True,
        ear=0.18,
        mar=0.2,
        eye_closed_seconds=1.6,
        mouth_open_seconds=0.0,
        perclos=0.25,
        perclos_coverage_seconds=10.0,
        recent_yawn_count=0,
        head_pitch=1.0,
        head_yaw=2.0,
        head_roll=3.0,
        head_away_seconds=0.0,
        phone_detected=False,
        phone_confidence=None,
        phone_seen_seconds=0.0,
    )


class EventWriterTests(unittest.TestCase):
    def test_writes_only_state_changes_as_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "events.jsonl"
            writer = JsonlEventWriter(path)
            self.assertTrue(writer.write_if_changed(snapshot(RiskLevel.NORMAL)))
            self.assertFalse(writer.write_if_changed(snapshot(RiskLevel.NORMAL)))
            self.assertTrue(writer.write_if_changed(snapshot(RiskLevel.WARNING)))

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([row["state"] for row in rows], ["NORMAL", "WARNING"])
            self.assertEqual(rows[1]["reasons"], ["eyes_closed"])
            self.assertEqual(rows[1]["head_yaw"], 2.0)


if __name__ == "__main__":
    unittest.main()
