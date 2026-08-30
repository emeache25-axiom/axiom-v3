#!/usr/bin/env python3
"""
AXIOM v3 — Captura del funding de BTC.

    python scripts/capturar_funding.py capturar --completo   # desde 2020
    python scripts/capturar_funding.py capturar              # solo lo que falta
    python scripts/capturar_funding.py estado
"""
from __future__ import annotations

import os, sys, asyncio, logging, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from backend.captura import funding

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def _dsn() -> str:
    d = os.environ.get("DATABASE_URL")
    if d:
        return d
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for l in env.read_text().splitlines():
            if l.strip().startswith("DATABASE_URL="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: falta DATABASE_URL", file=sys.stderr); sys.exit(1)


async def main(que: str, completo: bool) -> None:
    pool = await asyncpg.create_pool(_dsn())
    try:
        if que in ("capturar", "todo"):
            print("captura:", await funding.capturar(pool, completo))
        if que in ("estado", "todo"):
            print("\nestado del funding:")
            for k, v in (await funding.estado(pool)).items():
                print(f"  {k:<28} {v}")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("que", choices=["capturar", "estado", "todo"])
    ap.add_argument("--completo", action="store_true",
                    help="desde 2020 en vez de solo lo que falta")
    a = ap.parse_args()
    asyncio.run(main(a.que, a.completo))
