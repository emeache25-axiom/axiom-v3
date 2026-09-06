"""
AXIOM v3 — Captura de métricas on-chain de BTC (bitcoin-data.com).
════════════════════════════════════════════════════════════════════════════════
On-chain mira la CADENA, no los mercados. bitcoin-data.com (BGeometrics) sirve
las métricas calculadas desde su propio nodo Bitcoin, API oficial y abierta (sin
key en el free tier). Es lo contrario del scraping frágil de v2.

DOS MODOS:
  backfill()  — la primera vez: trae la serie completa (4 años) de cada métrica
                en UNA request y la guarda. La historia queda NUESTRA aunque la
                fuente la olvide (su ventana gratuita es móvil de 4 años).
  actualizar()— cada día: trae solo los últimos días y agrega el nuevo. Barato,
                entra holgado en el cupo de 15 req/día.

Las métricas seguidas hoy: MVRV Z-Score y NUPL. Sumar otra es agregar su
endpoint en fuentes.yaml y una línea en _METRICAS.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import asyncpg

from backend.fuentes.cliente import ClienteFuentes
from backend.nucleo import config as _config

logger = logging.getLogger(__name__)

# Métrica interna -> endpoint declarado en fuentes.yaml (fuente bitcoin-data).
# El mapeo de cada endpoint ya lleva d->fecha y <campo>->valor.
_METRICAS = {
    "mvrv_zscore": "mvrv_zscore",
    "nupl": "nupl",
}


def _mapear(item: dict, mapeo: dict) -> dict:
    """Aplica el mapeo de la fuente al vocabulario (fecha, valor)."""
    out = {}
    for origen, destino in mapeo.items():
        if origen in item:
            out[destino] = item[origen]
    return out


async def _guardar(pool, metrica: str, filas_crudas: list, mapeo: dict) -> int:
    """Inserta/actualiza una serie de {fecha, valor} para una métrica."""
    filas = []
    for item in filas_crudas:
        m = _mapear(item, mapeo)
        f, v = m.get("fecha"), m.get("valor")
        if not f or v is None:
            continue
        # La fuente da la fecha como string "YYYY-MM-DD"; la columna es DATE, y
        # asyncpg exige un date, no un str.
        if isinstance(f, str):
            f = date.fromisoformat(f)
        filas.append((f, metrica, float(v)))
    if not filas:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany("""
            INSERT INTO onchain_diaria (fecha, metrica, valor)
            VALUES ($1, $2, $3)
            ON CONFLICT (fecha, metrica) DO UPDATE SET
                valor        = EXCLUDED.valor,
                capturado_at = now()
        """, filas)
    return len(filas)


async def backfill(pool: asyncpg.Pool, cliente: ClienteFuentes) -> dict:
    """
    Trae la serie COMPLETA (4 años) de cada métrica seguida y la guarda. Se
    corre una vez al integrar, o cuando se agrega una métrica nueva.
    """
    mapeos = _config.actual().mapeos.get("bitcoin-data", {})
    total = {}
    for metrica, endpoint in _METRICAS.items():
        r = await cliente.pedir("bitcoin-data", endpoint)  # sin params = 4 años
        if not r.datos:
            logger.warning("[onchain] %s: sin datos en backfill", metrica)
            total[metrica] = 0
            continue
        n = await _guardar(pool, metrica, r.datos, mapeos.get(endpoint, {}))
        total[metrica] = n
        logger.info("[onchain] backfill %s: %d puntos", metrica, n)
    return {"backfill": total}


async def actualizar(pool: asyncpg.Pool, cliente: ClienteFuentes,
                     dias: int = 5) -> dict:
    """
    Trae los últimos `dias` de cada métrica y agrega los nuevos. Diario. Se pide
    una ventana corta (no solo el último) para tapar días que hubieran faltado.
    """
    mapeos = _config.actual().mapeos.get("bitcoin-data", {})
    desde = (date.today() - timedelta(days=dias)).isoformat()
    hasta = date.today().isoformat()
    total = {}
    for metrica, endpoint in _METRICAS.items():
        r = await cliente.pedir("bitcoin-data", endpoint,
                                startday=desde, endday=hasta)
        if not r.datos:
            total[metrica] = 0
            continue
        n = await _guardar(pool, metrica, r.datos, mapeos.get(endpoint, {}))
        total[metrica] = n
    logger.info("[onchain] actualizado: %s", total)
    return {"actualizado": total}


async def estado(pool: asyncpg.Pool) -> dict:
    """Qué hay capturado por métrica."""
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT metrica, COUNT(*) AS dias,
                   MIN(fecha) AS desde, MAX(fecha) AS hasta
            FROM onchain_diaria GROUP BY metrica ORDER BY metrica
        """)
    return {f["metrica"]: {"dias": f["dias"], "desde": str(f["desde"]),
                           "hasta": str(f["hasta"])} for f in filas}
