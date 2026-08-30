-- AXIOM v3 — Migración 009
-- El funding del perpetuo de BTC: qué cuesta mantener una posición apalancada.
--
-- ═══ POR QUÉ DERIBIT Y NO BINANCE ═══════════════════════════════════════════
--
--   Se evaluaron seis exchanges de perpetuos el 29/08/2026. LOS SEIS tienen el
--   funding saturado en 0,0100 %: no es una peculiaridad de ninguno, es la
--   tasa base del mecanismo. Cuando la prima del perpetuo sobre el índice es
--   chica, el funding se fija ahí.
--
--       binance   valor más repetido 0,0100 %  ( 8 % de los registros)
--       bybit                                   14 %
--       okx                                     12 %
--       bitget                                  25 %
--       gate                                    12 %
--       kucoin                                  28 %
--
--   Y sobre siete años de Binance, el 35,4 % de los registros están
--   exactamente en 0,0100 %. Eso crea un ESCALÓN enorme en el medio de la
--   distribución: el percentil 40 y el 70 son el mismo valor, y la medida no
--   discrimina justo donde el mercado pasa más tiempo.
--
--   Deribit NO satura: su perpetuo es INVERSO —denominado en dólares con
--   margen en BTC— y calcula el funding con otro mecanismo. Medido: su valor
--   más repetido aparece en el 7 % de los registros, contra 8-28 % del resto.
--
--   Además es HORARIO, no cada 8 horas: tres veces más resolución.
--
--   Contrapartida: empieza en enero de 2020 contra septiembre de 2019 en
--   Binance. Seis años y medio alcanzan para el percentil.
--
-- ═══ QUÉ SIGNIFICA Y QUÉ NO ═════════════════════════════════════════════════
--
--   El funding es lo que pagan los largos a los cortos —o al revés— para que
--   el perpetuo siga al precio al contado. Positivo = los largos pagan, o sea
--   hay más presión compradora apalancada.
--
--   NO dice quién va a ganar. Un funding alto sostenido puede preceder una
--   caída —demasiado apalancamiento— o simplemente reflejar una tendencia
--   fuerte que sigue.

CREATE TABLE IF NOT EXISTS funding_btc (
    hora         TIMESTAMPTZ PRIMARY KEY,
    tasa         NUMERIC(12,8) NOT NULL,   -- fracción por período, no %
    fuente       TEXT NOT NULL DEFAULT 'deribit:BTC/USD:BTC',
    capturado_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE funding_btc IS
    'Funding horario del perpetuo inverso de BTC en Deribit. Se eligió sobre '
    'Binance porque no satura en la tasa base de 0,01 % —los seis exchanges de '
    'perpetuos lineales sí lo hacen— y porque es horario (migración 009).';

COMMENT ON COLUMN funding_btc.tasa IS
    'En FRACCIÓN, no en porcentaje: 0,0001 = 0,01 %. Guardar la unidad de la '
    'fuente evita el error que en v2 hizo que un umbral en porcentaje se '
    'comparara contra un valor en fracción — cien veces de diferencia, y la '
    'señal nunca alcanzaba su primer escalón.';

CREATE INDEX IF NOT EXISTS idx_funding_dia
    ON funding_btc (CAST(hora AS DATE));

ALTER TABLE funding_btc OWNER TO axiom_user;
