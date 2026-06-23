# CONTROLLED PAPER DAY 1 — EOD REPORT

**Data:** 2026-06-23  
**Report (FINAL):** 2026-06-23T17:48 UTC (mercato ancora aperto — 2 posizioni residue aperte, chiudono a 20:00 UTC)
**Evidence directory:** `artifacts/controlled_paper_day1_20260623_114625/`  
**Operator:** Jonbj (Stefano Delgobbo)

---

## Verdict (FINAL)

### `CONTROLLED_PAPER_DAY1_EOD_PARTIAL_SUCCESS_BUG_FIXED_CONTINUE_DAY2`

> BUG-DAY1-01 rilevato e fixato nella stessa giornata (16:18 UTC).  
> Pipeline S1/S4 operativa dal ciclo 16:22 UTC. 3 trade aperti, 1 chiuso.  
> Governance pulita per tutta la giornata. Nessun stop criteria attivato.  
> Sistema pronto per Day 2.

---

## Executive Summary

Il Controlled Paper Day 1 (2026-06-23) ha prodotto risultati misti ma concludenti.

**Fase critica (14:07–16:07 UTC):** BUG-DAY1-01 ha bloccato tutte le submission degli ordini. La pipeline signal→decision→order generation era corretta, ma il layer di broker submission falliva perché `ALPACA_BRACKET_ENABLED=True` aggiungeva `order_class=BRACKET` agli ordini notional/fractional — incompatibile con Alpaca (error 42210000). 9 ordini rifiutati, 0 trade aperti in questa fase.

**Fix e recovery (16:18–16:22 UTC):** Bug identificato, fixato con una riga in `portfolio_scheduler.py:1345`, worker rebuilddato e riavviato in 4 minuti. Al ciclo 16:22 UTC `submitted=2` — fix confermato funzionante.

**Post-fix (16:22–17:48 UTC):** 3 trade aperti (MU, GS, GOOGL), 1 chiuso (GS +$0.45). Cicli 103–104 `submitted=0` per SIGNAL_DUPLICATE_SKIP (comportamento corretto — segnali già sparati oggi). Sistema operativo normalmente.

---

## Metriche Day 1 (FINAL)

| Metrica | Valore |
|---------|--------|
| Cicli eseguiti | **15** (id 90–104, 14:07–17:37 UTC) |
| Strategie attive | S1, S4 only ✅ |
| Decisioni generate | **12** (11 BUY, 1 SELL) |
| Ordini rifiutati broker (pre-fix) | 9 (BUG-DAY1-01) |
| Ordini bloccati idempotency (post-fix) | tutti i cicli 103–104 (SIGNAL_DUPLICATE_SKIP ✅) |
| Ordini sottomessi e fillati (post-fix) | **4** ✅ |
| Trade aperti oggi | **3** (MU, GS, GOOGL) |
| Trade chiusi oggi | **1** (GS) |
| PnL realizzato Day 1 | **+$0.45** (GS: buy $1,098.378 → sell $1,100.234) |
| PnL unrealizzato (17:48 UTC) | **-$4.29** (MU -$4.37, GOOGL +$0.08) |
| PnL netto Day 1 (17:48 UTC) | **-$3.85** |
| Account equity (17:48 UTC) | **$110,110.90** |
| Esposizione (17:48 UTC) | **0.48%** ($530 / $110k) |
| Drawdown intraday max | **0.004%** |
| Stop criteria attivati | **NESSUNO** ✅ |
| Kill-switch | false tutto il giorno ✅ |
| Live trading | NOT authorized ✅ |

---

## Findings Principali

### BUG-DAY1-01 — Bracket + Fractional incompatibili ✅ FIXATO

**Gravità:** HIGH — bloccava 100% delle submission per 2h (14:07–16:07 UTC)  
**Root cause:** `ALPACA_BRACKET_ENABLED=True` applicava `order_class=BRACKET` agli ordini notional (fractionable), incompatibile con Alpaca (error 42210000 "fractional orders must be simple orders").  
**Fix:** `portfolio_scheduler.py:1345` — aggiunto `and not is_fractionable` al branch P2-A.  
**Commit:** `54d3be3`  
**Confermato:** ciclo 16:22 UTC `submitted=2`, fill GS+MU ✅

### P0-09 — Regime:current assente (ongoing, non bloccante)

**Gravità:** MEDIUM  
**Effetto:** Tutti i 15 cicli usano high_vol fallback ×0.2 → posizioni ~$267 invece di ~$1,100 (score 0.02 × 0.2 × $110k). Il sistema è safe ma sotto-allocato per tutta la giornata.  
**Causa:** regime:current key assente in Redis. Regime detector potrebbe non girare o key scaduta.  
**Azione Day 2:** Investigare regime detector prima dell'apertura mercato.

---

## Cicli S1/S4 — Timeline Completa

| Ciclo | Ora UTC | Ordini | Submitted | Note |
|-------|---------|--------|-----------|------|
| 90 | 14:07 | 2 | **0** ❌ | BUG-DAY1-01: TSM+MS rifiutati |
| 91 | 14:22 | 2 | 0 | SIGNAL_DUPLICATE_SKIP |
| 92 | 14:37 | 2 | 0 | SIGNAL_DUPLICATE_SKIP |
| 93 | 14:52 | 0 | 0 | 0 segnali freschi |
| 94 | 15:07 | 2 | **0** ❌ | BUG-DAY1-01: TM rifiutato |
| 95 | 15:22 | 2 | 0 | SIGNAL_DUPLICATE_SKIP |
| 96 | 15:37 | 2 | **0** ❌ | BUG-DAY1-01: TSM rifiutato |
| 97 | 15:52 | 3 | **0** ❌ | BUG-DAY1-01: TSM+GS rifiutati |
| 98 | 16:07 | 4 | **0** ❌ | BUG-DAY1-01: tutti rifiutati |
| — | **16:18** | — | — | **FIX deployed (commit 54d3be3)** |
| 99 | 16:22 | 5 | **2** ✅ | MU+GS fillati |
| 100 | 16:37 | 5 | **1** ✅ | GOOGL fillato |
| 101 | 16:52 | 6 | **1** ✅ | GS SELL (portfolio_sell) |
| 102 | 17:07 | 5 | 0 | SIGNAL_DUPLICATE_SKIP ✅ |
| 103 | 17:22 | 5 | 0 | SIGNAL_DUPLICATE_SKIP ✅ |
| 104 | 17:37 | 5 | 0 | SIGNAL_DUPLICATE_SKIP ✅ |

**Nota cicli 102–104:** `submitted=0` per idempotency (GOOGL/MU/TM/TSM/TXN già sparati oggi), NON per bug. Comportamento corretto.

---

## Fills Alpaca (FINAL)

| Ora UTC | Symbol | Side | Qty | Avg Price | Notional | Esito |
|---------|--------|------|-----|-----------|---------|-------|
| 13:30 | XLK/QQQ/ORCL/IWM/CRM/AMAT | SELL | vari | vari | $11,141 | LEGACY FLATTEN (escluso Day 1) |
| 16:22:07 | MU    | BUY  | 0.245606315 | $1,086.332 | $266.82 | ✅ open |
| 16:22:07 | GS    | BUY  | 0.242912731 | $1,098.378 | $266.82 | ✅ closed |
| 16:37:04 | GOOGL | BUY  | 0.769970294 | $347.416   | $267.51 | ✅ open |
| 16:52:05 | GS    | SELL | 0.242912731 | $1,100.234 | $267.27 | ✅ +$0.45 realized |

---

## Governance Checks (FINAL 17:48 UTC)

| Check | Status |
|-------|--------|
| S1 mode | supervised_paper ✅ |
| S2 mode | disabled, approved=false ✅ |
| S4 mode | paper ✅ |
| S3/S7 | non presenti ✅ |
| GLOBAL_LIVE_PROMOTION_ENABLED | False (hardcoded) ✅ |
| Alpaca endpoint | paper-api.alpaca.markets only ✅ |
| Kill-switch (17:48 UTC) | false ✅ |
| Pyramiding events | 0 ✅ |
| Live trading | NOT authorized ✅ |
| S2/S3/S7 decisioni | 0 ✅ |

---

## Account Snapshot (FINAL 17:48 UTC)

| Campo | Valore |
|-------|--------|
| Account | PA34OYJWSJUY |
| Equity | $110,110.90 |
| Cash | $109,580.89 |
| Portfolio value | $110,110.90 |
| Posizioni aperte | 2 (GOOGL $267.58 +$0.08, MU $262.44 -$4.37) |
| Ordini aperti | 0 |

---

## PnL Day 1 (FINAL)

| Metrica | Valore |
|---------|--------|
| Post-flatten baseline equity | $110,114.75 (13:30 UTC) |
| Equity finale (17:48 UTC) | $110,110.90 |
| **Net PnL Day 1** | **-$3.85** |
| Breakdown realizzato | GS +$0.45 |
| Breakdown unrealizzato | MU -$4.37, GOOGL +$0.08 → tot -$4.29 |
| Legacy flatten PnL | EXCLUDED (-$376.84, LEGACY_FLATTEN_ORDER) |

> Nota: 2 posizioni ancora aperte (MU, GOOGL) — PnL unrealizzato cambierà fino a 20:00 UTC.

---

## Confronto vs. Baseline

| Metrica | Pre-flatten (12:48) | Post-flatten (13:30) | Final (17:48) |
|---------|---------------------|---------------------|----------------|
| Posizioni | 6 legacy | 0 ✅ | 2 S4 Day 1 |
| Equity | $110,118.59 | $110,114.75 | $110,110.90 |
| PnL Day 1 | — | 0.00 | **-$3.85** |
| PnL flatten | -$376.84 (legacy) | — | EXCLUDED |

---

## Raccomandazione Day 2

**✅ CONTINUARE DAY 2**

| Item | Status |
|------|--------|
| BUG-DAY1-01 | ✅ FIXATO (commit 54d3be3) |
| Governance | ✅ CLEAN |
| Stop criteria | ✅ NESSUNO ATTIVATO |
| Pipeline | ✅ OPERATIVA |

**Before Day 2:**
1. **P0-09 regime:current** — Investigare perché regime:current è assente in Redis. Quando risolto, i pesi tornano normali (~5% invece di ~1%) e le posizioni saranno più significative.
2. **GS roundtrip 30 min** — Monitorare se il pattern buy/sell a 30 min esatto si ripete. Potrebbe indicare over-trading S4 se i segnali cambiano di segno rapidamente.

---

## Non-Authorizations (conferma finale)

- Live trading: **NOT authorized** ✅
- Strategy live promotion: **NOT authorized** ✅
- GLOBAL_LIVE_PROMOTION_ENABLED: **False** ✅
- Credenziali live: **non usate** ✅
- Endpoint live Alpaca: **non contattato** ✅
- S2/S3/S7: **non attivi** ✅ (0 decisioni, 0 cicli)
- P3/P4: **non avviati** ✅

**Operator:** Jonbj (Stefano Delgobbo)  
**Report finalized:** 2026-06-23T17:48 UTC  
**Verdict:** `CONTROLLED_PAPER_DAY1_EOD_PARTIAL_SUCCESS_BUG_FIXED_CONTINUE_DAY2`
