from __future__ import annotations

import json
import tempfile
import time
import unittest
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from api_server.app import create_app
from api_server.schemas import GenerationSettings
from api_server.settings import Settings


class FakeEngine:
    model_version = "test"
    device = "cpu"

    def __init__(self, model_dir: Path):
        self.model_dir = model_dir

    def synthesize(self, prompt: Path, text: str, output: Path, settings: GenerationSettings) -> Path:
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * 2400)
        return output


class APIServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        prompts = root / "prompts"
        prompts.mkdir()
        prompt = prompts / "voice.wav"
        self.prompt = prompt
        with wave.open(str(prompt), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(24000)
            wav.writeframes(b"\x00\x00" * 24000 * 4)
        voices = root / "voices.json"
        voices.write_text(json.dumps({"voices": [{
            "code": "test_voice", "name": "测试音色",
            "audio_path": "prompts/voice.wav", "enabled": True,
            "defaults": GenerationSettings().model_dump(),
        }]}, ensure_ascii=False), encoding="utf-8")
        data = root / "data"
        data.mkdir()
        (data / "api_key.txt").write_text("test-key\n", encoding="utf-8")
        self.settings = Settings(
            root_dir=root, model_dir=root / "checkpoints", voices_file=voices, data_dir=data,
            output_dir=root / "outputs", api_key_file=data / "api_key.txt",
            database_file=data / "tasks.sqlite3", host="127.0.0.1", port=7870,
            public_base_url="https://api.example.test", max_text_length=200,
            task_retention_days=7, sync_timeout_seconds=5, allowed_origins=(),
        )
        self.client_context = TestClient(create_app(self.settings, FakeEngine))
        self.client = self.client_context.__enter__()
        self.client.app.state.tunnel_probe = lambda url, timeout: {
            "reachable": True,
            "status_code": 200,
            "latency_ms": 1,
            "error": None,
        }
        self.headers = {"Authorization": "Bearer test-key"}

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        self.temp.cleanup()

    def wait_for_task(self, task_id: str):
        for _ in range(50):
            response = self.client.get(f"/api/v1/tasks/{task_id}", headers=self.headers)
            if response.json()["status"] in {"succeeded", "failed"}:
                return response
            time.sleep(0.02)
        self.fail("task did not finish")

    def test_authentication_and_voice_listing(self):
        self.assertEqual(self.client.get("/api/v1/voices").status_code, 401)
        response = self.client.get("/api/v1/voices", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["code"], "test_voice")
        self.assertNotIn("audio_path", response.json()[0])

    def test_local_admin_page(self):
        self.assertEqual(self.client.get("/admin").status_code, 404)
        response = self.client.get("/admin", headers={"Host": "127.0.0.1:7870"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("IndexTTS 音色管理", response.text)

    def test_health_supports_browser_page_and_json_clients(self):
        response = self.client.get("/health", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("IndexTTS 运行状态", response.text)
        response = self.client.get("/health?format=json", headers={"Accept": "text/html"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_full_health_status_reports_tunnel_and_public_reachability(self):
        response = self.client.get("/health/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["tunnel_ready"])
        self.assertTrue(body["public_reachable"])
        self.assertEqual(body["connector"]["status_code"], 200)
        self.assertEqual(body["public"]["status_code"], 200)

    def test_local_api_requests_do_not_require_a_key(self):
        response = self.client.get("/api/v1/voices", headers={"Host": "127.0.0.1:7870"})
        self.assertEqual(response.status_code, 200)
        response = self.client.get(
            "/api/v1/voices",
            headers={"Host": "127.0.0.1:7870", "CF-Ray": "public-request"},
        )
        self.assertEqual(response.status_code, 401)

    def test_async_generation_and_download(self):
        response = self.client.post("/api/v1/tts", headers=self.headers, json={
            "voice": "test_voice", "text": "你好，API。",
            "settings": {"temperature": 0.9},
        })
        self.assertEqual(response.status_code, 202)
        finished = self.wait_for_task(response.json()["id"])
        self.assertEqual(finished.json()["status"], "succeeded")
        audio = self.client.get(finished.json()["audio_path"], headers=self.headers)
        self.assertEqual(audio.status_code, 200)
        self.assertTrue(audio.content.startswith(b"RIFF"))

    def test_openai_compatible_speech(self):
        response = self.client.post("/v1/audio/speech", headers=self.headers, json={
            "model": "indextts-1.5", "voice": "test_voice", "input": "同步生成",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "audio/wav")

    def test_multiple_requests_are_accepted_and_queued(self):
        def submit(index: int):
            return self.client.post("/api/v1/tts", headers=self.headers, json={
                "voice": "test_voice", "text": f"并发任务 {index}",
            })

        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(submit, range(4)))

        self.assertTrue(all(response.status_code == 202 for response in responses))
        task_ids = [response.json()["id"] for response in responses]
        sequences = [response.json()["sequence"] for response in responses]
        self.assertEqual(len(set(sequences)), 4)
        self.assertEqual(sorted(sequences), list(range(min(sequences), min(sequences) + 4)))
        finished = [self.wait_for_task(task_id) for task_id in task_ids]
        self.assertTrue(all(response.json()["status"] == "succeeded" for response in finished))

    def test_update_voice_defaults(self):
        response = self.client.patch("/api/v1/voices/test_voice", headers=self.headers, json={
            "name": "新中文名", "defaults": {"temperature": 0.7}
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "新中文名")
        self.assertEqual(response.json()["defaults"]["temperature"], 0.7)

    def test_duplicate_voice_code_is_rejected(self):
        with self.prompt.open("rb") as audio:
            response = self.client.post(
                "/api/v1/voices",
                headers=self.headers,
                data={"code": "test_voice", "name": "重复音色"},
                files={"audio": ("voice.wav", audio, "audio/wav")},
            )
        self.assertEqual(response.status_code, 409)

    def test_voice_code_is_generated_when_omitted(self):
        codes = []
        for index in range(3):
            with self.prompt.open("rb") as audio:
                response = self.client.post(
                    "/api/v1/voices",
                    headers=self.headers,
                    data={"name": f"自动编号音色 {index + 1}"},
                    files={"audio": ("voice.wav", audio, "audio/wav")},
                )
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()["defaults"]["infer_mode"], "normal")
            codes.append(response.json()["code"])
        self.assertEqual(codes, ["S-HVIE00R01", "S-HVIE00R02", "S-HVIE00R03"])


if __name__ == "__main__":
    unittest.main()
