-- Migration 068: censimento periodico della coda news (#544, opzione A).
--
-- Serie di sola osservazione: profondita' ed eta' di `news:queue` campionate ogni
-- 5 minuti, 24/7. Serve a rendere l'accumulo notturno e lo svuotamento alla campana
-- un dato durevole invece di un'inferenza dai log dei container, che i rebuild
-- delle 22:20Z e 06:20Z distruggono (#544).
--
-- Nessuna colonna di questa tabella e' letta da sentiment, execution o dal ciclo
-- di portafoglio: e' strumentazione, mai money path.
--
-- Semantica delle colonne, esplicita perche' le due meta' della riga hanno
-- affidabilita' diversa:
--   * `queue_depth` / `processing_depth` / `dead_letter_depth` sono ESATTE (LLEN).
--   * `n_fresh` / `n_stale` / `oldest_age_hours` / `p50_age_hours` vengono da un
--     CAMPIONE a testa e coda con tetto 500 item (src/workers/news_queue_census.py):
--     su code piu' profonde di 500 sono stime, non conteggi.
--   * `source IS NULL` = riga di sola profondita', scritta quando il campione non
--     contiene item classificabili (coda vuota o interamente illeggibile), cosi'
--     la serie delle profondita' non ha buchi proprio quando vale zero.
-- La frontiera fresh/stale non e' definita qui: e' `_is_stale_news` di
-- src/workers/sentiment.py, importato dal task (#169/#467).

CREATE TABLE IF NOT EXISTS news_queue_census (
    sampled_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    queue_depth         INTEGER NOT NULL CHECK (queue_depth >= 0),
    processing_depth    INTEGER NOT NULL CHECK (processing_depth >= 0),
    dead_letter_depth   INTEGER NOT NULL CHECK (dead_letter_depth >= 0),
    source              TEXT,
    n_fresh             INTEGER NOT NULL CHECK (n_fresh >= 0),
    n_stale             INTEGER NOT NULL CHECK (n_stale >= 0),
    oldest_age_hours    NUMERIC,
    p50_age_hours       NUMERIC
);

-- Il taglio naturale della serie e' temporale (il dente di sega notturno).
CREATE INDEX IF NOT EXISTS idx_news_queue_census_sampled_at
    ON news_queue_census (sampled_at DESC);

-- Lettura per sorgente: `gdelt_gkg` non puo' accumulare fuori seduta per
-- costruzione, `alpaca_benzinga` si' — il confronto e' il punto della misura.
CREATE INDEX IF NOT EXISTS idx_news_queue_census_source
    ON news_queue_census (source, sampled_at DESC);

COMMENT ON TABLE news_queue_census IS
    'Campione 5-min di profondita'' ed eta'' della coda news (#544); osservabilita'' pura, mai consumo della coda.';
