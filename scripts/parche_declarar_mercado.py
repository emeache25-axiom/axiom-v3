#!/usr/bin/env python3
"""
AXIOM v3 — Declarar el perfil de BTC al arrancar.

Modifica backend/app.py para que las cinco capacidades del mercado se declaren
junto con las del par. Parche y no reemplazo: mandar el archivo completo ya
pisó correcciones locales cuatro veces.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_declarar_mercado.py
    python3 scripts/parche_declarar_mercado.py --revertir
"""
from __future__ import annotations

import sys
import shutil
import argparse
import py_compile
from pathlib import Path
from datetime import datetime

DESTINO = Path("backend/app.py")


def revertir() -> int:
    bks = sorted(DESTINO.parent.glob(f"{DESTINO.name}.bak.*"))
    if not bks:
        print("No hay backups."); return 1
    shutil.copy2(bks[-1], DESTINO)
    print(f"Restaurado desde {bks[-1]}")
    return 0


def main() -> int:
    if not DESTINO.exists():
        print(f"ERROR: no se encuentra {DESTINO}.", file=sys.stderr); return 1

    src = DESTINO.read_text()
    if "dominio_mercado" in src:
        print("Ya está aplicado. Nada que hacer.")
        return 0

    cambios = []

    if "from backend.dominio import par as dominio_par" not in src:
        print("ERROR: no encuentro el import del dominio par.", file=sys.stderr)
        return 1
    src = src.replace(
        "from backend.dominio import par as dominio_par",
        "from backend.dominio import par as dominio_par\n"
        "from backend.dominio import mercado as dominio_mercado", 1)
    cambios.append("import del dominio mercado")

    if "dominio_par.declarar()" not in src:
        print("ERROR: no encuentro la declaración de capacidades.", file=sys.stderr)
        return 1
    src = src.replace(
        "        dominio_par.declarar()",
        "        dominio_par.declarar()\n        dominio_mercado.declarar()", 1)
    cambios.append("declaración de las capacidades del mercado")

    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DESTINO.with_suffix(f".py.bak.{sello}")
    shutil.copy2(DESTINO, backup)
    DESTINO.write_text(src)

    try:
        py_compile.compile(str(DESTINO), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(backup, DESTINO)
        print(f"ERROR de sintaxis: {e}\nSe restauró el backup.", file=sys.stderr)
        return 1

    print(f"Backup: {backup}")
    for c in cambios:
        print(f"  ~ {c}")
    print("\nOK. Ahora:  sudo systemctl restart axiom-v3")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    sys.exit(revertir() if a.revertir else main())
