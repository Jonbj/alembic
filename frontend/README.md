# Alembic — Operator Frontend

React + TypeScript + Vite single-page app — the operator monitoring/control surface for the Alembic LLM trading system. Talks to the FastAPI backend (`src/api/`, default `http://localhost:8001`).

**For the full operator guide (API surfaces, page inventory, runbooks, authorization status) see [`docs/FRONTEND_OPERATOR_GUIDE.md`](../docs/FRONTEND_OPERATOR_GUIDE.md).** This README covers the frontend build/dev workflow only.

## Stack

- React 19 + TypeScript + Vite 8
- Tailwind CSS 4 (`@tailwindcss/vite`)
- TanStack Query (server state) + TanStack Virtual (long lists)
- Recharts (P&L/equity charts) + lightweight-charts (price)
- React Router, lucide-react icons, class-variance-authority

## Pages (`src/pages/`)

Overview, Signals, Strategies, Trading, Performance, News, LLM, AutoImprove, Operations, Quality, Labeling, Validation, Backtest, Docs, SystemLog, Admin, Config, Login.

Trace model is shared across pages: `News -> Signal -> Decision -> Order -> Performance` (Trace drawer shows the full chain with `origin_strategy` for non-news orders).

## Development

```bash
cd frontend
npm install
npm run dev        # Vite dev server with HMR
npm run build      # tsc -b && vite build -> dist/
npm run lint       # eslint
npm run preview    # preview the production build
```

The backend URL is configured via Vite env (`VITE_API_URL`); defaults to the local compose backend. All operator API endpoints require the `X-API-Key` header (`ADMIN_API_KEY`).

## Deployment (compose)

The frontend is built into a static bundle and served by nginx in the `frontend` compose service (`build: ./frontend`, multi-stage Dockerfile). It is the primary monitoring surface — Grafana is no longer part of the local compose stack. After frontend changes: `docker compose build frontend && docker compose up -d frontend`.

## Notes

- Authorization: controlled paper trading is running; `GLOBAL_LIVE_PROMOTION_ENABLED = False` (paper, not live money). See the operator guide §4.
- The legacy `/trades` and `/dashboard` routes redirect to `Trading` and `Overview` respectively (`Trades.tsx` / `DashboardPage.tsx` removed).
- NUMERIC columns from Postgres are serialized as JSON numbers by the backend (since 2026-07-09) — frontend `.toFixed()` calls are safe; the old Decimal-as-string crash on the Quality page is resolved.