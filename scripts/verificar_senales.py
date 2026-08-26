#!/usr/bin/env python3
"""
¿PODEMOS CREER EN LAS SEÑALES?

════════════════════════════════════════════════════════════════════════════════
POR QUÉ ESTE SCRIPT EXISTE:

  Se midió si las señales eran redundantes, si sus votos estaban congelados, y
  se propuso recalibrar umbrales — TODO ASUMIENDO QUE LOS VALORES SON
  CORRECTOS. Nunca se verificó el dato.

  Es exactamente el error que v3 viene a evitar: construir sobre un número sin
  preguntarle de dónde viene. Antes de tocar un umbral hay que saber si el
  valor que ese umbral clasifica significa lo que decimos que significa.

QUÉ VERIFICA, y son cosas distintas:

  1. RANGO PLAUSIBLE — ¿el valor cae donde esa magnitud debería caer?
     Detecta el peor error posible: un número plausible en la escala
     equivocada. `funding_btc` osciló entre -0,0001 y 0,0001 y su umbral es
     ±0,01: el valor parece estar en FRACCIÓN y el umbral en PORCENTAJE. Cien
     veces de diferencia, y el clasificador nunca alcanza su primer escalón.

  2. VARIACIÓN — ¿el valor se movió?
     Un valor idéntico durante días no es estabilidad: es una fuente que dejó
     de actualizar y nadie se enteró.

  3. FRESCURA — ¿cuándo se actualizó por última vez?

  4. COHERENCIA CON EL UMBRAL — ¿el rango observado toca algún escalón?
     Si todos los valores caen en un solo tramo, la señal no puede votar otra
     cosa por construcción. No es que "no discrimine": es que la tabla de
     umbrales fue escrita para otro rango.

LO QUE NO VERIFICA:
  Que el valor sea CIERTO. Para eso habría que comparar contra la fuente
  original, y este script no sale a internet — corre sobre lo guardado. Un
  valor plausible, fresco y bien escalado puede igual estar mal si la fuente se
  equivocó. Eso se declara, no se resuelve acá.

    python verificar_senales.py
"""
from __future__ import annotations

import os
import sys
import asyncio

import asyncpg

DSN_V2 = os.environ.get("DSN_V2", "")

# ── Qué se espera de cada señal ──────────────────────────────────────────────
#
# Los rangos salen de la definición de cada magnitud, no de lo observado: si
# se derivaran de los datos, un dato mal escalado definiría su propio rango
# "correcto" y el chequeo no detectaría nada.
#
# (mínimo, máximo, unidad, de dónde sale)
ESPERADO = {
    "mvrv_zscore":    (-1.0, 12.0, "z-score",
                       "histórico: de -0,5 en suelos a +7 o más en techos"),
    "nupl":           (-60.0, 80.0, "% (no fracción)",
                       "porcentaje de ganancia/pérdida no realizada"),
    "lth_supply":     (10.0, 20.0, "millones de BTC",
                       "sobre ~19,8 M en circulación; los LTH rondan 13-16 M"),
    "mayer_multiple": (0.3, 4.0, "ratio precio/MA200",
                       "0,5 en capitulaciones, >2,4 recalentado"),
    "price_vs_ma50":  (0.5, 2.0, "ratio precio/MA50", "1,0 = sobre la media"),
    "price_vs_ema20": (0.7, 1.4, "ratio precio/EMA20", "1,0 = sobre la media"),
    "btc_vs_ath":     (-95.0, 5.0, "% desde el máximo",
                       "negativo salvo en máximo nuevo"),
    "fear_greed":     (0.0, 100.0, "índice 0-100", "alternative.me"),
    "btc_dominance":  (30.0, 75.0, "% de capitalización total", "CoinGecko"),
    "vol_mcap_ratio": (0.1, 50.0, "% volumen/capitalización", ""),
    "funding_btc":    (-0.003, 0.003, "FRACCIÓN por período de 8 h",
                       "el neutral de BTC es 0,0001 = 0,01 %. Si viniera en "
                       "PORCENTAJE el rango sería ±0,3"),
    "volume_relative": (0.0, 20.0, "ratio contra el volumen medio", ""),
}

# Los escalones de cada clasificador, tal como están en v2. Sirven para
# responder si el rango observado los toca.
UMBRALES = {
    "mvrv_zscore":    [0, 1, 2, 3.5],
    "nupl":           [0, 25, 50, 75],
    "lth_supply":     [12.5, 13.5, 14, 15],
    "mayer_multiple": [0.8, 1.0, 1.5, 2.4],
    "price_vs_ma50":  [0.90, 0.97, 1.05, 1.15],
    "price_vs_ema20": [0.98, 1.02],
    "btc_vs_ath":     [-60, -40, -20, -5],
    "fear_greed":     [20, 40, 60, 80],
    "btc_dominance":  [48, 53, 57, 60],
    "vol_mcap_ratio": [2, 4, 7, 12],
    "funding_btc":    [-0.01, 0.01],
}


async def main() -> None:
    if not DSN_V2:
        print("ERROR: falta DSN_V2", file=sys.stderr); sys.exit(1)
    conn = await asyncpg.connect(DSN_V2)
    try:
        filas = await conn.fetch("""
            SELECT r.signal_id,
                   COUNT(*)                                   AS lecturas,
                   MIN(r.raw_value)                           AS minimo,
                   MAX(r.raw_value)                           AS maximo,
                   AVG(r.raw_value)                           AS medio,
                   COUNT(DISTINCT r.raw_value)                AS valores_distintos,
                   COUNT(DISTINCT r.voted_regime)             AS votos_distintos,
                   MAX(s.created_at)                          AS ultima
            FROM signal_readings r
            JOIN snapshots s ON s.id = r.snapshot_id
            WHERE r.is_core AND r.raw_value IS NOT NULL
            GROUP BY r.signal_id ORDER BY r.signal_id
        """)
        # ¿Cuántas lecturas seguidas con el MISMO valor? Una fuente congelada
        # se ve así y no lanza ningún error.
        repetidos = await conn.fetch("""
            SELECT signal_id, raw_value, COUNT(*) AS veces
            FROM signal_readings
            WHERE is_core AND raw_value IS NOT NULL
            GROUP BY signal_id, raw_value
            ORDER BY veces DESC
        """)
    finally:
        await conn.close()

    peor_repetido = {}
    for r in repetidos:
        if r["signal_id"] not in peor_repetido:
            peor_repetido[r["signal_id"]] = (float(r["raw_value"]), r["veces"])

    print("═" * 78)
    print("¿PODEMOS CREER EN LAS SEÑALES?")
    print("═" * 78)

    problemas: list[str] = []

    for f in filas:
        s = f["signal_id"]
        mn, mx, med = float(f["minimo"]), float(f["maximo"]), float(f["medio"])
        esp = ESPERADO.get(s)

        print(f"\n▸ {s}")
        print(f"   observado : {mn:.6g} … {mx:.6g}   (medio {med:.6g})")
        if esp:
            lo, hi, unidad, nota = esp
            print(f"   esperado  : {lo:g} … {hi:g}  [{unidad}]")
            if nota:
                print(f"               {nota}")
            fuera = mn < lo or mx > hi
            if fuera:
                print("   ⚠ FUERA DEL RANGO ESPERADO — posible error de unidad o de fuente")
                problemas.append(f"{s}: rango observado fuera de lo esperado")

        # ¿Se movió?
        val, veces = peor_repetido.get(s, (None, 0))
        pct = veces / f["lecturas"] * 100
        print(f"   variación : {f['valores_distintos']} valores distintos "
              f"en {f['lecturas']} lecturas")
        if pct > 50:
            print(f"   ⚠ el valor {val:.6g} se repitió en {pct:.0f} % de las "
                  f"lecturas — ¿la fuente actualiza?")
            problemas.append(f"{s}: un solo valor en el {pct:.0f} % de las lecturas")

        # ¿El rango toca algún umbral?
        u = UMBRALES.get(s)
        if u:
            dentro = [x for x in u if mn <= x <= mx]
            print(f"   umbrales  : {u}")
            if not dentro:
                lado = "por DEBAJO" if mx < min(u) else "por ENCIMA" if mn > max(u) else "?"
                print(f"   ⚠ NINGÚN umbral cae en el rango observado — está {lado}.")
                print("     La señal no puede votar otra cosa POR CONSTRUCCIÓN:")
                print("     la tabla de escalones fue escrita para otro rango.")
                problemas.append(f"{s}: ningún umbral dentro del rango observado")
            elif len(dentro) < len(u) / 2:
                print(f"   ⚠ solo {len(dentro)} de {len(u)} umbrales son "
                      f"alcanzables en este rango")
                problemas.append(f"{s}: solo {len(dentro)}/{len(u)} umbrales alcanzables")

        print(f"   votos     : {f['votos_distintos']} distinto(s)")
        print(f"   última    : {str(f['ultima'])[:19]}")

    print("\n" + "═" * 78)
    print(f"PROBLEMAS ENCONTRADOS: {len(problemas)}")
    for p in problemas:
        print(f"  · {p}")
    print("\nLO QUE ESTO NO PRUEBA: que los valores sean CIERTOS. Un dato")
    print("plausible, fresco y bien escalado puede estar mal igual si la fuente")
    print("se equivocó — para saberlo hay que ir a la fuente original.")
    print("═" * 78)


if __name__ == "__main__":
    asyncio.run(main())
