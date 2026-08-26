"""
AXIOM v3 — Capacidades del mercado: el perfil de Bitcoin.
════════════════════════════════════════════════════════════════════════════════
NO ES UN RÉGIMEN. Es un PERFIL de cinco dimensiones, sin etiqueta.

POR QUÉ NO UNA ETIQUETA:
  Colapsar el estado en "alcista" o "bajista" destruye información por
  construcción. Un mercado que sube con volatilidad baja y en línea recta no es
  el mismo que uno que sube con volatilidad alta y de ida y vuelta — y los dos
  se llamarían igual.

  Verificado sobre datos reales: a 30 días BTC muestra dirección alta
  (percentil 83), volatilidad baja (26) y estructura muy baja (5,4) — un
  movimiento direccional limpio. A 90 días, dirección media y estructura alta
  (80): en el trimestre fue de ida y vuelta. Las dos lecturas son ciertas y
  dicen cosas distintas.

QUÉ NO SUPONE ESTE PERFIL, y es deliberado:
  · que el estado PERSISTA. Describe lo que ya pasó, no lo que sigue.
  · que CONDICIONE lo que viene. El precio futuro lo determinan cosas que este
    perfil no puede ver: una decisión de política monetaria, una quiebra, una
    regulación. Decir que el estado "condiciona" confundiría correlación con
    causa.
  · que exista un estado "normal". El neutro de cada dimensión es su propia
    distribución histórica, no un número elegido.

CADA DIMENSIÓN DEVUELVE VALOR **Y** PERCENTIL:
  Una capacidad que devuelve un número sin decir si es alto o bajo está
  incompleta. `btc_volatilidad = 42,58` no significa nada solo; que esté en el
  percentil 26 de nueve años sí.

  Se calcula ACÁ, en cada capacidad, y no en el perfil que las reúne: sacarlo
  afuera por eficiencia dejaría a las simples devolviendo datos que nadie puede
  interpretar.

MEDIDO ANTES DE DECLARAR (26/08/2026, 3.296 velas desde 2017):
  Las cinco son independientes a 30 días — ninguna correlación supera 0,55.
  volatilidad ⊥ estructura: r = -0,020, prácticamente cero. Es el mismo
  hallazgo que en la capa par (r = 0,049): moverse mucho y volver sobre los
  pasos son cosas distintas.

  Y algo que no se buscaba: dirección y estructura pasan de -0,548 a 30 días a
  -0,805 a 90. LA INDEPENDENCIA DEPENDE DE LA ESCALA. A ventanas largas un
  movimiento sostenido no puede ser oscilación, así que las dos preguntas se
  vuelven una. Declarado en el `no_sabe` de ambas.
"""
from __future__ import annotations

import logging
from math import log, sqrt

from backend.nucleo.capacidades import (
    registro, Simple, Compuesta, Objeto, Direccion, Epistemico, Propiedad,
    Vigencia, Alcance)

logger = logging.getLogger(__name__)

VENTANA = {"default": 30, "min": 7, "max": 365}

# Contra cuánta historia se calcula el percentil. `None` = toda la serie.
#
# Toda la serie da perspectiva pero mezcla mercados: la volatilidad de 2017
# —cuando el volumen era sesenta veces menor— pesa igual que la de hoy. Una
# ventana corta es más representativa del mercado actual y pierde contexto.
# Por eso es un parámetro y no una decisión cableada.
HISTORIA = {"default": None, "min": 90, "max": 4000}

MINIMO = 7


def _percentil(valor: float, serie: list[float]) -> float | None:
    """Qué proporción de la serie histórica es menor que este valor."""
    if valor is None or not serie:
        return None
    return sum(1 for x in serie if x < valor) / len(serie) * 100


async def _serie(pool, historia: int | None) -> list:
    """Las velas contra las que se calcula el percentil."""
    async with pool.acquire() as conn:
        if historia:
            return await conn.fetch("""
                SELECT fecha, maximo, minimo, cierre, volumen FROM (
                    SELECT * FROM btc_vela_diaria ORDER BY fecha DESC LIMIT $1
                ) t ORDER BY fecha
            """, historia)
        return await conn.fetch("""
            SELECT fecha, maximo, minimo, cierre, volumen
            FROM btc_vela_diaria ORDER BY fecha
        """)


def _envolver(valor, filas, ventana, serie_hist, extra=None) -> dict:
    """
    Todo resultado declara su valor, su POSICIÓN HISTÓRICA, y sobre cuántas
    velas se calculó.

    `velas` no es un detalle: una lectura sobre 10 velas etiquetada como
    "ventana de 30 días" no es comparable con una sobre 30, y sin declararlo se
    ven idénticas.
    """
    p = _percentil(valor, serie_hist)
    d = {
        "valor": valor,
        "percentil": round(p, 1) if p is not None else None,
        # El percentil es lo COMPARABLE entre dimensiones —cada una tiene su
        # escala—. El valor es el hecho.
        "historia_dias": len(serie_hist),
        "velas": len(filas),
        "ventana_pedida": ventana,
        "ventana_completa": len(filas) >= ventana,
        "hasta": str(filas[-1]["fecha"]) if filas else None,
        "_fuente_hasta": filas[-1]["fecha"] if filas else None,
    }
    if extra:
        d.update(extra)
    return d


# ══ Los cálculos, aplicables a cualquier tramo ═══════════════════════════════
#
# Cada uno toma una lista de velas y devuelve un número. Se usan dos veces: para
# el valor de hoy, y recorriendo la historia para armar la distribución contra
# la que se calcula el percentil.

def _calc_direccion(w) -> float | None:
    if len(w) < MINIMO:
        return None
    ini, fin = float(w[0]["cierre"]), float(w[-1]["cierre"])
    return (fin / ini - 1) * 100 if ini > 0 else None


def _calc_volatilidad(w) -> float | None:
    if len(w) < MINIMO:
        return None
    c = [float(f["cierre"]) for f in w]
    rets = [log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0]
    if len(rets) < 3:
        return None
    m = sum(rets) / len(rets)
    sd = sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    return sd * sqrt(365) * 100


def _calc_estructura(w) -> float | None:
    if len(w) < MINIMO:
        return None
    recorrido = sum(
        (float(f["maximo"]) - float(f["minimo"])) / float(f["minimo"]) * 100
        for f in w if float(f["minimo"]) > 0)
    ini, fin = float(w[0]["cierre"]), float(w[-1]["cierre"])
    neto = abs((fin / ini - 1) * 100) if ini > 0 else 0
    if recorrido <= 0:
        return None
    # Acotado a [0,1]: un neto mayor que el recorrido sería un dato roto.
    return max(0.0, min(1.0, 1 - neto / recorrido))


def _distribucion(serie, ventana: int, calc) -> list[float]:
    """
    El mismo cálculo aplicado a cada tramo de la historia.

    Es lo que permite responder "alto o bajo respecto de qué": la distribución
    de todos los valores que la dimensión tomó, no un umbral elegido.
    """
    vals = []
    for i in range(ventana, len(serie) + 1):
        v = calc(serie[i - ventana:i])
        if v is not None:
            vals.append(v)
    return vals


# ══ Las cinco dimensiones ════════════════════════════════════════════════════

async def _direccion(contexto, ventana=30, historia=None, **_):
    serie = await _serie(contexto["pool"], historia)
    w = serie[-ventana:]
    return _envolver(_calc_direccion(w), w, ventana,
                     _distribucion(serie, ventana, _calc_direccion))


async def _volatilidad(contexto, ventana=30, historia=None, **_):
    serie = await _serie(contexto["pool"], historia)
    w = serie[-ventana:]
    return _envolver(_calc_volatilidad(w), w, ventana,
                     _distribucion(serie, ventana, _calc_volatilidad))


async def _estructura(contexto, ventana=30, historia=None, **_):
    serie = await _serie(contexto["pool"], historia)
    w = serie[-ventana:]
    return _envolver(_calc_estructura(w), w, ventana,
                     _distribucion(serie, ventana, _calc_estructura))


async def _posicion(contexto, ventana=30, historia=None, **_):
    """
    Distancia al máximo de TODA la serie, en %.

    No usa la ventana para el máximo: "cerca del máximo histórico" es una
    posición estructural, no de las últimas semanas.
    """
    serie = await _serie(contexto["pool"], historia)
    if not serie:
        return {"valor": None, "_fuente_hasta": None}
    maximos = [float(f["maximo"]) for f in serie]
    cierres = [float(f["cierre"]) for f in serie]
    ath = max(maximos)
    idx_ath = maximos.index(ath)

    # La distribución: qué distancia al máximo VIGENTE EN CADA MOMENTO tuvo el
    # precio. Usar el máximo de hoy para todo el pasado daría percentiles
    # falsos — en 2018 nadie estaba a -37 % de un máximo que no existía.
    dist = []
    corriente = 0.0
    for i, f in enumerate(serie):
        corriente = max(corriente, maximos[i])
        if corriente > 0:
            dist.append((cierres[i] / corriente - 1) * 100)

    valor = (cierres[-1] / ath - 1) * 100
    p = _percentil(valor, dist)
    return {
        "valor": valor,
        "percentil": round(p, 1) if p is not None else None,
        "maximo_historico": ath,
        "maximo_historico_fecha": str(serie[idx_ath]["fecha"]),
        "historia_dias": len(serie),
        "hasta": str(serie[-1]["fecha"]),
        "ventana_completa": True,
        "_fuente_hasta": serie[-1]["fecha"],
    }


async def _participacion(contexto, ventana=30, historia=None, **_):
    """
    Volumen de la ventana contra su media larga.

    SOLO desde donde el volumen es comparable. El corte no está cableado: sale
    de `btc_metricas_validas`, que es un dato consultable.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        desde = await conn.fetchval(
            "SELECT comparable_desde FROM btc_metricas_validas WHERE tipo='volumen'")
        serie = await conn.fetch("""
            SELECT fecha, cierre, volumen FROM btc_vela_diaria
            WHERE ($1::date IS NULL OR fecha >= $1) ORDER BY fecha
        """, desde)

    if len(serie) < ventana * 5:
        return _envolver(None, list(serie), ventana, [],
                         {"comparable_desde": str(desde) if desde else None})

    usd = [float(f["volumen"]) * float(f["cierre"]) for f in serie]

    def ratio(hasta_i: int) -> float | None:
        corta = usd[hasta_i - ventana:hasta_i]
        larga = usd[max(0, hasta_i - ventana * 5):hasta_i]
        if not corta or not larga:
            return None
        ml = sum(larga) / len(larga)
        return (sum(corta) / len(corta)) / ml if ml > 0 else None

    dist = [v for i in range(ventana * 5, len(usd) + 1)
            if (v := ratio(i)) is not None]
    return _envolver(ratio(len(usd)), list(serie[-ventana:]), ventana, dist,
                     {"comparable_desde": str(desde) if desde else None})


# ══ La operación: reunir ═════════════════════════════════════════════════════

@registro.operacion("reunir")
async def _reunir(partes, pesos, parametros, contexto,
                  esperados=0, faltantes=(), **_):
    """
    Junta varias capacidades sin transformarlas.

    NO calcula nada nuevo ni produce una etiqueta: el perfil ES sus partes.
    Cualquier resumen que se le pusiera encima sería una inferencia, y este
    perfil no infiere.
    """
    return {
        "dimensiones": {n: r.valor for n, r in partes.items()},
        "completo": len(partes) == esperados,
        "faltantes": list(faltantes) or None,
    }


# ══ Las declaraciones ════════════════════════════════════════════════════════

_SOLAPAMIENTO = (
    "a ventanas largas se solapa con la dirección: medido, la correlación "
    "entre ambas pasa de -0,548 a 30 días a -0,805 a 90. A esa escala un "
    "movimiento sostenido no puede ser oscilación, así que las dos preguntas "
    "se vuelven una"
)

_PARAMS = {"ventana": VENTANA, "historia": HISTORIA}


def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="btc_direccion", objeto=Objeto.MERCADO, funcion=_direccion,
        alcance=Alcance.INDIVIDUAL, parametros=_PARAMS,
        descripcion="Cuánto se desplazó el precio de BTC en la ventana",
        propiedad=Propiedad(unidad="%", direccion=Direccion.NEUTRA,
                            minimo=-95, maximo=500),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el retorno acumulado entre el primer y el último cierre de "
                 "la ventana, y su percentil contra la distribución histórica "
                 "de esa misma medida",
            no_sabe="no dice CÓMO llegó ahí: el mismo +20 % puede ser una "
                    "subida sostenida o una montaña rusa. Para eso está la "
                    "estructura. Y a ventanas largas ambas se solapan "
                    "(r = -0,805 a 90 días)",
            fuente="binance:BTC/USDT — serie de referencia, NO un par operable",
            metodo="cierre contra cierre; no considera lo que pasó adentro")))

    registro.registrar(Simple(
        nombre="btc_volatilidad", objeto=Objeto.MERCADO, funcion=_volatilidad,
        alcance=Alcance.INDIVIDUAL, parametros=_PARAMS,
        descripcion="Cuánto se mueve BTC día a día, anualizado",
        propiedad=Propiedad(unidad="% anualizado",
                            direccion=Direccion.CONTEXTUAL, minimo=0, maximo=400),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el desvío estándar de los retornos logarítmicos diarios, "
                 "anualizado, y su percentil histórico",
            no_sabe="es SIMÉTRICA: no distingue la volatilidad de subida de la "
                    "de caída, y para operar no son lo mismo. El número solo no "
                    "dice si es alta o baja — eso lo dice el percentil",
            fuente="binance:BTC/USDT",
            metodo="retornos LOGARÍTMICOS: con retornos simples una suba del "
                   "50 % y una baja del 33 % —que se cancelan— pesarían "
                   "distinto")))

    registro.registrar(Simple(
        nombre="btc_estructura", objeto=Objeto.MERCADO, funcion=_estructura,
        alcance=Alcance.INDIVIDUAL, parametros=_PARAMS,
        descripcion="Si BTC recorre y vuelve, o se desplaza en línea recta",
        propiedad=Propiedad(unidad="0-1", direccion=Direccion.CONTEXTUAL,
                            minimo=0, maximo=1),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="1 − (desplazamiento neto / recorrido total) sobre la "
                 "ventana, y su percentil histórico",
            infiere="que un valor alto describe un mercado que vuelve sobre sus "
                    "pasos. NO infiere que vaya a seguir haciéndolo",
            no_sabe=f"no dice nada sobre el futuro: un mercado que osciló 30 "
                    f"días puede romper mañana. Y {_SOLAPAMIENTO}",
            fuente="binance:BTC/USDT",
            metodo="Efficiency Ratio invertido. Medido sobre 3.296 velas: es "
                   "INDEPENDIENTE de la volatilidad (r = -0,020) — un mercado "
                   "puede ser muy volátil y no ir a ningún lado")))

    registro.registrar(Simple(
        nombre="btc_posicion", objeto=Objeto.MERCADO, funcion=_posicion,
        alcance=Alcance.INDIVIDUAL, parametros=_PARAMS,
        descripcion="A qué distancia está BTC de su máximo histórico",
        propiedad=Propiedad(unidad="%", direccion=Direccion.CONTEXTUAL,
                            minimo=-95, maximo=0),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la distancia porcentual entre el último cierre y el máximo "
                 "de la serie, y su percentil contra la distancia al máximo "
                 "VIGENTE EN CADA MOMENTO del pasado",
            no_sabe="el máximo histórico depende de DÓNDE EMPIEZA la serie: la "
                    "de AXIOM arranca en 2017-08-17 porque es lo que Binance "
                    "ofrece. Un máximo anterior no se ve. Y estar lejos del "
                    "máximo no dice si está barato: dice dónde está",
            fuente="binance:BTC/USDT desde 2017-08-17",
            metodo="el percentil usa el máximo vigente en cada fecha, no el de "
                   "hoy: en 2018 nadie estaba a -37 % de un máximo que todavía "
                   "no existía. Medido: es INDEPENDIENTE de la dirección "
                   "(r = 0,339) — BTC puede subir 23 % y seguir a 38 % de su "
                   "máximo")))

    registro.registrar(Simple(
        nombre="btc_participacion", objeto=Objeto.MERCADO,
        funcion=_participacion, alcance=Alcance.INDIVIDUAL, parametros=_PARAMS,
        descripcion="Si el volumen reciente es alto o bajo contra su media",
        propiedad=Propiedad(unidad="ratio", direccion=Direccion.CONTEXTUAL,
                            minimo=0, maximo=20),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el volumen medio en USD de la ventana dividido por el de una "
                 "ventana cinco veces más larga, y su percentil histórico",
            no_sabe="es el volumen de UN exchange —Binance— y de UN par "
                    "—BTC/USDT—: no es el volumen del mercado. Y no distingue "
                    "volumen de acumulación del de distribución",
            fuente="binance:BTC/USDT",
            metodo="SOLO desde 2020-01-01, según btc_metricas_validas. Medido: "
                   "el volumen medio diario de 2017 fue 53 M USD contra "
                   "3.170 M en 2021 — sesenta veces menos. Antes de esa fecha "
                   "esto mediría el crecimiento de Binance, no el mercado")))

    # ── La compuesta ────────────────────────────────────────────────────────
    registro.registrar(Compuesta(
        nombre="btc_perfil", objeto=Objeto.MERCADO,
        operacion="reunir",
        componentes=["btc_direccion", "btc_volatilidad", "btc_estructura",
                     "btc_posicion", "btc_participacion"],
        parametros=_PARAMS,
        descripcion="El estado de Bitcoin en cinco dimensiones independientes",
        propiedad=Propiedad(unidad="perfil", direccion=Direccion.CONTEXTUAL),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="las cinco dimensiones juntas, cada una con su valor y su "
                 "percentil histórico",
            no_sabe="NO produce una etiqueta, y es deliberado: colapsar el "
                    "estado en 'alcista' o 'bajista' destruiría lo que "
                    "distingue un mercado que sube tranquilo de uno que sube "
                    "violento. Tampoco supone que el estado persista ni que "
                    "condicione lo que viene — el precio futuro lo determinan "
                    "cosas que este perfil no puede ver",
            metodo="reunir, no clasificar: el perfil ES sus partes. Las cinco "
                   "dimensiones se verificaron independientes a 30 días "
                   "(ninguna correlación supera 0,55) sobre 3.296 velas")))

    logger.info("[capacidades] mercado: perfil de BTC en 5 dimensiones")
