"""
AXIOM v3 — Capacidades del par.
════════════════════════════════════════════════════════════════════════════════
Las primeras capacidades declaradas. Salieron de `backend/captura/metricas.py`,
que estaba en el lugar equivocado: rango, oscilación y repetibilidad no son
captura —no hay ninguna fuente involucrada— sino derivaciones sobre datos que
ya tenemos.

TODO LO DECLARADO ACÁ SALIÓ DE MEDIR, no de suponer. Cada `no_sabe` y cada
`metodo` corresponde a algo que se verificó y, en varios casos, a un error que
v2 cometió por no declararlo.

SE CALCULAN PARA TODO EL UNIVERSO, POR EVENTO:
  Es el criterio de la arquitectura. Una métrica que sirve para COMPARAR y
  FILTRAR miles de objetos entre sí se calcula para todos cuando ocurre el
  evento que la invalida. Una que se consulta de a uno se calcula al pedido.

  Nadie va a rankear 3.000 pares por en qué franja hacen su máximo. Sí por
  cuánto se mueven.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia)

logger = logging.getLogger(__name__)

VENTANA = {"default": 30, "min": 7, "max": 365}

# Menos de esto no da una mediana con sentido. Y lo que importa más: una
# métrica sobre 10 velas etiquetada como "ventana de 30 días" NO es comparable
# con una sobre 30.
#
# Medido el 24/08/2026: sin exigir la ventana completa, la cabecera del
# screener eran tokens listados hacía tres semanas con rangos medianos de 165 %
# DIARIOS. Con `velas_usadas >= 30` aparecieron WLD, BONK, XPL — mercados
# reales. El dato estaba declarado y la consulta no lo miraba.
MINIMO_VELAS = 7


# ══ SQL compartido ═══════════════════════════════════════════════════════════
#
# El rango de cada día: (máximo − mínimo) / mínimo.
#
# Se descartan las velas con mínimo 0 o nulo: dividirían por cero, y son datos
# rotos, no días sin movimiento.
_RANGOS = """
    WITH recientes AS (
        SELECT v.par_id, v.fecha, v.maximo, v.minimo, v.cierre,
               ROW_NUMBER() OVER (PARTITION BY v.par_id
                                  ORDER BY v.fecha DESC) AS n
        FROM vela_diaria v
        JOIN pares p ON p.id = v.par_id
        WHERE p.estado = 'activa'
          AND ($2::bigint IS NULL OR v.par_id = $2)
    ),
    rangos AS (
        SELECT par_id, fecha, cierre,
               (maximo - minimo) / NULLIF(minimo, 0) * 100 AS rango
        FROM recientes
        WHERE n <= $1 AND minimo > 0 AND maximo IS NOT NULL
    )
"""


async def _rango_tipico(contexto, ventana=30, par_id=None, **_):
    """
    La mediana del rango diario.

    MEDIANA Y NO PROMEDIO, y no es un detalle de estilo. Verificado con un caso
    construido: un par que se mueve 0,4 % diario con UN solo día de 200 % da
    promedio 7,05 % y mediana 0,40 %. Ordenar por promedio lo pondría en la
    cabecera del ranking de movimiento.

    Y en v2 pasó de verdad: ARCIELUSDT tenía promedio 219,94 % contra mediana
    0,46 %, y el screener ordenaba por promedio. Medido sobre 2.958 pares:
    2.283 se mueven más de 50 puestos según cuál se use.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        filas = await conn.fetch(_RANGOS + """
            SELECT par_id,
                   PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY rango) AS valor,
                   COUNT(*)   AS velas,
                   MAX(fecha) AS hasta
            FROM rangos GROUP BY par_id
            HAVING COUNT(*) >= $3
        """, ventana, par_id, MINIMO_VELAS)
    return _empaquetar(filas, ventana)


async def _oscilacion(contexto, ventana=30, par_id=None, **_):
    """
    Cuánto va y vuelve, contra cuánto se desplaza.

    1 − Efficiency Ratio: 1 = recorre mucho y termina donde empezó; 0 = se
    desplaza en línea recta.

    ES UNA DIMENSIÓN INDEPENDIENTE DEL RANGO, no una variante. Correlación
    medida en v2: 0,049. Y verificado con dos casos construidos: rangos de
    6,19 % y 6,38 % dieron oscilación 0,967 y 0,565 — uno va y vuelve, el otro
    se desploma. Sin esto, "se mueve mucho" no distingue una oportunidad de un
    colapso.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        filas = await conn.fetch(_RANGOS + """
            , extremos AS (
                SELECT par_id, SUM(rango) AS recorrido, COUNT(*) AS velas,
                       MAX(fecha) AS hasta,
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
            SELECT par_id, velas, hasta,
                   -- Acotado a [0,1]: un neto mayor que el recorrido sería un
                   -- dato roto, no una oscilación negativa.
                   GREATEST(0, LEAST(1,
                       1 - ABS(COALESCE(neto,0)) / NULLIF(recorrido,0))) AS valor
            FROM extremos WHERE velas >= $3
        """, ventana, par_id, MINIMO_VELAS)
    return _empaquetar(filas, ventana)


async def _repetibilidad(contexto, ventana=30, par_id=None, **_):
    """
    Con qué frecuencia el par supera cada umbral de movimiento.

    ES UNA CURVA, NO UN NÚMERO, y eso se descubrió midiendo: el umbral de 3 %
    lo supera el 53 % del universo en más del 80 % de sus días — no discrimina
    nada. Recién desde 5 % separa.

    Devolver un solo umbral obligaría a elegirlo de antemano, y cuál sirve
    depende de la estrategia. La curva deja esa decisión donde corresponde.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        filas = await conn.fetch(_RANGOS + """
            SELECT par_id, COUNT(*) AS velas, MAX(fecha) AS hasta,
                   jsonb_build_object(
                     '1', ROUND(COUNT(*) FILTER (WHERE rango>=1)*100.0/COUNT(*), 2),
                     '2', ROUND(COUNT(*) FILTER (WHERE rango>=2)*100.0/COUNT(*), 2),
                     '3', ROUND(COUNT(*) FILTER (WHERE rango>=3)*100.0/COUNT(*), 2),
                     '5', ROUND(COUNT(*) FILTER (WHERE rango>=5)*100.0/COUNT(*), 2),
                     '8', ROUND(COUNT(*) FILTER (WHERE rango>=8)*100.0/COUNT(*), 2)
                   ) AS valor
            FROM rangos GROUP BY par_id
            HAVING COUNT(*) >= $3
        """, ventana, par_id, MINIMO_VELAS)
    return _empaquetar(filas, ventana)


def _empaquetar(filas, ventana: int) -> dict:
    """
    Cada resultado lleva sobre CUÁNTAS velas se calculó y hasta cuándo llegan.

    `velas` no es un detalle: una métrica sobre 10 velas etiquetada como
    "ventana de 30 días" no es comparable con una sobre 30, y sin declararlo se
    ven idénticas. Es el mismo problema que en v2 con la ventana pedida contra
    la efectiva —se pidieron 90 días y se usaron 61—.
    """
    return {
        "por_par": {
            str(f["par_id"]): {
                "valor": (float(f["valor"])
                          if isinstance(f["valor"], (int, float)) else f["valor"]),
                "velas": f["velas"],
                "hasta": str(f["hasta"]),
                "ventana_completa": f["velas"] >= ventana,
            }
            for f in filas
        },
        "ventana_pedida": ventana,
        "_fuente_hasta": (max((f["hasta"] for f in filas), default=None)),
    }


# ══ Las declaraciones ════════════════════════════════════════════════════════

def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="rango_tipico",
        objeto=Objeto.PAR,
        funcion=_rango_tipico,
        descripcion="Cuánto se mueve el par en un día típico",
        parametros={"ventana": VENTANA, "par_id": {"default": None}},
        propiedad=Propiedad(
            unidad="%",
            direccion=Direccion.MAS_ES_MEJOR,
            minimo=0,
            neutro=5.0,
            neutro_medido_en="mediana del universo operable, 24/08/2026"),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la mediana de (máximo−mínimo)/mínimo de cada día, sobre la "
                 "ventana pedida",
            no_sabe="es el rango DISPONIBLE, no el capturable: no descuenta "
                    "spread ni deslizamiento. Que un par recorra 5 % no "
                    "significa que se pueda comprar abajo y vender arriba — "
                    "medido en dos pares, la profundidad a ±0,1 % del mid es CERO",
            fuente="velas diarias del exchange",
            metodo="mediana y no promedio: un solo día excepcional distorsiona "
                   "el promedio. Verificado: 0,4 % diario con un día de 200 % da "
                   "promedio 7,05 % y mediana 0,40 %")))

    registro.registrar(Simple(
        nombre="oscilacion",
        objeto=Objeto.PAR,
        funcion=_oscilacion,
        descripcion="Si el par va y vuelve, o se desplaza en una dirección",
        parametros={"ventana": VENTANA, "par_id": {"default": None}},
        propiedad=Propiedad(
            unidad="0-1",
            direccion=Direccion.CONTEXTUAL,
            minimo=0, maximo=1,
            neutro=0.42,
            neutro_medido_en="universo operable, 78 días de período bajista"),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="1 − (desplazamiento neto / recorrido total) sobre la ventana",
            infiere="que un valor alto indica un par que vuelve sobre sus pasos, "
                    "lo que históricamente acompaña a los rangos operables",
            no_sabe="no dice NADA sobre el futuro: un par que osciló 30 días "
                    "puede romper mañana. Y no distingue oscilación con volumen "
                    "de la que produce un libro fino con órdenes aisladas",
            metodo="Efficiency Ratio invertido. Es INDEPENDIENTE del rango: "
                   "correlación medida 0,049")))

    registro.registrar(Simple(
        nombre="repetibilidad",
        objeto=Objeto.PAR,
        funcion=_repetibilidad,
        descripcion="Con qué frecuencia el par supera cada umbral de movimiento",
        parametros={"ventana": VENTANA, "par_id": {"default": None}},
        propiedad=Propiedad(
            unidad="% de días por umbral",
            direccion=Direccion.MAS_ES_MEJOR,
            comparable=False,
            por_que_no_comparable="es una curva, no un escalar: comparar dos "
                                  "pares exige elegir primero qué umbral importa"),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el porcentaje de días de la ventana en que el rango superó "
                 "1, 2, 3, 5 y 8 %",
            no_sabe="que un umbral se supere el 90 % de los días no dice CUÁNDO "
                    "dentro del día ni si se pudo capturar. Y el pasado reciente "
                    "puede no representar al régimen que viene",
            metodo="curva y no un número: medido, el umbral de 3 % lo supera el "
                   "53 % del universo en más del 80 % de sus días — no "
                   "discrimina. Recién desde 5 % separa")))

    logger.info("[capacidades] par: rango_tipico, oscilacion, repetibilidad")
