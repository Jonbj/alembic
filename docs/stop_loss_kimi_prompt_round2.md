# Prompt per Kimi 2.7-code — Stop-Loss Redesign, Round 2 (completamento gate + Phase 5)

Sei lo stesso ingegnere senior del Round 1. Il tuo handback è arrivato, verificato da Claude.
Hai fatto un lavoro solido sulle fasi 1-4 (migration 034 applicata al DB live, Gap A,
StopPolicy, vol_scaled flag-off). **Tre cose sono incomplete o sotto la barra** e questo
prompt le chiude. Lavori nel repo, autonomo (protocollo §3c del Round 1 vale ancora: non
bloccarti a fare domande, documenta e prosegui; unica fermata hard = gate FAIL).

---

## 0. Leggi prima

1. `docs/stop_loss_kimi_handback.md` — il TUO handback Round 1 (status, §5 remaining work).
2. `docs/superpowers/plans/2026-07-11-stop-loss-redesign.md` — lo spec, **fonte di verità**,
   in particolare **§5 (replay) e §10 (gate)**. Sono la barra a cui ti attieni.
3. `docs/stop_loss_kimi_prompt.md` — il prompt Round 1 (guardrail, seed, return contract).
4. `scripts/replay_stop_loss.py` — il tuo script Round 1 (199 righe), da **augmentare**.

**Dati pronti per te** (Claude li ha preparati, non rifare il fetch daily):
- `data/daily_close.csv` — pivot bar Alpaca daily, 341 giorni × 41 simboli (i simboli dei
  248 trade chiusi). Usalo per `σ_eff` allo stop (passalo come `--bars-csv`).
- I 41 simboli sono in `scripts/replay_stop_loss.py` non hardcodati — derivati dai trade.

**Verifica `file:line`** prima di editare (lo spec è verificato al 2026-07-11; il codice si
è mosso sui TUOI commit, adatta preservando la semantica).

---

## 1. Cosa è stato verificato e i tre buchi da chiudere

### ✅ Fatto e verificato (NON ritoccarli a meno che non li rompa un test)
- Phase 1 migration 034 — applicata al DB live (`stop_*` cols + `stop_decisions` +
  `stop_shadow_log`). **Non riapplicare.**
- Phase 2 Gap A — SELL `execution_decisions` row sullo stop.
- Phase 3 `StopPolicy` + freeze + fire log + shadow log.
- Phase 4 vol_scaled + stop-risk sizing, default `fixed`.

### 🔴 Buco 1 — Il gate di fase 6 è DEBOLE e NON È STATO ESEGNUITO alla barra spec §10
Hai scritto `replay_stop_loss.py` ma:
- (i) **Non lo hai mai lanciato** — nessun numero PASS/FAIL nell'handback. Claude lo ha
  lanciato lui (read-only, 248 trade). Risultato: 9/10 noise-stop evitati (incl. PANW), ma...
- (ii) **Il P&L counterfactual non è calcolato.** Riga `vol_cum_pnl = fixed_cum_pnl` le
  imposta **identiche per costrutto**. `pnl_delta` è solo la somma delle perdite degli stop
  evitati — NON modella cosa fa vol_scaled dopo aver evitato lo stop (tiene? recupera?
  crolla oltre il trigger vol?). Lo spec §10 richiede "bootstrap delta P&L ≥70-75%" —
  qui è letteralmente non calcolato.
- (iii) **Niente path intraday.** Usi `exit_price` come prezzo osservato. Lo spec §5
  richiede bar 15-min in `[entry_time, exit_time]`, trova il primo timestamp in cui
  `low <= trigger` → `stop_time`, `exit_fill = min(trigger*(1-slip), next bar open)`.
- (iv) **Solo 3 criteri** (sample≥20, avoided≥2, missed≤avoided) vs i **7+ dello spec §10**
  (bootstrap, walk-forward, ES95, max-DD, name-dependence).
- (v) **Sample**: solo 11 exit `stop_loss` reali su 248 trade. La metrica "false-stop
  reduction" su 11 soli stop ha bassa potenza. **Devi analizzare tutti i 248 trade per
  MAE** (il path intraday avrebbe fatto scattare il trigger prima dello strategy-exit? se
  sì, era false-stop = prezzo è tornato sopra entry prima del next rebalance/exit, o true
  stop = ha continuato a scendere). Questo porta il campione a 248, non 11.

### 🔴 Buco 2 — Phase 5 PARZIALE: il ratchet non è decablato
`src/portfolio/loss_feedback.py` (helper, 143 righe) + chiavi Redis per-strategia esistono,
MA `src/workers/performance.py::run_loss_feedback_check` **NON è cablato** a `LossFeedback`
(nessun `import`, nessuna `record_exit`). La contaminazione cross-strategy (perdita S1 →
soglia ingresso S4) è **ANCORA ATTIVA**. È un lever del loop di underdeployment.

### 🟡 Buco 3 — Minor (dal tuo handback §5)
- Aggregate stop-risk budget (sleeve 75-100bp) non cablato (solo per-position).
- `last_good` lookup: `StopPolicy` accetta un callable ma il scheduler non lo inietta.
- `d_hard` audit logging per fractionable (redundante per gli exit ma va loggato per audit).

---

## 2. Task A — Augment `scripts/replay_stop_loss.py` al gate completo spec §10

**Obiettivo**: trasformare lo script da "proxy debole" a "replay storico vero che risponde
'vol_scaled fa più soldi net del fisso, robustamente?'". **Read-only/idempotente** (non
scrive su DB; pattern di `scripts/validate_ticker_sentiment.py`).

### A1. Path intraday 15-min (NON exit_price)
Per ogni trade chiuso (248, `net_pnl NOT NULL`, escludi `LEGACY_FLATTEN`):
- fetch bar Alpaca 15-min (o più fine) per `[entry_time, min(exit_time, entry_time+H_max)]`
  via `StockHistoricalDataClient` + `StockBarsRequest(timeframe=TimeFrame.Minute)` —
  **pattern verificato in `src/workers/performance.py:~1949`** (counterfactual worker già
  fetcha bar 1-min storiche; copia il client init). Le bar storiche Alpaca sono 24/7
  (funzionano nel weekend). Rispetta i rate-limit: batcha per simbolo, retry con backoff.
- Per σ_eff all'entry usa `data/daily_close.csv` (già pronto) con lookback no-look-ahead
  (solo bar fino all'`entry_time`).

### A2. Simula il counterfactual REALE (fix del buco (ii))
Per ogni variante (fixed 2%, vol_scaled per-strategia, + le altre sotto):
- dal `entry_time`, scan del path 15-min: primo `low <= trigger` → `stop_time`,
  `exit_fill = min(trigger*(1-slip), bar_open_next)` (slippage/gap model).
- se il trigger NON è hit entro `min(exit_time, entry_time+H_max)` → esci al
  **strategy-exit** (prezzo/time del trade reale, exit_reason=`portfolio_sell`/`sentiment_reversal`).
- `variant_pnl = (exit_fill - entry_price) * qty - costs` (usa il cost_calc del repo).
- **`vol_cum_pnl ≠ fixed_cum_pnl`** — devono divergere per costrutto (rimuovi la riga
  `vol_cum_pnl = fixed_cum_pnl`). Questo è il punto: il P&L di vol_scaled deriva dal path
  simulato, non è copiato.

### A3. MAE/MFE su TUTTI i 248 trade (fix del buco (v))
Per ogni trade: il path intraday avrebbe fatto scattare il trigger PRIMA dello
strategy-exit? Se sì: false-stop se il prezzo torna sopra entry (o P&L>0) prima del next
rebalance / invalidazione segnale; true-stop se continua a scendere. Classifica false-stop
S1 (vs next rebalance) e false-stop S4 (vs event window). MAE/MFE vol-normalized,
time-to-stop, slippage, gap loss oltre soglia.

### A4. Varianti da confrontare
2%, 3%, 5%, 7%, vol_scaled(k=2.5/3/3.5/4 per strategia), ATR(14)*k, no-protective,
strategy-exit-only. **WALK-FORWARD**: split train/test per `entry_date` (es. 70/30),
NON selezionare e valutare sullo stesso periodo.

### A5. Gate — stampa TUTTI i spec §10 con numero + PASS/FAIL
```
false-stop reduction vs fixed 2%:     X%   (gate ≥40%)               PASS/FAIL
median net P&L:                      fixed X vs vol_scaled X          PASS/FAIL
bootstrap delta P&L positive:        X% dei resamples (gate ≥70-75%) PASS/FAIL
portfolio max-DD:                    delta (gate non >10% peggiore)   PASS/FAIL
ES95:                                delta (gate non >10% peggiore)   PASS/FAIL
costi/slippage inclusi:              sì/no
open-stop risk:                      X bp vs budget Y bp              entro/out
name-dependence:                     top-2 contrib X%                 PASS/FAIL
```
Esce non-zero se un gate **critico** fallisce (definisci quali sono critici nella PR).
Stampa la variante raccomandata con k/floor/cap per strategia + split walk-forward usato.

### A6. DEVI ESEGUIRE lo script e riportare i numeri (fix del buco (i))
Il gap Round 1 è stato "script scritto, gate non lanciato". **NON ripeterlo.** Lancia:
```
export $(grep -E '^DATABASE_URL=' .env)  # lo script NON auto-carica .env
.venv/bin/python scripts/replay_stop_loss.py --start 2026-06-01 --end 2026-07-11 \
    --bars-csv data/daily_close.csv --mode report
```
Riporta l'output completo nell'handback §b. Se il gate FAIL, **FERMATI** (unica fermata
hard): non forzare `vol_scaled`, riporta i numeri, proponi k/floor/cap rivisti.

---

## 3. Task B — Finisci Phase 5: wire `performance.py` → `LossFeedback`

Cabilia `src/workers/performance.py::run_loss_feedback_check` al modulo
`src/portfolio/loss_feedback.py` che hai già scritto:
- `from src.portfolio.loss_feedback import LossFeedback`
- raggruppa i trade chiusi per `stop_strategy` (colonna mig. 034; fallback
  `S4 if signal_id else S1` come `trading.py:96-103`)
- `R = net_pnl / risk_budget_at_entry`, `risk_budget_at_entry = stop_d_init * entry_notional`
  (colonne mig. 034; escludi `net_pnl NULL` — M7)
- chiama `LossFeedback.record_exit(strategy, exit_reason, net_pnl, risk_budget)` per trade
- exclude exit operativi (`LEGACY_FLATTEN`, `sentiment_reversal`, operational) —
  `TEACHING_REASONS = {stop_loss, portfolio_sell}` già nel seed
- scrivi per-strategia `feedback:entry_threshold:S*`; depreca la key legacy
  `feedback:entry_threshold` (senza suffisso) con fallback backward-compat
- `feedback:regime_scale` (F8 orphaned): NON cablarlo; lascialo scrivere com'è per il path
  legacy (il portfolio path non lo legge)

**Test obbligatori** (`tests/workers/test_loss_feedback.py`, estendi i tuoi):
- perdita S1 alza `feedback:entry_threshold:S1` ma NON `:S4` (no cross-contamination)
- perdita S1 −3R alza la soglia S1 **più di** −0.2R (magnitudo, non count)
- exit `LEGACY_FLATTEN` / `sentiment_reversal` non muovono nessuna soglia
- `decay` avvicina al baseline; 48h senza teaching exits → key scade → baseline
- S1 `threshold()` = 0.0 (no gate)
- backward-compat: solo key legacy → S4 la usa come fallback
- **test di integrazione**: `run_loss_feedback_check` su un fixture di trade misti S1/S4
  produce le key per-strategia giuste (questo è il test che manca al Round 1)

---

## 4. Task C — Minor (dal tuo handback §5)

- **Aggregate stop-risk budget**: oltre al per-position, wirea il sleeve budget 75-100bp
  (somma dei risk-budget delle posizioni aperte ≤ cap). Config in `risk:` di trading.yaml.
- **`last_good` lookup**: inietta nel scheduler un callable Redis-backed (ultime 5
  sessioni di `stop_vol_at_entry` per simbolo) → `StopPolicy(... last_good=<callable>)`.
- **`d_hard` audit logging**: per i fractionable, loga una riga `stop_decisions` (o una
  tabella/colonna di audit) per il d_hard check, anche se redundant per gli exit.

Se uno di questi è più grande del previsto, implementa il minimo viable e logga il resto
in handback §g (non bloccare A e B per C).

---

## 5. Guardrail (vale tutto il Round 1 §2 — riassunto)

1. Nessun LLM/remote nel hot path 15-min.
2. Protective stop sempre sintetico, per-ciclo, uniforme. Mai al broker.
3. Stop non si allarga mai (freeze-at-entry; d_init congelato).
4. Una posizione per simbolo (pyramiding guard).
5. **`stop_loss_mode` resta `fixed`** — NON abilitare `vol_scaled` in config (gate pendente).
6. Path legacy (`execution.py`) invariato.
7. Cooldown preservato.
8. `exit_reason` al submit-time.
9. Measure before enforce: shadow-only finché il gate §10 NON passa.
10. Tutti i test verdi (tranne 8 `test_day1_fixes` aggiornati).
    `scripts/audit_stop_loss_attribution.py` verde dopo ogni fase (lancialo: exit 0).

---

## 6. Ambiente (verificato Round 1)

- Branch: `stop-loss-redesign` (sei già lì). Lavora su questo branch, NON su main.
- Python: `.venv/bin/python` (ha psycopg2, alpaca-py, pandas, numpy). Tests: `.venv/bin/pytest -q`.
- DB: `DATABASE_URL` in `.env` — **lo script NON auto-carica .env**, esportalo.
- Alpaca: `ALPACA_API_KEY/SECRET_KEY/BASE_URL` in `.env`. Feed iex. Bar storiche 24/7.
- Dopo ogni fase: `.venv/bin/python scripts/audit_stop_loss_attribution.py` (exit 0) + `.venv/bin/pytest -q`.

---

## 7. Return contract — aggiorna `docs/stop_loss_kimi_handback.md`

Sovrascrivi l'handback. **Sezione §b CRITICA — deve contenere i numeri dell'esecuzione reale
del gate augmentato (A6), non "da lanciare":**
- tutti i 7 gate spec §10 con numero + PASS/FAIL (template in §A5 sopra)
- variante raccomandata: k/floor/cap per strategia + split walk-forward (train/test date)
- se GATE FAIL: "GATE FAIL — fermo", numeri, e k/floor/cap proposti per retry
- output completo del comando A6 (incollato)
- **§Phase5-proof**: il `from src.portfolio.loss_feedback import LossFeedback` + la call
  site in performance.py (file:line) + il test di integrazione che passa
- §a stato per fase, §c decisioni autonome, §d discrepanze file:line, §g bloccati, §i open questions

**Stampa anche un riassunto a video (≤30 righe)** con: status per fase, gate §10 in
evidenza (PASS/FAIL per ciascuno), "PROSSIMO STEP". Se gate FAIL, dillo in cima.

---

## 8. Cosa NON fare

- NON abilitare `stop_loss_mode: vol_scaled` (lascia `fixed`).
- NON riapplicare migration 034 (già al DB live).
- NON toccare il path legacy (`execution.py`).
- NON copiare `vol_cum_pnl = fixed_cum_pnl` — il counterfactual deve essere reale.
- NON dichiarare "gate PASS" senza aver lanciato lo script e incollato i numeri.

Inizia dal Task A (gate). È il vero sblocco.