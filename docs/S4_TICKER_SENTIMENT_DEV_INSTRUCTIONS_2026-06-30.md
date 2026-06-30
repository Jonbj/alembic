# S4 News Pipeline — Development Instructions

Data: 2026-06-30
Scope: indicazioni operative per sviluppo su pipeline news -> ticker -> sentiment -> signal -> ordine.

## 1. Obiettivo

Rendere S4 misurabile e piu sicura prima di qualunque promozione:

1. Il ticker deve essere risolto da un resolver deterministico, non deciso implicitamente dalla fonte o dall'LLM.
2. Il sentiment deve essere issuer-specific e usare confidence calibrata, non solo auto-riportata.
3. Il passaggio da news a ordine deve avere una soglia unica e documentata, coerente tra codice, config e documentazione.
4. Ogni cambiamento che modifica score o gating live deve essere validato su QX-01 prima di enforcement.

Non autorizzare live trading, non promuovere S4, non aumentare allocation.

## 2. Stato Attuale Da Tenere Presente

S4 e attiva solo come overlay paper al 10%, con `promotion_blocked=true`.

Il path operativo e `execution.engine: portfolio`, non il legacy `run-execution`.

Soglie attuali:

- Legacy `ExecutionWorker`: BUY se `score > 0.30`, signal fresco 30 minuti, no FinBERT fallback, EMA20 pass.
- Portfolio/S4 attivo: `S4Config.min_score = 0.10`, `min_confidence = 0.30`, `max_signal_age_hours = 4`, top-N ranking, minimo 2 titoli.
- Loss feedback puo alzare la soglia dinamica fino a `0.60`; baseline config `0.30`.

Questo mismatch va corretto o almeno reso esplicito. La documentazione corrente spesso descrive il gate legacy `score > 0.30 AND price > EMA20`, ma il portfolio path usa il ranker.

## 3. Vincoli Non Negoziabili

- Nessuna chiamata LLM nel trading loop.
- Nessun ordine se il ticker e ambiguo, non tradable, o a bassa confidence di risoluzione.
- Nessun fallback alla watchlist intera.
- Nessun uso di `buy/sell/hold` emesso dall'LLM come decisione operativa.
- Ogni modifica che cambia score/gate deve essere dietro flag o validata da QX-01.
- I backtest devono usare gli stessi filtri live: freshness, fallback policy, confidence policy.
- Non usare yfinance per nuove metriche di validazione se Alpaca historical e disponibile.

## 4. Sequenza Implementativa Raccomandata

### Fase A — Resolver Ticker In Shadow

Obiettivo: calcolare e salvare la risoluzione ticker senza bloccare ancora i signal live.

Azioni:

1. Cablare `src/connectors/ticker_resolver.py` e `ticker_resolver_providers.py` nel path ingestion/sentiment.
2. Per ogni news/ticker candidato salvare:
   - `resolved_ticker`
   - `resolution_confidence`
   - `ambiguity_margin`
   - `directness`
   - `tradable`
   - `decision`
   - evidenze usate: source metadata, cashtag, alias, SEC/OpenFIGI, LLM agreement.
3. Creare o completare una tabella tipo `news_resolved_entities`.
4. Non cambiare ancora lo score live in questa fase.

Acceptance:

- Test unitari per `RESOLVED`, `NO_TRADE_LOW_RESOLUTION_CONFIDENCE`, `NO_TRADE_AMBIGUOUS_TICKER`, `NO_TRADE_NOT_TRADABLE`, `NO_TRADE_UNCLEAR_ISSUER_IMPACT`.
- Dashboard/quality o query leggibile per confrontare resolver vs `news_labels`.
- Nessun incremento di signal generati rispetto al comportamento attuale.

### Fase B — Resolver Enforcement

Obiettivo: impedire che ticker non risolti entrino nel signal tradabile.

Prerequisito:

- QX-01 con numero sufficiente di label e baseline precision/recall.

Regole:

- Se `decision != RESOLVED`, non scrivere signal tradabile.
- Se `resolution_confidence < 0.80`, `NO_TRADE_LOW_RESOLUTION_CONFIDENCE`.
- Se `ambiguity_margin < 0.15`, `NO_TRADE_AMBIGUOUS_TICKER`.
- Se `tradable is false`, `NO_TRADE_NOT_TRADABLE`.
- Se `directness == unclear`, `NO_TRADE_UNCLEAR_ISSUER_IMPACT`.

Acceptance:

- Precision ticker migliora sul holdout QX-01.
- Macro/irrelevant false positive tende a zero.
- Recall persa documentata e accettata: per S4 e preferibile perdere news valide che tradare ticker sbagliati.

### Fase C — Sentiment Issuer-Specific Completo

Obiettivo: se una news cita piu emittenti, produrre sentiment separato per ciascun issuer risolto.

Azioni:

1. Non usare piu solo `asset_tags[0]` quando una news contiene piu ticker.
2. Per ogni resolved entity creare un prompt issuer-specific con evidence pertinente.
3. Persistire componenti separate:
   - polarity
   - confidence raw
   - confidence calibrated
   - materiality
   - directness
   - novelty
   - source_quality
   - event_type
   - risk_flags
   - evidence_sentences
4. FinBERT deve auditare solo evidence sentences per issuer, non decidere ticker.

Acceptance:

- Una news multi-ticker puo produrre sentiment positivo per un issuer e negativo/neutro per un altro.
- FinBERT non viene mai usato per ticker resolution.
- Test con esempi ambigui: Apple Hospitality/APLE vs Apple/AAPL, AI tema vs ticker AI, OpenAI/MSFT indiretto.

### Fase D — Confidence Calibration

Obiettivo: sostituire la confidence auto-riportata con una confidence utile per trading.

Azioni:

1. Usare `news_labels` + forward returns Alpaca per stimare calibration per modello.
2. Valutare almeno:
   - Brier score
   - ECE
   - sign accuracy
   - IC / ICIR per modello e fonte
3. Implementare `confidence_calibrated` separata da `confidence_raw`.
4. Non sovrascrivere la raw confidence: serve per audit.

Acceptance:

- ICIR OOS migliora rispetto a raw confidence o resta invariato con minore turnover.
- Bias per modello misurato prima/dopo.
- Nessuna calibrazione addestrata e validata sullo stesso split.

### Fase E — Score Finale S4

Obiettivo: passare da score minimale a score materiality/directness-aware.

Formula candidata, da attivare solo dopo QX-01:

```text
final_news_score =
    polarity
  * confidence_calibrated
  * materiality
  * directness_multiplier
  * source_quality
  * novelty
  * event_type_weight
```

Regole:

- `novelty` e `already_priced_in` non devono essere fidati se auto-riportati dall'LLM.
- `novelty` va calcolata con dati esterni: dedup contenuto, copertura precedente, price/volume move pre-signal.
- `risk_flags` come `rumor`, `ambiguous_entity`, `low_source_quality` devono poter forzare `NO_TRADE`.

Acceptance:

- Backtest/live parity mantenuta.
- IC per event_type/source/regime misurato.
- Score componenti visibili in audit/debug.

### Fase F — Soglia News -> Ordine

Obiettivo: eliminare il mismatch tra threshold legacy e S4 portfolio.

Decisione richiesta:

Scegliere uno dei due modelli e allineare codice + docs + config:

1. Modello threshold:
   - BUY candidate se `score > 0.30`
   - opzionale EMA20/momentum gate
   - piu semplice e coerente con documentazione storica.
2. Modello ranker:
   - candidate se `score >= min_score`, `confidence >= min_confidence`
   - ranking top-N
   - threshold dinamica loss feedback applicata prima del ranking.

Raccomandazione:

- Mantenere il modello ranker solo se viene documentato come source of truth.
- Rinominare/centralizzare la soglia per evitare tre concetti diversi: `ENTRY_THRESHOLD`, `S4Config.min_score`, `loss_feedback.threshold_baseline`.
- Se `0.30` resta baseline di trading, allora `S4Config.min_score=0.10` deve essere interpretato solo come prefilter, non come soglia d'ordine.

Acceptance:

- Un test end-to-end dimostra perche un signal con score `0.18`, `0.31`, `0.55` viene comprato o scartato.
- Decision log registra `SKIP_THRESHOLD`, `SKIP_STALE`, `SKIP_RESOLUTION`, `SKIP_RISK_FLAG`, `SKIP_FALLBACK`.
- Documentazione aggiornata in `docs/strategies.md`, `docs/ARCHITECTURE.md`, `docs/user_guide.md`.

## 5. File Rilevanti

Ticker:

- `src/connectors/ticker_extractor.py`
- `src/connectors/ticker_resolver.py`
- `src/connectors/ticker_resolver_providers.py`
- `src/connectors/marketaux.py`
- `src/connectors/alpaca_news.py`
- `src/connectors/cashtag.py`

Sentiment:

- `src/workers/sentiment.py`
- `src/llm/ensemble.py`
- `src/llm/finbert.py`
- `src/models/news.py`
- `src/models/signals.py`
- `src/store/pg_store.py`

S4/order path:

- `src/strategies/s4/config.py`
- `src/strategies/s4/ranking.py`
- `src/strategies/s4/strategy.py`
- `src/workers/portfolio_scheduler.py`
- `src/workers/execution.py`
- `config/trading.yaml`
- `config/strategies.yaml`

Quality/labeling:

- `migrations/029_news_labels.sql`
- `migrations/030_news_log_extraction_method.sql`
- `scripts/sample_news_labels.py`
- `scripts/compute_label_forward_returns.py`
- `scripts/validate_ticker_sentiment.py`
- `src/api/routes/quality_routes.py`

## 6. Test Minimi Richiesti

Unit:

- Resolver decision core.
- Provider evidence fail-open.
- Cashtag fallback senza watchlist fallback.
- Ensemble confidence gating e agreement weighting.
- S4 ranker: soglia, min confidence, min stocks, negative signal skip.

Integration:

- News senza ticker -> nessun signal tradabile.
- News con ticker ambiguo -> `NO_TRADE_*`.
- News multi-ticker -> piu issuer sentiment separati.
- FinBERT fallback non sovrascrive ensemble fresco.
- Backtest `_signals_as_of` applica freshness come live.

Quality:

- `validate_ticker_sentiment.py` produce metriche per source e extraction method.
- Forward returns popolati con Alpaca historical.
- Report prima/dopo ogni modifica QS/QT.

## 7. Cosa Non Fare

- Non abbassare/alzare soglie per ottenere piu trade senza IC/label evidence.
- Non usare LLM per decidere ticker finale.
- Non usare LLM per decidere `already_priced_in` come verita.
- Non attivare `agreement_weighting` live senza confronto su QX-01.
- Non promuovere S4 da paper.
- Non modificare allocation S4 oltre 10%.
- Non trattare FinBERT fallback come equivalente all'ensemble per decisioni di ingresso.

## 8. Definition Of Done

Il lavoro e completo solo quando:

1. Ogni signal tradabile ha ticker resolution tracciabile.
2. Ogni skip critico appare nel decision log con reason.
3. QX-01 misura precision/recall ticker e sentiment sign accuracy.
4. Score finale e soglia di ingresso sono univoci e documentati.
5. Backtest e live usano gli stessi filtri.
6. S4 resta `promotion_blocked` finche IC>placebo, shuffled-news test e 90-day paper evidence non sono disponibili.

