-- AXIOM v3 — Migración 010
-- El estado global del mercado: dominancia, capitalización total, volumen.
--
-- ═══ QUÉ ES Y POR QUÉ ═══════════════════════════════════════════════════════
--
--   La DOMINANCIA de BTC (su capitalización sobre la del mercado total) es una
--   brújula que muchos participantes usan: cuando sube, el capital se refugia
--   en BTC; cuando baja, rota hacia alts. La de stablecoins (implícita: lo que
--   no es BTC ni ETH ni resto) sube cuando el capital sale a refugio.
--
--   Sale del endpoint /global de CoinGecko, YA declarado en fuentes.yaml con su
--   mapeo. Se captura junto con el refresco de coins: misma fuente, misma
--   cadencia, mismo evento de vigencia (refresco_de_coins).
--
-- ═══ QUÉ NO ES ══════════════════════════════════════════════════════════════
--
--   La dominancia es una métrica DERIVADA: CoinGecko la calcula como
--   market_cap(btc) / market_cap(total). El denominador depende de CUÁNTAS
--   coins cuenta CoinGecko —por eso se guarda `coins_activas_fuente`: si ese
--   número salta, el denominador cambió y la dominancia se mueve sin que BTC
--   haya hecho nada—. No dice hacia dónde va el precio; dice cómo se reparte el
--   valor entre BTC y el resto en este momento.
--
--   Una fila por día (la última captura del día gana). No es tick: es la foto
--   diaria del reparto del mercado.

CREATE TABLE IF NOT EXISTS mercado_global (
    fecha                 DATE PRIMARY KEY,
    dominancia_btc        NUMERIC(8,4),    -- % : 47.8206
    dominancia_eth        NUMERIC(8,4),    -- %
    capitalizacion_total  NUMERIC(30,2),   -- USD
    volumen_total         NUMERIC(30,2),   -- USD, 24h
    coins_activas_fuente  INTEGER,         -- denominador implícito de la dominancia
    fuente                TEXT NOT NULL DEFAULT 'coingecko:global',
    fuente_updated_at     TIMESTAMPTZ,
    capturado_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE mercado_global IS
    'Estado global del mercado (dominancia, cap total, volumen) de CoinGecko '
    '/global. Foto diaria, capturada con el refresco de coins (migración 010).';

COMMENT ON COLUMN mercado_global.dominancia_btc IS
    'En PORCENTAJE (47.82 = 47,82 %), tal como lo da la fuente. Es una métrica '
    'derivada: market_cap(btc)/market_cap(total). Su movimiento puede venir del '
    'numerador (BTC) o del denominador (cuántas coins cuenta la fuente).';

COMMENT ON COLUMN mercado_global.coins_activas_fuente IS
    'Cuántas coins contaba CoinGecko al capturar. Es el denominador implícito: '
    'si salta, la dominancia se mueve sin que los precios cambien.';

ALTER TABLE mercado_global OWNER TO axiom_user;
