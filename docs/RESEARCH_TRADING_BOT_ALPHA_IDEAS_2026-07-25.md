# Source-Backed Alpha Sources Alembic Could Realistically Implement

**Date:** 2026-07-25
**Author:** Quant research agent (online investigation, primary-source traced)
**Scope:** Which *documented, source-backed sources of edge* — used by real systematic
strategies, published anomalies, or open quant frameworks — Alembic could realistically
implement given its architecture (offline-LLM Alpha-Miner, daily/portfolio cadence, Alpaca
equities, dormant IBKR, Backtrader with realistic costs).

**Nota:** research note, not a status tracker. The roadmap status lives in GitHub issues
under map issue `#21`. Every claim below is traced to a primary source (peer-reviewed paper,
working paper from a recognized institution, official framework docs, or actual source code)
with a URL in the [Sources](#sources) section. Edge decay, crowding, cost and feasibility are
called out honestly — several ideas are explicitly dropped.

---

## Executive summary (act on these five)

1. **The three best NEW, orthogonal bets are all event/fundamental signals Alembic can build
   on data it already touches, none of which overlap S1 (price momentum) or S4 (news
   sentiment):** (A) **analyst earnings-estimate revisions / SUE**, (B) **"Lazy Prices"
   10-K/10-Q text-change**, (C) **opportunistic insider Form-4 trades**. All three fit the
   offline-LLM + daily cadence perfectly and trade plain equities on Alpaca — no IBKR, no
   options. These are Tier A.
2. **Alembic already has the plumbing to pull the raw material.** `src/connectors/sec_edgar.py`
   already fetches 8-K/10-Q/10-K filings (today it dumps them into the sentiment pipeline as
   generic "news"); `src/connectors/finnhub_news.py` already authenticates to Finnhub (whose
   API also exposes earnings surprises, estimate revisions and insider transactions on
   endpoints Alembic has *not* wired). The gap is **signal extraction**, not data acquisition.
3. **Raw PEAD is dead — do not resurrect S7-style raw drift.** Post-2006 the drift is
   essentially zero for non-microcaps (Martineau, *Rest in Peace PEAD*); Alembic's own S7 raw
   test already FAILed. The *earnings event itself* is still valuable, but only as the trigger
   for the revision/tone signals in (1), not as a standalone drift trade.
4. **"Extend S4 into more NLP alpha" is only worth it via the filing-diff and
   earnings-tone routes — not via more social/Reddit/attention data.** Google-Trends attention
   (Da-Engelberg-Gao) and Reddit/WSB sentiment are crowded, short-horizon, and mostly predict
   *volatility*, not risk-adjusted return after costs. The durable, under-arbitraged NLP edge
   is diffing full filings (Lazy Prices), which almost nobody does at scale.
5. **Every options/vol idea beyond S2 (dispersion, VIX-term-structure carry, put-write) is
   blocked on the same two prerequisites as S2: real options data and IBKR options execution.**
   Alembic today only synthesizes Black-Scholes chains. Treat these as one program gated behind
   "become option-aware," not as separate quick wins. Meanwhile, respect the sober benchmark
   evidence: StockBench (Oct-2025) shows most LLM trading agents *fail to beat equal-weight
   buy-and-hold*, and FinGPT's own stock-movement accuracy is 45–53% — a direct caution for how
   much to expect from S4 alone.

---

## How this report filters alpha from plumbing

Most open-source "trading bots" (EMA/RSI crossover bots, RL bots, auto-optimizing swing bots,
Freqtrade indicator strategies, ib_async bots) carry **no alpha**. They are plumbing — risk
management, sizing, broker integration, dashboards, notifications — which Alembic already has
in abundance (realistic backtest costs, Telegram approval, vol-scaled stops, drawdown
kill-switch, portfolio scheduler). A fitted indicator with a good backtest and no economic
mechanism is **not** an edge; Freqtrade's own docs warn that "taking public strategies and
using backtests to assess performance is often problematic," and the entire genre is a
walk-forward-overfitting trap ([Freqtrade backtesting docs](https://www.freqtrade.io/en/stable/backtesting/);
[freqtrade-strategies repo](https://github.com/freqtrade/freqtrade-strategies)).

So the bar here is: **a documented economic reason returns should be positive after costs,**
plus out-of-sample survival. Anything that is only "fits history" is sent to
[What to ignore](#what-to-ignore-and-why).

A second filter is **crowding decay**: McLean & Pontiff show published cross-sectional
predictors deliver **26% lower returns out-of-sample and 58% lower post-publication**
([JF 2016](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365);
[SSRN 2156623](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623)). Every anomaly
below is discounted for this — the survivors are ones with a structural (attention/inattention,
informed-trader, insurance-premium) mechanism that resists arbitrage, or that require
unusual data effort that keeps the crowd out.

---

## What Alembic already is (so nothing here re-recommends it)

- **S1** — cross-sectional / time-series **price momentum** (skip-month, absolute-filter variants).
- **S2** — **Variance Risk Premium** via short puts on SPY/QQQ (options); coded but disabled,
  blocked on IBKR options execution + OOS gates; backtest currently trades SPY with *synthetic*
  BS chains (see `docs/strategies/s2-vrp-theory.md`).
- **S3** — cross-sectional momentum variant (beta-adjusted).
- **S4** — **news/LLM-sentiment** pipeline: hosted-LLM ensemble + FinBERT → `score = polarity ×
  confidence`, deterministic ticker resolution (SEC `company_tickers`, OpenFIGI). Their main LLM
  alpha bet; ensemble fallback rate is high (models disagree 49–86% of the time).
- (S7 PEAD was removed.)

Self-assessed as "more control infrastructure than alpha." The mandate here is **new,
orthogonal** edge, not refinements of S1.

---

# Tier A — implement (real, orthogonal, feasible on Alpaca equities + offline/daily)

## A1. Analyst earnings-estimate revisions / SUE (revisions momentum)

- **Edge + source.** When sell-side analysts revise EPS estimates, prices under-react and drift
  in the direction of the revision; revisions positively predict subsequent earnings surprises
  and announcement returns. Primary: Jung, Keeley & Ronen, *The Predictability of Analyst
  Forecast Revisions* ([SSRN 2991938](https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2991938_code739506.pdf?abstractid=2991938);
  *J. Accounting, Auditing & Finance* 2019). Foundational: Chan, Jegadeesh & Lakonishok,
  *Momentum Strategies* — earnings/revision momentum is **distinct from and additive to** price
  momentum ([1996 JF, NBER w5375](https://breesefine7110.tulane.edu/wp-content/uploads/sites/16/2015/10/Momentum-2001.pdf)).
  Mechanism: analyst inattention + gradual information diffusion.
- **Still works?** Among the more durable anomalies. McLean-Pontiff and reviews note
  earnings-based signals persisted better than accruals/asset-growth/investment styles. Decayed
  from its 1990s magnitude and partly captured by quant funds, but the *revision-direction*
  signal survives because it rides continuous analyst flow rather than a single publication.
  Discount for crowding; do not expect 1990s Sharpe.
- **Fit with Alembic.** Excellent. Daily cadence, offline computation, pure equity trade on
  Alpaca. **Orthogonal to S1** (fundamentals-driven, not price) and **to S4** (structured
  estimate deltas, not text sentiment). Naturally complements S4's earnings-event awareness.
- **Effort / prereqs.** Needs an estimate-revision + surprise feed. **Finnhub is already
  integrated** (`finnhub_news.py` holds the API key) and its API exposes
  `/stock/recommendation`, EPS-estimate and `/stock/earnings` (surprise) endpoints not yet
  wired — so this is "light up more endpoints of an existing vendor," not a new procurement.
  Build: a revisions/SUE signal worker + a modest coverage/quality check. Validate OOS before
  enabling scoring (their QX-01 discipline).
- **Verdict: Tier A** — highest-conviction orthogonal factor with data on an already-integrated
  vendor. Main risk is estimate-feed coverage/latency on Finnhub's tier; measure before trusting.

## A2. "Lazy Prices" — 10-K/10-Q text-change signal

- **Edge + source.** Cohen, Malloy & Nguyen, *Lazy Prices*
  ([JF 2020](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12885);
  [SSRN 1658471](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1658471);
  [NBER w25084](https://www.nber.org/system/files/working_papers/w25084/w25084.pdf)). Firms
  that **change** the language of their periodic filings year-over-year (especially risk-factor,
  litigation, and CEO/CFO sections) subsequently **underperform**; "non-changers" earn positive
  abnormal returns. A long-non-changers / short-changers portfolio earned up to **188 bps/month**
  (~22%/yr) in-sample. Crucially, **there is no announcement effect** — returns accrue only later,
  proving investors are inattentive to the simple diff. That inattention is the mechanism, and it
  resists arbitrage because computing it requires diffing entire filings, which almost no one does.
- **Still works?** Published 2020 on 1995–2014 data; expect post-publication decay per
  McLean-Pontiff, and some crowding now that similarity scoring is fashionable. But the required
  effort (full-text diff of the entire filing corpus, section-aware) keeps the crowd thin
  relative to price/volume factors. Treat magnitude conservatively; treat existence as robust.
- **Fit with Alembic.** Best available extension of the S4 NLP stack. LLM/embedding-native
  (cosine similarity of filing sections, or LLM-scored diff — exactly the muscle S4 already has),
  daily cadence, pure equity trade. **Orthogonal to S1**; **complementary but distinct from S4**
  (S4 scores *news tone now*; this scores *what changed in the filing vs last year*).
- **Effort / prereqs.** `src/connectors/sec_edgar.py` already pulls 10-K/10-Q; today it flattens
  them into the news/sentiment path. Build: (1) store full filing text keyed by CIK+form+period,
  (2) a section-aware year-over-year similarity/diff worker (cosine on TF-IDF/embeddings, or a
  Loughran-McDonald-weighted diff), (3) a signal from the change magnitude. No new vendor, no
  new instrument.
- **Verdict: Tier A** — the single most defensible NLP-native, orthogonal edge for this system.

## A3. Opportunistic insider trades (SEC Form 4)

- **Edge + source.** Cohen, Malloy & Pomorski, *Decoding Inside Information*
  ([JF 2012](https://ideas.repec.org/a/bla/jfinan/v67y2012i3p1009-1043.html);
  [SSRN 1692517](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1692517);
  [NBER w16454](https://www.nber.org/system/files/working_papers/w16454/w16454.pdf)). Over half
  of insider trades are "routine" (same calendar month every year) and carry **zero** predictive
  power. Stripping those leaves **"opportunistic" trades that hold all the signal: value-weight
  abnormal returns of ~82 bps/month.** Mechanism: genuinely informed, non-scheduled insider
  buying/selling predicts future firm news.
- **Still works?** Insider-return predictability is one of the more persistent effects (informed-
  trader mechanism, not a pure statistical artifact). Discount for crowding and for the fact that
  raw aggregate insider signals are weak — the *routine/opportunistic classifier is the alpha*,
  and it is the part most implementers skip.
- **Fit with Alembic.** Strong. Form 4 filings are **free from SEC EDGAR** (the connector Alembic
  already uses), the classification is **deterministic** (fits their "ticker resolution is
  deterministic, not LLM" philosophy), cadence is daily/event-driven, and it trades plain equities
  on Alpaca. **Orthogonal to S1, S2 and S4.**
- **Effort / prereqs.** Build a Form 4 parser (XML ownership docs on EDGAR), a per-insider history
  store to label routine vs opportunistic (needs a lookback to establish each insider's calendar
  pattern), and a signal worker. Cold-start requires backfilling insider histories. No new vendor.
- **Verdict: Tier A** — deterministic, free data already on hand, orthogonal, event-driven.

---

# Tier B — promising, but needs a data feed, an instrument, or validation

## B1. Residual / idiosyncratic momentum (upgrade to S1, de-crowds it)

- **Edge + source.** Blitz, Huij & Martens, *Residual Momentum*
  ([SSRN 2319861](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2319861); *J. Empirical
  Finance* 2011) and Blitz, Hanauer & Vidojevic, *The Idiosyncratic Momentum Anomaly*
  ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1059056020300927)).
  Rank on momentum of **residual** returns (from a Fama-French/market factor regression), not
  total returns. Result: **~2× the risk-adjusted profit** of plain momentum, **no long-term
  reversal, roughly half the crash risk, and nearly double the Sharpe** — and it survives after
  controlling for the standard factors including plain momentum.
- **Still works?** Documented across regions and updated through the late-2010s; the crash-risk
  reduction is the durable part (it hedges the factor exposures that cause momentum crashes).
- **Fit with Alembic.** Data = **Alpaca price history only** (cheap). But this is an
  *orthogonalization/upgrade of S1*, not net-new alpha — the brief explicitly says prioritize
  orthogonal over S1 refinements, so it ranks below Tier A despite being nearly free. Worth doing
  precisely because it reduces S1's crowding and crash exposure.
- **Effort / prereqs.** A rolling factor regression (market, or FF3/FF5) to extract residuals,
  then momentum on residuals. Needs factor-return series (Ken French library is free). Validate
  vs current S1.
- **Verdict: Tier B** — cheap, well-documented, strictly better momentum; but a refinement, not
  new orthogonal edge.

## B2. Quality / gross-profitability tilt (Novy-Marx)

- **Edge + source.** Novy-Marx, *The Other Side of Value: The Gross Profitability Premium*
  ([JFE 2013](https://www.sciencedirect.com/science/article/abs/pii/S0304405X13000044);
  [NBER w15940](https://www.nber.org/papers/w15940)). Gross profits/assets predicts the
  cross-section about as strongly as book/price, and is **negatively correlated with value**, so
  it diversifies. So robust it was folded into the Fama-French 5-factor model (2015).
- **Still works?** One of the more accepted, replicated premia; crowded as a factor-ETF theme but
  structurally grounded (profitable firms earn more). Modest long-only capture.
- **Fit with Alembic.** Long-only tilt is feasible on Alpaca. **Orthogonal to S1 momentum** and to
  everything in S4. Best used as a slow-moving quality overlay / eligibility filter that also
  de-risks the book (quality tilts defensively).
- **Effort / prereqs.** Needs **fundamentals** (gross profit, total assets) — Alpaca does *not*
  provide these; Finnhub `/stock/financials` or a fundamentals vendor is required. Rebalance
  quarterly. Data quality/point-in-time correctness is the main risk (avoid look-ahead on
  restated financials).
- **Verdict: Tier B** — robust and orthogonal, gated on a fundamentals feed.

## B3. 8-K event drift + earnings-call / filing tone (Loughran-McDonald) as an S4 extension

- **Edge + source.** Loughran & McDonald, *When Is a Liability Not a Liability?*
  ([JF 2011](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01625.x);
  [SSRN 1331573](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1331573);
  [LM Master Dictionary, Notre Dame SRAF](https://sraf.nd.edu/loughranmcdonald-master-dictionary/)):
  a finance-specific negative/uncertainty/litigious word-list predicts filing returns, volatility
  and unexpected earnings — three-quarters of "negative" words in the generic Harvard dictionary
  are false negatives in a financial context. Complementary: 8-K disclosures show **post-filing
  return drift** on some item types, and management **tone change** in MD&A relates to PEAD/accruals
  ([8-K disclosures, Rev. Acct. Studies](https://link.springer.com/article/10.1007/s11142-009-9114-7);
  [tone change & drift](https://link.springer.com/article/10.1007/s11142-009-9111-x)); complex/less
  readable 10-Ks are absorbed more slowly (financial-reporting-complexity underreaction,
  [Rev. Acct. Studies](https://link.springer.com/article/10.1007/s11142-008-9083-2)).
- **Still works?** LM tone is heavily used (crowded) but remains a standard, cheap baseline; the
  incremental edge is stronger on the *less-trafficked* pieces (8-K item-level drift, YoY tone
  *change* rather than level, complexity/readability).
- **Fit with Alembic.** Natural S4 extension — same filings the EDGAR connector already fetches,
  same NLP muscle. Risk: **partial overlap with S4's existing sentiment**; must be built as a
  *distinct filing-tone signal* (structured, per-filing, tone-*change*) rather than more of the
  same news scoring, or it adds correlation not diversification.
- **Effort / prereqs.** Wire the LM dictionary + a readability/complexity metric + 8-K item
  parsing into a filing-tone worker; measure incremental IC over S4.
- **Verdict: Tier B** — cheap and on-mission, but validate orthogonality to S4 before trusting.

## B4. Low-volatility / betting-against-beta (long-only tilt only)

- **Edge + source.** Frazzini & Pedersen, *Betting Against Beta*
  ([JFE 2014](https://econpapers.repec.org/RePEc:eee:jfinec:v:111:y:2014:i:1:p:1-25);
  [NBER w16601](https://www.nber.org/system/files/working_papers/w16601/w16601.pdf)). Leverage-
  constrained investors bid up high-beta names, so low-beta earns higher risk-adjusted returns;
  the BAB factor had a **0.75 Sharpe (1926–2009)**, positive in every 20-yr subperiod.
- **Still works?** The *low-vol tilt* persists but is now a crowded ETF theme; and the full BAB
  premium **requires leveraging the low-beta leg and shorting the high-beta leg** — Alembic is
  effectively long-only and unlevered, so it can only harvest the weaker "long low-beta" fragment.
  Critics also show much of BAB is a leverage/beta-construction artifact
  ([*Betting against betting against beta*, JFE 2021](https://www.sciencedirect.com/science/article/abs/pii/S0304405X21002051)).
- **Fit with Alembic.** Feasible as a **defensive long-only low-vol overlay** (price data only).
  Orthogonal-ish to momentum. Modest, crowded — a risk-reducer more than an alpha source.
- **Effort / prereqs.** Compute rolling beta/vol from Alpaca history; tilt eligibility/sizing.
- **Verdict: Tier B** — feasible and defensively useful, but capped by long-only/no-leverage.

## B5. Qlib + WorldQuant Alpha101 as a *feature & research library* (not standalone alpha)

- **Source.** Kakushadze, *101 Formulaic Alphas*
  ([arXiv 1601.00991](https://arxiv.org/pdf/1601.00991)) — 101 real WorldQuant price/volume
  formulas; Microsoft **Qlib**'s Alpha158/Alpha360 handlers
  ([Qlib docs](https://qlib.readthedocs.io/en/latest/component/data.html);
  [benchmarks README](https://raw.githubusercontent.com/microsoft/qlib/main/examples/benchmarks/README.md))
  — 158/360 engineered price/volume features + a full backtest/ML research harness.
- **Reality check.** These are **short-horizon, price/volume formulaic** signals designed for a
  large-book, market-neutral, low-turnover-cost WorldQuant context. Individually they are heavily
  decayed and **overlap S1/technical** — *not* durable standalone edges on daily US equities with
  Alembic's realistic costs. Their real value is as **tooling**: a vetted feature dictionary and a
  disciplined backtest/label harness to (a) engineer inputs for A1–A3/B1–B2 and (b) systematically
  test/orthogonalize S1.
- **Fit with Alembic.** Qlib is a research/offline library — a natural fit for the Alpha-Miner
  offline layer. Do not deploy Alpha101 formulas as live signals expecting alpha; mine them for
  features and use Qlib as the research harness.
- **Verdict: Tier B (as tooling/feature-engineering), Tier C as standalone alpha.**

---

# Tier C — skip here (decayed, crowded, or infeasible on this stack)

- **Raw PEAD / post-earnings drift (standalone).** Dead for non-microcaps since ~2006; prices now
  fully reflect surprises on announcement day (Martineau, *Rest in Peace PEAD*,
  [SSRN 3111607](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607);
  [Critical Finance Review](https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf); and
  [*Why Has PEAD Declined Over Time?*, Columbia CEASA](https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf)).
  Alembic's own S7 raw-PEAD test already FAILed. The earnings *event* still feeds A1/B3; the raw
  drift trade does not. Original phenomenon: Bernard & Thomas 1989/1990 (see
  [PEAD review, ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2214635020303750)).
- **Short-term reversal (Jegadeesh 1990 / liquidity-provision).** Real in principle — monthly
  reversal is compensation for liquidity provision, strongly predictable by VIX (Nagel,
  *Evaporating Liquidity*, [NBER w17653](https://www.nber.org/system/files/working_papers/w17653/w17653.pdf);
  [RFS 2012]) — but it is a **high-turnover, cost-sensitive, near-intraday** effect. Alembic's
  daily cadence + realistic cost model would eat it; it also needs inventory/liquidity-provider
  behavior Alembic isn't built for. Skip.
- **Time-series momentum (Moskowitz-Ooi-Pedersen).** The documented edge is a **multi-asset
  futures** phenomenon (58 futures across equities/FX/commodities/bonds;
  [SSRN 2089463](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463); JFE 2012). Alpaca
  gives no futures; on equity ETFs it degrades to a modest trend overlay that **overlaps S1**.
  Skip unless/until multi-asset instruments exist.
- **Options/vol beyond S2 — dispersion, VIX-term-structure carry, put-write/covered-call.** All
  real premia (VRP ≈ 4.2 vol pts 1990–2018 per [CBOE PUT white paper](https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/);
  [dispersion](https://quantpedia.com/strategies/dispersion-trading);
  [term-structure carry, NY Fed SR867](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr867.pdf))
  — but **blocked on the same prerequisites as S2**: real options data (Alembic only synthesizes
  BS chains) and IBKR options execution. Put-write/covered-call is essentially S2's cousin. Treat
  as one "become option-aware" program, not quick wins.
- **Options-implied-volatility-spread signal (Cremers-Weinbaum / An-Ang-Bali-Cakici).** The one
  options-derived idea that would *trade equities* (informed traders move options first; the
  put-call-parity IV spread predicts ~1%/month cross-sectional stock returns;
  [Cremers-Weinbaum, SSRN 968237](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968237);
  [An-Ang-Bali-Cakici, NBER w19590](https://www.nber.org/system/files/working_papers/w19590/w19590.pdf)).
  Attractive in principle, but **needs a per-name options quote/IV feed Alembic does not have**
  (only synthetic chains). Move to Tier B *only if* an options-data vendor is added. Data-blocked
  today.
- **Google-Trends / SVI attention (Da-Engelberg-Gao).** Free data
  ([JF 2011](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2011.01679.x);
  [SSRN 1364209](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364209)), but the edge is a
  ~2-week retail-attention **price-then-reversal** pattern: short-horizon, decayed, crowded, and
  more a volatility/turnover predictor than a durable return edge. Marginal for daily equity longs.
- **Reddit / WSB / Twitter social sentiment.** Heavily crowded and noisy; academic evidence
  (Bartov-Faurel-Mohanram Twitter-earnings; WSB studies) shows it predicts **volume/volatility and
  short bursts**, not robust risk-adjusted returns; retail backtests are classic overfits. Also
  overlaps S4. Skip as an alpha source (possibly useful as a *risk/crowding* flag, which is
  plumbing, not alpha).
- **EDGAR-download attention (Drake-Roulstone-Thornock).** Sophisticated-investor EDGAR downloads
  weakly predict returns/fundamentals
  ([Contemp. Acct. Research 2015](https://onlinelibrary.wiley.com/doi/abs/10.1111/1911-3846.12119)),
  but the SEC log-file feed is delayed and the effect is modest. Low priority vs A1–A3.

---

## What to ignore and why

- **RL trading bots (FinRL / FinRL-Meta).** No documented durable alpha; the frameworks
  themselves foreground **overfitting, survivorship bias, and low signal-to-noise** as the core
  problem, and "pure alpha from price alone remains hard"
  ([FinRL-Meta, arXiv 2211.03107 / NeurIPS 2022](https://arxiv.org/abs/2211.03107)). Useful as an
  execution/sizing research sandbox at best — that is plumbing Alembic already has.
- **Indicator-fitting / community Freqtrade & swing bots.** EMA/RSI/crossover/"auto-optimization"
  strategies are curve-fits with no economic mechanism; Freqtrade's docs themselves warn against
  trusting their backtests, and crypto→equity transfer is unjustified. No edge to import.
- **Multi-agent LLM "it beat the market" backtests (TradingAgents) taken at face value.** The
  architecture is interesting ([arXiv 2412.20138](https://arxiv.org/abs/2412.20138)) and worth
  mining for *design* ideas for S4's supervisor/debate step, but the reported outperformance is an
  uncontaminated-backtest claim, not out-of-sample live alpha — do not treat it as evidence of edge.
- **FinGPT as an alpha engine.** Excellent open resource for finance-domain LLM tooling
  ([arXiv 2306.06031](https://arxiv.org/html/2306.06031v2);
  [AI4Finance repo](https://github.com/AI4Finance-Foundation/FinGPT)), but its own numbers are
  the caution: sentiment F1 up to ~0.88 yet **stock-movement accuracy only 45–53%** (barely above
  a coin flip). Mine it for the sentiment pipeline; do not expect the movement prediction to be alpha.
- **Sober cross-check for the whole S4 thesis — StockBench (Oct 2025).** A contamination-free
  benchmark of GPT-5/Claude-4/Qwen3/Kimi-K2/GLM-4.5 as trading agents finds **most fail to beat a
  simple equal-weight buy-and-hold** on both cumulative and risk-adjusted return
  ([arXiv 2510.02209](https://arxiv.org/abs/2510.02209);
  [stockbench.github.io](https://stockbench.github.io/)). This is the strongest external reason to
  add the *structured, orthogonal* Tier-A signals rather than doubling down on LLM-sentiment alone.

---

## Consolidated ranking

| # | Idea | Family | Orthogonal to S1/S4? | Instrument | Data status in Alembic | Tier |
|---|------|--------|----------------------|------------|------------------------|------|
| A1 | Analyst estimate revisions / SUE | Event/fundamental | Yes / Yes | Equity (Alpaca) | Finnhub already integrated; endpoints unwired | **A** |
| A2 | Lazy Prices 10-K/10-Q text-change | Filing NLP | Yes / distinct from S4 | Equity (Alpaca) | EDGAR connector already fetches filings | **A** |
| A3 | Opportunistic insider Form 4 | Event | Yes / Yes | Equity (Alpaca) | Free on EDGAR; parser needed | **A** |
| B1 | Residual / idiosyncratic momentum | Cross-sectional | Upgrade of S1 | Equity (Alpaca) | Alpaca prices + French factors | B |
| B2 | Gross-profitability / quality tilt | Cross-sectional | Yes / Yes | Equity (Alpaca) | Needs fundamentals feed | B |
| B3 | 8-K drift + LM filing-tone change | Filing NLP | Partly overlaps S4 | Equity (Alpaca) | EDGAR + LM dictionary | B |
| B4 | Low-vol / BAB long-only tilt | Cross-sectional | Partly | Equity (Alpaca) | Alpaca prices | B |
| B5 | Qlib / Alpha101 as feature+research library | Tooling | n/a | n/a | Offline research layer | B (tooling) |
| C1 | Raw PEAD standalone | Event | — | — | Dead (Martineau); S7 FAILed | C |
| C2 | Short-term reversal | Cross-sectional | Yes | Equity | Cost/turnover kills it daily | C |
| C3 | Time-series momentum | Trend | Overlaps S1 | Futures (none) | Instrument-blocked | C |
| C4 | Dispersion / VIX carry / put-write | Options/vol | Yes | Options (IBKR) | Blocked like S2 | C |
| C5 | IV-spread equity signal | Options-derived | Yes | Equity + options data | Data-blocked (→B if feed added) | C |
| C6 | Google-Trends/SVI attention | Alt-data | Partly | Equity | Decayed/crowded/short-horizon | C |
| C7 | Reddit/WSB/Twitter sentiment | Alt-data | Overlaps S4 | Equity | Crowded/noisy | C |
| C8 | EDGAR-download attention | Alt-data | Yes | Equity | Modest/delayed | C |

---

## Sources

**Event-driven / fundamental**
- Jung, Keeley & Ronen, *The Predictability of Analyst Forecast Revisions* — https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID2991938_code739506.pdf?abstractid=2991938
- Chan, Jegadeesh & Lakonishok, *Momentum Strategies* (earnings + price momentum) — https://breesefine7110.tulane.edu/wp-content/uploads/sites/16/2015/10/Momentum-2001.pdf
- Cohen, Malloy & Nguyen, *Lazy Prices* — JF 2020 https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12885 · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1658471 · NBER w25084 https://www.nber.org/system/files/working_papers/w25084/w25084.pdf
- Cohen, Malloy & Pomorski, *Decoding Inside Information* — JF 2012 https://ideas.repec.org/a/bla/jfinan/v67y2012i3p1009-1043.html · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1692517 · NBER w16454 https://www.nber.org/system/files/working_papers/w16454/w16454.pdf
- Loughran & McDonald, *When Is a Liability Not a Liability?* — JF 2011 https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01625.x · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1331573 · LM Master Dictionary https://sraf.nd.edu/loughranmcdonald-master-dictionary/
- 8-K disclosures (Rev. Acct. Studies) — https://link.springer.com/article/10.1007/s11142-009-9114-7 · Management tone change & drift — https://link.springer.com/article/10.1007/s11142-009-9111-x · Financial-reporting complexity & underreaction — https://link.springer.com/article/10.1007/s11142-008-9083-2
- Martineau, *Rest in Peace Post-Earnings Announcement Drift* — SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3111607 · CFR pdf https://cfr.ivo-welch.info/published/papers/martineau2021rest.pdf
- *Why Has PEAD Declined Over Time?* (Columbia CEASA) — https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf
- PEAD review (ScienceDirect) — https://www.sciencedirect.com/science/article/pii/S2214635020303750
- Drake, Roulstone & Thornock, *Determinants and Consequences of Information Acquisition via EDGAR* — https://onlinelibrary.wiley.com/doi/abs/10.1111/1911-3846.12119

**Cross-sectional factors**
- Blitz, Huij & Martens, *Residual Momentum* — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2319861
- Blitz, Hanauer & Vidojevic, *The Idiosyncratic Momentum Anomaly* — https://www.sciencedirect.com/science/article/abs/pii/S1059056020300927
- Novy-Marx, *The Other Side of Value: The Gross Profitability Premium* — JFE 2013 https://www.sciencedirect.com/science/article/abs/pii/S0304405X13000044 · NBER w15940 https://www.nber.org/papers/w15940
- Frazzini & Pedersen, *Betting Against Beta* — JFE 2014 https://econpapers.repec.org/RePEc:eee:jfinec:v:111:y:2014:i:1:p:1-25 · NBER w16601 https://www.nber.org/system/files/working_papers/w16601/w16601.pdf · critique https://www.sciencedirect.com/science/article/abs/pii/S0304405X21002051
- Moskowitz, Ooi & Pedersen, *Time Series Momentum* — SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463
- Jegadeesh (1990) short-term reversal; Nagel, *Evaporating Liquidity* — NBER w17653 https://www.nber.org/system/files/working_papers/w17653/w17653.pdf
- McLean & Pontiff, *Does Academic Research Destroy Stock Return Predictability?* — JF 2016 https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12365 · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623

**Options / volatility**
- CBOE PUT-index / VRP white paper — https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/
- Dispersion trading (Quantpedia) — https://quantpedia.com/strategies/dispersion-trading
- Volatility term-premia (NY Fed SR867) — https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr867.pdf
- Cremers & Weinbaum, *Deviations from Put-Call Parity and Stock Return Predictability* — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=968237
- An, Ang, Bali & Cakici, *The Joint Cross Section of Stocks and Options* — NBER w19590 https://www.nber.org/system/files/working_papers/w19590/w19590.pdf

**Alt-data / attention / social**
- Da, Engelberg & Gao, *In Search of Attention* — JF 2011 https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2011.01679.x · SSRN https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1364209 · pdf https://www3.nd.edu/~zda/Google.pdf
- Bartov, Faurel & Mohanram (Twitter/earnings), WSB studies — https://link.springer.com/article/10.1007/s11408-022-00415-w

**Frameworks / benchmarks (tooling & sober checks, not alpha)**
- Kakushadze, *101 Formulaic Alphas* — https://arxiv.org/pdf/1601.00991
- Microsoft Qlib docs (Alpha158/360) — https://qlib.readthedocs.io/en/latest/component/data.html · benchmarks https://raw.githubusercontent.com/microsoft/qlib/main/examples/benchmarks/README.md
- TradingAgents — https://arxiv.org/abs/2412.20138 · https://github.com/tauricresearch/tradingagents
- FinGPT — https://arxiv.org/html/2306.06031v2 · https://github.com/AI4Finance-Foundation/FinGPT
- FinRL-Meta — https://arxiv.org/abs/2211.03107
- StockBench — https://arxiv.org/abs/2510.02209 · https://stockbench.github.io/
- Freqtrade backtesting docs / strategies — https://www.freqtrade.io/en/stable/backtesting/ · https://github.com/freqtrade/freqtrade-strategies

**Alembic internal grounding (fit/effort)**
- `src/connectors/sec_edgar.py` (already fetches 8-K/10-Q/10-K), `src/connectors/finnhub_news.py`
  (Finnhub integrated, only company-news endpoint wired), `src/strategies/{s1,s2,s3,s4}`,
  `docs/strategies/s2-vrp-theory.md`, `docs/RESEARCH_S2_S3_S7_PRIMARY_LITERATURE_2026-07-15.md`.
