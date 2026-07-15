# Prompt per Kimi 2.7-code — Fix-back WS-5 (record_trade_exit trade targeting)

Sei un ingegnere senior. Continui il lavoro sul branch `fixes-2026-07-14` (dal prompt
`docs/fixes_kimi_prompt_2026-07-14.md`). La review del tuo handback ha trovato **2
problemi in WS-5**; uno è già risolto, l'altro è il focus di questo prompt. Gli altri WS
(1, 2, 3, 4) sono **verificati OK** e non vanno toccati.

Lavori nel repo, in autonomia, sullo stesso branch `fixes-2026-07-14`. Nessun merge su
main, nessun deploy.

---

## 0. Stato della review (cosa è già a posto, cosa no)

| WS | Esito review | Azione |
|---|---|---|
| WS-1 (frontend selector) | ✅ OK — tsc clean, vitest 3/3 pass | nessuna |
| WS-2 (freeze metadata) | ✅ OK — wiring completo, d_init invariato in fixed | solo verify post-deploy (non-NULL colonne) |
| WS-3 (weights hygiene) | ✅ OK | nessuna |
| WS-4 (DST gate) | 🟡 PARTIAL — vedi §4 (decisione operatore, NON toccare qui) | nessuna in questo prompt |
| WS-5 (multi-tranche) | 🔴 2 blocker | vedi §1 (fix-back) |

**Già fatto dal reviewer (commit `5b4dc49` sul branch):** rinumerato
`migrations/035_multi_tranche_exit.sql` → `037_multi_tranche_exit.sql` per evitare la
collisione con `035_stop_loss_dhard_audit.sql` (presente su main). **Non toccare questo
file.** Se hai riferimenti al vecchio nome nel tuo handback o in test, aggiorna solo
quelli.

---

## 1. Blocker #2 — `record_trade_exit` colpisce trade sbagliate (design-sensitive)

### Sintesi del bug

In `src/store/pg_store.py` `record_trade_exit` hai droppato `AND exit_time IS NULL` dalla
WHERE (era `WHERE symbol = %s AND exit_time IS NULL`, ora `WHERE symbol = %s`) per poter
ritrovare la stessa trade sulle tranche 2/3 (che hanno già `exit_time` settato dalla
tranche 1). Questo però matcha **tutte le trade del symbol**, e il pyramiding guard
(`src/workers/portfolio_scheduler.py:1561`, `fetch_trades(status="open")` =
`exit_time IS NULL`) garantisce solo 1 trade aperta per symbol → ci sono **molte trade
storiche chiuse per symbol** (verificato su DB live: META 24, AZN 20, IWM 19, MSFT 19,
AMZN 16, MU 16, XLK 15…).

Due impatti concreti:

- **(A) Corruzione dati:** la `CASE` su `exit_order_ids` appende il nuovo `exit_order_id`
  a **tutte** le trade storiche del symbol (lo appende quando non è già nell'array). Le
  trade storiche vedono il loro `exit_order_ids` inquinato da un order_id estraneo. Per
  trade in attesa di reconciliation (`exit_price IS NULL` ma `exit_order_id` settato),
  `reconcile_trade_fills` aggrega anche l'order_id estraneo → potenziale corruzione P&L.
- **(B) Postmortem saltato:** `cur.fetchone()` senza `ORDER BY` su righe non determinate
  può ritornare una trade storica (`was_already_closed = True`) → la funzione ritorna
  `None` → il caller (`portfolio_scheduler.py:2053-2055`) **non esegue il postmortem /
  Decision Log SELL row (Gap-A)** per l'uscita reale. Ri-rompe il fix Gap-A (commit
  `05acc17`).

Il tuo test `test_exit_multi_tranche_weighted_average` usa **una sola trade per symbol**
e per questo non copre lo scenario — passa ma dà falsa sicurezza.

### Perché l'euristica ovvia NON è robusta (non usarla)

L'euristica "targetta la trade più recente per symbol (`ORDER BY entry_time DESC LIMIT 1`)"
**non è sicura** a causa dell'interazione con il pyramiding guard:

1. Tranche 1 setta `exit_time` sulla trade A → al ciclo successivo il guard la considera
   **chiusa** (`exit_time IS NULL` è false).
2. Se tra tranche 1 e tranche 2 arriva un nuovo segnale BUY per lo stesso symbol, il guard
   **lo permette** (A risulta chiusa) → apre una trade **C** più recente di A.
3. Tranche 2 di A → `ORDER BY entry_time DESC LIMIT 1` → ritorna **C** (la più recente),
   non A → setta `exit_time` su C (una trade appena aperta!) e appende l'order_id di A a
   C. **Corruzione peggiore.**

Quindi **non puoi targettare per "symbol + più recente"**. Devi targettare la trade
**specificamente**.

### Direzione di fix raccomandata (valuta e documenta; è una decisione di design)

Il problema radice: una volta che la tranche 1 setta `exit_time`, la trade non è più
"open" e perdi l'handle sulle tranche 2/3. **Non settare `exit_time`/`exit_reason` sulle
tranche intermedie** — solo sull'**ultima** tranche. Modello raccomandato:

- `record_trade_exit` riceve un parametro esplicito che dice se questa è la tranca finale
  (es. `is_final: bool`, oppure `remaining_qty: float` e il final è quando `<= 0`).
- **Tranche intermedia** (non finale): appendi solo `exit_order_id` a `exit_order_ids`,
  riduci `qty` se rilevante, ma **lascia `exit_time`/`exit_reason` NULL**. La trade resta
  "open" → il pyramiding guard continua a bloccare BUY duplicati sullo stesso symbol
  durante il wind-down (comportamento **corretto**: non vuoi re-BUY una posizione che
  stai chiudendo).
- **Tranche finale** (`is_final` / `remaining_qty <= 0`): setta `exit_time`,
  `exit_reason`, appendi l'ultimo `exit_order_id`, ritorna il `trade_id` (così il
  postmortem gira esattamente una volta, sull'ultima tranche).
- Il caller (`portfolio_scheduler.py:2053`) sa se è la tranca finale perché sa il
  `weight` residuo / la qty residua che sta portando a %. Passa l'informazione.

Questo modello:
- risolve (A): le trade storiche non vengono più toccate (WHERE targetta per id/trade
  specifica, non per symbol).
- risolve (B): il `trade_id` ritornato è quello giusto, postmortem gira una volta sola.
- risolve l'interazione guard: la trade resta "open" fino all'ultima tranca → niente re-BUY.

**Per targettare la trade specifica:** il caller ha accesso a `_open_trades` (caricati a
`portfolio_scheduler.py:1561`) che contengono gli `id` delle trade aperte. Passa il
`trade_id` al `record_trade_exit` invece di solo `symbol`. Aggiorna la firma di
`record_trade_exit` per accettare `trade_id` (o `entry_order_id` come handle stabile) e
depreca la lookup per-symbol. Aggiorna tutti i caller.

Se scegli un altro modello (es. una trade row per tranca, o tabella `trade_fills` figlia),
va bene — ma **deve** sopravvivere allo scenario multi-trade-storiche e all'interazione
guard. Documenta la scelta nell'handback.

### Test di regressione OBBLIGATORIO (lo scenario che avevi mancato)

Aggiungi un test che riproduce **esattamente** lo scenario scoperto dalla review:
- Prepara un DB/fixture con **più trade chiuse per lo stesso symbol** (es. 3 trade
  storiche chiuse di META + 1 trade aperta di META).
- Esegui un'uscita multi-tranche (3 tranche) sulla trade aperta.
- **Verifica:**
  1. Le 3 trade storiche chiuse di META hanno `exit_order_ids` **inalterato** (nessun
     order_id nuovo appeso). Questo è il assert che falliva con la tua implementazione.
  2. La trade target riceve `exit_order_ids` con i 3 order_id, `exit_time`/`exit_reason`
     settati solo sull'ultima tranca.
  3. Il `trade_id` ritornato è quello della trade target (non None, non una storica), e
     il postmortem verrebbe triggerato una sola volta.
  4. (Bonus) Simula un BUY sullo stesso symbol tra tranche 1 e 2: il guard lo blocca
     perché la trade è ancora "open".

Esegui anche la suite esistente per confermare nessuna regressione (WS-2/3/4 test devono
restare verdi).

### Piano di implementazione concreto (verificato dal reviewer sul codice)

Il modello `is_final` (NON settare `exit_time`/`exit_reason` sulle tranche intermedie,
solo sull'ultima) richiede **4 punti di contatto** — non è una patch rapida. Verificati
sul checkout del branch:

1. **`src/portfolio/types.py:14`** `CombinedOrder.allocation_weight` — esiste già. L'
   orchestrator (`src/portfolio/orchestrator.py:232,252`) setta `allocation_weight=
   target_wt` per SELL parziali e `=0.0` per full-close. Quindi **`is_final` =
   `allocation_weight == 0.0`** è derivabile. (Le SELL con `allocation_weight==0.0` sono
   già usate come discriminante a `portfolio_scheduler.py:1587,1688,1742`.)

2. **`src/workers/portfolio_scheduler.py` `_submit_portfolio_orders` (~linea 2772-2777)**:
   la SELL entry del dict `submitted` è `{"symbol", "side":"sell", "order_id",
   "qty"}` — **manca `allocation_weight`**. Aggiungi `allocation_weight` (dal
   `CombinedOrder`/order in input) al dict SELL così il caller può derivare `is_final`.

3. **Caller `src/workers/portfolio_scheduler.py:~2053`**: dove chiama
   `record_trade_exit(symbol=sym, exit_order_id=..., exit_time=ts, exit_reason=...)`.
   - Ricava il `trade_id` della posizione aperta per `sym`: è già disponibile in
     `_open_trades` (caricati a `:1561`, `fetch_trades(status="open")` — ogni row ha
     `id`, vedi `pg_store.fetch_trades` SELECT che include `id`). Costruisci una mappa
     `{symbol: id}` da `_open_trades` (o usa `fetch_open_trade_meta`/helper).
   - `is_final = (sub.get("allocation_weight", 0.0) == 0.0)` (o equivalente: SELL che
     porta il weight a 0).
   - Passa `trade_id` e `is_final` a `record_trade_exit`.

4. **`src/store/pg_store.py` `record_trade_exit`**: nuova firma con `trade_id=None,
   is_final=True` (kwarg, default is_final=True per backward-compat con caller/test che
   non lo passano — ma il caller live DEVE passarlo).
   - WHERE: `WHERE id = %s` se `trade_id` dato, altrimenti fallback
     `WHERE symbol = %s AND exit_time IS NULL` (mai `WHERE symbol = %s` nudo).
   - **Sempre**: appendi `exit_order_id` a `exit_order_ids` (dedup, come già fai) e
     setta `exit_order_id` singolo (COALESCE).
   - **Solo se `is_final`**: setta `exit_time`, `exit_reason`; ritorna `trade_id` (così
     il postmortem/Gap-A gira una volta sola, sull'ultima tranca).
   - **Se non `is_final`**: NON settare `exit_time`/`exit_reason` (la trade resta
     "open" → il pyramiding guard continua a bloccare BUY duplicati sul symbol durante
     il wind-down, comportamento corretto); ritorna `None`.

5. **`src/store/pg_store.py` `reconcile_trade_fills` sezione exit (~linea 1453)**: cambia
   il filtro da `WHERE exit_order_id IS NOT NULL AND exit_price IS NULL` a
   `WHERE exit_time IS NOT NULL AND exit_price IS NULL`. **Motivo:** con il modello
   `is_final`, la tranche 1 setta `exit_order_id` ma NON `exit_time`; se reconcile usasse
   `exit_order_id IS NOT NULL` riconcilierebbe dopo la tranche 1 (prematuro, P&L
   parziale). Usando `exit_time IS NOT NULL` (set solo sull'ultima tranca), reconcile
   riconcila solo la trade **completamente chiusa**, aggregando tutti gli order_id in
   `exit_order_ids`. reconcile_trade_fills è chiamato daily (`run_daily_report`), quindi
   non c'è race con il wind-down intragiornaliero.

**Invarianti che devono reggere** (verificabili con i test):
- Trade storiche chiuse di un symbol non vengono mai toccate da una nuova SELL sullo
  stesso symbol (i loro `exit_order_ids`/`exit_time`/`exit_price` restano immutati).
- Il `trade_id` ritornato è quello della trade target, e il postmortem gira una sola
  volta (sull'ultima tranca).
- Una SELL parziale (`allocation_weight > 0`) NON setta `exit_time` → la trade resta
  "open" → il pyramiding guard blocca re-BUY sullo stesso symbol.
- P&L di una uscita 3-tranche = somma dei 3 fill (prezzo medio pesato), riconciliato
  una sola volta a wind-down completato.

### Accettazione WS-5 (dopo fix-back)
- Test regressione multi-trade-storiche verde.
- Suite completa verde (stesso set del tuo handback, + il nuovo test).
- Verifica read-only su DB live (opzionale, post-deploy): le trade storiche di META non
  hanno order_id estranei in `exit_order_ids`.

### Gate
- Nessun flip in live. Branch dedicato (gia `fixes-2026-07-14`), nessun merge/deploy.
- La migrazione `037_multi_tranche_exit.sql` è già rinumerata dal reviewer — non
  ricreare `035`.

---

## 2. Cosa NON fare

- Non toccare WS-1, WS-2, WS-3, WS-4 (verificati OK). WS-4 è PARTIAL ma è una **decisione
  operatore** (vedi §4) — non cambiare la crontab in questo prompt.
- Non abilitare `vol_scaled`, non toccare `max_sector_exposure`, non merge su main.
- Non re-introdurre il vecchio comportamento (post-close orphans etc.).

---

## 3. Handback (deliverable obbligatorio)

- Stato WS-5 fix-back: DONE / PARTIAL / BLOCKED.
- Modello scelto (is_final vs remaining_qty vs per-tranche-row vs trade_fills) + perché.
- Commit hash sul branch.
- File toccati.
- Test: il nuovo test regressione (output), e la suite completa (n passed/fail).
- Verifica che le trade storiche non vengano più toccate (l'assert del test).

---

## 4. WS-4 (PARTIAL) — solo informazione, NON agire qui

Per tua conoscenza: WS-4 ha solo aggiunto il gate `is_market_open()` ma **non ha spostato
la crontab** (ancora `hour="14-21"` in `src/workers/celery_app.py`). Risultato:
- ✅ Orfani post-chiusura (segnali dopo le 20:00 UTC) — fissati.
- ❌ Primi 30 min (13:30-14:00 UTC) — ancora persi (il beat parte alle 14:00).

L'accettazione "primi 30 min coperti" non è soddisfatta. **È una decisione dell'operatore**
se accettare WS-4 come "fix solo orfani post-close" o se spostare anche la crontab a
`13-20` (con approssimazione EDT/EST). **Non toccare la crontab in questo prompt** —
lascia la decisione all'operatore. Limitati a documentare nello handback che WS-4 è
partial e perché.