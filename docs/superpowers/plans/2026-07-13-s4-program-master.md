# Programma S4 — Master di sequenziamento (handoff Sonnet)

**Scopo:** indice operativo di TUTTE le modifiche del programma "investire su S4",
con ordine, dipendenze, prompt di lancio e regole anti-collisione. Ogni wave ha il
suo documento; questo file dice solo *cosa lanciare, quando, e perché in
quest'ordine*.

**Contesto in una riga:** la S4 attuale (sentiment su news editoriali) ha IC≈0.01 e
P&L all-time −$788 misurati; il programma ripara la misurazione, massimizza la resa
del segnale esistente, e pivota l'input verso eventi primari (earnings chain).

---

## Le wave

| # | Cosa | Documento | Tipo | Stato |
|---|------|-----------|------|-------|
| 1 | **Fondamenta di misurazione** — forward return su TUTTI i segnali (fallback inclusi) + orizzonti 1/3/5gg | `2026-07-12-s4-measurement-foundation.md` | Piano TDD completo | PRONTO da lanciare |
| 2 | **Stage 2 shadow-mode** — i 3 modelli non attivi scorano il traffico live per 7 giorni, report auto via Telegram | `2026-07-12-stage2-shadow-mode.md` | Piano TDD completo | PRONTO, lanciare DOPO merge Wave 1 |
| 3 | **Ensemble a 3 modelli** — majority-of-3, outlier scartato e persistito ineligible, semaforo configurabile | `2026-07-12-three-model-ensemble.md` | Piano TDD completo | PRONTO, lanciare DOPO merge Wave 2 |
| 4 | **Vettore A — earnings chain** (consensus deterministico + transcript tone) | `2026-07-12-vettore-a-earnings-chain-brief.md` | Brief + discovery-first | Fase 0 lanciabile in parallelo dalla Wave 2 in poi |

## Perché quest'ordine

1. **Wave 1 prima di tutto**: senza forward return completi e multi-orizzonte, né il
   report shadow (Wave 2) né il gate del Vettore A (Wave 4) hanno un denominatore
   affidabile. È anche il piano più piccolo e a rischio zero (misurazione pura).
2. **Wave 2 prima della Wave 3**: il report shadow conferma (o smentisce) con dati
   live che deepseek è il terzo modello giusto — la Wave 3 lo assume dallo Stage 1
   (n=17). Se il report indica un candidato diverso, la Wave 3 cambia solo la
   selezione operatore, non il codice.
3. **Wave 2 e 3 toccano gli stessi file** (`sentiment.py`, `client.py`,
   `pg_store.py`): MAI in volo contemporaneamente. Wave 4 tocca file diversi
   (connectors/pead) e può correre in parallelo dalla Fase 0.
4. Il **pair swap glm+gpt-oss** (live dal 11/07) va valutato con la prima settimana
   di dati (fallback rate atteso <30% vs 75-80%): se il lunedì successivo il
   fallback resta alto, la priorità della Wave 3 sale.

## Regole per ogni lancio (valgono per tutte le wave)

- Un branch per wave, nome nel piano; **mai committare su main** o su branch di
  altri workstream (`stop-loss-redesign` è attivo).
- TDD stretto come da piano; full suite a fine wave: ammessi SOLO i 10 fallimenti
  pre-esistenti elencati in ogni piano.
- Niente deploy, niente migrazioni applicate, niente chiavi Redis toccate
  dall'agente: gli "Operator steps" in coda a ogni piano sono dell'operatore
  (review → merge → deploy → arm).
- Dopo ogni wave: review del branch (come per i deployment-fixes del 10/07) prima
  del merge.

## Prompt di lancio per wave (compilare la riga PIANO)

```
You are working in /home/stefano/Documents/Projects/Alembic (LLM algorithmic
trading system, paper trading). Read CLAUDE.md first.

Execute the implementation plan at PIANO task by task, in order, exactly as
written, using the superpowers:executing-plans skill (or
superpowers:subagent-driven-development if the plan's header recommends it).
The plan contains complete code and test code — do not improvise.

Hard rules:
- First action: create the branch named in the plan's Context, from main.
- Strict TDD: run each failing test, confirm the failure matches the plan's
  "Expected", implement, re-run. Never weaken a test.
- The "Operator steps/rollout" section is NOT yours: no deploy, no DB
  migrations applied, no Redis keys set, no merge to main.
- Tests: .venv/bin/pytest. Only the 10 pre-existing failures listed in the
  plan are acceptable at the end.
- If reality contradicts a plan step (an import, a signature, a mock target),
  follow the plan's inline fallback instruction; if truly stuck, stop and
  report rather than working around.

Final report: branch + commits, test counts per task, deviations with reasons,
confirmation that no operator step was executed.
```

Per la Wave 4 usare invece il kickoff prompt incluso nel brief (discovery-first,
STOP dopo la Fase 0 per review).

## Decisioni PO incorporate come assunzioni (revocabili)

- Provider event-driven: **FMP** (decisione roadmap #2) — già provato per ALPHA-A5.
- Universo S4: **large-cap invariato** (la #1 riguarda S7 small/mid, separata).
- Labeling QX-01: **in-house** (#4) — la coda `/labeling` prioritizza full-text dal
  10/07; obiettivo 150-200 label per sbloccare calibrazione e re-run Stage 1.
- Sleeve S4: resta 10% finché l'IC misurato non giustifica il gate P1-03/04.
