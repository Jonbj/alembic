# EVIDENCE — Log consolidato delle evidenze dell'audit

**Audit:** Alembic Strategy Audit
**Data:** 2026-08-04
**Scope:** S1, S2, S3, S4, S7

Questo documento consolida le **evidenze** raccolte durante l'audit: query DB
read-only, trace statiche, repro eseguiti, riferimenti letteratura, artefatti
del progetto. È la base verificabile dei verdetti. Ogni evidenza è
cross-riferita al REPORT/fase che la usa.

## 1. Query DB read-only (2026-08-04, container `alembic-postgres-1`)

Tutte le query sono `SELECT`-only, read-only, su `alembic-postgres-1` (DB
live `trading`). Schema ispezionato con `\d <table>` prima di ogni query.

### 1.1 — `strategy_lifecycle` (S1-S7 stato governance)

```sql
SELECT strategy_id, mode, approved, gate_report_id, promoted_at
FROM strategy_lifecycle ORDER BY strategy_id;
```
**Risultati chiave:**
- S1: mode=paper/live, approved=t
- S4: mode=paper, approved=t, promotion_blocked (colonna/separate)
- S7: **mode=research, approved=f, promoted_at=NULL,
  gate_report=reports/s7_backtest/ALPHA_A5_gate_report_2026-07-03_fmp.md**

→ Usato in: REPORT_S7 §8, GI-5 (governance asimmetrica).

### 1.2 — Runtime S4 (strategia live attiva)

```sql
-- sentiment_signals volume
SELECT count(*), min(generated_at), max(generated_at) FROM sentiment_signals;
-- → 6286 (2026-06-15 → 2026-08-03)

-- trades S4
SELECT count(*), sum(net_pnl), count(*) FILTER (WHERE net_pnl>0) FROM trades
  WHERE exit_reason IS NOT NULL;  -- proxy (trades non ha strategy_id)
-- → 64 trade S4 (via signal_id join), net_pnl +$329.10, 37/62 wins (60%)
-- (numeri confermati da report esistente + join execution_decisions)

-- execution_decisions (14g) reason distribution
SELECT reason, count(*) FROM execution_decisions
  WHERE tick_time > now() - interval '14 days'
  GROUP BY reason ORDER BY count DESC LIMIT 15;
-- → 2794 total, 93 S4-reason (3.3%), "feedback threshold 0.30x" = S4 gate,
--   "S1 momentum" = S1, NESSUN tag S7/pead

-- score vs signal_score (S4 fixed-slot conferma)
SELECT score, signal_score, regime_mult FROM execution_decisions
  WHERE reason ILIKE 'S4%' OR signal_score IS NOT NULL LIMIT 5;
-- → score=0.020 (peso 2%=10%×1/5), signal_score=0.356 (sentiment raw),
--   regime_mult=0.700
```

→ Usato in: REPORT_S4 §6 (runtime), OBS-1 (fixed-slot confermato), GI-6.

### 1.3 — Runtime S7 (mai live, zero ordini)

```sql
\d pead_signals
-- → "Did not find any relation" (TABLE NON MATERIALIZZATA)

SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename ILIKE '%pead%';
-- → 0 rows

SELECT count(*) FROM execution_decisions WHERE reason ILIKE '%s7%' OR reason ILIKE '%pead%';
-- → 0 (ZERO decisioni S7)

SELECT exit_reason, count(*) FROM trades GROUP BY exit_reason ORDER BY count DESC;
-- → portfolio_sell(304), blank(49), stop_loss(33), sentiment_reversal(25),
--   LEGACY_FLATTEN(16) — NESSUN tag S7/pead
```

→ Usato in: REPORT_S7 §6 (runtime MORTO), BUG-D, GI-9.

### 1.4 — Runtime S1/S3 (S3 morto)

```sql
-- S3 zero trade (confirmato in fase S3 06)
-- S1 75 trade (confirmato in fase S1 06 / sessione precedente)
```

→ Usato in: REPORT_S3 §6, REPORT_S1.

## 2. Trace statiche / ispezioni codice (read-only)

### 2.1 — Dead config `from_yaml` (S1/S2/S3)

AST walk (S3 repro_2): `from_yaml` classmethod definito in S3Config, **0 call
site** nel codebase; 2 istanziazioni bare `S3Config()`. Pattern confermato per
S1/S2 (grep). S4 **non** segue il pattern (wired via `trading.yaml
risk.s4_fixed_slot_sizing_enabled`, realmente letto).

→ Usato in: GI-1, REPORT_S3 BUG-B, REPORT_S1 BUG-1, REPORT_S2 BUG-D.

### 2.2 — Pannello bilanciato look-ahead (S1/S3)

S3 repro_1 (ESEGUITO): `first_admitted_date` per il ticker più recente
(2012-12-19) gated da IPO future-listed, non da info PIT-osservabile →
look-ahead nella costruzione del pannello. Stesso pattern S1 (BUG-2).

→ Usato in: GI-2, REPORT_S3 BUG-A, REPORT_S1 BUG-2.

### 2.3 — S4 gate drift backtest/live (S4)

S4 repro_1 (ESEGUITO): `backtest.py` ha **0 riferimenti** a `entry_threshold`;
`portfolio_scheduler.py:1277-1340` ne ha **9**. Il backtest non replica il
gate ratchet live (0.30), usa solo `min_score=0.10`.

→ Usato in: REPORT_S4 BUG-A, GI-2.

### 2.4 — S4 fallback sintetico (S4)

S4 repro_2 (ESEGUITO): `_generate_synthetic_signals` produce segnali RNG
(`rng.uniform(-0.5,0.9)` score, `model_id='synthetic'`); `summary.json`
scritto **senza flag** sintetico. 182 segnali sintetici generati nel repro.

→ Usato in: REPORT_S4 BUG-B, GI-2.

### 2.5 — S7 carburante zero (S7)

S7 repro_1 (ESEGUITO, statico): `surprise_pct` opzionale (`pead.py:17`) +
gate reject-None (`signal.py:42`) + consensus non wired (lifecycle) →
carburante zero. File rimossi (verifica assenza working tree).

→ Usato in: REPORT_S7 BUG-A, GI-6.

### 2.6 — S7 guard anti-reintro (S7)

S7 repro_2 (ESEGUITO): `tests/test_p0_13_strategy_containment.py:62-97`
`TestS7NotInOperationalRegistry` vivo nel working tree; guard
`get_active_strategies()` + `mode=research` verificata.

→ Usato in: REPORT_S7 OBS-1, GI-5.

## 3. Artefatti del progetto (evidenza interna)

### 3.1 — `docs/evidence/s4_ic.json` (S4 IC misurato)

Generato 2026-08-03. IC (Spearman cross-sectionale, sentiment_signals →
forward returns da Alpaca historical):
```
all:     IC 1g=-0.018, 3g=-0.010, 5g=-0.026  (nessuno significativo)
fallback: IC 1g=-0.020, 3g=-0.061, 5g=-0.063
n=34 giorni, 2002 obs
```
→ **Negativo su tutti gli orizzonti**, peggiore di placebo. P0-13 (IC>placebo)
NON confermato.

→ Usato in: REPORT_S4 §1, §5 (alpha assessment NEGATIVE), GI-8.

### 3.2 — `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md` (S7 valutazioni)

4 valutazioni pre-registrate:
- Finnhub 07-03: n=0 INCONCLUSIVE
- ALPHA-A5 large-cap 07-03: n=76 FAIL (drift=beta SPY, hit 51%<55%, no
  dose-response, media +0.05%, mediana −1.07%)
- POC-1 small/mid 07-04: n=15 INCONCLUSIVE_DATA (copertura IEX insufficiente)
- POC-2 transcript tone 07-15: n=73 **FAIL decision-grade** (IC(tone,
  excess_20d)=+0.012 vs +0.10 threshold, tercile −0.93% invertito, split-half
  −0.230/+0.244 opposti, cross-model kimi↔glm ρ=+0.858 robusto)

PO-5 pre-registrato "Se POC-2 FAIL → REMOVE" → applicato (commit d1e6de6).

→ Usato in: REPORT_S7 (tutte le fasi), GI-3, GI-5, GI-7.

### 3.3 — Git history S7

```
d1e6de6 feat(strategy)!: remove S7 (PEAD) — ALPHA-A3 edge confuted at decision-grade
5b7991c feat(s7): unlock PEAD — Finnhub earnings surprise feed
1dd2c35 feat(strategy): implement S7 PEAD earnings event strategy
```
Sorgente S7 recuperato da `git show 1dd2c35:src/strategies/s7/{strategy,signal}.py`
e `git show 1dd2c35:src/models/pead.py` (rimozione pulita confermata in fase 05).

→ Usato in: REPORT_S7 §2, fase 05.

### 3.4 — `config/strategies.yaml`, `config/trading.yaml`

- S4 wired via `trading.yaml risk.s4_fixed_slot_sizing_enabled` (letto, non dead).
- S1/S2/S3 `from_yaml` morto (GI-1).
- S7 entry rimossa (commit d1e6de6).

→ Usato in: GI-1, REPORT_S4 §2.

## 4. Riferimenti letteratura (WebSearch, accademici)

PEAD / earnings drift:
- Martineau 2021 "Rest in Peace PEAD" — https://doi.org/10.31235/osf.io/z7k3p
- Kettell-McInnis-Zhao 2022 "Why Has PEAD Declined" — https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf
- Nyllinge-Oldenburg 2025 "Resurgence of PEAD" — http://arc.hhs.se/download.aspx?MediumId=6317
- Ng-Rusticus-Verdi 2008 (JAR) — https://onlinelibrary.wiley.com/doi/10.1111/j.1475-679X.2008.00290.x
- Chordia-Goyal-Sadka-Shridhar 2009 (FAJ) — https://www.tandfonline.com/doi/abs/10.2469/faj.v65.n4.3
- Zhang-Cai-Keasey 2014 (Springer) — https://link.springer.com/article/10.1007/s11156-013-0386-4
- Quant Decoded 2025 (drift by cap) — https://quantdecoded.com/en/post-earnings-drift-by-market-cap-size-matters
- Kaczmarek-Zaremba 2025 (ML PEAD) — https://ideas.repec.org/a/eee/finlet/v86y2025ipes1544612325020057.html

Transcript tone:
- Hameleers 2025 (Tilburg, LLaMA tone) — http://arno.uvt.nl/show.cgi?fid=188469
- Chung-Tanaka-Ishii 2023 (ICAIF, ChatGPT+SBERT) — https://doi.org/10.1145/3604237.3626861
- Druz-Wagner-Zeckhauser 2015 (NBER WP 20991) — https://www.nber.org/system/files/working_papers/w20991/w20991.pdf

Analyst revisions:
- Livnat-Nissim 2006 (JAR) — https://onlinelibrary.wiley.com/doi/10.1111/j.1475-679X.2006.00196.x
- Zhang 2008 (analyst responsiveness) — https://www.sciencedirect.com/science/article/abs/pii/S0165410108000220

LLM sentiment / FinBERT:
- Lopez-Lira-Tang 2023 (ChatGPT Sharpe 3.28, FinBERT −0.43) — citato in REPORT_S4 fase 03
- Heston-Sinha (news 1-2 day predict) — citato in REPORT_S4 fase 03

Momentum / residual momentum:
- Moskowitz-Ooi-Pedersen 2012 (TSMOM) — REPORT_S1 fase 03
- Blitz-Huij-Martens 2011 (residual momentum) — REPORT_S3 fase 03
- Huij-Lansdorp 2017 (NON-decayed OOS) — REPORT_S3 fase 03
- Wiest 2022 (12-1 standard) — REPORT_S3 fase 03
- Jegadeesh 1990 (12-0 reversal) — REPORT_S3 fase 03

VRP:
- Bollershev-Tauchen-Zhou 2009 (VRP) — REPORT_S2 fase 03

→ Usato in: REPORT_S1..S7 fase 03, GI-4 (forma debole).

## 5. Repro eseguiti (artefatti audit)

| File | Strategia | Esito | Conferma |
|---|---|---|---|
| `S3/repro_1_balanced_panel_lookahead.py` | S3 | CONFIRMED | pannello bilanciato look-ahead |
| `S3/repro_2_deadconfig.py` | S3 | CONFIRMED | from_yaml 0 call site |
| `S3/repro_3_trivial_gate.py` | S3 | CONFIRMED | milestone_c accetta Sharpe=0 |
| `S4/repro_1_gate_drift.py` | S4 | CONFIRMED | backtest 0 entry_threshold vs scheduler 9 |
| `S4/repro_2_synthetic_fallback.py` | S4 | CONFIRMED | RNG signals, no synthetic flag |
| `S7/repro_1_carburante_zero.py` | S7 | CONFIRMED | surprise opzionale + gate + consensus non wired |
| `S7/repro_2_guard_anti_reintro.py` | S7 | CONFIRMED | test_p0_13 guard viva |
| (S1 repro in sessione precedente) | S1 | CONFIRMED | dead config, look-ahead |
| (S2 repro in sessione precedente) | S2 | CONFIRMED | fwd_21d look-ahead, IV stale |

Tutti i repro sono in `docs/audits/strategies/<id>/repro_<n>.py` (artefatti
audit, non codice produzione). Eseguiti con `PYTHONPATH=.` da project root.

## 6. Limiti dell'evidenza

- **S1 IC**: non misurato a decision-grade (time-series, no cross-sectional IC).
  Verdetto DECAYED basato su letteratura + pattern, non su misurazione diretta.
- **S4 IC**: misurato MA n=34 (small-sample). Direzione coerente (negativa)
  MA n<73 (decision-grade threshold di S7). Estendere a 73gg+ per conferma.
- **S3**: runtime morto → nessuna evidenza runtime; verdetto UNPROVEN su
  implementazione non-fedele + fenomeno NON-decayed (letteratura).
- **S7 resurgence post-2020** (Nyllinge 2025): ambigua, n=4 anni, non robusta.
  Non cambia il verdetto S7 (rimossa pre-evidenza) MA è una caveat per revival.
- **Costi di transazione live**: non misurati direttamente; inferiti da
  `cost_bps`/`cost_usd` in `trades` (S4) e letteratura (Chordia per PEAD).

L'evidenza è **sufficiente per i verdetti** con la confidenza dichiarata per
strategia (S7 ALTA, S4 MEDIA, S1/S2/S3 MEDIA-BASSA per limiti di misurazione).

---
**Stato:** EVIDENCE = done (2/4 cross_review). Prossimo: `PORTFOLIO_INTERACTIONS.md`.