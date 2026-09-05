"""
AXIOM v3 — El copiloto de skills.
════════════════════════════════════════════════════════════════════════════════
Portado del experimento de v2, contra el motor de capacidades de v3. Ver el
diseño completo en docs/AXIOM_v3.md §10.

LA IDEA QUE LO HACE FUNCIONAR (y que hundió al multi-agente):
  El CÓDIGO orquesta; el LLM sólo entiende y redacta. El LLM nunca ve datasets
  crudos ni decide qué capacidad ejecutar. Dos llamadas al LLM por turno —
  clasificar y redactar— y nada más.

LAS CUATRO ETAPAS:
  1. clasificar  (LLM, JSON)  — mensaje + foco → intención + target
  2. resolver    (código)     — target textual → id concreto (resolver_coin)
  3. ejecutar    (código)     — intención → capacidades, resueltas por el motor
                                EN PARALELO. Junta valor + epistémica.
  4. redactar    (LLM, texto) — material + disciplina epistémica → respuesta

SOBRE destila/presentacion:
  El diseño (§5.4) separa el carril de razonamiento del de presentación. En v3
  todavía NO está implementado: las capacidades devuelven un `valor` compacto
  (10-15 campos, ya pensado para leerse) que sirve de destilado de hecho. Cuando
  una capacidad necesite carriles distintos, se implementa. Hoy no hace falta.
"""
from __future__ import annotations

import json
import asyncio
import logging

from backend.llm.cliente import LLM, LLMError

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
#  MAPA DE INTENCIONES → CAPACIDADES
# ════════════════════════════════════════════════════════════════════════════
# Qué capacidades resuelve cada intención. El código mapea; el LLM sólo eligió
# la intención. Agregar una intención es agregar una entrada acá —y enseñarle al
# clasificador que existe (INTENCIONES abajo)—.
#
# `objeto`: cómo se arma el arg de la capacidad.
#   "mercado" → sin target (btc_estado, dominancia son del mercado, no de una coin)
#   "coin"    → el target resuelto va como {"coin_id": ...}
_MAPA = {
    "estado_btc": {
        "capacidades": ["btc_estado"],
        "objeto": "mercado",
    },
    "posicionamiento_btc": {
        "capacidades": ["btc_funding", "btc_opciones"],
        "objeto": "mercado",
    },
    "dominancia": {
        "capacidades": ["mercado_dominancia"],
        "objeto": "mercado",
    },
    "info_coin": {
        "capacidades": ["coin_estado", "coin_mercados"],
        "objeto": "coin",
    },
    "historia_coin": {
        "capacidades": ["coin_historia"],
        "objeto": "coin",
    },
}

# Lo que el clasificador puede elegir. "otro" es la salida honesta cuando no
# encaja en ninguna — el copiloto lo dice, no inventa.
INTENCIONES = list(_MAPA) + ["otro"]


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 1 — CLASIFICAR (LLM, JSON)
# ════════════════════════════════════════════════════════════════════════════
_SYS_CLASIFICAR = """\
Sos el clasificador de un asistente de análisis de mercado cripto. Tu ÚNICA
tarea es leer el mensaje del usuario y devolver un JSON compacto con:

  "intencion": una de [{intenciones}]
  "target":    el símbolo o nombre de la coin si la hay, o null

Reglas:
- estado_btc: cómo está / qué hace Bitcoin en general.
- posicionamiento_btc: funding, opciones, apalancamiento, max-pain de BTC.
- dominancia: dominancia de BTC, reparto del mercado, BTC vs alts.
- info_coin: qué es / precio / dónde se opera una coin concreta (que no sea BTC).
- historia_coin: cómo viene una coin en el tiempo, su evolución.
- otro: cualquier cosa que no encaje.

Si el mensaje se refiere a "esta"/"lo"/"la" y hay un objeto en foco, usá ese
objeto como target.

Devolvé SOLO el JSON, sin texto alrededor."""


async def clasificar(llm: LLM, mensaje: str, foco: dict | None = None) -> dict:
    """
    Mensaje (+ foco) → {intencion, target}. Una llamada LLM, salida JSON.

    El foco resuelve referencias: "¿cómo lo ves?" con foco {par: ROSE/BTC} se
    clasifica como el análisis de ese objeto.
    """
    sys = _SYS_CLASIFICAR.format(intenciones=", ".join(INTENCIONES))
    prompt = f'Mensaje: "{mensaje}"'
    if foco:
        prompt += f"\nObjeto en foco: {json.dumps(foco, ensure_ascii=False)}"

    try:
        r = await llm.completar_json(prompt, nivel="rapido", system=sys, max_tokens=300)
    except LLMError as e:
        logger.warning("[copiloto] clasificar falló: %s", e)
        return {"intencion": "otro", "target": None, "_error": str(e)}

    intencion = r.get("intencion")
    if intencion not in INTENCIONES:
        # El LLM inventó una intención fuera del catálogo: tratar como "otro"
        # en vez de romper. Se declara para no ocultarlo.
        logger.warning("[copiloto] intención desconocida: %r", intencion)
        return {"intencion": "otro", "target": r.get("target"),
                "_intencion_cruda": intencion}
    return {"intencion": intencion, "target": r.get("target")}


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 2 — RESOLVER TARGET (código)
# ════════════════════════════════════════════════════════════════════════════
async def resolver(pool, intencion: str, target: str | None) -> dict:
    """
    Target textual → args para las capacidades.

    Para intenciones de coin, resuelve el texto ("eth") a coin_id ("ethereum")
    usando resolver_coin —la fuente de verdad—. Para intenciones de mercado, no
    hay target que resolver.

    Devuelve {"args": {...}, "coin": {...}|None, "error": str|None}.
    """
    spec = _MAPA.get(intencion)
    if not spec or spec["objeto"] == "mercado":
        return {"args": {}, "coin": None, "error": None}

    # objeto == "coin": necesita resolver el target.
    if not target:
        return {"args": {}, "coin": None,
                "error": "no dijiste de qué coin"}

    from backend.dominio.coin import resolver_coin
    coin = await resolver_coin(pool, target)
    if coin is None:
        return {"args": {}, "coin": None,
                "error": f"no encontré la coin '{target}'"}
    return {"args": {"coin_id": coin["id"]}, "coin": coin, "error": None}


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 3 — EJECUTAR + JUNTAR (código, en paralelo)
# ════════════════════════════════════════════════════════════════════════════
async def ejecutar(motor, intencion: str, args: dict) -> list[dict]:
    """
    Resuelve las capacidades de la intención EN PARALELO por el motor.

    Cada capacidad devuelve DOS cosas separadas (el destila/presentacion del
    diseño §5.4, que acá aparece en su primer uso real):
      · `valor`    — los números. Van al redactor Y al frontend.
      · `no_sabe`  — los límites textuales. Van SÓLO al frontend (widget), NO al
                     redactor: pasarle diez párrafos de límites al LLM infla el
                     prompt y lo hace truncar. El redactor respeta los límites
                     por su system, no por recibir cada uno transcripto.

    Si una falla, se registra su error en vez de tumbar todo.
    """
    spec = _MAPA.get(intencion)
    if not spec:
        return []

    async def _una(nombre: str) -> dict:
        try:
            r = await motor.resolver(nombre, args)
            return {"capacidad": nombre, "valor": r.valor,
                    "no_sabe": r.no_sabe, "fuente_hasta": _fh(r.fuente_hasta),
                    "ok": True}
        except Exception as e:
            logger.warning("[copiloto] %s falló: %s", nombre, e)
            return {"capacidad": nombre, "error": str(e), "ok": False}

    return await asyncio.gather(*(_una(n) for n in spec["capacidades"]))


def _para_redactor(material: list[dict]) -> list[dict]:
    """
    Adelgaza el material para el LLM: sólo capacidad + valor (los números), sin
    los `no_sabe` textuales. Lo que el redactor necesita para redactar es el
    DATO; los límites los respeta por instrucción, no por recibir párrafos.
    Esto evita el truncamiento y da respuestas concisas, no volcados de datos.
    """
    fino = []
    for m in material:
        if m.get("ok"):
            fino.append({"capacidad": m["capacidad"], "valor": m["valor"]})
        else:
            fino.append({"capacidad": m["capacidad"],
                         "no_disponible": m.get("error", "no se pudo calcular")})
    return fino


def _fh(x):
    return x.isoformat() if hasattr(x, "isoformat") else (str(x) if x else None)


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 4 — REDACTAR (LLM, texto)
# ════════════════════════════════════════════════════════════════════════════
_SYS_REDACTAR = """\
Sos AXIOM, un asistente de análisis de mercado cripto. Te paso el mensaje del
usuario y los DATOS MEDIDOS por el sistema (en JSON). Redactá una respuesta
BREVE y clara en español rioplatense — como un colega trader que va al grano.

Extensión: 3 a 6 frases. Prosa fluida, sin listas.

CÓMO PRESENTAR LOS NÚMEROS (clave):
- No recites valores crudos: TRADUCILOS a su lectura. El percentil ya te dice la
  lectura —traducila a palabras y mostrá el número entre paréntesis—.
    · percentil alto (>70): "en la zona alta de su historia"
    · percentil medio (30-70): "en valores normales / promedio"
    · percentil bajo (<30): "en la zona baja de su historia"
  Ej: en vez de "volatilidad 46.99, percentil 34.3" → "la volatilidad está más
  bien baja (percentil 34)".
- FUNDING: no lo dejes crudo. El SIGNO dice quién paga: positivo = los largos
  pagan a los cortos (presión compradora apalancada); negativo = al revés. El
  PERCENTIL dice qué tan extremo es contra su historia (percentil 0 = en el piso,
  100 = en el techo). Ej: "el funding está apenas negativo y en el piso de su
  historia (percentil 0): los cortos pagan, sin presión compradora apalancada".
  NO infieras qué va a pasar con el precio a partir del funding.
- MAX-PAIN: traducí la distancia al spot. Ej: "el max-pain de opciones está en
  75.000, un 8% por debajo del precio actual". No digas que el precio "va a ir"
  ahí —es dónde se concentra la exposición, no un pronóstico—.
- Elegí los números que importan para la pregunta; no los vuelques todos.
- Redondeá: "≈2.700 millones", no "2693665406311.65".

Reglas de honestidad (obligatorias):
- Usá SOLO los datos que te paso. No inventes ni completes lo que falte.
- NO PREDIGAS el precio ni infieras causas ("subió porque..."). Describí el
  estado, no hacia dónde va ni por qué llegó ahí. AXIOM analiza, no pronostica.
- La lectura de un percentil es "dónde está en su historia", NO "está caro/barato"
  ni "va a subir/bajar".
- Si un dato figura como "no_disponible", mencionalo al pasar.
- Nada de disclaimers ni de "como modelo de IA".
"""


async def redactar(llm: LLM, mensaje: str, material: list[dict],
                   contexto: dict | None = None) -> str:
    """
    Material medido (ADELGAZADO: sólo valores, ver _para_redactor) + disciplina
    epistémica → respuesta breve. Una llamada.
    """
    payload = {
        "mensaje_del_usuario": mensaje,
        "datos_medidos": _para_redactor(material),
    }
    if contexto:
        payload["contexto"] = contexto
    prompt = json.dumps(payload, ensure_ascii=False)
    return await llm.completar(prompt, nivel="rapido", system=_SYS_REDACTAR, max_tokens=1200)


# ════════════════════════════════════════════════════════════════════════════
#  ORQUESTADOR — une las cuatro etapas
# ════════════════════════════════════════════════════════════════════════════
async def responder(llm: LLM, motor, pool, mensaje: str,
                    foco: dict | None = None) -> dict:
    """
    El flujo completo: clasificar → resolver → ejecutar → redactar.

    Devuelve {texto, intencion, target, material, widgets} — el frontend usa
    `texto` para el hilo y `widgets` (por ahora los nombres de las capacidades
    que respondieron) para montar las vistas cuando exista el catálogo (§10.5).
    """
    # 1. Clasificar
    clas = await clasificar(llm, mensaje, foco)
    intencion, target = clas["intencion"], clas.get("target")

    if intencion == "otro":
        texto = await redactar(llm, mensaje, [], contexto={
            "nota": "el mensaje no corresponde a ninguna capacidad disponible; "
                    "explicá brevemente qué SÍ podés responder: estado de BTC, "
                    "su funding/opciones, dominancia del mercado, e info e "
                    "historia de una coin"})
        return {"texto": texto, "intencion": intencion, "target": target,
                "material": [], "widgets": []}

    # 2. Resolver target
    res = await resolver(pool, intencion, target)
    if res["error"]:
        texto = await redactar(llm, mensaje, [], contexto={
            "problema": res["error"]})
        return {"texto": texto, "intencion": intencion, "target": target,
                "material": [], "widgets": []}

    # 3. Ejecutar capacidades (paralelo)
    material = await ejecutar(motor, intencion, res["args"])

    # 4. Redactar
    ctx = {"coin": res["coin"]["nombre"]} if res.get("coin") else None
    texto = await redactar(llm, mensaje, material, contexto=ctx)

    widgets = [m["capacidad"] for m in material if m.get("ok")]
    return {"texto": texto, "intencion": intencion, "target": target,
            "material": material, "widgets": widgets}
