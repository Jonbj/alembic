# Alembic — Data & Alpha Roadmap

**Data:** 2026-07-02
**Autore:** Senior Data/Product Reviewer (sessione di review read-only)
**Stato:** Proposta — nessun item è implementato a meno di flag `[EXISTING]`
**Scope:** roadmap di lavoro futuro su fonti dati, alpha e qualità della pipeline news/event-driven. NON include fix di bug puntuali già tracciati altrove (es. order-submission 422, frontend F0-F3) salvo dove sono prerequisiti di un alpha vector.

---

## 0. Tesi strategica

Alembic è oggi una **monocultura editorial-news**: 100% delle fonti produttive (GDELT GKG, MarketAux, Alpaca/Benzinga) sono articoli editoriali aggregati. Questa è la classe di dati con **meno alpha** per tre ragioni strutturali (non accidentali):

1. **Stale per definizione** — qualcuno scrive l'articolo dopo l'evento. Latenza misurata p50 69-182h (marketaux 7.6g, gdelt 7g, alpaca 2.9g). Il bucket 0-6h è il meno negativo (-0.63/trade) perché è l'unico che occasionalmente arriva "in tempo".
2. **Ipercompetuta** — ogni quant legge la stessa Benzinga/Reuters. Edge competito via verso zero.
3. **NER-dipendente** — ticker estratto da prosa → false positive (META ambiguo, cashtag mal parsato). Rischio worst-case (ordine su ticker sbagliato).

**Risultato empirico (17g, DB): -$525.74 su 177 trade, hit-rate 29%, MarketAux 0/20 winner, 39-48% signal near-zero (token LLM sprecati).**

**Pivot proposto:** smettere di porsi come "news-sentiment engine" e diventare un **event-driven LLM interpretation engine**, dove gli eventi sono documenti **primari semi-strutturati** (filings, earnings, transcript, stime, disclosure) — non editoriali aggregati. Qui: (a) competenza bassa (parsing difficile, pochi lo fanno), (b) ticker noto a priori (CIK→ticker, no NER), (c) timestamp pulito (event-time, non "pubblicato 7g dopo"), (d) LLM interpreta testo semi-strutturato meglio di un fattore numerico.

**L'alpha "hidden" non è una fonte news alternativa — è una classe di dati diversa.**

---

## 1. Roadmap per fasi

| fase | tema | orizzonte | gate di uscita |
|---|---|---|---|
| **P0** | Stop the bleeding (fonti editoriali + cecità metriche) | 1-2 sett | metriche per-fonte visibili; fonti net-negative rimosse/disabilitate |
| **P1** | Enabler trasversali (label set, dedup, freshness, metrica) | 2-4 sett | QX-01 label set operativo; freshness su `published_at`; content-hash dedup wired |
| **P2** | Pivot a event-driven (Vettori A/B/D) | 4-8 sett | S7 backtest positivo OOB; filings multi-evento; revisions wired |
| **P3** | Hidden alpha esplorativo (Vettori E/C/G) | solo se P2 sano | sleeve congressional; filtro options; macro extra |
| **REJECT** | Fonti editoriali premium / social sentiment | — | mai come alpha primario |

Ogni item: `ID`, `tipo`, `priorità`, `dipende-da`, `gap concreto`, `fonte/API`, `gate di validazione`, `rischio`.

---

## 2. FASE P0 — Stop the bleeding (fonti editoriali attuali)

Obiettivo: fermare la distruzione di capitale e rendere il sistema non-cieco sulla qualità delle fonti, prima di toccare qualunque alpha nuovo.

| ID | intervento | priorità | gap / evidenza | gate |
|---|---|---|---|---|
| **FIX-01** | Disabilitare MarketAux dal beat | P0 | 0/20 winner, -$14.11/trade, -$282 totale; latenza 7.6g; rate cap 100/giorno → ~4 news/giorno basse | n/a (rimozione, zero rischio di perdere edge) |
| **FIX-02** | Disabilitare RSS attuale (Reuters/CNBC) | P0 | 0 news_log in 17g → feed morti o no ticker match; mancante da README beat table | n/a; rianimare solo con feed IR ufficiali (P3) |
| **FIX-03** | Filtro freshness su `published_at` (NON `generated_at`) | P0 | filtro attuale su signal-age non cattura news stale; bucket 0-6h meno negativo suggerisce latenza = metà del danno | dopo filtro, P&L rolling per-fonte ≥0 su window pulita |
| **FIX-04** | P&L + latency per-fonte esposti (DB + frontend) | P1 | oggi il sistema è cieco: niente metriche per-fonte nel DB/frontend; news_log non registra scarti | dashboard Source Quality con funnel news→signal→decision→trade→P&L |
| **FIX-05** | Trace news→signal→decision→order→performance per fonte | P1 | join via news_log_id al 72%, va completato (backfill) ed esposto nel drawer trace frontend | trace end-to-end ricostruibile per ogni trade |
| **FIX-06** | Skip news senza asset_tags (confermato già fatto QT-01) + log `discarded_reason` | P1 | QT-01 fallback-watchlist fix già applicato (marketaux.py:218, alpaca_news.py:181); manca il logging del discard per misurare | `discarded_reason` enum in news_log |
| **FIX-07** | Riconciliare doc vs codice (SEC EDGAR, latenza GDELT, RSS beat table, Finnhub/GDELT DOC) | P2 | SEC EDGAR documentato attivo ma OFF+bug; latenza GDELT "1-6h" nei doc vs 7g empirici; RSS omessa da README beat table | doc riflette lo stato reale |

> Nota: FIX-06 corregge il finding W2/A1 della review ticker del 2026-06-30 — il fallback `asset_tags = list(self._symbols)` **è già stato rimosso** nel codice (QT-01 applicato). La correzione va registrata nei doc.

---

## 3. FASE P1 — Enabler trasversali (prerequisiti di ogni alpha nuovo)

Nessun alpha vector (P2/P3) va promosso senza questi. Sono il "measurement before enforcement" del CLAUDE.md.

| ID | intervento | priorità | gap concreto | gate |
|---|---|---|---|---|
| **EN-01** | QX-01 ground-truth label set operativo (spec in `TICKER_SENTIMENT_QUALITY_REVIEW_2026-06-30.md` §5) | P0 (prerequisito) | misura precision/recall extraction + calibration sentiment + IC end-to-end; oggi nessuna golden label | news_labels table popolata; κ annotatori ≥0.6; holdout 60/40 blind |
| **EN-02** | Estendere label set **per fonte** (200 news/fonte) | P0 | la qualità varia per fonte (NER vs metadata); serve segmentare il golden set per fonte | precision ticker per-fonte misurata |
| **EN-03** | Content-hash dedup pre-inference (wired) | P1 | `Deduplicator.is_duplicate` definito ma MAI chiamato (README:679 TODO); stesso articolo 3 fonti = 3 LLM call | 1 LLM call per articolo cross-source; token spesi ↓ |
| **EN-04** | Source priority + dedup cross-source | P1 | ordinare fonti per freshness/tagging/body, prima vince altre droppate via content-hash | priorità implicita ad Alpaca (metadata + body completo) |
| **EN-05** | Campi DB per metrica: `news_log.raw_ingested_at`, `discarded_reason`, `content_hash`; `sentiment_signals.published_at` (propagato) | P1 | misurare scarti + latency reale (`fetched_at − published_at`) | metriche latency reali per-fonte |
| **EN-06** | `ingestion_stats_daily` (o aggregazione log worker) per fonte: fetched/queued/duplicates/discarded_no_ticker/discarded_stale/parse_fail | P1 | log worker parziale, non persistito/aggregato | funnel per-fonte osservabile |
| **EN-07** | Alerting: P&L rolling per-fonte <0 per N giorni; latency p50 >6h; near-zero >40% | P2 | oggi nessun alert su degrado fonte | alert attivi su soglie |

---

## 4. FASE P2 — Pivot a event-driven (i vettori di alpha)

### Vettore A — Catena eventi earnings (SBLOCCA S7)

**Tesi:** PEAD è uno degli effetti più documentati (+3-5% su 20d post positive surprise). S7 è **già completa** (`pead_worker.py`, `s7/signal.py`) ma produce zero per assenza di dati: il consensus lo fa estrarre all'LLM dal testo del 8-K dove **non c'è**; il connector EDGAR ha il bug ticker → 0 input. Strategia costruita, carburante zero.

**LLM edge reale:** classificare direzione surprise + tone guidance dal linguaggio del transcript/Q&A è un compito NLP genuino che un fattore numerico non fa ("management ha detto 'headwinds'/'transitory' 14 volte in Q&A").

| ID | intervento | priorità | dipende | gap concreto | fonte/API | gate |
|---|---|---|---|---|---|---|
| **ALPHA-A1** | Wire earnings calendar (trigger ingestion + protezione S1) | P1 | — | `s1/earnings_calendar.py` previsto (roadmap linea 409) **non esiste** → S1 scoperto sugli earnings | Yahoo `earnings_dates` (free), Finnhub calendar, FMP `/earnings-calendar` | calendar wired; S1 riduce posizione pre-earnings |
| **ALPHA-A2** | Wire consensus EPS/revenue esterno | P1 | ALPHA-A1 | `pead_worker` estrae consensus dal 8-K (inesistente) → surprise_pct null → soglia 0.05 mai superata. Roadmap linea 227 "consensus Yahoo" NON implementato | FMP `/analyst-estimates`, Finnhub `/earnings`, Alpha Vantage `EARNINGS`, Zacks | surprise calcolato da consensus esterno, non LLM-extracted |
| **ALPHA-A3** | Wire transcripts (alpha qualitativo) | P2 | A2 | zero handling transcript; è dove LLM tone-analysis brilla | FMP `/earning_call_transcript`, Polygon transcripts | tone signal estratto da transcript, validato su label set |
| **ALPHA-A4** | Guidance direction (revised-up/down/maintained) cross-check 8-K item 7.01 + transcript | P2 | A3 | oggi LLM su 8-K solo | 8-K + transcript | guidance signal concorde con surprise direction ≥80% |
| **ALPHA-A5** | POC backtest S7 (gate go/no-go) | P1 | A2 | S7 mai validato con dati reali | backtest 1 anno FMP | **drift netto ≥1.5% a 20d, hit-rate >55%, test esplicito large vs small cap** (se large-cap drift ≈0 → alpha esiste in universo diverso: decisione espandi universo o abbandona S7) → RI-ESEGUITO 2026-07-03 con FMP (vedi reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md; supersede il run Finnhub INCONCLUSIVE) — **FAIL**: drift +1.96% (sopra soglia) ma hit-rate 51% (sotto soglia 55%), n=76 BEAT; 0 eventi small/mid-cap nel campione → confronto large-vs-small-cap non testato. **Analisi distribuzione 2026-07-03 (addendum nel report): il drift è interamente beta SPY (excess +0.05%, mediana −1.07%) + 5 outlier (media senza top-5 negativa), nessuna dose-response → S7 SHELVED (audit in strategy_lifecycle). Riapertura solo via decisione PO: universo small/mid oppure POC transcript-tone ALPHA-A3 (transcript FMP = premium, gated su vendor).** |

**Rischio concreto:** la watchlist 115-symbol è large-cap → PEAD può essere già competuto. POC-A5 deve includere subset small/mid-cap. Se su large-cap il drift è ~0, l'alpha di S7 va cercato in un universo diverso, non nel disegno della strategia.

### Vettore B — Filings primari (oltre l'editorial, oltre il solo 8-K earnings)

**Tesi:** disclosure SEC sono filing minuti dopo l'evento, ticker certo (CIK→ticker), prima dell'aggregazione editoriale. Alembic ha già il connector EDGAR ma lo usa solo per 8-K earnings e con bug. Espandere a tutti i material 8-K + Form 4 + 13F + FTD.

| ID | intervento | priorità | dipende | gap concreto | fonte/API | gate |
|---|---|---|---|---|---|---|
| **ALPHA-B0** | Fix SEC EDGAR ticker bug (CIK→ticker via `company_tickers.json`) | P0 | — | `sec_edgar.py:93` legge `ticker_symbol` che EDGAR non ritorna → 0 ticker → tutto scartato; documentato attivo ma OFF | SEC EDGAR free | ticker estratto correttamente; riconciliare doc (FIX-07) |
| **ALPHA-B1** | 8-K multi-evento (M&A, CEO change, going-concern, dividend, bankruptcy, material agreement) | P2 | B0 | oggi solo item 2.02 earnings; altri 8-K material events ignorati | SEC EDGAR full-text 8-K | evento classificato da LLM; P&L per tipo-evento |
| **ALPHA-B2** | Form 4 insider transactions | P2 | B0 | edge documentato, **bassissima competenza algoritmica**; zero handling | SEC EDGAR Form 4 RSS (free) | POC open-market purchases (filtro option/10b5-1), hold 60d, excess return >0, n≥100 |
| **ALPHA-B3** | 13F institutional ownership changes | P3 | B0 | whale tracking, slow (45g lag) ma uncrowded; zero handling | SEC EDGAR 13F (free) | POC excess return vs settore a 90d |
| **ALPHA-B4** | FTD (failures-to-deliver) squeeze signal | P3 | B0 | contrarian/crowding; zero handling | SEC FTD bi-settimanale (free) | POC signal di squeeze su crowded short |

**Rischio:** Form 4 rumoroso (exercise, 10b5-1 non informativi) → filtro rigoroso solo open-market purchases. Rischio operativo basso (gratis, strutturato).

### Vettore D — Revisions / rating changes (alimenta il drift di S7)

**Tesi:** le revisioni di stime EPS sono il **meccanismo** del post-earnings drift (analysts aggiornano lentamente → drift). Sinergico con A ma segnale separato (revisione senza earnings).

| ID | intervento | priorità | dipende | gap concreto | fonte/API | gate |
|---|---|---|---|---|---|---|
| **ALPHA-D1** | Wire analyst revisions + rating changes | P2 | A2 | zero handling; alimenta il drift di S7 | FMP `/grade`+`/price-target`, Tipranks, Zacks, Alpha Vantage `ANALYST_RATING` | POC "buy after upward revision, hold 20d", hit-rate >55% netto |
| **ALPHA-D2** | LLM interpretation della nota analyst (se disponibile) | P3 | D1 | distingue "revisione per evento aziendale" (persiste) vs "revisione per modello macro" (non persiste) | testo nota analyst | concordanza revision+tone su label set |

**Costo POC incluso in FMP one-stop** (Vettore A) o Tipranks separato.

---

## 5. FASE P3 — Hidden alpha esplorativo (solo se P2 sano)

Esplorato solo dopo che P0-P2 mostrano un sistema base sano. Nessun item qui è prerequisito.

### Vettore E — Eventi low-attention

| ID | intervento | priorità | gap/tesi | fonte | gate / rischio |
|---|---|---|---|---|---|
| **ALPHA-E1** | Congressional trading sleeve (satellite micro) | P3 | documentato, **bassissima competenza algoritmica**; lag 30-45g → incompatibile con orizzonte tactical S4 → sleeve lento separato (S9?) | Capitol Trades, Quiver Quant (free-ish scraping) | POC excess return a 60/90d; **rischio**: lag lungo, confondere fortuna con abuso info; sleeve ≤1-2% portafoglio |
| **ALPHA-E2** | FDA/biotech catalysts | P3 | evento biotech netto, LLM parsia trial outcomes; **incompatibile con watchlist large-cap attuale** → richiede universo separato | BioPharmCatalyst (~$50/mo) | solo se Alembic espande a sleeve biotech; rischio liquidità |
| **ALPHA-E3** | Short interest / borrow fee / squeeze | P3 | contrarian crowded-short | Finra short bi-settimanale, ORTEX/S3 | POC signal di squeeze; lag bi-settimanale |

### Vettore C — Options flow (filtro, NON primario)

| ID | intervento | priorità | tesi/onestà | fonte | gate |
|---|---|---|---|---|---|
| **ALPHA-C1** | Options flow come **filtro di conferma** | P3 | **più numerico che testuale → LLM edge debole**; ipercompetuto; solo come filtro ("non fare PEAD long se unusual put buying opposto al beat") | Unusual Whales, FlowAlgo, ThetaData, Polygon options | valore aggiunto *incrementale* sopra A/B/D, altrimenti scarta |

### Vettore G — Macro/cross-asset (regime per S2/S3/S5/S6, NON alpha S4)

| ID | intervento | priorità | tesi | fonte | gate |
|---|---|---|---|---|---|
| **ALPHA-G1** | CFTC Commitment of Traders | P3 | positioning contrarian | CFTC free (settimanale) | regime/contrarian per S2/S3 |
| **ALPHA-G2** | Credit spreads via FRED | P3 | leading equity risk | FRED series (free) | regime detector espanso |
| **ALPHA-G3** | CBOE put/call ratios | P3 | sentiment flow | CBOE free | regime/filtro |

> Vettore G **non è alpha S4/news** — alimenta le altre strategie del roadmap. Incluso per completezza.

---

## 6. REJECT — Cosa NON fare (esplicito)

| item | perché rifiutato | evidenza |
|---|---|---|
| **Vettore F — Social/retail sentiment (Reddit, StockTwits, X)** | il "alt data" **più competuto di tutti** (bot, hedge fund social-sentiment, meme quant); signal-to-noise basso; rilevante solo come detector di evento di liquidità estremo (meme squeeze) per *evitare* nomi o fare fade, non come sentiment direzionale | non è "hidden" — è rumore competuto |
| **Fonti editoriali premium** (Polygon news, Benzinga direct, Intrinio, Tiingo, NewsAPI paid) prima del pivot | aggiungere fonti editoriali premium a un sistema che perde -$525 sui dati editoriali **peggiora il problema**, non lo risolve | -$525 su 177 editorial trade; latenza 7g intrinseca alla classe |
| **Promuovere Finnhub a live** senza POC | shelved 2026-07-01; query-per-symbol (costo scaling watchlist); non validato | n/a |
| **Promuovere GDELT DOC 2.0 a live** senza POC | shelved; headline-only; rate limit severo; non validato | n/a |
| **Qualunque alpha vector a paper/live** senza backtest OOB positivo + label set QX-01 | alpha non validato = ipotesi, non verità | CLAUDE.md "measurement before enforcement" |

---

## 7. Gate di validazione trasversali (validi per ogni item P2/P3)

1. **Backtest out-of-sample netto post-costi positivo** su holdout non usato per tuning.
2. **Label set QX-01** misura precision extraction/sentiment per la nuova fonte ≥ soglia.
3. **Metrica per-fonte** visibile (funnel + P&L + latency + near-zero) prima della promozione.
4. **Soglie decisionali promuovi/rimuovi**:
   - rimuovi fonte se hit-rate <40% E P&L rolling 30g <0; oppure latency p50 >24h; oppure near-zero >50%.
   - promuovi POC a secondary se precision ticker (label set) ≥85% E overlap con primaria <60% E freshness p50 <6h.
5. **Niente in hot path**: ogni nuovo vettore è ingestion offline → LLM worker → Redis/PG signal → execution legge. (Vincolo non-negotiable CLAUDE.md.)

---

## 8. Sequenza operativa consigliata

```
P0 (1-2 sett)               P1 (2-4 sett)              P2 (4-8 sett)              P3 (solo se P2 sano)
──────────────              ──────────────             ──────────────             ──────────────────
FIX-01 disable marketaux   EN-01 QX-01 label set      ALPHA-A1 earnings calendar ALPHA-E1 congressional sleeve
FIX-02 disable RSS          EN-02 label set per fonte ALPHA-A2 consensus esterno ALPHA-E2 FDA (se sleeve biotech)
FIX-03 freshness published  EN-03 content-hash dedup  ALPHA-A5 POC S7 (GATE)     ALPHA-E3 short interest
FIX-04 P&L per-fonte        EN-04 source priority    ALPHA-B0 fix EDGAR bug     ALPHA-C1 options come filtro
FIX-05 trace per-fonte      EN-05 campi DB metrica   ALPHA-B1 8-K multi-evento ALPHA-G1-G3 macro extra
FIX-06 log discarded        EN-06 ingestion_stats    ALPHA-B2 Form 4 insider
FIX-07 riconcilia doc       EN-07 alerting           ALPHA-D1 revisions
                                                      ALPHA-A3 transcripts
                                                      ALPHA-A4 guidance cross-check
                                                      ALPHA-D2 LLM note analyst
                            │
                            └─ GATE ALPHA-A5: drift ≥1.5%, hit >55%, large vs small cap
                               ├─ PASS → S7 paper (sotto label set + metrica per-fonte)
                               └─ FAIL large-cap → valuta universo small/mid-cap OR abbandona S7
```

**La mossa strategica:** Vettori A+B+D insieme trasformano Alembic da "news-sentiment su editorial stale" (perde -$525) a "event-driven earnings/filings engine" dove i dati sono primari e freschi, il ticker è certo, l'LLM interpreta testo semi-strutturato che i fattori non sanno leggere, e S7 già costruita finalmente ha carburante. È sia la tesi di alpha **sia** la cura della malattia (latenza 7g, NER false-positive) diagnosticata in precedenza.

---

## 9. Stop point / decisioni aperte per l'utente

1. **Universo di trading**: la watchlist 115-symbol large-cap può essere inadatta a PEAD (edge competuto). Decisione: espandere a small/mid-cap per S7, o mantenere large-cap e accettare che S7 possa non funzionare? → determina se ALPHA-A5 passa il gate.
2. **One-stop provider**: FMP copre calendar+estimates+transcripts+ratings+insider+13F in una sola API. Decisione: adottare FMP come fonte dati event-driven unica, o preferire multi-vendor (Yahoo free + Finnhub + Tipranks)? Trade-off: un vendor vs resilienza/fonte-multipla.
3. **Sleeve biotech (ALPHA-E2)**: richiede universo separato → decisione strategica su espandere Alembic oltre large-cap US.
4. **Label set budget (QX-01)**: annotazione umana blind 2-annotatore costa tempo. Decisione: in-house vs esternalizzare? Determina la velocità di tutto il P1.

Nessun item di P2/P3 va implementato prima che P0+P1 siano completati e il gate ALPHA-A5 sia valutato.