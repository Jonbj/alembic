# Forensic Daily Report — 2026-08-25

**Generato:** 2026-08-26 · **Analista:** sessione forense automatizzata (read-only)
**Timezone operativo:** UTC (`src/workers/celery_app.py:51` → `timezone="UTC"`). Nessuna ambiguità: tutti i timestamp di questo report sono UTC.
**Sessione RTH 2026-08-25:** 13:30–20:00 UTC (09:30–16:00 America/New_York, EDT).
**Periodo:** giorno 17 della finestra di sola osservazione (inizio 2026-08-03, scadenza attesa 2026-09-28). Nessuna taratura proposta.

---

## 1. Executive summary

La giornata è **funzionalmente corretta sul money-path** e **rotta su tre punti dell'impianto di misura**.
Sul money-path: 4 ordini (3 BUY S4 — NVDA, CSCO, META — e 1 SELL S1 su XLE), tutti riconciliati
a segnale, decisione, fill e trade; zero ordini duplicati, zero fuori orario, zero senza risk check,
zero roundtrip intraday, zero SELL con sentiment positivo. Ollama up al 100% (196/196 risposte,
zero timeout, zero fallback FinBERT). P&L realizzato del giorno **+$91,80** (XLE), MTM sui 3 nuovi
ingressi **+$5,70**, NAV 109 864,64 → 109 958,17 (**+$93,53**, +0,085%) contro SPY +0,32%.
I tre difetti nuovi riguardano l'**evidenza**, non il denaro, ed è per questo che contano di più:
(a) il dossier legge `is_tradable` con un confronto sbagliato (`== "t"` contro `'true'`), quindi
l'aggregato della guardia ombra #335 è **strutturalmente zero** al primo giorno di vita;
(b) l'LLM riceve **solo il corpo** dell'articolo, mai il titolo — su HOOD (+8,17%, mover #1 della
seduta) il corpo Benzinga descriveva un'altra giornata e i due modelli hanno scorato −0,01;
(c) la classificazione RTH del lifecycle S4 interpreta come UTC i datetime naive del calendario
Alpaca, spostando la finestra di 4 ore: **3 fill su 3** sono usciti `CENSORED / FILL_OUTSIDE_RTH`
con `d0` e `due_session` NULL, e l'orologio di uscita D+2 non si arma mai.
F-003 (drawdown fittizio) risulta **risolto** dal deploy di #366: l'ALERT fantasma "17,9%" è sparito.

## 2. Verdict finale

> **ANOMALIE SIGNIFICATIVE** — money-path corretto, strumentazione dell'evidenza compromessa.

Nessun ordine sbagliato, nessuna perdita imputabile a un difetto. Ma tre difetti di **correttezza
dell'evidenza** sono attivi contemporaneamente e due di essi (DAY-001, DAY-003) sono al primo giorno
di esercizio della strumentazione appena deployata: se non corretti, le settimane di osservazione che
restano producono un ledger che misura zero per costruzione. Passano il test di esenzione della
`OBSERVATION_CHARTER.md` («se non lo correggo, l'evidenza che raccolgo nelle prossime settimane è
sbagliata?») e sono quindi ammissibili come remediation ticket in pieno freeze.

---

## 3. Timeline del 2026-08-25 (UTC)

| Ora | Componente | Evento | Esito | Fonte |
|---|---|---|---|---|
| 06:02 | mobile monitor | primo snapshot del giorno | ok, 48 posizioni | `portfolio_monitor_snapshots` |
| 12:38:53 | **suite di test** | scrittura `ingestion_stats_daily` source=`reuters` (36 fetched, 9 no_ticker) | **anomalia** — DB di produzione | `ingestion_stats_daily` |
| 13:30 | mercato | apertura RTH | — | — |
| 13:30–14:00 | ingest | **nessun fetch news** (beat parte a 14:00) | 30 min di sessione non coperti | `crontab(minute="*/15", hour="14-21")` |
| 13:30–14:07 | esecuzione | **nessun ciclo portfolio** (beat parte a 14:07) | 37 min di sessione non coperti | `crontab(minute="7,22,37,52", hour="14-21")` |
| 14:00:35 | ingest | primo fetch alpaca_benzinga | 14 righe nell'ora | `news_log` |
| 14:00:35 | LLM | primo scoring del giorno (MU, ensemble) | ok | `sentiment_signals` id 8856 |
| 14:07:00 | portfolio-cycle | primo ciclo (S1+S4) | 3 SKIP_STALE (GM 18,6h, QQQ 20,1h, XLK 19,9h) | `execution_decisions` 14274-14276 |
| 14:15:12 | LLM | NVDA score **+0,330** (single:gpt-oss, glm conf 0,35 < floor 0,4) | scartato a valle | `sentiment_signals` 8858 |
| 15:00:14 | ingest | primo fetch gdelt_gkg | 10 articoli, tutti effective-timely | `news_log` |
| 16:15:35 | LLM | DELL score **+0,581** (ensemble, il più forte con due modelli) | → SKIP_PYRAMIDING | `sentiment_signals` 8892 |
| 16:22:04 | portfolio-cycle | DELL bloccato: «P0-05 anti-pyramiding: già a libro dal 2026-07-13» | ordine non emesso | `execution_decisions` 14436 |
| 16:30:52 | LLM | MS score **+0,680** — score massimo del giorno, single:gpt-oss, articolo *"Buy this stock…, Morgan Stanley says"* | ticker sbagliato | `sentiment_signals` 8899 |
| 16:45:15 | LLM | HOOD score **−0,0098** su articolo titolato *"Why Is Robinhood Stock Surging on Tuesday?"* | **corpo di un altro articolo** | `sentiment_signals` 8902 |
| 17:22 / 17:52 / 18:22 / 18:37 / 19:07 / 19:22 | portfolio-cycle | 7 × SKIP_FALLBACK (ORCL, IWM, SHEL, **MS 0,680**, ORCL, INFY, GS) | esclusi dal ranking BUY (#108) | `execution_decisions` |
| 18:00:12 | LLM | XLE score **−0,357** su market-wrap a 10 ticker | supera soglia uscita −0,35 | `sentiment_signals` 8914 |
| **18:07:00** | portfolio-cycle | **SELL XLE** — `sentiment_reversal: score -0.357 < threshold -0.35` | decisione 14577 | `execution_decisions` |
| 18:07:04 → 18:07:07 | broker | ordine `e84311ee…` submitted → filled @ 62,50, qty 12,3722 | **+$91,80 net** | Alpaca / `trades` 282 |
| 18:46:42 | LLM | NVDA score **+0,420** (single:gpt-oss) | scartato a valle | `sentiment_signals` 8937 |
| 19:00:35 / 19:00:49 | LLM | CSCO **+0,320** / NVDA **+0,378** dallo stesso articolo Cisco↔Nvidia | ensemble a due modelli | 8942 / 8944 |
| **19:07:00** | portfolio-cycle | **BUY NVDA** (14679) + **BUY CSCO** (14680), peso 2,0% ciascuno | signal_score 0,4536 / 0,3839 | `execution_decisions` |
| 19:07:04 → 19:07:05 | broker | fill NVDA @ 212,74 (8,9456 sh) e CSCO @ 111,06 (17,1357 sh) | trades 829, 830 | Alpaca |
| 19:12:00 | lifecycle S4 | riconciliazione ingressi → **CENSORED / FILL_OUTSIDE_RTH** | `d0`/`due_session` NULL | `s4_lifecycle_events` |
| 19:22:04 | protective stops | stop GTC creati: NVDA **qty 8** (di 8,9456), CSCO **qty 17** (di 17,1357) | un ciclo dopo l'ingresso, solo parte intera | Alpaca orders |
| 19:22:04 | portfolio-cycle | 3 × SKIP_PYRAMIDING (LLY, SOXX, NVDA con «sentiment +0.000») | ordini non emessi | `execution_decisions` 14706-14708 |
| 19:45:13 | LLM | META **+0,385** (ensemble) su *"Evercore: META Could Surge Over 50%…"* | ok | `sentiment_signals` 8950 |
| 19:45:27 | ingest/LLM | ultimo scoring del giorno (NVDA +0,358, single) | fine giornata news | `sentiment_signals` 8952 |
| **19:52:00** | portfolio-cycle | **BUY META** (14747), peso 2,0% — **ultimo ciclo della sessione** | signal_score 0,38545 | `execution_decisions` |
| 19:52:04 | broker | fill META @ 569,43 (3,3410 sh) | trade 831 | Alpaca |
| 19:57:00 | lifecycle S4 | riconciliazione META → **CENSORED / FILL_OUTSIDE_RTH** | — | `s4_lifecycle_events` |
| 20:00:00 | mobile monitor | ultimo snapshot: NAV 109 958,17, 48 posizioni, MV 36 030,43, UPL +1 097,65 | — | `portfolio_monitor_snapshots` |
| 20:00 | mercato | chiusura RTH — **META resta senza stop protettivo** (nessun ciclo dopo) | esposizione notturna $1 902 non protetta | Alpaca orders |
| 21:00:00 | decay monitor | 12 righe (S1/S2/S4 × 4 metriche) con **valori misurati identici** | 2 × CRITICAL su hit_rate | `decay_reports` |
| 22:30:01 | risk monitor | NAV 109 973,25, exposure 32,78%, HHI 0,0257, drawdown 0,012429, **alerts `[]`**, `per_strategy_metrics` `{}` | ALERT fantasma sparito (#366) | `risk_reports` 74 |
| 22:45:00 | counterfactual | calcolo controfattuali 1h sulle guard decisions | 460 righe | `execution_decisions` |
| **[2026-08-26 08:01]** | dossier | `alpha_miner_dossier.py` genera il dossier 2026-08-25 (schema 2.5) | ok — F-044 non ricorre | `docs/evidence/dossier/` |

**Buchi noti nella timeline:** i log dei container non contengono una sola riga del 2026-08-25
(redeploy alle ~10:30 del 26). Latenza per-chiamata LLM, retry, errori transienti e riavvii worker
non sono ricostruibili per la giornata. Vedi [DAY-005].

---

## 4. Tabella news ingest

### 4.1 Per fonte

| Fonte | Fetched | Queued | Duplicati | Scartati no_ticker | Scartati stale | parse_fail | Righe in `news_log` | Articoli unici | Effective-timely | Quota |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `alpaca_benzinga` | 579 | 345 | **2 589** | 0 | 116 | 0 | 88 | 45 | 11 | 24,4% |
| `gdelt_gkg` | 1 279 | 11 | 0 | 1 268 | 4 | 0 | 10 | 10 | 10 | 100% |
| `reuters` *(non pipeline)* | 36 | 36 | 0 | 9 | 0 | 0 | 0 | 0 | — | — |
| **Totale pipeline** | **1 858** | **356** | **2 589** | **1 268** | **120** | **0** | **98** | **55** | **21** | **38,2%** |

Drop registrati in `news_queue_drops`: 2 589 `duplicate_id` (ingestion, benzinga), 1 268 `no_ticker`
(ingestion, gdelt), 139 `not_tradable` (sentiment, benzinga), 116 `stale` (sentiment, benzinga),
9 `no_ticker` (ingestion, **reuters**), 4 `stale` (sentiment, gdelt).

### 4.2 Copertura temporale e latenza

| Metrica | Valore |
|---|---|
| Primo fetch | 14:00:35 (30 min dopo l'apertura RTH) |
| Ultimo fetch | 19:45:27 (15 min prima della chiusura) |
| Copertura pre-market | **nessuna** |
| Righe per ora | 14h:14 · 15h:16 · 16h:18 · 17h:11 · 18h:24 · 19h:15 |
| Latenza published→fetched, mediana | **40,3 min** |
| Latenza published→fetched, media / max | 44,5 min / 111,2 min |
| Timestamp futuri (`published_at > fetched_at`) | **0** |
| Buchi orari intra-finestra | nessuno |

### 4.3 Per ticker (righe scorate)

| Ticker | Righe | Articoli unici | Max score | Min score | Fallback single-model |
|---|---:|---:|---:|---:|---:|
| NVDA | 18 | 18 | +0,420 | −0,104 | 10 |
| TSLA | 6 | 6 | +0,141 | −0,114 | 1 |
| HOOD | 5 | 5 | +0,174 | −0,010 | 3 |
| AMD | 4 | 4 | +0,267 | −0,066 | 2 |
| QQQ | 4 | 4 | +0,180 | 0,000 | 2 |
| META / CSCO / TXN / XLK / INTC / SPCX / XLE | 3 | 3 | +0,385 / +0,320 / +0,210 / +0,140 / +0,120 / +0,151 / 0,000 | … / … / … / … / … / −0,121 / **−0,357** | 1 / 0 / 1 / 2 / 2 / 1 / 0 |
| altri 30 ticker | ≤2 | ≤2 | — | — | — |

Concentrazione (dossier): top-5 ticker 42,9% degli articoli effective-timely, HHI 0,070;
per settore top-5 90,5%, HHI 0,211; per fonte HHI 0,501.
**Copertura effective-timely: 17 ticker su 96 (17,7%). 55 simboli di watchlist senza una sola news.**

### 4.4 Fan-out multi-ticker

| Ticker per articolo | Articoli | Righe generate |
|---:|---:|---:|
| 1 | 40 | 40 |
| 2 | 6 | 12 |
| 3 | 3 | 9 |
| 4 | 2 | 8 |
| 5 | 2 | 10 |
| 9 | 1 | 9 |
| 10 | 1 | 10 |

**59,2% delle righe scorate (58/98) nasce da articoli multi-ticker.** I due maggiori:
*"Bitcoin Tops $80,000, Oil Sinks As Navy Clears Hormuz Mines: Stock Market Today"* → 10 ticker
(AMD, HOOD, IWM, MRVL, MU, NVDA, QQQ, XLE, XLK, XLV) — è l'articolo che ha prodotto la SELL su XLE;
*"Treasury Bond Buybacks Cannot Solve A Fiscal Problem…"* → 9 ticker.

### 4.5 Top news per impatto sul segnale

| Ora | Ticker | Titolo | Score | Esito |
|---|---|---|---|---|
| 16:30 | MS | *Buy this stock to play boom in one area of AI, **Morgan Stanley** says* | **+0,680** | SKIP_FALLBACK — ticker sbagliato (F-020) |
| 16:15 | DELL | *What's Going On With Dell Technologies Stock Tuesday?* | **+0,581** | SKIP_PYRAMIDING |
| 18:46 | NVDA | *Nvidia, Blackwell and AI Spending: 4 ETFs in Focus Ahead of Earnings* | **+0,420** | SKIP_FALLBACK |
| 19:45 | META | *Evercore: META Could Surge Over 50% on $22B AI Opportunity* | **+0,385** | **BUY** |
| 19:00 | NVDA | *Nvidia's AI Chips Are Making Liquid Cooling the New Standard as Cisco Expands Its AI Bet* | **+0,378** | **BUY** |
| 18:00 | XLE | *Bitcoin Tops $80,000, Oil Sinks As Navy Clears Hormuz Mines* | **−0,357** | **SELL** |
| 19:00 | CSCO | (stesso articolo Cisco↔Nvidia) | **+0,320** | **BUY** |
| 16:45 | HOOD | *Why Is Robinhood Stock Surging on Tuesday?* | **−0,0098** | scartato — **corpo di un altro articolo** |

### 4.6 Problemi trovati nell'ingest

1. **Attribuzione ticker a società terze** (fan-out): INTC ← articolo su Bloom Energy; MU ← SanDisk;
   MRK ← Moderna; CSCO e NVDA ← Super Micro; META e SPCX ← OpenAI/influenza russa;
   AMD, INTC, MSFT, NVDA ← Dell.
2. **`org_lookup` su nome di casa d'analisi**: MS ← *"…Morgan Stanley says"* (F-020).
3. **Titolo e corpo di articoli diversi**: HOOD id 8902 — vedi [DAY-002].
4. **Righe `reuters` di test nel DB di produzione** (F-028).
5. Copertura: nessun fetch pre-market né nei primi 30 minuti di sessione.
6. Nessuna sanitizzazione mancante osservata: entità HTML (`&#39;`, `&amp;`) presenti nei corpi ma
   non tali da invertire il senso; nessun homoglifo o testo nascosto rilevato.

**Confidenza dell'analisi ingest: Alta** (dati integralmente da `news_log`, `news_queue_drops`,
`ingestion_stats_daily`; nessuna ricostruzione da log mancanti).

---

## 5. Tabella performance modelli LLM

### 5.1 Volumi e affidabilità

| Modello | Richieste | Risposte | Errori | Timeout | Refusal / output invalido | `eligible=true` in DB | Polarity media | Confidence media | σ polarity |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `glm-5.2:cloud` | 98 | **98** | 0 | 0 | 0 | 26 | +0,0990 | 0,322 | 0,222 |
| `gpt-oss:20b-cloud` | 98 | **98** | 0 | 0 | 0 | 26 | +0,0990 | **0,410** | 0,235 |
| `finbert` (fallback) | — | **0** | — | — | — | — | — | — | — |

**Ollama up al 100% della sessione.** `fallback_counters.consecutive_fallback = 0`, resettato
all'ultimo scoring (19:45:27). Zero chiamate FinBERT: **FinBERT fallback rate = 0,0%**.

*Latenza per-chiamata: non misurabile.* Non esiste colonna di durata in `llm_responses` e i log del
25 non esistono più ([DAY-005]).

### 5.2 Esito dell'aggregazione

| Esito | Segnali | Quota |
|---|---:|---:|
| `ensemble:glm-5.2+gpt-oss` (due modelli) | 59 | 60,2% |
| `single:gpt-oss:20b-cloud` (glm sotto floor) | 30 | 30,6% |
| `single:glm-5.2:cloud` (gpt-oss sotto floor) | 9 | 9,2% |
| **Totale `fallback_used=true`** | **39** | **39,8%** |

`ENSEMBLE_MIN_CONFIDENCE = 0.4` (`src/config.py:256`). Un modello contribuisce solo con
confidence ≥ 0,4. glm-5.2 ha confidence mediana più bassa (0,322 vs 0,410) e viene quindi **silenziato
3,3 volte più spesso** di gpt-oss — nonostante pesi 0,70 nell'ensemble
(`weight_update_log` id 17, 2026-08-24: glm 0,70 / gpt-oss 0,30, `purified_icir` glm +0,104,
gpt-oss **−0,029**). Su 30 segnali del giorno la decisione è quindi presa dal modello a peso minore
e ICIR purificato negativo — e poi scartata a valle da SKIP_FALLBACK (#108).

### 5.3 Distribuzione degli score

| Bucket score | n | min | max |
|---|---:|---:|---:|
| [−0,4 ; −0,2) | 3 | −0,357 | −0,236 |
| [−0,2 ; 0,0) | 10 | −0,164 | −0,010 |
| [0,0 ; +0,2) | **68** | 0,000 | +0,198 |
| [+0,2 ; +0,4) | 14 | +0,201 | +0,385 |
| [+0,4 ; +0,6) | 2 | +0,420 | +0,581 |
| [+0,6 ; +0,8) | 1 | +0,680 | +0,680 |

Score medio +0,0732, confidence media 0,423, `ensemble_std` media 0,0354.
**Solo 9 segnali su 98 (9,2%) superano |0,30|.** Bias rialzista netto: 84/98 con score ≥ 0.

### 5.4 Disaccordo fra modelli

Segnali con polarity di segno opposto fra i due modelli: **3 su 98 (3,1%)**.

| Signal | Ticker | glm-5.2 | gpt-oss | Score finale | `ensemble_std` |
|---|---|---|---|---|---|
| 8864 | MRK | +0,30 / 0,45 | −0,10 / 0,40 | +0,081 | 0,283 |
| 8862 | META | −0,10 / 0,20 | +0,05 / 0,40 | +0,020 | 0,000 |
| 8947 | PLTR | −0,10 / 0,25 | +0,10 / 0,60 | +0,060 | 0,000 |

Nei due casi con `std = 0` il disaccordo **non è registrato** perché un modello era sotto il floor:
lo std è calcolato solo sui contributori, quindi un disaccordo di segno risulta varianza nulla.

### 5.5 Verifica funzionale della pipeline LLM

| Domanda | Risposta | Evidenza |
|---|---|---|
| L'output LLM è validato prima del signal store? | **Parzialmente.** Parsing JSON strutturato + floor di confidence + gate di divergenza. Nessuna validazione semantica né RAG contro la fonte. | `src/workers/sentiment.py:356-410` |
| L'ensemble gestisce varianza alta? | **Sì in ingresso all'aggregazione** (divergenza → FinBERT), **no come gate d'ordine**: `ensemble_std` non entra in nessuna decisione. CSCO comprata con std 0,2475, XLE venduta con std 0,2121. | F-037 |
| Le news duplicate pesano più volte? | **No** — 0 duplicati di sindacazione per ticker; `uq_news_log_url_ticker` + `duplicate_id`/`duplicate_content` in `news_queue_drops`. | `copertura_articoli.totali` |
| La stessa news può generare segnali multipli? | **Sì, per ticker distinti** (fan-out): l'articolo Cisco↔Nvidia ha generato 2 BUY correlate nello stesso ciclo. Non per lo stesso ticker. | §4.4 |
| Confidence bassa riduce il peso? | **No, è binaria**: sotto 0,4 il modello viene eliminato del tutto, non pesato meno. Sopra 0,4 pesa `polarity × confidence`. | `ENSEMBLE_MIN_CONFIDENCE` |
| I modelli sono chiamati offline/background? | **Sì.** Celery `worker-inference` (concurrency=1, queue `inference`), scrittura in Postgres; `portfolio-cycle` legge solo dal DB. Zero chiamate LLM nel path d'ordine. | `celery_app.py`, `portfolio_scheduler.py` |
| Un'allucinazione LLM può entrare in decisione? | **Sì.** Nessun supervisor agent, nessun grounding RAG. Il caso HOOD ([DAY-002]) mostra che il modello riproduce fedelmente un input errato senza alcun controllo a valle. Mitigazione reale: gate 0,30 + SKIP_FALLBACK + long-only. | §7, [DAY-002] |

---

## 6. Tabella segnali finali per ticker

Segnali che superano il gate d'ingresso (|score| ≥ 0,30; soglia S4 letta da Redis
`feedback:entry_threshold:S4 = 0.3`):

| ID | Ora | Ticker | Score | Conf. | `ensemble_std` | Modello | Esito | Motivo |
|---|---|---|---:|---:|---:|---|---|---|
| 8858 | 14:15 | NVDA | +0,330 | 0,60 | 0,000 | single:gpt-oss | **scartato** | SKIP_FALLBACK (#108) |
| 8892 | 16:15 | DELL | +0,581 | 0,78 | 0,000 | ensemble | **scartato** | SKIP_PYRAMIDING (a libro dal 13/07) |
| 8899 | 16:30 | MS | **+0,680** | 0,85 | 0,000 | single:gpt-oss | **scartato** | SKIP_FALLBACK — ticker errato |
| 8914 | 18:00 | XLE | −0,357 | 0,70 | 0,212 | ensemble | **SELL** | `sentiment_reversal` |
| 8937 | 18:46 | NVDA | +0,420 | 0,70 | 0,000 | single:gpt-oss | **scartato** | SKIP_FALLBACK |
| 8942 | 19:00 | CSCO | +0,320 | 0,63 | 0,248 | ensemble | **BUY** | rank 4, top-N |
| 8944 | 19:00 | NVDA | +0,378 | 0,70 | 0,141 | ensemble | **BUY** | rank 2, top-N |
| 8950 | 19:45 | META | +0,385 | 0,55 | 0,177 | ensemble | **BUY** | rank 2, top-N |
| 8952 | 19:45 | NVDA | +0,358 | 0,65 | 0,000 | single:gpt-oss | **scartato** | SKIP_FALLBACK |

**9 segnali sopra soglia → 3 ordini d'ingresso (33%).** Dei 6 scartati, 4 per single-model fallback,
1 per anti-pyramiding, 1 (XLE) usato in uscita anziché in ingresso (long-only).

### 6.1 Popolazione completa degli intenti S4 (ledger #294)

| `reason_code` | Intenti | Simboli | Tracce in `execution_decisions` |
|---|---:|---:|---:|
| `SKIP_ENTRY_FRESHNESS` | 572 | 36 | **0** |
| `SKIP_ENTRY_GATE` | 456 | 38 | 456 (`SKIP_THRESHOLD`) ✓ |
| `SKIP_STALE` | 315 | 21 | **3** |
| `SKIP_FALLBACK` | 74 | 7 | **7** |
| `SKIP_PYRAMIDING` | 70 | 5 (LLY 24, SOXX 24, DELL 15, MRVL 5, NVDA 2) | **4** |
| `SUBMITTED` | 3 | 3 | 3 ✓ |
| `SKIP_IDEMPOTENCY` | 3 | 1 | 0 |
| `RANK_OUTSIDE_TOP_N` | 1 | 1 | 0 |

Solo `SKIP_ENTRY_GATE` e `SUBMITTED` sono ricostruibili da `execution_decisions`. Il bucket più
grande (572 `SKIP_ENTRY_FRESHNESS`) non lascia alcuna traccia nella tabella storicamente usata
dall'analisi.

---

## 7. Tabella ordini generati / eseguiti

| # | Decisione | Ora decisione | Strategia | Ticker | Azione | Qty | Prezzo fill | Notional | Stato | Order ID | Trade | Segnale | Risk check | Anomalie |
|---|---|---|---|---|---|---:|---:|---:|---|---|---|---|---|---|
| 1 | 14577 | 18:07:00 | **S1** (posizione) / S4 (segnale) | XLE | SELL / close | 12,3722 | 62,50 | 773,26 | **filled** 18:07:07 | `e84311ee…` | 282 | 8914 | `sentiment_reversal` −0,357 < −0,35 | chiude posizione **non** S4 (F-033) |
| 2 | 14679 | 19:07:00 | S4 | NVDA | BUY | 8,9456 | 212,74 | 1 903,10 | **filled** 19:07:05 | `b7d149d1…` | 829 | 8944 | gate 0,30, rank 2, peso 2,0%, regime ×1,0 | — |
| 3 | 14680 | 19:07:00 | S4 | CSCO | BUY | 17,1357 | 111,06 | 1 903,10 | **filled** 19:07:05 | `b2856577…` | 830 | 8942 | gate 0,30, rank 4, peso 2,0%, regime ×1,0 | — |
| 4 | 14747 | 19:52:00 | S4 | META | BUY | 3,3410 | 569,43 | 1 902,45 | **filled** 19:52:04 | `b880b47b…` | 831 | 8950 | gate 0,30, rank 2, peso 2,0%, regime ×1,0 | ultimo ciclo → **nessuno stop** |

### 7.1 Ordini protettivi (stop GTC)

| Ora | Ticker | Qty stop | Qty posizione | Copertura | Stato |
|---|---|---:|---:|---:|---|
| 19:22:04 | NVDA | 8 | 8,945614 | **89,4%** | `new` (aperto) |
| 19:22:04 | CSCO | 17 | 17,135692 | **99,2%** | `new` (aperto) |
| — | META | — | 3,340955 | **0%** | **nessuno stop creato** |

Stop protettivi GTC attivi sull'intero libro: **8 su 48 posizioni**. 12 posizioni sono sotto 1 azione
e per costruzione non proteggibili (`skip_no_whole_share`, `src/portfolio/fractional_stop_orders.py:71`);
notional $5 492,86, UPL −$66,75.

### 7.2 Motore e ambiente

- `execution.engine = portfolio` → solo `portfolio-cycle` emette ordini. Confermato: nessun ordine
  da `run-execution`.
- **Paper**, non live: `portfolio_monitor_snapshots.pipeline_health…portfolio.source = "alpaca_paper"`,
  `operational.mode = "paper"`; strategie `S1: supervised_paper (approved=false, alloc 0.50)`,
  `S4: paper (approved=false, alloc 0.10)`. **Distinzione paper/live esplicita e coerente.**
- 24 cicli portfolio, tutti `strategies_run = ["S1","S4"]`, `constraints_fired = []` in ognuno.
- Circuit breaker / kill-switch: nessun banner di halt in Redis, `alerts = []` in `risk_reports`,
  `active_incident_count = 0`. **Nessun blocco attivo.**

---

## 8. Tabella PnL / rendimento

### 8.1 Realizzato

| Trade | Ticker | Strategia | Entry | Exit | Qty | Gross | Costi | **Net** | Motivo |
|---|---|---|---|---|---:|---:|---:|---:|---|
| 282 | XLE | S1 (entry 2026-07-10, decisione 2318) | 55,05 | 62,50 | 12,3722 | +92,17 | 0,37 | **+91,80** | `sentiment_reversal` |

**Realizzato totale del giorno: +$91,80** su 1 trade chiuso. Tenuta 1 108,0 ore (46,2 giorni).
`drift_post_uscita = −$5,44` → l'uscita ha evitato una perdita ulteriore di 5,44 $ entro il close.

### 8.2 Non realizzato — posizioni aperte il 2026-08-25

| Ticker | Entry | Qty | Notional | MTM al close | vs apertura giornata | Percentile d'ingresso |
|---|---:|---:|---:|---:|---:|---:|
| NVDA | 212,74 | 8,9456 | 1 903,10 | **+2,77** | +18,11 | 0,569 |
| CSCO | 111,06 | 17,1357 | 1 903,10 | **+0,86** | −19,19 | 0,240 |
| META | 569,43 | 3,3410 | 1 902,45 | **+2,07** | +20,61 | **0,854** |
| **Totale** | | | **5 708,65** | **+5,70** | | mediana 0,569 |

`vs apertura` = differenza fra il P&L ottenuto e quello di un ingresso all'apertura RTH: CSCO ha
perso $19,19 entrando tardi, NVDA e META ne hanno guadagnati ~$19-21.

### 8.3 Non realizzato — posizioni aperte prima del 2026-08-25

Libro complessivo a fine giornata: **48 posizioni**, market value **$36 030,43**,
unrealized P&L **+$1 097,65** (snapshot 20:00:00). Al netto dei 3 ingressi del giorno (+$5,70),
il contributo delle posizioni preesistenti all'UPL è **+$1 091,95**.

### 8.4 Scomposizione decision-quality (dossier, read-only)

| Asse | USD |
|---|---:|
| `passive_pnl_usd` (libro all'apertura, tenuto fermo) | **−6,46** |
| `selection_pnl_usd` (i 3 ingressi del giorno) | **+5,70** |
| `exit_effect_usd` (la SELL XLE) | **+10,89** |
| `active_decision_pnl_usd` | **+16,59** |
| `actual_intraday_pnl_usd` | **+10,13** |
| `market_beta_1_usd` (quota spiegata da SPY) | −10,51 |
| `sector_beta_1_incremental_usd` | *null* |
| Assi additivi? | **no** (dichiarato dal dossier) |

### 8.5 NAV e P&L economico della finestra

| Data | NAV close | Δ | Note |
|---|---:|---:|---|
| 2026-08-24 | 109 864,64 | — | |
| **2026-08-25** | **109 958,17** | **+93,53** (+0,085%) | SPY +0,32%, QQQ +0,62% |

P&L economico cumulato dal 2026-08-03 (`docs/evidence/economic_pnl.json`, mark dal close del primo
giorno di finestra):

| Sleeve | 24/08 | **25/08** | Δ giorno | Capitale di riferimento |
|---|---:|---:|---:|---:|
| S1 | +612,38 | **+718,72** | **+106,34** | 33 229,16 |
| S4 | −505,34 | **−453,82** | **+51,52** | 68 154,04 |
| CONTAMINAZIONE | +95,24 | +125,15 | +29,92 | 8 348,07 |
| **BOOK** | +202,27 | **+390,05** | **+187,78** | 109 731,28 |

> **Cautela obbligata (deroga #182(a), pre-registrata il 2026-08-25):** la serie realizzata di S1 di
> questa giornata contiene un'uscita `sentiment_reversal` decisa da S4 (XLE, +$91,80). Il P&L
> realizzato di S1 **prima e dopo il deploy di #182(a) non sarà sommabile**. Il +$106,34 di S1 di oggi
> è per l'86% questa singola uscita.

### 8.6 Slippage e costi

| Metrica | Valore | Nota |
|---|---:|---|
| Costi modellati del giorno (3 entry + 1 exit) | **$2,07** | `cost_usd`: NVDA 0,344 · CSCO 1,010 · META 0,344 · XLE 0,373 |
| Slippage stimato | **non misurato** | `trades.slippage_est` è una copia esatta di `cost_usd` (XLE: 0,3726207086754916 su entrambi i campi) — F-015 |
| Commissioni broker | $0 (Alpaca paper, commission-free) | |

**Cosa manca per una misura di slippage vera:** il prezzo di riferimento al momento della decisione
(NBBO mid o open della barra al `tick_time`) non è persistito accanto al fill. Query necessaria:
`SELECT t.symbol, d.tick_time, t.entry_time, t.entry_price FROM trades t JOIN execution_decisions d ON d.id = t.decision_id`
affiancata alle quote SIP al `tick_time` — oggi ricostruibile solo ex-post da Alpaca, non dal DB.

---

## 9. Analisi correttezza buy/sell

| Controllo | Esito | Evidenza |
|---|---|---|
| BUY solo quando consentito | ✅ | 3 BUY, tutte con score ≥ 0,30, ensemble a due modelli, rank in top-N, `ema_pass=true`, `regime_mult=1.0`, peso 2,0% ciascuna |
| SELL/exit generate correttamente | ⚠️ | XLE: regola `sentiment_reversal` applicata correttamente, ma su posizione **S1**, da segnale **S4**, su articolo macro a 10 ticker. Meccanismo già deciso da rimuovere (deroga #182(a)) |
| Stop-loss rispettati | ⚠️ | Nessuno stop scattato. Stop GTC creati **un ciclo dopo** l'ingresso e solo sulla parte intera; **META senza stop** |
| Signal flip rispettato | ✅ | Nessun flip osservato |
| Max holding days rispettato | ✅ | Nessuna uscita per scadenza; `SKIP_STALE` (>4h) e `SKIP_ENTRY_FRESHNESS` (>2h) applicati coerentemente in ingresso |
| Rebalance band rispettata | ✅ | `constraints_fired = []` in tutti i 24 cicli; nessun rebalance emesso |
| Ordini duplicati | ✅ **nessuno** | 0 righe con `(symbol, decision, minuto)` ripetuti |
| Ordini contrari ravvicinati | ✅ **nessuno** | Nessun simbolo con BUY e SELL nella stessa giornata |
| Roundtrip < 30 min | ✅ **nessuno** | — |
| Pyramiding (>3 BUY consecutive senza SELL) | ✅ **nessuno** | Guard P0-05 attivo: 70 intenti bloccati su 5 simboli |
| SELL con sentiment positivo (bug A5) | ✅ **nessuno** | Unica SELL con `signal_score = −0,357` |
| Ordini su ticker non consentiti | ✅ | Tutti e 4 in watchlist |
| Ordini fuori orario | ✅ **nessuno** | Tutti fra 18:07 e 19:52 UTC, dentro 13:30–20:00 |
| Ordini senza risk check | ✅ **nessuno** | Ogni decisione porta `regime_mult`, `ema_pass`, rank, peso |
| Trade su dati stale | ✅ | 3 `SKIP_STALE` + 572 `SKIP_ENTRY_FRESHNESS` hanno funzionato |
| Trade con output LLM non valido | ✅ | 7 `SKIP_FALLBACK` hanno escluso i single-model dal ranking BUY |
| Trade con circuit breaker attivo | ✅ n/a | Nessun breaker attivo |
| Trade con strategia disabilitata | ✅ | S1 e S4 entrambe attive (`approved=false` = paper, corretto) |
| Coerenza paper/live | ✅ | `mode: paper`, `source: alpaca_paper` su tutti gli snapshot |
| Idempotenza retry Celery | ✅ | 3 `SKIP_IDEMPOTENCY` registrati — il guard funziona |
| Riconciliazione ordini↔fill↔posizioni | ⚠️ | Tutti e 4 gli ordini hanno trade e posizione corrispondenti; **ma** i 3 ingressi risultano `CENSORED` nel lifecycle S4 ([DAY-003]) |
| Ordini broker senza segnale/decisione | ✅ **nessuno** | Query di riconciliazione: 0 righe orfane |
| Score < 0,05 che generano ordini | ✅ **nessuno** | — |
| Ordini identici nello stesso minuto | ✅ **nessuno** | — |

### Avvertenza `exit_mechanism` (#184)

`execution_decisions.exit_mechanism` è **NULL su tutte le 474 righe del 2026-08-25**, incluse le 4
non-SKIP. Nessun conteggio o interpretazione di `exit_mechanism` è quindi possibile per questa
giornata, né come misura né come stima per età. Il presente report **non usa** quel campo.
Vedi `docs/exit_mechanism_labels.md`.

---

## 10. Anomalie trovate

### [DAY-001] Il dossier legge `is_tradable` con un confronto che non può mai essere vero: l'aggregato della guardia ombra #335 è zero per costruzione

* **Tipo:** Bug
* **Area:** Data / Ops (strumentazione dell'evidenza)
* **Ledger:** **F-045** (nuovo)
* **Evidenza:**
  * file: `scripts/alpha_miner_dossier.py:822` e `:847`
  * tabella: `s4_intent_events`, `docs/evidence/dossier/2026-08-25.json` → `aggregati.guardia_contraddizione`
  * timestamp: dossier generato 2026-08-26T08:01:43Z sui dati del 2026-08-25
  * query:
    ```sql
    -- DB: 76 dispositions tradabili
    SELECT reason_code, is_tradable, count(*) FROM s4_intent_events
    WHERE event_type='disposition' AND decision_slot >= '2026-08-25'
    GROUP BY 1,2;
    -- SKIP_PYRAMIDING|t|70   SKIP_IDEMPOTENCY|t|3   SUBMITTED|t|3
    ```
    ```
    -- dossier: 0 tradabili su 1494
    "guardia_contraddizione": {"giorno": {"n_intenti": 1494,
      "n_intenti_tradabili": 0, "n_valutabili": 0, "n_soppressi": 0, ...}}
    ```
* **Descrizione:** la query seleziona `COALESCE(disposition.is_tradable::text,'')`. In PostgreSQL il
  cast di un booleano a `text` produce `'true'`/`'false'`, non `'t'`/`'f'`. Il parser Python testa
  `row[7] == "t"`, che **non corrisponde mai**. Verificato:
  `SELECT true::text` → `true`. Conseguenza: `is_tradable` è `False` su tutte le 1 494 righe del
  dossier, comprese le 3 con `reason_code = SUBMITTED` che hanno effettivamente prodotto ordini
  eseguiti e riempiti. L'aggregato `guardia_contraddizione`, la cui definizione dichiarata è
  «*l'aggregato 'soppressi' include solo gli intenti con `disposition.is_tradable=true`*»
  (`scripts/alpha_miner_dossier.py:1461`), filtra quindi su un insieme sempre vuoto:
  `n_valutabili = 0`, `n_soppressi = 0`, `somma_pnl_realizzato_soppressi = 0.0`.
* **Impatto:** la strumentazione step-2 di #335, deployata il 2026-08-25 (commit `d5dacc3`), misura
  **zero per costruzione** dal suo primo giorno di vita. La domanda che deve rispondere — quanti
  intenti *tradabili* la guardia di contraddizione avrebbe soppresso, e con quale P&L — resta senza
  risposta, e senza che nulla lo segnali: uno zero è indistinguibile da «la guardia non scatta mai».
  Lo stesso campo alimenta `n_intenti_tradabili` e `n_intenti_non_tradabili`, che risultano
  rispettivamente 0 e 1 494 in ogni dossier futuro. Il difetto è **retroattivo su tutti i dossier
  schema 2.5** e sul cumulato di finestra, che rilegge i file già scritti.
* **Severità:** **Critical** (per l'evidenza; nessun impatto sul money-path)
* **Confidenza:** **High** — comportamento riprodotto direttamente sul DB.
* **Azione consigliata:** ticket di remediation. Sostituire il confronto con
  `row[7] == "true"` (o meglio: non castare a `text` e usare un adattatore booleano esplicito), e
  **rigenerare i dossier già scritti dello schema 2.5** perché il cumulato di finestra li rilegge.
  Passa il test di esenzione della `OBSERVATION_CHARTER.md`: senza la correzione, l'evidenza raccolta
  nelle settimane restanti è sbagliata. Non è taratura: nessuna soglia, peso o flag cambia.
* **Test/monitor consigliato:** test unitario che feeda una riga con `is_tradable = true` e asserisce
  `dossier["intenti_ingresso_s4"][i]["is_tradable"] is True`; assertion di sanità nel dossier —
  se `n_intenti_tradabili == 0` **e** esiste almeno un `reason_code == "SUBMITTED"`, alzare un
  `missingness` esplicito invece di scrivere zero.

---

### [DAY-002] Il modello riceve solo il corpo dell'articolo, mai il titolo: su HOOD (+8,17%, mover #1) il corpo descriveva un'altra giornata e i due modelli hanno scorato −0,01

* **Tipo:** Bug
* **Area:** News / LLM
* **Ledger:** **F-046** (nuovo)
* **Evidenza:**
  * file: `src/workers/sentiment.py:356` — `prompt = _DK_COT_PROMPT.format(text=clean_body[:_body_limit], symbol=clean_symbol)`; il titolo non compare nel prompt
  * file: `src/connectors/alpaca_news.py:156-166` — `body = summary` (preferito) o `content` ripulito; `headline` viene letto ma usato solo per `news_log.title`
  * tabella: `news_log` id **8902**, `llm_responses` signal_id 8902, `sentiment_signals` id 8902
  * timestamp: 2026-08-25 16:45:15 UTC
  * snippet:
    ```
    title:        "Why Is Robinhood Stock Surging on Tuesday?"
    body_snippet: "Robinhood Markets Inc. (NASDAQ: HOOD) stock traded lower Thursday
                   after a White House crypto summit and analyst debate."
    glm-5.2:cloud     pol  0.00  conf 0.20  "...traded lower following a White House crypto summit..."
    gpt-oss:20b-cloud pol -0.10  conf 0.30  "Robinhood's stock slipped after the White House crypto summit..."
    → score finale -0.0098   (HOOD chiude a +8,17%)
    ```
* **Descrizione:** due difetti che si compongono. (1) Il titolo — spesso l'unica parte
  dell'articolo che contiene la direzione — **non viene mai inviato al modello**. (2) Nel campo
  `summary` di Benzinga può arrivare un teaser di un articolo diverso: qui il titolo dice "Surging…
  on Tuesday", il corpo dice "traded lower **Thursday**" e cita un evento (summit cripto alla Casa
  Bianca) non pertinente alla seduta. I due modelli hanno analizzato correttamente il testo che
  hanno ricevuto; il testo era sbagliato. Non è un problema di ticker (HOOD è corretto) né di
  fan-out (`n_ticker_articolo = 1`, `relevance = ISSUER_SPECIFIC`, `attribution = ISSUER_SPECIFIC`
  secondo il dossier stesso): è l'**unico** articolo issuer-specific su HOOD della giornata, ed è
  stato scorato −0,01.
* **Impatto:** HOOD è il mover #1 della seduta (+8,17%) e uno dei 4 candidati miss del dossier, con
  causa dichiarata `BELOW_GATE`. La causa reale non è la soglia: è che l'informazione direzionale
  disponibile non è mai arrivata al modello. Struttturalmente, ogni articolo in cui il titolo porta
  il segnale e il corpo è un teaser generico produce un punteggio vicino a zero — e la finestra di
  osservazione lo registra come «la news non ha alpha» quando la news non è mai stata letta per
  intero. È l'errore che rende inutilizzabile la domanda di uscita n.1.
* **Severità:** **High**
* **Confidenza:** **High** (codice + riga di DB + risposte dei due modelli)
* **Azione consigliata:** ticket di remediation. Includere `title` nel prompt DK-CoT come campo
  distinto dal corpo (non concatenato: il modello deve poter pesare la contraddizione), e aggiungere
  un flag di **incoerenza titolo↔corpo** nel record di scoring quando i due divergono di direzione.
  Passa il test di esenzione: non è taratura, è l'input della misura. Il perimetro va limitato
  all'aggiunta del titolo — soglie, floor di confidence e pesi restano congelati.
* **Test/monitor consigliato:** test che verifica la presenza del titolo nel prompt renderizzato;
  monitor giornaliero sulla quota di articoli in cui il corpo cita un giorno della settimana diverso
  da quello del titolo o da `published_at`.

---

### [DAY-003] La classificazione RTH del lifecycle S4 legge i datetime naive del calendario Alpaca come UTC: 3 fill su 3 censurati, orologio D+2 mai armato

* **Tipo:** Bug
* **Area:** Orders / Data (DST/timezone)
* **Ledger:** **F-047** (nuovo)
* **Evidenza:**
  * file: `src/strategies/s4/lifecycle.py:20-23` (`_utc`: `value.replace(tzinfo=timezone.utc)` su input naive) e `:130-147` (`_session_dates`)
  * file: `src/workers/performance.py:118-127` — costruisce `MarketSession` da `GetCalendarRequest`
  * libreria: `alpaca/trading/models.py:374-385` — `Calendar.open`/`close` sono `datetime.strptime(f"{date} {HH:MM}", "%Y-%m-%d %H:%M")` → **naive, in ora locale di New York**
  * tabella: `s4_lifecycle_events`, 2026-08-25
  * snippet:
    ```
    NVDA | filled_at 19:07:05Z | CENSORED | FILL_OUTSIDE_RTH | d0 NULL | due_session NULL | reconstructible f
    CSCO | filled_at 19:07:05Z | CENSORED | FILL_OUTSIDE_RTH | d0 NULL | due_session NULL | reconstructible f
    META | filled_at 19:52:04Z | CENSORED | FILL_OUTSIDE_RTH | d0 NULL | due_session NULL | reconstructible f
    ```
    Riproduzione:
    ```python
    op = datetime.strptime('2026-08-25 09:30', '%Y-%m-%d %H:%M')   # naive, EDT
    _utc(op)  # -> 2026-08-25 09:30:00+00:00   (invece di 13:30Z)
    ```
* **Descrizione:** il calendario Alpaca restituisce apertura 09:30 e chiusura 16:00 come datetime
  **naive** espressi in `America/New_York`. `_utc()` li marca come UTC senza convertirli, quindi la
  finestra RTH usata dal riconciliatore diventa **09:30–16:00 UTC** invece di **13:30–20:00 UTC**:
  spostata indietro di 4 ore (5 in EST). Un fill è classificato "dentro sessione" solo se cade fra
  13:30 e 16:00 UTC, cioè nelle **prime 2,5 ore su 6,5** della seduta. Tutto ciò che accade dopo le
  12:00 di New York finisce `FILL_OUTSIDE_RTH`. Il 2026-08-25 i tre ingressi sono avvenuti alle
  19:07 e 19:52 UTC: **3 su 3 censurati**, `reconstructible = false`.
* **Impatto:** con `d0` e `due_session` a NULL l'orologio di uscita D+2 di #334 **non si arma mai**
  per gli ingressi pomeridiani, e infatti `s4_exit_policy_events` ha **zero righe** per la giornata.
  La riconciliazione shadow #295, deployata il 2026-08-25, non produce una sola osservazione
  utilizzabile al suo primo giorno. Il bug è **sistematico e sbilanciato**: censura selettivamente il
  62% della sessione, quindi qualunque statistica costruita sulle righe non censurate è distorta
  verso le prime ore del mattino. Non è la stessa cosa di F-021 (finestre beat a ora UTC fissa):
  quello è lo *scheduler*, questo è la *coercizione di un datetime naive* in un modulo diverso, con
  effetto su tabelle diverse.
* **Severità:** **High**
* **Confidenza:** **High** — riprodotto numericamente, coerente con 3/3 righe osservate.
* **Azione consigliata:** ticket di remediation. Localizzare i datetime del calendario ad
  `America/New_York` prima della conversione a UTC (`ZoneInfo("America/New_York").localize`-equivalente),
  oppure usare `session.date` + gli orari dichiarati con tz esplicita. Passa il test di esenzione:
  senza correzione, il ledger di lifecycle e l'orologio D+2 raccolgono dati sbagliati per tutte le
  settimane restanti. Nessuna soglia o parametro di strategia cambia.
* **Test/monitor consigliato:** test unitario con calendario naive `09:30/16:00` e fill alle 19:07Z
  che asserisce `reason_code is None` e `d0 == date(2026,8,25)`; monitor che alza un alert se la
  quota di `FILL_OUTSIDE_RTH` su fill con `broker_status = filled` supera lo 0%.

---

### [DAY-004] Il bearer token del protocollo forense è rifiutato da tutti gli endpoint REST: l'header giusto è `X-API-Key`

* **Tipo:** Ambiguità (documentazione operativa)
* **Area:** Ops
* **Ledger:** **F-041** (4ª occorrenza)
* **Evidenza:**
  * comando: `curl -H "Authorization: Bearer eJvMeu…" http://localhost:8001/api/positions`
  * risposta: `{"detail":"Invalid or expired JWT token"}` su decisions, trades, signals, positions, orders
  * file: `src/api/auth.py:1` — *"Authentication middleware: accepts JWT Bearer token **OR** X-API-Key header"*; `:12` `APIKeyHeader(name="X-API-Key")`
  * verifica: `curl -H "X-API-Key: eJvMeu…"` → **200 OK**, payload completo
* **Descrizione:** la chiave fornita nel prompt del cron è una API key statica, non un JWT. Passata
  come `Authorization: Bearer` viene instradata sul ramo JWT del middleware e rifiutata. Il ramo
  `X-API-Key` la accetta senza problemi. La chiave **non è scaduta**: è l'header del prompt a essere
  sbagliato.
* **Impatto:** ogni sessione forense spreca il primo tentativo su tutti e cinque gli endpoint e
  rischia di concludere «API non accessibili» e degradare l'analisi. È la quarta ricorrenza.
* **Severità:** **Low**
* **Confidenza:** **High**
* **Azione consigliata:** correggere l'header nel prompt del cron forense
  (`scripts/daily_alpha_miss_analysis.sh` / definizione del cron) da `Authorization: Bearer <k>` a
  `X-API-Key: <k>`. Nessuna modifica al codice.
* **Test/monitor consigliato:** smoke test nello script di cron che verifica un 200 su
  `/api/positions` prima di iniziare l'analisi e fallisce rumorosamente altrimenti.

---

### [DAY-005] I log dei container non sopravvivono al redeploy: la giornata analizzata non ha più log

* **Tipo:** Anomalia
* **Area:** Ops
* **Ledger:** **F-027** (11ª occorrenza)
* **Evidenza:**
  * comando: `docker compose logs worker --since 72h | grep -c "2026-08-25"` → **0**
  * idem per `worker-inference`, `beat`, `api`: **0 righe** con la data target
  * `docker compose ps`: api, beat, worker, worker-inference tutti `Up 2 hours` (redeploy ~10:30 del 2026-08-26)
* **Descrizione:** i container sono stati ricreati e i log precedenti eliminati. Nessuna riga del
  2026-08-25 è recuperabile da nessun servizio applicativo.
* **Impatto:** non ricostruibili per la giornata: latenza per-chiamata LLM, retry HTTP, eccezioni
  gestite, warning del semaforo Ollama, warning `_sync_fractional_protective_stops`, riavvii worker,
  esito dell'`AlpacaNewsAuthError`. Le sezioni 5 (latenza) e 16 (restart events) di questo report
  restano parzialmente non verificabili. Undicesima ricorrenza.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — driver di logging persistente (bind mount su
  `logs/` o log driver `journald`/`json-file` con volume) per i quattro servizi applicativi.
  È strumentazione, non taratura.
* **Test/monitor consigliato:** check nello script forense che, se `docker compose logs <svc> --since 48h`
  non contiene la data target, lo dichiari esplicitamente nel report invece di riportare "nessun errore".

---

### [DAY-006] `llm_responses.eligible` non identifica i contributori reali e il ramo single-model scarta il modello a peso maggiore

* **Tipo:** Bug
* **Area:** LLM
* **Ledger:** **F-010** (10ª occorrenza)
* **Evidenza:**
  * tabella: `llm_responses`, `sentiment_signals` 2026-08-25
  * query:
    ```sql
    SELECT s.model_id, count(*) n,
           sum(CASE WHEN e.n_elig=0 THEN 1 ELSE 0 END) zero_elig
    FROM sentiment_signals s JOIN (SELECT signal_id, sum(eligible::int) n_elig
      FROM llm_responses WHERE generated_at::date='2026-08-25' GROUP BY 1) e ON e.signal_id=s.id
    WHERE s.generated_at::date='2026-08-25' GROUP BY 1;
    -- ensemble:glm+gptoss | 59 | 33      <-- 33 ensemble con ZERO contributori "eligible"
    -- single:glm-5.2      |  9 |  9
    -- single:gpt-oss      | 30 | 30
    ```
  * file: `src/workers/sentiment.py:707-711` — `force_ineligible=result.fallback_used` marca
    `eligible=False` **entrambe** le risposte, inclusa quella che ha prodotto il punteggio
* **Descrizione:** su 98 segnali, solo 26 hanno entrambe le risposte marcate `eligible`. 33 segnali
  etichettati `ensemble:` hanno **zero** contributori eligible, e tutti i 39 single-model ne hanno
  zero — compresa la risposta che ha generato lo score. Il campo è quindi inutilizzabile per
  ricostruire chi ha contribuito, ed è lo stesso campo che alimenta LOO-ICIR. In parallelo,
  `ENSEMBLE_MIN_CONFIDENCE = 0.4` elimina il modello sotto floor invece di pesarlo meno: glm-5.2
  (confidence mediana 0,322, **peso 0,70**, ICIR purificato +0,104) viene escluso 30 volte,
  gpt-oss (0,410, peso 0,30, ICIR purificato **−0,029**) solo 9. In 30 casi su 98 la decisione è
  presa dal modello meno pesato e con ICIR negativo — e poi buttata via da SKIP_FALLBACK.
* **Impatto:** 39,8% del lavoro di scoring della giornata è scartato a valle, inclusi 4 dei 9
  segnali sopra soglia: NVDA +0,330 (14:15), MS +0,680 (16:30), NVDA +0,420 (18:46), NVDA +0,358
  (19:45). Controfattuale corto sul solo caso ben attribuito (NVDA 14:15, primo ciclo 14:22 @ 213,20,
  close 213,30, slot $1 903): **+$0,89** lasciati sul tavolo. Il caso MS (+$7,97 sullo stesso calcolo)
  **non** è contabilizzato qui perché il ticker era sbagliato (F-020): comprarlo sarebbe stato un
  errore, non un guadagno mancato. Il costo del giorno è quindi piccolo; ciò che pesa è la
  ricorrenza e il fatto che i pesi LOO-ICIR sono neutralizzati sul 30% del flusso.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation limitato all'**etichettatura**: `eligible` deve
  riflettere chi ha effettivamente contribuito al punteggio persistito. Il floor di confidence
  (0,4) è **taratura** e resta congelato fino al 2026-09-28.
* **Test/monitor consigliato:** invariante in test — per ogni `sentiment_signals` con
  `model_id LIKE 'single:%'` esiste esattamente **una** `llm_responses` con `eligible = true`, e per
  `model_id LIKE 'ensemble:%'` esattamente due. Monitor giornaliero sulla quota `fallback_used`.

---

### [DAY-007] `execution_decisions.signal_id` NULL su 466 righe su 474: la catena segnale→decisione→trade non è ricostruibile per chiave esterna

* **Tipo:** Bug
* **Area:** Signal / Data
* **Ledger:** **F-011** (14ª occorrenza)
* **Evidenza:**
  * query:
    ```sql
    SELECT decision, count(*), sum((signal_id IS NULL)::int) FROM execution_decisions
    WHERE tick_time::date='2026-08-25' GROUP BY 1;
    -- SKIP_THRESHOLD  |456|456   SKIP_FALLBACK|7|7   SKIP_STALE|3|3
    -- SKIP_PYRAMIDING |  4|  1   BUY|3|0   SELL|1|0
    ```
* **Descrizione:** **98,3% delle righe (466/474)** ha `signal_id` NULL. Solo le 4 decisioni operative
  e 3 SKIP_PYRAMIDING lo portano. Il `reason` contiene lo score come testo libero
  (`"score 0.267 < feedback threshold 0.300"`), non un riferimento.
* **Impatto:** impossibile ricostruire per join quale segnale abbia prodotto quale scarto; l'analisi
  deve ri-derivarlo per stringa e per timestamp, con rischio di attribuzione errata. Colpisce
  direttamente il calcolo dei controfattuali sugli scarti, che è il cuore della domanda di uscita
  n.1. Il nuovo ledger `s4_intent_events` (#294) copre parzialmente il buco per S4, ma
  `execution_decisions` resta la tabella storica su cui si basa la serie dal 2026-08-03.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — popolare `signal_id` su tutte le decisioni,
  incluse le SKIP. Cambio di sola tracciabilità, nessun effetto sul comportamento.
* **Test/monitor consigliato:** vincolo o test che asserisce `signal_id IS NOT NULL` su ogni
  decisione il cui `reason` cita uno score.

---

### [DAY-008] 59,2% delle righe scorate nasce da articoli multi-ticker su società terze

* **Tipo:** Bug
* **Area:** News
* **Ledger:** **F-012** (18ª occorrenza)
* **Evidenza:**
  * query: 58 righe su 98 provengono da 15 articoli con più di un ticker; distribuzione in §4.4
  * casi: INTC ← *"Bloom Energy Stock Rises as Pelosi-Linked Trades Draw Fresh Attention"*;
    MU ← *"SanDisk Stock Climbs As NAND Optimism Lifts Memory Stocks"*;
    MRK ← *"Moderna Stock Edges Higher Tuesday"*;
    CSCO e NVDA ← *"What's Going On With Super Micro Computer Stock Tuesday?"*;
    META e SPCX ← *"OpenAI Uncovers a Covert Russian Influence Machine…"*;
    AMD, INTC, MSFT, NVDA ← *"What's Going On With Dell Technologies Stock Tuesday?"*
  * dossier: `mapping_fanout_extra = 43`, `mapping_rilevanza.UNKNOWN = 77` su 98
* **Descrizione:** i tag `symbols` del provider generano una riga per ticker anche quando la società
  compare solo di sfondo. 77 righe su 98 hanno rilevanza `UNKNOWN` — cioè il classificatore non è
  in grado di dire se l'articolo parli davvero di quel titolo.
* **Impatto:** **costo del giorno: nessuno stimabile.** I tre ordini emessi provengono da articoli
  genuinamente pertinenti (Cisco↔Nvidia per CSCO e NVDA, Evercore↔Meta per META). Il fan-out ha
  però prodotto la SELL su XLE da un market-wrap a 10 ticker (vedi [DAY-009]) e occupa il 59% della
  capacità di scoring con righe di rumore, che si traduce in punteggi vicini a zero e nel bias
  osservato (68/98 segnali nel bucket [0 ; 0,2)).
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** nessuna azione in freeze — la soppressione del fan-out è taratura.
  Continuare a registrare la ricorrenza; il campo `mapping_rilevanza` esiste già e va usato come
  gate solo dopo il golden set QX-01.
* **Test/monitor consigliato:** monitor sulla quota `UNKNOWN` del mapping di rilevanza; alert se
  supera l'80% (oggi 78,6%).

---

### [DAY-009] Un market-wrap macro a 10 ticker forza l'uscita da una posizione S1 tenuta 46 giorni

* **Tipo:** Bug
* **Area:** Signal / Orders
* **Ledger:** **F-008** (7ª occorrenza)
* **Evidenza:**
  * `news_log` id 8914: *"Bitcoin Tops $80,000, Oil Sinks As Navy Clears Hormuz Mines: Stock Market Today"*,
    published 17:01:06, fetched 18:00:12, 10 ticker (AMD, HOOD, IWM, MRVL, MU, NVDA, QQQ, XLE, XLK, XLV)
  * `sentiment_signals` 8914: XLE **−0,357**, conf 0,70, `ensemble_std` 0,212
  * `execution_decisions` 14577, 18:07:00: `SELL` — *"sentiment_reversal: score -0.357 < threshold -0.35"*
  * `trades` 282: XLE, entry 2026-07-10 @ 55,05, exit 62,50, **+$91,80 net**, tenuta 1 108 h,
    `drift_post_uscita = −5,44`
* **Descrizione:** l'articolo è una cronaca di mercato generalista; l'unico riferimento all'energia è
  «*Brent slid below $90*». Il punteggio ticker-specifico che ne deriva (−0,357) supera di 7 millesimi
  la soglia di uscita (−0,35) e liquida una posizione aperta da 46 giorni.
* **Impatto:** **costo misurato −$5,44** (`drift_post_uscita`, trade 282): entro la chiusura XLE è
  sceso ancora, quindi *questa volta* l'uscita ha evitato una perdita. Il difetto resta:
  la decisione è stata presa da un articolo che non parla del titolo, e l'esito favorevole è
  coincidenza — XLE ha chiuso a −1,66% in una giornata di rotazione fuori dall'energia.
  Il margine sopra soglia (0,007) mostra quanto sia fragile.
* **Severità:** **Medium**
* **Confidenza:** **High** (misurata: net_pnl e drift del trade 282)
* **Azione consigliata:** nessuna in freeze (la soglia di uscita è taratura). Il perimetro della
  deroga #182(a) già pre-registrata copre il caso adiacente (chiusura di posizioni non-S4) ma **non**
  il caso «articolo macro che genera un punteggio ticker-specifico».
* **Test/monitor consigliato:** registrare, per ogni uscita `sentiment_reversal`, il numero di ticker
  dell'articolo causante e la rilevanza mappata; alert se un'uscita nasce da un articolo con più di
  5 ticker o rilevanza `UNKNOWN`.

---

### [DAY-010] `sentiment_reversal` di S4 liquida una posizione S1 e il P&L resta attribuito a S1

* **Tipo:** Rischio
* **Area:** PnL
* **Ledger:** **F-033** (3ª occorrenza)
* **Evidenza:**
  * `trades` 282: XLE, aperta da `execution_decisions` 2318 (2026-07-10, *"S1 momentum: time-series momentum signal, portfolio weight 1.4%"*), chiusa da `execution_decisions` 14577 (segnale S4 8914)
  * `stop_strategy` NULL sul trade 282 (riga legacy pre-patch, F-002)
  * dossier `chiusure[0].strategia = "S1"`; `economic_pnl.json` attribuisce l'intero +$91,80 a S1
  * `s4_intent_events`: nessun intento S4 su XLE — S4 non ha mai detenuto la posizione
* **Descrizione:** la variazione di P&L economico di S1 del giorno è **+$106,34**, di cui **+$91,80
  (86%)** proviene da un'uscita decisa da S4.
* **Impatto:** la serie realizzata di S1 — che deve rispondere alla domanda di uscita n.2 «S1 ha un
  edge?» — è prodotta per una quota rilevante da decisioni di S4. Il 2026-08-25 è pre-deploy della
  deroga #182(a), quindi la discontinuità dichiarata nella carta non è ancora avvenuta e questa
  giornata cade nel regime "vecchio".
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** nessuna azione di codice: #182(a) è già deciso, pre-registrato nella carta
  e in attesa di deploy. Marcare esplicitamente questa giornata come pre-deploy nella sintesi del 28/09.
* **Test/monitor consigliato:** colonna derivata `exit_decided_by_strategy` accanto a `stop_strategy`,
  così che l'attribuzione dell'uscita sia leggibile senza risalire a `execution_decisions`.

---

### [DAY-011] Telemetria del ciclo portfolio: 76 "ordini" contati, 4 realmente inviati

* **Tipo:** Bug
* **Area:** Ops / Frontend
* **Ledger:** **F-014** (13ª occorrenza)
* **Evidenza:**
  * query: `SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-08-25'` → **76**
  * ogni ciclo riporta `orders_count` 2, 3 o 5; nessun ciclo riporta 0
  * ordini realmente submitted alla giornata: **4** (3 BUY + 1 SELL) + 2 stop protettivi
  * `constraints_fired = []` su tutti e 24 i cicli, anche su quelli con 4 SKIP registrati
* **Descrizione:** `orders_count` conta gli ordini *obiettivo* del combiner, non quelli inviati. Nel
  ciclo delle 19:07, che ha effettivamente prodotto 2 BUY, il campo vale 5; nei cicli 14:07–19:52 che
  non hanno prodotto nulla vale comunque 2-5. `constraints_fired` resta vuoto anche quando 4
  decisioni di SKIP sono state scritte nella stessa transazione.
* **Impatto:** qualunque lettura di attività dal `portfolio_cycles` sovrastima di **19×**. È la
  tabella che alimenta i pannelli operativi.
* **Severità:** **Low** (non tocca il denaro) / **Medium** per l'auditabilità
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — rinominare il campo in `target_orders_count` e
  aggiungere `submitted_orders_count`; popolare `constraints_fired` con i guard effettivamente
  scattati. Sola strumentazione.
* **Test/monitor consigliato:** invariante `submitted_orders_count == count(execution_decisions WHERE decision IN ('BUY','SELL') AND tick_time = cycle.timestamp)`.

---

### [DAY-012] `trades.slippage_est` è una copia esatta di `cost_usd`: la qualità d'esecuzione non è misurata

* **Tipo:** Bug
* **Area:** PnL
* **Ledger:** **F-015** (13ª occorrenza)
* **Evidenza:**
  * `trades` 282 (XLE): `cost_usd = 0.3726207086754916`, `slippage_est = 0.3726207086754916` — identici a 16 cifre
  * i 3 trade aperti oggi hanno `cost_usd` valorizzato (0,344 / 1,010 / 0,344) e `slippage_est` **NULL**
* **Descrizione:** il campo non contiene uno slippage ma il costo modellato dal `TradeCostCalculator`.
  Non esiste da nessuna parte un confronto fra prezzo di riferimento al momento della decisione e
  prezzo di fill.
* **Impatto:** impossibile distinguere un fill buono da uno cattivo. I dati per una misura vera non
  sono persistiti (§8.6): servirebbe il mid NBBO al `tick_time`, che l'`event_market_context` del
  dossier calcola ex-post ma non viene scritto sulla riga del trade.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — persistere `reference_price` e `reference_source`
  al momento della submission e calcolare `slippage_est = (fill − reference) × qty × sign`.
  Strumentazione, non taratura.
* **Test/monitor consigliato:** test che asserisce `slippage_est != cost_usd` su un trade con fill
  divergente dal riferimento.

---

### [DAY-013] `org_lookup` attribuisce a MS un articolo su un titolo *raccomandato da* Morgan Stanley — ed è lo score più alto della giornata

* **Tipo:** Bug
* **Area:** News (ticker resolution)
* **Ledger:** **F-020** (12ª occorrenza)
* **Evidenza:**
  * `news_log` 8899: titolo *"Buy this stock to play boom in one area of AI, **Morgan Stanley** says"*,
    `source = gdelt_gkg`, `extraction_method = **org_lookup**`, ticker assegnato **MS**
  * `sentiment_signals` 8899: **+0,680**, conf 0,85 — **massimo assoluto della giornata**
  * `execution_decisions` 14600, 18:37: `SKIP_FALLBACK` (single-model)
* **Descrizione:** l'articolo raccomanda *un altro* titolo; Morgan Stanley compare solo come casa
  d'analisi nel boilerplate. `org_lookup` mappa il nome della banca sul suo ticker.
* **Impatto:** **nessun costo il 2026-08-25** — il segnale è stato scartato da SKIP_FALLBACK,
  ma per una ragione accidentale (glm-5.2 sotto il floor di confidence), **non** perché il ticker
  fosse riconosciuto sbagliato. Se glm avesse risposto con confidence ≥ 0,4 l'ensemble avrebbe
  prodotto lo score più alto del giorno su un ticker errato e MS sarebbe stato il candidato #1 al
  ranking BUY. Il difetto è quindi armato: oggi non ha sparato per caso.
* **Severità:** **High** (rischio latente) / **Low** (impatto realizzato)
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — `org_lookup` deve escludere le occorrenze in cui
  il nome dell'organizzazione compare in pattern attributivi (`"<Org> says"`, `"according to <Org>"`,
  `"<Org> analyst"`). È correttezza del resolver, esplicitamente fuori dal freeze di taratura
  («un ticker sbagliato è l'errore peggiore», CLAUDE.md).
* **Test/monitor consigliato:** golden case nel set QX-01 con esattamente questo titolo; monitor
  sulla quota di righe `extraction_method = org_lookup` che finiscono su ticker finanziari
  (MS, GS, DB, JPM, UBS).

---

### [DAY-014] Le finestre beat sono a ora UTC fissa: persi i primi 37 minuti di sessione

* **Tipo:** Bug
* **Area:** Ops (DST)
* **Ledger:** **F-021** (11ª occorrenza)
* **Evidenza:**
  * `src/workers/celery_app.py:51` `timezone="UTC"`; `:210` `crontab(minute="7,22,37,52", hour="14-21")`;
    `:78`/`:151`/`:162`/`:184` `crontab(minute="*/15", hour="14-21")`
  * primo `portfolio_cycles.timestamp` del giorno: **14:07:00** (apertura RTH 13:30 UTC)
  * primo `news_log.fetched_at`: **14:00:35**
* **Descrizione:** in EDT l'apertura è alle 13:30 UTC ma le finestre partono alle 14:00/14:07.
  **37 minuti di sessione senza cicli d'esecuzione** e 30 minuti senza ingest news, ogni giorno di
  ora legale.
* **Impatto:** i primi 37 minuti sono anche quelli a dispersione più alta. HOOD, mover #1 della
  giornata, aveva già fatto **+4,5% entro le 14:20** (13:30 open 103,20 → 14:20 open 108,27; close
  112,20): oltre metà del movimento è avvenuta prima che il sistema potesse osservarlo. Costo
  non separabile da F-030 e non attribuito qui per evitare doppio conteggio.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — schedulare le finestre su
  `crontab(..., hour="13-21")` con un guard di market-open, oppure spostare il beat su
  `America/New_York`. Nessuna soglia di strategia cambia: è la finestra di osservazione stessa.
* **Test/monitor consigliato:** test che, dato un calendario con apertura 13:30Z, asserisce che il
  primo slot pianificato cade entro 10 minuti dall'apertura, sia in EDT sia in EST.

---

### [DAY-015] Gli stop protettivi coprono solo la parte intera e nascono un ciclo dopo l'ingresso; META resta senza stop per tutta la notte

* **Tipo:** Rischio
* **Area:** Risk
* **Ledger:** **F-022** (2ª occorrenza)
* **Evidenza:**
  * ordini Alpaca 19:22:04: `e313f841…` NVDA sell **qty 8** (posizione 8,945614), `636f0c79…` CSCO sell **qty 17** (posizione 17,135692)
  * ingressi alle 19:07:00 → stop alle 19:22:04 (**un ciclo dopo**, 15 minuti scoperti)
  * META: ingresso 19:52:00, ultimo ciclo della sessione → **nessuno stop creato**; nessun ordine il 2026-08-26
  * file: `src/portfolio/fractional_stop_orders.py:71` — `whole_qty = math.floor(abs(position_qty))`, `skip_no_whole_share` sotto 1 azione
  * libro: **8 stop GTC attivi su 48 posizioni**; 12 posizioni sotto 1 azione (notional $5 492,86, UPL −$66,75) non proteggibili
* **Descrizione:** design noto (#62/#63): Alpaca rifiuta ordini stop su quantità frazionarie, quindi
  si protegge solo il pavimento intero. La riconciliazione avviene una volta per ciclo, quindi c'è
  sempre una finestra scoperta dopo l'ingresso — che diventa **una notte intera** se l'ingresso cade
  nell'ultimo ciclo della sessione.
* **Impatto:** copertura NVDA 89,4%, CSCO 99,2%, **META 0%**. $1 902,45 esposti senza stop dalla
  chiusura del 25 all'apertura del 26. Nessuna perdita materializzata (META ha aperto in gain,
  +$39,76 al momento dell'analisi), quindi **costo non stimabile**: è un'esposizione al rischio,
  non una perdita.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation limitato al **timing**: eseguire la sincronizzazione
  degli stop protettivi subito dopo il fill, non al ciclo successivo, e in particolare prima della
  chiusura per gli ingressi dell'ultimo slot. La size minima ≥ 1 azione resta **taratura** e resta
  congelata (già registrato nella carta il 2026-08-06 per #161).
* **Test/monitor consigliato:** monitor che alza un alert se, alla chiusura RTH, esiste una posizione
  ≥ 1 azione senza stop GTC aperto.

---

### [DAY-016] Un segnale forte viene sovrascritto da uno a punteggio nullo generato pochi minuti dopo

* **Tipo:** Bug
* **Area:** Signal
* **Ledger:** **F-023** (7ª occorrenza)
* **Evidenza:**
  * NVDA, ora 19:00 UTC: 4 segnali — **+0,378** (8944, 19:00:49), **0,000** (8946), +0,276 (8949, 19:45:13), +0,358 (8952, 19:45:27)
  * `execution_decisions` 14708, 19:22:04: `SKIP_PYRAMIDING` — *"P0-05 anti-pyramiding: già a libro dal 2026-08-25, **sentiment +0.000**, peso non allocato 2.0%"*
  * NVDA ha ricevuto **18 segnali** in giornata, di cui 10 single-model
* **Descrizione:** S4 usa il segnale più recente per simbolo. Alle 19:22 il segnale di riferimento
  per NVDA era 8946 con score **0,000**, sebbene 15 minuti prima lo stesso simbolo avesse prodotto
  +0,378 su un articolo pertinente (Cisco↔Nvidia) — quello che aveva appena generato la BUY.
* **Impatto:** in questa giornata l'effetto è neutro (la posizione era già aperta e il guard
  anti-pyramiding l'avrebbe bloccata comunque), quindi **costo non stimabile**. Il difetto è però
  visibile in chiaro: la traccia scritta a DB motiva un blocco con «sentiment +0.000» quando il
  sentiment reale sul simbolo era +0,378.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** nessuna in freeze — la regola di aggregazione per simbolo (ultimo vs.
  massimo vs. media pesata) è taratura. Continuare a registrare la ricorrenza.
* **Test/monitor consigliato:** registrare accanto a ogni decisione il numero di segnali disponibili
  per il simbolo nella finestra e il massimo |score| fra essi, così che la sovrascrittura sia
  visibile senza query manuali.

---

### [DAY-017] Il guard anti-pyramiding blocca 70 intenti e ne lascia traccia in `execution_decisions` solo 4

* **Tipo:** Bug
* **Area:** Signal / Ops
* **Ledger:** **F-031** (7ª occorrenza)
* **Evidenza:**
  * `s4_intent_events`: `SKIP_PYRAMIDING` = **70** intenti su 5 simboli (LLY 24, SOXX 24, DELL 15, MRVL 5, NVDA 2)
  * `execution_decisions`: `SKIP_PYRAMIDING` = **4** righe (DELL 16:22, LLY 19:22, SOXX 19:22, NVDA 19:22)
  * stessa asimmetria su `SKIP_STALE` (315 → 3) e `SKIP_ENTRY_FRESHNESS` (572 → **0**)
  * caso rilevante: **DELL**, segnale **+0,581** alle 16:15 (il più forte a due modelli della
    giornata), bloccato perché a libro dal 2026-07-13; `counterfactual_return_1h = −0,003525`
* **Descrizione:** il nuovo ledger #294 registra l'intera popolazione degli intenti; la tabella
  storica `execution_decisions` ne vede una frazione. Il bucket più grande della giornata
  (`SKIP_ENTRY_FRESHNESS`, 572) è completamente assente.
* **Impatto:** **costo attribuito −$1,85** sul caso DELL, controfattuale corto: primo ciclo dopo il
  segnale 16:22 @ 451,14, close 450,76, slot tipico S4 $2 200 → (450,76−451,14)/451,14 × 2 200 =
  **−1,85 $**. Il guard ha quindi *evitato* una perdita, coerentemente con il controfattuale a 1h
  registrato dal sistema (−0,35% → −$7,76 sullo stesso slot). L'anomalia è di osservabilità, non di
  denaro: la serie storica su `execution_decisions` sottostima gli scarti di **oltre 10×**.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — persistere una riga `execution_decisions` per ogni
  disposition del ledger #294, o dichiarare esplicitamente `s4_intent_events` come unica fonte e
  migrarvi l'analisi. Sola tracciabilità.
* **Test/monitor consigliato:** riconciliazione giornaliera che confronta i conteggi per
  `reason_code` fra `s4_intent_events` ed `execution_decisions` e alza un alert sulla divergenza.

---

### [DAY-018] La suite di test scrive nel database di produzione

* **Tipo:** Bug
* **Area:** Data / Ops
* **Ledger:** **F-028** (7ª occorrenza)
* **Evidenza:**
  * `ingestion_stats_daily`: riga `day=2026-08-25, source='reuters', fetched=36, queued=36, discarded_no_ticker=9`, `updated_at = 2026-08-25 **12:38:53**` (pre-apertura, e `reuters` non è una fonte della pipeline live)
  * `news_queue_drops`: 9 righe `no_ticker` / `ingestion` / source `reuters` nella stessa giornata
  * riga gemella il 2026-08-26 (`fetched=12`, 08:37:34) e il 2026-08-22
  * osservazione collaterale: `portfolio_monitor_snapshots` del 2026-08-26 08:35:31 riporta **1 posizione MSFT qty 12,3456** contro le 48 reali del broker — payload di test scritto in produzione dallo stesso pattern
* **Descrizione:** esecuzioni di test contro il DB live inquinano tabelle di evidenza con una fonte
  che non esiste nella pipeline.
* **Impatto:** **costo non stimabile** — non tocca ordini né P&L. Ma `ingestion_stats_daily` è una
  delle tabelle lette per ricostruire l'ingest: chi la interroghi senza sapere di `reuters` conta
  36 fetch inesistenti. Su `portfolio_monitor_snapshots` l'inquinamento è più grave perché
  contraddice il libro reale.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — la suite deve puntare a un database dedicato
  (variabile d'ambiente obbligatoria, fixture che rifiuta di partire se l'URL coincide con quello di
  produzione). Sola igiene dei dati.
* **Test/monitor consigliato:** guard in `conftest.py` che solleva se `DATABASE_URL` punta al DB
  live; monitor che alza un alert su qualunque `source` non presente nella whitelist della pipeline.

---

### [DAY-019] `duplicates` supera di 4,5× i `fetched` dello stesso giorno

* **Tipo:** Anomalia
* **Area:** Data
* **Ledger:** **F-007** (12ª occorrenza)
* **Evidenza:**
  * `ingestion_stats_daily` 2026-08-25, `alpaca_benzinga`: `fetched = 579`, `duplicates = **2 589**`, `queued = 345`
  * conferma indipendente: `news_queue_drops` contiene esattamente 2 589 righe `duplicate_id` per benzinga nella giornata
  * pattern ricorrente: 08-24 (699 vs 3 178), 08-21 (673 vs 3 356)
* **Descrizione:** il contatore dei duplicati è additivo sui run intra-giornata mentre `fetched`
  conta gli articoli distinti dell'ultima pagina; le due grandezze non sono comparabili nonostante
  vivano nella stessa riga.
* **Impatto:** **costo non stimabile.** Un tasso di duplicazione dell'82% (2 589 / 3 168) è
  plausibile per un polling ogni 15 minuti su una finestra scorrevole, ma dalla tabella non è
  possibile distinguere «polling ridondante, tutto normale» da «il dedup sta scartando articoli
  nuovi». La conferma incrociata su `news_queue_drops` di oggi è la prima misura indipendente e
  depone per la prima ipotesi.
* **Severità:** **Low**
* **Confidenza:** **Medium**
* **Azione consigliata:** ticket di remediation — separare `duplicates_within_run` da
  `duplicates_cumulative`, o normalizzare `fetched` allo stesso perimetro. Sola strumentazione.
* **Test/monitor consigliato:** invariante `duplicates <= fetched * n_runs` con `n_runs` persistito.

---

### [DAY-020] `combined_drawdown` è un massimo cumulato dal 2026-07-04, fermo a 1,2429% da 20 sedute: nessun drawdown corrente è sorvegliato

* **Tipo:** Rischio
* **Area:** Risk
* **Ledger:** **F-003** (15ª occorrenza — la forma è cambiata dopo il deploy di #366)
* **Evidenza:**
  * `risk_reports`: `combined_drawdown = 0.012429` **identico a 6 decimali dal 2026-08-06 al 2026-08-25** (20 righe consecutive), mentre il NAV oscillava fra 109 825,70 e 110 480,71
  * file: `src/portfolio/risk_monitor.py` → `max_drawdown_from_equity` è un massimo peak-to-trough sull'intera curva dal baseline, **monotono non decrescente**
  * `src/workers/risk_monitor_task.py:195-203` — `per_strategy_metrics` è deliberatamente lasciato vuoto (fix #366)
  * `risk_reports` 2026-08-25: `alerts = []`, `per_strategy_metrics = {}` — l'ALERT fantasma «Strategy portfolio drawdown 17.9% exceeds 10%», presente dal 07-31 al 08-24, **è sparito**
  * `portfolio_monitor_snapshots` 2026-08-25: `current_drawdown = **null**`
* **Descrizione:** #366 ha correttamente rimosso l'entry sintetica `portfolio` che produceva l'ALERT
  spurio. Quello che resta, però, è un massimo storico cumulato: per definizione non può scendere e
  non riflette la giornata. `current_drawdown` è `null` ovunque.
* **Impatto:** **costo non stimabile.** Il kill-switch condizionale dichiarato in
  `config/trading.yaml:271` (`recovery_drawdown_pct: 0.025` — sblocca quando il drawdown scende sotto
  la soglia) ha come unico ingresso una grandezza che **non può scendere**: la condizione di recupero
  non è valutabile. E la soglia di allarme (`portfolio_drawdown: 0.05`) è confrontata con un massimo
  storico, non con il drawdown in corso. Il libro oggi è tranquillo (1,24%), quindi il rischio è
  latente, non realizzato.
* **Severità:** **High** (controllo di rischio) / impatto realizzato nullo
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — affiancare a `combined_drawdown` (max storico) un
  `current_drawdown` = (peak − nav_oggi) / peak, e agganciare a quest'ultimo sia la soglia di allarme
  sia la condizione di recupero del kill-switch. È correttezza di un controllo di rischio, non
  taratura: nessuna soglia numerica cambia.
* **Test/monitor consigliato:** test che, data una curva 100 → 90 → 100, asserisce
  `current_drawdown == 0` e `max_drawdown == 0.10`; monitor che alza un alert se
  `combined_drawdown` resta identico per più di 10 sedute consecutive.

---

### [DAY-021] Il decay monitor confronta metriche pipeline-globali contro tre baseline distinte, inclusa S2 mai tradata

* **Tipo:** Bug
* **Area:** Ops
* **Ledger:** **F-004** (11ª occorrenza)
* **Evidenza:**
  * `decay_reports` 2026-08-25 21:00:00 — 12 righe, S1/S2/S4 × {ic, hit_rate, sharpe, max_drawdown}
  * `actual_value` **identico su tutte e tre le strategie**: ic 0,01520846, hit_rate 0,28286517, sharpe 0,45904327, max_drawdown 0,12095941
  * baseline distinte: ic 0,035 / 0,042 / 0,028 — hit_rate 0,54 / 0,56 / 0,52
  * esito: **2 × CRITICAL** su `hit_rate` (S1 e S2), 5 × WARNING
  * S2 non ha mai emesso un ordine: `strategies_run = ["S1","S4"]` in tutti e 24 i cicli
* **Descrizione:** una sola misura globale viene confrontata con tre soglie diverse, generando
  allarmi che dipendono solo da quale baseline è più severa.
* **Impatto:** **costo non stimabile.** Due CRITICAL al giorno di cui uno su una strategia inattiva:
  rumore che desensibilizza chi legge, su un canale che dovrebbe segnalare il decadimento reale.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** ticket di remediation — calcolare le metriche per strategia
  (`stop_strategy` è già disponibile su `trades` dal 2026-07) ed escludere le strategie senza trade.
  Sola strumentazione.
* **Test/monitor consigliato:** test che asserisce `actual_value` diversi fra strategie con trade
  disgiunti; guard che salta la valutazione per una strategia con zero trade nella finestra.

---

### [DAY-022] Copertura news della watchlist al 17,7%: 55 simboli su 96 senza una sola news, e i due mover più forti sono fra questi

* **Tipo:** Anomalia
* **Area:** News
* **Ledger:** **F-001** (18ª occorrenza)
* **Evidenza:**
  * dossier: `effective_timely_coverage.quota = 0,177` (17 ticker su 96); `mercato.watchlist_zero_news = 55`
  * `candidati_miss`: **RDDT +6,39%** causa `NO_NEWS`; **NVO +3,71%** causa `NO_NEWS`
  * `opportunity_v2.accessible_opportunity_usd`: RDDT **$86,42**, NVO **$36,31** (size S4 $2 200, entry all'apertura del primo ciclo eleggibile, uscita al close)
* **Descrizione:** la seduta aveva 11 mover oltre il 3% (9 al rialzo, 2 al ribasso, σ 1,90%). Su due
  di essi — fra cui il #2 assoluto — non è arrivato **nessun** articolo.
* **Impatto:** **costo congetturale $122,73** (86,42 + 36,31), somma delle opportunità accessibili
  sui due mover senza copertura. Nessun trade è avvenuto, quindi non è una perdita: è alpha che il
  sistema non ha potuto nemmeno valutare.
* **Severità:** **Medium**
* **Confidenza:** **Medium** (dossier deterministico, ma controfattuale interamente simulato)
* **Azione consigliata:** nessuna in freeze — l'ampliamento delle fonti è una decisione di roadmap
  (già tracciata come pivot editorial→event-driven). Continuare a registrare la ricorrenza e il costo.
* **Test/monitor consigliato:** già coperto dal ledger `market_daily.jsonl`; nessuna aggiunta.

---

### [DAY-023] La notizia arriva quando il movimento è già avvenuto

* **Tipo:** Anomalia
* **Area:** News
* **Ledger:** **F-030** (8ª occorrenza)
* **Evidenza:**
  * HOOD: prev close ≈ 103,62; barra 13:30 open 103,20; **14:20 open 108,27** (+4,5% prima di qualunque segnale); primo segnale 14:15 (score +0,174, articolo su ETF Bitcoin, non su HOOD); close 112,20
  * latenza published→fetched mediana **40,3 min** (max 111,2)
  * dossier `ingressi`: `quota_movimento_precedente_al_segnale` = **1,045** (CSCO), **0,847** (NVDA), **0,900** (META) — cioè fra l'85% e il 104% del movimento di sessione era già avvenuto al momento del segnale
* **Descrizione:** su tutti e tre gli ingressi effettivi della giornata, la quota del movimento
  intraday già consumata al momento del punteggio va dall'85% al 104%. Su CSCO supera il 100%:
  il titolo era già andato oltre e stava tornando indietro.
* **Impatto:** **costo attribuito $19,19** — la colonna `vs_apertura` del dossier misura per CSCO
  −$19,19 rispetto a un ingresso all'apertura di sessione (NVDA +$18,11 e META +$20,61 sono invece
  positivi, quindi l'effetto netto del giorno è favorevole: +$19,53). Riporto il solo caso negativo
  perché è quello imputabile al ritardo; il ledger sommerà una stima conservativa.
* **Severità:** **Medium**
* **Confidenza:** **Medium**
* **Azione consigliata:** nessuna in freeze. Il dato di oggi è però il migliore della finestra
  (latenza mediana 40 min contro 1h50m registrata a inizio agosto): vale la pena verificare alla
  sintesi del 28/09 se il miglioramento è stabile.
* **Test/monitor consigliato:** già coperto da `quota_movimento_precedente_al_segnale` nel dossier.

---

### [DAY-024] La varianza d'ensemble non è mai un gate: `ensemble_std` è letto solo dal postmortem

* **Tipo:** Rischio
* **Area:** LLM / Risk
* **Ledger:** **F-037** (4ª occorrenza)
* **Evidenza:**
  * `sentiment_signals` 8942 (CSCO): `ensemble_std = **0,2475**` → **BUY** eseguita
  * `sentiment_signals` 8914 (XLE): `ensemble_std = **0,2121**` → **SELL** eseguita
  * `sentiment_signals` 8950 (META): `ensemble_std = 0,1768` → **BUY** eseguita
  * nessun `SKIP_*` riferito alla varianza in tutta la giornata
  * 28 segnali `ensemble:` hanno `ensemble_std = 0` — fra questi i due casi di disaccordo di segno
    (8862 META, 8947 PLTR), dove lo std è nullo perché un modello era sotto floor
* **Descrizione:** CLAUDE.md prescrive «*Ensemble variance: flag high-variance outputs for human
  review or discard*». Il valore è calcolato e persistito, ma nessuna decisione lo consulta: le tre
  BUY della giornata hanno std fra 0,18 e 0,25 su una scala in cui il massimo teorico su due modelli
  è ~0,7. Peggio, lo std è calcolato **solo sui contributori**, quindi un disaccordo di segno fra un
  modello eligible e uno sotto floor risulta varianza **zero**.
* **Impatto:** **costo non stimabile** — le tre BUY sono in guadagno a fine giornata. È un
  guardrail dichiarato in architettura e non implementato nel path decisionale.
* **Severità:** **Medium**
* **Confidenza:** **High**
* **Azione consigliata:** nessuna in freeze — introdurre un gate di varianza è **taratura** e va al
  2026-09-28. Ammissibile subito solo la correzione del **calcolo**: `ensemble_std` deve essere
  calcolato su tutte le risposte ricevute, non sui soli contributori, altrimenti il numero che
  useremo per tarare il gate è sbagliato.
* **Test/monitor consigliato:** test che, dati due modelli con polarity +0,10 e −0,10 di cui uno
  sotto floor, asserisce `ensemble_std > 0`.

---

### Nota sul ledger delle evidenze (`docs/evidence/findings.json`)

Il cron **alpha-miss** (`ALPHA_MISS_REPORT_2026-08-25.md`) aveva già scritto occorrenze datate
2026-08-25 su **F-001, F-009, F-012, F-030, F-031, F-033, F-043, F-044** prima che questa sessione
forense girasse. Per non gonfiare né la ricorrenza né il costo cumulato — le due grandezze su cui
poggiano le soglie della `OBSERVATION_CHARTER.md` — **una sola occorrenza per finding per giornata**
è stata mantenuta, quella dell'alpha-miss, che è l'origine e lo strumento progettato per quella
misura. Le occorrenze corrispondenti di questo report ([DAY-022] F-001, [DAY-008] F-012,
[DAY-023] F-030, [DAY-017] F-031, [DAY-010] F-033) **non** sono state aggiunte al ledger: la loro
evidenza resta qui come conferma indipendente e come dettaglio non presente nell'alpha-miss.
Nessuna occorrenza preesistente è stata modificata o cancellata.

Riconciliazione delle stime di costo dove i due report divergono (nel ledger vale sempre la prima):

| Finding | Stima in questo report | **Stima nel ledger** (alpha-miss) | Motivo della differenza |
|---|---:|---:|---|
| F-001 | $122,73 (RDDT + NVO) | **$222,13** | l'alpha-miss include anche i miss non NO_NEWS della giornata |
| F-030 | $19,19 (solo `vs_apertura` di CSCO) | **$13,83** | l'alpha-miss misura entrambe le facce (ingresso + uscita), netta anziché sul solo caso negativo |
| F-031 | −$1,85 (DELL, controfattuale al close) | **$0,00** | l'alpha-miss considera DELL e MRVL insieme sul controfattuale a 1h |

Occorrenze scritte da **questa** sessione: F-003, F-004, F-007, F-008, F-010, F-011, F-014, F-015,
F-020, F-021, F-022, F-023, F-027, F-028, F-037, F-041 (16 ricorrenze) più i tre nuovi
**F-045, F-046, F-047**. `prossimo_id` avanzato da 45 a **48**.

Su **F-046** è dichiarata nel ledger una sovrapposizione parziale con l'occorrenza F-009 dell'alpha-miss:
entrambe riguardano il miss HOOD, ma misurano meccanismi diversi (F-009 = la soglia scarta un segnale
di segno corretto ma debole; F-046 = il segnale issuer-specific delle 16:45 aveva il segno **sbagliato**
perché il modello non ha mai visto il titolo). I $30,85 di F-046 sono un **sottoinsieme** dei $179,83
di F-009, non un costo aggiuntivo: alla sintesi del 28/09 va sommato **F-009, non entrambi**.

---

## 11. False positive e aree risultate corrette

| Area verificata | Esito | Evidenza |
|---|---|---|
| **F-003 — ALERT drawdown fantasma "17,9%"** | ✅ **RISOLTO** | Merge `15ec427` / `8c61a44` (#366) deployato. `risk_reports` 2026-08-25: `alerts = []`, `per_strategy_metrics = {}`. L'ALERT era presente ogni notte dal 07-31 al 08-24. *Resta il problema residuo del massimo cumulato, riportato come [DAY-020].* |
| **F-044 — il dossier non si genera più** | ✅ **RISOLTO** | `docs/evidence/dossier/2026-08-25.json` generato il 2026-08-26T08:01:43Z, schema 2.5, 2,1 MB, nessun errore `decision_at is ambiguous`. |
| **F-042 — ordine broker senza segnale/decisione** | ✅ **non ricorre** | Query di riconciliazione: 0 ordini orfani. Tutti e 4 gli ordini hanno `signal_id`, `decision_id` e `trade_id` (l'unica eccezione, XLE, porta `decision_id = 2318` che è la decisione di **ingresso** del trade — comportamento corretto dell'endpoint, non un orfano). |
| **F-013 — churn intraday SELL→BUY→SELL** | ✅ **non ricorre** | Nessun simbolo con BUY e SELL nella stessa giornata; nessun roundtrip < 30 min. |
| **F-035 — FIX-D annullato da `_signals_as_of`** | ✅ **non osservabile** | Nessuna uscita per scadenza segnale nella giornata; unica uscita `sentiment_reversal`. |
| **F-019 — latenza d'ingestione che consuma la finestra di freshness** | 🟡 **molto migliorato** | Mediana 40,3 min contro la finestra di entry-freshness di 2,0 h: consuma il **33%**, non il 92% registrato a inizio agosto. Nessuna occorrenza registrata per il 2026-08-25 per non gonfiare la ricorrenza con un non-evento. |
| **F-016 — fetch benchmark SPY fallito** | ✅ **non ricorre** | `mercato.rendimenti.SPY = +0,0032` presente nel dossier; `simboli_senza_dati = []`. |
| **Ollama / semaforo token** | ✅ **sano** | 196/196 risposte, 0 timeout, `consecutive_fallback = 0`. Il fix #368 (`3a3425d`) sembra reggere. |
| **Idempotenza retry Celery** | ✅ **funzionante** | 3 `SKIP_IDEMPOTENCY` nel ledger #294: il guard ha effettivamente respinto ri-sottomissioni. |
| **Guard di freschezza in ingresso** | ✅ **funzionante** | 572 `SKIP_ENTRY_FRESHNESS` + 315 `SKIP_STALE`: nessun trade su dati vecchi. |
| **Sanitizzazione input** | ✅ **nessun problema osservato** | Nessun homoglifo, nessun testo nascosto, nessun ticker non-ASCII. Presenti entità HTML non decodificate (`&#39;`, `&amp;`, `&#34;`) nei corpi: cosmetiche, non invertono il senso. |
| **Attribuzione degli articoli che hanno generato ordini** | ✅ **corretta** | CSCO e NVDA da *"Nvidia's AI Chips Are Making Liquid Cooling the New Standard as Cisco Expands Its AI Bet"* (2 ticker, entrambi soggetti reali); META da *"Evercore: META Could Surge Over 50% on $22B AI Opportunity"* (2 ticker, META soggetto). Nessuna delle tre BUY nasce da fan-out spurio. |
| **Coerenza paper/live** | ✅ | `mode: paper`, `source: alpaca_paper`, `approved: false` su entrambe le sleeve. |

---

## 12. Dati mancanti o non accessibili

| Dato | Stato | Query / fonte che servirebbe |
|---|---|---|
| Log applicativi del 2026-08-25 | **perso** (redeploy) | driver di logging persistente — vedi [DAY-005] |
| Latenza per-chiamata LLM | **non misurabile** | colonna `latency_ms` in `llm_responses`, oggi assente |
| Riavvii worker del 25 | **non verificabile** | log persistenti + `docker events` archiviati |
| Slippage reale | **non calcolabile** | `reference_price` al `tick_time` non persistito su `trades` — vedi [DAY-012] |
| `exit_mechanism` | **NULL su 474/474 righe** | nessuna interpretazione possibile per questa giornata (#184) |
| `performance_metrics` (composite IC, ICIR, PSI, drift) | **tabella vuota** — 0 righe in assoluto | popolamento del task che dovrebbe scriverla; oggi ICIR vive solo in `weight_update_log` |
| `sector_beta_1_incremental_usd` | `null` nel dossier | non calcolato per la giornata |
| `guard_cost_usd` / `guard_avoided_loss_usd` | `null` nel dossier | notional USD disponibile solo su `SKIP_PYRAMIDING` post-2026-08-19 con NAV osservata |
| `counterfactual_return_overnight` | NULL su tutte le guard decisions del 25 | calcolo pianificato per il giorno successivo; verificabile nel dossier 08-26 |
| `net_opportunity_usd` sui candidati miss | `null` (costi non modellati) | `TradeCostCalculator` non applicato al ramo simulato |
| API REST con l'header del prompt | **rifiutata** | usare `X-API-Key` — vedi [DAY-004] |

---

## 13. Raccomandazioni immediate

Tutte compatibili con il freeze: nessuna tocca soglie, pesi, flag, cooldown o parametri di strategia.

1. **[DAY-001] Correggere il confronto `is_tradable` nel dossier e rigenerare i dossier schema 2.5.**
   Priorità massima: è l'unico difetto che azzera *un intero strumento di misura* appena messo in
   servizio, e il cumulato di finestra rilegge i file già scritti — ogni giorno che passa aggiunge un
   dossier da rigenerare.
2. **[DAY-003] Localizzare i datetime del calendario Alpaca prima di convertirli a UTC.**
   Senza questa correzione il ledger di lifecycle S4 e l'orologio D+2 di #334 raccolgono zero
   osservazioni utilizzabili sul 62% della sessione.
3. **[DAY-002] Includere il titolo nel prompt DK-CoT.** Ogni giorno senza questa correzione produce
   punteggi calcolati su un input incompleto, e la domanda di uscita n.1 («la news ha alpha?») si
   auto-risponde di no.
4. **[DAY-020] Affiancare `current_drawdown` al massimo cumulato e agganciarvi il kill-switch.**
   Oggi la condizione di recupero del kill-switch ha come ingresso una grandezza monotona
   non decrescente.
5. **[DAY-004] Correggere l'header di autenticazione nel prompt del cron forense** (`X-API-Key`).
   Costo zero, quarta ricorrenza.
6. **[DAY-015] Sincronizzare gli stop protettivi subito dopo il fill**, e in ogni caso prima della
   chiusura per gli ingressi dell'ultimo slot. META è rimasta scoperta per una notte intera.
7. **[DAY-013] Escludere i pattern attributivi da `org_lookup`.** Il difetto oggi non ha sparato per
   una coincidenza (il modello a peso maggiore era sotto floor): con l'ensemble completo, lo score
   più alto della giornata sarebbe stato un ordine su un ticker sbagliato.
8. **[DAY-005] Rendere persistenti i log dei container.** Undicesima ricorrenza; senza log ogni
   report forense ha un buco strutturale su latenza ed eccezioni.

---

## 14. Test o monitor da aggiungere

| # | Test/monitor | Copre |
|---|---|---|
| T1 | Unit: riga con `is_tradable = true` → il dossier espone `True`. Assertion di sanità: `n_intenti_tradabili == 0` **e** almeno un `SUBMITTED` → `missingness` esplicito, mai zero silenzioso | DAY-001 |
| T2 | Unit: calendario naive `09:30/16:00` + fill 19:07Z → `reason_code is None`, `d0 == 2026-08-25` | DAY-003 |
| T3 | Monitor: alert se la quota `FILL_OUTSIDE_RTH` su fill con `broker_status = filled` supera 0% | DAY-003 |
| T4 | Unit: il prompt renderizzato contiene il titolo dell'articolo | DAY-002 |
| T5 | Monitor: quota di articoli in cui il corpo cita un giorno della settimana diverso da `published_at` | DAY-002 |
| T6 | Unit: curva 100→90→100 → `current_drawdown == 0`, `max_drawdown == 0.10`; monitor: `combined_drawdown` identico per >10 sedute → alert | DAY-020 |
| T7 | Invariante: `single:%` ⇒ esattamente 1 `llm_responses.eligible = true`; `ensemble:%` ⇒ esattamente 2 | DAY-006 |
| T8 | Unit: due modelli con polarity +0,10 / −0,10, uno sotto floor → `ensemble_std > 0` | DAY-024 |
| T9 | Monitor alla chiusura RTH: posizione ≥ 1 azione senza stop GTC aperto → alert | DAY-015 |
| T10 | Riconciliazione giornaliera dei conteggi per `reason_code` fra `s4_intent_events` ed `execution_decisions` | DAY-017 |
| T11 | Guard in `conftest.py`: solleva se `DATABASE_URL` punta al DB di produzione | DAY-018 |
| T12 | Smoke test nel cron forense: 200 su `/api/positions` prima di iniziare | DAY-004 |
| T13 | Golden case QX-01 con il titolo *"Buy this stock…, Morgan Stanley says"* → nessun ticker MS | DAY-013 |
| T14 | Unit: apertura 13:30Z ⇒ primo slot pianificato entro 10 min, in EDT e in EST | DAY-014 |
| T15 | Invariante: `portfolio_cycles.submitted_orders_count` == numero di BUY/SELL nello stesso `tick_time` | DAY-011 |
| T16 | Unit: trade con fill divergente dal riferimento ⇒ `slippage_est != cost_usd` | DAY-012 |
| T17 | Monitor: quota `mapping_rilevanza.UNKNOWN` > 80% → alert (oggi 78,6%) | DAY-008 |
| T18 | Monitor: uscita `sentiment_reversal` da articolo con > 5 ticker o rilevanza `UNKNOWN` → alert | DAY-009 |
| T19 | Invariante: `signal_id IS NOT NULL` su ogni `execution_decisions` il cui `reason` cita uno score | DAY-007 |
| T20 | Monitor: `source` non in whitelist nella pipeline → alert | DAY-018 |

---

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza** ai sensi della `OBSERVATION_CHARTER.md`. Nessuna proposta di taratura.

| ID | Titolo | Area | Priorità | Esente dal freeze? |
|---|---|---|---|---|
| **T-A** | Dossier: `is_tradable::text` produce `'true'`, il parser confronta `'t'` — l'aggregato della guardia ombra #335 è zero per costruzione; rigenerare i dossier schema 2.5 | Evidenza | **P0** | **Sì** — senza, il ledger delle settimane restanti misura zero |
| **T-B** | Lifecycle S4: i datetime naive del calendario Alpaca sono letti come UTC — 62% della sessione censurata, orologio D+2 mai armato | Orders/Data | **P0** | **Sì** — stesso profilo di T-A |
| **T-C** | Scoring: includere il titolo nel prompt DK-CoT e segnalare le incoerenze titolo↔corpo | News/LLM | **P0** | **Sì** — è l'input della misura, non una soglia |
| **T-D** | Risk: affiancare `current_drawdown` al massimo cumulato e agganciarvi allarme e recupero del kill-switch | Risk | **P1** | **Sì** — correttezza di un controllo di rischio; nessuna soglia cambia |
| **T-E** | Ticker resolution: `org_lookup` deve ignorare le occorrenze in pattern attributivi (`"<Org> says"`, `"according to <Org>"`, `"<Org> analyst"`) | News | **P1** | **Sì** — «un ticker sbagliato è l'errore peggiore» |
| **T-F** | Stop protettivi: sincronizzare subito dopo il fill e prima della chiusura per gli ingressi dell'ultimo slot | Risk | **P1** | **Sì** — solo il *timing*; la size minima ≥ 1 azione resta taratura |
| **T-G** | `llm_responses.eligible` deve riflettere i contributori reali del punteggio persistito | LLM | **P1** | **Sì** — sola etichettatura; il floor 0,4 resta congelato |
| **T-H** | `ensemble_std` calcolato su tutte le risposte ricevute, non sui soli contributori | LLM | **P1** | **Sì** — è il numero su cui si tarerà il gate al 28/09 |
| **T-I** | Log persistenti per api/beat/worker/worker-inference | Ops | **P1** | **Sì** — strumentazione |
| **T-J** | Suite di test: database dedicato obbligatorio, guard in `conftest.py` | Ops/Data | **P1** | **Sì** — igiene dei dati di evidenza |
| **T-K** | `execution_decisions.signal_id` popolato su tutte le decisioni, incluse le SKIP; una riga per ogni disposition del ledger #294 | Data | **P2** | **Sì** — sola tracciabilità |
| **T-L** | `trades`: persistere `reference_price`/`reference_source` e calcolare uno slippage vero | PnL | **P2** | **Sì** — strumentazione |
| **T-M** | `portfolio_cycles`: separare `target_orders_count` da `submitted_orders_count`; popolare `constraints_fired` | Ops | **P2** | **Sì** — strumentazione |
| **T-N** | Decay monitor: metriche per strategia, escludendo le strategie senza trade | Ops | **P2** | **Sì** — strumentazione |
| **T-O** | `ingestion_stats_daily`: separare `duplicates_within_run` da `duplicates_cumulative` | Data | **P3** | **Sì** — strumentazione |
| **T-P** | Prompt del cron forense: header `X-API-Key` invece di `Authorization: Bearer` | Ops | **P3** | n/a — non è codice applicativo |

---

## 16. Stato sistema

### Ollama

| Metrica | Valore |
|---|---|
| Stato | **UP per l'intera sessione** |
| Ore di downtime | **0** |
| Richieste totali | 196 (98 articoli × 2 modelli) |
| Risposte ricevute | **196/196** |
| Timeout | **0** |
| Errori / refusal / output invalido | **0** |
| `fallback_counters.consecutive_fallback` | **0** (ultimo reset 19:45:27) |
| Ultimo incremento del contatore | 2026-08-20 18:15:18 — nessun fallback consecutivo da 5 giorni |
| Coppia attiva (Redis `config:sentiment_llm_models`) | `glm52,gptoss` — **corretta**, nessun reset ad "all" |
| Pesi ensemble (`weight_update_log` id 17, 2026-08-24) | glm-5.2 **0,70** / gpt-oss **0,30**; `purified_icir` +0,104 / **−0,029**; VIX 14,89; nessun freeze |

### FinBERT

| Metrica | Valore |
|---|---|
| Chiamate di fallback | **0** |
| **FinBERT fallback rate sulle decisioni** | **0,0%** (0/98 segnali, 0/4 ordini) |
| Fallback single-model (≠ FinBERT) | **39/98 = 39,8%** — 30 volte escluso glm-5.2, 9 volte gpt-oss |
| Decisioni d'ordine da segnale single-model | **0/4** — tutte e 3 le BUY e la SELL provengono da ensemble a due modelli |

### Worker e infrastruttura

| Servizio | Stato attuale | Restart events del 2026-08-25 |
|---|---|---|
| `alembic-worker-1` | Up 2h (ricreato il 2026-08-26 ~10:30) | **non verificabile** — log persi ([DAY-005]) |
| `alembic-worker-inference-1` | Up 2h | **non verificabile** |
| `alembic-beat-1` | Up 2h | **non verificabile** |
| `alembic-api-1` | Up 2h (healthy) | **non verificabile** |
| `alembic-postgres-1` | Up 8 giorni (healthy) | 0 |
| `alembic-redis-1` | Up 8 giorni (healthy) | 0 |
| `alembic-frontend-1` | Up 8 giorni | 0 |

**Evidenza indiretta di continuità del 25:** 24 cicli portfolio su 24 slot attesi (14:07 → 19:52,
nessuno mancante); 93 snapshot mobile fra 06:02 e 20:00; ingest regolare in tutte e 6 le ore
di finestra; task serali (21:00 decay, 22:30 risk, 22:45 controfattuali) tutti eseguiti.
**Nessun buco compatibile con un riavvio durante la sessione.**

### Redis

| Chiave | Valore | Note |
|---|---|---|
| `config:sentiment_llm_models` | `glm52,gptoss` | corretta |
| `feedback:entry_threshold:S4` | `0.3` | coerente con la deroga #191 del 2026-08-07 |
| chiavi `circuit*` / `*halt*` / `*kill*` | nessuna | nessun blocco attivo |

### Libro a fine giornata

| Metrica | Valore |
|---|---|
| NAV (snapshot 20:00) | **109 958,17** |
| NAV (risk report 22:30) | 109 973,25 |
| Posizioni aperte | **48** |
| Market value | 36 030,43 |
| Unrealized P&L | **+1 097,65** |
| Gross exposure | **32,78%** (limite 50%) |
| Herfindahl | 0,0257 |
| `combined_drawdown` | 0,012429 *(massimo cumulato, vedi [DAY-020])* |
| `current_drawdown` | **null** |
| Alert attivi | **nessuno** |
| Posizioni sotto 1 azione | 12 — notional $5 492,86, UPL −$66,75, non proteggibili da stop |
| Stop GTC attivi | 8 su 48 |

---

*Report generato in modalità read-only. Nessun ordine inviato, nessun worker avviato, nessuna
pipeline rieseguita, nessun file modificato eccetto questo report e `docs/evidence/findings.json`.*
