# DECISIONS.md

Agent-autonomous decisions documented per P6 of the Agent Operating Guide.

---

## 2026-05-29 — [Phase A] Package structure: src/ instead of alembic/

**Context**: The agent guide (DR-01) specifies `alembic/backtest/` as the target path, but the
existing repo uses `src/` as the package root (all existing code is under `src/`).

**Options considered**:
A) Refactor repo to use `alembic/` as package root
B) Place new v2 modules under `src/backtest/` (adapt to existing structure)

**Decision**: Chose B.

**Rationale**: DR-01 explicitly states "Se il repo esistente ha una struttura diversa: NON refactor.
Adatta i nuovi moduli alla struttura esistente." The risk of breaking existing imports vastly
outweighs the naming benefit.

**Reversible**: Yes — a future task can rename `src/` → `alembic/` as a dedicated refactor.

---

## 2026-05-29 — [Phase A] Package manager: uv instead of poetry

**Context**: The guide uses `poetry run` throughout. The repo uses `uv` (uv.lock present,
.venv managed by uv). Poetry is not installed.

**Options considered**:
A) Install poetry and migrate
B) Use `uv run` as drop-in replacement for `poetry run`

**Decision**: Chose B.

**Rationale**: uv is already set up and the venv is active. All `poetry run <cmd>` → `uv run <cmd>`.
No behavioural difference for the commands used.

**Reversible**: Yes.

---

## 2026-05-29 — [T-001] pyproject.toml build-backend fix

**Context**: `setuptools.backends.legacy:build` failed with ModuleNotFoundError on the installed
setuptools version in the uv-managed venv. `uv sync` was blocked.

**Options considered**:
A) Pin a specific setuptools version that ships `backends`
B) Switch to `setuptools.build_meta` (standard, stable since setuptools 39)

**Decision**: Chose B.

**Rationale**: `setuptools.build_meta` is the canonical PEP 517 backend. No functionality loss.
The `backends.legacy` naming is a newer alias that is not stable across setups.

**Reversible**: Yes.

---

## 2026-06-07: S7 PEAD strategy

**Context**: Pipeline Ollama già esistente per sentiment. SEC EDGAR è gratis. PEAD è un'anomalia robusta in letteratura finanziaria (Ball & Brown 1968).

**Options considered**:
A) Usare solo segnali di sentiment per news post-earnings
B) Classificare direttamente gli 8-K filing SEC con LLM dedicato (S7)

**Decision**: Chose B.

**Rationale**: Il segnale PEAD è più diretto e meno rumoroso del sentiment generale. Il filing 8-K contiene informazioni strutturate (EPS, guidance) che un LLM può classificare con alta accuratezza. Sfrutta la pipeline Ollama esistente senza costi aggiuntivi.

**Reversible**: Yes — disabilitare in `config/strategies.yaml`.

---

## 2026-06-16: Worker split inference/celery

**Context**: FinBERT caricava il modello in ogni subprocess Celery con concurrency>1, causando OOM su hardware locale.

**Options considered**:
A) Ridurre concurrency globale del worker a 1
B) Separare un `worker-inference` dedicato (concurrency=1) per FinBERT/Ollama

**Decision**: Chose B.

**Rationale**: Separare i worker permette di mantenere concurrency=4 per i task leggeri mentre si garantisce un singolo processo per FinBERT con un'istanza singleton del modello.

**Reversible**: Yes — re-mergiare i due worker in `docker-compose.yml`.

---

## 2026-06-16: Rimozione DeepSeek/GLM dall'ensemble

**Context**: DeepSeek-V4-Pro causava OOM su hardware locale. GLM-5.1 aveva IC inferiore a Kimi K2.6 in A/B test.

**Decision**: LLM ensemble ridotto a Kimi K2.6 + Qwen3.5.

**Rationale**: La riduzione del carico Ollama migliora latenza e stabilità del sistema senza peggiorare significativamente la qualità del segnale.

**Reversible**: Yes — re-aggiungere i modelli in `src/llm/client.py`.

---

## 2026-06-16: Redis cycle lock per portfolio orchestrator

**Context**: Celery beat con heartbeat irregolare poteva schedulare due run del portfolio cycle sovrapposti, causando ordini duplicati.

**Options considered**:
A) Aumentare il TTL del beat schedule
B) Acquisire un lock Redis atomico all'inizio di ogni run

**Decision**: Chose B.

**Rationale**: Il lock Redis (`SET NX EX 840`) è atomico e garantisce al massimo un run attivo per volta. TTL 840s (14 min) previene deadlock se il task termina senza rilasciare il lock.

**Reversible**: Yes — rimuovere il lock da `src/workers/portfolio_scheduler.py`.
