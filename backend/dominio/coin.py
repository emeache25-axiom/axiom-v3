"""
AXIOM v3 — Capacidades de la coin.
════════════════════════════════════════════════════════════════════════════════
Las primeras capacidades sobre un objeto INDIVIDUAL parametrizado por id que no
es BTC. Responden la capa de INFORMACIÓN sobre una coin concreta:

  · coin_estado    — cómo está ahora: precio, cap, volumen, puesto, variaciones
  · coin_historia  — cómo viene en el tiempo: precio, volumen, puesto
  · coin_mercados  — dónde se opera: exchanges y pares

SON CONSULTAS DE A UNA, AL PEDIDO — no masivas. El criterio es el de la
arquitectura: "el estado de esta coin" no se usa para comparar 3.000 coins entre
sí, se consulta de a una. Por eso INDIVIDUAL con `coin_id`, no MASIVA por evento.

LO QUE NO SE PUEDE RESPONDER HOY (declarado, no inventado):
  · "qué hace / sector / categorías" — las columnas `sector` y `categorias`
    están VACÍAS en las 3.289 coins (medido 02/09). El sync no trae las
    categorías descriptivas de CoinGecko. Hasta capturarlas, es ❌.
  · "qué supply tiene" — no existe columna de supply en el esquema. CoinGecko lo
    da; no lo guardamos. ❌ hasta mapear el campo.

LA RESOLUCIÓN DE COIN vive acá y es la fuente de verdad. Cuando el copiloto de
skills se porte a v3, la reusa — no se duplica el "qué coin es 'btc'".

VIGENCIA: las tres usan `cierre_vela_diaria` porque es el ÚNICO evento de
invalidación implementado hoy en v3. Lo natural sería `refresco_de_coins` (cada
6h) para estado/historia y `cambio_universo` para mercados —están en el diseño
pero no existen como eventos aún—. Cuando se implementen, cambiar acá.
"""
from __future__ import annotations

import logging
from datetime import date

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)

VENTANA = {"default": 30, "min": 7, "max": 365}


# ════════════════════════════════════════════════════════════════════════════
#  RESOLUCIÓN DE COIN
# ════════════════════════════════════════════════════════════════════════════
async def resolver_coin(pool, texto: str) -> dict | None:
    """
    De 'btc' / 'bitcoin' / 'Bitcoin' a la coin. La fuente de verdad del sistema.

    Orden de resolución, del match más fuerte al más débil:
      1. id exacto (case-insensitive): 'bitcoin' → bitcoin
      2. symbol exacto: 'btc' / 'BTC' → BTC
      3. nombre exacto: 'Bitcoin'
      4. coincidencia parcial de nombre (prefijo)

    AMBIGÜEDAD: hay símbolos repetidos entre coins (varios proyectos con el mismo
    ticker). Cuando un match devuelve varias, se elige la de MEJOR PUESTO —la más
    grande, el desambiguador honesto— y se informa que hubo otras. Nunca se
    elige en silencio sin dejar rastro.

    Solo coins `seguida`. Devuelve dict con la coin o None.
    """
    if not texto or not texto.strip():
        return None
    t = texto.strip().lower()

    async with pool.acquire() as conn:
        # 1-3: id / symbol / nombre exactos, priorizando el tipo de match y el
        # puesto. La coincidencia exacta de id o symbol vale más que la de nombre.
        filas = await conn.fetch(
            """
            SELECT id, symbol, nombre, puesto, precio, capitalizacion,
                   volumen, variacion_24h, variacion_7d, estado,
                   CASE
                       WHEN lower(id) = $1     THEN 1
                       WHEN lower(symbol) = $1 THEN 2
                       WHEN lower(nombre) = $1 THEN 3
                       ELSE 4
                   END AS fuerza
            FROM coins
            WHERE seguida
              AND (lower(id) = $1 OR lower(symbol) = $1 OR lower(nombre) = $1
                   OR lower(nombre) LIKE $1 || '%')
            ORDER BY fuerza ASC, puesto ASC NULLS LAST
            LIMIT 25
            """,
            t)

    if not filas:
        return None

    elegida = filas[0]
    # ¿Hubo otras del mismo nivel de match? (mismo symbol, distinto proyecto)
    mismas = [f for f in filas
              if f["fuerza"] == elegida["fuerza"] and f["id"] != elegida["id"]]
    otras = [{"id": f["id"], "nombre": f["nombre"], "puesto": f["puesto"]}
             for f in mismas[:5]]

    return {
        "id": elegida["id"],
        "symbol": elegida["symbol"],
        "nombre": elegida["nombre"],
        "puesto": elegida["puesto"],
        "_fila": elegida,          # para que coin_estado no re-consulte
        "_ambiguo": otras or None, # otras coins que matchearon igual
    }


# ════════════════════════════════════════════════════════════════════════════
#  ESTADO ACTUAL
# ════════════════════════════════════════════════════════════════════════════
async def _coin_estado(contexto, coin_id=None, coin=None, **_) -> dict:
    """
    Cómo está la coin AHORA: precio, capitalización, volumen, puesto, variaciones.
    Lee la foto actual de `coins`. Acepta `coin_id` (id exacto) o `coin` (texto
    a resolver: symbol, nombre).
    """
    pool = contexto["pool"]
    ambiguo = None

    if coin_id is None and coin:
        r = await resolver_coin(pool, coin)
        if r is None:
            return {"valor": None, "encontrada": False, "consultado": coin}
        coin_id = r["id"]
        ambiguo = r["_ambiguo"]

    if coin_id is None:
        return {"valor": None, "encontrada": False}

    async with pool.acquire() as conn:
        f = await conn.fetchrow(
            """
            SELECT id, symbol, nombre, estado, seguida, puesto,
                   precio, capitalizacion, volumen,
                   variacion_24h, variacion_7d, fuente_updated_at
            FROM coins WHERE lower(id) = lower($1)
            """,
            coin_id)

    if f is None:
        return {"valor": None, "encontrada": False, "consultado": coin_id}

    return {
        "encontrada": True,
        "id": f["id"],
        "symbol": f["symbol"],
        "nombre": f["nombre"],
        "estado": f["estado"],
        "puesto": f["puesto"],
        "precio": float(f["precio"]) if f["precio"] is not None else None,
        "capitalizacion": float(f["capitalizacion"]) if f["capitalizacion"] is not None else None,
        "volumen": float(f["volumen"]) if f["volumen"] is not None else None,
        "variacion_24h": float(f["variacion_24h"]) if f["variacion_24h"] is not None else None,
        "variacion_7d": float(f["variacion_7d"]) if f["variacion_7d"] is not None else None,
        "ambiguo": ambiguo,
        "_fuente_hasta": f["fuente_updated_at"],
    }


# ════════════════════════════════════════════════════════════════════════════
#  HISTORIA
# ════════════════════════════════════════════════════════════════════════════
async def _coin_historia(contexto, coin_id=None, coin=None, ventana=30, **_) -> dict:
    """
    Cómo viene la coin en el tiempo: precio, volumen y puesto sobre la ventana.
    Lee la serie de `coin_diaria`.
    """
    pool = contexto["pool"]
    ambiguo = None

    if coin_id is None and coin:
        r = await resolver_coin(pool, coin)
        if r is None:
            return {"valor": None, "encontrada": False, "consultado": coin}
        coin_id = r["id"]
        ambiguo = r["_ambiguo"]

    if coin_id is None:
        return {"valor": None, "encontrada": False}

    async with pool.acquire() as conn:
        filas = await conn.fetch(
            """
            SELECT fecha, precio, volumen, puesto, capitalizacion
            FROM coin_diaria
            WHERE lower(coin_id) = lower($1)
            ORDER BY fecha DESC
            LIMIT $2
            """,
            coin_id, ventana)

    if not filas:
        return {"valor": None, "encontrada": False, "dias": 0,
                "consultado": coin_id}

    # De más viejo a más nuevo para leer la evolución.
    serie = list(reversed(filas))
    primero, ultimo = serie[0], serie[-1]

    def _f(v):
        return float(v) if v is not None else None

    precio_ini = _f(primero["precio"])
    precio_fin = _f(ultimo["precio"])
    cambio_pct = None
    if precio_ini and precio_fin and precio_ini > 0:
        cambio_pct = round((precio_fin - precio_ini) / precio_ini * 100, 2)

    puesto_ini = primero["puesto"]
    puesto_fin = ultimo["puesto"]
    # Puesto: MENOS es mejor. Mejora = subió de ranking = el número bajó.
    puestos_ganados = None
    if puesto_ini is not None and puesto_fin is not None:
        puestos_ganados = puesto_ini - puesto_fin

    return {
        "encontrada": True,
        "dias": len(serie),
        "dias_pedidos": ventana,
        "desde": str(primero["fecha"]),
        "hasta": str(ultimo["fecha"]),
        "precio_inicio": precio_ini,
        "precio_fin": precio_fin,
        "cambio_pct": cambio_pct,
        "puesto_inicio": puesto_ini,
        "puesto_fin": puesto_fin,
        "puestos_ganados": puestos_ganados,
        "volumen_ultimo": _f(ultimo["volumen"]),
        "ambiguo": ambiguo,
        "_fuente_hasta": ultimo["fecha"],
    }


# ════════════════════════════════════════════════════════════════════════════
#  MERCADOS — DÓNDE SE OPERA
# ════════════════════════════════════════════════════════════════════════════
async def _coin_mercados(contexto, coin_id=None, coin=None, **_) -> dict:
    """
    Dónde se opera la coin: exchanges y pares activos vinculados, con su mínimo
    de orden. Lee `pares` por `coin_id`.
    """
    pool = contexto["pool"]
    ambiguo = None

    if coin_id is None and coin:
        r = await resolver_coin(pool, coin)
        if r is None:
            return {"valor": None, "encontrada": False, "consultado": coin}
        coin_id = r["id"]
        ambiguo = r["_ambiguo"]

    if coin_id is None:
        return {"valor": None, "encontrada": False}

    async with pool.acquire() as conn:
        filas = await conn.fetch(
            """
            SELECT id, exchange, simbolo, base, quote, estado,
                   minimo_orden
            FROM pares
            WHERE lower(coin_id) = lower($1) AND estado = 'activa'
            ORDER BY exchange, simbolo
            """,
            coin_id)

    mercados = [{
        "par_id": f["id"],
        "exchange": f["exchange"],
        "simbolo": f["simbolo"],
        "base": f["base"],
        "quote": f["quote"],
        "minimo_orden": float(f["minimo_orden"]) if f["minimo_orden"] is not None else None,
    } for f in filas]

    exchanges = sorted({f["exchange"] for f in filas})

    return {
        "encontrada": bool(mercados),
        "coin_id": coin_id,
        "total_pares": len(mercados),
        "exchanges": exchanges,
        "mercados": mercados,
        "ambiguo": ambiguo,
    }


# ════════════════════════════════════════════════════════════════════════════
#  DECLARACIÓN
# ════════════════════════════════════════════════════════════════════════════
def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="coin_estado", objeto=Objeto.COIN,
        funcion=_coin_estado, alcance=Alcance.INDIVIDUAL,
        parametros={"coin_id": {"default": None}, "coin": {"default": None}},
        descripcion="Cómo está una coin ahora: precio, capitalización, volumen, "
                    "puesto y variaciones 24h/7d",
        propiedad=Propiedad(unidad="mixta", direccion=Direccion.CONTEXTUAL),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la foto actual de la coin en CoinGecko: precio en USD, "
                 "capitalización, volumen 24h, puesto por capitalización y "
                 "variaciones de 24h y 7d",
            infiere=None,
            no_sabe="es la última captura, no tiempo real: el precio se mueve "
                    "entre refrescos. El VOLUMEN es global de CoinGecko, no el de "
                    "un par operable —no cruzarlo con el volumen de un par—. Y NO "
                    "dice qué HACE la coin: sector y categorías no se capturan "
                    "hoy, y el supply tampoco",
            fuente="coingecko, tabla coins (foto actual)",
            metodo="lectura directa de la fila; resolución de la coin por id, "
                   "symbol o nombre, eligiendo la de mejor puesto ante symbols "
                   "repetidos")))

    registro.registrar(Simple(
        nombre="coin_historia", objeto=Objeto.COIN,
        funcion=_coin_historia, alcance=Alcance.INDIVIDUAL,
        parametros={"coin_id": {"default": None}, "coin": {"default": None},
                    "ventana": VENTANA},
        descripcion="Cómo viene una coin en el tiempo: precio, volumen y "
                    "movimiento de puesto sobre la ventana",
        propiedad=Propiedad(unidad="mixta", direccion=Direccion.CONTEXTUAL),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la evolución sobre la ventana desde coin_diaria: cambio "
                 "porcentual del precio entre el primer y último día, y cuántos "
                 "puestos ganó o perdió (menos es mejor: subir de ranking baja "
                 "el número)",
            infiere=None,
            no_sabe="la historia de coin_diaria arrancó ~13/08/2026: pedir 30 "
                    "días puede devolver menos, y el resultado declara cuántos "
                    "días efectivamente había. El puesto es casi estático día a "
                    "día; su VARIACIÓN es lo informativo, no su valor. La "
                    "variación de precio de la fuente es sobre ventana móvil, no "
                    "día contra día",
            fuente="coingecko, tabla coin_diaria (serie histórica)",
            metodo="primer vs último día de la ventana; puestos_ganados = "
                   "puesto_inicial − puesto_final")))

    registro.registrar(Simple(
        nombre="coin_mercados", objeto=Objeto.COIN,
        funcion=_coin_mercados, alcance=Alcance.INDIVIDUAL,
        parametros={"coin_id": {"default": None}, "coin": {"default": None}},
        descripcion="Dónde se opera una coin: exchanges y pares activos "
                    "vinculados, con su mínimo de orden",
        propiedad=Propiedad(unidad="lista", direccion=Direccion.CONTEXTUAL),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="los pares activos vinculados a la coin en los exchanges "
                 "operables (MEXC, CoinEx): símbolo, quote y mínimo de orden",
            infiere="que la coin es operable en esos mercados —el vínculo "
                    "coin↔par se resolvió automáticamente por símbolo base",
            no_sabe="sólo cubre los exchanges que AXIOM cataloga (MEXC, CoinEx), "
                    "no todos los del mundo. El vínculo automático por símbolo "
                    "puede errar con tickers repetidos. No dice cuánto se opera "
                    "en cada par —eso es liquidez, otra medición— ni si el par "
                    "tiene profundidad real",
            fuente="tabla pares, vínculo coin_id (MEXC + CoinEx via catálogo)",
            metodo="pares activos con coin_id = la coin resuelta")))

    logger.info("[capacidades] coin: estado, historia, mercados")
