"""Configuration loading and validation.

The dataclasses are deliberately independent from PyYAML.  This lets the core
logic and its tests run even before optional runtime packages are installed.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Union


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    width: int = 1280
    height: int = 720
    mirror: bool = True


@dataclass(frozen=True)
class FaceConfig:
    model_path: str = "models/face_landmarker.task"
    min_detection_confidence: float = 0.5
    min_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5


@dataclass(frozen=True)
class PhoneConfig:
    enabled: bool = True
    model_path: str = "models/yolo26n.pt"
    confidence_threshold: float = 0.35
    inference_interval_seconds: float = 0.35
    image_size: int = 416
    device: str = "auto"

    def validate(self) -> None:
        if not 0.0 < self.confidence_threshold <= 1.0:
            raise ValueError("phone confidence_threshold must be between 0 and 1")
        if self.inference_interval_seconds <= 0.0:
            raise ValueError("phone inference_interval_seconds must be positive")
        if self.image_size < 160:
            raise ValueError("phone image_size must be at least 160")
        device = str(self.device).strip().lower()
        if device == "gpu":
            device = "cuda"
        valid = device in {"auto", "cpu", "mps", "cuda"}
        valid = valid or device.isdigit()
        if device.startswith("cuda:"):
            valid = device.split(":", 1)[1].isdigit()
        if not valid:
            raise ValueError(
                "phone device must be auto, cpu, mps, cuda, or cuda:<index>"
            )


@dataclass(frozen=True)
class CalibrationConfig:
    enabled: bool = True
    duration_seconds: float = 5.0
    min_samples: int = 30
    eye_closed_ratio: float = 0.72
    mouth_open_ratio: float = 2.2
    ear_threshold_min: float = 0.08
    ear_threshold_max: float = 0.24
    mar_threshold_min: float = 0.45
    mar_threshold_max: float = 1.20

    def validate(self) -> None:
        if self.duration_seconds <= 0.0:
            raise ValueError("calibration duration_seconds must be positive")
        if self.min_samples < 1:
            raise ValueError("calibration min_samples must be at least 1")
        if not 0.0 < self.eye_closed_ratio < 1.0:
            raise ValueError("eye_closed_ratio must be between 0 and 1")
        if self.mouth_open_ratio <= 1.0:
            raise ValueError("mouth_open_ratio must exceed 1")
        if not 0.0 < self.ear_threshold_min < self.ear_threshold_max < 1.0:
            raise ValueError("invalid calibration EAR limits")
        if not 0.0 < self.mar_threshold_min < self.mar_threshold_max < 2.0:
            raise ValueError("invalid calibration MAR limits")


@dataclass(frozen=True)
class FatigueConfig:
    ear_closed_threshold: float = 0.21
    eye_warning_seconds: float = 1.5
    eye_danger_seconds: float = 3.0
    mar_open_threshold: float = 0.65
    yawn_min_seconds: float = 1.2
    yawn_window_seconds: float = 60.0
    yawn_warning_count: int = 2
    perclos_window_seconds: float = 60.0
    perclos_min_coverage_seconds: float = 10.0
    perclos_warning_threshold: float = 0.20
    perclos_danger_threshold: float = 0.35
    no_face_warning_seconds: float = 2.0
    head_yaw_warning_degrees: float = 25.0
    head_down_warning_degrees: float = 15.0
    head_pose_warning_seconds: float = 2.0
    phone_warning_seconds: float = 2.0
    recovery_seconds: float = 2.0

    def validate(self) -> None:
        if not 0.0 < self.ear_closed_threshold < 1.0:
            raise ValueError("ear_closed_threshold must be between 0 and 1")
        if not 0.0 < self.mar_open_threshold < 2.0:
            raise ValueError("mar_open_threshold must be between 0 and 2")
        if self.eye_warning_seconds < 0.0:
            raise ValueError("eye_warning_seconds cannot be negative")
        if self.eye_danger_seconds <= self.eye_warning_seconds:
            raise ValueError("eye_danger_seconds must exceed eye_warning_seconds")
        if self.yawn_min_seconds <= 0.0 or self.yawn_window_seconds <= 0.0:
            raise ValueError("yawn durations must be positive")
        if self.yawn_warning_count < 1:
            raise ValueError("yawn_warning_count must be at least 1")
        if self.perclos_window_seconds <= 0.0:
            raise ValueError("perclos_window_seconds must be positive")
        if not 0.0 <= self.perclos_warning_threshold < self.perclos_danger_threshold <= 1.0:
            raise ValueError("PERCLOS thresholds must satisfy 0 <= warning < danger <= 1")
        if self.perclos_min_coverage_seconds < 0.0:
            raise ValueError("perclos_min_coverage_seconds cannot be negative")
        if self.recovery_seconds < 0.0 or self.no_face_warning_seconds < 0.0:
            raise ValueError("recovery and no-face durations cannot be negative")
        if not 0.0 < self.head_yaw_warning_degrees < 90.0:
            raise ValueError("head_yaw_warning_degrees must be between 0 and 90")
        if not 0.0 < self.head_down_warning_degrees < 90.0:
            raise ValueError("head_down_warning_degrees must be between 0 and 90")
        if self.head_pose_warning_seconds < 0.0:
            raise ValueError("head_pose_warning_seconds cannot be negative")
        if self.phone_warning_seconds < 0.0:
            raise ValueError("phone_warning_seconds cannot be negative")


@dataclass(frozen=True)
class OutputConfig:
    show_window: bool = True
    write_events: bool = True
    events_path: str = "outputs/events.jsonl"
    record_session: bool = True
    sessions_path: str = "outputs/监测导出"


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    face: FaceConfig = field(default_factory=FaceConfig)
    phone: PhoneConfig = field(default_factory=PhoneConfig)
    calibration: CalibrationConfig = field(default_factory=CalibrationConfig)
    fatigue: FatigueConfig = field(default_factory=FatigueConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "AppConfig":
        config = cls(
            camera=CameraConfig(**dict(data.get("camera", {}))),
            face=FaceConfig(**dict(data.get("face", {}))),
            phone=PhoneConfig(**dict(data.get("phone", {}))),
            calibration=CalibrationConfig(**dict(data.get("calibration", {}))),
            fatigue=FatigueConfig(**dict(data.get("fatigue", {}))),
            output=OutputConfig(**dict(data.get("output", {}))),
        )
        config.calibration.validate()
        config.phone.validate()
        config.fatigue.validate()
        return config


def load_config(path: Union[str, Path]) -> AppConfig:
    """Load a YAML file while keeping PyYAML as a runtime-only dependency."""

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is not installed. Activate the project environment and run "
            "'python -m pip install -e .'."
        ) from exc

    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError("Configuration file not found: {}".format(config_path))
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, Mapping):
        raise ValueError("The configuration root must be a mapping")
    return AppConfig.from_mapping(data)
