#!/usr/bin/env python3
"""
¿QUÉ PASA SI COMPRO TODOS LOS DÍAS EN LA APERTURA?

════════════════════════════════════════════════════════════════════════════════
POR QUÉ ESTA MEDICIÓN ES DISTINTA DE LAS ANTERIORES:

  La apertura es un punto OBSERVABLE SIN AMBIGÜEDAD. No hay que elegirlo ni
  predecirlo: llega a las 00:00 UTC y ahí está.

  Todo lo medido hasta acá daba techos teóricos —"el mejor precio de venta en
  las próximas N horas"— que exigen saber después. Esto es lo primero que se
  puede EJECUTAR.

LO QUE SE MIDE, y son tres cosas distintas:

  1. RECORRIDO A FAVOR — cuánto llegó a subir sobre la apertura antes de que
     terminara el día. Es la oportunidad que hubo.

  2. RECORRIDO EN CONTRA — cuánto llegó a bajar. Es el riesgo que había que
     aguantar para llegar a esa oportunidad.

     Las dos juntas importan: una estrategia que gana 1 % después de tolerar
     4 % en contra no es la misma que una que gana 1 % sin sobresaltos.

  3. REGLAS SIMPLES — salir con +1 %, +2 %, o al cierre. Con stop y sin stop.
     Esto ya es una estrategia elemental, medible sobre nueve años.

LA COMPARACIÓN QUE CASI NADIE HACE:

  El resultado se compara contra COMPRAR Y NO HACER NADA en el mismo período.
  Si BTC subió mucho, cualquier estrategia de compra parece buena — la
  referencia no es cero, es el retorno del propio BTC.

  Es lo que separa una estrategia de una ilusión.

LO QUE NO INCLUYE, declarado:
  Comisiones ni deslizamiento. Los resultados son el techo de cada regla, no lo
  que se obtendría operando. Con 730 operaciones, una comisión del 0,1 % por
  lado se come 146 puntos porcentuales acumulados.

    python medir_entrada_apertura.py [--meses 24]
"""
from __future__ import annotations

import os
import sys
import asyncio
import argparse

import asyncpg

# Objetivos de salida a probar, en %. Y stops, para medir el efecto de cortar.
OBJETIVOS = (0.5, 1.0, 1.5, 2.0, 3.0)
STOPS = (None, 1.0, 2.0, 3.0)


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


def _mediana(v):
    s = sorted(v)
    return s[len(s) // 2] if s else None


async def main(meses: int) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        filas = await conn.fetch("""
            SELECT (hora AT TIME ZONE 'utc')::date              AS dia,
                   EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h,
                   apertura, maximo, minimo, cierre
            FROM btc_vela_horaria
            WHERE hora >= (now() AT TIME ZONE 'utc') - ($1 || ' months')::interval
            ORDER BY hora
        """, str(int(meses)))
    finally:
        await conn.close()

    por_dia: dict = {}
    for f in filas:
        por_dia.setdefault(str(f["dia"]), []).append(f)
    dias = {d: v for d, v in sorted(por_dia.items()) if len(v) == 24}

    if len(dias) < 60:
        print("No hay días completos suficientes."); return

    print("═" * 78)
    print(f"COMPRAR EN LA APERTURA · {len(dias)} días · {meses} meses")
    print(f"{min(dias)} → {max(dias)}")
    print("═" * 78)

    # ── 1 y 2. Recorrido a favor y en contra ────────────────────────────────
    a_favor, en_contra, al_cierre = [], [], []
    for velas in dias.values():
        abre = float(velas[0]["apertura"])
        if abre <= 0:
            continue
        alto = max(float(f["maximo"]) for f in velas)
        bajo = min(float(f["minimo"]) for f in velas)
        cierra = float(velas[-1]["cierre"])
        a_favor.append((alto / abre - 1) * 100)
        en_contra.append((bajo / abre - 1) * 100)
        al_cierre.append((cierra / abre - 1) * 100)

    print("\n▸ COMPRANDO EN LA APERTURA, ¿QUÉ PASÓ DESPUÉS?")
    print(f"  {'':22}{'media':>9}{'mediana':>10}{'peor':>10}{'mejor':>10}")
    for nombre, v in (("subió hasta", a_favor), ("bajó hasta", en_contra),
                      ("terminó en", al_cierre)):
        print(f"  {nombre:<22}{sum(v)/len(v):>8.2f}%{_mediana(v):>9.2f}%"
              f"{min(v):>9.2f}%{max(v):>9.2f}%")

    print(f"\n  días que llegaron a +1 %: "
          f"{sum(1 for x in a_favor if x >= 1)/len(a_favor)*100:>5.1f} %")
    print(f"  días que llegaron a +2 %: "
          f"{sum(1 for x in a_favor if x >= 2)/len(a_favor)*100:>5.1f} %")
    print(f"  días que bajaron a -1 %: "
          f"{sum(1 for x in en_contra if x <= -1)/len(en_contra)*100:>5.1f} %")
    print(f"  días que bajaron a -2 %: "
          f"{sum(1 for x in en_contra if x <= -2)/len(en_contra)*100:>5.1f} %")

    # ── La referencia: comprar y no hacer nada ──────────────────────────────
    primeros = dias[min(dias)]
    ultimos = dias[max(dias)]
    compra_inicial = float(primeros[0]["apertura"])
    valor_final = float(ultimos[-1]["cierre"])
    comprar_y_esperar = (valor_final / compra_inicial - 1) * 100

    print(f"\n▸ LA REFERENCIA")
    print(f"  comprar el primer día y no hacer nada: {comprar_y_esperar:+.2f} %")
    print("  Cualquier regla tiene que superar esto para valer la pena — si BTC")
    print("  subió mucho, cualquier estrategia de compra parece buena.")

    # ── 3. Reglas simples ───────────────────────────────────────────────────
    print("\n▸ REGLAS SIMPLES, día por día")
    print("  Compra en la apertura. Sale al tocar el objetivo, el stop, o al")
    print("  cierre si no tocó ninguno. El resultado es la SUMA de retornos")
    print("  diarios: es lo comparable con la referencia.\n")
    print(f"  {'objetivo':>9}{'stop':>7}{'aciertos':>10}{'stops':>8}"
          f"{'cierres':>9}{'acumulado':>12}{'por día':>10}")

    resultados = []
    for objetivo in OBJETIVOS:
        for stop in STOPS:
            total, ok, cortados, cerrados = 0.0, 0, 0, 0
            for velas in dias.values():
                abre = float(velas[0]["apertura"])
                if abre <= 0:
                    continue
                r = None
                for f in velas:
                    sube = (float(f["maximo"]) / abre - 1) * 100
                    baja = (float(f["minimo"]) / abre - 1) * 100
                    # Si en la misma hora se tocan los dos, no se puede saber
                    # cuál primero: se asume el PEOR caso, el stop. Suponer lo
                    # contrario inflaría el resultado sistemáticamente.
                    if stop is not None and baja <= -stop:
                        r = -stop; cortados += 1; break
                    if sube >= objetivo:
                        r = objetivo; ok += 1; break
                if r is None:
                    r = (float(velas[-1]["cierre"]) / abre - 1) * 100
                    cerrados += 1
                total += r
            n = len(dias)
            resultados.append((objetivo, stop, total))
            print(f"  {objetivo:>8.1f}%{str(stop or '—'):>7}{ok/n*100:>9.1f}%"
                  f"{cortados/n*100:>7.1f}%{cerrados/n*100:>8.1f}%"
                  f"{total:>11.1f}%{total/n:>9.3f}%")

    mejor = max(resultados, key=lambda x: x[2])
    print(f"\n▸ LA MEJOR REGLA vs. NO HACER NADA")
    print(f"  objetivo {mejor[0]} % con stop {mejor[1] or 'ninguno'}: "
          f"{mejor[2]:+.1f} % acumulado")
    print(f"  comprar y esperar:                    {comprar_y_esperar:+.1f} %")
    dif = mejor[2] - comprar_y_esperar
    print(f"  diferencia: {dif:+.1f} puntos porcentuales")

    print(f"\n▸ LO QUE FALTA DESCONTAR")
    costo = len(dias) * 0.2
    print(f"  {len(dias)} operaciones × 0,2 % (ida y vuelta) = {costo:.0f} % en costos")
    print(f"  la mejor regla neta: {mejor[2] - costo:+.1f} %")
    print("\n  Sin descontar comisiones ni deslizamiento, cualquier regla que")
    print("  opere todos los días parte con una desventaja enorme contra")
    print("  comprar una sola vez.")
    print("═" * 78)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--meses", type=int, default=24)
    a = ap.parse_args()
    asyncio.run(main(a.meses))
