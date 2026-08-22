"""
AXIOM v3 — Servidor.
════════════════════════════════════════════════════════════════════════════════
El único lugar donde se montan rutas. Si un router no está acá, no existe.

POR QUÉ ESO IMPORTA:
  v2 tenía 18 routers montados a mano y nadie tenía la lista completa. El
  inventario del 18/08/2026 encontró tres bajo el mismo prefijo
  `/api/experimental`, uno de ellos sin una sola llamada en siete días — y era
  el que el propio código llamaba "el corazón de v3".

  Acá los routers son pocos a propósito: casi todo lo que el sistema sabe hacer
  se expone por la ruta genérica de capacidades.

LA UI SE SIRVE DESDE ACÁ:
  Se evaluó separarla en otro servicio. No aporta: desplegar el frontend no
  requiere reiniciar el backend en ninguno de los dos casos, escalar por
  separado no aplica con un usuario, y que otro cliente consuma la API ya está
  garantizado por el diseño —la ruta genérica y el catálogo—, no por la
  separación física. Separarla costaría otro servicio y CORS.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app import axiom
from backend.api.rutas import capacidades, sistema

logger = logging.getLogger(__name__)

_RAIZ = Path(__file__).resolve().parent.parent.parent
_FRONTEND = _RAIZ / "frontend"


@asynccontextmanager
async def _ciclo(app: FastAPI):
    """
    Arranca el sistema con la API y lo detiene al cerrar.

    Un solo proceso: la API y la captura conviven. Se decidió así porque las
    capturas duran ~9 s y no compiten con nada. Cuando el motor de estrategias
    vaya a proceso aparte —y va a ir, porque una estrategia declarada por el
    copiloto no puede tener la posibilidad de colgar la aplicación— se revisa
    con datos en vez de anticipando.
    """
    await axiom.arrancar()
    app.state.axiom = axiom
    # El registro de capacidades es del punto 2 del plan. Se declara el
    # atributo para que las rutas puedan responder "todavía no existe" en vez
    # de fallar con AttributeError.
    app.state.registro_capacidades = None
    logger.info("[servidor] listo")
    try:
        yield
    finally:
        await axiom.detener()


app = FastAPI(
    title="AXIOM v3",
    description=(
        "Plataforma de información, investigación, análisis y desarrollo "
        "sobre el mercado cripto. Datos de mercado por CoinGecko."
    ),
    version="0.1.0",
    lifespan=_ciclo,
)

app.include_router(capacidades)
app.include_router(sistema)


@app.get("/api/salud", include_in_schema=False)
async def _ping() -> dict:
    """Lo mínimo para saber que el proceso responde."""
    return {"ok": True}


# ── La UI ────────────────────────────────────────────────────────────────────
# Se monta solo si existe: durante el punto 1 y 2 puede no haber frontend
# todavía, y eso no debe impedir que la API funcione.
if _FRONTEND.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(_FRONTEND), html=True), name="ui")
    logger.info("[servidor] UI montada desde %s", _FRONTEND)
else:
    @app.get("/", include_in_schema=False)
    async def _sin_ui():
        return JSONResponse({
            "axiom": "v3",
            "nota": "todavía no hay frontend; la API está en /api",
            "documentacion": "/docs",
        })
