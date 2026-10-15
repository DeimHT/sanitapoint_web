"""Arranque sin interfaz para el Programador de tareas de Windows."""
import argparse
import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="IPv4 fija de la interfaz de la red interna")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--runtime", type=Path, help="JSON externo con python y revision de la version activa")
    args = parser.parse_args()
    runtime = json.loads(args.runtime.read_text(encoding="utf-8-sig")) if args.runtime else {}
    python = runtime.get("python", sys.executable)
    entorno = os.environ.copy()
    entorno["SANITAPOINT_REVISION"] = runtime.get("revision", "local")
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    with (logs / f"servidor-{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8") as log:
        log.write(f"\nInicio: {datetime.now().isoformat()}\n")
        log.flush()
        return subprocess.call(
            [python, "-m", "uvicorn", "app.main:app", "--host", args.host,
             "--port", str(args.port), "--workers", "1"],
            cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, env=entorno,
        )


if __name__ == "__main__":
    sys.exit(main())
