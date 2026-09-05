# Forensic Daily Report — 2026-09-03

**Perimetro:** ricostruzione end-to-end della seduta 2026-09-03 (news ingest → sentiment LLM →
segnali → decisioni → ordini → fill → posizioni → P&L → anomalie). Modalità read-only, nessuna
modifica al sistema. Periodo di osservazione attivo (`docs/evidence/OBSERVATION_CHARTER.md`,
taratura congelata, giorno 22/40).

**Timezone:** UTC, non ambiguo — `src/workers/celery_app.py:53-54` dichiara esplicitamente
`timezone="UTC", enable_utc=True`, confermato da `SELECT now()` sul DB (`2026-09-04 12:30:51+00 |
UTC`). Market hours 13:30–20:00 UTC.

**Fonti usate:** query dirette Postgres (`docker exec alembic-postgres-1 psql`), API REST via
header `X-API-Key` (vedi [DAY-002]), e — dove le stesse evidenze erano già state ricostruite dal
job giornaliero indipendente — `docs/ALPHA_MISS_REPORT_2026-09-03.md` e
`docs/evidence/dossier/2026-09-03.json` (schema 2.7, Alpaca SIP, generato 2026-09-04T08:00:27Z).
Dove riuso quei numeri lo dichiaro; non li ricalcolo. I log applicativi del giorno target **non
sono disponibili** — vedi [DAY-001].

---

## 1. Executive summary

Seduta operativamente pulita end-to-end: 24 cicli di portafoglio (14:07–19:52 UTC, zero gap
>16min), 134 news ingerite da 2 fonti, ensemble a due modelli attivo tutto il giorno (nessun
outage Ollama, nessun trip del circuit breaker), 7 BUY + 6 SELL su `execution_decisions`, tutti
riconciliati 1:1 con `trades` e con gli ordini broker via API. Nessun ordine fuori orario, fuori
watchlist, duplicato o senza causa. Paper trading confermato su entrambe le strategie attive (S4
`paper`, S1 `supervised_paper`; S2 `disabled`, S7 `research`). Risk report EOD: nessun alert,
esposizione 31,96%, drawdown combinato 1,24%. Realizzato giornata **+$93,56** (S1 +$50,64, S4
+$42,93), MTM libro aperto **−$42,27**, equity chiusura **$110.132,01** (dossier).

Nessun difetto NUOVO di correttezza esecutiva trovato oggi. Tutte le anomalie individuate sono
**ricorrenze misurate** di difetti già aperti nel ledger — in particolare: (a) il meccanismo
`sentiment_reversal` di S4 ha ancora chiuso una posizione S1 (MU, deroga #182(a) pre-registrata il
2026-08-25, **deploy non ancora avvenuto** a 9 giorni di distanza), (b) i log applicativi del
giorno target sono andati persi per un redeploy avvenuto il giorno successivo, (c) il token bearer
fornito da questo stesso protocollo continua a essere instradato sul ramo sbagliato dell'auth, (d)
4 righe `trades` sono state inserite pre-market e cancellate senza traccia di audit (probabile
suite di test contro il DB di produzione), (e) gli stop protettivi coprono solo la parte intera
delle posizioni frazionarie (10/45 posizioni con floor(qty)=0 restano strutturalmente scoperte).
Nessuna di queste ha impedito il funzionamento del sistema o generato un ordine scorretto; sono
difetti di **misura/attribuzione/osservabilità**, coerenti con la natura "sola osservazione" della
finestra corrente.

## 2. Verdict finale

**OK con warning.**

Il processo ha funzionato correttamente lungo tutta la catena (nessun ordine senza segnale, nessun
fill non riconciliato, nessun rischio non gestito, nessuna violazione di orario/watchlist/paper-
live). I warning sono tutti ricorrenze già note e già in coda per correzione (deroghe
pre-registrate #182(a) e #191, o difetti congetturali senza impatto economico odierno diretto se
non per la misattribuzione di $1,34 su MU e la perdita realizzata di $9,74 su MSFT dal pattern di
churn). Nessuno di questi giustifica un downgrade a "anomalie significative": l'evidenza raccolta
oggi resta utilizzabile per le domande di uscita della carta, con le stesse avvertenze già
documentate (P&L S1/S4 attraverso #182(a) non sommabile finché non deployata).

---

## 3. Timeline del 2026-09-03 (UTC)

| Ora | Componente | Evento |
|---|---|---|
| 05:02:49 | `trades` (DB) | 4 righe inserite pre-market (id 971-974), poi cancellate senza record `DELETE` in `audit_log` — [DAY-005] |
| 13:30:01 | Alert/monitor | `alert_incident` CRITICAL "Ciclo di portafoglio in ritardo" + WARNING "Segnali sentiment in ritardo" (apertura mercato, nessun ciclo ancora eseguito); entrambi `recovered` entro il primo ciclo |
| 13:30–20:00 | Mercato | Regular Trading Hours |
| 14:00–19:46 | News ingest | `alpaca_benzinga`: 527 fetched, 278 queued, 126 persistite in `news_log`; `gdelt_gkg`: 2.104 fetched, 12 queued, 8 persistite |
| 14:07–19:52 | Portfolio cycle | 24 cicli, ogni 15 min, zero gap >16 min (`portfolio_cycles`) |
| 14:15–19:45 | LLM ensemble | 134 news scorate; 96 ensemble pieno, 37 single-model (un modello ha fallito/non risposto), 1 fallback FinBERT pieno — nessun outage sostenuto, `fallback_counters.consecutive_fallback` resta a 0 tutto il giorno |
| 15:22 | Decisione | BUY HOOD (score 0,633→peso 2,0%), trade 975 |
| 15:37 | Decisione | SELL CRM (`below_entry_gate`), chiude trade 903 (S4, apertura 08-28), +$30,37 |
| 15:52 | Decisione | BUY MSFT (score 0,548), trade 976 |
| 16:37 | Decisione | BUY NVDA (score 0,362), trade 977 |
| 16:52 | Decisione | BUY AVGO (score 0,572), trade 978 |
| 17:37 | Decisione | SELL MSFT (`below_entry_gate`, score corrente +0,149), chiude trade 976 dopo 1h45, **−$9,74** — [DAY-007] |
| 18:37 | Decisione | BUY CRM (score 0,744) + BUY PLTR (score 0,500), trade 979/980, stesso tick |
| 18:52 | Decisione | SELL NVDA (`below_entry_gate`, score corrente +0,000), chiude trade 977 dopo 2h15, +$12,29 |
| 19:07 | Decisione | SELL AVGO (`below_entry_gate`, score corrente +0,174), chiude trade 978 dopo 2h15, +$7,46 |
| 19:22 | Decisione | BUY QQQ (score 0,294), trade 981; SELL HOOD (`below_entry_gate`, score corrente +0,204), chiude trade 975 dopo 4h, +$2,55 |
| 19:37 | Decisione | Nessuna riga per TSLA nonostante segnale fallback 0,468 sopra gate — comportamento già isolato dal job alpha-miss (F-056/F-060), non ricontato qui |
| 19:52 | Decisione | SELL MU (`sentiment_reversal`, score −0,357 < soglia −0,35), chiude trade 552 (**S1**, apertura 07-28), +$50,64 — origine del segnale è S4, posizione è S1 — [DAY-004] |
| 22:30:01 | Risk report | NAV $110.070,79, esposizione 31,96%, HHI 0,0261, drawdown combinato 1,24%, **zero alert** |
| 22:50:00 | Alert EOD | Alert posizioni cieche lato uscita: ASML e WDC (§4 sotto), stato `recovered` |

## 4. News ingest — tabella per fonte

| Fonte | Fetched | Queued | Persistite (`news_log`) | Duplicate (ingestion) | No-ticker | Not-tradable | Stale |
|---|---:|---:|---:|---:|---:|---:|---:|
| alpaca_benzinga | 527 | 278 | 126 | 2.143* | 0 | 123 | 27 |
| gdelt_gkg | 2.104 | 12 | 8 | 0 | 2.092 | 0 | 0 |

\* `duplicates=2.143` supera `fetched=527` nello stesso giorno — ricorrenza nota [DAY-003], il
contatore non è azzerato per sessione (non è un dato fabbricato, è un contatore rotto).

**Copertura per ticker:** 46/96 simboli watchlist con almeno una riga (`news_log`), 50/96 (52,1%)
a zero copertura — numero riportato e discusso in dettaglio da `ALPHA_MISS_REPORT_2026-09-03.md`
§1/§Segnalazioni [F-001], non ricalcolato qui. Nessuna news con timestamp futuro trovata
(`published_at` max 18:54:19, `fetched_at` max 19:46:07, entrambi coerenti con RTH). Nessuna news
fuori mercato osservata come anomalia (l'ultima ingestione alle 19:46 è dentro la sessione).

**Top news per impatto sul segnale:** l'articolo macro "Wall Street Rallies as Fed's Waller Hints
at September Rate Hold" (~19:15 UTC) compare come fan-out su 8/12 mover della giornata — pattern
già isolato da [F-012] (ricorrenza registrata oggi dal job alpha-miss, non riappesa qui).

**Confidenza analisi ingest:** Alta sui conteggi (query dirette), media sulla classificazione
qualitativa (derivata dal dossier, non riletta articolo per articolo in questa sessione).

## 5. Performance modelli LLM

| Modello | Risposte | Ineligible (conf<0,4) | Polarity media | Confidence media | Min/Max polarity |
|---|---:|---:|---:|---:|---:|
| gpt-oss:20b-cloud | 134 | 75 | +0,170 | 0,482 | −0,550 / +0,850 |
| glm-5.2:cloud | 132 | 73 | +0,178 | 0,385 | −0,550 / +0,850 |

| Aggregato (`sentiment_signals.model_id`) | N | Score medio | Min/Max | Fallback |
|---|---:|---:|---:|---:|
| ensemble (glm-5.2 + gpt-oss) | 96 | 0,125 | −0,358 / +0,744 | 0 |
| single:gpt-oss:20b-cloud (glm ha fallito) | 32 | 0,078 | −0,210 / +0,468 | 32 |
| single:glm-5.2:cloud (gpt-oss ha fallito) | 5 | 0,118 | 0,000 / +0,220 | 5 |
| finbert (entrambi falliti/divergenti) | 1 | 0,024 | 0,024 | 1 |

**Verifica funzionale:**
- **Validazione prima del signal store:** sì — `_label_from_model_count` marca `eligible=False` e
  `fallback_used=True` su ogni lettura single-model o FinBERT (`sentiment.py:345-366`), così
  LOO-ICIR/audit non li contano come contributori pieni. Coerente con la correzione #90 già
  verificata nei giorni precedenti.
- **Varianza gestita:** sì — la divergenza fra i due modelli fa scattare il fallback FinBERT
  (`ensemble.py:293-300`, soglia divergenza), osservato 1 volta oggi.
- **News duplicate pesate più volte:** no, verificato — 134 righe `news_log` (126+8) producono
  esattamente 134 righe `sentiment_signals` (96+32+5+1), mappatura 1:1.
- **Stessa news → segnali multipli:** non osservato oggi (stesso controllo di cui sopra).
- **Confidence bassa riduce il peso:** sì per costruzione — 75/134 e 73/132 risposte sotto la
  soglia di confidence 0,4 sono escluse dal calcolo del polarity aggregato (non è un bug, è il
  meccanismo post-#90: i modelli abbassano volutamente la confidence su notizie settoriali/
  indirette, e il filtro le esclude come da design). Non genera un finding.
- **Chiamate offline/background:** sì, confermato da codice — nessuna chiamata LLM sincrona nel
  path di esecuzione ordini; il worker sentiment scrive su Postgres/Redis, il portfolio cycle legge
  solo dati precomputati.
- **Rischio hallucination diretto in decisione:** basso — l'output è JSON strutturato,
  `directness`/`materiality`/`risk_flags` sono persistiti e la sanitizzazione del testo di input
  precede il prompt (non riverificata riga per riga oggi, non in perimetro di questa sessione).

**Osservazione non costificata (non promossa a finding):** il fallimento single-model è asimmetrico
fra i due modelli — glm-5.2 ha fallito/non risposto 32 volte contro le 5 di gpt-oss, su un totale
di 37 letture single-model. Non è un outage sostenuto (nessun trip del breaker, nessuna sequenza
`consecutive_fallback` che si avvicini al trigger), ma è un pattern degno di essere ripreso se si
ripete: non ha superato la soglia per aprire un id nuovo o agganciarsi a un finding esistente con
sicurezza (F-049 riguarda un outage sostenuto, non un'asimmetria fra modelli su una singola
giornata).

## 6. Segnali finali per ticker (giornata operativa)

Riuso la tabella completa già ricostruita da `ALPHA_MISS_REPORT_2026-09-03.md` §2 (96 simboli,
return, stato nel libro, copertura articoli) — non la riproduco qui per intero. Estratto sui
simboli con decisione BUY/SELL oggi:

| Simbolo | Score ensemble | Gate 0,30 | Decisione | Note |
|---|---:|:--:|---|---|
| HOOD | +0,633 | ✅ | BUY 15:22 poi SELL 19:22 (below_entry_gate) | round-trip 4h, +$2,55 realizzati vs +$18,11 se tenuta al close (dossier) |
| MSFT | +0,548 | ✅ | BUY 15:52 poi SELL 17:37 (below_entry_gate) | round-trip 1h45, −$9,74 |
| NVDA | +0,362 | ✅ | BUY 16:37 poi SELL 18:52 (below_entry_gate) | round-trip 2h15, +$12,29 |
| AVGO | +0,572 | ✅ | BUY 16:52 poi SELL 19:07 (below_entry_gate) | round-trip 2h15, +$7,46 |
| CRM | +0,744 | ✅ | BUY 18:37 (aperta a fine giornata) | secondo ingresso della giornata sul simbolo (primo chiuso alle 15:37) |
| PLTR | +0,500 | ✅ | BUY 18:37 (aperta a fine giornata) | ingresso a movimento intraday già oltre il 100% (dossier, `quota_movimento_precedente_al_segnale=1,055`) |
| QQQ | +0,294 | ✅ | BUY 19:22 (aperta a fine giornata) | |
| MU | −0,357 (soglia sentiment_reversal −0,35) | n/a | SELL 19:52 (`sentiment_reversal`) | posizione **S1**, segnale **S4** — [DAY-004] |
| TSLA | +0,468 (fallback, 19:45:44) | ✅ | **nessuna riga in `execution_decisions`** | ricorrenza F-056/F-060 già registrata dal job alpha-miss per oggi, non riappesa |
| NOW/SPCX/ORCL | 0,10–0,18 | ❌ | SKIP_THRESHOLD | fan-out come unica fonte, F-012/F-009 (già registrati oggi) |

**Strategia:** tutte le BUY/SELL con score S4-style sono S4 (`stop_strategy='S4'`); MU è l'unica
uscita su posizione S1. Nessuna decisione S1 di ingresso oggi (S1 ribilancia su base propria, non
osservata oggi in `execution_decisions` come BUY diretta). **Paper confermato**: `strategy_lifecycle`
mostra S4=`paper`, S1=`supervised_paper` — nessun ordine live.

**Combiner/risk limits:** `regime_mult=0,7` uniforme su tutte le BUY (stato di regime unico per la
giornata), peso 2,0% NAV per ingresso S4 (coerente con la size tipica citata nel protocollo,
~2.200$ su un NAV di ~110.000$ — qui $1.385-1.412 di nozionale, leggermente sotto per via del
regime_mult 0,7). **Anti-pyramiding P0-05** ha bloccato 10 tentativi (XLE, MSFT, SNOW×2, NVDA,
HOOD, AVGO, IWM, ABBV, DELL) — pattern F-031, già registrato oggi dal job alpha-miss per i due
simboli con controfattuale calcolato (DELL, SNOW); i restanti 7 non hanno controfattuale calcolato
in questa sessione e non vengono costificati.

## 7. Ordini generati/eseguiti

| Tipo | Simbolo | Strategia | Ora | Prezzo | Qty | Stato | P&L netto | Broker order id |
|---|---|---|---|---:|---:|---|---:|---|
| BUY | HOOD | S4 | 15:22 | 123,14 | 11,4636 | filled | — | 6f485f3e… |
| SELL | CRM | S4 | 15:37 | 263,87 | 7,6000 | filled | +30,37 | e1e83a58… |
| BUY | MSFT | S4 | 15:52 | 513,54 | 2,7268 | filled | — | d4a95a24… |
| BUY | NVDA | S4 | 16:37 | 227,58 | 6,1735 | filled | — | 144b0ecd… |
| BUY | AVGO | S4 | 16:52 | 354,83 | 3,9355 | filled | — | 4c17d812… |
| SELL | MSFT | S4 | 17:37 | 510,07 | 2,7268 | filled | −9,74 | b23a3e63… |
| BUY | CRM | S4 | 18:37 | 267,51 | 5,1797 | filled | — | f76bb35a… |
| BUY | PLTR | S4 | 18:37 | 183,08 | 7,5684 | filled | — | 3129bed2… |
| SELL | NVDA | S4 | 18:52 | 229,62 | 6,1735 | filled | +12,29 | 1736ce49… |
| SELL | AVGO | S4 | 19:07 | 356,92 | 3,9355 | filled | +7,46 | 8f06ef54… |
| BUY | QQQ | S4 | 19:22 | 717,82 | 1,9444 | filled | — | 651d9ff0… |
| SELL | HOOD | S4 | 19:22 | 123,43 | 11,4636 | filled | +2,55 | c074ebdc… |
| SELL | MU | **S1** | 19:52 | 954,78 | 0,3981 | filled | +50,64 | 556a0a11… |

Tutte e 13 le righe `execution_decisions` BUY/SELL hanno un ordine broker corrispondente con
`filled_avg_price` coerente al centesimo con `trades.entry_price`/`exit_price` (riconciliazione
verificata via API `/orders`, header `X-API-Key`). Nessun ordine BUY/SELL senza decisione, nessuna
decisione senza ordine, nessun reject, nessun fill parziale.

**Ordini "sell" aggiuntivi visti in `/orders` senza `decision_id`/`trade_id` (CRM qty=5, PLTR
qty=7, QQQ qty=1, tutti stato `new`; più AVGO/NVDA/MSFT/HOOD qty intere, stato `canceled`):** NON
sono un'anomalia — sono gli **stop-loss protettivi lato broker**, sottomessi ~15 minuti dopo ogni
BUY (qty = parte intera della posizione, Alpaca non accetta stop su quantità frazionarie) e
cancellati/sostituiti quando la posizione viene chiusa dalla decisione di portafoglio prima che lo
stop scatti. Il meccanismo non ha un `decision_id` per design (non nasce da una riga di segnale).
Vedi però [DAY-008] per la copertura strutturalmente incompleta che questo genera.

## 8. PnL / rendimento della giornata

| Voce | Valore | Fonte |
|---|---:|---|
| Realizzato S1 | +$50,64 | trade 552 (MU) — unica chiusura S1, generata da `sentiment_reversal` (S4) |
| Realizzato S4 | +$42,93 | CRM +30,37, MSFT −9,74, NVDA +12,29, AVGO +7,46, HOOD +2,55 |
| Realizzato totale | +$93,56/93,57* | somma sopra (differenza di arrotondamento centesimale fra fonti) |
| MTM libro aperto (variazione intraday) | −$42,27 | dossier `docs/evidence/dossier/2026-09-03.json` |
| Equity di chiusura | $110.132,01 | dossier |
| Variazione equity giornata | +$51,29 | 93,56 − 42,27 = 51,29, coerente |
| NAV (risk_reports, 22:30 UTC) | $110.070,79 | `risk_reports` — differenza di ~$61 vs dossier plausibile per orario di snapshot diverso (22:30 vs close ufficiale), non indagata oltre |
| Esposizione totale | 31,96% | `risk_reports` |
| Herfindahl index | 0,0261 | `risk_reports` |
| Drawdown combinato | 1,24% | `risk_reports` |
| Alert risk report | nessuno | `risk_reports.alerts = []` |

**Distinzione realizzato/non realizzato rispettata**: nessuna cifra di P&L "economico" (§ carta di
osservazione) è stata confusa col realizzato in questa tabella. **Nessuna cifra di rendimento è
stata inventata**: dove il dato non era disponibile via query diretta ho riusato — dichiarandolo —
i numeri del dossier deterministico, non ricalcolati a mano.

**Costi/slippage:** `trades.cost_usd` e `trades.slippage_est` sono identici al centesimo su tutte
le righe della giornata (es. AVGO 0,7679/0,7679, MSFT 0,2793/0,2793) — ricorrenza nota [DAY-006],
nessun confronto prezzo-atteso/prezzo-fill esiste realmente nel sistema. `regulatory_cost_usd`
popolato correttamente e distinto (es. AVGO 0,0327). Costo totale stimato della giornata (righe con
`cost_usd` popolato, 6/7 ingressi + 2 uscite): ≈$4,4 in commissioni/regulatory, ordine di grandezza
trascurabile rispetto al realizzato.

**Dati mancanti per una misura più fine:** nessuna riga `stop_decisions` oggi (0 stop-loss
triggerati — coerente, tutte le uscite sono state `portfolio_sell`/`sentiment_reversal`, non stop);
non è quindi possibile validare oggi il comportamento degli stop-loss "in azione", solo la loro
copertura strutturale (§9).

## 9. Correttezza funzionale buy/sell

| Controllo | Esito |
|---|---|
| BUY generati solo quando consentito | ✅ — tutte le 7 BUY hanno `ema_pass=true`, score ≥ gate 0,30, `regime_mult=0,7` applicato uniformemente |
| SELL/exit generati correttamente | ✅ nel senso che ogni SELL ha una causa esplicita (`below_entry_gate` ×5, `sentiment_reversal` ×1, `portfolio_sell` sui trade table); ⚠️ una causa (`sentiment_reversal`) ha colpito la sleeve sbagliata — [DAY-004] |
| Stop-loss rispettati | n/a oggi — zero trigger, nessuna violazione osservabile |
| Signal flip rispettato | ✅ — nessun caso di BUY immediatamente seguito da SELL sullo stesso segnale nello stesso ciclo |
| Max holding days | n/a — nessuna posizione S4 ha raggiunto l'orizzonte massimo oggi |
| Rebalance band | non verificabile con i dati disponibili in questa sessione (S1 non ha generato decisioni dirette oggi) |
| Ordini duplicati | ✅ nessuno — ogni `entry_order_id`/`exit_order_id` è unico, nessun doppio invio nello stesso minuto |
| Ordini contrari ravvicinati senza rationale | ⚠️ 4 round-trip BUY→SELL entro 1h45–4h (HOOD, MSFT, NVDA, AVGO), tutti con rationale esplicito (`below_entry_gate`, età segnale > max_age) — non "senza causa", ma la causa è un difetto di banda noto [DAY-007] |
| Ordini su ticker non consentiti | ✅ nessuno — tutti nella watchlist di `config/trading.yaml` |
| Ordini fuori orario | ✅ nessuno — tutte le decisioni fra 15:22 e 19:52 UTC, dentro RTH |
| Trade su dati stale | ✅ verificato — `audit_log` mostra 539 `SIGNAL_STALE_SKIP` (il guard ha scartato attivamente segnali vecchi, non li ha lasciati passare) |
| Trade su LLM output non valido | ✅ nessun caso — tutte le decisioni derivano da `sentiment_signals` con `fallback_used` gestito |
| Trade con circuit breaker attivo | ✅ n/a — breaker mai attivo oggi |
| Trade su strategia disabilitata | ✅ — S2 (disabled) non ha generato alcuna decisione |
| Paper/live coerenza | ✅ — S4 `paper`, S1 `supervised_paper`, nessun ordine live |
| Idempotenza su retry Celery | ✅ per costruzione (25 `SIGNAL_DUPLICATE_SKIP` in `audit_log` oggi, guard attivo) |
| Riconciliazione ordini/fill/posizioni | ✅ — verificata 1:1 fra `execution_decisions`, `trades` e `/orders` API |

**Nota obbligatoria su `exit_mechanism`:** le 5 righe `below_entry_gate` di oggi portano
`exit_mechanism` popolato **direttamente** dal path S4 post-#184 (non dedotto dall'età) — non
serve applicare la cautela sulle etichette pre-fix. La riga MU (`sentiment_reversal`) proviene da
un path diverso (`portfolio_scheduler._sentiment_reversal_sells`, non dal ramo standard S4) e non
porta `exit_mechanism` in `execution_decisions`, ma `trades.exit_reason='sentiment_reversal'` è
un'etichetta osservata direttamente dal codice che l'ha generata, non dedotta — nessuna ambiguità.

## 10. Anomalie trovate

### [DAY-001] Log applicativi del 2026-09-03 non disponibili al momento dell'analisi

* Tipo: Anomalia (ricorrenza)
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/`
  * timestamp: verificato 2026-09-04 (oggi)
  * snippet/query: `ls logs/containers/` → solo `{api,beat,worker,worker-inference}-2026-09-04.log`; `logs/deploy_reconcile_2026-09-04.log` mostra un redeploy `41f09512 → d9c26792` alle 12:30:16Z del 09-04
* Descrizione: i log persistenti dichiarati dal protocollo come sopravviventi ai redeploy non
  coprono il giorno target: la directory contiene solo i log del giorno corrente, prodotti dopo il
  redeploy avvenuto stamattina. Ricorrenza esatta di F-027 (18ª occorrenza).
* Impatto: ogni affermazione su questo path live (timeout, errori, retry, latenze) è ricostruita
  da query dirette a Postgres/API invece che dai log, con minore granularità (nessun timestamp di
  errore applicativo, nessuno stack trace).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova (F-027 già aperto); la causa strutturale (rotazione senza
  persistenza cross-redeploy) resta da correggere.
* Test/monitor consigliato: alert quando la directory `logs/containers/` perde la copertura del
  giorno precedente prima che il forense lo richieda.

### [DAY-002] Bearer token del protocollo rifiutato su tutti gli endpoint REST

* Tipo: Anomalia (ricorrenza)
* Area: Ops
* Evidenza:
  * file/log/tabella: `src/api/auth.py`
  * timestamp: 2026-09-04 (verifica eseguita oggi contro l'istanza live)
  * snippet/query: `curl -H "Authorization: Bearer <token>" .../decisions` → `403 {"detail":"Invalid or expired JWT token"}`; stesso token con `curl -H "X-API-Key: <token>" .../positions` → `200 OK`
* Descrizione: il token fornito dal protocollo è una API key statica, ma le istruzioni curl del
  protocollo stesso la instradano come Bearer JWT, che fallisce sempre. Causa isolata e confermata
  in sessioni precedenti (F-041, 10ª occorrenza): `require_api_key` prova sempre il ramo JWT se
  l'header `Authorization` è presente, senza fallback su `X-API-Key`.
* Impatto: nessuno sul sistema di trading; impatto sul protocollo forense stesso, mitigato
  ricostruendo i dati via query dirette e via `X-API-Key`.
* Severità: Low
* Confidenza: High
* Azione consigliata: correggere le istruzioni curl del protocollo cron (usare `X-API-Key`), non
  il codice applicativo (il comportamento a due rami è intenzionale e documentato).
* Test/monitor consigliato: nessuno aggiuntivo.

### [DAY-003] `ingestion_stats_daily.duplicates` (2.143) supera `fetched` (527) per alpaca_benzinga

* Tipo: Anomalia (ricorrenza)
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`
  * timestamp: `updated_at 2026-09-03 19:45:00+00`
  * snippet/query: `SELECT * FROM ingestion_stats_daily WHERE day='2026-09-03'` → `alpaca_benzinga: fetched=527, queued=278, duplicates=2143`
* Descrizione: il contatore `duplicates` è quasi 4× il numero di articoli effettivamente
  recuperati nella stessa giornata — coerente con un accumulo non azzerato per sessione/run
  invece che un conteggio giornaliero pulito. Ricorrenza F-007 (20ª occorrenza).
* Impatto: qualunque lettura di "tasso di duplicazione" da questa tabella è inutilizzabile senza
  correggere il contatore; non influenza segnali/ordini (questi derivano da `news_log`, non da
  `ingestion_stats_daily`).
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova (già in coda su F-007).
* Test/monitor consigliato: assert `duplicates <= fetched` come guardia di sanità sul writer del
  contatore.

### [DAY-004] `sentiment_reversal` (segnale S4) chiude una posizione S1 (MU)

* Tipo: Anomalia (ricorrenza, deroga pre-registrata non ancora deployata)
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` id 18535, `trades` id 552, `src/workers/portfolio_scheduler.py:4844-4920` (`_sentiment_reversal_sells`)
  * timestamp: 2026-09-03 19:52:00 UTC
  * snippet/query: `reason='sentiment_reversal: score -0.357 < threshold -0.35'` su un trade con `stop_strategy='S1'`, apertura 2026-07-28
* Descrizione: `_sentiment_reversal_sells` itera su tutte le posizioni aperte sul broker senza
  filtro di strategia — chiude MU (S1, 37 giorni di detenzione) su un segnale generato dalla
  sleeve S4. La correzione (#182(a)) è stata **concessa come deroga** all'`OBSERVATION_CHARTER` il
  2026-08-25 proprio per questa classe di eventi, ma **non risulta deployata** (nessun commit di
  fix trovato in `git log --all`, solo i commit di decisione/registrazione). Ricorrenza F-033 (7ª
  occorrenza).
* Impatto: il realizzato di S1 del 2026-09-03 (+$50,64) è interamente prodotto da una decisione
  S4. Costo attribuito sul controfattuale corto (stessa qty tenuta al prezzo di chiusura):
  `drift_post_uscita = +$1,34` (dossier) — tenendo la posizione si sarebbe guadagnato $1,34 in più,
  quindi il costo della chiusura anticipata è piccolo, ma la **misattribuzione** dell'intero
  realizzato ($50,64) alla sleeve sbagliata resta intatta e continua a contaminare qualunque
  confronto S1 vs SPY richiesto dalla domanda di uscita 2 della carta.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova — la deroga #182(a) è già registrata e passa il test di
  esenzione della carta (difetto di misura, non di taratura); resta da eseguire il deploy già
  approvato.
* Test/monitor consigliato: contatore giornaliero "uscite sentiment_reversal per sleeve
  d'origine vs sleeve detentrice" per quantificare la contaminazione residua fino al deploy.

### [DAY-005] 4 righe `trades` inserite pre-market e cancellate senza traccia di audit

* Tipo: Anomalia (ricorrenza)
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `audit_log` id 17511-17514, `trades`
  * timestamp: 2026-09-03 05:02:49 UTC (4 insert consecutivi, ~30ms di distanza)
  * snippet/query: `SELECT * FROM trades WHERE id BETWEEN 971 AND 974` → 0 righe; `audit_log` ha 4 `INSERT` su quegli id, zero `DELETE` su `table_name='trades'` in tutta la sua storia
* Descrizione: stesso pattern esatto di F-039 (5ª occorrenza): righe inserite fuori da qualunque
  ciclo di portafoglio (05:02 UTC, ben prima del primo ciclo delle 14:07), poi sparite senza che
  `audit_log` registri mai una cancellazione — coerente con una suite di test che scrive sul DB di
  produzione bypassando il logging di audit sulle `DELETE`.
* Impatto: nessun trade reale toccato (id consumati e mai più esposti su `execution_decisions` o
  book); il costo è di integrità dell'evidenza futura — un audit trail che registra l'inserimento
  ma non la cancellazione non è un audit trail.
* Severità: Medium
* Confidenza: Medium (causa esatta non riconfermata oggi con lo stesso dettaglio delle occorrenze
  precedenti, ma pattern identico)
* Azione consigliata: nessuna nuova — già in coda su F-039 (guardia ambiente su
  `tests/store/test_pg_store_stop_methods.py` e logging di audit sulle `DELETE`).
* Test/monitor consigliato: trigger di audit anche su `DELETE FROM trades`.

### [DAY-006] `trades.slippage_est` identico a `cost_usd` su tutte le righe della giornata

* Tipo: Osservazione (ricorrenza)
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades`
  * timestamp: 2026-09-03
  * snippet/query: 7 righe con `cost_usd = slippage_est` al centesimo (es. AVGO 0,7679/0,7679)
* Descrizione: nessun confronto prezzo-atteso/prezzo-fill esiste realmente; `slippage_est` è
  una copia derivata dello stesso costo di trading, non una misura di qualità di esecuzione.
  Ricorrenza F-015 (17ª occorrenza).
* Impatto: nessuno oggi (latenza submitted→filled sub-secondo su tutti gli ordini, verificato via
  `/orders`), ma la metrica resta strutturalmente inutile per rilevare esecuzioni cattive.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova.
* Test/monitor consigliato: nessuno aggiuntivo (già proposto sulle occorrenze precedenti).

### [DAY-007] Churn intraday: 4 posizioni S4 aperte e chiuse entro 1h45–4h per invecchiamento del segnale, con SELL su sentiment corrente positivo

* Tipo: Anomalia (ricorrenza)
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions`
  * timestamp: HOOD 15:22→19:22, MSFT 15:52→17:37, NVDA 16:37→18:52, AVGO 16:52→19:07
  * snippet/query: `reason` di ogni SELL riporta `score=+0.149` (MSFT), `+0.204` (HOOD), `+0.174` (AVGO), `+0.000` (NVDA) — tutti ≥0, cioè non un segnale ribassista ma un segnale invecchiato oltre `max_age=4h` (o meno)
* Descrizione: nessuna banda fra il gate d'ingresso (0,30) e la logica di uscita per età del
  segnale produce chiusure entro poche ore anche quando il sentiment corrente resta positivo — è
  esattamente il pattern "SELL su sentiment positivo" già catalogato (F-013, 19ª occorrenza), oggi
  con 4 istanze nello stesso giorno (mai osservato prima con questa frequenza in un solo giorno).
* Impatto: MSFT ha prodotto una perdita realizzata diretta di **−$9,74** in un round-trip di 1h45;
  gli altri tre round-trip sono stati realizzati positivi (HOOD +2,55, NVDA +12,29, AVGO +7,46),
  ma con costo-opportunità visibile solo su HOOD (drift_post_uscita +$14,79 se tenuta al close,
  numero già discusso da `ALPHA_MISS_REPORT_2026-09-03.md` §4 e non riconteggiato qui per evitare
  doppio conteggio).
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova (banda gate/uscita è **taratura**, congelata dalla carta di
  osservazione fino al 28/09; il difetto di correttezza collegato — F-023, S4 usa solo il segnale
  più recente invece del più forte nella finestra — resta la leva applicabile senza toccare
  soglie).
* Test/monitor consigliato: contatore giornaliero di round-trip <4h con segno del segnale corrente
  concorde all'ingresso, per quantificare la ricorrenza fino alla scadenza della carta.

### [DAY-008] Copertura degli stop protettivi: 10/45 posizioni con quantità <1 azione restano strutturalmente senza stop

* Tipo: Anomalia (ricorrenza)
* Area: Risk / Broker
* Evidenza:
  * file/log/tabella: API `/orders` (header `X-API-Key`), `/positions`
  * timestamp: snapshot 2026-09-04 (vedi nota sotto)
  * snippet/query: `AMAT, AMD, ASML, CAT, DELL, LLY, MRVL, NOK, SPY, WDC` — tutte con `qty<1` e
    zero ordini `sell` aperti (`status='new'`) nel loro simbolo, su un book di 45 posizioni
* Descrizione: Alpaca non accetta stop su quantità frazionarie; il sistema piazza lo stop sulla
  parte intera della posizione (`floor(qty)`), quindi ogni posizione con meno di 1 azione resta
  **interamente** priva di protezione stop-loss. Ricorrenza F-022 (4ª occorrenza) — lo stesso
  insieme di 10 simboli (quasi identico alle occorrenze dell'08-25/09-02). Nozionale scoperto:
  ≈$3.663 su un book di ≈$35.112 (10,4%); coprendo anche la parte frazionaria mancante delle
  posizioni parzialmente coperte (es. QQQ, entrata oggi, coperta solo al 51,4%), lo scoperto
  totale sale a ≈$8.024 (22,9% del book).
* Impatto: esposizione a rischio non protetta, non un costo — nessun controfattuale indica che uno
  stop avrebbe fatto scattare un'uscita migliore oggi.
* Severità: Medium
* Confidenza: High per l'elenco dei simboli (verificato su finestra ordini di 500 righe, risalente
  al 07-16, sufficiente a coprire ogni posizione tranne le 8 aperte il 07-10 — per queste ultime la
  copertura è comunque confermata dove presente, es. BAC 96,1%, MS 98,3%, UBS 99,5%). **Nota sul
  timing:** lo snapshot è del 2026-09-04 pomeriggio (dopo un redeploy alle 12:30 UTC), non un
  prelievo puntuale delle 20:00 UTC del 09-03; per i simboli non tradati oggi la quantità e lo
  stato dello stop non sono cambiati dal 09-03, quindi il numero è una proxy ragionevole ma non
  un valore esatto di fine seduta 09-03.
* Severità: Medium
* Confidenza: Medium (per il timing dello snapshot, vedi sopra)
* Azione consigliata: nessuna nuova (già in coda su F-022 — dimensione minima di posizione ≥1
  azione è **taratura**, resta al 28/09 come da registro).
* Test/monitor consigliato: nessuno aggiuntivo.

---

## 11. False positive o aree risultate corrette

- **Ordini "sell" senza `decision_id`/`trade_id` in `/orders`:** a prima vista sembrano ordini
  fantasma (pattern F-042), ma sono gli stop-loss protettivi lato broker, che per design non
  nascono da una riga di decisione. Nessun'anomalia — vedi §7.
- **TSLA senza riga in `execution_decisions` alle 19:52:** verificato che è lo stesso caso già
  isolato e classificato oggi da `ALPHA_MISS_REPORT_2026-09-03.md` (F-056/F-060); non un nuovo
  difetto, non ricontato in questo report.
- **Ineligible rate elevato su `llm_responses` (75/134, 73/132):** non è un errore di validazione,
  è il filtro di confidence (soglia 0,4) che funziona come da design post-#90 — i modelli abbassano
  volutamente la confidence su notizie indirette/settoriali.
- **Prima stima di copertura stop protettivi (73,5% scoperto, 35/45 posizioni):** calcolata in
  prima battuta con `/orders?limit=100`, **scartata** dopo aver verificato che il limite di
  paginazione tagliava fuori gli stop più vecchi (es. AAPL, stop aperto dal 2026-07-22, fuori dalla
  finestra dei 100 ordini più recenti). Rifatta con `limit=500` (risale al 07-16): il numero
  corretto è 22,9% scoperto, coerente con le occorrenze precedenti di F-022. Riportato qui
  esplicitamente per trasparenza sul metodo, non come anomalia del sistema.
- **Zero stop_decisions oggi:** non è un'assenza sospetta, è coerente con zero trigger di
  stop-loss nella giornata (tutte le uscite sono state per gate/reversal, non per stop).
- **Nessun outage Ollama, nessun trip breaker:** verificato positivamente (non solo assenza di
  evidenza) via `ensemble_cycle_health` (17/34 cicli con almeno una lettura single-model, mai zero
  ensemble) e `fallback_counters.consecutive_fallback` (mai sopra 0 in modo persistente).

## 12. Dati mancanti o non accessibili

- **Log applicativi del 2026-09-03** (`worker`, `worker-inference`, `api`, `beat`): non disponibili
  — [DAY-001]. Ogni affermazione sul path live in questo report viene da query dirette, non dai
  log.
- **Rebalance band S1:** nessuna decisione S1 diretta osservata oggi in `execution_decisions`;
  senza log applicativi non è possibile confermare se S1 abbia valutato e scartato un
  ribilanciamento oggi o semplicemente non ne avesse uno schedulato.
- **Prezzo atteso vs prezzo di fill:** non misurabile — [DAY-006], `slippage_est` è una copia di
  `cost_usd`.
- **Snapshot esatto di fine seduta per la copertura stop (§10, DAY-008):** disponibile solo uno
  snapshot post-redeploy del giorno successivo; la query esatta servirebbe uno storico ordini con
  timestamp di stato, non solo lo stato corrente.

## 13. Raccomandazioni immediate

Nessuna raccomandazione di taratura (periodo di osservazione attivo, taratura congelata fino al
2026-09-28). Le uniche azioni operative segnalabili sono quelle già in coda:
1. Eseguire il deploy già approvato di #182(a) (`sentiment_reversal` non deve chiudere posizioni
   non-S4) — la deroga è concessa da 9 giorni, ogni giorno di attesa produce un'altra occorrenza
   misurata su F-033.
2. Correggere le istruzioni curl del protocollo forense cron per usare `X-API-Key` invece di
   `Authorization: Bearer` — [DAY-002], impatto solo sul tooling di analisi, zero rischio, banale.

## 14. Test o monitor da aggiungere

- Assert di sanità `duplicates <= fetched` su `ingestion_stats_daily` — [DAY-003].
- Trigger di audit su `DELETE FROM trades` (oggi il trigger copre solo `INSERT`/`UPDATE`) —
  [DAY-005].
- Contatore giornaliero "uscite `sentiment_reversal` per sleeve d'origine vs sleeve detentrice" —
  [DAY-004], utile a misurare la contaminazione residua fino al deploy di #182(a).
- Contatore giornaliero di round-trip BUY→SELL <4h con segno del segnale corrente concorde
  all'ingresso — [DAY-007].
- Alert quando `logs/containers/` perde la copertura del giorno precedente prima delle 08:00 UTC
  del giorno successivo — [DAY-001].

## 15. Ticket tecnici suggeriti

Nessun ticket nuovo: ogni anomalia trovata oggi è una ricorrenza di un difetto già aperto
(F-007, F-013, F-015, F-022, F-027, F-033, F-039, F-041) con azione già registrata nel ledger.
Non apro nuovi id — coerente con "nel dubbio, aggancia" del protocollo di osservazione.

## 16. Stato sistema

| Indicatore | Valore |
|---|---|
| Ollama ensemble | **Up** tutto il giorno, nessun outage sostenuto. 96/134 (71,6%) letture a ensemble pieno, 37/134 (27,6%) single-model (un modello ha fallito, asimmetria 32 gpt-oss-only vs 5 glm-only, non costificata — vedi §5), 1/134 (0,75%) fallback FinBERT pieno |
| FinBERT fallback rate | 0,75% delle letture (1/134); su decisioni BUY/SELL: 0/13 (nessuna decisione della giornata è nata da un fallback FinBERT) |
| Circuit breaker (`fallback_counters.consecutive_fallback`) | Mai sopra 0 in modo persistente; azzerato più volte durante la giornata, ultimo reset 19:46:07 UTC |
| Worker restart events | Non verificabile per assenza di log ([DAY-001]); nessun'evidenza indiretta di restart nel corso della giornata (24 cicli portfolio senza gap anomali, cadenza regolare 14:07-19:52) |
| Redeploy più vicino | 2026-09-04 12:30:16Z (`41f09512 → d9c26792`), **il giorno successivo** al target — causa nota della perdita dei log [DAY-001] |
