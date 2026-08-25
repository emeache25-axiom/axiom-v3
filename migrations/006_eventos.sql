-- AXIOM v3 — Migración 006
-- Cuándo ocurrió cada evento.
--
-- ═══ POR QUÉ HACE FALTA ═════════════════════════════════════════════════════
--
--   Una capacidad puede declarar que vence POR EVENTO —"vale hasta que cierre
--   la vela diaria"— en vez de por tiempo. Eso es lo correcto: es lo que
--   realmente pasa, mientras que "vale 6 horas" es arbitrario.
--
--   Pero para saber si un valor está vigente hay que poder responder: ¿cuándo
--   ocurrió por última vez el evento del que depende? Si el valor se calculó
--   ANTES del último cierre, está vencido.
--
--   El bus publica los eventos pero no deja rastro: vive en memoria y un
--   reinicio lo borra. Sin esta tabla, la vigencia por evento no se puede
--   verificar y habría que degradarla a vigencia por tiempo — perdiendo
--   justamente lo que la hacía honesta.
--
-- ═══ ES TAMBIÉN EL HISTORIAL DE HECHOS ══════════════════════════════════════
--
--   Además de resolver la vigencia, responde preguntas que el monitor necesita:
--   cuándo fue el último cierre, cuántas veces se publicó algo, si un evento
--   que debía ocurrir no ocurrió.
--
--   Eso último es lo más valioso y lo más difícil: la AUSENCIA de un evento no
--   está en ningún registro por definición. Con esta tabla se detecta
--   comparando contra lo esperado.

CREATE TABLE IF NOT EXISTS eventos (
    id            BIGSERIAL PRIMARY KEY,
    tipo          TEXT        NOT NULL,
    ocurrido_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    origen        TEXT,                    -- quién lo publicó
    datos         JSONB,

    -- Qué pasó con sus consumidores. Un evento publicado cuyos manejadores
    -- fallaron en silencio sería el mismo problema que el try/except de v2.
    suscriptores  SMALLINT,
    fallos        SMALLINT NOT NULL DEFAULT 0
);

COMMENT ON TABLE eventos IS
    'Cuándo ocurrió cada hecho. Necesario para resolver la vigencia POR EVENTO: '
    'un valor calculado antes del último cierre de vela está vencido. El bus '
    'vive en memoria y un reinicio lo borra (migración 006).';

-- La consulta que resuelve la vigencia: "¿cuándo fue el último de este tipo?"
CREATE INDEX IF NOT EXISTS idx_eventos_ultimo
    ON eventos (tipo, ocurrido_at DESC);

ALTER TABLE eventos OWNER TO axiom_user;
