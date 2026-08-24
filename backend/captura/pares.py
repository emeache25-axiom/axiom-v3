"""
AXIOM v3 — Captura de pares.
════════════════════════════════════════════════════════════════════════════════
Dos cosas, y son distintas:

    catalogar()   QUÉ PARES EXISTEN — una llamada por exchange, diaria.
                  Detecta altas y bajas.

    capturar_velas()  LA HISTORIA — velas diarias, al cerrar el día.

Todo lo demás —precios, tickers, libro, velas intradía— se lee EN VIVO cuando
hace falta. El exchange lo devuelve on-demand; guardarlo sería duplicar su
trabajo.

POR QUÉ ccxt:
  Verificado el 22/08/2026 contra MEXC y CoinEx:
    · conteos coincidentes con v2 — CoinEx idéntico (723 USDT, 169 BTC, 72
      USDC), MEXC con 2-3 % de diferencia por un criterio de "activo"
      ligeramente distinto y probablemente más actual
    · precisión conservada: ROSE/BTC a 8,1622e-08
    · 500 velas diarias de backfill
    · velas horarias disponibles

  Y sobre todo: agregar un exchange pasa a ser una entrada en el YAML. Con
  adaptadores propios sería escribir código cada vez — una limitación real.

LO QUE ccxt NO RESUELVE, declarado:
  · No inventa lo que el exchange no da: el ticker de CoinEx viene SIN bid/ask
    (0 de 1.208), así que su spread necesita el libro par por par. En MEXC sí
    viene (2.101 de 2.101).
  · Hace llamadas que uno no pidió: `load_markets()` carga spot Y swap en
    paralelo, y el endpoint de contratos de MEXC dio timeout. Por eso
    `defaultType: spot` en la configuración.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Any

import asyncpg

from backend.nucleo import config as _config
from backend.nucleo import bus as _bus
from backend.nucleo.fallos import clasificar, Causa

logger = logging.getLogger(__name__)

# Cuántas velas pedir de backfill la primera vez. ccxt trae hasta 500.
BACKFILL = 400

# Cuántos pares se piden en paralelo. Más no es mejor: los exchanges limitan
# por ritmo y ccxt ya espacia según su propio `rateLimit`.
CONCURRENCIA = 8


def _hoy_utc() -> date:
    return datetime.now(timezone.utc).date()


async def _abrir(nombre: str):
    """
    Instancia un exchange desde la configuración.

    Las opciones vienen del YAML: `defaultType: spot` no es un detalle, sin eso
    ccxt pide también los contratos y MEXC llegó a dar timeout.
    """
    import ccxt.async_support as ccxt

    d = _config.actual().exchanges.get(nombre)
    if d is None:
        raise ValueError(f"exchange '{nombre}' no declarado en config/fuentes.yaml")

    clase = getattr(ccxt, d["exchange_id"])
    return clase(d.get("opciones") or {})


# ══ 1. QUÉ PARES EXISTEN ═════════════════════════════════════════════════════

async def catalogar(pool: asyncpg.Pool, exchanges: list[str] | None = None) -> dict:
    """
    Trae el catálogo de cada exchange y detecta altas y bajas.

    Un par nuevo se detecta al día siguiente. Para la historia da igual, y para
    operar se consulta al exchange en vivo.
    """
    cfg = _config.actual()
    nombres = exchanges or list(
        (cfg.captura.get("universo", {}).get("pares", {}) or {}).get("exchanges", []))
    hoy = _hoy_utc()
    resumen: dict[str, Any] = {}

    for nombre in nombres:
        ex = await _abrir(nombre)
        try:
            mercados = await ex.load_markets()
        except Exception as e:
            # No se toca NADA de este exchange: si el catálogo no llegó, marcar
            # bajas sería dar por muertos pares que solo no pudimos consultar.
            # Es la lección de las 533 coins que estaban vivas con datos viejos.
            logger.error("[pares] %s: no se pudo traer el catálogo (%s) — "
                         "NO se marca ninguna baja", nombre, clasificar(e).value)
            resumen[nombre] = {"error": str(e)[:200], "causa": clasificar(e).value}
            await ex.close()
            continue

        try:
            spot = {s: m for s, m in mercados.items()
                    if m.get("spot") and m.get("active")}

            filas = []
            for simbolo, m in spot.items():
                lim = (m.get("limits") or {}).get("amount") or {}
                prec = m.get("precision") or {}
                filas.append((
                    nombre, simbolo, m.get("base"), m.get("quote"),
                    _entero(prec.get("price")), _entero(prec.get("amount")),
                    lim.get("min"),
                ))

            async with pool.acquire() as conn:
                async with conn.transaction():
                    previos = {
                        r["simbolo"]: r for r in await conn.fetch(
                            "SELECT simbolo, estado FROM pares WHERE exchange = $1",
                            nombre)
                    }

                    await conn.executemany("""
                        INSERT INTO pares (exchange, simbolo, base, quote,
                                           precision_precio, precision_cantidad,
                                           minimo_orden, capturado_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7, now())
                        ON CONFLICT (exchange, simbolo) DO UPDATE SET
                            base               = EXCLUDED.base,
                            quote              = EXCLUDED.quote,
                            precision_precio   = EXCLUDED.precision_precio,
                            precision_cantidad = EXCLUDED.precision_cantidad,
                            minimo_orden       = EXCLUDED.minimo_orden,
                            estado             = 'activa',
                            capturado_at       = now()
                    """, filas)

                    nuevos = [s for s in spot if s not in previos]
                    ausentes = [s for s, r in previos.items()
                                if r["estado"] == "activa" and s not in spot]

                    if ausentes:
                        await conn.execute("""
                            UPDATE pares SET estado='inactiva',
                                             estado_desde=$3,
                                             estado_motivo='dejó de aparecer en el catálogo'
                            WHERE exchange=$1 AND simbolo = ANY($2)
                        """, nombre, ausentes, hoy)

                    eventos = (
                        [("alta", s, "apareció en el catálogo") for s in nuevos] +
                        [("baja", s, "dejó de aparecer en el catálogo") for s in ausentes]
                    )
                    if eventos:
                        await conn.executemany("""
                            INSERT INTO universo_eventos (tipo, objeto, objeto_id,
                                                          evidencia)
                            VALUES ($1, 'par', $2, $3)
                        """, [(t, f"{nombre}:{s}", ev) for t, s, ev in eventos])

            resumen[nombre] = {"activos": len(spot), "altas": len(nuevos),
                               "bajas": len(ausentes)}
            logger.info("[pares] %s: %d activos · %d altas · %d bajas",
                        nombre, len(spot), len(nuevos), len(ausentes))
        finally:
            await ex.close()

    total_altas = sum(r.get("altas", 0) for r in resumen.values())
    total_bajas = sum(r.get("bajas", 0) for r in resumen.values())
    if total_altas or total_bajas:
        await _bus.bus.publicar(
            _bus.CAMBIO_DE_UNIVERSO,
            {"objeto": "par", "detalle": resumen},
            origen="pares.catalogar")

    return resumen


def _entero(v: Any) -> int | None:
    """
    La precisión de ccxt puede venir como entero (dígitos) o como float (tick
    size, ej. 0.0001). Se normaliza a dígitos.
    """
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f >= 1:
        return int(f)
    if f <= 0:
        return None
    # 0.0001 → 4 dígitos
    from math import log10
    return int(round(-log10(f)))


# ══ 2. LA HISTORIA ═══════════════════════════════════════════════════════════

async def capturar_velas(pool: asyncpg.Pool, exchanges: list[str] | None = None,
                         limite_pares: int | None = None) -> dict:
    """
    Velas diarias de todos los pares activos.

    Se guardan aunque el exchange las devuelva on-demand: el screener las
    consulta sobre MILES de pares a la vez, y pedirlas al vuelo sería inviable
    por latencia, no por disponibilidad.

    Idempotente: `ON CONFLICT` actualiza. Correrlo dos veces no duplica.
    """
    cfg = _config.actual()
    nombres = exchanges or list(
        (cfg.captura.get("universo", {}).get("pares", {}) or {}).get("exchanges", []))
    resumen: dict[str, Any] = {}

    for nombre in nombres:
        async with pool.acquire() as conn:
            pares = await conn.fetch("""
                SELECT p.id, p.simbolo,
                       (SELECT MAX(fecha) FROM vela_diaria v WHERE v.par_id = p.id)
                           AS ultima
                FROM pares p
                WHERE p.exchange = $1 AND p.estado = 'activa'
                ORDER BY p.id
            """, nombre)
        if limite_pares:
            pares = pares[:limite_pares]
        if not pares:
            resumen[nombre] = {"pares": 0}
            continue

        ex = await _abrir(nombre)
        guardadas = 0
        fallidos: dict[str, int] = {}
        sem = asyncio.Semaphore(CONCURRENCIA)

        async def uno(p):
            nonlocal guardadas
            async with sem:
                # Solo lo que falta: si ya hay historia, se piden pocos días.
                desde = p["ultima"]
                limite = BACKFILL if desde is None else max(
                    3, (_hoy_utc() - desde).days + 2)
                try:
                    velas = await ex.fetch_ohlcv(p["simbolo"], "1d", limit=limite)
                except Exception as e:
                    c = clasificar(e).value
                    fallidos[c] = fallidos.get(c, 0) + 1
                    return

                hoy = _hoy_utc()
                filas = []
                for v in velas:
                    f = datetime.fromtimestamp(v[0] / 1000, timezone.utc).date()
                    # La vela de HOY está incompleta: se excluye. Guardarla
                    # daría un rango de horas presentado como el del día.
                    if f >= hoy:
                        continue
                    filas.append((p["id"], f, v[1], v[2], v[3], v[4], v[5]))

                if not filas:
                    return
                async with pool.acquire() as conn:
                    await conn.executemany("""
                        INSERT INTO vela_diaria (par_id,fecha,apertura,maximo,
                                                 minimo,cierre,volumen)
                        VALUES ($1,$2,$3,$4,$5,$6,$7)
                        ON CONFLICT (par_id,fecha) DO UPDATE SET
                            apertura=EXCLUDED.apertura, maximo=EXCLUDED.maximo,
                            minimo=EXCLUDED.minimo,     cierre=EXCLUDED.cierre,
                            volumen=EXCLUDED.volumen,   capturado_at=now()
                    """, filas)
                guardadas += len(filas)

        try:
            await asyncio.gather(*[uno(p) for p in pares])
        finally:
            await ex.close()

        resumen[nombre] = {"pares": len(pares), "velas": guardadas,
                           "fallidos": fallidos or None}
        logger.info("[pares] %s: %d velas de %d pares%s", nombre, guardadas,
                    len(pares), f" · fallos: {fallidos}" if fallidos else "")

    return resumen


# ══ 3. VINCULAR CON LAS COINS ════════════════════════════════════════════════
#
# Es parte de armar el catálogo, no una derivación analítica: un par sin saber
# a qué coin corresponde deja el catálogo incompleto.

async def vincular_con_coins(pool: asyncpg.Pool) -> dict:
    """
    Vincula pares con coins cuando la coincidencia es INEQUÍVOCA.

    Un símbolo se vincula solo si hay UNA coin activa con ese símbolo. Si hay
    varias —y los símbolos se repiten mucho entre proyectos— no se elige: se
    deja sin vincular para que el trader decida desde la UI.

    NUNCA pisa un vínculo manual ni uno rechazado. La vinculación manual es la
    verdad; esto es una sugerencia.

    En v2 existía `pair_coin_alias` para los casos ambiguos y quedó con CERO
    filas: se creó el lugar y no la forma de decidir.
    """
    async with pool.acquire() as conn:
        r = await conn.execute("""
            WITH unicos AS (
                SELECT UPPER(symbol) AS sym, MIN(id) AS coin_id, COUNT(*) AS cuantas
                FROM coins WHERE estado = 'activa'
                GROUP BY UPPER(symbol)
                HAVING COUNT(*) = 1          -- solo lo INEQUÍVOCO
            )
            UPDATE pares p
            SET coin_id       = u.coin_id,
                vinculo       = 'automatico',
                vinculo_desde = (now() AT TIME ZONE 'utc')::date
            FROM unicos u
            WHERE UPPER(p.base) = u.sym
              AND p.estado = 'activa'
              AND p.coin_id IS NULL
              AND (p.vinculo IS NULL)        -- no toca manual ni rechazado
        """)
        vinculados = int(r.split()[-1])

        pendientes = await conn.fetchval("""
            SELECT COUNT(*) FROM pares
            WHERE coin_id IS NULL AND estado = 'activa'
        """)
        ambiguos = await conn.fetchval("""
            SELECT COUNT(DISTINCT p.base)
            FROM pares p
            WHERE p.coin_id IS NULL AND p.estado = 'activa'
              AND EXISTS (SELECT 1 FROM coins c
                          WHERE UPPER(c.symbol) = UPPER(p.base)
                            AND c.estado = 'activa'
                          GROUP BY UPPER(c.symbol) HAVING COUNT(*) > 1)
        """)

    logger.info("[metricas] vinculados %d · sin vincular %d (%d símbolos ambiguos)",
                vinculados, pendientes, ambiguos or 0)
    return {"vinculados": vinculados, "sin_vincular": pendientes,
            "simbolos_ambiguos": ambiguos or 0}


# ══ Estado ═══════════════════════════════════════════════════════════════════

async def estado(pool: asyncpg.Pool) -> dict:
    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT
              (SELECT COUNT(*) FROM pares WHERE estado='activa')        AS activos,
              (SELECT COUNT(*) FROM pares WHERE estado='inactiva')      AS inactivos,
              (SELECT COUNT(*) FROM pares WHERE coin_id IS NOT NULL)    AS vinculados,
              (SELECT COUNT(*) FROM pares
                 WHERE coin_id IS NULL AND estado='activa')             AS sin_vincular,
              (SELECT COUNT(*) FROM vela_diaria)                        AS velas,
              (SELECT COUNT(DISTINCT fecha) FROM vela_diaria)           AS dias,
              (SELECT MIN(fecha) FROM vela_diaria)                      AS desde,
              (SELECT MAX(fecha) FROM vela_diaria)                      AS hasta
        """)
        por_ex = await conn.fetch("""
            SELECT exchange, COUNT(*) FILTER (WHERE estado='activa') AS activos
            FROM pares GROUP BY exchange ORDER BY exchange
        """)
    d = dict(r)
    d["por_exchange"] = {f["exchange"]: f["activos"] for f in por_ex}
    return d
