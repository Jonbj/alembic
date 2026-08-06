# REPORT S7 — Post-Earnings Announcement Drift (PEAD) — RIMOSSA

**Audit:** Alembic Strategy Audit
**Strategia:** S7 `PEADStrategy` (post-earnings announcement drift, event-driven)
**Data:** 2026-08-04
**Verdetto implementazione:** `NEGATIVE` (POC-2 FAIL decision-grade, IC≈0,
cross-model robusto)
**Verdetto fenomeno:** `DECAYED` (large-cap competuto; small-cap vivo MA non
raggiunto; resurgence ambigua post-2020)
**Stato runtime:** **RIMOSSA 2026-07-15** (commit `d1e6de6`, #38 chiuso);
**mai live** (zero ordini lifecycle, `pead_signals` table mai materializzata)
**Fonti:** git history (`1dd2c35`: `src/strategies/s7/{strategy,signal}.py`,
`src/models/pead.py`), `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`,
`tests/test_p0_13_strategy_containment.py`, DB read-only, letteratura.

---

## 1. Sintesi esecutiva

S7 era la strategia **event-driven** del progetto: scommetteva sul PEAD
(post-earnings announcement drift) — dopo una sorpresa positiva negli
earnings, il prezzo sottoreagisce e drifta nella direzione della sorpresa nei
giorni seguenti. Il segnale era generato da un LLM (Ollama, DK-CoT) che
parsificava gli 8-K filing SEC in `EarningsLLMOutput` (direction, surprise_pct,
confidence), poi classificato da `EarningsSurpriseClassifier` con gate quality
(direction≠no_eps/inline, confidence≥0.70, |surprise|≥0.05). La strategia
`PEADStrategy` allocava pari peso (5%) ai segnali "beat" attivi entro 20 giorni,
con cap sleeve 25% (max 5 posizioni).

**S7 è stata rimossa il 2026-07-15** sulla base di un'evidenza
**decision-grade pre-registrata**. È il caso di **best-practice governance**
dell'intero audit: l'unica strategia misurata a campione sufficiente
(POC-2 n=73), killata su un criterion pre-registrato (PO-5: "Se POC-2 FAIL →
REMOVE"), e rimossa pulitamente (full runtime surface eliminato, guard
anti-reintroduzione `test_p0_13` viva nel working tree).

**Il verdetto è NEGATIVE con alta confidenza** — non UNPROVEN, non DECAYED
ambiguo: la variante alpha-specifica dichiarata (transcript tone → alpha,
ALPHA-A3) è **attivamente confutata** cross-modello a sample decision-grade
(IC tone/excess_20d = +0.012 ≈0, tercile spread −0.93% invertito, split-half
opposti, cross-model kimi↔glm ρ=+0.858 — il FAIL non è artefatto di un
modello). L'edge numerico (raw surprise) su large-cap è competuto (ALPHA-A5
n=76: drift = beta SPY, non alpha). L'universo dove l'edge accademico vive
(small-cap, net 3.8%) non era raggiungibile (POC-1 n=15, copertura IEX
insufficiente).

**La letteratura è coerente con il FAIL su ogni dimensione controllabile**:
PEAD large-cap competuto dal 2006 (Martineau 2021), declino strutturale per
persistenza SUE calante (Kettell 2022), costi consumano 70-100% (Chordia 2009).
Il tone edge vivo è a orizzonte 5-10g con embedding contestuali (Hameleers
2025, Chung 2023) — S7 usava hold 20d + polarity, la forma che decade OOS.

**La strategia non ha mai avuto carburante**: il consensus provider (ALPHA-A2)
non è mai stato wired → `surprise_pct` spesso null → il gate reject-None
(`signal.py:42`) filtrava tutti i segnali → zero ordini lifecycle. Questo non
è un bug di logica S7 (i gate sono corretti) ma un gap di integrazione
upstream — la causa strutturale del "mai live".

**Confronto con S1/S4**: S7 condivide con S1/S4 il pattern di **forma debole**
(long-only, polarity, large-cap, orizzonte mismatch). La differenza è la
**governance**: S7 è stata misurata a decision-grade e killata; S1/S4 sono
live nonostante IC<0/decay senza kill criterion. Per la cross_review, S7 è il
**caso di studio** di come il processo decisionale dovrebbe funzionare — lo
stesso disciplinamento dovrebbe applicarsi a S1/S4.

## 2. Specifica (fase 01)

**Segnale** (`signal.py:28-56`, git `1dd2c35`): LLM parsifica 8-K SEC →
`EarningsLLMOutput` (`pead.py:10-21`: ticker, filing_type, eps_actual,
eps_consensus, surprise_pct (opzionale), direction ∈ {beat,miss,inline,no_eps},
guidance, confidence∈[0,1]). `EarningsSurpriseClassifier.to_signal` gate:
reject no_eps/inline (:35), confidence<0.70 (:38), surprise None (:42),
|surprise|<0.05 (:45) → `SurpriseSignal` (symbol, direction, surprise_pct,
confidence, filing_id, detected_at, hold_until = detected_at+20d).

**Strategia** (`strategy.py:32-71`): `compute_target_weights` filtra
`direction=="beat" and confidence>=0.70 and is_active(as_of)`, pari peso
`max_position_pct=0.05`, cap sleeve `max_sleeve_pct=0.25` (max 5 posizioni),
hold 20 giorni (`is_active` gate `ts <= hold_until`).

**Config** (`PEADConfig`, `strategy.py:10-19`): max_position_pct=0.05,
max_sleeve_pct=0.25, min_confidence=0.70, surprise_threshold=0.05,
hold_days=20. `enabled=false`, `allocation_pct=0.15`.

**Runtime (rimosso)**: worker 8-K Ollama, worker Finnhub earnings, connector
calendar, API routes, beat task `pead-ingestion`, Redis store, config entry,
PEAD_* settings — tutti rimossi in `d1e6de6`. `pead_signals` table mai
materializzata.

## 3. Ipotesi (fase 02)

S7 scommette sul **PEAD canonico** (Ball-Brown 1968, Bernard-Thomas 1989):
sottoreazione alle informazioni degli earnings → drift misurabile. MA
implementa una **variante specificamente più debole**:
- **Long-only beat** (non simmetrico) → gamba debole,
- **Surprise LLM-extracted** (non consensus reale, ALPHA-A2 mai wired) →
  carburante debole,
- **Large-cap ALPHA-A5** (non small-cap dove l'edge vivo) → universo competuto,
- **Hold 20d** (non 5-10g dove il tone edge vivo) → orizzonte oltre il decay,
- **Polarity tone** (non embedding contestuale) → feature che decade OOS.

**Tesi dichiarata**: "L'LLM estrae tone qualitativo dall'8-K che predice il
drift 20g meglio del fattore numerico. Edge ortogonale a S1/S4." Questa è
l'alpha-specifico di S7.

**Falsificazione**: 4 valutazioni pre-registrate: ALPHA-A5 large-cap FAIL
(drift=beta, n=76), POC-1 small/mid INCONCLUSIVE_DATA (n=15), POC-2 transcript
tone FAIL decision-grade (IC≈0, n=73, cross-model robusto), Finnhub 0 eventi.
PO-5 pre-registrato "Se POC-2 FAIL → REMOVE" → applicato.

## 4. Letteratura (fase 03)

| Aspetto | Finding | Impatto S7 |
|---|---|---|
| PEAD large-cap | competuto dal 2006 (Martineau 2021), persistenza SUE calante (Kettell 2022) | ❌ universo competuto (FAIL ALPHA-A5) |
| PEAD small-cap | vivo, net 3.8% (Quant Decoded 2025) | ❌ non raggiunto (POC-1 n=15) |
| Costi | consumano 70-100% (Chordia 2009) su illiquido; ~null su large-cap | ⚠️ costi bassi ma edge ~zero |
| Tone orizzonte | vivo 5-10g (Hameleers Sharpe>1), decade 20g | ❌ hold 20d troppo lungo |
| Tone feature | embedding vivo, polarity decade OOS (Chung 2023) | ❌ polarity = debole |
| Tone direzione | negatività > positività (Druz 2015) | ❌ long-only = gamba debole |
| Carburante | analyst revisions (Livnat 2006, Vettore D) | ❌ consensus/revisioni mai wired |
| Resurgence post-2020 | ambigua, +280% large-cap (Nyllinge 2025) | ⚠️ non azionabile (rimossa pre-evidenza) |

**Convergenza**: la letteratura non supporta "large-cap, long-only beat,
polarity tone, hold 20d, consensus assente generi alpha netto." La forma
viva (small-cap + embedding + 5-10g + simmetrico + analyst revisions) è
**l'opposto dell'implementazione S7**.

## 5. Alpha assessment (fase 04)

**Implementazione: `NEGATIVE` (alta confidenza).** POC pre-registrato a
sample decision-grade: ALPHA-A5 FAIL (drift=beta, n=76), POC-2 FAIL (IC
tone/excess_20d = +0.012 ≈0, tercile −0.93% invertito, split-half opposti,
cross-model ρ=+0.858, n=73). La variante alpha-specifica (tone qualitativo)
è attivamente confutata, non "non misurata."

**Fenomeno: `DECAYED`.** Large-cap competuto (Martineau, Kettell); small-cap
vivo MA non raggiunto. Resurgence post-2020 ambigua, non azionabile (S7
rimossa pre-evidenza). Il fenomeno PEAD-tone non è globalmente morto (vive in
altre forme) MA è morto **nella forma S7**.

**Decomposizione beta**: long-only beat → market beta (drift=beta SPY
confermato in ALPHA-A5); event/news beta (core del PEAD); quality beta
(beat=firms profittevoli); size beta assente (large-cap). L'IC (che netta
beta) ≈0 → coerente con POC-2.

**Confidenza ALTA** (la più alta dell'audit): sample decision-grade (n=73 vs
S4 n=34), cross-model agreement (non artefatto), kill criterion pre-registrato
(no confirmation bias), coerente con letteratura, zero ordini (evidenza
pulita, no rumore di esecuzione).

## 6. Implementation audit (fase 06)

| Asse | Verdetto |
|---|---|
| 1 Data timing | OK (design, event-time 8-K) |
| 2 Look-ahead | OK (design, detected_at=filing) |
| 3 Leakage | N/A (mai eseguito) |
| 4 Survivorship | OK (8-K all filings) MA universe large-cap competuto |
| 5 Backtest | N/A (mai runnato WF; POC = event-study/IC, metodologicamente corretto) |
| 6 Signal gen | OK gates, **CARBURANTE ZERO** (consensus mai wired) |
| 7 Allocation | OK (design, pari peso cap sleeve) MA caller mai wired |
| 8 Risk controls | PARZIALE (cap sleeve 25%, hold 20d; no stop/regime) |
| 9 Execution | **N/A — MAI WIRED** (orchestrator nessun match S7) |
| 10 Accounting | N/A (zero trade) |
| 11 Paper trading | **N/A — MAI PROMOSSA** (mode=research, approved=f) |
| 12 Runtime | **MORTO — MAI LIVE** (zero ordini, zero decisioni, table inesistente) |

**Runtime (DB read-only 2026-08-04):**
```
strategy_lifecycle S7: mode=research, approved=f, promoted_at=NULL
\d pead_signals → "Did not find any relation" (TABLE NON MATERIALIZZATA)
pg_tables ILIKE '%pead%' → 0 rows
execution_decisions reason ILIKE '%s7%' OR '%pead%' → 0 (ZERO)
trades exit_reason: portfolio_sell(304), blank(49), stop_loss(33),
  sentiment_reversal(25), LEGACY_FLATTEN(16) → NESSUN tag S7
```

## 7. Bug confermati (fase 07)

| ID | Severità | Tipo | Conferma |
|---|---|---|---|
| **BUG-A** | HIGH (operatività) | carburante zero (consensus mai wired) | repro_1 ESEGUITO |
| **BUG-B** | HIGH (validità) | universo large-cap competuto | lifecycle + letteratura |
| **BUG-C** | MEDIUM (forma) | long-only + polarity + hold 20d | POC-2 IC≈0 + statica |
| **BUG-D** | LOW (persistenza) | `pead_signals` table mai materializzata | DB `\d` |
| **OBS-1** | positivo | guard anti-reintro `test_p0_13` viva | repro_2 ESEGUITO |
| UNCONFIRMED | — | hold 20 calendari vs trading days | mai eseguito |

**BUG-A** (carburante zero): `surprise_pct` opzionale (`pead.py:17`) + gate
reject-None (`signal.py:42`) + consensus mai wired (ALPHA-A2) → zero segnali
passano i gate → zero ordini. Gap upstream, non logica S7.

**BUG-B** (universo competuto): large-cap ALPHA-A5 dove PEAD morto (Martineau)
vs small-cap vivo (Quant Decoded 3.8%) non raggiunto (POC-1 n=15).

**BUG-C** (forma debole): long-only beat (gamba debole, Druz) + polarity
(feature che decade OOS, Chung) + hold 20d (oltre il decay tone, Hameleers) =
combinazione specificamente debole. POC-2 IC≈0 è la misurazione diretta.

**BUG-D** (persistenza): `pead_signals` table mai materializzata (DDL solo
doc, nessuna migration). Irrilevante (zero ordini) MA gap di persistenza.

**OBS-1** (positivo): `test_p0_13_strategy_containment.py:62-97`
(`TestS7NotInOperationalRegistry`) vivo nel working tree — impedisce la
reintroduzione di S7 nel `StrategyRegistry`. Best-practice governance che
manca a S1/S4.

**Critico**: i 4 bug sono tutti coerenti con la rimozione. Nessun revival
parziale (es. solo wired il consensus) salverebbe S7 — BUG-B (universo) e
BUG-C (forma) sono sulla forma debole. **Zero bug di path live** (mai
esistetto).

## 8. Stato di integrazione

- **Registry**: S7 assente (rimossa, guard `test_p0_13`).
- **Lifecycle DB**: `mode=research`, `approved=f`, nessun `promoted_at`.
- **Live**: MAI — orchestrator/scheduler nessun match S7.
- **Persistenza**: `pead_signals` table inesistente.
- **Guard anti-reintro**: viva (`test_p0_13`).
- **Costo affondato**: FMP Starter $29 (consensus) speso per esplorazione,
  killato dopo misurazione (non mantenuto sunk-cost).

## 9. Conclusione e raccomandazione

S7 è **rimossa correttamente** sulla base di un'evidenza decision-grade
pre-registrata. È il caso di best-practice governance dell'audit:

1. **Il segnale non predice** — POC-2 FAIL decision-grade (IC≈0, cross-model
   robusto). L'edge numerico (ALPHA-A5) è competuto su large-cap; l'edge
   qualitativo dichiarato (tone) è confutato a sample sufficiente.
2. **La forma è debole** — long-only + polarity + hold 20d + large-cap è la
   combinazione specificamente decaduta/competuta del fenomeno PEAD.
3. **Il carburante era assente** — consensus mai wired → zero ordini
   lifecycle. La strategia non ha mai esposto il sistema a rischio.
4. **La governance è corretta** — PO-5 pre-registrato, applicato su FAIL,
   rimozione pulita, guard anti-reintro viva.

**Raccomandazione**:
- **Non resuscitare S7** nella forma attuale. La guard `test_p0_13` deve
  restare viva (impedisce il zombie revival).
- **Qualora si volesse esplorare nuovamente il PEAD**: non è un revival di S7
  ma una **strategia nuova** che deve (1) wired il consensus/revisioni
  (ALPHA-A2/D1), (2) spostarsi su small/mid-cap (richiede copertura dati
  adeguata, non IEX), (3) usare embedding contestuali (non polarity), (4) hold
  5-10g, (5) simmetrizzare (short su miss), (6) passare un POC pre-registrato
  a decision-grade (n≥73) con kill criterion prima di qualunque promozione.
- **Applicare lo stesso disciplinamento a S1/S4** (cross_review): misurare IC
  a decision-grade, killare su FAIL pre-registrato. S1/S4 sono live nonostante
  IC<0/decay — S7 è il modello di come dovrebbero essere gestite.
- **Monitorare la resurgence post-2020** (Nyllinge 2025): se la resurgence
  large-cap si stabilizza (n>4 anni), rivalutare — MA con la forma corretta
  (embedding, non polarity), non con la forma S7.

**Rischi chiave**: nessuno runtime (strategia rimossa, zero ordini). L'unico
rischio è un **revival non-giustificato** se la guard `test_p0_13` viene
indebolita — mitigato dal test vivo. Il costo affondato ($29 FMP) è corretto
(killato dopo misurazione, non mantenuto).

**Lezione metodologica**: S7 è l'esempio di come il processo decisionale del
progetto **dovrebbe** funzionare sempre — POC pre-registrato, misurazione
decision-grade, kill criterion applicato, rimozione pulita, guard
anti-reintro. La differenza con S1/S4 (live con IC<0/decay) è il **deficit di
governance** che la cross_review deve indirizzare.

---
**Stato audit S7:** fasi 01-08 **done**. Strategia rimossa, auditata da git
history + docs + DB read-only. Verdetto NEGATIVE (implementazione) +
DECAYED (fenomeno) con alta confidenza. Best-practice governance.