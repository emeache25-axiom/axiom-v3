-- AXIOM v3 — Migración 001
-- El crudo, el universo de coins y su historia diaria.
--
-- ═══ PRINCIPIOS QUE ESTE ESQUEMA APLICA ═════════════════════════════════════
--
--   1. LA RESPUESTA CRUDA SE GUARDA donde hay valor histórico. Un campo que hoy
--      no se mapea, mañana está disponible — incluso hacia atrás. En v2 un
--      campo no mapeado era irrecuperable: había que volver a pedir todo, y
--      para datos históricos eso es imposible.
--
--   2. TODO DATO DECLARA SU FRESCURA. `fuente_updated_at` (cuándo lo actualizó
--      la fuente) es distinto de `capturado_at` (cuándo lo guardamos nosotros).
--      Confundirlos hizo que v2 mostrara variaciones de julio como si fueran
--      de hoy.
--
--   3. ESTADO Y SEGUIMIENTO SON EJES INDEPENDIENTES. Salir del top 2.000 NO es
--      estar inactiva. Medido en v2: de 558 coins con datos viejos, 533 estaban
--      VIVAS — solo estaban fuera del alcance del sync. Marcarlas inactivas por
--      antigüedad habría dado de baja 533 coins vivas.
--
--   4. PRECISIÓN SUFICIENTE. En v2, `numeric(24,8)` redondeaba a CERO los
--      precios de coins con supply enorme, y `numeric(8,4)` desbordaba con
--      variaciones de cuatro dígitos. Los dos errores rompieron el sync durante
--      semanas sin que nada avisara.
--
-- FUENTE DE COINS: CoinGecko, única. No hay competencia de fuentes ni
-- precedencias que declarar. (Los PARES son otra cosa: ahí el exchange es parte
-- de la identidad — un par en MEXC y el mismo en CoinEx son objetos distintos.)

-- ═══════════════════════════════════════════════════════════════════════════
-- CAPTURAS: la respuesta cruda, tal como vino
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Genérica a propósito: cada fuente devuelve una estructura distinta, así que
-- acá no hay columnas por campo. Lo que interpreta cada estructura es el MAPEO,
-- que se declara por fuente en el código.
--
-- QUÉ SE GUARDA Y QUÉ NO — decisión medida:
--   Guardar el crudo de CADA refresco de precios serían ~9 GB al año (11
--   páginas × 4 corridas diarias × ~200 KB). No lo vale: los refrescos intradía
--   se sobrescriben igual, su crudo no aporta.
--   Se guarda el crudo de lo que tiene VALOR HISTÓRICO: el snapshot diario.
--   ~800 MB al año, y es el que permite responder preguntas del pasado.

CREATE TABLE IF NOT EXISTS capturas (
    id            BIGSERIAL PRIMARY KEY,
    fuente        TEXT        NOT NULL,     -- 'coingecko', 'mexc', 'coinex'
    endpoint      TEXT        NOT NULL,     -- 'mercados', 'inventario', 'global'
    parametros    JSONB,                    -- con qué se pidió (page, ids…)

    -- Cuándo. Los DOS, porque son cosas distintas.
    pedido_at     TIMESTAMPTZ NOT NULL,     -- cuándo se hizo la llamada
    fuente_hasta  TIMESTAMPTZ,              -- hasta cuándo dice la fuente que llegan sus datos

    crudo         JSONB       NOT NULL,     -- la respuesta ENTERA, sin tocar
    items         INTEGER,                  -- cuántos elementos trajo (si es colección)
    intentos      SMALLINT    NOT NULL DEFAULT 1
);

COMMENT ON TABLE capturas IS
    'Respuestas crudas de las fuentes, tal como vinieron. Existe para que un '
    'campo no mapeado hoy esté disponible mañana, incluso para datos '
    'históricos — y para detectar si una fuente cambia su formato, cosa que en '
    'v2 se leía como NULL sin que nadie se enterara (migración 001).';

CREATE INDEX IF NOT EXISTS idx_capturas_fuente
    ON capturas (fuente, endpoint, pedido_at DESC);


-- ═══════════════════════════════════════════════════════════════════════════
-- COINS: el universo
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS coins (
    id                TEXT PRIMARY KEY,          -- el id de CoinGecko
    symbol            TEXT NOT NULL,
    nombre            TEXT NOT NULL,

    -- ── Estado: lo dice la FUENTE ────────────────────────────────────────
    -- Un activo inactivo NO se considera en ninguna capacidad. Se conserva:
    -- es historia. Y la inactivación NO se revierte automáticamente — no hay
    -- precedente de una coin que vuelva del listado, y tratar la reaparición
    -- como reactivación dejaría que un fallo puntual de la fuente resucite
    -- datos muertos.
    estado            TEXT NOT NULL DEFAULT 'activa'
                      CHECK (estado IN ('activa', 'inactiva')),
    estado_desde      DATE,
    estado_motivo     TEXT,

    -- ── Seguimiento: lo decidimos NOSOTROS ───────────────────────────────
    -- Independiente del estado. Una coin puede estar viva y fuera de nuestro
    -- criterio de seguimiento, y eso NO la hace inactiva.
    seguida           BOOLEAN NOT NULL DEFAULT false,
    seguida_desde     DATE,
    seguida_motivo    TEXT,                      -- 'top_2000', 'watchlist', 'manual'

    -- ── Datos de mercado ─────────────────────────────────────────────────
    -- numeric(30,12): en v2, (24,8) redondeaba a CERO los precios de coins con
    -- supply de 1e19. Un precio de 0 es un dato falso que se ve plausible.
    precio            NUMERIC(30,12),
    capitalizacion    NUMERIC(30,2),
    volumen           NUMERIC(30,2),
    puesto            INTEGER,
    -- numeric(16,4): en v2, (8,4) DESBORDABA con variaciones de cuatro cifras
    -- (una coin nueva puede hacer +71.349 % legítimamente) y el sync fallaba
    -- entero, reportándose como exitoso.
    variacion_24h     NUMERIC(16,4),
    variacion_7d      NUMERIC(16,4),

    -- ── Clasificación ────────────────────────────────────────────────────
    sector            TEXT,
    categorias        JSONB,                     -- las de la fuente, sin tocar

    -- ── Frescura ─────────────────────────────────────────────────────────
    fuente_updated_at TIMESTAMPTZ,               -- lo que dice la fuente
    capturado_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    creado_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON COLUMN coins.estado IS
    'activa | inactiva. Lo dice la FUENTE: inactiva = CoinGecko dejó de '
    'listarla. NO se infiere de la antigüedad de los datos — medido: 533 de '
    '558 coins con datos viejos estaban vivas.';

COMMENT ON COLUMN coins.seguida IS
    'Si la observamos. Independiente de `estado`: salir del top 2.000 no es '
    'estar inactiva.';

CREATE INDEX IF NOT EXISTS idx_coins_estado    ON coins (estado);
CREATE INDEX IF NOT EXISTS idx_coins_seguida   ON coins (seguida) WHERE seguida;
CREATE INDEX IF NOT EXISTS idx_coins_puesto    ON coins (puesto NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_coins_sector    ON coins (sector);


-- ═══════════════════════════════════════════════════════════════════════════
-- COIN_DIARIA: la historia
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Una foto por día. Es lo IRRECUPERABLE: CoinGecko no devuelve el ranking de
-- hace un mes, ni la capitalización de un sector en una fecha pasada. Si no se
-- captura hoy, ese día no existe nunca más.
--
-- Es lo que sostiene las preguntas de la capa de INVESTIGACIÓN: rotación de
-- capital, movimientos en el ranking, qué entró y salió del top N.

CREATE TABLE IF NOT EXISTS coin_diaria (
    fecha             DATE NOT NULL,             -- día UTC
    coin_id           TEXT NOT NULL,
    symbol            TEXT,

    precio            NUMERIC(30,12),
    capitalizacion    NUMERIC(30,2),
    volumen           NUMERIC(30,2),
    puesto            INTEGER,
    variacion_24h     NUMERIC(16,4),
    variacion_7d      NUMERIC(16,4),
    sector            TEXT,

    fuente_updated_at TIMESTAMPTZ,
    capturado_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    captura_id        BIGINT REFERENCES capturas(id),  -- ← de qué crudo salió

    PRIMARY KEY (fecha, coin_id)
);

COMMENT ON COLUMN coin_diaria.captura_id IS
    'La captura cruda de la que salió esta fila. Permite reinterpretar el '
    'pasado si mañana se mapea un campo nuevo, sin volver a pedir nada.';

CREATE INDEX IF NOT EXISTS idx_coin_diaria_coin   ON coin_diaria (coin_id, fecha DESC);
CREATE INDEX IF NOT EXISTS idx_coin_diaria_fecha  ON coin_diaria (fecha);
CREATE INDEX IF NOT EXISTS idx_coin_diaria_sector ON coin_diaria (fecha, sector);


-- ═══════════════════════════════════════════════════════════════════════════
-- INVENTARIO: qué existe, según la fuente
-- ═══════════════════════════════════════════════════════════════════════════
--
-- CoinGecko /coins/list devuelve TODAS las coins que conoce —18.518 al
-- 18/08/2026— en una sola llamada y sin API key.
--
-- Comparar contra esto detecta altas y bajas de forma INEQUÍVOCA. En v2 no
-- existía, y por eso "salió del top 2.000" se confundía con "está muerta": la
-- única señal disponible era la ausencia en un listado paginado, que no
-- distingue una cosa de la otra.

CREATE TABLE IF NOT EXISTS inventario (
    fuente      TEXT NOT NULL,
    id          TEXT NOT NULL,
    symbol      TEXT,
    nombre      TEXT,

    visto_desde DATE NOT NULL,        -- primera vez que apareció
    visto_hasta DATE NOT NULL,        -- última vez que se la vio en la lista
    presente    BOOLEAN NOT NULL DEFAULT true,

    PRIMARY KEY (fuente, id)
);

COMMENT ON TABLE inventario IS
    'Qué existe según cada fuente. `visto_hasta` con `presente=false` es una '
    'BAJA inequívoca: la fuente dejó de listarla (migración 001).';

CREATE INDEX IF NOT EXISTS idx_inventario_presente
    ON inventario (fuente, presente);


-- ═══════════════════════════════════════════════════════════════════════════
-- UNIVERSO_EVENTOS: altas, bajas y cambios de estado
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Las altas y bajas son información en sí misma: un exchange listando veinte
-- pares nuevos en una semana dice algo del mercado, y en v2 no quedaba rastro.
--
-- Y sirve de auditoría: si algo se marcó inactivo por error, queda el registro
-- de cuándo y con qué evidencia.

CREATE TABLE IF NOT EXISTS universo_eventos (
    id         BIGSERIAL PRIMARY KEY,
    ts         TIMESTAMPTZ NOT NULL DEFAULT now(),
    tipo       TEXT NOT NULL
               CHECK (tipo IN ('alta', 'baja', 'cambio_estado',
                               'inicio_seguimiento', 'fin_seguimiento')),
    objeto     TEXT NOT NULL CHECK (objeto IN ('coin', 'par')),
    objeto_id  TEXT NOT NULL,
    detalle    JSONB,
    evidencia  TEXT NOT NULL     -- por qué: sin esto, un estado es una afirmación sin respaldo
);

CREATE INDEX IF NOT EXISTS idx_universo_eventos_ts     ON universo_eventos (ts DESC);
CREATE INDEX IF NOT EXISTS idx_universo_eventos_objeto ON universo_eventos (objeto, objeto_id, ts DESC);


ALTER TABLE capturas         OWNER TO axiom_user;
ALTER TABLE coins            OWNER TO axiom_user;
ALTER TABLE coin_diaria      OWNER TO axiom_user;
ALTER TABLE inventario       OWNER TO axiom_user;
ALTER TABLE universo_eventos OWNER TO axiom_user;
