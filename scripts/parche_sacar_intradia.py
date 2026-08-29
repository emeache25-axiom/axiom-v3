#!/usr/bin/env python3
"""
AXIOM v3 — Sacar las capacidades intradía: estaban mal dirigidas.

════════════════════════════════════════════════════════════════════════════════
EL ERROR, y es de a qué objeto pertenece cada pregunta:

  BTC-LA-COIN es el objeto de referencia del mercado. Sus capacidades describen
  su ESTADO contra su historia: dónde está, qué tan volátil, cómo se compara
  con lo que fue. Es información sobre el mercado.

  BTC-EL-PAR —BTC/USDT en MEXC o CoinEx— es un mercado OPERABLE como cualquiera
  de los otros 2.975. Sus capacidades son las de par: rango, oscilación,
  repetibilidad, spread.

  `btc_giros_horarios` y `btc_calidad_horaria` preguntan "¿a qué hora conviene
  comprar?". Eso es una pregunta de PAR OPERABLE, y se estaba haciendo sobre la
  serie de referencia de Binance — un exchange donde AXIOM ni siquiera opera.

  Mal dirigidas dos veces: pregunta de par aplicada a la coin, y sobre un
  exchange que no se usa para operar.

  Eso explica por qué no llevaban a ningún lado. No es solo que el resultado
  fuera negativo: la pregunta estaba dirigida al objeto equivocado.

QUÉ SE CONSERVA:
  `btc_recorrido_oculto` — cuánto se mueve el precio adentro del día contra lo
  que muestra la vela. Esa SÍ es una propiedad del activo, no una pregunta
  operativa: describe cómo se comporta BTC, no cuándo comprarlo.

  Y las 78.994 velas horarias quedan guardadas. No se pierden, y van a servir
  cuando haya una pregunta que las pida — que es el orden correcto: la pregunta
  primero, el dato después.

Uso:
    cd /home/migue/apps/axiom-v3
    python3 scripts/parche_sacar_intradia.py
    python3 scripts/parche_sacar_intradia.py --revertir
"""
from __future__ import annotations

import sys
import shutil
import argparse
import py_compile
from pathlib import Path
from datetime import datetime

DESTINO = Path("backend/dominio/btc_intradia.py")


def revertir() -> int:
    bks = sorted(DESTINO.parent.glob(f"{DESTINO.name}.bak.*"))
    if not bks:
        print("No hay backups."); return 1
    shutil.copy2(bks[-1], DESTINO)
    print(f"Restaurado desde {bks[-1]}")
    return 0


NUEVO = '''"""
AXIOM v3 — Comportamiento intradía de BTC.
════════════════════════════════════════════════════════════════════════════════
Una sola capacidad, y hay una razón para que sea una sola.

QUÉ SE SACÓ Y POR QUÉ:

  `btc_giros_horarios` y `btc_calidad_horaria` preguntaban "¿a qué hora conviene
  comprar?". Esa es una pregunta de PAR OPERABLE, y se estaba haciendo sobre
  BTC-la-coin, con datos de Binance — un exchange donde AXIOM no opera.

  BTC-la-coin es el objeto de REFERENCIA del mercado: sus capacidades describen
  su estado contra su historia. BTC/USDT en MEXC o CoinEx es un mercado
  operable, y ahí sí caben las preguntas de entrada y salida, con las
  capacidades de par y los datos del exchange donde se opera.

  Las mediciones lo confirmaron antes de que entendiéramos por qué: la ventaja
  horaria nunca superó 0,2 % en ninguna ventana, y la mejor hora saltaba por
  todo el reloj (13, 18, 1, 10). No era solo un resultado negativo: la pregunta
  estaba dirigida al objeto equivocado.

LO QUE QUEDA:

  `btc_recorrido_oculto` describe cómo se comporta el activo —cuánto se mueve
  adentro del día contra lo que muestra la vela— y eso SÍ es una propiedad de
  BTC, no una pregunta operativa.

  Las 78.994 velas horarias siguen guardadas. Van a servir cuando haya una
  pregunta que las pida, que es el orden correcto: la pregunta primero, el dato
  después. Inventar qué medir porque hay datos disponibles es al revés de cómo
  se trabajó todo lo demás.
"""
from __future__ import annotations

import logging
from datetime import date

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)

MESES = {"default": 12, "min": 3, "max": 108}
HORAS = 24


async def _dias(pool, meses: int) -> dict:
    """
    Los días UTC completos, con sus 24 velas.

    Solo COMPLETOS: uno con 18 horas daría un recorrido parcial presentado como
    el del día.
    """
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT (hora AT TIME ZONE 'utc')::date AS dia,
                   maximo, minimo
            FROM btc_vela_horaria
            WHERE hora >= (now() AT TIME ZONE 'utc') - ($1 || ' months')::interval
            ORDER BY hora
        """, str(int(meses)))

    por_dia: dict = {}
    for f in filas:
        por_dia.setdefault(str(f["dia"]), []).append(f)
    return {d: v for d, v in por_dia.items() if len(v) == HORAS}


async def _recorrido_oculto(contexto, meses=12, **_):
    """
    Cuánto se mueve el precio adentro del día contra lo que muestra la vela.

    Un día puede cerrar plano habiéndose movido 8 % adentro. Se mide como el
    recorrido intradía —la suma de los rangos horarios— dividido por el rango
    de la vela diaria.

    Un valor de 3 significa que el precio recorrió tres veces lo que sugiere la
    vela: entró y salió de su rango varias veces.
    """
    dias = await _dias(contexto["pool"], meses)
    if not dias:
        return {"valor": None, "dias": 0}

    ratios = []
    for velas in dias.values():
        intra = sum((float(f["maximo"]) - float(f["minimo"])) / float(f["minimo"])
                    for f in velas if float(f["minimo"]) > 0) * 100
        alto = max(float(f["maximo"]) for f in velas)
        bajo = min(float(f["minimo"]) for f in velas)
        if bajo <= 0:
            continue
        rango = (alto - bajo) / bajo * 100
        if rango > 0:
            ratios.append(intra / rango)

    if not ratios:
        return {"valor": None, "dias": len(dias)}

    ratios.sort()
    n = len(ratios)
    return {
        "valor": round(ratios[n // 2], 3),
        "percentil_25": round(ratios[n // 4], 3),
        "percentil_75": round(ratios[3 * n // 4], 3),
        "minimo": round(ratios[0], 3),
        "maximo": round(ratios[-1], 3),
        "dias": n,
        "meses_pedidos": meses,
        "_fuente_hasta": date.fromisoformat(max(dias)),
    }


def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="btc_recorrido_oculto", objeto=Objeto.MERCADO,
        funcion=_recorrido_oculto, alcance=Alcance.INDIVIDUAL,
        parametros={"meses": MESES},
        descripcion="Cuánto se mueve BTC adentro del día contra lo que muestra "
                    "la vela diaria",
        propiedad=Propiedad(unidad="ratio", direccion=Direccion.CONTEXTUAL,
                            minimo=1, maximo=20),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la mediana de (recorrido intradía / rango de la vela diaria) "
                 "sobre días UTC completos",
            infiere="que un valor alto describe días donde el precio entra y "
                    "sale varias veces de su rango, en vez de recorrerlo una vez",
            no_sabe="no dice si ese recorrido es CAPTURABLE: no descuenta "
                    "spread ni deslizamiento, y recorrer tres veces el rango en "
                    "24 horas no significa que se pudiera operar cada tramo. "
                    "Tampoco dice CUÁNDO dentro del día ocurrió. Y es sobre la "
                    "serie de REFERENCIA de Binance: el comportamiento del par "
                    "operable en MEXC o CoinEx puede diferir",
            fuente="binance:BTC/USDT, velas horarias — serie de referencia, no "
                   "un par operable",
            metodo="suma de rangos horarios dividida por el rango del día. Solo "
                   "días con las 24 horas")))

    logger.info("[capacidades] btc: recorrido oculto")
'''


def main() -> int:
    if not DESTINO.exists():
        print(f"ERROR: no se encuentra {DESTINO}.", file=sys.stderr); return 1

    src = DESTINO.read_text()
    if "btc_giros_horarios" not in src:
        print("Ya está aplicado. Nada que hacer.")
        return 0

    sello = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = DESTINO.with_suffix(f".py.bak.{sello}")
    shutil.copy2(DESTINO, backup)
    DESTINO.write_text(NUEVO)

    try:
        py_compile.compile(str(DESTINO), doraise=True)
    except py_compile.PyCompileError as e:
        shutil.copy2(backup, DESTINO)
        print(f"ERROR de sintaxis: {e}\nSe restauró el backup.", file=sys.stderr)
        return 1

    print(f"Backup: {backup}")
    print("  ~ btc_giros_horarios  SACADA (pregunta de par, objeto coin)")
    print("  ~ btc_calidad_horaria SACADA (ídem)")
    print("  ~ btc_recorrido_oculto se conserva: describe el activo")
    print("\nLimpiar sus valores persistidos:")
    print("""  sudo -u postgres psql -d axiom_v3 -c \\
    "DELETE FROM valores WHERE capacidad IN ('btc_giros_horarios','btc_calidad_horaria');" """)
    print("\nY después:  sudo systemctl restart axiom-v3")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--revertir", action="store_true")
    a = ap.parse_args()
    sys.exit(revertir() if a.revertir else main())
