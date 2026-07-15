# Alembic Roadmap — Metodo di gestione (Wayfinder)

Testo di riferimento per tutte le sessioni (umane e agent) su come si gestisce la roadmap. Passarlo in chat a una nuova sessione, o leggerlo all'avvio. Source of truth enforced = GitHub issues, non checkbox nei plan doc.

La roadmap di Alembic è centralizzata su GitHub. NON si traccia lo stato dei
lavori nei plan doc markdown (driftavano: lavori DONE+merged con checkbox
vuote). Lo stato è enforced nelle issue.

## Source of truth

- **Map issue:** `#21` "Alembic Roadmap (Wayfinder map)" — label `wayfinder:map`.
  Il body è la roadmap vivente: Decisions-so-far, Fog, e la task list dei child.
- **Child:** `#22`-`#53` (una per lavoro aperto). Il body inizia con `Part of #21`.

## Regole

1. Ogni lavoro aperto = una child issue su `#21`. Mai una nuova checkbox in un `.md`.
2. "Done" = la child è CHIUSA, idealmente da una PR merged che contiene
   `closes #N` (GitHub la chiude da solo al merge). Non spuntare box a mano.
3. I plan doc in `docs/superpowers/plans/` sono **design spec** (il "come"), non
   tracker di stato. Linkano la child (`Part of #21`). `master-roadmap.md` = storico.
4. L'ordine di esecuzione è il grafo `blocked_by` (dipendenze native GitHub).
   Una ticket è eseguibile solo quando tutti i suoi blocker sono chiusi.

## Label

- **tier:** `tier0` (bloccante sistemico) .. `tier5` (backlog)
- **tipo:** `wayfinder:task` | `wayfinder:decision` | `wayfinder:backlog`
- **triage:** `ready-for-agent` (codice pronto) | `ready-for-human` (serve PO) | `needs-triage`
- **severità:** `critical` | `high` | `medium` | `pre-live-blocker` | `paper-monitoring`

## Operazioni (gh CLI)

- **Todo live:** `gh issue list --state open`
- **Frontier (prossimo lavoro):** child aperte SENZA `blocked_by` aperto E SENZA
  assignee, in ordine scaletta.
- **Claim:** `gh issue edit <n> --add-assignee @me`
- **Risolvi:** `gh issue comment <n> --body "<risultato>"`; `gh issue close <n>`
  + appendi puntatore nei Decisions-so-far di `#21`.
- **Aggiungi dipendenza:**
  `gh api --method POST repos/Jonbj/alembic/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`
  — `blocker-db-id` è l'**id di database** (`gh api .../issues/<n> --jq .id`), NON il numero `#N`.

## Grafo attuale (blocked_by)

```
QX-01(#30)         <- PO-4(#25)
QS-03(#35)         <- QX-01(#30)
Vettore-A(#37)     <- PO-1(#22), PO-2(#23)
S7-revival(#38)    <- PO-5(#26)
PO-6 flip S1(#27)  <- S1-ref(#33)
PO-7 pair swap(#28)<- Stage2(#34)
```

## Inizio sessione

`gh issue list --state open` è la tua todo. Scegli una child `ready-for-agent`
senza blocker, claim-ala (`--add-assignee @me`), lavorala, chiudila con
`closes #N` nella PR. Se serve una decisione PO, è `ready-for-human`:
NON lavorarla — prepara il contesto e fermati.

## Riferimenti

- Audit narrativo di origine: `docs/OPEN_WORK_AUDIT_2026-07-15.md` (snapshot, non tracker)
- Convenzioni: `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `CLAUDE.md` § Agent skills