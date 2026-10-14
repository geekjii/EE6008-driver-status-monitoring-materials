import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from driver_monitor.devices import resolve_torch_device


def fake_torch(cuda_available=False, cuda_count=0, mps_available=False):
    return SimpleNamespace(
        cuda=SimpleNamespace(
            is_available=lambda: cuda_available,
            device_count=lambda: cuda_count,
        ),
        backends=SimpleNamespace(
            mps=SimpleNamespace(is_available=lambda: mps_available)
        ),
    )


class DeviceSelectionTests(unittest.TestCase):
    def test_auto_prefers_cuda(self):
        selected = resolve_torch_device(
            "auto", fake_torch(cuda_available=True, cuda_count=1, mps_available=True)
        )
        self.assertEqual(selected.resolved, "cuda:0")
        self.assertTrue(selected.accelerated)

    def test_auto_uses_mps_when_cuda_is_unavailable(self):
        selected = resolve_torch_device("auto", fake_torch(mps_available=True))
        self.assertEqual(selected.resolved, "mps")

    def test_explicit_unavailable_accelerator_falls_back_to_cpu(self):
        selected = resolve_torch_device("cuda:0", fake_torch())
        self.assertEqual(selected.resolved, "cpu")
        self.assertTrue(selected.fallback)

    def test_missing_cuda_index_falls_back_to_cpu(self):
        selected = resolve_torch_device(
            "cuda:2", fake_torch(cuda_available=True, cuda_count=1)
        )
        self.assertEqual(selected.resolved, "cpu")

    def test_invalid_device_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            resolve_torch_device("tpu", fake_torch())


if __name__ == "__main__":
    unittest.main()
