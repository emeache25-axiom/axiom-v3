#!/usr/bin/env python3
"""
AXIOM v3 — La serie de BTC se actualiza sola.

EL PROBLEMA:
  Se capturaron 3.296 velas diarias y 78.994 horarias A MANO, y no hay ninguna
  tarea que las mantenga. A partir de mañana la serie empieza a quedar vieja
  sin que nada avise.

EL ARREGLO:
  Suscribir la captura de BTC al cierre del día, como suscriptor SEPARADO de
  las velas de pares. Separado a propósito: si Binance no responde, eso no debe
  impedir capturar de MEXC — son fuentes distintas sin relación entre sí.

  Y las horarias se capturan en la misma pasada: son 24 velas nuevas por día,
  una sola llamada.

Este parche MODIFICA backend/app.py en el servidor en vez de reemplazarlo:
mandar el archivo completo pisaría las correcciones locales, cosa que ya pasó
cuatro veces con otros archivos.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_btc_diario.py
    python3 scripts/parche_btc_diario.py --revertir
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
        print(f"ERROR: no se encuentra {DESTINO}. ¿Estás en axiom-v3?",
              file=sys.stderr)
        return 1

    src = DESTINO.read_text()

    if "_capturar_btc" in src:
        print("Ya está aplicado. Nada que hacer.")
        return 0

    cambios = []

    # ── 1. Importar el módulo ───────────────────────────────────────────────
    if "from backend.captura import universo, pares" in src:
        src = src.replace(
            "from backend.captura import universo, pares",
            "from backend.captura import universo, pares, bitcoin", 1)
        cambios.append("import de bitcoin")
    else:
        print("ERROR: no encuentro el import de captura. ¿Cambió el archivo?",
              file=sys.stderr)
        return 1

    # ── 2. Suscribir al cierre del día ──────────────────────────────────────
    ancla_sub = """        _bus.bus.suscribir(
            _bus.CAMBIO_DE_UNIVERSO, self._registrar_cambio_de_universo,
            "log_de_cambios_de_universo")"""
    nuevo_sub = """        # La serie de BTC va como suscriptor SEPARADO de las velas de pares:
        # si Binance no responde, eso no debe impedir capturar de MEXC. Son
        # fuentes distintas sin relación entre sí.
        _bus.bus.suscribir(
            _bus.CIERRE_VELA_DIARIA, self._capturar_btc,
            "serie_de_bitcoin")

        _bus.bus.suscribir(
            _bus.CAMBIO_DE_UNIVERSO, self._registrar_cambio_de_universo,
            "log_de_cambios_de_universo")"""
    if ancla_sub not in src:
        print("ERROR: no encuentro dónde suscribir. ¿Cambió el archivo?",
              file=sys.stderr)
        return 1
    src = src.replace(ancla_sub, nuevo_sub, 1)
    cambios.append("suscripción al cierre del día")

    # ── 3. El manejador ─────────────────────────────────────────────────────
    ancla_met = "    async def _catalogar_pares(self):"
    nuevo_met = '''    async def _capturar_btc(self, evento) -> dict:
        """
        La serie de referencia de Bitcoin: velas diarias y horarias.

        Solo lo que falta —una o dos velas diarias y 24 horarias— porque la
        captura es incremental: pide desde la última guardada, no desde 2017.

        BTC es un objeto propio, no un par: esta serie viene de Binance, que no
        es un exchange donde AXIOM opere. Los BTC/USDT de MEXC y CoinEx son
        otra cosa y viven en `pares`.
        """
        d = await bitcoin.capturar_diarias(self.pool)
        h = await bitcoin.capturar_horarias(self.pool)
        return {"diarias": d, "horarias": h}

    async def _catalogar_pares(self):'''
    if ancla_met not in src:
        print("ERROR: no encuentro dónde insertar el método.", file=sys.stderr)
        return 1
    src = src.replace(ancla_met, nuevo_met, 1)
    cambios.append("manejador _capturar_btc")

    # ── 4. Exponerlo en el estado ───────────────────────────────────────────
    if '"pares": await pares.estado(self.pool),' in src:
        src = src.replace(
            '"pares": await pares.estado(self.pool),',
            '"pares": await pares.estado(self.pool),\n'
            '            "bitcoin": await bitcoin.estado(self.pool),', 1)
        cambios.append("estado de bitcoin en /api/sistema/estado")

    # ── Escribir con backup ─────────────────────────────────────────────────
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
    print("\nOK. Ahora:")
    print("  sudo systemctl restart axiom-v3")
    print("\nY para verificar sin esperar al cierre:")
    print("""
  set -a; source .env; set +a
  venv/bin/python -c "
import asyncio, sys; sys.path.insert(0,'.')
import backend.app as A
from backend.nucleo import bus as B
async def main():
    a = A.Axiom(); await a.arrancar(con_planificador=False)
    print(await B.bus.publicar(B.CIERRE_VELA_DIARIA, {'dia_cerrado':'hoy'}, origen='prueba'))
    await a.detener()
asyncio.run(main())"
""")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    sys.exit(revertir() if a.revertir else main())
