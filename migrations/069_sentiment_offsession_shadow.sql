-- Migration 069: consumo shadow off-session della coda news (Opzione C, #432).
--
-- Unica destinazione di scrittura del worker `src/workers/sentiment_shadow.py`.
-- Il perimetro e' dichiarato nella carta di osservazione (deroga 2026-09-10) e
-- pre-registrato in docs/evidence/PREREGISTRAZIONE_offsession_shadow_2026-09-10.md:
-- nessuna riga di questo worker raggiunge `sentiment_signals`, `news_log` o
-- Redis. Questa tabella non e' letta da nessun path live -- ne' ingressi ne'
-- uscite -- ed esiste solo per rispondere, prima del 2026-09-28, alla domanda
-- "la coorte notturna scartata come stale vale qualcosa?".
--
-- Perche' `raw_item` in chiaro: il controfattuale deve poter essere ricalcolato
-- (per esempio con un prompt diverso) senza dipendere dalla coda Redis, che a
-- quel punto e' stata da tempo consumata o scaduta.

CREATE TABLE IF NOT EXISTS sentiment_signals_offsession_shadow (
    id              BIGSERIAL PRIMARY KEY,
    item_id         TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    model           TEXT NOT NULL,
    fallback_used   BOOLEAN NOT NULL DEFAULT FALSE,
    published_at    TIMESTAMPTZ,
    scored_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_item        JSONB
);

-- Un item della coda viene scorato una sola volta: la de-duplica primaria e' il
-- set Redis `shadow:processed:<notte>` (TTL 36h), ma quel set scade e questo
-- indice e' la garanzia durevole che il campione non contenga doppioni --
-- l'unita' di analisi pre-registrata e' il simbolo-giorno e un doppione la
-- gonfierebbe in silenzio.
CREATE UNIQUE INDEX IF NOT EXISTS idx_offsession_shadow_item
    ON sentiment_signals_offsession_shadow (item_id, symbol);

-- L'aggregazione pre-registrata e' (symbol, published_at::date UTC) filtrata su
-- |score| > 0,30.
CREATE INDEX IF NOT EXISTS idx_offsession_shadow_symbol_published
    ON sentiment_signals_offsession_shadow (symbol, published_at DESC);

CREATE INDEX IF NOT EXISTS idx_offsession_shadow_scored_at
    ON sentiment_signals_offsession_shadow (scored_at DESC);

COMMENT ON TABLE sentiment_signals_offsession_shadow IS
    'Controfattuale shadow off-session (#432, Opzione C). Mai letta dal path live; unica tabella scritta dal worker shadow.';
