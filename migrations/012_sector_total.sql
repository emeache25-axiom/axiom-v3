-- AXIOM v3 — Migración 012
-- El market cap total del mercado, capturado JUNTO con cada sector.
--
-- ═══ POR QUÉ ════════════════════════════════════════════════════════════════
--
--   La dominancia de un sector es sector / total. El numerador (market cap del
--   sector) y el denominador (market cap total) deben ser del MISMO instante:
--   una dominancia armada con el sector de hoy y el total de ayer no corresponde
--   a ningún momento real —es un número que no se puede fechar—.
--
--   En vez de un JOIN a mercado_global (que podría tener otra fecha), cada fila
--   de sector_diaria guarda su propio denominador, capturado en el mismo
--   instante. La señal es AUTOCONTENIDA: una fila, una fecha, sin ambigüedad de
--   cuándo. No podemos dudar de cuándo se actualizó un dato que mostramos.

ALTER TABLE sector_diaria
    ADD COLUMN IF NOT EXISTS cap_total_momento NUMERIC(30,2);

COMMENT ON COLUMN sector_diaria.cap_total_momento IS
    'Market cap total del mercado en el MISMO instante en que se capturó este '
    'sector. Hace la dominancia (market_cap/cap_total_momento) calculable de una '
    'sola fila, sin JOIN: numerador y denominador del mismo momento, misma fecha '
    '(migración 012).';
