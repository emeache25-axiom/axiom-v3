"""
AXIOM v3 — Captura del funding de BTC.
════════════════════════════════════════════════════════════════════════════════
Qué cuesta mantener una posición apalancada. Es la otra mitad del
posicionamiento: las opciones muestran DÓNDE está el dinero apostado, el
funding muestra QUÉ CUESTA sostener una posición.

POR QUÉ DERIBIT:
  Medido el 29/08/2026 sobre seis exchanges de perpetuos: LOS SEIS tienen el
  funding saturado en 0,0100 %. No es peculiaridad de ninguno — es la tasa base
  del mecanismo, que se aplica cuando la prima sobre el índice es chica.

  Sobre siete años de Binance, el 35,4 % de los registros están exactamente
  ahí. Eso crea un escalón en el medio de la distribución y el percentil deja
  de discriminar justo donde el mercado pasa más tiempo.

  Deribit no satura porque su perpetuo es INVERSO y calcula distinto: su valor
  más repetido aparece en el 7 % de los registros. Y es HORARIO, no cada
  8 horas.

CUÁNTA HISTORIA:
  Desde enero de 2020 — verificado pidiendo 2018, 2019, 2020 y 2021: los dos
  primeros vuelven vacíos, 2020 devuelve datos. Seis años y medio.

  La API entrega un mes por llamada (721 registros), así que el histórico
  completo son ~80 llamadas. Una sola vez.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

import asyncpg

logger = logging.getLogger(__name__)

SIMBOLO = "BTC/USD:BTC"
ORIGEN = datetime(2020, 1, 1, tzinfo=timezone.utc)
PAUSA = 0.4


async def _abrir():
    import ccxt.async_support as ccxt
    return ccxt.deribit({"timeout": 60000})


async def capturar(pool: asyncpg.Pool, completo: bool = False) -> dict:
    """
    Trae el funding que falta.

    `completo=True` va desde 2020; si no, desde la última hora guardada. En el
    refresco diario son 24 registros y una llamada.
    """
    async with pool.acquire() as conn:
        ultima = await conn.fetchval("SELECT MAX(hora) FROM funding_btc")

    desde = ORIGEN if (completo or ultima is None) else ultima

    ex = await _abrir()
    todas: list = []
    try:
        cursor = desde
        ahora = datetime.now(timezone.utc)
        while cursor < ahora:
            h = await ex.fetch_funding_rate_history(
                SIMBOLO, since=int(cursor.timestamp() * 1000), limit=1000)
            if not h:
                # Sin datos en este tramo: se avanza igual, porque un mes vacío
                # no significa que no haya nada después.
                cursor += timedelta(days=30)
                continue
            todas += h
            ultimo = datetime.fromtimestamp(h[-1]["timestamp"] / 1000, timezone.utc)
            if ultimo <= cursor:
                # La API no avanzó: se fuerza el salto para no quedar en bucle.
                cursor += timedelta(days=30)
            else:
                cursor = ultimo + timedelta(seconds=1)
            await asyncio.sleep(PAUSA)
    finally:
        await ex.close()

    filas = []
    vistas = set()
    for x in todas:
        t = x.get("fundingRate")
        ts = x.get("timestamp")
        if t is None or ts is None:
            continue
        hora = datetime.fromtimestamp(ts / 1000, timezone.utc)
        if hora in vistas:
            continue
        vistas.add(hora)
        filas.append((hora, t))

    if filas:
        async with pool.acquire() as conn:
            for i in range(0, len(filas), 5000):
                await conn.executemany("""
                    INSERT INTO funding_btc (hora, tasa) VALUES ($1, $2)
                    ON CONFLICT (hora) DO UPDATE SET
                        tasa = EXCLUDED.tasa, capturado_at = now()
                """, filas[i:i + 5000])

    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT COUNT(*) AS total, MIN(hora) AS desde, MAX(hora) AS hasta
            FROM funding_btc
        """)

    logger.info("[funding] %d nuevos · %d en total · %s → %s",
                len(filas), r["total"],
                str(r["desde"])[:10], str(r["hasta"])[:16])
    return {"nuevos": len(filas), "total": r["total"],
            "desde": str(r["desde"])[:10], "hasta": str(r["hasta"])[:16]}


async def estado(pool: asyncpg.Pool) -> dict:
    """
    Qué hay capturado y cómo se distribuye.

    El campo que importa es `en_valor_mas_repetido`: si un valor concentra
    mucho, la serie está saturada y el percentil no discrimina ahí. Es lo que
    descartó a Binance como fuente.
    """
    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT COUNT(*) AS registros, MIN(hora) AS desde, MAX(hora) AS hasta,
                   ROUND(MIN(tasa)*100, 4) AS min_pct,
                   ROUND(MAX(tasa)*100, 4) AS max_pct,
                   ROUND(AVG(tasa)*100, 5) AS medio_pct,
                   COUNT(*) FILTER (WHERE tasa < 0) AS negativos
            FROM funding_btc
        """)
        if not r or not r["registros"]:
            return {"registros": 0}
        rep = await conn.fetchrow("""
            SELECT tasa, COUNT(*) AS veces FROM funding_btc
            GROUP BY tasa ORDER BY veces DESC LIMIT 1
        """)

    return {
        "registros": r["registros"],
        "desde": str(r["desde"])[:10],
        "hasta": str(r["hasta"])[:16],
        "minimo_pct": float(r["min_pct"]),
        "maximo_pct": float(r["max_pct"]),
        "medio_pct": float(r["medio_pct"]),
        "negativos_pct": round(r["negativos"] / r["registros"] * 100, 1),
        "valor_mas_repetido_pct": float(rep["tasa"]) * 100 if rep else None,
        "en_valor_mas_repetido_pct": (
            round(rep["veces"] / r["registros"] * 100, 1) if rep else None),
    }
