"""
AXIOM v3 — Clasificación de fallos.
════════════════════════════════════════════════════════════════════════════════
"Falló" no es accionable. "El servidor no tiene internet" sí lo es, y es
distinto de "la fuente está caída", que a su vez es distinto de "hay un bug
nuestro".

POR QUÉ IMPORTA:
  Las tres cosas producen la misma línea en el registro si nadie las distingue,
  y las tres exigen respuestas opuestas:

    · sin internet        → esperar; reintentar sirve
    · fuente caída        → esperar; reintentar sirve pero puede tardar horas
    · límite de la fuente → esperar EXACTAMENTE lo que dijo; reintentar sirve
    · datos raros         → NO reintentar: va a volver a fallar igual
    · bug nuestro         → NO reintentar: hay que arreglarlo

  Y sobre todo: el monitor puede decirte cuál de las cinco fue, en vez de
  mostrarte una traza.

CUBRE httpx Y ccxt:
  ccxt tiene su propia jerarquía de excepciones y no hereda de las de httpx.
  Se clasifican por nombre para no importar ccxt acá —este módulo no debería
  depender de una biblioteca de exchanges— y porque los nombres de ccxt son
  estables y descriptivos.
"""
from __future__ import annotations

from enum import Enum


class Causa(str, Enum):
    """
    Por qué falló algo. El orden importa: de lo más externo a lo más nuestro.
    """
    SIN_RED = "sin_red"                 # el servidor no llega a internet
    FUENTE_CAIDA = "fuente_caida"       # la fuente no responde o da 5xx
    LIMITE_FUENTE = "limite_fuente"     # rate limit: hay que esperar
    FUENTE_RECHAZA = "fuente_rechaza"   # 4xx: el pedido está mal o no existe
    DATOS_INESPERADOS = "datos_inesperados"   # respondió algo que no es lo declarado
    BASE_DE_DATOS = "base_de_datos"     # PostgreSQL
    NUESTRO = "nuestro"                 # un bug de AXIOM
    DESCONOCIDA = "desconocida"


# Qué hacer con cada causa. Reintentar lo que no va a cambiar es perder tiempo
# y ocultar el problema real.
REINTENTABLE = {
    Causa.SIN_RED: True,
    Causa.FUENTE_CAIDA: True,
    Causa.LIMITE_FUENTE: True,
    Causa.FUENTE_RECHAZA: False,
    Causa.DATOS_INESPERADOS: False,
    Causa.BASE_DE_DATOS: True,     # puede ser un corte momentáneo
    Causa.NUESTRO: False,
    Causa.DESCONOCIDA: True,       # ante la duda, reintentar una vez
}

EXPLICACION = {
    Causa.SIN_RED: "el servidor no pudo salir a internet",
    Causa.FUENTE_CAIDA: "la fuente no respondió o devolvió un error suyo",
    Causa.LIMITE_FUENTE: "la fuente aplicó su límite de llamadas",
    Causa.FUENTE_RECHAZA: "la fuente rechazó el pedido: revisar la declaración",
    Causa.DATOS_INESPERADOS: "la fuente respondió algo distinto de lo declarado — puede haber cambiado su formato",
    Causa.BASE_DE_DATOS: "problema con PostgreSQL",
    Causa.NUESTRO: "error en el código de AXIOM",
    Causa.DESCONOCIDA: "no se pudo clasificar",
}


# ── Por nombre de excepción ──────────────────────────────────────────────────
#
# Se clasifica por NOMBRE y no por tipo para no importar ccxt ni asyncpg acá:
# este módulo no debería depender de las bibliotecas que envuelve. Los nombres
# de ccxt son estables y descriptivos, así que alcanza.

_POR_NOMBRE: dict[str, Causa] = {
    # ── httpx / red ─────────────────────────────────────────────────────────
    "ConnectError":            Causa.SIN_RED,
    "ConnectTimeout":          Causa.SIN_RED,
    "ReadTimeout":             Causa.FUENTE_CAIDA,
    "WriteTimeout":            Causa.SIN_RED,
    "PoolTimeout":             Causa.NUESTRO,
    "TimeoutException":        Causa.FUENTE_CAIDA,
    "NetworkError":            Causa.SIN_RED,
    "TransportError":          Causa.SIN_RED,
    "RemoteProtocolError":     Causa.FUENTE_CAIDA,
    "ProxyError":              Causa.SIN_RED,
    "UnsupportedProtocol":     Causa.NUESTRO,

    # ── DNS y sistema ───────────────────────────────────────────────────────
    "gaierror":                Causa.SIN_RED,
    "ConnectionRefusedError":  Causa.SIN_RED,
    "ConnectionResetError":    Causa.SIN_RED,
    "OSError":                 Causa.SIN_RED,

    # ── ccxt ────────────────────────────────────────────────────────────────
    # Su jerarquía no hereda de httpx, así que va aparte.
    "NetworkError":            Causa.SIN_RED,
    "RequestTimeout":          Causa.FUENTE_CAIDA,
    "ExchangeNotAvailable":    Causa.FUENTE_CAIDA,
    "OnMaintenance":           Causa.FUENTE_CAIDA,
    "DDoSProtection":          Causa.LIMITE_FUENTE,
    "RateLimitExceeded":       Causa.LIMITE_FUENTE,
    "ExchangeError":           Causa.FUENTE_RECHAZA,
    "BadSymbol":               Causa.FUENTE_RECHAZA,
    "BadRequest":              Causa.FUENTE_RECHAZA,
    "AuthenticationError":     Causa.FUENTE_RECHAZA,
    "PermissionDenied":        Causa.FUENTE_RECHAZA,
    "NotSupported":            Causa.FUENTE_RECHAZA,
    "BadResponse":             Causa.DATOS_INESPERADOS,
    "NullResponse":            Causa.DATOS_INESPERADOS,

    # ── AXIOM ───────────────────────────────────────────────────────────────
    "RespuestaInesperada":     Causa.DATOS_INESPERADOS,
    "FuenteError":             Causa.FUENTE_RECHAZA,

    # ── asyncpg ─────────────────────────────────────────────────────────────
    "PostgresError":           Causa.BASE_DE_DATOS,
    "InterfaceError":          Causa.BASE_DE_DATOS,
    "TooManyConnectionsError": Causa.BASE_DE_DATOS,
    "UndefinedColumnError":    Causa.NUESTRO,   # el esquema no coincide: es bug
    "UndefinedTableError":     Causa.NUESTRO,
    "DataError":               Causa.NUESTRO,   # precisión insuficiente, overflow
    "NumericValueOutOfRangeError": Causa.NUESTRO,

    # ── Python ──────────────────────────────────────────────────────────────
    "KeyError":                Causa.NUESTRO,
    "AttributeError":          Causa.NUESTRO,
    "TypeError":               Causa.NUESTRO,
    "ValueError":              Causa.NUESTRO,
    "IndexError":              Causa.NUESTRO,
    "ZeroDivisionError":       Causa.NUESTRO,
}

# Pistas en el mensaje, para cuando el nombre no alcanza. Se miran en orden.
_POR_MENSAJE: tuple[tuple[str, Causa], ...] = (
    ("name or service not known",  Causa.SIN_RED),
    ("temporary failure in name",  Causa.SIN_RED),
    ("network is unreachable",     Causa.SIN_RED),
    ("no route to host",           Causa.SIN_RED),
    ("connection refused",         Causa.SIN_RED),
    ("rate limit",                 Causa.LIMITE_FUENTE),
    ("too many requests",          Causa.LIMITE_FUENTE),
    ("429",                        Causa.LIMITE_FUENTE),
    ("503",                        Causa.FUENTE_CAIDA),
    ("502",                        Causa.FUENTE_CAIDA),
    ("504",                        Causa.FUENTE_CAIDA),
    ("maintenance",                Causa.FUENTE_CAIDA),
)


# Qué causa gana cuando hay varias en la cadena. Lo MÁS EXTERNO gana: si un
# FuenteError fue causado por un ConnectError, lo relevante es que no hay
# internet — el FuenteError es solo cómo lo envolvimos nosotros.
_PRIORIDAD = (
    Causa.SIN_RED,            # la más externa: nada funciona sin esto
    Causa.LIMITE_FUENTE,
    Causa.FUENTE_CAIDA,
    Causa.BASE_DE_DATOS,
    Causa.DATOS_INESPERADOS,
    Causa.FUENTE_RECHAZA,
    Causa.NUESTRO,            # la más interna: solo si nada externo explica
)


def clasificar(exc: BaseException) -> Causa:
    """
    Por qué falló, mirando TODA la cadena de causas.

    Una excepción envuelta esconde la real: un `FuenteError` causado por un
    `ConnectError` es, en los hechos, falta de internet. Clasificar por la
    envoltura daría "la fuente rechazó el pedido" cuando el problema es que el
    servidor no sale a la red — y son respuestas opuestas.

    Por eso se recorre la cadena entera y gana la causa MÁS EXTERNA según
    `_PRIORIDAD`, no la primera que aparece.
    """
    encontradas: list[Causa] = []
    vistos: set[int] = set()
    actual: BaseException | None = exc

    while actual is not None and id(actual) not in vistos:
        vistos.add(id(actual))

        for clase in type(actual).__mro__:
            c = _POR_NOMBRE.get(clase.__name__)
            if c is not None:
                # `OSError` es demasiado genérico para ganarle a una pista
                # concreta del mensaje; se registra igual pero no corta.
                encontradas.append(c)
                break

        msg = str(actual).lower()
        for pista, c in _POR_MENSAJE:
            if pista in msg:
                encontradas.append(c)
                break

        actual = actual.__cause__ or actual.__context__

    if not encontradas:
        return Causa.DESCONOCIDA

    for c in _PRIORIDAD:
        if c in encontradas:
            return c
    return encontradas[0]


def describir(exc: BaseException) -> dict:
    """Lo que el monitor necesita para decir algo útil en vez de una traza."""
    c = clasificar(exc)
    return {
        "causa": c.value,
        "explicacion": EXPLICACION[c],
        "reintentable": REINTENTABLE[c],
        "excepcion": type(exc).__name__,
        "mensaje": str(exc)[:300],
    }
