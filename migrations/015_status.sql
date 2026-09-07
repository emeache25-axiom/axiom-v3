-- AXIOM v3 — Migración 015
-- El estado de consolidación de un dato on-chain (flash / final).
--
-- ═══ POR QUÉ ════════════════════════════════════════════════════════════════
--
--   Coin Metrics marca los datos recientes como "flash" (preliminar, puede
--   cambiar al consolidarse) y luego los revisa a "final". Es información
--   epistémica que AXIOM no descarta: un flujo de ayer marcado "flash" todavía
--   puede corregirse, y quien lee un dato debe saber si ya está firme.
--
--   Nullable: las métricas de otras fuentes (bitcoin-data) no traen status y
--   quedan en NULL —que se lee como "sin marca de consolidación", no como
--   flash ni final—.

ALTER TABLE onchain_diaria
    ADD COLUMN IF NOT EXISTS status TEXT;

COMMENT ON COLUMN onchain_diaria.status IS
    'Estado de consolidación del dato en la fuente: flash (preliminar, puede '
    'cambiar) o final. Lo trae Coin Metrics; NULL para fuentes que no lo marcan '
    '(migración 015).';
