-- AXIOM v3 — Migración 014
-- Correlación de BTC con mercados tradicionales (S&P 500, oro), por día.
--
-- ═══ QUÉ ES Y PARA QUÉ ══════════════════════════════════════════════════════
--
--   ¿BTC se mueve JUNTO con las acciones/el oro, o independiente? Es una cara
--   del Estado del Mercado: correlación alta con el S&P = BTC actúa como activo
--   de riesgo (risk-on); alta con oro = comportamiento de refugio; baja con
--   ambos = clase propia, desacoplado. Dice qué TIPO de activo está siendo BTC
--   en este momento.
--
--   Genérica por par y ventana: hoy dos pares (btc-sp500, btc-gold) y tres
--   ventanas rolling (30/60/90 obs). El percentil (¿la correlación de hoy es
--   alta o baja contra su historia?) lo calcula la capacidad al leer.
--
-- ═══ FUENTE ═════════════════════════════════════════════════════════════════
--
--   sharpe.ai, correlación de Pearson calculada por ellos sobre precios de
--   terceros. Es un AGREGADOR, no fuente primaria: el número lo computa Sharpe.
--   Para correlación (matemática estándar) es aceptable, y la capacidad lo
--   declara. Se guarda la serie porque el free tier es de ventana móvil y el
--   percentil necesita la historia.

CREATE TABLE IF NOT EXISTS correlacion_diaria (
    fecha        DATE NOT NULL,
    par          TEXT NOT NULL,       -- 'btc-sp500', 'btc-gold'
    ventana      INTEGER NOT NULL,    -- 30, 60, 90 (observaciones del rolling)
    valor        NUMERIC(12,8),       -- correlación de Pearson, -1 a 1
    fuente       TEXT NOT NULL DEFAULT 'sharpe.ai',
    capturado_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (fecha, par, ventana)
);

COMMENT ON TABLE correlacion_diaria IS
    'Correlación de BTC con mercados tradicionales (S&P 500, oro) por día, par y '
    'ventana rolling (30/60/90 obs). Fuente sharpe.ai (agregador, calcula el '
    'Pearson). Se guarda la serie para el percentil (migración 014).';

COMMENT ON COLUMN correlacion_diaria.valor IS
    'Correlación de Pearson (-1 a 1). Alta con S&P = risk-on; alta con oro = '
    'refugio; baja con ambos = desacoplado. Calculada por Sharpe, no por AXIOM.';

CREATE INDEX IF NOT EXISTS idx_correlacion_par_vent_fecha
    ON correlacion_diaria (par, ventana, fecha DESC);

ALTER TABLE correlacion_diaria OWNER TO axiom_user;
