-- AXIOM v3 — Migración 013
-- Métricas ON-CHAIN de BTC (valuación por costo base), por día.
--
-- ═══ QUÉ ES Y PARA QUÉ ══════════════════════════════════════════════════════
--
--   On-chain mira la CADENA, no los mercados: cuánto vale BTC respecto del
--   costo base agregado de sus tenedores (a qué precio se movieron por última
--   vez las monedas). Responde "¿dónde está el mercado en su ciclo de
--   valuación?" —caro/barato respecto de su historia—, una cara del Estado del
--   Mercado que ninguna otra fuente cubre (funding, opciones, dominancia miran
--   los mercados; esto mira la cadena).
--
--   HOY dos métricas: mvrv_zscore y nupl. La tabla es genérica (metrica+fecha)
--   para sumar SOPR, Puell, etc. sin migrar.
--
-- ═══ POR QUÉ GUARDAMOS LA SERIE (y no solo el último) ═══════════════════════
--
--   La fuente (bitcoin-data.com, free) sólo da los ÚLTIMOS 4 AÑOS: una ventana
--   móvil que cada día olvida el más viejo. Guardando la serie en nuestra
--   tabla, la historia es NUESTRA y no la perdemos cuando salga de la ventana.
--   Y el percentil (¿dónde está hoy contra su historia?) necesita esa serie.
--
-- ═══ FUENTE HONESTA ═════════════════════════════════════════════════════════
--
--   Dato CALCULADO por BGeometrics desde su propio nodo Bitcoin, no medido por
--   nosotros —a diferencia de funding o dominancia, que calculamos de datos
--   crudos observables—. Es confiable (API oficial, metodología pública), pero
--   la capacidad debe declarar que el número viene calculado de terceros.

CREATE TABLE IF NOT EXISTS onchain_diaria (
    fecha        DATE NOT NULL,
    metrica      TEXT NOT NULL,       -- 'mvrv_zscore', 'nupl', …
    valor        NUMERIC(20,8),
    fuente       TEXT NOT NULL DEFAULT 'bitcoin-data.com',
    capturado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fecha, metrica)
);

COMMENT ON TABLE onchain_diaria IS
    'Métricas on-chain de BTC (MVRV Z-Score, NUPL, …) por día, de '
    'bitcoin-data.com. Se guarda la serie porque la fuente free sólo expone 4 '
    'años móviles. Dato calculado por terceros desde su nodo, no medido por '
    'AXIOM (migración 013).';

COMMENT ON COLUMN onchain_diaria.valor IS
    'Valor de la métrica ese día, tal como lo da la fuente. El percentil (dónde '
    'está hoy contra su historia) lo calcula la capacidad al leer.';

CREATE INDEX IF NOT EXISTS idx_onchain_metrica_fecha
    ON onchain_diaria (metrica, fecha DESC);

ALTER TABLE onchain_diaria OWNER TO axiom_user;
