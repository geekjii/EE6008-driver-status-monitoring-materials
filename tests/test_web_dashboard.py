import sys
import unittest
from pathlib import Path
from dataclasses import replace
import tempfile
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from driver_monitor.web_dashboard import WebMonitorService, create_app
from driver_monitor.session_recording import SessionRecorder
from driver_monitor.fatigue_engine import FatigueEngine
from driver_monitor.runtime import RuntimeFrame


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

    def test_export_endpoint_saves_package_and_report_without_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            service = WebMonitorService(PROJECT_ROOT / "configs" / "default.yaml")
            service.config = replace(service.config, output=replace(service.config.output, sessions_path=directory))
            app = create_app(PROJECT_ROOT / "configs" / "default.yaml")
            app.state.monitor = service
            client = TestClient(app)
            self.assertEqual(client.post("/api/export").status_code, 409)
            recorder = SessionRecorder(Path(directory), service.config, 0, "cpu")
            service._recorder = recorder
            try:
                engine = FatigueEngine(service.config.fatigue)
                snapshot = engine.update(0, False, None, None)
                recorder.record(RuntimeFrame(None, None, snapshot, 0, 0, 0, None, timestamp=0), service.config.fatigue)
                response = client.post("/api/export")
                self.assertEqual(response.status_code, 200)
                exported = response.json()
                self.assertEqual(client.get(exported["report_url"]).status_code, 200)
                self.assertIn("监测结果与时间曲线", client.get(exported["report_url"]).text)
                self.assertTrue(client.get(exported["download_url"]).content.startswith(b"PK"))
                self.assertEqual(client.get("/api/status").json()["session"]["frames"], 1)
                self.assertFalse(client.get("/api/status").json()["running"])
                prefix = exported["report_url"].rsplit("/", 1)[0]
                self.assertEqual(client.get(prefix + "/%E7%9B%91%E6%B5%8B%E6%95%B0%E6%8D%AE.csv").status_code, 200)
                with self.assertRaises(ValueError):
                    service.export_file("监测_/../../../../", "导出_../../", "report")
            finally:
                recorder.finish()


if __name__ == "__main__":
    unittest.main()
