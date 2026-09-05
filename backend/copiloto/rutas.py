"""
AXIOM v3 — Router del copiloto.
════════════════════════════════════════════════════════════════════════════════
Una ruta: POST /api/copiloto. Recibe un mensaje (y opcionalmente el objeto en
foco de la vista donde está el usuario) y devuelve la respuesta redactada más
los widgets a montar.

El copiloto reusa las instancias vivas de la app —llm, motor, pool— igual que
la ruta de capacidades reusa el motor. No crea nada propio.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from backend.copiloto.skills import responder

logger = logging.getLogger(__name__)

copiloto = APIRouter(prefix="/api/copiloto", tags=["copiloto"])


class PedidoCopiloto(BaseModel):
    mensaje: str
    # El objeto en foco de la vista donde está el usuario (§10.4). Mínimo:
    # {vista, par|coin, ...}. Opcional — sin foco, el copiloto clasifica sólo
    # por el texto.
    foco: dict | None = None


@copiloto.post("")
async def preguntar(pedido: PedidoCopiloto, request: Request) -> dict:
    """
    El flujo completo del copiloto: clasificar → resolver → ejecutar → redactar.
    """
    ax = request.app.state.axiom
    if not ax.llm.disponible:
        raise HTTPException(
            503, "el copiloto no está disponible: no hay proveedor de LLM configurado")

    mensaje = (pedido.mensaje or "").strip()
    if not mensaje:
        raise HTTPException(400, "mensaje vacío")

    try:
        return await responder(
            ax.llm, ax.motor, ax.pool, mensaje, pedido.foco)
    except Exception as e:
        logger.exception("[copiloto] error resolviendo el mensaje")
        raise HTTPException(500, f"error del copiloto: {e}")
