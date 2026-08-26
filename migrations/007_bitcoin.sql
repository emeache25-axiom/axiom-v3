-- AXIOM v3 — Migración 007
-- Bitcoin como objeto propio.
--
-- ═══ POR QUÉ APARTE Y NO COMO UN PAR MÁS ════════════════════════════════════
--
--   BTC/USDT en MEXC y en CoinEx son PARES OPERABLES: mercados donde el trader
--   puede comprar y vender, con su libro, su spread y su profundidad.
--
--   Esta serie es otra cosa: la REFERENCIA de precio de Bitcoin, traída de
--   Binance, que NO es un exchange operable para AXIOM. Se usa para describir
--   el estado de Bitcoin, no para operarlo.
--
--   Mezclarlas invitaría al error de leer el spread de Binance para decidir
--   una operación en MEXC.
--
-- ═══ LA SERIE NO ES HOMOGÉNEA, Y ESO SE DECLARA ═════════════════════════════
--
--   3.297 velas diarias sin huecos desde el 17/08/2017. Pero medido el
--   26/08/2026, el volumen medio diario por año:
--
--       2017      53 M USD        2021    3.170 M
--       2018     263 M            2022    3.278 M
--       2019     333 M            2023    2.528 M
--       2020     785 M            2024    2.326 M
--
--   El volumen de 2017 es SESENTA VECES menor que el de 2021. Una métrica de
--   volumen o participación calculada sobre todo el período no mide el
--   comportamiento del mercado: mide el crecimiento de Binance y la adopción
--   de USDT.
--
--   Por eso existe `btc_metricas_validas`: la advertencia vive EN EL DATO y no
--   depende de que cada consulta se acuerde.

-- ═══════════════════════════════════════════════════════════════════════════
-- VELAS DIARIAS
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS btc_vela_diaria (
    fecha        DATE PRIMARY KEY,
    apertura     NUMERIC(20,8),
    maximo       NUMERIC(20,8),
    minimo       NUMERIC(20,8),
    cierre       NUMERIC(20,8),
    volumen      NUMERIC(30,8),      -- en BTC, como lo devuelve ccxt
    fuente       TEXT NOT NULL DEFAULT 'binance:BTC/USDT',
    capturado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE btc_vela_diaria IS
    'Serie de referencia de Bitcoin. NO es un par operable: Binance es fuente '
    'de datos, no un exchange donde AXIOM opera (migración 007).';

-- ═══════════════════════════════════════════════════════════════════════════
-- VELAS HORARIAS
-- ═══════════════════════════════════════════════════════════════════════════
--
-- ~80.000 velas para nueve años, unos 80 MB. Habilitan las estadísticas por
-- franja horaria —en qué momento del día ocurre el máximo, con qué frecuencia
-- el máximo llega antes que el mínimo— y la volatilidad intradía, que la vela
-- diaria no puede mostrar.
--
-- Se capturan SOLO para BTC. Para los ~3.000 pares serían millones de filas
-- para responder preguntas que se hacen de a un par: ahí se piden al exchange
-- en el momento.

CREATE TABLE IF NOT EXISTS btc_vela_horaria (
    hora         TIMESTAMPTZ PRIMARY KEY,
    apertura     NUMERIC(20,8),
    maximo       NUMERIC(20,8),
    minimo       NUMERIC(20,8),
    cierre       NUMERIC(20,8),
    volumen      NUMERIC(30,8),
    fuente       TEXT NOT NULL DEFAULT 'binance:BTC/USDT',
    capturado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_btc_horaria_dia
    ON btc_vela_horaria (CAST(hora AS DATE));

-- ═══════════════════════════════════════════════════════════════════════════
-- DESDE CUÁNDO ES COMPARABLE CADA TIPO DE MÉTRICA
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS btc_metricas_validas (
    tipo             TEXT PRIMARY KEY,
    comparable_desde DATE NOT NULL,
    motivo           TEXT NOT NULL
);

INSERT INTO btc_metricas_validas (tipo, comparable_desde, motivo) VALUES
 ('precio', '2017-08-17',
  'La serie completa. El precio es comparable en todo el período: lo que cambia es su escala, no su significado.'),
 ('volatilidad', '2017-08-17',
  'Se calcula sobre retornos relativos, así que el cambio de escala del precio no la afecta. Con la salvedad de que 2017-2018 fue un mercado mucho menos líquido y su volatilidad refleja eso.'),
 ('volumen', '2020-01-01',
  'MEDIDO: el volumen medio diario de 2017 fue 53 M USD contra 3.170 M en 2021, sesenta veces menos. Antes de 2020 una métrica de volumen mide el crecimiento de Binance y la adopción de USDT, no el mercado.'),
 ('participacion', '2020-01-01',
  'Misma razón que el volumen: cualquier ratio con volumen en el numerador o el denominador arrastra el cambio de escala.'),
 ('ciclo', '2017-08-17',
  'DOS ciclos observables con esta serie: 2018-2021 y 2022-2025. El de 2012-2016 queda fuera. Con n=2 se puede DESCRIBIR qué pasó, no verificar un patrón: cualquier modelo de fases ajustado a dos casos es sobreajuste. Y el ciclo 2018-2021 tuvo la liquidez creciendo un orden de magnitud por debajo, así que ni siquiera esos dos casos son comparables entre sí.')
ON CONFLICT (tipo) DO UPDATE SET
    comparable_desde = EXCLUDED.comparable_desde,
    motivo           = EXCLUDED.motivo;

COMMENT ON TABLE btc_metricas_validas IS
    'Desde cuándo cada tipo de métrica es comparable sobre la serie de BTC. '
    'La advertencia vive en el dato porque lo que hay que recordar se olvida '
    '(migración 007).';

-- ═══════════════════════════════════════════════════════════════════════════
-- HALVINGS
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Lo ÚNICO verificable del ciclo. Están en el protocolo: ocurren cada 210.000
-- bloques y los futuros se pueden estimar. "Faltan N días para el próximo
-- halving" es un dato MEDIDO, sin ambigüedad.
--
-- Lo que NO es verificable es que el ciclo se repita. El halving corta la
-- emisión a la mitad —eso es un hecho del protocolo, no una observación
-- estadística— pero su impacto se diluye: pasar de 900 a 450 BTC diarios sobre
-- un mercado de un billón de dólares pesa mucho menos que en 2012 sobre uno de
-- millones. La misma regla produce efectos cada vez más chicos.

CREATE TABLE IF NOT EXISTS btc_halvings (
    numero      SMALLINT PRIMARY KEY,
    fecha       DATE NOT NULL,
    bloque      INTEGER,
    recompensa  NUMERIC(12,8),      -- BTC por bloque DESPUÉS del halving
    estimado    BOOLEAN NOT NULL DEFAULT false
);

INSERT INTO btc_halvings (numero, fecha, bloque, recompensa, estimado) VALUES
 (1, '2012-11-28',  210000, 25,       false),
 (2, '2016-07-09',  420000, 12.5,     false),
 (3, '2020-05-11',  630000,  6.25,    false),
 (4, '2024-04-19',  840000,  3.125,   false),
 (5, '2028-04-01', 1050000,  1.5625,  true)
ON CONFLICT (numero) DO NOTHING;

COMMENT ON COLUMN btc_halvings.estimado IS
    'El futuro es estimado: su fecha depende del tiempo real de bloque, que '
    'varía con el hashrate. Los pasados son hechos.';

ALTER TABLE btc_vela_diaria      OWNER TO axiom_user;
ALTER TABLE btc_vela_horaria     OWNER TO axiom_user;
ALTER TABLE btc_metricas_validas OWNER TO axiom_user;
ALTER TABLE btc_halvings         OWNER TO axiom_user;
