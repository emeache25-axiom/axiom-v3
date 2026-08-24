"""
AXIOM v3 — Métricas de pares.
════════════════════════════════════════════════════════════════════════════════
Deriva de las velas diarias lo que permite COMPARAR pares entre sí: cuánto se
mueve el día típico, si va y vuelve o se desploma, y con qué constancia.

SE PRECALCULAN, y ese es el criterio de la arquitectura: una métrica que sirve
para comparar y filtrar miles de objetos va por evento para todo el universo.
Una que se consulta de a uno se calcula al pedido.

TODO LO DE ACÁ SALIÓ DE MEDIR, no de suponer:

  · MEDIANA, no promedio. En v2 el promedio ponía COLAPSOS en la cabecera:
    ARCIELUSDT tenía promedio 219,94 % contra mediana 0,46 % — un par plano
    encabezando el ranking de movimiento por un único día de 6.118 %. Medido
    sobre 2.958 pares: 2.283 se mueven más de 50 puestos según cuál se use.

  · LA REPETIBILIDAD ES UNA CURVA, no un número. Medido: el umbral de 3 % lo
    supera el 53 % del universo en más del 80 % de sus días — no discrimina
    nada. Recién desde 5 % separa.

  · LA OSCILACIÓN ES INDEPENDIENTE DEL RANGO. Correlación medida: 0,049. No es
    una variante de "cuánto se mueve": es "cómo se mueve". Un par puede
    recorrer 8 % desplomándose (no sirve para operar rangos) o yendo y
    volviendo (sí sirve).
"""
from __future__ import annotations

import logging
from datetime import date

import asyncpg

logger = logging.getLogger(__name__)

VENTANA = 30
MINIMO_VELAS = 7        # menos que esto no da una mediana con sentido


async def calcular(pool: asyncpg.Pool, ventana: int = VENTANA) -> dict:
    """
    Recalcula las métricas de todos los pares activos con velas suficientes.

    Una sola consulta para todo el universo: hacerlo par por par sobre miles de
    pares sería inviable, y el cálculo es puro SQL.
    """
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            WITH recientes AS (
                SELECT v.par_id, v.fecha, v.apertura, v.maximo, v.minimo, v.cierre,
                       ROW_NUMBER() OVER (PARTITION BY v.par_id
                                          ORDER BY v.fecha DESC) AS n
                FROM vela_diaria v
                JOIN pares p ON p.id = v.par_id
                WHERE p.estado = 'activa'
            ),
            ventana AS (
                SELECT * FROM recientes WHERE n <= $1
            ),
            -- El rango de cada día: (máximo − mínimo) / mínimo.
            -- Se descartan las velas con mínimo 0 o nulo: dividirían por cero y
            -- son datos rotos, no días sin movimiento.
            rangos AS (
                SELECT par_id, fecha, cierre,
                       (maximo - minimo) / NULLIF(minimo, 0) * 100 AS rango
                FROM ventana
                WHERE minimo > 0 AND maximo IS NOT NULL
            ),
            -- Para la oscilación: el recorrido TOTAL contra el desplazamiento
            -- NETO. Se usa el rango de cada día como proxy del recorrido, en
            -- vez de la suma de |cierre−apertura|, porque captura también lo
            -- que pasó DENTRO del día.
            extremos AS (
                SELECT par_id,
                       MAX(fecha) AS hasta,
                       COUNT(*)   AS velas,
                       SUM(rango) AS recorrido,
                       -- desplazamiento neto entre la primera y la última vela
                       (MAX(cierre) FILTER (WHERE fecha = maxf)
                        - MAX(cierre) FILTER (WHERE fecha = minf))
                         / NULLIF(MAX(cierre) FILTER (WHERE fecha = minf), 0)
                         * 100 AS neto
                FROM (SELECT r.*,
                             MIN(fecha) OVER (PARTITION BY par_id) AS minf,
                             MAX(fecha) OVER (PARTITION BY par_id) AS maxf
                      FROM rangos r) t
                GROUP BY par_id
            )
            SELECT r.par_id,
                   e.hasta,
                   e.velas,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.rango) AS rango_tipico,
                   AVG(r.rango)                                          AS rango_promedio,
                   -- El ratio se calcula ACÁ y no en Python: AVG devuelve
                   -- Decimal y PERCENTILE_CONT devuelve float, y dividirlos
                   -- entre sí en Python es un TypeError.
                   AVG(r.rango) / NULLIF(
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r.rango), 0)
                                                                         AS rango_ratio,
                   -- 1 − ER: 1 = va y vuelve, 0 = se desplaza en línea recta.
                   -- Se acota a [0,1]: un neto mayor que el recorrido sería un
                   -- dato roto, no una oscilación negativa.
                   GREATEST(0, LEAST(1,
                       1 - ABS(COALESCE(e.neto, 0)) / NULLIF(e.recorrido, 0)
                   ))                                                    AS oscilacion,
                   COUNT(*) FILTER (WHERE r.rango >= 1) * 100.0 / COUNT(*) AS d1,
                   COUNT(*) FILTER (WHERE r.rango >= 2) * 100.0 / COUNT(*) AS d2,
                   COUNT(*) FILTER (WHERE r.rango >= 3) * 100.0 / COUNT(*) AS d3,
                   COUNT(*) FILTER (WHERE r.rango >= 5) * 100.0 / COUNT(*) AS d5,
                   COUNT(*) FILTER (WHERE r.rango >= 8) * 100.0 / COUNT(*) AS d8
            FROM rangos r
            JOIN extremos e ON e.par_id = r.par_id
            WHERE e.velas >= $2
            GROUP BY r.par_id, e.hasta, e.velas, e.neto, e.recorrido
        """, ventana, MINIMO_VELAS)

        if not filas:
            return {"calculadas": 0, "nota": "no hay pares con velas suficientes"}

        await conn.executemany("""
            INSERT INTO par_metricas (par_id, hasta_fecha, velas_usadas,
                ventana_dias, rango_tipico, rango_promedio, rango_ratio,
                oscilacion, dias_sobre_1pct, dias_sobre_2pct, dias_sobre_3pct,
                dias_sobre_5pct, dias_sobre_8pct, calculado_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13, now())
            ON CONFLICT (par_id) DO UPDATE SET
                hasta_fecha     = EXCLUDED.hasta_fecha,
                velas_usadas    = EXCLUDED.velas_usadas,
                ventana_dias    = EXCLUDED.ventana_dias,
                rango_tipico    = EXCLUDED.rango_tipico,
                rango_promedio  = EXCLUDED.rango_promedio,
                rango_ratio     = EXCLUDED.rango_ratio,
                oscilacion      = EXCLUDED.oscilacion,
                dias_sobre_1pct = EXCLUDED.dias_sobre_1pct,
                dias_sobre_2pct = EXCLUDED.dias_sobre_2pct,
                dias_sobre_3pct = EXCLUDED.dias_sobre_3pct,
                dias_sobre_5pct = EXCLUDED.dias_sobre_5pct,
                dias_sobre_8pct = EXCLUDED.dias_sobre_8pct,
                calculado_at    = now()
        """, [
            (f["par_id"], f["hasta"], f["velas"], ventana,
             f["rango_tipico"], f["rango_promedio"], f["rango_ratio"],
             f["oscilacion"], f["d1"], f["d2"], f["d3"], f["d5"], f["d8"])
            for f in filas
        ])

        # Métricas viejas: si un par dejó de tener velas frescas, sus métricas
        # ya no representan nada. En v2 se mostraban junto a las del día
        # anterior sin distinguirse — hasta 20 días de desfase.
        rancias = await conn.fetchval("""
            SELECT COUNT(*) FROM par_metricas
            WHERE hasta_fecha < (now() AT TIME ZONE 'utc')::date - 3
        """)

    logger.info("[metricas] %d pares · ventana %d días%s",
                len(filas), ventana,
                f" · {rancias} con métricas de más de 3 días" if rancias else "")
    return {"calculadas": len(filas), "ventana_dias": ventana,
            "con_metricas_rancias": rancias}


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
