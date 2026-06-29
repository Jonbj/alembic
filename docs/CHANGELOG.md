# CHANGELOG — Alembic Trading System

Registro delle modifiche rilevanti al sistema (decisioni architetturali, nuove strategie, configurazioni).

---

## 2026-06-29

### Portfolio Scheduler — Anti-stale-ranker-sell guard
- **Bug fix**: posizioni con segnale fresco positivo venivano vendute quando `CrossSectionalRanker` ritornava `{}` pesi per vincolo `min_stocks=2` (es. solo 1 segnale a forza positiva tra i 2 che passano il gate assoluto). L'orchestratore interpretava `merged_weights={}` come "sell all" per le posizioni correnti.
  - Root cause: il gate `abs(score) >= threshold` ammette segnali negativi (es. MU -0.4185) che passano il gate ma vengono scartati dal ranker long-only (`strength = score*confidence <= 0`). Con 1 candidato positivo < `min_stocks=2` il ranker ritorna vuoto.
  - Fix: nuovo `_fresh_signal_protected_symbols()` — protegge le posizioni aperte con segnale fresco >= threshold da SELL senza attributazione di strategy.
  - 8 test TDD aggiunti in `tests/workers/test_protected_sell.py`.

### LLM Ensemble
- **Qwen3.5 sostituito da GLM-5.2** nel sentiment ensemble news. Motivo: Qwen3.5 estraeva ticker in modo troppo aggressivo (es. MU da notizia macro Iran/US deal); GLM-5.2 è il flagship Zhipu AI con reasoning long-horizon migliore per analisi macroeconomica.
- Ensemble attivo: Kimi K2.6 + GLM-5.2 (2 modelli) — entrambi attivi, confermato da log `worker-inference`
- Fallback weights performance worker aggiornati: `{kimi-k2.6:cloud: 0.50, glm-5.2:cloud: 0.50}`
- GLM-5.2 e Kimi K2.6 in timeout da 20:47 UTC per Ollama cloud overload — FinBERT fallback attivo fino a disponibilità Ollama

---

## 2026-06-17

### Documentazione
- Riorganizzazione completa docs/: archiviate ~25 file obsoleti in `docs/archive/`
- Aggiornati: ARCHITECTURE.md, strategies.md, operations.md, API.md, CLAUDE.md, DECISIONS.md
- Creati: docs/strategies/s7-pead.md, docs/CHANGELOG.md, docs/llm-config.md

---

## 2026-06-16

### Modifiche
- **Worker split**: separato `worker-inference` (concurrency=1, queue `inference`) da `worker` (concurrency=4, queue `celery`) per isolare FinBERT/Ollama
- **Redis cycle lock**: aggiunto `SET portfolio:cycle:lock NX EX 840` in `portfolio_scheduler.py` per prevenire run concorrenti
- **Hold minimum 30 min**: filtro SELL su simboli comprati negli ultimi 30 minuti (previene roundtrip S4→S1)
- **FinBERT int8 quantization**: `torch.quantization.quantize_dynamic` applicato al load di FinBERT (~50% RAM reduction)
- **Daily analysis script**: `scripts/daily_analysis.sh` con cron 14:30 CEST lun-ven, output su Telegram

### LLM Ensemble
- DeepSeek-V4-Pro rimosso (OOM + latency eccessiva)
- GLM-5.1 rimosso (IC inferiore a Kimi K2.6 in A/B test)
- **Attivi**: Kimi K2.6, Qwen3.5

---

## 2026-06-15

### Code Review
- Review completa del codebase: vedi `archive/2026-06-p0-p2-controlled-paper-history/02_external_reviews/CODE_REVIEW_FULL_2026-06-15.md` (archived 2026-06-23)
- Identificati 13 fix prioritari ora tracciati in `docs/superpowers/plans/2026-06-16-master-roadmap.md`

---

## 2026-06-07

### Nuova Strategia
- **S7 PEAD** aggiunto: classifica 8-K filing SEC via Ollama, cattura Post-Earnings Announcement Drift
- Allocazione target: 15%
- Worker: `src/workers/pead_worker.py`
- Beat task: `pead-ingestion` (queue `inference`, ogni 30 min 14:05-21:35 UTC)

---

## 2026-06-06

### Bug Fix (P0/P1)
- Connection leak in PostgreSQL store: aggiunto `finally: pg.close()` in tutti i task Celery
- `asyncio.run()` in contesto async: sostituito con `await` corretto
- N+1 queries: batch query per simboli multipli
- Race condition PostgreSQL: aggiunto `FOR UPDATE` su operazioni critiche
- Vedi `archive/2026-06-p0-p2-controlled-paper-history/02_external_reviews/CODE_REVIEW_FULL_2026-06-15.md` per lista completa (archived 2026-06-23)

---

## 2026-05-26

### Backtest
- Completato backtest GKG novembre 2025 (run-id: gkg-nov25-v1)
- IC/ICIR analizzato; S2 disabilitata definitivamente (OOS IC = −0.55, tutti i gate falliti)

---

## 2026-05-18

### Frontend
- Dashboard React aggiunta: Overview, Signals, Trades, Performance, LLM, Admin
- Backend FastAPI: routes per trades, signals, decisions, performance, analytics

---

## 2026-05-13

### Infrastruttura
- GDELT GKG bulk ingestion implementata (`src/connectors/gdelt_gkg.py`)
- A/B test GDELT completato: GKG > standard per IC (~15% improvement)
- Multi-asset news-driven pipeline completata

---

## 2026-05-03

### Foundation
- Sistema LLM Alpha Miner implementato (pipeline offline)
- FinBERT sentiment + Ollama ensemble (4 modelli, poi ridotti a 2)
- Backtrader backtesting framework
- Celery + Redis + PostgreSQL stack operativo
- Portfolio Orchestrator (Phase G): weight-then-order multi-strategy cycle
