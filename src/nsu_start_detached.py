"""Start a detached NSU process and print its PID. Avoids shell $! quoting issues."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit("usage: nsu_start_detached.py LOG_PATH CMD...")
    log_path = Path(sys.argv[1])
    cmd = sys.argv[2:]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handle = log_path.open("ab")
    proc = subprocess.Popen(
        cmd,
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        cwd=str(Path(cmd[1]).parent if len(cmd) > 1 else os.getcwd()),
    )
    print(proc.pid)


if __name__ == "__main__":
    main()
