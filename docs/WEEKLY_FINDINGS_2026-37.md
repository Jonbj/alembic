# Weekly Findings — ISO Week 37 (2026-09-07 → 2026-09-11)

Synthesis of the one daily alpha-miss report, two raw dossiers with no report, and five job
logs covering the sessions of Monday 2026-09-07 through Friday 2026-09-11. Read-only
analysis; no code, orders or tuning were touched. Written 2026-09-12.

**The headline of this week is not a trade. It is that the measurement pipeline stopped
twice and nobody was told.** Two of the week's four trading sessions have no report, no
row in the pre-registered evidence ledger, and no finding occurrences, because both
Claude-driven crons died on the account's weekly quota on 2026-09-10 and again on
2026-09-11. Everything below about 2026-09-09 and 2026-09-10 was reconstructed in this
review directly from the raw dossier JSON and the live database.

---

## 1. Scope

### Sessions in the week

| Date | Session | Report | Dossier | Status |
|---|---|---|---|---|
| Mon 2026-09-07 | **US market closed** (Labor Day) | — | — | No trading session. The cron ran and re-targeted 2026-09-04 (§5.2). |
| Tue 2026-09-08 | traded | `docs/ALPHA_MISS_REPORT_2026-09-08.md` | `2026-09-08.json` | ✅ complete |
| Wed 2026-09-09 | traded | **none** | `2026-09-09.json` | ⚠️ run failed after the dossier |
| Thu 2026-09-10 | traded | **none** | `2026-09-10.json` | ⚠️ run failed after the dossier |
| Fri 2026-09-11 | traded | not yet analysable | not yet generated | Scheduled for the Monday 2026-09-14 run (D-1 convention, see W36 §1). **No data for 09-11 is asserted anywhere in this document.** |

Verified by `ls`, not taken from the brief:

```
docs/ALPHA_MISS_REPORT_2026-09-08.md      34427  (last full report of the week)
docs/evidence/dossier/2026-09-08.json   3084926
docs/evidence/dossier/2026-09-09.json   3202789
docs/evidence/dossier/2026-09-10.json   3487230
docs/FORENSIC_DAILY_REPORT_2026-09-07.md  37616
docs/FORENSIC_DAILY_REPORT_2026-09-08.md  75332   (last forensic report of the week)
```

There is no `ALPHA_MISS_REPORT_2026-09-07.md` and that is correct — 09-07 was a market
holiday. There is no `ALPHA_MISS_REPORT_2026-09-09.md` or `-09-10.md`, and that is **not**
correct: those are the two lost sessions.

### The two failed runs, verbatim

`logs/alpha_miss_analysis_2026-09-10.log` (target 2026-09-09), final three lines:

```
INFO 2026-09-09 -> 2026-09-09.json | mover 7 (up 4, down 3) | zero-news 38 | ingressi 2 | chiusure 1
Dossier generato: /home/stefano/Documents/Projects/Alembic/docs/evidence/dossier/2026-09-09.json
You've hit your weekly limit · resets Sep 11, 4pm (Europe/Rome)
FAILED: sessione Claude terminata con codice 1
```

`logs/alpha_miss_analysis_2026-09-11.log` (target 2026-09-10):

```
INFO 2026-09-10 -> 2026-09-10.json | mover 13 (up 3, down 10) | zero-news 40 | ingressi 2 | chiusure 6
Dossier generato: /home/stefano/Documents/Projects/Alembic/docs/evidence/dossier/2026-09-10.json
You've hit your weekly limit · resets 4pm (Europe/Rome)
FAILED: sessione Claude terminata con codice 1
```

**The forensic cron died the same way on the same two days.** `logs/daily_analysis_2026-09-10.log`
(371 bytes) and `-09-11.log` (363 bytes) both end on `You've hit your weekly limit` +
`FAILED: sessione Claude terminata con codice 1`. So **four analysis runs were lost, not two**,
and `docs/FORENSIC_DAILY_REPORT_2026-09-09.md` and `-09-10.md` do not exist either.

### What the failures cost the evidence base

| Artifact | 09-08 | 09-09 | 09-10 |
|---|---|---|---|
| dossier JSON | ✅ | ✅ | ✅ |
| alpha-miss report | ✅ | ❌ | ❌ |
| forensic report | ✅ | ❌ | ❌ |
| row in `market_daily.jsonl` | ✅ | ❌ | ❌ |
| occurrences in `findings.json` | 40 | **0** | **0** |
| day in `economic_pnl.json` | ✅ | ❌ | ❌ |

```bash
tail -1 docs/evidence/market_daily.jsonl | jq -r .data   # 2026-09-08
jq -r '.scoreboard.giorno.n' docs/evidence/economic_pnl.json   # 26  (of 40)
```

Two independent dossiers carry the frozen consequence in-band: `aggregati.miss_cumulati` is
**bit-identical** in `2026-09-09.json` and `2026-09-10.json` —
`{"NO_NEWS":67,"THIN_NEUTRAL":70,"WRONG_SIGN":11,"FILTERED":12,"OUT_OF_STRATEGY_SCOPE":5}` —
because `_miss_cumulati()` reads `market_daily.jsonl`, which stopped advancing on 09-08.

### Sources actually used

- `docs/ALPHA_MISS_REPORT_2026-09-08.md`
- `docs/evidence/dossier/2026-09-08.json`, `2026-09-09.json`, `2026-09-10.json` — **schema 2.9**, not 2.8 as the brief stated; the bump carries #509's `causa` / `causa_legacy` split
- `logs/alpha_miss_analysis_2026-09-{07,08,09,10,11}.log`, `logs/daily_analysis_2026-09-{09,10,11}.log`, `logs/roadmap_agent_cron.log`
- `docs/FORENSIC_DAILY_REPORT_2026-09-07.md`, `-09-08.md` (findings F-072/F-073 → #551/#550, not re-filed)
- `docs/evidence/findings.json` (`prossimo_id: 74`), `market_daily.jsonl`, `economic_pnl.json`
- `logs/containers/{worker,worker-inference,api,beat,worker-news-stream}-2026-09-{08..11}.log`
- Live DB `alembic-postgres-1` / `trading`: `execution_decisions`, `s4_intent_events`, `sentiment_signals`, `news_log`, `ticker_lookup`
- `docs/WEEKLY_FINDINGS_2026-36.md` for format continuity and de-duplication
- Source code under `src/` and `scripts/` for root-cause location

---

## 2. Summary statistics

### Per session

| Session | Movers ≥3% | up / down | Held or caught | Miss candidates | Zero-news | σ cross-sect. | SPY / QQQ |
|---|---:|---|---:|---:|---|---:|---|
| 2026-09-08 | 19 | 9 / 10 | 10 | 9 | 37 / 96 (38,5%) | 2,50% | −0,55% / −0,08% |
| 2026-09-09 | 7 | 4 / 3 | 3 | 4 | 38 / 96 (39,6%) | 1,75% | −0,46% / −0,29% |
| 2026-09-10 | 13 | 3 / 10 | 10 | 3 | 40 / 96 (41,7%) | 1,87% | −0,60% / −1,06% |
| **Week (3 sessions)** | **39** | **16 / 23** | **23** | **16** | mean 38,3 / 96 (39,9%) | — | — |

2026-09-11 is excluded from every figure in this document.

### Miss causes

For 09-08 the analyst re-reading is the report's own. For 09-09 and 09-10 there was no
report, so the classification below is this review's, made after reading each article title
in the dossier; the dossier's mechanical `causa` is given alongside so the two are
separable.

| Symbol | Session | Return | Dossier `causa` | Analyst reading | Evidence |
|---|---|---:|---|---|---|
| BIDU | 09-08 | −6,96% | BELOW_GATE | THIN_NEUTRAL | max own −0,099, correct sign, ⅓ of gate |
| NOW | 09-08 | −4,99% | BELOW_GATE | **WRONG_SIGN** | +0,26 from a digest headlined about HOOD; `quota_righe_fanout` 1,0 |
| INFY | 09-08 | −4,87% | NO_NEWS | NO_NEWS | zero rows |
| F | 09-08 | −4,24% | BELOW_GATE | THIN_NEUTRAL | fan-out **−0,2990** vs gate 0,30 — **margin 0,001**, narrowest in the series |
| SONY | 09-08 | −4,19% | NO_NEWS | NO_NEWS | zero rows |
| TSLA | 09-08 | +3,98% | BELOW_GATE | THIN_NEUTRAL | max own +0,138, gap 0,162; net accessible 21,48 $ |
| ARM | 09-08 | +3,74% | OFF_TOPIC_NON_DECIDIBILE | THIN_NEUTRAL | +0,028; net accessible 34,42 $ |
| ADBE | 09-08 | −3,47% | BELOW_GATE | THIN_NEUTRAL | one fan-out row, score **0,000 exact** |
| RDDT | 09-08 | −3,29% | OFF_TOPIC_NON_DECIDIBILE | **WRONG_SIGN** | 3 rows, all positive, against −3,29% |
| CMCSA | 09-09 | −6,61% | NON_ACTIONABLE (legacy NON_CLASSIFICATO) | signal correct, **blocked by mandate** | 1 row, **−0,386**, correct sign, above gate in magnitude, `n_ticker=1`, `TAG_UNCONFIRMED` |
| META | 09-09 | +6,55% | BELOW_GATE | THIN_NEUTRAL | max own +0,234, gap 0,066; accessible 6,62 $ net |
| F | 09-09 | −3,93% | BELOW_GATE | THIN_NEUTRAL | max fan-out −0,204, no own channel |
| **IBM** | 09-09 | **+3,38%** | NO_NEWS | NO_NEWS | zero rows; **net accessible 82,29 $ — the week's largest** |
| ORCL | 09-10 | −5,38% | NON_ACTIONABLE (legacy NON_CLASSIFICATO) | **WRONG_SIGN** | max own **+0,36** — above gate, bullish, on the day's 2nd-worst stock, and `fallback: true` |
| ARM | 09-10 | −3,80% | NO_NEWS | NO_NEWS | zero rows |
| F | 09-10 | +3,20% | BELOW_GATE | THIN_NEUTRAL | max own +0,1725; accessible 4,77 $, net 3,52 $ |

Analyst totals over 16 candidates: **THIN_NEUTRAL 8 (50,0%)** · **NO_NEWS 4 (25,0%)** ·
**WRONG_SIGN 3 (18,8%)** · mandate-blocked-with-correct-signal 1 (6,3%) · FILTERED 0 ·
OUT_OF_STRATEGY_SCOPE 0.

Dossier mechanical classifier for the same 16: `BELOW_GATE` 8, `NO_NEWS` 4,
`NON_ACTIONABLE` 2, `OFF_TOPIC_NON_DECIDIBILE` 2.

**THIN_NEUTRAL dominance from W36 holds** (11/22 = 50,0% then, 8/16 = 50,0% now), and it is
the same 50 % three weeks running. NO_NEWS fell from 31,8 % to 25,0 %.

### Money

| Measure | Week 37 |
|---|---:|
| Gross close-to-close × 2.200 $ across the 16 candidates | ≈1.480 $ |
| **`net_opportunity_usd` actually reachable** | **≈148 $** |
| — of which IBM 09-09 (NO_NEWS) | **82,29 $** |
| — of which ARM 09-08 (THIN_NEUTRAL) | 34,42 $ |
| — of which TSLA 09-08 (THIN_NEUTRAL) | 21,48 $ |
| — of which META 09-09 (THIN_NEUTRAL) | 6,16 $ |
| — of which F 09-10 (THIN_NEUTRAL) | 3,52 $ |

Eleven of the sixteen candidates are downside moves on unheld names, so their accessible
opportunity is **0,00 $** by construction on a long-only book. The gross figure is reported
only for comparability with the historical series, as in W36 — it overstates the prize by
roughly an order of magnitude.

### Book

| Session | Intraday P&L | of which passive | of which selection | exit effect | market beta-1 |
|---|---:|---:|---:|---:|---:|
| 2026-09-08 | −161,63 $ | −73,24 $ | −118,35 $ | +29,96 $ | −132,57 $ |
| 2026-09-09 | −93,16 $ | −77,05 $ | −15,08 $ | −1,03 $ | −78,38 $ |
| 2026-09-10 | −100,59 $ | −88,93 $ | −3,00 $ | −8,67 $ | −9,74 $ |
| **Total** | **−355,38 $** | **−239,22 $** | **−136,43 $** | **+20,26 $** | — |

(`decision_quality.summary`; the axes are not additive by construction,
`counterfactual_axes_are_additive: false`.)

Closing equity is available only for 09-08 — **109.910,06 $**, −63,61 $ on the session,
realised −163,44 $ — because the two later sessions produced no report and the dossier does
not carry an Alpaca equity snapshot.

**Two thirds of the week's measured intraday loss is passive**, i.e. held exposure rather
than any decision taken that day. On 09-10 the split is starkest: −88,93 $ passive against
−9,74 $ of market beta, so the loss is sector-concentrated, not market-driven.

### Economic scoreboard

Stuck at **day 26 / 40**, `as_of 2026-09-08`, because of the failed runs.

- S4 economic cumulative **−495,22 $** against the ±200 $ band — `within: false`, and
  deteriorating from the ≈−400 $ that held flat through all of W36.
- S1 **+948,78 $**, against an SPY benchmark of +465,45 $ on a 43.848,85 $ base →
  **delta +483,33 $**.
- Book **+418,72 $**; contamination −34,84 $ on 1 position.
- NO_NEWS-dominant days 12 / 26 (46,2 %), paper threshold 60 % → not exceeded.
- **`numerosita.S4 = 74`** — past the n=73 that #179 exists to precede (§5, #179).

---

## 3. Market context

Two regimes across the three analysable sessions, and the book crossed the second one
entirely passively.

- **09-08 — rotation into legacy semis/hardware and energy, out of enterprise software.**
  INTC +9,05%, NOK +6,18%, AMD +5,90%, AMAT +3,98%, ARM +3,74%, QCOM +3,17% against
  NOW −4,99%, INFY −4,87%, CRM −3,90%, ADBE −3,47%. Indices near flat (SPY −0,55%,
  QQQ −0,08%) on σ 2,50% — idiosyncratic, not beta.
- **09-09 — quiet, narrow.** Only 7 movers, σ 1,75%, the lowest dispersion of the window.
  META +6,55% on its own AI-agent news; CMCSA −6,61% on a CFO guidance walk-down. No
  sector axis.
- **09-10 — the semis rout, and the book was long all of it.** INTC −5,57%, ORCL −5,38%,
  DELL −5,35%, MU −4,90%, WDC −4,43%, RIO −4,19%, ARM −3,80%, MRVL −3,43%, AMD −3,36%,
  AMAT −3,17%, SOXX −2,74%. **10 of the 13 movers were down, 9 of the 13 were already
  held.** By sector notional, semis carried 10 positions / 5.313 $ / −60,33 $ passive, the
  single largest drag.

The two-week theme from W36 — semis/hardware up against software — **inverted inside 48
hours** on 09-10, with the book at maximum exposure to the side that broke. That is a
concentration observation, not an alpha one: nothing in the pipeline chose to be long
eleven semis names on 09-10 rather than ten on 09-08.

---

## 4. Findings

F-codes continue from `docs/evidence/findings.json` (`prossimo_id: 74` at time of writing).

### 4.1 — F-074 — The daily evidence crons lose a session permanently on quota exhaustion → **#563**

Four runs across two scripts died on `You've hit your weekly limit`, and sessions 09-09 and
09-10 are now absent from `market_daily.jsonl`, `findings.json` and `economic_pnl.json`
(§1). Three mechanisms, all located:

1. **No gap detection.** `scripts/daily_alpha_miss_analysis.sh:51-63` takes `cal[-1]` from
   the Alpaca calendar and never compares it against what is already at ledger. A failed day
   is never re-targeted.
2. **Quota exhaustion is terminal and indistinguishable from a real error.** `:475-487`
   treats a *self-clearing* block exactly like a permanent failure: `exit 1`. The quota reset
   at 16:00 Rome on 09-11; both jobs had already fired at 10:00 and 14:30 Rome and neither
   was re-attempted after it.
3. **The repo already contains the fix, and even it has the hole.**
   `scripts/roadmap_agent_loop.sh` detects engine exhaustion, benches the engine to a known
   expiry and does not charge the attempt. But `_RATE_LIMIT_RE` at line 84 —
   `rate.?limit|429|quota exceeded|too many requests|usage limit|resource_exhausted|overloaded`
   — **does not match Claude Code's actual string**. Verified:
   `echo "You've hit your weekly limit · resets 4pm (Europe/Rome)" | grep -qiE "$RE"` → no match.

Compounding: `tg_send()` (`:83-96`) pipes curl to `/dev/null`, never checks its exit code,
and every call site appends `|| true`. [F-005] records six `400 Bad Request` responses from
`api.telegram.org/sendMessage` in `logs/containers/worker-2026-09-08.log`, so "the alert was
sent" is not a claim this deployment can currently make.

Both evidence crons also share an unpartitioned quota with `roadmap_agent_loop.sh`, which
fires 8×/day (`0 7,12,17,21` claude + `0 9,14,19,23` codex) and runs first.

### 4.2 — F-075 — Market-holiday runs re-analyse the previous session; there is no idempotency guard → **#564**

Labor Day made `DATE_TARGET` resolve to **2026-09-04 on two consecutive runs**, 09-07 and
09-08. The Claude session correctly refused to re-append —

> «This session's task — the 2026-09-04 alpha-miss analysis — was already completed and
> committed by an earlier run (commit `e5512c9`) […] I did not re-run or re-append anything»

— but by then the dossier had already been regenerated, and afterwards the wrapper re-ran
the economic scoreboard and **committed both files as `88bfb05 evidence: ledger 2026-09-04`,
the same message as `e5512c9`**. Every guard in the script is about ledger integrity (#510)
or code freshness (#507); none asks *"have I already done this"*. The duplicate detection
lives only in the prompt, i.e. in the model's judgement, and runs after the expensive steps
and before the ones that follow.

This recurs on every weekday US market holiday — roughly 9 times a year.

### 4.3 — F-076 — Re-running the pipeline silently rewrites the frozen evidence series → **#565**

The consequence of 4.2, and the more serious half. `git show 88bfb05`:

- **The committed dossier for a closed session changed its prices.** 95 changed value lines
  in `docs/evidence/dossier/2026-09-04.json`: WDC `close_price` 467,46 → 467,31,
  `ritorno_seduta` 0,05863170 → 0,05862764, `dispersione_sigma` 0,024183443 → 0,024183337.
- **The economic scoreboard rewrote 18 historical daily values back to 2026-08-04** —
  the whole observation window — with deltas of ±0,029811 / ±0,089432 $, the signature of a
  single position's mark re-scaling.

Root cause: `scripts/economic_pnl_scoreboard.py::_load_closes()` (lines 94-121) re-fetches
the **entire** window on every invocation with `adjustment="all"`, and `scrivi()` replaces
the file wholesale. Retroactive adjustment plus full recomputation means any bar revision
propagates **backwards** through the whole pre-registered series.
`scripts/commit_evidence_ledger.sh::stage_paths()` is the last line of defence and, per
#510's own write-up, falls through to a bare `cp` for `docs/evidence/dossier/*.json`.

`docs/evidence/OBSERVATION_CHARTER.md` forbids exactly this: a published series is never
silently revised, and a change in measurement is a discontinuity to be annotated. Here the
series revises itself on a schedule, under a duplicate commit message.

The dollar amounts are cents. **The property is what matters**: nothing bounds the drift, and
a real split on a held name would move the same mechanism by percent — including the `#185`
and `#191` segment boundaries the charter uses. The same principle was already accepted and
fixed once, for `forward_return`, in #192/#193.

### 4.4 — F-077 — The relevance classifier cannot see the issuer in its own headline → **#566**

`ticker_lookup` stores suffixed legal names only, and `_contains_term()` requires a
whole-phrase match, so articles that name the company by its common name are filed
`TAG_UNCONFIRMED` (the `source_metadata` path) or `FALSE_ENTITY_MATCH` (the `org_lookup`
path) and excluded from `max_score_own`.

**AAPL, 2026-09-09, Apple's product-launch day** — `copertura_articoli.per_ticker.AAPL`:
33 unique articles, `ISSUER_SPECIFIC: 10`, **`TAG_UNCONFIRMED: 23`**,
`quota_effective_timely` **0,303**. The 23 are titled *"Apple Announces AirPods 5"*,
*"Apple Announces Apple Watch Series 12 And Apple Watch Ultra 4"*, *"Apple Introduces Audio
Intelligence"*. Apple's coverage of its own launch is recorded as 30 %.

**ORCL, 2026-09-10** — signal 10450, `extraction_method: org_lookup`,
`testo_scorato: "Oracle set to report as Street weighs capex risk against cloud growth"`,
`relevance: "FALSE_ENTITY_MATCH"`. An article whose first word is the company name, filed
as a false entity match. `FALSE_ENTITY_MATCH: 2` on 09-10 is the first non-zero value this
category has ever carried, and both instances are wrong in this direction.

**CMCSA, 2026-09-09** — the day's worst mover (−6,61 %), one article,
*"Comcast CFO Says Q3 Broadband Subscriber Losses Unlikely To Improve…"*, `n_ticker=1`,
score **−0,386** (correct sign, above gate in magnitude), `TAG_UNCONFIRMED`,
`max_score_own: null`.

Rate over the week: **62 of 704 rows (8,8 %)** — 10 / **29 (16,0 %)** / 14 / 9 by session;
`source_metadata` 59, `org_lookup` 3; AAPL 23, NVDA 7, ORCL 5, CVX 4, QCOM 4, TSLA 3.
**65 of 89 `ticker_lookup` rows have no alias equal to their own suffix-stripped stem.**

Measurement-only — `article_coverage.py` is imported by `scripts/alpha_miner_dossier.py` and
`scripts/measure_169_dedup_rules.py`, by no live worker — and that is why it matters: it
corrupts the evidence, not the orders. It also **blocks #405's proposed enforcement**, whose
fix item 1 is precisely this check; gating on it today would suppress ~15 correctly-tagged
rows per session. The fix is the alias table, **not** relaxing the matcher to a substring
test — that would re-open the false-positive hole #405 exists to close.

### 4.5 — F-078 — `funnel_v2` has no exit-side KPI → **#567**

On **2026-09-10**, 8 of 13 movers were `EXIT_RISK` (INTC −5,57%, DELL −5,35%, MU −4,90%,
WDC −4,43%, RIO −4,19%, MRVL −3,43%, AMD −3,36%, AMAT −3,17%). All 8 were excluded via
`esclusi_pipeline: {"held": 9}`, and every published KPI ran on a denominator of 1 or 2:
`active_signal_recall` 1/2, `execution_conversion_rate` 1/1, `profitable_capture_rate` 0/2.

Only INTC produced a SELL. `execution_decisions` for the other seven:

```
DELL|SKIP_THRESHOLD|24|0.000|0.000     MU  |SKIP_THRESHOLD|24|0.000|0.000
RIO |SKIP_THRESHOLD|24|0.000|0.000     WDC |SKIP_THRESHOLD|24|0.000|0.000
AMD |SKIP_THRESHOLD|19|0.000|0.000     AMAT|SKIP_THRESHOLD|11|0.000|0.000
MRVL|SKIP_THRESHOLD| 5|0.000|0.000
```

Four positions ran **24 consecutive cycles** while bleeding 4,2–5,4 %, producing nothing but
`SKIP_THRESHOLD`. DELL's rows carry `signal_id 10245`, generated **2026-09-09 19:59:48Z** —
the previous session — on all 24 cycles, with `signal_score 0,105`.

Root cause is deliberate scope that was never completed:
`src/analysis/dossier/funnel.py:343-354` runs `classify_pipeline()` only for
`ENTRY_OPPORTUNITY` and collapses `EXIT_RISK` and `PASSIVE_EXPOSURE` to the same exclusion
string `"held"`; the KPI block at `:402-436` has no exit-side term at all. Excluding held
movers from *entry* KPIs is correct and was the point of #281 — the defect is that no
exit-side KPI was added in their place.

The book's own attribution says this is where the money went: −88,93 $ passive against
−9,74 $ of market beta on 09-10, and −239,22 $ of the week's −355,38 $ intraday total.

A secondary observation recorded here and not filed: `_rapporto()` publishes 0/2 with no
`INSUFFICIENT_N` state, so a two-observation zero reads exactly like a measured zero —
against the discipline `config/s4_kill_criterion.yaml` applies everywhere else.

---

## 5. Recorded against existing issues

Comments added with dated W37 evidence rather than duplicate issues.

| Finding | Issue | W37 evidence added |
|---|---|---|
| Per-ticker news blind spot — **with a correction** | [**#511**](https://github.com/Jonbj/alembic/issues/511) | 14 symbols zero on all 3 sessions. Of W36's "permanent 16": **8 persisted** (ASML, BP, ERIC, JD, MMM, PBR, SAP, SONY), **8 produced news** (AZN, GE, IBM, RDDT, RIO, SBUX, T, VALE), **6 new** (BAC, BRK.B, COST, TXN, UBS, UNH). The set is half-persistent with a rotating remainder — the "permanent" framing needs narrowing. And leaving the set is not coverage: **IBM** produced news in W37 and was still the week's largest accessible miss (+3,38 %, `news_count: 0` that session, **82,29 $**). Source HHI still 0,802. |
| Buys after the move is >100 % complete | [**#512**](https://github.com/Jonbj/alembic/issues/512) | 4 of 6 non-degenerate entries above 1,0: **MU 1,264** (09-09, highest ever recorded, previous 1,0676), RDDT **1,0367**, NVDA 1,0046, SPCX-2 1,038. **RDDT 09-10 is the sharpest case**: the day's *best* mover at +6,08 %, correctly selected, bought at 18:07 for 155,67 $ against a 155,34 $ close — `funnel_v2` files it `BAD_FILL`, not a miss. Selection right, timing fatal. |
| S4 kill-criterion sample threshold | [**#179**](https://github.com/Jonbj/alembic/issues/179) | **`numerosita.S4 = 74`** as of 09-08 — past the n=73 in the issue title. The issue is labelled `waiting`; the condition fired and nothing observed it. Two blockers flagged: the series has a 3-session hole (#563) and is mutable (#565). S4 economic −495,22 $ vs the ±200 $ band, deteriorating from ≈−400 $. |
| FMP earnings calendar | [**#507**](https://github.com/Jonbj/alembic/issues/507) | **Fixed and confirmed.** `status: OBSERVED`, empty `missingness`, `streak: 0` on both 09-09 and 09-10, and on 09-10 the source **discriminated** — ADBE flagged, ADBE closed −2,37 %. HTTP 200 to FMP visible in both cron logs. Proposed for closure by the operator. |
| Provider-tag validation | [**#405**](https://github.com/Jonbj/alembic/issues/405) | Its fix item 1 is now implemented and yields **62 false negatives/week** at current alias quality (#566) — do not gate on it until `ticker_lookup` is repaired. `FALSE_ENTITY_MATCH` finally became non-zero and its first 2 assignments are both wrong. New same-direction case: **NOW 09-08**, single row `+0,26`, `subject_ticker=NOW`, `ISSUER_SPECIFIC`, from *"Robinhood To Rally Around 23%?…"* — a HOOD digest, against a −4,99 % day, `quota_righe_fanout` 1,0, fourth session in five. |
| Top-N saturation | [**#400**](https://github.com/Jonbj/alembic/issues/400) | 93,6 % → **98,3 %** (118/120, 09-09) → **98,0 %** (99/101, 09-10). Two slots in a hundred reached a buyable name. **Cost still demonstrably zero**: of 41 `RANK_OUTSIDE_TOP_N` rows across both days, `is_tradable = true` on none. `SKIP_ENTRY_FRESHNESS` is the second-largest disposition both days (665, 762); `SKIP_FALLBACK` jumped 15 → 196. |

Already filed before this review and confirmed still live, so no action: **#550** and **#551**
(F-072/F-073, forensic reports of 09-07 and 09-08); **#544** (FinBERT fallback evidence);
**#549** (the anti-selective gate); **#509** — closed 2026-09-09, and its fix is **visibly
working** in these dossiers, which now carry `causa: NON_ACTIONABLE` with
`causa_legacy: NON_CLASSIFICATO` preserved alongside, exactly as designed.

---

## 6. Observations not turned into issues

| Observation | Why not filed |
|---|---|
| **FinBERT fallback at 32–37 % on every session of the week** (09-08 37,4%, 09-09 32,2%, 09-10 34,3%, 09-11 32,8%). Concentrated: 09-10 at 14:00Z was 24/60 (40,0%). | This is a *standing rate*, not the outage [F-049] describes, and the mechanism is already owned by #544 and the closed #427/#431. Recording the level because a chronic third of signals coming from the fallback model changes how every score in the window should be read — but there is no new mechanism here. |
| **`DECAY CRITICAL` alerts rose from 6/day to 10/day** (09-09, 09-10, 09-11) and still exist only as `log.critical`. | [F-004] and [F-062], both already recorded. Volume change only. |
| **Telegram `400 Bad Request`** on 2, 6 and 4 alerts across 09-09/09-10/09-11. | [F-005]. Folded into #563 as the reason the failure alert cannot be verified, rather than re-filed. |
| **The `SKIP_THRESHOLD` reason string prints `abs(sig_score)`** — `portfolio_scheduler.py:3707`, so AMD's −0,081 is logged as *"score 0.081 < feedback threshold 0.300"*. | Cosmetic in the log; `signal_score` is persisted signed and the funnel reads the signed field (`funnel.py` criterion 3 is explicit about this). Worth a one-line fix whenever that file is next touched, not an issue. |
| **`execution_decisions.score = 0.0` on all `SKIP_THRESHOLD` rows.** | Checked and *not* a bug: `portfolio_scheduler.py:3700` sets it deliberately — *"no allocation weight — it never reached ranking"* — and `signal_score` carries the real value. Recorded so the next reviewer does not re-open it. |
| **SELL rows still missing `signal_id`**: 0/5 on 09-08, 2/6 on 09-10 (`regressions: ["SELL","SKIP_PYRAMIDING"]`), while overall fill rate is 99,1–99,9 %. | [F-011], and §9.3 of the 09-08 report already flags it as a probable defect. Belongs to the existing exit-traceability work; adding a third issue would fragment it. |
| **`aggregati.cause_del_giorno` still reports `NON_CLASSIFICATO`** on both new dossiers. | By design, not residue. `funnel_v2.nota_freeze` states the legacy counts are preserved intact under the #171 freeze; #509's fix added `causa`/`causa_legacy` alongside rather than replacing. Working as specified. |
| **Semis concentration on 09-10**: 10 held positions, 5.313 $ notional, −60,33 $ passive, the single largest sector drag on the day the complex fell 2,4–5,6 %. | A portfolio-construction observation, not a pipeline defect — nothing in the pipeline *chose* that concentration and no gate was bypassed. It is the substance behind #567's exit-side KPI gap; filing it separately would duplicate that. |
| **F recurred as a miss on all three analysable sessions** (−4,24 %, −3,93 %, +3,20 %), always below gate, never above 0,2990. ARM recurred twice (THIN_NEUTRAL then NO_NEWS). | Per-name recurrence of #408 (near-gate) and #511 (coverage). Noted for frequency; no new mechanism. |
| **Schema version moved 2.8 → 2.9** between the 09-08 and 09-09 dossiers. | Expected: it carries #509's `causa`/`causa_legacy` split, merged 2026-09-09. Recorded because the task brief said 2.8 and the dossiers say 2.9. |

---

## 7. GitHub issues created

| # | Title | Labels |
|---|---|---|
| [#563](https://github.com/Jonbj/alembic/issues/563) | `[BUG]` The daily evidence crons lose a session permanently when the Claude quota is exhausted | bug, observability, alpha-miss, weekly-findings, wayfinder:task, ready-for-agent, tier2, freeze-ok |
| [#564](https://github.com/Jonbj/alembic/issues/564) | `[BUG]` Market-holiday runs re-analyse the previous session: no idempotency guard | bug, observability, alpha-miss, weekly-findings, wayfinder:task, ready-for-agent, tier2, freeze-ok |
| [#565](https://github.com/Jonbj/alembic/issues/565) | `[DATA]` Re-running the evidence pipeline rewrites the frozen series | bug, data-quality, observability, alpha-miss, weekly-findings, wayfinder:task, ready-for-agent, tier2, freeze-ok |
| [#566](https://github.com/Jonbj/alembic/issues/566) | `[DATA]` `ticker_lookup` stores only suffixed legal names, so the relevance classifier cannot see the issuer in its own headline | bug, data-quality, alpha-miss, weekly-findings, wayfinder:task, ready-for-agent, tier2, freeze-ok, paper-monitoring |
| [#567](https://github.com/Jonbj/alembic/issues/567) | `[OBS]` `funnel_v2` has no exit-side KPI | bug, observability, alpha-miss, weekly-findings, wayfinder:task, ready-for-agent, tier2, freeze-ok, paper-monitoring |

All five are `freeze-ok` under #171: measurement, instrumentation and configuration only.
None proposes a threshold change, and #566 and #567 explicitly defer any enforcement to a
post-freeze decision.

**Dependency to respect when these are picked up:** #565 before #563. #563's proposed gap
recovery back-fills missed sessions by re-targeting past dates, and under current code that
back-fill would re-adjust every artifact it touches. #563 must either wait for #565 or be
implemented as ledger-rows-only with the committed dossiers left frozen. Both issues state
this.

### Comments added to existing issues

#511, #512, #179, #507, #405, #400 — see §5.

---

## 8. Continuity with Week 36

**Held.**

- **THIN_NEUTRAL dominance**: 50,0 % of candidates in W36, 50,0 % in W37. Unchanged for a
  third week.
- **Buying after the move is complete**: W36 found NVDA at 1,0676 and PLTR at 1,055; W37
  found four cases including MU at **1,264**, a new high (#512).
- **Instruments failing silently**: W36's closing claim was that *"the measurement
  instruments failed silently three separate ways this week — during the exact window whose
  only product is measurement"*, and that four of six issues being instrument repairs was
  itself the finding. In W37 **all five** issues are instrument repairs, and the failure
  mode escalated from *wrong* to *absent*: two sessions produced no measurement at all.
- **Near-gate misses**: W36 had 0,019–0,040. W37's F at **0,001** on 09-08 is the narrowest
  in the series. Still mostly without money behind it — F is a downside mover on a long-only
  book.

**Changed.**

- **Zero-news improved and stabilised**: 50,8/96 mean in W36, **38,3/96 (39,9 %)** in W37 —
  the best three-session stretch of the observation window.
- **The permanent-blind-spot set is only half permanent** (§5, #511). W36's central claim
  needs narrowing; the structural reading survives for the persistent half.
- **The earnings calendar is fixed** (#507) — W36's first filed issue, confirmed working on
  two sessions with a real discrimination.
- **`NON_CLASSIFICATO` is repaired** (#509, closed 09-09), visible and working in both new
  dossiers.
- **Top-N saturation worsened materially**, 93,6 % → 98 %, and still costs nothing
  measurable (#400).

**New in W37 and absent from W36.** Everything in §4 — the cron losing sessions to quota,
the holiday duplicate run, the retro-adjusted rewrite of the frozen series, the alias gap in
the relevance classifier, and the missing exit-side funnel.

---

## 9. Reading of the week

**The pipeline did not fail this week. The apparatus that watches it did, twice, and the
evidence base now has a hole nobody was told about.** Two sessions in four are missing from
the pre-registered ledger; the economic scoreboard still reads day 26 of 40 four days after
day 26; `miss_cumulati` is frozen at the same five numbers in two consecutive dossiers. The
runs that died left a dossier behind, which is the only reason this review could be written
at all — and the dossier is exactly the artifact that #565 shows is not immutable.

**Where the money went is not where the instruments were pointed.** Two thirds of the week's
−355,38 $ intraday loss is passive — held positions moving, not decisions taken. On 09-10
eight of thirteen movers were held-and-falling, seven of them ran up to 24 cycles producing
nothing but `SKIP_THRESHOLD`, and every published funnel KPI that day ran on a denominator of
two. The entry side has four KPIs and the exit side has none, so the sessions the book
actually loses money in are the ones the measurement is quietest about.

**The one genuinely reachable miss of the week came from a known blind spot that had stopped
being blind.** IBM, +3,38 % on 09-09, zero news rows, **82,29 $** net accessible — more than
half the week's total reachable opportunity, from a symbol #511 lists and which *did* produce
news on other sessions of the same week. Membership in the blind set turns out to be neither
stable nor the right thing to track.

**And the measurement of coverage is itself miscalibrated in both directions at once.** #508
inflates it with content-mill articles; #566 deflates it by failing to recognise "Apple" as
Apple — 23 of 33 launch-day articles, on a day the tag was correct and the text unambiguous.
Both errors land in the same numerator, the net is unknown, and that numerator feeds the
NO_NEWS-dominance count the charter's first exit question is measured on.

**What the evidence does not support**, and is worth saying before the n=73 decision is
taken: that S4's −495,22 $ is now a verdict. It is a number produced by a window with three
missing sessions, computed from a series that has been shown to rewrite its own history, on
a book whose losses this week were two-thirds passive. #179's trigger has fired
mechanically; the conditions for answering it honestly have not.

---

*Generated in an autonomous weekly analysis session. Read-only with respect to the trading
system: no code changed, no orders placed, no workers started. Files written: this document
and the GitHub issues and comments listed above. This file is intentionally left untracked,
as `docs/WEEKLY_FINDINGS_2026-36.md` was.*
