-- Migration 022: zeygos_scores table
-- Stores parsed Zeygos sector report data: ticker scores per report date.
-- Populated by the Telegram bot when a Zeygos PDF is forwarded to it.

CREATE TABLE IF NOT EXISTS zeygos_scores (
    id                SERIAL PRIMARY KEY,
    report_date       DATE             NOT NULL,
    market            VARCHAR(5)       NOT NULL CHECK (market IN ('USA', 'EU')),
    sector            VARCHAR(100)     NOT NULL,
    rank              SMALLINT         NOT NULL CHECK (rank BETWEEN 1 AND 5),
    ticker_refinitiv  VARCHAR(30)      NOT NULL,
    ticker            VARCHAR(20)      NOT NULL,
    company_name      VARCHAR(200)     NOT NULL DEFAULT '',
    score_analysts    DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_momentum    DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_valuation   DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_solidity    DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_dividend    DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_growth      DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_interest    DOUBLE PRECISION NOT NULL DEFAULT 0,
    score_finale      DOUBLE PRECISION NOT NULL,
    ingested_at       TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT zeygos_scores_unique UNIQUE (report_date, ticker_refinitiv)
);

CREATE INDEX IF NOT EXISTS idx_zeygos_scores_date_finale
    ON zeygos_scores (report_date DESC, score_finale DESC);

CREATE INDEX IF NOT EXISTS idx_zeygos_scores_ticker
    ON zeygos_scores (ticker, report_date DESC);
