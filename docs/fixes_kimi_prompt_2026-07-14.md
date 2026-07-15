# Prompt per Kimi 2.7-code — Fix rilevati il 2026-07-14 (implementazione)

Sei un ingegnere senior. Implementa una batteria di fix su un sistema di trading
algoritmico live (Alembic, "Alpha Miner ATS", paper trading). Lavori nel repo (hai
accesso ai file). Questo prompt è autosufficiente; le root-cause sono già diagnosticate
(con `file:line` verificati il 2026-07-14 su `main`) — il tuo compito è implementarle
fedelmente, non ri-diagnosticare.

Sono **5 work-stream indipendenti** (WS-1…WS-5), ordinati per urgenza. Possono essere
svolti in sequenza; **non c'è dipendenza tra loro** salvo dove esplicitato. Per ciascuno:
root-cause con `file:line`, direzione di fix, test di accettazione, gate.

---

## 0. Prima di tutto

1. **Azione operativa NON di codice (falla tu ora, una riga):**
   ```
   docker exec alembic-redis-1 redis-cli SET config:sentiment_llm_models glm52,gptoss
   ```
   La selezione modelli è di nuovo su `"all"` (degraderebbe i segnali del prossimo task).
   Re-setta la coppia live `glm52,gptoss`. Questo NON risolve il bug — vedi WS-1.

2. **Leggi per contesto (read-only):**
   - `docs/FORENSIC_DAILY_REPORT_2026-07-13.md` — evidenza quantitativa del 07-13
     (fallback 57%, 14 stop del cohort 07-10, gap DST, bug SHEL 3-tranche).
   - `CLAUDE.md` §Tech Stack (coppia LLM, registry `in_all` semantics).
   - `src/llm/model_registry.py` — la registry con `in_all` flags.

3. **Verifica ogni `file:line`** citato qui contro il tuo checkout prima di editare
   (usa `Agent(subagent_type="Explore")` per fan-out read-only sui simboli). Se il codice
   si è mosso, adatta la posizione ma **non cambiare la semantica** del fix descritto.

---

## 1. Protocollo di esecuzione

- **Autonomo dall'inizio alla fine**: non bloccarti a fare domande, documenta le decisioni
  inline e prosegui. Unica fermata hard = un gate di misura che FAIL.
- **Un fix alla volta per work-stream**: niente "while I'm here" che fondono WS.
- **TDD ove possibile** (WS-1, WS-2, WS-3 hanno superficie testabile). Per WS-4/WS-5
  (scheduler/reconcile) usa test mirati o script di verifica read-only.
- **Flag-off / shadow dove il fix tocca il path di esecuzione live**: tutti questi fix
  salvo WS-1 sono misurabili o dietro flag; non flippare nulla in live senza gate.
- **Branch dedicato** `fixes-2026-07-14` da `main`. Commit per work-stream.
- **Alla fine restituisci un handback strutturato** (§6) — deliverable obbligatorio come
  il codice.

---

## WS-1 (URGENTE) — Selettore coppia modelli nel frontend

### Root-cause (diagnosticata 2026-07-14)

Il toggle del Sidebar è **strettamente binario** e non può esprimere la coppia live
`glm52,gptoss`. Inoltre `"all"` NON significa "la coppia live" — si espande nei modelli
con `in_all=True` = `{kimi, glm52}` (la VECCHIA coppia del 07-01), che è peggiore (kimi =
worst-accuracy, lento). Ogni click sul toggle distrugge la coppia impostata manualmente.

- `frontend/src/components/layout/Sidebar.tsx` (~linea 25-40):
  ```js
  const isSavings = llmModels !== 'all'
  const toggleSavings = async () => {
    const next = isSavings ? 'all' : 'glm52'   // ← scrive SOLO "all" o "glm52"
    ... POST /api/admin/llm-models { models: next } ...
  }
  ```
  Label bug: quando la coppia è `"glm52,gptoss"`, `isSavings = "glm52,gptoss" !== 'all'`
  → `true` → il pulsante mostra **"Economy (GLM-5.2)"** (falso: è la coppia piena).
  L'operatore vede "Economy", clicca per il "Full ensemble" → scrive `"all"` → reverte.

- `frontend/src/store/index.ts` (~linea 13, 31, 37): default `llmModels: 'all'`,
  commento stale `"all" = full ensemble, "glm52" = GLM-5.2 economy mode`.

- `frontend/src/components/layout/Layout.tsx` (~linea 88-95): polling `GET /api/admin/status`
  ogni 15s, legge `data.llm_models` → `setLlmModels`. (Questo è solo sync, **non** scrive
  `"all"` — lo scrive solo il click del toggle.)

- `src/api/routes/admin.py`:78 (`GET /status`) e :92-111 (`POST /llm-models`). Docstring
  **stale**: il POST docstring elenca `"kimi, qwen, deepseek, glm"` (modelli non presenti
  nella registry); `redis_store.set_llm_models` docstring dice `"all" → Kimi + GLM-5.2`.

- `src/llm/model_registry.py:84-110` `normalize_model_selection`: `"all"` →
  `keys = [m.key for m in _MODELS if m.in_all]` = `{kimi, glm52}`. `gptoss` ha `in_all=False`
  (linea 32) → **mai incluso in `"all"`**.

- Timeline: toggle aggiunto 07-01 (commit `96e5bf6`, mondo kimi/glm52); gptoss/qwen35
  registrati 07-11 (commit `7d530bb`, `in_all=False`); **toggle mai aggiornato**.

### Direzione di fix (decisa)

Sostituire il toggle binario con un **selettore coppia basato sulla registry**:
- Il `GET /api/admin/status` già restituisce `llm_model_registry` (`LLMModelsData` con
  `models: LLMModelInfo[]` dove ogni modello ha `key, model_id, label, active,
  economy_default`). Usa quello per renderizzare un multi-select (o dropdown) dei modelli
  selezionabili, con la coppia corrente spuntata.
- L'etichetta del pulsante/banner deve **riflettere lo stato reale**: mostrare i modelli
  attivi (es. "GLM-5.2 + GPT-OSS"), non "Economy" per qualsiasi valore ≠ `"all"`.
- POST invia la lista dei modelli spuntati come stringa comma-separated (es. `"glm52,gptoss"`).
  `normalize_model_selection` già la accetta e la canonicalizza correttamente (verificato).
- Mantieni una scorciatoia "Economy (GLM-5.2)" come preset separato (imposta `glm52`
  solo) se vuoi conservare la funzionalità di risparmio, ma **non usare più `"all"` come
  stato del toggle** — o, se lo mantieni, renderizza chiaramente che `"all"` = kimi+glm52
  (i modelli `in_all`) e NON la coppia live. Decisione di design tua; documenta la scelta.
- Aggiorna i docstring stale in `admin.py` e `redis_store.set_llm_models`.

### Accettazione
- Test frontend: quando il backend ha `llm_models="glm52,gptoss"`, il selettore mostra
  glm52 e gptoss spuntati, etichetta corretta, e nessun click involontario scrive `"all"`.
- Test backend (se manca): `POST /llm-models {models:"glm52,gptoss"}` → canonical
  `"glm52,gptoss"`, `GET /status` lo riporta invariato.
- Verifica end-to-end: imposta `"glm52,gptoss"`, ricarica la UI, il selettore riflette la
  coppia, ricarica ancora — **non reverte a `"all"`**.

### Gate
Nessun gate di misura (frontend + API, no path di trading). Flip live diretto dopo review.

---

## WS-2 — Gap D: persistere i metadata di stop all'entry (freeze-at-entry)

### Root-cause

Il redesign stop-loss F9a (commit `7cc6a91`→`99215ff`, 07-11) ha wire-ato lo schema
freeze-at-entry (migration 034) e il modulo `StopPolicy`, ma **i metadata di stop non
vengono persistiti all'entry**. Verifica live 07-14: su tutti i trade aperti oggi,
`trades.stop_vol_at_entry`, `stop_k`, `stop_floor`, `stop_cap` sono **NULL**, e in
`stop_decisions` le colonne `vol_at_entry`, `k`, `sigma_eff` sono NULL anche sulle stop
fire-ate (solo `entry_price`, `trigger_price`, `d_init`, `observed_price` sono popolate).

**Conseguenza:** il mode `vol_scaled` (parcheggiato) **non può essere abilitato** perché
mancano gli input di sizing (σ/k/floor/cap congelati all'entry). F9a fase 6 (gate) è
bloccata da questo. È il **prerequisito** per sbloccare l'handoff F9a già aperto
(`docs/stop_loss_kimi_handback.md`).

- `src/store/pg_store.py:735-754` `_INSERT_TRADE`: lo schema ha già le colonne
  `stop_strategy, stop_mode, stop_vol_at_entry, stop_k, stop_floor, stop_cap,
  stop_d_init, stop_vol_source` — l'INSERT le accetta, ma il caller passa NULL.
- `src/store/pg_store.py` `record_trade_entry` (def sopra la `_INSERT_TRADE`): trova il
  caller e verifica quali parametri stop passa. L'entry path parte da
  `src/workers/portfolio_scheduler.py` (e/o `execution.py`) → `record_trade_entry`.
- `src/store/pg_store.py:1049` `INSERT INTO stop_decisions`: popola solo alcune colonne.
- `src/workers/portfolio_scheduler.py:1915` "Persist stop_decisions fire log" — questo è
  il path di fire (exit), non di freeze-entry.

### Direzione di fix

1. Traccia l'entry path: dove si crea la posizione e si calcola lo stop (il `StopPolicy`
   / `freeze-at-entry` già calcola σ, k, floor, cap, d_init a runtime per decidere il
   trigger — vedi `src/risk/` o dov'è `StopPolicy`). **Quegli stessi valori devono essere
   passati a `record_trade_entry` e scritti nelle colonne `stop_*` di `trades`.**
2. Quando una stop fire-a (`stop_decisions` insert a pg_store.py:1049), popola anche
   `vol_at_entry`, `k`, `sigma_eff`, `floor`, `cap` leggendoli dal trade congelato
   (dovrebbero ora essere non-NULL su `trades` grazie al punto 1; o passali direttamente
   dallo StopPolicy al fire).
3. Non cambiare il mode live (resta `fixed`); questo fix popola solo i metadata.
   L'abilitazione di `vol_scaled` resta un flip separato gated (F9a fase 6).

### Accettazione
- Su nuovi trade aperti dopo il fix: `trades.stop_vol_at_entry`, `stop_k`, `stop_floor`,
  `stop_cap`, `stop_d_init`, `stop_vol_source` **non-NULL** (per mode `fixed` popola
  comunque d_init e i valori che il policy calcola; vol_at_entry/k/floor/cap se
  calcolati, anche se il mode è fixed).
- Su nuove stop fire: `stop_decisions.vol_at_entry`, `k`, `sigma_eff` non-NULL.
- Test: un test che apre un trade (o un fixture) e verifica le colonne popolate.
- Verifica read-only su DB live post-deploy: le 5 colonne non-NULL sui nuovi trade.

### Gate
- Flag-off: il popolamento metadata è sicuro (non cambia behavior di esecuzione), ma
  deploya prima in shadow/verifica che non produca errori sui path di entry esistenti.
- **NON abilitare vol_scaled** in questo work-stream — quello è F9a fase 6, handoff
  separato, gated su replay 15-min.

---

## WS-3 — Hygiene: pesi ensemble `ensemble:weights:current` stale

### Root-cause (severity: hygiene, NON corruption live)

`ensemble:weights:current` = `{"kimi":0.41, "qwen3.5":0.59}` — pesi LOO-ICIR scritti
 quando la coppia era diversa, **mai ri-sincronizzati dopo lo swap a glm52+gptoss**.
 L'auto_apply guardrail richiede la chiave VIX etc.; su stato fresco non aggiorna.

**Importante — non è un corruption live:** `src/workers/sentiment.py:488-504` già
filtra i pesi con `normalize_weights_for_active_models(...)`, che **droppa i modelli non
nella coppia attiva**. Quindi kimi+qwen3.5 vengono scartati a runtime e l'ensemble usa
pesi uniform su glm52+gptoss. Il danno è solo cosmetico/audit (la chiave mente sullo
stato) + confusione in dashboard (`frontend/src/pages/LLM.tsx` tab "Pesi ensemble").

- `src/workers/performance.py:1374` `set_ensemble_weights(suggested_weights,
  source="auto_apply")` — dove vengono scritti i pesi stale.
- `src/workers/performance.py:780` `run_weekly_weights` (lunedi 04:00 UTC) — il
  rebalancing settimanale.
- `src/llm/model_registry.py:124` `normalize_weights_for_active_models` — il filtro.

### Direzione di fix
- Al **swap di coppia** (POST `/llm-models` con nuova selezione, WS-1), **invalida /
  cancella** `ensemble:weights:current` se i pesi referenziano modelli non più attivi
  (o forzane il re-sync uniform). Così la dashboard non mostra pesi di una coppia morta.
- Alternativa/minimo: in `run_weekly_weights`, se i pesi suggestionati referenziano
  modelli non nella coppia attiva, non scriverli (o normalizza prima di scrivere).
- Documenta che i pesi sono per-model e devono sempre ⊆ coppia attiva.

### Accettazione
- Dopo un swap coppia, `GET /api/.../weights` non mostra più kimi+qwen3.5 se la coppia
  è glm52+gptoss (mostra uniform o i pesi della coppia attiva).
- Test: swap → check weights coerenti con la coppia attiva.

### Gate
Nessuno (hygiene + dashboard). Flip live diretto.

---

## WS-4 — Disallineamento DST: finestra Celery non insegue l'orario reale di mercato

### Root-cause (dal forense 07-13)

Il beat schedule ha la finestra **hardcoded `hour="14-21"` UTC** (mon-fri). Ma NYSE in
EDT apre 13:30 e chiude 20:00 UTC. Conseguenze misurate 07-13:
- **Primi 30 min di sessione persi** (13:30-14:00 UTC): nessuna ingestion/scoring attivo.
- **~88 segnali/giorno (~29% del volume) ingeriti dopo le 20:00 UTC** (post-chiusura reale)
  e **mai consumati** da un ciclo di portfolio (l'ultimo ciclo è alle 19:52).

- `src/workers/celery_app.py:65-200` `beat_schedule`: sentiment-worker, ingestion
  (alpaca/gdelt), portfolio-cycle, ecc. tutti `crontab(..., hour="14-21", ...)` o
  `minute="*/15", hour="14-21"`.
- `src/workers/celery_app.py:51` `timezone="UTC"`.
- Il portfolio_scheduler **già** interroga l'orologio reale Alpaca
  (`trading_client.get_clock().is_open`) e si ferma a mercato chiuso — ma l'**ingestion**
  no, continua a ingerire fino alle 21:00 UTC.

### Direzione di fix (decidi e documenta)
Opzione A (preferibile, robusta): gate-are ingestion + sentiment sullo stesso clock
Alpaca già usato dal portfolio (`is_open`), invece di una crontab hardcoded. Le task
partono comunque via beat ma escono subito se mercato chiuso.
Opzione B: spostare la crontab a `hour="13-20"` (EDT approssimato) — ma **non risolve il
DST** (EST vs EDT shift di 1h due volte l'anno); peggiore di A.
Opzione C: parametrizzare la finestra da config (`trading.yaml`) con valori EDT-aware
e un job che la ricalcola. Più complesso.

**Raccomandata A** (coerenza con il portfolio, niente magic numbers UTC, immune al DST).

### Accettazione
- Fuori mercato reale (pre 13:30 / post 20:00 UTC in EDT), ingestion e sentiment non
  producono segnali "orfani" (verifica: conteggio segnali con `generated_at` > 20:00 UTC
  scende a ~0 nei giorni di mercato).
- Primi 30 min (13:30-14:00 UTC) ora coperti.

### Gate
Misura read-only pre/post: `scripts/`-style query su `sentiment_signals.generated_at`
per ora UTC, confronta prima/dopo. Non flippare senza un giorno di confronto.

---

## WS-5 — Bug reconciliation uscite multi-tranche (SHEL)

### Root-cause (dal forense 07-13)

SHEL è uscita in 3 tranche (18:22, 19:22, 19:52 UTC) ma il ledger `trades` registra solo
la **prima tranche** — P&L e qty delle tranche 2-3 persi.

- `src/store/pg_store.py:1359` `reconcile_trade_fills`: la sezione exit-reconcile
  (dopo `# Reconcile exit fills`) fa `SELECT ... WHERE exit_order_id IS NOT NULL AND
  exit_price IS NULL` e per ogni trade chiama `get_order_by_id(exit_order_id)`.
  **Una trade → un `exit_order_id`** → recupera solo la prima tranche. Le tranche
  successive hanno order_id diversi che non sono referenziati dalla trade row.
- Verifica anche dove viene impostato `exit_order_id` all'uscita (portfolio_scheduler /
  record_trade_exit `src/store/pg_store.py:913`): una posizione parzialmente chiusa
  sovrascrive `exit_order_id` con l'ultimo ordine o accumula? Indaga il path di uscita
  multi-tranche (SELL parziali / weight→0% in più cicli).

### Direzione di fix
- Decidi con il modello dati: (a) una trade = una riga con `exit_order_id` che
  accumula/raggruppa le tranche (memorizza lista order_id + fill aggregato), o
  (b) una trade row per tranche (split), o (c) tabella `trade_fills` figlia.
- Raccomandazione minima: in `reconcile_trade_fills`, per un'uscita multi-tranche,
  recupera **tutti** i fill order dell'uscita e aggrega (prezzo medio pesato su qty,
  P&L sommato). Serve identificare gli order_id delle tranche (mantieni una lista sul
  trade, o query Alpaca per gli order della position close).
- Documenta il modello scelto. Allinea `record_trade_exit` se necessario.

### Accettazione
- Su un'uscita 3-tranche riprodotta (o fixture): `trades.exit_price` = prezzo medio
  pesato delle 3 tranche, `qty`/`gross_pnl`/`net_pnl` coerenti con la somma dei fill.
- Verifica read-only: il caso SHEL reale (07-13) riconciliato correttamente.

### Gate
Misura: replay della reconciliation sul giorno 07-13, confronta P&L pre/post.
Non flippare in live senza verify su dati storici.

---

## 6. Handback strutturato (deliverable obbligatorio)

Alla fine restituisci, per OGNI work-stream:
- **Stato**: DONE / PARTIAL / BLOCKED + gate PASS/FAIL (se applicabile).
- **Commit**: hash + branch `fixes-2026-07-14`.
- **File toccati** (lista).
- **Test**: quali aggiunti, risultato suite (n passed/fail).
- **Verifica live** (read-only): cosa hai controllato su DB/Redis post-deploy (es.
  colonne stop non-NULL su nuovi trade per WS-2; segnali post-20:00 UTC ~0 per WS-4).
- **Decisioni di design** prese (es. multi-select vs dropdown per WS-1; modello dati
  tranche per WS-5; opzione A/B/C per WS-4).
- **Gate da flippare** e prerequisiti (es. WS-2 → sblocca F9a fase 6).
- **Cose NON fatte** e perché.

---

## 7. Cosa NON fare

- Non abilitare `vol_scaled` in WS-2 (è F9a fase 6, handoff separato, gated su replay).
- Non flippare il sector cap (`max_sector_exposure`) — è una decisione operativa
  separata (shipped disabled a 0.0 di proposito, vedi memoria progetto).
- Non toccare la logica di trading / sizing / regime in questi WS — sono fix di
  config/UI/persistenza/scheduler/reconcile, non di strategia.
- Non mergiare su `main`: branch dedicato, nessun deploy senza review.