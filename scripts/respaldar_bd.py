"""Respaldo consistente de la base SQLite, incluso con ventas en curso."""
import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
from datetime import datetime
import uuid

ROOT = Path(__file__).resolve().parents[1]


def respaldar(origen: Path, destino: Path) -> Path:
    origen = origen.resolve(strict=True)
    destino.mkdir(parents=True, exist_ok=True)
    nombre = f"sanitapoint-{datetime.now():%Y-%m-%d_%H-%M-%S}-{uuid.uuid4().hex[:8]}.db"
    final = destino / nombre
    temporal = destino / (nombre + ".parcial")
    try:
        with closing(sqlite3.connect(origen.as_uri() + "?mode=ro", uri=True, timeout=30)) as fuente:
            with closing(sqlite3.connect(temporal)) as copia:
                fuente.backup(copia, pages=256, sleep=0.1)
                resultado = copia.execute("PRAGMA integrity_check").fetchall()
                if resultado != [("ok",)]:
                    raise RuntimeError(f"Respaldo no valido: {resultado}")
        os.replace(temporal, final)
        return final
    except BaseException:
        temporal.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destino", type=Path, required=True)
    parser.add_argument("--origen", type=Path, default=ROOT / "data" / "sanitapoint.db")
    args = parser.parse_args()
    print(f"Respaldo verificado: {respaldar(args.origen, args.destino)}", flush=True)


if __name__ == "__main__":
    main()
