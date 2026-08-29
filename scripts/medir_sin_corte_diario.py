#!/usr/bin/env python3
"""
¿IMPORTA LA HORA DE ENTRADA, SIN IMPONER EL CORTE DEL DÍA?

════════════════════════════════════════════════════════════════════════════════
POR QUÉ ESTA MEDICIÓN:

  Todo lo anterior preguntaba "¿dónde está el mínimo DEL DÍA?", y el día UTC es
  una frontera arbitraria. Si el mínimo se forma a las 22 y el máximo a las 3
  del día siguiente, la medición por día lo parte en dos y no ve el movimiento.

  Y hay un indicio de que eso pasa: en la medición por día, las horas 0 y 23
  concentraban el 22,5 % de los mínimos entre las dos. Los extremos se agrupan
  justo donde el corte los separa.

LA PREGUNTA, sin fronteras artificiales:

  Si compro a la hora H, ¿cuál es el MEJOR precio de venta en las siguientes N
  horas? Sin importar si eso cruza la medianoche.

  Eso responde lo operativo directamente: comprando a una hora determinada,
  cuánto se podía sacar después.

LO QUE HAY EN JUEGO — medido sobre 730 días:
  · rango diario mediano: 3,07 %
  · 76 % de los días superan 2 %, y 51,6 % superan 3 %
  · capturando solo el 30 % del rango quedan 0,92 % por día, y el 85,6 % de los
    días superarían el 0,5 %

  O sea: EL MOVIMIENTO ESTÁ. Lo que falta es una regla de entrada, y el horario
  por día ya demostró no serlo (ventaja de 0,08 % sobre 729 días).

HIPÓTESIS, escritas antes de mirar:

  H1  Sin el corte diario aparece una ventaja horaria mayor que 0,08 %.
      Predicción: > 0,3 % en algún horizonte.

  H2  Si H1 se confirma, la mejor hora será CONSISTENTE entre horizontes. Si
      cada horizonte da una hora distinta, es ruido — es lo que pasó con las
      ventanas de la medición por día (13, 18, 1, 10).

REGLA DE DESCARTE:
  Si la ventaja no supera 0,3 % o la mejor hora salta entre horizontes, no hay
  patrón horario y el tema queda cerrado.

    python medir_sin_corte_diario.py [--meses 24]
"""
from __future__ import annotations

import os
import sys
import asyncio
import argparse
from collections import defaultdict

import asyncpg

HORIZONTES = (6, 12, 24, 48)
HORAS = 24


def _dsn() -> str:
    d = os.environ.get("DATABASE_URL")
    if d:
        return d
    from pathlib import Path
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for l in env.read_text().splitlines():
            if l.strip().startswith("DATABASE_URL="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    print("ERROR: falta DATABASE_URL", file=sys.stderr); sys.exit(1)


async def main(meses: int) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        filas = await conn.fetch("""
            SELECT hora, EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h,
                   maximo, minimo, cierre
            FROM btc_vela_horaria
            WHERE hora >= (now() AT TIME ZONE 'utc') - ($1 || ' months')::interval
            ORDER BY hora
        """, str(int(meses)))
    finally:
        await conn.close()

    if len(filas) < 24 * 60:
        print("No hay suficientes velas."); return

    h = [f["h"] for f in filas]
    cierre = [float(f["cierre"]) for f in filas]
    alto = [float(f["maximo"]) for f in filas]
    bajo = [float(f["minimo"]) for f in filas]
    n = len(filas)

    print("═" * 78)
    print(f"SIN CORTE DIARIO · {n:,} velas horarias · {meses} meses")
    print(f"{str(filas[0]['hora'])[:16]} → {str(filas[-1]['hora'])[:16]}")
    print("═" * 78)

    print("\n▸ SI COMPRO A LA HORA H, ¿CUÁNTO SE PODÍA SACAR DESPUÉS?")
    print("  El mejor precio de venta en las siguientes N horas, contra el")
    print("  cierre de la hora de entrada. Es el MÁXIMO teórico: exige vender")
    print("  exactamente en el pico.\n")

    resumen = {}
    for horizonte in HORIZONTES:
        por_hora = defaultdict(list)
        for i in range(n - horizonte):
            entrada = cierre[i]
            if entrada <= 0:
                continue
            salida = max(alto[i + 1: i + 1 + horizonte])
            por_hora[h[i]].append((salida / entrada - 1) * 100)

        medias = {hh: sum(v) / len(v) for hh, v in por_hora.items() if v}
        if not medias:
            continue
        mejor = max(medias, key=medias.get)
        peor = min(medias, key=medias.get)
        ventaja = medias[mejor] - medias[peor]
        resumen[horizonte] = (mejor, ventaja, medias)
        print(f"  {horizonte:>2}h → mejor hora {mejor:>2} ({medias[mejor]:.3f} %) · "
              f"peor {peor:>2} ({medias[peor]:.3f} %) · VENTAJA {ventaja:.3f} %")

    print("\n▸ LAS HIPÓTESIS")
    ventajas = [v for _, v, _ in resumen.values()]
    mejores = [m for m, _, _ in resumen.values()]
    max_v = max(ventajas) if ventajas else 0
    print(f"  H1 la ventaja supera 0,3 %: "
          f"{'CONFIRMADA' if max_v > 0.3 else 'DESCARTADA'} — la mayor es {max_v:.3f} %")

    # Consistencia: si las mejores horas están dentro de un rango de ±3, hay
    # patrón; si saltan por todo el reloj, cada horizonte encuentra su ganador
    # por azar.
    if len(mejores) > 1:
        dispersion = max(mejores) - min(mejores)
        circular = min(dispersion, HORAS - dispersion)
        print(f"  H2 la mejor hora es consistente: "
              f"{'CONFIRMADA' if circular <= 3 else 'DESCARTADA'} — "
              f"las mejores horas son {mejores}, dispersión {circular} h")

    print("\n▸ LA DISTRIBUCIÓN COMPLETA (horizonte 24 h)")
    if 24 in resumen:
        _, _, medias = resumen[24]
        base = sum(medias.values()) / len(medias)
        print(f"  media de todas las horas: {base:.3f} %\n")
        for hh in range(HORAS):
            if hh not in medias:
                continue
            desvio = medias[hh] - base
            barra = "█" * int(abs(desvio) * 200)
            signo = "+" if desvio >= 0 else "−"
            print(f"  {hh:>2}h  {medias[hh]:>6.3f} %  {signo}{abs(desvio):.3f}  {barra}")

    print("\n▸ QUÉ SIGNIFICA")
    print("  Este es el máximo TEÓRICO: exige vender exactamente en el pico de")
    print("  la ventana, cosa que solo se sabe después. Un resultado alto acá")
    print("  NO es una oportunidad — es el techo de lo que habría sido posible.")
    print("\n  Lo que la medición sí responde es si ese techo depende de la HORA")
    print("  de entrada. Si todas las horas dan parecido, el reloj no informa.")
    print("═" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", type=int, default=24)
    a = ap.parse_args()
    asyncio.run(main(a.meses))
