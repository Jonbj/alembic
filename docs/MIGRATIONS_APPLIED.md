# Migrazioni applicate al DB live

Tracking manuale delle migrazioni PostgreSQL applicate al database di produzione (`alembic-postgres-1`).

> **NOTA**: questo DB non ha tabella `schema_migrations`. Lo stato "applicata o no" vive in questo file. Aggiornare dopo ogni applicazione manuale.

## Stato

| # | File | Applicata il | Note |
|---|------|-------------|------|
| 001–045 | (tutte le migrazioni fino a 045) | Pre-2026-08-22 | Storico non tracciato. Verificare con `psql` se serve. |
| 046 | 046_news_labels_2annotator.sql | 2026-09-01 | Applicata a mano lavorando a #405, in singola transazione dopo `pg_dump -t news_labels`: `UNIQUE(url)` → `UNIQUE(news_log_id, annotator_id)`, backfill 148/148, `news_label_splits` creata vuota. **Questa riga e' rimasta a "NON applicata" fino al 2026-09-02**, un giorno intero dopo l'applicazione. Conseguenza emersa solo col nuovo schema: la ground truth canonica di #449 esclude i singleton e tutte e 27 le label esistenti sono singleton, quindi serve la seconda annotazione anche sul campione storico. |
| 047 | 047_news_discard_reasons.sql | 2026-08-22 | Applicata a mano. Backfill 3477 righe. |
| 048 | 048_skip_pyramiding_counterfactual.sql | 2026-08-22 | Applicata a mano sotto il nome precedente `046_skip_pyramiding_counterfactual.sql`. |
| 049 | 049_counterfactual_coverage.sql | 2026-08-22 | Applicata a mano. 3 ADD COLUMN + 2 indici. |
| 050 | 050_s4_entry_intent_ledger.sql | 2026-08-25 | Applicata a mano. Ledger intenti S4 (#294): tabella append-only + 2 viste. Era su main dal merge di #294 ma mai applicata al live — scoperta durante la review di #350, che ci costruisce sopra. |
| 051 | 051_s4_shadow_lifecycle.sql | 2026-08-25 | Applicata a mano. Lifecycle shadow S4 (#295/#350): tabella append-only + 3 viste. Applicata subito dopo 050, da cui dipende. |
| 052 | 052_shadow_failure_reason.sql | 2026-08-25 | Applicata a mano. `ADD COLUMN IF NOT EXISTS failure_reason` + indice parziale (#358). Righe pre-25/08 restano NULL: lì NULL significa «non classificato», non «successo». |
| 053 | 053_s4_p0_shadow_baseline.sql | 2026-08-26 | Applicata a mano prima del deploy del worker (#296/PR #367). Ledger policy + 3 viste di validazione shadow. |
| 054 | 054_llm_response_relevance.sql | 2026-08-26 | Applicata a mano. 6 `ADD COLUMN IF NOT EXISTS` nullable su `llm_responses` (#328/PR #357). **Rinumerata da 052 in review**: 052 e 053 erano gia' occupate. NULL = campo omesso dal modello, distinto dal default dello schema. |
| 055 | 055_s4_exit_policy_current_tiebreak.sql | 2026-08-27 | Applicata a mano insieme al deploy di #374/PR #375. Vista `s4_exit_policy_current` con tie-break deterministico. Presenza verificata sul live il 2026-09-02. |
| 056 | 056_stop_strategy_attribution.sql | 2026-08-29 | Applicata col merge di #393. Attribuisce la coorte legacy e vieta `trades.stop_strategy` NULL (vincolo `NOT VALID`, non retroattivo). Colonna verificata sul live il 2026-09-02. |
| 057 | 057_quantity_remaining.sql | 2026-09-01 | Applicata a mano con deploy + repair (#397/PR #445): `ADD COLUMN IF NOT EXISTS trades.quantity_remaining`. NOK/WDC/MRVL riconciliati col broker lo stesso giorno. Colonna verificata sul live il 2026-09-02. |
| 058 | 058_portfolio_session_grid_metrics.sql | **NON applicata** | Merge di #428 il 2026-09-01, ma la tabella `portfolio_session_grid_metrics` **non esiste sul live** (verificato il 2026-09-02). Finche' resta cosi', la misura dei margini dei cicli sulla seduta non ha dove scrivere. |
| 059 | 059_ensemble_cycle_health.sql | 2026-09-01 | Applicata col deploy di #427/PR #463 (container ripartiti alle 20:20 UTC, cioe' 20 minuti **dopo** la chiusura). Tabella presente e vuota al 2026-09-02: e' atteso, il worker esce con `market_closed` prima di scrivere. Le prime righe sono attese dalla seduta del 2026-09-02. |

## Convenzione

- Una riga per migrazione, in ordine numerico
- Data = giorno di applicazione al DB live
- "NON applicata" per le pending
- Note = contesto rilevante (backfill, rename, vincoli)

## Come verificare

Questo file e' tracciamento manuale e resta indietro (e' successo con la 046: applicata il
2026-09-01, ancora marcata "NON applicata" il 2026-09-02, e con le 055-059 mai aggiunte).
Prima di fidarsene, interrogare lo schema:

```bash
docker exec alembic-postgres-1 psql -U trading -d trading -c "\\d <tabella>"
docker exec alembic-postgres-1 psql -U trading -d trading -t -A -c \
  "SELECT count(*) FROM pg_tables WHERE tablename='<tabella>';"
```

Ultima verifica completa dello stato di questo file contro il live: **2026-09-02**.