"""
AXIOM v3 — Captura de flujos y supply de exchanges (Coin Metrics Community).
════════════════════════════════════════════════════════════════════════════════
Cuánto BTC entra/sale de los exchanges (presión de venta potencial vs.
acumulación) y cuánto hay acumulado en ellos. De Coin Metrics Community —API
abierta, holgada (100/min), historia larga—.

FORMA DE LA RESPUESTA (distinta de bitcoin-data): se piden varias métricas
juntas y vienen en el mismo punto temporal:
  {"data":[{"time":"2026-09-05T00:00:00Z",
            "FlowInExNtv":"7360.36","FlowInExNtv-status":"flash",
            "FlowOutExNtv":"8310.24","FlowOutExNtv-status":"flash"}]}
Valores como STRING; `time` ISO; cada métrica trae su `<metrica>-status`
(flash=preliminar / final=consolidado), que se guarda.

MÉTRICAS: se guardan crudas flow_in_ex, flow_out_ex, sply_ex. El neto
(in - out) lo calcula la capacidad al leer —no se guarda derivado—.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

import asyncpg

from backend.fuentes.cliente import ClienteFuentes

logger = logging.getLogger(__name__)

# métrica de Coin Metrics -> nombre interno en onchain_diaria.
_METRICAS = {
    "FlowInExNtv": "flow_in_ex",
    "FlowOutExNtv": "flow_out_ex",
    "SplyExNtv": "sply_ex",
}
# horizonte del backfill: mismo que las otras on-chain, para percentiles comparables.
_DESDE = "2022-09-01"


def _fecha(iso: str) -> date:
    """'2026-09-05T00:00:00.000000000Z' -> date."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")[:19]).date()


async def _guardar(pool, filas: list[tuple]) -> int:
    """filas: [(fecha, metrica, valor, status)]."""
    if not filas:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO onchain_diaria (fecha, metrica, valor, status)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (fecha, metrica) DO UPDATE SET
                valor        = EXCLUDED.valor,
                status       = EXCLUDED.status,
                capturado_at = now()
        """, filas)
    return len(filas)


def _extraer(datos: list) -> list[tuple]:
    """
    De la respuesta de Coin Metrics arma [(fecha, metrica_interna, valor,
    status)]. Cada punto temporal trae varias métricas con su -status.
    """
    filas = []
    for punto in datos:
        f = _fecha(punto["time"])
        for cm_metrica, interna in _METRICAS.items():
            if cm_metrica not in punto:
                continue
            valor = punto[cm_metrica]
            if valor is None:
                continue
            status = punto.get(f"{cm_metrica}-status")
            filas.append((f, interna, float(valor), status))
    return filas


async def _pedir(cliente: ClienteFuentes, desde: str | None) -> list:
    metrics = ",".join(_METRICAS)
    params = {"metrics": metrics}
    if desde:
        params["start_time"] = desde
    r = await cliente.pedir("coinmetrics", "asset_metrics", **params)
    return (r.datos or {}).get("data", []) if isinstance(r.datos, dict) else []


async def backfill(pool: asyncpg.Pool, cliente: ClienteFuentes) -> dict:
    """Trae la serie desde 2022-09 de flow in/out y supply en exchanges."""
    datos = await _pedir(cliente, _DESDE)
    n = await _guardar(pool, _extraer(datos))
    logger.info("[coinmetrics] backfill: %d filas (%d puntos)", n, len(datos))
    return {"backfill": n, "puntos": len(datos)}


async def actualizar(pool: asyncpg.Pool, cliente: ClienteFuentes,
                     dias: int = 10) -> dict:
    """Trae los últimos días y agrega/actualiza (los flash se revisan a final)."""
    from datetime import timedelta
    desde = (date.today() - timedelta(days=dias)).isoformat()
    datos = await _pedir(cliente, desde)
    n = await _guardar(pool, _extraer(datos))
    logger.info("[coinmetrics] actualizado: %d filas", n)
    return {"actualizado": n}


async def estado(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT metrica, COUNT(*) AS dias,
                   MIN(fecha) AS desde, MAX(fecha) AS hasta
            FROM onchain_diaria
            WHERE metrica IN ('flow_in_ex','flow_out_ex','sply_ex')
            GROUP BY metrica ORDER BY metrica
        """)
    return {f["metrica"]: {"dias": f["dias"], "desde": str(f["desde"]),
                           "hasta": str(f["hasta"])} for f in filas}
