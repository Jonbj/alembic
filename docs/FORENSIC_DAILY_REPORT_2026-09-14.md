# Forensic Daily Report — 2026-09-14 (lunedì)

**Analista:** sessione forense automatica (read-only)
**Generato:** 2026-09-15
**Timezone operativo:** UTC. Confermato da `src/workers/celery_app.py` (`timezone = "UTC"`, `enable_utc`)
e da tutti i timestamp `timestamptz` a DB. RTH 2026-09-14 = **13:30–20:00 UTC** (EDT, DST attivo).
**Modalità broker:** **PAPER** — `ALPACA_BASE_URL=https://paper-api.alpaca.markets`,
`config/trading.yaml → execution.engine: portfolio`, `/portfolio/status` riporta
S1 `supervised_paper` e S4 `paper`, entrambe `live_authorized: false`.

---

## 1. Executive summary

La pipeline ha girato end-to-end senza interruzioni strutturali: 229 articoli ingeriti (206 Benzinga,
23 GDELT), 229 segnali scorati su 58 simboli, 24 cicli portfolio, 9 chiusure e 4 ingressi, tutti su
simboli in watchlist e tutti dentro RTH. Il P&L realizzato dichiarato è **−113,79 $** su 9 trade
chiusi; il conto paper ha fatto **−497,12 $ (−0,45 %)** contro SPY **−0,45 %** — giornata di beta,
non di difetto di segnale. Il difetto più grave è contabile: lo stop d_hard su **MU** (1 azione,
piazzato il 09-09) si è **riempito alle 13:32:07 a 908,56 $** e non è stato scritto in `trades` —
nessuna riga, nessuna decisione, nessun alert. Il realizzato vero della giornata è **≈ −240,64 $**,
cioè 126,85 $ peggiore di quanto qualunque consumatore a valle (ratchet loss-feedback, decay
monitor, dossier) creda. Secondo punto: **nessun alert ha raggiunto un essere umano** — 6 invii
Telegram su 6 respinti con 400, 10 CRITICAL del decay monitor solo su `log.critical`, 0 dispositivi
mobile registrati e 0 consegne. AMAT e WDC hanno violato d_hard 20 % in **tutti e 24** i cicli
senza che esistesse un ordine di stop (quantità < 1 azione, non frazionabile). Ollama non è mai
caduta del tutto: 20 timeout su 458 chiamate (4,4 %), ma il tasso di fallback sui segnali è
**31,0 %** (71/229). PANW, il mover della giornata (+13,09 %), è stato comprato alle 16:37 con il
**101,7 % del movimento già avvenuto**. La sanitizzazione non decodifica le entità HTML: il
**61,6 %** delle righe scorate arriva al modello con `&amp;` / `&#39;` dentro.

## 2. Verdict finale

> **ANOMALIE SIGNIFICATIVE** — il processo decisionale ha funzionato come progettato, ma la
> contabilità del P&L è dimostrabilmente sbagliata (fill di stop orfano, −126,85 $ non registrati)
> e l'intero strato di allerta è muto. Nessuna delle due cose è una taratura: sono difetti di
> correttezza che rendono sbagliata l'evidenza raccolta nelle prossime settimane.

---

## 3. Timeline del 2026-09-14 (tutti gli orari UTC)

| ora | componente | evento | esito | fonte |
|---|---|---|---|---|
| 03:19–12:52 | worker-inference | drenaggio backlog notturno coda news (queue_depth 359→392 alle 13:25) | ok | `worker-inference-2026-09-14.log`, `news_queue_census` |
| 04:00:00 | weight rebalancer | LOO ICIR settimanale: pesi invariati glm 0,70 / gpt-oss 0,30 (`max_delta` 4,3e-13); ICIR purificato gpt-oss **−0,022** | applicato | `weight_update_log` id 20 |
| 04:00:00 | TelegramNotifier | alert respinto **400 Bad Request** (1/6) | **fallito** | `worker-2026-09-14.log:1240` |
| 08:09:15 | worker-inference | SIGTERM → `WorkerLostError` job 30370; ready 08:09:24 | riavvio 1/4 | log:17676 |
| 10:16:52 | worker | riavvio 2/4 | ok | `worker-...log:3036` |
| **13:30:00** | **apertura RTH** | incidente mobile `pipeline:portfolio_cycle_late` **CRITICAL** aperto + `pipeline:signal_stale` WARNING | aperti, "recovered" 14:08 / 13:33 | `mobile_events` |
| **13:32:07** | **broker** | **fill stop d_hard MU 1 azione @ 908,56** (ordine `f7e44edd`, inviato 2026-09-09) | **filled, orfano** | `/api/orders`; nessuna riga in `trades` |
| 13:32:37 | ingest | prima riga Benzinga della giornata | ok | `news_log` |
| 13:48:26 | worker-inference | primo doppio timeout Ollama (90 s) → fallback FinBERT su JNJ | degradato | log:30098, `finbert_fallback_events` |
| 13:49:18 | LLM | MU **−0,405** (ensemble) | segnale | `sentiment_signals` 10669 |
| 13:54:09 | LLM | AZN **+0,396** (ensemble) | segnale | 10672 |
| **14:07:00** | **portfolio-cycle #1** | primo ciclo della seduta — **37 min dopo l'apertura, 2 cicli persi** | 5 ordini target | `portfolio_cycles` 1467 |
| 14:07:05 | #161 monitor | 12/45 posizioni non proteggibili (qty<1); AMAT −27,9 %, WDC −22,0 % | 3 alert Telegram → **400** | log:4094-4101 |
| 14:07:06 | esecuzione | **SELL MRVL** 0,5515 @221,558 (`sentiment_reversal` −0,390) → net **−27,11** | filled | `trades` 312 |
| 14:07:06 | esecuzione | **SELL MU** 0,4070 @915,626 (`sentiment_reversal` −0,405) → net **−49,53** | filled | `trades` 989 |
| 14:07:07 | esecuzione | **BUY AZN** 8,8657 @162,673 (score +0,396, peso 2 %) | filled | `trades` 999 |
| 14:22:05 | esecuzione | **SELL ORCL** 9,3725 @143,110 `below_entry_gate` (score −0,114) → net **−88,68** | filled | `trades` 997 |
| 14:22:05 | esecuzione | **SELL SPCX** 9,7251 @149,00 `below_entry_gate` (score **+0,183**) → net **+7,88** | filled | `trades` 995 |
| 14:22:06 | risk | stop protettivo AZN **8 su 8,8657 azioni** (parte intera) | poi canceled | `/api/orders` `a717fe6c` |
| 14:30:00 | loss-feedback | ratchet S4 congelato (EWMA R −1,03, P&L rolling −256,72) | alert → **400** | log:4255 |
| 14:37:04 | esecuzione | **SELL NOW** 10,7571 @138,58 `below_entry_gate` (score **+0,231**) → net **+51,06** | filled | `trades` 993 |
| 14:53:56 | LLM | MU ri-scorato **+0,347** (1 h dopo il reversal a −0,405) | segnale | 10732 |
| 15:02–15:53 | Ollama | finestra di degrado: 15 timeout; fallback 23/44 segnali nell'ora | degradato | log:31105-32015 |
| 15:07:04 | esecuzione | **BUY HOOD** 12,5771 @114,250 (score +0,325) | filled | `trades` 1000 |
| 15:07:03 | guard | **BUY MU bloccato** da *reversal cooldown* (1ª di 5) — riga `execution_decisions` = `BUY`, `order_id` NULL | bloccato | log:4539, ed 22482 |
| 15:22:04 | risk | stop protettivo HOOD **12 su 12,5771** | poi canceled | `60260205` |
| 15:37:05 | esecuzione | **SELL TSLA** 3,9400 @362,16 `fallback_filtered` → net **−10,45** | filled | `trades` 998 |
| 15:42:18 | breaker | breaker fallback scatta a count=3; **callback di alert muore** (`asyncio.run()` dentro event loop) | **alert perso** | log:31843 |
| 15:52:04 | esecuzione | **SELL AZN** 8,8657 @164,09 → net **+11,77** (`hold_minimum_expiry` in `trades`, `below_entry_gate` score +0,000 in `execution_decisions`) | filled | `trades` 999 |
| 16:34:59 | LLM | PANW **+0,405** (ensemble) | segnale | 10802 |
| 16:37:04 | esecuzione | **BUY PANW** 3,8762 @374,40 — **89° percentile** del range di seduta, **101,7 %** del movimento già avvenuto | filled | `trades` 1001, dossier `ingressi` |
| 16:52:04 | risk | stop protettivo PANW **3 su 3,8762** (77,4 % del nozionale) | **new** (ancora a mercato) | `29dcdf94` |
| 18:22:04 | esecuzione | **SELL HOOD** 12,5771 @113,94 `below_entry_gate` (+0,117) → net **−4,69** | filled | `trades` 1000 |
| 18:22:04 | guard | **BUY LLY bloccato** da P0-05 con sentiment **+0,416** (sopra gate), posizione 797 $ vs target 2 973 $ | bloccato | ed `SKIP_PYRAMIDING` |
| 18:30:00 | loss-feedback | ratchet S4 (3 perdite consecutive, P&L rolling −194,93) | alert → **400** | log:5960 |
| 19:06:24 | LLM | NFLX **+0,322** | segnale | 10857 |
| 19:07:16 | esecuzione | **BUY NFLX** 17,9503 @80,55 — 81° percentile, **117 %** del movimento già avvenuto | filled | `trades` 1002 |
| 19:22:22 | risk | stop protettivo NFLX **17 su 17,9503** | **new** | `5f284cf2` |
| 19:32:08 | LLM | BAC **−0,443** | segnale | 10871 |
| 19:37:07 | esecuzione | **SELL BAC** 11,4411 @59,21 (`sentiment_reversal`) → net **−4,03** | filled | `trades` 250 |
| 19:37 / 19:54 | resolver | OpenFIGI DNS fallita (HACK, GM): `Name or service not known` | degradato | log:42696, 43267 |
| 19:52:00 | portfolio-cycle #24 | ultimo ciclo (chiusura 20:00) | 4 ordini target | `portfolio_cycles` |
| 19:54:30 | ingest | ultima riga news della giornata | ok | `news_log` |
| 20:20:29 | worker | riavvio 3/4 | ok | log:6770 |
| 20:33:04 | mobile snapshot | lettura Alpaca fallita (DNS) → `pipeline:broker_stale` **CRITICAL**; task Celery comunque `succeeded` | recovered 20:34 | log, `mobile_events` |
| 21:00:00 | decay monitor | **10 alert CRITICAL** (S1 3, S2 4, S4 3) — Sharpe, IC, hit rate | **solo log** | log:21:00:00 |
| 22:20:10 | worker-inference | SIGTERM → `WorkerLostError` job 1429; riavvio 4/4 | job perso | log:49342 |
| 22:50:00 | mobile | `portfolio_cycle_session_grid` WARNING + `coverage:held_no_news_loss` PFE/SBUX — tutti "recovered" in **<1 s** | chiusi subito | `mobile_events` |
| 22:55:00 | stale-drop | Benzinga **430/883 (48,7 %)** droppati stale, `alert_required = true` | nessun alert consegnato | `stale_drop_metrics_daily` |
| 23:15:27 | ingest | ultimo aggiornamento `ingestion_stats_daily` | ok | DB |

---

## 4. News ingest

### Per fonte

| fonte | fetched | queued | in `news_log` | duplicates | scartati no-ticker | scartati stale | parse fail | p50 latenza pub→fetch | p90 | max |
|---|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 1 610 | 885 | **206** | **7 568** | 0 | 618 | 0 | 13,0 min | 48,7 min | 94 min |
| gdelt_gkg | 2 922 | 23 | **23** | 5 | **2 894 (99,0 %)** | 0 | 0 | 3,2 min | 37,3 min | 41 min |

- Copertura temporale righe: **13:32:37 → 19:54:30 UTC**. Nessuna riga pre-market né post-market:
  l'ingest è di fatto gated su RTH (nessuna riga fra 20:00 e 13:32 del giorno dopo).
- **Nessun timestamp futuro** (`published_at > fetched_at`: 0 righe), nessun `published_at` NULL,
  nessun titolo vuoto, nessun `body_full` vuoto, `discarded_reason` NULL su tutte le 229 righe.
- **Dedup:** 229 righe ↔ 137 `content_hash` distinti ↔ 138 URL distinti. Zero coppie
  (content_hash, ticker) ripetute → **nessun doppio conteggio dello stesso articolo sullo stesso
  ticker**. I 92 mapping extra sono fan-out multi-ticker, non duplicati di sindacazione.
- **Fan-out:** 106 articoli su 1 ticker, 32 su 2-10 ticker → **123/229 righe scorate (53,7 %)
  provengono da articoli multi-ticker**.
- **Estrazione ticker:** `source_metadata` 206, `org_lookup` 23. Nessun verdetto del resolver
  deterministico. Mappatura di rilevanza del dossier: ISSUER_SPECIFIC 105, **TAG_UNCONFIRMED 120**,
  FALSE_ENTITY_MATCH 4, content_empty 1.
- **Copertura watchlist:** 46/96 ticker con articolo *effective-timely* (**47,9 %**);
  **38 simboli con zero news**.
- **Nessun ticker fuori watchlist** né in `news_log` né in `sentiment_signals`.

### Ticker più rappresentati (righe scorate)

| ticker | righe | score max | score min |
|---|---|---|---|
| NVDA | 23 | +0,210 | −0,276 |
| INTC | 10 | +0,050 | −0,396 |
| PANW | 9 | **+0,560** | 0,000 |
| AMD | 9 | 0,000 | −0,276 |
| ORCL | 8 | +0,174 | −0,275 |
| MU | 7 | +0,347 | **−0,405** |
| MRVL | 7 | +0,068 | −0,390 |
| GOOGL | 7 | +0,065 | −0,270 |
| NOK | 7 | +0,090 | −0,252 |
| META | 6 | +0,420 | −0,212 |

### Top news per impatto sul segnale

| ora | ticker | score | modello | esito |
|---|---|---|---|---|
| 13:49 | MU | −0,405 | ensemble | **SELL** forzato (sentiment_reversal) |
| 13:54 | AZN | +0,396 | ensemble | **BUY** 14:07 |
| 14:03 | MRVL | −0,390 | ensemble | **SELL** forzato |
| 15:05 | HOOD | +0,325 | ensemble | **BUY** 15:07 |
| 16:35 | PANW | +0,405 | ensemble | **BUY** 16:37 |
| 19:06 | NFLX | +0,322 | ensemble | **BUY** 19:07 |
| 19:32 | BAC | −0,443 | ensemble | **SELL** forzato |
| 15:42 | AMAT | −0,691 | **finbert** (fallback) | `SKIP_FALLBACK` |
| 19:37 | PANW | **+0,560** | **single:gpt-oss** (fallback) | escluso dal ranking |

### Problemi trovati in ingest
1. `duplicates` (7 568) supera di 4,7× `fetched` (1 610) — contatore additivo cross-run mai
   verificato indipendentemente → **[DAY-011]**.
2. **48,7 % della coda Benzinga scartata per staleness** (430/883), `alert_required = true` e
   nessun alert consegnato → **[DAY-019]**.
3. GDELT scarta il 99 % di quanto scarica per assenza di ticker: la fonte produce 23 righe utili su
   2 922 chiamate.
4. Entità HTML non decodificate su 141/229 righe → **[DAY-007]**.

**Confidenza dell'analisi ingest: Alta** (tutti i numeri da `news_log` / `ingestion_stats_daily` /
`stale_drop_metrics_daily`, nessuna stima).

---

## 5. Performance modelli LLM

| modello | chiamate | risposte persistite | timeout Ollama | tasso errore | polarity media | confidence media | `eligible=false` |
|---|---|---|---|---|---|---|---|
| `glm-5.2:cloud` | 229 | 218 | **11** | 4,8 % | −0,0352 | 0,3895 | 121/218 (55,5 %) |
| `gpt-oss:20b-cloud` | 229 | 220 | **9** | 3,9 % | −0,0860 | 0,4751 | 123/220 (55,9 %) |
| `finbert` (fallback) | 13 | 13 | — | 0 | −0,0727 (score) | 0,2442 | n/a |
| `kimi-k5:cloud` (regime) | ≥1 | — | 1 | — | — | — | n/a |

**Composizione dei 229 segnali del giorno**

| percorso | n | quota |
|---|---|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 158 | 69,0 % |
| `single:gpt-oss:20b-cloud` (glm caduto) | 50 | 21,8 % |
| `single:glm-5.2:cloud` (gpt-oss caduto) | 8 | 3,5 % |
| `finbert` | 13 | 5,7 % |
| **fallback totale** | **71** | **31,0 %** |

**Fallback per ora** (fallback / segnali): 13h 7/21 · 14h 11/60 · 15h **23/44 (52,3 %)** ·
16h 9/24 · 17h 3/23 · 18h 3/23 · 19h 15/34.

**Latenza:** non esiste strumentazione per-chiamata. Proxy disponibile: 65 cicli d'ensemble,
durata media **204,3 s** di parete per ciclo multi-articolo, tetto di timeout 90 s per modello.
*Dato mancante — vedi §12.*

**Distribuzione score (229 segnali):** media −0,034, |score| ≥ 0,30 su 13 segnali (5,7 %),
estremi AMAT −0,691 (FinBERT) e PANW +0,560 (single gpt-oss).

**Disaccordo fra modelli:** `ensemble_std` medio 0,0738. Massimo osservato su segnale non-fallback:
MRVL 10683 `std` 0,212 (comunque tradato), NOK 10735 `std` **0,354** con **entrambi** i contributori
`eligible=false`.

### Verifica funzionale

| domanda | esito |
|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Il parsing JSON è validato; enum (`directness`, `event_type`) e normalizzazione Unicode no (F-055). Un segnale con entrambi i contributori `eligible=false` viene comunque persistito come `ensemble:` con score calcolato → **[DAY-020]**. |
| L'ensemble gestisce la varianza alta? | **No come gate.** `ensemble_std` è calcolato e persistito ma non è mai una condizione d'ingresso; la divergenza innesca solo il fallback FinBERT (6 casi oggi). |
| Le news duplicate pesano più volte? | **No.** Zero coppie (content_hash, ticker) ripetute. Il fan-out multi-ticker (53,7 % delle righe) è per costruzione, non un duplicato. |
| La stessa news può generare segnali multipli? | **No per ticker** (vincolo unico `(symbol, generated_at)`, 229 news ↔ 229 segnali). **Sì per ticker diversi** via fan-out. |
| Confidence bassa riduce il peso? | **Sì:** `score = polarity × confidence` verificata su tutte le righe (es. NOK −0,35×0,30 → −0,105). Ma **solo in ingresso**: nessuna soglia di confidence protegge l'uscita. |
| I modelli sono chiamati offline/background? | **Sì.** Tutte le chiamate su `worker-inference` (coda `inference`, concurrency 1); `portfolio_scheduler` legge solo `sentiment_signals` da DB. Nessuna chiamata LLM dentro il ciclo d'esecuzione. |
| Rischio che un'allucinazione entri in decisione? | **Sì, mitigato ma non chiuso.** Nessun agente supervisore; il gate è puramente numerico (score ≥ 0,30). Il `reasoning` del modello è copiato verbatim in `execution_decisions.reason` senza verifica contro la fonte. |

---

## 6. Segnali finali e decisioni

### Distribuzione decisioni (2 503 righe)

| decisione | n | note |
|---|---|---|
| `OBSERVE_LATE_ENTRY` | 1 426 | strumentazione ombra |
| `SKIP_THRESHOLD` | 729 | 60 righe con \|score\| ≥ 0,25 (vicino al gate) |
| `SHADOW_LATE_ENTRY` | 300 | strumentazione ombra |
| `SKIP_FALLBACK` | 23 | segnali fallback esclusi dal ranking per design |
| **SELL** | **9** | 9/9 con `order_id` |
| **BUY** | **9** | **solo 4 con `order_id`** |
| `SKIP_PYRAMIDING` | 6 | a fronte di **51** blocchi loggati |
| `SKIP_STALE` | 1 | SOXX |

### Segnali che hanno superato il gate 0,30

| ticker | score | ora | esito | causa |
|---|---|---|---|---|
| AZN | +0,396 | 13:54 | **BUY** 14:07 | — |
| HOOD | +0,325 | 15:05 | **BUY** 15:07 | — |
| PANW | +0,405 | 16:35 | **BUY** 16:37 | — |
| NFLX | +0,322 | 19:06 | **BUY** 19:07 | — |
| MU | +0,347 | 14:53 | **nessun ordine** | reversal cooldown (5 cicli) |
| LLY | +0,416 | 18:19 | **nessun ordine** | P0-05 anti-pyramiding |
| MRK | +0,307 | 19:52 | **nessun ordine** | P0-05 anti-pyramiding |
| PANW | +0,560 | 19:37 | **nessun ordine** | fallback single-model, escluso dal ranking |
| MU/MRVL/BAC | −0,405 / −0,390 / −0,443 | — | **SELL forzati** | `sentiment_reversal` (soglia −0,35) |

Tutti i BUY sono **S4 news-driven** con `regime_mult = 0,70` (regime SIDEWAYS) e peso target 2,0 %
(`score` in `execution_decisions` = 0,02 = il peso, non il sentiment; il sentiment è in
`signal_score`). Combiner portfolio applicato: `strategies_run = ["S1","S4"]` su tutti i 24 cicli,
`constraints_fired = []` (nessun cap settoriale o di esposizione ha morso). Nessun circuit breaker
attivo. Distinzione paper/live esplicita e coerente.

### Ordini generati ed eseguiti

| ora invio | strat | ticker | azione | qty | prezzo fill | stato | decisione | causale | segnale | anomalia |
|---|---|---|---|---|---|---|---|---|---|---|
| (09-09) | — | MU | **sell stop 1 sh** | 1 | **908,56** | **filled 13:32:07** | — | d_hard 12 % | — | **orfano: nessun trade, nessuna decisione** |
| 14:07:05 | S4 | AZN | BUY | 8,8657 | 162,673 | filled | 22060 | sentiment +0,396 | 10672 | — |
| 14:07:06 | S1 | MRVL | SELL | 0,5515 | 221,558 | filled | 2810 | sentiment_reversal | 10683 | leg residua di uscita parziale |
| 14:07:06 | S4 | MU | SELL | 0,4070 | 915,626 | filled | 19957 | sentiment_reversal | 10669 | `quantity_remaining = 1` su trade chiuso |
| 14:22:05 | S4 | ORCL | SELL | 9,3725 | 143,110 | filled | 21833 | below_entry_gate (−0,114) | — | `signal_id` NULL |
| 14:22:05 | S4 | SPCX | SELL | 9,7251 | 149,00 | filled | 21614 | below_entry_gate (**+0,183**) | — | SELL con sentiment positivo |
| 14:22:06 | risk | AZN | sell stop | 8 | — | **canceled** | — | stop protettivo | — | copre 90,2 % del nozionale |
| 14:37:04 | S4 | NOW | SELL | 10,7571 | 138,58 | filled | 21449 | below_entry_gate (**+0,231**) | — | SELL con sentiment positivo |
| 15:07:04 | S4 | HOOD | BUY | 12,5771 | 114,250 | filled | 22483 | sentiment +0,325 | 10743 | — |
| 15:22:04 | risk | HOOD | sell stop | 12 | — | **canceled** | — | stop protettivo | — | copre 95,4 % |
| 15:37:05 | S4 | TSLA | SELL | 3,9400 | 362,16 | filled | 21961 | fallback_filtered | — | `signal_id` NULL |
| 15:52:04 | S4 | AZN | SELL | 8,8657 | 164,09 | filled | 22060 | below_entry_gate (+0,000) | — | segnale forte sovrascritto da uno a 0 |
| 16:37:04 | S4 | PANW | BUY | 3,8762 | 374,40 | filled | 23118 | sentiment +0,405 | 10802 | ingresso a 89° percentile |
| 16:52:04 | risk | PANW | sell stop | 3 | — | **new** | — | stop protettivo | — | copre **77,4 %** |
| 18:22:04 | S4 | HOOD | SELL | 12,5771 | 113,94 | filled | 22483 | below_entry_gate (+0,117) | — | — |
| 19:07:16 | S4 | NFLX | BUY | 17,9503 | 80,55 | filled | 24149 | sentiment +0,322 | 10857 | ingresso a 81° percentile |
| 19:22:22 | risk | NFLX | sell stop | 17 | — | **new** | — | stop protettivo | — | copre 94,7 % |
| 19:37:07 | S1 | BAC | SELL | 11,4411 | 59,21 | filled | 24430 | sentiment_reversal | 10871 | — |
| ×5 | S4 | MU | **BUY** | — | — | **nessun ordine** | 22482/22593/22701/22808/22913 | reversal cooldown | 10732 | riga `BUY` senza causa reale |

`portfolio_cycles.orders_count` somma **84** ordini sui 24 cicli, contro **13 ordini realmente
inviati**: il contatore conta i pesi target, non le submission (F-014, confermato anche oggi —
DELL compare come `BUY` in tutti e 24 i cicli senza produrre un solo ordine).

---

## 7. Rendimento e P&L

### Realizzato — 9 trade chiusi il 2026-09-14

| trade | ticker | strat | aperto il | entry | exit | qty | gross | costi | **net** |
|---|---|---|---|---|---|---|---|---|---|
| 989 | MU | S4 | 09-09 | 1 035,406 | 915,626 | 0,4070 | −48,75 | 0,78 | **−49,53** |
| 312 | MRVL | S1 | 07-14 | 221,914 | 204,557 | 1,5515 | −26,93 | 0,18 | **−27,11** |
| 995 | SPCX | S4 | 09-11 | 148,034 | 149,00 | 9,7251 | +9,40 | 1,51 | **+7,88** |
| 997 | ORCL | S4 | 09-11 | 152,487 | 143,110 | 9,3725 | −87,89 | 0,78 | **−88,68** |
| 993 | NOW | S4 | 09-11 | 133,76 | 138,58 | 10,7571 | +51,85 | 0,79 | **+51,06** |
| 998 | TSLA | S4 | 09-11 | 364,74 | 362,16 | 3,9400 | −10,17 | 0,29 | **−10,45** |
| 999 | AZN | S4 | **09-14** | 162,673 | 164,09 | 8,8657 | +12,56 | 0,79 | **+11,77** |
| 1000 | HOOD | S4 | **09-14** | 114,250 | 113,94 | 12,5771 | −3,90 | 0,79 | **−4,69** |
| 250 | BAC | S1 | 07-10 | 59,53 | 59,21 | 11,4411 | −3,66 | 0,37 | **−4,03** |
| | | | | | | | **−107,49** | **6,30** | **−113,79** |

**Non registrato in `trades`:** fill dello stop d_hard MU, 1 azione @ 908,56 contro entry 1 035,406
→ **−126,85 $ lordi**. **Realizzato vero della giornata ≈ −240,64 $.**

### Per strategia (solo righe con `stop_strategy` valorizzato)

| strategia | trade chiusi | net |
|---|---|---|
| S4 | 6 | **−92,64** |
| S1 | 2 (MRVL, BAC) | **−31,15** |
| (leg orfana MU) | 1 | **−126,85** (non attribuita) |

### Posizioni aperte il 2026-09-14 (non realizzato a fine seduta)

| ticker | qty | entry | MTM fine seduta (dossier) | non realizzato a chiusura (`/api/positions`) |
|---|---|---|---|---|
| PANW | 3,8762 | 374,40 | **−1,78** | −27,52 |
| NFLX | 17,9503 | 80,55 | **−4,13** | −19,39 |

### Conto (Alpaca paper)

| metrica | valore |
|---|---|
| equity 2026-09-11 | 109 742,28 |
| **equity 2026-09-14** | **109 245,16** |
| **P&L di giornata** | **−497,12 (−0,45 %)** |
| SPY | **−0,45 %** |
| valore di mercato posizioni | 31 045,05 (40 posizioni) |
| non realizzato totale | +840,05 |

Il delta fra −497,12 (conto, mark-to-market su tutto il libro) e −113,79 (realizzato sui 9 trade
chiusi) è il non realizzato delle 38 posizioni preesistenti: **non sono la stessa grandezza** e non
vanno confuse. La perdita di giornata è spiegata dal beta (book −0,45 % vs SPY −0,45 %), non da
errori di segnale.

**Slippage: non misurabile.** `trades.slippage_est` è identico a `cost_usd` su tutte e 4 le righe
nuove → è il costo modellato, non lo scostamento fra prezzo atteso e prezzo eseguito
(**[DAY-024]**). Non esiste da nessuna parte il prezzo di riferimento al momento della decisione
confrontabile col fill.

**Commissioni:** 0 (Alpaca paper). I 6,30 $ di "costi" sono il modello interno
`TradeCostCalculator` (spread + impatto + regolatori), non addebiti reali.

---

## 8. Analisi correttezza buy/sell

> **Avvertenza #184.** Le righe `execution_decisions.exit_mechanism` del 2026-09-14 contengono
> `below_entry_gate` e `fallback_filtered` — etichette **osservate** post-fix, derivate dalla causale
> effettiva e non dall'età dell'ultimo segnale. Nessuna riga `expired`/`whipsaw` dedotta per età
> compare in giornata, quindi i conteggi di questa sezione **non** sono stime per orologio. Le righe
> storiche pre-fix restano non confrontabili.

| controllo | esito | evidenza |
|---|---|---|
| BUY solo quando consentito | ✅ | 4/4 BUY con score ≥ 0,322 > gate 0,30, `ema_pass = true`, entro RTH, simbolo in watchlist, peso 2 % coerente col combiner |
| SELL/exit generati correttamente | ⚠️ | 9/9 eseguiti, ma 2 su sentiment **positivo** (NOW +0,231, SPCX +0,183) perché il gate d'uscita è 0 e non c'è banda → **[DAY-009]** |
| Stop-loss rispettati | ❌ | `stop_loss: 0.0` (protettivo disabilitato per decisione paper). Il d_hard 12-20 % è un vero ordine broker: ha funzionato su MU ma **non esiste** sulle posizioni < 1 azione, e AMAT/WDC hanno violato la soglia in 24/24 cicli → **[DAY-002]** |
| Signal flip rispettato | ✅ | 3 `sentiment_reversal` a soglia −0,35 (MU −0,405, MRVL −0,390, BAC −0,443), tutti eseguiti nel ciclo stesso |
| Max holding days rispettato | ✅ | nessuna posizione S4 oltre `max_signal_age` senza uscita; 8-11 segnali stale droppati per ciclo |
| Rebalance band rispettata | ⚠️ | `hold_minimum_minutes = 90` rispettato (AZN 105 min, HOOD 195 min); `exit_persistence_cycles = 2` rispettato. Ma non c'è banda fra gate d'ingresso 0,30 e gate d'uscita 0 |
| Ordini duplicati | ✅ | nessuna coppia (simbolo, lato) ripetuta nello stesso minuto né nello stesso ciclo |
| Ordini contrari ravvicinati | ⚠️ | MU: SELL 14:07 → 5 decisioni BUY 15:07-16:07. Nessun ordine emesso (reversal cooldown) → comportamento **corretto**, audit trail **sbagliato** → **[DAY-005]** |
| Roundtrip < 30 min | ✅ | nessuno. Roundtrip minimo AZN 105 min |
| Pyramiding (> 3 BUY senza SELL) | ✅ | guard P0-05 attivo: 51 blocchi loggati, 0 pyramiding eseguito |
| Ordini su ticker non consentiti | ✅ | 0 simboli fuori watchlist in news, segnali e ordini |
| Ordini fuori orario | ✅ | tutti i 14 fill fra 13:32:07 e 19:37:08 UTC, dentro RTH |
| Trade su dati stale | ✅ | 1 `SKIP_STALE` (SOXX); S4 ha droppato 8-11 segnali > 4 h per ciclo |
| Trade su output LLM non valido | ✅ | 23 `SKIP_FALLBACK`: i segnali fallback sono esclusi dal ranking d'ingresso |
| Circuit breaker | ✅ | mai attivo (`constraints_fired = []` su 24 cicli) |
| Strategia disabilitata | ✅ | S1 e S4 `enabled: true`, `approved: true`, `live_authorized: false` |
| Paper/live coerente | ✅ | paper end-to-end |
| Idempotenza retry Celery | ⚠️ | 2 `WorkerLostError` (SIGTERM 08:09 e 22:20) hanno perso job in volo; 4 restart con `(recovery)` ri-processano messaggi non-ack → **[DAY-025]** |
| Riconciliazione ordini/fill/posizioni | ⚠️ | **simboli**: 40/40 allineati fra `/api/positions` e `trades WHERE exit_time IS NULL`. **Quantità**: MU chiuso con `quantity_remaining = 1` e leg di stop mai contabilizzata → **[DAY-001]** |

---

## 9. Anomalie trovate

### [DAY-001] Fill dello stop d_hard su MU orfano: −126,85 $ mai scritti in `trades`

* Tipo: Bug
* Area: PnL / Broker
* Evidenza:
  * file/log/tabella: `/api/orders` (`f7e44edd-686c-44e7-b58a-70c2169aaede`), `trades` id 989, `/api/performance/daily`
  * timestamp: submitted 2026-09-09T14:52:06Z, **filled 2026-09-14T13:32:07Z**
  * snippet/query:
    ```sql
    SELECT id,symbol,qty,quantity_remaining,exit_order_ids,gross_pnl,net_pnl FROM trades WHERE id=989;
    -- qty 0.407003629 | quantity_remaining 1 | exit_order_ids {588ba012...} | net_pnl -49.53
    -- entry_notional 1456.83 / entry_price 1035.406 = 1.4070 azioni comprate
    ```
* Descrizione: la posizione MU era 1,4070 azioni. Lo stop broker d_hard (1 azione, la sola parte
  intera) si è riempito all'apertura del 09-14 a 908,56. `trades.qty` è stata decrementata a 0,4070
  ma **il P&L di quella leg non è stato scritto da nessuna parte**: l'ordine non ha `trade_id`,
  `quantity_remaining` è rimasta a 1 su un trade già chiuso, e `exit_order_ids` contiene solo la
  seconda leg. Il realizzato dichiarato della giornata (−113,79 $) omette −126,85 $.
* Impatto: il P&L realizzato pubblicato è sbagliato del **112 %**. Consumatori a valle contaminati:
  ratchet loss-feedback (che ha già deciso due volte in giornata su `rolling P&L`), decay monitor,
  dossier alpha-miss, `/api/performance/daily`. La serie di evidenza delle prossime settimane
  eredita l'errore.
* Severità: **Critical**
* Confidenza: **High** (aritmetica su righe di DB e ordini broker)
* Azione consigliata: ticket di correttezza — ogni fill del broker con `symbol` in posizione deve
  essere riconciliato contro `trades` e, se non attribuibile, scritto come uscita parziale con il
  proprio P&L; `quantity_remaining` va portata a 0 alla chiusura.
* Test/monitor consigliato: job di riconciliazione giornaliero
  `Σ(fill_qty × fill_price) per simbolo == Σ(trades leg)`; alert su qualunque ordine `filled` senza
  `trade_id`.

### [DAY-002] d_hard violato in 24/24 cicli su AMAT e WDC senza alcun ordine di stop a mercato

* Tipo: Rischio
* Area: Risk
* Evidenza:
  * file/log/tabella: `stop_shadow_log`, `worker-2026-09-14.log:4094-4101`
  * timestamp: 14:07:03 → 19:52:30 UTC (ogni ciclo)
  * snippet/query:
    ```sql
    SELECT count(*) FILTER (WHERE d_hard_breached) FROM stop_shadow_log
    WHERE cycle_ts >= '2026-09-14' AND cycle_ts < '2026-09-15';  -- 48 (AMAT 24 + WDC 24)
    ```
    `#161: 12/45 held positions are unprotectable (qty < 1): [AMAT, AMD, ASML, CAT, DELL, LLY, MRVL, MU, NOK, SPY, UNH, WDC]`
* Descrizione: `fractional_stop_orders` salta la creazione dello stop quando la parte intera è 0
  (`skip_no_whole_share`). AMAT (0,8571 sh), WDC (0,3347 sh) e NOK (0,5640 sh) non hanno mai avuto
  un ordine broker. `stop_shadow_log` registra la violazione di d_hard (20 %) a ogni ciclo e nessun
  meccanismo la converte in un'uscita. Sulle posizioni con parte intera lo stop copre comunque solo
  quella: PANW 3/3,8762 = **77,4 %** del nozionale.
* Impatto: AMAT ha chiuso a −28,4 %, WDC a −21,8 %, NOK a −17,1 %, tutte scoperte per l'intera
  seduta. Perdita subita in giornata su queste tre posizioni ≈ **35,9 $** (AMAT −28,2, WDC −6,8,
  NOK −0,9), ma l'esposizione strutturale è l'intero nozionale sub-1-azione.
* Severità: **High**
* Confidenza: **High** (misura) per la violazione; **Low** per la cifra controfattuale
* Azione consigliata: ticket — quando la parte intera è 0 e d_hard è violato, il ciclo portfolio
  deve emettere un market sell frazionario invece di limitarsi a loggare.
* Test/monitor consigliato: invariante `d_hard_breached == true` per N cicli consecutivi ⇒ o esiste
  un ordine di uscita, o scatta un alert consegnato.

### [DAY-003] Nessun alert della giornata ha raggiunto un essere umano

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-2026-09-14.log` (6 × `400 Bad Request`), `mobile_notification_deliveries`, `monitor_devices`
  * timestamp: 04:00:00, 14:07:05, 14:07:06, 14:30:00, 14:37:04, 18:30:00
  * snippet/query:
    ```
    TelegramNotifier: Failed to send alert: Client error '400 Bad Request' for url 'https://api.telegram.org/bot.../sendMessage'
    SELECT count(*) FROM mobile_notification_deliveries;  -- 0
    SELECT count(*) FROM monitor_devices;                 -- 0
    ```
* Descrizione: due canali, entrambi muti. Telegram ha respinto **6 invii su 6** con 400 (alert #161
  posizioni scoperte, ratchet loss-feedback S4 ×2, alert notturno). Il canale mobile scrive
  `mobile_events` (6 incidenti in giornata, 2 CRITICAL) ma ha 0 dispositivi registrati e 0 consegne
  da sempre. In più i 10 CRITICAL del decay monitor delle 21:00 finiscono solo su `log.critical`.
* Impatto: il 2026-09-14 il sistema ha rilevato correttamente posizioni scoperte al −28 %, un
  breaker di fallback, un broker irraggiungibile e un decadimento CRITICAL su tre strategie, e
  **nessuna di queste informazioni è uscita dai log**. L'osservabilità operativa è nulla.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket — riparare il payload Telegram lato Python (il 400 è quasi certamente
  parse-mode/escape, stesso difetto già corretto lato shell con #591 ma non nel `TelegramNotifier`);
  dare un canale agli alert del decay monitor.
* Test/monitor consigliato: test d'integrazione che invii ogni template di alert a un endpoint
  Telegram finto e fallisca su HTTP ≥ 400; metrica giornaliera `alert_emessi` vs `alert_consegnati`.

### [DAY-004] Il bot token Telegram compare in chiaro nei log a livello INFO

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `logs/containers/worker-2026-09-14.log`
  * timestamp: 04:00:00 e altre 5 occorrenze
  * snippet: `HTTP Request: POST https://api.telegram.org/bot8611445937:AAH3WL4LY...`
* Descrizione: `httpx` logga l'URL completo, che contiene il bot token. I log sono persistiti su
  host in chiaro.
* Impatto: chiunque legga i log può assumere il controllo del bot di alerting.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ruotare il token e silenziare/redigere il logger `httpx` per il dominio
  `api.telegram.org`.
* Test/monitor consigliato: gate CI che cerchi pattern `bot\d+:[A-Za-z0-9_-]{30,}` nei log campione.

### [DAY-005] Cinque decisioni `BUY` su MU persistite senza ordine e senza la causa reale del blocco

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` id 22482, 22593, 22701, 22808, 22913; `worker-2026-09-14.log:4539,4647,4756,4862,4970`
  * timestamp: 15:07, 15:22, 15:37, 15:52, 16:07 UTC
  * snippet/query:
    ```sql
    SELECT id,symbol,decision,order_id,left(reason,60) FROM execution_decisions
    WHERE tick_time::date='2026-09-14' AND decision='BUY' AND order_id IS NULL;
    -- 5 righe MU, reason = "S4 news-driven: sentiment +0.347 (ensemble...)"
    ```
    Log: `Reversal cooldown: skipping BUY for MU — force-sold on sentiment reversal`
* Descrizione: il cooldown post-reversal ha correttamente impedito il rientro su MU (venduto alle
  14:07 a −0,405, ri-scorato +0,347 alle 14:53). Ma la riga persistita dice `decision = 'BUY'` con
  `order_id` NULL e `reason` che riporta la motivazione d'acquisto, non il blocco. Dal DB un BUY
  bloccato da guard è indistinguibile da un fallimento di submission.
* Impatto: qualunque analisi che conti i BUY da `execution_decisions` sovrastima del 125 % (9 righe
  vs 4 ordini). Il comportamento di trading è corretto; l'audit trail no.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — codice decisione dedicato (`SKIP_REVERSAL_COOLDOWN`) e `reason` che
  riporti il guard che ha morso.
* Test/monitor consigliato: invariante `decision IN ('BUY','SELL') ⇒ order_id IS NOT NULL`.

### [DAY-006] P0-05 blocca 51 ingressi ma ne persiste 6, fra cui LLY con sentiment +0,416 sopra gate

* Tipo: Bug
* Area: Orders
* Evidenza:
  * file/log/tabella: `worker-2026-09-14.log` (24 DELL, 13 BAC, 7 LLY, 5 TSLA, 1 NOW, 1 MRK), `execution_decisions` `SKIP_PYRAMIDING`
  * timestamp: 14:07:03 → 19:52:30
  * snippet: `P0-05 anti-pyramiding: gia' a libro dal 2026-07-15, sentiment +0.416, peso target 2.7%, target $2973, posizione $797`
* Descrizione: il guard ha sparato **51 volte** in giornata e ha lasciato **6** righe
  `SKIP_PYRAMIDING` (una per simbolo). Il caso LLY è sostanziale, non solo di tracciamento: segnale
  +0,416 (il più forte non tradato della seduta), posizione a 797 $ contro un target di 2 973 $ —
  il rabbocco di ~2 176 $ è stato bloccato perché il simbolo era già a libro da S1.
* Impatto: sui simboli condivisi S1/S4, S4 resta strutturalmente sotto-esposto e il segnale forte
  non si traduce in esposizione. Limite superiore del mancato guadagno su LLY (+2,02 % di seduta):
  ≈ **44 $**.
* Severità: **Medium**
* Confidenza: **High** per il blocco; **Low** per la cifra (congetturale, movimento di giornata
  intera usato come limite superiore)
* Azione consigliata: ticket di osservabilità — persistere una riga per ogni firing, non una per
  simbolo. La decisione se il guard debba distinguere "rabbocco al target" da "pyramiding" è
  taratura, **fuori** dalla finestra di osservazione.
* Test/monitor consigliato: contatore giornaliero `guard_firings` vs `righe_persistite`, allineati.

### [DAY-007] `sanitize_text` non decodifica le entità HTML: il 61,6 % delle righe scorate arriva al modello con `&amp;` / `&#39;`

* Tipo: Bug
* Area: News / LLM
* Evidenza:
  * file/log/tabella: `src/text/sanitizer.py` (nessun `html.unescape`), `finbert_fallback_events.finbert_input`, `news_log`
  * timestamp: tutta la giornata
  * snippet/query:
    ```sql
    SELECT count(*) FILTER (WHERE title ~ '&(amp|#39|quot|lt|gt);' OR body_full ~ '&(amp|#39|quot|lt|gt);'), count(*)
    FROM news_log WHERE fetched_at::date='2026-09-14';   -- 141 / 229 (61,6 %)
    -- finbert_input: "Salesforce&#39;s AI Business Is Booming, Why Isn&#39;t CRM S..."
    --                "Johnson &amp; Johnson's RYBREVANT Combination Extends Surviv..."
    ```
* Descrizione: `sanitize_text` normalizza NFKC, rimuove zero-width, BiDi ed emoji, ma non fa mai
  `html.unescape`. Il connettore Benzinga (`src/connectors/alpaca_news.py:150-164`) rimuove i tag
  HTML con una regex e lascia le entità. Risultato: 141 righe su 229 (133 su 206 Benzinga)
  raggiungono sia FinBERT sia i due modelli Ollama con le entità intatte.
* Impatto: degrado della NER sui possessivi e sui nomi con `&` proprio dove la risoluzione del
  ticker conta (`Johnson & Johnson` → `Johnson &amp; Johnson`); su FinBERT il troncamento a 512
  caratteri viene consumato da rumore (`&#39;` = 5 caratteri per un apostrofo). Non quantificabile
  in dollari sulla singola giornata.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — `html.unescape` in testa a `sanitize_text`, prima
  della normalizzazione NFKC. È una correzione di correttezza dell'input, non una taratura.
* Test/monitor consigliato: test unitario su `sanitize_text("A &amp; B&#39;s")`; check giornaliero
  che `news_log` non contenga entità HTML nel testo che va al modello.

### [DAY-008] AZN: segnale +0,396 sovrascritto da un segnale +0,000 generato 25 minuti dopo, posizione chiusa

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `sentiment_signals` (AZN: 10672 = +0,396 alle 13:54, secondo segnale = 0,000 alle 14:19), `execution_decisions` 22809
  * timestamp: ingresso 14:07, uscita 15:52
  * snippet: `[below_entry_gate] S4 signal fell below the active feedback entry threshold (age=1.5h ..., score=+0.000): weight 0.0%, position closed.`
* Descrizione: S4 usa solo il segnale **più recente** per simbolo. Un secondo articolo su AZN,
  scorato 0,000, ha rimpiazzato il +0,396 che aveva motivato l'ingresso; alla scadenza del
  `hold_minimum` di 90 minuti la posizione è stata chiusa per "sotto il gate d'ingresso" pur non
  esistendo alcun segnale contrario.
* Impatto: oggi benigno — AZN è sceso dopo l'uscita, quindi chiudere ha **risparmiato 2,75 $**
  (`drift_post_uscita` −2,748 nel dossier). Il meccanismo resta sbagliato: la forza del segnale
  d'ingresso è cancellata da un articolo irrilevante.
* Severità: **Medium**
* Confidenza: **High** (misura) sul meccanismo; **High** sul controfattuale (dossier, EOD)
* Azione consigliata: ticket — la selezione del segnale per-simbolo deve pesare forza e recency,
  non solo recency. La scelta della regola di aggregazione è taratura: il ticket copre solo il fatto
  che un segnale a 0,000 possa cancellare un +0,396.
* Test/monitor consigliato: log di ogni sostituzione di segnale con `Δscore > 0,20` e contatore
  giornaliero delle uscite `below_entry_gate` causate da sostituzione.

### [DAY-009] Due SELL con sentiment positivo: NOW a +0,231 e SPCX a +0,183

* Tipo: Bug
* Area: Signal / Orders
* Evidenza:
  * file/log/tabella: `execution_decisions` 22272 (NOW), 22168 (SPCX)
  * timestamp: 14:22:00 (SPCX), 14:37:00 (NOW)
  * snippet: `[below_entry_gate] S4 signal fell below the active feedback entry threshold (age=0.3h ..., score=+0.231): weight 0.0%, position closed.`
* Descrizione: il gate d'ingresso è 0,30, quello d'uscita è 0. Un segnale **positivo** ma sotto il
  gate d'ingresso porta il peso target a 0 e chiude la posizione. Nessuna banda d'isteresi, nessuna
  soglia di confidence sull'uscita.
* Impatto: NOW ha continuato a salire (+7,41 % di seduta): `drift_post_uscita` **+40,55 $** — uscire
  è costato quella cifra. SPCX è sceso: uscire ha risparmiato 8,27 $. **Netto ≈ +32,28 $ di costo.**
* Severità: **High**
* Confidenza: **High** per l'evento; **Medium** per il costo (controfattuale corto, mark EOD)
* Azione consigliata: il valore della banda è taratura **congelata**. Il ticket ammissibile è
  strumentale: distinguere in `exit_mechanism` "segnale contrario" da "segnale concorde ma sotto il
  gate d'ingresso", perché oggi le due cose sono la stessa etichetta.
* Test/monitor consigliato: contatore giornaliero `SELL con signal_score > 0` e P&L di drift
  post-uscita associato.

### [DAY-010] Ingressi tardivi: PANW comprato con il 101,7 % del movimento già avvenuto

* Tipo: Anomalia
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `docs/evidence/dossier/2026-09-14.json → ingressi`
  * timestamp: PANW 16:37, NFLX 19:07
  * snippet:
    ```json
    {"symbol":"PANW","ora_utc":"16:37","entry_percentile":0.8905,
     "quota_movimento_precedente_al_segnale":1.0168,"vs_apertura":106.42,"mtm_eod":-1.78}
    {"symbol":"NFLX","ora_utc":"19:07","entry_percentile":0.8142,
     "quota_movimento_precedente_al_segnale":1.1704,"vs_apertura":24.23}
    ```
* Descrizione: PANW è stato **il mover della giornata (+13,09 %)** e il sistema l'ha preso: il
  segnale è arrivato alle 16:34:59 e l'ordine alle 16:37, ma all'89° percentile del range di seduta,
  con il movimento interamente consumato. NFLX idem (81° percentile, 117 %). La latenza di ingest
  Benzinga (p50 13 min, p90 48,7 min) più il ciclo a 15 minuti spiegano il ritardo.
* Impatto: comprare all'apertura invece che al segnale avrebbe reso **+106,42 $** su PANW e
  **+24,23 $** su NFLX → **130,65 $** lasciati sul tavolo. Il MTM di fine seduta dei due ingressi è
  −1,78 e −4,13: il segnale era giusto, il prezzo no.
* Severità: **High**
* Confidenza: **High** per la misura; **Medium** per il costo (controfattuale "compra all'apertura",
  non eseguibile ex-ante)
* Azione consigliata: nessuna taratura in finestra. Ticket di misura: rendere `entry_percentile` e
  `quota_movimento_precedente_al_segnale` una metrica giornaliera di prima classe e non solo un
  campo di dossier.
* Test/monitor consigliato: serie giornaliera del percentile d'ingresso mediano, da confrontare con
  la finestra 08-03 → 09-28.

### [DAY-011] `ingestion_stats_daily.duplicates` (7 568) supera di 4,7× `fetched` (1 610)

* Tipo: Anomalia
* Area: Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` riga `2026-09-14 / alpaca_benzinga`
  * timestamp: aggiornato l'ultima volta 23:15:27
  * snippet/query: `fetched 1610 | queued 885 | duplicates 7568 | discarded_stale 618 | parse_fail 0`
* Descrizione: il contatore dei duplicati è additivo attraverso i run e non è riconciliabile con
  `fetched` dello stesso giorno. GDELT è coerente (2 922 / 5); solo Benzinga esplode.
* Impatto: la metrica di deduplicazione è inutilizzabile come diagnostico; non si può dire se il
  tasso di duplicazione del provider stia peggiorando.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: ticket — definire la semantica del contatore (per-fetch o cumulativo) e
  renderla verificabile contro `news_log`.
* Test/monitor consigliato: invariante `duplicates + queued + discarded_* ≈ fetched` per giorno e
  per fonte.

### [DAY-012] Primo ciclo portfolio alle 14:07 contro apertura RTH alle 13:30: 2 cicli persi

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles` (primo 14:07:00, ultimo 19:52:00), `mobile_events` `pipeline:portfolio_cycle_late`
  * timestamp: incidente CRITICAL aperto 13:30:01, "recovered" 14:08:00
  * snippet/query: `SELECT min(timestamp),count(*) FROM portfolio_cycles WHERE timestamp::date='2026-09-14'; -- 14:07:00, 24`
* Descrizione: le finestre beat sono espresse in ora UTC fissa e non seguono il DST. Con EDT
  attivo l'apertura è alle 13:30 UTC ma il primo ciclo parte alle 14:07: mancano i cicli delle
  13:37 e 13:52. Il sistema **rileva** il ritardo (incidente CRITICAL) e lo chiude da solo senza
  che nessuno intervenga.
* Impatto: 37 minuti di apertura senza ciclo, ogni seduta, per tutta la durata del DST. Oggi nessun
  segnale sopra gate è caduto in quella finestra (il primo è AZN alle 13:54, catturato dal ciclo
  14:07), quindi costo misurabile nullo — ma il fill dello stop MU delle 13:32 è caduto proprio lì.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — le finestre beat devono derivare dal calendario
  Alpaca, non da ore UTC cablate.
* Test/monitor consigliato: assert giornaliero `primo_ciclo - apertura_RTH <= cadenza_ciclo`.

### [DAY-013] `signal_id` NULL su 6 SELL su 9: la catena segnale→decisione→trade non è ricostruibile

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions`, dossier `decision_signal_id_coverage`
  * timestamp: 14:22, 14:37, 15:37, 15:52, 18:22 UTC
  * snippet/query:
    ```json
    "SELL": {"rows":9,"with_signal_id":3,"without_signal_id":6,"fill_rate":0.333,"expected_fill_rate":"must_be_full"}
    "SKIP_PYRAMIDING": {"rows":6,"with_signal_id":2,"fill_rate":0.333,"expected_fill_rate":"must_be_full"}
    ```
* Descrizione: le uscite per `below_entry_gate` / `fallback_filtered` citano il segnale nel testo
  di `reason` (score e ora di generazione) ma non valorizzano la chiave esterna. Le uscite per
  `sentiment_reversal` sì (3/3).
* Impatto: il 67 % delle uscite non è collegabile per chiave al segnale che le ha causate; ogni
  misura di IC o di attribuzione deve fare parsing di testo libero.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — popolare `signal_id` su tutti i rami d'uscita.
* Test/monitor consigliato: invariante già dichiarata nel dossier (`expected_fill_rate: must_be_full`)
  promossa ad assert che fallisce il ciclo.

### [DAY-014] Dieci alert CRITICAL del decay monitor su tre strategie, recapitati a nessuno

* Tipo: Bug
* Area: Ops / Risk
* Evidenza:
  * file/log/tabella: `worker-2026-09-14.log` 21:00:00
  * timestamp: 2026-09-14T21:00:00Z
  * snippet:
    ```
    DECAY CRITICAL [S4]: IC dropped 335% from 0.028 to -0.066
    DECAY CRITICAL [S4]: Sharpe below 50% of baseline: 0.28 vs 0.80
    DECAY CRITICAL [S4]: Hit rate dropped 19.0pp from 52.0% to 33.0%
    ... S1 (3), S2 (4) ... {'total_alerts': 10}
    ```
* Descrizione: `run_decay_check` emette `log.critical` e restituisce `succeeded`. Nessun canale.
  In più le tre strategie sono confrontate contro baseline distinte usando metriche di pipeline
  globali — S2 non è mai stata tradata e riceve comunque 4 alert.
* Impatto: il segnale di decadimento più forte del sistema è invisibile; e per un terzo è rumore
  (S2).
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — instradare i CRITICAL del decay monitor su un canale consegnato;
  escludere le strategie senza trade.
* Test/monitor consigliato: assert `total_alerts > 0 ⇒ almeno una consegna registrata`.

### [DAY-015] Il breaker del fallback scatta e il callback di allerta muore in un'eccezione

* Tipo: Bug
* Area: LLM / Ops
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-14.log:31843`
  * timestamp: 15:42:18Z
  * snippet:
    ```
    Fallback breaker alert callback failed for count=3: asyncio.run() cannot be called from a running event loop
    /app/src/workers/sentiment.py:...: RuntimeWarning: coroutine 'TelegramNotifier.send_fallback_alert' was never awaited
    ```
* Descrizione: il breaker rileva correttamente 3 fallback consecutivi durante il degrado Ollama
  delle 15:02-15:53, poi il callback chiama `asyncio.run()` dentro un event loop già attivo e
  solleva. La coroutine non viene mai attesa.
* Impatto: il rilevatore di outage dell'ensemble è di fatto inerte proprio nel momento in cui
  serve. Il 52,3 % dei segnali dell'ora era fallback e nessuno l'ha saputo.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — sostituire `asyncio.run()` con
  `loop.create_task` / `run_coroutine_threadsafe` nel callback del breaker.
* Test/monitor consigliato: test che invochi il callback da dentro un event loop attivo.

### [DAY-016] Il fetch del benchmark SPY fallisce 84 volte in giornata senza alcun alert

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `worker-2026-09-14.log` (84 occorrenze)
  * timestamp: distribuite su tutti i cicli
  * snippet: `SPY benchmark fetch failed: {"message":"subscription does not permit querying recent SIP data"}`
* Descrizione: limite di sottoscrizione SIP sul dato recente. Il fallimento è loggato a WARNING e
  ignorato; ogni calcolo che dipende dal benchmark degrada in silenzio.
* Impatto: l'attribuzione beta del dossier ricade su `beta = 1` e nessuna metrica relativa al
  benchmark è affidabile in giornata.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — dichiarare l'indisponibilità in `missingness` invece di degradare
  in silenzio.
* Test/monitor consigliato: alert quando il fetch benchmark fallisce su > 10 cicli consecutivi.

### [DAY-017] 38 simboli di watchlist su 96 senza una sola news; copertura effective-timely 47,9 %

* Tipo: Osservazione
* Area: News
* Evidenza:
  * file/log/tabella: dossier `copertura_articoli`, `mercato.watchlist_zero_news`
  * timestamp: seduta intera
  * snippet: `effective_timely_coverage: {"ticker_coperti":46,"ticker_universo":96,"quota":0.479}` · `watchlist_zero_news: 38`
* Descrizione: con due sole fonti reali (Benzinga dominante, GDELT residuale al 99 % di scarto), la
  metà della watchlist non è mai osservabile dal segnale news-driven.
* Impatto: 4 dei 38 simboli senza news erano mover (> 3 %) — invisibili per costruzione, non per
  errore di soglia.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna azione in finestra; è il vincolo strutturale che la roadmap fonti
  deve sciogliere.
* Test/monitor consigliato: serie giornaliera di `effective_timely_coverage`.

### [DAY-018] Il 53,7 % delle righe scorate nasce da articoli fan-out multi-ticker

* Tipo: Osservazione
* Area: News / Signal
* Evidenza:
  * file/log/tabella: `news_log`, dossier `copertura_articoli.mapping_fanout_extra: 92`
  * timestamp: seduta intera
  * snippet/query:
    ```sql
    WITH d AS (SELECT url,count(DISTINCT ticker) nt FROM news_log WHERE fetched_at::date='2026-09-14' GROUP BY url)
    SELECT sum(nt) FILTER (WHERE nt>1) FROM d;  -- 123 su 229
    ```
* Descrizione: 32 articoli su 138 sono mappati su 2-10 ticker e producono 123 delle 229 righe
  scorate. La mappatura di rilevanza segna **TAG_UNCONFIRMED su 120 righe** e
  **FALSE_ENTITY_MATCH su 4**.
* Impatto: metà del materiale che alimenta il ranking è un pezzo su società terze in cui il ticker
  compare di riflesso.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna in finestra (l'enforcement del resolver è gated su golden set, QX-01).
* Test/monitor consigliato: quota fan-out e quota TAG_UNCONFIRMED come serie giornaliere.

### [DAY-019] Il 48,7 % della coda Benzinga scartato per staleness, `alert_required = true`, nessun alert

* Tipo: Bug
* Area: News / Ops
* Evidenza:
  * file/log/tabella: `stale_drop_metrics_daily`, `news_queue_drops`
  * timestamp: misurato 22:55:00Z
  * snippet/query:
    ```
    queued 883 | stale_drops 430 | already_stale_at_fetch 305 | went_stale_in_queue 8
    went_stale_off_session 117 | stale_drop_share 0.487 | alert_threshold 0.25 | alert_required TRUE
    ```
    `SELECT count(*) FROM news_queue_drops WHERE dropped_at::date='2026-09-14';  -- 11 308`
* Descrizione: quasi metà della coda viene buttata perché già vecchia: 305 articoli erano stale
  **già al fetch**, 117 sono scaduti fuori sessione. La soglia di alert (25 %) è superata di quasi
  il doppio e `alert_required` è true, ma non esiste consegna (vedi [DAY-003]).
* Impatto: la finestra di freschezza è consumata prima che il segnale possa nascere; combinato con
  [DAY-010] è la stessa patologia vista dal lato ingest.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket — collegare `alert_required` a un canale consegnato. La soglia è
  taratura congelata.
* Test/monitor consigliato: la serie `stale_drop_share` per fonte esiste già: va solo resa
  rumorosa quando supera la soglia.

### [DAY-020] Segnali `ensemble:` persistiti con entrambi i contributori `eligible=false`

* Tipo: Bug
* Area: LLM
* Evidenza:
  * file/log/tabella: `llm_responses` + `sentiment_signals`
  * timestamp: es. 10735 (NOK), 10723 (GOOGL), 10678 (XLK)
  * snippet/query:
    ```
    id 10735 NOK score -0.105 std 0.354 | glm-5.2:cloud:-0.20/0.30/false | gpt-oss:20b-cloud:-0.70/0.30/false
    ```
    Totale: 121/218 risposte glm e 123/220 gpt-oss marcate `eligible=false` (≈ 56 %).
* Descrizione: il flag `eligible` non esclude il contributore dal calcolo dell'ensemble: NOK 10735
  è etichettato `ensemble:` e ha uno score calcolato pur avendo entrambi i modelli ineleggibili, con
  divergenza massima (polarity −0,20 vs −0,70, `std` 0,354).
* Impatto: oggi nessuno di questi segnali ha superato il gate (massimo |score| 0,105), quindi
  nessun ordine ne è nato. Ma `eligible` è una garanzia che non garantisce nulla, e il 56 % delle
  risposte lo porta.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — decidere e documentare la semantica di `eligible`; se è un filtro,
  applicarlo; se è telemetria, rinominarlo.
* Test/monitor consigliato: invariante `model_id LIKE 'ensemble:%' ⇒ ≥ 2 contributori eleggibili`.

### [DAY-021] Il decay monitor allerta su S2, che non ha mai tradato

* Tipo: Bug
* Area: Risk
* Evidenza:
  * file/log/tabella: `worker-2026-09-14.log` 21:00:00
  * timestamp: 21:00:00Z
  * snippet: `DECAY CRITICAL [S2]: Max drawdown exceeds baseline by 5.8pp: 11.8% vs 6.0%` (4 alert S2)
* Descrizione: le metriche confrontate sono globali di pipeline, non per-strategia: le tre
  strategie ricevono lo stesso IC (−0,066) confrontato con tre baseline diverse. S2 non compare in
  `strategies_run` di nessun ciclo.
* Impatto: 4 dei 10 CRITICAL della giornata sono rumore strutturale.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — calcolare le metriche di decadimento per sleeve ed escludere le
  strategie senza trade.
* Test/monitor consigliato: assert che nessun alert di decadimento sia emesso per una strategia con
  0 trade nella finestra.

### [DAY-022] Broker irraggiungibile alle 20:33 e il task Celery risulta `succeeded`

* Tipo: Bug
* Area: Broker / Ops
* Evidenza:
  * file/log/tabella: `worker-2026-09-14.log` 20:33:04; `mobile_events` `pipeline:broker_stale`
  * timestamp: 20:33:04 → recovered 20:34:03
  * snippet: `Mobile snapshot: Alpaca broker read failed: ... NameResolutionError ... Failed to resolve 'paper-api.alpaca.markets'`
* Descrizione: risoluzione DNS fallita verso Alpaca (e, poco prima, verso OpenFIGI alle 19:37 e
  19:54: `OpenFIGI lookup failed for HACK / GM`). Il task Celery non propaga il fallimento. Fuori
  orario: nessun ciclo portfolio perso.
* Impatto: nullo in giornata (post-chiusura), ma è lo stesso schema che in orario cancellerebbe
  cicli interi lasciando il task verde.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: ticket — un fallimento di lettura broker deve marcare il task fallito, non
  loggare e proseguire.
* Test/monitor consigliato: contatore giornaliero `broker_read_failures` con soglia.

### [DAY-023] Il resolver deterministico dei ticker non produce verdetti: 120 righe TAG_UNCONFIRMED contro 105 ISSUER_SPECIFIC

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log.extraction_method`, dossier `copertura_articoli.mapping_rilevanza`
  * timestamp: seduta intera
  * snippet/query:
    ```sql
    SELECT extraction_method,count(*) FROM news_log WHERE fetched_at::date='2026-09-14' GROUP BY 1;
    -- source_metadata 206 | org_lookup 23   (nessun verdetto resolver)
    -- mapping_rilevanza: ISSUER_SPECIFIC 105 | TAG_UNCONFIRMED 120 | FALSE_ENTITY_MATCH 4
    ```
* Descrizione: nessuna riga della giornata porta un `extraction_method` prodotto dal resolver
  deterministico; l'attribuzione resta quella dei metadati del provider. La maggioranza relativa
  delle mappature resta non confermata, e 4 sono falsi match d'entità.
* Impatto: `false_positive_ticker_rate` non è né misurato né vincolato; 4 righe sono attribuite al
  ticker sbagliato.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: nessuna azione di enforcement in finestra (QX-01: gated su golden set). Il
  ticket ammissibile è di misura: rendere visibile che il resolver non emette verdetti.
* Test/monitor consigliato: serie giornaliera dei verdetti resolver per esito.

### [DAY-024] `slippage_est` è una copia di `cost_usd`: la qualità d'esecuzione non è misurata

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` id 999, 1000, 1001, 1002
  * timestamp: 2026-09-14
  * snippet/query:
    ```sql
    SELECT id,symbol,cost_usd,slippage_est FROM trades WHERE entry_time::date='2026-09-14';
    -- 999 AZN 0.7944384141789159 / 0.7944384141789159  (identici su tutte e 4 le righe)
    ```
* Descrizione: il campo che dovrebbe misurare lo scostamento fra prezzo atteso e prezzo eseguito
  contiene il costo modellato. Non esiste da nessuna parte il prezzo di riferimento al momento
  della decisione da confrontare col fill.
* Impatto: impossibile distinguere una perdita da esecuzione da una perdita da segnale.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — persistere `decision_price` (già esiste in `execution_decisions`)
  accanto al fill e calcolare lo slippage come differenza.
* Test/monitor consigliato: assert `slippage_est != cost_usd` su almeno una riga.

### [DAY-025] Due `WorkerLostError` da SIGTERM: job in volo persi, ri-processamento in crash-recovery

* Tipo: Rischio
* Area: Ops
* Evidenza:
  * file/log/tabella: `worker-inference-2026-09-14.log:17676, 49342`
  * timestamp: 08:09:15 e 22:20:10
  * snippet: `billiard.exceptions.WorkerLostError: Worker exited prematurely: signal 15 (SIGTERM) Job: 30370.` / `Job: 1429.`
* Descrizione: 4 riavvii di container in giornata (08:09, 10:16, 20:20, 22:20). Due hanno ucciso un
  job in volo; i worker ripartono in modalità `(recovery)` e ripristinano i messaggi non-ack
  (`Restoring 1 unacknowledged message(s)`). Il ciclo sentiment non è idempotente: un articolo già
  scorato e persistito può essere ri-scorato.
* Impatto: entrambi gli eventi sono fuori orario di mercato, quindi nessun segnale di trading è
  stato duplicato oggi. Il rischio resta se un riavvio cade in sessione.
* Severità: **Medium**
* Confidenza: **High** per l'evento; **Medium** per l'assenza di duplicazione (verificata solo dal
  vincolo unico `(symbol, generated_at)`)
* Azione consigliata: ticket — chiave d'idempotenza per articolo sul ciclo sentiment.
* Test/monitor consigliato: test che riesegua un ciclo interrotto e verifichi zero segnali
  duplicati.

### [DAY-026] Incidenti mobile chiusi in meno di un secondo da un valutatore che non li ha aperti

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `mobile_events`
  * timestamp: 22:50:00.45 → 22:50:01.09
  * snippet:
    ```
    pipeline:portfolio_cycle_session_grid  occurred 22:50:00.453  last_observed 22:50:01.094  status recovered
    coverage:held_no_news_loss:PFE         occurred 22:50:00.732  last_observed 22:50:01.091  status recovered
    coverage:held_no_news_loss:SBUX        occurred 22:50:00.743  last_observed 22:50:01.076  status recovered
    ```
* Descrizione: tre incidenti aperti da job specializzati vengono marcati `recovered` entro ~0,6 s
  dal valutatore generico, che non ne è proprietario. Anche l'incidente CRITICAL
  `portfolio_cycle_late` delle 13:30 risulta "recovered" alle 14:08 senza che nulla sia stato
  corretto.
* Impatto: nessun incidente resta aperto abbastanza da essere notato; combinato con [DAY-003]
  (0 dispositivi, 0 consegne) l'intero sottosistema di incident è decorativo.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket — il valutatore generico non deve chiudere fingerprint di cui non è
  proprietario.
* Test/monitor consigliato: assert `durata_incidente > cadenza_del_job_proprietario`.

### [DAY-027] `performance_metrics` vuota da sempre: IC composito, ICIR e PSI non sono mai stati persistiti

* Tipo: Osservazione
* Area: Data
* Evidenza:
  * file/log/tabella: `performance_metrics`
  * timestamp: n/a (tabella vuota)
  * snippet/query:
    ```sql
    SELECT count(*) FROM performance_metrics;  -- 0
    grep -rn "performance_metrics" src/ --include=*.py   -- nessun riferimento
    ```
* Descrizione: la tabella che dovrebbe ospitare `composite_ic`, `icir`, `psi_90d`, `psi_12m`,
  `drift_level` e `consecutive_negative_ic_days` esiste nello schema, ha un trigger di
  `updated_at`, e non è referenziata da una sola riga di codice applicativo. Il ribilanciamento LOO
  ICIR scrive invece su `weight_update_log` (20 righe, l'ultima il 2026-09-14 alle 04:00).
* Impatto: il monitoraggio di drift PSI descritto nell'architettura non esiste come serie
  persistita; nessun impatto sulle decisioni odierne.
* Severità: **Low**
* Confidenza: **High**
* Azione consigliata: o alimentare la tabella, o rimuoverla dallo schema e dalla documentazione,
  perché oggi suggerisce una capacità che non c'è.
* Test/monitor consigliato: nessuno; è una decisione di pulizia.

---

## 10. False positive e aree risultate corrette

| area | verifica | esito |
|---|---|---|
| Ordini fuori watchlist | 0 simboli estranei in `news_log`, `sentiment_signals`, `execution_decisions`, ordini broker | **corretto** |
| Ordini fuori orario | tutti i 14 fill fra 13:32:07 e 19:37:08 UTC | **corretto** |
| Ordini duplicati / race del scheduler | nessuna coppia (simbolo, lato) ripetuta nello stesso minuto o ciclo | **corretto** |
| Roundtrip < 30 min | minimo 105 min (AZN); `hold_minimum_minutes = 90` ha morso correttamente | **corretto** |
| Pyramiding | 51 tentativi bloccati, 0 eseguiti | **corretto** (il difetto è di tracciamento) |
| News duplicate pesate più volte | 0 coppie `(content_hash, ticker)` ripetute | **corretto** |
| Timestamp futuri | 0 righe con `published_at > fetched_at` | **corretto** |
| Campi news mancanti | 0 titoli vuoti, 0 corpi vuoti, 0 `published_at` NULL, 0 `parse_fail` | **corretto** |
| Ollama "giù": `fallback_used=True` su tutti i simboli | **falso positivo** — mai. Massimo 52,3 % in un'ora, 31,0 % di giornata | **corretto** |
| Ordini con score < 0,05 | nessuno: tutti e 4 i BUY hanno `signal_score` ≥ 0,322 | **corretto** |
| Segnali senza news | nessuno: 229 segnali ↔ 229 righe `news_log`, `news_log_id` sempre valorizzato | **corretto** |
| Ordini senza segnale | nessuno fra quelli emessi in giornata. L'unico ordine senza segnale è il fill dello stop MU, che per costruzione non ne ha ([DAY-001]) | **corretto** |
| FinBERT riceve titolo **e** corpo | `finbert_fallback_events`: `title_chars > 0` **e** `body_chars > 0` su **13/13** righe | **corretto** — conferma residua di #453/#544 chiusa |
| LLM nel trading loop | tutte le chiamate su `worker-inference`; `portfolio_scheduler` legge solo da DB | **corretto** |
| Distinzione paper/live | esplicita a tre livelli (env, config, `/portfolio/status`) | **corretto** |
| Circuit breaker | mai attivato, `constraints_fired = []` su 24/24 cicli | **corretto** |
| Riconciliazione simboli | 40/40 fra `/api/positions` e `trades WHERE exit_time IS NULL` | **corretto** |
| Calendario earnings | `status: OBSERVED`, FMP risponde, 0 simboli flaggati, streak unknown = 0 | **corretto** — la cecità nota è rientrata |

---

## 11. Dati mancanti o non accessibili

1. **Latenza LLM per chiamata.** Nessuna strumentazione. Disponibile solo la durata di ciclo
   (`ensemble_cycle_health`, media 204,3 s per ciclo multi-articolo). Query che servirebbe: una
   colonna `latency_ms` su `llm_responses`.
2. **Prezzo di riferimento al momento della decisione vs fill.** `execution_decisions.decision_price`
   esiste ma non è confrontato col fill in nessuna vista. Senza questo lo slippage reale
   (distinto dal costo modellato, [DAY-024]) non è calcolabile.
3. **P&L attribuito per sleeve.** `trades.stop_strategy` copre solo i trade post-patch; la leg
   orfana di MU (−126,85 $) non è attribuita ad alcuna strategia.
4. **Prezzo del fill dello stop MU nel contesto intraday del 09-09.** Serve per stabilire se lo stop
   a 908,56 (−12,25 % dall'entry) fosse il trigger corretto o un fill anomalo. Query: barre 5 min di
   MU dal 2026-09-09 al 2026-09-14 via Alpaca.
5. **Etichetta di seduta di `/api/performance/pnl`.** La riga `2026-09-14 / −497,12` è coerente con
   la seduta del 14, ma il difetto noto di sfasamento di un giorno di calendario su quell'endpoint
   non è stato ri-verificato in questa sessione: il numero è usato come contesto, non come misura.
6. **`risk_reports` e `portfolio_cycle_persist_failures`** non interrogati: schema senza colonna
   `created_at`, nome della colonna temporale non verificato in questa sessione.

---

## 12. Raccomandazioni immediate

1. **Riconciliare il P&L del 2026-09-14** prima che entri in qualunque serie: il realizzato vero è
   ≈ **−240,64 $**, non −113,79. ([DAY-001])
2. **Ruotare il bot token Telegram** esposto in chiaro nei log e redigere il logger `httpx`.
   ([DAY-004])
3. **Riparare il canale di alert** (Telegram 400 + 0 dispositivi mobile): oggi il sistema non ha
   modo di dire a nessuno che qualcosa va male. ([DAY-003])
4. **Decidere cosa fare delle posizioni sub-1-azione** che violano d_hard da giorni (AMAT −28 %,
   WDC −22 %, NOK −17 %): o si chiudono a mano, o si accetta esplicitamente che non siano
   proteggibili. ([DAY-002])
5. Nessuna delle raccomandazioni tocca soglie, pesi o parametri di strategia: la carta di
   osservazione resta rispettata fino al 2026-09-28.

## 13. Test e monitor da aggiungere

| # | monitor | invariante |
|---|---|---|
| M1 | riconciliazione fill↔trade giornaliera | ogni ordine `filled` ha un `trade_id`; `Σ qty fill = Σ qty leg` per simbolo |
| M2 | alert emessi vs consegnati | `alert_emessi == alert_consegnati` per giorno |
| M3 | integrità decisioni | `decision IN ('BUY','SELL') ⇒ order_id IS NOT NULL` |
| M4 | copertura `signal_id` | `fill_rate == 1.0` su BUY, SELL, SKIP_* (già dichiarata `must_be_full` nel dossier) |
| M5 | enforcement d_hard | `d_hard_breached` per N cicli ⇒ ordine d'uscita o alert consegnato |
| M6 | allineamento apertura | `primo_ciclo − apertura_RTH ≤ cadenza_ciclo` |
| M7 | sanitizzazione input | nessuna entità HTML nel testo passato al modello |
| M8 | integrità ensemble | `model_id LIKE 'ensemble:%' ⇒ ≥ 2 contributori eleggibili` |
| M9 | guard firings vs righe persistite | conteggi allineati per guard e per giorno |
| M10 | idempotenza sentiment | riesecuzione di un ciclo interrotto ⇒ 0 segnali duplicati |
| M11 | slippage reale | `slippage_est != cost_usd` su almeno una riga |
| M12 | staleness coda | `stale_drop_share > soglia ⇒ alert consegnato` |

## 14. Ticket tecnici suggeriti

Tutti di **correttezza** (esenti dal freeze: senza questi l'evidenza raccolta nelle prossime
settimane è sbagliata). Nessuno tocca una taratura.

| # | titolo | finding | severità |
|---|---|---|---|
| T1 | Riconciliare ogni fill del broker contro `trades`; scrivere le uscite parziali con il proprio P&L; azzerare `quantity_remaining` alla chiusura | [DAY-001] | Critical |
| T2 | Emettere un market sell frazionario quando d_hard è violato e non esiste un ordine di stop (parte intera 0) | [DAY-002] | High |
| T3 | Riparare il payload del `TelegramNotifier` (400) e dare un canale consegnato agli alert del decay monitor | [DAY-003], [DAY-014] | High |
| T4 | Ruotare il token Telegram e redigere gli URL `api.telegram.org` nei log | [DAY-004] | Medium |
| T5 | Codici decisione dedicati per i BUY/SELL bloccati dai guard, con `reason` = causa del blocco | [DAY-005], [DAY-006] | Medium |
| T6 | `html.unescape` in testa a `sanitize_text` | [DAY-007] | Medium |
| T7 | Popolare `signal_id` su tutti i rami d'uscita | [DAY-013] | Medium |
| T8 | Sostituire `asyncio.run()` nel callback del breaker di fallback | [DAY-015] | Medium |
| T9 | Derivare le finestre beat dal calendario Alpaca invece che da ore UTC cablate | [DAY-012] | Medium |
| T10 | Definire e applicare la semantica di `llm_responses.eligible` | [DAY-020] | Medium |
| T11 | Calcolare le metriche di decadimento per sleeve; escludere le strategie senza trade | [DAY-021] | Medium |
| T12 | Chiave d'idempotenza per articolo sul ciclo sentiment | [DAY-025] | Medium |
| T13 | Impedire al valutatore mobile generico di chiudere fingerprint di cui non è proprietario | [DAY-026] | Medium |
| T14 | Calcolare lo slippage reale da `decision_price` vs fill | [DAY-024] | Medium |
| T15 | Rendere fallito il task Celery quando la lettura broker fallisce | [DAY-022] | Low |
| T16 | Definire la semantica di `ingestion_stats_daily.duplicates` | [DAY-011] | Low |
| T17 | Alimentare o rimuovere `performance_metrics` | [DAY-027] | Low |

## 15. Stato sistema

| voce | valore |
|---|---|
| **Ollama** | **UP tutto il giorno, mai down.** 20 timeout (90 s) su 458 chiamate = **4,4 %**. Finestra di degrado 13:48–15:53 UTC (**2 h 05 m**), picco 15:02–15:53 con 15 timeout. Nessun intervallo con fallback al 100 %. **Downtime totale: 0 h.** |
| **Modelli attivi** | `glm-5.2:cloud` (peso 0,70) + `gpt-oss:20b-cloud` (peso 0,30), pesi confermati dal ribilanciamento LOO ICIR delle 04:00 (`max_delta` 4,3e-13, nessuna variazione) |
| **FinBERT fallback rate** | **13/229 segnali = 5,7 %** invocazioni FinBERT (7 per timeout Ollama, 6 per divergenza d'ensemble). **Fallback complessivo** (FinBERT + single-model): **71/229 = 31,0 %** |
| **Segnali usati per decidere** | 158/229 (69,0 %) da ensemble completo |
| **Worker restart** | **4** — worker 10:16:52 e 20:20:29; worker-inference 08:09:23 e 22:20:22. **2 `WorkerLostError`** (SIGTERM, job 30370 e 1429), entrambi fuori orario di mercato |
| **Cicli portfolio** | 24 eseguiti (14:07:00 → 19:52:00 UTC); 2 persi all'apertura ([DAY-012]); 0 falliti; 0 righe in `portfolio_cycle_persist_failures` |
| **Cicli sentiment** | 198 esecuzioni 03:19 → 21:45 UTC; coda drenata a fine giornata (`queue_depth` 26 alle 23:55, `dead_letter_depth` 0) |
| **Broker** | Alpaca paper. 1 finestra di irraggiungibilità DNS alle 20:33 (~60 s, post-chiusura). OpenFIGI irraggiungibile alle 19:37 e 19:54 |
| **Alert consegnati** | **0** (6 Telegram → 400, 10 decay CRITICAL → solo log, 6 mobile events → 0 dispositivi, 0 consegne) |
| **Regime** | SIDEWAYS, `regime_mult` 0,70, osservato alle 19:52:30 |
| **Equity fine giornata** | 109 245,16 $ (−497,12 $, −0,45 %) vs SPY −0,45 % |
