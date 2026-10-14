"""Frame-rate-independent fatigue state engine."""

from collections import deque
from math import isfinite
from typing import Deque, List, Optional, Tuple

from .config import FatigueConfig
from .domain import FatigueSnapshot, RiskLevel


Segment = Tuple[float, float, bool]


class FatigueEngine:
    """Fuse eye and mouth signals using real timestamps.

    PERCLOS is time-weighted.  Ten and thirty frames per second therefore give
    nearly the same answer for the same physical eye-closure schedule.
    """

    def __init__(self, config: FatigueConfig):
        config.validate()
        self.config = config
        self._last_timestamp: Optional[float] = None
        self._last_eye_closed: Optional[bool] = None
        self._eye_closed_since: Optional[float] = None
        self._mouth_open_since: Optional[float] = None
        self._no_face_since: Optional[float] = None
        self._head_away_since: Optional[float] = None
        self._phone_seen_since: Optional[float] = None
        self._yawn_registered = False
        self._yawn_events: Deque[float] = deque()
        self._eye_segments: Deque[Segment] = deque()
        self._state = RiskLevel.NORMAL
        self._recovery_since: Optional[float] = None

    def update(
        self,
        timestamp: float,
        face_detected: bool,
        ear: Optional[float],
        mar: Optional[float],
        pitch: Optional[float] = None,
        yaw: Optional[float] = None,
        roll: Optional[float] = None,
        phone_detected: bool = False,
        phone_confidence: Optional[float] = None,
    ) -> FatigueSnapshot:
        timestamp = float(timestamp)
        if not isfinite(timestamp):
            raise ValueError("timestamps must be finite")
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("timestamps must be strictly monotonic")

        if ear is not None and (not isfinite(ear) or ear < 0.0):
            ear = None
        if mar is not None and (not isfinite(mar) or mar < 0.0):
            mar = None

        head_down = bool(
            face_detected
            and pitch is not None
            and pitch >= self.config.head_down_warning_degrees
        )
        looking_away = bool(
            face_detected
            and yaw is not None
            and abs(yaw) >= self.config.head_yaw_warning_degrees
        )
        head_away = head_down or looking_away
        pose_reliable_for_fatigue = not head_away and all(
            angle is None or isfinite(angle) for angle in (pitch, yaw, roll)
        )
        eye_reliable = face_detected and pose_reliable_for_fatigue and ear is not None
        if eye_reliable:
            # Require valid observations at both ends. A lost face or distorted
            # pose cannot extend the previous eye state across an unknown gap.
            self._append_previous_eye_interval(timestamp)

        if head_away:
            if self._head_away_since is None:
                self._head_away_since = timestamp
        else:
            self._head_away_since = None

        if phone_detected:
            if self._phone_seen_since is None:
                self._phone_seen_since = timestamp
        else:
            self._phone_seen_since = None

        eye_closed = bool(
            face_detected
            and pose_reliable_for_fatigue
            and ear is not None
            and ear < self.config.ear_closed_threshold
        )
        mouth_open = bool(
            face_detected
            and pose_reliable_for_fatigue
            and mar is not None
            and mar > self.config.mar_open_threshold
        )

        if face_detected:
            self._no_face_since = None
        elif self._no_face_since is None:
            self._no_face_since = timestamp

        if eye_closed:
            if self._eye_closed_since is None:
                self._eye_closed_since = timestamp
        else:
            self._eye_closed_since = None

        if mouth_open:
            if self._mouth_open_since is None:
                self._mouth_open_since = timestamp
            mouth_open_seconds = timestamp - self._mouth_open_since
            if mouth_open_seconds >= self.config.yawn_min_seconds and not self._yawn_registered:
                self._yawn_events.append(timestamp)
                self._yawn_registered = True
        else:
            self._mouth_open_since = None
            self._yawn_registered = False

        self._last_timestamp = timestamp
        self._last_eye_closed = (
            eye_closed
            if eye_reliable
            else None
        )
        self._prune_windows(timestamp)

        eye_closed_seconds = (
            timestamp - self._eye_closed_since if self._eye_closed_since is not None else 0.0
        )
        mouth_open_seconds = (
            timestamp - self._mouth_open_since if self._mouth_open_since is not None else 0.0
        )
        no_face_seconds = timestamp - self._no_face_since if self._no_face_since is not None else 0.0
        head_away_seconds = (
            timestamp - self._head_away_since
            if self._head_away_since is not None
            else 0.0
        )
        phone_seen_seconds = (
            timestamp - self._phone_seen_since
            if self._phone_seen_since is not None
            else 0.0
        )
        perclos, coverage = self._calculate_perclos(timestamp)

        raw_state, reasons = self._classify(
            face_detected=face_detected,
            eye_closed_seconds=eye_closed_seconds,
            mouth_open_seconds=mouth_open_seconds,
            no_face_seconds=no_face_seconds,
            perclos=perclos,
            coverage=coverage,
            head_down=head_down,
            looking_away=looking_away,
            head_away_seconds=head_away_seconds,
            phone_detected=phone_detected,
            phone_seen_seconds=phone_seen_seconds,
        )
        state, held_for_recovery = self._stabilize(
            raw_state, timestamp, can_recover=eye_reliable and mar is not None
        )
        if held_for_recovery:
            reasons.append("recovering")

        return FatigueSnapshot(
            timestamp=timestamp,
            state=state,
            raw_state=raw_state,
            reasons=tuple(reasons),
            face_detected=face_detected,
            ear=ear,
            mar=mar,
            eye_closed_seconds=eye_closed_seconds,
            mouth_open_seconds=mouth_open_seconds,
            perclos=perclos,
            perclos_coverage_seconds=coverage,
            recent_yawn_count=len(self._yawn_events),
            head_pitch=pitch,
            head_yaw=yaw,
            head_roll=roll,
            head_away_seconds=head_away_seconds,
            phone_detected=phone_detected,
            phone_confidence=phone_confidence,
            phone_seen_seconds=phone_seen_seconds,
        )

    def _append_previous_eye_interval(self, timestamp: float) -> None:
        if (
            self._last_timestamp is not None
            and timestamp > self._last_timestamp
            and self._last_eye_closed is not None
        ):
            self._eye_segments.append(
                (self._last_timestamp, timestamp, self._last_eye_closed)
            )

    def _prune_windows(self, timestamp: float) -> None:
        eye_cutoff = timestamp - self.config.perclos_window_seconds
        while self._eye_segments and self._eye_segments[0][1] <= eye_cutoff:
            self._eye_segments.popleft()

        yawn_cutoff = timestamp - self.config.yawn_window_seconds
        while self._yawn_events and self._yawn_events[0] < yawn_cutoff:
            self._yawn_events.popleft()

    def _calculate_perclos(self, timestamp: float) -> Tuple[float, float]:
        window_start = timestamp - self.config.perclos_window_seconds
        coverage = 0.0
        closed = 0.0
        for start, end, was_closed in self._eye_segments:
            overlap_start = max(start, window_start)
            overlap_end = min(end, timestamp)
            duration = max(0.0, overlap_end - overlap_start)
            coverage += duration
            if was_closed:
                closed += duration
        if coverage <= 1e-9:
            return 0.0, 0.0
        return closed / coverage, coverage

    def _classify(
        self,
        face_detected: bool,
        eye_closed_seconds: float,
        mouth_open_seconds: float,
        no_face_seconds: float,
        perclos: float,
        coverage: float,
        head_down: bool,
        looking_away: bool,
        head_away_seconds: float,
        phone_detected: bool,
        phone_seen_seconds: float,
    ) -> Tuple[RiskLevel, List[str]]:
        warning_reasons: List[str] = []
        danger_reasons: List[str] = []

        if not face_detected and no_face_seconds >= self.config.no_face_warning_seconds:
            warning_reasons.append("face_missing")
        if eye_closed_seconds >= self.config.eye_warning_seconds:
            warning_reasons.append("eyes_closed")
        if eye_closed_seconds >= self.config.eye_danger_seconds:
            danger_reasons.append("eyes_closed_too_long")
        if mouth_open_seconds >= self.config.yawn_min_seconds:
            warning_reasons.append("yawning")
        if len(self._yawn_events) >= self.config.yawn_warning_count:
            warning_reasons.append("repeated_yawning")
        if head_away_seconds >= self.config.head_pose_warning_seconds:
            if head_down:
                warning_reasons.append("head_down")
            if looking_away:
                warning_reasons.append("looking_away")
        if phone_detected and phone_seen_seconds >= self.config.phone_warning_seconds:
            warning_reasons.append("phone_detected")

        enough_coverage = coverage >= self.config.perclos_min_coverage_seconds
        if enough_coverage and perclos >= self.config.perclos_warning_threshold:
            warning_reasons.append("high_perclos")
        if enough_coverage and perclos >= self.config.perclos_danger_threshold:
            danger_reasons.append("very_high_perclos")

        if danger_reasons:
            return RiskLevel.DANGER, danger_reasons + warning_reasons
        if warning_reasons:
            return RiskLevel.WARNING, warning_reasons
        return RiskLevel.NORMAL, []

    def _stabilize(
        self, raw_state: RiskLevel, timestamp: float, can_recover: bool = True
    ) -> Tuple[RiskLevel, bool]:
        if raw_state >= self._state:
            self._state = raw_state
            self._recovery_since = None
            return self._state, False

        if not can_recover:
            self._recovery_since = None
            return self._state, True

        if self.config.recovery_seconds == 0.0:
            self._state = raw_state
            self._recovery_since = None
            return self._state, False

        if self._recovery_since is None:
            self._recovery_since = timestamp
        if timestamp - self._recovery_since >= self.config.recovery_seconds:
            self._state = raw_state
            self._recovery_since = None
            return self._state, False
        return self._state, True
