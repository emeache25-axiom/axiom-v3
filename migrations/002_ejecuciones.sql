-- AXIOM v3 — Migración 002
-- Registro de ejecuciones: qué corrió, por qué, y qué produjo.
--
-- ═══ QUÉ PROBLEMA RESUELVE ══════════════════════════════════════════════════
--
--   En v2 el patrón era:
--
--       try:
--           ...
--       except Exception as exc:
--           logger.error(f"[scheduler] Error en sync precios: {exc}")
--
--   La excepción se capturaba, se logueaba, y la función devolvía normalmente.
--   APScheduler nunca se enteraba y anotaba "executed successfully". El sync de
--   precios falló en TODAS sus corridas durante semanas y las tres del día
--   figuraban como exitosas.
--
--   Se descubrió auditando datos, no por ninguna alarma.
--
-- ═══ DOS COSAS QUE v2 APRENDIÓ TARDE, Y ACÁ VIENEN DE ENTRADA ═══════════════
--
--   1. `resultado` — la falla PARCIAL no lanza excepción.
--      `sync_prices` devolvía {'updated': 1750} cuando debía devolver 2000:
--      perdía una página entera por un `continue` mal puesto. Técnicamente no
--      falló nada. Ningún `raise` lo habría detectado.
--      Guardar QUÉ DEVOLVIÓ cada corrida y compararlo con las anteriores es la
--      única forma de verlo.
--
--   2. `disparador` — v3 tiene DOS cosas que ejecutan: las tareas del
--      planificador y los manejadores del bus. La foto diaria no es una tarea:
--      la dispara un evento. Registrar solo tareas la dejaría invisible — y es
--      justo lo que más importa que funcione, porque su dato es irrecuperable.
--
--      Este campo permite responder POR QUÉ corrió algo, no solo QUE corrió.
--
-- ═══ EL REGISTRO ES TRANSPARENTE ════════════════════════════════════════════
--
--   Lo escriben el planificador y el bus, no las funciones ejecutadas. En v2
--   registrar dependía de que cada job se acordara, y por eso el observador
--   llegó tarde y a medias. Acá nada queda fuera porque nadie tiene que
--   acordarse.

CREATE TABLE IF NOT EXISTS ejecuciones (
    id           BIGSERIAL PRIMARY KEY,

    -- Qué se ejecutó: 'refrescar_coins', 'foto_diaria_del_universo'…
    que          TEXT        NOT NULL,

    -- POR QUÉ corrió. Es la diferencia con v2, que solo sabía QUE corrió:
    --   'planificador'                  → una tarea temporal
    --   'evento:cierre_vela_diaria'     → reaccionó a un hecho
    --   'manual'                        → alguien lo pidió
    disparador   TEXT        NOT NULL,

    inicio       TIMESTAMPTZ NOT NULL,
    fin          TIMESTAMPTZ NOT NULL DEFAULT now(),
    duracion_seg NUMERIC(10,3),

    estado       TEXT        NOT NULL CHECK (estado IN ('ok', 'error')),

    -- Lo que devolvió. Acá se ven las fallas PARCIALES: un job que devuelve
    -- menos de lo habitual no lanza excepción pero está roto.
    resultado    JSONB,

    error        TEXT,
    traza        TEXT
);

COMMENT ON TABLE ejecuciones IS
    'Una fila por cada cosa que el sistema ejecuta, venga del planificador o '
    'del bus de eventos. Existe porque en v2 el patrón try/except hacía que el '
    'scheduler reportara como exitosos jobs que fallaban en todas sus corridas '
    '(migración 002).';

COMMENT ON COLUMN ejecuciones.disparador IS
    'Por qué corrió: planificador, evento:<tipo>, o manual. v2 solo sabía QUE '
    'corrió; sin esto, lo disparado por eventos quedaría invisible.';

COMMENT ON COLUMN ejecuciones.resultado IS
    'Lo que devolvió. Sirve para detectar fallas PARCIALES: en v2 sync_prices '
    'devolvía 1750 en vez de 2000 sin lanzar ninguna excepción.';

-- "¿Cómo viene esto últimamente?" — el uso principal.
CREATE INDEX IF NOT EXISTS idx_ejecuciones_que
    ON ejecuciones (que, inicio DESC);

-- "¿Qué falló?" — parcial: indexa solo lo que no salió bien, que es una
-- fracción mínima de las filas.
CREATE INDEX IF NOT EXISTS idx_ejecuciones_error
    ON ejecuciones (inicio DESC) WHERE estado <> 'ok';

CREATE INDEX IF NOT EXISTS idx_ejecuciones_disparador
    ON ejecuciones (disparador, inicio DESC);

ALTER TABLE ejecuciones OWNER TO axiom_user;
