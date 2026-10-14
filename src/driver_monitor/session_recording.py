"""Per-frame recording and independent, camera-free session exports."""

import csv
from dataclasses import asdict
from datetime import datetime, timezone
from importlib import metadata
import json
from math import isfinite
from pathlib import Path
import shutil
from threading import Lock
from time import monotonic
from typing import Any, Optional
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile


# One field definition owns CSV headings and the offline report's table.
COLUMNS = [
    ("frame_index", "帧序号 / Frame"),
    ("timestamp", "输入时间（秒） / Input time (s)"),
    ("recorded_at_utc", "记录时间（UTC） / Recorded UTC"),
    ("phase", "阶段 / Phase"), ("state", "状态 / State"),
    ("raw_state", "原始状态 / Raw state"), ("reasons", "状态原因 / Reasons"),
    ("calibration_round", "校准轮次 / Calibration round"),
    ("calibration_valid", "校准样本有效 / Valid calibration sample"),
    ("calibration_remaining_seconds", "校准剩余（秒） / Calibration remaining (s)"),
    ("calibration_sample_count", "校准样本数 / Calibration samples"),
    ("open_eye_baseline", "睁眼基准 / Open-eye baseline"),
    ("closed_mouth_baseline", "闭嘴基准 / Closed-mouth baseline"),
    ("ear_threshold", "闭眼阈值 / EAR threshold"),
    ("mar_threshold", "张嘴阈值 / MAR threshold"),
    ("face_detected", "检测到人脸 / Face detected"),
    ("pose_usable", "面部指标可用 / Facial metrics usable"),
    ("ear", "眼睛EAR / Eye EAR"), ("mar", "嘴巴MAR / Mouth MAR"),
    ("eye_closed", "闭眼判断 / Eye closed"), ("mouth_open", "张嘴判断 / Mouth open"),
    ("eye_closed_seconds", "持续闭眼（秒） / Eye closure (s)"),
    ("mouth_open_seconds", "持续张嘴（秒） / Mouth opening (s)"),
    ("perclos", "PERCLOS（0–1） / PERCLOS ratio"),
    ("perclos_coverage_seconds", "PERCLOS有效覆盖（秒） / Coverage (s)"),
    ("perclos_ready", "PERCLOS达到最小覆盖 / PERCLOS ready"),
    ("recent_yawn_count", "窗口内哈欠次数 / Recent yawns"),
    ("head_pitch", "头部俯仰（度） / Pitch (deg)"),
    ("head_yaw", "头部左右（度） / Yaw (deg)"),
    ("head_roll", "头部侧倾（度） / Roll (deg)"),
    ("head_away_seconds", "持续偏离（秒） / Looking away (s)"),
    ("phone_checked", "手机已有推理结果 / Phone checked"),
    ("phone_fresh", "本帧手机新推理 / Fresh phone inference"),
    ("phone_detected", "检测到手机 / Phone detected"),
    ("phone_confidence", "手机置信度（0–1） / Phone confidence"),
    ("phone_timestamp", "手机推理时间（秒） / Phone inference time (s)"),
    ("phone_result_age_seconds", "手机结果距今（秒） / Phone result age (s)"),
    ("phone_seen_seconds", "持续出现手机（秒） / Phone presence (s)"),
    ("phone_inference_ms", "手机推理耗时（毫秒） / Phone inference (ms)"),
    ("phone_boxes", "手机框坐标 / Phone boxes"),
    ("phone_device", "手机推理设备 / Phone device"),
    ("fps", "处理帧率 / Processing FPS"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def clean(value: Any) -> Any:
    if isinstance(value, float) and not isfinite(value):
        return None
    if isinstance(value, (tuple, list)):
        return [clean(item) for item in value]
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    return value


def cell(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    # User-supplied source/error strings must remain text in spreadsheet apps.
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(clean(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


class SessionRecorder:
    """Stream all frame measurements to disk; exports never consume camera frames."""

    def __init__(self, directory: Path, config: Any, source: Any, device: Optional[str] = None):
        self.config = config
        self.session_id = "监测_{}Z_{}".format(
            datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"), uuid4().hex[:8]
        )
        self.directory = Path(directory).resolve() / self.session_id
        self.directory.mkdir(parents=True, exist_ok=False)
        self._lock = Lock()
        self._export_lock = Lock()
        self._closed = False
        self._frames = 0
        self._round = 0
        self._previous = None
        self._phone_timestamp = None
        self._signature = None
        self._flush_time = monotonic()
        self._last_export = None
        self._export_error = None
        self._event_count = 0
        self._durations = {}
        self._reason_durations = {}
        self._phone_inferences = 0
        self._face_missing_seconds = 0.0
        self._first_timestamp = None
        self._last_timestamp = None
        self.metadata = {
            "schema_version": 1, "session_id": self.session_id,
            "started_at_utc": utc_now(), "finished_at_utc": None,
            "source": {"type": "camera" if isinstance(source, int) else "video", "value": str(source)},
            "status": "recording", "error": None, "config": asdict(config),
            "phone_device": device, "data_origin": "monitoring_runtime",
            "time_basis": "camera elapsed time" if isinstance(source, int) else "video media time",
        }
        self.metadata["versions"] = {}
        for name in ("ee6008-driver-monitor", "mediapipe", "ultralytics", "torch", "opencv-contrib-python"):
            try:
                self.metadata["versions"][name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                self.metadata["versions"][name] = None
        self._data = (self.directory / "逐帧原始数据.jsonl").open("w", encoding="utf-8")
        self._csv = (self.directory / "监测数据.csv").open("w", encoding="utf-8-sig", newline="")
        self._writer = csv.writer(self._csv)
        self._writer.writerow([label for _, label in COLUMNS])
        self._events = (self.directory / "事件记录.csv").open("w", encoding="utf-8-sig", newline="")
        self._event_writer = csv.writer(self._events)
        self._event_writer.writerow(["时间（秒） / Time (s)", "事件 / Event", "状态 / State", "原因 / Reasons", "详情 / Detail"])
        write_json(self.directory / "会话信息.json", self.metadata)

    def set_device(self, device: Optional[str]) -> None:
        with self._lock:
            self.metadata["phone_device"] = device

    def recalibrate(self, timestamp: Optional[float] = None) -> None:
        with self._lock:
            self._round += 1
            self._phone_timestamp = None
            if self._frames:
                self._event_writer.writerow([timestamp if timestamp is not None else self._last_timestamp, "RECALIBRATE", "CALIBRATING", "", self._round])
                self._event_count += 1

    def record(self, result: Any, effective_config: Any) -> None:
        signals, snapshot, phone, calibration = result.signals, result.snapshot, result.phone_observation, result.calibration_result
        timestamp = result.timestamp
        if timestamp is None or not isfinite(timestamp):
            raise ValueError("Session recording requires a finite input timestamp")
        pose_ok = bool(signals is not None and all(
            angle is None or isfinite(angle) for angle in (signals.pitch, signals.yaw, signals.roll)
        ) and (signals.pitch is None or signals.pitch < effective_config.head_down_warning_degrees)
          and (signals.yaw is None or abs(signals.yaw) < effective_config.head_yaw_warning_degrees))
        measurements_ok = bool(pose_ok and signals.ear is not None and signals.mar is not None
                               and isfinite(signals.ear) and isfinite(signals.mar)
                               and signals.ear >= 0 and signals.mar >= 0)
        row = {
            "timestamp": timestamp, "recorded_at_utc": utc_now(),
            "phase": "calibrating" if snapshot is None else "monitoring",
            "state": snapshot.state.name if snapshot else "CALIBRATING",
            "raw_state": snapshot.raw_state.name if snapshot else None,
            "reasons": list(snapshot.reasons) if snapshot else [],
            "calibration_valid": measurements_ok if snapshot is None else None,
            "calibration_remaining_seconds": result.calibration_remaining_seconds,
            "calibration_sample_count": calibration.sample_count if calibration else result.calibration_sample_count,
            "open_eye_baseline": calibration.open_eye_baseline if calibration else None,
            "closed_mouth_baseline": calibration.closed_mouth_baseline if calibration else None,
            "ear_threshold": effective_config.ear_closed_threshold if snapshot else None,
            "mar_threshold": effective_config.mar_open_threshold if snapshot else None,
            "face_detected": signals is not None, "pose_usable": measurements_ok,
            "ear": signals.ear if signals else None, "mar": signals.mar if signals else None,
            "eye_closed": signals.ear < effective_config.ear_closed_threshold if snapshot and measurements_ok else None,
            "mouth_open": signals.mar > effective_config.mar_open_threshold if snapshot and measurements_ok else None,
            "phone_checked": phone is not None,
            "phone_detected": phone.detected if phone else None,
            "phone_confidence": phone.confidence if phone else None,
            "phone_timestamp": phone.timestamp if phone else None,
            "phone_result_age_seconds": max(0.0, timestamp - phone.timestamp) if phone else None,
            "phone_inference_ms": phone.inference_ms if phone else None,
            "phone_boxes": [asdict(box) for box in phone.boxes] if phone else [],
            "fps": result.fps,
        }
        for key in ("eye_closed_seconds", "mouth_open_seconds", "perclos", "perclos_coverage_seconds", "recent_yawn_count", "head_away_seconds", "phone_seen_seconds"):
            row[key] = getattr(snapshot, key) if snapshot else None
        for key, attr in (("head_pitch", "pitch"), ("head_yaw", "yaw"), ("head_roll", "roll")):
            row[key] = getattr(signals, attr) if signals else None
        row["perclos_ready"] = bool(snapshot and snapshot.perclos_coverage_seconds >= effective_config.perclos_min_coverage_seconds)
        with self._lock:
            if self._closed:
                raise RuntimeError("Cannot record into a finished session")
            if self._last_timestamp is not None and timestamp <= self._last_timestamp:
                raise ValueError("Session timestamps must be strictly increasing")
            self._frames += 1
            row.update(frame_index=self._frames, calibration_round=self._round,
                       phone_device=self.metadata["phone_device"],
                       phone_fresh=phone is not None and phone.timestamp != self._phone_timestamp)
            if row["phone_fresh"]:
                self._phone_inferences += 1
            self._phone_timestamp = phone.timestamp if phone else None
            row = clean(row)
            if self._previous is not None:
                duration = timestamp - self._previous["timestamp"]
                state = self._previous["state"]
                self._durations[state] = self._durations.get(state, 0.0) + duration
                for reason in self._previous["reasons"]:
                    self._reason_durations[reason] = self._reason_durations.get(reason, 0.0) + duration
                if not self._previous["face_detected"]:
                    self._face_missing_seconds += duration
            signature = tuple(json.dumps(row[key], ensure_ascii=False) for key in (
                "state", "reasons", "face_detected", "pose_usable", "eye_closed", "mouth_open", "phone_detected", "calibration_round",
            ))
            if signature != self._signature:
                self._event_writer.writerow([timestamp, "OBSERVATION_CHANGE", row["state"], cell(row["reasons"]),
                    cell({key: row[key] for key in ("face_detected", "pose_usable", "eye_closed", "mouth_open", "phone_detected", "calibration_round")})])
                self._event_count += 1
                self._signature = signature
            self._data.write(json.dumps(row, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
            self._writer.writerow([cell(row.get(key)) for key, _ in COLUMNS])
            self._previous = row
            self._first_timestamp = timestamp if self._first_timestamp is None else self._first_timestamp
            self._last_timestamp = timestamp
            if monotonic() - self._flush_time >= 1:
                self._flush()

    def _flush(self) -> None:
        for handle in (self._data, self._csv, self._events):
            handle.flush()
        self._flush_time = monotonic()

    def info(self) -> dict:
        with self._lock:
            return {"session_id": self.session_id, "frames": self._frames, "closed": self._closed,
                    "directory": str(self.directory), "last_export": self._last_export,
                    "export_error": self._export_error}

    def _summary(self) -> dict:
        return clean({**self.metadata, "exported_at_utc": utc_now(), "frames": self._frames,
                     "first_timestamp": self._first_timestamp, "last_timestamp": self._last_timestamp,
                     "observed_seconds": (self._last_timestamp - self._first_timestamp) if self._frames else 0,
                     "state_seconds": dict(self._durations), "reason_seconds": dict(self._reason_durations),
                     "face_missing_seconds": self._face_missing_seconds, "event_count": self._event_count,
                     "fresh_phone_inferences": self._phone_inferences,
                     "duration_method": "Previous observation applies to the next input timestamp; the final frame has no inferred tail duration.",
                     "missing_data": "Blank/null means unavailable; 0 means measured zero. Phone results are held until the next inference; phone_fresh identifies new decisions."})

    def export(self) -> dict:
        # One exporter at a time; frames only pause briefly while files are copied.
        with self._export_lock:
            with self._lock:
                if not self._frames:
                    raise ValueError("还没有可导出的监测数据")
                if not self._closed:
                    self._flush()
                export_id = "导出_{}Z_{}".format(datetime.now(timezone.utc).strftime("%H%M%S"), uuid4().hex[:8])
                destination = self.directory / export_id
                destination.mkdir(exist_ok=False)
                for name in ("逐帧原始数据.jsonl", "监测数据.csv", "事件记录.csv"):
                    shutil.copyfile(self.directory / name, destination / name)
                summary = self._summary()
            write_json(destination / "监测摘要.json", summary)
            write_json(destination / "字段说明.json", {key: label for key, label in COLUMNS})
            rows = [json.loads(line) for line in (destination / "逐帧原始数据.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            payload = {"summary": summary, "columns": [{"key": key, "label": label} for key, label in COLUMNS],
                       "rows": [[row.get(key) for key, _ in COLUMNS] for row in rows]}
            template = (Path(__file__).parent / "web" / "report_template.html").read_text(encoding="utf-8")
            encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            (destination / "监测报告.html").write_text(template.replace("__SESSION_DATA__", encoded), encoding="utf-8")
            archive = destination / "监测导出.zip"
            with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
                for path in destination.iterdir():
                    if path != archive:
                        zipped.write(path, path.name)
            result = {"session_id": self.session_id, "export_id": export_id, "frames": summary["frames"],
                      "directory": str(destination), "report_path": str(destination / "监测报告.html"),
                      "archive_path": str(archive), "status": summary["status"]}
            with self._lock:
                self._last_export = result
                self._export_error = None
            return result

    def finish(self, status: str = "stopped", error: Optional[str] = None) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self.metadata.update(status=status, error=error, finished_at_utc=utc_now())
            self._event_writer.writerow([self._last_timestamp, "SESSION_END", status, "", cell(error)])
            self._event_count += 1
            try:
                self._flush()
            finally:
                for handle in (self._data, self._csv, self._events):
                    handle.close()
            write_json(self.directory / "会话信息.json", self._summary())
        if self._frames:
            try:
                self.export()
            except Exception as exc:
                with self._lock:
                    self._export_error = str(exc)
                write_json(self.directory / "导出错误.json", {"error": str(exc), "raw_data_directory": str(self.directory)})
