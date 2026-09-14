-- #570: conserva il corpo completo ricevuto dal provider accanto allo snippet
-- compatibile con i lettori esistenti. Nessun backfill: per le righe storiche
-- il testo integrale non e' recuperabile dall'API, quindi body_full resta NULL.
ALTER TABLE news_log
    ADD COLUMN IF NOT EXISTS body_full TEXT;

COMMENT ON COLUMN news_log.body_full IS
    'Corpo completo dell''articolo ricevuto all''ingestione (#570). '
    'NULL per lo storico: nessun backfill, perche'' il payload originario non e'' recuperabile.';
