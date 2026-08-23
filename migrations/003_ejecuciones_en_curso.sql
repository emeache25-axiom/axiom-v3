-- AXIOM v3 — Migración 003
-- Una ejecución se registra al EMPEZAR, no solo al terminar.
--
-- POR QUÉ:
--   Hasta acá `ejecuciones` se escribía al terminar. Eso deja un agujero: una
--   tarea que arrancó y todavía corre NO APARECE EN NINGÚN LADO. Si la captura
--   de velas tarda cuatro minutos, durante esos cuatro minutos el sistema no
--   puede responder "está corriendo" — solo "no hay nada".
--
--   Y peor: una tarea colgada es indistinguible de una que nunca arrancó.
--
--   El monitor tiene que poder decir tres cosas: qué pasó, QUÉ ESTÁ PASANDO y
--   qué pasará. La del medio necesita esto.
--
-- QUÉ CAMBIA:
--   · se admite el estado 'en_curso'
--   · `fin` y `duracion_seg` pasan a ser opcionales: mientras corre no existen
--   · se agrega `intento`, para el reintento del cierre del día

ALTER TABLE ejecuciones ALTER COLUMN fin DROP NOT NULL;
ALTER TABLE ejecuciones ALTER COLUMN fin DROP DEFAULT;

ALTER TABLE ejecuciones DROP CONSTRAINT IF EXISTS ejecuciones_estado_check;
ALTER TABLE ejecuciones ADD CONSTRAINT ejecuciones_estado_check
    CHECK (estado IN ('en_curso', 'ok', 'error'));

-- Cuál intento es. El cierre del día se reintenta dentro de una ventana de 4 h
-- porque su dato es IRRECUPERABLE: si no se captura, ese día no existe nunca
-- más. Pasadas las 4 h los datos ya derivaron demasiado del cierre real y se
-- declara el hueco en vez de guardar algo distorsionado.
ALTER TABLE ejecuciones ADD COLUMN IF NOT EXISTS intento SMALLINT NOT NULL DEFAULT 1;

COMMENT ON COLUMN ejecuciones.estado IS
    'en_curso | ok | error. `en_curso` existe para que el monitor pueda decir '
    'qué está pasando ahora: sin esto, una tarea colgada es indistinguible de '
    'una que nunca arrancó (migración 003).';

COMMENT ON COLUMN ejecuciones.intento IS
    'Número de intento. El cierre del día se reintenta dentro de una ventana '
    'de 4 h: su dato es irrecuperable.';

-- "¿Qué está corriendo ahora?" — la consulta del monitor.
CREATE INDEX IF NOT EXISTS idx_ejecuciones_en_curso
    ON ejecuciones (inicio DESC) WHERE estado = 'en_curso';
