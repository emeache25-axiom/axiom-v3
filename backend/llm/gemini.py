"""
AXIOM v3 — Cliente de Gemini (el LLM del copiloto).
════════════════════════════════════════════════════════════════════════════════
El copiloto usa el LLM para DOS cosas y ninguna más: clasificar la intención de
un mensaje y redactar la respuesta final. El LLM nunca ve datasets crudos ni
decide qué capacidad ejecutar — eso lo hace el código. Esta es la razón por la
que el copiloto de skills funciona donde el multi-agente falló.

POR QUÉ UN CLIENTE APARTE Y NO UNA FUENTE MÁS (fuentes.yaml):
  Las fuentes de fuentes.yaml devuelven datos que se mapean al vocabulario
  (precio, dominancia…). El LLM no: manda un prompt, recibe texto generado. No
  es un dato mapeable, es un servicio de generación. Forzarlo en ClienteFuentes
  —cuyo `pedir` está hecho para JSON de datos— sería una abstracción equivocada.
  Pero se sigue el MISMO estilo: httpx async centralizado, key en .env por
  nombre, límites y reintentos explícitos.

POR QUÉ REST Y NO EL SDK:
  El SDK google-genai es una dependencia pesada que cambia seguido y abstrae el
  rate limit, el timeout y el modelo exacto. Con httpx —que ya está en el
  proyecto— se controla todo eso y no se agrega dependencia. Mismo criterio con
  el que se eligió no depender de ccxt en producción.
"""
from __future__ import annotations

import os
import json as _json
import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Los modelos, EN ORDEN DE PREFERENCIA. El cliente prueba el primero; si Google
# lo retiró (404) o está saturado (503 tras reintentos), pasa al siguiente.
#
# POR QUÉ UNA CADENA Y NO UN MODELO FIJO:
#   Un nombre concreto (gemini-3.6-flash) es estable pero CADUCA —Google retira
#   versiones, y ese día da 404, como gemini-2.0-flash ya lo hace—. Un alias
#   (gemini-flash-latest) no caduca pero SATURA —da 503 más seguido—. Ningún
#   valor único sirve. La cadena da lo mejor de ambos: un concreto estable
#   primero, el alias como red de seguridad detrás.
#
#   Cuando Google saque el próximo flash, se agrega a la lista en el .env —un
#   dato, no código—. El sistema no se muere esperando que alguien edite código.
_DEFECTO = "gemini-3.6-flash,gemini-flash-latest"
MODELOS = [m.strip() for m in
           os.environ.get("GEMINI_MODELOS", _DEFECTO).split(",") if m.strip()]

# La key vive en el .env, nunca acá. Se lee por nombre, igual que las fuentes.
CLAVE_EN = "GEMINI_API_KEY"

_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Límites, declarados y conservadores. El free tier de Flash ronda 15 RPM / 1M
# TPM, pero el número exacto se MIDE cuando se lo use, no se supone. Estos
# valores dejan margen y se ajustan con datos.
TIMEOUT_S = 60.0
REINTENTOS = 3
ESPERA_BASE_S = 2.0
ESPERA_MAXIMA_S = 60.0


class GeminiError(Exception):
    pass


class _ModeloNoDisponible(Exception):
    """
    Interno: un modelo concreto no sirve ahora (retirado o saturado). Es la
    señal para que completar() pase al siguiente de la cadena. No sale del
    módulo —afuera sólo se ve GeminiError si TODA la cadena falla—.
    """
    pass


class Gemini:
    """
    Cliente del LLM. Se instancia una vez y se comparte (mantiene el cliente
    HTTP). Mismo ciclo de vida que ClienteFuentes: abrir() / cerrar().
    """

    def __init__(self, modelos: list[str] | None = None):
        # Lista en orden de preferencia. `modelo_actual` recuerda cuál funcionó
        # último, para no empezar desde el principio en cada llamada una vez que
        # uno demostró andar.
        self.modelos = list(modelos) if modelos else list(MODELOS)
        self.modelo_actual = self.modelos[0] if self.modelos else None
        self._clave = os.environ.get(CLAVE_EN)
        self._http: httpx.AsyncClient | None = None

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
        """Si hay key. El copiloto puede consultarlo para degradar con gracia."""
        return bool(self._clave)

    # ── Lo único que hace peticiones al LLM ──────────────────────────────────
    async def completar(self, prompt: str, *, system: str | None = None,
                        json: bool = False, max_tokens: int = 1024,
                        temperatura: float = 0.4) -> str:
        """
        Manda un prompt, devuelve el texto generado.

        `system`  — instrucción de sistema (la disciplina epistémica del copiloto
                    va acá, separada del mensaje del usuario).
        `json`    — pide a Gemini que devuelva JSON válido (responseMimeType).

        Recorre la CADENA de modelos: prueba el preferido y, si Google lo retiró
        (404) o quedó saturado (503 tras reintentos), pasa al siguiente. Dentro
        de cada modelo reintenta ante 429/5xx respetando retry-after. Otros 4xx
        (un 400 por prompt inválido) se propagan sin fallback: no es culpa del
        modelo, probar otro daría el mismo error.
        """
        if not self._clave:
            raise GeminiError(
                f"no hay clave de Gemini: definí {CLAVE_EN} en el .env")
        if not self.modelos:
            raise GeminiError("no hay modelos declarados (GEMINI_MODELOS)")
        if self._http is None:
            await self.abrir()

        # Ordena la cadena empezando por el que funcionó último, sin perder los
        # demás como respaldo.
        cadena = ([self.modelo_actual] +
                  [m for m in self.modelos if m != self.modelo_actual]
                  ) if self.modelo_actual else list(self.modelos)

        errores: list[str] = []
        for modelo in cadena:
            try:
                texto = await self._completar_en(
                    modelo, prompt, system, json, max_tokens, temperatura)
            except _ModeloNoDisponible as e:
                # 404 o 503 agotado: este modelo no sirve ahora, probar el
                # siguiente. Se avisa para que se pueda actualizar la lista.
                errores.append(f"{modelo}: {e}")
                logger.warning("[gemini] '%s' no disponible, pruebo el "
                               "siguiente de la cadena", modelo)
                continue
            # Funcionó: recordar este modelo para las próximas llamadas.
            if self.modelo_actual != modelo:
                logger.info("[gemini] usando '%s'", modelo)
                self.modelo_actual = modelo
            return texto

        raise GeminiError(
            "ningún modelo de la cadena respondió. "
            "Actualizá GEMINI_MODELOS en el .env. Detalle: "
            + " | ".join(errores))

    async def _completar_en(self, modelo: str, prompt: str,
                            system: str | None, json: bool,
                            max_tokens: int, temperatura: float) -> str:
        """
        Un intento contra UN modelo, con sus reintentos por 429/5xx.

        Lanza _ModeloNoDisponible si el modelo no sirve (404, o 503 agotado) —la
        señal para que completar() pase al siguiente de la cadena—. Otros 4xx se
        propagan como GeminiError (no es problema del modelo).
        """
        url = f"{_BASE}/models/{modelo}:generateContent"
        cuerpo: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperatura,
            },
        }
        if system:
            cuerpo["systemInstruction"] = {"parts": [{"text": system}]}
        if json:
            cuerpo["generationConfig"]["responseMimeType"] = "application/json"

        espera = ESPERA_BASE_S
        ultimo = None
        for intento in range(1, REINTENTOS + 1):
            try:
                r = await self._http.post(
                    url, params={"key": self._clave}, json=cuerpo)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                ultimo = f"error de red: {e}"
                logger.warning("[gemini] %s %s (intento %d/%d)",
                               modelo, ultimo, intento, REINTENTOS)
            else:
                if r.status_code == 200:
                    return self._extraer_texto(r.json())
                if r.status_code == 404:
                    # Modelo retirado: no reintentar, saltar al siguiente ya.
                    raise _ModeloNoDisponible(f"HTTP 404 (retirado)")
                if r.status_code == 429 or r.status_code >= 500:
                    ra = r.headers.get("retry-after")
                    if ra and ra.isdigit():
                        espera = min(float(ra), ESPERA_MAXIMA_S)
                    ultimo = f"HTTP {r.status_code}: {r.text[:150]}"
                    logger.warning("[gemini] %s %s (intento %d/%d)",
                                   modelo, ultimo, intento, REINTENTOS)
                else:
                    # 400 y otros 4xx: culpa del pedido, no del modelo.
                    raise GeminiError(f"HTTP {r.status_code}: {r.text[:300]}")

            if intento < REINTENTOS:
                await asyncio.sleep(espera)
                espera = min(espera * 2, ESPERA_MAXIMA_S)

        # Agotó los reintentos por saturación: este modelo no sirve ahora.
        raise _ModeloNoDisponible(f"agotó {REINTENTOS} intentos ({ultimo})")

    async def completar_json(self, prompt: str, *, system: str | None = None,
                             max_tokens: int = 1024) -> Any:
        """
        Como completar(json=True) pero además parsea. Devuelve el objeto Python.
        Si el modelo devolvió algo que no es JSON válido, GeminiError —no un
        parse silencioso que rompe después.
        """
        texto = await self.completar(prompt, system=system, json=True,
                                     max_tokens=max_tokens, temperatura=0.1)
        try:
            return _json.loads(texto)
        except _json.JSONDecodeError as e:
            raise GeminiError(
                f"Gemini debía devolver JSON y no lo hizo: {e}. "
                f"Devolvió: {texto[:300]}")

    # ── Interno ───────────────────────────────────────────────────────────
    @staticmethod
    def _extraer_texto(respuesta: dict) -> str:
        """
        Saca el texto de la respuesta de Gemini. La estructura es
        candidates[0].content.parts[*].text. Se declara explícito el caso de que
        no venga —un bloqueo por seguridad o una respuesta vacía— en vez de
        reventar con un KeyError opaco.
        """
        candidatos = respuesta.get("candidates")
        if not candidatos:
            motivo = respuesta.get("promptFeedback", {}).get("blockReason")
            raise GeminiError(
                f"Gemini no devolvió candidatos"
                + (f" (bloqueado: {motivo})" if motivo else ""))
        partes = candidatos[0].get("content", {}).get("parts", [])
        texto = "".join(p.get("text", "") for p in partes)
        if not texto.strip():
            raise GeminiError("Gemini devolvió una respuesta vacía")
        return texto
