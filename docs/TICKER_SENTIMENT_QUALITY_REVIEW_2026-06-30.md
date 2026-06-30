# Estrazione Ticker + Definizione Sentiment — Review qualitativa e specifica del ground-truth label set

Data: 2026-06-30 · Modalità: READ-ONLY · Scope: analisi critica AS-IS delle due fasi + specifica del dataset golden (QX-01) prerequisito per misurare ogni proposta di miglioramento.

> **Verifica sul vivo.** Evidenza da: codice (`src/`), docs (`docs/`), migrazioni, e query SELECT su DB produzione (llm_responses, sentiment_signals, ticker_lookup, news_log — ultimi 7/14 giorni). Nessuna modifica eseguita.

---

## 0. Executive Summary

Le due fasi **funzionano end-to-end** (news → ticker → ensemble → score → signal: 477 signal ensemble + 136 FinBERT negli ultimi 7 giorni) ma **la qualità del segnale è debole e parzialmente falsificabile**, per cause strutturali diverse nelle due fasi.

**Estrazione ticker** — l'errore peggiore non è l'estrazione in sé ma il **fallback che associa l'intera watchlist a una news senza entity metadata** (false positive di massa); la mappa `ticker_lookup` è uno snapshot statico di 89 entry senza point-in-time → look-ahead in backtest.

**Sentiment** — la confidence è **auto-riportata, compressa ~0.65 e poco discriminante** (kimi std 0.178, p50 0.65); la polarity di kimi è **quasi neutra** (mean 0.011, 22% near-zero) mentre qwen ha **bias positivo** (mean 0.116, 84 pos vs 32 neg); l'ensemble "agreement increases confidence" **è falso nel codice**; RAG/supervisor richiesti da CLAUDE.md **assenti**; backtest e live divergono (T0 contamination aperto).

Risultato empirico: **26% dei signal ensemble è near-zero** (abs(score)<0.05) e non clearerà mai la soglia S4; il sentiment è in gran parte rumore debole con una coda che guida i trade.

**Blocco metodologico:** nessuna proposta di qualità è falsificabile finché non esiste un **dataset golden etichettato** che misuri precision/recall dell'estrazione e accuracy/calibration del sentiment. Per questo la specifica del label set (QX-01, §5) è il prerequisito e precede ogni QT/QS.

---

## 1. AS-IS — Come funziona oggi

### 1.1 Estrazione ticker
5 fonti (GDELT GKG, MarketAux, Alpaca/Benzinga, SEC EDGAR, RSS) → coda Redis `news:queue` → `TickerExtractor` (lookup su `ticker_lookup`) → `sanitize_ticker` (solo nel SentimentWorker) → score. `ticker_lookup`: 89 entry (64 sp500 + 17 adr + 8 etf), popolato da CSV snapshot + INSERT statici nelle migrazioni 009/010, **nessun aggiornamento automatico**, nessun `valid_from/valid_to`. Cambi ticker (FB→META, TWTR→X, GOOG→GOOGL, BRK.A→BRK.B) solo in `_TICKER_ALIASES` hard-coded (3 entry).

### 1.2 Sentiment
`run_sentiment_worker`: ensemble 2 modelli (kimi-k2.6 + glm-5.2; qwen3.5 rimosso 2026-06-29) via `asyncio.gather` → `EnsembleAggregator`: filter conf≥0.4, divergence std≥0.30 → discard, else weighted polarity by confidence, **confidence=mean(conf) indipendente dall'accordo**. Prompt DK-CoT ma **senza few-shot** (CLAUDE.md req #3 non soddisfatta), `reasoning` una frase sola. Fallback FinBERT (entropic confidence) su timeout/budget/divergence. Score = polarity × confidence.

---

## 2. Discussione critica (con evidenza empirica)

### 2.1 Estrazione ticker

**A1 — Fallback watchlist = generatore di false positive (ALTA).** `marketaux.py:210` e `alpaca_news.py:187`: se la fonte non fornisce entity/symbols, l'articolo viene taggato con **tutti i ~89 simboli della watchlist** e enqueued N volte. Una news macro genera N signal su ticker non correlati → inquina IC e attribution. Non c'è guard che distingua "entity metadata assente" da "entity presente ma non-US" (quest'ultimo è scartato correttamente, il primo no).

**A2 — Mappa ticker statica, non point-in-time (ALTA per backtest).** Snapshot senza `valid_from/valid_to`, nessun sync con SEC `company_tickers.json`/cambi S&P. Un backtest che re-esegue GDELT storico oggi usa la mappa attuale → look-ahead. Verificato sul DB: **89 entry, 0 collisioni nome→multi-ticker** oggi (W3 latente non attiva), ma lo diventa se la mappa cresce senza disambiguazione contestuale.

**A3 — Sanitizzazione post-enqueue (MEDIA).** `sanitize_ticker` solo nel SentimentWorker, non prima dell'enqueue → ticker "sporchi" entrano in `news:queue`; incoerente col CLAUDE.md.

**A4 — Dedup cross-source debole + WebSocket bypass (MEDIA).** Stesso articolo da 3 fonti con 3 URL → 3 LLM call (README:679 ammette, content-hash dedup pre-inference mai implementato). Path `news_stream` scrive directly in `news_log` bypassando il Deduplicator Redis → double-inference se batch e stream coesistono. `news_log` non salva `org_names`/candidati scartati → **impossibile misurare precision/recall** (nessun ground-truth esiste).

### 2.2 Sentiment (con numeri dai DB vivi, 7gg)

**B1 — Confidence auto-riportata, compressa, poco informativa (HIGH).**

| model | n | mean conf | std | p25 | p50 | p75 |
|---|---|---|---|---|---|---|
| kimi | 464 | 0.648 | 0.178 | 0.60 | 0.65 | 0.75 |
| qwen3.5 | 364 | 0.649 | 0.256 | 0.44 | 0.70 | 0.85 |
| glm | 15 | 0.657 | 0.157 | 0.60 | 0.65 | 0.75 |

Confidence concentrata 0.6–0.75, usa poco [0,1]. Conseguenza: `score = polarity × 0.65` comprime il range dinamico; filtri `min_confidence=0.4` (ensemble) e `0.3` (S4) quasi mai attivi per kimi (p25=0.60). Confidence perde valore discriminante.

**B2 — Polarità: kimi neutra, qwen con bias positivo (HIGH).**

| model | mean pol | std | near_zero | pos>0.5 | neg<-0.5 |
|---|---|---|---|---|---|
| kimi | **0.011** | 0.315 | 101 (22%) | 22 | 21 |
| qwen | **0.116** | 0.412 | 107 (29%) | 84 | 32 |

Kimi quasi neutro (bilanciato 22/21 forte), qwen ha **bias long** (84 pos vs 32 neg). L'ensemble neutro+biased-long produce signal sistematicamente sbilanciati al positivo. Su 477 signal ensemble: **mean_score 0.045, std 0.269, 125 near-zero (26%)**. La coda sola guida i trade; il corpo è rumore debole.

**B3 — "Agreement increases confidence" è falso nel codice (MEDIUM).** `ensemble.py:260`: `confidence = mean(conf)`, indipendente da `ensemble_std` (docstring mente). `ensemble_std` mean = **0.060** sui signal prodotti (molto sotto soglia 0.30) → modelli concordano quasi sempre, ma la concordanza non aumenta la confidence e il disaccordo moderato non la sconta. Il discard hard a 0.30 quasi mai triggera.

**B4 — RAG e supervisor assenti (HIGH — violazione CLAUDE.md).** CLAUDE.md:75-79 richiede RAG, ensemble variance per "flag human review", supervisor agent. Codice: 0 hit RAG, nessun supervisor, ensemble variance solo hard-discard. Il `reasoning` LLM può contenere claim quantitativi ("EPS beat 12%") non verificati contro la fonte. Hallucination entra nel signal senza gate.

**B5 — Backtest/live divergence + T0 contamination aperto (HIGH).** Live: signal TTL Redis 4h, `max_signal_age_hours=4`. Backtest: `fetch_signals_for_backtest_batch` **nessun filtro età, include fallback FinBERT, nessun filtro confidence**; `max_signal_age_hours=4` e `signals_lookback_hours=96` **definiti in config ma mai letti**. P2_STATUS:71 documenta "IC T0 contamination open". → Backtest IC non riproducibile in live.

**B6 — Persistenza eligible falsa + idempotency signal assente (MEDIUM).** `llm_responses.eligible` scritto `True` hardcoded anche per modelli scartati <0.4 → LOO ICIR e audit post-hoc **non riflettono cosa è entrato nel signal**. `sentiment_signals` UNIQUE(symbol, generated_at) ma `generated_at=now()` per run → **stessa news re-processata dopo 4h genera signal duplicato**.

---

## 3. Proposte di miglioramento qualità (requisiti/ticket, non patch)

Priorità: **Q0** = alto impatto + bassa complessità / prerequisito per misurare; **Q1** = alto impatto; **Q2** = metodologico/lungo termine.

### 3.1 Estrazione ticker

| ID | proposta | problema | complessità | priorità | gate validazione |
|---|---|---|---|---|---|
| **QT-01** | Eliminare il fallback `asset_tags = list(self._symbols)`: se la fonte non fornisce entity US, scartare l'articolo o estrarre ticker dal body via cashtag/LLM. Mai associare l'intera watchlist. | A1 | bassa | **Q0** | #signal near-zero e #trades su ticker non correlati prima/dopo, su label set |
| **QT-02** | `ticker_lookup` point-in-time: `valid_from/valid_to`, sync SEC `company_tickers.json` + S&P changes, migrare `_TICKER_ALIASES` dentro la tabella con date. Backtest risolve as-of. | A2 | media | **Q1** | Backtest con lookup as-of vs attuale → differenza IC ≥0 (no leakage) |
| **QT-03** | `sanitize_ticker` all'ingestion + log candidati `org_names`/ticker scartati in `news_log` (colonne nuove). | A3/A4 | bassa | **Q0** | Ricostruire precision/recall su label set |
| **QT-04** | Content-hash dedup pre-inference (SHA title+body) nel SentimentWorker; disabilitare `run-alpaca-ingestion` beat quando `run_news_stream` attivo, o unificare. | A4 | bassa-media | **Q1** | LLM call / news unica prima/dopo; costo ↓, IC invariato |
| **QT-05** | Ground-truth label set ticker extraction (§5). | misurabilità | media | **Q0** | Dataset esiste; baseline precision/recall registrata |
| **QT-06** | Disambiguazione contestuale omonimi (lookup multipli → usa body/keyword; se ambiguo scarta). | W3 latente | media | Q2 | Su label set, riduce FP senza perdere recall |

### 3.2 Sentiment

| ID | proposta | problema | complessità | priorità | gate validazione |
|---|---|---|---|---|---|
| **QS-01** | Calibrare la confidence: smettere di usare confidence auto-riportata come peso. (a) calibrazione isotonic/Platt su `(confidence, forward_return)` storico per-modello, (b) surrogato entropico/margin dai logit, (c) ensemble agreement+margin come confidence reale. Score = polarity × confidence_calibrata. | B1 | media | **Q0** | IC/ICIR per-modello OOS con confidence calibrata vs raw → ICIR migliorato >20% relativo |
| **QS-02** | Correggere bias positivo qwen + bias neutro kimi: per-modello bias normalization (rimuovere mean polarity per-regime) o down-weight qwen nel combiner finché non calibrato. | B2 | bassa-media | **Q1** | Polarity per-modello centrata a 0; IC simmetrico long/short |
| **QS-03** | Rendere vero "agreement increases confidence": `confidence_agg = g(mean_conf, 1-ensemble_std)` con soft penalty per disaccordo moderato (0.1–0.3) invece di solo hard discard a 0.30. Flag `degraded_ensemble` quando 1 solo modello eligible. | B3/W3 | bassa-media | **Q1** | Backtest: signal con std alto hanno realized return più volatile → confidence li sconta |
| **QS-04** | Aggiungere few-shot + domain knowledge al prompt (CLAUDE.md req #3/#1): 2–3 esempi analogici + contesto fondamentali (settore, recenti earnings). `reasoning` a vera CoT multi-frase tracciabile. | W4 | bassa | **Q1** | A/B prompt su label set → polarity accuracy ↑, near_zero ↓ |
| **QS-05** | RAG + supervisor: recuperare fonte/contesto e verificare claim quantitativi nel reasoning; supervisor cross-check prima del signal store. Required CLAUDE.md. | W5 | alta | **Q1** | Tasso claim non verificati → 0; refusal/invalid logging strutturato |
| **QS-06** | Persistere `eligible` reale in `llm_responses` + **idempotency signal per (news_id, symbol)**. | B6/W7 | bassa | **Q0** | `llm_responses` riflette verità; count signal = count news unica per symbol |
| **QS-07** | Backtest/live parity: applicare in backtest `max_signal_age_hours=4`, escludere `fallback_used=True` (o separarli), filtrare `confidence` come in live. Chiudere T0 contamination. | B5/W8 | media | **Q1** | Backtest IC su signal filtrati == live IC proxy entro tolleranza |
| **QS-08** | Novelty/price-already-moved gate: non tradare news se prezzo ha già mosso >X% pre-segnale. Riduce alpha falso da lagged reaction. | W14 | media | Q2 | Su label set, signal post-move hanno forward_return ≈ 0 → gate li esclude senza perdere IC |
| **QS-09** | Backfill `news_log_id` sui signal via lookup (url,ticker) non via ON CONFLICT return None. | W9 | bassa | Q1 | NULL rate news_log_id → 0 |
| **QS-10** | Logging strutturato refusal/invalid vs timeout (ensemble.py:317 usa `print`). | W10 | bassa | Q1 | Metrica refusal_rate per modello tracciata |

### 3.3 Trasversale
- **QX-01**: dataset golden etichettato end-to-end (news → ticker corretto → sentiment atteso → forward return). **Prerequisito per misurare le due fasi. Specifica dettagliata in §5.**
- **QX-02**: dashboard qualità continua (frontend): per-modello polarity/confidence distribution, near-zero rate, fallback rate, divergence rate, extraction precision/recall vs label set. Mappa sui gap F0-01/F1-05 del frontend review.

---

## 4. Grounding del sampling frame (dati DB, 14 giorni)

| fonte | n news | n ticker distinti | body medio (char) | has_body | has_published_at | range |
|---|---|---|---|---|---|---|
| alpaca_benzinga | 407 | 203 | 138 | 407/407 | 407/407 | 06-15 → 06-29 |
| gdelt_gkg | 396 | 29 | **73** (titolo) | 396/396 | 396/396 | 06-16 → 06-29 |
| marketaux | 64 | 33 | 364 | 64/64 | 64/64 | 06-16 → 06-29 |
| **totale** | **867** | — | — | 100% | 100% | 14 giorni |

Osservazioni che vincolano il label set:
- **gdelt_gkg** ha body medio 73 char = solo titolo (`gdelt_gkg.py:208 body=title`) e risolve solo 29 ticker su 396 news → sentiment su headline, selettività alta. Il label set deve annotare "text adequacy" e trattare gdelt come categoria a sé.
- **alpaca_benzinga** 203 ticker su 407 news → copertura ampia; candidate principale per misurare il fallback-watchlist (A1) se presenti articoli con ticker sospetti.
- **marketaux** solo 64 in 14gg (free tier 100 req/day ma ~3 art/req, coverage bassa) → va **oversamplato** proporzionalmente.
- Nessuna news con `ticker` NULL o body vuoto → frame pulito.
- **Nota operativa:** last news = 2026-06-29 22:37; al momento della query (06-30) nessuna news odierna ingerita — da verificare se l'ingestion è in pausa (fuori scope, ma rilevante per il campionamento futuro).

---

## 5. Specifica del ground-truth label set (QX-01) — approfondimento

### 5.1 Obiettivo
Produrre un dataset etichettato **end-to-end** che consenta di misurare, in modo falsificabile e ripetibile:
1. **Estrazione ticker**: precision, recall, FP/FN rate per fonte e per modalità (lookup vs fallback watchlist).
2. **Sentiment**: polarity sign-accuracy, calibration (Brier, ECE), near-zero correctness, bias per-modello.
3. **End-to-end**: IC (Spearman score vs forward_return) per model, per source, per regime.
4. **Falsificabilità**: ogni proposta QT/QS viene validata contro questo set prima di essere accettata.

Principio **Alpha Miner preservato**: il label set è usato **solo offline** da script di validazione, mai nel hot path di esecuzione.

### 5.2 Unità di labeling
Una **news item** = riga di `news_log` (identificata da `id`). Ogni news item ha già: `id, title, url, source, ticker (estratto dal sistema), body_snippet, raw_sentiment, fetched_at, published_at`. L'annotatore valuta la news **indipendentemente** dal ticker estratto dal sistema (blind), poi si confronta.

### 5.3 Schema (tabella `news_labels`, nuova)

| colonna | tipo | descrizione |
|---|---|---|
| `label_id` | bigint PK | id label |
| `news_log_id` | bigint FK→news_log.id | item etichettato |
| `url`, `source`, `fetched_at`, `published_at` | copia da news_log | denormalizzato per query |
| `extracted_ticker` | text | ticker estratto dal sistema (per confronto) |
| `annotator_id` | text | chi ha etichettato |
| `label_date` | timestamptz | quando |
| `adjudicated` | bool | passato per disaccordo? |
| `adjudicator_id` | text | chi ha risolto |
| `gt_tickers` | text[] | ticker ground-truth (può essere vuoto = news non company-specific) |
| `gt_relevance` | enum | `company_specific` / `sector` / `macro` / `irrelevant` |
| `gt_sentiment_dir` | enum | `positive` / `negative` / `neutral` |
| `gt_sentiment_strength` | float | [-1,1] (0=neutro, ±1=forte) |
| `gt_rationale` | text | motivazione breve (per audit) |
| `text_adequacy` | enum | `full` / `headline_only` / `insufficient` (gdelt=headline_only) |
| `extraction_correct` | bool | extracted_ticker ∈ gt_tickers |
| `extraction_fp` | bool | extracted_ticker ∉ gt_tickers (falso positivo) |
| `extraction_fn` | text[] | gt_tickers non estratti (falsi negativi) |
| `fallback_watchlist_used` | bool | se l'estrazione è caduta nel fallback A1 (richiede QT-03 logging) |
| `forward_return_1h` | float | ritorno +1h close-to-close dal `published_at` |
| `forward_return_1d` | float | ritorno +1d |
| `forward_return_2d` | float | ritorno +2d |
| `price_source` | text | fonte prezzo usata (yfinance/alpaca/—) |
| `notes` | text | annotazioni libere |

Uniqueness: `UNIQUE(news_log_id, annotator_id)` (2 annotatori per item).

### 5.4 Sampling frame & strategia

Frame disponibile: 867 news / 14 giorni / 3 fonti. **Target fase 1: ~400 item etichettati** (200 per extraction+direction, +200 per calibration). Stratificazione:

| fonte | frame | target fase 1 | sovra-campionamento |
|---|---|---|---|
| alpaca_benzinga | 407 | 180 | oversample articoli con sospetto fallback-watchlist (≥6 ticker estratti) e |raw_sentiment|<0.05 |
| gdelt_gkg | 396 | 150 | oversample near-zero polarity (22% già neutri) e i 29 ticker distinti (coverage completo) |
| marketaux | 64 | 70 (oversample 100% fase 1) | N piccolo + body lungo → alta resa informativa |

Sovra-campionamento mirato ai **failure mode** (per massimizzare informazione per unità di costo di annotazione):
- **F1** articoli dove l'estrazione ha usato il fallback watchlist (flag `fallback_watchlist_used` dopo QT-03) → misura diretta di A1.
- **F2** articoli near-zero (|score|<0.05) → verifica che siano davvero neutrali (calibration).
- **F3** articoli multi-ticker nel `gt_tickers` → misura recall multipla.
- **F4** articoli off-market-hours vs market-hours → regime/latency.

Stratificazione temporale: 50% market hours (13:30–20:00 UTC), 50% off; weekdays distribuiti.

Random seed fisso per riproducibilità (nessun `Math.random` in script di sampling — seed hardcoded).

### 5.5 Protocollo di annotazione

1. **Blind**: l'annotatore vede `title + body_snippet + source + published_at`, **non** vede il ticker estratto dal sistema (evita bias di conferma). Decide `gt_tickers`, `gt_relevance`, `gt_sentiment_dir/strength`.
2. **2 annotatori indipendenti** per item.
3. **Rubric** (definizioni scritte, parte della specifica):
   - `gt_relevance`: `company_specific` = news materialmente su risultati/prodotto/guida di quella specifica azienda; `sector` = news di settore che la tocca indirettamente; `macro` = FED/rates/macro senza link azienda-specifico; `irrelevant` = off-topic.
   - `gt_sentiment_dir`: positive = prevedibilmente bullish per cash flow/competitività; negative = bearish; neutral = non materiale o ambiguo.
   - `gt_sentiment_strength`: 0±0.2 neutro/debole; ±0.2–0.6 moderato; ±0.6–1 forte. Rubric con esempi annotati.
4. **Adjudication**: disaccordo → terzo annotatore (adjudicator) decide; record `adjudicated=true`.
5. **Inter-annotator agreement**: target **Cohen's κ ≥ 0.6** (substantial) per ticker (exact match o overlap), **κ ≥ 0.7** per direction. Sotto soglia → rubric da rifinire prima di continuare.
6. **Tool**: form semplice (CSV/PG o UI minimale in seguito); nessuna dipendenza pesante in fase 1.

### 5.6 Forward return — definizione e vincoli

- Orizzonti: **+1h** (intraday, allineato a `counterfactual_return_1h` già in `execution_decisions`), **+1d**, **+2d** close-to-close.
- Prezzo: adjusted close da fonte esterna. **Dipendenza critica**: yfinance è risk register R-09 (affidabilità EMA20/drawdown) → per il label set serve una **fonte prezzo affidabile** (Alpaca historical bars paper, o un provider di reference). Da definire prima di popolare `forward_return_*`.
- **Point-in-time**: prezzo calcolato al `published_at` (o primo market open successivo se off-hours), mai look-ahead. Usare prezzo di chiusura, non intraday futuro.
- Survivors: il label set misura forward return solo su ticker liquidi in watchlist; documentare i delistati come non calcolabili.

### 5.7 Metriche abilitate (per fase)

| metrica | formula | fase |
|---|---|---|
| Extraction precision | Σ extraction_correct / Σ extracted | ticker |
| Extraction recall | Σ gt_tickers trovati / Σ gt_tickers | ticker |
| FP rate | Σ extraction_fp / n | ticker |
| FN rate | Σ |extraction_fn| / Σ gt_tickers | ticker |
| Polarity sign accuracy | Σ sign(score)==gt_dir / n (esclusi gt_neutral) | sentiment |
| Calibration (Brier) | mean((confidence − |gt_strength|)²) | sentiment |
| Calibration (ECE) | expected calibration error per bin | sentiment |
| Near-zero correctness | P(gt_neutral | abs(score)<0.05) | sentiment |
| Per-model bias | mean(polarity | gt_neutral) per model | sentiment |
| IC end-to-end | Spearman(score, forward_return_1d) per model/source/regime | end-to-end |
| ICIR | IC/std(IC) per window | end-to-end |

Ogni metrica è calcolata **per source** e **per failure-mode** (fallback vs no, near-zero vs no).

### 5.8 Integrazione & harness di validazione

- Script offline `scripts/validate_ticker_sentiment.py` (read-only, non in hot path): legge `news_labels`, join con `news_log`/`llm_responses`/`sentiment_signals`, produce le metriche §5.7 in un report JSON/markdown.
- **CI gate** (soft in fase 1, hard dopo baseline): una modifica a QT/QS non è accettata se non migliora la metrica target sul label set senza peggiorare le altre oltre un delta.
- **Holdout**: il label set va diviso in **train (calibrazione QS-01) / test (validazione)** 60/40; non calibrare e validare sullo stesso split (overfit del label set stesso).

### 5.9 Sizing & rollout

- **Fase 1 (2-3 sett.)**: 400 item etichettati → baseline precision/recall estrazione + polarity accuracy + IC end-to-end. Sblocca QT-01/03/05, QS-01/06.
- **Fase 2 (4-6 sett.)**: +300 item → calibrazione isotonic confidence (QS-01), validazione bias correction (QS-02).
- **Fase 3 (continuo)**: 50 item/sett. campionati automaticamente → **drift monitor** (quality degradation detection, R-05 LLM divergence).

### 5.10 Rischi e limiti del label set

1. **Annotator bias / rubric soggettiva**: mitigato da 2 annotatori + κ target + adjudication.
2. **Fonte prezzo inaffidabile** (yfinance R-09): blocca `forward_return_*`; serve fonte reference prima di Fase 2.
3. **gdelt body=headline (73 char)**: sentiment etichettato su titolo solo → la metrica di sentiment su gdelt misura "headline sentiment", non full-text. Documentare come limitazione; non comparare directly con marketaux (364 char).
4. **Survivorship price**: forward return solo su ticker attivi; introdurre bias noto.
5. **Overfit del label set**: tuning di QT/QS sul label set può overfittare la distribuzione del campione → holdout + drift monitor.
6. **Costo annotazione**: ~400 item × 2 annotatori ≈ 800 giudizi; stimare 5-10 min/giudizio → ~80-130h lavoro umano. Prioritizzare F1-F4 oversampling per massimizzare informazione.
7. **Distribuzione non stazionaria**: il frame è 14 giorni; eventi rari (M&A, earnings surprise) sottorappresentati → Fase 3 drift monitor li cattura nel tempo.

---

## 6. Sequenza di implementazione raccomandata (dipendenze)

1. **QT-03** (logging candidati + `fallback_watchlist_used` flag) → prerequisito per misurare A1 sul label set.
2. **QX-01 Fase 1** (400 label) → baseline misurabile.
3. **QT-01** (elimina fallback watchlist) → validato sul label set (precision ↑).
4. **QS-06** (eligible reale + idempotency signal) → dati puliti per calibration.
5. **QS-01 + QS-02** (calibrazione confidence + bias correction) → validato su holdout (ICIR >20%).
6. **QT-02** (ticker_lookup PIT) → validato (no leakage in backtest).
7. **QS-03/04/05** (agreement-confidence, few-shot, RAG/supervisor) → A/B su label set.
8. **QS-07** (backtest/live parity) → chiude T0 contamination.
9. **QX-02** (dashboard qualità continua) → frontend.
10. **QX-01 Fase 2/3** (calibration + drift monitor) → continuo.

---

## 7. Stop point

Non ho modificato file, codice, config né DB. Read-only: lettura codice/docs + query SELECT su DB produzione. Le proposte QT/QS/QX sono requisiti/ticket da validare con i gate indicati prima di qualunque implementazione. Non propongo di promuovere strategie né di andare live. Il label set (QX-01) è specificato come design, non implementato; la sua costruzione richiede annotazione umana e una decisione sulla fonte prezzo (dipendenza R-09).