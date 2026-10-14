"""MediaPipe face landmarks converted into simple fatigue signals.

MediaPipe is imported only when ``MediaPipeFaceAnalyzer`` is constructed.  The
geometry and state-machine tests can therefore run without camera dependencies.
"""

from dataclasses import dataclass
from math import atan2, degrees, sqrt
import os
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple, Union

from .geometry import eye_aspect_ratio, mouth_aspect_ratio


# Six points ordered for the EAR formula: two corners and two eyelid pairs.
LEFT_EYE_INDICES = (33, 160, 158, 133, 153, 144)
RIGHT_EYE_INDICES = (362, 385, 387, 263, 373, 380)

# Eight outer-lip points ordered clockwise for the MAR formula.
MOUTH_INDICES = (61, 39, 0, 269, 291, 405, 17, 181)
DISPLAY_LANDMARK_INDICES = tuple(
    dict.fromkeys(LEFT_EYE_INDICES + RIGHT_EYE_INDICES + MOUTH_INDICES)
)


@dataclass(frozen=True)
class FaceSignals:
    ear: float
    mar: float
    landmarks: Sequence[Any]
    pitch: Optional[float] = None
    yaw: Optional[float] = None
    roll: Optional[float] = None


def rotation_matrix_to_euler_degrees(matrix: Any) -> Tuple[float, float, float]:
    """Convert a 3x3 face rotation matrix into pitch, yaw and roll degrees."""

    if len(matrix) < 3 or any(len(row) < 3 for row in matrix[:3]):
        raise ValueError("rotation matrix must contain at least 3 rows and 3 columns")
    sy = sqrt(float(matrix[0][0]) ** 2 + float(matrix[1][0]) ** 2)
    singular = sy < 1e-6
    if not singular:
        pitch = atan2(float(matrix[2][1]), float(matrix[2][2]))
        yaw = atan2(-float(matrix[2][0]), sy)
        roll = atan2(float(matrix[1][0]), float(matrix[0][0]))
    else:
        pitch = atan2(-float(matrix[1][2]), float(matrix[1][1]))
        yaw = atan2(-float(matrix[2][0]), sy)
        roll = 0.0
    return degrees(pitch), degrees(yaw), degrees(roll)


def extract_face_signals(
    landmarks: Sequence[Any], image_width: float = 1.0, image_height: float = 1.0
) -> FaceSignals:
    """Calculate EAR and MAR using pixel-proportional coordinates.

    MediaPipe coordinates are normalized independently on each axis.  Scaling
    them by the actual frame dimensions prevents a 16:9 camera from producing
    different ratios than a portrait video of the same face.
    """

    required_index = max(DISPLAY_LANDMARK_INDICES)
    if len(landmarks) <= required_index:
        raise ValueError(
            "Face landmark result has {} points; at least {} are required".format(
                len(landmarks), required_index + 1
            )
        )
    if image_width <= 0.0 or image_height <= 0.0:
        raise ValueError("image dimensions must be positive")

    def scaled_points(indices: Sequence[int]):
        return [
            (landmarks[index].x * image_width, landmarks[index].y * image_height)
            for index in indices
        ]

    left_ear = eye_aspect_ratio(scaled_points(LEFT_EYE_INDICES))
    right_ear = eye_aspect_ratio(scaled_points(RIGHT_EYE_INDICES))
    mar = mouth_aspect_ratio(scaled_points(MOUTH_INDICES))
    return FaceSignals(
        ear=(left_ear + right_ear) / 2.0,
        mar=mar,
        landmarks=landmarks,
    )


class MediaPipeFaceAnalyzer:
    """Synchronous video-mode analyzer suitable for camera and video frames."""

    def __init__(
        self,
        model_path: Union[str, Path],
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ):
        path = Path(model_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(
                "MediaPipe face model not found: {}. Run "
                "'python scripts/download_face_model.py' first.".format(path)
            )
        cache_directory = path.parent.parent / ".cache" / "matplotlib"
        cache_directory.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(cache_directory))
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is not installed. Activate .venv and run "
                "'python -m pip install -e .'."
            ) from exc

        self._mp = mp
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(
                model_asset_path=str(path),
                delegate=mp.tasks.BaseOptions.Delegate.CPU,
            ),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=min_detection_confidence,
            min_face_presence_confidence=min_presence_confidence,
            min_tracking_confidence=min_tracking_confidence,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1

    def analyze(self, rgb_frame: Any, timestamp_ms: int) -> Optional[FaceSignals]:
        timestamp_ms = int(timestamp_ms)
        if timestamp_ms <= self._last_timestamp_ms:
            raise ValueError("MediaPipe timestamps must be strictly increasing")
        self._last_timestamp_ms = timestamp_ms
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=rgb_frame,
        )
        result = self._landmarker.detect_for_video(image, timestamp_ms)
        if not result.face_landmarks:
            return None
        height, width = rgb_frame.shape[:2]
        signals = extract_face_signals(
            result.face_landmarks[0], image_width=width, image_height=height
        )
        matrices = getattr(result, "facial_transformation_matrixes", None)
        if not matrices:
            return signals
        pitch, yaw, roll = rotation_matrix_to_euler_degrees(matrices[0])
        return FaceSignals(
            ear=signals.ear,
            mar=signals.mar,
            landmarks=signals.landmarks,
            pitch=pitch,
            yaw=yaw,
            roll=roll,
        )

    def close(self) -> None:
        self._landmarker.close()

    def __enter__(self) -> "MediaPipeFaceAnalyzer":
        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        self.close()
