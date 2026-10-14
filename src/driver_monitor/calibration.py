"""Short personal calibration for face-shape-dependent EAR and MAR values."""

from dataclasses import dataclass
from math import isfinite
from typing import List, Optional

from .config import CalibrationConfig


def _percentile(values: List[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("cannot calculate a percentile from no values")
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class CalibrationResult:
    open_eye_baseline: float
    closed_mouth_baseline: float
    ear_closed_threshold: float
    mar_open_threshold: float
    sample_count: int


class CalibrationSession:
    """Collect ordinary open-eye/closed-mouth frames before monitoring starts."""

    def __init__(self, config: CalibrationConfig):
        config.validate()
        self.config = config
        self._last_timestamp: Optional[float] = None
        self._last_sample_valid = False
        self._valid_seconds = 0.0
        self._ears: List[float] = []
        self._mars: List[float] = []
        self.result: Optional[CalibrationResult] = None

    @property
    def sample_count(self) -> int:
        return len(self._ears)

    def remaining_seconds(self, timestamp: float) -> float:
        # Only observed, valid intervals count; waiting off camera cannot finish
        # calibration. Keep the timestamp argument for the display API.
        return max(0.0, self.config.duration_seconds - self._valid_seconds)

    def update(
        self, timestamp: float, ear: Optional[float], mar: Optional[float]
    ) -> Optional[CalibrationResult]:
        if self.result is not None:
            return self.result
        timestamp = float(timestamp)
        if not isfinite(timestamp):
            raise ValueError("calibration timestamps must be finite")
        if self._last_timestamp is not None and timestamp <= self._last_timestamp:
            raise ValueError("calibration timestamps must be strictly monotonic")
        valid = (
            ear is not None and mar is not None
            and isfinite(ear) and isfinite(mar)
            and ear >= 0.0 and mar >= 0.0
        )
        if valid and self._last_sample_valid and self._last_timestamp is not None:
            self._valid_seconds += timestamp - self._last_timestamp
        self._last_timestamp = timestamp
        self._last_sample_valid = valid
        if not valid:
            return None
        self._ears.append(float(ear))
        self._mars.append(float(mar))

        enough_time = self._valid_seconds >= self.config.duration_seconds
        enough_samples = self.sample_count >= self.config.min_samples
        if not enough_time or not enough_samples:
            return None

        # Upper-eye and lower-mouth percentiles reduce the effect of accidental
        # blinks or a brief smile during calibration.
        open_eye_baseline = _percentile(self._ears, 0.75)
        closed_mouth_baseline = _percentile(self._mars, 0.25)
        ear_threshold = _clamp(
            open_eye_baseline * self.config.eye_closed_ratio,
            self.config.ear_threshold_min,
            self.config.ear_threshold_max,
        )
        mar_threshold = _clamp(
            closed_mouth_baseline * self.config.mouth_open_ratio,
            self.config.mar_threshold_min,
            self.config.mar_threshold_max,
        )
        self.result = CalibrationResult(
            open_eye_baseline=open_eye_baseline,
            closed_mouth_baseline=closed_mouth_baseline,
            ear_closed_threshold=ear_threshold,
            mar_open_threshold=mar_threshold,
            sample_count=self.sample_count,
        )
        return self.result
