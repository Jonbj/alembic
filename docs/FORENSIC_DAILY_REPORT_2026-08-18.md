# Forensic Daily Report — 2026-08-18

Analista: sessione autonoma Claude (Trading Systems Forensic Analyst + Senior Backend Engineer + Quant Operations Reviewer).
Modalità: read-only. Nessun ordine inviato, nessuna pipeline rieseguita, nessuna patch di codice applicata.
Timezone operativo: **UTC**, confermato in `src/workers/celery_app.py:51` (`timezone="UTC"`). Nessuna ambiguità di fuso trovata nel codice.
Finestre usate in questo report: pre-market = prima delle 13:30 UTC; market hours = 13:30–20:00 UTC (NYSE 9:30–16:00 ET, confermato dai `portfolio_monitor_snapshots` che iniziano/finiscono esattamente lì); post-market = dopo le 20:00 UTC; batch giornalieri = task Celery schedulati (21:00 decay, 22:30 risk).

## 1. Executive summary

Book paper (`alpaca_paper`) confermato per tutta la giornata, nessun halt operatore, nessuna deroga attiva al gate S4 (0,30 di baseline, coerente con #191). 3 BUY (HD, NVDA, TSLA), 2 SELL (HD, NVDA, entrambe `below_entry_gate`), entrambe con roundtrip ~105 min e P&L realizzato quasi nullo (+$0,70 e +$0,25). Nessuna violazione di correttezza trovata sul money path: gate rispettato, anti-pyramiding ha bloccato 5 tentativi come da design, nessuna SELL su sentiment positivo, nessun ordine fuori orario, nessun duplicato, nessun trade su dati stale o con LLM non validato, drawdown (0,42%) e gross exposure (30,5%) ben dentro i limiti (5%/50%). NAV −$293,39 sulla giornata (110.473,80 → 110.180,41), quasi interamente mark-to-market su book esistente (realizzato dei 2 trade chiusi = +$0,96), su una seduta di forte vendita nei semiconduttori (MU −7,0%, MRVL −7,8%, ARM −6,7%, INTC −6,6%). Sette difetti già noti dal ledger sono ricorsi identici (F-002, F-003, F-004, F-007, F-011 al valore più alto mai osservato, F-013, F-015, F-027). Due elementi nuovi per questa sessione: i container applicativi sono stati **ricreati** (non solo riavviati) alle 08:20 UTC del giorno successivo, cancellando ogni log Docker del 18/08 (nuova faccia di F-027); e il bearer token fornito per l'API REST di questo protocollo veniva rifiutato con "Invalid or expired JWT token" su tutti gli endpoint — causa isolata: va inviato come header `X-API-Key`, non `Authorization: Bearer`, per come `require_api_key` instrada i due meccanismi di auth (nuovo F-041, bug di tooling non di trading). I miss NO_NEWS/BELOW_GATE/long-only del giorno (BIDU, HOOD, META, RDDT, ADBE, AVGO) sono già stati tracciati dal cron alpha-miss separato (F-001, F-009, F-012, F-040) prima di questa sessione — non riproposti come nuove occorrenze.

## 2. Verdict finale

**OK con warning.**

Il processo end-to-end (news → segnale → decisione → ordine → fill → posizione) ha funzionato correttamente e in modo verificabile dal DB per tutta la giornata. I warning riguardano esclusivamente lo strato di osservabilità/monitoraggio (risk_reports, decay_reports, audit trail signal_id, log dei container) — difetti tutti già tracciati, nessuno nuovo nel money path.

## 3. Timeline del 2026-08-18 (UTC)

| Ora | Componente | Evento | Fonte |
|---|---|---|---|
| 13:00:41 | news ingest (alpaca_benzinga) | prima news pubblicata della giornata (pre-market, 30 min prima dell'apertura) | `news_log.published_at` |
| 13:30:00 | portfolio_monitor | primo snapshot NAV=110.216,88, nav_change_today=−256,92, 47 posizioni aperte | `portfolio_monitor_snapshots` |
| 14:00–19:45 | sentiment worker | 164 righe `sentiment_signals` generate (100 ensemble dual-model, 64 fallback single-model), nessun errore/timeout osservabile da log (persi, vedi §12/[DAY-401]) | `sentiment_signals`, `llm_responses` |
| 14:15:06 | ingest | prima riga `sentiment_signals` della giornata (BIDU, ensemble, score −0,454) | `sentiment_signals` |
| 14:22:00 | execution | **BUY HD** — sentiment +0,569 (ensemble glm-5.2+gpt-oss), peso target 2,0% | `execution_decisions` id 8067→`trades` id 737 |
| 15:07–17:22 | execution | 5 blocchi `SKIP_PYRAMIDING` (IWM, WDC, HD, UNH, NVDA) — guard P0-05 anti-pyramiding, comportamento corretto | `execution_decisions` |
| 15:52, 18:07(×2), 19:37 | execution | 4 blocchi `SKIP_FALLBACK` (PANW, IWM, XOM, MMM) — segnale single-model escluso dal ranking BUY per assenza di ensemble (#108) | `execution_decisions` |
| 16:07:00 | execution | **SELL HD** — `below_entry_gate`, nuovo segnale delle 15:30 con score 0,000 (età 0,6h < max 4h): posizione chiusa, roundtrip 105 min, net_pnl +$0,70 | `execution_decisions` id→`trades` id 737 |
| 16:37:00 | execution | **BUY NVDA** (+0,504) e **BUY TSLA** (+0,426), stesso ciclo | `execution_decisions` id 8158/8153 |
| 18:22:00 | execution | **SELL NVDA** — `below_entry_gate`, segnale delle 17:30 con score −0,150 (segno invertito): roundtrip 105 min, net_pnl +$0,25 | `execution_decisions`→`trades` id 738 |
| 18:52:08 | execution | `SKIP_STALE` SOXX — segnale 4,1h > max_age 4h, score −0,115 scartato correttamente | `execution_decisions` |
| 19:45:42 | sentiment worker | ultimo segnale della giornata | `sentiment_signals` |
| 19:52:10 | execution | ultimo ciclo di decisioni loggato (CAT, GOOGL, altri SKIP_THRESHOLD) | `execution_decisions` |
| 20:00:00 | portfolio_monitor | ultimo snapshot NAV=110.180,41, nav_change_today=−293,39, 48 posizioni, gross_exposure 30,5%, drawdown 0,42% | `portfolio_monitor_snapshots` |
| 21:00:00 | decay_monitor | `decay_reports`: 12 righe, valori actual IDENTICI su S1/S2/S4 (ricorrenza F-004) | `decay_reports` |
| 22:30:01 | risk_monitor | `risk_reports` id 67: combined_drawdown 1,24% vs per_strategy portfolio.drawdown 17,75% → ALERT falso "17.8% exceeds 10%" (ricorrenza F-003) | `risk_reports` |
| 2026-08-19 08:20:07–11 | infra | **worker/api/worker-inference/beat ricreati** (redeploy, `Created`=`StartedAt`); postgres/redis non toccati. Ogni log Docker del 18/08 per questi 4 container è irrecuperabile (nuova occorrenza F-027) | `docker inspect` |

Nessuna news con timestamp futuro (0 righe `published_at > now()`), nessun buco intraday nei 5-minute snapshot (13:30→20:00, cadenza regolare, 79 righe attese e trovate).

## 4. Tabella news ingest

| Fonte | Fetched | Queued | Duplicates | Discarded (no ticker) | Landed in `news_log` |
|---|---|---|---|---|---|
| alpaca_benzinga | 698 | 335 | **3.278** (4,7× fetched — F-007) | 0 | 84 |
| gdelt_gkg | 1.970 | 143 | 49 | 1.800 | 80 |
| **Totale** | 2.668 | 478 | — | 1.800 | **164** |

- Copertura watchlist: 40/96 simboli (42%) con zero righe — dentro la banda 38-57% osservata dal 31/07 (F-001, già registrata oggi dal cron alpha-miss separato).
- Finestra temporale coperta: `published_at` 13:00:41→18:00:00 UTC; `fetched_at`/`generated_at` 14:15:06→19:45:42 UTC. Nessuna news oltre le 18:00 UTC nonostante lo scheduler GDELT resti attivo fino alle 21:00 — non anomalo di per sé (dipende dal flusso reale dei publisher), ma riduce la finestra di reazione utile a ~4h del pomeriggio.
- 178 news scartate per staleness (>2h, soglia `MAX_NEWS_AGE_HOURS=2` in `src/config.py:310`) — 135 alpaca_benzinga + 43 gdelt_gkg, filtro funzionante come da design, non un'anomalia.
- Deduplicazione (url, ticker): **0 collisioni vere** — i 31 gruppi di `content_hash` ripetuto sono fan-out dello stesso articolo su ticker diversi (comportamento noto, F-012/F-020), non un fallimento del dedup.
- Top ticker per volume news: MS 16, MU 14, NVDA 12, GS 11, AMZN 9 — MS+GS assorbono 27 righe (fan-out bancario noto, F-020).
- Nessun campo mancante rilevante, nessun timestamp futuro, nessun retry loggato (i log applicativi del giorno non sono recuperabili, vedi §12).
- Confidenza dell'analisi: **alta** sui conteggi DB, **media** sulla causa esatta del taglio a 18:00 UTC (non verificabile senza i log ingest persi).

## 5. Tabella performance modelli LLM

| Model | Righe `sentiment_signals` | Ruolo | Score medio | Confidence media | Note |
|---|---|---|---|---|---|
| ensemble:glm-5.2+gpt-oss | 100 (61%) | ensemble dual-model completo | −0,008 | 0,319 | std medio disaccordo 0,057, max 0,318 (META) — nessun caso di varianza estrema |
| single:gpt-oss:20b-cloud | 58 (35%) | fallback (glm-5.2 non disponibile/scartato) | −0,033 | 0,486 | fallback_used=true su tutte le 58; distribuito uniformemente in ogni ora (9,14,13,11,7,4) — nessuna finestra di outage totale |
| single:glm-5.2:cloud | 5 (3%) | fallback (gpt-oss non disponibile/scartato) | +0,067 | 0,420 | fallback_used=true su tutte e 5 |
| finbert | 1 (1%) | fallback deterministico finale | +0,002 | 0,068 | 1 sola riga — guardrail di ultima istanza usato una volta |

`llm_responses`: 164 chiamate per modello, `eligible=true` (confidence ≥ soglia LOO-ICIR 0,4, `ENSEMBLE_MIN_CONFIDENCE` in `src/config.py:250`) solo su 30/164 (18%) per ciascun modello — atteso dato che la confidence media delle singole risposte gira intorno a 0,3-0,4, non un errore di chiamata. `fallback_counters.consecutive_fallback = 0` a fine giornata: nessuna sequenza di fallback prolungata, il pattern osservato è un 35-39% di fallback distribuito, non un'interruzione Ollama.

Verifica funzionale:
- **Output validato prima del signal store**: sì, via `eligible` (gate di confidence) e `force_ineligible` sui fallback (`pg_store.py:1727-1751`), coerente con l'architettura DK-CoT descritta in CLAUDE.md.
- **Varianza alta gestita**: gate presente (`ensemble_std`) ma **non risulta usato come blocco d'ingresso** oggi — nessun caso però lo avrebbe richiesto (std max 0,318, sotto qualunque soglia ragionevole).
- **News duplicate pesate più volte**: no, 164 `sentiment_signals` = 164 `news_log_id` distinti (1:1).
- **Stessa news → segnali multipli**: no, confermato dal punto precedente.
- **Confidence bassa riduce il peso**: sì, per costruzione (score = polarity × confidence, formula CLAUDE.md rispettata — verificato a campione: HD score/reasoning coerenti).
- **Chiamate offline/background, mai nel trading loop**: confermato — worker `worker-inference` dedicato (concurrency=1, queue `inference`), separato da `worker` che esegue `portfolio-cycle`.
- **Rischio hallucination diretto in decisione**: mitigato dal gate di soglia (0,30) e dal confidence gate (0,4), ma **non verificabile oggi il contenuto testuale delle 164 `reasoning`** in modo sistematico (fuori scope di questa sessione, nessun errore di parsing/refusal osservato nei campioni letti).

## 6. Tabella segnali finali per ticker (BUY/SELL generati)

| Ticker | Ora | Score ensemble | Weight target | Decisione | Strategia |
|---|---|---|---|---|---|
| HD | 14:22 | +0,569 | 2,0% | BUY | S4 |
| HD | 16:07 | 0,000 (nuovo segnale 15:30) | 0,0% | SELL (below_entry_gate) | S4 |
| NVDA | 16:37 | +0,504 | 2,0% | BUY | S4 |
| TSLA | 16:37 | +0,426 | 2,0% | BUY | S4 |
| NVDA | 18:22 | −0,150 (nuovo segnale 17:30) | 0,0% | SELL (below_entry_gate) | S4 |

Gate d'ingresso usato: **0,30** (baseline di design, `feedback:entry_threshold:S4`=0,30 confermato su Redis — nessuna deroga ratchet attiva). 499 righe `SKIP_THRESHOLD` su 514 decisioni totali (97,1%) — il grosso del traffico decisionale è scarto sotto soglia, atteso per un motore a gate singolo su una watchlist di 96 simboli con 15 minuti di ciclo.

## 7. Tabella ordini generati/eseguiti

| Ticker | Decisione | Ora decisione | Order ID | Entry/Exit price | Qty | Stato | Strategia | Rationale | Anomalie |
|---|---|---|---|---|---|---|---|---|---|
| HD | BUY | 14:22:00 | 93f1a6da-… | 339,98 | 3,7658 | filled | S4 | sentiment +0,569, earnings beat | nessuna |
| HD | SELL | 16:07:00 | f20d16fc-… | 340,88 | 3,7658 | filled | S4 | below_entry_gate | roundtrip 105 min (F-013) |
| NVDA | BUY | 16:37:00 | d092558c-… | 219,65 | 5,8082 | filled | S4 | sentiment +0,504, CUDA lock-in | stesso tick_time di TSLA (stesso ciclo, non race) |
| TSLA | BUY | 16:37:00 | 17def6fc-… | 337,20 | 3,7835 | filled (aperta a EOD) | S4 | sentiment +0,426, Einride Semi order | mtm_eod −$1,25 |
| NVDA | SELL | 18:22:00 | 7e0af547-… | 220,23 | 5,8082 | filled | S4 | below_entry_gate, segno invertito | roundtrip 105 min (F-013) |

Tutti gli `entry_order_id`/`exit_order_id` sono UUID Alpaca distinti (nessun duplicato), nessuna coppia BUY/SELL nello stesso minuto sullo stesso simbolo, nessun ordine fuori 13:30–20:00 UTC, nessun ordine con `signal_score` assente o incoerente col gate. Broker: `broker_environment=paper`, `mode=paper`, `source=alpaca_paper` per l'intera giornata (confermato su tutti gli snapshot).

## 8. Tabella PnL/rendimento

| Voce | Valore | Fonte |
|---|---|---|
| NAV apertura (13:30) | $110.216,88 (nav_change_today −256,92 ⇒ chiusura precedente ≈$110.473,80) | `portfolio_monitor_snapshots` |
| NAV chiusura (20:00) | $110.180,41 | `portfolio_monitor_snapshots` |
| Variazione NAV giornata | **−$293,39** (−0,27%) | idem |
| P&L realizzato (2 trade chiusi) | +$0,96 (HD +$0,70, NVDA +$0,25) | `trades.net_pnl` |
| P&L non realizzato (implicito) | ≈ −$294,35 (NAV change − realizzato) | derivato |
| Gross exposure EOD | 30,5% (limite 50%) | `portfolio_monitor_snapshots` |
| Drawdown corrente EOD | 0,42% (limite 5%) | idem |
| Herfindahl (risk_reports 22:30) | 0,023 | `risk_reports` |
| Costi/commissioni sui 2 trade chiusi | HD $0,70 (5,25 bps), NVDA $0,25 (1,75 bps) — `slippage_est` identico a `cost_usd` in entrambi i casi (F-015) | `trades` |
| Split S1/S4/legacy (posizioni aperte a EOD) | S1 34, S4 3, non attribuibile (legacy 07-10) 11 su 48 totali | `trades` |
| MTM stimato oggi del blocco legacy non attribuibile | ≈ **−$13,93** (4,7% della variazione NAV giornaliera) — stima via qty × delta-close dai rendimenti giornalieri, non uno snapshot diretto | derivato (F-002) |

Il libro ha assorbito una seduta di forte vendita nei semiconduttori (MU −7,0%, MRVL −7,8%, ARM −6,7%, INTC −6,6%, AMD −4,3%, AVGO −3,2%, NVDA −2,3% su `mercato.rendimenti` del dossier), coerente col segno negativo della giornata nonostante i 2 trade S4 chiusi in utile. Non posso scomporre il P&L non realizzato per singola posizione con precisione superiore a quanto sopra: manca uno snapshot posizione-per-posizione a inizio giornata (solo il totale NAV è campionato ogni 5 minuti); la stima usa i rendimenti daily-close del dossier, non i prezzi di apertura reali per ogni ticker.

## 9. Analisi correttezza buy/sell

| Controllo | Esito |
|---|---|
| BUY generati solo quando consentito (gate 0,30, no halt, no circuit breaker) | ✅ verificato: tutti e 3 sopra soglia, nessun halt attivo (`system:halted_by_operator` vuoto) |
| SELL/exit generati correttamente | ✅ entrambe le SELL sono `below_entry_gate` con segnale nuovo che invalida quello d'ingresso, non arbitrarie |
| Stop-loss rispettati | ✅ nessuno stop scattato oggi (`stop_decisions` = 0 righe), coerente: nessuna posizione ha toccato la soglia |
| Signal flip rispettato | ✅ NVDA: segno passato da +0,504 a −0,150 → uscita corretta |
| Max holding days | n/a oggi (nessuna posizione ha raggiunto l'orizzonte massimo) |
| Rebalance band | n/a — nessun evento di ribilanciamento S1 osservato oggi nei log decisionali S4 |
| Niente ordini duplicati | ✅ verificato, nessuna coppia (tick_time, symbol, decision) ripetuta |
| Niente ordini contrari ravvicinati senza rationale | ✅ ogni SELL ha un `reason` testuale coerente col nuovo segnale che l'ha causata |
| Niente ordini su ticker non consentiti | ✅ tutti i simboli in decisione appartengono alla watchlist nota |
| Niente ordini fuori orario | ✅ tutte le decisioni BUY/SELL cadono 14:22–18:22 UTC, dentro 13:30–20:00 |
| Niente trade su dati stale | ✅ `SKIP_STALE` ha funzionato (SOXX scartato a 4,1h) |
| Niente trade su LLM output non valido | ✅ nessuna riga `SKIP_FALLBACK` è diventata BUY (4 fallback esclusi dal ranking come da #108) |
| Niente trade con circuit breaker attivo | ✅ nessun alert CRITICAL da `risk_reports` ha bloccato ordini (l'alert era comunque un falso positivo, F-003) |
| Niente trade con strategia disabilitata | ✅ solo S4 ha generato ordini oggi, S4 è attiva |
| Paper/live coerente | ✅ `paper` ovunque |
| Idempotenza retry Celery | ✅ nessun ordine duplicato nello stesso ciclo |
| Reconciliation ordini↔fill↔posizioni | ✅ 48 `trades` aperti = 48 posizioni via API; 3 BUY + 2 SELL oggi = coerente col delta posizioni (47→48→47→49→48 nei snapshot, in linea con apertura/chiusura infragiornaliera) |

**Pattern operativi specifici richiesti:**
- Roundtrip < 30 min: **nessuno** (HD e NVDA sono a 105 min, non sotto soglia).
- BUY ripetuto >3× senza SELL intermedio: **nessuno**, guard anti-pyramiding ha bloccato 5 tentativi (IWM, WDC, HD, UNH, NVDA).
- SELL con sentiment positivo (bug A5): **nessuno** — HD a 0,000, NVDA a −0,150.
- `fallback_used=True` su tutti i simboli in un periodo (Ollama giù): **non riscontrato** — fallback distribuito 35-39%, mai il 100% in nessuna ora.
- NO-ORDER (decisione creata ma ordine non generato): **non applicabile** — le uniche righe BUY/SELL hanno tutte `order_id` popolato.
- Score < 0,05 con ordine generato: **nessuno** — tutti i BUY hanno `signal_score` ≥ 0,30 (attenzione: la colonna `score` di `execution_decisions` è il **peso target**, non lo score di sentiment — verificato in `pg_store.py:412-416`, da non confondere).
- Ordini identici nello stesso minuto (race scheduler): **nessuno** — NVDA e TSLA condividono `tick_time` 16:37:00 ma sono simboli diversi nello stesso ciclo portfolio, non un duplicato.

## 10. Anomalie trovate

### [DAY-401] Container `worker`/`api`/`worker-inference`/`beat` ricreati la mattina dopo — log Docker del 18/08 irrecuperabili (ricorrenza F-027, meccanismo nuovo)

* Tipo: Anomalia (ricorrenza F-027, nona occorrenza — meccanismo diverso da tutte le precedenti)
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `docker inspect alembic-worker-1/api-1/worker-inference-1/beat-1`
  * timestamp: `Created`=`StartedAt`=2026-08-19T08:20:07–11Z per tutti e 4 i container
  * snippet/query: `Created=2026-08-19T08:20:07.710423742Z | StartedAt=2026-08-19T08:20:11.467...Z | RestartCount=0` (worker); `alembic-postgres-1` invece ha `Created` al 21/05 e `StartedAt` al 17/08 (riavvio host precedente, non toccato oggi)
* Descrizione: a differenza dell'occorrenza dell'08-17 (riavvio host, container non ricreati, `Created` invariato), oggi i 4 container basati su codice applicativo hanno `Created`=`StartedAt`, prova di una **ricreazione reale** (redeploy) avvenuta la mattina del 19/08, ore dopo la chiusura della sessione del 18/08 analizzata. Il risultato pratico è identico alle occorrenze precedenti di F-027: zero righe di log Docker per l'intera giornata del 18/08 su questi 4 container (`docker compose logs --since 48h | grep 2026-08-18` restituisce 0 righe per ERROR/WARNING/CRITICAL). Le tabelle DB (`portfolio_cycles`, `execution_decisions`, `sentiment_signals`, `portfolio_monitor_snapshots`) mostrano continuità completa senza buchi — la pipeline applicativa ha funzionato regolarmente, solo l'evidenza di log testuale è persa.
* Impatto: impossibile confermare/escludere errori applicativi silenziosi (refusal LLM, retry, eccezioni catturate ma non propagate al DB) per l'intera giornata analizzata da questa sessione.
* Severità: Medium
* Confidenza: High (meccanismo verificato via `docker inspect`, non congetturato)
* Azione consigliata: nessun fix di codice in questo ciclo (ammesso come ricorrenza F-027, già in ledger da 9 occorrenze); valutare — fuori da questo ciclo di osservazione — l'esportazione dei log applicativi verso uno store persistente esterno ai container prima di ogni redeploy.
* Test/monitor consigliato: idem F-027 — hook pre-redeploy che esporta gli ultimi N giorni di log, o driver di log con retention indipendente dal ciclo di vita del container.

### [DAY-402] Il token di questo protocollo forense viene rifiutato su tutti gli endpoint REST ("Invalid or expired JWT token") — causa isolata: header sbagliato, non chiave scaduta

* Tipo: Bug (nuovo finding F-041)
* Area: Ops / Data
* Evidenza:
  * file/log/tabella: `src/api/auth.py:15-46` (`require_api_key`)
  * timestamp: 2026-08-19 (sessione corrente)
  * snippet/query: `curl -H "Authorization: Bearer <token>" .../api/decisions` → 403 `{"detail":"Invalid or expired JWT token"}`; `curl -H "X-API-Key: <stesso token>" .../api/decisions` → 200 OK. Confermato: `docker exec alembic-api-1 printenv ADMIN_API_KEY` == il token fornito da questo protocollo.
* Descrizione: `require_api_key` prova prima il path JWT se l'header `Authorization: Bearer …` è presente (righe 27-37), e se il decode fallisce **non ripiega mai** sul controllo `X-API-Key` (righe 39-41 sono raggiungibili solo se `Authorization` è assente). Il token fornito da questo protocollo è la chiave statica legacy (`ADMIN_API_KEY`), pensata per il path `X-API-Key`, non un JWT — per questo ogni chiamata con `Authorization: Bearer` fallisce sempre, indipendentemente da quanto la chiave sia "fresca". Non è una chiave scaduta: è il meccanismo di trasporto sbagliato nel template di questo prompt/skill.
* Impatto: questa sessione (e presumibilmente ogni sessione di questo cron che segua le istruzioni curl come scritte) non può leggere `/api/decisions|trades|signals|positions|orders` senza scoprire e correggere l'header — ho dovuto ricostruire i dati via query dirette a Postgres come fallback, previsto dal protocollo stesso ("Risorse disponibili" include Postgres) ma con più lavoro e superficie di errore.
* Severità: Low (workaround esiste ed è documentato nel protocollo stesso — l'accesso DB diretto)
* Confidenza: High (root cause isolata e riprodotta con successo su `X-API-Key`)
* Azione consigliata: correggere il template/skill che genera le istruzioni curl di questo protocollo per usare `X-API-Key: <token>` invece di `Authorization: Bearer <token>`, oppure emettere per il cron un vero JWT via `POST /api/auth/login`. Nessun fix richiesto sul codice di `require_api_key`: il comportamento a due path è intenzionale e documentato nel suo stesso docstring.
* Test/monitor consigliato: nessuno strutturale — è un errore di configurazione del prompt, non del sistema.

### [DAY-403] `risk_reports`: tripla incoerenza drawdown/daily_pnl, ALERT falso invariato (ricorrenza F-003)

* Tipo: Difetto (ricorrenza, undicesima occorrenza)
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports` id 67, `portfolio_monitor_snapshots` (20:00 UTC)
  * timestamp: 2026-08-18 22:30:01 UTC
  * snippet/query: `combined_drawdown=0.012429 (1,24%)`, `per_strategy_metrics.portfolio.drawdown=0.1775475695171766 (17,75%)` → `alerts=[{"level":"ALERT","message":"Strategy portfolio drawdown 17.8% exceeds 10%"}]`, mentre `current_drawdown` reale allo snapshot delle 20:00 = 0,004209 (0,42%)
* Descrizione: stesso schema documentato dal 31/07 — tre grandezze incompatibili chiamate "drawdown" nello stesso record, l'ALERT generato dalla peggiore delle tre. Valore quasi identico all'occorrenza dell'08-17 (17,75% vs 17,75%), come se la serie `per_strategy_metrics.portfolio.drawdown` fosse bloccata su un calcolo che non si aggiorna più in modo coerente col NAV reale.
* Impatto: l'ALERT quotidiano è rumore — nessuno se ne accorgerebbe il giorno in cui il drawdown vero supera davvero il 5%.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-003, già in ledger.
* Test/monitor consigliato: idem F-003 — riconciliazione automatica fra le tre fonti di drawdown con alert sullo scarto stesso.

### [DAY-404] `decay_reports`: metriche pipeline-globali identiche su S1/S2/S4, S2 morta comunque CRITICAL (ricorrenza F-004)

* Tipo: Difetto (ricorrenza, ottava occorrenza)
* Area: Risk
* Evidenza: `decay_reports`, timestamp 2026-08-18 21:00:00
* Descrizione: `hit_rate=0,3177`, `ic=0,0277`, `max_drawdown=0,1194`, `sharpe=−7,58` **identici** su S1, S2 e S4; confrontati contro 3 baseline diverse → CRITICAL su `sharpe` per tutte e tre le strategie, incluso S2 che non ha mai una riga in `trades`.
* Impatto: il meccanismo di sorveglianza del decadimento — proprio ciò su cui poggia la finestra di osservazione — non distingue S1 da S4.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-004.
* Test/monitor consigliato: idem F-004.

### [DAY-405] `ingestion_stats_daily.duplicates` (3.278) supera `fetched` (698) di 4,7× per alpaca_benzinga (ricorrenza F-007)

* Tipo: Osservazione (ricorrenza, ottava occorrenza)
* Area: News / Data
* Evidenza: `ingestion_stats_daily` day=2026-08-18, source=alpaca_benzinga
* Descrizione: stesso schema strutturale già tracciato dal 10/08 — il contatore `duplicates` non torna con nessuna lettura indipendente delle righe realmente persistite (164 righe `news_log` totali). `gdelt_gkg` nello stesso giorno resta coerente (49 duplicati su 1.970 fetched).
* Impatto: impossibile rispondere con certezza a "quanta news sta scartando il dedup" per la fonte Benzinga.
* Severità: Low
* Confidenza: Medium (congetturale)
* Azione consigliata: nessuna nuova — ricorrenza di F-007.
* Test/monitor consigliato: idem F-007.

### [DAY-406] `execution_decisions.signal_id` NULL su 509/514 righe (99,0%) — valore più alto mai osservato (ricorrenza F-011)

* Tipo: Difetto (ricorrenza, valore massimo della serie)
* Area: Signal / Data
* Evidenza: `execution_decisions`, 2026-08-18
* Descrizione: 509 righe su 514 hanno `signal_id` NULL, incluse **entrambe** le SELL del giorno (HD, NVDA) nonostante il `reason` citi esplicitamente score e orario di generazione del segnale causante — la prova che il segnale esiste è nel testo, non in una join verificabile a chiave esterna.
* Impatto: la catena segnale→decisione→trade non è ricostruibile per query, solo per lettura testuale del `reason`.
* Severità: Medium
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-011.
* Test/monitor consigliato: idem F-011.

### [DAY-407] `trades.slippage_est` == `cost_usd` esatto su entrambe le chiusure di oggi (ricorrenza F-015)

* Tipo: Difetto (ricorrenza)
* Area: Orders / PnL
* Evidenza: `trades` id 737 (HD: slippage_est=cost_usd=0,7024910133744303), id 738 (NVDA: slippage_est=cost_usd=0,2537252983105616)
* Descrizione: la colonna dedicata alla qualità di esecuzione è una copia esatta del costo stimato, non una misura indipendente.
* Impatto: nessuna misura reale di slippage disponibile.
* Severità: Low
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-015.
* Test/monitor consigliato: idem F-015.

### [DAY-408] Churn intraday: HD e NVDA aperte e chiuse nello stesso pomeriggio via `below_entry_gate` (ricorrenza F-013)

* Tipo: Difetto (ricorrenza)
* Area: Signal / Orders
* Evidenza: `execution_decisions`/`trades` id 737 (HD, 14:22→16:07, 105 min), id 738 (NVDA, 16:37→18:22, 105 min)
* Descrizione: nessuna banda d'isteresi fra il gate d'ingresso (0,30) e la soglia d'uscita (0): un nuovo segnale sullo stesso simbolo, anche di poche ore più tardi e con score debole/invertito, chiude la posizione. Meccanismo già isolato in `portfolio_scheduler.py:3715-3722` (il filtro si applica all'intero `signals_df`, non solo ai candidati nuovi). Oggi entrambi i roundtrip sono stati marginalmente positivi (+$0,70, +$0,25), ma il pattern resta strutturale.
* Impatto: costi di transazione ripetuti su posizioni che durano meno di 2 ore quando il "santo graal" dichiarato dalla strategia è news-driven, non intraday scalping.
* Severità: Low (oggi P&L neutro/positivo)
* Confidenza: High
* Azione consigliata: nessuna nuova — ricorrenza di F-013 (rimedio è taratura, fuori scope osservazione).
* Test/monitor consigliato: idem F-013.

### [DAY-409] 11/48 posizioni aperte restano senza `stop_strategy` (legacy 07-10), oggi ≈ −$13,93 di MTM non attribuibile (ricorrenza F-002)

* Tipo: Osservazione (ricorrenza)
* Area: PnL / Data
* Evidenza: `trades` (11 righe con `stop_strategy IS NULL`, tutte `entry_time`='2026-07-10'), posizioni via API (`X-API-Key`)
* Descrizione: stesso insieme di sempre (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE). Contributo stimato oggi (qty × delta-close dai rendimenti giornalieri del dossier): BAC +3,89, GOOGL +0,38, GS −7,00, MS −2,01, PBR −2,80, RIO −3,95, ROKU −2,45, SPY −4,73, UBS −6,24, UNH −2,70, XLE +13,68 ⇒ **totale ≈ −$13,93**, il 4,7% della variazione NAV di oggi (−$293,39) — quota più bassa osservata nella serie rispetto alle occorrenze precedenti (11-58%).
* Impatto: split P&L economico S1 vs SPY (domanda di uscita 2 della carta) resta parzialmente indeterminato finché queste 11 posizioni sono aperte, anche se oggi il loro peso relativo è basso.
* Severità: Low
* Confidenza: Medium (stima via decomposizione rendimento giornaliero, non uno snapshot diretto pre/post)
* Azione consigliata: nessuna nuova — ricorrenza di F-002.
* Test/monitor consigliato: idem F-002.

## 11. False positive o aree risultate corrette

- **Ordini BUY/SELL simultanei su NVDA/TSLA alle 16:37:00**: verificato **non** essere una race condition — stesso ciclo portfolio, simboli diversi, comportamento atteso del combiner multi-simbolo.
- **`score` di `execution_decisions` apparentemente basso (0,02) sui BUY**: **non** è lo score di sentiment (che è in `signal_score`, correttamente ≥0,30 su tutti e 3) — è il peso target di portafoglio (2,0%). Nessuna violazione della soglia gate.
- **Fallback single-model 35-39% distribuito su tutte le ore**: verificato **non** essere un'interruzione totale di Ollama — `consecutive_fallback=0` a fine giornata, nessuna ora con 100% fallback, coerente con un tasso di indisponibilità/degradazione parziale del solo modello secondario, non un outage.
- **`ensemble_std` massimo 0,318 (META)**: sotto qualunque soglia di allerta ragionevole — nessun caso di disaccordo estremo tra i due modelli oggi.
- **Miss NO_NEWS/BELOW_GATE/long-only del giorno (BIDU −12,73%, HOOD −4,90%, META −4,45%, RDDT −3,80%, ADBE +3,58%, AVGO −3,17%)**: già interamente tracciati oggi dal cron alpha-miss separato (F-001, F-009, F-012, F-040), con costo verificato zero o non stimabile per vincolo long-only/#277 — non riproposti come nuove occorrenze in questa sessione per evitare doppio conteggio.
- **Reconciliation ordini↔posizioni**: 48 `trades` aperti = 48 posizioni via API — nessuna divergenza.

## 12. Dati mancanti o non accessibili

- **Log applicativi Docker (`worker`, `api`, `worker-inference`, `beat`) per l'intera giornata del 18/08**: irrecuperabili, i container sono stati ricreati il 19/08 alle 08:20 UTC (§10, [DAY-401]). Non posso confermare/escludere errori silenziosi, timeout LLM a livello di singola chiamata, o la causa esatta del taglio della finestra news a 18:00 UTC (§4).
- **Endpoint REST `/api/decisions|trades|signals|positions|orders` con l'header fornito dal protocollo**: inaccessibili con `Authorization: Bearer`, risolti con `X-API-Key` dopo diagnosi (§10, [DAY-402]). Dati recuperati comunque via Postgres diretto + API con header corretto.
- **Prezzi intraday per-tick per ricostruire il P&L non realizzato posizione-per-posizione**: solo il NAV aggregato è campionato ogni 5 minuti; la scomposizione per singolo ticker in §8 è una stima via rendimento daily-close, non una misura diretta.
- **Conferma broker-side di submit/fill (timestamp Alpaca `submitted_at`/`filled_at`, eventuali reject)**: non interrogata direttamente via Trading API in questa sessione (fuori scope read-only del protocollo); mi sono basato su `entry_price`/`exit_price` popolati in `trades` come prova indiretta di fill avvenuto.
- **Testo completo delle 164 `reasoning` LLM**: letto solo a campione, non validato sistematicamente per refusal/parsing-fail.

## 13. Raccomandazioni immediate

Nessuna azione immediata richiesta sul money path — tutte le anomalie di oggi sono ricorrenze note di difetti di osservabilità, già in ledger, con rimedio classificato come taratura/instrumentazione fuori dal perimetro d'esenzione della carta (tranne dove già derogato, es. #236). L'unica azione a costo zero e beneficio immediato: **correggere l'header nel template di questo protocollo cron da `Authorization: Bearer` a `X-API-Key`** ([DAY-402]) — evita che ogni futura esecuzione di questo stesso cron ripeta la stessa diagnosi.

## 14. Test o monitor da aggiungere

- Riconciliazione automatica giornaliera fra le tre fonti di "drawdown" (`combined_drawdown`, `per_strategy_metrics.portfolio.drawdown`, `portfolio_monitor_snapshots.current_drawdown`) con alert sullo scarto stesso, non sul valore peggiore (F-003).
- Hook pre-redeploy che esporta gli ultimi N giorni di log applicativi verso uno store esterno al ciclo di vita del container (F-027) — rilevante perché ha già impedito la verifica indipendente in almeno 9 sessioni forensi.
- Filtro `strategy_id` in `decay_monitor_task._fetch_actual_metrics` per non scorare S2 (morta) e per separare le metriche di S1 da S4 (F-004).

## 15. Ticket tecnici suggeriti

Nessun ticket nuovo proposto in questo ciclo (tutte le anomalie sono ricorrenze già trackate con ticket esistenti in ledger, salvo F-041 che non richiede un ticket di codice — è un errore di configurazione del prompt di questo stesso protocollo, corretto testualmente in §13).

## 16. Stato sistema

| Voce | Valore |
|---|---|
| Ollama (glm-5.2 + gpt-oss, hosted ollama.com) | Nessun outage totale rilevato: 100/164 (61%) ensemble dual-model completo, 64/164 (39%) fallback single-model distribuito su tutte le ore, `consecutive_fallback=0` a fine giornata. Ore di downtime totale stimate: **0** (degradazione parziale continua, non un'interruzione) |
| FinBERT fallback rate | 1/164 righe (0,6%) — solo il fallback di ultima istanza, non il fallback single-model LLM |
| Fallback LLM complessivo (single-model, esclude finbert) | 63/164 righe (38,4%) |
| Worker restart/redeploy events | **1**: `worker`, `api`, `worker-inference`, `beat` ricreati il 2026-08-19 08:20:07-11 UTC (redeploy, non riavvio host — `uptime -s` host invariato al 17/08). `postgres`/`redis` non toccati |
| Operator halt | Assente (`system:halted_by_operator` non impostato) |
| Modalità trading | `paper` confermato su tutti gli snapshot del giorno |
| Coppia modelli sentiment attiva | `glm52,gptoss` (confermato su Redis, coerente con CLAUDE.md) |
| Gate d'ingresso S4 | 0,30 (baseline, nessuna deroga ratchet attiva) |
