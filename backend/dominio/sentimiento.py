"""
AXIOM v3 — Sentimiento del mercado, medido (no opinado).
════════════════════════════════════════════════════════════════════════════════
POR QUÉ NO USAMOS UN ÍNDICE DE SENTIMIENTO DE TERCEROS:
  El Fear & Greed (alternative.me, CMC) es un índice COMPUESTO y OPACO: cada
  fuente pondera sus componentes (volatilidad, volumen, redes, encuestas…) con
  una fórmula propietaria y variable, así que el mismo día dan números distintos
  y ninguno declara cómo llega a su número. Eso choca con el principio de AXIOM:
  cada capacidad declara qué mide, cómo y qué no sabe. Un índice que no puede
  declarar su método sería un cuerpo extraño.

  AXIOM muestra lo que SUCEDE, no lo que se cree que sucede. Así que el
  "sentimiento" se lee de señales MEDIDAS y transparentes, cada una declarando
  lo suyo, sin colapsarlas en un número con pesos inventados:

    · dominancia de stablecoins  → capital refugiado (ACÁ)
    · funding                    → presión apalancada (btc_funding)
    · put/call por OI            → cobertura vs. optimismo (btc_opciones)
    · volatilidad en su percentil → miedo suele subir la vol (btc_perfil)

  Esta capacidad mide la PRIMERA. Las otras tres ya se miden en sus capacidades.
  Una lectura compuesta (reunir las cuatro) es un paso futuro, cuando las señales
  estén sueltas como capacidades invocables.

LA DOMINANCIA DE STABLES ES UN COCIENTE OBSERVABLE:
  market cap del sector `stablecoins` / market cap total del mercado. Sube cuando
  el capital se refugia en stables (miedo); baja cuando sale hacia riesgo. Se
  calcula al leer —no se guarda pre-calculada— usando el market cap del sector
  (sector_diaria) y el total (mercado_global).
"""
from __future__ import annotations

import logging

from backend.nucleo.capacidades import (
    registro, Simple, Objeto, Direccion, Epistemico, Propiedad, Vigencia,
    Alcance, Presentacion)

logger = logging.getLogger(__name__)

VENTANA = {"default": 30, "min": 7, "max": 365}
SECTOR_STABLES = "stablecoins"


async def _sentimiento_stables(contexto, ventana=30, **_) -> dict:
    """
    Dominancia de stablecoins y su posición contra su historia reciente.

    dominancia = market_cap(stablecoins) / capitalizacion_total, en %. Se lee de
    sector_diaria (numerador) y mercado_global (denominador), por fecha.
    """
    pool = contexto["pool"]
    async with pool.acquire() as conn:
        # AUTOCONTENIDO: cada fila de sector_diaria guarda su numerador
        # (market_cap del sector) Y su denominador (cap_total_momento), ambos del
        # MISMO instante de captura. La dominancia se calcula de una sola fila,
        # con una sola fecha. Sin JOIN a otra tabla que podría tener otra fecha:
        # un dato que no se sabe de cuándo es, es un dato que miente.
        filas = await conn.fetch(
            """
            SELECT fecha, market_cap AS cap_stables,
                   cap_total_momento AS cap_total
            FROM sector_diaria
            WHERE sector_id = $1
              AND market_cap IS NOT NULL
              AND cap_total_momento IS NOT NULL
              AND cap_total_momento > 0
            ORDER BY fecha DESC
            LIMIT $2
            """,
            SECTOR_STABLES, ventana)

    if not filas:
        return {"valor": None, "dias": 0}

    # Dominancia por día, en %.
    serie = [(f["fecha"], float(f["cap_stables"]) / float(f["cap_total"]) * 100)
             for f in filas]
    # serie viene desc (más nuevo primero).
    fecha_actual, dom_actual = serie[0]
    vals = [d for _, d in serie]

    # Percentil del valor actual dentro de la ventana: fracción de días por
    # debajo. Dominancia ALTA = más miedo; el percentil lo sitúa en su historia.
    menores = sum(1 for d in vals if d < dom_actual)
    percentil = round(menores / len(vals) * 100, 1)  # 0-100, como el resto

    cambio_pp = None
    if len(vals) >= 2:
        cambio_pp = round(dom_actual - vals[-1], 3)  # vs. el más viejo de la ventana

    return {
        "dominancia_stables_pct": round(dom_actual, 3),
        "percentil_actual": percentil,
        "cambio_pp_ventana": cambio_pp,
        "minimo_ventana": round(min(vals), 3),
        "maximo_ventana": round(max(vals), 3),
        "dias": len(vals),
        "dias_pedidos": ventana,
        "_fuente_hasta": fecha_actual,
    }


def declarar() -> None:
    """Se llama una vez al arrancar."""

    registro.registrar(Simple(
        nombre="mercado_sentimiento", objeto=Objeto.MERCADO,
        titulo="Sentimiento (stables)",
        presentacion=Presentacion(tipo="serie_nivel", campos=[
            {"clave": "dominancia_stables_pct", "etiqueta": "Dominancia stables", "formato": "pct"},
            {"clave": "percentil_actual", "etiqueta": "Percentil", "formato": "pct_hist"},
            {"clave": "cambio_pp_ventana", "etiqueta": "Cambio", "formato": "signo"},
            {"clave": "minimo_ventana", "etiqueta": "Mínimo", "formato": "pct"},
            {"clave": "maximo_ventana", "etiqueta": "Máximo", "formato": "pct"},
        ]),
        funcion=_sentimiento_stables, alcance=Alcance.INDIVIDUAL,
        parametros={"ventana": VENTANA},
        descripcion="Sentimiento medido vía dominancia de stablecoins: qué "
                    "parte del mercado está refugiada en stables, y su posición "
                    "contra su historia reciente",
        propiedad=Propiedad(unidad="%", direccion=Direccion.CONTEXTUAL,
                            minimo=0, maximo=100),
        vigencia=Vigencia(evento="refresco_de_coins"),
        epistemico=Epistemico(
            mide="la dominancia de stablecoins —market cap del sector "
                 "'stablecoins' de CoinGecko sobre la capitalización total del "
                 "mercado, en %— y su percentil contra la ventana reciente",
            infiere="que una dominancia de stables en alza describe capital "
                    "refugiándose en stablecoins (aversión al riesgo), y en baja, "
                    "capital saliendo hacia activos de riesgo (apetito). Es UNA "
                    "señal de sentimiento, medida; no el sentimiento completo",
            no_sabe="es SOLO UNA de varias señales de sentimiento —las otras "
                    "(funding, put/call, volatilidad) se leen en sus propias "
                    "capacidades y NO están reunidas acá—. NO es un índice de "
                    "miedo/codicia: deliberadamente no se colapsa en un número "
                    "con pesos inventados, porque eso sería opacar lo que cada "
                    "señal mide. No predice el precio. La historia arrancó cuando "
                    "empezó a capturarse el sector stablecoins",
            fuente="coingecko: sector 'stablecoins' de /coins/categories y "
                   "capitalización total de /global, capturados JUNTOS en la "
                   "misma fila de sector_diaria (mismo instante)",
            metodo="cociente market_cap(stablecoins)/cap_total_momento por día, "
                   "ambos del mismo instante de captura (autocontenido, sin JOIN "
                   "a otra tabla que pudiera tener otra fecha); percentil como "
                   "fracción de días de la ventana por debajo del valor actual")))

    logger.info("[capacidades] mercado: sentimiento (dominancia de stablecoins)")
