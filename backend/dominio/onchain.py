"""
AXIOM v3 — Capacidades on-chain de BTC (valuación por costo base).
════════════════════════════════════════════════════════════════════════════════
On-chain es la cara del Estado del Mercado que mira la CADENA, no los mercados:
¿cuánto vale BTC respecto del costo base agregado de sus tenedores, y en qué
punto de su ciclo de valuación está?

  mercado_mvrv  — MVRV Z-Score: valor de mercado vs. valor realizado, normalizado.
  mercado_nupl  — NUPL: ganancia/pérdida no realizada del mercado.

Ambas leen de onchain_diaria (métricas de bitcoin-data.com) y sitúan el valor
actual en su PERCENTIL contra la historia acumulada —igual disciplina que las
capacidades de BTC: el número solo no dice si es alto o bajo; lo dice el
percentil—.

HONESTIDAD DE FUENTE: a diferencia de funding o dominancia (que AXIOM calcula de
datos crudos observables), estas métricas vienen CALCULADAS por BGeometrics desde
su nodo. Confiable (API oficial, método público), pero se declara que el número
es de terceros. Y describe el ESTADO del ciclo, no predice hacia dónde va.
"""
from __future__ import annotations

import logging

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)


async def _leer_metrica(pool, metrica: str) -> dict:
    """
    Valor actual de una métrica on-chain y su percentil contra toda la historia
    guardada. Devuelve el dict común a mvrv y nupl.
    """
    async with pool.acquire() as conn:
        filas = await conn.fetch(
            """
            SELECT fecha, valor FROM onchain_diaria
            WHERE metrica = $1 AND valor IS NOT NULL
            ORDER BY fecha
            """,
            metrica)

    if not filas:
        return {"valor": None, "dias": 0}

    serie = [(f["fecha"], float(f["valor"])) for f in filas]
    fecha_actual, actual = serie[-1]
    vals = [v for _, v in serie]

    # Percentil del valor actual contra toda la historia: fracción de días por
    # debajo. Alto = el mercado está caro respecto de su costo base histórico.
    menores = sum(1 for v in vals if v < actual)
    percentil = round(menores / len(vals) * 100, 1)

    vals_ord = sorted(vals)
    n = len(vals_ord)
    return {
        "valor": round(actual, 4),
        "percentil": percentil,
        "minimo_historico": round(vals_ord[0], 4),
        "maximo_historico": round(vals_ord[-1], 4),
        "mediana_historica": round(vals_ord[n // 2], 4),
        "dias": n,
        "desde": str(serie[0][0]),
        "_fuente_hasta": fecha_actual,
    }


async def _mvrv(contexto, **_) -> dict:
    return await _leer_metrica(contexto["pool"], "mvrv_zscore")


async def _nupl(contexto, **_) -> dict:
    return await _leer_metrica(contexto["pool"], "nupl")


def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="mercado_mvrv", objeto=Objeto.MERCADO,
        funcion=_mvrv, alcance=Alcance.INDIVIDUAL,
        parametros={},
        descripcion="MVRV Z-Score de BTC: valuación del mercado respecto de su "
                    "costo base agregado, y su posición en su ciclo histórico",
        propiedad=Propiedad(unidad="z-score", direccion=Direccion.CONTEXTUAL),
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="el MVRV Z-Score actual —valor de mercado menos valor realizado, "
                 "normalizado por el desvío del valor de mercado— y su percentil "
                 "contra toda la historia on-chain guardada",
            infiere="que un MVRV Z-Score en percentil alto describe un mercado "
                    "caro respecto del costo base de sus tenedores (históricamente "
                    "asociado a zonas de techo de ciclo), y en percentil bajo, "
                    "barato (zonas de piso). Describe el ESTADO del ciclo",
            no_sabe="NO predice el precio: un mercado caro puede encarecerse más, "
                    "uno barato abaratarse más. Es una métrica de CICLO LARGO "
                    "(meses), no de trading. El número viene CALCULADO por "
                    "bitcoin-data.com desde su nodo —no lo mide AXIOM—: es "
                    "confiable pero es dato de terceros. La historia gratuita "
                    "cubre 4 años, así que el percentil es contra ese período (y "
                    "lo que AXIOM haya acumulado además)",
            fuente="bitcoin-data.com (BGeometrics), MVRV Z-Score calculado desde "
                   "su nodo Bitcoin — API oficial, método público (Mahmudov/Puell)",
            metodo="valor actual de onchain_diaria; percentil como % de días de "
                   "la historia guardada por debajo del valor actual")))

    registro.registrar(Simple(
        nombre="mercado_nupl", objeto=Objeto.MERCADO,
        funcion=_nupl, alcance=Alcance.INDIVIDUAL,
        parametros={},
        descripcion="NUPL de BTC: ganancia/pérdida no realizada del mercado, y "
                    "su posición en su ciclo histórico",
        propiedad=Propiedad(unidad="fracción", direccion=Direccion.CONTEXTUAL,
                            minimo=-1, maximo=1),
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="el NUPL actual —fracción del market cap que es ganancia no "
                 "realizada— y su percentil contra toda la historia guardada",
            infiere="que un NUPL alto describe un mercado con mucha ganancia no "
                    "realizada (históricamente asociado a euforia/techo), y "
                    "negativo, un mercado en pérdida agregada (capitulación/piso). "
                    "Describe el ESTADO del ciclo",
            no_sabe="NO predice el precio ni el momento de un giro. Es métrica de "
                    "CICLO LARGO, no de trading. Viene CALCULADA por "
                    "bitcoin-data.com desde su nodo —dato de terceros confiable, "
                    "no medido por AXIOM—. El percentil es contra los ~4 años de "
                    "historia gratuita (más lo que AXIOM acumule)",
            fuente="bitcoin-data.com (BGeometrics), NUPL calculado desde su nodo "
                   "Bitcoin — API oficial",
            metodo="valor actual de onchain_diaria; percentil como % de días de "
                   "la historia guardada por debajo del valor actual")))

    logger.info("[capacidades] mercado: mvrv, nupl (on-chain, valuación de ciclo)")
