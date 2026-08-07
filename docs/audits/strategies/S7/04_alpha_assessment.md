# S7 — 04 Alpha Assessment

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift)
**Data:** 2026-08-04
**Verdetto implementazione:** `NEGATIVE` (POC-2 FAIL decision-grade, IC≈0)
**Verdetto fenomeno:** `DECAYED` (large-cap competuto; small-cap vivo ma non
raggiunto; resurgence ambigua post-2020)

## Sintesi del verdetto

S7 è **rimossa** sulla base di un'evidenza **decision-grade pre-registrata**.
Questo è il caso più pulito dell'intero audit: il progetto ha misurato l'alpha a
campione sufficiente, il FAIL era robusto cross-modello, e il kill criterion
(PO-5) è stato applicato. **Il verdetto è NEGATIVE con alta confidenza** — non
UNPROVEN, non DECAYED-ambiguo: la variante alpha-specifica (tone polarity su
large-cap, hold 20d) è **attivamente confutata**.

| Criterio | Esito | Evidenza |
|---|---|---|
| Implementazione genera alpha numerico (raw surprise)? | **NEGATIVE** | ALPHA-A5 n=76: drift=beta SPY, hit 51%<55%, no dose-response, mediana −1.07% |
| Implementazione genera alpha qualitativo (tone)? | **NEGATIVE** | POC-2 n=73 decision-grade: IC(tone, excess_20d)=+0.012 (~0), tercile −0.93% invertito, split-half opposto, cross-model ρ=+0.858 |
| Universo raggiungibile? | **NO** | POC-1 small/mid n=15 INCONCLUSIVE_DATA, copertura IEX insufficiente |
| Carburante (consensus/revisioni) wired? | **NO** | ALPHA-A2 consensus mai wired → surprise_pct null → soglia 0.05 mai superata → zero ordini |
| Backtest OOS valido? | **N/A** | mai runnato (zero ordini lifecycle); `pead_signals` table mai materializzata |
| Net alpha dopo costi/decay/capacity/regime? | **NEGATIVE** | edge competuto su large-cap (costi ~null ma edge ~null); small-cap non raggiunto |

## Implementazione: NEGATIVE (con alta confidenza)

S7 è **l'unica strategia dell'audit con un POC pre-registrato a sample
decision-grade**. Le altre (S1, S4) sono live senza IC misurato a decision-grade
(S4 ha IC<0 MA a 34 giorni, small-sample; S1 non ha IC cross-sectionale). S7 è
stata **misurata correttamente e killata correttamente**:

- **ALPHA-A5 large-cap** (n=76): il test dell'edge **numerico** (raw surprise).
  Risultato: drift = beta SPY (NON alpha), hit-rate 51% (<55% gate), no
  dose-response (sorprese più grandi non producono drift più grande), media
  excess +0.05%, mediana −1.07%. **FAIL pulito**: l'edge numerico su large-cap
  è competuto. Coerente con Martineau 2021 (PEAD large-cap morto dal 2006),
  Kettell 2022 (persistenza SUE calante), Chordia 2009 (large-cap drift
  near-zero dopo costi).

- **POC-2 transcript tone** (n=73, **decision-grade**): il test dell'edge
  **qualitativo dichiarato** (ALPHA-A3, l'alpha-specifico di S7). Risultato:
  - `IC(tone, excess_20d) = +0.012` — **non-predittivo** (IC≈0),
  - tercile spread −0.93% — **invertito** (alto tone → drift negativo, opposto
    all'ipotesi),
  - split-half −0.230 / +0.244 — **incoerente** (il segno flippa tra metà del
    campione, segno non stabile),
  - **cross-model agreement kimi↔glm ρ=+0.858** — due LLM indipendenti
    concordano (il FAIL non è artefatto di un modello, è la forma).
  **FAIL robusto** a sample decision-grade. Coerente con Chung 2023 (polarity
  tone decade OOS post-2020), Hameleers 2025 (tone alpha decade a 20g, S7 hold
  = 20d), Druz 2015 (negatività > positività, S7 long-only = debole).

- **POC-1 small/mid** (n=15): INCONCLUSIVE_DATA (n<30, copertura IEX
  insufficiente). L'universo dove l'edge vivo sopravvive (small-cap net 3.8%,
  Quant Decoded) **non è raggiungibile** con i dati del progetto.

**Conclusione implementazione**: la variante specifica implementata da S7
(large-cap, last surprise, polarity tone, long-only beat, hold 20d) è la
**combinazione specificamente debole** su ogni dimensione che il progetto
poteva controllare. Il FAIL non è un artefatto di esecuzione o di un modello,
ma la conclusione corretta su una strategia configurata sulla **forma
competuta** del fenomeno PEAD.

## Fenomeno: DECAYED (con caveat resurgence)

- **Large-cap (universo S7)**: PEAD **competuto/decaduto** dal 2006 (Martineau
  2021), declino strutturale (Kettell 2022 — persistenza SUE calante, non solo
  arbitraggio). Costi consumano 70-100% (Chordia 2009) ma edge già ~zero su
  large-cap. → **DECAYED**.

- **Small-cap (non raggiunto)**: PEAD **vivo**, net 3.8% (Quant Decoded 2025),
  ma S7 non raggiungeva quell'universo (POC-1 n=15). Il fenomeno non è globalmente
  morto — **è morto nella forma che S7 implementava** (large-cap).

- **Resurgence post-2020** (Nyllinge-Oldenburg 2025): large-cap drift 0.52%→
  1.99%, +280%. **Ambigua**: 4 anni di dati (2021-24), meccanismo non chiaro
  (retail/passivo non spiegano). S7 è stata rimossa 2026-07-15 **prima** che
  questa evidenza fosse disponibile/robusta. La resurgence **non salva S7**:
  (1) la decisione è congrua con l'evidenza al tempo (2026-07), (2) la resurgence
  è ambigua e non stabile, (3) anche se reale, l'implementazione S7 (polarity,
  hold 20d, long-only) resta la forma debole. → **DECAYED con caveat** (possibile
  resurgence non stabile, MA non azionabile per S7).

- **Tone (sub-fenomeno)**: edge **vivo ma a orizzonte 5-10g con embedding
  contestuale**, non polarity a 20g. La forma S7 è DECAYED (polarity decade OOS
  post-2020, Chung 2023).

**Verdetto fenomeno**: **DECAYED** per la forma large-cap/polarity/20g che S7
implementava. Il fenomeno PEAD-tone **non è globalmente morto** (small-cap vivo,
  embedding vivo) MA è morto nella forma S7. La resurgence post-2020 è ambigua e
  non azionabile. Classifico DECAYED (non NEGATIVE fenomeno) perché il fenomeno
  canonico sopravvive in altre forme — la strategia è morta, non l'anomalia.

## Decomposizione beta (cosa S7 avrebbe esposto se fosse live)

- **Market beta**: long-only beat → beta di mercato (positivo in rialzo) →
  non alpha (coerente col finding ALPHA-A5 "drift=beta SPY").
- **Momentum beta**: hold 20d post-earnings → overlap con momentum (S1) MA
  event-driven, non time-series momentum → overlap parziale.
- **Size beta**: large-cap ALPHA-A5 → niente size premium (l'universo dove
  PEAD vivo è small-cap, il opposto).
- **Quality beta**: beat earnings → firms profittevoli → quality exposure
  (parziale, non isolato).
- **Event/news beta**: earnings announcement → beta di evento (partly
  prezzabile, il core del PEAD).

**Isolamento**: la domanda pertinente è "il drift post-earnings è alpha o beta?"
La letteratura (Ng-Rusticus-Verdi 2008: ERC più bassi per high-cost, drift =
compensazione informazione) e l'evidenza progetto (ALPHA-A5: drift=beta SPY)
indicano che **su large-cap il "drift" è quasi interamente beta di mercato, non
alpha**. L'IC (che netta beta) sarebbe ≈0 → coerente con POC-2 IC +0.012.

## Criteri di promozione / governance

- **PO-5 pre-registrato (condizionale)**: "Se POC-2 FAIL → REMOVE S7" →
  POC-2 FAIL → REMOVE applicata (2026-07-15, commit d1e6de6, #38 chiuso).
  **Esempio di governance corretta**: kill criterion pre-registrato, applicato
  su evidenza decision-grade. Da contrastare con S1/S4 (live nonostante
  IC<0/decay, nessun kill criterion).
- **Mai wired**: S7 non è mai stata nel `PortfolioOrchestrator` (P0-13,
  guard test_p0_13_strategy_containment), `enabled=false`, zero ordini
  lifecycle. Nessun rischio di esecuzione su alpha negativo (a differenza di
  S4 che esegue live con IC<0).
- **`strategy_lifecycle`**: `mode=research`, `approved=f`, nessun
  `promoted_at`. MAI promossa a paper/live. Coerente.
- **Cost**: FMP Starter $29 (consensus source) speso per l'esplorazione MA
  S7 rimossa → costo affondato corretto (killato dopo misurazione, non
  mantenuto sunk-cost).

## Confidenza del verdetto

**ALTA** (la più alta dell'audit):
- Sample **decision-grade** (n=73 POC-2, vs S4 n=34 small-sample).
- **Cross-model agreement** ρ=+0.858 (due LLM indipendenti concordano sul
  FAIL → non artefatto).
- **Kill criterion pre-registrato** (PO-5) → non confirmation bias.
- **Coerente con la letteratura** su ogni dimensione controllabile.
- **Zero ordini lifecycle** → nessun rumore di esecuzione, evidenza pulita.

**Unica fonte di incertezza**: la resurgence post-2020 (Nyllinge 2025) potrebbe
implicare che l'edge large-cap non sia permanentemente morto MA: (1) ambigua,
(2) non azionabile per S7 (rimossa), (3) anche se reale, la forma S7 resta
debole. Non cambia il verdetto.

## Confronto con gli altri verdetti (ante-cross_review)

| Strategia | Implementazione | Fenomeno | Live? | Governance |
|---|---|---|---|---|
| S1 | DECAYED | DECAYED | sì (paper) | nessun kill criterion |
| S2 | NEGATIVE | DECAYED | no (dead config) | dead config (non governance) |
| S3 | UNPROVEN | UNPROVEN (non-decayed) | no (morto) | non misurato (dead) |
| S4 | NEGATIVE (IC<0) | DECAYED | **sì (paper, esegue)** | promotion_blocked (MA esegue) |
| **S7** | **NEGATIVE** | **DECAYED** | **no (rimossa)** | **PO-5 kill criterion applicato** |

**S7 è il caso di best-practice governance** dell'audit: l'unica strategia
misurata a decision-grade, killata su FAIL pre-registrato, mai esposta a
esecuzione su alpha negativo. Il **risultato** (NEGATIVE) è uguale a S2/S4, MA
la **governance** è radicalmente migliore. Per la cross_review: il sistema
dovrebbe applicare lo **stesso criterio PO-5 a S1/S4** (IC<0/decay misurato →
ridurre a shadow o rimuovere) invece di mantenerle live.

---
**Stato fase:** 04_alpha_assessment = **done**. Prossimo cursore: `S7:05_code_mapping`.