-- AXIOM v3 — Migración 005
-- Dónde viven los resultados de las capacidades.
--
-- ═══ POR QUÉ GENÉRICA Y NO UNA COLUMNA POR CAPACIDAD ════════════════════════
--
--   Porque el copiloto va a poder CREAR capacidades.
--
--   Con una columna por capacidad, crear una desde la UI implicaría un
--   ALTER TABLE en producción: la aplicación modificando su propio esquema en
--   caliente. Un error de tipeo agregaría una columna que después nadie borra,
--   y el esquema dejaría de reflejar un diseño para reflejar una acumulación.
--
--   Acá una capacidad nueva son filas, nunca esquema.
--
--   Se conoce la contrapartida: filtrar por varias capacidades a la vez exige
--   pivotear, y el screener hace exactamente eso. Se mide antes de dar el
--   modelo por bueno; si se degrada, la respuesta son índices o vistas
--   materializadas para las más consultadas, no volver a columnas.
--
-- ═══ EL VALOR NUNCA VIAJA SOLO ══════════════════════════════════════════════
--
--   Cada fila trae su procedencia: cuándo se calculó, hasta qué dato llegan
--   sus insumos, hasta cuándo vale, y con cuántos componentes se hizo.
--
--   No es opcional cuando el consumidor es un modelo que razona: un número sin
--   su frescura lo toma como verdad y construye encima. En v2 métricas
--   calculadas hasta hacía 20 días se mostraban junto a otras del día anterior
--   sin que nada las distinguiera.

CREATE TABLE IF NOT EXISTS valores (
    id            BIGSERIAL PRIMARY KEY,

    capacidad     TEXT NOT NULL,
    -- Sobre qué. `objeto` dice de qué clase es —par, coin, conjunto— y
    -- `objeto_id` cuál: el id del par, el id de la coin, el nombre del sector.
    objeto        TEXT NOT NULL,
    objeto_id     TEXT NOT NULL,

    -- Con qué parámetros se calculó. Dos resultados de la misma capacidad con
    -- ventanas distintas son valores DISTINTOS, no uno que reemplaza al otro.
    args          JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- El valor. numeric para lo que se compara y ordena; jsonb para lo que no
    -- es un número —una lectura de régimen, una curva de repetibilidad—.
    valor_num     NUMERIC(30,12),
    valor_json    JSONB,

    -- ── Procedencia ───────────────────────────────────────────────────────
    calculado_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Hasta qué dato llegan los INSUMOS. Distinto de calculado_at: si se
    -- calcula a las 15:00 con velas hasta ayer, la métrica cubre HASTA AYER.
    -- Eso es lo que se muestra, no la hora del cálculo.
    fuente_hasta  TIMESTAMPTZ,
    vigente_hasta TIMESTAMPTZ,          -- si vence por tiempo
    vigente_evento TEXT,                -- si vence por evento

    -- Para compuestas: con cuántas partes se calculó. Un régimen con 10 de 12
    -- señales se lee distinto de uno completo.
    componentes_esperados   SMALLINT,
    componentes_disponibles SMALLINT,

    -- Lo que el motor detectó: valor fuera del rango declarado, ventana
    -- incompleta, componentes faltantes.
    advertencias  JSONB,

    UNIQUE (capacidad, objeto, objeto_id, args)
);

COMMENT ON TABLE valores IS
    'Resultados de capacidades. Genérica a propósito: el copiloto va a poder '
    'crear capacidades, y con una columna por capacidad eso exigiría ALTER '
    'TABLE en producción (migración 005).';

COMMENT ON COLUMN valores.args IS
    'Los parámetros del cálculo. Parte de la clave: rango_tipico con ventana 30 '
    'y con ventana 90 son valores distintos, no uno que pisa al otro.';

COMMENT ON COLUMN valores.fuente_hasta IS
    'Hasta qué dato llegan los insumos. Distinto de calculado_at — en v2 se '
    'confundían y métricas de hace 20 días se veían igual que las de ayer.';

-- El uso principal: "dame esta capacidad para estos objetos".
CREATE INDEX IF NOT EXISTS idx_valores_cap
    ON valores (capacidad, objeto, objeto_id);

-- El screener: filtrar y ordenar por una capacidad numérica sobre todo un
-- objeto. Es la consulta que decide si el modelo genérico aguanta.
CREATE INDEX IF NOT EXISTS idx_valores_orden
    ON valores (capacidad, objeto, valor_num DESC NULLS LAST)
    WHERE valor_num IS NOT NULL;

-- "¿Qué está vencido?"
CREATE INDEX IF NOT EXISTS idx_valores_vigencia
    ON valores (capacidad, vigente_hasta) WHERE vigente_hasta IS NOT NULL;

ALTER TABLE valores OWNER TO axiom_user;
