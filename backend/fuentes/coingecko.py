"""
AXIOM v3 — Fuente: CoinGecko.
════════════════════════════════════════════════════════════════════════════════
DECLARACIÓN, no implementación. Acá no hay `httpx` ni reintentos ni esperas: eso
vive una sola vez en `cliente.py`. Este archivo dice QUÉ ofrece CoinGecko y
CÓMO se mapean sus campos al vocabulario de AXIOM.

POR QUÉ SE ELIGIÓ Y SE SOSTIENE — verificado el 15/08/2026:

  Se evaluaron alternativas. CoinPaprika tiene más llamadas mensuales en su
  nivel gratuito pero **está capado a 2.000 coins**, menos de las que ya
  seguíamos. CoinDesk (ex CryptoCompare) **retiró su nivel gratuito en mayo de
  2026**. CoinMarketCap no da histórico en el gratuito.

  Y el consumo real de AXIOM es bajísimo: unas 960 llamadas al mes contra un
  techo de 10.000. Estamos al 10 %.

  **El cuello de botella nunca fue el proveedor: era el diseño.** v2 pedía 8
  páginas porque alguien escribió 8, no por una restricción.

  (Estos números cambian: conviene reverificarlos antes de decidir de nuevo, no
  darlos por permanentes.)

Ver AXIOM_v3_declaraciones.md §1
"""
from __future__ import annotations

from backend.fuentes.cliente import Fuente, Endpoint, Limites

# ── Límites ──────────────────────────────────────────────────────────────────
# El nivel gratuito ronda 30 llamadas por minuto. Se declara 25 para dejar
# margen: llegar al tope y comerse un 429 cuesta más tiempo que ir un poco más
# lento. El reintento existe igual, pero como red, no como método.
_LIMITES = Limites(
    llamadas_por_minuto=25,
    reintentos=4,
    respeta_retry_after=True,
    espera_base_s=5.0,
    espera_maxima_s=120.0,
    timeout_s=30.0,
)


COINGECKO = Fuente(
    nombre="coingecko",
    base_url="https://api.coingecko.com/api/v3",
    limites=_LIMITES,
    ofrece=("precio", "capitalizacion", "ranking", "categorias",
            "inventario", "dominancia"),
    no_ofrece=("libro", "velas_intradia", "funding", "desbloqueos"),
    endpoints={

        # ── El inventario ────────────────────────────────────────────────────
        "inventario": Endpoint(
            path="/coins/list",
            devuelve="coleccion",
            descripcion=(
                "TODAS las coins que CoinGecko conoce: id, symbol, name. "
                "18.423 al 16/08/2026, sin API key, en una sola llamada. "
                "Es la referencia de EXISTENCIA: comparar contra esto detecta "
                "altas y bajas de forma inequívoca, mucho mejor que deducirlas "
                "de la ausencia en un listado paginado — que fue lo que en v2 "
                "hizo confundir 'salió del top 2000' con 'está muerta'."
            ),
        ),

        # ── Datos de mercado ─────────────────────────────────────────────────
        "mercados": Endpoint(
            path="/coins/markets",
            params_fijos={"vs_currency": "usd", "per_page": 250},
            params_admite=("page", "ids", "order", "price_change_percentage",
                           "sparkline", "category"),
            devuelve="coleccion",
            descripcion=(
                "Precio, capitalización, ranking y variaciones. Paginado de a "
                "250. Admite `ids` separados por coma para pedir coins "
                "concretas sin recorrer el ranking — así se detectó que 533 de "
                "558 coins 'desactualizadas' estaban vivas."
            ),
        ),

        "ficha": Endpoint(
            path="/coins/{id}",
            params_fijos={"localization": "false", "tickers": "false",
                          "market_data": "false", "community_data": "false",
                          "developer_data": "false"},
            devuelve="objeto",
            descripcion=(
                "Ficha de una coin: descripción, categorías, links, génesis. "
                "Devuelve 404 si la coin ya no existe — y ESE 404 es la señal "
                "inequívoca de baja."
            ),
        ),

        "global": Endpoint(
            path="/global",
            devuelve="objeto",
            descripcion=(
                "Agregados del mercado: capitalización total, volumen total y "
                "dominancia por activo. De acá sale `btc_dominance`."
            ),
        ),
    },
)


# ══ Mapeos al vocabulario ════════════════════════════════════════════════════
#
# La respuesta CRUDA se guarda entera; esto solo dice qué campo corresponde a
# qué propiedad. Agregar un campo mañana es agregar una línea acá — y estará
# disponible incluso para lo ya capturado, porque el crudo quedó.
#
# En v2 un campo no mapeado era irrecuperable hacia atrás: había que volver a
# pedir todo, y para datos históricos eso es imposible.

MAPEO_MERCADOS = {
    "id":                                    "id",
    "symbol":                                "symbol",
    "name":                                  "nombre",
    "current_price":                         "precio",
    "market_cap":                            "capitalizacion",
    "market_cap_rank":                       "puesto",
    "total_volume":                          "volumen",
    "price_change_percentage_24h":           "variacion_24h",
    "price_change_percentage_7d_in_currency": "variacion_7d",
    "ath":                                   "maximo_historico",
    "ath_change_percentage":                 "distancia_al_maximo",
    "ath_date":                              "maximo_historico_fecha",
    "circulating_supply":                    "supply_circulante",
    "total_supply":                          "supply_total",
    "max_supply":                            "supply_maximo",
    "last_updated":                          "fuente_updated_at",
}

MAPEO_GLOBAL = {
    "data.total_market_cap.usd":             "capitalizacion_total",
    "data.total_volume.usd":                 "volumen_total",
    "data.market_cap_percentage.btc":        "dominancia_btc",
    "data.market_cap_percentage.eth":        "dominancia_eth",
    "data.active_cryptocurrencies":          "coins_activas_fuente",
    "data.updated_at":                       "fuente_updated_at",
}

MAPEO_FICHA = {
    "id":                                    "id",
    "symbol":                                "symbol",
    "name":                                  "nombre",
    "categories":                            "categorias",
    "description.en":                        "descripcion",
    "genesis_date":                          "fecha_genesis",
    "links.homepage":                        "sitios",
    "hashing_algorithm":                     "algoritmo",
    "last_updated":                          "fuente_updated_at",
}
