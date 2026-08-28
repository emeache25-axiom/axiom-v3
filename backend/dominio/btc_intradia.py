"""
AXIOM v3 — Lo que la vela diaria no puede mostrar.
════════════════════════════════════════════════════════════════════════════════
Dos preguntas sobre las velas horarias:

  · ¿en qué hora del día se producen los GIROS? El máximo y el mínimo del día
    SON los giros del día.
  · si compro a la hora H, ¿qué tan cerca del mínimo del día estaría? Y si
    vendo a la hora H, ¿qué tan cerca del máximo?

Las dos, en tres poblaciones: global, días alcistas y días bajistas.

═══ POR QUÉ SEPARAR ALCISTAS DE BAJISTAS ═══════════════════════════════════════

Medido el 28/08/2026 sobre 729 días, y fue el hallazgo que obligó a rehacer
esto:

  · en días ALCISTAS el mínimo cae en la hora 0 el 28,8 % de las veces
  · en días BAJISTAS, el 0,8 %
  · y al revés para el máximo: 25,2 % en bajistas, CERO en alcistas

La distribución global mezcla dos poblaciones con lógica OPUESTA y el resultado
es un promedio que no describe a ninguna. Un z de 14,57 en la hora 0 que parecía
un hallazgo era aritmética: en un día que sube, el mínimo tiene que estar antes
de que suba.

Confirmado por la prueba más directa: cuando el mínimo cae en la hora 0 está a
-0,24 % de la apertura; cuando cae en otra hora, a -1,42 %. Seis veces más
lejos. "Mínimo en la hora 0" significaba, la mayoría de las veces, que el precio
NUNCA BAJÓ de donde abrió.

Separar las poblaciones no elimina el efecto —sigue ahí, y es real— pero lo
muestra en vez de promediarlo hasta volverlo engañoso.

═══ LA VENTAJA TIENE QUE SUPERAR EL COSTO ══════════════════════════════════════

`btc_calidad_horaria` reporta la diferencia entre la mejor y la peor hora. Si
esa diferencia es 0,3 % y el spread es 0,4 %, la ventaja NO EXISTE por más
significativa que sea estadísticamente.

Es la distinción entre un hallazgo y algo accionable, y se declara en el
resultado en vez de dejarla a criterio de quien mira.
"""
from __future__ import annotations

import logging
from datetime import date
from math import sqrt

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)

MESES = {"default": 12, "min": 3, "max": 108}
HORAS = 24
TASA_BASE = 100 / HORAS          # 4,1667 % por hora si fuera azar
CASOS_MINIMOS = 20               # por hora, para que la comparación signifique


async def _dias(pool, meses: int) -> dict:
    """
    Los días UTC completos, con sus 24 velas.

    Solo COMPLETOS: un día con 18 horas daría un extremo que quizá no es el
    extremo, y su hora sería un artefacto de dónde se cortó la serie.
    """
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT (hora AT TIME ZONE 'utc')::date              AS dia,
                   EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h,
                   apertura, maximo, minimo, cierre
            FROM btc_vela_horaria
            WHERE hora >= (now() AT TIME ZONE 'utc') - ($1 || ' months')::interval
            ORDER BY hora
        """, str(int(meses)))

    por_dia: dict = {}
    for f in filas:
        por_dia.setdefault(str(f["dia"]), []).append(f)
    return {d: v for d, v in por_dia.items() if len(v) == HORAS}


def _clasificar(velas) -> str:
    """Alcista si cierra por encima de donde abrió."""
    abre = float(velas[0]["apertura"])
    cierra = float(velas[-1]["cierre"])
    return "alcista" if cierra >= abre else "bajista"


def _z(observado: int, total: int, p: float = 1 / HORAS) -> float:
    """
    Cuántos desvíos por encima del azar. Aproximación normal a la binomial.

    NO corrige por mirar 24 horas: alguna va a destacar por casualidad. Un z de
    2 en la hora más alta es menos concluyente que un z de 2 en una hora
    elegida de antemano, y eso va declarado en el `no_sabe`.
    """
    esperado = total * p
    sd = sqrt(total * p * (1 - p))
    return (observado - esperado) / sd if sd > 0 else 0.0


def _distribucion(dias: dict, cual: str) -> dict:
    """La distribución horaria de un extremo, con su tasa base."""
    conteo = {h: 0 for h in range(HORAS)}
    for velas in dias.values():
        if cual == "minimo":
            h = min(velas, key=lambda f: float(f["minimo"]))["h"]
        else:
            h = max(velas, key=lambda f: float(f["maximo"]))["h"]
        conteo[h] += 1

    total = len(dias)
    if total == 0:
        return {}
    top = max(conteo, key=conteo.get)
    return {
        "hora_mas_frecuente": top,
        "concentracion_pct": round(conteo[top] / total * 100, 2),
        "veces_el_azar": round((conteo[top] / total) / (1 / HORAS), 2),
        "z": round(_z(conteo[top], total), 2),
        "por_hora": {
            str(h): {
                "casos": conteo[h],
                "pct": round(conteo[h] / total * 100, 2),
                "veces_el_azar": round((conteo[h] / total) / (1 / HORAS), 2),
                "z": round(_z(conteo[h], total), 2),
            } for h in range(HORAS)
        },
        "dias": total,
        "casos_por_hora": round(total / HORAS, 1),
        "poder_suficiente": total / HORAS >= CASOS_MINIMOS,
    }


async def _giros(contexto, meses=12, **_):
    """
    Dónde se producen los giros del día: el máximo y el mínimo.

    En tres poblaciones, porque la global mezcla dos lógicas opuestas.
    """
    dias = await _dias(contexto["pool"], meses)
    if not dias:
        return {"valor": None, "dias": 0}

    grupos = {"global": dias, "alcista": {}, "bajista": {}}
    for d, velas in dias.items():
        grupos[_clasificar(velas)][d] = velas

    resultado = {
        g: {"minimo": _distribucion(ds, "minimo"),
            "maximo": _distribucion(ds, "maximo")}
        for g, ds in grupos.items() if ds
    }

    glob = resultado.get("global", {}).get("minimo", {})
    return {
        # El escalar es la hora más frecuente del mínimo global: es lo
        # ordenable. Todo lo demás va en la estructura.
        "valor": float(glob.get("hora_mas_frecuente", 0)) if glob else None,
        "poblaciones": resultado,
        "dias": len(dias),
        "alcistas": len(grupos["alcista"]),
        "bajistas": len(grupos["bajista"]),
        "tasa_base_pct": round(TASA_BASE, 2),
        "meses_pedidos": meses,
        "_fuente_hasta": date.fromisoformat(max(dias)),
    }


def _calidad(dias: dict) -> dict:
    """
    Para cada hora: qué tan lejos del extremo del día está su cierre.

    · comprar a la hora H → distancia al MÍNIMO del día, en %. Cero sería
      comprar exactamente en el piso.
    · vender a la hora H → distancia al MÁXIMO, en %.

    Se promedia sobre todos los días de la población. NO condiciona por nada
    que solo se sepa al final: la distancia se mide igual en un día que sube
    que en uno que baja.
    """
    compra = {h: [] for h in range(HORAS)}
    venta = {h: [] for h in range(HORAS)}

    for velas in dias.values():
        bajo = min(float(f["minimo"]) for f in velas)
        alto = max(float(f["maximo"]) for f in velas)
        for f in velas:
            c = float(f["cierre"])
            if bajo > 0:
                compra[f["h"]].append((c / bajo - 1) * 100)
            if alto > 0:
                venta[f["h"]].append((1 - c / alto) * 100)

    def _resumir(d):
        out = {}
        for h, vals in d.items():
            if not vals:
                continue
            vals_ord = sorted(vals)
            out[str(h)] = {
                "media_pct": round(sum(vals) / len(vals), 3),
                "mediana_pct": round(vals_ord[len(vals_ord) // 2], 3),
                "casos": len(vals),
            }
        return out

    rc, rv = _resumir(compra), _resumir(venta)
    if not rc or not rv:
        return {}

    mejor_c = min(rc, key=lambda h: rc[h]["media_pct"])
    peor_c = max(rc, key=lambda h: rc[h]["media_pct"])
    mejor_v = min(rv, key=lambda h: rv[h]["media_pct"])
    peor_v = max(rv, key=lambda h: rv[h]["media_pct"])

    return {
        "comprar": {
            "por_hora": rc,
            "mejor_hora": int(mejor_c),
            "peor_hora": int(peor_c),
            # LA CIFRA QUE DECIDE SI SIRVE: si esta diferencia no supera el
            # costo de operar, la ventaja no existe por más consistente que sea.
            "ventaja_pct": round(rc[peor_c]["media_pct"] - rc[mejor_c]["media_pct"], 3),
        },
        "vender": {
            "por_hora": rv,
            "mejor_hora": int(mejor_v),
            "peor_hora": int(peor_v),
            "ventaja_pct": round(rv[peor_v]["media_pct"] - rv[mejor_v]["media_pct"], 3),
        },
    }


async def _calidad_horaria(contexto, meses=12, **_):
    dias = await _dias(contexto["pool"], meses)
    if not dias:
        return {"valor": None, "dias": 0}

    grupos = {"global": dias, "alcista": {}, "bajista": {}}
    for d, velas in dias.items():
        grupos[_clasificar(velas)][d] = velas

    resultado = {g: _calidad(ds) for g, ds in grupos.items() if ds}
    glob = resultado.get("global", {})

    return {
        # El escalar es la ventaja de comprar en la mejor hora contra la peor:
        # es lo que decide si esto sirve para algo.
        "valor": glob.get("comprar", {}).get("ventaja_pct"),
        "poblaciones": resultado,
        "dias": len(dias),
        "alcistas": len(grupos["alcista"]),
        "bajistas": len(grupos["bajista"]),
        "meses_pedidos": meses,
        "_fuente_hasta": date.fromisoformat(max(dias)),
    }


async def _recorrido_oculto(contexto, meses=12, **_):
    """
    Cuánto se mueve el precio adentro del día contra lo que muestra el cierre.

    Un día puede cerrar plano habiéndose movido 8 % adentro. Se mide como el
    recorrido intradía —la suma de los rangos horarios— dividido por el rango
    de la vela diaria.
    """
    dias = await _dias(contexto["pool"], meses)
    if not dias:
        return {"valor": None, "dias": 0}

    ratios = []
    for velas in dias.values():
        intra = sum((float(f["maximo"]) - float(f["minimo"])) / float(f["minimo"])
                    for f in velas if float(f["minimo"]) > 0) * 100
        alto = max(float(f["maximo"]) for f in velas)
        bajo = min(float(f["minimo"]) for f in velas)
        if bajo <= 0:
            continue
        rango = (alto - bajo) / bajo * 100
        if rango > 0:
            ratios.append(intra / rango)

    if not ratios:
        return {"valor": None, "dias": len(dias)}

    ratios.sort()
    n = len(ratios)
    return {
        "valor": round(ratios[n // 2], 3),
        "percentil_25": round(ratios[n // 4], 3),
        "percentil_75": round(ratios[3 * n // 4], 3),
        "minimo": round(ratios[0], 3),
        "maximo": round(ratios[-1], 3),
        "dias": n,
        "meses_pedidos": meses,
        "_fuente_hasta": date.fromisoformat(max(dias)),
    }


# ══ Las declaraciones ════════════════════════════════════════════════════════

_MEZCLA = (
    "la distribución GLOBAL mezcla dos poblaciones con lógica opuesta: medido "
    "sobre 729 días, en días alcistas el mínimo cae en la hora 0 el 28,8 % de "
    "las veces y en bajistas el 0,8 %. Leer solo el global es leer un promedio "
    "que no describe a ninguna de las dos"
)

_ARITMETICA = (
    "en un día que sube, el mínimo TIENE que estar antes de que suba: eso es "
    "aritmética, no un horario favorable. Verificado: cuando el mínimo cae en "
    "la hora 0 está a -0,24 % de la apertura, contra -1,42 % cuando cae en otra "
    "hora — la mayoría de las veces significa que el precio nunca bajó de donde "
    "abrió"
)

_MIRAR_TODAS = (
    "mirar las 24 horas y quedarse con la mayor infla las coincidencias: alguna "
    "va a destacar por azar. El z reportado NO corrige eso"
)


def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="btc_giros_horarios", objeto=Objeto.MERCADO, funcion=_giros,
        alcance=Alcance.INDIVIDUAL, parametros={"meses": MESES},
        descripcion="En qué hora UTC se producen los giros del día — el máximo "
                    "y el mínimo — en global, alcistas y bajistas",
        propiedad=Propiedad(unidad="hora UTC", direccion=Direccion.NEUTRA,
                            minimo=0, maximo=23, comparable=False,
                            por_que_no_comparable="es una distribución de 24 "
                            "categorías en tres poblaciones; el escalar es solo "
                            "la moda del mínimo global"),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la distribución horaria del máximo y del mínimo diarios sobre "
                 "días UTC completos, separada en global, alcistas y bajistas, "
                 "con la tasa base de 4,17 % por hora",
            infiere="que una hora muy por encima de su tasa base describe un "
                    "momento donde ese extremo tiende a formarse. NO infiere "
                    "que vaya a seguir así",
            no_sabe=f"{_ARITMETICA}. Además, {_MEZCLA}. Y {_MIRAR_TODAS}. Sobre "
                    f"todo: saber que un día fue alcista solo se sabe cuando "
                    f"TERMINÓ, así que esta distribución describe el pasado y no "
                    f"da una regla para operar hoy",
            fuente="binance:BTC/USDT, velas horarias",
            metodo="solo días con las 24 horas. El máximo y el mínimo del día "
                   "SON sus giros, por definición")))

    registro.registrar(Simple(
        nombre="btc_calidad_horaria", objeto=Objeto.MERCADO,
        funcion=_calidad_horaria, alcance=Alcance.INDIVIDUAL,
        parametros={"meses": MESES},
        descripcion="Qué tan cerca del extremo del día quedaría comprando o "
                    "vendiendo a cada hora",
        propiedad=Propiedad(unidad="% de ventaja", direccion=Direccion.MAS_ES_MEJOR,
                            minimo=0, maximo=20),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="para cada hora, la distancia media entre su cierre y el mínimo "
                 "del día (comprar) o el máximo (vender), sobre todos los días "
                 "de cada población",
            infiere="que la hora con menor distancia media ofreció "
                    "históricamente mejores entradas. NO infiere que vaya a "
                    "ofrecerlas mañana",
            no_sabe="LA VENTAJA TIENE QUE SUPERAR EL COSTO: si la diferencia "
                    "entre la mejor y la peor hora es 0,3 % y el spread es "
                    "0,4 %, no existe ventaja por más consistente que sea el "
                    "patrón. Se reporta `ventaja_pct` para poder compararla. "
                    "Y es un PROMEDIO: no dice nada sobre un día puntual",
            fuente="binance:BTC/USDT, velas horarias",
            metodo="se usa el CIERRE de cada vela horaria como precio de "
                   "referencia: es el precio que efectivamente se observa "
                   "cuando la hora terminó. No condiciona por nada que solo se "
                   "sepa al final del día")))

    registro.registrar(Simple(
        nombre="btc_recorrido_oculto", objeto=Objeto.MERCADO,
        funcion=_recorrido_oculto, alcance=Alcance.INDIVIDUAL,
        parametros={"meses": MESES},
        descripcion="Cuánto se mueve BTC adentro del día contra lo que muestra "
                    "la vela diaria",
        propiedad=Propiedad(unidad="ratio", direccion=Direccion.CONTEXTUAL,
                            minimo=1, maximo=20),
        vigencia=Vigencia(evento="cierre_vela_diaria"),
        epistemico=Epistemico(
            mide="la mediana de (recorrido intradía / rango de la vela diaria)",
            infiere="que un valor alto describe días donde el precio entra y "
                    "sale varias veces de su rango, en vez de recorrerlo una vez",
            no_sabe="no dice si ese recorrido es CAPTURABLE: no descuenta "
                    "spread ni deslizamiento, y recorrer tres veces el rango en "
                    "24 horas no significa que se pudiera operar cada tramo. "
                    "Tampoco dice CUÁNDO dentro del día ocurrió",
            fuente="binance:BTC/USDT, velas horarias",
            metodo="suma de rangos horarios dividida por el rango del día")))

    logger.info("[capacidades] btc intradía: giros horarios, calidad por hora, "
                "recorrido oculto")
