-- AXIOM v3 — Migración 008
-- La cadena de opciones de BTC: el posicionamiento.
--
-- ═══ POR QUÉ FOTO DIARIA Y NO CONSULTA AL PEDIDO ════════════════════════════
--
--   La pregunta que decide es: "¿hoy hay más interés abierto que ayer?"
--
--   Deribit devuelve el estado ACTUAL, no el de hace una semana. Si no se
--   captura hoy, ese día no existe nunca más — el mismo caso que `coin_diaria`.
--
--   Y sin historia no se pueden responder las preguntas que importan:
--     · ¿está creciendo el interés abierto?
--     · ¿se está moviendo de strike? Si migra de 80.000 a 90.000, algo cambió
--     · ¿cambió el sesgo? Más puts que ayer es alguien comprando protección
--
-- ═══ POR QUÉ CONTRATO POR CONTRATO Y NO AGREGADO ════════════════════════════
--
--   Agregar decide de antemano qué se va a poder preguntar. Guardar el detalle
--   deja abiertas preguntas que hoy no imaginamos.
--
--   El costo es bajo: ~1.026 contratos por día son ~375.000 filas al año.
--
-- ═══ QUÉ ES Y QUÉ NO ES EL INTERÉS ABIERTO ══════════════════════════════════
--
--   NO dice de qué lado está cada participante. Un call abierto tiene un
--   comprador y un vendedor; el interés abierto cuenta el CONTRATO, no la
--   dirección.
--
--   Leer "hay mucho interés en calls de 100.000" como "el mercado espera
--   100.000" es un error común: por cada comprador de ese call hay alguien que
--   lo vendió.
--
--   Lo que sí dice es DÓNDE HAY CONCENTRACIÓN, que es distinto y sigue siendo
--   útil.

CREATE TABLE IF NOT EXISTS opcion_diaria (
    fecha         DATE NOT NULL,
    simbolo       TEXT NOT NULL,          -- BTC/USD:BTC-260925-100000-C

    -- Lo que identifica al contrato
    subyacente    TEXT NOT NULL DEFAULT 'BTC',
    vencimiento   DATE NOT NULL,
    strike        NUMERIC(20,2) NOT NULL,
    tipo          TEXT NOT NULL CHECK (tipo IN ('call', 'put')),

    -- El estado
    interes_abierto NUMERIC(20,4),        -- en contratos
    volumen_24h     NUMERIC(20,4),
    -- Volatilidad implícita de ESTE contrato. Es lo que permite ver la
    -- SONRISA: si las puts fuera del dinero están más caras que las calls, el
    -- mercado está pagando por protección.
    iv              NUMERIC(10,4),
    precio_marca    NUMERIC(20,8),

    -- El precio del subyacente al momento de la captura. Sin esto no se puede
    -- saber después qué strikes estaban dentro o fuera del dinero.
    subyacente_precio NUMERIC(20,2),

    capturado_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    fuente        TEXT NOT NULL DEFAULT 'deribit',

    PRIMARY KEY (fecha, simbolo)
);

COMMENT ON TABLE opcion_diaria IS
    'Foto diaria de la cadena de opciones de BTC en Deribit. Existe porque la '
    'pregunta "¿hoy hay más interés abierto que ayer?" necesita tener ayer '
    'guardado, y Deribit solo devuelve el presente (migración 008).';

COMMENT ON COLUMN opcion_diaria.interes_abierto IS
    'Contratos abiertos. NO dice de qué lado está cada participante: por cada '
    'comprador hay un vendedor. Dice dónde hay CONCENTRACIÓN.';

COMMENT ON COLUMN opcion_diaria.subyacente_precio IS
    'El precio de BTC al capturar. Sin esto no se puede reconstruir después '
    'qué strikes estaban dentro o fuera del dinero.';

-- "¿Cómo cambió el interés abierto de este vencimiento?"
CREATE INDEX IF NOT EXISTS idx_opcion_venc
    ON opcion_diaria (vencimiento, fecha);

-- "¿Dónde está concentrado hoy?"
CREATE INDEX IF NOT EXISTS idx_opcion_fecha_strike
    ON opcion_diaria (fecha, strike);

-- La evolución de un contrato puntual
CREATE INDEX IF NOT EXISTS idx_opcion_simbolo
    ON opcion_diaria (simbolo, fecha DESC);

ALTER TABLE opcion_diaria OWNER TO axiom_user;
