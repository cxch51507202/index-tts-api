from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api_server.controller import create_controller_app


class LocalControllerTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch("api_server.controller._task_info", return_value={"state": "Ready", "enabled": True}),
            patch("api_server.controller._service_info", return_value={"status": "Running", "start_type": "Automatic"}),
            patch("api_server.controller._listener_pid", return_value=8123),
            patch("api_server.controller._api_process_info", return_value={"pid": 8123, "name": "python.exe"}),
            patch(
                "api_server.controller._probe",
                side_effect=lambda url, timeout=1.5: {
                    "reachable": url.endswith("20241/ready"),
                    "status_code": 200,
                    "latency_ms": 1,
                    "error": None,
                },
            ),
            patch("api_server.controller._start_api", return_value={"ok": True, "message": "started"}),
            patch("api_server.controller._stop_api", return_value={"ok": True, "message": "stopped"}),
            patch("api_server.controller._restart_api", return_value={"ok": True, "message": "restarted"}),
            patch("api_server.controller._service_action", return_value={"ok": True, "message": "done"}),
            patch("api_server.controller._run", return_value=(0, "ok")),
        ]
        for current in self.patches:
            current.start()
        self.app = create_controller_app()

    def tearDown(self):
        for current in reversed(self.patches):
            current.stop()

    def test_local_status_and_page_are_available(self):
        with TestClient(self.app, client=("127.0.0.1", 50000)) as client:
            response = client.get("/status")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["api"]["phase"], "starting")
            page = client.get("/admin")
            self.assertEqual(page.status_code, 200)
            self.assertIn("IndexTTS 本机控制台", page.text)

    def test_mutating_actions_require_the_page_token(self):
        with TestClient(self.app, client=("127.0.0.1", 50000)) as client:
            self.assertEqual(client.post("/api/start").status_code, 403)
            token = self.app.state.control_token
            response = client.post("/api/start", headers={"x-index-tts-controller-token": token})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["ok"])

    def test_non_loopback_clients_are_hidden(self):
        with TestClient(self.app, client=("10.0.0.2", 50000)) as client:
            self.assertEqual(client.get("/status").status_code, 404)
            self.assertEqual(client.get("/admin").status_code, 404)


if __name__ == "__main__":
    unittest.main()
