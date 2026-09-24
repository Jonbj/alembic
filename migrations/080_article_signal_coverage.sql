-- Migration 080: classificazione articolo al momento dello scoring (#637).
--
-- Serie nuova, additiva e solo osservazionale. Non modifica news_log ne'
-- sentiment_signals, per non cambiare i denominatori delle serie #508/#511;
-- non e' letta dal ranking, dal gate o dall'esecuzione. NULL sulle righe
-- storiche significa quindi «non strumentato», non una classificazione zero.

CREATE TABLE IF NOT EXISTS article_signal_coverage (
    id BIGSERIAL PRIMARY KEY,
    signal_id BIGINT NOT NULL UNIQUE REFERENCES sentiment_signals(id) ON DELETE CASCADE,
    news_log_id BIGINT REFERENCES news_log(id) ON DELETE SET NULL,
    symbol TEXT NOT NULL,
    canonical_article_id TEXT NOT NULL,
    timing_category TEXT NOT NULL,
    session_anchor DATE,
    relevance TEXT NOT NULL,
    attribution TEXT NOT NULL,
    subject_ticker TEXT,
    content_empty_reason TEXT,
    fanout_degree INTEGER NOT NULL,
    score_own DOUBLE PRECISION,
    score_fanout DOUBLE PRECISION,
    novelty_proxy BOOLEAN,
    input_scope TEXT NOT NULL,
    classified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (timing_category IN ('ANTICIPATORY', 'CONCURRENT', 'RETROSPECTIVE', 'UNKNOWN')),
    CHECK (relevance IN ('ISSUER_SPECIFIC', 'SECTOR_MACRO', 'FALSE_ENTITY_MATCH', 'IRRELEVANT_FANOUT', 'TAG_UNCONFIRMED', 'UNKNOWN')),
    CHECK (attribution IN ('ISSUER_SPECIFIC', 'FANOUT', 'UNKNOWN')),
    CHECK (fanout_degree >= 1),
    CHECK (input_scope IN ('full_article', 'unavailable'))
);

CREATE INDEX IF NOT EXISTS article_signal_coverage_symbol_anchor_article_idx
    ON article_signal_coverage (symbol, session_anchor, canonical_article_id);

COMMENT ON TABLE article_signal_coverage IS
    'Classificazione osservazionale al momento dello scoring (#637). Serie additiva: non letta dal money path.';

COMMENT ON COLUMN article_signal_coverage.session_anchor IS
    'Prima seduta Alpaca in cui l''articolo poteva essere agito; NULL = calendario non disponibile.';

COMMENT ON COLUMN article_signal_coverage.novelty_proxy IS
    'TRUE apre il primo cluster canonico per simbolo e seduta; FALSE si accoda; NULL = ancora non disponibile.';
