# 00 — Agent Operating Guide

**Audience**: agente LLM autonomo (Claude, GPT, simili) che implementa Alembic v2 partendo dalla documentazione `/alembic_v2/`.

**Obiettivo del documento**: permettere all'agente di portare a termine l'implementazione di Alembic v2 con **interventi umani minimi** (solo dove esplicitamente richiesto).

---

## Come usare questa guida

1. **Leggi tutti i 7 file in `/agent_guide/` prima di iniziare**, in ordine numerico.
2. **Leggi i 6 file in `/alembic_v2/`** (la documentazione di prodotto).
3. **Esegui in sequenza** le fasi A → G come da `04_roadmap.md`. Una fase alla volta. Non saltare.
4. **Per ogni task**, segui il template definito sotto.
5. **Quando trovi ambiguità**, applica le `06_decision_rules.md` PRIMA di chiedere all'utente.
6. **Chiedi all'utente solo nei `HUMAN_GATE`** esplicitamente marcati.

---

## Principi operativi non negoziabili

### P1 — Read before write
Prima di scrivere QUALSIASI codice, esplora il repo esistente. Comandi standard:
```bash
git ls-files | head -50
find . -name "*.py" | grep -i "<keyword>"
grep -r "<symbol>" --include="*.py" .
```
Mai assumere che un componente esista o non esista. Verificare.

### P2 — Test before claim done
Un task è "done" solo quando i suoi acceptance criteria sono **verificati con esecuzione**, non solo letti. Se l'acceptance dice "test passes", esegui `pytest path/to/test`.

### P3 — Commit small, commit often
Un commit per task atomico (T-NNN). Mai commit "WIP" o "vari fix". Format del commit:
```
[T-NNN] Short description

- Bullet of what changed
- Bullet of what was tested
- References: <link to relevant docs>
```

### P4 — Branch per phase
Un branch git per ogni fase. Format: `phase-A-foundation`, `phase-B-s1-momentum`, etc. Merge in main solo a milestone passed.

### P5 — Anti-look-ahead first
Quando crei codice di backtest, FIRST scrivi i test anti-look-ahead, THEN il codice. È non negoziabile.

### P6 — Document decisions
Ogni decisione non banale presa autonomamente va in `DECISIONS.md` nel repo, format:
```
## YYYY-MM-DD — [T-NNN] Title
**Context**: why this came up
**Options considered**: A, B, C
**Decision**: chose X
**Rationale**: ...
**Reversible**: yes/no
```

### P7 — Fail loud, not silent
Se qualcosa è ambiguo o non specificato, **non inventare**. Applica decision rules. Se ancora ambiguo, **stop e chiedi**. Mai best-guess silente.

### P8 — Reproducibility above all
Ogni script deve essere ri-eseguibile e dare stesso output. Niente paths hardcoded, niente sleep arbitrari, niente "funziona sulla mia macchina".

---

## Stack tecnico assunto

L'agente DEVE verificare questi prima di iniziare:

| Componente | Versione minima | Comando di verifica |
|---|---|---|
| Python | 3.11+ | `python --version` |
| Poetry o pip | recente | `poetry --version` / `pip --version` |
| PostgreSQL | 15+ | `psql --version` |
| Redis | 7+ | `redis-cli --version` |
| Git | recente | `git --version` |
| Docker (opzionale) | recente | `docker --version` |

Se uno di questi manca: STOP, chiedi setup all'utente.

---

## Template di esecuzione task

Ogni task in `01_phase_A.md` ... `04_phase_F_G.md` ha questa struttura standardizzata. L'agente la segue rigorosamente.

```markdown
### T-NNN — <Title>

**Status**: OPEN | IN_PROGRESS | DONE | BLOCKED
**Effort**: S | M | L | XL
**Dependencies**: [list of T-NNN]
**Reference docs**: [list of /alembic_v2/*.md sections]

#### Prerequisites check
[Comandi shell da eseguire per verificare che le dipendenze siano soddisfatte]

#### Files to create
- `path/to/new_file_1.py` (purpose)
- `path/to/new_file_2.py` (purpose)

#### Files to modify
- `path/to/existing_file.py` (what changes)

#### Implementation steps
1. Step concreto con comando o pseudo-codice
2. Step concreto
3. ...

#### Acceptance verification
[Comandi shell da eseguire per verificare che il task sia done. Ognuno deve passare.]

#### On failure
[Cosa fare se acceptance fail: debug pattern, dove guardare, quando re-prioritizzare]

#### Commit message template
```
[T-NNN] Title

- What was added
- What was tested
```
```

---

## Sequenza di esecuzione completa

```
PHASE A — Foundation (settimane 1-4)
├── T-001: Setup vectorbt + data loading
├── T-002: Backtest engine event-driven base
├── T-003: Cost model
├── T-004: Anti-look-ahead test suite
├── T-005: Walk-forward framework
├── T-006: Metrics engine
└── T-007: Validation gates
                                       ← MILESTONE A — Backtest Foundation Ready
                                       ← HUMAN_GATE: verifica con utente che backtest engine sia accettabile

PHASE B — S1 Time-Series Momentum (settimane 5-7)
├── T-101: Universe + data
├── T-102: S1 signal
├── T-103: S1 strategy module
├── T-104: S1 backtest + gates
└── T-105: S1 sensitivity
                                       ← MILESTONE B — S1 validated
                                       ← HUMAN_GATE: review S1 backtest report

PHASE C — S3 Cross-Sectional Momentum (settimane 8-10)
├── T-201: Universe + liquidity
├── T-202: S3 signal
└── T-203: S3 module + backtest
                                       ← MILESTONE C — S3 R&D SLEEVE (gates 3&5 FAIL, OOS Sharpe 0.15)
                                       ← Portfolio live = S1 + S2 + S4. S3 esclusa. Continua con PHASE D.

PHASE D — S2 Volatility Risk Premium (settimane 11-16)
├── T-301: IBKR setup                  ← HUMAN_GATE: serve IBKR account
├── T-302: Option chain ingestion
├── T-303: Black-Scholes + greeks
├── T-304: S2 signal
├── T-305: S2 exit logic
├── T-306: S2 regime overlay
├── T-307: S2 event filter
└── T-308: S2 backtest + gates
                                       ← MILESTONE D — S2 validated

PHASE E — S4 News Refactor (settimane 17-18)
├── T-401: Refactor to cross-sectional
├── T-402: S4 module
└── T-403: S4 backtest + gates (tolleranti)
                                       ← MILESTONE E — S4 in portfolio (10%)

PHASE F — Portfolio Combiner (settimane 19-22)
├── T-501: Combiner base
├── T-502: Risk parity overlay
├── T-503: Constraint enforcer
├── T-504: Vol targeting
└── T-505: Full multi-strategy backtest
                                       ← MILESTONE F — Combined system validated
                                       ← HUMAN_GATE: review combined backtest

PHASE G — Production Deployment (settimane 23-30)
├── T-601: Celery multi-strategy orchestration
├── T-602: Risk monitor multi-strategy
├── T-603: Dashboard
├── T-604: Paper trading 90gg          ← HUMAN_GATE: continuous monitoring
└── T-605: Decay monitoring
                                       ← MILESTONE G — Paper trading 90gg passed
```

---

## HUMAN_GATE: quando fermarsi e chiedere

L'agente DEVE fermarsi e chiedere all'utente nei seguenti casi.

### Categoria 1 — Risorse esterne richieste
- **HG-1**: account IBKR mancante (T-301)
- **HG-2**: API key non disponibili (Alpaca, MarketAux, IBKR, FRED)
- **HG-3**: capitale per paper trading non configurato
- **HG-4**: setup database/redis non disponibile in ambiente

### Categoria 2 — Decisioni strategiche
- **HG-5**: una strategia FALLISCE i gate. Non skip, non re-tune. Stop e analizza con l'utente.
- **HG-6**: backtest mostra Sharpe estremamente alto (>2.0) → quasi sicuramente bug. Stop, debug, escalate.
- **HG-7**: divergenza significativa (>5%) tra vectorbt e NautilusTrader/LEAN per stessa strategia → debug needed.
- **HG-8**: live performance diverge >2σ da backtest → stop, indaga.

### Categoria 3 — Decisioni operative
- **HG-9**: passaggio da paper a live (capitale reale)
- **HG-10**: ritiro/sostituzione di una strategia in produzione
- **HG-11**: modifica di parametri "core" di una strategia (non fix, ma re-tuning)
- **HG-12**: cambio universe (aggiunta/rimozione ticker)

### Categoria 4 — Errori critici di sistema
- **HG-13**: DB corruption sospetta
- **HG-14**: discrepanza broker positions vs DB > 1%
- **HG-15**: anti-look-ahead test FAIL in CI

### Format della richiesta HUMAN_GATE

Quando l'agente si ferma per HG:
```markdown
## 🛑 HUMAN_GATE [HG-N]: <Short title>

**Context**: cosa stava facendo l'agente
**Trigger**: cosa ha causato il gate
**Why human needed**: spiegazione esplicita
**Options for user**:
A) Option A description
B) Option B description
C) Option C description
**Recommended**: opzione X, perché Y
**Files to inspect**: [paths]
**Awaiting**: tua decisione su A/B/C
```

L'agente NON procede finché l'utente non risponde.

---

## Self-validation checklist per ogni task

Prima di marcare un task DONE, l'agente verifica:

- [ ] Tutti gli acceptance criteria del task sono soddisfatti, ognuno verificato con comando esplicito
- [ ] Tutti i test scritti per il task passano (`pytest path/`)
- [ ] CI (se configurata) è green
- [ ] Nessuna decisione non documentata in `DECISIONS.md`
- [ ] Commit fatto con messaggio standard
- [ ] Nessun TODO/FIXME/XXX nel codice del task
- [ ] Linting clean (`ruff check .` e `mypy strict`)
- [ ] Coverage del modulo nuovo ≥ 80%

Se uno di questi fail → task NON è done.

---

## Cosa fare quando le cose si rompono

### Debug pattern standardizzato

1. **Riproduci il fail** in isolation (esempio minimo)
2. **Read the error message** (sembra ovvio, ma molti LLM lo skip)
3. **Check assumptions** (data file presente? variable env settata? path corretto?)
4. **Inspect git log** del file: chi/cosa ha toccato recentemente
5. **Search known issues**: `grep -r "<error keyword>" docs/`
6. **Bisect** se il bug è stato introdotto da poco

### Quando un test fail dopo un cambio piccolo

1. NON modificare il test per farlo passare
2. NON commentare il test
3. NON aggiungere try/except per nascondere
4. Capisci PERCHÉ fallisce. Poi:
   - Se il test era sbagliato → discuti con utente prima di modificarlo
   - Se il codice è sbagliato → fix il codice

### Quando il backtest dà numeri "strani"

Sharpe > 2.0 OOS netto costi: 99% probabilità è un bug.
Cause comuni:
- Look-ahead (esempi specifici in `01_phase_A.md`)
- Survivorship bias nell'universe
- Slippage troppo ottimista nel cost model
- Tipo di dato sbagliato (close vs adj close per signal computation)
- Data point-in-time errato

**Procedura**:
1. Stop. Non procedere come se fosse normale.
2. Apri sanity check: run su SPY buy-and-hold deve dare Sharpe ~0.5-0.6 storico.
3. Se sanity check fail → bug nel data o nell'engine.
4. Se sanity check ok → bug nella strategy.
5. Escalate HG-6 se non risolvi in 1-2 ore di debug.

---

## File del repo che l'agente DEVE conoscere prima di iniziare

L'agente esegue questi comandi all'inizio della sessione, per familiarizzare col repo:

```bash
# Struttura generale
git ls-tree -r HEAD --name-only | head -100

# Documenti chiave
cat README.md 2>/dev/null | head -100
cat ARCHITECTURE.md 2>/dev/null | head -100
cat CLAUDE.md 2>/dev/null | head -200

# Issue tracker GitHub (se accessibile)
# Verifica issues etichettate 'pre-live-blocker' e 'high'

# Cerca componenti esistenti
find . -type d -name "strategies" -o -name "signals" -o -name "regime*"
grep -r "class.*Strategy" --include="*.py" | head -20
grep -r "regime_classifier\|RegimeDetector" --include="*.py" | head -10

# Test esistenti
find . -name "test_*.py" | head -20
pytest --collect-only 2>/dev/null | head -30

# Config esistente
find . -name "*.yaml" -o -name "*.yml" | grep -v node_modules | head -10
```

L'output di questi comandi va salvato in `/tmp/repo_survey.txt` e referenziato durante l'esecuzione delle fasi.

---

## Cosa fare con il codice esistente

Dal repo Alembic v1 (Jonbj/alembic) esistono già:
- News ingestion pipeline
- LLM ensemble scoring (4 modelli)
- Signal aggregation EWMA
- Regime classifier (Kimi+Qwen LLM pair)
- Performance monitoring (PSI, CUSUM, Newey-West)
- GDELT backtest pipeline
- Risk monitor + circuit breaker
- Celery workers
- Alpaca SDK integration

L'agente DEVE:
1. **Riusare**, non riscrivere
2. **Wrappare** in interfacce standard se necessario (vedi `02_architecture.md` di Alembic v2)
3. **Refactorare solo se inevitabile**, e documentare il perché
4. **Marcare deprecated** ciò che diventa obsoleto, non eliminare immediatamente

Mapping esistente → v2:
| Codice esistente | Riuso v2 | Modifica richiesta |
|---|---|---|
| news ingestion | S4 + S2 event filter | nessuna |
| LLM ensemble | S4 + S2 event filter | nessuna |
| signal aggregation | S4 | wrap in `BaseStrategy` |
| regime classifier | S1 filter + S2 modulation | esporre come `RegimeService` |
| risk monitor | tutte le strategie | estendere a opzioni |
| Celery workers | tutti | aggiungere task per S1, S2, S3 |
| Alpaca SDK | S1, S3, S4 paper | mantenere |

---

## Riassunto: come l'agente lavora

```
START
  │
  ▼
Read all /agent_guide/ + /alembic_v2/ docs
  │
  ▼
Run repo survey (commands above)
  │
  ▼
Verify stack prerequisites
  │
  ▼
Pick next task in current phase (start from T-001)
  │
  ▼
Read task spec carefully
  │
  ▼
Apply template (Prerequisites → Files → Implementation → Acceptance)
  │
  ▼
Hit ambiguity? ──Yes──▶ Apply decision_rules.md ──Resolved?──Yes──▶ continue
                                                          │
                                                          No
                                                          │
                                                          ▼
                                                       HUMAN_GATE
                                                          │
                                                          ▼
                                                       wait for response
  │
  ▼
Verify acceptance criteria with explicit commands
  │
  ▼
All pass? ──No──▶ Debug pattern ──Resolved?──No──▶ HUMAN_GATE
   │
   Yes
   │
   ▼
Commit + push
   │
   ▼
Next task or Milestone check
   │
   ▼
End of phase? ──Yes──▶ HUMAN_GATE for milestone review
   │
   No
   │
   └─▶ Loop to "Pick next task"
```
