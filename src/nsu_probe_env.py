"""Read-only NSU environment probe. No GPU reservation, no installs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def scrub(value):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            lowered = key.lower()
            if "token" in lowered or "secret" in lowered or "password" in lowered:
                out[key] = "<redacted>"
            else:
                out[key] = scrub(item)
        return out
    if isinstance(value, list):
        return [scrub(item) for item in value]
    return value


def run(cmd: list[str], timeout: int = 20) -> str:
    try:
        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        text = (completed.stdout or "") + (completed.stderr or "")
        return f"exit={completed.returncode}\n{text.strip()}"
    except Exception as exc:
        return f"failed {type(exc).__name__}: {exc}"


def main() -> None:
    home = Path("/home/scientists/gluz_d_s")
    control = home / "kaggle/_control"
    project = home / "kaggle/projects/arc-prize-2026-arc-agi-3"
    report = {
        "host": os.uname().nodename,
        "user": os.environ.get("USER"),
        "python": sys.version,
        "which": {
            name: shutil.which(name)
            for name in [
                "python3",
                "pip3",
                "uv",
                "conda",
                "virtualenv",
                "nvidia-smi",
                "quota",
                "gcc",
                "git",
                "curl",
            ]
        },
        "ensurepip": None,
        "control_exists": control.is_dir(),
        "coordination_keys": [],
        "coordination": None,
        "project_exists": project.is_dir(),
        "project_children": [],
        "manifest": None,
        "df": run(["df", "-hT", str(home)]),
        "quota": run(["quota", "-s"]),
        "du_project": run(["du", "-sh", str(project)]),
        "du_kaggle": run(["du", "-sh", str(home / "kaggle")]),
        "nvidia_smi": run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,driver_version",
                "--format=csv",
            ]
        ),
    }
    try:
        import ensurepip  # noqa: F401

        report["ensurepip"] = True
    except Exception as exc:
        report["ensurepip"] = f"{type(exc).__name__}: {exc}"

    status_path = control / "COORDINATION_STATUS.json"
    if status_path.is_file():
        data = json.loads(status_path.read_text(encoding="utf-8"))
        report["coordination_keys"] = sorted(data.keys())
        report["coordination"] = scrub(data)

    if project.is_dir():
        report["project_children"] = sorted(path.name for path in project.iterdir())
        manifest = project / "PROJECT_MANIFEST.json"
        if manifest.is_file():
            report["manifest"] = json.loads(manifest.read_text(encoding="utf-8"))

    pip3 = shutil.which("pip3")
    if pip3:
        report["pip3_version"] = run([pip3, "--version"])
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
