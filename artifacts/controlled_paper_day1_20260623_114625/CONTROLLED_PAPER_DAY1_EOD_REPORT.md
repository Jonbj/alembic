# CONTROLLED PAPER DAY 1 — EOD REPORT

**Data:** 2026-06-23  
**Report (interim):** 2026-06-23T17:15 UTC — mercato ancora aperto, aggiornamento finale a 20:00 UTC  
**Evidence directory:** `artifacts/controlled_paper_day1_20260623_114625/`  
**Operator:** Jonbj (Stefano Delgobbo)

---

## Verdict (interim)

### `CONTROLLED_PAPER_DAY1_PARTIAL_SUCCESS_BUG_FIXED_CONTINUE_DAY2`

> BUG-DAY1-01 rilevato e fixato nella stessa giornata. Pipeline S1/S4 operativa.
> Primo trade reale Paper Day 1: MU BUY 16:22 UTC. Governance pulita. Nessun stop criteria attivato.

---

## Executive Summary

Il Controlled Paper Day 1 (2026-06-23) ha prodotto risultati misti ma concludenti:

**Fase critica (14:07–16:07 UTC):** BUG-DAY1-01 ha bloccato tutte le submission degli ordini. La pipeline di signal→decision→order generation era corretta, ma il layer di broker submission falliva perché `ALPACA_BRACKET_ENABLED=True` aggiungeva `order_class=BRACKET` agli ordini notional/fractional — incompatibile con l'API Alpaca (error 42210000). 9 ordini rifiutati, 0 trade aperti.

**Fix e recovery (16:18–16:22 UTC):** Bug identificato, fixato (1 riga in `portfolio_scheduler.py:1345`), worker rebuilddato e riavviato in 4 minuti. Al ciclo successivo (16:22 UTC) `submitted=2` — fix confermato funzionante.

**Post-fix (16:22–17:12 UTC):** 3 trade aperti (MU, GS, GOOGL), 1 chiuso (GS +$0.45). Sistema operativo normalmente. La governance è rimasta pulita per tutta la giornata.

---

## Metriche Day 1

| Metrica | Valore |
|---------|--------|
| Cicli eseguiti | 13 (id 90–102, 14:07–17:07 UTC) |
| Strategie attive | S1, S4 only ✅ |
| Decisioni generate | 12 (11 BUY, 1 SELL) |
| Ordini tentati (pre-fix) | 9 → tutti rifiutati (BUG-DAY1-01) |
| Ordini sottomessi (post-fix) | 4 → tutti filled ✅ |
| Trade aperti oggi | 3 (MU, GS, GOOGL) |
| Trade chiusi oggi | 1 (GS) |
| PnL realizzato Day 1 | +$0.45 (GS) |
| PnL unrealizzato (17:12 UTC) | -$1.24 (MU -$1.59, GOOGL +$0.35) |
| PnL netto Day 1 (17:12 UTC) | **-$0.79** |
| Account equity (17:12 UTC) | $110,113.94 |
| Esposizione massima | 0.48% ($533 / $110k) |
| Drawdown intraday | 0.0007% |
| Stop criteria attivati | NESSUNO ✅ |
| Kill-switch | false tutto il giorno ✅ |
| Live trading | NOT authorized ✅ |

---

## Findings Principali

### BUG-DAY1-01 — Bracket + Fractional incompatibili ✅ FIXATO

**Gravità:** HIGH (bloccava 100% delle submission per 2h)  
**Root cause:** `ALPACA_BRACKET_ENABLED=True` applicava `order_class=BRACKET` anche agli ordini notional (fractionable), mentre Alpaca richiede che gli ordini notional/fractional siano "simple" (no bracket).  
**Fix:** `portfolio_scheduler.py:1345` — aggiunto `and not is_fractionable` al branch P2-A.  
**Commit:** `54d3be3`  
**Confermato:** ciclo 16:22 UTC `submitted=2`, fill GS e MU ✅

### P0-09 — Regime:current assente (ongoing, non bloccante)

**Gravità:** MEDIUM  
**Effetto:** Tutti i cicli usano high_vol fallback ×0.2 → posizioni molto piccole (~$267 vs. ~$1,100 atteso con regime normale). Il sistema è safe ma sotto-allocato.  
**Causa probabile:** Regime detector non scrive `regime:current` in Redis durante le ore di mercato, o la chiave è scaduta.  
**Azione:** Investigare prima di Day 2 (non bloccante per la continuazione).

---

## Cicli S1/S4 — Timeline

| Ciclo | Ora UTC | Ordini | Submitted | Note |
|-------|---------|--------|-----------|------|
| 90 | 14:07 | 2 | **0** | BUG-DAY1-01: TSM+MS rifiutati |
| 91 | 14:22 | 2 | 0 | SIGNAL_DUPLICATE_SKIP |
| 92 | 14:37 | 2 | 0 | SIGNAL_DUPLICATE_SKIP |
| 93 | 14:52 | 0 | 0 | 0 segnali freschi |
| 94 | 15:07 | 2 | **0** | BUG-DAY1-01: TM rifiutato |
| 95 | 15:22 | 2 | 0 | SIGNAL_DUPLICATE_SKIP |
| 96 | 15:37 | 2 | **0** | BUG-DAY1-01: TSM rifiutato |
| 97 | 15:52 | 3 | **0** | BUG-DAY1-01: TSM+GS rifiutati |
| 98 | 16:07 | 4 | **0** | BUG-DAY1-01: MS+TXN+GS+TSM rifiutati |
| **FIX 16:18** | | | | **BUG-DAY1-01 fixato, worker riavviato** |
| 99 | 16:22 | 5 | **2** ✅ | MU+GS fill confermati |
| 100 | 16:37 | 5 | **1** ✅ | GOOGL fill confermato |
| 101 | 16:52 | 6 | **1** ✅ | GS SELL (portfolio_sell) |
| 102 | 17:07 | 5 | TBD | In corso al momento del report |

---

## Governance Checks

| Check | Status |
|-------|--------|
| S1 mode | supervised_paper ✅ |
| S2 mode | disabled, approved=false ✅ |
| S4 mode | paper ✅ |
| S3/S7 | non presenti ✅ |
| GLOBAL_LIVE_PROMOTION_ENABLED | False (hardcoded) ✅ |
| Alpaca endpoint | paper-api.alpaca.markets only ✅ |
| Kill-switch | false tutto il giorno ✅ |
| Pyramiding events | 0 (BUG-5 guard attivo) ✅ |
| Live trading | NOT authorized ✅ |

---

## Account Snapshot (17:12 UTC)

| Campo | Valore |
|-------|--------|
| Account | PA34OYJWSJUY |
| Equity | $110,113.94 |
| Cash | $109,580.89 |
| Portfolio value | $110,113.94 |
| Posizioni aperte | 2 (GOOGL $267.85, MU $265.22) |
| Ordini aperti | 0 |

---

## Posizioni Aperte (17:12 UTC — non finale)

| Symbol | Qty | Market Value | Unrealized P&L | Entry Notional |
|--------|-----|-------------|----------------|----------------|
| MU | 0.2456 | $265.22 | -$1.59 | $266.82 |
| GOOGL | 0.7700 | $267.85 | +$0.35 | $267.51 |

*Aggiornamento finale posizioni e PnL: market close 20:00 UTC.*

---

## Confronto vs. Baseline

| Metrica | Pre-flatten (12:48 UTC) | Post-flatten baseline (13:30 UTC) | EOD (17:12 UTC) |
|---------|------------------------|----------------------------------|------------------|
| Posizioni | 6 legacy | 0 ✅ | 2 (S4 Day 1) |
| Equity | $110,118.59 | $110,114.75 | $110,113.94 |
| PnL Day 1 | — | 0.00 | **-$0.79** |
| PnL flatten | -$376.84 (legacy, escluso) | — | — |

---

## Raccomandazione Day 2

**✅ CONTINUARE DAY 2**

BUG-DAY1-01 è fixato. S1/S4 operativi. Governance pulita. Nessun stop criteria attivato.

**Before Day 2 (priorità):**
1. Investigare P0-09 (regime:current assente) — capire perché il regime detector non scrive in Redis
2. Monitorare il pattern GS open/close a 30 min — verificare se è over-trading S4 o comportamento corretto

---

## Non-Authorizations (conferma finale)

- Live trading: **NOT authorized** ✅
- Strategy live promotion: **NOT authorized** ✅
- GLOBAL_LIVE_PROMOTION_ENABLED: **False** ✅
- Credenziali live: **non usate** ✅
- Endpoint live: **non contattato** ✅
- S2/S3/S7: **non attivi** ✅
- P3/P4: **non avviati** ✅

**Operator:** Jonbj (Stefano Delgobbo)  
**Timestamp:** 2026-06-23T17:15 UTC  
**Status:** INTERIM — aggiornamento finale previsto 20:05 UTC
