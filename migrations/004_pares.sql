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


-- ═══════════════════════════════════════════════════════════════════════════
-- MÉTRICAS DEL PAR
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Derivadas de las velas. Se guardan —en vez de calcularse al vuelo— porque se
-- usan para COMPARAR y FILTRAR miles de pares entre sí: es el criterio de la
-- arquitectura para decidir qué va precalculado.
--
-- `hasta_fecha` NO es opcional: en v2, métricas calculadas hasta hace 20 días
-- se mostraban junto a otras del día anterior sin que nada las distinguiera.
-- Un número sin su fecha de corte no es comparable.

CREATE TABLE IF NOT EXISTS par_metricas (
    par_id            BIGINT PRIMARY KEY REFERENCES pares(id) ON DELETE CASCADE,

    -- Hasta qué vela llegan estas métricas y sobre cuántas se calcularon.
    hasta_fecha       DATE NOT NULL,
    velas_usadas      SMALLINT NOT NULL,
    ventana_dias      SMALLINT NOT NULL,

    -- El día TÍPICO. Mediana, no promedio: en v2 el promedio ponía COLAPSOS en
    -- la cabecera — ARCIELUSDT tenía promedio 219,94 % contra mediana 0,46 %,
    -- un par plano encabezando el ranking por un único día de 6.118 %.
    rango_tipico      NUMERIC(12,4),
    rango_promedio    NUMERIC(12,4),   -- solo para calcular el ratio
    rango_ratio       NUMERIC(12,4),   -- promedio/típico: alto = hubo evento o dato roto

    -- 1 − Efficiency Ratio en logaritmos. Separa el par que VA Y VUELVE del
    -- que se desploma. Medido: correlación 0,049 con el rango — es una
    -- dimensión INDEPENDIENTE, no una variante de lo mismo.
    oscilacion        NUMERIC(8,4),

    -- Curva de repetibilidad, no un número: medido en v2, el umbral de 3 % lo
    -- supera el 53 % del universo en más del 80 % de los días. Discrimina
    -- desde 5 %.
    dias_sobre_1pct   NUMERIC(6,2),
    dias_sobre_2pct   NUMERIC(6,2),
    dias_sobre_3pct   NUMERIC(6,2),
    dias_sobre_5pct   NUMERIC(6,2),
    dias_sobre_8pct   NUMERIC(6,2),

    calculado_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN par_metricas.rango_promedio IS
    'NO comparable entre pares: un solo día excepcional lo distorsiona. Existe '
    'solo para calcular rango_ratio. Ordenar por él pone colapsos arriba.';

COMMENT ON COLUMN par_metricas.hasta_fecha IS
    'Hasta qué vela llegan. Sin esto, una métrica de hace 20 días se ve igual '
    'que una de ayer — pasó en v2.';

CREATE INDEX IF NOT EXISTS idx_metricas_rango ON par_metricas (rango_tipico DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_metricas_osc   ON par_metricas (oscilacion DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_metricas_hasta ON par_metricas (hasta_fecha);


ALTER TABLE pares        OWNER TO axiom_user;
ALTER TABLE vela_diaria  OWNER TO axiom_user;
ALTER TABLE par_metricas OWNER TO axiom_user;
