#!/usr/bin/env python3
"""
AXIOM v3 — Captura de pares.

    python scripts/capturar_pares.py catalogo    # qué pares existen
    python scripts/capturar_pares.py velas       # historia diaria
    python scripts/capturar_pares.py metricas    # rango, oscilación, repetibilidad
    python scripts/capturar_pares.py vinculos    # par ↔ coin, solo lo inequívoco
    python scripts/capturar_pares.py todo
    python scripts/capturar_pares.py estado
"""
from __future__ import annotations

import os, sys, asyncio, logging, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from backend.captura import pares, metricas

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


async def main(que: str, limite: int | None) -> None:
    pool = await asyncpg.create_pool(_dsn())
    try:
        if que in ("catalogo", "todo"):
            print("catálogo :", await pares.catalogar(pool))
        if que in ("velas", "todo"):
            print("velas    :", await pares.capturar_velas(pool, limite_pares=limite))
        if que in ("metricas", "todo"):
            print("métricas :", await metricas.calcular(pool))
        if que in ("vinculos", "todo"):
            print("vínculos :", await metricas.vincular_con_coins(pool))
        if que in ("estado", "todo"):
            print("\nestado de pares:")
            for k, v in (await pares.estado(pool)).items():
                print(f"  {k:<16} {v}")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("que", choices=["catalogo","velas","metricas","vinculos","todo","estado"])
    ap.add_argument("--limite", type=int, default=None,
                    help="cuántos pares procesar (para probar sin esperar)")
    a = ap.parse_args()
    asyncio.run(main(a.que, a.limite))
