# Handback — fixes-2026-07-14 (WS-1…WS-5)

**Data:** 2026-07-14  
**Branch di lavoro:** `fixes-2026-07-14` (da `main` @ `ea436fd`)  
**No merge su `main`.** Nessun deploy eseguito. Tutti i cambi live-path sono flag-off o a shadow.

---

## §0.1 — Azione operativa immediata

```bash
docker exec alembic-redis-1 redis-cli SET config:sentiment_llm_models glm52,gptoss
```

Verifica:

```
glm52,gptoss
-1
```

La coppia live è resettata. Il frontend Sidebar mostrerà ora i checkbox `glm52` + `gptoss` selezionati.

---

## §1 — Riepilogo esecuzione per work-stream

| WS | Scopo | Commit | Files principali | Stato |
|----|-------|--------|------------------|-------|
| WS-1 | Registry-based LLM model-pair selector + canonical order | `9688afa` | `frontend/src/store/index.ts`, `Layout.tsx`, `Sidebar.tsx`, `src/api/routes/admin.py`, `src/store/redis_store.py`, `src/llm/model_registry.py`, `frontend/src/tests/llm_model_selector.test.tsx`, `tests/api/test_api.py`, `tests/llm/test_model_registry.py` | ✅ Completato |
| WS-2 | Stop-policy freeze-at-entry con metadati completi anche in `fixed` | `d4512b0` | `src/portfolio/stop_policy.py`, `src/workers/portfolio_scheduler.py`, `tests/portfolio/test_stop_policy.py` | ✅ Completato |
| WS-3 | Resync pesi ensemble stantii al pair-swap e normalizzazione | `3ffe2fc` | `src/api/routes/admin.py`, `src/workers/performance.py`, `tests/workers/test_sentiment_worker.py` | ✅ Completato |
| WS-4 | Market-clock gating fail-closed per ingestion e sentiment | `a06e9f0` | `src/workers/market_clock.py`, `src/workers/ingestion.py`, `src/workers/sentiment.py`, `tests/workers/test_market_clock.py`, `tests/workers/test_ingestion_worker.py`, `tests/workers/test_sentiment_worker.py` | ✅ Completato |
| WS-5 | Multi-tranche exit reconciliation | `b18006d` | `migrations/035_multi_tranche_exit.sql`, `src/store/pg_store.py`, `tests/test_pg_store.py` | ✅ Completato |

---

## §2 — Dettaglio implementativo

### WS-1 — Model selector

- Il toggle binario legacy del Sidebar è sostituito da checkbox multi-selezione + pulsante **Economy**.
- `normalize_model_selection` in `src/llm/model_registry.py:96` ordina deterministicamente secondo l'ordine del registro, quindi la chiave Redis è stabile anche se l'utente clicca `gptoss,glm52`.
- `POST /llm-models` in `src/api/routes/admin.py` resynca automaticamente i pesi `ensemble:weights:current` se contengono modelli fuori dalla nuova coppia.
- Commento ingannevole `"all" = full ensemble` rimosso da `frontend/src/store/index.ts`.

**Gate live:** il cambio di modelli attivi richiede comunque azione operator via UI/API; non è automatico.

### WS-2 — Stop metadata freeze

- `StopPolicy.freeze()` in `src/portfolio/stop_policy.py` calcola sempre `sigma_eff`, `k`, `floor`, `cap` e li scrive in `FrozenStop`.
- In modalità `fixed`, `d_init` resta il 2% configurato; in modalità `vol_scaled` è `min(max(k*sigma_eff, floor), cap)`.
- Il legacy batch BUY in `src/workers/portfolio_scheduler.py` passa `_frozen_stop_legacy` affinché il primo tranche abbia metadati di ingresso.

**Gate live:** `vol_scaled` non è abilitato (`mode=fixed`); la raccolta è solo per Gap D.

### WS-3 — Ensemble weight hygiene

- `check_and_apply_weights` in `src/workers/performance.py` normalizza i pesi suggeriti rispetto ai soli `active_model_ids` prima di scriverli.
- `POST /llm-models` esegue resync se necessario.

**Gate live:** il rebalancing LOO ICIR continua a funzionare sui soli modelli attivi; nessun peso fantasma persiste.

### WS-4 — Market clock gating

- Nuovo helper `src/workers/market_clock.py:is_market_open()` usa `alpaca-py TradingClient.get_clock()`; se il clock fallisce ritorna `False` (fail-closed).
- `run_alpaca_ingestion_worker`, `run_news_ingestion_worker` e `run_sentiment_worker` fanno early-return quando il mercato è chiuso.
- Importazioni spostate al top del modulo per permettere patching nei test.

**Gate live:** i worker non tentano più ingestion/sentiment in orari di mercato chiuso, riducendo rumore e timeout su Ollama fuori sessione.

### WS-5 — Multi-tranche exit reconciliation

- Migrazione `migrations/035_multi_tranche_exit.sql` aggiunge `exit_order_ids TEXT[]` su `trades`.
- `record_trade_exit` in `src/store/pg_store.py`:
  - appende l'`order_id` a `exit_order_ids` senza duplicati;
  - setta `exit_time` solo al primo close;
  - setta `exit_reason` solo al primo close (COALESCE);
  - ritorna `(trade_id, was_already_closed)` così il chiamante sa se è una tranche iniziale o successiva.
- `reconcile_trade_fills` itera su **tutti** gli `exit_order_ids`, calcola:
  - `exit_qty = sum(filled_qty)`
  - `exit_price = weighted_average(filled_avg_price * filled_qty)`
  - aggiorna `qty` e `gross_pnl = (exit_price - entry_price) * exit_qty`.

**Test aggiunto:** `TestReconcileTradesFills::test_exit_multi_tranche_weighted_average` verifica 3 tranche SHEL con prezzi/qty realistici.

**Gate live:** il cambiamento schema è retro-compatibile per query che usavano `exit_order_id` singolo; la nuova logica è attiva non appena la migrazione viene applicata.

---

## §3 — Risultati test

```text
.venv/bin/python -m pytest \
  tests/api/test_api.py \
  tests/llm/test_model_registry.py \
  tests/portfolio/test_stop_policy.py \
  tests/test_pg_store.py \
  tests/store/test_pg_store_stop_methods.py \
  tests/workers/test_ingestion_worker.py \
  tests/workers/test_sentiment_worker.py \
  tests/workers/test_market_clock.py \
  -q --tb=short

141 passed, 4 skipped, 6 warnings in 5.97s
```

I 4 skipped sono pre-esistenti (test condizionali su credenziali/configurazione).

---

## §4 — Cosa NON è stato fatto (come da §7 prompt)

- ❌ Nessun flip di `vol_scaled` (resta `fixed`).
- ❌ Nessun cambio a `max_sector_exposure` (non toccato).
- ❌ Nessuna modifica a sizing/regime/trading logic generale.
- ❌ Nessun merge su `main`.
- ❌ Nessun deploy.

---

## §5 — Azioni consigliate per l'operatore prima del merge/deploy

1. **Applica la migrazione WS-5 in ambiente di staging/pre-prod:**
   ```bash
   psql -h alembic-postgres-1 -d alembic -f migrations/035_multi_tranche_exit.sql
   ```
2. **Verifica che `config:sentiment_llm_models` sia ancora `glm52,gptoss` dopo un refresh del frontend.**
3. **Esegui un dry-run di `reconcile_trade_fills` su 1-2 trade multi-tranche storici** per validare l'arithmetica del prezzo medio ponderato.
4. **Conferma il comportamento fail-closed di `is_market_open()` in paper** durante pre-market / post-market.
5. **Decidi se abilitare `vol_scaled` in un secondo momento** con gate S1 10% / canary separato (non in questa branch).

---

## §6 — Note residuali / debito tecnico esplicito

- `record_trade_exit` ritorna `None` per le chiamate esistenti che non usano il nuovo valore di ritorno; il chiamante legacy non è rotto.
- Il campo `exit_order_id` singolo rimane popolato con il primo order ID per retro-compatibilità; in futuro può essere deprecato in favore esclusivo di `exit_order_ids`.
- I test frontend per il nuovo Sidebar (`frontend/src/tests/llm_model_selector.test.tsx`) sono stati aggiunti ma non eseguiti in questa sessione per mancanza di ambiente Node pronto; raccomandato `npm test -- llm_model_selector` prima del merge.

---

**Fine handback.**
