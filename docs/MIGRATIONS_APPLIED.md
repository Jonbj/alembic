# Migrazioni applicate al DB live

Tracking manuale delle migrazioni PostgreSQL applicate al database di produzione (`alembic-postgres-1`).

> **NOTA**: questo DB non ha tabella `schema_migrations`. Lo stato "applicata o no" vive in questo file. Aggiornare dopo ogni applicazione manuale.

## Stato

| # | File | Applicata il | Note |
|---|------|-------------|------|
| 001–046 | (tutte le migrazioni fino a 046) | Pre-2026-08-22 | Storico non tracciato. Verificare con `psql` se serve. |
| 047 | 047_news_discard_reasons.sql | 2026-08-22 | Applicata a mano. Backfill 3477 righe. |
| 048 | 048_skip_pyramiding_counterfactual.sql | 2026-08-22 | Applicata a mano sotto il nome precedente `046_skip_pyramiding_counterfactual.sql`. |
| 049 | 049_counterfactual_coverage.sql | 2026-08-22 | Applicata a mano. 3 ADD COLUMN + 2 indici. |
| 046 | 046_news_labels_2annotator.sql | NON applicata | Nessun hot path la usa. Modifica UNIQUE con backfill, applicare separatamente. |
| 050 | 050_s4_entry_intent_ledger.sql | 2026-08-25 | Applicata a mano. Ledger intenti S4 (#294): tabella append-only + 2 viste. Era su main dal merge di #294 ma mai applicata al live — scoperta durante la review di #350, che ci costruisce sopra. |
| 051 | 051_s4_shadow_lifecycle.sql | 2026-08-25 | Applicata a mano. Lifecycle shadow S4 (#295/#350): tabella append-only + 3 viste. Applicata subito dopo 050, da cui dipende. |
| 052 | 052_shadow_failure_reason.sql | 2026-08-25 | Applicata a mano. `ADD COLUMN IF NOT EXISTS failure_reason` + indice parziale (#358). Righe pre-25/08 restano NULL: lì NULL significa «non classificato», non «successo». |

## Convenzione

- Una riga per migrazione, in ordine numerico
- Data = giorno di applicazione al DB live
- "NON applicata" per le pending
- Note = contesto rilevante (backfill, rename, vincoli)