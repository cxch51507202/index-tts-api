from __future__ import annotations

import runpy
import sys
import traceback
from datetime import datetime
from pathlib import Path


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    with (log_dir / "api-server.log").open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = log
        sys.stderr = log
        print(f"\n[{datetime.now().isoformat(timespec='seconds')}] Starting IndexTTS API")
        try:
            runpy.run_module("api_server", run_name="__main__")
        except BaseException:
            traceback.print_exc(file=log)
            raise


if __name__ == "__main__":
    main()
