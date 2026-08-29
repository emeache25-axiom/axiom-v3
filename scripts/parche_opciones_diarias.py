#!/usr/bin/env python3
"""
AXIOM v3 — La cadena de opciones se captura sola cada día.

Suscribe la captura al cierre del día, como suscriptor SEPARADO de los demás:
si Deribit no responde, eso no debe impedir capturar de CoinGecko ni de MEXC.
Son fuentes distintas sin relación entre sí.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_opciones_diarias.py
    python3 scripts/parche_opciones_diarias.py --revertir
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
    if "_capturar_opciones" in src:
        print("Ya está aplicado. Nada que hacer."); return 0

    cambios = []

    # 1. El import
    ancla = "from backend.captura import universo, pares, bitcoin"
    if ancla not in src:
        print("ERROR: no encuentro el import de captura.", file=sys.stderr); return 1
    src = src.replace(ancla, ancla + ", opciones", 1)
    cambios.append("import de opciones")

    # 2. La suscripción
    ancla_sub = """        _bus.bus.suscribir(
            _bus.CIERRE_VELA_DIARIA, self._capturar_btc,
            "serie_de_bitcoin")"""
    nuevo_sub = ancla_sub + """

        # La cadena de opciones va SEPARADA: si Deribit no responde, eso no
        # debe impedir capturar de CoinGecko ni de MEXC. Fuentes distintas sin
        # relación entre sí.
        _bus.bus.suscribir(
            _bus.CIERRE_VELA_DIARIA, self._capturar_opciones,
            "cadena_de_opciones")"""
    if ancla_sub not in src:
        print("ERROR: no encuentro la suscripción de bitcoin. "
              "¿Se aplicó el parche de BTC?", file=sys.stderr)
        return 1
    src = src.replace(ancla_sub, nuevo_sub, 1)
    cambios.append("suscripción al cierre del día")

    # 3. El manejador
    ancla_met = "    async def _catalogar_pares(self):"
    nuevo_met = '''    async def _capturar_opciones(self, evento) -> dict:
        """
        La foto diaria de la cadena de opciones de BTC.

        Existe porque la pregunta "¿hoy hay más interés abierto que ayer?"
        necesita tener ayer guardado, y Deribit solo devuelve el presente.
        """
        return await opciones.capturar(self.pool)

    async def _catalogar_pares(self):'''
    if ancla_met not in src:
        print("ERROR: no encuentro dónde insertar el método.", file=sys.stderr)
        return 1
    src = src.replace(ancla_met, nuevo_met, 1)
    cambios.append("manejador _capturar_opciones")

    # 4. El estado
    if '"bitcoin": await bitcoin.estado(self.pool),' in src:
        src = src.replace(
            '"bitcoin": await bitcoin.estado(self.pool),',
            '"bitcoin": await bitcoin.estado(self.pool),\n'
            '            "opciones": await opciones.estado(self.pool),', 1)
        cambios.append("estado de opciones en /api/sistema/estado")

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
