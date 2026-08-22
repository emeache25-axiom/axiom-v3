#!/usr/bin/env python3
"""
AXIOM v3 — Estado del sistema.

    python scripts/salud.py            # resumen de las últimas 24 h
    python scripts/salud.py --horas 72
    python scripts/salud.py --historial 20
"""
from __future__ import annotations

import os, sys, json, asyncio, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from backend.nucleo.registro import registro
from backend.captura import universo


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


async def main(horas: int, historial: int) -> None:
    pool = await asyncpg.create_pool(_dsn())
    registro.conectar(pool)
    try:
        print("═" * 72)
        print(f"AXIOM v3 — estado · últimas {horas} h")
        print("═" * 72)

        print("\n▸ UNIVERSO")
        for k, v in (await universo.estado(pool)).items():
            print(f"  {k:<18} {v}")

        s = await registro.salud(horas)
        print(f"\n▸ EJECUCIONES")
        if not s["tareas"]:
            print("  nada ejecutado en la ventana")
        else:
            print(f"  {'qué':<28}{'corridas':>9}{'err':>6}{'dur':>8}  última")
            for t in s["tareas"]:
                marca = " ⚠" if t["errores"] else "  "
                print(f" {marca}{t['que']:<27}{t['corridas']:>9}{t['errores']:>6}"
                      f"{str(t['dur_media']):>8}  {str(t['ultima'])[:19]}")
                if t["ultimo_error"]:
                    print(f"      └ {t['ultimo_error'][:60]}")

        if historial:
            print(f"\n▸ ÚLTIMAS {historial} EJECUCIONES")
            for e in await registro.historial(historial):
                r = e["resultado"] or e["error"] or ""
                print(f"  {str(e['inicio'])[:19]}  {e['que']:<26}"
                      f"{e['disparador']:<28}{e['estado']:<6} {str(r)[:44]}")
        print("\n" + "═" * 72)
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=int, default=24)
    ap.add_argument("--historial", type=int, default=0)
    a = ap.parse_args()
    asyncio.run(main(a.horas, a.historial))
