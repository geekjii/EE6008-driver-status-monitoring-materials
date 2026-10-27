"""Reusable monitoring runtime shared by the simple and desktop interfaces."""

from collections import deque
from contextlib import suppress
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from time import monotonic
from typing import Any, Deque, Optional, Union

from .calibration import CalibrationResult, CalibrationSession
from .config import AppConfig
from .domain import FatigueSnapshot
from .events import JsonlEventWriter
from .face_landmarks import FaceSignals, MediaPipeFaceAnalyzer
from .fatigue_engine import FatigueEngine
from .phone_detection import PhoneDetector, PhoneObservation
from .session_recording import SessionRecorder


class FpsMeter:
    def __init__(self, window: int = 30):
        self._times: Deque[float] = deque(maxlen=window)

    def update(self, timestamp: float) -> float:
        self._times.append(timestamp)
        if len(self._times) < 2:
            return 0.0
        duration = self._times[-1] - self._times[0]
        return 0.0 if duration <= 0.0 else (len(self._times) - 1) / duration


@dataclass(frozen=True)
class RuntimeFrame:
    frame: Any
    signals: Optional[FaceSignals]
    snapshot: Optional[FatigueSnapshot]
    fps: float
    calibration_remaining_seconds: float
    calibration_sample_count: int
    calibration_result: Optional[CalibrationResult]
    phone_observation: Optional[PhoneObservation] = None
    timestamp: Optional[float] = None

    @property
    def calibrating(self) -> bool:
        return self.snapshot is None


def _open_capture(source: Union[int, str], config: AppConfig):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is not installed. Activate .venv and run "
            "'python -m pip install -e .'."
        ) from exc

    capture = cv2.VideoCapture(source)
    if isinstance(source, int):
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.camera.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.camera.height)
    if not capture.isOpened():
        capture.release()
        if isinstance(source, int):
            raise RuntimeError(
                "Cannot open camera {}. Check that no other app is using it and grant "
                "camera permission to Codex or Terminal. On macOS: System Settings > "
                "Privacy & Security > Camera. You can also test a file with --video."
                .format(source)
            )
        raise RuntimeError("Cannot open video source: {}".format(source))
    return capture


class MonitorRuntime:
    """Own the camera, detector, calibration, risk engine, and event writer."""

    def __init__(
        self,
        config: AppConfig,
        project_root: Path,
        video_path: Optional[Path] = None,
        phone_detector: Optional[PhoneDetector] = None,
        session_recorder: Optional[SessionRecorder] = None,
    ):
        import cv2

        self.config = config
        self.project_root = project_root.resolve()
        self.video_path = video_path
        self.source: Union[int, str] = config.camera.index
        if video_path is not None:
            self.source = str(video_path.expanduser().resolve())

        model_path = Path(config.face.model_path)
        if not model_path.is_absolute():
            model_path = self.project_root / model_path
        events_path = Path(config.output.events_path)
        if not events_path.is_absolute():
            events_path = self.project_root / events_path

        self.writer = JsonlEventWriter(events_path) if config.output.write_events else None
        self.capture = None
        self.analyzer = None
        self._closed = False
        self.recorder = session_recorder
        try:
            if self.recorder is None and config.output.record_session:
                directory = Path(config.output.sessions_path)
                if not directory.is_absolute():
                    directory = self.project_root / directory
                self.recorder = SessionRecorder(directory, config, self.source)
            self.capture = _open_capture(self.source, config)
            self.analyzer = MediaPipeFaceAnalyzer(
                model_path=model_path,
                min_detection_confidence=config.face.min_detection_confidence,
                min_presence_confidence=config.face.min_presence_confidence,
                min_tracking_confidence=config.face.min_tracking_confidence,
            )

            self.phone_detector: Optional[PhoneDetector] = phone_detector
            self.phone_observation: Optional[PhoneObservation] = None
            self._last_phone_inference_timestamp = float("-inf")
            if config.phone.enabled and self.phone_detector is None:
                phone_model_path = Path(config.phone.model_path)
                if not phone_model_path.is_absolute():
                    phone_model_path = self.project_root / phone_model_path
                self.phone_detector = PhoneDetector(
                    model_path=phone_model_path,
                    confidence_threshold=config.phone.confidence_threshold,
                    image_size=config.phone.image_size,
                    device=config.phone.device,
                )
            self._cv2 = cv2
            self._start = monotonic()
            self._last_timestamp_ms = -1
            self._last_video_timestamp: Optional[float] = None
            self._video_fps = self.capture.get(cv2.CAP_PROP_FPS) if video_path else 0.0
            self._meter = FpsMeter()
            if self.recorder is not None:
                self.recorder.set_device(self.phone_detector.device if self.phone_detector is not None else None)
            self.reset_calibration()
        except Exception as exc:
            with suppress(Exception):
                self.close(status="error", error=str(exc))
            raise

    def reset_calibration(self) -> None:
        if self.recorder is not None:
            self.recorder.recalibrate()
        self.phone_observation = None
        self._last_phone_inference_timestamp = float("-inf")
        if self.config.calibration.enabled:
            self.calibration: Optional[CalibrationSession] = CalibrationSession(
                self.config.calibration
            )
            self.engine: Optional[FatigueEngine] = None
        else:
            self.calibration = None
            self.engine = FatigueEngine(self.config.fatigue)

    def read(self) -> Optional[RuntimeFrame]:
        if self._closed:
            return None
        try:
            return self._read_frame()
        except Exception as exc:
            # Preserve the original processing error after releasing both
            # resources, even if a backend also fails during cleanup.
            with suppress(Exception):
                self.close(status="error", error=str(exc))
            raise

    def _video_timestamp(self) -> float:
        timestamp = self.capture.get(self._cv2.CAP_PROP_POS_MSEC) / 1000.0
        previous = self._last_video_timestamp
        if not (
            isfinite(timestamp) and timestamp >= 0.0
            and (previous is None or timestamp > previous)
        ):
            if not isfinite(self._video_fps) or self._video_fps <= 0.0:
                raise RuntimeError(
                    "Video has no reliable timing: timestamps are missing or not "
                    "increasing and FPS is invalid. Re-encode it with valid timing."
                )
            timestamp = 0.0 if previous is None else previous + 1.0 / self._video_fps
        self._last_video_timestamp = timestamp
        return timestamp

    def _read_frame(self) -> Optional[RuntimeFrame]:
        ok, frame = self.capture.read()
        if not ok:
            self.close(status="completed" if self.video_path is not None else "stream_ended")
            return None

        now = monotonic()
        if self.video_path is None:
            timestamp = now - self._start
        else:
            timestamp = self._video_timestamp()
        timestamp_ms = max(self._last_timestamp_ms + 1, int(round(timestamp * 1000.0)))
        self._last_timestamp_ms = timestamp_ms

        if self.video_path is None and self.config.camera.mirror:
            frame = self._cv2.flip(frame, 1)
        rgb_frame = self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2RGB)
        signals = self.analyzer.analyze(rgb_frame, timestamp_ms)

        calibration_result = self.calibration.result if self.calibration is not None else None
        if self.calibration is not None and self.engine is None:
            calibration_signals = signals
            if signals is not None and (
                any(
                    angle is not None and not isfinite(angle)
                    for angle in (signals.pitch, signals.yaw, signals.roll)
                )
                or (signals.pitch is not None
                    and signals.pitch >= self.config.fatigue.head_down_warning_degrees)
                or (signals.yaw is not None
                    and abs(signals.yaw) >= self.config.fatigue.head_yaw_warning_degrees)
            ):
                calibration_signals = None
            calibration_result = self.calibration.update(
                timestamp=timestamp,
                ear=calibration_signals.ear if calibration_signals is not None else None,
                mar=calibration_signals.mar if calibration_signals is not None else None,
            )
            if calibration_result is not None:
                calibrated_config = replace(
                    self.config.fatigue,
                    ear_closed_threshold=calibration_result.ear_closed_threshold,
                    mar_open_threshold=calibration_result.mar_open_threshold,
                )
                self.engine = FatigueEngine(calibrated_config)
                print(
                    "Calibration complete: EAR threshold {:.3f}, MAR threshold {:.3f}"
                    .format(
                        calibration_result.ear_closed_threshold,
                        calibration_result.mar_open_threshold,
                    )
                )

        snapshot = None
        if self.engine is not None:
            if (
                self.phone_detector is not None
                and timestamp - self._last_phone_inference_timestamp
                >= self.config.phone.inference_interval_seconds
            ):
                self.phone_observation = self.phone_detector.detect(frame, timestamp)
                self._last_phone_inference_timestamp = timestamp
            snapshot = self.engine.update(
                timestamp=timestamp,
                face_detected=signals is not None,
                ear=signals.ear if signals is not None else None,
                mar=signals.mar if signals is not None else None,
                pitch=signals.pitch if signals is not None else None,
                yaw=signals.yaw if signals is not None else None,
                roll=signals.roll if signals is not None else None,
                phone_detected=(
                    self.phone_observation.detected
                    if self.phone_observation is not None
                    else False
                ),
                phone_confidence=(
                    self.phone_observation.confidence
                    if self.phone_observation is not None
                    and self.phone_observation.detected
                    else None
                ),
            )
            if self.writer is not None:
                self.writer.write_if_changed(snapshot)

        remaining = 0.0
        sample_count = 0
        if self.calibration is not None and self.engine is None:
            remaining = self.calibration.remaining_seconds(timestamp)
            sample_count = self.calibration.sample_count

        result = RuntimeFrame(
            frame=frame,
            signals=signals,
            snapshot=snapshot,
            fps=self._meter.update(now),
            calibration_remaining_seconds=remaining,
            calibration_sample_count=sample_count,
            calibration_result=calibration_result,
            phone_observation=self.phone_observation,
            timestamp=timestamp,
        )
        if self.recorder is not None:
            self.recorder.record(result, self.engine.config if self.engine is not None else self.config.fatigue)
        return result

    def close(self, status: str = "stopped", error: Optional[str] = None) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.capture is not None:
                self.capture.release()
        finally:
            try:
                if self.analyzer is not None:
                    self.analyzer.close()
            finally:
                if self.recorder is not None:
                    self.recorder.finish(status=status, error=error)

    def __enter__(self) -> "MonitorRuntime":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close(status="error" if exc_value else "stopped", error=str(exc_value) if exc_value else None)
