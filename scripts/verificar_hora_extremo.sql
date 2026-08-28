-- ¿POR QUÉ LA PRIMERA HORA DEL DÍA CONCENTRA LOS MÍNIMOS?
-- ═══════════════════════════════════════════════════════════════════════════
--
-- Medido: con el día cortado a las 00 UTC, la hora 0 concentra 109 mínimos de
-- 729 días — 3,59 veces el azar, z = 14,57.
--
-- Pero al cortar el día a las 12 UTC, las horas que destacan son 12, 13 y 14.
-- EL PATRÓN SIGUE AL CORTE, NO AL RELOJ: es un artefacto de dónde definimos
-- que empieza el día.
--
-- HIPÓTESIS de por qué ocurre, escritas antes de medir:
--
--   H1  ARRASTRE DE TENDENCIA. Si el precio viene cayendo, el mínimo del día
--       nuevo tiende a formarse temprano —hereda el nivel bajo del día
--       anterior— y si sigue cayendo, tarde. Predicción: el efecto es MUCHO
--       más fuerte en días bajistas que en alcistas.
--
--   H2  SI H1 ES CIERTA, en días alcistas debería pasar lo simétrico: el
--       MÁXIMO concentrado en la primera hora. Predicción: sí.
--
--   H3  EL EFECTO NO ES SOLO DE LA PRIMERA HORA sino de los BORDES: las horas
--       0 y 23 juntas deberían concentrar mucho más que dos horas cualquiera.
--       Predicción: sí, y por la misma razón.
--
-- Si las tres se confirman, la medida no dice nada sobre horarios de operación:
-- dice que los extremos de un día tienden a estar en sus bordes, que es una
-- propiedad de cómo se define un día y no del mercado.

\echo '═══ H1 · ¿el efecto depende de si el día fue alcista o bajista? ═══'
\echo ''

WITH velas AS (
    SELECT (hora AT TIME ZONE 'utc')::date              AS dia,
           EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h,
           apertura, cierre, maximo, minimo
    FROM btc_vela_horaria
    WHERE hora >= (now() AT TIME ZONE 'utc') - interval '24 months'
),
completos AS (SELECT dia FROM velas GROUP BY dia HAVING COUNT(*) = 24),
resumen AS (
    SELECT v.dia,
           (array_agg(v.apertura ORDER BY v.h))[1]              AS abre,
           (array_agg(v.cierre   ORDER BY v.h DESC))[1]         AS cierra,
           (array_agg(v.h        ORDER BY v.minimo))[1]         AS h_min,
           (array_agg(v.h        ORDER BY v.maximo DESC))[1]    AS h_max
    FROM velas v JOIN completos c ON c.dia = v.dia
    GROUP BY v.dia
)
SELECT CASE WHEN cierra >= abre THEN 'alcista' ELSE 'bajista' END AS tipo_de_dia,
       COUNT(*)                                           AS dias,
       COUNT(*) FILTER (WHERE h_min = 0)                   AS min_en_hora_0,
       ROUND(100.0 * COUNT(*) FILTER (WHERE h_min = 0) / COUNT(*), 1) AS pct_min,
       ROUND(100.0 * COUNT(*) FILTER (WHERE h_min = 0) / COUNT(*) / 4.17, 2)
                                                           AS veces_el_azar
FROM resumen GROUP BY 1 ORDER BY 1;

\echo ''
\echo '═══ H2 · en días alcistas, ¿el MÁXIMO se concentra en la hora 0? ═══'
\echo ''

WITH velas AS (
    SELECT (hora AT TIME ZONE 'utc')::date AS dia,
           EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h,
           apertura, cierre, maximo, minimo
    FROM btc_vela_horaria
    WHERE hora >= (now() AT TIME ZONE 'utc') - interval '24 months'
),
completos AS (SELECT dia FROM velas GROUP BY dia HAVING COUNT(*) = 24),
resumen AS (
    SELECT v.dia,
           (array_agg(v.apertura ORDER BY v.h))[1]           AS abre,
           (array_agg(v.cierre   ORDER BY v.h DESC))[1]      AS cierra,
           (array_agg(v.h        ORDER BY v.minimo))[1]      AS h_min,
           (array_agg(v.h        ORDER BY v.maximo DESC))[1] AS h_max
    FROM velas v JOIN completos c ON c.dia = v.dia
    GROUP BY v.dia
)
SELECT CASE WHEN cierra >= abre THEN 'alcista' ELSE 'bajista' END AS tipo_de_dia,
       COUNT(*) AS dias,
       COUNT(*) FILTER (WHERE h_max = 0) AS max_en_hora_0,
       ROUND(100.0 * COUNT(*) FILTER (WHERE h_max = 0) / COUNT(*), 1) AS pct_max,
       ROUND(100.0 * COUNT(*) FILTER (WHERE h_max = 0) / COUNT(*) / 4.17, 2)
                                                              AS veces_el_azar
FROM resumen GROUP BY 1 ORDER BY 1;

\echo ''
\echo '═══ H3 · ¿es de los BORDES o solo de la primera hora? ═══'
\echo '  Dos horas cualquiera deberían dar 8,3 %. Los bordes (0 y 23):'
\echo ''

WITH velas AS (
    SELECT (hora AT TIME ZONE 'utc')::date AS dia,
           EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h, maximo, minimo
    FROM btc_vela_horaria
    WHERE hora >= (now() AT TIME ZONE 'utc') - interval '24 months'
),
completos AS (SELECT dia FROM velas GROUP BY dia HAVING COUNT(*) = 24),
resumen AS (
    SELECT v.dia,
           (array_agg(v.h ORDER BY v.minimo))[1]      AS h_min,
           (array_agg(v.h ORDER BY v.maximo DESC))[1] AS h_max
    FROM velas v JOIN completos c ON c.dia = v.dia GROUP BY v.dia
)
SELECT 'mínimo' AS extremo,
       ROUND(100.0*COUNT(*) FILTER (WHERE h_min IN (0,23))/COUNT(*),1) AS bordes_pct,
       ROUND(100.0*COUNT(*) FILTER (WHERE h_min IN (11,12))/COUNT(*),1) AS centro_pct
FROM resumen
UNION ALL
SELECT 'máximo',
       ROUND(100.0*COUNT(*) FILTER (WHERE h_max IN (0,23))/COUNT(*),1),
       ROUND(100.0*COUNT(*) FILTER (WHERE h_max IN (11,12))/COUNT(*),1)
FROM resumen;

\echo ''
\echo '═══ LA PRUEBA DEFINITIVA · el extremo relativo a la APERTURA ═══'
\echo '  Si el mínimo de la hora 0 es solo arrastre, entonces en esos días'
\echo '  el mínimo debería estar MUY CERCA del precio de apertura.'
\echo ''

WITH velas AS (
    SELECT (hora AT TIME ZONE 'utc')::date AS dia,
           EXTRACT(HOUR FROM hora AT TIME ZONE 'utc')::int AS h,
           apertura, minimo
    FROM btc_vela_horaria
    WHERE hora >= (now() AT TIME ZONE 'utc') - interval '24 months'
),
completos AS (SELECT dia FROM velas GROUP BY dia HAVING COUNT(*) = 24),
resumen AS (
    SELECT v.dia,
           (array_agg(v.apertura ORDER BY v.h))[1] AS abre,
           MIN(v.minimo)                            AS minimo_dia,
           (array_agg(v.h ORDER BY v.minimo))[1]    AS h_min
    FROM velas v JOIN completos c ON c.dia = v.dia GROUP BY v.dia
)
SELECT CASE WHEN h_min = 0 THEN 'mínimo en la hora 0'
            ELSE 'mínimo en otra hora' END AS caso,
       COUNT(*) AS dias,
       ROUND(AVG((minimo_dia/abre - 1) * 100)::numeric, 3) AS caida_media_pct,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP
              (ORDER BY (minimo_dia/abre - 1) * 100))::numeric, 3) AS caida_mediana
FROM resumen GROUP BY 1 ORDER BY 1;
