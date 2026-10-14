import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from driver_monitor.web_dashboard import WebMonitorService, create_app


class WebDashboardTests(unittest.TestCase):
    def test_service_starts_in_private_idle_state(self):
        service = WebMonitorService(PROJECT_ROOT / "configs" / "default.yaml")
        status = service.snapshot()
        self.assertEqual(status["phase"], "idle")
        self.assertFalse(status["running"])

    def test_app_exposes_local_control_and_video_routes(self):
        app = create_app(PROJECT_ROOT / "configs" / "default.yaml")
        paths = {route.path for route in app.routes}
        self.assertTrue(
            {"/", "/api/status", "/api/start", "/api/stop", "/api/video"}
            <= paths
        )


if __name__ == "__main__":
    unittest.main()
