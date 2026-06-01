# Frontend Code Review — Consolidated Report
*13 models reviewed · 2026-05-19*

---

## Scoring Summary

| Rank | Model | Score | Tier |
|------|-------|-------|------|
| 1 | qwen3-coder-next:cloud | **7.3 / 10** | Top |
| 2 | qwen3-coder-480b:cloud | **7.2 / 10** | Top |
| 3 | glm-5.1:cloud | **7.1 / 10** | Top |
| 4 | devstral-2:123b-cloud | **7.0 / 10** | High |
| 5 | ministral-3:14b-cloud | **6.9 / 10** | High |
| 6 | deepseek-v4-pro:cloud | **6.8 / 10** | Mid |
| 7 | nemotron-3-super:cloud | **6.7 / 10** | Mid |
| 8 | gemma4:31b-cloud | **6.5 / 10** | Mid |
| 9 | gemini-3-flash-preview:cloud | **6.4 / 10** | Mid |
| 10 | minimax-m2.7:cloud | **6.3 / 10** | Low |
| 11 | minimax-m2:cloud | **6.1 / 10** | Low |
| 12 | kimi-k2.6:cloud | **6.2 / 10** | Low |
| 13 | qwen3.5:cloud | **5.8 / 10** | Bottom |

Score range: 5.8–7.3. Spread of 1.5 points indicates moderate inter-model variance. All 13 models assigned Testing a flat 1/10, indicating universal agreement on the most critical gap.

---

## Issue Frequency Table

| Issue | Frequency | Severity | Models That Caught It |
|-------|-----------|----------|-----------------------|
| Zero test coverage | 13/13 | 🔴 Critical | All 13 |
| `strict: false` in tsconfig | 13/13 | 🔴 Critical | All 13 |
| XSS via unsanitized URL in `News.tsx` | 13/13 | 🔴 Critical | All 13 |
| Inline styles — Tailwind not used in JSX | 13/13 | 🟡 Important | All 13 |
| Incoherent dark/light theme (Backtest + Sidebar vs rest) | 13/13 | 🟡 Important | All 13 |
| `as any` cast in `Config.tsx` (3 occurrences) | 13/13 | 🟡 Important | All 13 |
| React Fragment without `key` in `News.tsx` | 12/13 | 🟡 Important | All except gemini-3-flash |
| Code duplication: `directionBadge`, `KPICard`, tab pattern | 12/13 | 🟡 Important | All except gemini-3-flash |
| No `React.lazy` / code splitting (10 pages loaded at boot) | 13/13 | 🔵 Nice-to-have | All 13 |
| No `useMemo` / `useCallback` — missing memoization | 13/13 | 🔵 Nice-to-have | All 13 |
| No `Error Boundary` | 13/13 | 🔵 Nice-to-have | All 13 |
| API error handling monolithic (no 401/404/500 distinction) | 11/13 | 🟡 Important | All except minimax-m2, minimax-m2.7 |
| Inconsistent API module pattern (single fn vs object) | 11/13 | 🔵 Nice-to-have | All except kimi-k2.6, qwen3.5 |
| No Zustand devtools middleware | 9/13 | 🔵 Nice-to-have | deepseek, devstral, glm-5.1, minimax-m2, minimax-m2.7, ministral-3, nemotron, qwen3-480b, qwen3-next |
| `Position` type fields as `string` needing `parseFloat` | 8/13 | 🟡 Important | devstral, glm-5.1, gemma4, kimi-k2.6, minimax-m2, minimax-m2.7, ministral-3, qwen3-480b, qwen3-next |
| API key stored in `localStorage` (XSS-readable) | 6/13 | 🟡 Important | glm-5.1, gemini-flash, gemma4, kimi-k2.6, ministral-3, qwen3.5 |
| No CSRF token on mutation endpoints | 5/13 | 🟡 Important | glm-5.1, minimax-m2, minimax-m2.7, nemotron, ministral-3 |
| No URL encoding / `URLSearchParams` in some API modules | 3/13 | 🔵 Nice-to-have | glm-5.1, kimi-k2.6, ministral-3 |
| No table virtualization for large datasets | 2/13 | 🔵 Nice-to-have | glm-5.1, ministral-3 |
| CSS variables incomplete (missing `--card-bg`, `--card-border`) | 1/13 | 🔵 Nice-to-have | glm-5.1 only |
| `mode` persistence could cause backend/frontend desync offline | 2/13 | 🔵 Nice-to-have | glm-5.1, ministral-3 |

---

## Common Patterns (≥ 7/13 models)

### 1. Zero Test Coverage — 13/13 models

**What it is:** No `.test.ts`, `.spec.ts`, or `__tests__/` directory exists anywhere in the frontend codebase.

**Why it matters:** This is a financial trading dashboard that triggers kill switches, mode changes (paper → semi-auto → full-auto), and P&L calculations. A bug in the store, API client, or a utility function (`fmt()`, `pct()`, `directionBadge()`) can silently produce incorrect financial output. Every model assigned Testing **1/10** — the only unanimous score across all 13 reviews.

**Concrete fix:**
```bash
npm install -D vitest @testing-library/react @testing-library/user-event jsdom
```
Minimum test surface:
- `src/store/index.ts` — `setMode`, `setApiKey`, `setKillswitch`, `partialize` persistence
- `src/api/client.ts` — happy path, 401 path, 500 path, API key injection
- `src/pages/Admin.tsx` and `src/pages/Backtest.tsx` — rendering, loading/error states
- Utility functions: `fmt()`, `pct()`, `directionBadge()`, sentiment filtering

---

### 2. `strict: false` in `tsconfig.app.json` — 13/13 models

**What it is:** `"strict": false` disables null/undefined checks, implicit `any`, strict function types.

**Why it matters:** In a financial context, `parseFloat(undefined)` returns `NaN` and propagates silently through P&L calculations. With strict off, the compiler does not catch this class of bug at all. High-polarity/low-confidence signals could be miscalculated without a compile-time error.

**Concrete fix:**
```json
// tsconfig.app.json
{
  "compilerOptions": {
    "strict": true
  }
}
```
After enabling, the `Config.tsx` `as any` casts will surface as errors — fix them by defining a `ConfigResponse` interface:
```tsx
interface ConfigResponse {
  symbols: { watchlist: string[] }
  risk: { portfolio_drawdown: number; stop_loss: number }
}
```
Replace `fetchConfig` return type `Record<string, unknown>` with `ConfigResponse`.

---

### 3. XSS via unsanitized URL in `News.tsx` — 13/13 models

**What it is:** `src/pages/News.tsx` renders API-provided URLs directly into `<a href>`:
```tsx
<a href={item.url} target="_blank" rel="noreferrer">{item.url}</a>
```
If the database or API is compromised and returns `javascript:alert(document.cookie)`, the browser executes it on click.

**Why it matters:** An attacker who can write a malicious URL into the news feed (via a compromised data source or SSRF into the backend) can execute arbitrary JavaScript in the user's browser session, stealing the API key stored in `localStorage`.

**Concrete fix:**
```tsx
function safeUrl(url: string): string | undefined {
  try {
    const parsed = new URL(url)
    if (parsed.protocol === 'https:' || parsed.protocol === 'http:') return url
  } catch {}
  return undefined
}

// In JSX:
const href = safeUrl(item.url)
{href ? <a href={href} target="_blank" rel="noreferrer">{item.url}</a> : <span>{item.url}</span>}
```

---

### 4. Inline Styles — Tailwind CSS Installed but Unused — 13/13 models

**What it is:** `@tailwindcss/vite` is in `vite.config.ts` and `@import "tailwindcss"` is in `index.css`, but **zero Tailwind utility classes** appear in any JSX file. All styling is via `style={{...}}` objects.

**Why it matters:** Style objects are serialized into the JS bundle (larger bundle), prevent browser CSS caching, make JSX unreadable (hundreds of characters of inline style per component), and make global theming impossible without a full rewrite.

**Concrete fix (example migration):**
```tsx
// Before:
<div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>

// After:
<div className="flex gap-4 mb-6 flex-wrap">
```
Migrate page by page, starting with the most-visited (`Overview.tsx`, `Signals.tsx`).

---

### 5. Incoherent Dark/Light Theme — 13/13 models

**What it is:** `Backtest.tsx` and `Sidebar.tsx` use a dark theme (`background: #1e293b`, white text, `border: #334155`). All other pages (`Overview`, `Signals`, `Trading`, `Performance`, `News`, `LLM`, `Config`, `Admin`) use a light theme (`background: #f8fafc`, `var(--text-muted)`).

**Why it matters:** Users navigating between Backtest and other pages experience a jarring visual switch. No global design system exists — CSS variables `--blue`, `--green`, `--red` are defined in `index.css` but `--card-bg`, `--card-border`, etc. are not, so each page invents its own colors inline.

**Concrete fix:** Pick one theme (dark is more appropriate for a trading dashboard). Define a complete token set in `index.css`:
```css
:root {
  --bg-primary: #0f172a;
  --bg-card: #1e293b;
  --border: #334155;
  --text-primary: #f1f5f9;
  --text-muted: #94a3b8;
  --blue: #3b82f6;
  --green: #22c55e;
  --red: #ef4444;
}
```
Then migrate inline colors to these variables during the Tailwind migration.

---

### 6. `as any` cast in `Config.tsx` — 13/13 models

**What it is:** Three `as any` casts in `src/pages/Config.tsx`:
```tsx
const symbols = (cfg as any)?.symbols?.watchlist ?? []
setDrawdown(((cfg as any)?.risk?.portfolio_drawdown ?? 0.1) * 100)
setStopLoss((cfg as any)?.risk?.stop_loss ?? 0.05)
```
Root cause: `fetchConfig` returns `Record<string, unknown>` with no typed shape.

**Why it matters:** If the backend changes `symbols` to `assets` or `risk.stop_loss` to `risk.stopLoss`, the frontend silently uses the fallback value `0.05` (a 5% stop loss) instead of the configured value. No compile-time error. This is a risk management misconfiguration that could go undetected.

**Concrete fix:** Define and use `ConfigResponse` (see fix in issue 2).

---

### 7. React Fragment without `key` in `News.tsx` — 12/13 models

**What it is:** In `src/pages/News.tsx`:
```tsx
{news.map((item: NewsItem) => (
  <>
    <tr key={item.id}>...</tr>
    {expanded === item.id && <tr>...</tr>}
  </>
))}
```
The `<>` shorthand Fragment does not accept a `key` prop. React emits a warning and reconciliation may produce incorrect DOM diffs.

**Concrete fix:**
```tsx
import { Fragment } from 'react'

{news.map((item: NewsItem) => (
  <Fragment key={item.id}>
    <tr>...</tr>
    {expanded === item.id && <tr>...</tr>}
  </Fragment>
))}
```

---

### 8. Code Duplication — 12/13 models

**What it is:** Several identical or near-identical utilities and components scattered across pages:
- `directionBadge()` — identical in `src/pages/Overview.tsx` and `src/pages/Signals.tsx`
- `polarityBadge()` — similar in `src/pages/LLM.tsx` and `src/pages/Performance.tsx`
- `KPICard` — light variant in `Overview.tsx`, dark variant in `Backtest.tsx`, incompatible implementations
- Tab pattern — identical structure in `src/pages/Trading.tsx` and `src/pages/LLM.tsx`

**Concrete fix:** Extract to `src/components/shared/`:
```
src/components/shared/
├── DirectionBadge.tsx     — single source for BUY/SELL/HOLD badge
├── PolarityBadge.tsx      — bullish/bearish/neutral
├── KPICard.tsx            — accepts `theme?: 'light' | 'dark'` prop
└── TabButton.tsx          — reusable tab with active state
```

---

## Top Performer Differentiators

**Top 3 by score:** qwen3-coder-next (7.3), qwen3-coder-480b (7.2), glm-5.1 (7.1)
**Bottom 3 by score:** qwen3.5 (5.8), minimax-m2 (6.1), kimi-k2.6 (6.2)

### What top performers caught that bottom performers missed

#### 1. CSRF vulnerability on mutation endpoints (caught by glm-5.1, ministral-3; missed by qwen3.5, minimax-m2, kimi-k2.6)

glm-5.1 explicitly noted:
> "Le mutation endpoints (kill switch, mode change, config update) sono vulnerabili senza token CSRF se l'API key è nel localStorage."

The kill switch endpoint and mode-change endpoint are state-mutating requests. If the API key is in `localStorage` and there is no CSRF token, a crafted cross-origin page can trigger a kill switch activation or mode escalation by tricking the user's browser. Bottom performers either ignored this or mentioned only the XSS vector.

#### 2. API key in `localStorage` is XSS-readable (caught by glm-5.1, gemini-flash, gemma4, kimi-k2.6, ministral-3; missed by minimax-m2, minimax-m2.7, deepseek, nemotron, devstral)

glm-5.1 made the causal chain explicit:
> "Qualsiasi script XSS nel dominio può leggerla. Considerare `sessionStorage` o httpOnly cookie."

The XSS in `News.tsx` and the `localStorage` storage create a compound attack: XSS → extract API key → authenticate as user → execute trades. The bottom performers mentioned XSS but did not connect it to API key exposure.

#### 3. `URLSearchParams` missing in some API modules — string interpolation risk (caught by glm-5.1, kimi-k2.6; missed by 11 others)

glm-5.1 specifically noted that `signals.ts` uses string interpolation for query string construction instead of `URLSearchParams`, which is used correctly in `backtest.ts`. This creates inconsistency and risk of URL injection if ticker symbols contain special characters (e.g., `BRK.B`, `BRK/B`). In a financial ticker context, this is a real edge case.

```tsx
// Vulnerable pattern (signals.ts):
apiFetch<Signal[]>(`/api/signals?ticker=${ticker}&limit=${limit}`)

// Safe pattern (backtest.ts):
const params = new URLSearchParams({ ticker, limit: String(limit) })
apiFetch<Signal[]>(`/api/signals?${params}`)
```

#### 4. Table virtualization for large datasets (caught by glm-5.1 only; missed by all 12 others)

glm-5.1 identified that tables with hundreds of rows (signals, backtest results) render all DOM nodes simultaneously — a real performance problem in a live trading dashboard where signal tables can grow unboundedly.

**Suggested fix:** `react-virtual` or `@tanstack/react-virtual` for `Signals.tsx` and `Backtest.tsx` tables.

#### 5. Granularity of concrete code snippets

Top performers provided exact file paths and line-level code in their fixes. For example, glm-5.1 quoted:
```tsx
// Config.tsx:16-18 — 3 cast `as any` that elude the type system
const symbols = (cfg as any)?.symbols?.watchlist ?? []
setDrawdown(((cfg as any)?.risk?.portfolio_drawdown ?? 0.1) * 100)
setStopLoss((cfg as any)?.risk?.stop_loss ?? 0.05)
```
And provided the exact replacement interface. Bottom performers (qwen3.5, minimax-m2, kimi-k2.6) mentioned the same issues but without file-level attribution, making the fixes harder to act on.

#### 6. `mode` persistence desync risk (caught by glm-5.1, ministral-3; missed by 11 others)

glm-5.1 noted that persisting `mode` in `localStorage` can cause a scenario where the backend switches the system to `halted` (e.g., circuit breaker triggered) while the user is offline. On reload, the frontend restores `mode: 'paper'` from localStorage and does not reflect the backend's `halted` state until the next API poll. For a kill-switch system, this gap matters.

---

## Severity Breakdown

### Critical — fix before deploy

1. **Zero test coverage** — all 13 models, Testing 1/10
   - Files to test: `src/store/index.ts`, `src/api/client.ts`, `src/pages/Admin.tsx`, `src/pages/Backtest.tsx`
   - No test runner configured; add `vitest` + `@testing-library/react`

2. **`strict: false` in `tsconfig.app.json`** — all 13 models, TypeScript 5-6/10
   - One-line fix: `"strict": true`
   - Cascading fix: define `ConfigResponse` interface, eliminate 3 `as any` casts in `Config.tsx`

3. **XSS via unsanitized URL in `src/pages/News.tsx`** — all 13 models
   - Validate `http:`/`https:` protocol before rendering `<a href>`
   - Compound risk: API key in `localStorage` is exfiltrable via XSS

### Important — fix in next sprint

4. **Inline styles — Tailwind not used in JSX** — all 13 models, UI 4-5/10
   - Migrate page by page; start with `Overview.tsx` and `Signals.tsx`

5. **Dark/light theme incoherence** — all 13 models
   - Standardize on dark theme; define full CSS token set in `index.css`

6. **`as any` in `Config.tsx`** — all 13 models (also covered under Critical #2)
   - Define `ConfigResponse` type, retype `fetchConfig` return

7. **Fragment without `key` in `News.tsx`** — 12/13 models
   - Replace `<>` with `<Fragment key={item.id}>`; one-line fix

8. **Code duplication** — 12/13 models
   - Extract `DirectionBadge`, `KPICard`, `TabButton`, `PolarityBadge` to `src/components/shared/`

9. **API error handling monolithic** — 11/13 models
   - Differentiate 401 (redirect to auth), 429 (rate limit toast), 500 (error banner) in `src/api/client.ts`

10. **`Position` fields as `string` requiring `parseFloat` per render** — 8/13 models
    - Normalize in `src/api/positions.ts`: convert `qty`, `market_value`, `unrealized_pl`, `unrealized_plpc`, `avg_entry_price`, `current_price` to `number` at API boundary

11. **API key in `localStorage`** — 6/13 models
    - Consider `sessionStorage` to limit persistence window; or implement httpOnly cookie auth on backend

12. **CSRF on mutation endpoints** — 5/13 models
    - Add CSRF token to `apiFetch` for non-GET requests; or confirm SameSite cookie policy on backend

### Nice-to-have — backlog

13. **No `React.lazy` / code splitting** — all 13 models
    - 10 pages loaded at boot; add `React.lazy` + `Suspense` in `src/App.tsx`

14. **No `useMemo` / `useCallback`** — all 13 models
    - `cumPnL` in `Performance.tsx`, bucket/signal filtering in `Backtest.tsx` and `Signals.tsx`

15. **No Error Boundary** — all 13 models
    - Add global `<ErrorBoundary>` in `App.tsx`; prevents white-screen crashes

16. **Inconsistent API module pattern** — 11/13 models
    - Standardize all API modules on `backtest.ts` object pattern with `URLSearchParams`

17. **No Zustand devtools** — 9/13 models
    - Add `devtools` middleware from `zustand/middleware` for debug in development

18. **Missing `URLSearchParams` in `signals.ts`** — 3/13 models (glm-5.1, kimi-k2.6, ministral-3)
    - Risk: ticker symbols with special characters break query strings

19. **Table virtualization** — 1/13 models (glm-5.1)
    - Add `@tanstack/react-virtual` for unbounded-length tables in `Signals.tsx` and `Backtest.tsx`

20. **`mode` localStorage desync** — 2/13 models (glm-5.1, ministral-3)
    - On app init, sync `mode` from backend before using persisted value

---

## Prioritized Roadmap

### Phase 1 — Pre-deploy (1–2 days)

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 1 | Enable `strict: true` in tsconfig | `tsconfig.app.json` | 5 min |
| 2 | Define `ConfigResponse` interface, remove 3 `as any` casts | `src/pages/Config.tsx`, `src/api/config.ts` | 1 hr |
| 3 | Fix XSS: validate protocol before rendering `<a href>` in News | `src/pages/News.tsx` | 30 min |
| 4 | Fix Fragment key warning in News | `src/pages/News.tsx` | 5 min |
| 5 | Setup Vitest + RTL; write store tests | `src/store/index.test.ts` | 3 hr |
| 6 | Write API client tests (happy path, 401, 500) | `src/api/client.test.ts` | 2 hr |

**Phase 1 total: ~1 day**

---

### Phase 2 — Sprint 1 (1 week)

| # | Task | File(s) | Effort |
|---|------|---------|--------|
| 7 | Extract shared components: `DirectionBadge`, `KPICard`, `TabButton`, `PolarityBadge` | `src/components/shared/` | 4 hr |
| 8 | Standardize API modules to `backtestApi` object pattern + `URLSearchParams` | `src/api/*.ts` (8 modules) | 4 hr |
| 9 | Differentiate HTTP error codes in `apiFetch` (401/429/500) | `src/api/client.ts` | 2 hr |
| 10 | Normalize `Position` string fields to `number` in API layer | `src/api/positions.ts` | 1 hr |
| 11 | Migrate `Overview.tsx` and `Signals.tsx` inline styles to Tailwind | `src/pages/Overview.tsx`, `Signals.tsx` | 1 day |
| 12 | Standardize on dark theme; complete CSS token set in `index.css` | `src/index.css` | 2 hr |
| 13 | Add `React.lazy` + `Suspense` for all 10 page routes | `src/App.tsx` | 1 hr |
| 14 | Add global `<ErrorBoundary>` | `src/App.tsx`, `src/components/ErrorBoundary.tsx` | 1 hr |
| 15 | Add `useMemo` for `cumPnL` in Performance, filtered data in Backtest/Signals | `src/pages/Performance.tsx`, `Backtest.tsx`, `Signals.tsx` | 2 hr |
| 16 | Add Zustand devtools middleware | `src/store/index.ts` | 30 min |

**Phase 2 total: ~5 days**

---

### Phase 3 — Backlog

| # | Task | File(s) | Notes |
|---|------|---------|-------|
| 17 | Migrate remaining 8 pages inline styles to Tailwind | `src/pages/*.tsx` | Largest effort, low urgency |
| 18 | CSRF token for mutation endpoints | `src/api/client.ts` + backend | Requires backend coordination |
| 19 | Move API key from `localStorage` to `sessionStorage` or httpOnly cookie | `src/store/index.ts` + backend | Requires backend coordination |
| 20 | Table virtualization for Signals and Backtest | `src/pages/Signals.tsx`, `Backtest.tsx` | Only needed if rows > 500 |
| 21 | Sync `mode` from backend on app init (override localStorage) | `src/App.tsx` | Prevents desync after emergency halt |
| 22 | Add `useCallback` for handlers passed to child components | Multiple pages | Low impact until child components are memoized |

---

## Appendix: Area Score Averages Across All 13 Models

| Area | Avg Score | Min | Max |
|------|-----------|-----|-----|
| Architecture & Structure | 7.9 / 10 | 6 | 9 |
| TypeScript / React Quality | 5.5 / 10 | 5 | 7 |
| Zustand State Management | 8.0 / 10 | 7 | 9 |
| API Client Layer | 7.1 / 10 | 6 | 8 |
| UI / UX | 4.8 / 10 | 4 | 6 |
| Performance | 5.1 / 10 | 4 | 6 |
| Testing | **1.0 / 10** | 1 | 1 |
| Best Practices & Security | 6.0 / 10 | 5 | 7 |

Architecture and State Management are genuine strengths. Testing is a unanimous failure. UI/UX is the second weakest area. The gap between Architecture (7.9) and Testing (1.0) is the defining characteristic of this codebase: excellent structural decisions undermined by an absence of verification.
