# Vettore A — Earnings Event Chain: Handoff Brief (spec-level)

**Status:** requirements + assumptions locked; NO implementation plan yet — the first
task of the implementing agent is a bounded discovery on FMP, then writing the plan
with the superpowers:writing-plans skill. This is deliberately NOT a fake-precise TDD
plan: FMP response schemas must be probed before exact code can be honest.

**Why this vector:** measured 2026-07-12 — the current S4 (editorial-news sentiment,
large-cap) has IC ≈ 0.01, hit-rate 51.8%, negative avg forward return on tradeable
scores (≥0.30), and −$788 all-time over 237 trades. Latency is NOT the problem
(median 1.1h news→score): the *content* is already priced. The designed cure
(`docs/ROADMAP_DATA_ALPHA_2026-07-02.md` §4, Vettore A) is switching the input from
editorial news to the primary earnings event chain: calendar → deterministic surprise
→ transcript tone — data that is fresh, ticker-certain, and semi-structured (where an
LLM has a real comparative advantage). It also unlocks S7 PEAD ("S7 produce zero per
dati mancanti: consensus non wired").

## Assumptions adopted (revocable by the PO — flag if you disagree)

- **A1 — Provider: FMP one-stop** (roadmap open decision #2). Already used
  successfully for the ALPHA-A5 backtest (`reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md`);
  `FMP_API_KEY` is already present in the container env.
- **A2 — Universe: unchanged large-cap watchlist for S4 enrichment** (open decision #1
  concerns S7's PEAD edge on small/mid — separate decision, NOT blocked by this work).
- **A3 — Gates: the pre-registered ALPHA-A3 transcript-tone gate applies** (see
  `1007b13` s7-poc: POC-2c tone IC analysis + pre-registered gate). No new alpha goes
  live un-gated; QX-01 discipline (CLAUDE.md) stays in force.

## What exists already (do NOT rebuild)

- `src/connectors/earnings_calendar.py` — `EarningsCalendarProvider` (Finnhub
  calendar) feeding the `earnings-pead` worker; **consensus is NOT wired** (the known
  gap that zeroes S7).
- `src/workers/earnings_pead_worker.py` + `pead_signals` table + S7 strategy code
  (shelved, `strategy_lifecycle.mode=research`).
- S7 POC transcript tooling: `scripts/score_s7_transcripts.py` (POC-2b, DK-CoT tone
  scoring, resumable) and the POC-2c IC analysis — reuse the prompt + caching pattern.
- Sentiment pipeline plumbing (sanitizer, budget tracker, Redis/PG stores, decision
  log) — the event chain rides the same offline-worker architecture (CLAUDE.md: no
  LLM in the hot path).

## Deliverables for the implementing agent

**Phase 0 — Discovery (bounded: ≤ half a day, read-only, no live changes):**
1. Probe FMP with the existing key (inside `alembic-worker-1`): earnings calendar,
   analyst estimates (consensus EPS), transcripts endpoints for 5 watchlist symbols.
   Record: exact endpoints, response schemas, rate limits, historical depth, cost tier.
2. Verify the consensus gap: where `earnings_pead_worker` expects consensus and what
   shape it needs.
3. Output: a short discovery report appended to this file (schemas + gaps + any
   assumption invalidated).

**Phase 1 — Deterministic surprise (no LLM):** FMP consensus wired into the earnings
worker → `surprise_pct = (actual − consensus)/|consensus|` computed deterministically
at event time; stored on `pead_signals`. Acceptance: for the last 4 earnings weeks of
the watchlist, ≥90% of events have consensus + actual + surprise populated within 1h
of the report.

**Phase 2 — Transcript tone as S4 input:** on earnings day, transcript (or press
release when transcript lags) scored with the POC-2b DK-CoT tone prompt by the live
ensemble pair, producing a NORMAL `sentiment_signals` row (source-tagged) — so it
flows through the existing gate/ranker/decision-log unchanged, and IC is measurable
with the multi-horizon forward returns from the measurement-foundation plan.
Acceptance: event-sourced signals distinguishable via `news_log.source`, IC
computable separately per source.

**Phase 3 — Gate evaluation:** after ≥4 weeks of event-sourced signals: IC(event
signals) vs IC(editorial signals) with the pre-registered thresholds. PASS → PO
decision on rebalancing S4's input mix / sleeve; FAIL → document and stop (no
tuning-until-it-passes).

## Hard constraints

- Ingestion offline → worker → PG/Redis → execution reads (CLAUDE.md non-negotiable).
- Every phase behind its own branch + review; nothing merges without the acceptance
  criteria met; no config/allocation changes anywhere in this work.
- Budget: transcript scoring only on event days (~5-15/day on the watchlist in
  earnings season) — estimate and report cost in Phase 0.

## Kickoff prompt (for a fresh agent — model: claude-sonnet-5 for Phases 1-2; use a
stronger model or ask for review if Phase 0 discovery contradicts this brief)

```
You are working in /home/stefano/Documents/Projects/Alembic (LLM trading system,
paper trading). Read CLAUDE.md, then
docs/superpowers/plans/2026-07-12-vettore-a-earnings-chain-brief.md (this file),
then docs/ROADMAP_DATA_ALPHA_2026-07-02.md §4 (Vettore A).

Execute Phase 0 (bounded discovery, read-only) exactly as described in the brief,
append the discovery report to the brief file, and STOP for review. Do not start
Phase 1 until the discovery report is approved. After approval, use the
superpowers:writing-plans skill to produce a full TDD plan for Phase 1 only, and
execute it with superpowers:subagent-driven-development on branch
vettore-a-phase1-<date>. Never touch main, config files, or the live DB.
```
