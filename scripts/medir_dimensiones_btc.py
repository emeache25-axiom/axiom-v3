#!/usr/bin/env python3
"""
¿LAS DIMENSIONES DEL PERFIL DE BTC SON INDEPENDIENTES?

════════════════════════════════════════════════════════════════════════════════
POR QUÉ ESTA MEDICIÓN VA ANTES DE DECLARAR NADA:

  Un perfil de N dimensiones solo aporta N cosas si las dimensiones miden
  cosas DISTINTAS. Si dos son variantes de la misma, el perfil aparenta
  riqueza y repite información — que es exactamente lo que encontramos en las
  12 señales de v2: seis de doce votaban lo mismo más del 90 % del tiempo.

  Es el mismo criterio que sirvió con los pares: `rango` y `oscilacion`
  resultaron independientes (correlación 0,049) y por eso las dos valen.

HIPÓTESIS, escritas ANTES de mirar:

  H1  DIRECCIÓN y POSICIÓN correlacionan fuerte. Si el precio subió mucho en
      la ventana, está cerca de su máximo reciente. Predicción: |r| > 0,70.
      Si se confirma, una de las dos sobra.

  H2  VOLATILIDAD y ESTRUCTURA son independientes, como pasó en los pares.
      Un mercado puede moverse mucho tendiendo o moviéndose mucho y
      volviendo. Predicción: |r| < 0,30.

  H3  PARTICIPACIÓN es la más independiente de todas: el volumen no tiene por
      qué acompañar al precio. Predicción: su correlación media es la menor.

REGLA DE DESCARTE:
  Dos dimensiones con |r| > 0,70 sobre 3.000+ días son redundantes: aportan
  una donde parecen dos. Se conserva la más interpretable y se declara por qué
  se descartó la otra.

LO QUE ESTO NO PRUEBA:
  Que las dimensiones sirvan para algo. Mide si son distintas entre sí, no si
  describen el mercado de forma útil. Eso es otra pregunta y otra medición.

    python medir_dimensiones_btc.py [--ventana 30]
"""
from __future__ import annotations

import os
import sys
import asyncio
import argparse
from itertools import combinations
from math import log, sqrt

import asyncpg


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


def _pearson(xs, ys):
    pares = [(a, b) for a, b in zip(xs, ys) if a is not None and b is not None]
    n = len(pares)
    if n < 30:
        return None, 0
    mx = sum(p[0] for p in pares) / n
    my = sum(p[1] for p in pares) / n
    num = sum((a - mx) * (b - my) for a, b in pares)
    dx = sqrt(sum((a - mx) ** 2 for a, _ in pares))
    dy = sqrt(sum((b - my) ** 2 for _, b in pares))
    return (num / (dx * dy) if dx and dy else None), n


def _percentil(valor, serie):
    """Qué proporción de la serie es menor que el valor."""
    if not serie:
        return None
    return sum(1 for x in serie if x < valor) / len(serie) * 100


async def main(ventana: int) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        velas = await conn.fetch("""
            SELECT fecha, apertura, maximo, minimo, cierre, volumen
            FROM btc_vela_diaria ORDER BY fecha
        """)
        desde_vol = await conn.fetchval(
            "SELECT comparable_desde FROM btc_metricas_validas WHERE tipo='volumen'")
    finally:
        await conn.close()

    if len(velas) < ventana * 3:
        print("No hay velas suficientes."); return

    f = [v["fecha"] for v in velas]
    c = [float(v["cierre"]) for v in velas]
    h = [float(v["maximo"]) for v in velas]
    l = [float(v["minimo"]) for v in velas]
    vol = [float(v["volumen"]) * float(v["cierre"]) for v in velas]

    print("═" * 76)
    print(f"DIMENSIONES DEL PERFIL DE BTC · ventana {ventana} días")
    print(f"{len(velas)} velas · {f[0]} → {f[-1]}")
    print("═" * 76)

    # ── Las cinco dimensiones, calculadas día por día ────────────────────────
    dims: dict[str, list] = {k: [] for k in
                             ("direccion", "volatilidad", "estructura",
                              "posicion", "participacion")}

    for i in range(len(velas)):
        if i < ventana:
            for k in dims:
                dims[k].append(None)
            continue

        w_c = c[i - ventana + 1: i + 1]
        w_h = h[i - ventana + 1: i + 1]
        w_l = l[i - ventana + 1: i + 1]
        w_v = vol[i - ventana + 1: i + 1]

        # DIRECCIÓN — retorno acumulado de la ventana, en %
        dims["direccion"].append((w_c[-1] / w_c[0] - 1) * 100)

        # VOLATILIDAD — desvío de los retornos LOGARÍTMICOS diarios,
        # anualizado. Se usan logs para que una suba del 50 % y una baja del
        # 33 % —que se cancelan— pesen igual.
        rets = [log(w_c[j] / w_c[j - 1]) for j in range(1, len(w_c))
                if w_c[j - 1] > 0]
        if len(rets) > 2:
            m = sum(rets) / len(rets)
            sd = sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
            dims["volatilidad"].append(sd * sqrt(365) * 100)
        else:
            dims["volatilidad"].append(None)

        # ESTRUCTURA — 1 − |desplazamiento neto| / recorrido total.
        # 1 = recorre mucho y vuelve; 0 = se desplaza en línea recta.
        # Es la misma oscilación que se usa en pares.
        recorrido = sum((w_h[j] - w_l[j]) / w_l[j] * 100
                        for j in range(len(w_h)) if w_l[j] > 0)
        neto = abs((w_c[-1] / w_c[0] - 1) * 100)
        dims["estructura"].append(
            max(0.0, min(1.0, 1 - neto / recorrido)) if recorrido > 0 else None)

        # POSICIÓN — distancia al máximo de TODA la historia previa, en %.
        # Negativo salvo en máximo nuevo.
        maximo_historico = max(h[: i + 1])
        dims["posicion"].append((c[i] / maximo_historico - 1) * 100)

        # PARTICIPACIÓN — volumen de la ventana contra su media larga.
        # Solo desde donde el volumen es comparable: medido, el de 2017 fue
        # sesenta veces menor que el de 2021, así que antes mide el
        # crecimiento de Binance y no el mercado.
        if desde_vol and f[i] >= desde_vol and i >= ventana * 4:
            largo = vol[i - ventana * 4: i + 1]
            media_larga = sum(largo) / len(largo)
            media_corta = sum(w_v) / len(w_v)
            dims["participacion"].append(
                media_corta / media_larga if media_larga > 0 else None)
        else:
            dims["participacion"].append(None)

    # ── Correlaciones ───────────────────────────────────────────────────────
    print("\n▸ ¿SON INDEPENDIENTES?")
    print(f"  {'dimensión A':<16}{'dimensión B':<16}{'corr':>9}{'días':>9}")
    corr = {}
    for a, b in combinations(dims, 2):
        r, n = _pearson(dims[a], dims[b])
        if r is None:
            continue
        corr[(a, b)] = r
        marca = " ⚠" if abs(r) > 0.70 else "  "
        print(f" {marca}{a:<15}{b:<16}{r:>9.3f}{n:>9}")

    print("\n▸ LAS HIPÓTESIS")
    def _ver(nombre, a, b, cond, pred):
        r = corr.get((a, b)) or corr.get((b, a))
        if r is None:
            print(f"  {nombre}: sin datos"); return
        ok = cond(abs(r))
        print(f"  {nombre}: {'CONFIRMADA' if ok else 'DESCARTADA'} — "
              f"r = {r:.3f} (predije {pred})")

    _ver("H1 dirección ≈ posición", "direccion", "posicion",
         lambda x: x > 0.70, "|r| > 0,70")
    _ver("H2 volatilidad ⊥ estructura", "volatilidad", "estructura",
         lambda x: x < 0.30, "|r| < 0,30")

    medias = {}
    for d in dims:
        suyas = [abs(v) for (a, b), v in corr.items() if d in (a, b)]
        if suyas:
            medias[d] = sum(suyas) / len(suyas)
    if medias:
        menor = min(medias, key=medias.get)
        print(f"  H3 participación la más independiente: "
              f"{'CONFIRMADA' if menor == 'participacion' else 'DESCARTADA'} — "
              f"la menor correlación media es {menor} ({medias[menor]:.3f})")

    print("\n▸ CUÁNTO APORTA CADA UNA")
    print("  Correlación media con las demás. Alta = repite lo que otras dicen.")
    for d, m in sorted(medias.items(), key=lambda x: x[1]):
        print(f"  {d:<16}{m:>6.3f}  {'█' * int(m * 40)}")

    print("\n▸ REDUNDANTES según la regla escrita antes de mirar")
    red = [(a, b, r) for (a, b), r in corr.items() if abs(r) > 0.70]
    if not red:
        print("  NINGUNA. Las cinco dimensiones son independientes.")
    else:
        for a, b, r in sorted(red, key=lambda x: -abs(x[2])):
            print(f"  · {a} ≈ {b}  (r = {r:.3f}) — aportan una donde parecen dos")

    # ── Hoy ─────────────────────────────────────────────────────────────────
    print("\n▸ EL PERFIL DE HOY")
    print(f"  {'dimensión':<16}{'valor':>12}{'percentil':>12}  lectura")
    hoy = {}
    for d in dims:
        v = dims[d][-1]
        if v is None:
            continue
        serie = [x for x in dims[d] if x is not None]
        p = _percentil(v, serie)
        hoy[d] = (v, p)
        # El percentil es lo comparable; el valor absoluto es el hecho.
        lect = ("muy bajo" if p < 10 else "bajo" if p < 30 else
                "medio" if p < 70 else "alto" if p < 90 else "muy alto")
        print(f"  {d:<16}{v:>12.2f}{p:>11.1f}%  {lect} contra su propia historia")

    print("\n  El PERCENTIL es lo comparable entre dimensiones —cada una tiene")
    print("  su escala—. El VALOR es el hecho. Ninguna lectura de acá supone")
    print("  que el estado persista ni que condicione lo que viene.")
    print("\n" + "═" * 76)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ventana", type=int, default=30)
    a = ap.parse_args()
    asyncio.run(main(a.ventana))
