"""Ejecuta un archivo .sql contra la DATABASE_URL del .env.

Uso:
    python run_migration.py migrations/002_monitor_outbound.sql
    python run_migration.py migrations/*.sql
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

import os

DATABASE_URL = os.getenv("DATABASE_URL")


def run_file(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    print(f"→ Ejecutando {path.name} ({len(sql)} bytes)")
    with psycopg2.connect(DATABASE_URL, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print(f"✔ {path.name} OK")


def main() -> int:
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL no está en el .env", file=sys.stderr)
        return 2
    if len(sys.argv) < 2:
        print("Uso: python run_migration.py <archivo.sql> [<archivo2.sql> ...]", file=sys.stderr)
        return 2

    files: list[Path] = []
    for arg in sys.argv[1:]:
        # Soporta glob (útil para *.sql)
        matches = glob.glob(arg)
        if not matches:
            print(f"ERROR: no se encontró {arg}", file=sys.stderr)
            return 2
        files.extend(Path(m) for m in matches)

    for f in sorted(set(files)):
        if not f.is_file() or f.suffix.lower() != ".sql":
            print(f"skip {f} (no es .sql)")
            continue
        run_file(f)

    print("\nListo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
