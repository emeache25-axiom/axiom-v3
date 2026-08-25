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
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.nucleo.motor import MotorError

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
    from backend.nucleo.capacidades import registro as reg
    return {"total": len(reg), "operaciones": reg.operaciones,
            "capacidades": reg.listar()}


@capacidades.post("/capacidad/{nombre}")
async def ejecutar_capacidad(nombre: str, request: Request,
                             pedido: PedidoCapacidad | None = None) -> Any:
    """
    Resuelve CUALQUIER capacidad declarada.

    Una sola ruta para todas: agregar una capacidad no requiere endpoint nuevo.
    """
    motor = request.app.state.axiom.motor
    args = pedido.model_dump() if pedido else {}
    objeto_id = args.pop("objeto_id", None)

    try:
        # Primero el caché: una capacidad masiva sobre 3.000 pares tarda
        # segundos, y recalcularla en cada consulta HTTP sería absurdo cuando
        # el valor no cambió. La vigencia decide, no el que llama.
        hay, valor = await motor.vigente(nombre, objeto_id, args)
        if hay:
            cap = motor.registro.obtener(nombre)
            return {
                "capacidad": nombre, "valor": valor, "desde_cache": True,
                "epistemico": {"mide": cap.epistemico.mide,
                               "infiere": cap.epistemico.infiere or None,
                               "no_sabe": cap.epistemico.no_sabe},
            }
        r = await motor.resolver(nombre, args)
        return r.a_dict()
    except KeyError as e:
        raise HTTPException(404, str(e))
    except MotorError as e:
        # 400 y no 500: un parámetro mal escrito o fuera de rango es culpa de
        # quien llama, no del servidor. Y el mensaje ya dice qué admite — es
        # justamente lo que en v2 faltaba, donde un parámetro no reconocido se
        # ignoraba en silencio.
        raise HTTPException(400, str(e))


@capacidades.get("/capacidad/{nombre}/explicar")
async def explicar_capacidad(nombre: str, request: Request) -> dict:
    """
    De qué se compone una respuesta, sin calcularla.

    Si una capacidad es una composición declarada, se puede mostrar de dónde
    salió. En v2 eso se escribía a mano en cada capacidad.
    """
    try:
        return await request.app.state.axiom.motor.explicar(nombre)
    except KeyError as e:
        raise HTTPException(404, str(e))


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


# ══ 3. Configuración ═════════════════════════════════════════════════════════

configuracion = APIRouter(prefix="/api/config", tags=["config"])


@configuracion.get("")
async def ver_config() -> dict:
    """
    La configuración vigente. NUNCA incluye claves: el YAML declara qué
    variable de entorno tiene cada una, y el valor vive en el .env.
    """
    from backend.nucleo import config
    return config.resumen()


@configuracion.get("/archivo/{nombre}")
async def ver_archivo(nombre: str) -> dict:
    """
    El YAML crudo, para editarlo. Los comentarios son parte del valor: toda la
    disciplina de AXIOM es declarar el porqué, y un archivo que los admite es
    coherente con eso.
    """
    from backend.nucleo.config import DIR_CONFIG, ARCHIVOS
    if nombre not in ARCHIVOS:
        raise HTTPException(404, f"no existe '{nombre}'. Hay: {list(ARCHIVOS)}")
    ruta = DIR_CONFIG / f"{nombre}.yaml"
    return {"nombre": nombre, "contenido": ruta.read_text(encoding="utf-8")}


@configuracion.post("/recargar")
async def recargar_config(request: Request) -> dict:
    """
    Relee los archivos sin reiniciar.

    TOLERANTE a propósito: si la configuración nueva es inválida, se conserva
    la anterior y se devuelve qué está mal. Perder el servicio por un error de
    tipeo en el panel sería peor que el problema.
    """
    from backend.nucleo import config
    r = config.recargar()
    if not r["aplicada"]:
        # 422 y no 500: el pedido se entendió, la configuración es la que no
        # sirve. Y el sistema sigue andando con la anterior.
        return JSONResponse(status_code=422, content=r)
    return r
