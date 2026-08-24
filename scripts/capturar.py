#!/usr/bin/env python3
"""
AXIOM v3 — Captura del universo de coins.

    python scripts/capturar.py inventario   # qué existe (altas y bajas)
    python scripts/capturar.py refresco     # qué vale (precio, ranking)
    python scripts/capturar.py foto         # la historia del día
    python scripts/capturar.py todo         # las tres, en orden
    python scripts/capturar.py estado       # qué sabe el sistema

El orden importa: inventario → refresco → foto. La foto retrata lo que el
refresco dejó, y el refresco no debería incluir lo que el inventario dio de baja.
"""
from __future__ import annotations

import os
import sys
import asyncio
import logging
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg

from backend.fuentes.cliente import ClienteFuentes
from backend.nucleo import config as _config
from backend.captura import universo

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL")
    if dsn:
        return dsn
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for l in env.read_text().splitlines():
            if l.strip().startswith("DATABASE_URL="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: falta DATABASE_URL", file=sys.stderr)
    sys.exit(1)


async def main(que: str, cuantas: int) -> None:
    pool = await asyncpg.create_pool(_dsn())
    cliente = ClienteFuentes()
    for f in _config.actual().fuentes.values():
        cliente.registrar(f)
    try:
        async with cliente:
            if que in ("inventario", "todo"):
                print("inventario:", await universo.inventariar(pool, cliente))
            if que in ("refresco", "todo"):
                print("refresco  :", await universo.refrescar(
                    pool, cliente, cuantas=cuantas))
            if que in ("foto", "todo"):
                print("foto      :", await universo.fotografiar(pool))
            if que in ("estado", "todo"):
                print("\nestado del universo:")
                for k, v in (await universo.estado(pool)).items():
                    print(f"  {k:<16} {v}")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Captura del universo de coins")
    ap.add_argument("que", choices=["inventario", "refresco", "foto",
                                    "todo", "estado"])
    ap.add_argument("--cuantas", type=int, default=universo.SEGUIDAS_POR_DEFECTO,
                    help="cuántas coins seguir (default: 3000)")
    a = ap.parse_args()
    asyncio.run(main(a.que, a.cuantas))
