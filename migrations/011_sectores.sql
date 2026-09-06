-- AXIOM v3 — Migración 011
-- El market cap de un sector (categoría de CoinGecko), por día.
--
-- ═══ QUÉ ES Y PARA QUÉ ══════════════════════════════════════════════════════
--
--   HOY guarda UNA sola categoría: `stablecoins`. De ahí sale la señal de
--   sentimiento más transparente que tenemos: la dominancia de stablecoins
--   —market cap del sector / market cap total del mercado—. Sube cuando el
--   capital se refugia en stables (miedo); baja cuando sale hacia riesgo.
--
--   Se mide, no se opina: es un cociente de dos market caps observables, no un
--   índice compuesto con ponderación propietaria (por eso NO se usó el Fear &
--   Greed de terceros: cada fuente lo pondera distinto y no es auditable).
--
-- ═══ POR QUÉ LA TABLA ES GENÉRICA (sector_id, no una columna por stable) ═════
--
--   La misma tabla servirá para "capital por sector" cuando se ataque esa
--   pregunta. Hoy tiene una fila por día (stablecoins); mañana, las categorías
--   que ese análisis pida.
--
--   ADVERTENCIA declarada para el futuro: las categorías de CoinGecko SE
--   SOLAPAN (una coin está en varias) y NO se pueden sumar para repartir el
--   mercado sin doble conteo. Guardar market caps por sector es válido; SUMARLOS
--   como si fueran particiones NO. Eso se resuelve cuando se construya sectores.
--
-- ═══ LA DOMINANCIA NO SE GUARDA, SE CALCULA ═════════════════════════════════
--
--   Se guarda el market_cap del sector. La dominancia (sector / total) la
--   calcula la capacidad al leer, usando `capitalizacion_total` de
--   mercado_global. Guardar el cociente pre-calculado sería redundante y podría
--   desincronizarse de su denominador.

CREATE TABLE IF NOT EXISTS sector_diaria (
    fecha                 DATE NOT NULL,
    sector_id             TEXT NOT NULL,   -- id de la categoría en CoinGecko
    nombre                TEXT,
    market_cap            NUMERIC(30,2),   -- USD
    market_cap_change_24h NUMERIC(16,4),   -- %
    volumen               NUMERIC(30,2),   -- USD, 24h
    fuente                TEXT NOT NULL DEFAULT 'coingecko:categories',
    fuente_updated_at     TIMESTAMPTZ,
    capturado_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fecha, sector_id)
);

COMMENT ON TABLE sector_diaria IS
    'Market cap y volumen de un sector (categoría de CoinGecko) por día. Hoy '
    'solo la categoría stablecoins, para la señal de sentimiento. Preparada '
    'para "capital por sector" (migración 011). Las categorías de CoinGecko se '
    'solapan: NO sumarlas como particiones del mercado.';

COMMENT ON COLUMN sector_diaria.market_cap IS
    'Market cap del sector en USD. La DOMINANCIA (este market_cap sobre el total '
    'de mercado_global) se calcula al leer, no se guarda: evita desincronizar el '
    'cociente de su denominador.';

CREATE INDEX IF NOT EXISTS idx_sector_id_fecha
    ON sector_diaria (sector_id, fecha DESC);

ALTER TABLE sector_diaria OWNER TO axiom_user;
