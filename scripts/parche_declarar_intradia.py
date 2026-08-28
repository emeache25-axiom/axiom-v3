#!/usr/bin/env python3
"""
AXIOM v3 — Declarar las capacidades intradía de BTC.

Modifica backend/app.py para registrar el módulo btc_intradia junto con los
demás. Parche y no reemplazo: mandar el archivo completo ya pisó correcciones
locales cuatro veces.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_declarar_intradia.py
    python3 scripts/parche_declarar_intradia.py --revertir
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
    if "dominio_intradia" in src:
        print("Ya está aplicado. Nada que hacer."); return 0

    ancla_imp = "from backend.dominio import mercado as dominio_mercado"
    if ancla_imp not in src:
        print("ERROR: no encuentro el import del dominio mercado. "
              "¿Se aplicó el parche anterior?", file=sys.stderr)
        return 1
    src = src.replace(
        ancla_imp,
        ancla_imp + "\nfrom backend.dominio import btc_intradia as dominio_intradia",
        1)

    ancla_dec = "        dominio_mercado.declarar()"
    if ancla_dec not in src:
        print("ERROR: no encuentro la declaración del mercado.", file=sys.stderr)
        return 1
    src = src.replace(ancla_dec, ancla_dec + "\n        dominio_intradia.declarar()", 1)

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
    print("  ~ import de btc_intradia")
    print("  ~ declaración de las capacidades intradía")
    print("\nOK. Ahora:  sudo systemctl restart axiom-v3")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    sys.exit(revertir() if a.revertir else main())
