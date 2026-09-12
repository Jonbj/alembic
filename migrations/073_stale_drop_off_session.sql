-- 067_stale_drop_off_session.sql
-- #432 (Opzione B): la seduta di accodamento diventa un dato persistito, e la
-- partizione causale degli scarti stale passa da tre gruppi a quattro.
--
-- Deroga alla carta di osservazione registrata il 2026-09-10 in
-- docs/evidence/OBSERVATION_CHARTER.md: difetto di correttezza dello strumento
-- di misura, con discontinuita' dichiarata sulla serie stale_drop_metrics_daily.
--
-- Perche' serve. La 062 registra due cause: "arrivata gia' vecchia"
-- (already_stale_at_fetch) e "invecchiata in coda" (went_stale_in_queue). Per il
-- WebSocket raw_ingested_at ~= published_at, quindi TUTTA la coorte accodata a
-- mercato chiuso — che nessun consumatore poteva lavorare, perche' il worker di
-- sentiment ha la guardia di seduta — cadeva in went_stale_in_queue, la stessa
-- casella in cui cade un outage del consumatore a mercato aperto. Le due hanno
-- fix opposti: la prima non e' un guasto, la seconda si'. L'alert non le
-- distingueva ed e' diventato un falso allarme strutturale pur restando
-- formalmente corretto.
SET lock_timeout = '2s';

-- 1. Il flag di seduta sulle righe di scarto.
--
-- E' una proprieta' del momento di ACCODAMENTO, non di quello di scarto: un
-- outage a mercato aperto resta in-seduta per costruzione, qualunque cosa
-- succeda dopo. NULL = non ricostruibile (payload illeggibile): il collettore
-- lo legge come in-seduta, fail-closed verso l'allerta.
ALTER TABLE news_queue_drops
    ADD COLUMN IF NOT EXISTS enqueued_off_session BOOLEAN;

COMMENT ON COLUMN news_queue_drops.enqueued_off_session IS
    'True se raw_ingested_at cade fuori dalla regular session US (#432). '
    'Scritto da build_news_discard_row via is_regular_session_time; NULL = ignoto.';

-- 2. Backfill delle righe scritte prima della colonna.
--
-- Necessario, non cosmetico: la serie va ricalcolata per intero da UNA sola
-- provenienza (carta, voce del 2026-08-01 su market_daily.jsonl), e le righe di
-- 08-09/09 — quelle su cui si giudica la correzione — precedono la colonna.
--
-- Derivazione one-shot e retroattiva: il calendario Alpaca non e' interrogabile
-- per ogni riga storica. Il predicato e' lo STESSO di
-- src/workers/market_clock.py::is_regular_session_time — giorno feriale e ora
-- locale di New York in [09:30, 16:00) — e il fuso, non un orario UTC cablato,
-- si occupa di EDT/EST. Come l'helper, non modella festivita' e chiusure
-- anticipate: un istante di festivita' risulta in-seduta, quindi resta nel
-- gruppo che concorre alla soglia (falso allarme possibile, guasto scusato per
-- errore no). Da qui in avanti il flag arriva scritto dal path di scarto e
-- questa espressione non viene piu' usata.
UPDATE news_queue_drops
SET enqueued_off_session = NOT (
        EXTRACT(ISODOW FROM (raw_ingested_at AT TIME ZONE 'America/New_York')) <= 5
        AND (raw_ingested_at AT TIME ZONE 'America/New_York')::time
            >= TIME '09:30'
        AND (raw_ingested_at AT TIME ZONE 'America/New_York')::time
            < TIME '16:00'
    )
WHERE enqueued_off_session IS NULL
  AND raw_ingested_at IS NOT NULL;

-- 3. Il quarto gruppo causale sul rollup.
ALTER TABLE stale_drop_metrics_daily
    ADD COLUMN IF NOT EXISTS went_stale_off_session INTEGER NOT NULL DEFAULT 0;

-- 4. Il CHECK sulla somma passa da tre a quattro addendi.
--
-- La 062 lo dichiara inline nel CREATE TABLE, quindi il nome e' generato da
-- Postgres: va trovato per definizione, non per nome. Rimosso e sostituito —
-- affiancarlo lo lascerebbe a rifiutare ogni riga con off-session > 0.
--
-- Il predicato cerca la SOMMA, non la colonna: `already_stale_at_fetch`
-- compare anche nel CHECK di non-negativita' della 062, e cercare la sola
-- colonna se lo porterebbe via insieme al vincolo da sostituire.
DO $$
DECLARE
    vecchio TEXT;
BEGIN
    FOR vecchio IN
        SELECT conname
        FROM pg_constraint
        WHERE conrelid = 'stale_drop_metrics_daily'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%already_stale_at_fetch%'
          AND pg_get_constraintdef(oid) LIKE '%unclassified_stale%'
          AND pg_get_constraintdef(oid) LIKE '%stale_drops%'
          AND pg_get_constraintdef(oid) NOT LIKE '%went_stale_off_session%'
    LOOP
        EXECUTE format(
            'ALTER TABLE stale_drop_metrics_daily DROP CONSTRAINT %I', vecchio
        );
    END LOOP;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'stale_drop_metrics_daily'::regclass
          AND conname = 'ck_stale_drop_metrics_cause_split'
    ) THEN
        ALTER TABLE stale_drop_metrics_daily
            ADD CONSTRAINT ck_stale_drop_metrics_cause_split CHECK (
                already_stale_at_fetch + went_stale_in_queue + went_stale_off_session
                + unclassified_stale = stale_drops
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'stale_drop_metrics_daily'::regclass
          AND conname = 'ck_stale_drop_metrics_off_session_non_negative'
    ) THEN
        ALTER TABLE stale_drop_metrics_daily
            ADD CONSTRAINT ck_stale_drop_metrics_off_session_non_negative CHECK (
                went_stale_off_session >= 0
            );
    END IF;
END $$;

COMMENT ON COLUMN stale_drop_metrics_daily.went_stale_off_session IS
    'Scarti stale accodati a seduta chiusa (#432): pubblicati, NON nella soglia.';

COMMENT ON COLUMN stale_drop_metrics_daily.alert_required IS
    'Dal 2026-09-10 (#432) NON e'' derivabile da stale_drop_share: la soglia si '
    'applica alla quota accodata entro seduta, cioe'' a '
    '(stale_drops - went_stale_off_session) / queued.';

COMMENT ON COLUMN stale_drop_metrics_daily.day IS
    'Dal 2026-09-10 (#432) e'' il giorno di ACCODAMENTO (coorte), non piu'' il '
    'giorno di scarto: e'' il giorno su cui ingestion_stats_daily.queued — il '
    'denominatore — e'' incrementato. Discontinuita'' dichiarata nella carta.';
