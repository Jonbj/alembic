# Frontend Code Review — Tournament Task

**Branch:** `feat/frontend`
**Scope:** SPA React + Vite + TypeScript + Tailwind + shadcn/ui

## Compito

Fai una **code review esaustiva** del codice frontend in questo repository. Il codice si trova nel branch `feat/frontend` (worktree corrente).

## Aree di analisi richieste

1. **Architettura & Struttura**
   - Organizzazione delle directory
   - Separazione dei concerns (componenti, store, API, pages)
   - Scalabilità dell'architettura

2. **Qualità del codice TypeScript/React**
   - Type safety e uso dei generics
   - Hook patterns (useEffect, useMemo, useCallback)
   - Component composition

3. **Gestione dello stato**
   - Zustand store design
   - Derived state
   - Async state management

4. **API Client Layer**
   - Fetch patterns
   - Error handling
   - Loading states

5. **UI/UX**
   - Tailwind usage
   - shadcn/ui component integration
   - Responsive design
   - Accessibility

6. **Performance**
   - Bundle size considerations
   - Memoization
   - Lazy loading

7. **Testing**
   - Test coverage
   - Testing patterns (unit, integration, e2e)

8. **Best Practices & Anti-pattern**
   - SOLID principles
   - DRY
   - Security (XSS, input sanitization)

## Output atteso

Genera un report di code review dettagliato che includa:
- **Punteggio complessivo** (1-10)
- **Punteggi per area** (1-10)
- **Criticità trovate** (blocker, warning, suggestion)
- **Raccomandazioni concrete** con esempi di codice
- **Confronto con best practices** del settore

Salva il report in `.claude/frontend_review.md`.

## Post-review

Dopo aver completato la review, esegui:
```bash
python ../../scripts/model_tournament.py collect
```
