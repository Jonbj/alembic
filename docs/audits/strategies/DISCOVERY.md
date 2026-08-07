# DISCOVERY — Inventario delle strategie Alembic

**Data:** 2026-08-03T21:59:15Z
**Metodo:** unione di `config/strategies.yaml`, `src/strategies/<id>/`, tabella DB `strategy_lifecycle`, `src/strategies/registry.py`, `docs/` e storia git. Deduplicazione per `strategy_id`.

## Risultato: 5 strategie

L'audit copre **ogni** strategia — implementata, configurata, disabilitata, sperimentale, o rimossa. Non si limita a S1/S4 né alle strategie abilitate.

| ID | Nome / Classe | Stato | Lifecycle `mode` | Approvata | Alloc. | Ipotesi scientifica |
|----|---------------|-------|------------------|-----------|--------|---------------------|
| **S1** | `TimeSeriesMomentum` | abilitata | `supervised_paper` | sì | 0.50 | Momentum (TS/CS ibrido) |
| **S2** | `VRPStrategy` | disabilitata | `disabled` | no | 0.00 | Variance Risk Premium (proxy) |
| **S3** | `CrossSectionalMomentum` | disabilitata | *(nessuna riga lifecycle)* | no | 0.00 | Residual momentum |
| **S4** | `NewsDrivenTactical` | abilitata | `paper` | sì | 0.10 | News sentiment drift |
| **S7** | `PEAD` (transcript tone) | **rimossa** | `research` | no | 0.00 | Post-Earnings-Announcement Drift |

Non esistono S5/S6/S8+ in nessuna fonte (config, sorgente, DB, registry, docs, git).

## Sorgenti consultate

1. **`config/strategies.yaml`** — chiavi `S1,S2,S3,S4` sotto `strategies:` + blocco commento che documenta la rimozione di S7 (2026-07-15).
2. **`src/strategies/<id>/`** — directory implementate: `s1`, `s2`, `s3`, `s4`. Classe per ciascuna: `TimeSeriesMomentum`, `VRPStrategy`, `CrossSectionalMomentum`, `NewsDrivenTactical`.
3. **`src/strategies/registry.py`** — `_SAFE_DEFAULTS` cita solo S1/S2/S4 (fallback quando il config manca).
4. **`strategy_lifecycle` (DB, read-only `SELECT`)** — righe per S1, S2, S4, S7. **S3 non ha riga** → è registrata solo in config/sorgente, mai promossa a nessun lifecycle mode.
5. **`docs/strategies.md`**, `docs/RESEARCH_S2_S3_S7_PRIMARY_LITERATURE_2026-07-15.md`, `docs/RESEARCH_S3_STRATEGY_REVIEW_2026-07-20.md`, `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`, `docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md`, `docs/S1_REFINEMENTS_BACKTEST_2026-07-27.md`.
6. **Storia git** — `git log -- 'src/strategies/s7'`: implementazione `1dd2c35`, rimozione `d1e6de6` ("ALPHA-A3 edge confuted at decision-grade"). Sorgente S7 recuperabile da git per l'audit.

## Note di stato per l'audit

- **S1** — unica sleeve con capitale reale-assegnato (0.50). Backtest dichiarato invalido nel config stesso (same-bar t+0, survivorship, zero-cost, stress/regime circolare, DSR n_trials=1). `promotion_blocked` implicito via `mode=supervised_paper`; `approved=true` (riga lifecycle) ma `GLOBAL_LIVE_PROMOTION_ENABLED=False`.
- **S2** — PROXY di equity, **non** usa opzioni; l'ipotesi (VRP short-put) e l'implementazione sono disallineate per costruzione. Sharpe OOS −0.55. L'audit verificherà se il proxy misura mai la VRP reale.
- **S3** — residual momentum; `config` nota "possible sizing lookahead" e gate 3/5 falliti. Nessuna riga lifecycle → non è mai entrata nel runtime.
- **S4** — sleeve tattica news-sentiment, capped 0.10, `promotion_blocked` (P0-13). L'unico path live è `execution.engine=portfolio`. Storicamente violato long-only (DAY-001: BUY su MSFT sentiment −0.110). L'audit verificherà guard/long-only, freshness, feedback threshold, e divergenza ensemble.
- **S7** — rimossa; auditeremo da git history + docs per stabilire se la conclusione POC-2 FAIL (IC≈0, n=73) regge o se la rimozione ha scartato un edge vivo.

## Prossimo cursore

`S1:01_specification` — la prima fase della prima strategia abilitata con capitale.