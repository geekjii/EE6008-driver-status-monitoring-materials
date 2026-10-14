"""Cross-platform inference device selection with an explicit CPU fallback."""

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class DeviceSelection:
    requested: str
    resolved: str
    accelerated: bool
    fallback: bool
    reason: str

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_torch(torch_module: Optional[Any]) -> Optional[Any]:
    if torch_module is not None:
        return torch_module
    try:
        import torch
    except ImportError:
        return None
    return torch


def _mps_available(torch_module: Any) -> bool:
    backend = getattr(getattr(torch_module, "backends", None), "mps", None)
    return bool(backend is not None and backend.is_available())


def _cuda_available(torch_module: Any) -> bool:
    cuda = getattr(torch_module, "cuda", None)
    return bool(cuda is not None and cuda.is_available())


def resolve_torch_device(
    requested: str = "auto", torch_module: Optional[Any] = None
) -> DeviceSelection:
    """Resolve an Ultralytics/PyTorch device without assuming one platform.

    Explicit CUDA or MPS requests fall back to CPU when the backend is not
    available. Invalid device names are rejected so configuration mistakes do
    not silently change inference behavior.
    """

    value = str(requested or "auto").strip().lower()
    if value == "gpu":
        value = "cuda"
    if value.isdigit():
        value = "cuda:{}".format(value)
    if value == "cuda":
        value = "cuda:0"
    if value not in {"auto", "cpu", "mps"} and not value.startswith("cuda:"):
        raise ValueError(
            "Unsupported inference device {!r}; use auto, cpu, mps, cuda, or "
            "cuda:<index>.".format(requested)
        )
    if value.startswith("cuda:") and not value.split(":", 1)[1].isdigit():
        raise ValueError("CUDA device index must be a non-negative integer")

    if value == "cpu":
        return DeviceSelection(
            requested=str(requested),
            resolved="cpu",
            accelerated=False,
            fallback=False,
            reason="已按配置使用 CPU。",
        )

    torch_runtime = _load_torch(torch_module)
    if torch_runtime is None:
        return DeviceSelection(
            requested=str(requested),
            resolved="cpu",
            accelerated=False,
            fallback=value != "auto",
            reason="未安装 PyTorch，设备检查退回 CPU。",
        )

    if value == "auto":
        if _cuda_available(torch_runtime):
            return DeviceSelection(
                requested=str(requested),
                resolved="cuda:0",
                accelerated=True,
                fallback=False,
                reason="自动选择了可用的 NVIDIA CUDA。",
            )
        if _mps_available(torch_runtime):
            return DeviceSelection(
                requested=str(requested),
                resolved="mps",
                accelerated=True,
                fallback=False,
                reason="自动选择了可用的 Apple MPS。",
            )
        return DeviceSelection(
            requested=str(requested),
            resolved="cpu",
            accelerated=False,
            fallback=False,
            reason="未发现可用的 CUDA 或 MPS，自动使用 CPU。",
        )

    if value == "mps":
        if _mps_available(torch_runtime):
            return DeviceSelection(
                requested=str(requested),
                resolved="mps",
                accelerated=True,
                fallback=False,
                reason="Apple MPS 可用。",
            )
        return DeviceSelection(
            requested=str(requested),
            resolved="cpu",
            accelerated=False,
            fallback=True,
            reason="Apple MPS 不可用，已安全退回 CPU。",
        )

    if _cuda_available(torch_runtime):
        index_text = value.split(":", 1)[1]
        index = int(index_text)
        device_count = getattr(torch_runtime.cuda, "device_count", lambda: index + 1)()
        if index < int(device_count):
            return DeviceSelection(
                requested=str(requested),
                resolved="cuda:{}".format(index),
                accelerated=True,
                fallback=False,
                reason="NVIDIA CUDA 设备 {} 可用。".format(index),
            )
        reason = "CUDA 可用，但不存在编号为 {} 的显卡，已退回 CPU。".format(index)
    else:
        reason = "NVIDIA CUDA 不可用，已安全退回 CPU。"
    return DeviceSelection(
        requested=str(requested),
        resolved="cpu",
        accelerated=False,
        fallback=True,
        reason=reason,
    )
