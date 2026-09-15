-- 075_news_transport_provenance.sql
-- #541: la provenienza di TRASPORTO diventa un dato persistito per riga, e il
-- tasso di articoli mai consegnati dal WebSocket diventa una serie storica
-- invece di una ricostruzione a mano dai log dei container.
--
-- Perche' serve. `source` dice CHI ha pubblicato (`alpaca_benzinga`), non DA
-- DOVE e' arrivato. Alpaca/Benzinga ha due consegne per lo stesso contenuto —
-- il WebSocket 24/7 e il poller REST a 15 minuti — e #455 le ha unificate sotto
-- un solo contratto di dedup/telemetria. Scelta corretta, ma una volta
-- persistita la riga non dice piu' quale dei due l'ha vista per primo:
--
--   SELECT source, count(*) FROM news_log WHERE created_at >= '2026-09-07 13:00+00'
--   GROUP BY 1;  -->  alpaca_benzinga 185, gdelt_gkg 17
--
-- Due misure aperte ne dipendono, entrambe documentate:
--   * #455 ha trovato ~2,5% di articoli (3 su ~120 l'08/09) mai consegnati dal
--     WebSocket pur avendo simboli sottoscritti. Quel numero e' stato
--     ricostruito incrociando log di container che ruotano, quindi non e'
--     riproducibile domani e la decisione «spegnere il polling REST?» resta
--     sospesa su un campione di una giornata sola.
--   * docs/research/stale_cohort_fetch_latency_2026-09-15.md §4.1 attribuisce
--     il gradino `already_stale_at_fetch` 18 → 263 fra il 09 e il 10/09 al
--     passaggio del primo avvistamento dal REST al WS, ma **per inferenza dalla
--     latenza** (`raw_ingested_at - published_at` ~ 0 ⇒ WebSocket). Con questa
--     colonna la stessa domanda si risponde per osservazione.
--
-- Perimetro. Sola telemetria, dentro il profilo d'esenzione gia' ammesso per
-- #161, #324 e #561: nessuna soglia, nessun peso, nessun flag di strategia,
-- nessun parametro di taratura (freeze #171 fino al 2026-09-28). Il destino di
-- nessuna news cambia, il contratto di dedup di #455 resta uno solo — il
-- trasporto non entra in nessuna chiave di dedup, altrimenti WS e REST
-- smetterebbero di deduplicarsi a vicenda e ogni articolo entrerebbe due volte.
-- Nessuna serie esistente cambia definizione: le colonne sono additive e
-- nullable, le viste sono nuove.
SET lock_timeout = '2s';

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. La colonna, sui due ledger che raccontano il destino di un articolo.
--
-- Regola di scrittura: **registra chi osserva**, non chi ha pubblicato.
--   * `news_log` raccoglie cio' che e' sopravvissuto ed e' stato scorato, e solo
--     il primo avvistamento supera il dedup: la colonna vale quindi, per
--     costruzione, la provenienza del PRIMO avvistamento.
--   * `news_queue_drops` raccoglie gli scarti, e ogni riga porta il trasporto
--     dell'avvistamento che l'ha prodotta. Lo stesso articolo ha una riga `ws`
--     (accodato) e N righe `rest` (`duplicate_id` ai poll successivi): e'
--     esattamente la coppia che rende attribuibile il gradino del 10/09.
--
-- NULL = «path non strumentato». E' un'informazione vera e diversa da `rest`:
-- i connettori senza variante WebSocket (GDELT, MarketAux, Finnhub, RSS, EDGAR)
-- non hanno un trasporto da discriminare e restano NULL di proposito.
ALTER TABLE news_log
    ADD COLUMN IF NOT EXISTS transport TEXT;

ALTER TABLE news_queue_drops
    ADD COLUMN IF NOT EXISTS transport TEXT;

-- Dominio chiuso sui due trasporti che esistono davvero. Un terzo valore in una
-- serie pubblicata e' un valore che fra sei settimane nessuno sa piu' leggere.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'news_log'::regclass
          AND conname = 'ck_news_log_transport'
    ) THEN
        ALTER TABLE news_log
            ADD CONSTRAINT ck_news_log_transport
            CHECK (transport IS NULL OR transport IN ('ws', 'rest'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'news_queue_drops'::regclass
          AND conname = 'ck_news_queue_drops_transport'
    ) THEN
        ALTER TABLE news_queue_drops
            ADD CONSTRAINT ck_news_queue_drops_transport
            CHECK (transport IS NULL OR transport IN ('ws', 'rest'));
    END IF;
END $$;

COMMENT ON COLUMN news_log.transport IS
    'Consegna che ha visto per primo l''articolo: ws | rest | NULL (#541). '
    'NULL = path non strumentato o riga anteriore alla migrazione 075. '
    'Distinta da `source`, che dice chi ha pubblicato.';

COMMENT ON COLUMN news_queue_drops.transport IS
    'Consegna che ha prodotto QUESTO scarto: ws | rest | NULL (#541). '
    'Proprieta'' dell''avvistamento, non dell''articolo: lo stesso articolo ha '
    'una riga ws (accodato) e N righe rest (duplicate_id ai poll successivi).';

-- **Nessun backfill.** Le righe anteriori a questa migrazione non hanno la
-- provenienza e non e' ricostruibile: dedurla dalla latenza (`~0 ⇒ ws`) e'
-- l'euristica di analisi dichiarata in §2.1 del documento del 15/09, e
-- scriverla nel ledger la trasformerebbe in un dato misurato che non e'. NULL
-- resta NULL, e la serie comincia dal deploy — dichiarato, non stimato.

CREATE INDEX IF NOT EXISTS idx_news_queue_drops_transport
    ON news_queue_drops (transport, dropped_at DESC)
    WHERE transport IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Lo snapshot della sottoscrizione attiva.
--
-- La DoD di #541 richiede che il tasso sia calcolato **solo sui simboli
-- effettivamente sottoscritti in quel momento**: un articolo su un titolo fuori
-- watchlist recuperato dal REST non e' un articolo perso dal WebSocket, e
-- contarlo come tale gonfierebbe il tasso proprio nella direzione che porta a
-- NON spegnere il polling. Oggi la condizione non e' verificabile a posteriori
-- — `WATCHLIST_SYMBOLS` e' baked nell'immagine e non lascia traccia storica.
--
-- Scritta da `registra_sottoscrizione()` all'avvio di worker-news-stream, cioe'
-- l'unico momento in cui la sottoscrizione cambia (il processo sottoscrive una
-- volta e resta connesso). Una finestra senza snapshot vale «non sottoscritto»:
-- nessun miss dichiarato, mai un miss inventato.
CREATE TABLE IF NOT EXISTS news_stream_subscriptions (
    id           BIGSERIAL PRIMARY KEY,
    observed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    transport    TEXT NOT NULL DEFAULT 'ws' CHECK (transport IN ('ws', 'rest')),
    symbols      TEXT[] NOT NULL,
    symbol_count INTEGER NOT NULL CHECK (symbol_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_news_stream_subscriptions_observed
    ON news_stream_subscriptions (observed_at DESC);

COMMENT ON TABLE news_stream_subscriptions IS
    'Simboli sottoscritti dal flusso WebSocket, campionati all''avvio (#541). '
    'Serve alla condizione «solo i simboli sottoscritti» del tasso di WS-missed.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Primo avvistamento per (articolo, ticker).
--
-- Il ledger e' diviso in due tabelle per destino — sopravvissuto (`news_log`) o
-- scartato (`news_queue_drops`) — ma la domanda «da dove e' entrato» e' una
-- sola. La vista le unisce e tiene l'avvistamento piu' antico.
--
-- Granularita': la COPPIA (url, simbolo), non l'articolo. E' la stessa unita'
-- delle righe di scarto, ed e' dichiarata nel nome delle colonne a valle:
-- l'analisi del 15/09 §2.3 ha mostrato che «313 scarti» sono in realta' 69
-- articoli (rapporto 4,5:1 dall'espansione per ticker), e una serie che conta
-- coppie chiamandole articoli e' gonfia per costruzione.
CREATE OR REPLACE VIEW news_transport_first_sighting AS
WITH avvistamenti AS (
    SELECT url, ticker AS symbol, source, published_at, raw_ingested_at, transport
    FROM news_log
    WHERE url <> ''
      AND raw_ingested_at IS NOT NULL
      AND published_at IS NOT NULL
    UNION ALL
    SELECT url, symbol, source, published_at, raw_ingested_at, transport
    FROM news_queue_drops
    WHERE url IS NOT NULL AND url <> ''
      AND symbol IS NOT NULL
      AND raw_ingested_at IS NOT NULL
      AND published_at IS NOT NULL
)
SELECT DISTINCT ON (url, symbol)
       url,
       symbol,
       source,
       published_at,
       raw_ingested_at AS first_seen_at,
       transport       AS first_transport,
       EXTRACT(EPOCH FROM (raw_ingested_at - published_at)) / 3600.0
           AS first_seen_delay_hours
FROM avvistamenti
ORDER BY url, symbol, raw_ingested_at ASC;

COMMENT ON VIEW news_transport_first_sighting IS
    'Primo avvistamento per coppia (url, simbolo) su news_log u news_queue_drops, '
    'col trasporto che lo ha prodotto (#541). Granularita'' = coppia, non articolo.';

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. La serie storica dei WS-missed: una query sola.
--
-- DoD #541: «quanti articoli il WebSocket ha perso ieri, su quali simboli, con
-- che ritardo di recupero REST», senza leggere i log dei container.
--
--   SELECT * FROM news_ws_missed_daily WHERE day = CURRENT_DATE - 1;
--
-- Definizione di miss: primo avvistamento `rest` **e** simbolo presente nella
-- sottoscrizione attiva al momento della PUBBLICAZIONE. Le righe senza
-- trasporto (storico pre-075, connettori non strumentati) sono escluse: una
-- riga non attribuita non e' ne' un miss ne' una consegna riuscita, e metterla
-- in uno dei due gruppi falserebbe il tasso in una direzione precisa.
--
-- `day` e' il giorno di **pubblicazione**, non di avvistamento: e' la domanda
-- «quanti articoli di ieri ha perso», e per un miss i due giorni possono
-- differire proprio per via del ritardo di recupero.
CREATE OR REPLACE VIEW news_ws_missed_daily AS
WITH attribuiti AS (
    SELECT f.url,
           f.symbol,
           f.published_at,
           f.first_transport,
           f.first_seen_delay_hours,
           COALESCE(
               f.symbol = ANY (s.symbols) OR '*' = ANY (s.symbols),
               FALSE
           ) AS symbol_subscribed
    FROM news_transport_first_sighting f
    LEFT JOIN LATERAL (
        SELECT sub.symbols
        FROM news_stream_subscriptions sub
        WHERE sub.transport = 'ws'
          AND sub.observed_at <= f.published_at
        ORDER BY sub.observed_at DESC
        LIMIT 1
    ) s ON TRUE
    WHERE f.first_transport IS NOT NULL
      AND f.source = 'alpaca_benzinga'
)
SELECT
    (published_at AT TIME ZONE 'UTC')::date AS day,
    count(DISTINCT url) FILTER (WHERE symbol_subscribed)
        AS articoli_sottoscritti,
    count(*) FILTER (WHERE symbol_subscribed)
        AS coppie_sottoscritte,
    count(DISTINCT url) FILTER (WHERE symbol_subscribed AND first_transport = 'rest')
        AS articoli_ws_missed,
    count(*) FILTER (WHERE symbol_subscribed AND first_transport = 'rest')
        AS coppie_ws_missed,
    count(DISTINCT url) FILTER (WHERE symbol_subscribed AND first_transport = 'rest')::double precision
        / NULLIF(count(DISTINCT url) FILTER (WHERE symbol_subscribed), 0)
        AS quota_ws_missed,
    array_agg(DISTINCT symbol) FILTER (WHERE symbol_subscribed AND first_transport = 'rest')
        AS simboli_ws_missed,
    avg(first_seen_delay_hours) FILTER (WHERE symbol_subscribed AND first_transport = 'rest')
        AS ritardo_recupero_medio_ore,
    max(first_seen_delay_hours) FILTER (WHERE symbol_subscribed AND first_transport = 'rest')
        AS ritardo_recupero_max_ore
FROM attribuiti
GROUP BY 1
ORDER BY 1 DESC;

COMMENT ON VIEW news_ws_missed_daily IS
    'Serie giornaliera degli articoli mai consegnati dal WebSocket (#541): '
    'primo avvistamento rest su simbolo sottoscritto, col ritardo di recupero. '
    'Articoli e coppie (articolo x ticker) sono contati separatamente. '
    'La decisione sullo spegnimento del polling REST richiede >= 10 sedute.';
