"""
AXIOM v3 — Captura de la serie de Bitcoin.
════════════════════════════════════════════════════════════════════════════════
BTC es un OBJETO PROPIO, no un par más.

  · `pares` tiene BTC/USDT en MEXC y CoinEx: mercados OPERABLES, con su libro,
    su spread y su profundidad.
  · Esto es la serie de REFERENCIA, traída de Binance, que no es un exchange
    donde AXIOM opere.

  Mezclarlas invitaría al error de leer el spread de Binance para decidir una
  operación en MEXC.

QUÉ SE CAPTURA:
  · velas DIARIAS desde 2017-08-17 — 3.297 al 26/08/2026, sin huecos
  · velas HORARIAS — ~80.000 para nueve años, unos 80 MB

  Las horarias se capturan SOLO para BTC. Para los ~3.000 pares serían millones
  de filas para responder preguntas que se hacen de a un par: ahí se piden al
  exchange en el momento.

LO QUE LA SERIE NO ES:
  HOMOGÉNEA. Medido: el volumen medio diario de 2017 fue 53 M USD contra
  3.170 M en 2021 — sesenta veces menos. Cualquier métrica de volumen sobre
  todo el período mide el crecimiento de Binance, no el mercado. Por eso existe
  `btc_metricas_validas`, que declara desde cuándo vale cada tipo de métrica.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, date, timedelta

import asyncpg

logger = logging.getLogger(__name__)

# Fuente y símbolo. Binance porque tiene la historia más larga disponible por
# ccxt: desde agosto de 2017. MEXC no devuelve nada tan atrás y CoinEx arranca
# en diciembre de 2023.
EXCHANGE = "binance"
SIMBOLO = "BTC/USDT"

# El primer día con datos. Antes de esto Binance no existía.
ORIGEN_MS = 1502928000000        # 2017-08-17

POR_LLAMADA = 1000               # el máximo que devuelve ccxt
PAUSA = 0.3                      # entre llamadas, para no gatillar el límite


def _hoy_utc() -> date:
    return datetime.now(timezone.utc).date()


async def _abrir():
    import ccxt.async_support as ccxt
    # defaultType=spot evita que ccxt cargue también los contratos, que es lo
    # que hizo dar timeout a MEXC.
    return ccxt.binance({"options": {"defaultType": "spot"}, "timeout": 60000})


async def _traer(ex, temporalidad: str, desde_ms: int) -> list:
    """
    Trae todas las velas desde `desde_ms` paginando de a 1.000.

    Se pide desde la ÚLTIMA vela + un período, no desde el principio: en el
    refresco diario eso son 2 velas en vez de 3.297.
    """
    todas: list = []
    cursor = desde_ms
    paso = 86400000 if temporalidad == "1d" else 3600000
    while True:
        velas = await ex.fetch_ohlcv(SIMBOLO, temporalidad,
                                     since=cursor, limit=POR_LLAMADA)
        if not velas:
            break
        todas += velas
        if len(velas) < POR_LLAMADA:
            break
        cursor = velas[-1][0] + paso
        await asyncio.sleep(PAUSA)
    return todas


async def capturar_diarias(pool: asyncpg.Pool, completo: bool = False) -> dict:
    """
    Velas diarias de BTC.

    `completo=True` trae toda la historia desde 2017; si no, solo lo que falta.
    Idempotente: `ON CONFLICT` actualiza.
    """
    async with pool.acquire() as conn:
        ultima = await conn.fetchval("SELECT MAX(fecha) FROM btc_vela_diaria")

    if completo or ultima is None:
        desde = ORIGEN_MS
    else:
        # Desde la última guardada, para recapturarla por si estaba incompleta.
        desde = int(datetime.combine(
            ultima, datetime.min.time(), timezone.utc).timestamp() * 1000)

    ex = await _abrir()
    try:
        velas = await _traer(ex, "1d", desde)
    finally:
        await ex.close()

    hoy = _hoy_utc()
    filas = []
    for t, o, h, l, c, v in velas:
        f = datetime.fromtimestamp(t / 1000, timezone.utc).date()
        # La vela de HOY está incompleta: se excluye. Guardarla daría un rango
        # de horas presentado como el del día.
        if f >= hoy:
            continue
        filas.append((f, o, h, l, c, v))

    if filas:
        async with pool.acquire() as conn:
            await conn.executemany("""
                INSERT INTO btc_vela_diaria (fecha,apertura,maximo,minimo,cierre,volumen)
                VALUES ($1,$2,$3,$4,$5,$6)
                ON CONFLICT (fecha) DO UPDATE SET
                    apertura=EXCLUDED.apertura, maximo=EXCLUDED.maximo,
                    minimo=EXCLUDED.minimo,     cierre=EXCLUDED.cierre,
                    volumen=EXCLUDED.volumen,   capturado_at=now()
            """, filas)

    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM btc_vela_diaria")
        desde_f = await conn.fetchval("SELECT MIN(fecha) FROM btc_vela_diaria")
        hasta_f = await conn.fetchval("SELECT MAX(fecha) FROM btc_vela_diaria")

    logger.info("[btc] diarias: %d nuevas · %d en total · %s → %s",
                len(filas), total, desde_f, hasta_f)
    return {"nuevas": len(filas), "total": total,
            "desde": str(desde_f), "hasta": str(hasta_f)}


async def capturar_horarias(pool: asyncpg.Pool, completo: bool = False) -> dict:
    """
    Velas horarias de BTC.

    Habilitan lo que la vela diaria no puede mostrar: en qué franja del día
    ocurre el máximo, con qué frecuencia el máximo llega antes que el mínimo, y
    la volatilidad intradía.

    Nueve años son ~80.000 velas y unas 80 llamadas paginadas.
    """
    async with pool.acquire() as conn:
        ultima = await conn.fetchval("SELECT MAX(hora) FROM btc_vela_horaria")

    if completo or ultima is None:
        desde = ORIGEN_MS
    else:
        desde = int(ultima.timestamp() * 1000)

    ex = await _abrir()
    try:
        velas = await _traer(ex, "1h", desde)
    finally:
        await ex.close()

    ahora = datetime.now(timezone.utc)
    filas = []
    for t, o, h, l, c, v in velas:
        hora = datetime.fromtimestamp(t / 1000, timezone.utc)
        # La hora en curso está incompleta.
        if hora >= ahora.replace(minute=0, second=0, microsecond=0):
            continue
        filas.append((hora, o, h, l, c, v))

    if filas:
        async with pool.acquire() as conn:
            # De a 5.000 para no armar una sentencia enorme en el backfill
            # inicial, que son ~80.000 filas.
            for i in range(0, len(filas), 5000):
                await conn.executemany("""
                    INSERT INTO btc_vela_horaria (hora,apertura,maximo,minimo,cierre,volumen)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    ON CONFLICT (hora) DO UPDATE SET
                        apertura=EXCLUDED.apertura, maximo=EXCLUDED.maximo,
                        minimo=EXCLUDED.minimo,     cierre=EXCLUDED.cierre,
                        volumen=EXCLUDED.volumen,   capturado_at=now()
                """, filas[i:i+5000])

    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM btc_vela_horaria")
        desde_h = await conn.fetchval("SELECT MIN(hora) FROM btc_vela_horaria")
        hasta_h = await conn.fetchval("SELECT MAX(hora) FROM btc_vela_horaria")

    logger.info("[btc] horarias: %d nuevas · %d en total", len(filas), total)
    return {"nuevas": len(filas), "total": total,
            "desde": str(desde_h)[:16], "hasta": str(hasta_h)[:16]}


async def estado(pool: asyncpg.Pool) -> dict:
    """
    Qué historia hay, y desde cuándo vale cada tipo de métrica.

    La validez viene de `btc_metricas_validas`, no de un comentario: es un dato
    consultable y no algo que haya que recordar.
    """
    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT (SELECT COUNT(*)  FROM btc_vela_diaria)  AS dias,
                   (SELECT MIN(fecha) FROM btc_vela_diaria) AS desde,
                   (SELECT MAX(fecha) FROM btc_vela_diaria) AS hasta,
                   (SELECT COUNT(*)  FROM btc_vela_horaria) AS horas
        """)
        validas = await conn.fetch(
            "SELECT tipo, comparable_desde FROM btc_metricas_validas ORDER BY tipo")
        halving = await conn.fetchrow("""
            SELECT numero, fecha, recompensa,
                   ((now() AT TIME ZONE 'utc')::date - fecha) AS dias_desde
            FROM btc_halvings
            WHERE fecha <= (now() AT TIME ZONE 'utc')::date
            ORDER BY fecha DESC LIMIT 1
        """)
        proximo = await conn.fetchrow("""
            SELECT numero, fecha, estimado,
                   (fecha - (now() AT TIME ZONE 'utc')::date) AS dias_hasta
            FROM btc_halvings
            WHERE fecha > (now() AT TIME ZONE 'utc')::date
            ORDER BY fecha LIMIT 1
        """)

    # Huecos: la serie debería ser continua. Un faltante es un día que no
    # existe, y conviene verlo antes de calcular nada encima.
    esperados = ((r["hasta"] - r["desde"]).days + 1) if r["desde"] else 0

    return {
        "velas_diarias": r["dias"],
        "velas_horarias": r["horas"],
        "desde": str(r["desde"]),
        "hasta": str(r["hasta"]),
        "dias_esperados": esperados,
        "huecos": esperados - r["dias"] if esperados else 0,
        "comparable_desde": {v["tipo"]: str(v["comparable_desde"]) for v in validas},
        "ultimo_halving": (
            {"numero": halving["numero"], "fecha": str(halving["fecha"]),
             "hace_dias": halving["dias_desde"],
             "recompensa_btc": float(halving["recompensa"])}
            if halving else None),
        "proximo_halving": (
            {"numero": proximo["numero"], "fecha": str(proximo["fecha"]),
             "en_dias": proximo["dias_hasta"], "estimado": proximo["estimado"]}
            if proximo else None),
    }
