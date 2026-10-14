"""Small domain objects shared by the monitoring pipeline."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Tuple


class RiskLevel(IntEnum):
    """Ordered risk levels so higher values mean more urgent risk."""

    NORMAL = 0
    WARNING = 1
    DANGER = 2


@dataclass(frozen=True)
class FatigueSnapshot:
    """One explainable result produced for a video frame."""

    timestamp: float
    state: RiskLevel
    raw_state: RiskLevel
    reasons: Tuple[str, ...]
    face_detected: bool
    ear: Optional[float]
    mar: Optional[float]
    eye_closed_seconds: float
    mouth_open_seconds: float
    perclos: float
    perclos_coverage_seconds: float
    recent_yawn_count: int
    head_pitch: Optional[float]
    head_yaw: Optional[float]
    head_roll: Optional[float]
    head_away_seconds: float
    phone_detected: bool
    phone_confidence: Optional[float]
    phone_seen_seconds: float
