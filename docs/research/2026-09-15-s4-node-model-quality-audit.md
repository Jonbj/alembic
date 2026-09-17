# S4 node-model quality audit — 2026-09-15

## Question and conclusion

Are the two local models sufficient for their assigned S4 role? **Yes, conditionally for
the bounded, gated candidate-extraction and adversarial-review workflow; no for autonomous
research conclusions or for accepting node-1 output without node 2 and deterministic gates.**

The evidence supports a deliberately narrow claim. Node 1 (`qwen3.8-27b-implementer`)
regularly produces useful, source-grounded candidate cards, but also overstates or mis-cites
materially often enough that it is not a reliable final arbiter. Node 2
(`qwen3.8-27b-reviewer`) demonstrably catches many of those defects and returns complete,
schema-valid reviews. This is a good fit for the contract's two-stage design. It is not an
accuracy validation of node 2: this audit has no independently labelled gold set.

## Scope and method

Read-only audit performed on 2026-09-15. I used only the primary local artifacts requested:

- [`NODE_CONTRACT.md`](s4-web-validation-2026-08-28/NODE_CONTRACT.md), which defines the
  restricted roles and stop rules;
- [`scripts/s4_cluster_literature.py`](../../scripts/s4_cluster_literature.py) and its
  coordinator tests, plus the read-only consolidator and its tests;
- protocol-v4 JSONL output in `s4-web-validation-2026-08-28/node-output/`; and
- the corresponding `source-cache` raw and extracted-text files.

I (1) inspected the enforcement code and its tests, (2) counted cards, candidate claims,
reviews, verdicts, retries and recovery events, (3) recomputed each cached source's raw SHA-256
against its cards and searched the extracted source text for each normalized evidence quote, and
(4) read a purposive sample of accepted claims and reviewer rejections. The test command was:

```text
uv run pytest tests/scripts/test_s4_cluster_literature.py tests/scripts/test_consolidate_s4_literature.py -q
```

Result: **19 passed**.

The measurements are a snapshot of append-only files while the pass remains active; later rows
can increase totals. Invalidated campaigns are not treated as current evidence.

## What the coordinator guarantees (and what it does not)

The coordinator supplies important protection that should not be attributed to either model:

- strict JSON schemas, fixed source/chunk identities, allowed hypothesis IDs and verdicts;
- coordinator-derived evidence quotes from a short line range, plus rejection ledger entries;
- exact complete node-2 coverage of each submitted claim ID; and
- persisted retry limits, split/recovery coverage proofs, source hashes and append-only output.

The tests exercise malformed JSON recovery, invalid claim-line rejection, persisted retry/split
recovery, node-2 completeness and invalidated-campaign exclusion. These tests passed. They prove
the intended mechanical controls, not semantic truth of a model judgement.

## Quantitative integrity checks

At the snapshot:

| Check | Result | Interpretation |
|---|---:|---|
| Node-1 card rows / proposed / accepted claims | 310 / 520 / 402 | 77.3% of proposed claims passed the deterministic gate; extraction is producing usable volume but needs that gate. |
| Node-1 rejected candidate claims | 118 (`INVALID_LINE_RANGE`) | 22.7% of proposed claims were rejected before review, entirely for invalid line ranges. |
| Empty node-1 cards | 117 | Empty output is being used rather than forcing a claim. |
| Node-2 review rows / unique claim IDs | 450 / 355 | Raw append-only history includes 95 duplicate IDs across runs/retries; the finalizer explicitly rejects duplicate reviews for one source representation. |
| Node-2 verdicts, all retained history | 327 supported; 88 overstated; 30 ambiguous; 5 not applicable | 123/450 (27.3%) are not accepted as supported: node 2 is materially discriminating rather than rubber-stamping. |
| Current valid consolidation | 292 unique claims, each reviewed: 213 supported; 54 overstated; 21 ambiguous; 4 not applicable | 79/292 (27.1%) current claims are not accepted as supported. 77 include a non-empty minimal correction. |
| Node-2 malformed/incomplete review fields | 0 empty `reason`; 0 empty `reason_codes` | Structural review quality is good in persisted rows. |
| Raw-source hashes checked | 292 claim records, 0 mismatches | For records whose raw/text cache pair is present, card provenance matches the frozen raw source. |
| Quote membership checked | 289/292 normalized quotes found; 3 not found | See the specific reproducibility caveat below. |
| Node-1 failed attempts / node-2 failed attempts | 182 / 0 | Node 1 has substantial format/line-reference reliability pressure; node 2 completed its persisted review calls. |
| Split / verified recovery events | 108 / 105 | Recovery is usually proven, but three split events had not yet acquired a verified recovery row in this active snapshot; the ledger also has one `CHUNK_FAILED`. |
| Source terminal events | 14 complete; 1 incomplete; 1 unavailable | The active pass is not yet a completed corpus-level result. |

There are 47 valid node-1 claims awaiting review (43 from `ACA003`, four from `ACA004`) and no
orphan review rows; that is ordinary in-flight backlog, not an integrity failure.

Four currently represented sources (`ACA001`–`ACA004`, 110 accepted candidate-claim records) have no
matching raw/text pair in this repository's `source-cache`, so their quote provenance could not
be independently recomputed here. This does not show that they are wrong; it limits this audit.

## Claim-level sample

| Record | Finding | What it says about the models |
|---|---|---|
| `ACA006-C10-01`, `SUPPORTED` | Node 1 reported the source's 3,623-SEO sample and the 0.064 vs 0.042 correlations; the quote contains both values and node 2 identified the numeric/context match. | A strong example of bounded extraction plus appropriate scope limitation. |
| `ACA006-C0-02`, `OVERSTATED` | Node 1 claimed Fin-Neg had stronger correlations than Harvard, but its quote only said the lists had significant relations. Node 2 identified `Quote_Mismatch` and supplied a narrower correction. | Direct evidence that the reviewer catches a material node-1 overclaim. |
| `ACA010-C3-01`, `AMBIGUOUS` | Node 1 asserted statistically significant three-day directional accuracy and model-to-score comparison; its quote contained metrics without headers or a significance test. Node 2 correctly requested the missing mapping/test. | Good detection of a subtle, quantitative support gap. |
| `ACA014-C2.1-02`, `NOT_APPLICABLE` | Node 1 asserted a mid-cap/non-monotonic momentum result, while its quote was only a page-number/transition fragment. Node 2 rejected it as insufficient/mismatched. | The gate does not prevent every semantic mismatch, but the second model caught this severe one. |
| `ACA006-C1-01`, `SUPPORTED` | The claim carefully presents a literature summary that linguistic content is useful in explaining returns, volatility or volume; the quote states that summary and the limitations say it is not the paper's primary result. | An acceptable use of a scoped, non-causal evidence card, but also a reminder that `SUPPORTED` means supported by the supplied excerpt—not independent replication. |

## Reproducibility and quality limitations

1. Three cache-text membership failures deserve follow-up: `ACA012-C1-01`,
   `ACA014-C2.1-02`, and `ACA014-C3-01`. Their raw-file hashes match the cards, but their
   recorded quote lacks the form-feed character present in the current extracted text. The contract
   requires byte-normalized membership. This is likely an extraction-normalization provenance
   mismatch, not evidence of invented source content, but it means the audit cannot call quote
   membership perfect. `ACA014-C2.1-02` was anyway rejected by node 2; `ACA012-C1-01` and
   `ACA014-C3-01` were marked supported and should be re-derived from the frozen text before
   relying on them.
2. The 182 node-1 failed attempts and 118 rejected candidates show that node 1 needs its retry,
   split and rejection machinery. It should never be used as a direct final-output model.
3. Node 2's rejection rate is encouraging but not a calibrated precision/recall estimate. It sees
   node-1's selected quote and context, not the whole source; both models are also in the same
   local Qwen workflow. A blinded, human-labelled stratified sample is still needed to quantify
   false approvals and false rejections.
4. The audit does not assess corpus completeness, the truth of the underlying papers, or whether
   any literature finding transfers to a live long-only Alembic strategy. The contract explicitly
   excludes those decisions.

## Operational recommendation

Continue the current two-node pass only under its existing contract: persist every candidate,
retain node-2 verdicts, and use only `SUPPORTED` records in the deterministic consolidation.
Before any final research conclusion, fix/re-run the three quote-provenance records above and
perform a small blinded human audit stratified by node-2 verdict (especially `SUPPORTED` versus
`OVERSTATED`). Do not simplify this into a node-1-only workflow or treat node-2 `SUPPORTED` as
an approval for strategy deployment.
