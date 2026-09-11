"""
AXIOM v3 — El copiloto de skills.
════════════════════════════════════════════════════════════════════════════════
Portado del experimento de v2, contra el motor de capacidades de v3. Ver el
diseño completo en docs/AXIOM_v3.md §10.

LA IDEA QUE LO HACE FUNCIONAR (y que hundió al multi-agente):
  El CÓDIGO orquesta; el LLM sólo entiende y redacta. El LLM nunca ve datasets
  crudos. Dos llamadas al LLM por turno —clasificar y redactar— y nada más.

EL COPILOTO DESCUBRE LAS CAPACIDADES DEL REGISTRO (no hay mapa hardcodeado):
  El clasificador recibe el CATÁLOGO de capacidades consultables —leído del
  registro, la única fuente de verdad— y elige cuáles responden la pregunta.
  Agregar una capacidad NO requiere tocar el copiloto: si está declarada y es
  consultable, el copiloto la conoce sola.

  Preferencia por COMPUESTAS: si una compuesta declarada (btc_estado, btc_perfil)
  cubre la pregunta, el LLM la usa —eficiente, cacheada, reproducible—. Si no hay
  ninguna que encaje, compone al vuelo las simples que necesite. Las piezas
  internas (dimensiones de una compuesta, consultable=False) no se ofrecen.

LAS CUATRO ETAPAS:
  1. clasificar  (LLM, JSON)  — mensaje + foco + catálogo → capacidades + target
  2. resolver    (código)     — target textual → id concreto (resolver_coin)
  3. ejecutar    (código)     — resuelve las capacidades por el motor EN PARALELO
  4. redactar    (LLM, texto) — material + disciplina epistémica → respuesta
"""
from __future__ import annotations

import json
import asyncio
import logging

from backend.llm.cliente import LLM, LLMError

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
#  CATÁLOGO — leído del registro (reemplaza al _MAPA hardcodeado)
# ════════════════════════════════════════════════════════════════════════════
def _catalogo(motor) -> list[dict]:
    """
    Las capacidades CONSULTABLES del registro. Las internas (consultable=False,
    p. ej. las dimensiones de btc_perfil) no entran.
    """
    cat = []
    for c in motor.registro.listar():
        if not c.get("consultable", True):
            continue
        cat.append({
            "nombre": c["nombre"],
            "objeto": c["objeto"],
            "tipo": c["tipo"],
            "descripcion": c["descripcion"],
        })
    return cat


def _objeto_de(motor, nombre: str):
    try:
        return motor.registro.obtener(nombre).objeto.value
    except Exception:
        return None


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 1 — CLASIFICAR (LLM, JSON)
# ════════════════════════════════════════════════════════════════════════════
_SYS_CLASIFICAR = """\
Sos el clasificador de AXIOM, un asistente de análisis de mercado cripto. Te doy
el mensaje del usuario y el CATÁLOGO de capacidades disponibles (cada una con qué
responde). Tu tarea: elegir qué capacidad(es) responden la pregunta.

Devolvé SOLO un JSON compacto:
  "capacidades": ["nombre1", "nombre2", ...]   // las que responden; [] si ninguna
  "target":      "símbolo o nombre de coin"     // si es sobre una coin, o null

Reglas:
- Elegí las MÍNIMAS capacidades que respondan bien. No sumes de más.
- Si una capacidad COMPUESTA cubre la pregunta, PREFERILA sobre sus piezas
  sueltas. Ej: "¿cómo está bitcoin?" → una sola capacidad de estado, no cinco.
- Para preguntas amplias ("¿cómo está el mercado?") podés elegir varias.
- Si la pregunta es sobre una coin específica (no BTC como mercado), poné su
  símbolo/nombre en "target" y elegí las capacidades de objeto "coin".
- Si el mensaje se refiere a "esta"/"lo"/"la" y hay objeto en foco, usalo de target.
- Si NINGUNA capacidad responde la pregunta, devolvé "capacidades": [].

Devolvé SOLO el JSON, sin texto alrededor."""


async def clasificar(llm: LLM, motor, mensaje: str,
                     foco: dict | None = None) -> dict:
    catalogo = _catalogo(motor)
    lineas = [f'- {c["nombre"]} ({c["objeto"]}, {c["tipo"]}): {c["descripcion"]}'
              for c in catalogo]
    nombres_validos = {c["nombre"] for c in catalogo}

    prompt = ('CATÁLOGO:\n' + "\n".join(lineas) +
              f'\n\nMensaje del usuario: "{mensaje}"')
    if foco:
        prompt += f'\nObjeto en foco: {json.dumps(foco, ensure_ascii=False)}'

    try:
        r = await llm.completar_json(prompt, nivel="rapido",
                                     system=_SYS_CLASIFICAR, max_tokens=300)
    except LLMError as e:
        logger.warning("[copiloto] clasificar falló: %s", e)
        return {"capacidades": [], "target": None, "_error": str(e)}

    elegidas = r.get("capacidades") or []
    validas = [n for n in elegidas if n in nombres_validos]
    if len(validas) != len(elegidas):
        logger.warning("[copiloto] capacidades inventadas, descartadas: %s",
                       set(elegidas) - nombres_validos)
    return {"capacidades": validas, "target": r.get("target")}


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 2 — RESOLVER TARGET (código)
# ════════════════════════════════════════════════════════════════════════════
async def resolver(pool, motor, capacidades, target):
    necesita_coin = any(_objeto_de(motor, n) == "coin" for n in capacidades)
    if not necesita_coin:
        return {"args": {}, "coin": None, "error": None}
    if not target:
        return {"args": {}, "coin": None, "error": "no dijiste de qué coin"}
    from backend.dominio.coin import resolver_coin
    coin = await resolver_coin(pool, target)
    if coin is None:
        return {"args": {}, "coin": None, "error": f"no encontré la coin '{target}'"}
    return {"args": {"coin_id": coin["id"]}, "coin": coin, "error": None}


# ════════════════════════════════════════════════════════════════════════════
#  ETAPA 3 — EJECUTAR (código, en paralelo)
# ════════════════════════════════════════════════════════════════════════════
async def ejecutar(motor, capacidades, args):
    async def _una(nombre):
        try:
            a = args if _objeto_de(motor, nombre) == "coin" else {}
            r = await motor.resolver(nombre, a)
            # La presentación (cómo dibujar) viaja con el material: el frontend
            # renderiza por tipo+campos sin saber de capacidades concretas.
            cap = motor.registro.obtener(nombre)
            pres = cap.presentacion
            return {"capacidad": nombre, "valor": r.valor,
                    "no_sabe": r.no_sabe, "fuente_hasta": _fh(r.fuente_hasta),
                    "presentacion": {"tipo": pres.tipo, "campos": pres.campos},
                    "titulo": cap.descripcion,
                    "ok": True}
        except Exception as e:
            logger.warning("[copiloto] %s falló: %s", nombre, e)
            return {"capacidad": nombre, "error": str(e), "ok": False}
    return await asyncio.gather(*(_una(n) for n in capacidades))


def _para_redactor(material):
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
Sos AXIOM, un instrumento de análisis de mercado cripto para un trader
profesional. Redactá una respuesta clara y precisa en español rioplatense
(usás "vos"), con el registro de un buen analista: directo, sobrio, seguro de lo
que sabe y honesto sobre lo que no.

REGISTRO (importante):
- Profesional, no acartonado. Nada de muletillas casuales: sin "che", "la posta",
  "al toque", "tirame", "posta". Tampoco jerga de chatbot ni signos de
  exclamación ni entusiasmo impostado.
- Escribí como un analista que le habla a un colega que sabe: sin explicar de más.
- Extensión: 3 a 6 frases. Prosa fluida, sin listas.

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

CUANDO NO HAY DATOS (el mensaje no corresponde a ninguna capacidad, o falta un
dato): explicá con precisión y sobriedad qué podés responder —estado del mercado
y de BTC, funding y opciones, dominancia, sentimiento, on-chain, correlación con
tradicionales, flujo de exchanges, e info e historia de una coin— y pedí una
consulta concreta. Mismo registro profesional: sin jovialidad, sin disculpas
exageradas, sin muletillas.
"""


async def redactar(llm, mensaje, material, contexto=None):
    payload = {"mensaje_del_usuario": mensaje, "datos_medidos": _para_redactor(material)}
    if contexto:
        payload["contexto"] = contexto
    prompt = json.dumps(payload, ensure_ascii=False)
    return await llm.completar(prompt, nivel="rapido",
                               system=_SYS_REDACTAR, max_tokens=1200)


# ════════════════════════════════════════════════════════════════════════════
#  ORQUESTADOR
# ════════════════════════════════════════════════════════════════════════════
async def responder(llm, motor, pool, mensaje, foco=None):
    clas = await clasificar(llm, motor, mensaje, foco)
    capacidades, target = clas["capacidades"], clas.get("target")

    if not capacidades:
        ctx = {"nota": "el mensaje no corresponde a ninguna capacidad disponible"}
        if clas.get("_error"):
            ctx = {"problema": "el asistente no está disponible ahora; reintentá"}
        texto = await redactar(llm, mensaje, [], contexto=ctx)
        return {"texto": texto, "capacidades": [], "target": target,
                "material": [], "widgets": []}

    res = await resolver(pool, motor, capacidades, target)
    if res["error"]:
        texto = await redactar(llm, mensaje, [], contexto={"problema": res["error"]})
        return {"texto": texto, "capacidades": capacidades, "target": target,
                "material": [], "widgets": []}

    material = await ejecutar(motor, capacidades, res["args"])
    ctx = {"coin": res["coin"]["nombre"]} if res.get("coin") else None
    texto = await redactar(llm, mensaje, material, contexto=ctx)

    widgets = [m["capacidad"] for m in material if m.get("ok")]
    return {"texto": texto, "capacidades": capacidades, "target": target,
            "material": material, "widgets": widgets}
