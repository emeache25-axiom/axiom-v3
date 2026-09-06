"""
AXIOM v3 — Captura de correlación de BTC con mercados tradicionales (Sharpe).
════════════════════════════════════════════════════════════════════════════════
¿BTC se mueve junto con el S&P/oro o independiente? Una cara del estado del
mercado. Fuente: sharpe.ai, correlación de Pearson que ellos calculan sobre
precios de terceros (agregador, no fuente primaria).

FORMA DE LA RESPUESTA (anidada, se procesa acá, no por mapeo declarativo):
  { "pair": ["bitcoin","sp500"],
    "windows": [ {"label":"30 obs","data":[{"date":..,"value":..}, ...]},
                 {"label":"60 obs", ...}, {"label":"90 obs", ...} ] }
  La ventana "1095 obs" viene vacía: se ignora.

TOLERANCIA: Sharpe a veces devuelve un par vacío (glitch de caché). Se guarda lo
que venga y se sigue —no se rompe por un par que falló—.
"""
from __future__ import annotations

import logging
from datetime import date

import asyncpg

from backend.fuentes.cliente import ClienteFuentes

logger = logging.getLogger(__name__)

# par interno -> (asset1, asset2) de Sharpe.
_PARES = {
    "btc-sp500": ("bitcoin", "sp500"),
    "btc-gold": ("bitcoin", "gold"),
}

# Ventanas rolling que guardamos (obs). La 1095 viene vacía en el free.
_VENTANAS = {30, 60, 90}


def _ventana_de_label(label: str) -> int | None:
    """'90 obs' -> 90. None si no es una ventana que seguimos."""
    try:
        n = int(label.split()[0])
    except (ValueError, IndexError):
        return None
    return n if n in _VENTANAS else None


async def _guardar(pool, par: str, puntos_por_ventana: dict) -> int:
    """puntos_por_ventana: {ventana: [(fecha, valor), ...]}."""
    filas = []
    for ventana, puntos in puntos_por_ventana.items():
        for f, v in puntos:
            if v is None:
                continue
            if isinstance(f, str):
                f = date.fromisoformat(f)
            filas.append((f, par, ventana, float(v)))
    if not filas:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO correlacion_diaria (fecha, par, ventana, valor)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (fecha, par, ventana) DO UPDATE SET
                valor        = EXCLUDED.valor,
                capturado_at = now()
        """, filas)
    return len(filas)


async def _pedir_par(cliente: ClienteFuentes, par: str, period: str) -> dict:
    """Pide la historia de un par y arma {ventana: [(fecha,valor)]}."""
    a1, a2 = _PARES[par]
    r = await cliente.pedir("sharpe", "correlacion_historia",
                            asset1=a1, asset2=a2, period=period)
    out = {}
    if not r.datos:
        return out
    for w in r.datos.get("windows", []):
        ventana = _ventana_de_label(w.get("label", ""))
        if ventana is None:
            continue
        puntos = [(p.get("date"), p.get("value")) for p in w.get("data", [])
                  if p.get("date") and p.get("value") is not None]
        if puntos:
            out[ventana] = puntos
    return out


async def backfill(pool: asyncpg.Pool, cliente: ClienteFuentes) -> dict:
    """Trae la serie completa (~3 años) de cada par y la guarda."""
    total = {}
    for par in _PARES:
        try:
            puntos = await _pedir_par(cliente, par, "3y")
            n = await _guardar(pool, par, puntos)
            total[par] = n
            logger.info("[correlacion] backfill %s: %d puntos (%d ventanas)",
                        par, n, len(puntos))
        except Exception as e:
            logger.warning("[correlacion] backfill %s falló: %s", par, e)
            total[par] = 0
    return {"backfill": total}


async def actualizar(pool: asyncpg.Pool, cliente: ClienteFuentes) -> dict:
    """Trae la ventana reciente (1y) de cada par y agrega lo nuevo. Diario."""
    total = {}
    for par in _PARES:
        try:
            puntos = await _pedir_par(cliente, par, "1y")
            total[par] = await _guardar(pool, par, puntos)
        except Exception as e:
            logger.warning("[correlacion] actualizar %s falló: %s", par, e)
            total[par] = 0
    logger.info("[correlacion] actualizado: %s", total)
    return {"actualizado": total}


async def estado(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT par, ventana, COUNT(*) AS dias,
                   MIN(fecha) AS desde, MAX(fecha) AS hasta
            FROM correlacion_diaria GROUP BY par, ventana ORDER BY par, ventana
        """)
    return {f"{f['par']}/{f['ventana']}": {"dias": f["dias"],
            "desde": str(f["desde"]), "hasta": str(f["hasta"])} for f in filas}
