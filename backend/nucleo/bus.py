"""
AXIOM v3 — Bus de eventos.
════════════════════════════════════════════════════════════════════════════════
Quien publica un hecho no sabe quién lo escucha. Quien escucha no sabe quién lo
publicó.

POR QUÉ EXISTE:
  v3 se organiza por EVENTOS, no por reloj. En v2 todos los jobs son cron y
  ninguno dice POR QUÉ ese momento: el sync de velas corre a las 00:30 UTC
  porque a esa hora hay velas nuevas — ya es un job por evento disfrazado de
  cron.

  Declararlo como evento tiene una ventaja concreta: **si el evento no ocurrió,
  no hay nada que recalcular**. Y si ocurre antes, se dispara antes.

POR QUÉ EN MEMORIA, Y HASTA CUÁNDO:
  Hoy todo v3 corre en un proceso. Un bus en memoria es un diccionario de
  callbacks: sin infraestructura, sin broker, sin otra cosa que falle.

  Cuando el motor de estrategias vaya a proceso aparte —y va a ir, porque una
  estrategia declarada por el copiloto no puede tener la posibilidad de colgar
  la aplicación— este bus se reemplaza por Redis o LISTEN/NOTIFY de PostgreSQL.
  **Y nadie más se entera**, porque quien publica no sabe cómo llega.

  Esa es toda la razón de que exista esta capa en vez de llamadas directas.

LO QUE ESTE BUS NO HACE, declarado:
  · No persiste. Un evento publicado mientras el proceso está caído se pierde.
    Para lo que dispara —recalcular algo que igual se va a recalcular— es
    aceptable. Para una señal de estrategia NO lo sería, y por eso las señales
    se registran en base ADEMÁS de publicarse.
  · No garantiza orden entre suscriptores distintos.
  · No reintenta. Un suscriptor que falla no bloquea a los demás ni se
    reintenta solo: se registra el fallo y sigue.

Ver AXIOM_v3_arquitectura.md §7.3
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ══ Los eventos del sistema ══════════════════════════════════════════════════
#
# Son pocos a propósito. Casi todo lo que en v2 corre por reloj cuelga de uno.
# Los cuatro primeros son "llegaron datos nuevos"; el último es "pasó algo" —
# no invalida cálculos, produce un hecho.

CIERRE_VELA_DIARIA   = "cierre_vela_diaria"
CIERRE_VELA_HORARIA  = "cierre_vela_horaria"
REFRESCO_DE_COINS    = "refresco_de_coins"
CAMBIO_DE_UNIVERSO   = "cambio_de_universo"    # alta, baja o cambio de estado
SENAL_DE_ESTRATEGIA  = "senal_de_estrategia"

EVENTOS = (
    CIERRE_VELA_DIARIA,
    CIERRE_VELA_HORARIA,
    REFRESCO_DE_COINS,
    CAMBIO_DE_UNIVERSO,
    SENAL_DE_ESTRATEGIA,
)


class EventoDesconocido(Exception):
    """
    Se intentó publicar o suscribir a un evento que no está declarado.

    Es a propósito: un typo en el nombre de un evento haría que el publicador
    hable solo y el suscriptor espere para siempre, sin que nada falle. Ese es
    exactamente el modo de fallo silencioso que v3 viene a evitar.
    """


@dataclass(frozen=True)
class Evento:
    """Un hecho que ocurrió."""
    tipo: str
    datos: dict[str, Any] = field(default_factory=dict)
    ocurrido_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))
    origen: str = ""          # quién lo publicó, para poder rastrearlo

    def __repr__(self) -> str:
        return f"<Evento {self.tipo} de {self.origen or '?'} {self.datos}>"


Manejador = Callable[[Evento], Awaitable[None] | None]


class Bus:
    """
    Publicar y suscribir, en memoria.

    Los manejadores se ejecutan EN PARALELO y de forma aislada: uno que falla
    no impide que los demás corran. Esa decisión importa — si recalcular una
    métrica falla, la invalidación del caché tiene que ocurrir igual.
    """

    def __init__(self):
        self._suscriptores: dict[str, list[tuple[str, Manejador]]] = defaultdict(list)
        self._publicados: dict[str, int] = defaultdict(int)
        self._fallos: dict[str, int] = defaultdict(int)

    # ── Suscripción ─────────────────────────────────────────────────────────
    def suscribir(self, tipo: str, manejador: Manejador,
                  nombre: str = "") -> None:
        """
        Registra un manejador. `nombre` es para poder decir CUÁL falló: sin él,
        un error en un lambda no dice nada útil.
        """
        if tipo not in EVENTOS:
            raise EventoDesconocido(
                f"evento '{tipo}' no declarado. Declarados: {list(EVENTOS)}")
        etiqueta = nombre or getattr(manejador, "__name__", repr(manejador))
        self._suscriptores[tipo].append((etiqueta, manejador))
        logger.info("[bus] %s ← %s", tipo, etiqueta)

    def suscriptores_de(self, tipo: str) -> list[str]:
        return [n for n, _ in self._suscriptores.get(tipo, [])]

    # ── Publicación ─────────────────────────────────────────────────────────
    async def publicar(self, tipo: str, datos: dict[str, Any] | None = None,
                       origen: str = "") -> dict:
        """
        Publica un hecho y espera a que todos los manejadores terminen.

        Devuelve qué pasó con cada uno. Nadie está obligado a mirarlo, pero
        existe: un evento que se publica y cuyos manejadores fallan en silencio
        sería el mismo problema que el `try/except` de v2.
        """
        if tipo not in EVENTOS:
            raise EventoDesconocido(
                f"evento '{tipo}' no declarado. Declarados: {list(EVENTOS)}")

        evento = Evento(tipo=tipo, datos=datos or {}, origen=origen)
        manejadores = list(self._suscriptores.get(tipo, []))
        self._publicados[tipo] += 1

        if not manejadores:
            # No es un error: un evento sin consumidores es perfectamente
            # válido. `cierre_vela_horaria` no tiene ninguno todavía.
            logger.debug("[bus] %s publicado, sin suscriptores", tipo)
            return {"evento": tipo, "suscriptores": 0, "ok": 0, "fallos": 0}

        async def _correr(etiqueta: str, m: Manejador):
            try:
                r = m(evento)
                if inspect.isawaitable(r):
                    await r
                return etiqueta, None
            except Exception as e:
                # Aislado a propósito: un manejador que falla no puede impedir
                # que los otros corran. Pero el fallo NO se traga — se registra
                # y se devuelve.
                logger.error("[bus] %s → %s FALLÓ: %s", tipo, etiqueta, e,
                             exc_info=True)
                self._fallos[tipo] += 1
                return etiqueta, e

        resultados = await asyncio.gather(
            *[_correr(n, m) for n, m in manejadores])

        fallos = {n: repr(e) for n, e in resultados if e is not None}
        logger.info("[bus] %s → %d suscriptor(es), %d fallo(s)",
                    tipo, len(manejadores), len(fallos))
        return {
            "evento": tipo,
            "suscriptores": len(manejadores),
            "ok": len(manejadores) - len(fallos),
            "fallos": len(fallos),
            "detalle_fallos": fallos or None,
        }

    def publicar_sin_esperar(self, tipo: str,
                             datos: dict[str, Any] | None = None,
                             origen: str = "") -> asyncio.Task:
        """
        Publica sin bloquear a quien publica.

        Para cuando el publicador no debe esperar a los consumidores: una
        captura que termina no tiene por qué esperar a que se recalculen las
        métricas derivadas.
        """
        return asyncio.get_running_loop().create_task(
            self.publicar(tipo, datos, origen))

    # ── Estado ──────────────────────────────────────────────────────────────
    def estado(self) -> dict:
        """Qué eventos existen, quién escucha cada uno y cuántos hubo."""
        return {
            "eventos": {
                tipo: {
                    "suscriptores": self.suscriptores_de(tipo),
                    "publicados": self._publicados.get(tipo, 0),
                    "fallos": self._fallos.get(tipo, 0),
                }
                for tipo in EVENTOS
            }
        }


# Instancia compartida.
bus = Bus()
