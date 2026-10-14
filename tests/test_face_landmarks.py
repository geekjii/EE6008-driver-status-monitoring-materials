import sys
import unittest
from math import cos, radians, sin
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.face_landmarks import (
    LEFT_EYE_INDICES,
    MOUTH_INDICES,
    RIGHT_EYE_INDICES,
    extract_face_signals,
    rotation_matrix_to_euler_degrees,
)


def point(x, y):
    return SimpleNamespace(x=x, y=y)


class FaceLandmarkSignalTests(unittest.TestCase):
    def test_rotation_matrix_reports_head_angles_in_degrees(self):
        angle = radians(20.0)
        yaw_matrix = [
            [cos(angle), 0.0, sin(angle)],
            [0.0, 1.0, 0.0],
            [-sin(angle), 0.0, cos(angle)],
        ]

        pitch, yaw, roll = rotation_matrix_to_euler_degrees(yaw_matrix)

        self.assertAlmostEqual(pitch, 0.0, places=5)
        self.assertAlmostEqual(yaw, 20.0, places=5)
        self.assertAlmostEqual(roll, 0.0, places=5)

    def test_extracts_average_ear_and_mar(self):
        landmarks = [point(0.0, 0.0) for _ in range(478)]
        eye_points = [
            point(0.0, 0.0),
            point(0.25, -0.2),
            point(0.75, -0.2),
            point(1.0, 0.0),
            point(0.75, 0.2),
            point(0.25, 0.2),
        ]
        mouth_points = [
            point(0.0, 0.0),
            point(0.25, -0.3),
            point(0.50, -0.4),
            point(0.75, -0.3),
            point(1.0, 0.0),
            point(0.75, 0.3),
            point(0.50, 0.4),
            point(0.25, 0.3),
        ]
        for index, value in zip(LEFT_EYE_INDICES, eye_points):
            landmarks[index] = value
        for index, value in zip(RIGHT_EYE_INDICES, eye_points):
            landmarks[index] = value
        for index, value in zip(MOUTH_INDICES, mouth_points):
            landmarks[index] = value

        signals = extract_face_signals(landmarks)

        self.assertAlmostEqual(signals.ear, 0.4)
        self.assertAlmostEqual(signals.mar, 2.0 / 3.0)

    def test_rejects_incomplete_landmark_result(self):
        with self.assertRaisesRegex(ValueError, "at least"):
            extract_face_signals([point(0.0, 0.0)] * 100)

    def test_ratios_are_independent_of_frame_aspect_ratio(self):
        square = [point(0.0, 0.0) for _ in range(478)]
        wide = [point(0.0, 0.0) for _ in range(478)]
        eye_points = [
            (0.0, 0.0),
            (0.25, -0.2),
            (0.75, -0.2),
            (1.0, 0.0),
            (0.75, 0.2),
            (0.25, 0.2),
        ]
        mouth_points = [
            (0.0, 0.0),
            (0.25, -0.3),
            (0.50, -0.4),
            (0.75, -0.3),
            (1.0, 0.0),
            (0.75, 0.3),
            (0.50, 0.4),
            (0.25, 0.3),
        ]
        for indices, values in (
            (LEFT_EYE_INDICES, eye_points),
            (RIGHT_EYE_INDICES, eye_points),
            (MOUTH_INDICES, mouth_points),
        ):
            for index, (x, y) in zip(indices, values):
                square[index] = point(x, y)
                wide[index] = point(x / 2.0, y)

        square_signals = extract_face_signals(square, image_width=1, image_height=1)
        wide_signals = extract_face_signals(wide, image_width=2, image_height=1)

        self.assertAlmostEqual(square_signals.ear, wide_signals.ear)
        self.assertAlmostEqual(square_signals.mar, wide_signals.mar)


if __name__ == "__main__":
    unittest.main()
