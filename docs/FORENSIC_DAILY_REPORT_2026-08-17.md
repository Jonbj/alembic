# Forensic Daily Report — 2026-08-17

Analista: sessione autonoma read-only. Timezone operativo: **UTC** (confermato in
`src/workers/celery_app.py`: `timezone="UTC"`; Postgres `SHOW timezone` = UTC). Market hours =
13:30–20:00 UTC. Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`): nessuna
proposta di taratura, solo difetti di correttezza sono ammessi come ticket.

Fonti: query dirette `docker exec alembic-postgres-1 psql` (SELECT-only), `docs/ALPHA_MISS_REPORT_2026-08-17.md`
(già scritto e verificato in una sessione precedente da `docs/evidence/dossier/2026-08-17.json`, Alpaca
SIP `adjustment=all`), lettura codice (`src/workers/portfolio_scheduler.py`, `src/store/pg_store.py`),
`docs/evidence/findings.json`, `docker logs`/`docker inspect`. **L'API REST locale
(`localhost:8001/api`) ha rifiutato il token fornito** (`{"detail":"Invalid or expired JWT token"}`) —
tutte le tabelle sono state lette via SQL diretto. **I log Docker di `worker`/`beat`/`worker-inference`
per la maggior parte del pomeriggio del 2026-08-17 non sono stati recuperabili in modo affidabile in
questa sessione** — vedi [DAY-301] e §12.

---

## 1. Executive summary

Giornata di mercato ad alta dispersione (σ cross-sectional ~2,1%, indici piatti-negativi: SPY −0,47%,
QQQ −0,16%) con **zero nuovi ingressi** e **2 chiusure S4** (JD −$36,80, BA −$27,93, entrambe per
`[below_entry_gate]`, meccanismo FIX-D osservato correttamente — non una stima per età). 194 news
ingerite (103 Benzinga, 91 GDELT), 200 segnali su modelli LLM (fallback rate 39%), 473 decisioni
(453 SKIP_THRESHOLD, 10 SKIP_PYRAMIDING, 8 SKIP_FALLBACK, 2 SELL, **0 BUY**). Nessun ordine sotto
soglia, nessun duplicato, nessuna violazione anti-pyramiding, paper mode confermato su tutti gli 82
snapshot del giorno. Il money path di oggi è **funzionalmente corretto**.

**Evento operativo rilevante**: l'host è stato riavviato alle **14:03:37 UTC** (`uptime -s`), circa 34
minuti dopo l'apertura del mercato, portando al riavvio simultaneo di tutti e 5 i container Alembic
(`worker`/`beat`/`worker-inference` StartedAt 14:04:22Z, `api` 14:04:24Z, `RestartCount=0` su tutti —
riavvio del processo, non ricreazione: `Created` resta 2026-08-15). **Nessun impatto misurabile sulla
pipeline**: 24 cicli portfolio regolari 14:07–19:52 senza buchi, 82 snapshot ogni 5 min 13:30–20:00
senza buchi, ingest news continuato fino alle 18:15. **Ma il recupero dei log Docker per
`worker`/`beat`/`worker-inference` nel pomeriggio si è rivelato inaffidabile in questa sessione**
(vedi [DAY-301]) — impossibile confermare/escludere errori applicativi silenziosi nel pomeriggio dai
soli log.

**Sei ricorrenze di difetti già tracciati nel ledger**, nessuna nuova: F-003 (drawdown/daily_pnl di
`risk_reports` sganciati dal NAV reale, oggi il divario più ampio della serie: alert 17,8% vs drawdown
reale 0,15%), F-004 (decay_reports pipeline-globale, S2 morta comunque scorata CRITICAL), F-007
(duplicati > fetched su Benzinga), F-009 (SPCX: 4 segnali col segno giusto, nessuno sopra gate),
F-011 (signal_id NULL su 465/473 decisioni, 98,3%), F-015 (slippage_est identico a cost_usd), F-016
(SPY benchmark fetch fallito 84 volte), F-005 (nuova sorgente: alert Telegram 400 su un task diverso
dal loss-feedback).

## 2. Verdict finale

**OK con warning.** Il flusso segnale→decisione→ordine→posizione del 2026-08-17 è corretto: nessun
bug nel money path, gate rispettato, anti-pyramiding funzionante, nessun ordine anomalo, uscite S4
etichettate col meccanismo osservato corretto (#184/#236 già deployati). Il warning riguarda
l'infrastruttura di misura durante la finestra di osservazione: (a) il pannello di rischio
(`risk_reports`) continua a riportare tre numeri incompatibili per lo stesso concetto di drawdown, oggi
al divario più ampio mai osservato nella serie; (b) un riavvio host a metà seduta ha lasciato un buco
nella capacità di leggere i log applicativi per gran parte del pomeriggio, un rischio già tracciato
(F-027) ma con un meccanismo nuovo (riavvio senza ricreazione, non un redeploy notturno).

## 3. Timeline del 2026-08-17 (UTC)

| ora | componente | evento |
|---|---|---|
| 00:00–13:00 | worker (overnight) | task orari regolari, nessun impatto sul money path; 84 WARNING `SPY benchmark fetch failed` nell'arco del giorno (F-016) |
| 04:00:00 | mobile_alert_task / TelegramNotifier | `Starting weekly weight computation (observational)` seguito da `400 Bad Request` su `sendMessage` — consegna alert fallita (F-005, nuova sorgente) |
| 13:00–13:59 | news ingest | prime righe `news_log` (Benzinga dalle 13:04) |
| 13:30 | mercato USA | apertura |
| 13:30–14:00 | portfolio_monitor_snapshots | 6 snapshot regolari ogni 5 min, NAV apertura $110.487,36 |
| **14:02:01–14:04:24** | **host + 5 container** | **riavvio host (`uptime -s`=14:03:37 UTC) → `worker`/`beat`/`worker-inference` StartedAt 14:04:22Z, `api` 14:04:24Z, RestartCount=0 (processo riavviato, container non ricreato). Ultima riga log `worker` prima del riavvio: 14:02:01,027 UTC — [DAY-301]** |
| 14:07 | portfolio-cycle | primo ciclo dopo il riavvio (id 982), nessun ritardo/gap rispetto alla cadenza attesa; SKIP_PYRAMIDING su JD, BA |
| 14:07–19:52 | portfolio-cycle | 24 cicli totali, cadenza 15 min esatta, **zero buchi attribuibili al riavvio** |
| 15:30 | sentiment_signals | segnale BA/JD score +0,000 (sotto la soglia feedback attiva) |
| 15:52:06 | execution_decisions / trades | **SELL JD** (id 725, entry 08-14 $29,02 → exit $28,46, net_pnl −$36,80, `[below_entry_gate]`) e **SELL BA** (id 726, entry 08-14 $230,98 → exit $227,53, net_pnl −$27,93, `[below_entry_gate]`) — uniche righe `trades` chiuse del giorno |
| 15:55 | portfolio_monitor_snapshots | cash +$3.549,46 (74.309,54→77.859,00), open_positions 49→47, coerente con le 2 chiusure |
| 13:00–18:15 | news ingest | 194 righe totali (103 alpaca_benzinga, 91 gdelt_gkg), copertura 38/96 simboli watchlist (40%) a zero righe (F-001, ricorrenza già registrata nel ledger dalla run alpha-miss) |
| 20:00:00 | portfolio_monitor_snapshots | EOD: NAV $110.476,06, `nav_change_today` +$37,28, 47 posizioni aperte, cash $77.859,00, `current_drawdown` 0,15% |
| 21:00 | decay_monitor | 12 righe `decay_reports`, valori actual IDENTICI su S1/S2/S4 (F-004, ricorrenza) |
| 22:30:01 | risk_monitor | `risk_reports` id 66: `combined_drawdown` 1,24%, `per_strategy_metrics.portfolio.drawdown` 17,8% → ALERT "17.8% exceeds 10%", `daily_pnl` −$1.980,38 (F-003, ricorrenza al divario più ampio della serie) |

Nessun evento fuori orario, nessuna news con `published_at` futuro o `fetched_at < published_at`
(verificato = 0 righe su 194).

## 4. Tabella news ingest

| fonte | fetched (stats) | queued | duplicates | discarded_no_ticker | righe in news_log 08-17 |
|---|---:|---:|---:|---:|---:|
| alpaca_benzinga | 747 | 399 | **3.694** | 0 | 103 |
| gdelt_gkg | 1.711 | 122 | 110 | 1.546 | 91 |
| **totale news_log** | | | | | **194** |

- **[F-007] ricorrenza**: `duplicates` (3.694) supera `fetched` (747) per `alpaca_benzinga` — stesso
  pattern strutturale già tracciato, il contatore duplicati non è vincolato al fetched dello stesso
  giorno (probabile finestra di dedup cross-day più ampia del contatore giornaliero).
- Nessuna riga `source='reuters'` in `ingestion_stats_daily` oggi — **F-028 NON ricorre** (a differenza
  del 08-14): nessuna evidenza di contaminazione test↔produzione sulla tabella ingest oggi.
- 38/96 simboli watchlist (40%) a zero copertura, leggero miglioramento sulla banda 42-57% osservata
  dal 07-31 (F-001, dettaglio completo in `docs/ALPHA_MISS_REPORT_2026-08-17.md` §7).
- Nessuna news futura, nessun `fetched_at < published_at` (0/194 verificato).

## 5. Tabella performance modelli LLM

| model_id | righe (signal-level) | quota | score medio | confidenza media |
|---|---:|---:|---:|---:|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 122 | 61,0% | +0,035 | 0,282 |
| `single:gpt-oss:20b-cloud` | 71 | 35,5% | +0,034 | 0,520 |
| `single:glm-5.2:cloud` | 6 | 3,0% | +0,083 | 0,608 |
| `finbert` | 1 | 0,5% | +0,105 | 0,323 |

- `sentiment_signals.fallback_used`: 122 false / **78 true → fallback rate 39,0%**, sopra il 28,4%
  dell'08-14 ma dentro la banda ampia osservata in altre sedute (memoria: 70-86% in periodi peggiori).
- `llm_responses` per-modello: 400 righe totali per 200 segnali (esattamente 2 per segnale, nessuna
  riga orfana). **`eligible=true` 50 (12,5%) / `eligible=false` 350 (87,5%)** — coerente con l'85%
  osservato l'08-14, stesso meccanismo (soglia di confidenza individuale 0,4 in `ensemble.py`).
- Nessuna riga fuori range: score ∈ [−0,445, +0,604], confidenza ∈ [0,10, 0,90].
- Massimo disaccordo ensemble (`ensemble_std`): JPM 0,212 e ORCL 0,212 — non estremo (soglia di
  attenzione empirica ~0,40 dai report precedenti).
- Nessuna evidenza di refusal/JSON non parsabile ricostruibile da DB (nessun campo dedicato; i log
  applicativi che potrebbero mostrarlo sono in gran parte irrecuperabili oggi, vedi [DAY-301]).
- Modelli chiamati offline/background confermato per lettura codice (`worker-inference`,
  concurrency=1, coda `inference`) — nessuna chiamata LLM sincrona nel ciclo portfolio.

## 6. Tabella segnali finali per ticker (rilevanti al money path)

| simbolo | ora (UTC) | score | esito |
|---|---|---:|---|
| BA | 15:30 | +0,000 | **SELL** — `[below_entry_gate]`, weight 0,0% |
| JD | 15:30 | +0,000 | **SELL** — `[below_entry_gate]`, weight 0,0% |
| MU | 17:15 | +0,604 (score massimo del giorno) | SKIP_PYRAMIDING (già a libro dal 07-28) |
| WDC | 15:07 | +0,448 | SKIP_PYRAMIDING (già a libro dal 07-21, mover +5,35%) |
| UNH | 17:22 | +0,444 | SKIP_PYRAMIDING (già a libro dal 07-10) |
| LLY | 16:37 | +0,439 | SKIP_PYRAMIDING (già a libro dal 07-15) |
| SHEL | 15:52 | +0,485 | SKIP_PYRAMIDING (già a libro dal 07-14) |
| MRVL | 14:07/17:07 | +0,080/+0,040 (fallback) | SKIP_FALLBACK — escluso da ranking BUY (mover +5,54%, ma già a libro S1 dal 07-14, nessun nuovo ordine necessario) |
| SPCX | vedi §7 dossier | +0,188 max (4 segnali) | SKIP_THRESHOLD — nessuno sopra gate 0,30 (F-009, mover +4,45% non catturato, costo non stimabile per #277) |
| ORCL | 18:00 | −0,445 (score minimo del giorno) | SKIP_THRESHOLD |

Dettaglio completo per ticker (96 simboli, cause di miss) in `docs/ALPHA_MISS_REPORT_2026-08-17.md` §2-3.

## 7. Tabella ordini generati/eseguiti

| symbol | decisione | tick_time UTC | strategia | qty | entry/exit | net_pnl | stop_strategy | esito |
|---|---|---|---|---:|---:|---:|---|---|
| JD | SELL | 15:52:06 | S4 | 62,3015 | $29,02→$28,46 | −$36,80 | S4 | FILLED (trade id 725) |
| BA | SELL | 15:52:06 | S4 | 7,8071 | $230,98→$227,53 | −$27,93 | S4 | FILLED (trade id 726) |

- **Zero BUY oggi** (`ingressi` vuoto nel dossier, nessuna riga `entry_time::date='2026-08-17'`).
- Nessun ordine duplicato: nessuna coppia symbol+decisione nello stesso minuto con COUNT>1.
- 10 SKIP_PYRAMIDING, tutte verificate contro posizioni realmente aperte da date precedenti — nessuna
  falsa applicazione del guard.
- 8 SKIP_FALLBACK, tutte con `reason` che cita esplicitamente `#108` (esclusione fallback single-model
  dal ranking BUY) — meccanismo funzionante e loggato (nessuna soppressione silenziosa osservata oggi,
  a differenza delle occorrenze F-006 di giorni precedenti).
- **[F-015] ricorrenza**: `slippage_est` == `cost_usd` esatto per entrambe le chiusure (JD: 1,912=1,912;
  BA: 0,998=0,998) — la colonna dedicata non misura nulla di indipendente dal costo stimato.
- Modalità: **paper** confermata su tutti gli 82 snapshot (`mode='paper'`, `broker_environment='paper'`).
- `execution.engine=portfolio` unico motore attivo (confermato `config/trading.yaml:142`); log worker
  14:00:00 conferma `legacy execution worker inactive`.
- Nessuna riga `stop_decisions` oggi (nessun trigger di stop-loss).

## 8. Tabella PnL/rendimento

| voce | valore |
|---|---:|
| NAV apertura (13:30:00) | $110.487,36 |
| NAV chiusura (20:00:00) | $110.476,06 |
| `nav_change_today` (colonna dedicata, EOD) | **+$37,28** |
| Variazione NAV apertura→chiusura (calcolo diretto) | −$11,30 |
| Cash EOD | $77.859,00 (da $74.309,54 pre-chiusure) |
| Posizioni aperte EOD | 47 |
| Realizzato del giorno (JD+BA) | **−$64,73** |
| MTM stimato — 4 mover catturati per holding (AMAT+MRVL+WDC+MU) | ≈ +$140,28 (qty×Δclose) |
| MTM stimato — 11 posizioni legacy senza `stop_strategy` (F-002) | **+$21,53 su +$37,28 di nav_change_today (58%)** |
| `risk_reports` daily_pnl (22:30) | −$1.980,38 — **non riconciliato**, vedi [DAY-302] |
| `risk_reports` nav (22:30) | $110.480,71 |

**Nota positiva**: a differenza dell'08-14, `nav_change_today` oggi **è internamente coerente**: il
valore alle 13:30 (+$48,58) e alle 20:00 (+$37,28) implicano entrambi lo stesso NAV di chiusura
precedente (~$110.438,78, vs $110.440,21 riportato nell'EOD dell'08-14 — scarto di $1,43, dentro il
rumore). Il campo non mostra oggi la stessa incoerenza interna registrata come nuova faccia di F-003
l'08-14 — vedi [DAY-302] per la parte che invece resta rotta (`risk_reports.daily_pnl`/drawdown).

Non è possibile scomporre il P&L per strategia con precisione: 11/47 posizioni (23%) restano senza
`stop_strategy` (F-002), e oggi rappresentano il 58% del movimento netto del NAV — la quota più alta
osservata nella serie di occorrenze di questo finding. Costi/slippage: entrambe le chiusure hanno
`cost_bps`/`slippage_est`/`cost_usd` popolati (vedi §7); nessun'altra riga valorizzata (nessun altro
trade chiuso).

## 9. Analisi correttezza buy/sell

- **BUY generati solo quando consentito**: non applicabile, zero BUY oggi.
- **SELL generati correttamente**: sì, entrambe le SELL (JD, BA) hanno rationale esplicito
  `[below_entry_gate]` — meccanismo osservato (non stimato per età, #184/#236 già deployati) e
  coerente con lo stato reale dei segnali (score +0,000 alle 15:30, sotto la soglia feedback attiva
  0,30 di S4).
- **Anti-pyramiding rispettato**: sì, 10/10 SKIP_PYRAMIDING verificati contro posizioni realmente
  aperte da date precedenti (07-10 → 08-14).
- **Nessuna SELL con sentiment positivo (bug A5)**: score alla base di entrambe le SELL è +0,000
  (neutro/sotto soglia), non positivo — non applicabile.
- **Nessun ordine duplicato, nessun ordine fuori orario, nessun ordine su ticker non in watchlist.**
- **Nessun trade generato da segnale non valido**: score/confidenza entro range attesi per tutte le
  righe della giornata.
- **Nessun trade durante circuit breaker attivo**: `system:halted_by_operator` non impostato (Redis
  verificato), nessun gap anomalo nei 24 cicli.
- **Idempotenza Celery**: `audit_log` mostra 429 righe `SIGNAL_STALE_SKIP` per `sentiment_signals`
  applicate durante la giornata — nessun segnale processato due volte con effetto ordine duplicato.
  **Nessuna riga `audit_log` di tipo DELETE su `trades` oggi** (473 INSERT storiche, zero DELETE mai) —
  **nessuna ricorrenza della contaminazione DAY-201 (08-14)**.
- **Paper/live coerente**: sì, confermato su ogni snapshot.
- **Reconciliation trades↔posizioni**: 47 posizioni aperte a fine giornata coerenti con
  `open_positions` dello snapshot delle 20:00; API Alpaca diretta non interrogata (fuori dal protocollo
  read-only).

Avvertenza `exit_mechanism` (#184): **non applicabile come caveat oggi** — entrambe le SELL portano
l'etichetta `below_entry_gate` che, dopo il deploy di #236 (2026-08-14), è **osservata** (letta dallo
stato reale dei segnali), non dedotta per età. Nessuna stima da correggere.

## 10. Anomalie trovate

### [DAY-301] Riavvio host a metà seduta di mercato con recupero inaffidabile dei log `worker`/`beat`/`worker-inference` per gran parte del pomeriggio — ricorrenza F-027 con meccanismo nuovo

* Tipo: Anomalia (ricorrenza F-027, meccanismo diverso dalle occorrenze precedenti)
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `docker inspect`, `uptime -s`, `docker logs alembic-worker-1`
  * timestamp: host `uptime -s` = 2026-08-17 16:03:37 CEST = 14:03:37 UTC; `docker inspect --format '{{.State.StartedAt}}'` → worker/beat/worker-inference 2026-08-17T14:04:22.9Z, api 2026-08-17T14:04:24.7Z, tutti `RestartCount=0`, `Created` invariato al 2026-08-15 (container riavviato, non ricreato)
  * snippet/query: `docker logs alembic-worker-1 -t` (senza `--since`) mostra 3.573 righe del 2026-08-17, l'ultima delle quali a 14:02:01,027 UTC; `docker logs alembic-worker-1 --since <qualunque timestamp posteriore, incluso "5m">` restituisce sistematicamente 0 righe **anche quando `docker logs --tail 3` nello stesso istante mostra righe correnti con timestamp coerente** (verificato ripetutamente: alle 12:35:55 UTC dell'08-18, `--tail 3` mostra entry a 12:35:00-12:35:01, ma `--since 5m` sullo stesso container restituisce 0 righe). Il container `api` non mostra questo comportamento: `--since 5m` restituisce 30 righe correnti.
* Descrizione: l'host su cui gira lo stack è stato riavviato durante l'orario di mercato (34 minuti dopo l'apertura), portando al riavvio simultaneo di tutti e 5 i container. Le tabelle DB (`portfolio_cycles`, `portfolio_monitor_snapshots`, `execution_decisions`, `trades`, `news_log`) mostrano **continuità totale** senza buchi attribuibili al riavvio — la pipeline applicativa ha ripreso a funzionare correttamente entro il minuto successivo. Ma il recupero storico dei log Docker per `worker`/`beat`/`worker-inference` (non per `api`) si è dimostrato inaffidabile in questa sessione: sia la lettura completa sia il filtro `--since` si fermano all'ultima riga pre-riavvio (14:02:01 UTC) o restituiscono zero righe, anche quando `--tail` prova che il container sta producendo log correnti regolarmente. Non sono riuscito a determinare con certezza se questo sia (a) un vero buco applicativo nella scrittura dei log dopo il riavvio del processo Celery (possibile rottura della redirezione stdout dei worker `ForkPoolWorker` dopo un riavvio del `MainProcess`, dato che il fenomeno è specifico ai container basati su Celery e non ad `api`), oppure (b) un limite del driver di log `json-file` (rotazione `max-size:50m, max-file:5`) combinato con un bug noto di Docker/Moby nel filtro `--since` su file ruotati. In entrambi i casi, il risultato pratico per questa sessione è lo stesso: **impossibile leggere in modo affidabile i log applicativi di `worker`/`beat`/`worker-inference` per gran parte del pomeriggio del giorno analizzato**, la stessa categoria di rischio già tracciata da F-027 ma con un meccanismo diverso (riavvio del processo, non ricreazione del container da redeploy).
* Impatto: nessuna perdita diretta (la pipeline ha funzionato correttamente secondo il DB). L'impatto è sulla capacità di questo stesso protocollo forense di verificare "eccezioni silenziose", "errori non propagati ad alert", latenza LLM e retry per il pomeriggio dell'08-17 — categorie richieste esplicitamente dal prompt forense e non verificabili oggi se non per assenza di sintomi nel DB (nessun task Celery fallito visibile nelle tabelle applicative, ma un'eccezione che non scrive su DB non lascerebbe comunque traccia).
* Severità: Medium (nessun impatto sul money path osservato; impatto pieno sull'osservabilità)
* Confidenza: **High** sull'osservazione empirica (riavvio host confermato da tre fonti indipendenti — `uptime`, `docker inspect` su 5 container, buco nei log); **Low** sulla causa esatta del fallimento di recupero log (non ho potuto escludere un artefatto dello strumento `docker logs` di questa sessione da una vera perdita applicativa).
* Azione consigliata: nessun fix di codice proposto in questo ciclo (causa non isolata con certezza). Ammesso come ricorrenza di F-027 per il test di esenzione: la carta prevede già che l'assenza di log per il giorno analizzato sia una categoria di difetto tracciata: se non corretta, l'evidenza raccolta durante la finestra resta parzialmente non verificabile ogni volta che capita un riavvio/deploy nello stesso giorno analizzato — qui il rischio si estende anche a riavvii non pianificati dell'host, non solo ai redeploy applicativi già coperti da F-027.
* Test/monitor consigliato: verificare se `PYTHONUNBUFFERED`/line-buffering è impostato per i processi Celery (mitiga la classe di bug "buffer non flushato dopo un segnale di riavvio"); considerare un log driver con retention indipendente dal ciclo di vita del container (es. `journald` o shipping a un aggregatore esterno) invece di `json-file` locale, così un'analisi forense del giorno successivo non dipende dalla cache locale del container.

### [DAY-302] `risk_reports`: divario drawdown/daily_pnl più ampio della serie osservata — ricorrenza F-003

* Tipo: Difetto (ricorrenza)
* Area: PnL / Risk
* Evidenza:
  * file/log/tabella: `risk_reports` id 66, `portfolio_monitor_snapshots`
  * timestamp: 2026-08-17 22:30:01 UTC (risk_reports); 20:00:00 UTC (snapshot EOD)
  * snippet/query: `combined_drawdown`=0,012429 (1,24%); `per_strategy_metrics->portfolio->drawdown`=0,177548 (17,75%) → genera `alerts=[{"level":"ALERT","message":"Strategy portfolio drawdown 17.8% exceeds 10%"}]`; `current_drawdown` reale da `portfolio_monitor_snapshots` alle 20:00 = 0,001537 (0,15%); `daily_pnl`=−1.980,38 contro `nav_change_today`=+37,28 (o −11,30 sul calcolo diretto apertura→chiusura)
* Descrizione: stessa famiglia di difetto documentata dal 07-31 (8 occorrenze precedenti) — tre numeri incompatibili per "drawdown" nello stesso record, e `daily_pnl` scollegato dal NAV reale sia in valore (50x) sia spesso in segno. Oggi il valore dell'alert (17,8%) è il **più alto mai osservato nella serie** (precedente massimo: 17,19% l'08-14, in crescita monotona da 13,9% il 07-31), mentre `combined_drawdown` resta bloccato a 1,24% (identico su tutte le occorrenze dal 07-31) e il drawdown reale (0,15%) è ai minimi storici della serie — la divergenza tra i tre numeri sta aumentando, non diminuendo.
* Impatto: nessuna perdita diretta; il rischio è che l'alert di drawdown, sparando ogni sera per il motivo sbagliato e con valore in crescita monotona indipendente dal NAV reale, desensibilizzi rispetto a un vero superamento della soglia del 5% durante la finestra di osservazione.
* Severità: Medium (invariata dalle occorrenze precedenti)
* Confidenza: High
* Azione consigliata: nessuna nuova — appendere l'occorrenza a F-003 nel ledger (fatto in questa sessione).
* Test/monitor consigliato: idem F-003 — riconciliazione automatica giornaliera fra le tre fonti di "drawdown"/"daily_pnl" con alert sullo scarto.

### [DAY-303] `execution_decisions.signal_id` NULL su 465/473 righe (98,3%) — ricorrenza F-011 al valore più alto osservato

* Tipo: Difetto (ricorrenza)
* Area: Signal / Data
* Evidenza: `SELECT COUNT(*), COUNT(*) FILTER (WHERE signal_id IS NULL) FROM execution_decisions WHERE created_at::date='2026-08-17'` → 473 totali, 465 NULL.
* Descrizione: la catena segnale→decisione→trade resta non tracciabile a livello di chiave esterna per la quasi totalità delle decisioni del giorno (F-011, già tracciato dal 07-31). Le due SELL di oggi (JD, BA) hanno anch'esse `signal_id` NULL nonostante il rationale citi esplicitamente uno score e un orario di generazione — la prova che il segnale causante esiste è nel testo del `reason`, non in una join verificabile.
* Impatto: nessuna perdita diretta; impatto sull'auditabilità della catena decisionale durante l'osservazione.
* Severità: Medium (invariata)
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-011.
* Test/monitor consigliato: idem F-011.

### [DAY-304] `portfolio_cycles.orders_count` non riconcilia con gli ordini realmente eseguiti — ricorrenza F-014

* Tipo: Difetto (ricorrenza)
* Area: Ops / Data
* Evidenza: `portfolio_cycles` del 2026-08-17 mostra `orders_count` fra 4 e 7 per ciascuno dei 24 cicli (totale implicito >100), mentre le uniche righe `trades` con `entry_time`/`exit_time` nel 2026-08-17 sono le 2 SELL delle 15:52.
* Descrizione: `orders_count` conta gli ordini target calcolati dal combiner in quel ciclo (inclusi quelli poi bloccati da guard come anti-pyramiding), non gli ordini realmente inviati/eseguiti — stesso meccanismo già tracciato in F-014.
* Impatto: nessuno sul money path; rischio di lettura errata dell'attività di trading se questa colonna viene usata come proxy di "ordini eseguiti" invece che "ordini valutati".
* Severità: Low (invariata)
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-014.
* Test/monitor consigliato: idem F-014.

## 11. False positive o aree risultate corrette

- **Nessun ordine sotto soglia**: verificato, nessuna decisione ha uno score sotto 0,05 alla base di un
  ordine reale (le due SELL sono guidate dal gate feedback, non da uno score minimo).
- **Nessun pyramiding reale**: le 10 SKIP_PYRAMIDING sono il guard che funziona correttamente.
- **Nessuna SELL con sentiment positivo (bug A5)**: score neutro/sotto-soglia alla base di entrambe le
  SELL, non positivo.
- **Nessun fallback_used=True su tutti i simboli**: fallback rate 39%, non un evento di outage totale
  di Ollama (i modelli hanno prodotto ensemble su 122/200 segnali).
- **Nessun NO-ORDER anomalo**: entrambe le SELL hanno una riga `trades`/`execution_decisions`
  corrispondente, nessuna decisione orfana.
- **Nessuna race condition scheduler**: nessuna coppia symbol+decisione duplicata nello stesso minuto.
- **Paper/live**: nessuna ambiguità, confermato su ogni snapshot.
- **`nav_change_today` internamente coerente oggi** (a differenza dell'08-14): stesso NAV di
  riferimento implicito su tutta la giornata — vedi §8.
- **F-028 (righe fantasma `reuters`) NON ricorre oggi**: nessuna contaminazione test↔produzione
  osservata su `ingestion_stats_daily`.
- **Nessuna ricorrenza di DAY-201 (08-14)**: `audit_log` non mostra alcun INSERT/DELETE anomalo su
  `trades` oggi, solo `SIGNAL_STALE_SKIP` sui segnali — nessuna evidenza di suite di test contro il
  DB di produzione oggi.
- **Meccanismo di uscita `[below_entry_gate]` funziona come da specifica post-#236**: le due SELL sono
  guidate da uno stato di segnale realmente osservato (score +0,000), non da una stima per età.
- **8 SKIP_FALLBACK correttamente loggate**: nessuna soppressione silenziosa osservata oggi (a
  differenza delle occorrenze F-006 precedenti su AVGO/HOOD).

## 12. Dati mancanti o non accessibili

- **API REST locale**: token fornito rifiutato (`Invalid or expired JWT token`) su `GET /api/decisions`.
  Sostituito con query SQL dirette (più autorevoli, ma bypassano eventuale logica applicativa di
  filtro/formattazione). Query che servirebbe: rigenerare il token e ripetere le chiamate `curl`.
- **Log Docker `worker`/`beat`/`worker-inference` per gran parte del pomeriggio 08-17**: recupero
  inaffidabile in questa sessione — vedi [DAY-301]. Non ricostruibili: latenza per-chiamata LLM, testo
  esatto di eventuali errori/timeout Ollama, eventuali eccezioni non persistite in tabelle applicative,
  per il periodo 14:02–20:00 UTC circa. Ricostruzione fatta interamente da Postgres.
- **Posizioni broker Alpaca dirette**: non interrogate (fuori dal protocollo read-only); riconciliazione
  fatta solo contro `portfolio_monitor_snapshots.open_positions` (47) e il conteggio `trades` aperti.
- **Causa esatta del riavvio host** delle 14:03:37 UTC: non determinabile da questa sessione (nessun
  accesso a log di sistema/host al di fuori di `uptime`); potrebbe essere un riavvio pianificato
  (manutenzione, patch) o un evento non pianificato — nessuna evidenza per distinguere i due casi.

## 13. Raccomandazioni immediate

1. **[DAY-301]** Verificare se i processi Celery (`worker`, `beat`, `worker-inference`) scrivono su
   stdout in modalità line-buffered (`PYTHONUNBUFFERED=1` o equivalente) — un buffer non flushato dopo
   un riavvio del processo padre è la spiegazione più probabile per la specificità del fenomeno ai
   container basati su Celery (non `api`).
2. Considerare uno shipping dei log verso un aggregatore esterno indipendente dal ciclo di vita del
   container Docker, così un'analisi del giorno successivo a un riavvio/redeploy non dipende dalla
   cache locale `json-file` — riduce l'impatto ricorrente di F-027 indipendentemente dal meccanismo
   esatto (ricreazione o riavvio).
3. Nessuna azione di taratura raccomandata: il money path del 2026-08-17 è corretto a specifica.

## 14. Test o monitor da aggiungere

- (Già raccomandato in cicli precedenti, non ripetuto in dettaglio) riconciliazione automatica
  giornaliera `risk_reports` drawdown/daily_pnl vs NAV reale (F-003); monitor decay per-strategia
  invece che pipeline-globale (F-004); consegna Telegram degli alert (F-005, ora con due sorgenti
  diverse di trigger osservate — loss-feedback e weekly-weight-computation).
- Alert su assenza di log Docker per un container per più di N minuti durante l'orario di mercato,
  indipendentemente dal fatto che il container risulti "running" (avrebbe intercettato [DAY-301] in
  tempo reale invece che in un'analisi del giorno successivo).

## 15. Ticket tecnici suggeriti

- **Nuovo, da aprire (ammesso dal freeze come difetto di correttezza-osservabilità)**: garantire che i
  processi Celery producano log leggibili dopo un riavvio del processo (line-buffering esplicito) e
  valutare un log driver/aggregatore con retention indipendente dal container — senza, ogni riavvio
  host o container a metà seduta produce un buco nell'evidenza raccolta durante la finestra di
  osservazione, esattamente il rischio che F-027 già segnala ma con un meccanismo aggiuntivo non
  coperto dalle mitigazioni finora proposte per quel finding (che si concentravano sui redeploy
  applicativi, non sui riavvii host).

## 16. Stato sistema

- **Ollama up/down**: nessuna evidenza di downtime totale — fallback rate 39,0% (78/200 segnali),
  ensemble a due modelli ha comunque prodotto la maggioranza dei segnali (122/200, 61%). Downtime
  esatto non quantificabile per il pomeriggio a causa di [DAY-301].
- **FinBERT fallback rate**: 1/200 segnali (0,5%) — il fallback deterministico di ultima istanza è
  stato usato una sola volta oggi; il fallback prevalente resta single-model LLM (77/200, 38,5%).
- **Worker restart events**: **sì, un evento oggi** — riavvio simultaneo di tutti e 5 i container alle
  14:04:22-24 UTC, conseguente a un riavvio host alle 14:03:37 UTC (34 minuti dopo l'apertura del
  mercato). Nessun impatto misurabile sulla continuità della pipeline (24/24 cicli portfolio regolari,
  82/82 snapshot regolari), ma impatto significativo sulla capacità di leggere i log applicativi del
  pomeriggio — vedi [DAY-301].
