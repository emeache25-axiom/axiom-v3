"""
AXIOM v3 — Configuración.
════════════════════════════════════════════════════════════════════════════════
Lee los YAML de `config/`, los valida, y construye las fuentes.

POR QUÉ EN ARCHIVOS Y NO EN CÓDIGO:
  Agregar un exchange o cambiar un límite no debería requerir editar Python ni
  desplegar nada. Y hay una razón concreta y reciente: la API key de CoinGecko
  vivía en `coingecko.py` y **tres veces seguidas** un despliegue la pisó,
  devolviendo el sistema a 4 llamadas por minuto sin que nada avisara.

  La configuración que vive en el código se pierde en cada despliegue.

POR QUÉ ARCHIVOS Y NO BASE DE DATOS:
  Se evaluó. La base tiene una sola ventaja —que un panel la escriba— y un
  archivo también se puede escribir desde un panel. A cambio, los archivos:
    · versionan en git, así un cambio de configuración queda en el historial
      junto al código que lo consume
    · se revisan en un diff antes de aplicarse
    · admiten COMENTARIOS, y toda la disciplina de AXIOM es declarar el porqué

  La configuración de fuentes cambia dos veces por año. Guardar en base algo
  que se toca tan poco, y que además se quiere poder revisar, es más máquina de
  la que hace falta.

LAS CLAVES NO ESTÁN ACÁ:
  El YAML declara QUÉ VARIABLE DE ENTORNO tiene cada clave; el valor vive en el
  `.env`. Así el archivo se versiona sin filtrar nada y un panel puede
  configurar una fuente sin ver el secreto.

VALIDACIÓN ASIMÉTRICA, a propósito:
  · al ARRANCAR: estricta. Un YAML inválido impide levantar. Arrancar con una
    configuración a medias es peor que no arrancar: el sistema haría algo
    distinto de lo declarado y nadie se enteraría.
  · al RECARGAR en caliente: tolerante. Si se edita desde el panel y queda mal,
    sigue con la configuración anterior y avisa qué está mal. Perder el
    servicio por un error de tipeo en la UI sería peor que el problema.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from backend.fuentes.cliente import Fuente, Endpoint, Limites

logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_CONFIG = RAIZ / "config"

ARCHIVOS = ("fuentes", "captura", "vigencias")


class ConfigInvalida(Exception):
    """
    La configuración no se puede usar. Trae TODOS los problemas, no el primero.

    Corregir de a un error por intento es innecesariamente lento cuando el
    validador ya los vio a todos.
    """

    def __init__(self, problemas: list[str]):
        self.problemas = problemas
        super().__init__("configuración inválida:\n  - " + "\n  - ".join(problemas))


@dataclass
class Config:
    """La configuración cargada y validada."""
    fuentes: dict[str, Fuente] = field(default_factory=dict)
    captura: dict[str, Any] = field(default_factory=dict)
    vigencias: dict[str, Any] = field(default_factory=dict)
    exchanges: dict[str, dict] = field(default_factory=dict)
    crudo: dict[str, Any] = field(default_factory=dict)
    cargada_de: str = ""
    # {fuente: {endpoint: {campo_fuente: propiedad_axiom}}}
    mapeos: dict[str, dict[str, dict]] = field(default_factory=dict)

    # Qué claves declaradas NO están en el entorno. No impide arrancar —una
    # fuente puede funcionar sin clave, más lento— pero tiene que verse.
    claves_faltantes: list[str] = field(default_factory=list)


def _leer(nombre: str, directorio: Path) -> dict:
    ruta = directorio / f"{nombre}.yaml"
    if not ruta.exists():
        raise ConfigInvalida([f"falta {ruta}"])
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigInvalida([f"{nombre}.yaml no es YAML válido: {e}"]) from e
    if not isinstance(datos, dict):
        raise ConfigInvalida([f"{nombre}.yaml debe ser un diccionario"])
    return datos


def _validar_fuente_rest(nombre: str, d: dict, problemas: list[str]) -> None:
    if not d.get("base_url"):
        problemas.append(f"fuente '{nombre}': falta base_url")
    eps = d.get("endpoints") or {}
    if not eps:
        problemas.append(f"fuente '{nombre}': no declara endpoints")
    for ep_nombre, ep in eps.items():
        if not isinstance(ep, dict) or not ep.get("path"):
            problemas.append(f"fuente '{nombre}.{ep_nombre}': falta path")
        devuelve = (ep or {}).get("devuelve", "objeto")
        if devuelve not in ("objeto", "coleccion"):
            problemas.append(
                f"fuente '{nombre}.{ep_nombre}': `devuelve` debe ser "
                f"'objeto' o 'coleccion', no '{devuelve}'")


def _validar_exchange(nombre: str, d: dict, problemas: list[str]) -> None:
    if not d.get("exchange_id"):
        problemas.append(f"exchange '{nombre}': falta exchange_id")
        return
    # Se verifica contra ccxt: declarar un exchange que no existe tiene que
    # fallar acá y no la primera vez que se lo use.
    try:
        import ccxt
        if d["exchange_id"] not in ccxt.exchanges:
            problemas.append(
                f"exchange '{nombre}': ccxt no conoce '{d['exchange_id']}'. "
                f"Hay {len(ccxt.exchanges)} disponibles.")
    except ImportError:
        problemas.append("ccxt no está instalado y hay exchanges declarados")


def _construir_fuente(nombre: str, d: dict) -> Fuente:
    lim = d.get("limites") or {}
    limites = Limites(
        llamadas_por_minuto=int(lim.get("llamadas_por_minuto", 30)),
        reintentos=int(lim.get("reintentos", 4)),
        respeta_retry_after=bool(lim.get("respeta_retry_after", True)),
        espera_base_s=float(lim.get("espera_base_s", 5)),
        espera_maxima_s=float(lim.get("espera_maxima_s", 120)),
        timeout_s=float(lim.get("timeout_s", 30)),
    )

    headers: dict[str, str] = {}
    var = d.get("clave_en")
    if var:
        valor = os.environ.get(var, "")
        if valor:
            headers = {d.get("clave_header", "x-api-key"): valor}

    endpoints = {
        n: Endpoint(
            path=ep["path"],
            params_fijos=ep.get("params_fijos") or {},
            params_admite=tuple(ep.get("params_admite") or ()),
            devuelve=ep.get("devuelve", "objeto"),
            descripcion=(ep.get("descripcion") or "").strip(),
        )
        for n, ep in (d.get("endpoints") or {}).items()
    }

    return Fuente(
        nombre=nombre,
        base_url=d["base_url"],
        endpoints=endpoints,
        limites=limites,
        headers=headers,
        ofrece=tuple(d.get("ofrece") or ()),
        no_ofrece=tuple(d.get("no_ofrece") or ()),
    )


def cargar(directorio: Path | None = None) -> Config:
    """
    Lee y valida. Lanza `ConfigInvalida` con TODOS los problemas encontrados.
    """
    dir_ = directorio or DIR_CONFIG
    problemas: list[str] = []

    crudo = {n: _leer(n, dir_) for n in ARCHIVOS}

    bloque = crudo["fuentes"].get("fuentes") or {}
    if not bloque:
        problemas.append("fuentes.yaml no declara ninguna fuente")

    fuentes: dict[str, Fuente] = {}
    exchanges: dict[str, dict] = {}
    claves_faltantes: list[str] = []

    for nombre, d in bloque.items():
        if not isinstance(d, dict):
            problemas.append(f"fuente '{nombre}': debe ser un diccionario")
            continue
        tipo = d.get("tipo")
        if tipo == "rest":
            _validar_fuente_rest(nombre, d, problemas)
            var = d.get("clave_en")
            if var and not os.environ.get(var):
                # No impide arrancar: sin clave la fuente funciona, más lento.
                # Pero tiene que verse — v2 estuvo días a 4 llamadas por minuto
                # sin que nadie lo notara.
                claves_faltantes.append(f"{nombre} → ${var}")
        elif tipo == "ccxt":
            _validar_exchange(nombre, d, problemas)
            exchanges[nombre] = d
        else:
            problemas.append(
                f"fuente '{nombre}': tipo '{tipo}' desconocido "
                f"(esperado 'rest' o 'ccxt')")

    # Coherencia entre archivos: la captura no puede pedir algo no declarado.
    universo = crudo["captura"].get("universo") or {}
    fuente_coins = (universo.get("coins") or {}).get("fuente")
    if fuente_coins and fuente_coins not in bloque:
        problemas.append(
            f"captura.yaml usa la fuente '{fuente_coins}', que no está "
            f"declarada en fuentes.yaml")
    for ex in (universo.get("pares") or {}).get("exchanges") or []:
        if ex not in bloque:
            problemas.append(
                f"captura.yaml usa el exchange '{ex}', que no está declarado")

    if problemas:
        raise ConfigInvalida(problemas)

    mapeos: dict[str, dict] = {}
    for nombre, d in bloque.items():
        if d.get("tipo") == "rest":
            fuentes[nombre] = _construir_fuente(nombre, d)
            if d.get("mapeos"):
                mapeos[nombre] = d["mapeos"]

    cfg = Config(
        fuentes=fuentes,
        captura=crudo["captura"],
        vigencias=crudo["vigencias"].get("vigencias") or {},
        exchanges=exchanges,
        crudo=crudo,
        cargada_de=str(dir_),
        claves_faltantes=claves_faltantes,
        mapeos=mapeos,
    )

    logger.info("[config] %d fuente(s) REST · %d exchange(s) · desde %s",
                len(fuentes), len(exchanges), dir_)
    if claves_faltantes:
        logger.warning("[config] SIN CLAVE en el entorno: %s — la fuente va a "
                       "funcionar con límites mucho más bajos",
                       ", ".join(claves_faltantes))
    return cfg


# ══ La configuración vigente ═════════════════════════════════════════════════

_actual: Config | None = None


def actual() -> Config:
    global _actual
    if _actual is None:
        _actual = cargar()
    return _actual


def recargar() -> dict:
    """
    Relee los archivos SIN reiniciar. Tolerante a propósito.

    Si la configuración nueva es inválida, se conserva la anterior y se
    devuelve qué está mal. Perder el servicio por un error de tipeo en el panel
    sería peor que el problema que se quería resolver.
    """
    global _actual
    try:
        nueva = cargar()
    except ConfigInvalida as e:
        logger.error("[config] recarga RECHAZADA: %s", e.problemas)
        return {"aplicada": False, "problemas": e.problemas,
                "nota": "sigue vigente la configuración anterior"}

    _actual = nueva
    logger.info("[config] recargada")
    return {
        "aplicada": True,
        "fuentes": sorted(nueva.fuentes),
        "exchanges": sorted(nueva.exchanges),
        "claves_faltantes": nueva.claves_faltantes,
    }


def resumen() -> dict:
    """Lo que el panel muestra. Nunca incluye claves."""
    c = actual()
    return {
        "cargada_de": c.cargada_de,
        "fuentes": {
            n: {
                "base_url": f.base_url,
                "endpoints": sorted(f.endpoints),
                "ofrece": list(f.ofrece),
                "no_ofrece": list(f.no_ofrece),
                "llamadas_por_minuto": f.limites.llamadas_por_minuto,
                "autenticada": bool(f.headers),
            }
            for n, f in c.fuentes.items()
        },
        "exchanges": {
            n: {"exchange_id": d.get("exchange_id"),
                "operable": d.get("operable", False),
                "spread_desde": d.get("spread_desde")}
            for n, d in c.exchanges.items()
        },
        "captura": c.captura.get("capturas", {}),
        "universo": c.captura.get("universo", {}),
        "vigencias": c.vigencias,
        "mapeos": {f: sorted(m) for f, m in c.mapeos.items()},
        "claves_faltantes": c.claves_faltantes,
    }
