#!/usr/bin/env python3
"""
AXIOM v3 — El funding se captura solo cada día.

Se engancha al mismo manejador que las opciones: las dos son de Deribit y las
dos describen posicionamiento. Si Deribit no responde, fallan juntas — y eso
está bien, porque comparten fuente.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_funding_diario.py
    python3 scripts/parche_funding_diario.py --revertir
"""
from __future__ import annotations

import sys, shutil, argparse, py_compile
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
    if "funding.capturar" in src:
        print("Ya está aplicado."); return 0

    cambios = []
    ancla = "from backend.captura import universo, pares, bitcoin, opciones"
    if ancla not in src:
        print("ERROR: no encuentro el import. ¿Se aplicó el parche de opciones?",
              file=sys.stderr)
        return 1
    src = src.replace(ancla, ancla + ", funding", 1)
    cambios.append("import de funding")

    viejo = '''        return await opciones.capturar(self.pool)'''
    nuevo = '''        cadena = await opciones.capturar(self.pool)
        # El funding va acá y no en su propio suscriptor porque comparte
        # fuente con las opciones: si Deribit no responde, fallan juntas, y
        # separarlas daría dos alertas del mismo problema.
        tasas = await funding.capturar(self.pool)
        return {"opciones": cadena, "funding": tasas}'''
    if viejo not in src:
        print("ERROR: no encuentro el manejador de opciones.", file=sys.stderr)
        return 1
    src = src.replace(viejo, nuevo, 1)
    cambios.append("captura de funding junto a las opciones")

    if '"opciones": await opciones.estado(self.pool),' in src:
        src = src.replace(
            '"opciones": await opciones.estado(self.pool),',
            '"opciones": await opciones.estado(self.pool),\n'
            '            "funding": await funding.estado(self.pool),', 1)
        cambios.append("estado del funding en /api/sistema/estado")

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
    for c in cambios: print(f"  ~ {c}")
    print("\nOK. Ahora:  sudo systemctl restart axiom-v3")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    sys.exit(revertir() if a.revertir else main())
