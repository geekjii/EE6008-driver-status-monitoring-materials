import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.phone_detection import (
    build_phone_observation,
    find_phone_class_id,
)


class PhoneDetectionTests(unittest.TestCase):
    def test_finds_phone_class_without_hard_coded_coco_index(self):
        self.assertEqual(find_phone_class_id({0: "person", 67: "cell phone"}), 67)
        self.assertEqual(find_phone_class_id(["person", "mobile phone"]), 1)

    def test_missing_phone_class_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "phone class"):
            find_phone_class_id({0: "person", 1: "car"})

    def test_observation_keeps_boxes_and_highest_confidence(self):
        observation = build_phone_observation(
            timestamp=1.5,
            xyxy=((1, 2, 3, 4), (5, 6, 7, 8)),
            confidences=(0.55, 0.81),
            inference_ms=42.0,
        )

        self.assertTrue(observation.detected)
        self.assertAlmostEqual(observation.confidence, 0.81)
        self.assertEqual(len(observation.boxes), 2)

    def test_empty_detection_is_explicit(self):
        observation = build_phone_observation(1.0, (), (), 10.0)
        self.assertFalse(observation.detected)
        self.assertEqual(observation.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()

