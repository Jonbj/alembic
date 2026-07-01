# S4 News-Pipeline — R&D Backlog (2026-06-29)

**Tipo:** backlog R&D · **Scope:** miglioramenti alla pipeline news→sentiment→segnale di S4
**Origine:** cross-check con un'analisi esterna (ChatGPT, 29/06/2026) su "migliori LLM cloud per estrarre ticker e decidere buy/sell", filtrata criticamente contro l'architettura reale di Alembic.

---

## Stato: IMPLEMENTAZIONE AVVIATA (freeze annullato dal PO, 2026-06-30)

Il vincolo di validazione/freeze è stato esplicitamente **revocato dal PO**: si procede con gli sviluppi.
Design di riferimento completo: **`docs/Alembic_ticker_sentiment_design.docx`** (v1.0, 2026-06-29) — separazione
formale di **entity extraction / ticker resolution / issuer-specific sentiment**, resolver deterministico,
FinBERT come auditor, gate NO_TRADE per ambiguità.

### Implementation status

| Item | Stato | Commit |
|---|---|---|
| Bug confidence² nel ranking S4 (rank by `score`, non `score×confidence`) | ✅ **DONE** | `e5927de` |
| **Increment 1 — Ticker false-positive guard** (cashtag + soglia lunghezza + parole comuni) nel path RSS regex | ✅ **DONE** | questo commit |
| **Resolver deterministico — decision core** (scoring §4.4, gate NO_TRADE §4.3, directness §4.2) | ✅ **DONE** | `dc5921d` |
| **Resolver — provider esterni** (OpenFIGI + SEC company_tickers + alias + tradability, `gather_evidence`) | ✅ **DONE, verificato live** (AAPL→RESOLVED, garbage→NO_TRADE, SEC NVIDIA→NVDA) | questo commit |
| **QT-01 — Drop watchlist fallback** (marketaux/alpaca: no entity → cashtag, mai watchlist intera) | ✅ **DONE** | `e1845c7` |
| **Punto 1a — schema + prompt arricchito** (`event_type`/`directness`/`materiality`/`novelty`/`risk_flags`/`evidence_sentences` in `LLMSentimentOutput`, prompt issuer-specific + no buy/sell/hold) | ✅ **DONE** (backward-compatible, default neutri) | `137861a` |
| **QS-06 — eligible reale** (`llm_responses.eligible = confidence ≥ soglia`, non hardcoded True) | ✅ **DONE, deployed** | `fb24dec` |
| **QS-07 — backtest/live parity** (`_signals_as_of` applica `max_signal_age_hours`; chiude la T0 contamination) | ✅ **DONE, deployed** (solo backtest, zero impatto live) | `b4421f2` |
| **QT-03 — provenance estrazione** (`news_log.extraction_method`: source_metadata / cashtag / org_lookup / regex; migr. 030) | ✅ **DONE, deployed** | `71a98e5` |
| **QS-09 — backfill news_log_id** (SELECT esistente su conflitto → news_log_id mai NULL) | ✅ **DONE, deployed** | `33f52e5` |
| **QS-10 — logging strutturato fallimenti ensemble** (kind timeout/invalid/error, no più `print`) | ✅ **DONE, deployed** | `33f52e5` |
| **QX-01 tooling** — tabella `news_labels` (migr. 029), sampling 148 stratificato, UI Labeling **blind**, forward-return Alpaca, harness `validate_ticker_sentiment.py` | ✅ **DONE, live** (annotazione in corso) | `9d21215`, `537471f` |
| **QX-02 — dashboard qualità** (`/quality`: distribuzione per-modello, near-zero/fallback rate, precision estrazione dal label set) | ✅ **DONE, live** | `0dcf4da` |
| **QS-03 — agreement→confidence** (confidence scontata dalla divergenza, dietro flag `agreement_weighting`) | ✅ **DONE** (default OFF: cambia live score → attivare post-QX-01) | `fb24dec` |
| Punto 1b — gate `risk_flags` + weighting `materiality×directness` sul live score | ⏳ **gated su QX-01** (calibrazione/label set: cambia comportamento, non falsificabile senza misura) | — |
| Resolver — **shadow mode wired (Fase A)** (`news_resolved_entities` migr. 031 + `resolver_shadow.py`; verdetto persistito per ogni news, **no gating**) | ✅ **DONE, deployed** (verificato live: XLF/XLE→NO_TRADE_LOW_CONF, XLI/XLC→NO_TRADE_NOT_TRADABLE) | `565bb89` |
| Resolver — enforcement (decision != RESOLVED → no signal tradabile) | ⏳ **gated su QX-01** (shadow → calibrazione → enforce) | — |
| B3 — novelty evento + already-priced | 📋 roadmap Fase 5 | — |
| Issuer-specific sentiment (FinBERT su evidence sentences) | 📋 roadmap Fase 2-3 | — |
| Harness IC per-modello (LOO-ICIR) | 📋 roadmap Fase 5 | — |

### Cross-reference con `TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md` (altro agente)
Il quality review (empirico, query sui DB vivi) **conferma e prioritizza**: (1) il vero generatore di
false-positive è il **fallback watchlist** (A1 → QT-01, **fatto**); (2) sul sentiment i fix ad alto valore
sono **calibrazione confidence (QS-01)** e **bias correction qwen (QS-02)** — più dell'arricchimento schema;
(3) **blocco metodologico**: nulla è falsificabile senza il **golden label set (QX-01)**, che richiede
annotazione umana + una **fonte prezzo affidabile** (R-09, non yfinance). Conseguenza: enforcement
(Punto 1b, resolver, QS-01) è correttamente **gated su QX-01**.

**Aggiornamento 2026-06-30** — il binario di misura QX-01 è **costruito e live**: tabella `news_labels`,
sampling 148 (Fase 1: 150, 1 annotatore, blind), UI **Labeling** (`/labeling`), harness extraction, e
dashboard **Quality** (`/quality`). **Fonte prezzo decisa: Alpaca historical** (forward return 1h/1d/2d
point-in-time, automatici). QT-03 (provenance) **fatto**. Primo baseline pre-fix (17 annotate): precision
estrazione **0.24**, macro-FP **2.0** — conferma quantitativa del problema. Resta: completare l'annotazione →
forward return → sentiment sign-accuracy + IC end-to-end → calibrazione QS-01/QS-02 → enforce con gate misurati.

Roadmap a fasi (dal design doc §11): Fase 1 resolver + `news_resolved_entities` → Fase 2 issuer sentiment →
Fase 3 FinBERT auditor → Fase 4 gate portfolio (`resolution_confidence`/`directness`/`ambiguity_margin`) →
Fase 5 backtest+LOO-ICIR → Fase 6 auto-improve (threshold per event_type/fonte).

---

## 1. Cosa Alembic fa GIÀ (non rifare)

L'analisi esterna in larga parte *conferma* l'architettura esistente:

| Principio | Implementazione attuale |
|---|---|
| LLM offline, produce feature non ordini (Alpha Miner) | `score = polarity × confidence` → Redis → execution legge al tick |
| Output JSON strutturato / function calling | `LLMSentimentOutput` Pydantic + `response_schema` (`src/workers/sentiment.py:123`) |
| Ensemble + variance + fallback | Kimi + GLM-5.2 (Qwen3.5 sostituito, commit `150d2c2` 2026-06-29); divergence → fallback FinBERT |
| Tiering di costo | pre-filtro MarketAux (skip near-neutral `|sent|<0.20` → −60-80% token) + fallback FinBERT a budget esaurito |
| Dedup articoli | `src/connectors/deduplicator.py` |
| Estrazione ticker | `src/connectors/ticker_extractor.py` |
| Valutazione multi-modello | model tournament (`docs/model-tournament-workflow.md`, branch `feat/fb-*_cloud`) |

**Schema sentiment attuale (minimale):** `{polarity, confidence, reasoning}` (`src/workers/sentiment.py:60-72`).

---

## 2. Backlog (prioritizzato)

### B1 — Schema del segnale arricchito  ·  priorità ALTA
**Problema:** l'LLM produce solo polarity/confidence/reasoning. Si perdono segnali con valore di trading.
**Codice attuale:** `_DK_COT_PROMPT` + `LLMSentimentOutput` in `src/workers/sentiment.py`.
**Proposta:** estendere il Pydantic schema + il prompt DK-CoT con:
- **`risk_flags`**: `rumor | already_priced_in | ambiguous_entity | low_source_quality` → usati come **gate di esecuzione** (S4 non apre su rumor/entità ambigua/fonte scarsa). *Nota:* `already_priced_in` NON va chiesto all'LLM (vedi §3) — calcolarlo esterno (B3).
- **`event_type`**: `earnings | guidance | mna | regulatory | lawsuit | product | macro | analyst_rating | insider | other` → **routing**: `earnings` → S7 PEAD (già esistente); `mna`/`regulatory` → gestione dedicata.
- **`materiality`** [0,1] e **`time_horizon`** (`intraday|1-5d|1-3m|long`) → pesare il segnale e scegliere l'holding period.
- **`evidence`**: frasi chiave dall'articolo (auditabilità — si lega alla review frontend su why-trade).
**Perché:** migliora qualità segnale e auditabilità; sblocca routing per-evento.
**Rischio:** prompt più lungo = più token (mitigabile col tiering esistente); più campi = più superficie di allucinazione → validare ogni campo (specie `materiality`).
**Acceptance:** schema esteso + gate `risk_flags` testati; misurare IC con/senza i nuovi campi sul model tournament prima di promuovere.
**Dipendenze:** nessuna per i gate; `event_type→S7` richiede wiring combiner.

### B2 — Resolver esterno del ticker con confidence  ·  priorità ALTA
**Problema:** `ticker_extractor.py` non valida contro un'autorità esterna. Rischio ticker errato su ADR / dual-listing / omonimie (es. INFY ADR vs locale, "AI", "META").
**Proposta:** dopo l'estrazione entità dell'LLM, risolvere con **OpenFIGI** e/o **SEC `company_tickers`** → `{resolved_ticker, exchange, isin_or_figi, resolution_confidence}` + flag `ambiguous_entity`. Sotto una soglia di confidence → scartare il segnale (o marcarlo `ambiguous_entity` per B1).
**Perché:** riduce trade su ticker sbagliato; entrambi i provider sono free e pensati per symbology.
**Rischio:** chiamata esterna in pipeline offline (non hot-path, ok); rate limit → cache locale.
**Acceptance:** resolver con cache + confidence; test su ADR/dual-listing noti; segnali sotto soglia scartati.
**Dipendenze:** nessuna (sostituisce/avvolge `ticker_extractor`).

### B3 — Novelty / "già prezzata" calcolata esternamente  ·  priorità MEDIA
**Problema:** il dedup attuale è a livello articolo, non risponde a "questa notizia muove ancora il prezzo o è già prezzata?".
**Proposta:** combinare (a) dedup vs coverage precedente (esteso da `deduplicator.py`) + (b) check **price/volume-already-moved** (se il titolo si è già mosso sulla notizia → non inseguire). Output: `novelty` [0,1] usato come gate/peso.
**Perché:** evita di inseguire news stantie/già scontate — uno dei modi principali in cui le strategie news perdono.
**Rischio:** definire "già mosso" richiede dati prezzo intraday affidabili (vedi R-09 yfinance nel residual risk register).
**Acceptance:** `novelty` calcolata senza LLM; backtest che mostri riduzione di trade su news già prezzate.

### B4 — Selezione modello guidata dal tournament (non dai nomi)  ·  priorità BASSA
**Problema:** la tentazione di scegliere "il modello migliore" per nome (GPT-5.x, Opus 4.x, Gemini 3.x).
**Proposta:** nessun cambio per nome. Usare il **model tournament esistente** per misurare IC/accuratezza di estrazione sul *nostro* dataset, e il tiering esistente (economico sul volume, frontier solo sugli ambigui/alta materiality). Eventuale uso di un cloud frontier solo nel path **offline** (compatibile con l'Alpha Miner) e solo se il tournament lo giustifica sul rapporto IC/costo.
**Perché:** i nomi cambiano ogni mese e sono già stantii (l'analisi citava "Opus 4.7" quando esiste 4.8); il costo cloud su ogni articolo è insostenibile per il budget infra (~$1440/anno).

---

## 3. Respinti / cautele (dall'analisi esterna)

- **`already_priced_in` / `novelty` auto-riportati dall'LLM → RESPINTO.** Il modello non *sa* cosa è prezzato. Calcolare esterno (B3). È il campo meno affidabile da chiedere a un LLM.
- **Cloud frontier su ogni news → RESPINTO per costo.** Il tiering esistente è la risposta corretta.
- **Scegliere modelli per nome → RESPINTO.** Misurare col tournament.
- **Validità statistica:** il backtest WSJ citato (strategie LLM raramente battono buy-and-hold su 20 anni) *rafforza* la disciplina attuale — validare IC>placebo prima di scalare S4. Da tenere come promemoria anti-overconfidence.

---

## 4. Sequenza consigliata (dopo la validazione)

1. **B1 gate `risk_flags` + `event_type`** (estende schema, basso rischio, alto valore) — misurare IC.
2. **B2 resolver OpenFIGI/SEC** (riduce errori ticker, indipendente).
3. **B3 novelty/already-priced esterna** (richiede dati prezzo affidabili).
4. **B4** è continuo, non un ticket: usare il tournament per ogni scelta modello.

Ogni step: TDD, misurato sul model tournament, S4 resta `promotion_blocked` finché IC>placebo non è confermato.

---

## 5. Riferimenti

- Pipeline sentiment: `src/workers/sentiment.py` · ensemble `src/llm/ensemble.py` · client `src/llm/client.py`
- Ticker: `src/connectors/ticker_extractor.py` · dedup `src/connectors/deduplicator.py`
- Strategie: S4 (news), S7 PEAD (earnings drift) — `config/strategies.yaml`
- Tournament: `docs/model-tournament-workflow.md`, branch `feat/fb-*_cloud`
- Vincoli: `docs/RESIDUAL_RISK_REGISTER.md` (R-09 yfinance), `CLAUDE.md` (Alpha Miner, DK-CoT, hallucination mitigation)
- Memoria correlata: capital-deployment/regime (regime_mult come collo di bottiglia del deployment)

---

## 6. Stop Point

Questo è un documento di backlog R&D read-only. Non ho modificato S4, la pipeline news, lo schema sentiment, né alcun parametro di trading. Non ho autorizzato modifiche durante la finestra di validazione, né promozioni, né live trading. Gli item vanno ripresi a fine validazione e misurati prima di qualsiasi promozione.
