"""Local YOLO phone detection with a small, testable result model."""

from dataclasses import dataclass
import os
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence, Tuple, Union

from .devices import DeviceSelection, resolve_torch_device


PHONE_CLASS_NAMES = {"cell phone", "mobile phone", "phone"}


@dataclass(frozen=True)
class PhoneBox:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float


@dataclass(frozen=True)
class PhoneObservation:
    timestamp: float
    detected: bool
    confidence: float
    boxes: Tuple[PhoneBox, ...]
    inference_ms: float


def find_phone_class_id(names: Union[Mapping[int, str], Sequence[str]]) -> int:
    """Find the COCO phone class without relying on a hard-coded index."""

    items = names.items() if isinstance(names, Mapping) else enumerate(names)
    for class_id, name in items:
        if str(name).strip().lower() in PHONE_CLASS_NAMES:
            return int(class_id)
    raise ValueError("model does not contain a cell phone class")


def build_phone_observation(
    timestamp: float,
    xyxy: Sequence[Sequence[float]],
    confidences: Sequence[float],
    inference_ms: float,
) -> PhoneObservation:
    if len(xyxy) != len(confidences):
        raise ValueError("phone boxes and confidences must have the same length")
    boxes = tuple(
        PhoneBox(
            x1=float(coordinates[0]),
            y1=float(coordinates[1]),
            x2=float(coordinates[2]),
            y2=float(coordinates[3]),
            confidence=float(confidence),
        )
        for coordinates, confidence in zip(xyxy, confidences)
    )
    return PhoneObservation(
        timestamp=float(timestamp),
        detected=bool(boxes),
        confidence=max((box.confidence for box in boxes), default=0.0),
        boxes=boxes,
        inference_ms=float(inference_ms),
    )


class PhoneDetector:
    """Run a COCO-pretrained Ultralytics detector for only the phone class."""

    def __init__(
        self,
        model_path: Union[str, Path],
        confidence_threshold: float = 0.35,
        image_size: int = 416,
        device: str = "auto",
    ):
        path = Path(model_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                "YOLO phone model not found: {}. Run "
                "'python scripts/download_phone_model.py' first.".format(path)
            )
        cache_directory = path.parent.parent / ".cache" / "ultralytics"
        cache_directory.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("YOLO_CONFIG_DIR", str(cache_directory))
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is not installed. Activate .venv and run "
                "'python -m pip install -e \".[actions]\"'."
            ) from exc

        self.model = YOLO(str(path))
        self.phone_class_id = find_phone_class_id(self.model.names)
        self.confidence_threshold = float(confidence_threshold)
        self.image_size = int(image_size)
        self.device_selection: DeviceSelection = resolve_torch_device(device)
        self.device = self.device_selection.resolved

    def detect(self, frame: Any, timestamp: float) -> PhoneObservation:
        started = perf_counter()
        results = self.model.predict(
            source=frame,
            classes=[self.phone_class_id],
            conf=self.confidence_threshold,
            imgsz=self.image_size,
            device=self.device,
            verbose=False,
        )
        inference_ms = (perf_counter() - started) * 1000.0
        boxes = results[0].boxes if results else None
        if boxes is None or len(boxes) == 0:
            return build_phone_observation(timestamp, (), (), inference_ms)
        return build_phone_observation(
            timestamp=timestamp,
            xyxy=boxes.xyxy.detach().cpu().tolist(),
            confidences=boxes.conf.detach().cpu().tolist(),
            inference_ms=inference_ms,
        )
