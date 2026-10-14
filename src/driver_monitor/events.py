"""Append-only event logging for later review."""

import json
from pathlib import Path
from typing import Optional, Union

from .domain import FatigueSnapshot


class JsonlEventWriter:
    def __init__(self, path: Union[str, Path]):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._last_state: Optional[str] = None

    def write_if_changed(self, snapshot: FatigueSnapshot) -> bool:
        state_name = snapshot.state.name
        if state_name == self._last_state:
            return False
        payload = {
            "timestamp": round(snapshot.timestamp, 3),
            "state": state_name,
            "raw_state": snapshot.raw_state.name,
            "reasons": list(snapshot.reasons),
            "face_detected": snapshot.face_detected,
            "ear": snapshot.ear,
            "mar": snapshot.mar,
            "head_pitch": snapshot.head_pitch,
            "head_yaw": snapshot.head_yaw,
            "head_roll": snapshot.head_roll,
            "head_away_seconds": round(snapshot.head_away_seconds, 3),
            "phone_detected": snapshot.phone_detected,
            "phone_confidence": snapshot.phone_confidence,
            "phone_seen_seconds": round(snapshot.phone_seen_seconds, 3),
            "eye_closed_seconds": round(snapshot.eye_closed_seconds, 3),
            "mouth_open_seconds": round(snapshot.mouth_open_seconds, 3),
            "perclos": round(snapshot.perclos, 4),
            "perclos_coverage_seconds": round(snapshot.perclos_coverage_seconds, 3),
            "recent_yawn_count": snapshot.recent_yawn_count,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self._last_state = state_name
        return True
