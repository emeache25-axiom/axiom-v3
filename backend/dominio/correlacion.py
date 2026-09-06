"""
AXIOM v3 — Correlación de BTC con mercados tradicionales.
════════════════════════════════════════════════════════════════════════════════
¿BTC se mueve junto con las acciones/el oro, o independiente? Una cara del estado
del mercado que dice qué TIPO de activo está siendo BTC ahora:

  · correlación alta con el S&P  → risk-on (BTC como activo de riesgo)
  · correlación alta con el oro  → refugio
  · baja con ambos               → clase propia, desacoplado

Lee correlacion_diaria (fuente sharpe.ai). Ventana configurable (30/60/90 obs,
default 90). Da la correlación actual con S&P y con oro, más su percentil contra
la historia —el número solo no dice si es alto o bajo; lo dice el percentil—.
"""
from __future__ import annotations

import logging

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)

VENTANA = {"default": 90, "min": 30, "max": 90}
_PARES = {"btc-sp500": "S&P 500", "btc-gold": "oro"}


async def _corr_par(conn, par: str, ventana: int) -> dict | None:
    """Correlación actual de un par en una ventana + su percentil histórico."""
    filas = await conn.fetch(
        """
        SELECT fecha, valor FROM correlacion_diaria
        WHERE par = $1 AND ventana = $2 AND valor IS NOT NULL
        ORDER BY fecha
        """,
        par, ventana)
    if not filas:
        return None
    vals = [float(f["valor"]) for f in filas]
    actual = vals[-1]
    menores = sum(1 for v in vals if v < actual)
    return {
        "correlacion": round(actual, 3),
        "percentil": round(menores / len(vals) * 100, 1),
        "minimo": round(min(vals), 3),
        "maximo": round(max(vals), 3),
        "dias": len(vals),
        "hasta": filas[-1]["fecha"],
    }


async def _correlacion(contexto, ventana=90, **_) -> dict:
    pool = contexto["pool"]
    # La ventana pedida puede no ser exacta 30/60/90; se toma la más cercana.
    ventana = min((30, 60, 90), key=lambda w: abs(w - int(ventana)))

    out = {"ventana": ventana}
    fuente_hasta = None
    async with pool.acquire() as conn:
        for par, nombre in _PARES.items():
            r = await _corr_par(conn, par, ventana)
            clave = "sp500" if par == "btc-sp500" else "gold"
            out[clave] = r
            if r and (fuente_hasta is None or r["hasta"] < fuente_hasta):
                fuente_hasta = r["hasta"]

    if not out.get("sp500") and not out.get("gold"):
        return {"valor": None, "dias": 0}

    # convertir date a str en los sub-dicts para el JSON
    for k in ("sp500", "gold"):
        if out.get(k) and out[k].get("hasta"):
            out[k]["hasta"] = str(out[k]["hasta"])

    if fuente_hasta:
        out["_fuente_hasta"] = fuente_hasta
    return out


def declarar() -> None:
    """Se llama una vez al arrancar."""
    registro.registrar(Simple(
        nombre="mercado_correlacion_tradfi", objeto=Objeto.MERCADO,
        funcion=_correlacion, alcance=Alcance.INDIVIDUAL,
        parametros={"ventana": VENTANA},
        descripcion="Correlación de BTC con mercados tradicionales (S&P 500 y "
                    "oro): si se mueve como activo de riesgo, como refugio o "
                    "desacoplado. Ventana configurable (30/60/90, default 90)",
        propiedad=Propiedad(unidad="correlación", direccion=Direccion.CONTEXTUAL,
                            minimo=-1, maximo=1),
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="la correlación de Pearson de los retornos de BTC con el S&P 500 "
                 "y con el oro, en la ventana pedida, y el percentil de cada una "
                 "contra su propia historia",
            infiere="que una correlación alta con el S&P describe a BTC "
                    "moviéndose como activo de riesgo (risk-on); alta con el oro, "
                    "como refugio; baja con ambos, desacoplado (clase propia). El "
                    "percentil dice si esa correlación es alta o baja PARA BTC",
            no_sabe="correlación NO es causalidad ni predicción: describe cómo se "
                    "movieron juntos en la ventana, no por qué ni qué harán. Es "
                    "móvil —cambia semana a semana—. La calcula sharpe.ai (un "
                    "agregador) sobre precios de terceros, no AXIOM; es Pearson "
                    "estándar, verificable en principio pero no medido acá. La "
                    "historia arranca ~2024-01, así que el percentil es contra "
                    "ese período",
            fuente="sharpe.ai, correlación rolling BTC vs S&P 500 (SPY) y oro "
                   "(GLD) — agregador, calcula el Pearson sobre precios propios",
            metodo="última correlación de correlacion_diaria para la ventana; "
                   "percentil como % de días de la historia por debajo del valor "
                   "actual. Ventana: la más cercana entre 30/60/90 a la pedida")))

    logger.info("[capacidades] mercado: correlacion_tradfi (BTC vs S&P, oro)")
