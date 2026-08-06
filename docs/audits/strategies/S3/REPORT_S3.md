# REPORT S3 — Cross-Sectional Residual Momentum

**Audit:** Alembic Strategy Audit
**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Verdetto implementazione:** `UNPROVEN` (backtest invalidato, variante non fedele)
**Verdetto fenomeno:** `UNPROVEN` con prior positivo (non decaduto)
**Stato runtime:** **MORTO** (zero trades, nessun path live, `mode=research`)
**Fonti:** `src/strategies/s3/{strategy,signal,universe,backtest}.py`,
`src/strategies/registry.py`, `reports/s3_backtest/summary.json`,
`docs/RESEARCH_S3_STRATEGY_REVIEW_2026-07-20.md`, letteratura (fase 03).

---

## 1. Sintesi esecutiva

S3 scommette sul **momentum residuale cross-sectionale**: la componente
idiosincratica del momentum azionario, netta del contributo `beta×momentum` di
mercato. L'ipotesi teorica (Blitz-Huij-Martens 2011; Gutman 2023) ha prior
accademico **forte** e, a differenza di S1/S2, **NON decade** significativamente
post-pubblicazione (Huij-Lansdorp 2017) — crash meno severi, turnover minore,
Sharpe ~doppio del momentum lordo.

**L'implementazione Alembic non testa fedelmente questa ipotesi.** Il codice
diverge dal design originale (#55) su 8 dimensioni materiali (DV-1..DV-8):
12-0 invece di 12-1 (contaminato dalla short-term reversal), long-short invece
di long-only, sizing non normalizzato, 50 sopravvissuti OGGI come universo,
pannello bilanciato con look-ahead, dead config, cap 20% invece di 10%. Il
backtest OOS Sharpe 0.148 misura una **variante confusa**, non il residual
momentum canonico. È numericamente ~0, ma in un backtest invalidato da
look-ahead + survivorship, quindi non è una falsificazione pulita.

S3 è **completamente morta a runtime**: non è nel registry (`registry.py` carica
solo S1/S2/S4), non ha riga in `strategy_lifecycle`, zero trades in `trades`,
nessun riferimento in `src/portfolio/`. Coerente con `mode=research`.

Il percorso corretto (review interna 2026-07-20) è un **POC A/B offline** della
**variante originale** 12-1 long-only normalizzata, PIT, prima di qualunque
paper trading o broker wiring. L'issue #55 (design-alignment) è ancora aperta.

## 2. Specifica (fase 01)

**Segnale** (`signal.py:39-68`):
$$\mathrm{rm}_{i,t} = \left(\frac{P_{i,t}}{P_{i,t-252}}-1\right) - \beta_{i,t}^{(252)}\left(\frac{P_{\mathrm{SPY},t}}{P_{\mathrm{SPY},t-252}}-1\right)$$

`lookback=252` (12-0, include mese corrente), `beta_window=252` (rolling OLS
`Cov/Var`). Residuo 1-factor (solo beta×SPY; non FF3).

**Ranking** (`signal.py:71-108`): rank ascendente, `decile=ceil(rank·10/n_valid)`.
Long decile 10, short decile 1 (default → **long-short**, design long-only).

**Universo** (`backtest.py:209-210`): `active_at(end)[:50]` con `end=today` →
50 sopravvissuti liquidi OGGI riusati su 2000-today.

**Sizing** (`strategy.py:92-139`): inverse-vol 252d, `target_vol=0.10`,
`max_weight=0.20`, **non normalizzato**, PIT lookup del vol (fix `e15d5e7`).

**Rebalance** mensile (`strategy.py:153-167`); exit su assenza dal target;
NAV = cash + Σ market_value (`strategy.py:169-175`).

**Config**: `S3Config` defaults; `from_yaml` esiste ma 0 call site, nessun yaml
(dead config, DV-8).

**Backtest**: WF 1260/252, OOS Sharpe 0.148, `milestone_c_pass=false` (gate 3/5
FAIL), gate 1/2 PASS con `min_sharpe=0.0` (banali), file 2026-06-01 non in Git,
non riproducibile.

## 3. Ipotesi scientifica (fase 02)

S3 scommette sull'**underreaction idiosincratica** (Jegadeesh-Titman 1993):
gli investitori reagiscono lentamente alle notizie specifiche dell'azienda non
coperte dal beta di mercato; il residuo cattura questa underreaction lenta, con
crash meno severi del momentum lordo (perché la componente beta è sottratta) e
incremental alpha oltre il momentum lordo (Gutman 2023).

**Il codice testa un'ipotesi diversa**: "momentum lordo 12-0 (con reversal),
long-short, sizing non normalizzato, sui 50 sopravvissuti" — non "residual
momentum 12-1 long-only PIT". L'OOS 0.148 non falsifica il residual momentum
canonico: falsifica una variante confusa.

## 4. Letteratura (fase 03)

| Aspetto | Finding | Impatto S3 |
|---|---|---|
| Fondativo | Blitz-Huij-Martens 2011: Sharpe ~2× momentum lordo, +4.7%/anno 2000-2009 vs −8.5% lordo | Prior forte a favore |
| Distinto | Blitz-Hanauer-Vidojevic 2020: non subsumed, incremental alpha, no reversal long-run | Non è puro momentum-beta |
| **Decay** | Huij-Lansdorp 2017: replica OOS post-pubblicazione robusta, **poco decay** | **Differenza chiave vs S1/S2** — non decaduto |
| 12-1 | Wiest 2022 (JT 1993, Carhart 1997): skip ultimo mese è standard per isolare momentum da reversal | **DV-1/DV-2 confermati**: 12-0 viola la convenzione |
| Costi | BHM 2011: ~metà turnover del momentum lordo | A favore di S3 |
| Regime | BHM 2011: crash meno severi del momentum lordo | A favore, ma ridotto da long-short + non-normalizzato |
| Alt-beta | Ehsani-Linn 2023: gran parte del momentum è factor momentum | S3 1-factor sotto-pulito (no size/value/quality) |
| Low-vol | Schneider 2020: low-vol = coskewness | Inverse-vol sizing → low-vol beta |

**Convergenza**: la letteratura sostiene il residual momentum come anomalia
genuina non decaduta, ma non supporta l'implementazione S3 (12-0, long-short, non
normalizzato, 50 sopravvissuti).

## 5. Alpha assessment (fase 04)

**Implementazione: `UNPROVEN`.** Il codice testa una variante economicamente
diversa dal residual momentum canonico. Il backtest 0.148 è (a) numericamente ~0,
(b) invalidato da survivorship + pannello bilanciato + soglie banali, (c) non
riproducibile. Non è falsificazione pulita del fenomeno, né conferma della
variante. Non `NEGATIVE` (backtest invalidato); non `GENUINE_NET_ALPHA` (0.148 ~0,
gate 3/5 FAIL).

**Fenomeno: `UNPROVEN` con prior positivo.** La letteratura sostiene il residual
momentum come anomalia genuina, non subsumed, non decaduta, con Sharpe ~doppio.
Il progetto non l'ha testato fedelmente; issue #55 aperta. A priori, S3 è la
strategia **meno screditata** dalla letteratura tra S1/S2/S3, ma l'implementazione
corrente non la testa.

**Decomposizione beta**: anche un rendimento positivo non sarebbe alpha pulito —
momentum-beta (~0.5 corr), low-vol-beta (inverse-vol sizing), size-beta (50
large-cap), factor momentum residuo (1-factor non FF3).

## 6. Implementation audit (fase 06)

| Asse | Verdetto |
|---|---|
| Data timing | OK (rolling causale, prices_until PIT) |
| **Look-ahead** | **FAIL** (pannello bilanciato DV-7 + survivorship DV-6) |
| Leakage | OK sizing PIT / WARNING precompute (leakage composizione) |
| **Survivorship** | **FAIL** (snapshot corrente + active_at(end)) |
| Backtest method | DEBOLE (WF ok, no costi, no DSR, soglie banali, non riproducibile) |
| Signal gen | FORMULA OK, PARAMETRI NON CANONICI (12-0, 1-factor) |
| Allocation | NON NORMALIZZATO (DV-4, no sleeve) |
| Risk controls | NESSUNO (no stop/DD/kill-switch) |
| Execution | BACKTEST-ONLY (no path live) |
| Accounting | DEBOLE (NAV MTM ok, no costi) |
| Paper trading | N/A (mode=research) |
| **Runtime** | **MORTO** (zero trades, zero lifecycle, zero registry) |

**Runtime (DB read-only 2026-08-04):**
```
trades.stop_strategy: (blank)288, S1=75, S4=64, S3=0
strategy_lifecycle: S1, S2, S4, S7 (nessuna riga S3)
```

## 7. Bug confermati (fase 07)

| ID | Severità | Luogo | Conferma |
|---|---|---|---|
| **BUG-A** | CRITICAL | `signal.py:136` pannello bilanciato look-ahead | repro_1 ESEGUITO |
| BUG-B | MED | `strategy.py:36-53` dead config (from_yaml 0 call, no yaml) | repro_2 ESEGUITO (AST) |
| **BUG-C** | HIGH | `backtest.py:200,209-210` survivorship universe | repro_2 traccia statica |
| BUG-D | MED (latente) | `backtest.py:97` gate `milestone_c` banale `[0.0,1.0]` | repro_3 ESEGUITO |
| DV-1 | DESIGN | `signal.py:60` 12-0 vs 12-1 (contaminazione reversal) | letteratura (Jegadeesh 1990, Wiest 2022) |

**BUG-A** (CRITICAL): `valid_rows = residual.notna().all(axis=1)` — la data è
ammessa iff tutti i ticker (inclusi future-listed) hanno residual non-NaN. repro_1:
prima data ammissibile 2012-12-19, gated dal ticker IPO 2012, non dai tickeri
osservabili PIT dal 2010. Look-ahead nella selezione delle date (come S1 BUG-2).

**BUG-C** (HIGH): `active_at(end)[:50]` con `end=today` — filtro PIT applicato
una sola volta alla data finale; 50 sopravvissuti OGGI riusati su 2000-today.

**BUG-D** (latente): `0.0 <= oos_sharpe <= 1.0` accetta Sharpe=0; il commento
documenta `[0.4,0.6]`. Attualmente latente (gate 3/5 FAIL → overall_passed=False).

## 8. Divergenze codice ↔ design (#55)

| ID | Codice | Design originale |
|---|---|---|
| DV-1 | formation 12-0 (`signal.py:60`) | 12-1 skip mese |
| DV-2 | market correction 12-0 (`signal.py:61`) | 12-1 |
| DV-3 | long-short (`strategy.py:33`) | long-only |
| DV-4 | sizing non normalizzato (`strategy.py:121-139`) | inverse-vol 60d normalizzato |
| DV-5 | cap 20% (`strategy.py:31`) | 10% |
| DV-6 | 50 sopravvissuti (`backtest.py:209-210`) | US large/mid PIT |
| DV-7 | pannello bilanciato (`signal.py:136`) | n/a (look-ahead) |
| DV-8 | dead config (`strategy.py:36-53`) | yaml-driven |

## 9. Conclusione e raccomandazione

S3 è la strategia **meno screditata** dalla letteratura tra le tre momentum-family
auditate (S1 decaduto, S2 decaduto+negativo, S3 non decaduto), ma:
1. L'implementazione **non testa** il fenomeno (8 divergenze materiali dal design).
2. Il backtest è **invalidato** da 2 bug critici/high (BUG-A look-ahead, BUG-C
   survivorship) + costi non modellati + soglie banali + non riproducibile.
3. A runtime è **completamente morta** (zero attività, nessun path live).

**Raccomandazione** (allinea con review interna 2026-07-20 e issue #55 aperta):
- **NON** interpretare 0.148 come falsificazione del residual momentum.
- Eseguire un **POC A/B offline** della **variante originale** 12-1 long-only,
  sizing inverse-vol 60d normalizzato, universo PIT (market-cap filter
  implementato), pannello NON bilanciato (drop per-ticker, non per-data), costi
  modellati, DSR per multiple testing.
- Solo se il POC mostra OOS Sharpe > 0.4 (soglia reale, non 0.0) post-cost,
  considerare paper trading. Fino ad allora: `mode=research`, nessun wiring.

**Rischi chiave**: non-test fedele; bias di backtest; decay futuro non escluso
(la letteratura dice "poco decay finora"); beta non isolato (1-factor);
long-short vs long-only (rischio short-squeeze/borrow non modellato).

---
**Stato audit S3:** fasi 01-08 **done**. Report consolidato.