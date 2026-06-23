# Frontend Dashboard — Design Spec
**Data:** 2026-05-18  
**Versione:** 1.0.0  
**Status:** Approvato

---

## 1. Obiettivo

Aggiungere un frontend web al sistema Alembic che combini monitoring (sola lettura) e controllo (azioni admin). L'interfaccia è destinata all'operatore del sistema (uso personale/single-user).

---

## 2. Approccio architetturale

**SPA React + FastAPI esteso (Approccio A).**

Il frontend React consuma le API FastAPI esistenti e 6 nuovi endpoint aggiunti al backend. Nessun servizio intermedio. In produzione, `vite build` genera una cartella `frontend/dist/` che FastAPI serve con `StaticFiles` — un unico processo, nessuna infrastruttura aggiuntiva.

---

## 3. Stack tecnico

| Categoria | Libreria | Versione |
|-----------|----------|----------|
| Framework | React | 18 |
| Linguaggio | TypeScript | 5.x |
| Build tool | Vite | 5.x |
| Routing | React Router | v6 |
| Data fetching | TanStack Query | v5 |
| Styling | Tailwind CSS | v3 |
| Componenti | shadcn/ui | latest |
| Grafici P&L / IC | Recharts | 2.x |
| Grafici prezzo | Lightweight Charts (TradingView) | 4.x |
| Stato globale | Zustand | 4.x |

---

## 4. Design visivo

**Stile:** Clean Finance — sfondo bianco/grigio chiaro (`#f8fafc`), tipografia sans-serif, accenti blu (`#3b82f6`) e verde (`#16a34a`). Ispirato a Bloomberg Terminal light.

**Navigazione:** Sidebar fissa a sinistra (~160px) con icona + etichetta testuale per ogni sezione. La sezione attiva ha sfondo blu. In fondo alla sidebar: badge modalità operativa (paper/full_auto/halted) con colore semantico.

---

## 5. Struttura pagine

### 5.1 Overview (home)
- 4 KPI card: Net P&L mese corrente, posizioni aperte (count + ticker), IC a 7 giorni, segnali oggi (BUY/SELL/HOLD count)
- Grafico a barre P&L mensile (ultimi 6 mesi)
- Mini-tabella posizioni aperte con P&L non realizzato
- Tabella ultimi segnali (10 righe: ticker, direction, confidence, fonte, ora)
- Header con badge alert (es. "2 segnali in attesa") e pulsante kill-switch rapido

### 5.2 Segnali
- Tabella completa segnali attivi in Redis
- Colonne: ticker, direction (▲/▼), confidence, source, EMA filter result, timestamp
- Filtri: ticker, direction, fonte
- Badge colorati per direction: verde BUY, rosso SELL, grigio HOLD

### 5.3 Trading
- **Tab "Posizioni aperte"**: dati live Alpaca — ticker, qty, prezzo medio, valore corrente, P&L non realizzato (€/$), P&L%
- **Tab "Storico ordini"**: ultimi 100 ordini — ticker, side (buy/sell), qty, prezzo eseguito, status, timestamp; P&L realizzato per trade dove disponibile
- Entrambe le tab si aggiornano ogni 60 secondi

### 5.4 Performance
- **Grafici IC/ICIR** nel tempo (linea, dati da PG)
- **Grafico P&L cumulativo** (linea)
- **Grafico prezzo** per ticker selezionato — candlestick con TradingView Lightweight Charts, overlay con i segnali BUY/SELL come marker
- Selettore ticker e range temporale (1M / 3M / 6M / 1Y)
- Tabella accuracy per modello (FinBERT, Opus, Qwen, DeepSeek) con IC individuale

### 5.5 News
- Tabella news ingested dal DB: titolo, fonte (GDELT/MarketAux/Alpaca), ticker associato, sentiment assegnato, confidence, timestamp
- Filtri: ticker, fonte, data range, sentiment
- Click su una riga espande i dettagli dell'articolo e le risposte LLM associate
- **Nota implementativa:** richiede una nuova tabella PG `news_log` (migrazione `006_add_news_log.sql`) e la scrittura da `IngestionWorker` al momento del fetch. Senza questa tabella la sezione mostrerebbe solo `sentiment_signals` senza titolo/URL.

### 5.6 LLM
- **Tab "Feedback modelli"**: per ogni articolo processato — testo troncato, risposta di ogni modello (direction + reasoning), sentiment finale, divergenza ensemble (`ensemble_std` da `sentiment_signals`, dettaglio per-modello da `llm_responses`)
- **Tab "Pesi ensemble"**: pesi correnti vs suggerimento con diff visiva, pulsante "Approva" (richiede API key), campo note, data scadenza suggerimento
- Filtri: modello, ticker, data
- **Nota implementativa:** il dettaglio per-modello richiede una nuova tabella PG `llm_responses` (migrazione `007_add_llm_responses.sql`) e la scrittura dall'`EnsembleWorker` prima del merge. Senza di essa, il tab mostra solo il dato aggregato da `sentiment_signals` (`model_id`, `reasoning`, `ensemble_std`, `fallback_used`).

### 5.7 Config
- Form per i parametri runtime:
  - Simboli monitorati (lista editabile) — scrive su `config/trading.yaml`
  - `MAX_DRAWDOWN_PCT` (slider 1%–20%) — scrive su `config/trading.yaml`
  - Stop-loss threshold — scrive su `config/trading.yaml`
  - Costo per modello (per audit budget) — read-only (da `config.MODEL_COSTS`)
- Salvataggio via `POST /api/config` (richiede API key) — il backend aggiorna `config/trading.yaml` e ricarica la configurazione; `EMA_PERIOD` è una costante compile-time in `execution.py` e non è editabile a runtime
- **Nota implementativa:** la rilettura di `trading.yaml` a caldo richiede un meccanismo di reload (signal SIGHUP o riavvio Celery worker); da definire in implementazione
- Sezione read-only con versione sistema, uptime, last execution cycle

### 5.8 Admin
- **Pulsante kill-switch** grande e prominente con dialog di conferma ("Sei sicuro? Questa azione ferma tutti gli ordini.")
- **Selettore modalità** operativa: `backtest` / `paper` / `semi_auto` / `full_auto` / `halted` con descrizione di ogni stato
- Log delle ultime attivazioni kill-switch con timestamp e motivo
- Entrambe le azioni richiedono API key

### 5.9 Auto-improve *(Fase 2 — placeholder)*
- Sezione visibile in sidebar ma contrassegnata "Coming soon"
- Conterrà: trigger manuale backtest, visualizzazione risultati A/B test, approvazione modelli aggiornati
- Non implementata in questa fase

---

## 6. Nuovi endpoint FastAPI

Tutti i GET sono pubblici (nessuna API key). Il POST `/api/config` richiede API key.

| Endpoint | Metodo | Fonte | Risposta |
|----------|--------|-------|----------|
| `/api/positions` | GET | Alpaca client | Lista posizioni aperte con P&L |
| `/api/orders` | GET | Alpaca client | Storico ordini (query param: `limit`, `status`) |
| `/api/news/recent` | GET | PostgreSQL `news_log` *(nuova tabella)* | Lista news (query param: `limit`, `ticker`, `source`) |
| `/api/llm/feedback` | GET | PostgreSQL `llm_responses` *(nuova tabella)* + `sentiment_signals` | Risposte LLM per articolo (query param: `limit`, `ticker`) |
| `/api/performance/pnl` | GET | PostgreSQL | P&L aggregato per mese + cumulativo |
| `/api/config` | GET + POST | Redis | Lettura e scrittura parametri runtime |

---

## 7. Aggiornamento dati (polling)

Nessun WebSocket. TanStack Query gestisce il polling con `refetchInterval`:

| Dati | Intervallo |
|------|-----------|
| Modalità + killswitch status | 15 secondi |
| Segnali, posizioni, KPI overview | 60 secondi |
| News, storico ordini, LLM feedback | 5 minuti |
| Performance / grafici storici | On-demand (click utente) |

In caso di errore API: 3 retry con backoff esponenziale, poi errore inline nella sezione interessata (non blocca il resto della UI).

---

## 8. Autenticazione frontend

- Nessun sistema di login dedicato
- L'utente inserisce l'API key una volta in un modale "Impostazioni" (icona in fondo alla sidebar)
- La key viene salvata in `localStorage` e allegata come header `X-API-Key` a tutte le chiamate admin
- Le pagine read-only (Overview, Segnali, Trading, Performance, News) funzionano senza key
- Se una chiamata admin restituisce 401, appare un banner "API key non valida" con link a Impostazioni

---

## 9. Struttura cartelle

```
frontend/
├── src/
│   ├── api/                  # client functions (signals.ts, positions.ts, …)
│   ├── components/
│   │   ├── ui/               # shadcn/ui (Button, Card, Badge, Table, Dialog, …)
│   │   ├── layout/           # Sidebar.tsx, Layout.tsx, ModeBadge.tsx
│   │   └── charts/           # PriceChart.tsx, PnLChart.tsx, IcChart.tsx
│   ├── pages/
│   │   ├── Overview.tsx
│   │   ├── Signals.tsx
│   │   ├── Trading.tsx
│   │   ├── Performance.tsx
│   │   ├── News.tsx
│   │   ├── LLM.tsx
│   │   ├── Config.tsx
│   │   ├── Admin.tsx
│   │   └── AutoImprove.tsx   # placeholder
│   ├── hooks/                # useSignals.ts, usePositions.ts, usePnl.ts, …
│   ├── store/                # Zustand: mode, killswitchActive, apiKey
│   ├── main.tsx
│   └── App.tsx
├── index.html
├── tailwind.config.ts
├── vite.config.ts
└── package.json
```

---

## 10. Deploy

**Sviluppo:**
```bash
# Backend
uvicorn src.api.main:app --reload --port 8000

# Frontend (in frontend/)
npm run dev  # porta 5173, proxy /api → localhost:8000
```

**Produzione:**
```bash
cd frontend && npm run build   # genera frontend/dist/
```
FastAPI monta `frontend/dist/` con `StaticFiles(directory="frontend/dist", html=True)` — nessun nginx aggiuntivo.

---

## 11. Testing

- **Vitest + React Testing Library** per componenti critici: KillSwitchButton (dialog conferma), WeightApprovalForm (validazione), ApiKeyModal
- Nessun E2E in questa fase (tool personale, backend già coperto da 594 test)
- Typecheck con `tsc --noEmit` nel CI

---

## 12. Fuori scope (questa fase)

- Auto-improve interface (Fase 2)
- `semi_auto` mode per-order approval UI (già deferred a Fase B/C lato backend)
- Notifiche push / WebSocket
- Multi-utente / ruoli
- Mobile responsive (ottimizzato per desktop)
