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

## Convenzione

- Una riga per migrazione, in ordine numerico
- Data = giorno di applicazione al DB live
- "NON applicata" per le pending
- Note = contesto rilevante (backfill, rename, vincoli)