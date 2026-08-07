# Research: the "Ralph" autonomous-agentic-coding technique — applicability to Alembic's open backlog

**Date:** 2026-07-23
**Scope:** primary-source research on "Ralph" / "Ralph Wiggum as a Software Engineer" (Geoffrey Huntley), cross-referenced against Alembic's live GitHub issue backlog (map issue [#21](https://github.com/Jonbj/alembic/issues/21) + open children, pulled live via `gh` on 2026-07-23) and the non-negotiable constraints in `CLAUDE.md`.
**Not in scope:** no code changes, no issue edits, no new backtests. This is a research note, not a tracker — roadmap status remains GitHub issue #21 per `docs/agents/wayfinder-roadmap-method.md`.
**Method:** every claim about Ralph is tagged either "source states" (direct claim from a primary source, quoted or closely paraphrased) or "inference" (this document's own reasoning). Every non-obvious claim carries a citation URL. Backlog facts in Part 2 come from live `gh issue list`/`gh issue view` output, not from memory or the audit docs.

## Executive verdict

**No — Ralph cannot take over Alembic's issue backlog wholesale, and the sources' own stated scope already rules this out before Alembic-specific risk is even considered.** Ralph's primary documentation explicitly scopes itself to greenfield, single-topic, acceptance-test-bearing specs with a human "sitting on the loop, not in it" ([`github.com/ghuntley/how-to-ralph-wiggum`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)) — not to judgment calls, and the author states plainly: "There's no way in heck would I use Ralph in an existing code base" ([ghuntley.com/ralph/](https://ghuntley.com/ralph/)). Alembic is a live paper-trading brownfield system with a real incident history of subtle correctness bugs in exactly the risk-adjacent code (kill-switch, BUY/SELL guard asymmetry, signal_id↔score desync) that a loop optimized for velocity-over-review is least suited to touch unsupervised.

That said, the backlog is not monolithic. Of 50 open issues pulled live, a genuine subset — mostly Tier 2 greenfield mobile-app slices and a handful of narrowly-scoped, already-acceptance-criteria-bearing Tier 4 bug fixes — matches Ralph's own stated sweet spot closely enough to justify a **small, bounded trial**, never a wholesale handover. See Part 4 for the category-by-category breakdown and Part 5 for the scoped recommendation and guardrails.

---

## Part 1 — What Ralph actually is

### 1.1 The loop, verbatim

The primary source states the mechanism in its "purest form" as a single bash line:

```bash
while :; do cat PROMPT.md | claude-code ; done
```

"Ralph is a technique. In its purest form, Ralph is a Bash loop." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)

Each iteration re-invokes the coding CLI against a fixed prompt file, with **no shared context** between iterations except what has been written back to disk. The companion workshop repository (same author) restates this more operationally: "The bash loop runs → feeds `PROMPT.md` to claude; Agent completes one task → updates `IMPLEMENTATION_PLAN.md` on disk, commits, exits; Bash loop restarts immediately → fresh context window." — [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)

### 1.2 What files it reads/writes, and their role

Two file-naming schemes appear across the primary sources — the original `ghuntley.com/ralph/` post (2025) and the later companion workshop repo (source states it is "an improved" iteration). Both describe the same functional roles; this document treats the workshop repo's names as the current, refined version.

| Role | Original post naming | Workshop-repo naming | Function (source states) |
|---|---|---|---|
| The fixed instruction fed every loop | `PROMPT.md` | `PROMPT.md` (two variants: `PROMPT_plan.md`, `PROMPT_build.md`) | Instructs "one task" per loop, "commit when tests pass" |
| The living TODO list | `@fix_plan.md` | `IMPLEMENTATION_PLAN.md` | "Prioritized bullet-point list of tasks derived from gap analysis (specs vs code)... persists on disk between iterations and acts as shared state between otherwise isolated loop executions" |
| Operational memory | `@AGENT.md` | `AGENTS.md` | "Single, canonical 'heart of the loop'... concise, operational 'how to run/build' guide," deliberately kept to ~60 lines; "Status, progress, and planning belong in `IMPLEMENTATION_PLAN.md`, not here" |
| Source of truth for requirements | `@specs/*` | `specs/*` | "One markdown file per topic of concern... the source of truth for what should be built" |
| Standard-library reference | `specs/stdlib/*` | (same) | Consulted before implementation to avoid re-deriving known patterns |

Sources: [ghuntley.com/ralph/](https://ghuntley.com/ralph/), [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md).

The workshop repo adds an explicit **spec-scoping discipline** not stated in the original post: a spec must pass a "can you describe the topic of concern in one sentence without conjoining unrelated capabilities?" test — its own worked example of a *failing* spec is "the user system handles authentication, profiles, and billing → 3 topics." — [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md). This is directly relevant to Alembic's Tier 5 backlog buckets (Part 4).

### 1.3 What "statelessness" buys you (source's claim)

The source frames the fresh-context-per-loop design as a direct countermeasure to context degradation, not an incidental property: "The more you use the context window, the worse the outcomes you'll get." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/). The companion "how to build a coding agent" post generalizes this into a quantified claim: for a 200K-token-advertised model, "~176K [is] truly usable," and the "smart zone" is "40-60% context utilization" — the stated goal of one-task-per-loop is to keep each loop's context inside that zone rather than accumulating history. — [ghuntley.com/agent/](https://ghuntley.com/agent/)

Persistent state is deliberately relocated from the model's context to disk/git: "progress persist[s] in files and git history rather than in the LLM's context window" (workshop repo framing). The tradeoff this buys, per the source: determinism of *setup* ("deterministically allocate the stack the same way every loop") in exchange for non-determinism of *execution* — "That's the beauty of Ralph — the technique is deterministically bad in an undeterministic world." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)

### 1.4 Two operating modes (workshop repo, refines the original post)

| Mode | Prompt file | Behavior (source states) |
|---|---|---|
| PLANNING | `PROMPT_plan.md` | "Generate/update `IMPLEMENTATION_PLAN.md` only... no implementation, no commits" (gap analysis between specs and code) |
| BUILDING | `PROMPT_build.md` | "Assumes plan exists, picks tasks from it, implements, runs tests (backpressure), commits" |

Source: [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md). This mode split does not appear explicitly in the original 2025 post, which describes the plan/build distinction more loosely; treat it as the technique's later refinement by the same author, not a claim about the original post's exact mechanics.

---

## Part 2 — Origin, requirements, cost/hardware, failure modes (as stated by the sources)

### 2.1 Stated prerequisites / assumptions

- **Tool must not cap calls:** "Ralph can be done with any tool that does not cap tool calls and usage." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)
- **Senior engineer must design the harness:** "There is no way this is possible without senior expertise guiding Ralph." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/). The workshop repo restates the operator's role sharply: "You need to get out of his way... Your job is now to sit on the loop, not in it — to engineer the setup and environment that will allow Ralph to succeed." — [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)
- **Strong type system / static analysis as backpressure:** "I wanted extreme correctness, which meant using Rust," and for dynamic languages "I must stress the importance of wiring in a static analyser/type checker." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/). Backpressure in general is the mechanism that gates a commit: "tests/build failures force the agent to fix issues before committing." — [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)
- **Sandboxing is a stated requirement, not an option:** "Running without a sandbox exposes credentials, browser cookies, SSH keys, and access tokens on your machine. Run in isolated environments with minimum viable access." — [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)

### 2.2 Cost / hardware figures actually stated

The primary sources give very sparse, non-generalizable cost data:

- A single anecdote: "Cost of a $50k USD contract, delivered, MVP, tested + reviewed with @ampcode. $297 USD." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/). No breakdown of API token spend, wall-clock time, or iteration count accompanies this figure.
- A later post gives a rate, not a total: "the cost of software development is $10.42 an hour" (2026-02-27). — [ghuntley.com/real/](https://ghuntley.com/real/). This post gives no hardware detail and — notably — the source itself does not substantiate the figure with a methodology; treat it as a rhetorical claim, not a cost model.
- **No hardware requirements are stated anywhere in the four Huntley posts fetched for this research.** Ralph as described runs against a cloud-hosted coding-CLI backend (Claude Code / Amp), not local inference — there is no GPU/local-model sizing discussion in any of these posts. (Inference: this is consistent with Alembic's own architecture, where the Ollama Cloud ensemble is likewise not local inference — see `CLAUDE.md` Tech Stack — but that parallel is superficial; Ralph's cost model and Alembic's LLM-cost model are unrelated.)

**Conclusion on cost (inference):** the sources do not supply a reusable cost model. The one concrete multi-hundred-dollar figure is a single anecdote for an unspecified greenfield MVP scope, with no per-iteration API spend disclosed. Any cost projection for an Alembic trial would have to be measured empirically, not inferred from these numbers.

### 2.3 Known failure modes (stated by the sources)

| Failure mode | Source's description | Source's stated mitigation |
|---|---|---|
| Non-deterministic false negatives in search | "code-based search can be non-deterministic"; the agent can assume code is unimplemented when it already exists | Explicit prompt instruction: "don't assume an item is not implemented" |
| Placeholder / stub implementations | "Claude has the inherent bias to do minimal and placeholder implementations" | Explicit prohibition in the prompt: "DO NOT IMPLEMENT PLACEHOLDER OR SIMPLE IMPLEMENTATIONS" |
| Broken/non-compiling codebase after an unattended run | "you'll wake up to a broken codebase that doesn't compile" | Manual intervention: reset and re-loop, or a hand-crafted "rescue prompt" |
| Context exhaustion on large error output | A large compiler-error list fills the context window before the fix can complete | Offload the diagnosis to a different model with more headroom (author used Gemini) |
| Duplicate/redundant implementations | The LLM re-implements a function that already exists elsewhere in the codebase | Tighten search discipline and require documentation of what already exists |
| Going in circles / ignoring instructions | Stated plainly as expected, not exceptional, behavior: "Ralph can go in circles, ignore instructions, or take wrong directions — this is expected and part of the tuning process." | Regenerate the plan; the author states he has "deleted the TODO list multiple times" |
| Intent/scope drift over many loops | Raised independently in third-party discussion of the technique (not the original post) — see Part 3.2 | Not resolved in the sources reviewed; flagged by a practitioner as "probably the next thing to solve" |

Sources: [ghuntley.com/ralph/](https://ghuntley.com/ralph/), [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md).

---

## Part 3 — Where the sources say it's a good fit / bad fit

### 3.1 Stated fit (Huntley's own posts)

**Good fit, stated explicitly:**
- "This works best as a technique for bootstrapping Greenfield, with the expectation you'll get 90% done with it." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)
- Projects where an approximate-90%-done outcome is acceptable, and cost/time optimization is prioritized over long-term human maintainability (inference, drawn from the "greenfield" quote plus the cost-anecdote framing).
- Case study: **CURSED**, a new programming language the author built with Ralph, including a compiler that can "generate code in a language not in Claude's training data" — the author frames the result honestly as "under baked, baked, or baked with unspecified latent behaviours" at time of writing, not a finished product. — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)
- A third-party case study cited in the same post: a Y Combinator hackathon team "shipped 6 repos overnight" using a Ralph-style loop ([`repomirror.md`](https://github.com/repomirrorhq/repomirror/blob/main/repomirror.md), referenced from [ghuntley.com/ralph/](https://ghuntley.com/ralph/)) — again a greenfield, throwaway/prototype context, not a brownfield production system.

**Bad fit, stated explicitly:**
- "There's no way in heck would I use Ralph in an existing code base." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/). This is the single most direct, unambiguous scope-limiting statement in the primary source, and Alembic is unambiguously an existing (brownfield, live paper-trading) codebase.
- The author explicitly rejects the framing that the technique removes the need for engineering judgment: "Anyone claiming that engineers are no longer required and a tool can do 100% of the work without an engineer is peddling horseshit." — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)
- The companion "everything is a loop" post separately warns against reaching for multi-agent complexity when it isn't needed: "At this stage, it's not needed. Consider microservices and all the complexities that come with them." — [ghuntley.com/loop/](https://ghuntley.com/loop/). This is an argument for scope discipline generally, reinforcing the single-topic-spec requirement (§1.2), rather than a direct brownfield/greenfield statement.
- The workshop repo's spec-scoping rule doubles as an implicit "bad fit" signal: any request that cannot be reduced to a single-sentence, non-conjoined topic is, by the technique's own admission, not yet Ralph-ready material — it needs to be decomposed by a human first. — [`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)

### 3.2 Third-party adaptation and critique (substantive, adds information beyond Huntley's own posts)

- **`mikeyobrien/ralph-orchestrator`** — an open-source, MIT-licensed re-implementation ("an improved implementation of the Ralph Wiggum technique for autonomous AI agent orchestration," >1,000 GitHub stars at time of research) that generalizes the loop across multiple coding-CLI backends (Claude Code, Gemini CLI, Codex, Amp, Copilot CLI, etc.) and adds a human-in-the-loop channel: "Agents can ask questions and block until answered; humans can send proactive guidance at any time," plus "Gates that reject incomplete work (tests, lint, typecheck)." — [`github.com/mikeyobrien/ralph-orchestrator/README.md`](https://github.com/mikeyobrien/ralph-orchestrator/blob/main/README.md). Notably, this README **does not itself state any explicit exclusion list of unsuitable codebases or tasks** — the safety posture is entirely delegated to whatever gates the operator configures, and the only loop-termination control documented is "Ralph iterates until it outputs `LOOP_COMPLETE` or hits the iteration limit," with the limit's default left unspecified in the README. This is a real information gap in the wild: a popular third-party implementation gives no built-in warning against brownfield/risk-adjacent use — the burden is entirely on the human harness-builder to reintroduce the caution the original author states in prose.
- **Hacker News discussion, "Continuous agents and what happens after Ralph Wiggum?"** ([news.ycombinator.com/item?id=46632445](https://news.ycombinator.com/item?id=46632445)) — the two substantive technical concerns raised (as opposed to hype commentary, which was excluded per this research's scope) were: (1) a direct question about whether autonomously-generated authentication code had passed any security testing, met only with a reactive "it can often easily find its own bugs when prompted to do so" rather than a proactive security-assurance answer; and (2) an acknowledged, unresolved failure mode of "intent drift" over long unattended runs, which the responding practitioner called "probably the next thing to solve" rather than a solved problem. Both concerns are directly relevant to Alembic: security-and-correctness-critical code (auth in the HN example; order execution/risk gating in Alembic's case) is exactly where "let it find its own bugs" is the weakest guarantee, and intent drift over many loops is a bad match for narrowly-scoped, invariant-preserving fixes.
- **DreamHost, "The Ralph Wiggum Loop, from First Principles"** ([dreamhost.com/blog/ralph-wiggum/](https://www.dreamhost.com/blog/ralph-wiggum/)) — secondary source, and this research's own fetch assessed it as "predominantly a summary of Geoffrey Huntley's original work with limited independent critique," so it is cited only for one operationally useful, non-redundant point: it explicitly names exploratory/under-specified work as unsuitable — "exploratory work, because if you don't have clear acceptance tests, you'll just get a chaotic loop that invents things you didn't ask for" — and recommends hard iteration/time limits as a bare-minimum guardrail ("Enforce iteration limits and time limits so the loop can't run forever and burn through your token budget"). Flagged here as secondary/lower-trust, included because it is a concrete, checkable operational claim rather than hype.

### 3.3 Synthesis of "good fit / bad fit" purely from the sources

| Dimension | Good fit (source-stated) | Bad fit (source-stated) |
|---|---|---|
| Codebase state | Greenfield, new project | Existing/brownfield ("no way in heck") |
| Spec quality | Single-topic, one-sentence-describable, acceptance-test-bearing | Multi-topic, exploratory, no clear acceptance test (chaotic loop) |
| Correctness bar | "~90% done" is an acceptable outcome | Zero-tolerance / security-critical correctness needs (HN critique: no proactive security assurance) |
| Judgment required | None beyond harness design ("engineer the setup," not the code) | Domain judgment, security sign-off, or genuine decision-making |
| Backpressure available | Strong typed/static-analysis backpressure exists | Backpressure weak or absent (dynamic language, no gates) |
| Operator posture | Human "sits on the loop, not in it," reviews commits after the fact | Any workflow that needs the human inside the loop making calls mid-task |

---

## Part 4 — Ground truth on Alembic's open backlog (2026-07-23, live)

### 4.1 Headline counts

Pulled via `gh issue list --state open --limit 200 --json number,title,labels` in this repo, 2026-07-23. **50 open issues total**, including the map issue #21 itself and two pre-Wayfinder legacy issues (#12, #17) that were never imported into the tier system.

| Tier | Count (open) | Notes |
|---|---|---|
| tier0 | 2 | systemic blockers (QX-01 golden label set + its migration prereq) |
| tier1 | 8 | code ready, flag-off (shadow evidence collection + flip decisions) |
| tier2 | 11 | plan written, not executed |
| tier3 | 4 | PO decisions pending (`wayfinder:decision`, all `ready-for-human`) |
| tier4 | 12 | pre-live hardening |
| tier5 | 3 | backlog buckets, `needs-triage` |
| no tier label | 10 | 7 are the new mobile/Android slices (#92–#99, tiered outside the original audit-derived scheme), 1 is the map itself, 2 are legacy (#12, #17) |

| Wayfinder type | Count |
|---|---|
| `wayfinder:task` | 37 |
| `wayfinder:decision` | 6 |
| `wayfinder:backlog` | 4 |
| `wayfinder:map` | 1 |
| none | 2 (legacy #12, #17) |

| Triage label | Count |
|---|---|
| `ready-for-agent` | 25 |
| `ready-for-human` | 9 |
| `needs-triage` | 4 |
| none | 12 |

Source: live `gh` pull, 2026-07-23 (raw JSON retained in this session's scratch working set, not committed to the repo).

### 4.2 How issues are actually specified in practice — sampled bodies

Body quality varies sharply and correlates with tier/type more than with the triage label alone:

- **Fully spec'd, acceptance-criteria-bearing (the Ralph-friendly shape):** [#93](https://github.com/Jonbj/alembic/issues/93) ("Mobile monitor: coherent snapshot, performance, positions, and events read API") and [#95](https://github.com/Jonbj/alembic/issues/95) ("Android monitor: Compose scaffold...") both carry a `## What to build`, a link to an approved design doc, an explicit `## Acceptance criteria` checklist (5-6 concrete, testable bullets), and a `## Blocked by` list of native GitHub issue dependencies. [#84](https://github.com/Jonbj/alembic/issues/84) (S3 design-alignment POC) similarly carries `## Problem Statement`, `## Solution`, and numbered `## User Stories`. These three read like the single-topic specs Ralph's own workshop repo asks for.
- **Thin, audit-pointer-only (not yet Ralph-ready by the source's own bar):** most Tier 4 pre-live-hardening issues are one- or two-line stubs that only point at an external doc, e.g. [#42](https://github.com/Jonbj/alembic/issues/42) ("B3: kill-switch resume non ripristina mode") — full body: *"Part of #21. **Tier 4 — pre-live blocker.** Audit ref: Tier 4 B3."* — and [#45](https://github.com/Jonbj/alembic/issues/45) ("B13/14/18: coerenza numeri risk") in the same shape. Neither carries acceptance criteria, a described root cause, or a solution sketch. Consistent with this, **8 of the 12 open Tier 4 issues have no triage label at all** (not `ready-for-agent`) — the backlog's own state agrees these are not yet fed for an agent, human or otherwise.
- **Deliberately vague grab-bags (`wayfinder:backlog`, `needs-triage`):** [#51](https://github.com/Jonbj/alembic/issues/51), [#52](https://github.com/Jonbj/alembic/issues/52), [#53](https://github.com/Jonbj/alembic/issues/53) each bundle several unrelated workstreams in one issue body (e.g. #51: "ALPHA-B0 SEC EDGAR ticker bug... ALPHA-B/C/D/E/G vectors... QT-02... QS-04/05/08... EN-04... EN-07"). These fail Ralph's own single-topic spec test on their face — they are exactly the "conjoined unrelated capabilities" example the workshop repo warns against (§1.2) — and the repo's own labeling agrees (`needs-triage`, not `ready-for-agent`).
- **`wayfinder:decision` issues are structurally different, not just harder tasks:** [#22](https://github.com/Jonbj/alembic/issues/22) ("PO-1: Universo small/mid vs large-cap") reads *"**Tipo:** decisione PO — APERTA... Decidere: universe = US large-cap only, oppure includere small/mid-cap."* There is no code deliverable described at all — the issue's entire content is a question requiring a product-owner judgment call with downstream strategic consequences (risk model, resolver scope). The same shape holds for [#83](https://github.com/Jonbj/alembic/issues/83) and [#85](https://github.com/Jonbj/alembic/issues/85), both explicit "PO decision: flip `<flag>` once shadow evidence accumulates" tickets that are, as of this research, still blocked on insufficient shadow-evidence sample size (n=1-2) rather than on any code work.
- **A revealing edge case — risk-adjacent bugs already labeled `ready-for-agent` in current practice:** [#107](https://github.com/Jonbj/alembic/issues/107) (drawdown miscalculation risking a spurious CRITICAL alert), [#110](https://github.com/Jonbj/alembic/issues/110) (S4/S1 re-buying a symbol on a weak fallback signal that contradicts the ensemble reversal that just sold it), [#111](https://github.com/Jonbj/alembic/issues/111) (single-model sentiment reads mislabeled as full-ensemble, bypassing reliability guards — 49% of a 7-day sample was FinBERT fallback, 34% was silently single-model), and [#113](https://github.com/Jonbj/alembic/issues/113) (fractional protective-stop sync failing to create a stop for `held_for_orders` shares) are **all four currently tagged `ready-for-agent`** in the live tracker, despite sitting squarely inside `CLAUDE.md`'s non-negotiable categories (guardrail fallback behavior, ensemble reliability gating, stop-loss protection) and inside this system's own documented incident history (the BUY/SELL asymmetric guard and the signal_id↔score desync noted in the task background are the direct ancestors of #110/#111). **This is a finding, not an assumption**: Alembic's own triage practice does not currently use "touches risk-adjacent code" as a triage-label signal — `ready-for-agent` here means "fully specified for a human-supervised AFK coding session with PR review," per `docs/agents/triage-labels.md`, not "safe for an unattended Ralph-style loop that commits without per-task human review." Treating the label as a green light for an unsupervised loop would be a misreading of what the label was designed to certify.

### 4.3 The intended human/agent workflow around these labels

Per `docs/agents/wayfinder-roadmap-method.md` and `docs/agents/triage-labels.md`: `ready-for-agent` means "fully specified, ready for an AFK agent" — i.e., a single autonomous **session** that claims the issue (`gh issue edit <n> --add-assignee @me`), does the work, and closes it via a merged PR with `closes #N`. This already implies a PR review gate before merge — nothing in the documented workflow describes direct-to-main commits from an agent. `ready-for-human` explicitly means "requires human implementation" — the method doc is blunt about the correct response to seeing this label: **"NON lavorarla — prepara il contesto e fermati"** ("do NOT work it — prepare context and stop"). `needs-triage` means a maintainer has not yet evaluated the issue at all. Frontier selection (`docs/agents/issue-tracker.md`) is explicitly "open children without an open blocker and without an assignee, in scaletta order" — i.e., even within `ready-for-agent`, the intended workflow is one claimed issue at a time with human-reviewable PRs, not a standing unattended loop consuming the whole frontier.

---

## Part 5 — Mapping Ralph-suitability to Alembic's actual issue categories

This section applies the sources' *own* stated fit criteria (Part 3.3) — not general risk vibes — to the backlog categories actually found in Part 4, then separately overlays `CLAUDE.md`'s non-negotiable constraints and the incident history named in this task's background, since those are Alembic-specific facts the Ralph sources have no opinion on.

| Category (from live backlog) | Example issues | Fit against Ralph's *own* stated criteria | CLAUDE.md / incident-history overlay | Verdict |
|---|---|---|---|---|
| Tier 2 mobile/Android greenfield slices | #93, #95, #96, #97, #98, #99 | Strong match: new subsystem (Android app / mobile read API), single-topic specs with acceptance-criteria checklists and native `Blocked by` chains — closest thing in this backlog to Ralph's stated "greenfield" sweet spot | Read-only monitoring surface; no order execution, no sentiment scoring, no ticker resolution. Auth/session security (#92, closed) is adjacent to "security-critical" (HN critique §3.2) so still needs a human security review, not zero-oversight | **Plausible bounded-trial candidate**, with a mandatory security-focused human review gate on auth/session code specifically |
| Tier 4 fully-spec'd, narrow-scope bug fixes | #41 (frontend XSS/DOMPurify/CSP), #112 (varchar truncation test fix), #75 (`qty:"None"` / degenerate herfindahl display bugs) | Good match: single-topic, `ready-for-agent`, backed by strong backpressure (TypeScript/Pydantic type systems, existing test suite) — exactly the "typed language + static analysis as backpressure" pattern the source recommends | Frontend/display/test-infra scope; not order execution or risk gating | **Plausible bounded-trial candidate** |
| Tier 4 thin, audit-pointer-only bug fixes | #42, #43, #44, #45, #46, #47, #48, #50 | **Fails the source's own spec bar today** — one-line "Audit ref: Tier X BXX" bodies with no acceptance criteria; 8 of 12 have no triage label at all, meaning the repo's own process agrees they are not yet ready for any agent, human-supervised or not | #42 is the kill-switch resume bug and #45 is risk-number coherence (drawdown/exposure/stop thresholds) — both squarely inside CLAUDE.md's non-negotiable risk/guardrail territory regardless of spec quality | **Not Ralph-ready as-is; needs human spec-writing first** (per the source's own single-topic-spec discipline), and #42/#45 specifically should stay human-implemented even after spec-writing given the kill-switch/risk-number subject matter |
| Tier 2 bugs already touching guardrail/ensemble/stop-loss logic | #107 (drawdown calc), #110 (fallback-signal re-buy bypassing reversal guard), #111 (single-model reads mislabeled as ensemble), #113 (fractional stop-sync gap) | Well-specified by Ralph's own bar (clear problem statements, root cause named) — this is *not* a spec-quality failure | Squarely inside CLAUDE.md's non-negotiable "guardrails: LLM ensemble variance/timeout must fall back to deterministic indicators; never block order execution" and "ticker resolution/sentiment scoring gated" clauses, and direct descendants of the named incident history (BUY/SELL asymmetric guard, signal_id↔score desync). Their current `ready-for-agent` label reflects "fully specified for an AFK session with PR review" per `docs/agents/triage-labels.md`, not "safe for an unattended commit-without-review loop" | **Excluded from an unattended Ralph-style loop regardless of spec quality or existing label** — human-supervised agent work with mandatory pre-merge review is the ceiling here, matching current practice, not a new restriction |
| Tier 1 flag-off shadow-evidence / wiring tasks | #32 (F8 regime_scale gate-flip timer), #33 (S1 refinements), #34 (Stage-2 shadow ARM) | Reasonable match on spec quality (concrete, narrow, code-ready) but these modify strategy weighting/sizing logic that runs (in shadow) against real signals | Not order-submission-path today (flag-off/shadow-only by design), but the artifact they produce directly feeds a later `wayfinder:decision` flip (#27, #28, #31) that *does* touch capital deployment | **Borderline — plausible with a human merge gate**, but the loop must not be allowed to also decide the downstream flip; the flip stays `ready-for-human` regardless of how the shadow-wiring PR was authored |
| Tier 0 QX-01 labeling infrastructure | #30, #54 | Good spec match (#54 has a numbered scope list with concrete Cohen's κ thresholds and file targets) | CLAUDE.md is explicit: "Measurement before enforcement (QX-01): resolver enforcement, confidence calibration, and risk_flags gating are gated on a golden label set — don't enable scoring changes un-measured." The infra itself (migration, sampler, κ harness) is not a scoring change | **Plausible bounded-trial candidate for the infra work itself**, with an explicit, separately-reviewed exclusion on ever having a loop auto-flip anything downstream that #30/#54 gate |
| Tier 3 `wayfinder:decision` PO tickets | #22, #24, #27, #28, #29, #83, #85 | **Structurally not code tasks.** Ralph's own sources describe a technique for producing code/artifacts against a spec — these issues *are* the spec-writing/judgment step upstream of any code, exactly the role the source reserves for "senior expertise guiding Ralph," not for Ralph itself | Universe selection (#22), sleeve additions (#24), pair-swap evaluation (#28), sector-cap flip (#29) — all have direct P&L/risk-model consequences and are already `ready-for-human` by the repo's own process, with the method doc's explicit instruction to *stop*, not work, on sighting this label | **Not Ralph-suitable at all** — this is the category the sources' own scope excludes as clearly as anything in this research |
| Tier 5 backlog grab-bags | #51, #52, #53 | **Fails the source's own spec-scoping test on its face** — each bundles multiple unrelated workstreams in one issue, the literal "conjoined unrelated capabilities" anti-pattern named in the workshop repo | N/A until decomposed | **Not Ralph-ready as-is**; needs human decomposition into single-topic child issues first — which is also just what the repo's own `needs-triage` label already says needs to happen, independent of Ralph |
| Ambiguous-state doc/code-drift tasks | #40 ("07-10 deployment-fixes: task residui... stato incerto") | This is exactly the failure mode the source names directly: "code-based search can be non-deterministic... don't assume an item is not implemented." A loop asked to "finish task 2/3/6" without first confirming what's actually done risks re-implementing already-shipped work or silently skipping a gap | Low direct risk-code overlap, but the ambiguity itself is the hazard | **Needs a human/agent triage pass to resolve current state before any Ralph-style loop, per the source's own named failure mode** — not a risk-gating exclusion, a spec-readiness one |

---

## Part 6 — Concrete verdict

**Can Ralph take over all of Alembic's open issues? No, not wholesale.** Two independent lines of evidence converge on this, and neither depends on the other:

1. **The sources' own stated scope already excludes most of this backlog.** Ralph is documented, by its own creator, as a greenfield-bootstrapping technique ("There's no way in heck would I use Ralph in an existing code base" — [ghuntley.com/ralph/](https://ghuntley.com/ralph/)) for single-topic, acceptance-test-bearing specs, with a human "sitting on the loop, not in it" for review, not for judgment calls. Alembic's backlog contains a real, currently-open `wayfinder:decision` tier (#22, #24, #27, #28, #29, #83, #85) that is structurally a set of questions for a human, not code tasks — plus three `needs-triage` grab-bag issues (#51, #52, #53) that fail the technique's own single-topic spec-scoping test on their face, plus 8 of 12 Tier 4 pre-live-hardening issues that are currently too thin (one-line audit pointers, no triage label) to feed to any agent, human-supervised or not.
2. **Where the sources' own scope would otherwise allow it, Alembic-specific facts narrow it further.** `CLAUDE.md`'s non-negotiable constraints (no synchronous LLM calls in the trading loop, deterministic ticker resolution, golden-label-gated scoring changes, asymmetric-guardrail discipline) and this system's own incident history (a kill-switch silently disabled by an uninitialized `peak_equity`, a BUY/SELL guard that let fallback-sentiment BUYs through where it correctly blocked SELLs, a signal_id↔score desync that recorded a buy against the wrong sentiment score) describe exactly the class of subtle, hard-to-test-for correctness bug that this codebase has actually produced in exactly the code paths (guardrails, drawdown/risk gating, sentiment/ensemble labeling, order execution) where a handful of currently-`ready-for-agent` issues (#107, #110, #111, #113) already live. Ralph's own HN critique thread names the identical concern in miniature — "did that scratch auth system pass any level of security testing?" met only with a reactive "it can find its own bugs if you ask it to" ([news.ycombinator.com/item?id=46632445](https://news.ycombinator.com/item?id=46632445)) — which is a weaker assurance than Alembic's own stated bar of measurement-before-enforcement and human sign-off.

**Scoped recommendation for a bounded trial**, if one is wanted:

- **In-scope candidate set:** the Tier 2 mobile/Android greenfield slices (#93, #95–#99) and the narrowly-specified, strongly-typed/tested Tier 4 fixes (#41, #75, #112) — the two categories in Part 5 that match the sources' own "greenfield or strongly backpressured, single-topic, acceptance-criteria-bearing" bar without also touching a `CLAUDE.md` non-negotiable.
- **Explicit exclusion list, regardless of how well-specified a future version of the ticket becomes:** anything touching `src/workers/execution.py`, `src/workers/portfolio_scheduler.py`, the kill-switch/drawdown-cap path, `src/connectors/ticker_resolver*.py`, the sentiment scoring formula (`src/workers/sentiment.py`), the ensemble fallback/guardrail logic, or any file gated by the QX-01 golden label set. This maps directly onto the Tier 2 "already touching guardrail/ensemble/stop-loss logic" row in Part 5 (#107, #110, #111, #113) and the risk-relevant Tier 4 stubs (#42, #45) — these stay human-implemented even once properly spec'd.
- **Guardrails for the trial itself**, synthesized from the sources' own stated requirements (sandboxing, backpressure, human review) plus Alembic's existing process (which already requires PR review and `closes #N` for `ready-for-agent` work — see `docs/agents/wayfinder-roadmap-method.md`):
  - No direct-to-`main` commits from the loop under any circumstance; every loop iteration's output lands as a PR, never an auto-merge — this is already the documented Alembic norm and should not be relaxed for a Ralph trial, only tested against it.
  - A human review gate before merge on every PR the loop produces, not just a sampled subset — the sources' own framing ("sit on the loop, not in it") describes post-hoc review of *commits*, and Alembic's incident history is a direct argument for keeping that review real rather than rubber-stamped.
  - Hard iteration and time-box limits per issue (the one concrete operational guardrail multiple sources converge on: [`ralph-orchestrator`](https://github.com/mikeyobrien/ralph-orchestrator/blob/main/README.md)'s undocumented-default iteration cap is itself a gap worth not repeating; DreamHost's summary explicitly recommends "enforce iteration limits and time limits so the loop can't run forever and burn through your token budget," [dreamhost.com/blog/ralph-wiggum/](https://www.dreamhost.com/blog/ralph-wiggum/)).
  - Sandboxed execution with no access to live broker credentials, Alpaca live-trading keys, or production database write access beyond what the specific in-scope issue requires — directly per the workshop repo's stated sandboxing requirement ([`github.com/ghuntley/how-to-ralph-wiggum/README.md`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md)).
  - No expansion of the in-scope set without a fresh human decision — i.e., the trial answers "does this help on the narrow candidate set," not "should this become the default workflow"; that would itself be a `wayfinder:decision`-shaped question, per Alembic's own tracker conventions, not something the loop decides for itself.

---

## Sources consulted

**Primary (Geoffrey Huntley, same author):**
- [ghuntley.com/ralph/](https://ghuntley.com/ralph/) — "Ralph Wiggum as a 'software engineer'" (originating post)
- [ghuntley.com/loop/](https://ghuntley.com/loop/) — "everything is a ralph loop"
- [ghuntley.com/real/](https://ghuntley.com/real/) — "Software development now costs less than than the wage of a minimum wage worker"
- [ghuntley.com/agent/](https://ghuntley.com/agent/) — "how to build a coding agent: free workshop"
- [`github.com/ghuntley/how-to-ralph-wiggum`](https://github.com/ghuntley/how-to-ralph-wiggum/blob/main/README.md) — companion workshop repository (same author), refined file model (`AGENTS.md`/`IMPLEMENTATION_PLAN.md`) and spec-scoping discipline

**Third-party adaptation and critique:**
- [`github.com/mikeyobrien/ralph-orchestrator`](https://github.com/mikeyobrien/ralph-orchestrator/blob/main/README.md) — open-source multi-backend re-implementation
- [news.ycombinator.com/item?id=46632445](https://news.ycombinator.com/item?id=46632445) — "Continuous agents and what happens after Ralph Wiggum?" (substantive comments only)
- [dreamhost.com/blog/ralph-wiggum/](https://www.dreamhost.com/blog/ralph-wiggum/) — secondary summary, cited only for its non-redundant "no acceptance tests → chaotic loop" and iteration-limit points; flagged as low independent-analysis content by this research's own review

**Alembic ground truth (live, 2026-07-23):**
- `gh issue list --state open --limit 200 --json number,title,labels` (this repository)
- `gh issue view 21` (roadmap map) and sampled children: #22, #34, #40, #41, #42, #45, #51, #54, #59, #84, #92, #93, #95, #107, #110, #111
- `docs/agents/issue-tracker.md`, `docs/agents/wayfinder-roadmap-method.md`, `docs/agents/triage-labels.md`
- `CLAUDE.md` (this repository, Non-Negotiable constraints)
