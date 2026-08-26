#!/usr/bin/env python3
"""
AXIOM v3 — Captura de la serie de Bitcoin.

    python scripts/capturar_btc.py diarias --completo   # backfill desde 2017
    python scripts/capturar_btc.py horarias --completo   # ~80.000 velas
    python scripts/capturar_btc.py diarias               # solo lo que falta
    python scripts/capturar_btc.py estado
"""
from __future__ import annotations

import os, sys, asyncio, logging, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from backend.captura import bitcoin

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
        if que in ("diarias", "todo"):
            print("diarias :", await bitcoin.capturar_diarias(pool, completo))
        if que in ("horarias", "todo"):
            print("horarias:", await bitcoin.capturar_horarias(pool, completo))
        if que in ("estado", "todo"):
            e = await bitcoin.estado(pool)
            print("\nestado de la serie de BTC:")
            for k, v in e.items():
                if isinstance(v, dict):
                    print(f"  {k}:")
                    for k2, v2 in v.items():
                        print(f"      {k2:<16} {v2}")
                else:
                    print(f"  {k:<18} {v}")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("que", choices=["diarias", "horarias", "todo", "estado"])
    ap.add_argument("--completo", action="store_true",
                    help="trae toda la historia desde 2017 en vez de solo lo que falta")
    a = ap.parse_args()
    asyncio.run(main(a.que, a.completo))
