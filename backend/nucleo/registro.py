"""
AXIOM v3 — Registro de ejecuciones.
════════════════════════════════════════════════════════════════════════════════
Envuelve cualquier cosa que el sistema ejecute y deja constancia: qué corrió,
por qué, cuánto tardó, cómo terminó y QUÉ DEVOLVIÓ.

TRANSPARENTE A PROPÓSITO:
  Lo usan el planificador y el bus. Las funciones ejecutadas no saben que
  existe y no tienen que acordarse de nada.

  En v2 registrar dependía de que cada job lo hiciera, y por eso el observador
  llegó tarde y a medias: hubo que parchear once wrappers para que devolvieran
  su resultado, y aun así uno quedó afuera —justo el del sync de precios, que
  era el ejemplo de falla parcial—.

TRES COSAS QUE REGISTRA Y v2 NO TENÍA DE ENTRADA:

  · el RESULTADO — sin él no se ven las fallas parciales. `sync_prices`
    devolvía {'updated': 1750} en vez de 2000 y no lanzaba ninguna excepción.
  · el DISPARADOR — por qué corrió. La foto diaria la dispara un evento, no una
    tarea: registrar solo tareas la dejaría invisible.
  · la EXCEPCIÓN se relanza. En v2 se logueaba y se tragaba, y el scheduler
    reportaba "executed successfully".

QUÉ HACE SI NO PUEDE REGISTRAR:
  Loguea y sigue. Un problema anotando la corrida no puede romper la corrida.
  Es la única excepción tragada legítima de este módulo.
"""
from __future__ import annotations

import json
import inspect
import logging
import traceback as _tb
from datetime import datetime, timezone
from typing import Any, Callable

import asyncpg

logger = logging.getLogger(__name__)

_MAX_TRAZA = 4000


def _serializable(v: Any) -> str | None:
    """
    Deja el resultado en algo que entre en JSONB.

    Las funciones devuelven dicts simples, pero puede colarse un date o un
    Decimal; en ese caso se guarda su representación antes que perder el dato.
    """
    if v is None:
        return None
    try:
        return json.dumps(v, default=str)
    except Exception:
        return json.dumps({"_repr": str(v)[:1000]})


class Registro:
    """
    Escribe en `ejecuciones`. Se instancia una vez con el pool.

    El pool se asigna después de arrancar, así que puede no estar: en ese caso
    no registra pero tampoco rompe.
    """

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    def conectar(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def _guardar(self, fila: dict) -> None:
        if self.pool is None:
            logger.debug("[registro] sin pool; %s no se registró", fila.get("que"))
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ejecuciones (que, disparador, inicio, fin,
                                             duracion_seg, estado, resultado,
                                             error, traza)
                    VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9)
                """, fila["que"], fila["disparador"], fila["inicio"],
                     fila["fin"], fila["duracion_seg"], fila["estado"],
                     fila.get("resultado"), fila.get("error"), fila.get("traza"))
        except Exception as e:
            # Deliberado: si no se puede anotar, se pierde el REGISTRO, no la
            # ejecución. Es la única excepción tragada legítima acá.
            logger.warning("[registro] no se pudo anotar %s: %s",
                           fila.get("que"), e)

    async def _abrir(self, que: str, disparador: str, intento: int) -> int | None:
        """
        Anota que ALGO EMPEZÓ y devuelve su id.

        Sin esto, una tarea en curso no aparece en ningún lado y una tarea
        colgada es indistinguible de una que nunca arrancó. El monitor tiene
        que poder decir qué está pasando ahora, no solo qué pasó.
        """
        if self.pool is None:
            return None
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval("""
                    INSERT INTO ejecuciones (que, disparador, inicio, estado,
                                             intento)
                    VALUES ($1, $2, now(), 'en_curso', $3)
                    RETURNING id
                """, que, disparador, intento)
        except Exception as e:
            logger.warning("[registro] no se pudo abrir %s: %s", que, e)
            return None

    async def _cerrar(self, id_: int | None, estado: str,
                      resultado: Any = None, error: str | None = None,
                      traza: str | None = None) -> None:
        """Cierra una ejecución abierta. Si no se pudo abrir, no hay qué cerrar."""
        if self.pool is None or id_ is None:
            return
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE ejecuciones SET
                        fin          = now(),
                        duracion_seg = ROUND(EXTRACT(EPOCH FROM (now() - inicio))::numeric, 3),
                        estado       = $2,
                        resultado    = $3::jsonb,
                        error        = $4,
                        traza        = $5
                    WHERE id = $1
                """, id_, estado, resultado, error, traza)
        except Exception as e:
            logger.warning("[registro] no se pudo cerrar %s: %s", id_, e)

    async def ejecutar(self, que: str, disparador: str,
                       funcion: Callable, *args, intento: int = 1,
                       **kwargs) -> Any:
        """
        Ejecuta algo y lo registra: al empezar y al terminar.

        Si falla: registra el error con su traza y RELANZA. Quien llamó decide
        qué hacer — pero nadie puede ignorar que falló, que es exactamente lo
        que pasaba en v2.
        """
        id_ = await self._abrir(que, disparador, intento)
        try:
            r = funcion(*args, **kwargs)
            if inspect.isawaitable(r):
                r = await r
        except Exception as e:
            await self._cerrar(
                id_, "error", None, str(e)[:2000],
                "".join(_tb.format_exception(
                    type(e), e, e.__traceback__))[:_MAX_TRAZA])
            logger.error("[registro] %s (%s) FALLÓ: %s", que, disparador, e)
            raise

        await self._cerrar(id_, "ok", _serializable(r))
        return r

    async def en_curso(self) -> list[dict]:
        """
        Qué está corriendo AHORA.

        Una fila con muchos minutos acá es una tarea colgada — y esa distinción
        no existía antes: sin registro de inicio, colgada y nunca-arrancada se
        veían igual.
        """
        if self.pool is None:
            return []
        async with self.pool.acquire() as conn:
            filas = await conn.fetch("""
                SELECT id, que, disparador, inicio, intento,
                       ROUND(EXTRACT(EPOCH FROM (now() - inicio))::numeric, 1)
                           AS corriendo_hace_seg
                FROM ejecuciones WHERE estado = 'en_curso'
                ORDER BY inicio
            """)
        return [dict(f) for f in filas]

    # ── Consulta ────────────────────────────────────────────────────────────
    async def historial(self, limite: int = 50, que: str | None = None) -> list[dict]:
        if self.pool is None:
            return []
        async with self.pool.acquire() as conn:
            filas = await conn.fetch("""
                SELECT id, que, disparador, inicio, duracion_seg, estado,
                       intento, resultado, LEFT(error, 300) AS error
                FROM ejecuciones
                WHERE ($2::text IS NULL OR que = $2)
                ORDER BY id DESC LIMIT $1
            """, limite, que)
        return [dict(f) for f in filas]

    async def salud(self, horas: int = 24) -> dict:
        """
        Resumen por tarea. Responde de un vistazo la pregunta que en v2 nadie
        podía hacerse: ¿qué está fallando en silencio?
        """
        if self.pool is None:
            return {"horas": horas, "tareas": []}
        async with self.pool.acquire() as conn:
            filas = await conn.fetch("""
                SELECT que,
                       MAX(disparador)                             AS disparador,
                       COUNT(*)                                    AS corridas,
                       COUNT(*) FILTER (WHERE estado='ok')         AS ok,
                       COUNT(*) FILTER (WHERE estado='error')      AS errores,
                       MAX(inicio)                                 AS ultima,
                       ROUND(AVG(duracion_seg), 2)                 AS dur_media,
                       MAX(error) FILTER (WHERE estado='error')    AS ultimo_error
                FROM ejecuciones
                WHERE inicio >= now() - ($1 || ' hours')::interval
                GROUP BY que
                ORDER BY errores DESC, que
            """, str(int(horas)))
        return {"horas": horas, "tareas": [dict(f) for f in filas]}


registro = Registro()
