"""
AXIOM v3 — Cliente de fuentes REST.
════════════════════════════════════════════════════════════════════════════════
UNA sola implementación de "pedirle algo a una API externa". El rate limit, los
reintentos, el timeout y el manejo de errores se declaran en la fuente y se
aplican a todo lo que la use.

POR QUÉ EXISTE — medido en v2 el 18/08/2026:

  Cinco archivos hablaban con CoinGecko y TRES lo hacían sin pasar por ningún
  adaptador: `coins_sync`, `categorias_fill` y `coin_info_service`. Cada uno con
  su propio manejo de rate limit, escrito por separado.

  Consecuencia concreta: cuando se arregló el bug del 429 en `coins_sync` —un
  `continue` que saltaba a la página siguiente y perdía 250 coins por corrida—
  ese arreglo NO protegió a los otros dos. Siguen con el problema.

  Y había DOS carpetas de adaptadores: `backend/data/` (viva) y
  `backend/exchanges/` (819 líneas, CERO importadores).

LA REGLA: si escribís `httpx.get()` fuera de este módulo, algo está mal.

Ver AXIOM_v3_declaraciones.md §1
"""
from __future__ import annotations

import json
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FuenteError(Exception):
    """Fallo al obtener datos de una fuente externa."""


class RespuestaInesperada(FuenteError):
    """
    La fuente respondió, pero no con lo que su declaración dice.

    Es un error distinto de "no respondió": significa que la API cambió, o que
    la declaración está mal. En v2 esto no existía — si CoinGecko renombraba un
    campo, se leía como None y nadie se enteraba.
    """


@dataclass(frozen=True)
class Limites:
    """
    Cómo tratar a una fuente para no hacerla enojar.

    `respeta_retry_after` importa: CoinGecko manda el header `retry-after` y
    obedecerlo es más rápido y más cortés que esperar un fijo. En v2 se esperaba
    60 s a ciegas.
    """
    llamadas_por_minuto: int = 30
    reintentos: int = 4
    respeta_retry_after: bool = True
    espera_base_s: float = 5.0
    espera_maxima_s: float = 120.0
    timeout_s: float = 30.0


@dataclass(frozen=True)
class Endpoint:
    """
    Un punto de acceso de la fuente.

    `params_admite` es una lista blanca a propósito: un parámetro mal escrito
    que la API ignora en silencio es un modo de falla real —le pasó a v2 con un
    `dias` que nunca llegaba y devolvía siempre la ventana por defecto—. Acá
    falla al pedirlo, no seis meses después.
    """
    path: str
    params_fijos: dict[str, Any] = field(default_factory=dict)
    params_admite: tuple[str, ...] = ()
    devuelve: str = "objeto"          # objeto | coleccion
    descripcion: str = ""


@dataclass(frozen=True)
class Fuente:
    """De dónde vienen los datos. Se declara una vez."""
    nombre: str
    base_url: str
    endpoints: dict[str, Endpoint]
    limites: Limites = field(default_factory=Limites)
    headers: dict[str, str] = field(default_factory=dict)
    # Qué ofrece y qué no. Se declara para que quien pida algo que la fuente no
    # tiene reciba un error claro, en vez de un fallo silencioso.
    ofrece: tuple[str, ...] = ()
    no_ofrece: tuple[str, ...] = ()


@dataclass
class Respuesta:
    """
    Lo que devuelve una llamada.

    Trae el CRUDO además de los datos: si mañana hace falta un campo que hoy no
    se mapea, está acá — y también en lo que se haya persistido. En v2 un campo
    no mapeado era irrecuperable hacia atrás.
    """
    datos: Any
    fuente: str
    endpoint: str
    pedido_at: datetime
    intentos: int = 1
    desde_cache: bool = False

    @property
    def es_coleccion(self) -> bool:
        return isinstance(self.datos, list)


class _Regulador:
    """
    Limita el ritmo de salida hacia una fuente.

    Ventana deslizante simple: recuerda las marcas de tiempo del último minuto y
    espera si ya se alcanzó el tope. Es más preciso que un `sleep` fijo entre
    llamadas, que desperdicia tiempo cuando las respuestas tardan.
    """

    def __init__(self, por_minuto: int):
        self._por_minuto = max(1, por_minuto)
        self._marcas: list[float] = []
        self._lock = asyncio.Lock()

    async def esperar_turno(self) -> None:
        async with self._lock:
            ahora = asyncio.get_running_loop().time()
            self._marcas = [t for t in self._marcas if ahora - t < 60.0]
            if len(self._marcas) >= self._por_minuto:
                espera = 60.0 - (ahora - self._marcas[0]) + 0.05
                if espera > 0:
                    logger.debug("[fuentes] regulando: espero %.1fs", espera)
                    await asyncio.sleep(espera)
                ahora = asyncio.get_running_loop().time()
                self._marcas = [t for t in self._marcas if ahora - t < 60.0]
            self._marcas.append(ahora)


class ClienteFuentes:
    """
    Ejecuta las declaraciones de fuente.

    Se instancia una vez y se comparte: mantiene el cliente HTTP y el regulador
    de cada fuente. Dos instancias regularían por separado y se pisarían.
    """

    def __init__(self, fuentes: dict[str, Fuente] | None = None):
        self._fuentes: dict[str, Fuente] = dict(fuentes or {})
        self._reguladores: dict[str, _Regulador] = {}
        self._http: httpx.AsyncClient | None = None

    # ── Registro ────────────────────────────────────────────────────────────
    def registrar(self, fuente: Fuente) -> None:
        if fuente.nombre in self._fuentes:
            raise ValueError(f"fuente duplicada: {fuente.nombre}")
        self._fuentes[fuente.nombre] = fuente
        logger.info("[fuentes] registrada: %s (%d endpoints)",
                    fuente.nombre, len(fuente.endpoints))

    def obtener_fuente(self, nombre: str) -> Fuente:
        f = self._fuentes.get(nombre)
        if f is None:
            raise FuenteError(
                f"fuente '{nombre}' no declarada. "
                f"Declaradas: {sorted(self._fuentes)}")
        return f

    def ofrece(self, fuente: str, que: str) -> bool:
        """
        Si la fuente ofrece cierta capacidad. Se declara, no se descubre
        fallando: preguntarle el libro a quien no lo da tiene que dar un error
        claro antes de la llamada, no un vacío después.
        """
        f = self.obtener_fuente(fuente)
        if que in f.no_ofrece:
            return False
        return not f.ofrece or que in f.ofrece

    # ── Ciclo de vida ───────────────────────────────────────────────────────
    async def abrir(self) -> None:
        if self._http is None:
            self._http = httpx.AsyncClient(follow_redirects=True)

    async def cerrar(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def __aenter__(self):
        await self.abrir()
        return self

    async def __aexit__(self, *_):
        await self.cerrar()

    # ── Lo único que hace peticiones en todo AXIOM ──────────────────────────
    async def pedir(self, fuente: str, endpoint: str,
                    **params: Any) -> Respuesta:
        """
        Pide un endpoint aplicando lo que la fuente declaró.

        Reintenta ante 429 y 5xx; los 4xx que no sean 429 se propagan sin
        reintentar, porque reintentar un 404 es perder el tiempo.
        """
        f = self.obtener_fuente(fuente)
        ep = f.endpoints.get(endpoint)
        if ep is None:
            raise FuenteError(
                f"endpoint '{endpoint}' no declarado en '{fuente}'. "
                f"Declarados: {sorted(f.endpoints)}")

        # Lista blanca: un parámetro no declarado es un error acá, no una
        # sorpresa dentro de seis meses.
        sobrantes = set(params) - set(ep.params_admite)
        if sobrantes:
            raise FuenteError(
                f"{fuente}.{endpoint} no admite {sorted(sobrantes)}. "
                f"Admite: {sorted(ep.params_admite)}")

        if self._http is None:
            await self.abrir()

        regulador = self._reguladores.setdefault(
            fuente, _Regulador(f.limites.llamadas_por_minuto))

        url = f.base_url.rstrip("/") + "/" + ep.path.lstrip("/")
        consulta = {**ep.params_fijos,
                    **{k: v for k, v in params.items() if v is not None}}

        ultimo: str = ""
        for intento in range(1, f.limites.reintentos + 1):
            await regulador.esperar_turno()
            pedido_at = datetime.now(timezone.utc)
            try:
                r = await self._http.get(
                    url, params=consulta, headers=f.headers,
                    timeout=f.limites.timeout_s)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                ultimo = f"{type(e).__name__}: {e}"
                espera = self._espera(f, intento, None)
                logger.warning("[fuentes] %s.%s red (%d/%d): %s — espero %.2fs",
                               fuente, endpoint, intento, f.limites.reintentos,
                               ultimo, espera)
                await asyncio.sleep(espera)
                continue

            if r.status_code == 200:
                try:
                    datos = r.json()
                except json.JSONDecodeError as e:
                    raise RespuestaInesperada(
                        f"{fuente}.{endpoint} devolvió algo que no es JSON: {e}"
                    ) from e

                # La declaración dice qué forma tiene la respuesta. Si no
                # coincide, la API cambió o la declaración está mal — y en
                # cualquiera de los dos casos hay que enterarse ahora.
                if ep.devuelve == "coleccion" and not isinstance(datos, list):
                    raise RespuestaInesperada(
                        f"{fuente}.{endpoint} declara devolver una colección "
                        f"y devolvió {type(datos).__name__}")

                if intento > 1:
                    logger.info("[fuentes] %s.%s recuperado en el intento %d",
                                fuente, endpoint, intento)
                return Respuesta(datos=datos, fuente=fuente, endpoint=endpoint,
                                 pedido_at=pedido_at, intentos=intento)

            if r.status_code == 429 or r.status_code >= 500:
                # Se reintenta LA MISMA petición. En v2, el 429 hacía `continue`
                # sobre el bucle de páginas y saltaba a la SIGUIENTE, perdiendo
                # 250 coins por corrida durante semanas.
                ra = r.headers.get("retry-after") if f.limites.respeta_retry_after else None
                espera = self._espera(f, intento, ra)
                ultimo = f"HTTP {r.status_code}"
                logger.warning(
                    "[fuentes] %s.%s %s (%d/%d) — espero %.2fs y REINTENTO "
                    "la misma petición",
                    fuente, endpoint, ultimo, intento, f.limites.reintentos,
                    espera)
                await asyncio.sleep(espera)
                continue

            # 4xx que no es 429: reintentar no va a cambiar nada.
            raise FuenteError(
                f"{fuente}.{endpoint} HTTP {r.status_code}: {r.text[:200]}")

        raise FuenteError(
            f"{fuente}.{endpoint} agotó {f.limites.reintentos} intentos. "
            f"Último: {ultimo}")

    @staticmethod
    def _espera(f: Fuente, intento: int, retry_after: str | None) -> float:
        """
        Cuánto esperar antes del próximo intento.

        Si la fuente dijo cuánto, se le hace caso —sabe mejor que nosotros—.
        Si no, espera exponencial acotada por `espera_maxima_s`: sin tope, el
        cuarto intento esperaría minutos.
        """
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), f.limites.espera_maxima_s))
            except ValueError:
                pass
        return min(f.limites.espera_base_s * (2 ** (intento - 1)),
                   f.limites.espera_maxima_s)


# Instancia compartida. Se puebla al importar las declaraciones.
cliente = ClienteFuentes()
