# Second-order/spillover news characterization — design spec

Part of #21. Closes the residual scope of #408 after the Variant A prompt fix
(#399/#408, `bf5bef2e`, 2026-09-01) shipped in deroga. The operator's comment on
#408 (2026-09-01T10:35Z) explicitly scoped what remains:

> "Il funnel actionability v2 e la classificazione 'secondo ordine' come
> categoria a sé (punto 1 della tua investigation) restano da fare — non
> deployati qui, solo il fix del prompt sottostante."

This spec covers point 1 only: **characterise the class** — add an
independent label for "second-order/spillover" articles, count how often it
occurs, and measure its realised forward return. It is a measurement ticket.
It changes no gate, threshold, prompt, or config, and is `freeze-ok` under
`OBSERVATION_CHARTER.md`.

## Why an independent detector, not the LLM's own `directness` field

`llm_responses.directness` (`direct|customer_supplier|competitor_readthrough|
sector|macro|unclear`) is already persisted for every scored article and was
used in the 2026-09-01 research to measure the ~2.2x magnitude gap / ~5-6x
gate-pass gap that justified Variant A. Reusing it again here to "characterise
the class" would be circular: it is the model's own self-assessment of
exactly the thing being independently validated. This spec instead builds a
deterministic, rule-based detector that does not depend on the LLM's output,
so it can also serve as an outside check on how well `directness` tracks
reality (reported as a bonus cross-tab, not a primary deliverable).

## Detector

New pure module: `src/analysis/second_order_news.py`.

For a `news_log` row `(ticker, title)`:

1. Look up the tagged ticker's own company name + aliases from
   `ticker_lookup` (`company_name`, `aliases[]`, keyed by `ticker`).
2. **Self-reference check**: the headline must mention the ticker's own
   company (name, an alias, or a `"$TICKER"`/word-boundary ticker mention).
   This is what keeps the detector from overlapping with #405's fan-out /
   wrong-ticker-tag bug — e.g. "Why Is Mastercard Stock Surging?" mistagged
   onto `V` mentions no Visa entity at all, so it is correctly *not* flagged
   here (it belongs to #405, a different failure mode: wrong ticker, not
   under-scored magnitude on a correctly-tagged spillover).
3. **Causal connector check**: the headline must contain one of a short,
   precision-biased connector list (case-insensitive, word-boundary):
   `following`, `after`, `on the back of`, `amid`, `on news of`, `thanks to`,
   `as a result of`. Deliberately excludes bare `as`/`on`, which are too
   common and would blow out false positives.
4. **Third-party check**: in the headline text following the matched
   connector, a *different* company's name/alias from `ticker_lookup` must
   appear (i.e. not the ticker's own company from step 1).
5. If 2-4 all hold → classify `second_order`, recording the matched
   connector and the matched third-party ticker/company. Otherwise, the
   article is left unclassified by this detector (it makes no claim that
   unclassified articles are "direct" — it is a precision-biased, lower-bound
   classifier by design: false positives are more costly here than false
   negatives, since we want confidence in what gets counted).

Sanity-checked against real `news_log` rows before writing this spec:
correctly flags all four seed headlines from #408 (ADBE/Salesforce,
AVGO/NVIDIA, INTC/Nvidia, NOW/Salesforce — all via the `following` connector)
and correctly stays silent on the MA/V "Why Is Mastercard Stock Surging?"
and HOOD headlines from the 08-24/08-25 reports (no self-reference or no
connector), which are fan-out/other-cause cases, not this pattern.

## Data sourcing — no migration, no schema change

- `news_log`: 9,270 rows live, 2026-06-15 → 2026-09-03. Full history, no
  retention concern for this window.
- `sentiment_signals`: already carries `forward_return`, `forward_return_3d`,
  `forward_return_5d` per `news_log_id` (94-97% populated across ~9,750
  rows). Reused directly — no need to re-fetch bars from Alpaca.
- `llm_responses.directness`: joined via `sentiment_signals.id = 
  llm_responses.signal_id`, for the bonus agreement cross-tab.

Everything is read-only against existing tables. No new table, no migration,
nothing added to the money path or the money-path-adjacent tables the freeze
protects.

## Script

`scripts/characterize_second_order_news.py`:

1. Load all `news_log` rows (ticker, title, id, fetched_at) in range.
2. Load `ticker_lookup` once (company_name, aliases, ticker) for the
   self-reference / third-party checks.
3. Run the detector per row.
4. For rows classified `second_order`, join to `sentiment_signals` (via
   `news_log_id`) for forward returns, and to `llm_responses` (via
   `signal_id`) for `directness`.
5. Compute and emit:
   - occurrence count and rate (`second_order` rows / total rows with a
     tagged ticker present in `ticker_lookup`),
   - realised forward-return distribution (`forward_return`,
     `forward_return_3d`, `forward_return_5d`: mean, median, n) for
     `second_order` rows vs. all other rows, as a comparison, not a causal
     claim,
   - agreement rate: of the `second_order`-flagged rows that have an
     `llm_responses.directness` value, what fraction the model itself
     labeled `competitor_readthrough` or `sector` (its own two "spillover"
     buckets) vs. `direct`/other.
6. Write `docs/evidence/second_order_news.json` (following the existing
   `docs/evidence/*.json` shape: a top-level object with a `generated_at`,
   the window covered, and the aggregates above) plus a short Italian
   summary paragraph in the same file, mirroring how prior measurement
   tickets (#430, #433) reported results.

Idempotent, offline-computable, no side effects beyond writing the one
evidence file. Runnable inside the worker container the same way
`compute_label_forward_returns.py` is (`docker compose exec worker python
scripts/characterize_second_order_news.py`).

## Tests (TDD)

Unit tests for the detector (`tests/analysis/test_second_order_news.py` or
matching existing test layout):

- Positive: the four seed headlines from #408, each classified
  `second_order` with the correct connector and third-party ticker.
- Negative — no connector: e.g. "Why Is Mastercard Stock Surging on
  Monday?" tagged `MA` (own company, no connector) → unclassified.
- Negative — no self-reference: the same headline tagged `V` (fan-out
  mistag, #405 territory) → unclassified.
- Negative — connector present but no third-party match: "Visa Stock Climbs
  After Trump Buys Millions in Stock" tagged `V` → unclassified (no company
  name from `ticker_lookup` follows the connector).
- Negative — connector present, only the *own* company matches after it
  (e.g. "Salesforce stock rises following Salesforce's own earnings beat")
  → unclassified (third-party match must differ from the ticker's own
  company).

Script-level test: a small fixture DB (or mocked query layer, matching how
other `scripts/*.py` in this repo are tested) verifying the aggregation and
evidence-JSON shape end to end on a handful of rows.

## Out of scope

- Any change to the sentiment prompt, gate, threshold, or `directness`
  schema itself (already done in #399/#408 Variant A).
- Verifying whether Variant A's deployed effect matches the pre-deploy
  projection — that is #453, a separate ticket with its own acceptance
  criteria, not duplicated here.
- The "funnel actionability v2" half of the operator's comment — not part
  of this ticket's literal point 1, left for a separate issue if wanted.
- Persisting the classification back into any live table read by the
  trading pipeline (would be a live schema change, out of scope for a
  measurement ticket and unnecessary for the stated goal).
