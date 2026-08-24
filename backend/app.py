"""
AXIOM v3 — Armado del sistema.
════════════════════════════════════════════════════════════════════════════════
El único lugar donde se conecta todo: fuentes, bus, planificador y captura.

Acá se ve el modelo completo en pocas líneas:

    el planificador sabe CUÁNDO           → publica eventos o trae datos
    el bus reparte los HECHOS             → sin saber quién escucha
    la captura reacciona                  → sin saber quién la disparó

Ninguna pieza conoce a las otras. Este archivo es el que las presenta.
"""
from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

import asyncpg

from backend.fuentes.cliente import ClienteFuentes
from backend.nucleo import config as _config
from backend.nucleo import bus as _bus
from backend.nucleo import planificador
from backend.nucleo.registro import registro
from backend.captura import universo, pares, metricas

logger = logging.getLogger(__name__)


def dsn() -> str:
    d = os.environ.get("DATABASE_URL")
    if d:
        return d
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for l in env.read_text().splitlines():
            if l.strip().startswith("DATABASE_URL="):
                return l.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("falta DATABASE_URL")


class Axiom:
    """
    El sistema armado. Mantiene el pool, el cliente de fuentes y las
    suscripciones.
    """

    def __init__(self):
        self.pool: asyncpg.Pool | None = None
        self.fuentes = ClienteFuentes()

    async def arrancar(self, con_planificador: bool = True) -> None:
        self.pool = await asyncpg.create_pool(dsn(), min_size=2, max_size=10)
        registro.conectar(self.pool)

        # Las fuentes salen del YAML, no del código. Si la configuración es
        # inválida, ConfigInvalida impide arrancar — arrancar con una
        # configuración a medias haría algo distinto de lo declarado sin que
        # nadie se entere.
        cfg = _config.actual()
        for f in cfg.fuentes.values():
            self.fuentes.registrar(f)
        if cfg.claves_faltantes:
            # No impide arrancar, pero tiene que verse: una fuente sin clave
            # funciona con límites mucho más bajos. En v2 un despliegue pisó la
            # clave TRES veces y el sistema quedó a 4 llamadas por minuto sin
            # que nada avisara.
            logger.warning("[axiom] fuentes SIN CLAVE: %s",
                           ", ".join(cfg.claves_faltantes))
        await self.fuentes.abrir()

        self._suscribir()

        if con_planificador:
            planificador.iniciar({
                "cerrar_el_dia":     self._cerrar_el_dia,
                "reintentar_cierre": self._reintentar_cierre,
                "refrescar_coins":   self._refrescar_coins,
                "inventariar_coins": self._inventariar_coins,
                "catalogar_pares":   self._catalogar_pares,
            })
            # Al arrancar, una sola consulta: ¿falta alguna foto? Reemplaza al
            # chequeo cada minuto que había antes. Se apoya en lo que
            # efectivamente se guardó, no en una variable en memoria que un
            # reinicio borra.
            await planificador.recuperar_dias_faltantes(self.pool)

        logger.info("[axiom] arrancado")

    async def detener(self) -> None:
        planificador.detener()
        await self.fuentes.cerrar()
        if self.pool:
            await self.pool.close()
        logger.info("[axiom] detenido")

    # ── Suscripciones: quién reacciona a qué ────────────────────────────────
    def _suscribir(self) -> None:
        """
        La foto diaria se dispara por EVENTO, no por cron.

        En v2 corría a las 00:20 UTC "porque a esa hora ya hay datos del día
        nuevo" — o sea que ya era un evento disfrazado de horario. Acá el
        disparador es explícito: cerró el día.
        """
        _bus.bus.suscribir(
            _bus.CIERRE_VELA_DIARIA, self._fotografiar_al_cerrar_dia,
            "foto_diaria_del_universo")

        # Las velas de pares también van al cerrar el día: es cuando hay una
        # vela nueva y completa. Va como suscriptor SEPARADO de la foto de
        # coins — si CoinGecko está caído, eso no debe impedir capturar velas
        # de MEXC. Son dos cosas sin relación entre sí.
        _bus.bus.suscribir(
            _bus.CIERRE_VELA_DIARIA, self._capturar_velas_de_pares,
            "velas_diarias_de_pares")

        _bus.bus.suscribir(
            _bus.CAMBIO_DE_UNIVERSO, self._registrar_cambio_de_universo,
            "log_de_cambios_de_universo")

    async def _fotografiar_al_cerrar_dia(self, evento) -> None:
        """
        Retrata el día que CERRÓ, no el que empieza.

        Es la distinción que importa: el evento trae `dia_cerrado` y la foto se
        guarda con esa fecha. Fotografiar el día nuevo daría una foto de datos
        de cero minutos de antigüedad.
        """
        from datetime import date
        cerrado = evento.datos.get("dia_cerrado")
        fecha = date.fromisoformat(cerrado) if cerrado else None
        r = await universo.fotografiar(self.pool, fecha=fecha)
        logger.info("[axiom] foto del día cerrado: %s", r)
        # Devolver importa: es lo que queda en `ejecuciones.resultado` y lo que
        # permite detectar una falla parcial. Un manejador que no devuelve nada
        # se registra como 'ok' sin decir qué hizo.
        return r

    async def _registrar_cambio_de_universo(self, evento) -> None:
        """
        Deja constancia visible de altas y bajas.

        Ya quedan en `universo_eventos`; esto es para que se vea en el log sin
        tener que consultar la base. Las bajas importan: son coins que dejan de
        entrar en toda capacidad.
        """
        d = evento.datos
        altas, bajas = d.get("altas") or [], d.get("bajas") or []
        if bajas:
            logger.warning("[axiom] BAJAS en el universo (%d): %s",
                           len(bajas), ", ".join(bajas[:10]))
        if altas:
            logger.info("[axiom] altas en el universo: %d", len(altas))
        return {"altas": len(altas), "bajas": len(bajas)}

    # ── Tareas del planificador ─────────────────────────────────────────────
    async def _cerrar_el_dia(self):
        return await planificador.cerrar_el_dia(self.pool)

    async def _reintentar_cierre(self):
        return await planificador.reintentar_cierre(self.pool)

    async def _capturar_velas_de_pares(self, evento) -> dict:
        """
        Velas diarias y métricas derivadas.

        El orden importa: primero las velas, después las métricas — que se
        calculan SOBRE las velas. Y la vinculación al final, porque necesita
        que el catálogo de pares esté al día.
        """
        r = await pares.capturar_velas(self.pool)
        m = await metricas.calcular(self.pool)
        return {"velas": r, "metricas": m}

    async def _catalogar_pares(self):
        r = await pares.catalogar(self.pool)
        v = await metricas.vincular_con_coins(self.pool)
        return {"catalogo": r, "vinculos": v}

    async def _refrescar_coins(self):
        return await universo.refrescar(self.pool, self.fuentes)

    async def _inventariar_coins(self):
        return await universo.inventariar(self.pool, self.fuentes)

    # ── Estado ──────────────────────────────────────────────────────────────
    async def estado(self) -> dict:
        return {
            "universo": await universo.estado(self.pool),
            "pares": await pares.estado(self.pool),
            "planificador": planificador.estado(),
            "bus": _bus.bus.estado(),
            "salud": await registro.salud(horas=24),
            "config": _config.resumen(),
        }


axiom = Axiom()


# ══ Ejecución directa: el servicio ═══════════════════════════════════════════

async def _main() -> None:
    import asyncio
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s")

    await axiom.arrancar()
    try:
        # El planificador corre en el event loop; este proceso solo espera.
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await axiom.detener()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())
