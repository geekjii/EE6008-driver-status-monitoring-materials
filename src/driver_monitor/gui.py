"""Beginner-friendly local desktop dashboard built with Tkinter."""

import argparse
from datetime import datetime
from pathlib import Path
from queue import Empty, Full, Queue
import threading
from typing import Dict, Optional, Sequence

from .config import AppConfig, load_config
from .domain import RiskLevel
from .overlay import REASON_LABELS, draw_face_landmarks
from .runtime import MonitorRuntime, RuntimeFrame


STATE_NAMES = {
    RiskLevel.NORMAL: "状态正常",
    RiskLevel.WARNING: "需要注意",
    RiskLevel.DANGER: "疲劳危险",
}

STATE_COLORS = {
    RiskLevel.NORMAL: "#22c55e",
    RiskLevel.WARNING: "#f59e0b",
    RiskLevel.DANGER: "#ef4444",
}

STATE_BGR_COLORS = {
    RiskLevel.NORMAL: (94, 197, 34),
    RiskLevel.WARNING: (11, 158, 245),
    RiskLevel.DANGER: (68, 68, 239),
}


class MonitorWorker(threading.Thread):
    """Keep camera/model work away from Tk's UI thread."""

    def __init__(
        self,
        config: AppConfig,
        project_root: Path,
        frame_queue: Queue,
        event_queue: Queue,
        video_path: Optional[Path] = None,
    ):
        super().__init__(daemon=True)
        self.config = config
        self.project_root = project_root
        self.frame_queue = frame_queue
        self.event_queue = event_queue
        self.video_path = video_path
        self.stop_event = threading.Event()
        self.command_queue: Queue = Queue()

    def stop(self) -> None:
        self.stop_event.set()

    def recalibrate(self) -> None:
        self.command_queue.put("recalibrate")

    def _put_latest(self, result: RuntimeFrame) -> None:
        try:
            self.frame_queue.put_nowait(result)
        except Full:
            try:
                self.frame_queue.get_nowait()
            except Empty:
                pass
            self.frame_queue.put_nowait(result)

    def run(self) -> None:
        previous_state = None
        calibration_reported = False
        try:
            with MonitorRuntime(
                self.config, self.project_root, self.video_path
            ) as runtime:
                self.event_queue.put(("started", None))
                while not self.stop_event.is_set():
                    try:
                        while True:
                            command = self.command_queue.get_nowait()
                            if command == "recalibrate":
                                runtime.reset_calibration()
                                calibration_reported = False
                                previous_state = None
                                self.event_queue.put(("recalibrating", None))
                    except Empty:
                        pass

                    result = runtime.read()
                    if result is None:
                        self.event_queue.put(("ended", None))
                        break
                    if result.calibration_result is not None and not calibration_reported:
                        calibration_reported = True
                        self.event_queue.put(("calibrated", result.calibration_result))
                    if result.snapshot is not None and result.snapshot.state != previous_state:
                        previous_state = result.snapshot.state
                        self.event_queue.put(("state", result.snapshot))
                    self._put_latest(result)
        except Exception as exc:
            self.event_queue.put(("error", str(exc)))
        finally:
            self.event_queue.put(("stopped", None))


class DriverMonitorDashboard:
    def __init__(self, root, config_path: Path):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.config_path = config_path.resolve()
        self.project_root = self.config_path.parent.parent
        self.base_config = load_config(self.config_path)
        self.worker: Optional[MonitorWorker] = None
        self.frame_queue: Queue = Queue(maxsize=2)
        self.event_queue: Queue = Queue()
        self.selected_video: Optional[Path] = None
        self._photo = None

        root.title("EE6008 驾驶员疲劳感知仪表盘")
        root.geometry("1320x820")
        root.minsize(1080, 700)
        root.configure(bg="#0b1220")
        root.protocol("WM_DELETE_WINDOW", self.close)

        self._configure_styles()
        self._build_layout()
        self._set_running_controls(False)
        self._append_event("界面已就绪；点击“开始监测”打开摄像头。")
        root.after(100, self._bring_to_front)
        root.after(30, self._poll)

    def _bring_to_front(self) -> None:
        """Make a Finder-launched dashboard visible instead of hiding behind apps."""

        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.focus_force()
        self.root.after(800, lambda: self.root.attributes("-topmost", False))

    def _configure_styles(self) -> None:
        style = self.ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(
            "Primary.TButton",
            font=("Arial", 13, "bold"),
            foreground="#ffffff",
            background="#2563eb",
            borderwidth=0,
            padding=(20, 11),
        )
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        style.configure(
            "Secondary.TButton",
            font=("Arial", 12),
            foreground="#e5e7eb",
            background="#263244",
            borderwidth=0,
            padding=(16, 10),
        )
        style.map("Secondary.TButton", background=[("active", "#334155")])
        style.configure(
            "Danger.TButton",
            font=("Arial", 12),
            foreground="#ffffff",
            background="#b91c1c",
            borderwidth=0,
            padding=(16, 10),
        )

    def _build_layout(self) -> None:
        tk = self.tk

        header = tk.Frame(self.root, bg="#0b1220", padx=24, pady=18)
        header.pack(fill="x")
        tk.Label(
            header,
            text="EE6008  驾驶员疲劳感知",
            font=("Arial", 24, "bold"),
            fg="#f8fafc",
            bg="#0b1220",
        ).pack(side="left")
        tk.Label(
            header,
            text="● 本地处理 · 不上传画面",
            font=("Arial", 12),
            fg="#67e8f9",
            bg="#0b1220",
        ).pack(side="right")

        body = tk.Frame(self.root, bg="#0b1220", padx=24)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        left = tk.Frame(body, bg="#111827", highlightbackground="#263244", highlightthickness=1)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        self.video_label = tk.Label(
            left,
            text="摄像头尚未启动",
            font=("Arial", 22),
            fg="#64748b",
            bg="#111827",
        )
        self.video_label.grid(row=0, column=0, sticky="nsew")

        source_bar = tk.Frame(left, bg="#182233", padx=14, pady=10)
        source_bar.grid(row=1, column=0, sticky="ew")
        self.source_var = tk.StringVar(value="输入：Mac 摄像头 0")
        tk.Label(
            source_bar,
            textvariable=self.source_var,
            font=("Arial", 11),
            fg="#cbd5e1",
            bg="#182233",
        ).pack(side="left")
        self.fps_var = tk.StringVar(value="0.0 FPS")
        tk.Label(
            source_bar,
            textvariable=self.fps_var,
            font=("Arial", 11, "bold"),
            fg="#67e8f9",
            bg="#182233",
        ).pack(side="right")

        right = tk.Frame(body, bg="#0b1220")
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)

        self.status_card = tk.Frame(right, bg="#1f2937", padx=20, pady=16)
        self.status_card.grid(row=0, column=0, sticky="ew")
        self.state_var = tk.StringVar(value="尚未开始")
        self.state_label = tk.Label(
            self.status_card,
            textvariable=self.state_var,
            font=("Arial", 28, "bold"),
            fg="#94a3b8",
            bg="#1f2937",
        )
        self.state_label.pack(anchor="w")
        self.state_detail_var = tk.StringVar(value="点击开始监测，系统会先校准约5秒")
        self.state_detail_label = tk.Label(
            self.status_card,
            textvariable=self.state_detail_var,
            font=("Arial", 11),
            fg="#cbd5e1",
            bg="#1f2937",
            justify="left",
            wraplength=390,
        )
        self.state_detail_label.pack(anchor="w", pady=(5, 0))

        metrics = tk.Frame(right, bg="#0b1220")
        metrics.grid(row=1, column=0, sticky="ew", pady=12)
        for column in range(2):
            metrics.columnconfigure(column, weight=1)
        self.metric_vars: Dict[str, object] = {}
        metric_specs = [
            ("face", "人脸", "--"),
            ("ear", "EAR 眼睛", "--"),
            ("mar", "MAR 嘴巴", "--"),
            ("perclos", "PERCLOS", "--"),
            ("closed", "持续闭眼", "--"),
            ("yawns", "近期哈欠", "--"),
        ]
        for index, (key, title, default) in enumerate(metric_specs):
            card = tk.Frame(metrics, bg="#172033", padx=14, pady=11)
            card.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=(0, 6) if index % 2 == 0 else (6, 0),
                pady=5,
            )
            tk.Label(
                card,
                text=title,
                font=("Arial", 10),
                fg="#94a3b8",
                bg="#172033",
            ).pack(anchor="w")
            variable = tk.StringVar(value=default)
            self.metric_vars[key] = variable
            tk.Label(
                card,
                textvariable=variable,
                font=("Arial", 18, "bold"),
                fg="#f8fafc",
                bg="#172033",
            ).pack(anchor="w", pady=(4, 0))

        events_card = tk.Frame(right, bg="#111827", padx=12, pady=10)
        events_card.grid(row=2, column=0, sticky="nsew")
        right.rowconfigure(2, weight=1)
        tk.Label(
            events_card,
            text="事件提示",
            font=("Arial", 12, "bold"),
            fg="#e2e8f0",
            bg="#111827",
        ).pack(anchor="w", pady=(0, 6))
        self.event_text = tk.Text(
            events_card,
            height=8,
            bg="#111827",
            fg="#cbd5e1",
            insertbackground="#ffffff",
            borderwidth=0,
            font=("Arial", 10),
            wrap="word",
            state="disabled",
        )
        self.event_text.pack(fill="both", expand=True)

        controls = tk.Frame(self.root, bg="#0b1220", padx=24, pady=18)
        controls.pack(fill="x")
        self.start_button = self.ttk.Button(
            controls, text="开始监测", style="Primary.TButton", command=self.start
        )
        self.start_button.pack(side="left")
        self.stop_button = self.ttk.Button(
            controls, text="停止", style="Danger.TButton", command=self.stop
        )
        self.stop_button.pack(side="left", padx=10)
        self.calibrate_button = self.ttk.Button(
            controls,
            text="重新校准",
            style="Secondary.TButton",
            command=self.recalibrate,
        )
        self.calibrate_button.pack(side="left")
        self.camera_button = self.ttk.Button(
            controls,
            text="使用摄像头",
            style="Secondary.TButton",
            command=self.use_camera,
        )
        self.camera_button.pack(side="right")
        self.video_button = self.ttk.Button(
            controls,
            text="选择视频…",
            style="Secondary.TButton",
            command=self.choose_video,
        )
        self.video_button.pack(side="right", padx=10)

    def _set_running_controls(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.calibrate_button.configure(state="normal" if running else "disabled")
        self.video_button.configure(state="disabled" if running else "normal")
        self.camera_button.configure(state="disabled" if running else "normal")

    def choose_video(self) -> None:
        from tkinter import filedialog

        selected = filedialog.askopenfilename(
            title="选择测试视频",
            filetypes=[("视频文件", "*.mp4 *.mov *.avi *.mkv"), ("全部文件", "*")],
        )
        if selected:
            self.selected_video = Path(selected)
            self.source_var.set("输入：{}".format(self.selected_video.name))

    def use_camera(self) -> None:
        self.selected_video = None
        self.source_var.set("输入：Mac 摄像头 {}".format(self.base_config.camera.index))

    def start(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        config = self.base_config
        self.worker = MonitorWorker(
            config=config,
            project_root=self.project_root,
            frame_queue=self.frame_queue,
            event_queue=self.event_queue,
            video_path=self.selected_video,
        )
        self._set_running_controls(True)
        self.state_var.set("正在启动")
        self.state_detail_var.set("正在打开输入和加载人脸模型…")
        self.worker.start()

    def stop(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self._set_running_controls(False)
        self.state_var.set("已停止")
        self.state_detail_var.set("摄像头正在释放，可以再次开始监测")

    def recalibrate(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.worker.recalibrate()

    def _append_event(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_text.configure(state="normal")
        self.event_text.insert("end", "[{}] {}\n".format(timestamp, message))
        self.event_text.see("end")
        self.event_text.configure(state="disabled")

    def _update_video(self, result: RuntimeFrame) -> None:
        from PIL import Image, ImageTk

        frame = result.frame.copy()
        if result.snapshot is None:
            color = (60, 190, 255)
        else:
            color = STATE_BGR_COLORS[result.snapshot.state]
        draw_face_landmarks(frame, result.signals, color)

        rgb = frame[:, :, ::-1]
        image = Image.fromarray(rgb)
        target_width = max(640, self.video_label.winfo_width())
        target_height = max(360, self.video_label.winfo_height())
        image.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
        background = Image.new("RGB", (target_width, target_height), "#111827")
        position = (
            (target_width - image.width) // 2,
            (target_height - image.height) // 2,
        )
        background.paste(image, position)
        self._photo = ImageTk.PhotoImage(background)
        self.video_label.configure(image=self._photo, text="")

    def _update_metrics(self, result: RuntimeFrame) -> None:
        self.fps_var.set("{:.1f} FPS".format(result.fps))
        self.metric_vars["face"].set("已检测" if result.signals is not None else "未检测")
        self.metric_vars["ear"].set(
            "{:.3f}".format(result.signals.ear) if result.signals is not None else "--"
        )
        self.metric_vars["mar"].set(
            "{:.3f}".format(result.signals.mar) if result.signals is not None else "--"
        )

        if result.snapshot is None:
            color = "#38bdf8"
            self.status_card.configure(bg="#12324a")
            self.state_label.configure(bg="#12324a", fg=color)
            self.state_detail_label.configure(bg="#12324a")
            self.state_var.set("正在个人校准")
            if result.signals is None:
                detail = "请让脸完整出现在画面中"
            else:
                detail = "正常睁眼、闭嘴看镜头，还需约 {:.1f} 秒（{}帧）".format(
                    result.calibration_remaining_seconds,
                    result.calibration_sample_count,
                )
            self.state_detail_var.set(detail)
            self.metric_vars["perclos"].set("等待校准")
            self.metric_vars["closed"].set("--")
            self.metric_vars["yawns"].set("--")
            return

        snapshot = result.snapshot
        color = STATE_COLORS[snapshot.state]
        self.status_card.configure(bg="#1f2937")
        self.state_label.configure(bg="#1f2937", fg=color)
        self.state_detail_label.configure(bg="#1f2937")
        self.state_var.set(STATE_NAMES[snapshot.state])
        reasons = "、".join(REASON_LABELS.get(item, item) for item in snapshot.reasons)
        self.state_detail_var.set(reasons or "当前没有检测到持续疲劳信号")
        self.metric_vars["perclos"].set("{:.1%}".format(snapshot.perclos))
        self.metric_vars["closed"].set("{:.1f} 秒".format(snapshot.eye_closed_seconds))
        self.metric_vars["yawns"].set("{} 次".format(snapshot.recent_yawn_count))

    def _handle_event(self, kind: str, payload) -> None:
        if kind == "started":
            self._append_event("监测已启动，正在进行个人校准。")
        elif kind == "recalibrating":
            self._append_event("已重新开始校准，请正常睁眼并闭嘴。")
        elif kind == "calibrated":
            self._append_event(
                "校准完成：EAR阈值 {:.3f}，MAR阈值 {:.3f}。".format(
                    payload.ear_closed_threshold, payload.mar_open_threshold
                )
            )
        elif kind == "state":
            reasons = "、".join(REASON_LABELS.get(item, item) for item in payload.reasons)
            self._append_event(
                "状态变为 {}{}".format(
                    STATE_NAMES[payload.state], "：" + reasons if reasons else ""
                )
            )
        elif kind == "ended":
            self._append_event("视频处理完成或输入已经结束。")
        elif kind == "error":
            self._append_event("运行错误：{}".format(payload))
            self.state_var.set("启动失败")
            self.state_detail_var.set(str(payload))
        elif kind == "stopped":
            self._set_running_controls(False)

    def _poll(self) -> None:
        latest = None
        try:
            while True:
                latest = self.frame_queue.get_nowait()
        except Empty:
            pass
        if latest is not None:
            self._update_video(latest)
            self._update_metrics(latest)

        try:
            while True:
                kind, payload = self.event_queue.get_nowait()
                self._handle_event(kind, payload)
        except Empty:
            pass
        self.root.after(30, self._poll)

    def close(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.worker.join(timeout=2.0)
        self.root.destroy()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EE6008 desktop monitoring dashboard")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/default.yaml"),
        help="YAML configuration file",
    )
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Start the configured camera immediately after opening the dashboard",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        import tkinter as tk
    except ImportError as exc:
        raise RuntimeError(
            "Tkinter is missing. On Homebrew Python 3.11 run "
            "'brew install python-tk@3.11'."
        ) from exc

    root = tk.Tk()
    dashboard = DriverMonitorDashboard(root, args.config)
    if args.autostart:
        root.after(300, dashboard.start)
    root.mainloop()


if __name__ == "__main__":
    main()
