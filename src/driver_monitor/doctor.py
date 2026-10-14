"""Read-only cross-platform environment diagnostics for people and AI agents."""

import argparse
import importlib.util
import json
import os
import platform
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .config import load_config
from .devices import resolve_torch_device


PACKAGE_NAMES = {
    "fastapi": "fastapi",
    "mediapipe": "mediapipe",
    "numpy": "numpy",
    "cv2": "opencv-contrib-python",
    "PIL": "Pillow",
    "yaml": "PyYAML",
    "uvicorn": "uvicorn",
    "torch": "torch",
    "torchvision": "torchvision",
    "ultralytics": "ultralytics",
}


def _package_report(import_name: str, distribution_name: str) -> Dict[str, Any]:
    available = importlib.util.find_spec(import_name) is not None
    version: Optional[str] = None
    if available:
        try:
            version = metadata.version(distribution_name)
        except metadata.PackageNotFoundError:
            version = "unknown"
    return {"available": available, "version": version}


def _resolve_path(project_root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (project_root / path).resolve()


def _file_report(path: Path) -> Dict[str, Any]:
    exists = path.is_file()
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": path.stat().st_size if exists else None,
    }


def _writable_parent(path: Path) -> bool:
    parent = path.parent
    while not parent.exists() and parent != parent.parent:
        parent = parent.parent
    return parent.is_dir() and os.access(parent, os.W_OK)


def _camera_report(index: int) -> Dict[str, Any]:
    try:
        import cv2
    except ImportError:
        return {"checked": True, "opened": False, "reason": "OpenCV 未安装"}
    capture = cv2.VideoCapture(index)
    try:
        opened = bool(capture.isOpened())
    finally:
        capture.release()
    return {
        "checked": True,
        "opened": opened,
        "reason": "摄像头可以打开" if opened else "摄像头无法打开或尚未授权",
    }


def build_report(
    project_root: Path,
    config_path: Path,
    check_camera: bool = False,
) -> Dict[str, Any]:
    project_root = project_root.expanduser().resolve()
    config_path = config_path.expanduser()
    if not config_path.is_absolute():
        config_path = project_root / config_path
    config_path = config_path.resolve()

    packages = {
        name: _package_report(name, distribution)
        for name, distribution in PACKAGE_NAMES.items()
    }
    errors = []
    config = None
    try:
        config = load_config(config_path)
    except Exception as exc:
        errors.append("配置读取失败：{}".format(exc))

    files: Dict[str, Any] = {"config": _file_report(config_path)}
    selected_device = None
    output = None
    camera = {"checked": False, "opened": None, "reason": "未请求摄像头检查"}
    if config is not None:
        face_model = _resolve_path(project_root, config.face.model_path)
        files["face_model"] = _file_report(face_model)
        if not files["face_model"]["exists"]:
            errors.append("缺少人脸模型：{}".format(face_model))
        if config.phone.enabled:
            phone_model = _resolve_path(project_root, config.phone.model_path)
            files["phone_model"] = _file_report(phone_model)
            if not files["phone_model"]["exists"]:
                errors.append("缺少手机检测模型：{}".format(phone_model))
            selected_device = resolve_torch_device(config.phone.device).as_dict()
        output_path = _resolve_path(project_root, config.output.events_path)
        output = {
            "path": str(output_path),
            "parent_writable": _writable_parent(output_path),
        }
        if not output["parent_writable"]:
            errors.append("日志目录不可写：{}".format(output_path.parent))
        if check_camera:
            camera = _camera_report(config.camera.index)

    required_imports = ["fastapi", "mediapipe", "numpy", "cv2", "PIL", "yaml", "uvicorn"]
    if config is not None and config.phone.enabled:
        required_imports.extend(["torch", "torchvision", "ultralytics"])
    for name in required_imports:
        if not packages[name]["available"]:
            errors.append("缺少 Python 依赖：{}".format(name))

    python_ok = sys.version_info[:2] == (3, 11)
    if not python_ok:
        errors.append("需要 Python 3.11，当前为 {}".format(platform.python_version()))

    return {
        "ok": not errors,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
            "supported": python_ok,
        },
        "project_root": str(project_root),
        "packages": packages,
        "files": files,
        "inference_device": selected_device,
        "output": output,
        "camera": camera,
        "errors": errors,
    }


def _print_human(report: Dict[str, Any]) -> None:
    status = "可以运行" if report["ok"] else "需要处理"
    print("环境诊断：{}".format(status))
    print(
        "系统：{system} {release} ({machine})".format(**report["platform"])
    )
    print("Python：{}".format(report["python"]["version"]))
    device = report.get("inference_device")
    if device is not None:
        print("手机检测设备：{}".format(device["resolved"]))
        print("设备说明：{}".format(device["reason"]))
    print("摄像头：{}".format(report["camera"]["reason"]))
    if report["errors"]:
        print("发现的问题：")
        for error in report["errors"]:
            print("- {}".format(error))
    else:
        print("配置、依赖和本地模型检查通过。")


def build_parser() -> argparse.ArgumentParser:
    default_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="检查 EE6008 项目运行环境")
    parser.add_argument("--project-root", type=Path, default=default_root)
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    parser.add_argument("--camera", action="store_true", help="实际尝试打开并立即释放摄像头")
    parser.add_argument("--json", action="store_true", help="输出便于 AI 读取的 JSON")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(args.project_root, args.config, args.camera)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
