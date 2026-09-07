# Forensic Daily Report — 2026-09-04

**Perimetro:** ricostruzione end-to-end della seduta 2026-09-04 (news ingest → sentiment LLM →
segnali → decisioni → ordini → fill → posizioni → P&L → anomalie). Modalità read-only, nessuna
modifica al sistema. Periodo di osservazione attivo (`docs/evidence/OBSERVATION_CHARTER.md`,
taratura congelata, giorno 23/40 — venerdì, ultimo giorno di borsa prima del weekend e del Labor
Day del 2026-09-07).

**Timezone:** UTC, non ambiguo — `src/workers/celery_app.py` dichiara `timezone="UTC",
enable_utc=True`, confermato da `SELECT now()` sul DB. Market hours 13:30–20:00 UTC.

**Fonti usate:** query dirette Postgres (`docker exec alembic-postgres-1 psql`), API REST via
header `X-API-Key` (Bearer rifiutato, vedi [DAY-008]), log applicativi persistenti
`logs/containers/{api,beat,worker,worker-inference}-2026-09-04.log` (disponibili per intero,
nessuna perdita oggi), `logs/deploy_reconcile_2026-09-04.log`, e — dove le stesse evidenze erano
già ricostruite dal job giornaliero indipendente — `docs/ALPHA_MISS_REPORT_2026-09-04.md` e
`docs/evidence/dossier/2026-09-04.json` (generato 2026-09-07T08:00:19Z, Alpaca SIP
adjustment=all). Dove riuso quei numeri lo dichiaro; non li ricalcolo.

---

## 1. Executive summary

Seduta pulita **sul lato esecuzione**: 24 cicli di sentiment/portafoglio (14:00–19:52 UTC), 82
news ingerite da 2 fonti, ensemble a due modelli attivo tutto il giorno (nessun outage Ollama
sostenuto), **zero BUY** e 2 SELL su `execution_decisions` (PLTR −$53,06 S4/`below_entry_gate`,
IWM +$12,19 S1/`sentiment_reversal`), entrambe riconciliate 1:1 con `trades` e con gli ordini
broker via API. Nessun ordine fuori orario, fuori watchlist, duplicato o senza causa. Realizzato
giornata **−$40,87**, equity chiusura **$109.970,86** (dossier), NAV risk report **$109.964,91**,
zero alert nel risk report.

**Trovato oggi un difetto NUOVO di correttezza, non di taratura, con severità alta**: il ledger
append-only `s4_intent_events` — che alimenta rank/diagnostica/missingness del ranking S4 e
diverse misure già in coda (F-051/F-052/F-061/F-063/F-064) — **non ha scritto una sola riga in
tutta la giornata** (0/0 su 24 cicli, contro 3.188 righe il 09-03). Causa: un deploy avvenuto la
sera del 09-03 (22:20 UTC) ha attivato codice che scrive le colonne `held_at_rank` e
`signal_age_at_slot`, introdotte dalla migrazione `060_s4_burned_slot_metrics.sql` (merged
2026-09-02) — **mai applicata al database di produzione**. L'INSERT fallisce per intero (non solo
sulle due colonne nuove), a ogni ciclo, con un semplice `WARNING` di log: nessun alert, nessuna
riga `mobile_events`, nessun trigger nel risk report. Le tabelle a valle (`s4_lifecycle_events`,
`s4_exit_policy_events`) restano popolate da un percorso di scrittura diverso e non sono toccate,
quindi il contratto di trial P0/P1/P2 (#293) non è cieco sull'esito delle posizioni — ma ogni
diagnostica di ranking/candidatura S4 per il 2026-09-04 è irrecuperabile. Vedi [DAY-001]/[F-068].

Tutte le altre anomalie trovate sono **ricorrenze misurate** di difetti già aperti: (a)
`sentiment_reversal` (meccanismo S4) ha chiuso ancora una posizione S1 (IWM, deroga #182(a)
pre-registrata il 25/08, **non ancora deployata** a 10 giorni di distanza), (b) tutti e 3 i
tentativi di alert Telegram della giornata sono falliti con 400 Bad Request (100% di fallimento
oggi, non solo un campione), col bot token nuovamente in chiaro nei log, (c) il bearer token del
protocollo forense continua a fallire sul ramo JWT, (d) il contatore duplicati news supera ancora
il fetched giornaliero, (e) 10/43 posizioni restano strutturalmente senza stop protettivo per
quantità frazionaria <1 azione, (f) `slippage_est` resta una copia di `cost_usd`.

## 2. Verdict finale

**OK con warning.**

La catena di esecuzione ha funzionato correttamente end-to-end: nessun ordine senza segnale,
nessun fill non riconciliato, nessuna violazione di orario/watchlist/paper-live, nessun rischio non
gestito, zero ordini generati da segnali sotto soglia o da dati stale. Il giorno a zero BUY è
coerente con l'assenza di segnali sopra gate su simboli non detenuti (confermato da
`ALPHA_MISS_REPORT_2026-09-04.md`), non un sintomo di guasto.

Il downgrade da "OK" puro è dovuto principalmente a **[DAY-001]/[F-068]**: un difetto di
correttezza nuovo, non nella taratura ma nello strumento di misura del ranking S4, che ha azzerato
un'intera giornata di evidenza su una tabella centrale per il trial in corso. Non giustifica
"anomalie significative" perché non ha toccato una singola decisione, ordine o fill reale — ma è
più serio delle ricorrenze abituali perché è un fallimento del 100% (24/24 cicli), silenzioso
(nessun alert su nessun canale) e riproducibile deterministicamente al prossimo giorno di borsa
(2026-09-08) finché la migrazione non viene applicata.

---

## 3. Timeline del 2026-09-04 (UTC)

| Ora | Componente | Evento |
|---|---|---|
| 07:34:08 | worker-inference | Restart pre-market (redeploy 41f09512→38cd921f della sera precedente, 22:20 UTC 09-03) |
| 08:20:03 | Deploy | Riconciliazione `38cd921f → 7e65bf38` (17 commit, backend+frontend) |
| 08:20:18 | worker-inference | Restart post-rebuild |
| 12:20:04 | Deploy | Riconciliazione `7e65bf38 → 6bdde374` (3 commit, backend) |
| 12:29:32–12:30:16 | Deploy | Riconciliazione `6bdde374 → d9c26792` (1 commit, backend+frontend), containers ricreati |
| 13:30–20:00 | Mercato | Regular Trading Hours — **nessun redeploy/restart in questa finestra** |
| 14:00–19:45 | News ingest | `alpaca_benzinga`: 601 fetched, 283 queued, 74 persistite in `news_log`; `gdelt_gkg`: 2.012 fetched, 8 queued, 8 persistite |
| 14:00–19:45 | Sentiment worker | 24 cicli schedulati, 24 ricevuti/completati (Celery); 23/24 hanno scritto una riga in `ensemble_cycle_health` — il ciclo delle 17:45 ha completato in 0,46s con `{'processed': 0, 'reason': 'no_items_in_queue'}` e **non ha scritto riga di telemetria**, comportamento distinto da un guasto (vedi §11, nota su F-065) |
| 14:07–19:52 | Portfolio cycle | 24 cicli (`portfolio_cycles`), cadenza regolare 15 min |
| 14:07–19:52 (ogni ciclo) | S4 intent ledger | **INSERT fallito su ogni ciclo**, candidate e disposition: `column "held_at_rank" of relation "s4_intent_events" does not exist` — [DAY-001] |
| 14:22:00 | Decisione | SELL PLTR (`below_entry_gate`, S4, segnale 19,1h vecchio vs max_age 4h, score +0,192), chiude trade 980, **−$53,06** |
| 14:37:07–08 | Alert | `#161`: 10/44 posizioni non proteggibili (qty<1); 3 tentativi Telegram, **tutti 400 Bad Request** — [DAY-003] |
| 18:52:00 | Decisione | SELL IWM (`sentiment_reversal`, score −0,383 < soglia −0,35), chiude trade 422 (**S1**, apertura 07-24), **+$12,19** — [DAY-002] |
| 22:30:01 | Risk report | NAV $109.964,91, esposizione 29,98%, HHI 0,0273, drawdown combinato 1,24%, **zero alert** |

## 4. News ingest — tabella per fonte

| Fonte | Fetched | Queued | Persistite (`news_log`) | Duplicate (ingestion) | Discarded no-ticker | Discarded stale | Parse fail |
|---|---:|---:|---:|---:|---:|---:|---:|
| alpaca_benzinga | 601 | 283 | 74 | 2.155* | 0 | 89 | 0 |
| gdelt_gkg | 2.012 | 8 | 8 | 1 | 2.003 | 4 | 0 |

\* `duplicates=2.155` supera `fetched=601` nello stesso giorno — ricorrenza [DAY-004]/F-007, il
contatore non è azzerato per sessione.

**Copertura per ticker:** 42/96 simboli watchlist con almeno una riga `news_log`, **54/96 (56,3%)
a zero copertura** — secondo valore più alto della finestra osservata dal 07-31 (record 60
l'08-31), numero riportato in dettaglio da `ALPHA_MISS_REPORT_2026-09-04.md` §1/§6, non ricalcolato
qui. Nessuna news con `published_at > fetched_at` (zero timestamp futuri, verificato via query).
Nessuna news fuori mercato osservata come anomalia (`fetched_at` max 19:45:34, dentro RTH).

**Top news per impatto sul segnale:** l'unico articolo scorato su MU alle 15:30 ("Micron, SanDisk
Jump 4% Even as Hot Jobs Report Briefly Flips Fed Hike Odds Above 50%") è il solo pezzo della
giornata a citare un catalizzatore macro esplicito (jobs report/tassi), coerente con la rotazione
settoriale semis-su/software-giù descritta da `ALPHA_MISS_REPORT_2026-09-04.md` §7 — nessun secondo
articolo indipendente conferma il nesso sugli altri mover deboli.

**Confidenza analisi ingest:** Alta sui conteggi (query dirette), media sulla classificazione
qualitativa (derivata dal dossier/alpha-miss, non riletta articolo per articolo in questa sessione).

## 5. Performance modelli LLM

| Modello | Risposte | Ineligible (conf<0,4) | Polarity media | Confidence media | Min/Max polarity |
|---|---:|---:|---:|---:|---:|
| gpt-oss:20b-cloud | 82 | 31 | −0,015 | 0,452 | −0,900 / +0,700 |
| glm-5.2:cloud | 82 | 47 | +0,012 | 0,376 | −0,600 / +0,450 |

| Aggregato (`sentiment_signals.model_id`) | N | Score medio | Min/Max | Fallback |
|---|---:|---:|---:|---:|
| ensemble (glm-5.2 + gpt-oss) | 58 | −0,013 | −0,442 / +0,347 | 0 |
| single:gpt-oss:20b-cloud (glm ha fallito) | 19 | 0,002 | −0,293 / +0,280 | 19 |
| single:glm-5.2:cloud (gpt-oss ha fallito) | 3 | 0,000 | 0,000 / 0,000 | 3 |
| finbert (entrambi falliti/divergenti) | 2 | 0,010 | 0,008 / 0,012 | 2 |

`ensemble_cycle_health` (23 righe su 24 cicli attesi, vedi §11): 58 letture ensemble + 22 single +
2 finbert = 82, coerente con `sentiment_signals`. `fallback_counters.consecutive_fallback` resta a
0 tutto il giorno (ultimo reset 19:45:34 UTC): **nessun outage sostenuto, nessun trip del circuit
breaker**.

**Verifica funzionale:**
- **Validazione prima del signal store:** sì — le letture single-model/FinBERT sono marcate
  `fallback_used=True` e non contano come contributori pieni (coerente con #90).
- **Varianza gestita:** nessuna divergenza estrema osservata oggi tale da forzare FinBERT come
  gate primario (i 2 casi FinBERT sono normali fallback per mancata risposta, non per divergenza).
- **News duplicate pesate più volte:** no, verificato — 82 righe `news_log` (74+8) producono
  esattamente 82 righe `sentiment_signals` (58+19+3+2), mappatura 1:1.
- **Stessa news → segnali multipli:** non osservato (stesso controllo di cui sopra).
- **Confidence bassa riduce il peso:** sì per costruzione — 31/82 e 47/82 risposte sotto soglia
  0,4 escluse dal calcolo del polarity aggregato, comportamento da design post-#90.
- **Chiamate offline/background:** sì, confermato da codice — nessuna chiamata LLM sincrona nel
  path di esecuzione ordini.
- **Rischio hallucination diretto in decisione:** basso — output JSON strutturato, nessuna BUY
  generata oggi da un singolo modello o da un fallback (le uniche 2 decisioni sono SELL guidate da
  meccanismi di età/soglia, non da un nuovo score positivo).

**FinBERT fallback rate:** 2/82 letture (2,4%); su decisioni BUY/SELL: 0/2 (nessuna delle 2
decisioni della giornata nasce da una lettura FinBERT).

## 6. Segnali finali per ticker

Riuso la tabella completa già ricostruita da `ALPHA_MISS_REPORT_2026-09-04.md` §2 (96 simboli,
return, stato nel libro) e §3 (9 miss candidati classificati) — non la riproduco per intero.
Estratto sui simboli con decisione o quasi-soglia rilevante oggi:

| Simbolo | Score/segnale | Gate 0,30 | Esito | Note |
|---|---:|:--:|---|---|
| PLTR | età 19,1h, score +0,192 al momento della chiusura | n/a (uscita per età) | SELL 14:22 (`below_entry_gate`) | posizione S4 aperta il 09-03, −$53,06 |
| IWM | −0,383 | n/a (soglia sentiment_reversal −0,35) | SELL 18:52 (`sentiment_reversal`) | posizione **S1** (apertura 07-24), segnale **S4**-style — [DAY-002] |
| MU | +0,258 (own/ISSUER_SPECIFIC) | ❌ (0,042 sotto gate) | SKIP_THRESHOLD | mover +6,10%, near-miss più stretto della giornata (F-009) |
| ADBE | −0,156 (fan-out) | ❌ | SKIP_THRESHOLD | mover più ampio della giornata (−6,73%), zero pezzo issuer-specific |
| TMUS | −0,21 (fan-out) | ❌ | SKIP_THRESHOLD | mover −3,46% |
| WDC, TMUS, WDC, LLY | single-model fallback | n/a | SKIP_FALLBACK (4 righe) | esclusi dal ranking BUY per design (#108), F-010 |
| CRM, SNOW | n/a | n/a | SKIP_PYRAMIDING (P0-05) | già a libro, peso non allocato |
| TSLA | max fan-out −0,299 | n/a | mai promosso a canale own | 7 articoli, zero ISSUER_SPECIFIC, vedi F-067 (già registrato oggi dal job alpha-miss) |

**Strategia:** entrambe le SELL nascono da meccanismi S4 (`below_entry_gate`,
`sentiment_reversal`); IWM è però una posizione S1 — [DAY-002]. **Zero BUY**: nessun simbolo non
detenuto ha superato il gate 0,30 col segno giusto oggi (coerente con `ALPHA_MISS_REPORT
_2026-09-04.md`, "ingressi: []"). **Paper confermato**: `strategy_lifecycle` mostra S4=`paper`,
S1=`supervised_paper`, S2=`disabled`, S7=`research` — nessun ordine live.

**Combiner/risk limits:** anti-pyramiding P0-05 ha bloccato 2 tentativi (CRM, SNOW), entrambi già
a libro. Nessun regime_mult applicato oggi (nessuna BUY).

## 7. Ordini generati/eseguiti

| Tipo | Simbolo | Strategia | Ora | Prezzo | Qty | Stato | P&L netto | Rationale |
|---|---|---|---|---:|---:|---|---:|---|
| SELL | PLTR | S4 | 14:22 | 176,17 | 7,5684 | filled | −53,06 | below_entry_gate |
| SELL | IWM | S1* | 18:52 | 295,66 | 2,6299 | filled | +12,19 | sentiment_reversal (*origine segnale S4) |

Entrambe le righe `execution_decisions` hanno un ordine broker corrispondente con
`filled_avg_price` coerente al centesimo con `trades.exit_price` (verificato via API `/orders`,
`X-API-Key`). Nessun ordine BUY/SELL senza decisione, nessuna decisione senza ordine, nessun
reject, nessun fill parziale, nessun ordine fuori orario o fuori watchlist.

**Ordini "sell" aggiuntivi in `/orders?limit=500` senza `decision_id`/`trade_id` (33 simboli, stato
`new`, più diverse righe `canceled` storiche):** non sono un'anomalia — sono gli stop-loss
protettivi lato broker (qty = parte intera della posizione), stesso pattern già isolato nei report
precedenti (F-042 falso positivo). Vedi però [DAY-005] per la copertura strutturalmente incompleta.

## 8. PnL / rendimento della giornata

| Voce | Valore | Fonte |
|---|---:|---|
| Realizzato S4 | −$53,06 | trade 980 (PLTR, `below_entry_gate`) |
| Realizzato S1 | +$12,19 | trade 422 (IWM, `sentiment_reversal` — origine segnale S4, [DAY-002]) |
| Realizzato totale | −$40,87 | somma sopra, coerente con dossier |
| MTM libro aperto (variazione intraday) | −$68,99 | `docs/evidence/dossier/2026-09-04.json` |
| Equity di chiusura | $109.970,86 | dossier |
| Variazione equity giornata | −$109,86 | −40,87 − 68,99 = −109,86, coerente |
| NAV (risk_reports, 22:30 UTC) | $109.964,91 | `risk_reports` — differenza di ~$6 vs dossier, snapshot orario diverso, non indagata oltre (ordine di grandezza trascurabile) |
| Esposizione totale | 29,98% | `risk_reports` |
| Herfindahl index | 0,0273 | `risk_reports` |
| Drawdown combinato | 1,24% | `risk_reports` |
| Alert risk report | nessuno | `risk_reports.alerts = []` |

**Distinzione realizzato/non realizzato rispettata.** Nessuna cifra è stata inventata: dove il
dato non era disponibile via query diretta ho riusato — dichiarandolo — i numeri del dossier.

**Costi/slippage:** `trades.cost_usd` e `trades.slippage_est` identici al centesimo su entrambe le
righe (PLTR 0,7609/0,7609; IWM 0,1479/0,1479) — ricorrenza [DAY-006]/F-015. `regulatory_cost_usd`
popolato e distinto correttamente. Costo totale stimato della giornata: ≈$0,96 in
commissioni/regulatory, trascurabile rispetto al realizzato.

## 9. Correttezza funzionale buy/sell

| Controllo | Esito |
|---|---|
| BUY generati solo quando consentito | ✅ n/a — zero BUY oggi, coerente con zero segnali sopra gate su simboli non detenuti |
| SELL/exit generati correttamente | ✅ entrambe le SELL hanno causa esplicita; ⚠️ una (`sentiment_reversal`) ha colpito la sleeve sbagliata — [DAY-002] |
| Stop-loss rispettati | n/a oggi — zero trigger di stop |
| Signal flip rispettato | ✅ nessun caso BUY→SELL sullo stesso segnale nello stesso ciclo |
| Max holding days | n/a — nessuna posizione S4 ha raggiunto l'orizzonte massimo oggi |
| Rebalance band | non verificabile con i dati disponibili (S1 non ha generato decisioni dirette di ribilanciamento oggi; `strategy_rebalance_snapshots`, migrazione 064, non esiste ancora sul DB live) |
| Ordini duplicati | ✅ nessuno |
| Ordini contrari ravvicinati senza rationale | ✅ nessuno — solo 2 decisioni in giornata, entrambe SELL su simboli diversi |
| Ordini su ticker non consentiti | ✅ nessuno — PLTR e IWM nella watchlist |
| Ordini fuori orario | ✅ nessuno — 14:22 e 18:52 UTC, dentro RTH |
| Trade su dati stale | ✅ verificato attivamente — 660 `SIGNAL_STALE_SKIP` in `audit_log` (guard ha scartato segnali vecchi) |
| Trade su LLM output non valido | ✅ nessun caso |
| Trade con circuit breaker attivo | ✅ n/a — breaker mai attivo oggi |
| Trade su strategia disabilitata | ✅ — S2 (disabled) non ha generato alcuna decisione |
| Paper/live coerenza | ✅ — S4 `paper`, S1 `supervised_paper`, nessun ordine live |
| Idempotenza su retry Celery | ✅ per costruzione — zero `SIGNAL_DUPLICATE_SKIP` oggi (nessuna duplicazione osservata, non un'anomalia: nessun retry ha prodotto un doppio invio) |
| Riconciliazione ordini/fill/posizioni | ✅ verificata 1:1 fra `execution_decisions`, `trades` e `/orders` API |

**Nota obbligatoria su `exit_mechanism`:** la riga PLTR (`below_entry_gate`) porta
`exit_mechanism='below_entry_gate'` popolato **direttamente** dal path S4 post-#184 (non dedotto
dall'età) — nessuna cautela necessaria. La riga IWM (`sentiment_reversal`) proviene da
`portfolio_scheduler._sentiment_reversal_sells`, non porta `exit_mechanism` in
`execution_decisions`, ma `trades.exit_reason='sentiment_reversal'` è un'etichetta osservata
direttamente dal codice che l'ha generata, non dedotta dall'età — nessuna ambiguità.

## 10. Anomalie trovate

### [DAY-001] `s4_intent_events`: INSERT fallito su tutti i 24 cicli della giornata — colonna mancante per migrazione non applicata

* Tipo: Bug (nuovo)
* Area: Signal / Data / Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-04.log`; tabella `s4_intent_events`; `migrations/060_s4_burned_slot_metrics.sql`; `src/store/pg_store.py:619-652`; `src/strategies/s4/intent_ledger.py:170,265,301`
  * timestamp: ogni ciclo 14:07:06→19:52:07 UTC, 48 occorrenze (24 candidate + 24 disposition)
  * snippet/query: `[2026-09-04 14:07:06,430: WARNING/ForkPoolWorker-4] #294: failed to write S4 candidate intent events: column "held_at_rank" of relation "s4_intent_events" does not exist`; `SELECT count(*) FROM s4_intent_events WHERE created_at::date='2026-09-04'` → `0` (contro 3.188 il 09-03); `SELECT column_name FROM information_schema.columns WHERE table_name='s4_intent_events' AND column_name IN ('held_at_rank','signal_age_at_slot')` → 0 righe
* Descrizione: il commit `2c70e0f` ("feat: persisti gli slot S4 bruciati", #429, merged
  2026-09-02T14:10Z) ha aggiunto sia la migrazione 060 (colonne `held_at_rank`,
  `signal_age_at_slot`) sia il codice che le scrive in un INSERT a riga singola
  (`pg_store.py:619-652`). Il deploy di produzione delle 2026-09-03T22:20:01Z
  (`41f09512→38cd921f`, 33 commit) ha portato il codice in produzione, ma **nessun passo del
  pipeline di deploy applica le migrazioni** (`grep -i migrat logs/deploy_reconcile_2026-09-0{2,3,4}.log`
  → zero righe): la migrazione 060 non è mai stata eseguita sul DB live. Da quel deploy in poi
  ogni tentativo di scrivere un evento (candidate o disposition) nel ledger S4 fallisce per
  intero — non solo sulle due colonne nuove, perché sono nella stessa istruzione INSERT delle
  altre 20 colonne. Il 09-03 non ha mostrato il sintomo perché la sessione di trading di quel
  giorno (fino alle 19:52 UTC) era terminata prima del deploy delle 22:20. Le tabelle a valle
  `s4_lifecycle_events` (6 righe oggi) e `s4_exit_policy_events` (13 righe oggi) sono popolate da
  un percorso di scrittura indipendente e non ne risentono.
* Impatto: **zero impatto sull'esecuzione** (nessuna decisione, ordine o fill è stato bloccato o
  alterato — il fallimento è gestito come `WARNING` non fatale). Impatto pieno
  sull'**osservabilità del ranking S4**: rank persistito (F-052), missingness/beta attribution
  (F-064), qualificatore earnings-day (F-063), popolazione candidati vs tradabili (F-051,
  RANK_OUTSIDE_TOP_N) e la nuova misura "slot bruciati" stessa (#429, la ragione per cui la
  colonna esiste) non hanno **nessuna** riga su cui calcolarsi per il 2026-09-04. Il difetto è
  silenzioso su ogni canale: nessuna riga `mobile_events`, nessun alert nel risk report, nessun
  trigger Telegram — si vede solo incrociando log applicativi e conteggio tabella, esattamente
  come nel pattern già descritto da F-065 (ma qui il ciclo *ha* prodotto lavoro, solo non lo ha
  potuto persistere).
* Severità: High
* Confidenza: High (misurata: 0 righe su 24/24 cicli, causa isolata a livello di singola query SQL
  e singolo commit, riproducibile leggendo lo schema live)
* Azione consigliata: applicare `migrations/060_s4_burned_slot_metrics.sql` al database di
  produzione (operazione di correzione, non di taratura — nessuna soglia, peso o comportamento di
  trading è toccato dalla migrazione). Passa il test di esenzione della carta: senza la
  correzione, ogni giorno di borsa da qui in avanti (a partire dal prossimo, 2026-09-08)
  continuerà a produrre zero righe nel ledger di ranking S4.
* Test/monitor consigliato: alert quando `s4_intent_events` non riceve alcuna riga in una giornata
  con almeno un ciclo di portafoglio eseguito (join contro `portfolio_cycles`); guardia di deploy
  che confronti le migrazioni presenti in `migrations/` con quelle applicate al DB prima di
  promuovere un'immagine che le referenzia nel codice.

### [DAY-002] `sentiment_reversal` (segnale S4) chiude una posizione S1 (IWM)

* Tipo: Anomalia (ricorrenza, deroga pre-registrata non ancora deployata)
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` id 19048, `trades` id 422, `src/workers/portfolio_scheduler.py` (`_sentiment_reversal_sells`)
  * timestamp: 2026-09-04 18:52:00 UTC
  * snippet/query: `reason='sentiment_reversal: score -0.383 < threshold -0.35'` su un trade con `stop_strategy='S1'`, apertura 2026-07-24
* Descrizione: stesso pattern esatto di [DAY-004] del report del 09-03 (MU): `_sentiment_reversal_sells`
  itera su tutte le posizioni aperte sul broker senza filtro di strategia, chiude IWM (S1, 42
  giorni di detenzione) su un segnale di provenienza S4-style. La deroga #182(a), concessa il
  2026-08-25, **non risulta ancora deployata** (nessun commit di fix in `git log --all`, solo
  commit di decisione/registrazione — 10 giorni dalla concessione). Ricorrenza F-033 (8ª
  occorrenza).
* Impatto: il realizzato di S1 del 2026-09-04 (+$12,19) è interamente prodotto da una decisione
  S4: misattribuzione che contamina qualunque confronto S1 vs SPY richiesto dalla domanda di
  uscita 2 della carta. Costo diretto della chiusura anticipata non quantificato in questa
  sessione (nessun `drift_post_uscita` letto per questa riga specifica).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova — la deroga #182(a) è già approvata e in coda; resta da
  eseguire il deploy.
* Test/monitor consigliato: contatore giornaliero "uscite sentiment_reversal per sleeve d'origine
  vs sleeve detentrice" (già suggerito il 09-03, non ancora implementato).

### [DAY-003] Alert Telegram: 100% di fallimento oggi (3/3), bot token in chiaro nei log

* Tipo: Anomalia (ricorrenza, aggravata)
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-04.log`
  * timestamp: 2026-09-04 14:37:08 UTC, 3 tentativi consecutivi
  * snippet/query: `HTTP Request: POST https://api.telegram.org/bot8611445937:AAH3.../sendMessage "HTTP/1.1 400 Bad Request"` × 3; trigger: `#161: 10/44 held positions are unprotectable (qty < 1)`
* Descrizione: il job che segnala le posizioni non proteggibili (#161, deroga di strumentazione
  registrata nella carta) tenta 3 invii Telegram nella giornata — **tutti e 3 falliscono** con
  400 Bad Request. Ricorrenza F-005 (misura oggi il 100% di fallimento, non un campione parziale
  come in occorrenze precedenti). Ogni riga di log del tentativo espone il bot token per intero
  nell'URL a livello INFO — ricorrenza F-018.
* Impatto: l'unico canale operativo per l'alert #161 è completamente non funzionante oggi; le 10
  posizioni non proteggibili (stesso elenco di [DAY-005]) restano visibili solo nei log
  applicativi (che sopravvivono, a differenza di altre giornate — F-027 non ricorre oggi).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova (F-005/F-018 già aperti); la causa (formato payload o
  parse_mode non valido per l'API Telegram) non è stata investigata in questa sessione.
* Test/monitor consigliato: test di integrazione che invii un messaggio Telegram di prova e
  verifichi 200 OK come parte della suite di smoke-test post-deploy; rotazione/mascheramento del
  bot token nei log (F-018).

### [DAY-004] `ingestion_stats_daily.duplicates` (2.155) supera `fetched` (601) per alpaca_benzinga

* Tipo: Anomalia (ricorrenza)
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: `updated_at 2026-09-04 19:45:06+00`
  * snippet/query: `SELECT * FROM ingestion_stats_daily WHERE day='2026-09-04'` → `alpaca_benzinga: fetched=601, queued=283, duplicates=2155`
* Descrizione: il contatore `duplicates` è quasi 3,6× il numero di articoli effettivamente
  recuperati nella stessa giornata — coerente con un accumulo non azzerato per
  sessione/run. Ricorrenza F-007 (21ª occorrenza).
* Impatto: nessuno sui segnali/ordini (derivano da `news_log`, non da questo contatore); rende
  inutilizzabile qualunque lettura di "tasso di duplicazione" da questa tabella.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova (già in coda su F-007).
* Test/monitor consigliato: assert `duplicates <= fetched` come guardia di sanità sul writer.

### [DAY-005] Copertura stop protettivi: 10/43 posizioni con quantità <1 azione restano strutturalmente scoperte

* Tipo: Anomalia (ricorrenza)
* Area: Risk / Broker
* Evidenza:
  * file/log/tabella: API `/positions`, `/orders?limit=500`
  * timestamp: snapshot 2026-09-07 (stato corrente delle posizioni; per i simboli non tradati il 09-04 la quantità e lo stato dello stop non sono cambiati dal 09-04, stesso avvertimento metodologico del report del 09-03)
  * snippet/query: 10 simboli con `qty<1` — `AMAT, AMD, ASML, CAT, DELL, LLY, MRVL, NOK, SPY, WDC` (stesso identico insieme del 09-02/09-03) — zero ordini stop (`status='new'`) sul loro simbolo, su un book di 43 posizioni con 33 simboli coperti
* Descrizione: Alpaca non accetta stop su quantità frazionarie; il sistema piazza lo stop solo
  sulla parte intera (`floor(qty)`), quindi ogni posizione sotto 1 azione resta interamente priva
  di protezione. Ricorrenza F-022 (5ª occorrenza).
* Impatto: esposizione a rischio non protetta, non un costo diretto — nessun trigger di stop
  osservato oggi che sarebbe stato mancato.
* Severità: Medium
* Confidenza: High per l'elenco (identico alle 2 occorrenze precedenti, nessuna nuova posizione
  frazionaria aperta oggi — zero BUY).
* Azione consigliata: nessuna nuova (dimensione minima di posizione ≥1 azione è **taratura**,
  resta al 28/09 come da registro).
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-006] `trades.slippage_est` identico a `cost_usd` su entrambe le righe della giornata

* Tipo: Osservazione (ricorrenza)
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` id 980, 422
  * timestamp: 2026-09-04
  * snippet/query: PLTR `cost_usd=0,7609176`/`slippage_est=0,7609172` (arrotondamento a parte, stesso valore sorgente); IWM `0,1479401`/`0,1479401`
* Descrizione: nessun confronto prezzo-atteso/prezzo-fill esiste realmente; `slippage_est` è una
  copia derivata dello stesso costo di trading. Ricorrenza F-015 (18ª occorrenza).
* Impatto: nessuno oggi (2 fill, entrambi coerenti al centesimo con l'ordine broker); metrica
  strutturalmente inutile per rilevare esecuzioni cattive.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-007] 4 esclusioni `SKIP_FALLBACK` non costificate nella giornata

* Tipo: Osservazione (ricorrenza)
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` id 18817, 19049, 19080, 19142
  * timestamp: 16:52, 19:07, 19:22, 19:52 UTC
  * snippet/query: `single-model fallback (...) excluded from BUY ranking (#108) — no ensemble computed for this symbol today` su WDC (×2), TMUS, LLY
* Descrizione: come da design post-#90, un segnale single-model (l'altro modello non ha risposto)
  è escluso dal ranking BUY anche quando il segno e la magnitudine sarebbero altrimenti validi
  (WDC 16:52 score +0,280, sopra gate). Ricorrenza F-010 (6ª occorrenza) — nessuna misura
  automatica del costo-opportunità di questa esclusione esiste ancora nel sistema.
* Impatto: costo non stimabile automaticamente; WDC era anche un mover della giornata (+5,86%,
  già in portafoglio, coperto solo parzialmente da altre fonti secondo `ALPHA_MISS_REPORT
  _2026-09-04.md` §4).
* Severità: Low
* Confidenza: Medium (nessun ricalcolo manuale del controfattuale in questa sessione)
* Azione consigliata: nessuna nuova (già in coda su F-010).
* Test/monitor consigliato: nessuno aggiuntivo oltre quanto già proposto sulle occorrenze precedenti.

### [DAY-008] Bearer token del protocollo forense rifiutato su tutti gli endpoint REST

* Tipo: Anomalia (ricorrenza)
* Area: Ops
* Evidenza:
  * file/log/tabella: `src/api/auth.py`
  * timestamp: 2026-09-07 (verifica eseguita oggi contro l'istanza live)
  * snippet/query: `curl -H "Authorization: Bearer <token>" .../decisions` → `403 {"detail":"Invalid or expired JWT token"}`; stesso token con `X-API-Key` → `200 OK`
* Descrizione: causa isolata e confermata nelle sessioni precedenti (F-041, 11ª occorrenza):
  `require_api_key` prova sempre il ramo JWT se l'header `Authorization` è presente, senza
  fallback su `X-API-Key`. Il protocollo cron fornisce le istruzioni curl sbagliate.
* Impatto: nessuno sul sistema di trading; impatto solo sul protocollo forense stesso, mitigato
  ricostruendo i dati via query dirette e via `X-API-Key`.
* Severità: Low
* Confidenza: High
* Azione consigliata: correggere le istruzioni curl del protocollo cron (usare `X-API-Key`), non
  il codice applicativo.
* Test/monitor consigliato: nessuno aggiuntivo.

---

## 11. False positive o aree risultate corrette

- **Ciclo sentiment delle 17:45 assente da `ensemble_cycle_health`:** verificato nel log
  `worker-inference` che il task è stato ricevuto e ha **completato con successo** in 0,46s,
  `{'processed': 0, 'reason': 'no_items_in_queue'}` — coerente con il buco genuino in `news_log`
  fra le 17:15 e le 18:00 (nessun articolo pubblicato in quella finestra). **Non è un'occorrenza
  di task-non-eseguito come F-065**: qui il ramo di uscita anticipata per coda vuota semplicemente
  non scrive una riga di telemetria, a differenza del ramo osservato il 09-02 (che scriveva
  `aggregate=0` anche a coda vuota). Questo è però un **affinamento rilevante di F-065**: la stessa
  assenza di riga può derivare sia da un guasto sia da un ciclo perfettamente sano che non aveva
  nulla da processare — un consumatore della tabella `ensemble_cycle_health` da sola non può
  distinguere i due casi, e serve incrociare i log Celery (quando disponibili) per farlo. Aggiunta
  un'occorrenza a F-065 con questa nota, nessun nuovo id.
- **Ordini "sell" senza `decision_id`/`trade_id` in `/orders`:** sono gli stop-loss protettivi
  lato broker, non ordini fantasma — vedi §7, stesso falso positivo già isolato il 09-03 (F-042).
- **Zero BUY in giornata:** non è un sintomo di guasto — coerente al 100% con
  `ALPHA_MISS_REPORT_2026-09-04.md` (`ingressi: []`, nessun segnale sopra gate su simboli non
  detenuti col segno giusto).
- **TSLA senza segnale "proprio" (7 articoli, tutti fan-out/TAG_UNCONFIRMED):** già isolato e
  classificato oggi da `ALPHA_MISS_REPORT_2026-09-04.md` come [F-067]; non ricontato qui.
- **Zero `SIGNAL_DUPLICATE_SKIP` oggi:** non è un'assenza sospetta di logging — è coerente con
  zero retry Celery duplicati osservabili nella giornata (il guard esiste e ha funzionato in altre
  giornate, es. 09-03; la sua assenza di trigger oggi non implica che sia disattivato).
- **Nessun redeploy/restart durante il mercato:** verificato positivamente sui log di
  riconciliazione — le 3 ricostruzioni dell'immagine sono tutte concluse entro le 12:30:16 UTC,
  ben prima dell'apertura RTH (13:30); i 3 restart di `worker-inference` corrispondono
  esattamente a quelle 3 riconciliazioni, zero eventi imprevisti durante la sessione.
- **Discrepanza NAV dossier ($109.970,86) vs risk report ($109.964,91):** ~$6 di differenza,
  ordine di grandezza coerente con orari di snapshot diversi (22:30 UTC vs chiusura), non indagata
  oltre — stesso pattern non anomalo già osservato il 09-03.

## 12. Dati mancanti o non accessibili

- **Prezzo atteso vs prezzo di fill:** non misurabile — [DAY-006], `slippage_est` è una copia di
  `cost_usd`.
- **Rebalance band S1:** nessuna decisione S1 diretta osservata oggi; la tabella
  `strategy_rebalance_snapshots` (migrazione 064, commit `8af5ffc` "feat: persisti e misura i
  ribilanciamenti S1") non esiste ancora sul DB live — funzionalità mergiata ma non ancora
  deployata/migrata, non correlata a [DAY-001] (colonna diversa, tabella diversa).
- **Costo diretto della chiusura anticipata IWM ([DAY-002]):** non calcolato in questa sessione
  (nessun `drift_post_uscita` letto per questa riga specifica dal dossier).
- **Diagnostica di ranking/candidatura S4 dell'intera giornata:** irrecuperabile per
  [DAY-001]/F-068 — non un dato "non ancora raccolto", ma un dato che non è mai stato scritto.

## 13. Raccomandazioni immediate

Nessuna raccomandazione di taratura (periodo di osservazione attivo, taratura congelata fino al
2026-09-28). Azioni operative di correttezza segnalabili:

1. **Applicare `migrations/060_s4_burned_slot_metrics.sql` al database di produzione** —
   [DAY-001]/F-068, priorità alta: ogni giorno di borsa che passa senza applicarla (a partire dal
   prossimo, 2026-09-08) produce un'altra giornata a zero righe sul ledger di ranking S4.
2. Eseguire il deploy già approvato di #182(a) (`sentiment_reversal` non deve chiudere posizioni
   non-S4) — la deroga è concessa da 10 giorni, ogni giorno di attesa produce un'altra occorrenza
   misurata su F-033.
3. Investigare la causa del 400 Bad Request su ogni invio Telegram (F-005): oggi il tasso di
   fallimento è 100% (3/3), non un campione parziale come in passato.
4. Correggere le istruzioni curl del protocollo forense cron per usare `X-API-Key` — [DAY-008],
   impatto solo sul tooling di analisi.

## 14. Test o monitor da aggiungere

- Alert quando `s4_intent_events` non riceve righe in una giornata con almeno un
  `portfolio_cycles` eseguito — [DAY-001], avrebbe individuato il difetto entro il primo ciclo
  (14:07 UTC) invece che 3 giorni dopo.
- Guardia di deploy: confrontare le migrazioni presenti in `migrations/` con quelle applicate al
  DB prima di promuovere un'immagine che le referenzia nel codice — [DAY-001].
- Test di integrazione post-deploy che invii un messaggio Telegram di prova e verifichi 200 OK —
  [DAY-003].
- Assert di sanità `duplicates <= fetched` su `ingestion_stats_daily` — [DAY-004] (già proposto).
- Contatore giornaliero "uscite `sentiment_reversal` per sleeve d'origine vs sleeve detentrice" —
  [DAY-002] (già proposto il 09-03, non ancora implementato).

## 15. Ticket tecnici suggeriti

- **Nuovo (correttezza):** applicare la migrazione 060 al DB di produzione e aggiungere una
  guardia di deploy che verifichi l'allineamento schema/codice prima del rebuild — [DAY-001]/F-068.
  Passa il test di esenzione della carta di osservazione (difetto di correttezza dello strumento
  di misura, non di taratura).
- Nessun altro ticket nuovo: ogni altra anomalia trovata oggi è una ricorrenza di un difetto già
  aperto (F-005, F-007, F-010, F-015, F-018, F-022, F-033, F-041) con azione già registrata nel
  ledger.

## 16. Stato sistema

| Indicatore | Valore |
|---|---|
| Ollama ensemble | **Up** tutto il giorno, nessun outage sostenuto. 58/82 (70,7%) letture a ensemble pieno, 22/82 (26,8%) single-model, 2/82 (2,4%) fallback FinBERT pieno |
| FinBERT fallback rate | 2,4% delle letture (2/82); su decisioni BUY/SELL: 0/2 (nessuna decisione della giornata nasce da un fallback FinBERT) |
| Circuit breaker (`fallback_counters.consecutive_fallback`) | Mai sopra 0 in modo persistente; ultimo reset 19:45:34 UTC |
| Worker restart events | 3 restart di `worker-inference`, tutti pre-market (07:34→08:20, 08:20→12:20, 12:20→12:30 UTC), **zero durante RTH (13:30–20:00)** |
| Redeploy della giornata | 3 riconciliazioni (`38cd921f→7e65bf38` 08:20, `7e65bf38→6bdde374` 12:20, `6bdde374→d9c26792` 12:29-12:30), tutte concluse prima dell'apertura del mercato |
| S4 intent ledger (`s4_intent_events`) | **0 righe scritte su 24 cicli** — [DAY-001]/F-068, difetto nuovo di correttezza, non un problema di infrastruttura Ollama/worker |
