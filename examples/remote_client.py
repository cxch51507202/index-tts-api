from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="API base URL")
    parser.add_argument("--key", required=True, help="API key")
    parser.add_argument("--voice", default="wang_liqun")
    parser.add_argument("--text", required=True)
    parser.add_argument("--output", default="output.wav")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    headers = {"Authorization": f"Bearer {args.key}"}
    response = requests.post(
        f"{base}/api/v1/tts", headers=headers,
        json={"voice": args.voice, "text": args.text}, timeout=30,
    )
    response.raise_for_status()
    task = response.json()
    print(f"submitted: sequence={task['sequence']} id={task['id']}")

    while True:
        status = requests.get(f"{base}/api/v1/tasks/{task['id']}", headers=headers, timeout=30)
        status.raise_for_status()
        task = status.json()
        position = task.get("queue_position")
        position_text = f", queue_position={position}" if position is not None else ""
        print(f"sequence={task['sequence']} id={task['id']}: {task['status']}{position_text}")
        if task["status"] == "succeeded":
            break
        if task["status"] == "failed":
            raise RuntimeError(task.get("error") or "generation failed")
        time.sleep(1)

    audio_url = task.get("audio_url") or f"{base}{task['audio_path']}"
    audio = requests.get(audio_url, headers=headers, timeout=60)
    audio.raise_for_status()
    Path(args.output).write_bytes(audio.content)
    print(f"saved: {args.output}")


if __name__ == "__main__":
    main()
