# Review avversaria del fix #192 — barre Alpaca RAW → adjusted nei forward return

Sei un reviewer avversario. Reviewa un fix GIÀ applicato (code-fix in PR non mergiata + recompute GIÀ eseguito LIVE sul DB di un paper-trading system) e dai un verdict GO / NO-GO su merge + deploy. Sii scettico: lo storico di `sentiment_signals` (6562 righe) è già stato ricalcolato sul DB live, quindi un errore nella logica del recompute significa che 6562 righe di un sistema attivo ora potrebbero contenere valori sistematicamente sbagliati. Non fidarti dei numeri che ti riporto — verificane alcuni in modo indipendente.

## Come ottenere il codice
- PR: https://github.com/Jonbj/alembic/pull/194 (branch `fix/fwd-returns-adjusted-bars`, commit `27004a9`). `gh pr diff 194` per il diff.
- Issue: `gh issue view 192` (body aggiornato con correzione impatto + sezione "Recompute eseguito").
- Diagnostico read-only di quantificazione/verify: `scripts/quantify_fwd_return_adjustment_gap.py` (committato in `5330cb3`). Puoi ri-eseguirlo nel container per verifiche indipendenti:
  `docker compose exec -T worker python - < scripts/quantify_fwd_return_adjustment_gap.py`
- Backup raw pre-recompute (NON committato, sul working tree host): `backups/sentiment_signals_fwd_raw_backup_20260807.csv` (6848 righe).
- DB live: `docker compose exec -T postgres psql -U trading -d trading -c "..."` per query dirette.

## Background

`StockBarsRequest.adjustment` (alpaca-py) ha default `None` → query param omesso → Alpaca REST serve barre **RAW** (non adjusted per split/dividendi). I forward return di `sentiment_signals` erano calcolati su barre raw → split/reverse-split/ex-dividend dentro la finestra di hold producevano return spuri (es. INTW forward split → 1d −88% invece di −7.8%; PAVS reverse split → 5d +5199% invece di −46.6%). L'IC su questi return alimenta l'ICIR che drive i pesi ensemble (`ensemble:weights:current`) → money-path potenziale.

Repo: Alembic, LLM-based ATS (FastAPI+Celery+Redis, Alpaca paper/live). LLMs mai nel hot path. Stack live: container `alembic-postgres-1` + `alembic-redis-1` + `alembic-worker-1`. `src/` è BAKED nel container worker (non mounted).

## Scope delle modifiche

1. **Code-fix `adjustment=Adjustment.ALL`** su 6 siti (import `Adjustment` da `alpaca.data.enums`):
   - `scripts/compute_label_forward_returns.py` — `_forward_returns`, 2 req (daily + minute 1h) [golden set QX-01]
   - `src/workers/performance.py` — `run_forward_return_worker` (req ~1630) + `run_counterfactual_worker` (req ~2216)
   - `src/workers/execution.py` — `_build_market_cache` (req ~252), EMA entry-gate ← **behavior change LIVE**
   - `src/portfolio/spy.py` — `fetch_spy_closes` (req ~90), benchmark SPY
   - Precedente corretto: `src/backtest/data/alpaca_loader.py` (già `adjustment="all"`)
2. **Regression test** `tests/workers/test_forward_return_horizons.py::test_worker_requests_iex_feed`: `assert req.adjustment == Adjustment.ALL` (7 test verdi, hermetic per CI).
3. **`scripts/recompute_fwd_returns_adjusted.py`** (NUOVO, 154 righe): recompute one-shot dello storico `sentiment_signals.forward_return_{,3d,5d}` da barre adjusted. **Già eseguito LIVE** (6562 righe sovrascritte, UPDATE diretto no COALESCE).

## Decisioni già prese — valutale, non darle per scontate

- **EMA entry-gate incluso** = behavior change live accettato dall'operatore. Prima l'EMA usava barre raw (jump al split); ora adjusted. Valuta se può flippare entry decision in modo problematico ai bordi di split/dividendo.
- **Recompute con UPDATE diretto**, NON `bulk_add_forward_returns` (che usa `COALESCE(%s, col)` → `None` preserverebbe il raw contaminato). Quindi orizzonti non recomputabili diventano NULL (pending) invece di mantenere il raw.
- **Impatto produzione dichiarato ~0.0001** (watchlist-only), NON ~0.04 (quello è all-symbols incl. outlier off-watchlist PAVS/INTW). La watchlist (~96 mega/large-cap, `config/trading.yaml`) è il filtro `symbol = ANY(%s)` dell'IC di produzione → esclude i micro-cap contaminati.
- **Counterfactual (1h minute) NON recomputato** (lo storico `execution_decisions.counterfactual_return_1h` intatto) — assunzione: finestra 1h senza esposizione a corporate action.
- Freeze #171 (03/08→28/09, niente tarature) — operatore ha marked il bug-fix exempt (`freeze-ok`).

## Punti ad alto rischio da scrutinare (verifica ATTIVA, non riassunto)

1. **Siti mancanti.** Grep tutti i `StockBarsRequest(` e `get_stock_bars(` nel repo. Ogni call site che NON setta `adjustment=` è un bug gemello. Conferma che i 6 siti sono TUTTI quelli che fetchano barre daily/hourly per misurazione o trading (controlla `src/workers/`, `src/portfolio/`, `src/api/`, `src/backtest/`, `scripts/`). Particolare attenzione a eventuali loader di `backtest_signals` (orizzonte 24h — vedi punto 8).
2. **Fedeltà del recompute al worker.** Apri `src/workers/performance.py` `run_forward_return_worker` e confronta riga per riga con `scripts/recompute_fwd_returns_adjusted.py::recompute()`. Verifica IDENTICI: (a) `signal_date = generated_at.date()` + regola `hour >= 21` UTC (soglia esatta, gestione tz naive vs aware); (b) T0 = primo trading day `>= signal_date`; (c) `fwd[n] = (close[t_dates[n]] - close_t0)/close_t0` per n∈{1,3,5}; (d) `None` se bar insufficienti; (e) campo del bar usato (close) e indice/data usato come chiave. UNA divergenza = 6562 righe sistematicamente sbagliate → NO-GO + rollback dal backup.
3. **Finestra di fetch del recompute.** Lo script fetcha `start-2d .. end+12d` per simbolo. Il worker usa una finestra diversa? Se la finestra del recompute è PIÙ STRETTA di quella che il worker userebbe, orizzonti che il worker avrebbe computato potrebbero risultare NULL nel recompute (dati validi cancellati → pending). Verifica che la finestra copra T0 e T+5 per i segnali ai bordi (generated_at min/max).
4. **UPDATE diretto + NULL.** Verifica che: (a) gli orizzonti NULL nel recompute erano GIÀ NULL pre-recompute (pending, non dati validi cancellati) — confronta le righe partial col backup; (b) il worker riprenderà i NULL via `fetch_signals_pending_forward_return` (leggi `src/store/pg_store.py`: la WHERE clause include `forward_return IS NULL OR forward_return_3d IS NULL OR forward_return_5d IS NULL`?). Se il worker NON riprende i NULL, le righe partial restano con orizzonti NULL permanentemente.
5. **Honesty dell'impatto.** Verifica in modo indipendente: (a) PAVS e INTW NON sono in `config.WATCHLIST_SYMBOLS`; (b) `fetch_all_signals_for_ic` / `fetch_all_per_model_signals_for_ic` in `src/store/pg_store.py` filtrano `symbol = ANY(%s)` con la watchlist; (c) il ~0.0001 è plausibile (IC watchlist-only near-zero, contaminazione quasi tutta micro-cap off-watchlist). Se PAVS/INTW fossero watchlistati, o se l'IC NON fosse watchlist-filtered, l'impatto sarebbe ~0.04 e il fix sarebbe money-path-critico → cambia la prioritizzazione e il done-signal.
6. **Counterfactual 1h.** Valuta se una finestra 1h di barre MINUTE può attraversare una corporate action. Split/dividendi applicano al market open. Una finestra 1h intraday same-day non attraversa un open → raw==adjusted intra-day. Ma: la finestra del counterfactual spanna mai la mezzanotte o include l'open stesso? Leggi `run_counterfactual_worker` e conferma che la window è intraday same-day; altrimenti lo storico `execution_decisions` (non recomputato) è contaminato e andrebbe recomputato.
7. **Test gaps.** Asserzione nuova solo sul forward-return worker req. NON testati: counterfactual `req.adjustment`, `compute_label` req, `spy` req, EMA req. E `scripts/recompute_fwd_returns_adjusted.py` non ha test (la logica è replicata al worker, punto 2, ma non testata). Valuta se serve un test recompute-vs-worker su fixture note.
8. **`backtest_signals` orizzonte 24h.** Fuori scope ("verificare separatamente"). Il 24h PUÒ attraversare corporate action. Verifica se `backtest_signals` fetcha barre raw per l'orizzonte 24h → bug gemello non fixato da flaggare come follow-up.
9. **Deploy state & done-signal.** Il recompute è già live (touchless, DB). Il code-fix è live solo dopo `docker compose build worker && docker compose up -d worker` (src/ baked). Fino ad allora il worker running (vecchio codice) scrive RAW → re-contaminazione al prossimo run del forward-return worker. La PR ha `Closes #192` → al merge l'issue chiude ma il deploy è pendente. Valuta se chiudere #192 al merge è il done-signal corretto o se l'issue dovrebbe restare aperta fino a deploy verificato.

## Numeri che ho verificato (ri-verifica i critical in modo indipendente)

- Post-recompute: contamination (stored−adj) = 0.0000% su 1d/3d/5d; IC delta = +0.0000 (stored == adj).
- Worst-case spot-check: INTW id945 1d −88.49%→−7.83%; PAVS id821 5d +5199%→−46.64%.
- Row count preservato: non-null 1d/3d/5d = 6562/6167/5790; 286 righe all-NULL pending untouched; tabella totale 6848 (backup 6849 righe incl. header).

## Vincoli operativi

- DB live già scritto dal recompute. Non reversibile facilmente se non via backup CSV → re-UPDATE. La review è in parte RETROSPETTIVA sul recompute.
- Paper trading (no soldi reali) ma sistema attivo e monitorato (Telegram, dashboards).
- Repo NON branch-protected → merge su review. Nessun merge senza review operatore.

## Deliverable

Lista di finding ranked (most-severe first), ognuno con: `file:line`, claim, scenario di failure concreto (input/stato → output/crash sbagliato), verdict (CONFIRMED / PLAUSIBLE), fix suggerito. Alla fine: **verdict GO / NO-GO su merge + deploy** con i blocker eventuali. Se la logica del recompute diverge dal worker (punto 2) o se orizzonti validi sono stati NULL-ati (punto 4a), è **NO-GO** — i 6562 valori live sono sbagliati e serve rollback dal backup + recompute corretto.