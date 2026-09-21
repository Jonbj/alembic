# Pre-registrazione #596 — Provenance dell'exit per articoli fan-out altro-ticker

**Data**: 2026-09-21
**Issue**: [#596](https://github.com/...)
**Status charter**: in regime di observation freeze fino al 2026-09-28 (#171). La
presente pre-registrazione e' puramente **misurativa** (instrumentation only):
lo script NON modifica il comportamento di trading, legge solo `execution_decisions`
esistenti + `news_log` + `sentiment_signals`. Il fix vero (enforcement sulla
rilevanza attribution) e' fuori freeze.

## Domanda

Quante uscite S4 negli ultimi ~7 settimane sono state guidate da un articolo
la cui rilevanza verso il ticker venduto e' debole — `SECTOR_MACRO`,
`IRRELEVANT_FANOUT`, o `FALSE_ENTITY_MATCH` — e quindi quanto rumore
"altro-ticker" ha consumato il gate d'uscita senza che il punteggio fosse
effettivamente issuer-specific per il simbolo?

## Campione (fissato prima della misura)

- **Finestra**: 2026-08-01T00:00:00Z → 2026-09-21T23:59:59Z (inclusi i due casi
  di cronaca della issue: MU 2026-09-14 e SOXX 3861 di #67).
- **Population**: tutte le righe di `execution_decisions` con
  `decision='SELL'` AND `tick_time` nella finestra AND
  `exit_mechanism IN ('below_entry_gate', NULL)` — `sentiment_reversal` non
  compare in `exit_mechanism` (e' in `reason`), quindi lo script lo deduce dalla
  stringa di reason (`sentiment_reversal:` prefix).
- **Join**:
  - `execution_decisions.signal_id = sentiment_signals.id`
  - `sentiment_signals.news_log_id = news_log.id`
- **Esclusioni post-join**:
  - righe con `signal_id IS NULL` (BUY/SELL senza signal — fuori scope)
  - righe con `news_log_id IS NULL` (la provenance non e' ricostruibile)
  - righe il cui `news_log.url` e' vuoto (fan-out non misurabile)

## Variabile di esito (fissata prima della misura)

Per ogni riga, classifico l'articolo rispetto al ticker della decisione con
`classify_attribution()` di `src/analysis/dossier/article_coverage.py`. Le
categorie sono mutuamente esclusive (`RELEVANCE_CATEGORIES`).

**Categorizzazione "rumorosa"** (perdita di exit gate):
- `SECTOR_MACRO` — l'articolo parla del settore, non del ticker.
- `IRRELEVANT_FANOUT` — `n_ticker_articolo >= 2` e articolo non rilevante per
  il ticker venduto.
- `FALSE_ENTITY_MATCH` — il ticker e' nell'articolo ma per omonimia /
  acronimo, non per identita' d'emittente.

**Categorizzazione "pulita"**:
- `ISSUER_SPECIFIC` — ticker presente come issuer dell'articolo.

Esiti `UNKNOWN` e `TAG_UNCONFIRMED` vengono riportati ma non classificati
come rumore: la strumentazione non puo' pronunciarsi.

## Outcome atteso (pre-registrato, senza guardare i dati)

- **OUT-A**: la quota di uscite rumorose sul totale uscite S4 e' > 30%. Allora
  la issue #596 e' confermata su scala recente e merita un fix di enforcement.
- **OUT-B**: la quota e' ≤ 10%. Allora il caso MU 2026-09-14 era anomalo e
  il fan-out non e' un problema di regime.
- **OUT-INCONCLUSIVE**: 10% < quota ≤ 30%. Servono piu' dati o un fix di
  gating parziale; l'esito non decide la issue.

Queste soglie sono pre-registrate: se dopo la misura la quota cade fra 25% e
35%, NON posso spostare la soglia per farla quadrare con OUT-A o OUT-B.

## Strumento di misura

`scripts/measure_596_exit_fanout_attribution.py` — uno script offline che:
1. apre una connessione al DB live `alembic-postgres-1` con la stessa
   routine di `src/store/pg_store.py`;
2. esegue la query join descritta sopra;
3. classifica ogni riga con `classify_attribution()`;
4. scrive l'artefatto JSON in
   `docs/evidence/EXIT_FANOUT_PROVENANCE_596_2026-09-21.json`.

Lo script NON usa il ranker di produzione e NON tocca
`ensemble:weights:current`, `config:sentiment_llm_models`, o qualunque
chiave Redis di stato: e' read-only.

## Cosa NON e' coperto da questa PR

- L'enforcement (ignorare l'exit quando `attribution` e' rumoroso) richiede un
  cambiamento di comportamento ed e' **fuori freeze** fino al 2026-09-28.
- La migrazione 078 e' additive (colonne nullable), quindi e' safe da
  applicare anche durante il freeze (non cambia righe esistenti).

## Multiplicity

Una sola misura, una sola variabile di esito, una sola popolazione. Niente
grid search.
