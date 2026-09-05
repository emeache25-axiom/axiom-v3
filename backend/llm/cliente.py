"""
AXIOM v3 — Cliente de LLM unificado (el LLM del copiloto).
════════════════════════════════════════════════════════════════════════════════
UN cliente que habla formato OpenAI-compatible —el estándar que entienden Gemini
(su endpoint /openai), Groq, OpenRouter y casi todos—. Los proveedores y los
modelos son CONFIGURACIÓN, no código.

POR QUÉ ASÍ (la lección de v2, recuperada):
  v2 ya había concluido que la solución no es "elegir el modelo perfecto" sino
  DESACOPLARSE DEL PROVEEDOR. Un modelo se satura (429), se cae (503) o Google lo
  retira (404); cualquier proveedor puede fallar. La robustez no viene de un
  modelo, viene de poder saltar a otro —incluso de otro proveedor— sin reescribir
  nada. Como todos hablan OpenAI-compat, agregar un proveedor es una línea de
  config.

DOS DIMENSIONES QUE RESUELVE:
  1. NIVEL DE TAREA. Clasificar necesita poco; crear una estrategia necesita
     razonamiento estructurado. El copiloto pide un NIVEL ("rapido"/"capaz"), no
     un modelo. Cada nivel es una cadena de modelos en orden de preferencia.
  2. DISPONIBILIDAD / PROVEEDOR. La cadena de un nivel puede cruzar proveedores:
     si gemini:... cae, salta a groq:... transparentemente. Nunca sin copiloto.

CONFIGURACIÓN (en el .env):
  LLM_PROVEEDORES=gemini,groq
  LLM_GEMINI_URL=https://generativelanguage.googleapis.com/v1beta/openai
  LLM_GEMINI_KEY_EN=GEMINI_API_KEY
  LLM_GROQ_URL=https://api.groq.com/openai/v1
  LLM_GROQ_KEY_EN=GROQ_API_KEY
  LLM_RAPIDO=gemini:gemini-flash-lite-latest,groq:openai/gpt-oss-20b
  LLM_CAPAZ=groq:openai/gpt-oss-120b,gemini:gemini-3.7-flash

  Un modelo se escribe "proveedor:modelo". La cadena de un nivel se recorre en
  orden; ante 404/429/503 agotado, salta al siguiente —sea del proveedor que sea—.
"""
from __future__ import annotations

import os
import json as _json
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── Defaults (se pueden sobrescribir por entorno) ────────────────────────────
_URLS_DEFECTO = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
}
_KEYS_DEFECTO = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}
_NIVELES_DEFECTO = {
    "rapido": "gemini:gemini-flash-lite-latest,groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash-lite",
    "capaz":  "groq:openai/gpt-oss-120b,gemini:gemini-3.7-flash,gemini:gemini-flash-latest",
}

TIMEOUT_S = 60.0
REINTENTOS = 3
ESPERA_BASE_S = 2.0
ESPERA_MAXIMA_S = 60.0


class LLMError(Exception):
    pass


class _ModeloNoDisponible(Exception):
    """Interno: un modelo concreto no sirve ahora (retirado o saturado). Señal
    para pasar al siguiente de la cadena. No sale del módulo."""
    pass


class _Proveedor:
    """Un endpoint OpenAI-compatible: su URL y su key."""
    def __init__(self, nombre: str, url: str, key: str | None):
        self.nombre = nombre
        self.url = url.rstrip("/")
        self.key = key

    @property
    def disponible(self) -> bool:
        return bool(self.key)


class LLM:
    """
    Cliente único. Se instancia una vez y se comparte (mantiene el HTTP).
    Mismo ciclo de vida que ClienteFuentes: abrir() / cerrar().
    """

    def __init__(self):
        # Proveedores declarados.
        nombres = [p.strip() for p in
                   os.environ.get("LLM_PROVEEDORES", "gemini,groq").split(",")
                   if p.strip()]
        self.proveedores: dict[str, _Proveedor] = {}
        for n in nombres:
            url = os.environ.get(f"LLM_{n.upper()}_URL", _URLS_DEFECTO.get(n, ""))
            key_en = os.environ.get(f"LLM_{n.upper()}_KEY_EN",
                                    _KEYS_DEFECTO.get(n, ""))
            key = os.environ.get(key_en) if key_en else None
            if url:
                self.proveedores[n] = _Proveedor(n, url, key)

        # Niveles: cada uno una cadena de "proveedor:modelo".
        self.niveles: dict[str, list[tuple[str, str]]] = {}
        for nivel, defecto in _NIVELES_DEFECTO.items():
            crudo = os.environ.get(f"LLM_{nivel.upper()}", defecto)
            self.niveles[nivel] = self._parsear_cadena(crudo)

        # Recuerda el modelo que funcionó por nivel, para no reintentar desde
        # el principio.
        self._ultimo_ok: dict[str, tuple[str, str]] = {}
        self._http: httpx.AsyncClient | None = None

    @staticmethod
    def _parsear_cadena(crudo: str) -> list[tuple[str, str]]:
        """'gemini:x,groq:y' → [('gemini','x'), ('groq','y')]."""
        pares = []
        for item in crudo.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" not in item:
                logger.warning("[llm] modelo sin proveedor, ignorado: %r", item)
                continue
            prov, modelo = item.split(":", 1)
            pares.append((prov.strip(), modelo.strip()))
        return pares

    # ── Ciclo de vida ───────────────────────────────────────────────────────
    async def abrir(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=TIMEOUT_S)

    async def cerrar(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self):
        await self.abrir()
        return self

    async def __aexit__(self, *_):
        await self.cerrar()

    @property
    def disponible(self) -> bool:
        """Si hay al menos un proveedor con key."""
        return any(p.disponible for p in self.proveedores.values())

    # ── Lo único que se llama desde afuera ──────────────────────────────────
    async def completar(self, prompt: str, *, nivel: str = "rapido",
                        system: str | None = None, json: bool = False,
                        max_tokens: int = 1024, temperatura: float = 0.4) -> str:
        """
        Manda un prompt, devuelve el texto. `nivel` elige la cadena de modelos:
        "rapido" para clasificar/redactar, "capaz" para crear (estrategias).

        Recorre la cadena del nivel: prueba el preferido y, si cae (404/429/503
        agotado), salta al siguiente —aunque sea de otro proveedor—. Un 400 (mala
        petición) se propaga sin fallback: probar otro modelo daría lo mismo.
        """
        if not self.disponible:
            raise LLMError("ningún proveedor de LLM tiene clave configurada")
        if self._http is None:
            await self.abrir()

        cadena = self.niveles.get(nivel)
        if not cadena:
            raise LLMError(f"nivel '{nivel}' no declarado. "
                           f"Hay: {sorted(self.niveles)}")

        # Empezar por el que funcionó último en este nivel.
        ult = self._ultimo_ok.get(nivel)
        if ult and ult in cadena:
            orden = [ult] + [x for x in cadena if x != ult]
        else:
            orden = list(cadena)

        errores = []
        for prov_nombre, modelo in orden:
            prov = self.proveedores.get(prov_nombre)
            if prov is None or not prov.disponible:
                errores.append(f"{prov_nombre}:{modelo}: proveedor sin clave/URL")
                continue
            try:
                texto = await self._completar_en(
                    prov, modelo, prompt, system, json, max_tokens, temperatura)
            except _ModeloNoDisponible as e:
                errores.append(f"{prov_nombre}:{modelo}: {e}")
                logger.warning("[llm] %s:%s no disponible, sigo con la cadena",
                               prov_nombre, modelo)
                continue
            if self._ultimo_ok.get(nivel) != (prov_nombre, modelo):
                logger.info("[llm] nivel '%s' usando %s:%s",
                            nivel, prov_nombre, modelo)
                self._ultimo_ok[nivel] = (prov_nombre, modelo)
            return texto

        raise LLMError(
            f"nivel '{nivel}': ningún modelo respondió. "
            f"Revisá las cadenas en el .env. Detalle: " + " | ".join(errores))

    async def completar_json(self, prompt: str, *, nivel: str = "rapido",
                             system: str | None = None,
                             max_tokens: int = 1024) -> Any:
        """Como completar(json=True) pero parsea. LLMError si no vino JSON."""
        texto = await self.completar(prompt, nivel=nivel, system=system,
                                     json=True, max_tokens=max_tokens,
                                     temperatura=0.1)
        try:
            return _json.loads(texto)
        except _json.JSONDecodeError as e:
            raise LLMError(f"el modelo debía devolver JSON y no lo hizo: {e}. "
                           f"Devolvió: {texto[:300]}")

    # ── Un intento contra un modelo concreto ────────────────────────────────
    async def _completar_en(self, prov: _Proveedor, modelo: str, prompt: str,
                            system: str | None, json: bool,
                            max_tokens: int, temperatura: float) -> str:
        """
        Una request OpenAI-compatible con reintentos por 429/5xx. Lanza
        _ModeloNoDisponible si el modelo no sirve (404, o 5xx/429 agotado).
        """
        url = f"{prov.url}/chat/completions"
        mensajes = []
        if system:
            mensajes.append({"role": "system", "content": system})
        mensajes.append({"role": "user", "content": prompt})
        cuerpo: dict[str, Any] = {
            "model": modelo,
            "messages": mensajes,
            "max_tokens": max_tokens,
            "temperature": temperatura,
        }
        if json:
            cuerpo["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {prov.key}",
                   "Content-Type": "application/json"}

        espera = ESPERA_BASE_S
        ultimo = None
        for intento in range(1, REINTENTOS + 1):
            try:
                r = await self._http.post(url, headers=headers, json=cuerpo)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                ultimo = f"error de red: {e}"
                logger.warning("[llm] %s:%s %s (intento %d/%d)",
                               prov.nombre, modelo, ultimo, intento, REINTENTOS)
            else:
                if r.status_code == 200:
                    return self._extraer(r.json())
                if r.status_code == 404:
                    raise _ModeloNoDisponible("HTTP 404 (modelo inexistente)")
                if r.status_code == 429 or r.status_code >= 500:
                    ra = r.headers.get("retry-after")
                    if ra and ra.isdigit():
                        espera = min(float(ra), ESPERA_MAXIMA_S)
                    ultimo = f"HTTP {r.status_code}: {r.text[:150]}"
                    logger.warning("[llm] %s:%s %s (intento %d/%d)",
                                   prov.nombre, modelo, ultimo, intento, REINTENTOS)
                else:
                    raise LLMError(f"{prov.nombre}:{modelo} HTTP "
                                   f"{r.status_code}: {r.text[:300]}")

            if intento < REINTENTOS:
                await asyncio.sleep(espera)
                espera = min(espera * 2, ESPERA_MAXIMA_S)

        raise _ModeloNoDisponible(f"agotó {REINTENTOS} intentos ({ultimo})")

    @staticmethod
    def _extraer(respuesta: dict) -> str:
        """
        Saca el texto de una respuesta OpenAI-compatible:
        choices[0].message.content. Declara explícito el caso vacío en vez de
        reventar con un KeyError opaco.
        """
        choices = respuesta.get("choices")
        if not choices:
            raise LLMError("respuesta sin choices")
        msg = choices[0].get("message", {})
        texto = msg.get("content") or ""
        if not texto.strip():
            # Modelos con 'thinking' pueden gastar todo el presupuesto de tokens
            # razonando y no dejar content. Se declara, no se oculta.
            raise LLMError("el modelo devolvió content vacío "
                           "(¿max_tokens muy bajo para un modelo con thinking?)")
        return texto
