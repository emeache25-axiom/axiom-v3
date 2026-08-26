#!/usr/bin/env python3
"""
¿Las 12 señales del régimen miden cosas DISTINTAS?

════════════════════════════════════════════════════════════════════════════════
POR QUÉ IMPORTA:

  `regimen_btc` produce una CONVICCIÓN contando cuántas señales coinciden. Eso
  solo tiene sentido si las señales son independientes. Si tres miden lo mismo
  con distinto nombre, votan igual POR CONSTRUCCIÓN y la convicción está
  inflada: parece consenso y es redundancia.

  Nunca se midió. Es el mismo caso de `rango` y `oscilacion` — ahí la
  correlación resultó 0,049 y por eso las dos valen. Acá no lo sabemos.

HIPÓTESIS, escritas ANTES de mirar:

  H1  `mayer_multiple`, `price_vs_ma50` y `price_vs_ema20` son la misma
      pregunta a distinta escala: precio sobre su media. Predicción:
      correlación > 0,80 entre las tres.

  H2  `mvrv_zscore`, `nupl` y `lth_supply` salen del mismo costo base
      on-chain. Predicción: correlación > 0,70.

  H3  `btc_dominance` no mide a Bitcoin sino BTC contra las alts. Predicción:
      es la MENOS correlacionada con el resto.

REGLA DE DESCARTE:
  Si dos señales correlacionan > 0,85 en VALOR y coinciden en > 85 % de sus
  VOTOS, son redundantes: aportan un voto donde debería haber uno.

  Si ninguna pasa ese umbral, las 12 son independientes y la convicción es
  legítima. Sería un buen resultado.

Corre contra axiom_v2, que tiene ~80 días de las 12 capturadas cada hora.

    python medir_senales.py
"""
from __future__ import annotations

import os
import sys
import asyncio
from itertools import combinations

import asyncpg

DSN_V2 = os.environ.get(
    "DSN_V2", "postgresql:///axiom_v2?host=/var/run/postgresql")

UMBRAL_VALOR = 0.85
UMBRAL_VOTO = 0.85


def _pearson(xs, ys):
    n = len(xs)
    if n < 10:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = sum((a - mx) ** 2 for a in xs) ** 0.5
    dy = sum((b - my) ** 2 for b in ys) ** 0.5
    return num / (dx * dy) if dx and dy else None


async def main() -> None:
    conn = await asyncpg.connect(DSN_V2)
    try:
        filas = await conn.fetch("""
            SELECT r.signal_id, r.snapshot_id, r.raw_value, r.voted_regime
            FROM signal_readings r
            WHERE r.is_core AND r.raw_value IS NOT NULL
            ORDER BY r.snapshot_id
        """)
        info = await conn.fetchrow("""
            SELECT COUNT(DISTINCT snapshot_id) AS lecturas,
                   MIN(s.created_at)::date AS desde,
                   MAX(s.created_at)::date AS hasta
            FROM signal_readings r JOIN snapshots s ON s.id = r.snapshot_id
            WHERE r.is_core
        """)
    finally:
        await conn.close()

    # Agrupar por señal, indexado por snapshot para poder alinear
    por_senal: dict[str, dict[int, tuple]] = {}
    for f in filas:
        por_senal.setdefault(f["signal_id"], {})[f["snapshot_id"]] = (
            float(f["raw_value"]), f["voted_regime"])

    print("═" * 74)
    print(f"¿SON INDEPENDIENTES? · {info['lecturas']} lecturas · "
          f"{info['desde']} → {info['hasta']}")
    print("═" * 74)
    print(f"\n{len(por_senal)} señales: {', '.join(sorted(por_senal))}\n")

    pares = []
    for a, b in combinations(sorted(por_senal), 2):
        comunes = sorted(set(por_senal[a]) & set(por_senal[b]))
        if len(comunes) < 30:
            continue
        xs = [por_senal[a][s][0] for s in comunes]
        ys = [por_senal[b][s][0] for s in comunes]
        r = _pearson(xs, ys)
        if r is None:
            continue
        # Coincidencia de VOTO: es lo que realmente afecta a la convicción.
        # Dos señales pueden correlacionar poco en valor y votar igual siempre.
        iguales = sum(1 for s in comunes
                      if por_senal[a][s][1] == por_senal[b][s][1])
        pares.append((a, b, r, iguales / len(comunes), len(comunes)))

    print("▸ PARES MÁS PARECIDOS (por coincidencia de VOTO)")
    print(f"  {'señal A':<20}{'señal B':<20}{'corr':>8}{'voto igual':>12}")
    for a, b, r, v, n in sorted(pares, key=lambda x: -x[3])[:14]:
        marca = " ⚠" if abs(r) >= UMBRAL_VALOR and v >= UMBRAL_VOTO else "  "
        print(f" {marca}{a:<19}{b:<20}{r:>8.3f}{v*100:>11.1f}%")

    print("\n▸ REDUNDANTES según la regla escrita antes de mirar")
    print(f"  (corr >= {UMBRAL_VALOR} Y voto igual >= {UMBRAL_VOTO*100:.0f} %)")
    red = [p for p in pares if abs(p[2]) >= UMBRAL_VALOR and p[3] >= UMBRAL_VOTO]
    if not red:
        print("  NINGUNA. Las señales son independientes y la convicción es")
        print("  legítima — cada voto aporta información propia.")
    else:
        for a, b, r, v, n in sorted(red, key=lambda x: -x[3]):
            print(f"  · {a} ≈ {b}  (corr {r:.3f}, votan igual {v*100:.0f} %)")

    print("\n▸ LAS HIPÓTESIS")
    def _ver(nombre, grupo, umbral):
        dentro = [p for p in pares if p[0] in grupo and p[1] in grupo]
        if not dentro:
            print(f"  {nombre}: sin datos suficientes")
            return
        peor = min(abs(p[2]) for p in dentro)
        ok = peor >= umbral
        print(f"  {nombre}: {'CONFIRMADA' if ok else 'DESCARTADA'} — "
              f"correlación mínima del grupo {peor:.3f} (predije > {umbral})")
        for a, b, r, v, _ in dentro:
            print(f"      {a} ↔ {b}: {r:>7.3f}  voto {v*100:>5.1f}%")

    _ver("H1 tres medias móviles",
         {"mayer_multiple", "price_vs_ma50", "price_vs_ema20"}, 0.80)
    _ver("H2 tres on-chain",
         {"mvrv_zscore", "nupl", "lth_supply"}, 0.70)

    if "btc_dominance" in por_senal:
        suyas = [abs(p[2]) for p in pares if "btc_dominance" in (p[0], p[1])]
        otras = [abs(p[2]) for p in pares if "btc_dominance" not in (p[0], p[1])]
        if suyas and otras:
            ma, mo = sum(suyas)/len(suyas), sum(otras)/len(otras)
            print(f"  H3 btc_dominance aparte: "
                  f"{'CONFIRMADA' if ma < mo else 'DESCARTADA'} — "
                  f"su correlación media es {ma:.3f} contra {mo:.3f} del resto")

    print("\n▸ CUÁNTO APORTA CADA UNA")
    print("  Correlación media con las demás. Alta = dice lo que ya dicen otras.")
    for s in sorted(por_senal):
        suyas = [abs(p[2]) for p in pares if s in (p[0], p[1])]
        if suyas:
            m = sum(suyas) / len(suyas)
            barra = "█" * int(m * 30)
            print(f"  {s:<20}{m:>6.3f}  {barra}")
    print("\n" + "═" * 74)


if __name__ == "__main__":
    asyncio.run(main())
