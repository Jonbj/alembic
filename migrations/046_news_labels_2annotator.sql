-- migrations/046_news_labels_2annotator.sql
-- QX-01 (#54): evolve news_labels dallo schema single-annotator (UNIQUE url,
-- una riga per articolo) allo schema 2-annotator + adjudication della specifica
-- (docs/TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md §5.3-5.5).
--
--   UNIQUE(url)                       ->  UNIQUE(news_log_id, annotator_id)
--   + colonne adjudicated / adjudicator_id  (terzo annotatore risolve i disaccordi)
--   + backfill news_log_id / fetched_at dalle righe legacy url-keyed
--   + tabella news_label_splits per l'holdout 60/40 (train/test, §5.8)
--
-- Strumentazione/misura sola (freeze #171): nessuna taratura, nessun hot path.
-- Non rompe i reader esistenti (tutti leggono per status / label_id / url, che
-- restano intatti). Idempotente sulle colonne e sugli indici; i vincoli seguono
-- la convenzione del repo (apply_migrations.py non e' rirunnabile sulle CONSTRAINT).

-- 1. Colonne della specifica non ancora presenti.
ALTER TABLE news_labels ADD COLUMN IF NOT EXISTS news_log_id    BIGINT;
ALTER TABLE news_labels ADD COLUMN IF NOT EXISTS fetched_at     TIMESTAMPTZ;
ALTER TABLE news_labels ADD COLUMN IF NOT EXISTS adjudicated    BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE news_labels ADD COLUMN IF NOT EXISTS adjudicator_id TEXT;

-- 2. Backfill news_log_id / fetched_at per le righe seminate sotto il vecchio
--    schema url-keyed, cosi' il nuovo UNIQUE(news_log_id, annotator_id) le tiene.
--    Una news_log puo' avere piu' righe per stessa url (tickers distinti): si
--    prende un id rappresentativo per url (MAX), basta un riferimento all'articolo.
UPDATE news_labels AS lbl
   SET news_log_id = sub.news_log_id,
       fetched_at  = COALESCE(sub.fetched_at, lbl.fetched_at)
  FROM (SELECT url, MAX(id) AS news_log_id, MAX(fetched_at) AS fetched_at
          FROM news_log
         WHERE url <> ''
         GROUP BY url) AS sub
 WHERE lbl.news_log_id IS NULL
   AND lbl.url = sub.url;

CREATE INDEX IF NOT EXISTS idx_news_labels_news_log_id ON news_labels (news_log_id);

-- 3. Scambia la garanzia di univocita': url -> (news_log_id, annotator_id).
--    Permette esattamente due annotatori per articolo (A, B) piu' la riga di
--    adjudication; le pending legacy (annotator_id NULL) convivono grazie al
--    trattamento NULL di Postgres (distinti, mai uguali).
ALTER TABLE news_labels DROP CONSTRAINT IF EXISTS news_labels_url_key;
ALTER TABLE news_labels ADD CONSTRAINT news_labels_news_log_annotator_uniq
    UNIQUE (news_log_id, annotator_id);

-- 4. Holdout 60/40 (§5.8): split train/test per news_log_id, popolato da
--    scripts/split_news_labels_holdout.py (assegnazione deterministica).
CREATE TABLE IF NOT EXISTS news_label_splits (
    news_log_id  BIGINT PRIMARY KEY,
    split        TEXT NOT NULL CHECK (split IN ('train', 'test')),
    assigned_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);