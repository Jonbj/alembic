-- Migration 065: tabella shadow dedicata alle PoC fonti news esterne (#458).
--
-- Accoglie i campioni raccolti dai PoC shadow (Twelve Data press_releases e,
-- in futuro, eventuali altre fonti oggetto di PoC analoga). Non viene letta
-- dal path live: solo misure di copertura/latenza/qualita' PRIMA di decidere
-- se integrare la fonte. Idempotente (`CREATE TABLE IF NOT EXISTS`) per
-- poter coesistere con PoC paralleli che usino lo stesso schema.
--
-- Ref: docs/research/2026-09-01-fonti-news-consolidato.md, issue #458.

CREATE TABLE IF NOT EXISTS news_poc_samples (
    id              BIGSERIAL PRIMARY KEY,
    poc_source      TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    external_id     TEXT,                     -- id del comunicato (Twelve Data: campo `id`)
    title           TEXT,
    body_chars      INT,                       -- lunghezza del body dopo strip HTML/CSS
    url             TEXT,
    published_at    TIMESTAMPTZ,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    latency_seconds DOUBLE PRECISION,
    ticker_valid    BOOLEAN,                   -- il simbolo richiesto compare in title/body?
    raw_response    JSONB,                     -- risposta grezza per debug (solo PoC, no retention)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_news_poc_samples_source_symbol
    ON news_poc_samples (poc_source, symbol);

CREATE UNIQUE INDEX IF NOT EXISTS idx_news_poc_samples_source_extid
    ON news_poc_samples (poc_source, external_id)
    WHERE external_id IS NOT NULL;

COMMENT ON TABLE news_poc_samples IS
    'Campioni PoC shadow di fonti news esterne (#458). Mai letta dal path live.';