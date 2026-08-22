"""
AXIOM v3 — Planificador.
════════════════════════════════════════════════════════════════════════════════
Lo único que este módulo sabe es CUÁNDO. Qué se hace con eso lo deciden los
suscriptores del bus.

LA DISTINCIÓN QUE v2 NO HACÍA:

  En v2 todos los jobs son cron y ninguno dice POR QUÉ ese momento. El sync de
  velas corre a las 00:30 UTC *porque a esa hora hay velas nuevas* — o sea que
  ya era un job por evento, disfrazado de cron.

  Acá se separa:

    · TAREAS PERIÓDICAS — traer datos. "Cada 6 horas pedile los precios a
      CoinGecko". Eso sí es temporal y va acá.

    · EVENTOS — hechos que ocurren. "Cerró el día UTC". El planificador los
      DETECTA y los publica; quién reacciona no es asunto suyo.

  La ventaja concreta: si el evento no ocurrió, no hay nada que recalcular. Y
  quien reacciona no necesita saber a qué hora corre nada.

POR QUÉ APSCHEDULER:
  Hace bien lo único que se le pide: disparar a una hora. Y su sistema de
  listeners es lo que en v2 permitió construir el observador de jobs, que
  encontró un bot muerto hacía dos meses a las pocas horas de existir.

  Lo que NO se le pide es orquestar: para eso está el bus.

Ver AXIOM_v3_arquitectura.md §7.3
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, date

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.nucleo import bus as _bus

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

# Último día UTC visto. Sirve para detectar el cambio de día una sola vez,
# aunque el chequeo corra cada minuto.
_ultimo_dia: date | None = None


# ══ Detección de eventos temporales ══════════════════════════════════════════

async def _detectar_cambio_de_dia() -> None:
    """
    Publica `cierre_vela_diaria` cuando cambia el día UTC.

    Corre cada minuto pero publica UNA sola vez por día: compara contra el
    último día visto en vez de confiar en la hora exacta. Así, si el proceso
    estuvo caído a las 00:00, el evento se publica igual al levantarse — cosa
    que un cron a las 00:00 no haría.
    """
    global _ultimo_dia
    hoy = datetime.now(timezone.utc).date()

    if _ultimo_dia is None:
        # Primer chequeo tras arrancar: se toma nota sin publicar. Publicar acá
        # dispararía el evento en cada reinicio, y un reinicio no es un cierre
        # de vela.
        _ultimo_dia = hoy
        logger.info("[planificador] día UTC en curso: %s", hoy)
        return

    if hoy != _ultimo_dia:
        cerrado = _ultimo_dia
        _ultimo_dia = hoy
        logger.info("[planificador] cerró el día UTC %s", cerrado)
        await _bus.bus.publicar(
            _bus.CIERRE_VELA_DIARIA,
            {"dia_cerrado": str(cerrado), "dia_nuevo": str(hoy)},
            origen="planificador")


# ══ Registro de tareas ═══════════════════════════════════════════════════════

def _envolver(nombre: str, corrutina, *args, **kwargs):
    """
    Envuelve una tarea para que su fallo se PROPAGUE.

    En v2 cada job hacía `try / except / logger.error` y devolvía normalmente:
    APScheduler nunca se enteraba y reportaba "executed successfully" mientras
    el job fallaba en todas sus corridas. El sync de precios estuvo semanas así.

    Acá se loguea Y se relanza: el scheduler tiene que saber que falló.
    """
    async def _tarea():
        try:
            r = await corrutina(*args, **kwargs)
            logger.info("[planificador] %s: %s", nombre, r)
            return r
        except Exception as exc:
            logger.error("[planificador] %s FALLÓ: %s", nombre, exc)
            raise
    _tarea.__name__ = f"tarea_{nombre}"
    return _tarea


def iniciar(tareas: dict) -> AsyncIOScheduler:
    """
    Arranca el planificador.

    `tareas` trae las funciones ya con sus dependencias resueltas (pool,
    cliente): este módulo no las conoce ni tiene por qué.
    """
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    _scheduler = AsyncIOScheduler(timezone="UTC")

    # ── Detección de eventos: cada minuto, publica solo cuando algo cambia ──
    _scheduler.add_job(
        _detectar_cambio_de_dia,
        trigger=IntervalTrigger(minutes=1),
        id="detectar_dia",
        name="Detectar cierre del día UTC",
        max_instances=1,
        coalesce=True,
    )

    # ── Traer datos: esto SÍ es temporal ────────────────────────────────────
    if "refrescar_coins" in tareas:
        _scheduler.add_job(
            _envolver("refresco de coins", tareas["refrescar_coins"]),
            trigger=IntervalTrigger(hours=6),
            id="refrescar_coins",
            name="Refrescar precios y ranking de coins",
            max_instances=1,
            coalesce=True,
            # Un refresco perdido se recupera si el proceso vuelve dentro de la
            # hora; más tarde que eso, conviene esperar al próximo.
            misfire_grace_time=3600,
        )

    if "inventariar_coins" in tareas:
        _scheduler.add_job(
            _envolver("inventario", tareas["inventariar_coins"]),
            # Una vez al día alcanza: las coins nuevas no aparecen cada hora, y
            # es una sola llamada.
            trigger=CronTrigger(hour=1, minute=0),
            id="inventariar_coins",
            name="Inventario completo de la fuente",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=7200,
        )

    _scheduler.start()
    logger.info("[planificador] activo · %d tarea(s) · eventos: %s",
                len(_scheduler.get_jobs()), ", ".join(_bus.EVENTOS))
    return _scheduler


def detener() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[planificador] detenido")


def estado() -> dict:
    if _scheduler is None:
        return {"activo": False}
    return {
        "activo": True,
        "tareas": [
            {"id": j.id, "nombre": j.name,
             "proxima": str(j.next_run_time) if j.next_run_time else None}
            for j in _scheduler.get_jobs()
        ],
    }
