"""
AXIOM v3 — Posicionamiento de BTC (Deribit).
════════════════════════════════════════════════════════════════════════════════
Dos lecturas del ESTADO del posicionamiento del mercado sobre BTC. Ninguna es
una pregunta operativa —no dicen cuándo entrar ni qué va a hacer el precio—;
describen dónde está cargado y concentrado el mercado, contra su propia historia.

POR QUÉ SON DE BTC-LA-REFERENCIA Y NO DE UN PAR:

  El funding y las opciones de Deribit son propiedades del posicionamiento
  agregado sobre BTC, no de un par operable en MEXC o CoinEx. Igual que
  `btc_recorrido_oculto`, describen el activo de referencia, no una entrada.

LO QUE HAY QUE TENER PRESENTE (va al `no_sabe`, no es un detalle):

  - El FUNDING mide el costo de mantener un perpetuo, no una intención. Positivo
    sostenido = los largos pagan a los cortos = apalancamiento comprador cargado.
    Es PRESIÓN, no DIRECCIÓN: el funding puede quedar caro mucho tiempo sin que
    el precio ceda, y un pico puede ser tanto euforia por agotarse como fuerza
    genuina. Se guarda y se compara en FRACCIÓN (0,0001 = 0,01 %), la unidad de
    la fuente; convertir a porcentaje solo para mostrar.

  - El INTERÉS ABIERTO de opciones dice CONCENTRACIÓN, no lado. Por cada
    comprador hay un vendedor: un muro de OI en un strike marca dónde el mercado
    tiene exposición acumulada, no hacia dónde apuesta. El put/call por OI es
    una lectura de dónde se acumuló, no un pronóstico. Sin greeks capturados, no
    hay nada basado en delta: se trabaja con OI, strike, IV y distancia al spot.
"""
from __future__ import annotations

import logging
from datetime import date

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)

# Ventana por defecto para situar el valor actual contra su historia reciente.
DIAS_FUNDING = {"default": 30, "min": 7, "max": 365}


# ════════════════════════════════════════════════════════════════════════════
#  FUNDING
# ════════════════════════════════════════════════════════════════════════════
async def _funding(contexto, dias=30, **_) -> dict:
    """
    Estado de la tasa de funding de BTC contra su historia reciente.

    Lee la última tasa capturada y la sitúa dentro de la ventana de `dias`:
    su percentil, la mediana del período, cuántas horas estuvo positiva. Todo
    en FRACCIÓN; se agrega el equivalente en porcentaje solo para mostrar.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        ultima = await conn.fetchrow(
            "SELECT hora, tasa FROM funding_btc ORDER BY hora DESC LIMIT 1")
        if ultima is None:
            return {"valor": None, "horas": 0}

        # La ventana reciente: todas las tasas de los últimos `dias`, ordenadas,
        # para percentil y mediana. Traer la columna cruda y ordenar en Python
        # mantiene el cálculo del percentil a la vista y sin depender del motor
        # de percentiles de PostgreSQL.
        filas = await conn.fetch(
            """
            SELECT tasa FROM funding_btc
            WHERE hora >= (SELECT MAX(hora) FROM funding_btc)
                          - ($1::int * INTERVAL '1 day')
            ORDER BY tasa
            """,
            dias)

    tasas = [float(f["tasa"]) for f in filas]
    n = len(tasas)
    if n == 0:
        return {"valor": None, "horas": 0}

    actual = float(ultima["tasa"])
    mediana = tasas[n // 2]
    # Percentil del valor actual dentro de la ventana: fracción de horas por
    # debajo de él. 0,90 = más alto que el 90 % del período.
    menores = sum(1 for t in tasas if t < actual)
    percentil = round(menores / n, 3)
    positivas = sum(1 for t in tasas if t > 0)

    return {
        # Carril de razonamiento: fracción (unidad de la fuente).
        "tasa_actual": round(actual, 8),
        "mediana_ventana": round(mediana, 8),
        "percentil_actual": percentil,
        "horas_positivas_pct": round(positivas / n * 100, 1),
        "minimo_ventana": round(tasas[0], 8),
        "maximo_ventana": round(tasas[-1], 8),
        "horas": n,
        "dias_pedidos": dias,
        # Solo para mostrar: la misma tasa en porcentaje. No se razona sobre
        # esto —evita el error de v2 de comparar un umbral en % contra fracción.
        "tasa_actual_pct": round(actual * 100, 6),
        "mediana_ventana_pct": round(mediana * 100, 6),
        "_fuente_hasta": ultima["hora"],
    }


# ════════════════════════════════════════════════════════════════════════════
#  OPCIONES
# ════════════════════════════════════════════════════════════════════════════
async def _corte_trimestral(conn, fecha) -> date | None:
    """
    El vencimiento trimestral cercano: dónde cortar el cálculo de max-pain.

    Los trimestrales de Deribit (marzo, junio, sep, dic) son las paredes grandes
    del calendario. NO alcanza con "primer vencimiento en un mes trimestral": en
    septiembre hay diarios (1, 2, 3-sep) y semanales (4, 11, 18-sep) además del
    trimestral (25-sep). Tampoco basta "último viernes": hay cuatro viernes en
    el mes. Lo que SÍ define al trimestral es su tamaño —medido, no supuesto—:
    el 25-sep concentra 164k de OI contra 28k del segundo. Así que el corte es
    EL VENCIMIENTO DE MAYOR OI dentro del primer mes trimestral presente.
    """
    # El primer mes trimestral que aparece, como (año, mes).
    fila = await conn.fetchrow(
        """
        SELECT EXTRACT(YEAR FROM vencimiento)::int  AS anio,
               EXTRACT(MONTH FROM vencimiento)::int AS mes
        FROM opcion_diaria
        WHERE fecha = $1 AND EXTRACT(MONTH FROM vencimiento) IN (3,6,9,12)
        ORDER BY vencimiento LIMIT 1
        """,
        fecha)
    if fila is None:
        return None
    # Dentro de ese mes, el vencimiento de mayor OI: el trimestral.
    corte = await conn.fetchval(
        """
        SELECT vencimiento
        FROM opcion_diaria
        WHERE fecha = $1
          AND EXTRACT(YEAR FROM vencimiento)::int = $2
          AND EXTRACT(MONTH FROM vencimiento)::int = $3
        GROUP BY vencimiento
        ORDER BY SUM(interes_abierto) DESC NULLS LAST LIMIT 1
        """,
        fecha, fila["anio"], fila["mes"])
    return corte


def _max_pain(strikes: list[tuple[float, str, float]]) -> tuple[float | None, float | None]:
    """
    Max-pain: el strike donde MÁS opciones expiran sin valor.

    Para cada strike candidato K, se suma el valor intrínseco total que tendrían
    todas las opciones abiertas si el precio expirara en K:
      · cada call con strike < K vale (K − strike) × OI
      · cada put  con strike > K vale (strike − K) × OI
    El K que MINIMIZA esa suma es max-pain — el punto de menor pago total a los
    tenedores, el "imán" que muestra la web de Deribit.

    `strikes` es una lista de (strike, tipo, oi). Devuelve (strike, dolor_min).
    El cálculo pondera por distancia: un OI lejano pesa más en la suma, así que
    max-pain es sensible a strikes extremos con mucho OI. Es el método estándar.
    """
    candidatos = sorted({s for s, _, _ in strikes})
    if not candidatos:
        return None, None

    mejor_k = None
    menor_dolor = None
    for k in candidatos:
        dolor = 0.0
        for strike, tipo, oi in strikes:
            if tipo == "call" and strike < k:
                dolor += (k - strike) * oi
            elif tipo == "put" and strike > k:
                dolor += (strike - k) * oi
        if menor_dolor is None or dolor < menor_dolor:
            menor_dolor = dolor
            mejor_k = k
    return mejor_k, menor_dolor


async def _opciones(contexto, **_) -> dict:
    """
    Estado del posicionamiento en opciones de BTC del último día capturado.

    Dos lecturas que NO se mezclan, replicando lo que presenta la propia fuente
    (Deribit calcula estas métricas sobre los datos crudos por instrumento; no
    hay endpoint que las sirva hechas, así que las calculamos igual que su web):

      · AGREGADO (contexto macro): put/call por OI y OI total sobre todos los
        vencimientos. Es posicionamiento de fondo, no dirección.

      · MAX-PAIN de corto/medio plazo: el strike donde más opciones expiran sin
        valor —el "imán" del precio hacia el vencimiento— calculado SOLO sobre
        los vencimientos hasta el trimestral cercano inclusive, para que no lo
        contaminen los trimestrales lejanos (dic, mar) que no tocan el spot de
        estos días.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        ultima_fecha = await conn.fetchval(
            "SELECT MAX(fecha) FROM opcion_diaria")
        if ultima_fecha is None:
            return {"valor": None, "contratos": 0}

        # AGREGADO: todos los vencimientos. Contexto macro.
        agg = await conn.fetchrow(
            """
            SELECT COUNT(*)                                        AS contratos,
                   COUNT(DISTINCT vencimiento)                     AS vencimientos,
                   SUM(interes_abierto)                            AS oi_total,
                   SUM(interes_abierto) FILTER (WHERE tipo='put')  AS oi_put,
                   SUM(interes_abierto) FILTER (WHERE tipo='call') AS oi_call,
                   MAX(subyacente_precio)                          AS spot
            FROM opcion_diaria WHERE fecha = $1
            """,
            ultima_fecha)

        # El corte: el trimestral cercano (mayor OI del primer mes trimestral).
        corte = await _corte_trimestral(conn, ultima_fecha)
        # Si no hay ningún trimestral capturado (raro), el corte es el último
        # vencimiento presente: max-pain cae sobre "todos", y queda declarado.
        if corte is None:
            corte = await conn.fetchval(
                "SELECT MAX(vencimiento) FROM opcion_diaria WHERE fecha = $1",
                ultima_fecha)

        # Los strikes hasta el corte, para calcular max-pain en Python.
        filas = []
        if corte is not None:
            filas = await conn.fetch(
                """
                SELECT strike, tipo, SUM(interes_abierto) AS oi
                FROM opcion_diaria
                WHERE fecha = $1 AND vencimiento <= $2 AND interes_abierto > 0
                GROUP BY strike, tipo
                """,
                ultima_fecha, corte)

    oi_put = float(agg["oi_put"] or 0)
    oi_call = float(agg["oi_call"] or 0)
    spot = float(agg["spot"]) if agg["spot"] is not None else None

    strikes = [(float(f["strike"]), f["tipo"], float(f["oi"])) for f in filas]
    max_pain, _dolor = _max_pain(strikes)

    dist_max_pain_pct = None
    if spot and max_pain and spot > 0:
        dist_max_pain_pct = round((max_pain - spot) / spot * 100, 2)

    return {
        # Agregado — contexto.
        "put_call_oi": round(oi_put / oi_call, 3) if oi_call > 0 else None,
        "oi_total": round(float(agg["oi_total"] or 0), 1),
        "oi_put": round(oi_put, 1),
        "oi_call": round(oi_call, 1),
        "spot": spot,
        "contratos": agg["contratos"],
        "vencimientos": agg["vencimientos"],
        # Max-pain de corto/medio plazo — el imán del precio, como en Deribit.
        "max_pain": max_pain,
        # Positiva: max-pain por encima del spot. Negativa: por debajo.
        "distancia_max_pain_pct": dist_max_pain_pct,
        "max_pain_hasta_venc": str(corte) if corte else None,
        "_fuente_hasta": ultima_fecha,
    }


# ════════════════════════════════════════════════════════════════════════════
#  DECLARACIÓN
# ════════════════════════════════════════════════════════════════════════════
def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="btc_funding", objeto=Objeto.MERCADO,
        funcion=_funding, alcance=Alcance.INDIVIDUAL,
        parametros={"dias": DIAS_FUNDING},
        descripcion="Estado de la tasa de funding de BTC contra su historia "
                    "reciente: nivel actual, percentil y signo dominante",
        propiedad=Propiedad(unidad="fracción", direccion=Direccion.CONTEXTUAL,
                            minimo=-0.01, maximo=0.01),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la última tasa de funding capturada, en fracción, y su "
                 "posición dentro de la ventana reciente: percentil contra las "
                 "tasas del período, mediana, y qué porcentaje de las horas "
                 "estuvo positiva",
            infiere="que un funding positivo y alto en su percentil describe un "
                    "mercado donde los largos pagan a los cortos —apalancamiento "
                    "comprador cargado—; negativo, lo inverso. Es una lectura de "
                    "PRESIÓN acumulada, no de dirección futura",
            no_sabe="no dice qué va a hacer el precio. El funding puede quedar "
                    "caro mucho tiempo sin que el precio ceda, y un pico tanto "
                    "puede anunciar agotamiento como confirmar fuerza. Mide el "
                    "costo de mantener el perpetuo, no la intención de nadie: "
                    "por cada largo que paga hay un corto que cobra. Es sobre el "
                    "perpetuo inverso de Deribit (BTC/USD), no sobre el par "
                    "operable en MEXC o CoinEx",
            fuente="deribit:BTC/USD:BTC, funding horario — perpetuo inverso, "
                   "elegido sobre Binance porque no satura en el cap de 0,01 %",
            metodo="última tasa capturada; percentil como fracción de horas de "
                   "la ventana por debajo del valor actual; todo en fracción, el "
                   "porcentaje se agrega solo para mostrar")))

    registro.registrar(Simple(
        nombre="btc_opciones", objeto=Objeto.MERCADO,
        funcion=_opciones, alcance=Alcance.INDIVIDUAL,
        parametros={},
        descripcion="Estado del posicionamiento en opciones de BTC: put/call y "
                    "OI total (contexto) y el max-pain de corto/medio plazo "
                    "contra el spot (el imán del precio, como en Deribit)",
        propiedad=Propiedad(unidad="ratio", direccion=Direccion.CONTEXTUAL,
                            minimo=0, maximo=10),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="del último día capturado, en dos planos: (1) AGREGADO sobre "
                 "todos los vencimientos — razón put/call por interés abierto y "
                 "OI total; (2) MAX-PAIN — el strike donde más opciones expiran "
                 "sin valor, calculado sobre los vencimientos hasta el trimestral "
                 "cercano inclusive, y su distancia porcentual al spot",
            infiere="que el agregado describe el posicionamiento de fondo, y que "
                    "el max-pain marca el punto de menor pago total a los "
                    "tenedores —el nivel hacia el que, según la teoría de "
                    "max-pain, el precio tiende a gravitar cerca del vencimiento",
            no_sabe="el interés abierto NO dice de qué lado está cada "
                    "participante: por cada comprador hay un vendedor, mide "
                    "CONCENTRACIÓN, no dirección. Max-pain es una regularidad "
                    "estadística discutida, no una ley: el precio no tiene por "
                    "qué ir ahí, y el número pondera por distancia, así que es "
                    "sensible a strikes extremos con mucho OI. El trimestral se "
                    "detecta por su OI, no por la regla del último viernes de "
                    "Deribit. Sin greeks capturados no hay lectura basada en "
                    "delta ni gamma-exposure. Es el último día en la tabla, no "
                    "intradía en vivo",
            fuente="deribit, opciones de BTC — una fila por opción por día, con "
                   "el precio spot al capturar para reconstruir ITM/OTM",
            metodo="put/call por OI sobre el agregado; max-pain minimizando el "
                   "valor intrínseco total (calls con strike<K + puts con "
                   "strike>K, ponderado por OI) sobre los strikes hasta el "
                   "trimestral cercano — mismo cálculo que muestra la web de "
                   "Deribit, hecho sobre los datos crudos porque no hay endpoint "
                   "que lo sirva")))

    logger.info("[capacidades] btc: funding, opciones (posicionamiento Deribit)")
