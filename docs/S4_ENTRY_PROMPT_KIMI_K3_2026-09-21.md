# S4 — stock entry phase: analysis prompt for Kimi K3

**Date:** 2026-09-21 · **Recipient:** Kimi K3 (external analysis, one long pass)
· **Same method, earlier instances:** `docs/S4_PROMPT_ANALISI_ESTERNA_2026-08-03.md`,
`docs/S4_DECISIONE_ORIZZONTE_PROMPT_ESTERNO_2026-08-13.md`

> **Output language: Italian.** The prompt is in English because most of the attached
> research artifacts are; the deliverable goes into an Italian-language repository, so
> **write your answer in Italian**. Keep verbatim and untranslated: file paths, code
> identifiers, config keys, SQL column names, dossier field names
> (`quota_movimento_precedente_al_segnale`, `candidati_miss`, `funnel_v2`, `score_firmato`,
> `max_score_own`, `max_score_fanout`, …), decision codes (`SKIP_PYRAMIDING`,
> `NO_TRADE_*`, `ANTICIPATORY`, …), finding IDs (`F-0xx`) and hypothesis IDs (`H0x`).
> Tables and headings in Italian; identifiers as they are in the code.

---

## 0. Read this before anything else

Your job is **not** to confirm the system described below, and **not** to produce a list of
ideas. It is to design, from the available evidence, **the most robust possible entry
structure for the S4 sleeve**, stating for every component what evidence it rests on and
what would falsify it.

Non-negotiable rules of engagement:

1. **Do not answer by agreeing.** If the question is badly posed, reframe it and say so. If
   the evidence does not support a choice, the correct answer is "not decidable with this
   data, here is what would be needed" — that is a legitimate outcome and preferable to a
   forced choice.
2. **Do not invent numbers.** Every figure you write must come from a cited artifact (file,
   dossier field, JSONL row) or be explicitly marked as a *conjectural order of magnitude*.
   A declared estimate is fine; an estimate dressed as a measurement is not.
3. **Keep three registers separate** and never mix them inside one sentence: (a) **measured**
   on our data, (b) **supported in the literature** (claims with `review.verdict ==
   "SUPPORTED"`), (c) **conjectural**. If a sentence mixes registers, split it.
4. **Distinguish discovery from confirmatory.** The window 2026-08-03 → 2026-09-04 has
   already been inspected exhaustively (34 Alpha Miss reports + a funnel audit): any new cut
   on that window is **discovery**, not a result. Say so every time you do it.
5. **Long-only.** There is no short leg. A bearish signal can only close or reduce an
   existing position, never open one. Proposals requiring shorting are out of mandate (you
   may note them separately, not as part of the structure).
6. **The literature does not authorise a change.** The web material is research with
   traceable evidence: it exists to formulate an explicit hypothesis, which must then be
   validated separately. Do not use it as direct justification for a parameter change.

---

## 1. The question, in one line

**How should the S4 entry phase be structured** — which stages, in what precedence order,
with what decision units and what admissibility conditions — so the sleeve buys *informative
events* instead of *price coverage of a move that already happened*?

Secondary question, to be answered only after the first: **which additional measurements on
data we already hold** are worth pre-registering in order to choose between the variants you
propose (see §7 D4, capped at 5 proposals, with power and multiplicity constraints).

This is not a question about fine-tuning one threshold. It is a question of architecture: the
internal evidence already says that moving the gate alone does not recover the problem.

---

## 2. The system, in brief

**Alembic** is a US-equities ATS on the *Alpha Miner* paradigm: LLMs are never in the
execution path. They run offline, produce sentiment signals written to PostgreSQL/Redis, and
the execution engine reads pre-computed signals.

- Execution: **Alpaca**, **paper trading**, ~$110,000 NAV
- Universe: fixed watchlist of **96 US large-cap symbols**
- Portfolio cycle: every **15 minutes**, RTH only (~14:00–21:00 UTC), 24 cycles/day
- **Long-only**, no shorting
- Active sleeves: **S1** (cross-sectional momentum, 50% of capital) and **S4** (news-driven, 10%)
- S4 is `promotion_blocked`: no gate report exists and `IC > placebo` has never been confirmed

### 2.1 The S4 entry chain as it stands today, stage by stage

```
source → article → sanitisation → event → ticker → LLM scoring → admissibility
       → order gate → cross-sectional ranking → sizing → guards → order → fill
```

| Stage | Rule in production today | Where it lives |
|---|---|---|
| Sources | Benzinga via Alpaca (REST + WebSocket), GDELT GKG, minor others | `src/connectors/` |
| Max article age | `MAX_NEWS_AGE_HOURS = 2` | `src/config.py:316` |
| Dedup | TTL `4h` on key `(hash, asset_tags[0])` — **twice** `MAX_NEWS_AGE_HOURS`; known defect, correction already pre-registered | `src/connectors/deduplicator.py:22` |
| Ticker | deterministic resolver, separate from the LLM; cashtag required for ambiguous tickers; `NO_TRADE_*` when evidence is weak | `src/connectors/ticker_resolver*.py` |
| Scoring | 2-model ensemble via Ollama Cloud + local FinBERT as fallback; DK-CoT prompt, structured JSON output | `src/workers/sentiment.py` |
| Signal formula | `score = polarity × confidence`, `polarity ∈ [-1,+1]`, `confidence ∈ [0,1]` | idem |
| Ranker prefilters | `min_confidence = 0.30`; `min_score = 0.10`; drops `score ≤ 0` (long-only); **one signal per symbol, the most recent** | `src/strategies/s4/config.py`, `ranking.py` |
| Freshness | `max_signal_age_hours = 4`; `signals_lookback_hours = 96` | `src/strategies/s4/config.py` |
| **Order gate** | `feedback:entry_threshold` in Redis, **baseline 0.30**, ceiling 0.60, 24h decay; the upward ratchet is **frozen** (`threshold_ratchet_enabled: false`) | `src/workers/portfolio_scheduler.py` |
| Ranking | sort descending by `effective_strength = score`, take the first **`n_top = 5`** | `src/strategies/s4/ranking.py` |
| Sizing | fixed weight `1/n_top` per selected name (**2% of NAV per slot**); unused slots stay undeployed | `s4_fixed_slot_sizing_enabled: true` |
| Cycle-exit guards | `SKIP_THRESHOLD` (this *is* the gate), `SKIP_PYRAMIDING` (anti-pyramiding on names already held), `SKIP_IDEMPOTENCY`, `SKIP_FALLBACK`, `SKIP_STALE` | `portfolio_scheduler.py` |
| Anti-churn | `hold_minimum_minutes = 90`; `exit_persistence_cycles = 2` | `config/trading.yaml` |
| Risk | **protective stop disabled** (`stop_loss: 0.0`, explicit decision 2026-07-15); `max_position_pct 0.10`; `max_portfolio_exposure 0.50`; vol target 0.12; `regime_mult` scales order notional | `config/trading.yaml` |

### 2.2 What exists in the code that **no signal path reads**

These two points are central: the information is computed, it is just not wired to the decision.

- `src/analysis/dossier/article_coverage.py` classifies every article as
  **`ANTICIPATORY` / `CONCURRENT` / `RETROSPECTIVE`** and flags content-mill templates as
  `CONTENT_EMPTY`. It lives **only** in the dossier layer (ex-post diagnostics). Every
  retrospective article still becomes a tradable signal.
- `src/workers/sentiment_shadow.py` consumes the **off-session** queue but writes to a shadow
  table no consumer reads.

---

## 3. Material to read, and how to use it

### 3.1 Web research (local nodes, protocol v4)

- **Readable synthesis, start here:** `docs/research/2026-08-28-s4-deep-web-validation.md`
- **Consolidated, reviewed claims, row by row:**
  `docs/research/s4-web-validation-2026-08-28/node-output/consolidated_claims.jsonl`
  (**292 records**; fields: `claim`, `evidence_quote`, `hypotheses`, `limitations`, `stance`,
  `transferability`, `review`, plus source and chunk hashes)
- **Frozen hypothesis registry H01–H22:** `docs/research/s4-web-validation-2026-08-28/HYPOTHESES.md`
- **Node contract and stop rules:** `docs/research/s4-web-validation-2026-08-28/NODE_CONTRACT.md`
- Raw node-1 extractions: `node-output/node1_cards.jsonl` · adversarial node-2 reviews:
  `node-output/node2_reviews.jsonl` · execution/retry/recovery ledger: `node-output/run_ledger.jsonl`
- **Quality audit of the two nodes:** `docs/research/2026-09-15-s4-node-model-quality-audit.md`

**Binding rules of use:**

- For the evidence matrix, consider **only** records with `review.verdict == "SUPPORTED"`
  (**213 of 292**). `OVERSTATED` (54), `AMBIGUOUS` (21) and `NOT_APPLICABLE` (4) are control
  material: you may cite them to explain *why* a thesis fails, never as a result.
- `stance` gives the direction relative to the hypothesis: `SUPPORTS` (158), `QUALIFIES` (65),
  `METHOD_ONLY` (67), `CONTRADICTS` (2). A `METHOD_ONLY` is not evidence about the effect: it
  is evidence about **how to measure**. Use it for measurement design, not for direction.
- **H16 and H17 are `INSUFFICIENT` (zero supported claims).** Treat them as uncovered by the
  collected literature: exclusive first-loss cause in the funnel (H16) and the nature of the
  negative leg (H17). If your structure depends on either, declare it as an uncovered
  assumption.
- The campaign `source-recovery-persistent-2026-09-03` is **invalidated**: exclude it.
  `ACA009` is unavailable (HTTP 403); `ACA010` is a separately identified manuscript, not a
  silent replacement.
- From the quality audit: node 1 (`qwen3.8-27b-implementer`) produces useful volume but
  overstates or mis-cites often enough that it is not a final arbiter (the deterministic gate
  promoted **77.3%** of proposed claims, 402 of 520); node 2 demonstrably catches many of
  those defects. **There is no labelled gold set**: the pipeline is validated mechanically,
  not semantically. Do not read a `SUPPORTED` as truth — read it as "quote verified and not
  overstated".

### 3.2 Internal evidence on entry (our own data)

- **Entry funnel audit:** `docs/research/s4-entry-audit-2026-09-07/ENTRY_FUNNEL_AUDIT.md` and
  `ENTRY_FUNNEL_FINDINGS_2026-09-08.md` (plus `NO_NEWS_SOURCE_AUDIT_2026-09-08.md`,
  `ALPHA_MISS_ENRICHMENT_AUDIT.md`, `FORWARD_PROTOCOL_COMPATIBILITY_AUDIT_2026-09-08.md`)
- **Event study around the news timestamp:** `docs/research/2026-09-16-s4-event-study-latenza.md`
- **Pre-market gap executability:** `docs/research/2026-09-16-premarket-eseguibilita-gap.md`
  and `docs/evidence/premarket_feasibility_608.json`
- **Late-entry joint distribution:** `docs/evidence/LATE_ENTRY_JOINT_DISTRIBUTION_2026-09-08.md`
- **34 daily Alpha Miss reports:** `docs/ALPHA_MISS_REPORT_2026-07-24.md` → `2026-09-17.md`
- **Longitudinal findings:** `docs/evidence/findings.json` (**86 findings**, dated occurrences
  with `costo_usd`) plus `docs/WEEKLY_FINDINGS_2026-*.md`
- **Frozen point-in-time dossiers:** `docs/evidence/dossier/*.json` (31 sessions,
  2026-08-03 → 2026-09-17, `schema_version` 2.0 → 3.1)
- **Economic P&L:** `docs/evidence/economic_pnl.json` · **S4 IC:** `docs/evidence/s4_ic.json`,
  `s4_ic_2x2.json`

**Precedence on conflict:** the **number** comes from the frozen dossier; the **causal
classification** comes from the most recent weekly review. An issue describes a mechanism; it
does not replace verification against the data. Dossier schemas move from 2.0 to 3.1: a
metric may be aggregated **only** over the window where its definition is compatible.

---

## 4. What we already know — the constraint you start from

Every figure below is measured on our data. Where it is not pre-registered, I say so.

### 4.1 Latency consumes the useful window (exploratory)

- Publication → scoring latency: median **46.0 min**, p90 **92.8 min**. Decomposed:
  publication → first-seen **10.9 min**, first-seen → ingestion **30.7 min**.
- At scoring time, the median **share of the intraday move already elapsed** is **88.8%**;
  2,180 of 3,622 observations (60.2%) are at 75% or more.
- Over the remaining leg to the close: median return **−0.009%**, mean +0.023%, median MFE
  +0.462%, median MAE −0.504%.

### 4.2 The intraday event study: the news does **not** move the price (exploratory)

749 in-hours Benzinga news items, `|score| ≥ 0.10`, 25 sessions, 76 symbols, SIP minute bars.

| T−60 | T−15 | T−1 | T+1 | T+15 | T+60 |
|---|---|---|---|---|---|
| −0.013% | +0.000% | −0.004% | +0.000% | +0.022% | +0.010% |

Flat curve, every CI contains zero. The control that separates "real event" from "timestamp
misalignment" is **minute-level volatility**, which on a real event runs 2–5×:

| T−10 | T−1 | T+0 | T+1 | T+5 | T+30 |
|---|---|---|---|---|---|
| 0.84× | 0.92× | **0.89×** | 0.89× | 0.78× | 0.75× |

**No spike, and the ratio is below 1 everywhere**: the reference window is more agitated than
the event itself. On `|score| ≥ 0.5` only (n=35) it is 0.58× at T+0. At `published_at`, a
median **61.3%** of the [−60,+60] move has already happened; by the time we score, **82.9%**.
Our median lag on that subset is 21.7 min.

**Reading:** two thirds of the delay belongs to the source, one third is ours. The intraday
Benzinga stream is largely **price coverage** — the article follows the move. A faster source
carrying the *same* content does not help: you cannot front-run a mirror.

### 4.3 The reversal: off-hours news (exploratory, then pre-registered)

Same measurement on news published while the market is closed: 380 events, 330 usable.

| | sign-aligned mean | t |
|---|---|---|
| opening gap, raw | +0.678% | +3.86 |
| gap in excess of SPY | +0.637% | +3.81 |
| **excess gap, clustered by day (49 days)** | **+0.560%** | **+2.35** |
| intraday **after** the open | +0.078% | +0.49 |

Days with a positive mean: 29 of 49. Signals scored **after** the open of the reaction
session: **279 of 330 (85%)**. With day-clustering the `t` falls to 2.35, **below the house
bar of |t| ≥ 3**: a strong candidate, not a result. Confirmatory test pre-registered in
`docs/evidence/PREREGISTRAZIONE_GAP_OFFHOURS_2026-09-16.md` (#606, threshold n expected
around mid-November 2026).

**The real obstacle:** the gap **is not collectible by entering at the open** — by then it has
happened, and what remains is the intraday leg worth +0.078% at t 0.49. The +0.560% proves the
signal is *informative*, not that the return is *available*. Collecting it requires
extended-hours execution, i.e. an execution change (issue #608: advancing scoring alone is
worth **−0.6 bp**, measured — the news is published when the gap has already occurred).

### 4.4 Consequence: the aggregate IC mixes two opposite populations

- **intraday** (~80% of flow): non-events, no reaction, negative IC — dilutive
- **off-hours** (~20%): real events, correct sign, **not harvested**, because 85% is scored
  after the open

Post-hoc decomposition of the 1-day IC:

| cut | segment | obs | IC 1d | t |
|---|---|---:|---|---|
| pub→scoring latency | < 15 min | 289 | **+0.101** | +1.14 |
| | 15–60 min | 1,168 | +0.021 | +0.51 |
| | 1–3 h | 1,973 | −0.028 | −1.13 |
| source | alpaca_benzinga | 2,608 | −0.022 | −1.05 |
| | gdelt_gkg | 1,006 | **−0.099** | −2.65 |
| engine | ensemble | 2,720 | −0.039 | −1.68 |
| | FinBERT fallback | 1,925 | −0.038 | −1.50 |

Three readings, all to be treated as hypotheses: a **latency gradient** (positive sign only
below 15 minutes, and that band is nearly empty — 4–8 distinct days); **GDELT** (28% of
observations carry most of the negative sign, and it holds when segmenting by period); and
**the ensemble does not beat FinBERT** (two cloud models with a DK-CoT prompt tie a local
3-class classifier — that is evidence about the premise of the whole paradigm, not only about S4).

### 4.5 The 0.30 gate separates weakly, and does not persist (exploratory)

- Positive signals with `score ≥ 0.30` and a non-flat intraday outcome (n=257): **54.9%**
  continue in the positive direction to the close; mean return from score price to close
  +0.146%, median +0.058%.
- Positive signals **below** 0.30 (n=1,268): hit rate 48.7%, mean +0.046%, median −0.010%.
- Reduced to one signal per ticker/session using the ranker's own rule: mean cross-sectional
  IC between score and **same-session residual return** is +0.031 over 24 days (descriptive
  t 0.77). On **close-to-close forward returns**: mean IC **−0.065** at 1d (t −2.59),
  **−0.066** at 3d (t −1.96), **−0.070** at 5d (t −1.93), over 23/21/19 days.
  **Not corrected for multiplicity.**

### 4.6 Coverage: half the universe has no usable news

Across 24 dossiers: on average **46.6 of 96 symbols** per session (48.6%) have **no** news row
at all. On the 9 dossiers that also expose `effective_timely` coverage, the mean falls to
**19.8 of 96 (20.6%)** — the presence of a raw row **greatly overstates** genuinely timely,
issuer-specific coverage. Over those same 9 sessions, 13 tickers never receive a raw row and
**38 never receive an `effective_timely` article**.

### 4.7 Taxonomy of missed movers (144 candidates over 24 dossiers)

| Dossier label | N | Share | Cautious reading |
|---|---:|---:|---|
| `NO_NEWS` | 59 | 41.0% | no observable news→signal chain |
| `BELOW_GATE` | 51 | 35.4% | score insufficient per the classifier |
| `NON_CLASSIFICATO` | 17 | 11.8% | causal information lost in the legacy taxonomy |
| `OFF_TOPIC_NON_DECIDIBILE` | 15 | 10.4% | article present, attribution/relevance undecidable |
| others | 2 | 1.4% | transitional taxonomy versions |

**These are not final causal counts:** `BELOW_GATE` hides wrong-sign signals, fan-out,
bearish signals that a long-only sleeve cannot act on, and genuine near-misses.

### 4.8 One typical session, for scale (2026-09-17)

15 movers ≥3%. **1,973 S4 intents** generated → **102 tradable** → **5 submitted**. Of the 97
dropped: **75 `SKIP_PYRAMIDING`** (73.5% of tradable intents; 43 of them on symbols held by
S1/legacy) and 22 `SKIP_IDEMPOTENCY`. Of the 5 entries, 3 enter above the 50th percentile of
the session range (20-day rolling median: 0.569); **1 of 5** closes net profitable. MU enters
with `quota_movimento_precedente_al_segnale = 1.0588` (the move entirely consumed) and marks
−$1.97. 7 of the 15 movers were **already held at the open**: the book was in the theme by
inheritance, not by that day's decision.

Two cases that show this is an **attribution** problem rather than a threshold problem:
- **ORCL +5.19%**: `score_firmato` 0.22 (below the 0.30 gate) — but that 0.22 came from a
  **macro fan-out** piece ("Nasdaq 100 Rallies as Oil Slides"), not from the only
  issuer-specific Oracle article, which scored 0.021 and was **retrospective**.
  `max_score_own = 0.021` versus `max_score_fanout = 0.22`.
- **ARM +8.57%**: the only issuer-specific article is a "…Stocks Moving Higher On Thursday"
  piece — it **reports** the rise, it does not anticipate it. No row explains the move.

### 4.9 Open entry-side findings, with cumulative cost and recurrence

From `docs/evidence/findings.json` (86 findings). Those touching entry:

| ID | days | cum. cost | summary |
|---|---:|---:|---|
| F-001 | 31 | $5,068 | low news coverage: most symbols have no article on the day |
| F-009 | 20 | $2,458 | the 0.30 gate drops **correct-sign** signals on strong movers |
| F-012 | 28 | $938 | half of scored rows come from **multi-ticker fan-out** articles |
| F-030 | 15 | $363 | the news arrives when the move has already happened |
| F-031 | 18 | $324 | the anti-pyramiding guard blocks S4 entries on names already held by S1/legacy |
| F-051 | 4 | $221 | ranking assigns top-N slots to days-old signals on names already held |
| F-023 | 12 | $32 | only the **most recent** signal per symbol is used: a strong signal is overwritten by a weak one |
| F-019 | 14 | $2 | ingestion latency consumes 92% of the entry-freshness window |
| F-008 | 11 | $64 | a generic macro article inverts a ticker-specific signal |
| F-046 | 3 | $31 | the model receives **only the article body**, never the headline |
| F-076 | 3 | $0 | `sanitize_text` does not decode HTML entities: 61.6% of scored rows reach the model corrupted |
| F-066 | 1 | $11 | a content-mill article with a correct ticker and zero informative content passes the gate |
| F-067 | 1 | $0 | unambiguously ticker-specific headlines are never promoted to `ISSUER_SPECIFIC` |
| F-057 | 7 | $0 | the deterministic ticker resolver has **never produced a `RESOLVED` verdict** |
| F-037 | 8 | $0 | ensemble variance is never a gate: `ensemble_std` is read only by the postmortem |
| F-054 | 5 | $0 | the ensemble-divergence guard is bypassed by the eligibility filter |
| F-056 | 2 | $56 | a more recent non-fallback signal is always preferred to a better fallback signal |
| F-043 | 3 | $82 | on some sessions every above-gate signal is bullish and the names fall |
| F-040 | 8 | $58 | above-gate bearish signals with the correct sign never produce any action |
| F-013 | 21 | $87 | no band between entry gate (0.30) and exit (0): intraday churn |
| F-035 | 3 | $14 | a second staleness filter inside S4 cancels FIX-D |
| F-020 | 13 | $68 | ticker resolution: articles about same-named private firms attributed to bank tickers |
| F-032 | 3 | $0 | canonicalisation: providers write `BRKB`, the watchlist says `BRK.B` |

### 4.10 Economic state, for context

`economic_pnl.json` as_of 2026-09-16, day **29/40** of the observation window: S4 cumulative
economic P&L **−$979.55** against a pre-registered band of ±$200 (outside the band, and the
worst value of the window). Book cumulative −$654.00; S1 +$360.38 against an SPY benchmark of
+$441.89 on the same capital base.

---

## 5. House rules that constrain your answer

These are method, not bureaucracy: a proposal that violates them is unusable.

1. **Tuning freeze until 2026-09-28** (`docs/evidence/OBSERVATION_CHARTER.md`): thresholds,
   weights, flags, cooldowns and strategy parameters are frozen. **Only** correctness defects
   are exempt, under this test: *"if I do not fix this, is the evidence I collect over the
   coming weeks wrong?"*. For every proposal you make, **apply that test explicitly** and
   classify it: `DIFETTO_DI_CORRETTEZZA` (deployable now) or `TARATURA` (deployable only at
   expiry, after pre-registration).
2. **Pre-registration:** sample, rule and outcome are fixed **before** seeing the result.
   Picking the best variant out of a grid after the fact is not a result, absent a declared
   multiplicity correction.
3. **Declare the null and the power:** `|t| ≥ 3` is the bar; `INSUFFICIENT_N` **outranks**
   PASS/FAIL by construction; "effect not detectable at this n" is never "effect absent".
   The live S4 criterion is `config/s4_kill_criterion.yaml` — **213 clean sessions** required,
   series valid from **2026-09-08**, `significativo_a_t = 3.0`, `max_ic_rilevabile_a_t = 0.05`.
4. **A measurement must call the production rule, not reimplement it** (#169, #467): reuse the
   tested helper, do not rewrite the ranker's ordering inside the analysis script. This rule
   has already been violated three times.
5. **Changing how you measure is a discontinuity:** it is annotated in the artifact and in the
   charter. A published series is never silently revised.
6. **Measurement before enforcement (QX-01):** resolver enforcement, confidence calibration
   and `risk_flags` gating are all gated on a **golden label set** (`news_labels` table, blind
   `/labeling` UI, `/quality` dashboard).

---

## 6. Weaknesses in the evidence — use them, that is why they are listed

1. The funnel audit window is **24 sessions**, already inspected via the Alpha Miss reports,
   and contains several families of comparisons. Its results **narrow** hypotheses; they do
   not confirm them.
2. `quota_movimento_precedente_al_segnale` uses the **ex-post known close**: it describes
   timing, not a tradable rule. It can be negative or greater than 1.
3. The forward ICs are close-to-close on trading sessions, **not** returns from the intraday
   instant of the signal, and they are corrected neither for multiplicity nor for overlap.
4. The `< 15 min` latency band carrying the only positive IC is **nearly empty** (4–8 distinct
   days): it is the easiest place in all of this to fool yourself.
5. Because of a **documented** misalignment, the reactivation criterion currently evaluates a
   different population and horizon from the pre-registered ones (`TUTTI` at 1 day instead of
   `ensemble-only ∩ |score| ≥ 0.30` at 2 sessions): its verdict must be read as diagnostics,
   not as the criterion.
6. There is no **semantic gold set** for sentiment: signal quality has never been measured
   against representative, blind human labels (this is exactly H15).
7. Dossier schemas move 2.0 → 3.1 inside the window: some metrics are not comparable
   end-to-end, and session 2026-08-28 has no frozen dossier.
8. Alpaca rejects the **entire** request with `subscription does not permit querying recent SIP
   data` when the window touches the recent-data embargo: this had silently removed the **most
   liquid** symbols from the sample (n 380→68, inflating the effect from +0.678% to +0.936%).
   Any measurement you propose must **truncate the data window and fail loudly** on a failed
   fetch, never continue on whatever is left.

---

## 7. What you must deliver

You are free on internal form, but all six blocks must be present, in this order.

### D1 — Reconstructed specification and evidence matrix

Rewrite the current entry phase as an **explicit functional specification** (stages, decision
units, precedence order, what fails open and what fails closed). For each design choice, one
matrix row: *choice · evidence register (measured / supported / conjectural) · cited artifact
· relevant H0x · verdict*. Explicitly flag the choices **no evidence supports** — those are
the real output of this block.

### D2 — The proposed entry architecture

One structure, not a menu. It must answer at least:

- **What is the decision unit**: the article, the information event, the symbol-day, the
  symbol-cycle? (H05 is relevant and has supported claims.)
- **How do you separate a real event from price coverage**, given that `ANTICIPATORY` /
  `CONCURRENT` / `RETROSPECTIVE` and `CONTENT_EMPTY` are already computed but read by no
  signal path. Where does that signal belong in the chain, and does it fail open or closed?
- **How do you treat fan-out**: half of scored rows come from multi-ticker pieces, and on ORCL
  the signal closest to the gate **was not about Oracle**. `max_score_own` and
  `max_score_fanout` already exist in the dossier.
- **How do you treat the off-hours population** (~20% of flow, the only one with the correct
  sign) given that 85% is scored after the open, that the gap is not collectible at the open,
  and that advancing scoring alone is worth a measured −0.6 bp.
- **What does admissibility do** beyond a score threshold: novelty, relevance, directness,
  source quality, event type (H06 and H21 have supported claims); and whether **ensemble
  variance** should become an entry gate instead of postmortem telemetry.
- **What belongs to the gate and what belongs to the ranking**: today the gate is absolute
  (0.30) and the ranking is cross-sectional over survivors. An absolute gate on a
  non-stationary quantity is a choice, not a given: if you change it, argue it.
- **How do you resolve the conflict with the other sleeves**: `SKIP_PYRAMIDING` is the fate of
  73.5% of tradable intents, and 43 of 75 are on names held by S1/legacy. Is that a correct
  guard applied at the wrong level, or is the guard correct and the problem upstream?
- **How do you treat temporal aggregation of signals**: today a strong signal is overwritten
  by the most recent one even when weaker, and top-N slots can go to days-old signals.
- **How do you handle the possibility that the signal does not exist**: given that the ensemble
  does not beat FinBERT and the intraday IC is ≈0-to-negative, it is legitimate to conclude
  that part of the entry structure must be **declining to enter**. If you conclude that, say
  it and quantify the abstention criterion.

For each proposed stage, state **what activates it, what blocks it, and what happens when the
datum is missing** (an entry structure with undefined behaviour on missing data is not a
structure).

### D3 — One card per proposed change

One card per change, at most **8** changes, ordered by evidence-to-cost ratio:

- **Mechanism**: why it should work, in one causal sentence
- **Charter classification**: `DIFETTO_DI_CORRETTEZZA` or `TARATURA` (apply the §5.1 test)
- **Falsifiable hypothesis**, with its H0
- **Where it goes in the code**: file and stage of the chain; if the change belongs to the
  execution layer rather than the signal layer, say so (that is a different order of magnitude
  of work)
- **Expected effect**: sign and order of magnitude, declared as conjecture
- **Cost if wrong**: what gets worse, and how we would see it
- **Interaction**: which of your other proposed changes it collides with or overlaps

### D4 — Additional measurements on existing data (**at most 5**)

Propose **at most 5**, and for each declare:

- question, hypothesis and **H0**; statistical unit; population and window
- **discovery or confirmatory**: anything on the 2026-08-03 → 2026-09-04 window is discovery
  and must be labelled as such
- a declared **multiplicity correction** (how many hypotheses in the family) and **power**:
  what minimum effect is detectable at `|t| ≥ 3` with the available n — if n is insufficient,
  the outcome is `INSUFFICIENT_N` and it belongs in the proposal, not discovered afterwards
- **which production helper** it must call (§5.4)
- **what would falsify it**, in one line

Data and artifacts actually available for these measurements, with no new collection work:

- 31 frozen point-in-time dossiers (2026-08-03 → 2026-09-17) with timeline, price at score,
  MFE/MAE, entry percentile, `funnel_v2` and the `pipeline`/`actionability` axes
- a full snapshot of **3,748 signals** and **11,881 S4 intents** (2026-08-03 → 2026-09-05),
  with outcomes at 1d for 96.7%, 3d for 89.7%, 5d for 84.2%
- the S4 intent ledger (2026-08-25 → 2026-09-05)
- DB tables: `news_log` (with `extraction_method`), `sentiment_signals`, `llm_responses`,
  `execution_decisions`, `trades`, `s4_intent_events`, `news_labels`
- Alpaca SIP minute and daily bars (**subject to the §6.8 embargo**), `market_daily.jsonl`
- `docs/evidence/s4_ic.json`, `s4_ic_2x2.json`, `economic_pnl.json`, `findings.json`
- existing, tested scripts: `scripts/compute_s4_ic.py`, `scripts/measure_169_dedup_rules.py`
  (contains `scelta_produzione()`), `scripts/analyze_s4_entry_audit.py`,
  `scripts/export_s4_entry_funnel_snapshot.py`, `scripts/measure_608_premarket_feasibility.py`,
  `scripts/compute_label_forward_returns.py`, `src/backtest/` (walk-forward + gates)
- **Caution:** `src/backtest/forward_returns.py` and `src/backtest/data/loader.py` use
  **yfinance**, whereas live trading and all published evidence use **Alpaca**. A measurement
  mixing the two price sources is not comparable with the published series: declare which
  source you use.

If you judge that **no** additional measurement on existing data is informative — for instance
because the window is exhausted and only forward time helps — **say so and argue it**. That is
an acceptable answer: H12 holds precisely that backfill is discovery and that an untouched
forward replica is required for promotion.

### D5 — Traps and anti-recommendations

What **not** to do, and specifically: which of the changes that look obvious from the evidence
are in fact noise selection. Concrete precedent to keep in mind: an `INSUFFICIENT_N` verdict
with 0/42 cells at the bar, where the rule that looked best (`issuer_first`) was **noise
selection**, and the real defect was an anti-selective gate elsewhere.

### D6 — Work order

A single final sequence, with declared dependencies between steps and a clean separation
between what is deployable now (correctness defects) and what waits for 2026-09-28. If
anything in your structure requires data we do not have, put it last, state **exactly** which
datum is needed, and do not leave it implicit.

---

## 8. Explicit prohibitions

- Do not propose new paid data sources without declaring that they are paid (the current
  constraint is free-tier: a $30/month News API has already been ruled out).
- Do not propose shorting in any form as part of the structure.
- Do not propose a **synchronous** LLM call in the execution path: that violates the system's
  primary architectural constraint.
- Do not dress a tuning change as a correctness fix in order to bypass the freeze.
- Do not report a number from the exploratory pilot as a result.
- Do not close with a summary of what you have already said: end at D6.
