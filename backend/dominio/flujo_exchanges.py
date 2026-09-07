"""
AXIOM v3 — Flujo y supply de BTC en exchanges (Coin Metrics).
════════════════════════════════════════════════════════════════════════════════
La cara de "¿el BTC se mueve hacia donde se vende, o se retira a guardar?":

  · FLUJO NETO (entradas − salidas de exchanges): entrada neta = presión de venta
    potencial (mandan BTC al exchange para vender); salida neta = acumulación
    (retiran a cold storage). Es flujo con signo → se lee por neto + racha.
  · SUPPLY EN EXCHANGES: cuánto BTC hay acumulado en exchanges. Nivel → se lee
    por percentil. Bajando sostenido = acumulación de largo plazo (menos oferta
    disponible); subiendo = distribución. Menos ruidoso que el flujo diario.

Ambas de Coin Metrics. El último dato puede venir "flash" (preliminar): se
declara, no se oculta —un flujo de ayer puede revisarse al consolidarse—.
"""
from __future__ import annotations

import logging

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance)

logger = logging.getLogger(__name__)


async def _flujo(contexto, dias=7, **_) -> dict:
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        # Flujo: in y out por día, para el neto de la ventana y la racha.
        flujo = await conn.fetch(
            """
            SELECT i.fecha,
                   i.valor AS entrada, o.valor AS salida,
                   i.status AS status
            FROM onchain_diaria i
            JOIN onchain_diaria o ON o.fecha = i.fecha AND o.metrica = 'flow_out_ex'
            WHERE i.metrica = 'flow_in_ex'
            ORDER BY i.fecha DESC LIMIT 40
            """)
        # Supply en exchanges: toda la serie para el percentil.
        supply = await conn.fetch(
            """
            SELECT fecha, valor, status FROM onchain_diaria
            WHERE metrica = 'sply_ex' AND valor IS NOT NULL
            ORDER BY fecha
            """)

    out = {}
    fuente_hasta = None  # date, para el motor (no string)

    # ── Flujo neto (lectura de flujo) ────────────────────────────────────────
    if flujo:
        netos = [(f["fecha"], float(f["entrada"]) - float(f["salida"]),
                  f["status"]) for f in flujo]  # desc
        fecha_ult, neto_ult, status_ult = netos[0]
        ventana = netos[:dias]
        neto_ventana = round(sum(n for _, n, _ in ventana), 2)
        # racha: días consecutivos del mismo signo desde el más reciente
        signo = 1 if neto_ult > 0 else (-1 if neto_ult < 0 else 0)
        racha = 0
        if signo:
            for _, n, _ in netos:
                if (n > 0 and signo > 0) or (n < 0 and signo < 0):
                    racha += 1
                else:
                    break
        out["flujo"] = {
            "neto_ultimo_dia": round(neto_ult, 2),
            "neto_ventana": neto_ventana,
            "dias_ventana": len(ventana),
            "racha_dias": racha,
            "racha_signo": "entradas" if neto_ult > 0 else ("salidas" if neto_ult < 0 else "neutro"),
            "status_ultimo": status_ult,
            "hasta": str(fecha_ult),
        }
        fuente_hasta = fecha_ult

    # ── Supply en exchanges (lectura de nivel: percentil) ────────────────────
    if supply:
        vals = [float(f["valor"]) for f in supply]
        actual = vals[-1]
        menores = sum(1 for v in vals if v < actual)
        fecha_sup = supply[-1]["fecha"]
        out["supply_en_exchanges"] = {
            "btc": round(actual, 0),
            "percentil": round(menores / len(vals) * 100, 1),
            "minimo": round(min(vals), 0),
            "maximo": round(max(vals), 0),
            "dias": len(vals),
            "status_ultimo": supply[-1]["status"],
            "hasta": str(fecha_sup),
        }
        # el más restrictivo (más viejo) de los dos "hasta"
        if fuente_hasta is None or fecha_sup < fuente_hasta:
            fuente_hasta = fecha_sup

    if not out:
        return {"valor": None, "dias": 0}

    if fuente_hasta is not None:
        out["_fuente_hasta"] = fuente_hasta  # date, no str
    return out


def declarar() -> None:
    """Se llama una vez al arrancar."""
    registro.registrar(Simple(
        nombre="mercado_flujo_exchanges", objeto=Objeto.MERCADO,
        funcion=_flujo, alcance=Alcance.INDIVIDUAL,
        parametros={"dias": {"default": 7, "min": 1, "max": 30}},
        descripcion="Flujo neto de BTC hacia/desde exchanges (presión de venta "
                    "vs. acumulación) y cuánto BTC hay acumulado en exchanges",
        propiedad=Propiedad(unidad="BTC", direccion=Direccion.CONTEXTUAL),
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="el flujo NETO diario de BTC a exchanges (entradas − salidas, en "
                 "BTC; + = entra, − = sale), su neto acumulado de la ventana y la "
                 "racha; y el SUPPLY en exchanges (BTC acumulado) con su percentil "
                 "histórico",
            infiere="que entradas netas describen BTC yendo hacia donde se vende "
                    "(presión de venta potencial) y salidas, acumulación a cold "
                    "storage. Un supply en exchanges bajo en su historia = menos "
                    "oferta disponible para vender (acumulación de fondo)",
            no_sabe="NO predice el precio: BTC entrando a un exchange no garantiza "
                    "venta (puede ser colateral, custodia, arbitraje). El último "
                    "dato puede venir marcado 'flash' (preliminar) y revisarse al "
                    "consolidarse —se reporta en status_ultimo—. La atribución de "
                    "qué direcciones son 'de exchange' la hace Coin Metrics "
                    "(heurística de terceros), no AXIOM",
            fuente="coinmetrics community: FlowInExNtv/FlowOutExNtv (flujo) y "
                   "SplyExNtv (supply), en BTC, atribución de Coin Metrics",
            metodo="neto = entradas − salidas por día; racha = días consecutivos "
                   "del mismo signo; percentil del supply como % de días por "
                   "debajo del actual. El neto no se guarda, se calcula al leer")))

    logger.info("[capacidades] mercado: flujo_exchanges (Coin Metrics)")
