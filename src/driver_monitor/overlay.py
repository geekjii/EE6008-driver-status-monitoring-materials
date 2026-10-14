"""OpenCV display helpers for the local monitoring window."""

from typing import Any, Iterable, Optional

from .domain import FatigueSnapshot, RiskLevel
from .face_landmarks import DISPLAY_LANDMARK_INDICES, FaceSignals
from .phone_detection import PhoneObservation


STATE_COLORS = {
    RiskLevel.NORMAL: (70, 190, 70),
    RiskLevel.WARNING: (0, 190, 255),
    RiskLevel.DANGER: (40, 40, 230),
}

REASON_LABELS = {
    "face_missing": "FACE MISSING",
    "eyes_closed": "EYES CLOSED",
    "eyes_closed_too_long": "LONG EYE CLOSURE",
    "yawning": "YAWNING",
    "repeated_yawning": "REPEATED YAWNS",
    "high_perclos": "HIGH PERCLOS",
    "very_high_perclos": "VERY HIGH PERCLOS",
    "recovering": "RECOVERING",
    "head_down": "HEAD DOWN",
    "looking_away": "LOOKING AWAY",
    "phone_detected": "PHONE DETECTED",
}


def draw_face_landmarks(frame: Any, signals: Optional[FaceSignals], color: Any) -> Any:
    """Draw only selected eye and mouth points for use inside richer UIs."""

    if signals is None:
        return frame
    import cv2

    height, width = frame.shape[:2]
    for index in DISPLAY_LANDMARK_INDICES:
        landmark = signals.landmarks[index]
        cv2.circle(
            frame,
            (int(landmark.x * width), int(landmark.y * height)),
            3,
            color,
            -1,
            cv2.LINE_AA,
        )
    return frame


def draw_phone_boxes(
    frame: Any, observation: Optional[PhoneObservation]
) -> Any:
    """Draw YOLO phone boxes without changing the detector result."""

    if observation is None or not observation.detected:
        return frame
    import cv2

    color = (28, 78, 225)
    for box in observation.boxes:
        point1 = (int(box.x1), int(box.y1))
        point2 = (int(box.x2), int(box.y2))
        cv2.rectangle(frame, point1, point2, color, 3, cv2.LINE_AA)
        label_y = max(24, int(box.y1) - 8)
        cv2.putText(
            frame,
            "PHONE {:.0%}".format(box.confidence),
            (int(box.x1), label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            color,
            2,
            cv2.LINE_AA,
        )
    return frame


def _format_optional(value: Optional[float]) -> str:
    return "--" if value is None else "{:.3f}".format(value)


def _draw_lines(frame: Any, lines: Iterable[str], color: Any) -> None:
    import cv2

    y = 38
    for index, line in enumerate(lines):
        scale = 0.82 if index == 0 else 0.58
        thickness = 2 if index == 0 else 1
        cv2.putText(
            frame,
            line,
            (18, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            thickness + 3,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            line,
            (18, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color if index == 0 else (245, 245, 245),
            thickness,
            cv2.LINE_AA,
        )
        y += 30


def draw_overlay(
    frame: Any,
    snapshot: FatigueSnapshot,
    signals: Optional[FaceSignals],
    fps: float,
) -> Any:
    """Draw an explainable state panel and selected facial landmarks in-place."""

    import cv2

    color = STATE_COLORS[snapshot.state]
    height, width = frame.shape[:2]
    cv2.rectangle(frame, (0, 0), (min(width, 430), min(height, 250)), (20, 20, 20), -1)
    cv2.rectangle(frame, (0, 0), (width - 1, height - 1), color, 5)

    reasons = ", ".join(REASON_LABELS.get(item, item) for item in snapshot.reasons)
    lines = [
        "STATE: {}".format(snapshot.state.name),
        "Face: {}    FPS: {:.1f}".format("YES" if snapshot.face_detected else "NO", fps),
        "EAR: {}    MAR: {}".format(
            _format_optional(snapshot.ear), _format_optional(snapshot.mar)
        ),
        "Pitch: {}  Yaw: {}  Roll: {}".format(
            _format_optional(snapshot.head_pitch),
            _format_optional(snapshot.head_yaw),
            _format_optional(snapshot.head_roll),
        ),
        "Eyes closed: {:.1f}s".format(snapshot.eye_closed_seconds),
        "PERCLOS: {:.1%} ({:.1f}s data)".format(
            snapshot.perclos, snapshot.perclos_coverage_seconds
        ),
        "Yawns / window: {}".format(snapshot.recent_yawn_count),
        "Phone: {} ({})".format(
            "YES" if snapshot.phone_detected else "NO",
            _format_optional(snapshot.phone_confidence),
        ),
        "Reason: {}".format(reasons or "--"),
        "Press Q or Esc to quit",
    ]
    _draw_lines(frame, lines, color)

    if signals is not None:
        for index in DISPLAY_LANDMARK_INDICES:
            landmark = signals.landmarks[index]
            point = (int(landmark.x * width), int(landmark.y * height))
            cv2.circle(frame, point, 2, color, -1, cv2.LINE_AA)
    return frame


def draw_calibration_overlay(
    frame: Any,
    signals: Optional[FaceSignals],
    remaining_seconds: float,
    sample_count: int,
    fps: float,
) -> Any:
    """Explain the short start-up calibration without emitting risk alerts."""

    import cv2

    height, width = frame.shape[:2]
    color = (255, 190, 60)
    cv2.rectangle(frame, (0, 0), (min(width, 560), min(height, 190)), (20, 20, 20), -1)
    cv2.rectangle(frame, (0, 0), (width - 1, height - 1), color, 5)
    lines = [
        "CALIBRATING: {:.1f}s".format(remaining_seconds),
        "Look at camera with eyes open and mouth relaxed",
        "Face: {}    Samples: {}    FPS: {:.1f}".format(
            "YES" if signals is not None else "NO", sample_count, fps
        ),
        "EAR: {}    MAR: {}".format(
            _format_optional(signals.ear if signals is not None else None),
            _format_optional(signals.mar if signals is not None else None),
        ),
        "Press Q or Esc to quit",
    ]
    _draw_lines(frame, lines, color)
    if signals is not None:
        for index in DISPLAY_LANDMARK_INDICES:
            landmark = signals.landmarks[index]
            cv2.circle(
                frame,
                (int(landmark.x * width), int(landmark.y * height)),
                2,
                color,
                -1,
                cv2.LINE_AA,
            )
    return frame
