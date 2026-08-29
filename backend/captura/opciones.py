"""
AXIOM v3 — Captura de la cadena de opciones de BTC.
════════════════════════════════════════════════════════════════════════════════
Una foto diaria del posicionamiento en opciones: cuánto interés abierto hay en
cada strike y cada vencimiento, y con qué volatilidad implícita.

POR QUÉ DERIBIT:
  Es donde se forma el precio de las opciones de cripto — 1.741 contratos de
  BTC listados. Los exchanges de perpetuos no tienen mercado de opciones
  comparable.

POR QUÉ FOTO DIARIA:
  La pregunta que decide es "¿hoy hay más interés abierto que ayer?". Deribit
  devuelve el estado ACTUAL, no el de hace una semana: si no se captura hoy,
  ese día no existe nunca más.

  Sin historia no se puede responder si el interés crece, si migra de strike, o
  si cambió el sesgo — que son las preguntas que importan.

CUÁNTO CUESTA:
  Medido el 29/08/2026: `fetch_tickers` con `kind=option` trae 1.026 contratos
  con su interés abierto EN UNA SOLA LLAMADA, en 2,4 segundos. La captura es
  trivial.

QUÉ NO DICE EL INTERÉS ABIERTO:
  De qué lado está cada participante. Un call abierto tiene un comprador y un
  vendedor; el interés abierto cuenta el CONTRATO, no la dirección.

  Leer "hay mucho interés en calls de 100.000" como "el mercado espera 100.000"
  es un error común: por cada comprador de ese call hay alguien que lo vendió y
  cobra si no llega.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, date

import asyncpg

logger = logging.getLogger(__name__)

EXCHANGE = "deribit"
SUBYACENTE = "BTC"

# El símbolo de ccxt: BTC/USD:BTC-260925-100000-C
_SIMBOLO = re.compile(r"-(\d{6})-(\d+(?:\.\d+)?)-([CP])$")


def _hoy_utc() -> date:
    return datetime.now(timezone.utc).date()


def _descomponer(simbolo: str) -> tuple[date, float, str] | None:
    """
    Saca vencimiento, strike y tipo del símbolo.

    Se parsea el símbolo en vez de leer los campos del mercado porque así la
    captura no depende de haber cargado `load_markets` — una llamada menos y un
    punto menos de falla.
    """
    m = _SIMBOLO.search(simbolo)
    if not m:
        return None
    aammdd, strike, tipo = m.groups()
    try:
        venc = datetime.strptime(aammdd, "%y%m%d").date()
    except ValueError:
        return None
    return venc, float(strike), ("call" if tipo == "C" else "put")


async def _abrir():
    import ccxt.async_support as ccxt
    return ccxt.deribit({"timeout": 60000})


async def capturar(pool: asyncpg.Pool, fecha: date | None = None) -> dict:
    """
    La cadena completa, en una llamada.

    Idempotente: `ON CONFLICT` actualiza, así que correrlo dos veces el mismo
    día refresca en vez de duplicar.
    """
    fecha = fecha or _hoy_utc()
    ex = await _abrir()
    try:
        tickers = await ex.fetch_tickers(
            params={"currency": SUBYACENTE, "kind": "option"})
    finally:
        await ex.close()

    if not tickers:
        raise RuntimeError("Deribit no devolvió ninguna opción")

    filas = []
    sin_parsear = 0
    precio_sub = None

    for simbolo, t in tickers.items():
        partes = _descomponer(simbolo)
        if partes is None:
            sin_parsear += 1
            continue
        venc, strike, tipo = partes
        info = t.get("info") or {}

        # El precio del subyacente viene en cada ticker; se toma el primero que
        # aparezca. Sin esto no se puede reconstruir después qué strikes
        # estaban dentro o fuera del dinero.
        if precio_sub is None:
            u = info.get("underlying_price") or info.get("index_price")
            if u:
                precio_sub = float(u)

        def _num(v):
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        filas.append((
            fecha, simbolo, SUBYACENTE, venc, strike, tipo,
            _num(info.get("open_interest")),
            _num(info.get("volume")),
            _num(info.get("mark_iv")),
            _num(info.get("mark_price")),
            precio_sub,
        ))

    if not filas:
        raise RuntimeError("ninguna opción pudo interpretarse")

    async with pool.acquire() as conn:
        # De a 2.000 para no armar una sentencia enorme.
        for i in range(0, len(filas), 2000):
            await conn.executemany("""
                INSERT INTO opcion_diaria (fecha, simbolo, subyacente,
                    vencimiento, strike, tipo, interes_abierto, volumen_24h,
                    iv, precio_marca, subyacente_precio)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                ON CONFLICT (fecha, simbolo) DO UPDATE SET
                    interes_abierto   = EXCLUDED.interes_abierto,
                    volumen_24h       = EXCLUDED.volumen_24h,
                    iv                = EXCLUDED.iv,
                    precio_marca      = EXCLUDED.precio_marca,
                    subyacente_precio = EXCLUDED.subyacente_precio,
                    capturado_at      = now()
            """, filas[i:i + 2000])

        r = await conn.fetchrow("""
            SELECT COUNT(*) AS contratos,
                   COUNT(DISTINCT vencimiento) AS vencimientos,
                   SUM(interes_abierto)         AS interes_total,
                   COUNT(DISTINCT fecha)        AS dias
            FROM opcion_diaria WHERE fecha = $1
        """, fecha)
        dias = await conn.fetchval(
            "SELECT COUNT(DISTINCT fecha) FROM opcion_diaria")

    logger.info("[opciones] %s: %d contratos · %d vencimientos · %d días de historia",
                fecha, r["contratos"], r["vencimientos"], dias)
    return {
        "fecha": str(fecha),
        "contratos": r["contratos"],
        "vencimientos": r["vencimientos"],
        "interes_total": float(r["interes_total"] or 0),
        "subyacente_precio": precio_sub,
        "sin_parsear": sin_parsear,
        "dias_de_historia": dias,
    }


async def estado(pool: asyncpg.Pool) -> dict:
    """Qué hay capturado, y cómo viene cambiando."""
    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT COUNT(DISTINCT fecha) AS dias,
                   MIN(fecha) AS desde, MAX(fecha) AS hasta,
                   COUNT(*)   AS filas
            FROM opcion_diaria
        """)
        if not r or not r["dias"]:
            return {"dias": 0}

        # La pregunta que motivó guardar esto: ¿hoy hay más que ayer?
        evolucion = await conn.fetch("""
            SELECT fecha,
                   COUNT(*)                                        AS contratos,
                   ROUND(SUM(interes_abierto)::numeric, 1)         AS interes,
                   ROUND(SUM(interes_abierto) FILTER (WHERE tipo='put')::numeric
                         / NULLIF(SUM(interes_abierto)
                                  FILTER (WHERE tipo='call'), 0), 3) AS put_call
            FROM opcion_diaria
            GROUP BY fecha ORDER BY fecha DESC LIMIT 7
        """)

    return {
        "dias": r["dias"],
        "desde": str(r["desde"]),
        "hasta": str(r["hasta"]),
        "filas": r["filas"],
        "ultimos_dias": [
            {"fecha": str(e["fecha"]), "contratos": e["contratos"],
             "interes_abierto": float(e["interes"] or 0),
             # Por cada contrato de call, cuántos de put. Más de 1 es más
             # dinero en protección que en apuestas al alza — con la salvedad
             # de que el interés abierto no dice de qué lado está cada uno.
             "put_call": float(e["put_call"]) if e["put_call"] else None}
            for e in evolucion
        ],
    }
