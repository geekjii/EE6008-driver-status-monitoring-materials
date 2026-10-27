"""Local web presentation layer for the Python monitoring runtime."""

import argparse
import json
from collections import deque
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from queue import Empty, Queue
from threading import Condition, Event, Lock, Thread, Timer
from time import time
from typing import Any, Deque, Dict, Literal, Optional, Sequence, Tuple
import webbrowser

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import load_config
from .overlay import draw_face_landmarks, draw_phone_boxes
from .phone_detection import PhoneDetector
from .runtime import MonitorRuntime, RuntimeFrame
from .session_recording import SessionRecorder
from urllib.parse import quote


WEB_DIRECTORY = Path(__file__).resolve().parent / "web"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"

STATE_NAMES = {
    "NORMAL": "状态正常",
    "WARNING": "需要注意",
    "DANGER": "疲劳危险",
}

REASON_NAMES = {
    "face_missing": "人脸长时间离开画面",
    "eyes_closed": "持续闭眼",
    "eyes_closed_too_long": "闭眼时间过长",
    "yawning": "正在打哈欠",
    "repeated_yawning": "频繁打哈欠",
    "high_perclos": "闭眼占比较高",
    "very_high_perclos": "闭眼占比过高",
    "recovering": "状态恢复确认中",
    "head_down": "持续低头",
    "looking_away": "持续偏离前方",
    "phone_detected": "持续检测到手机",
}


def _initial_payload() -> Dict[str, Any]:
    return {
        "phase": "idle",
        "running": False,
        "source": "camera",
        "source_label": "摄像头",
        "video_path": None,
        "frames_processed": 0,
        "state": "IDLE",
        "reasons": [],
        "message": "点击开始监测，系统会先建立个人面部基准。",
        "face_detected": False,
        "ear": None,
        "mar": None,
        "head_pitch": None,
        "head_yaw": None,
        "head_roll": None,
        "head_away_seconds": 0.0,
        "phone_detected": False,
        "phone_confidence": None,
        "phone_seen_seconds": 0.0,
        "phone_inference_ms": None,
        "phone_device": None,
        "perclos": 0.0,
        "perclos_coverage_seconds": 0.0,
        "eye_closed_seconds": 0.0,
        "recent_yawn_count": 0,
        "fps": 0.0,
        "calibration_remaining_seconds": 0.0,
        "calibration_sample_count": 0,
        "ear_threshold": None,
        "mar_threshold": None,
        "events": [],
        "updated_at": time(),
    }


class WebMonitorService:
    """Thread-safe bridge between local inference and HTTP presentation."""

    def __init__(self, config_path: Path):
        self.config_path = config_path.expanduser().resolve()
        self.project_root = self.config_path.parent.parent
        self.config = load_config(self.config_path)
        self._lock = Lock()
        self._frame_condition = Condition()
        self._stop_event = Event()
        self._commands: Queue = Queue()
        self._thread: Optional[Thread] = None
        self._payload = _initial_payload()
        self._payload.update(
            source_label="摄像头 {}".format(self.config.camera.index),
            camera_index=self.config.camera.index,
            phone_enabled=self.config.phone.enabled,
        )
        self._events: Deque[Dict[str, Any]] = deque(maxlen=12)
        self._event_number = 0
        self._jpeg: Optional[bytes] = None
        self._frame_version = 0
        self._phone_detector: Optional[PhoneDetector] = None
        self._recorder: Optional[SessionRecorder] = None
        self._saved_export = self.find_recent_export()

    def find_recent_export(self) -> Optional[Dict[str, Any]]:
        root = Path(self.config.output.sessions_path)
        if not root.is_absolute():
            root = self.project_root / root
        files = sorted(root.glob("监测_*/导出_*/监测摘要.json"), key=lambda path: path.stat().st_mtime, reverse=True)
        for path in files:
            try:
                summary = json.loads(path.read_text(encoding="utf-8"))
                if not (path.parent / "监测报告.html").is_file():
                    continue
                return {"session_id": path.parent.parent.name, "export_id": path.parent.name,
                        "frames": summary["frames"], "directory": str(path.parent.resolve()),
                        "report_path": str(path.parent / "监测报告.html"),
                        "archive_path": str(path.parent / "监测导出.zip"), "status": summary["status"]}
            except (OSError, ValueError, KeyError):
                continue
        return None

    def prepare_phone_detector(self) -> None:
        """Load PyTorch/YOLO on the main thread before camera work starts."""

        if not self.config.phone.enabled or self._phone_detector is not None:
            return
        model_path = Path(self.config.phone.model_path)
        if not model_path.is_absolute():
            model_path = self.project_root / model_path
        self._phone_detector = PhoneDetector(
            model_path=model_path,
            confidence_threshold=self.config.phone.confidence_threshold,
            image_size=self.config.phone.image_size,
            device=self.config.phone.device,
        )
        self._update_payload(
            phone_device=self._phone_detector.device_selection.resolved,
            compute_message=self._phone_detector.device_selection.reason,
        )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            payload = deepcopy(self._payload)
            payload["events"] = list(self._events)
            recorder = self._recorder
        payload["session"] = recorder.info() if recorder else None
        if recorder is None and self._saved_export:
            payload["session"] = {"session_id": self._saved_export["session_id"],
                                  "frames": self._saved_export["frames"], "read_only": True,
                                  "closed": True, "directory": self._saved_export["directory"],
                                  "last_export": self._saved_export, "export_error": None}
        if payload["session"] and payload["session"]["last_export"]:
            payload["session"]["last_export"] = self.export_links(payload["session"]["last_export"])
        return payload

    def export_links(self, result: Dict[str, Any]) -> Dict[str, Any]:
        prefix = "/api/exports/{}/{}".format(quote(result["session_id"]), quote(result["export_id"]))
        links = {**result, "report_url": prefix + "/report", "download_url": prefix + "/archive"}
        if (Path(result["directory"]) / "关键指标折线图.html").is_file():
            links["charts_url"] = prefix + "/charts"
        return links

    def export_session(self) -> Dict[str, Any]:
        with self._lock:
            recorder = self._recorder
        if recorder is None:
            raise ValueError("还没有可导出的监测数据")
        return self.export_links(recorder.export())

    def export_file(self, session_id: str, export_id: str, kind: str) -> Path:
        allowed = {"report": "监测报告.html", "charts": "关键指标折线图.html",
                   "监测报告.html": "监测报告.html", "archive": "监测导出.zip",
                   "监测数据.csv": "监测数据.csv", "事件记录.csv": "事件记录.csv"}
        if kind not in allowed or not session_id.startswith("监测_") or not export_id.startswith("导出_"):
            raise ValueError("找不到导出文件")
        root = Path(self.config.output.sessions_path)
        if not root.is_absolute():
            root = self.project_root / root
        root = root.resolve()
        path = (root / session_id / export_id / allowed[kind]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("找不到导出文件")
        if kind == "archive":
            updated = path.parent / "监测导出_含折线图.zip"
            if updated.is_file():
                path = updated
        return path

    def _add_event(self, title: str, detail: str, level: str = "info") -> None:
        with self._lock:
            self._add_event_locked(title, detail, level)

    def _add_event_locked(self, title: str, detail: str, level: str = "info") -> None:
        self._event_number += 1
        self._events.appendleft(
            {
                "id": self._event_number,
                "title": title,
                "detail": detail,
                "level": level,
                "timestamp": time(),
            }
        )
        self._payload["events"] = list(self._events)

    def _update_payload(self, **values: Any) -> None:
        with self._lock:
            if values.get("running") and self._stop_event.is_set():
                return
            self._payload.update(values)
            self._payload["updated_at"] = time()

    def _reset_payload_locked(self, **values: Any) -> None:
        """Clear live readings while retaining source and device information."""

        retained = {
            key: self._payload[key]
            for key in (
                "source", "source_label", "video_path", "camera_index",
                "phone_enabled", "phone_device", "compute_message", "frames_processed",
            )
            if key in self._payload
        }
        self._payload = {**_initial_payload(), **retained, **values}

    def _clear_frame(self) -> None:
        with self._frame_condition:
            self._jpeg = None
            self._frame_version += 1
            self._frame_condition.notify_all()

    def start(self, source: str = "camera", video_path: Optional[Path] = None) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if source not in {"camera", "video"}:
                raise ValueError("请选择摄像头或本地视频")
            if source == "video":
                if video_path is None or not str(video_path).strip():
                    raise ValueError("请输入本地视频的完整路径")
                video_path = Path(video_path).expanduser().resolve()
                if not video_path.is_file():
                    raise ValueError("找不到本地视频文件，请检查路径")
                source_label = "视频 · {}".format(video_path.name)
            else:
                if video_path is not None:
                    raise ValueError("使用视频路径时，请选择本地视频输入")
                source_label = "摄像头 {}".format(self.config.camera.index)
            self._stop_event.clear()
            self._recorder = None
            if self.config.output.record_session:
                directory = Path(self.config.output.sessions_path)
                if not directory.is_absolute():
                    directory = self.project_root / directory
                self._recorder = SessionRecorder(
                    directory, self.config, video_path if video_path is not None else self.config.camera.index,
                    self._phone_detector.device if self._phone_detector is not None else None,
                )
            self._commands = Queue()
            self._clear_frame()
            self._reset_payload_locked(
                phase="starting",
                running=True,
                state="STARTING",
                source=source,
                source_label=source_label,
                video_path=str(video_path) if video_path is not None else None,
                frames_processed=0,
                message="正在打开{}并加载人脸模型…".format(
                    "本地视频" if source == "video" else "摄像头"
                ),
            )
            self._add_event_locked("监测启动", source_label)
            self._thread = Thread(target=self._run, args=(video_path,), daemon=True)
            self._thread.start()
        return True

    def stop(self) -> bool:
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                return False
            self._stop_event.set()
            self._reset_payload_locked(
                phase="stopping", running=True, state="STOPPING",
                message="正在停止并释放输入资源…",
            )
            self._clear_frame()
        thread.join(timeout=3.0)
        return True

    def recalibrate(self) -> bool:
        with self._lock:
            if (
                self._thread is None or not self._thread.is_alive()
                or self._stop_event.is_set()
            ):
                return False
        self._commands.put("recalibrate")
        return True

    def wait_for_frame(
        self, previous_version: int, timeout: float = 1.0
    ) -> Tuple[Optional[bytes], int]:
        with self._frame_condition:
            if self._frame_version <= previous_version:
                self._frame_condition.wait(timeout=timeout)
            return self._jpeg, self._frame_version

    def _publish_frame(self, result: RuntimeFrame) -> None:
        import cv2

        frame = result.frame.copy()
        if result.snapshot is None:
            color = (60, 190, 255)
        elif result.snapshot.state.name == "NORMAL":
            color = (94, 197, 34)
        elif result.snapshot.state.name == "WARNING":
            color = (11, 158, 245)
        else:
            color = (68, 68, 239)
        draw_face_landmarks(frame, result.signals, color)
        draw_phone_boxes(frame, result.phone_observation)
        ok, encoded = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82]
        )
        if not ok:
            return
        with self._frame_condition:
            if self._stop_event.is_set():
                return
            self._jpeg = encoded.tobytes()
            self._frame_version += 1
            self._frame_condition.notify_all()

    def _publish_metrics(self, result: RuntimeFrame) -> None:
        calibration = result.calibration_result
        common = {
            "running": True,
            "face_detected": result.signals is not None,
            "ear": result.signals.ear if result.signals is not None else None,
            "mar": result.signals.mar if result.signals is not None else None,
            "head_pitch": result.signals.pitch if result.signals is not None else None,
            "head_yaw": result.signals.yaw if result.signals is not None else None,
            "head_roll": result.signals.roll if result.signals is not None else None,
            "fps": result.fps,
            "calibration_remaining_seconds": result.calibration_remaining_seconds,
            "calibration_sample_count": result.calibration_sample_count,
            "ear_threshold": (
                calibration.ear_closed_threshold if calibration is not None else None
            ),
            "mar_threshold": (
                calibration.mar_open_threshold if calibration is not None else None
            ),
        }
        if result.snapshot is None:
            self._update_payload(
                phase="calibrating",
                state="CALIBRATING",
                reasons=[],
                message=(
                    "正在使用视频开头建立个人基准"
                    if self._payload["source"] == "video"
                    else "请正常睁眼、闭嘴并正对镜头"
                    if result.signals is not None
                    else "请让脸完整出现在画面中"
                ),
                perclos=0.0,
                perclos_coverage_seconds=0.0,
                eye_closed_seconds=0.0,
                recent_yawn_count=0,
                head_away_seconds=0.0,
                phone_detected=False,
                phone_confidence=None,
                phone_seen_seconds=0.0,
                phone_inference_ms=(
                    result.phone_observation.inference_ms
                    if result.phone_observation is not None
                    else None
                ),
                **common,
            )
            return

        snapshot = result.snapshot
        self._update_payload(
            phase="monitoring",
            state=snapshot.state.name,
            reasons=list(snapshot.reasons),
            message="当前没有检测到持续疲劳信号" if not snapshot.reasons else "",
            perclos=snapshot.perclos,
            perclos_coverage_seconds=snapshot.perclos_coverage_seconds,
            eye_closed_seconds=snapshot.eye_closed_seconds,
            recent_yawn_count=snapshot.recent_yawn_count,
            head_away_seconds=snapshot.head_away_seconds,
            phone_detected=snapshot.phone_detected,
            phone_confidence=snapshot.phone_confidence,
            phone_seen_seconds=snapshot.phone_seen_seconds,
            phone_inference_ms=(
                result.phone_observation.inference_ms
                if result.phone_observation is not None
                else None
            ),
            **common,
        )

    def _run(self, video_path: Optional[Path] = None) -> None:
        previous_state = None
        calibration_reported = False
        frames_processed = 0
        phase, state, message = "idle", "IDLE", "监测已停止"
        event_title, event_detail, event_level = "监测停止", "输入资源已安全释放", "info"
        try:
            with MonitorRuntime(
                self.config,
                self.project_root,
                video_path=video_path,
                phone_detector=self._phone_detector,
                session_recorder=self._recorder,
            ) as runtime:
                while not self._stop_event.is_set():
                    try:
                        while True:
                            command = self._commands.get_nowait()
                            if command == "recalibrate":
                                runtime.reset_calibration()
                                calibration_reported = False
                                previous_state = None
                                self._add_event(
                                    "重新校准", "请正常睁眼、闭嘴并正对镜头"
                                )
                    except Empty:
                        pass

                    result = runtime.read()
                    if self._stop_event.is_set():
                        break
                    if result is None:
                        if video_path is None:
                            raise RuntimeError("摄像头画面已经结束")
                        phase, state = "completed", "COMPLETED"
                        message = "视频分析完成，共处理 {} 帧".format(frames_processed)
                        if self.config.calibration.enabled and not calibration_reported:
                            message += "；未完成个人校准，未生成疲劳判断"
                        event_title, event_detail, event_level = "视频分析完成", message, "success"
                        break
                    frames_processed += 1
                    self._publish_frame(result)
                    self._publish_metrics(result)
                    self._update_payload(frames_processed=frames_processed)

                    if result.calibration_result is not None and not calibration_reported:
                        calibration_reported = True
                        self._add_event(
                            "个人校准完成",
                            "EAR {:.3f} · MAR {:.3f}".format(
                                result.calibration_result.ear_closed_threshold,
                                result.calibration_result.mar_open_threshold,
                            ),
                            "success",
                        )
                    if result.snapshot is not None and result.snapshot.state != previous_state:
                        previous_state = result.snapshot.state
                        level = (
                            "success"
                            if result.snapshot.state.name == "NORMAL"
                            else "warning"
                            if result.snapshot.state.name == "WARNING"
                            else "danger"
                        )
                        self._add_event(
                            "状态变为 {}".format(
                                STATE_NAMES[result.snapshot.state.name]
                            ),
                            "、".join(
                                REASON_NAMES.get(reason, reason)
                                for reason in result.snapshot.reasons
                            )
                            or "当前状态稳定",
                            level,
                        )
        except Exception as exc:
            phase, state, message = "error", "ERROR", str(exc)
            event_title, event_detail, event_level = "运行错误", message, "danger"
        finally:
            with self._lock:
                self._reset_payload_locked(
                    phase=phase, state=state, message=message,
                    frames_processed=frames_processed,
                )
                self._clear_frame()
                self._add_event_locked(event_title, event_detail, event_level)


class StartRequest(BaseModel):
    source: Literal["camera", "video"] = "camera"
    video_path: Optional[str] = None


def create_app(config_path: Path = DEFAULT_CONFIG_PATH) -> FastAPI:
    service_lock = Lock()

    def monitor() -> WebMonitorService:
        # Importing the CLI must not require an unrelated default configuration.
        with service_lock:
            if dashboard.state.monitor is None:
                dashboard.state.monitor = WebMonitorService(config_path)
            return dashboard.state.monitor

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        service = monitor()
        service.prepare_phone_detector()
        try:
            yield
        finally:
            service.stop()

    dashboard = FastAPI(
        title="EE6008 Driver Fatigue Dashboard",
        lifespan=lifespan,
    )
    dashboard.state.monitor = None
    dashboard.mount("/assets", StaticFiles(directory=WEB_DIRECTORY), name="assets")

    @dashboard.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIRECTORY / "index.html")

    @dashboard.get("/api/health")
    def health():
        return {"status": "ok", "mode": "local"}

    @dashboard.get("/api/status")
    def status():
        return monitor().snapshot()

    @dashboard.post("/api/start")
    def start(request: Optional[StartRequest] = None):
        service = monitor()
        request = request or StartRequest()
        try:
            started = service.start(request.source, request.video_path)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"started": started, "status": service.snapshot()}

    @dashboard.post("/api/stop")
    def stop():
        service = monitor()
        return {"stopped": service.stop(), "status": service.snapshot()}

    @dashboard.post("/api/recalibrate")
    def recalibrate():
        service = monitor()
        if not service.recalibrate():
            raise HTTPException(status_code=409, detail="监测尚未启动")
        return {"recalibrating": True}

    @dashboard.post("/api/export")
    def export():
        try:
            return monitor().export_session()
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail="导出失败：{}".format(exc)) from exc

    @dashboard.get("/api/exports/{session_id}/{export_id}/{kind}")
    def exported_file(session_id: str, export_id: str, kind: str):
        try:
            path = monitor().export_file(session_id, export_id, kind)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if kind in {"report", "charts", "监测报告.html"}:
            return FileResponse(path, media_type="text/html")
        return FileResponse(path, filename=path.name, media_type="application/zip" if kind == "archive" else "text/csv")

    @dashboard.get("/api/video", include_in_schema=False)
    def video() -> StreamingResponse:
        service = monitor()
        def frames():
            version = -1
            while True:
                jpeg, next_version = service.wait_for_frame(version)
                if not service.snapshot()["running"]:
                    return
                if jpeg is None or next_version == version:
                    continue
                version = next_version
                yield (
                    b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                    + jpeg
                    + b"\r\n"
                )

        return StreamingResponse(
            frames(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    return dashboard


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EE6008 local web dashboard")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    import uvicorn

    args = build_parser().parse_args(argv)
    url = "http://127.0.0.1:{}".format(args.port)
    if not args.no_browser:
        Timer(0.8, lambda: webbrowser.open(url)).start()
    dashboard = create_app(args.config)
    uvicorn.run(
        dashboard,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
