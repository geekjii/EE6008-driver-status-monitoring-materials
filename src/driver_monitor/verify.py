"""Repeatable, camera-free acceptance checks; no accuracy claims or human data."""

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, Dict, Optional, Sequence
from uuid import uuid4

from .config import FatigueConfig, load_config
from .events import JsonlEventWriter
from .fatigue_engine import FatigueEngine


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def run_logic_checks(output_directory: Path) -> list:
    """Replay fixed signals through the real engine and event writer."""
    output_directory.mkdir(parents=True, exist_ok=True)
    cases = [
        ("normal_and_short_blink", [
            (0.0, {}, "NORMAL", None),
            (1.0, {"ear": 0.10}, "NORMAL", None),
            (1.2, {}, "NORMAL", None),
        ]),
        ("sustained_closure_and_recovery", [
            (0.0, {"ear": 0.10}, "NORMAL", None),
            (1.6, {"ear": 0.10}, "WARNING", "eyes_closed"),
            (3.1, {"ear": 0.10}, "DANGER", "eyes_closed_too_long"),
            (3.2, {}, "DANGER", "recovering"),
            (5.3, {}, "NORMAL", None),
        ]),
        ("repeated_yawning", [
            (0.0, {"mar": 0.9}, "NORMAL", None),
            (1.3, {"mar": 0.9}, "WARNING", "yawning"),
            (1.5, {"mar": 0.9}, "WARNING", "yawning"),
            (2.0, {}, "WARNING", "recovering"),
            (4.1, {}, "NORMAL", None),
            (5.0, {"mar": 0.9}, "NORMAL", None),
            (6.3, {"mar": 0.9}, "WARNING", "repeated_yawning"),
        ]),
        ("missing_face", [
            (0.0, {"face_detected": False, "ear": None, "mar": None}, "NORMAL", None),
            (2.1, {"face_detected": False, "ear": None, "mar": None}, "WARNING", "face_missing"),
        ]),
        ("head_down_excludes_eye_and_mouth", [
            (0.0, {"pitch": 20.0, "ear": 0.08, "mar": 0.9}, "NORMAL", None),
            (3.1, {"pitch": 20.0, "ear": 0.08, "mar": 0.9}, "WARNING", "head_down"),
        ]),
        ("looking_away", [
            (0.0, {"yaw": -35.0}, "NORMAL", None),
            (2.1, {"yaw": -35.0}, "WARNING", "looking_away"),
        ]),
        ("phone_persistence_and_reset", [
            (0.0, {"phone_detected": True}, "NORMAL", None),
            (1.0, {}, "NORMAL", None),
            (1.5, {"phone_detected": True}, "NORMAL", None),
            (3.0, {"phone_detected": True}, "NORMAL", None),
            (3.6, {"phone_detected": True}, "WARNING", "phone_detected"),
            (3.7, {}, "WARNING", "recovering"),
            (5.8, {}, "NORMAL", None),
        ]),
    ]
    results = []
    for name, steps in cases:
        result: Dict[str, Any] = {"name": name, "ok": False, "checkpoints": []}
        try:
            engine = FatigueEngine(FatigueConfig())
            writer = JsonlEventWriter(output_directory / (name + ".jsonl"))
            for timestamp, values, expected_state, expected_reason in steps:
                signals = {"face_detected": True, "ear": 0.3, "mar": 0.2}
                signals.update(values)
                snapshot = engine.update(timestamp=timestamp, **signals)
                writer.write_if_changed(snapshot)
                result["checkpoints"].append({
                    "timestamp": timestamp,
                    "expected_state": expected_state,
                    "actual_state": snapshot.state.name,
                    "expected_reason": expected_reason,
                    "actual_reasons": list(snapshot.reasons),
                })
                _require(snapshot.state.name == expected_state, "unexpected risk state")
                _require(expected_reason in snapshot.reasons if expected_reason else not snapshot.reasons,
                         "unexpected risk reason")
                if name == "head_down_excludes_eye_and_mouth":
                    _require(snapshot.eye_closed_seconds == 0 and snapshot.recent_yawn_count == 0
                             and snapshot.perclos_coverage_seconds == 0, "unreliable pose counted as fatigue")
            if name == "repeated_yawning":
                _require(snapshot.recent_yawn_count == 2, "a sustained yawn was counted more than once")
            rows = [json.loads(line) for line in writer.path.read_text(encoding="utf-8").splitlines()]
            expected_states = []
            for _, _, state, _ in steps:
                if not expected_states or expected_states[-1] != state:
                    expected_states.append(state)
            _require([row["state"] for row in rows] == expected_states, "event log differs from state changes")
            result.update(ok=True, event_count=len(rows), event_file=writer.path.name)
        except Exception as exc:
            result["error"] = str(exc)
        results.append(result)

    result = {"name": "perclos_across_frame_rates", "ok": False, "observations": []}
    try:
        for fps in (10, 30):
            engine = FatigueEngine(FatigueConfig())
            for frame_index in range(10 * fps + 1):
                timestamp = frame_index / fps
                snapshot = engine.update(timestamp, True, 0.1 if 4 <= timestamp < 6 else 0.3, 0.2)
            result["observations"].append({"fps": fps, "perclos": snapshot.perclos,
                                           "coverage_seconds": snapshot.perclos_coverage_seconds})
            _require(abs(snapshot.perclos - 0.2) < 1e-6, "PERCLOS differs from the two-second closure schedule")
            _require(abs(snapshot.perclos_coverage_seconds - 10) < 1e-6, "incorrect observation coverage")
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    results.append(result)
    return results


def run_video_smoke(config, project_root: Path, output_directory: Path) -> Dict[str, Any]:
    """Decode a generated blank clip and execute both real models on CPU."""
    import cv2
    import numpy as np
    from .runtime import MonitorRuntime

    fps, frame_count = 10, 40
    output_directory.mkdir(parents=True, exist_ok=True)
    events_path = (output_directory / "video_events.jsonl").resolve()
    smoke_config = replace(
        config,
        calibration=replace(config.calibration, enabled=False),
        phone=replace(config.phone, device="cpu"),
        fatigue=FatigueConfig(),
        output=replace(config.output, show_window=False, write_events=True, events_path=str(events_path)),
    )
    with TemporaryDirectory(prefix="driver-monitor-verify-") as directory:
        video_path = Path(directory) / "synthetic_blank.avi"
        writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), fps, (320, 240))
        try:
            _require(writer.isOpened(), "OpenCV cannot create the synthetic MJPG video")
            for _ in range(frame_count):
                writer.write(np.zeros((240, 320, 3), dtype=np.uint8))
        finally:
            writer.release()
        processed = 0
        phone_timestamps = set()
        timestamps = []
        started = perf_counter()
        with MonitorRuntime(smoke_config, project_root, video_path=video_path) as runtime:
            while True:
                frame = runtime.read()
                if frame is None:
                    break
                processed += 1
                _require(processed <= frame_count, "runtime did not stop at video EOF")
                _require(frame.signals is None, "unexpected face detected in blank synthetic video")
                _require(frame.snapshot is not None, "smoke calibration must be disabled")
                timestamps.append(frame.snapshot.timestamp)
                if frame.phone_observation is not None:
                    _require(not frame.phone_observation.detected, "unexpected phone detected in blank video")
                    phone_timestamps.add(frame.phone_observation.timestamp)
            device = runtime.phone_detector.device_selection.resolved if runtime.phone_detector else None
        elapsed = perf_counter() - started
    _require(processed == frame_count, "not all generated video frames were decoded")
    _require(all(b > a for a, b in zip(timestamps, timestamps[1:])), "video timestamps did not advance")
    _require(abs(timestamps[-1] - 3.9) < 0.05, "video time differs from generated clip duration")
    if config.phone.enabled:
        _require(device == "cpu" and len(phone_timestamps) > 0, "CPU phone inference did not execute")
    rows = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines()]
    _require([row["state"] for row in rows] == ["NORMAL", "WARNING"], "unexpected blank-video event sequence")
    _require("face_missing" in rows[-1]["reasons"], "missing-face event was not logged")
    return {
        "ok": True, "input": "generated blank MJPG video; no people or camera",
        "processed_frames": processed, "source_fps": fps, "last_timestamp_seconds": timestamps[-1],
        "wall_seconds": round(elapsed, 3), "processing_fps_including_model_load": round(processed / elapsed, 2),
        "face_inference": "cpu", "phone_device": device,
        "phone_inference_count": len(phone_timestamps), "event_count": len(rows),
        "event_file": events_path.name,
        "overrides": {"calibration_enabled": False, "phone_device": "cpu", "fatigue": asdict(smoke_config.fatigue)},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="无需摄像头或真人的离线验收")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/verification"))
    parser.add_argument("--logic-only", action="store_true", help="只检查合成信号逻辑，不加载模型，供 CI 使用")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.project_root.expanduser().resolve()
    config_path = args.config.expanduser()
    if not config_path.is_absolute():
        config_path = root / config_path
    output_root = args.output_dir.expanduser()
    if not output_root.is_absolute():
        output_root = root / output_root
    now = datetime.now(timezone.utc)
    run_directory = output_root / (now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    run_directory.mkdir(parents=True, exist_ok=False)
    report: Dict[str, Any] = {
        "schema_version": 1, "created_at": now.isoformat(),
        "scope": "synthetic_logic_only" if args.logic_only else "synthetic_logic_and_cpu_video",
        "camera_accessed": False, "human_testing_performed": False,
        "limitations": ["Synthetic checks do not measure real-world detection accuracy.",
                        "No human calibration, camera, Windows/Linux hardware, CUDA or TensorRT validation."],
        "logic_config": asdict(FatigueConfig()),
    }
    report["logic_checks"] = run_logic_checks(run_directory)
    report["ok"] = all(check["ok"] for check in report["logic_checks"])
    if args.logic_only:
        report["doctor"] = {"skipped": True, "reason": "logic-only mode"}
        report["video_smoke"] = {"skipped": True, "reason": "logic-only mode"}
    else:
        from .doctor import build_report
        try:
            report["doctor"] = build_report(root, config_path, check_camera=False)
            report["config_sha256"] = hashlib.sha256(config_path.read_bytes()).hexdigest()
            if not report["doctor"]["ok"]:
                report["ok"] = False
                report["video_smoke"] = {"skipped": True, "reason": "environment diagnosis failed"}
            else:
                report["video_smoke"] = run_video_smoke(load_config(config_path), root, run_directory)
        except Exception as exc:
            report["ok"] = False
            report["video_smoke"] = {"ok": False, "error": str(exc)}
    report_path = run_directory / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print("离线验收：{}；合成逻辑场景 {}/{} 通过".format(
        "通过" if report["ok"] else "失败",
        sum(check["ok"] for check in report["logic_checks"]), len(report["logic_checks"])))
    print("范围：{}；未访问摄像头、未进行真人测试".format(report["scope"]))
    print("验收报告：{}".format(report_path))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
