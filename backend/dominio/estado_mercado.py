"""
AXIOM v3 — Estado global del mercado y estado de BTC.
════════════════════════════════════════════════════════════════════════════════
Dos cosas:

  mercado_dominancia  — la brújula: qué parte del mercado es BTC, cómo cambia.
  btc_estado          — el estado de BTC en una sola lectura, REUNIENDO lo que
                        ya se mide: comportamiento (perfil), presión en
                        derivados (funding), posicionamiento en opciones
                        (max-pain) y reparto del mercado (dominancia).

POR QUÉ REUNIR Y NO CLASIFICAR (igual que btc_perfil):
  No se produce una etiqueta de "régimen". Se decidió que colapsar el estado en
  'alcista'/'bajista' destruye lo que distingue un mercado que sube tranquilo de
  uno que sube violento. `btc_estado` ES sus partes: cada una declara lo suyo y
  el copiloto las lee juntas. Sin régimen — por diseño.

  btc_estado compone btc_perfil (que a su vez reúne 5 dimensiones): composición
  anidada, que el motor soporta. El resultado tiene cuatro bloques, uno de los
  cuales trae adentro el perfil completo.
"""
from __future__ import annotations

import logging

from backend.nucleo.capacidades import (
    registro, Simple, Compuesta, Objeto, Direccion, Epistemico, Propiedad,
    Vigencia, Alcance)

logger = logging.getLogger(__name__)

VENTANA = {"default": 30, "min": 7, "max": 365}


# ════════════════════════════════════════════════════════════════════════════
#  DOMINANCIA — la brújula del reparto del mercado
# ════════════════════════════════════════════════════════════════════════════
async def _dominancia(contexto, ventana=30, **_) -> dict:
    """
    Qué parte del mercado es BTC, y cómo viene esa proporción.

    Lee mercado_global: la dominancia actual y su cambio sobre la ventana. La
    dominancia es un cociente (cap BTC / cap total): sube cuando el capital se
    refugia en BTC, baja cuando rota hacia alts.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        actual = await conn.fetchrow(
            """
            SELECT fecha, dominancia_btc, dominancia_eth,
                   capitalizacion_total, volumen_total, coins_activas_fuente
            FROM mercado_global ORDER BY fecha DESC LIMIT 1
            """)
        if actual is None:
            return {"valor": None, "dias": 0}

        # La serie de la ventana, para el cambio y el rango.
        serie = await conn.fetch(
            """
            SELECT fecha, dominancia_btc
            FROM mercado_global
            ORDER BY fecha DESC LIMIT $1
            """,
            ventana)

    dom_actual = float(actual["dominancia_btc"]) if actual["dominancia_btc"] is not None else None
    vals = [float(f["dominancia_btc"]) for f in serie if f["dominancia_btc"] is not None]

    cambio_pp = None  # en PUNTOS PORCENTUALES (es un %; su diferencia son pp)
    if len(vals) >= 2 and dom_actual is not None:
        # serie viene desc: vals[-1] es el más viejo de la ventana
        cambio_pp = round(dom_actual - vals[-1], 2)

    return {
        "dominancia_btc": dom_actual,
        "dominancia_eth": float(actual["dominancia_eth"]) if actual["dominancia_eth"] is not None else None,
        "cambio_pp_ventana": cambio_pp,
        "minimo_ventana": round(min(vals), 2) if vals else None,
        "maximo_ventana": round(max(vals), 2) if vals else None,
        "capitalizacion_total": float(actual["capitalizacion_total"]) if actual["capitalizacion_total"] is not None else None,
        "volumen_total": float(actual["volumen_total"]) if actual["volumen_total"] is not None else None,
        "coins_activas_fuente": actual["coins_activas_fuente"],
        "dias": len(vals),
        "dias_pedidos": ventana,
        "_fuente_hasta": actual["fecha"],
    }


# ════════════════════════════════════════════════════════════════════════════
#  DECLARACIÓN
# ════════════════════════════════════════════════════════════════════════════
def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="mercado_dominancia", objeto=Objeto.MERCADO,
        funcion=_dominancia, alcance=Alcance.INDIVIDUAL,
        parametros={"ventana": VENTANA},
        descripcion="Qué parte del mercado es BTC (y ETH), y cómo cambió esa "
                    "proporción sobre la ventana",
        propiedad=Propiedad(unidad="%", direccion=Direccion.CONTEXTUAL,
                            minimo=0, maximo=100),
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="la dominancia actual de BTC y ETH (su capitalización sobre la "
                 "del mercado total, en %), la capitalización y el volumen "
                 "totales, y el cambio de la dominancia de BTC en puntos "
                 "porcentuales sobre la ventana",
            infiere="que una dominancia de BTC en alza describe capital "
                    "refugiándose en BTC, y en baja, rotando hacia alts —la "
                    "lectura que muchos participantes usan como brújula",
            no_sabe="la dominancia es una métrica DERIVADA: su denominador es la "
                    "capitalización total, que depende de cuántas coins cuenta "
                    "CoinGecko. Si ese conteo salta, la dominancia se mueve sin "
                    "que los precios cambien —por eso se reporta "
                    "coins_activas_fuente—. No dice hacia dónde va el precio, y "
                    "la historia arrancó cuando empezó a capturarse /global",
            fuente="coingecko:global (endpoint /global, mapeo en fuentes.yaml)",
            metodo="última fila de mercado_global; cambio = dominancia hoy − "
                   "dominancia del día más viejo de la ventana, en pp")))

    registro.registrar(Compuesta(
        nombre="btc_estado", objeto=Objeto.MERCADO,
        operacion="reunir",
        componentes=["btc_perfil", "btc_funding", "btc_opciones",
                     "mercado_dominancia"],
        # Sin `parametros` propios: el estado es una reunión de fotos y cada
        # componente usa su propia noción de ventana (funding y dominancia miran
        # `dias`, perfil mira `ventana`, opciones el último día). Forzar una
        # ventana común rompía la propagación —el motor valida estricto y
        # btc_funding no admite `ventana`, admite `dias`—.
        descripcion="El estado de Bitcoin en una lectura: comportamiento, "
                    "presión en derivados, posicionamiento en opciones y reparto "
                    "del mercado",
        propiedad=Propiedad(unidad="estado", direccion=Direccion.CONTEXTUAL),
        # La compuesta vence cuando vence su componente MÁS volátil: dominancia y
        # funding se refrescan con las coins (cada 6h), no sólo al cierre diario.
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="cuatro caras del estado de BTC, cada una con su propia "
                 "declaración: el perfil de comportamiento (5 dimensiones), la "
                 "presión del funding, el posicionamiento en opciones (put/call "
                 "y max-pain) y la dominancia de mercado",
            no_sabe="NO produce una etiqueta ni un 'régimen', y es deliberado: "
                    "colapsar cuatro lecturas independientes en una sola palabra "
                    "destruye lo que cada una aporta. btc_estado ES sus partes; "
                    "el que lee decide qué pesa. Ninguna de las cuatro predice el "
                    "precio, y sus límites individuales (heredados) siguen "
                    "valiendo: funding y opciones son de Deribit, el perfil es de "
                    "Binance, la dominancia es un cociente derivado",
            metodo="reunir, no clasificar —igual que btc_perfil—: el estado es "
                   "la reunión de capacidades que ya se miden por separado, cada "
                   "una declarando lo suyo. Composición anidada: btc_perfil trae "
                   "adentro sus 5 dimensiones")))

    logger.info("[capacidades] mercado: dominancia, btc_estado (compuesta)")
