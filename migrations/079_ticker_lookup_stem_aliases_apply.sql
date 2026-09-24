-- Migration 079: applica il backfill bare-stem approvato dall'operatore (#566 / F-077).
--
-- Solo il bucket "safe" del CSV (docs/evidence/proposals/ticker_lookup_stem_backfill.csv,
-- 28 ticker): alias in minuscolo aggiunto a ticker_lookup.aliases. I bucket "short"
-- (11) e "collision" (1, AAPL/'apple') restano FUORI per progetto (CLAUDE.md §
-- Ticker Resolution: l'ambiguita' non si indovina) — restano candidati per review umana.
--
-- Eseguito manualmente il 2026-09-24 (UPDATE array_append, 28 righe) dopo
-- approvazione operatore in chat; questa migration registra l'azione nel ledger.
-- Idempotente: array_append solo se l'alias non e' gia' presente.
--
-- Discontinuita' dichiarata nel charter 2026-09-24: da questa data il relevance
-- classifier vede gli issuer anche nei titoli bare ("Oracle set to report...").

UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'abbvie') WHERE ticker='ABBV' AND NOT 'abbvie' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'adobe') WHERE ticker='ADBE' AND NOT 'adobe' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'broadcom') WHERE ticker='AVGO' AND NOT 'broadcom' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'bank of america') WHERE ticker='BAC' AND NOT 'bank of america' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'comcast') WHERE ticker='CMCSA' AND NOT 'comcast' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'costco wholesale') WHERE ticker='COST' AND NOT 'costco wholesale' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'salesforce') WHERE ticker='CRM' AND NOT 'salesforce' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'chevron') WHERE ticker='CVX' AND NOT 'chevron' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'walt disney') WHERE ticker='DIS' AND NOT 'walt disney' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'alphabet') WHERE ticker='GOOGL' AND NOT 'alphabet' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'international business machines') WHERE ticker='IBM' AND NOT 'international business machines' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'intel') WHERE ticker='INTC' AND NOT 'intel' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'mcdonald''s') WHERE ticker='MCD' AND NOT 'mcdonald''s' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'merck') WHERE ticker='MRK' AND NOT 'merck' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'microsoft') WHERE ticker='MSFT' AND NOT 'microsoft' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'netflix') WHERE ticker='NFLX' AND NOT 'netflix' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'nvidia') WHERE ticker='NVDA' AND NOT 'nvidia' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'oracle') WHERE ticker='ORCL' AND NOT 'oracle' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'palo alto') WHERE ticker='PANW' AND NOT 'palo alto' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'petroleo brasileiro') WHERE ticker='PBR' AND NOT 'petroleo brasileiro' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'pfizer') WHERE ticker='PFE' AND NOT 'pfizer' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'qualcomm') WHERE ticker='QCOM' AND NOT 'qualcomm' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'starbucks') WHERE ticker='SBUX' AND NOT 'starbucks' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'tesla') WHERE ticker='TSLA' AND NOT 'tesla' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'unitedhealth') WHERE ticker='UNH' AND NOT 'unitedhealth' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'wells fargo') WHERE ticker='WFC' AND NOT 'wells fargo' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'walmart') WHERE ticker='WMT' AND NOT 'walmart' = ANY(COALESCE(aliases,'{}'));
UPDATE ticker_lookup SET aliases = array_append(COALESCE(aliases,'{}'),'exxon mobil') WHERE ticker='XOM' AND NOT 'exxon mobil' = ANY(COALESCE(aliases,'{}'));
