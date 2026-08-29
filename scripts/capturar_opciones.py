#!/usr/bin/env python3
"""
AXIOM v3 — Captura de la cadena de opciones de BTC.

    python scripts/capturar_opciones.py capturar
    python scripts/capturar_opciones.py estado
"""
from __future__ import annotations

import os, sys, asyncio, logging, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from backend.captura import opciones

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


async def main(que: str) -> None:
    pool = await asyncpg.create_pool(_dsn())
    try:
        if que in ("capturar", "todo"):
            print("captura:", await opciones.capturar(pool))
        if que in ("estado", "todo"):
            e = await opciones.estado(pool)
            print("\nestado de la cadena de opciones:")
            for k, v in e.items():
                if k == "ultimos_dias":
                    print("  evolución:")
                    print(f"    {'fecha':<12}{'contratos':>11}{'interés':>14}{'put/call':>10}")
                    for d in v:
                        pc = d['put_call']
                        print(f"    {d['fecha']:<12}{d['contratos']:>11}"
                              f"{d['interes_abierto']:>14,.1f}"
                              f"{('—' if pc is None else f'{pc:.3f}'):>10}")
                else:
                    print(f"  {k:<18} {v}")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("que", choices=["capturar", "estado", "todo"])
    a = ap.parse_args()
    asyncio.run(main(a.que))
