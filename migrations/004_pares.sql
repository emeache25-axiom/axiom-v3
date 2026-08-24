-- AXIOM v3 — Migración 004
-- El catálogo de pares y sus velas diarias.
--
-- ═══ EL PAR ES IDENTIDAD COMPLETA ═══════════════════════════════════════════
--
--   Un par es `exchange + base + quote`. ROSE/BTC en MEXC y ROSE/BTC en CoinEx
--   NO son el mismo par en dos lados: son mercados distintos, con su propio
--   libro, su propio spread y su propio precio.
--
--   Medido en v2: el mismo activo puede costar el doble de operar según el
--   quote — BRODIE/USD1 tenía 4,09 % de spread contra 1,77 % de BRODIE/USDT.
--   Tratarlos como uno solo escondería exactamente la decisión que importa:
--   DÓNDE operar.
--
-- ═══ QUÉ SE GUARDA, Y QUÉ NO ════════════════════════════════════════════════
--
--   Se guarda lo IRRECUPERABLE o lo que se necesita a escala:
--     · el catálogo — qué pares existen y en qué estado
--     · las velas DIARIAS — base de rango, oscilación y repetibilidad, y se
--       consultan sobre miles de pares a la vez
--
--   NO se guarda: precios, tickers, libro ni velas intradía. El exchange los
--   devuelve on-demand y se consultan de a un par. Guardarlos sería duplicar
--   su trabajo — y en v2 el libro capturado "por si acaso" llegó a 3,9 GB para
--   DOS pares, el 98 % de toda la base.

-- ═══════════════════════════════════════════════════════════════════════════
-- PARES
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS pares (
    id            BIGSERIAL PRIMARY KEY,

    -- La identidad. `simbolo` es como lo llama el exchange (BTC/USDT en ccxt).
    exchange      TEXT NOT NULL,
    simbolo       TEXT NOT NULL,
    base          TEXT NOT NULL,
    quote         TEXT NOT NULL,

    -- ── Estado: lo dice el EXCHANGE ───────────────────────────────────────
    -- Un par inactivo NO se considera en ninguna capacidad. Se conserva: es
    -- historia. Y la inactivación no se revierte automáticamente.
    estado        TEXT NOT NULL DEFAULT 'activa'
                  CHECK (estado IN ('activa', 'inactiva')),
    estado_desde  DATE,
    estado_motivo TEXT,

    -- ── Vínculo con la coin ───────────────────────────────────────────────
    -- Frágil por naturaleza: hay que adivinar que el símbolo ROSE de MEXC es
    -- `oasis-network` en CoinGecko, y los símbolos se repiten entre proyectos
    -- distintos. En v2 existía `pair_coin_alias` para resolver ambigüedades y
    -- quedó con CERO filas: se creó el lugar y no la forma de decidir.
    --
    -- Acá se guarda el vínculo Y CÓMO se estableció. La vinculación MANUAL es
    -- la verdad; la automática es una sugerencia. Lo automático NUNCA pisa lo
    -- manual.
    coin_id       TEXT REFERENCES coins(id),
    vinculo       TEXT CHECK (vinculo IN ('automatico', 'manual', 'rechazado')),
    vinculo_desde DATE,
    vinculo_nota  TEXT,

    -- ── Metadatos del exchange ────────────────────────────────────────────
    -- Se guardan porque condicionan si un par es operable de verdad: un
    -- mínimo de orden alto puede volver inviable un par por lo demás atractivo.
    precision_precio  SMALLINT,
    precision_cantidad SMALLINT,
    minimo_orden      NUMERIC(30,12),

    capturado_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    creado_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (exchange, simbolo)
);

COMMENT ON TABLE pares IS
    'Un par es exchange+base+quote. El mismo activo en dos exchanges son dos '
    'filas: tienen libro, spread y precio propios (migración 004).';

COMMENT ON COLUMN pares.vinculo IS
    'automatico = coincidencia inequívoca de símbolo · manual = lo decidió el '
    'trader, y es la VERDAD · rechazado = se evaluó y no corresponde. Lo '
    'automático nunca pisa lo manual.';

CREATE INDEX IF NOT EXISTS idx_pares_estado   ON pares (estado);
CREATE INDEX IF NOT EXISTS idx_pares_coin     ON pares (coin_id);
CREATE INDEX IF NOT EXISTS idx_pares_base     ON pares (base);
CREATE INDEX IF NOT EXISTS idx_pares_quote    ON pares (exchange, quote);
CREATE INDEX IF NOT EXISTS idx_pares_sin_vinculo
    ON pares (exchange, base) WHERE coin_id IS NULL AND estado = 'activa';


-- ═══════════════════════════════════════════════════════════════════════════
-- VELAS DIARIAS
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Recuperables del exchange —devuelve 500 de backfill— pero se guardan igual:
-- el screener las consulta sobre MILES de pares a la vez, y pedirlas al vuelo
-- sería inviable por latencia, no por disponibilidad.
--
-- PRECISIÓN: numeric(30,12). En v2, (24,8) redondeaba a CERO precios de pares
-- que cotizan en 1e-08 — verificado: ROSE/BTC vale 8,1622e-08. Un precio de
-- cero es un dato falso que se ve plausible.

CREATE TABLE IF NOT EXISTS vela_diaria (
    par_id      BIGINT NOT NULL REFERENCES pares(id) ON DELETE CASCADE,
    fecha       DATE   NOT NULL,

    apertura    NUMERIC(30,12),
    maximo      NUMERIC(30,12),
    minimo      NUMERIC(30,12),
    cierre      NUMERIC(30,12),
    volumen     NUMERIC(30,8),          -- en moneda BASE, como lo da ccxt

    capturado_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (par_id, fecha)
);

COMMENT ON COLUMN vela_diaria.volumen IS
    'En moneda BASE, que es como lo devuelve ccxt. Para comparar entre pares '
    'hay que multiplicarlo por el cierre: 100 unidades de algo que vale 0,001 '
    'no es lo mismo que 100 de algo que vale 10.';

CREATE INDEX IF NOT EXISTS idx_vela_par   ON vela_diaria (par_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_vela_fecha ON vela_diaria (fecha);


-- NOTA: las MÉTRICAS del par —rango típico, oscilación, repetibilidad— NO
-- están acá a propósito.
--
-- No son captura: son derivaciones sobre datos que ya tenemos, sin ninguna
-- fuente involucrada. En la arquitectura de v3 son CAPACIDADES simples del
-- objeto par, y su forma de persistirse la define el registro de capacidades
-- —el punto 2 del plan—, no esta migración.
--
-- Crear la tabla ahora sería repetir lo de `pair_coin_alias` en v2: el lugar
-- creado sin la forma de usarlo, y cero filas durante meses.
--
-- El VÍNCULO par↔coin sí está en `pares`, porque es parte de armar el catálogo
-- y porque el vínculo manual es un dato del trader, no un cálculo.


ALTER TABLE pares       OWNER TO axiom_user;
ALTER TABLE vela_diaria OWNER TO axiom_user;
