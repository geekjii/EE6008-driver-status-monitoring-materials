"""Geometry functions for facial fatigue signals.

The functions accept any point objects exposing ``x`` and ``y`` attributes,
or ordinary ``(x, y)`` tuples.  This keeps MediaPipe outside the mathematics.
"""

from math import hypot
from typing import Any, Sequence, Tuple


def _xy(point: Any) -> Tuple[float, float]:
    if hasattr(point, "x") and hasattr(point, "y"):
        return float(point.x), float(point.y)
    return float(point[0]), float(point[1])


def distance(first: Any, second: Any) -> float:
    x1, y1 = _xy(first)
    x2, y2 = _xy(second)
    return hypot(x2 - x1, y2 - y1)


def eye_aspect_ratio(points: Sequence[Any]) -> float:
    """Calculate EAR from six ordered eye landmarks."""

    if len(points) != 6:
        raise ValueError("EAR requires exactly six eye landmarks")
    horizontal = distance(points[0], points[3])
    if horizontal <= 1e-9:
        raise ValueError("Eye horizontal distance is zero")
    vertical_a = distance(points[1], points[5])
    vertical_b = distance(points[2], points[4])
    return (vertical_a + vertical_b) / (2.0 * horizontal)


def mouth_aspect_ratio(points: Sequence[Any]) -> float:
    """Calculate MAR from eight ordered outer-mouth landmarks.

    Order: left corner, upper-left, upper-mid, upper-right, right corner,
    lower-right, lower-mid, lower-left.
    """

    if len(points) != 8:
        raise ValueError("MAR requires exactly eight mouth landmarks")
    horizontal = distance(points[0], points[4])
    if horizontal <= 1e-9:
        raise ValueError("Mouth horizontal distance is zero")
    vertical_a = distance(points[1], points[7])
    vertical_b = distance(points[2], points[6])
    vertical_c = distance(points[3], points[5])
    return (vertical_a + vertical_b + vertical_c) / (3.0 * horizontal)

