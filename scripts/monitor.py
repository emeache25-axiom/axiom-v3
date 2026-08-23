#!/usr/bin/env python3
"""
AXIOM v3 — Monitor: qué pasó, qué está pasando, qué pasará.

    python scripts/monitor.py
"""
from __future__ import annotations

import os, sys, asyncio, argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from backend.nucleo.monitor import monitor
from backend.nucleo import bus as B


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


async def main(horas: int) -> None:
    pool = await asyncpg.create_pool(_dsn())
    try:
        m = await monitor(pool, None, B.bus, horas)
        print("═" * 72)
        print(f"AXIOM v3 — monitor · {m['ahora'][:19]} UTC")
        print("═" * 72)

        if m["alertas"]:
            print("\n▸ ALERTAS")
            for a in m["alertas"]:
                print(f"  ⚠ {a}")
        else:
            print("\n▸ sin alertas")

        print("\n▸ QUÉ ESTÁ PASANDO")
        if not m["esta_pasando"]:
            print("  nada en curso")
        for e in m["esta_pasando"]:
            print(f"  {e['que']:<24}{e['disparador']:<30}hace {e['segundos']}s")

        print("\n▸ QUÉ PASÓ")
        if not m["paso"]:
            print("  nada en la ventana")
        for e in m["paso"][:12]:
            marca = "⚠" if e["estado"] == "error" else " "
            det = e["error"] or str(e["resultado"] or "")
            print(f" {marca}{str(e['inicio'])[:19]}  {e['que']:<22}"
                  f"{e['estado']:<7}{det[:40]}")

        print("\n▸ QUÉ DEBÍA PASAR Y NO PASÓ")
        h = m["no_paso"]["huecos_de_historia"]
        print(f"  huecos de historia: {', '.join(h) if h else 'ninguno'}")
        for c in m["no_paso"]["ejecuciones_colgadas"]:
            print(f"  colgada: {c['que']} hace {c['minutos']} min")

        print("\n" + "═" * 72)
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--horas", type=int, default=24)
    a = ap.parse_args()
    asyncio.run(main(a.horas))
