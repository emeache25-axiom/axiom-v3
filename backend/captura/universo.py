"""
AXIOM v3 — Captura del universo de coins.
════════════════════════════════════════════════════════════════════════════════
Tres cosas, y son distintas:

  inventariar()  QUÉ EXISTE — /coins/list, una llamada, sin API key.
                 Detecta altas y bajas de forma INEQUÍVOCA.

  refrescar()    QUÉ VALE — /coins/markets paginado. Precio, capitalización,
                 ranking, variaciones de las coins que seguimos.

  fotografiar()  LA HISTORIA — la foto diaria. Es lo IRRECUPERABLE.

POR QUÉ SEPARADAS:
  En v2 esto era un solo job y por eso "salió del top 2.000" se confundía con
  "está muerta": la única señal disponible era la ausencia en un listado
  paginado, que no distingue una cosa de la otra.

  Medido el 18/08/2026: de 558 coins con datos viejos, **533 estaban VIVAS** —
  CoinGecko las devuelve cuando se las pide por id. Solo 25 no responden.
  Marcarlas inactivas por antigüedad habría dado de baja 533 coins vivas.

Ver AXIOM_v3_arquitectura.md §7 y AXIOM_v3_declaraciones.md §1
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, date
from typing import Any

import asyncpg

from backend.fuentes.cliente import ClienteFuentes, FuenteError
from backend.fuentes.coingecko import COINGECKO, MAPEO_MERCADOS
from backend.nucleo import bus as _bus

logger = logging.getLogger(__name__)

# Cuántas coins seguimos. Es una DECISIÓN, no una restricción de la fuente:
# en v2 se pedían 8 páginas "porque alguien escribió 8", y las ~580 que
# quedaban afuera envejecían en silencio.
SEGUIDAS_POR_DEFECTO = 3000
POR_PAGINA = 250

# Cuántas coins se piden por lote al refrescar por id.
LOTE_IDS = 200


def _leer(obj: Any, ruta: str) -> Any:
    """Lee una ruta con puntos: 'data.market_cap_percentage.btc'."""
    for parte in ruta.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(parte)
    return obj


def _mapear(item: dict, mapeo: dict[str, str]) -> dict:
    """Aplica un mapeo de campos de la fuente al vocabulario."""
    return {destino: _leer(item, origen) for origen, destino in mapeo.items()}


def _fecha_utc() -> date:
    return datetime.now(timezone.utc).date()


def _a_timestamp(v: Any) -> datetime | None:
    """
    Texto ISO → datetime. Las APIs devuelven fechas como texto y asyncpg exige
    el tipo real: valida ANTES de mandar, así que un cast en el SQL no alcanza.

    Vive acá y no en cada capturador porque toda fuente devuelve fechas así.
    Un formato inesperado devuelve None en vez de romper la captura entera: es
    un campo de frescura, no el dato.
    """
    if v is None or isinstance(v, datetime):
        return v
    if not isinstance(v, str):
        return None
    try:
        # La 'Z' de ISO 8601 no la entiende fromisoformat antes de 3.11
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("[universo] fecha no reconocida: %r", v)
        return None


async def _guardar_captura(conn, fuente: str, endpoint: str,
                           parametros: dict, respuesta) -> int:
    """
    Persiste la respuesta CRUDA y devuelve su id.

    Se guarda entera, sin tocar. Un campo que hoy no se mapea, mañana está acá
    — incluso para datos históricos. En v2 eso era irrecuperable: había que
    volver a pedir todo, y para el pasado eso es imposible.
    """
    items = len(respuesta.datos) if isinstance(respuesta.datos, list) else 1
    return await conn.fetchval("""
        INSERT INTO capturas (fuente, endpoint, parametros, pedido_at,
                              crudo, items, intentos)
        VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, $6, $7)
        RETURNING id
    """, fuente, endpoint, json.dumps(parametros or {}),
         respuesta.pedido_at, json.dumps(respuesta.datos), items,
         respuesta.intentos)


# ══ 1. QUÉ EXISTE ════════════════════════════════════════════════════════════

async def inventariar(pool: asyncpg.Pool, cliente: ClienteFuentes) -> dict:
    """
    Trae el inventario completo de la fuente y detecta altas y bajas.

    Una sola llamada, sin API key, ~18.500 coins. Es la referencia de
    EXISTENCIA: comparar contra esto es inequívoco, a diferencia de deducir la
    baja de la ausencia en un listado paginado.
    """
    r = await cliente.pedir("coingecko", "inventario")
    hoy = _fecha_utc()
    vistos = {c["id"]: c for c in r.datos if isinstance(c, dict) and c.get("id")}

    if not vistos:
        raise FuenteError("el inventario vino vacío — no se toca nada")

    async with pool.acquire() as conn:
        async with conn.transaction():
            previos = {
                row["id"]: row for row in await conn.fetch(
                    "SELECT id, presente FROM inventario WHERE fuente='coingecko'")
            }

            # Altas y presencia
            await conn.executemany("""
                INSERT INTO inventario (fuente, id, symbol, nombre,
                                        visto_desde, visto_hasta, presente)
                VALUES ('coingecko', $1, $2, $3, $4, $4, true)
                ON CONFLICT (fuente, id) DO UPDATE SET
                    symbol      = EXCLUDED.symbol,
                    nombre      = EXCLUDED.nombre,
                    visto_hasta = EXCLUDED.visto_hasta,
                    presente    = true
            """, [(c["id"], c.get("symbol"), c.get("name"), hoy)
                  for c in vistos.values()])

            nuevas = [cid for cid in vistos if cid not in previos]

            # Bajas: estaban presentes y ya no vienen
            ausentes = [cid for cid, row in previos.items()
                        if row["presente"] and cid not in vistos]
            if ausentes:
                await conn.execute(
                    "UPDATE inventario SET presente=false "
                    "WHERE fuente='coingecko' AND id = ANY($1)", ausentes)

            # Los eventos son información: en v2 no quedaba rastro de altas ni
            # bajas, y por eso nadie podía responder qué apareció este mes.
            if nuevas:
                await conn.executemany("""
                    INSERT INTO universo_eventos (tipo, objeto, objeto_id,
                                                  detalle, evidencia)
                    VALUES ('alta', 'coin', $1, $2::jsonb, $3)
                """, [(cid,
                       json.dumps({"symbol": vistos[cid].get("symbol"),
                                   "nombre": vistos[cid].get("name")}),
                       "apareció en /coins/list") for cid in nuevas])

            if ausentes:
                await conn.executemany("""
                    INSERT INTO universo_eventos (tipo, objeto, objeto_id,
                                                  evidencia)
                    VALUES ('baja', 'coin', $1, $2)
                """, [(cid, "desapareció de /coins/list") for cid in ausentes])

                # Una baja del inventario ES una baja: la fuente dejó de
                # conocerla. No se revierte automáticamente.
                await conn.execute("""
                    UPDATE coins SET estado='inactiva',
                                     estado_desde=$2,
                                     estado_motivo='desapareció de /coins/list'
                    WHERE id = ANY($1) AND estado='activa'
                """, ausentes, hoy)

    logger.info("[universo] inventario: %d coins · %d altas · %d bajas",
                len(vistos), len(nuevas), len(ausentes))

    # Solo si algo cambió. Publicar "no pasó nada" haría que los consumidores
    # trabajen de más en cada corrida, que es lo contrario de la ventaja de
    # organizarse por eventos.
    if nuevas or ausentes:
        await _bus.bus.publicar(
            _bus.CAMBIO_DE_UNIVERSO,
            {"objeto": "coin", "altas": nuevas, "bajas": ausentes},
            origen="universo.inventariar")

    return {"en_la_fuente": len(vistos), "altas": len(nuevas),
            "bajas": len(ausentes)}


# ══ 2. QUÉ VALE ══════════════════════════════════════════════════════════════

async def refrescar(pool: asyncpg.Pool, cliente: ClienteFuentes,
                    cuantas: int = SEGUIDAS_POR_DEFECTO,
                    guardar_crudo: bool = False) -> dict:
    """
    Trae precio, capitalización y ranking de las primeras `cuantas` coins.

    `guardar_crudo=False` por defecto: el crudo de CADA refresco serían ~9 GB al
    año (11 páginas × 4 corridas diarias). Los refrescos intradía se sobreescriben
    igual, así que su crudo no aporta. El crudo se guarda en la FOTO diaria, que
    es la que tiene valor histórico.
    """
    paginas = (cuantas + POR_PAGINA - 1) // POR_PAGINA
    total = 0
    hoy = _fecha_utc()

    async with pool.acquire() as conn:
        for pagina in range(1, paginas + 1):
            r = await cliente.pedir(
                "coingecko", "mercados", page=pagina,
                price_change_percentage="24h,7d")

            if not r.datos:
                logger.info("[universo] página %d vacía — fin del ranking", pagina)
                break

            captura_id = None
            if guardar_crudo:
                captura_id = await _guardar_captura(
                    conn, "coingecko", "mercados", {"page": pagina}, r)

            motivo = f"top_{cuantas}"
            filas = []
            for item in r.datos:
                m = _mapear(item, MAPEO_MERCADOS)
                if not m.get("id"):
                    continue
                filas.append((
                    m["id"], (m.get("symbol") or "").upper(),
                    m.get("nombre") or m["id"],
                    m.get("precio"), m.get("capitalizacion"), m.get("volumen"),
                    m.get("puesto"), m.get("variacion_24h"), m.get("variacion_7d"),
                    _a_timestamp(m.get("fuente_updated_at")), hoy, motivo,
                ))

            await conn.executemany("""
                INSERT INTO coins (id, symbol, nombre, precio, capitalizacion,
                                   volumen, puesto, variacion_24h, variacion_7d,
                                   fuente_updated_at, seguida, seguida_desde,
                                   seguida_motivo, capturado_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,
                        $10, true, $11, $12, now())
                ON CONFLICT (id) DO UPDATE SET
                    symbol            = EXCLUDED.symbol,
                    nombre            = EXCLUDED.nombre,
                    precio            = EXCLUDED.precio,
                    capitalizacion    = EXCLUDED.capitalizacion,
                    volumen           = EXCLUDED.volumen,
                    puesto            = EXCLUDED.puesto,
                    variacion_24h     = EXCLUDED.variacion_24h,
                    variacion_7d      = EXCLUDED.variacion_7d,
                    fuente_updated_at = EXCLUDED.fuente_updated_at,
                    seguida           = true,
                    capturado_at      = now()
            """, filas)

            total += len(filas)
            logger.info("[universo] página %d/%d: %d coins",
                        pagina, paginas, len(filas))

    logger.info("[universo] refresco completo: %d coins", total)

    # Quien publica no sabe quién escucha. Hoy la foto diaria y mañana lo que
    # haga falta: recalcular agregados, invalidar cachés de capacidades que
    # dependen de estos datos.
    await _bus.bus.publicar(
        _bus.REFRESCO_DE_COINS,
        {"actualizadas": total, "paginas": paginas},
        origen="universo.refrescar")

    return {"actualizadas": total, "paginas": paginas}


# ══ 3. LA HISTORIA ═══════════════════════════════════════════════════════════

async def fotografiar(pool: asyncpg.Pool, fecha: date | None = None) -> dict:
    """
    La foto diaria del universo. Es lo IRRECUPERABLE.

    CoinGecko no devuelve el ranking de hace un mes ni la capitalización de un
    sector en una fecha pasada. Si no se captura hoy, ese día no existe nunca
    más.

    Idempotente: correrlo dos veces el mismo día actualiza, no duplica.
    """
    fecha = fecha or _fecha_utc()

    async with pool.acquire() as conn:
        n = await conn.fetchval("""
            INSERT INTO coin_diaria (fecha, coin_id, symbol, precio,
                                     capitalizacion, volumen, puesto,
                                     variacion_24h, variacion_7d, sector,
                                     fuente_updated_at)
            SELECT $1, id, symbol, precio, capitalizacion, volumen, puesto,
                   variacion_24h, variacion_7d, sector, fuente_updated_at
            FROM coins
            WHERE estado = 'activa' AND seguida AND precio IS NOT NULL
            ON CONFLICT (fecha, coin_id) DO UPDATE SET
                precio            = EXCLUDED.precio,
                capitalizacion    = EXCLUDED.capitalizacion,
                volumen           = EXCLUDED.volumen,
                puesto            = EXCLUDED.puesto,
                variacion_24h     = EXCLUDED.variacion_24h,
                variacion_7d      = EXCLUDED.variacion_7d,
                sector            = EXCLUDED.sector,
                fuente_updated_at = EXCLUDED.fuente_updated_at,
                capturado_at      = now()
            RETURNING 1
        """, fecha)

        # `RETURNING 1` con fetchval devuelve solo la primera fila; el conteo
        # real se pide aparte.
        guardadas = await conn.fetchval(
            "SELECT COUNT(*) FROM coin_diaria WHERE fecha = $1", fecha)
        dias = await conn.fetchval(
            "SELECT COUNT(DISTINCT fecha) FROM coin_diaria")

    logger.info("[universo] foto de %s: %d coins · %d días de historia",
                fecha, guardadas, dias)
    return {"fecha": str(fecha), "coins": guardadas, "dias_de_historia": dias}


# ══ Estado ═══════════════════════════════════════════════════════════════════

async def estado(pool: asyncpg.Pool) -> dict:
    """Qué sabe el sistema sobre su propio universo."""
    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT
              (SELECT COUNT(*) FROM inventario WHERE presente)          AS en_la_fuente,
              (SELECT COUNT(*) FROM coins WHERE estado='activa')        AS activas,
              (SELECT COUNT(*) FROM coins WHERE estado='inactiva')      AS inactivas,
              (SELECT COUNT(*) FROM coins WHERE seguida)                AS seguidas,
              (SELECT COUNT(*) FROM coins WHERE seguida
                 AND capturado_at::date >= (now() AT TIME ZONE 'utc')::date)
                                                                        AS al_dia,
              (SELECT COUNT(DISTINCT fecha) FROM coin_diaria)           AS dias_historia,
              (SELECT MIN(fecha) FROM coin_diaria)                      AS desde,
              (SELECT MAX(fecha) FROM coin_diaria)                      AS hasta
        """)
    return dict(r)
