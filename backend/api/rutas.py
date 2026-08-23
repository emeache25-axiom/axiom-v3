"""
AXIOM v3 — API.
════════════════════════════════════════════════════════════════════════════════
Pocas rutas escritas a mano. La mayoría de lo que el sistema sabe hacer se
expone por UNA ruta genérica que resuelve cualquier capacidad del registro.

POR QUÉ ASÍ:
  Si cada capacidad necesitara su endpoint, agregar una sería: declararla,
  escribir la ruta, montarla. Tres pasos donde debería haber uno.

  v2 tenía 18 routers montados a mano en main.py, y el inventario del
  18/08/2026 encontró lo previsible: TRES bajo el mismo prefijo
  `/api/experimental`, uno de ellos —el orquestador, que el propio código
  llamaba "el corazón de v3"— sin una sola llamada en siete días. Nadie lo
  notó porque nada obligaba a mirarlo.

LO QUE SE ESCRIBE A MANO, y por qué no puede derivarse:
  · el estado del sistema — no es una capacidad, es introspección
  · la configuración — no consulta datos, los cambia
  · las colecciones del usuario — watchlist, estrategias: son CRUD

Todo lo demás sale del registro.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ══ 1. Capacidades — la ruta genérica ════════════════════════════════════════

capacidades = APIRouter(prefix="/api", tags=["capacidades"])


class PedidoCapacidad(BaseModel):
    """Los argumentos van en el cuerpo: una capacidad puede recibir cualquier cosa."""
    class Config:
        extra = "allow"


@capacidades.get("/capacidades")
async def listar_capacidades(request: Request) -> dict:
    """
    El catálogo: qué sabe hacer el sistema y qué declara cada cosa.

    Es lo que permite que un cliente —la web, una app, el copiloto— descubra
    las capacidades sin que nadie le pase una lista. Agregar una capacidad la
    hace visible sin tocar el cliente.
    """
    reg = getattr(request.app.state, "registro_capacidades", None)
    if reg is None:
        # El registro de capacidades es del punto 2 del plan. Hasta que exista,
        # se dice claramente en vez de devolver una lista vacía que parecería
        # "no hay ninguna".
        return {"disponible": False,
                "nota": "el registro de capacidades todavía no está construido"}
    return {"disponible": True, "capacidades": reg.listar()}


@capacidades.post("/capacidad/{nombre}")
async def ejecutar_capacidad(nombre: str, request: Request,
                             pedido: PedidoCapacidad | None = None) -> Any:
    """
    Resuelve CUALQUIER capacidad declarada.

    Una sola ruta para todas: agregar una capacidad no requiere endpoint nuevo.
    """
    reg = getattr(request.app.state, "registro_capacidades", None)
    if reg is None:
        raise HTTPException(
            501, "el registro de capacidades todavía no está construido")
    args = pedido.model_dump() if pedido else {}
    try:
        return await reg.ejecutar(nombre, args)
    except KeyError:
        raise HTTPException(404, f"capacidad '{nombre}' no declarada")


# ══ 2. Sistema — introspección ═══════════════════════════════════════════════

sistema = APIRouter(prefix="/api/sistema", tags=["sistema"])


@sistema.get("/estado")
async def estado(request: Request) -> dict:
    """
    Qué está pasando: el universo, el planificador, el bus y la salud.

    Es lo que responde "¿está funcionando?" sin entrar por SSH a mirar el
    journal — que era la única forma hasta acá.
    """
    axiom = request.app.state.axiom
    return await axiom.estado()


@sistema.get("/ejecuciones")
async def ejecuciones(request: Request, limite: int = 50,
                      que: str | None = None) -> dict:
    """
    Historial: qué corrió, por qué, cuánto tardó y qué devolvió.

    El `resultado` es lo que permite ver una falla PARCIAL — un job que corre,
    no falla, y hace menos de lo que dice.
    """
    from backend.nucleo.registro import registro
    return {"ejecuciones": await registro.historial(min(limite, 500), que)}


@sistema.get("/salud")
async def salud(request: Request, horas: int = 24) -> dict:
    """Resumen por tarea: corridas, errores y duración media."""
    from backend.nucleo.registro import registro
    return await registro.salud(horas)


@sistema.get("/fuentes")
async def fuentes(request: Request) -> dict:
    """
    Qué fuentes hay declaradas, con sus límites y qué ofrece cada una.

    `ofrece` / `no_ofrece` importa: preguntarle el libro a una fuente que no lo
    da tiene que fallar con un mensaje claro, no devolver vacío.
    """
    cliente = request.app.state.axiom.fuentes
    return {
        "fuentes": [
            {
                "nombre": f.nombre,
                "base_url": f.base_url,
                "endpoints": sorted(f.endpoints),
                "ofrece": list(f.ofrece),
                "no_ofrece": list(f.no_ofrece),
                "limites": {
                    "llamadas_por_minuto": f.limites.llamadas_por_minuto,
                    "reintentos": f.limites.reintentos,
                    "timeout_s": f.limites.timeout_s,
                },
                # Nunca la clave: solo si está puesta.
                "autenticada": bool(f.headers),
            }
            for f in cliente._fuentes.values()
        ]
    }


@sistema.get("/monitor")
async def monitor(request: Request, horas: int = 24) -> dict:
    """
    Qué pasó, qué está pasando, qué pasará — y qué DEBÍA pasar y no pasó.

    Esa última es la más valiosa: no es un evento sino la AUSENCIA de uno, así
    que ningún registro la contiene. Se detecta cruzando lo esperado contra lo
    registrado.
    """
    from backend.nucleo.monitor import monitor as _monitor
    from backend.nucleo import planificador
    from backend.nucleo.bus import bus as _bus
    ax = request.app.state.axiom
    return await _monitor(ax.pool, planificador._scheduler, _bus, horas)


@sistema.get("/eventos")
async def eventos(request: Request) -> dict:
    """Qué eventos existen, quién escucha cada uno y cuántos se publicaron."""
    from backend.nucleo.bus import bus
    return bus.estado()
