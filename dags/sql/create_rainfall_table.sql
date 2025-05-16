CREATE TABLE IF NOT EXISTS public.rainfall (
    id            integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    city          varchar(64)   NOT NULL,
    record_ts     timestamptz   NOT NULL,
    rainfall_mm   numeric(6,2)  NOT NULL,
    ingestion_ts  timestamptz   DEFAULT now(),
    CONSTRAINT uq_city_rec UNIQUE (city, record_ts)
);