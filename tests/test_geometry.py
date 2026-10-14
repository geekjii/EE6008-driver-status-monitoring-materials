import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.geometry import eye_aspect_ratio, mouth_aspect_ratio


class GeometryTests(unittest.TestCase):
    def test_open_eye_has_larger_ear_than_closed_eye(self):
        open_eye = [(0, 0), (1, -1), (3, -1), (4, 0), (3, 1), (1, 1)]
        closed_eye = [(0, 0), (1, -0.1), (3, -0.1), (4, 0), (3, 0.1), (1, 0.1)]
        self.assertGreater(eye_aspect_ratio(open_eye), eye_aspect_ratio(closed_eye))
        self.assertAlmostEqual(eye_aspect_ratio(open_eye), 0.5)
        self.assertAlmostEqual(eye_aspect_ratio(closed_eye), 0.05)

    def test_open_mouth_has_larger_mar(self):
        open_mouth = [
            (0, 0), (1, -1), (2, -1.2), (3, -1),
            (4, 0), (3, 1), (2, 1.2), (1, 1),
        ]
        closed_mouth = [
            (0, 0), (1, -0.1), (2, -0.1), (3, -0.1),
            (4, 0), (3, 0.1), (2, 0.1), (1, 0.1),
        ]
        self.assertGreater(mouth_aspect_ratio(open_mouth), mouth_aspect_ratio(closed_mouth))

    def test_wrong_number_of_points_is_rejected(self):
        with self.assertRaises(ValueError):
            eye_aspect_ratio([(0, 0)] * 5)
        with self.assertRaises(ValueError):
            mouth_aspect_ratio([(0, 0)] * 7)


if __name__ == "__main__":
    unittest.main()

