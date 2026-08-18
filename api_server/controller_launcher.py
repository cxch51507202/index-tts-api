from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path

import uvicorn

from .controller import app


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    log_dir = base_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "local-controller.log").open("a", encoding="utf-8", buffering=1) as log:
        sys.stdout = log
        sys.stderr = log
        print(f"\n[{datetime.now().isoformat(timespec='seconds')}] Starting local controller")
        try:
            uvicorn.run(app, host="127.0.0.1", port=7871, reload=False, access_log=True)
        except BaseException:
            traceback.print_exc(file=log)
            raise


if __name__ == "__main__":
    main()
