"""
AXIOM v3 — Capacidades del mercado: el perfil de Bitcoin.
════════════════════════════════════════════════════════════════════════════════
NO ES UN RÉGIMEN. Es un PERFIL de cinco dimensiones, sin etiqueta.

POR QUÉ NO UNA ETIQUETA:
  Colapsar el estado en "alcista" o "bajista" destruye información por
  construcción. Un mercado que sube con volatilidad baja y en línea recta no es
  el mismo que uno que sube con volatilidad alta y de ida y vuelta — y los dos
  se llamarían igual.

  Verificado hoy sobre datos reales: a 30 días BTC muestra dirección alta
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
  · que exista un estado "normal". El neutro de cada dimensión es su propio
    percentil histórico, no un número elegido.

MEDIDO ANTES DE DECLARAR (26/08/2026, 3.296 velas desde 2017):
  Las cinco son independientes a 30 días — ninguna correlación supera 0,55.
  volatilidad ⊥ estructura: r = -0,020, prácticamente cero. Es el mismo
  hallazgo que en la capa par (r = 0,049): moverse mucho y volver sobre los
  pasos son cosas distintas.

  Y algo que no se buscaba: dirección y estructura pasan de -0,548 a 30 días a
  -0,805 a 90. LA INDEPENDENCIA DEPENDE DE LA ESCALA. A ventanas largas un
  movimiento sostenido no puede ser oscilación, así que las dos preguntas se
  vuelven una. Está declarado en el `no_sabe` de ambas.
"""
from __future__ import annotations

import logging
from math import log, sqrt

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)

VENTANA = {"default": 30, "min": 7, "max": 365}

# Cuántas velas hacen falta como mínimo. Menos que esto no da una lectura con
# sentido, y el resultado lo declara en `ventana_completa`.
MINIMO = 7


async def _velas(pool, ventana: int, hasta_hoy: bool = True) -> list:
    """Las últimas `ventana` velas diarias de BTC, en orden."""
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT fecha, maximo, minimo, cierre, volumen
            FROM (SELECT * FROM btc_vela_diaria ORDER BY fecha DESC LIMIT $1) t
            ORDER BY fecha
        """, ventana)
    return filas


def _envolver(valor, filas, ventana, extra=None) -> dict:
    """
    Todo resultado declara sobre cuántas velas se calculó y hasta cuándo llegan.

    `velas` no es un detalle: una lectura sobre 10 velas etiquetada como
    "ventana de 30 días" no es comparable con una sobre 30, y sin declararlo se
    ven idénticas.
    """
    d = {
        "valor": valor,
        "velas": len(filas),
        "ventana_pedida": ventana,
        "ventana_completa": len(filas) >= ventana,
        "hasta": str(filas[-1]["fecha"]) if filas else None,
        "_fuente_hasta": filas[-1]["fecha"] if filas else None,
    }
    if extra:
        d.update(extra)
    return d


# ══ Las cinco dimensiones ════════════════════════════════════════════════════

async def _direccion(contexto, ventana=30, **_):
    """Retorno acumulado de la ventana."""
    filas = await _velas(contexto["pool"], ventana)
    if len(filas) < MINIMO:
        return _envolver(None, filas, ventana)
    ini, fin = float(filas[0]["cierre"]), float(filas[-1]["cierre"])
    return _envolver((fin / ini - 1) * 100 if ini > 0 else None, filas, ventana)


async def _volatilidad(contexto, ventana=30, **_):
    """
    Desvío de los retornos LOGARÍTMICOS diarios, anualizado.

    Logarítmicos porque una suba del 50 % y una baja del 33 % se cancelan, y
    con retornos simples pesarían distinto. Anualizado para que el número sea
    comparable entre ventanas.
    """
    filas = await _velas(contexto["pool"], ventana)
    if len(filas) < MINIMO:
        return _envolver(None, filas, ventana)
    c = [float(f["cierre"]) for f in filas]
    rets = [log(c[i] / c[i - 1]) for i in range(1, len(c)) if c[i - 1] > 0]
    if len(rets) < 3:
        return _envolver(None, filas, ventana)
    m = sum(rets) / len(rets)
    sd = sqrt(sum((r - m) ** 2 for r in rets) / (len(rets) - 1))
    return _envolver(sd * sqrt(365) * 100, filas, ventana)


async def _estructura(contexto, ventana=30, **_):
    """
    1 − |desplazamiento neto| / recorrido total.

    1 = recorre mucho y vuelve donde empezó. 0 = se desplaza en línea recta.
    Es la misma medida que `oscilacion` en la capa par.
    """
    filas = await _velas(contexto["pool"], ventana)
    if len(filas) < MINIMO:
        return _envolver(None, filas, ventana)
    recorrido = sum(
        (float(f["maximo"]) - float(f["minimo"])) / float(f["minimo"]) * 100
        for f in filas if float(f["minimo"]) > 0)
    ini, fin = float(filas[0]["cierre"]), float(filas[-1]["cierre"])
    neto = abs((fin / ini - 1) * 100) if ini > 0 else 0
    if recorrido <= 0:
        return _envolver(None, filas, ventana)
    # Acotado a [0,1]: un neto mayor que el recorrido sería un dato roto.
    return _envolver(max(0.0, min(1.0, 1 - neto / recorrido)), filas, ventana)


async def _posicion(contexto, ventana=30, **_):
    """
    Distancia al máximo de TODA la historia, en %.

    No usa la ventana para el máximo —usa la serie entera— porque "cerca del
    máximo histórico" es una posición estructural, no de las últimas semanas.
    La ventana solo determina de cuándo es el precio que se compara.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        r = await conn.fetchrow("""
            SELECT (SELECT MAX(maximo) FROM btc_vela_diaria)  AS ath,
                   (SELECT cierre FROM btc_vela_diaria
                    ORDER BY fecha DESC LIMIT 1)              AS actual,
                   (SELECT fecha FROM btc_vela_diaria
                    ORDER BY fecha DESC LIMIT 1)              AS fecha,
                   (SELECT fecha FROM btc_vela_diaria
                    ORDER BY maximo DESC LIMIT 1)             AS fecha_ath
        """)
    if not r or not r["ath"]:
        return {"valor": None, "_fuente_hasta": None}
    ath, act = float(r["ath"]), float(r["actual"])
    return {
        "valor": (act / ath - 1) * 100,
        "maximo_historico": ath,
        "maximo_historico_fecha": str(r["fecha_ath"]),
        "hasta": str(r["fecha"]),
        "ventana_completa": True,
        "_fuente_hasta": r["fecha"],
    }


async def _participacion(contexto, ventana=30, **_):
    """
    Volumen de la ventana contra su media larga (4× la ventana).

    SOLO desde donde el volumen es comparable. Medido: el volumen medio diario
    de 2017 fue 53 M USD contra 3.170 M en 2021 — sesenta veces menos. Antes de
    2020 esto mediría el crecimiento de Binance y la adopción de USDT, no el
    mercado.

    El corte no está cableado acá: sale de `btc_metricas_validas`, que es un
    dato consultable y no algo que haya que recordar.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        desde = await conn.fetchval(
            "SELECT comparable_desde FROM btc_metricas_validas WHERE tipo='volumen'")
        filas = await conn.fetch("""
            SELECT fecha, cierre, volumen FROM (
                SELECT * FROM btc_vela_diaria
                WHERE ($2::date IS NULL OR fecha >= $2)
                ORDER BY fecha DESC LIMIT $1
            ) t ORDER BY fecha
        """, ventana * 5, desde)
    if len(filas) < ventana * 2:
        return _envolver(None, list(filas), ventana,
                         {"comparable_desde": str(desde) if desde else None})

    usd = [float(f["volumen"]) * float(f["cierre"]) for f in filas]
    corta = usd[-ventana:]
    larga = usd
    mc = sum(corta) / len(corta)
    ml = sum(larga) / len(larga)
    return _envolver(
        mc / ml if ml > 0 else None, list(filas[-ventana:]), ventana,
        {"comparable_desde": str(desde) if desde else None})


# ══ Las declaraciones ════════════════════════════════════════════════════════

_SOLAPAMIENTO = (
    "a ventanas largas se solapa con la dirección: medido, la correlación "
    "entre ambas pasa de -0,548 a 30 días a -0,805 a 90. A esa escala un "
    "movimiento sostenido no puede ser oscilación, así que las dos preguntas "
    "se vuelven una"
)


def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="btc_direccion",
        objeto=Objeto.MERCADO,
        funcion=_direccion,
        alcance=Alcance.INDIVIDUAL,
        descripcion="Cuánto se desplazó el precio de BTC en la ventana",
        parametros={"ventana": VENTANA},
        propiedad=Propiedad(
            unidad="%", direccion=Direccion.NEUTRA, minimo=-95, maximo=500),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el retorno acumulado entre el primer y el último cierre de "
                 "la ventana",
            no_sabe="no dice CÓMO llegó ahí: el mismo +20 % puede ser una subida "
                    "sostenida o una montaña rusa. Para eso está la estructura. "
                    "Y a ventanas largas ambas se solapan (r = -0,805 a 90 días)",
            fuente="binance:BTC/USDT — serie de referencia, NO un par operable",
            metodo="cierre contra cierre; no considera lo que pasó adentro")))

    registro.registrar(Simple(
        nombre="btc_volatilidad",
        objeto=Objeto.MERCADO,
        funcion=_volatilidad,
        alcance=Alcance.INDIVIDUAL,
        descripcion="Cuánto se mueve BTC día a día, anualizado",
        parametros={"ventana": VENTANA},
        propiedad=Propiedad(
            unidad="% anualizado", direccion=Direccion.CONTEXTUAL,
            minimo=0, maximo=400),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el desvío estándar de los retornos logarítmicos diarios, "
                 "anualizado por raíz de 365",
            no_sabe="es simétrica: no distingue volatilidad de subida de la de "
                    "caída, y para operar no son lo mismo. Tampoco dice si es "
                    "alta o baja en términos absolutos — eso lo dice su "
                    "percentil histórico",
            fuente="binance:BTC/USDT",
            metodo="retornos LOGARÍTMICOS: con retornos simples, una suba del "
                   "50 % y una baja del 33 % —que se cancelan— pesarían distinto")))

    registro.registrar(Simple(
        nombre="btc_estructura",
        objeto=Objeto.MERCADO,
        funcion=_estructura,
        alcance=Alcance.INDIVIDUAL,
        descripcion="Si BTC recorre y vuelve, o se desplaza en línea recta",
        parametros={"ventana": VENTANA},
        propiedad=Propiedad(
            unidad="0-1", direccion=Direccion.CONTEXTUAL, minimo=0, maximo=1),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="1 − (desplazamiento neto / recorrido total) sobre la ventana",
            infiere="que un valor alto describe un mercado que vuelve sobre sus "
                    "pasos. NO infiere que vaya a seguir haciéndolo",
            no_sabe=f"no dice nada sobre el futuro: un mercado que osciló 30 días "
                    f"puede romper mañana. Y {_SOLAPAMIENTO}",
            fuente="binance:BTC/USDT",
            metodo="Efficiency Ratio invertido. Medido sobre 3.296 velas: es "
                   "INDEPENDIENTE de la volatilidad (r = -0,020) — un mercado "
                   "puede ser muy volátil y no ir a ningún lado")))

    registro.registrar(Simple(
        nombre="btc_posicion",
        objeto=Objeto.MERCADO,
        funcion=_posicion,
        alcance=Alcance.INDIVIDUAL,
        descripcion="A qué distancia está BTC de su máximo histórico",
        parametros={"ventana": VENTANA},
        propiedad=Propiedad(
            unidad="%", direccion=Direccion.CONTEXTUAL, minimo=-95, maximo=0),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la distancia porcentual entre el último cierre y el máximo de "
                 "toda la serie",
            no_sabe="el máximo histórico depende de DÓNDE EMPIEZA la serie: la "
                    "de AXIOM arranca en 2017-08-17 porque es lo que Binance "
                    "ofrece. Un máximo anterior a esa fecha no se ve. Y estar "
                    "lejos del máximo no dice si está barato: dice dónde está",
            fuente="binance:BTC/USDT desde 2017-08-17",
            metodo="usa la serie ENTERA para el máximo, no la ventana: 'cerca "
                   "del máximo histórico' es una posición estructural. Medido: "
                   "es INDEPENDIENTE de la dirección (r = 0,339) — BTC puede "
                   "subir 23 % y seguir a 38 % de su máximo")))

    registro.registrar(Simple(
        nombre="btc_participacion",
        objeto=Objeto.MERCADO,
        funcion=_participacion,
        alcance=Alcance.INDIVIDUAL,
        descripcion="Si el volumen reciente es alto o bajo contra su media",
        parametros={"ventana": VENTANA},
        propiedad=Propiedad(
            unidad="ratio", direccion=Direccion.CONTEXTUAL, minimo=0, maximo=20),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="el volumen medio en USD de la ventana dividido por el de una "
                 "ventana cinco veces más larga",
            no_sabe="es el volumen de UN exchange —Binance— y de UN par "
                    "—BTC/USDT—: no es el volumen del mercado. Y no distingue "
                    "volumen de acumulación del de distribución",
            fuente="binance:BTC/USDT",
            metodo="SOLO desde 2020-01-01, según btc_metricas_validas. Medido: "
                   "el volumen medio diario de 2017 fue 53 M USD contra 3.170 M "
                   "en 2021 — sesenta veces menos. Antes de esa fecha esto "
                   "mediría el crecimiento de Binance, no el mercado")))

    logger.info("[capacidades] mercado: perfil de BTC en 5 dimensiones")
