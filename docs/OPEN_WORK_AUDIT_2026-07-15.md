# Open Work Audit — 2026-07-15

Audit di tutta la documentazione/roadmap/plans per estrarre i lavori **ancora aperti o mai chiusi**. Estratto da 3 agent Explore in parallelo + cross-referenza con git/memory.

> **Caveat importante (doc/code drift):** molti plan doc hanno checkbox `- [ ]` mai spuntate **ma il lavoro è in realtà DONE e merged** (il piano non è stato aggiornato post-esecuzione). Dove ho cross-confermato lo stato reale via commit/memory, lo marco. **Non fidarti dei checkbox vuoti come indicatore di "non fatto"** — verifica sempre contro git.

---

## TIER 0 — Bloccante sistemico (gating di tutto P1+P2)

### QX-01 — Golden label set
- **Stato:** tooling DONE (tabella `news_labels`, UI `/labeling`, harness, dashboard `/quality`); **annotazione ferma a 17/148**.
- **Blocca:** enforcement resolver full, calibrazione confidence QS-01/02, QS-03 agreement, Punto 1b risk_flags+materiality, tutta la promozione qualità S4.
- **Sblocco:** PO Decisione #4 (annotazione in-house vs esternalizzata) → accelerare a 400 label Fase 1.

---

## TIER 1 — Codice pronto, flag-off (cambia trading solo al flip operatore)

| Item | Stato reale | Gate di flip |
|---|---|---|
| **F9a vol-scaled stop** | implementato+merged, `stop_loss_mode: fixed` (live 2%). Gate fase 6 FAIL 07-11. **Calibrazione delegata a Kimi oggi** (`docs/stop_loss_calibration_kimi_prompt_2026-07-15.md`) | gate OOS PASS (bootstrap ≥70%, DD delta ≤0.10) → canary S1 10% → PO sign-off |
| **Sector exposure cap** | wired+merged (ea436fd), `max_sector_exposure: 0.0` = off. Non avrebbe boundato l'incidente 07-13 a sizing attuale | PO flip 0.10 (ricalibrare con F9a) |
| **F8 regime_scale** | wired portfolio path (2bf31bd), `apply_regime_scale: false` = shadow-only | 10-14gg shadow → flip |
| **S1 refinements** (skip-month, absolute filter, cap-after-norm) | piano TDD esiste, flag default off. **Non verificato se implementato** (plan checkbox vuote) | comparison report → PO flip |
| **Stage 2 shadow mode** | **IMPLEMENTED+merged** (a099719, migration 038, auto-arm script lunedì 09:00) | armare toggle Redis → 7gg report → PO decide coppia |
| **QS-03 agreement_weighting** | codice DONE, default OFF | post-QX-01 |

---

## TIER 2 — Piani scritti, mai eseguiti (o parzialmente)

| Piano | Stato reale (cross-verificato) |
|---|---|
| **3-model ensemble** (deepseek 3° modello, majority-of-3) | **NON partito.** Nessun branch, deepseek non in `model_registry.py`, `_OLLAMA_SEM_SLOTS=2` hardcoded. Piano+handoff esistono |
| **Vettore A earnings chain** | Phase 0 discovery **non fatto** (brief senza report). Consensus wired via Finnhub (pre-empt parziale). Transcript tone Phase 2 non fatto |
| **S7 revival resume** | tasks `- [ ]`, POC-1 inconclusivo (n=15<30), POC-2 transcript tone parziale (commit presenti). **Deadline PO: 2026-08-01** |
| **S2-1 Source P&L Funnel** | **Parziale:** FIX-04/05 DONE, FIX-06 colonna esiste ma NULL (popolata da S2-2 non fatto), frontend Source Funnel DONE. Resto tasks aperti |
| **S4 measurement foundation (Wave 1)** | ✅ **DONE merged 07-13 (3591d5c)** nonostante checkbox vuote — coverage fwd 97/78/63%. **Doc drift:** piano non aggiornato |
| **07-10 deployment-fixes (7 task)** | **Parziale:** Task1 S1 sparse-ticker DONE live 07-10, F4/F5/F6/F8 done (237e660, 2bf31bd). Task2/3/6 stato incerto. **Doc drift** |
| **Sector cap plan (4 task TDD)** | ✅ **DONE merged** nonostante checkbox vuote. **Doc drift** |

---

## TIER 3 — Decisioni PO pendenti

| # | Decisione | Stato | Impatto |
|---|---|---|---|
| 1 | Universo small/mid vs large-cap | **APERTA** | Determina se S7/ALPHA-A5 riapre |
| 2 | FMP one-stop provider | provvisoriamente adottata (revocabile) | Vettore A |
| 3 | Sleeve biotech (oltre large-cap US) | **APERTA, zero progresso** | Espansione |
| 4 | Budget annotazione QX-01 (in-house vs out) | **APERTA** | Sblocca Tier 0 |
| 5 | S7 tieni/elimina | **APERTA, deadline 2026-08-01** | Rimozione completa se FAIL |
| 6 | Flip S1 refinements | pendente post-comparison report | |
| 7 | Valutazione pair swap glm+gptoss | pendente (lunedì fallback rate) | Priorità Wave 3 |
| 8 | Flip sector cap 0.10 | pendente | |

---

## TIER 4 — Pre-live hardening (Technical Review 07-02, release-blocker ancora aperti)

> Questi sono blocchi per il go-live reale (non paper). Molti B-fix chiusi, ma non tutti.

| Item | Stato | Note |
|---|---|---|
| **B7/B32 — PostgreSQL pool leak** | **APERTO, CONFERMATO LIVE** | Ieri 20 connessioni worker/beat leaked "idle in transaction" tenevano lock su `trades` (bloccato migration 037). Stop container → leak 0. Fonte = worker/beat |
| **B5 — Frontend XSS (DOMPurify + CSP + token storage)** | **APERTO, Critical** | |
| B3 — kill-switch resume non ripristina mode | APERTO | |
| B8 — rate limiting + CORS | APERTO | |
| B9 — `SentimentResult.model_dump_json` Pydantic v2 | APERTO | |
| B13/14/18 — coerenza numeri risk (drawdown 5/10%, exposure 50/95%, stop 2/5%) | APERTO | functional review §6.1 insiste |
| B31 — `LLMBudgetTracker` `FOR UPDATE` senza commit | APERTO (P1) | |
| B33/34 — Celery `acks_late` global + Ollama time limit | APERTO | |
| B35 — debounce news stream | APERTO | |
| B44 — stop-loss broker-side sui frazionabili | APERTO | |
| B5b — frontend lint + test base | APERTO | |

---

## TIER 5 — Backlog P2/P3 (mai avviati, gated dietro P0+P1 + ALPHA-A5 FAIL)

- **ALPHA-B0** — SEC EDGAR ticker bug (`ticker_symbol` non ritornato) — ancora disabilitato nel beat, **APERTO**
- **ALPHA-B/C/D/E/G** vectors — backlog, gated dietro P0+P1
- **QT-02** — `ticker_lookup` point-in-time (no `valid_from/valid_to` → look-ahead backtest) — APERTO
- **QS-04/05/08** — few-shot/RAG-supervisor/novelty gate — TODO gated su label set
- **EN-04** — source priority cross-source — possibile OPEN
- **EN-07** — alerting degrado fonte — APERTO
- **Master roadmap A-09..A-13** — docker hardening, pyproject config (mypy/ruff/coverage), llm_client tests, pagination safety, token-aware truncation in finbert.py
- **F12** — approval gate fail-open su row lifecycle assente (lean: fail-closed-on-absent)
- **F11** — correlation pass ConstraintEnforcer non wired (sector pass wired ma cap=0)
- **F13** — Zeygos universe filter dead code (0 call site)
- **S5 Crypto / S6 Macro** — da buildare, gate attivazione (BTC MA50 etc.)
- **Sprint 2/3 functional review** (S2-2..S2-8, S3-1..S3-9) — pending, criteri di ingresso da verificare

---

## finding trasversale — Doc/code drift

Piano documenti con checkbox `- [ ]` ma lavoro **effettivamente DONE+merged**: S4-measurement (Wave 1), sector-cap, parte dei 07-10 deployment-fixes. I plan doc non vengono aggiornati post-esecuzione → l'audit "naïf" dei checkbox sovrastima il lavoro aperto. **Azione consigliata:** aggiornare i checkbox nei plan doc post-merge (o smettere di usarli come source of truth e basarsi su git + memory).

---

## Top 5 più actionabili ora

1. **Kimi calibrazione F9a** — già delegata oggi (prompt pronto). Sblocca il flip dello stop vol-scaled.
2. **QX-01 annotazione** — serve PO Decisione #4 (in-house vs out). È il collo di bottiglia di tutta la qualità S4.
3. **B7/B32 pool leak** — confermato live ieri. Pre-live blocker. Root cause = connessioni worker/beat non chiuse.
4. **Stage 2 shadow arm** — codice merged, manca solo l'arm del toggle + 7gg di raccolta → decide la coppia modello definitiva.
5. **S7 decisione PO** — deadline 2026-08-01. Se FAIL → rimozione completa (beat + lifecycle + disdetta FMP).