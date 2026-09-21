-- 078_execution_decision_provenance.sql
-- #596: la provenienza del punteggio consumato da una decisione di uscita
-- (``sentiment_reversal`` e ``below_entry_gate``, in particolare) NON e' oggi
-- ricostruibile. ``execution_decisions.signal_id`` e' FK verso
-- ``sentiment_signals`` (gia' dal 016) e da li si raggiunge ``news_log`` via
-- ``sentiment_signals.news_log_id`` (gia' dal 016). Ma:
--
--   * ``news_log_id`` sulla decisione non e' denormalizzato e la join si rompe
--     quando la ``sentiment_signals`` viene cancellata (SET NULL, ON DELETE);
--   * ``n_ticker_articolo`` (fan-out degree) e la categoria di attribution
--     (``ISSUER_SPECIFIC`` / ``FANOUT`` / ``TAG_UNCONFIRMED`` / ...) vanno
--     calcolate ogni volta dalla join, e non c'e' un lock di cache — uno stesso
--     articolo ri-appare come FANOUT per simboli diversi nello stesso ciclo;
--   * il titolo e l'URL dell'articolo non sono sulla decisione, quindi la
--     ricostruzione richiede SEMPRE due hop di join, due-tre a schiena dritta
--     quando si guarda un incident post-mortem.
--
-- Perimetro. Sola telemetria additiva, dentro il profilo d'esenzione di #161,
-- #324, #541, #561, #075: nessuna soglia, nessun peso, nessun flag di
-- strategia, nessuna regola di ranking. Le colonne sono scritte solo dai path
-- instrumentati (``sentiment_reversal`` in ``_submit_reversal_force_sells`` e
-- weight-zero SELL S4 con ``exit_mechanism='below_entry_gate'`` in
-- ``_submit_portfolio_orders``); tutti gli altri call-site continuano a
-- scrivere NULL senza alcuna interruzione. Il freeze #171 non e' toccato.
--
-- Nessun backfill: le righe pre-migrazione restano NULL e la serie comincia
-- dal deploy — come #075, NULL = "non strumentato", mai un valore ricostruito
-- a posteriori. Le nuove colonne sono tutte NULL-able e additive.

SET lock_timeout = '2s';

-- ───────────────────────────────────────────────────────────────────────────
-- 1. Provenienza del punteggio sulla decisione di esecuzione.
-- ───────────────────────────────────────────────────────────────────────────

-- news_log_id denormalizzato: la join sentiment_signals→news_log e' gia' nota
-- al momento della scrittura (signal_id e' FK a sentiment_signals), e rompe
-- solo quando la sentiment_signals viene cancellata (SET NULL). Persisterlo
-- direttamente qui rende la decisione indipendente dal destino del segnale.
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS news_log_id BIGINT
        REFERENCES news_log(id) ON DELETE SET NULL;

COMMENT ON COLUMN execution_decisions.news_log_id IS
    'FK denormalizzata verso news_log del segnale che ha guidato la decisione '
    '(#596). Distinta da signal_id: signal_id FK verso sentiment_signals (puo'' '
    'essere NULL per cancellazioni ON DELETE SET NULL); news_log_id resta anche '
    'quando sentiment_signals viene cancellata. NULL = non strumentato o riga '
    'anteriore alla migrazione 078.';

-- fan-out degree dell'articolo: quanti ticker distinti condividono lo stesso
-- URL (stesso pattern di ``build_signal_diagnostics._default_db_enricher``).
-- 1 = articolo single-issuer, > 1 = fan-out. None = news_log NULL o URL vuota.
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS n_ticker_articolo INTEGER;

ALTER TABLE execution_decisions
    ADD CONSTRAINT ck_execution_decisions_n_ticker_articolo_positive
        CHECK (n_ticker_articolo IS NULL OR n_ticker_articolo >= 1);

COMMENT ON COLUMN execution_decisions.n_ticker_articolo IS
    'Fan-out degree dell''articolo che ha guidato la decisione (#596). '
    'Conteggio di ticker distinti con lo stesso URL su news_log (1 = single-'
    'issuer, > 1 = fan-out). NULL = news_log assente/URL vuota/pre-migrazione.';

-- attribution: categoria di rilevanza dell'articolo rispetto al ticker della
-- decisione. I valori sono quelli di ``article_coverage.RELEVANCE_CATEGORIES``
-- (ISSUER_SPECIFIC, FANOUT, TAG_UNCONFIRMED, SECTOR_MACRO, IRRELEVANT_FANOUT,
-- FALSE_ENTITY_MATCH, UNKNOWN). Dominio chiuso: niente free-text, per poter
-- aggregare senza NLP.
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS attribution TEXT;

ALTER TABLE execution_decisions
    ADD CONSTRAINT ck_execution_decisions_attribution_domain
        CHECK (attribution IS NULL OR attribution IN (
            'ISSUER_SPECIFIC',
            'FANOUT',
            'TAG_UNCONFIRMED',
            'SECTOR_MACRO',
            'IRRELEVANT_FANOUT',
            'FALSE_ENTITY_MATCH',
            'UNKNOWN'
        ));

COMMENT ON COLUMN execution_decisions.attribution IS
    'Categoria di rilevanza dell''articolo rispetto al ticker della decisione '
    '(#596). Stesso dominio di article_coverage.RELEVANCE_CATEGORIES. '
    'Calcolata al momento della scrittura via classify_attribution() con '
    'ticker=symbol della decisione ed extraction_method della news_log. '
    'NULL = news_log assente/pre-migrazione.';

-- Titolo e URL denormalizzati: articolo "altro-ticker" che ha fatto uscire la
-- posizione (MU su titolo WDC, #596). Senza denormalizzazione la diagnosi
-- richiede due join anche post-deploy.
ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS article_title TEXT;

ALTER TABLE execution_decisions
    ADD COLUMN IF NOT EXISTS article_url TEXT;

COMMENT ON COLUMN execution_decisions.article_title IS
    'Titolo della news_log che ha guidato la decisione (#596). NULL = news_log '
    'assente/pre-migrazione. Campo diagnostico: nessun vincolo di lunghezza, '
    'il body full e'' su news_log.body_full (#074).';

COMMENT ON COLUMN execution_decisions.article_url IS
    'URL canonicalizzato della news_log che ha guidato la decisione (#596). '
    'NULL = news_log assente/URL vuota/pre-migrazione.';

-- Indice di copertura per la misura #596: uscite guidate da fan-out
-- (``attribution IN ('FANOUT', 'TAG_UNCONFIRMED')``) o single-issuer.
CREATE INDEX IF NOT EXISTS idx_execution_decisions_attribution
    ON execution_decisions (attribution, tick_time DESC)
    WHERE attribution IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_execution_decisions_n_ticker_articolo
    ON execution_decisions (n_ticker_articolo, tick_time DESC)
    WHERE n_ticker_articolo IS NOT NULL;

-- news_log_id e' gia' un indice candidato naturale via PK di news_log; non
-- aggiungiamo un indice dedicato per non duplicarlo.