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
