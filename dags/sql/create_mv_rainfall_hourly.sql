-- Silver layer  : one trusted reading per hour per city
CREATE MATERIALIZED VIEW IF NOT EXISTS public.mv_rainfall_hourly AS
WITH latest_per_hour AS (
    SELECT DISTINCT ON (city, date_trunc('hour', record_ts))
           city,
           date_trunc('hour', record_ts) AS hour_ts,
           rainfall_mm
    FROM public.rainfall
    ORDER BY city,
             date_trunc('hour', record_ts),
             record_ts DESC          -- keep latest in that hour
)
SELECT * FROM latest_per_hour;

-- Unique index required for CONCURRENT refresh
CREATE UNIQUE INDEX IF NOT EXISTS ux_mv_city_hour
    ON public.mv_rainfall_hourly (city, hour_ts);