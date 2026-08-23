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


# ══ El cierre del día UTC ════════════════════════════════════════════════════
#
# NO se chequea periódicamente: se PROGRAMA el despertar.
#
# El cierre del día no tiene productor —nadie nos avisa que cambió el día, es
# una propiedad del tiempo, no un hecho de un sistema—. Pero eso no obliga a
# preguntarse a cada rato si ya pasó: se sabe EXACTAMENTE cuándo va a pasar.
#
# Una primera versión chequeaba cada minuto por si el proceso había estado
# caído a medianoche. Eran 1.440 comprobaciones diarias para detectar algo que
# ocurre una vez, y el argumento de que "cada una cuesta cero" es justamente
# cómo se degradan los sistemas: mil cosas ejecutándose por las dudas sí
# cuestan.
#
# El caso del proceso caído se resuelve mejor y aparte: al arrancar se
# verifica si falta alguna foto. Eso consulta la base UNA vez y además es más
# confiable, porque se apoya en lo que efectivamente se guardó y no en una
# variable en memoria que un reinicio borra.


# Hasta qué hora del día siguiente tiene sentido guardar "el cierre de ayer".
# Pasado eso los datos ya derivaron demasiado: guardarlos sería registrar el
# mediodía de hoy con la fecha de ayer. Un HUECO DECLARADO es mejor.
VENTANA_REINTENTO_H = 4


async def _hay_foto(pool, fecha) -> bool:
    async with pool.acquire() as conn:
        return bool(await conn.fetchval(
            "SELECT 1 FROM coin_diaria WHERE fecha = $1 LIMIT 1", fecha))


async def cerrar_el_dia(pool, intento: int = 1) -> dict:
    """
    Publica `cierre_vela_diaria` para el día que acaba de cerrar.

    Retrata el día que CERRÓ, no el que empieza: fotografiar el día nuevo daría
    datos de cinco minutos de antigüedad.

    Idempotente: si la foto de ayer ya existe, no vuelve a publicar. Eso permite
    que el reintento horario lo llame sin miedo.
    """
    from datetime import timedelta
    ayer = datetime.now(timezone.utc).date() - timedelta(days=1)

    if await _hay_foto(pool, ayer):
        return {"dia": str(ayer), "estado": "ya_estaba", "intento": intento}

    logger.info("[planificador] cerró el día UTC %s (intento %d)", ayer, intento)
    r = await _bus.bus.publicar(
        _bus.CIERRE_VELA_DIARIA,
        {"dia_cerrado": str(ayer), "intento": intento},
        origen="planificador")
    return {"dia": str(ayer), "estado": "publicado",
            "intento": intento, "suscriptores": r["suscriptores"],
            "fallos": r["fallos"]}


async def reintentar_cierre(pool) -> dict:
    """
    Verifica cada hora si la foto de ayer llegó a guardarse, y reintenta.

    ES UN CHEQUEO PERIÓDICO, y eso normalmente se evita —el cierre del día se
    programa, no se comprueba—. Acá está justificado y la diferencia importa:

      · verifica algo IRRECUPERABLE. Si la captura de las 00:05 falló porque la
        fuente estaba caída, ese día no existe nunca más. Es lo único del
        sistema que merece insistir.
      · una vez que la foto está, el chequeo es una consulta trivial que
        devuelve "ya estaba" y no hace nada.
      · tiene LÍMITE: pasadas VENTANA_REINTENTO_H se declara el hueco y se deja
        de intentar. Un dato del mediodía guardado como cierre de ayer sería
        peor que la ausencia.
    """
    from datetime import timedelta
    ahora = datetime.now(timezone.utc)
    ayer = ahora.date() - timedelta(days=1)

    if await _hay_foto(pool, ayer):
        return {"dia": str(ayer), "estado": "ya_estaba"}

    if ahora.hour >= VENTANA_REINTENTO_H:
        # Fuera de ventana: se declara el hueco y no se intenta más hoy.
        logger.warning(
            "[planificador] HUECO en %s — pasaron más de %d h del cierre y los "
            "datos actuales ya no representan ese día. No se rellena.",
            ayer, VENTANA_REINTENTO_H)
        return {"dia": str(ayer), "estado": "hueco_declarado",
                "motivo": f"fuera de la ventana de {VENTANA_REINTENTO_H} h"}

    intento = ahora.hour + 1
    logger.warning("[planificador] falta la foto de %s — reintento %d",
                   ayer, intento)
    return await cerrar_el_dia(pool, intento=intento)


async def recuperar_dias_faltantes(pool, dias_atras: int = 7) -> dict:
    """
    Al arrancar: ¿falta alguna foto? Recupera SOLO la del día que acaba de
    cerrar; las anteriores se declaran como huecos.

    Reemplaza al chequeo periódico: una consulta al arrancar en vez de 1.440
    comprobaciones diarias, y además se apoya en lo que efectivamente se
    guardó, no en una variable en memoria que un reinicio borra.

    ═══ POR QUÉ SOLO EL DÍA DE AYER ═══════════════════════════════════════

    `fotografiar()` retrata lo que hay en `coins` AHORA y le pone la fecha que
    se le pida. Para el día que acaba de cerrar eso es correcto: los datos
    actuales SON los de ese cierre.

    Para días anteriores es FABRICAR. Una fila con fecha 2026-08-20 y precios
    del 22 es un dato falso que se ve perfectamente plausible — la peor clase
    de error, porque nada lo delata después.

    Pasó de verdad: la primera versión de esta función publicaba el evento para
    el día faltante más reciente, sin importar cuál fuera, y generó una foto
    del 20 con datos del 22.

    Un HUECO DECLARADO es mejor que un dato inventado. Los días que faltan se
    reportan y quedan visibles; no se rellenan.
    """
    from datetime import timedelta

    hoy = datetime.now(timezone.utc).date()
    ayer = hoy - timedelta(days=1)
    esperados = {hoy - timedelta(days=d) for d in range(1, dias_atras + 1)}

    async with pool.acquire() as conn:
        filas = await conn.fetch(
            "SELECT DISTINCT fecha FROM coin_diaria WHERE fecha >= $1",
            hoy - timedelta(days=dias_atras))
    guardados = {f["fecha"] for f in filas}
    faltantes = sorted(esperados - guardados)

    if not faltantes:
        logger.info("[planificador] sin huecos en los últimos %d días", dias_atras)
        return {"faltantes": [], "recuperado": None}

    huecos = [str(f) for f in faltantes]

    # Solo si falta AYER se puede recuperar: sus datos son los de ahora.
    if ayer in faltantes:
        logger.info("[planificador] falta la foto de ayer (%s) — se recupera", ayer)
        await _bus.bus.publicar(
            _bus.CIERRE_VELA_DIARIA,
            {"dia_cerrado": str(ayer), "recuperacion": True},
            origen="planificador.recuperar")
        huecos_restantes = [h for h in huecos if h != str(ayer)]
    else:
        huecos_restantes = huecos

    if huecos_restantes:
        # NO se rellenan: no hay forma de saber qué valía cada coin ese día.
        # Se declara el hueco para que sea visible en vez de quedar oculto.
        logger.warning(
            "[planificador] HUECOS sin recuperar: %s — no se rellenan porque "
            "la fuente da el estado de HOY, no el de esos días",
            ", ".join(huecos_restantes))

    return {
        "faltantes": huecos,
        "recuperado": str(ayer) if ayer in faltantes else None,
        "huecos_declarados": huecos_restantes,
    }


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
        from backend.nucleo.registro import registro as _reg
        # El registro relanza si falla, así que el scheduler se entera. En v2
        # el try/except devolvía normalmente y APScheduler anotaba
        # "executed successfully" mientras el job fallaba en cada corrida.
        r = await _reg.ejecutar(nombre, "planificador", corrutina, *args, **kwargs)
        logger.info("[planificador] %s: %s", nombre, r)
        return r
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

    # ── El cierre del día: se PROGRAMA, no se chequea ───────────────────────
    # 00:05 UTC y no 00:00: a las cero en punto las fuentes todavía están
    # cerrando sus propias velas.
    _scheduler.add_job(
        _envolver("cierre_del_dia", tareas["cerrar_el_dia"]),
        trigger=CronTrigger(hour=0, minute=5),
        id="cierre_del_dia",
        name="Cierre del día UTC",
        max_instances=1,
        coalesce=True,
        # Si el proceso estuvo caído en ese momento, APScheduler lo dispara al
        # levantarse dentro de las 2 h. Más tarde que eso lo resuelve
        # `recuperar_dias_faltantes`, que mira lo que efectivamente falta.
        misfire_grace_time=7200,
    )

    # ── Red de seguridad de lo IRRECUPERABLE ────────────────────────────────
    # Cada hora, dentro de la ventana, verifica si la foto de ayer llegó a
    # guardarse. Es un chequeo periódico y normalmente se evita — acá está
    # justificado porque si ese dato no se captura, ese día no existe más.
    if "reintentar_cierre" in tareas:
        _scheduler.add_job(
            _envolver("reintentar_cierre", tareas["reintentar_cierre"]),
            trigger=CronTrigger(hour=f"1-{VENTANA_REINTENTO_H}", minute=5),
            id="reintentar_cierre",
            name="Reintento del cierre del día",
            max_instances=1,
            coalesce=True,
        )

    # ── Traer datos: esto SÍ es temporal ────────────────────────────────────
    if "refrescar_coins" in tareas:
        _scheduler.add_job(
            _envolver("refrescar_coins", tareas["refrescar_coins"]),
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
            _envolver("inventariar_coins", tareas["inventariar_coins"]),
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
