# Model Tournament Workflow

Tool per confrontare N modelli AI sullo stesso piano di sviluppo in modo strutturato e riproducibile.

## Perché serve

Il bulk-copy di codice generato da un singolo modello in N worktree non produce un confronto reale. Questo tool garantisce che ogni modello lavori in isolamento e che le metriche vengano raccolte in modo consistente.

## Architettura

```
┌─────────────┐     init        ┌──────────────────────────┐
│  models.md  │ ──────────────▶ │  .worktrees/tournament-*   │
└─────────────┘                 │  + .claude/tournament-     │
                                │    prompt.md (per modello) │
                                └──────────────────────────┘
                                          │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
              ┌──────────┐          ┌──────────┐          ┌──────────┐
              │  sonnet  │          │  opus    │          │  haiku   │
              │ worktree │          │ worktree │          │ worktree │
              └────┬─────┘          └────┬─────┘          └────┬─────┘
                   │ /model sonnet        │ /model opus          │ /model haiku
                   │ implementa           │ implementa           │ implementa
                   │ collect              │ collect              │ collect
                   └────┬─────────────────┴────┬─────────────────┘
                        ▼                      ▼
                 ┌──────────────┐      ┌──────────────┐
                 │  .claude/    │      │  .claude/    │
                 │ tournament_  │      │ tournament_  │
                 │ state.json   │      │ state.json   │
                 └──────┬───────┘      └──────────────┘
                        │
                        ▼ report
                 ┌──────────────┐
                 │ model_tour-  │
                 │ nament_report│
                 │ .md          │
                 └──────────────┘
```

## Comandi

### 1. Inizializzazione

```bash
python scripts/model_tournament.py init docs/superpowers/plans/2026-05-18-frontend-backend.md
```

Legge `models.md`, crea un worktree + branch per ogni modello, e scrive il piano in `.claude/tournament-prompt.md` dentro ogni worktree.

Opzioni:
- `--models sonnet,opus,haiku` — testa solo un subset
- `--base-branch feat/some-base` — branch di partenza alternativo

### 2. Sviluppo per modello (iterativo)

Per ogni modello:

```bash
# In Claude Code:
/model sonnet

# Nel terminale:
cd .worktrees/tournament-sonnet

# Chiedi a Claude:
"Implementa il piano descritto in .claude/tournament-prompt.md"

# Dopo il completamento:
python ../../scripts/model_tournament.py collect
```

`collect` raccoglie automaticamente:
- Test passati / errori
- Numero di commit totali e nuovi
- File sorgente modificati (esclusi `__pycache__` e `.pyc`)

### 3. Stato intermedio

```bash
python scripts/model_tournament.py status
```

Mostra una tabella con lo stato di ogni modello (pending / completed) e le metriche raccolte.

### 4. Report comparativo

```bash
python scripts/model_tournament.py report
```

Genera `model_tournament_report.md` con:
- Tabella riassuntiva per tutti i modelli
- Ranking dei modelli completati
- Best performer (per test passati, errori, granularità commit)

### 5. Pulizia

```bash
python scripts/model_tournament.py cleanup
```

Rimuove tutti i worktree, i branch, e il file di stato.

## Convenzioni

- Ogni worktree è isolato: modifiche in un worktree non toccano gli altri
- I branch partono dal `base-branch` specificato (default: `main`)
- Il file di stato `.claude/tournament_state.json` è la fonte di verità
- I prompt per modello sono in `.claude/tournament-prompt.md` dentro ogni worktree

## Limitazioni

- Il cambio modello (`/model <nome>`) richiede azione manuale in Claude Code
- Lo script non può lanciare sessioni Claude autonomamente
- Il confronto è su metriche oggettive (test, commit); la qualità del codice richiede review umana

## Esempio completo

```bash
# Setup
python scripts/model_tournament.py init docs/plan.md --models "sonnet,opus,qwen3-coder-480b-cloud"

# Sessione 1: sonnet
/model sonnet
cd .worktrees/tournament-sonnet
# (implementa il piano)
python ../../scripts/model_tournament.py collect

# Sessione 2: opus
/model opus
cd .worktrees/tournament-opus
# (implementa il piano)
python ../../scripts/model_tournament.py collect

# Sessione 3: qwen3-coder
/model qwen3-coder-480b-cloud
cd .worktrees/tournament-qwen3-coder-480b-cloud
# (implementa il piano)
python ../../scripts/model_tournament.py collect

# Report finale
cd /repo/root
python scripts/model_tournament.py report
cat model_tournament_report.md

# Pulizia
python scripts/model_tournament.py cleanup
```
