"""
AXIOM v3 — Monitor.
════════════════════════════════════════════════════════════════════════════════
Responde tres preguntas, y las tres hacen falta:

    QUÉ PASÓ          las ejecuciones terminadas, con su resultado
    QUÉ ESTÁ PASANDO  lo que corre AHORA, y hace cuánto
    QUÉ PASARÁ        lo programado, y qué va a disparar cada cosa

La del medio no existía hasta la migración 003: el registro escribía recién al
terminar, así que una tarea colgada era indistinguible de una que nunca
arrancó.

Y hay una cuarta que es la más valiosa y la más difícil:

    QUÉ DEBÍA PASAR Y NO PASÓ

Eso no es un evento — es la AUSENCIA de uno, y por definición ningún registro
la contiene. Se detecta cruzando lo que debía ejecutarse contra lo que quedó
registrado. Un monitor que solo muestra lo que pasa es lindo; uno que muestra
lo que faltó es útil.

EL EJEMPLO QUE MOTIVÓ ESTO:

    proceso de 00:05 no completó, falló
    en ejecución: proceso de respaldo
    próximo intento de actualización: 01:05
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import asyncpg

logger = logging.getLogger(__name__)


async def _huecos_de_historia(pool, dias: int = 7) -> list[str]:
    """
    Qué días no tienen foto. Es la ausencia más importante del sistema: cada
    hueco es un día que no existe nunca más.
    """
    hoy = datetime.now(timezone.utc).date()
    esperados = {hoy - timedelta(days=d) for d in range(1, dias + 1)}
    async with pool.acquire() as conn:
        filas = await conn.fetch(
            "SELECT DISTINCT fecha FROM coin_diaria WHERE fecha >= $1",
            hoy - timedelta(days=dias))
    return sorted(str(f) for f in (esperados - {f["fecha"] for f in filas}))


async def _colgadas(pool, minutos: int = 30) -> list[dict]:
    """
    Ejecuciones que arrancaron y nunca cerraron.

    Una tarea que lleva media hora "en curso" no está trabajando: se colgó, o
    el proceso murió sin cerrarla. Las dos cosas hay que verlas.
    """
    async with pool.acquire() as conn:
        filas = await conn.fetch("""
            SELECT id, que, disparador, inicio, intento,
                   ROUND(EXTRACT(EPOCH FROM (now() - inicio))/60, 1) AS minutos
            FROM ejecuciones
            WHERE estado = 'en_curso'
              AND inicio < now() - ($1 || ' minutes')::interval
            ORDER BY inicio
        """, str(int(minutos)))
    return [dict(f) for f in filas]


async def monitor(pool, scheduler=None, bus=None, horas: int = 24) -> dict:
    """
    El estado completo del sistema en una sola llamada.
    """
    ahora = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        # ── Qué está pasando ────────────────────────────────────────────────
        corriendo = [dict(f) for f in await conn.fetch("""
            SELECT id, que, disparador, inicio, intento,
                   ROUND(EXTRACT(EPOCH FROM (now() - inicio))::numeric, 1) AS segundos
            FROM ejecuciones WHERE estado = 'en_curso' ORDER BY inicio
        """)]

        # ── Qué pasó ────────────────────────────────────────────────────────
        recientes = [dict(f) for f in await conn.fetch("""
            SELECT id, que, disparador, inicio, duracion_seg, estado, intento,
                   resultado, LEFT(error, 200) AS error
            FROM ejecuciones
            WHERE inicio >= now() - ($1 || ' hours')::interval
              AND estado <> 'en_curso'
            ORDER BY id DESC LIMIT 40
        """, str(int(horas)))]

        fallidas = [e for e in recientes if e["estado"] == "error"]

    # ── Qué pasará ──────────────────────────────────────────────────────────
    # Se compone de dos cosas: las tareas programadas, y lo que cada evento va
    # a disparar cuando ocurra. Lo segundo lo sabe el bus.
    programado = []
    if scheduler is not None:
        for j in scheduler.get_jobs():
            programado.append({
                "que": j.id,
                "nombre": j.name,
                "cuando": str(j.next_run_time) if j.next_run_time else None,
                "en_minutos": (
                    round((j.next_run_time - ahora).total_seconds() / 60, 1)
                    if j.next_run_time else None),
            })
        programado.sort(key=lambda x: x["cuando"] or "9999")

    reacciones = {}
    if bus is not None:
        estado_bus = bus.estado()["eventos"]
        reacciones = {t: i["suscriptores"]
                      for t, i in estado_bus.items() if i["suscriptores"]}

    # ── Qué debía pasar y no pasó ───────────────────────────────────────────
    huecos = await _huecos_de_historia(pool)
    colgadas = await _colgadas(pool)

    # ── El resumen en palabras ──────────────────────────────────────────────
    alertas = []
    if huecos:
        alertas.append(
            f"faltan {len(huecos)} foto(s) de los últimos 7 días: "
            f"{', '.join(huecos)} — esos días no se pueden recuperar")
    if colgadas:
        for c in colgadas:
            alertas.append(
                f"«{c['que']}» lleva {c['minutos']} min en curso: "
                f"se colgó o el proceso murió sin cerrarla")
    if fallidas:
        ult = fallidas[0]
        # `error` viene con la causa entre corchetes: "[sin_red] ...". Eso es lo
        # accionable — "falló" a secas no dice si hay que esperar o arreglar
        # algo.
        alertas.append(
            f"«{ult['que']}» no completó (intento {ult['intento']}): "
            f"{ult['error']}")
        reint = [e for e in recientes
                 if e["que"] == ult["que"] and e["estado"] == "ok"
                 and e["inicio"] > ult["inicio"]]
        if reint:
            alertas.append(
                f"  → se recuperó en el intento {reint[0]['intento']}")

    return {
        "ahora": str(ahora),
        "alertas": alertas,
        "esta_pasando": corriendo,
        "paso": recientes,
        "pasara": programado,
        "reacciones_por_evento": reacciones,
        "no_paso": {
            "huecos_de_historia": huecos,
            "ejecuciones_colgadas": colgadas,
        },
    }
