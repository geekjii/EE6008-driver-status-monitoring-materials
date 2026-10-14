"""Simple OpenCV preview application."""

from pathlib import Path
from typing import Optional

from .config import AppConfig
from .runtime import MonitorRuntime


def run_monitor(
    config: AppConfig,
    project_root: Path,
    video_path: Optional[Path] = None,
    show_window: Optional[bool] = None,
) -> None:
    """Run until the camera/video ends or the user presses Q/Escape."""

    import cv2

    display = config.output.show_window if show_window is None else show_window
    window_name = "EE6008 Driver Fatigue Monitor"

    with MonitorRuntime(config, project_root, video_path) as runtime:
        while True:
            result = runtime.read()
            if result is None:
                break

            if display:
                if result.calibrating:
                    from .overlay import draw_calibration_overlay

                    draw_calibration_overlay(
                        frame=result.frame,
                        signals=result.signals,
                        remaining_seconds=result.calibration_remaining_seconds,
                        sample_count=result.calibration_sample_count,
                        fps=result.fps,
                    )
                else:
                    from .overlay import draw_overlay

                    draw_overlay(
                        result.frame,
                        result.snapshot,
                        result.signals,
                        result.fps,
                    )
                cv2.imshow(window_name, result.frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break

    if display:
        cv2.destroyAllWindows()
