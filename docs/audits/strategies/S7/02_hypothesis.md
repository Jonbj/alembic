# S7 — 02 Ipotesi scientifica / d'investimento

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift)
**Data:** 2026-08-04

## Ipotesi canonica

S7 scommette sul **Post-Earnings Announcement Drift (PEAD)**: dopo una sorpresa
negli earnings announcement, il prezzo non si aggiorna istantaneamente all'effetto
informativo → **drift misurabile** nella direzione della sorpresa nei giorni/
settimane seguenti. Anomalia canonica dell'efficient-market (Ball-Brown 1968,
Foster-Olson-Shevlin 1984, Bernard-Thomas 1989, 1990).

**Claim accademico**: i mercati sottoreagiscono (underreaction) alle informazioni
contenute nell'annuncio. La sotto-reazione è attribuita a:
- **Anchoring/conservatism** (investitori ancorano al pre-announcement price),
- **Attention limitation** (Hirshleifer-Lim-Teoh 2009: information overload nei
  periodi di earnings season),
- **Information processing costs** (raccogliere/parse EPS, consensus, guida),
- **Disposition effect** (vendi vincitori troppo presto → drift soffocato).

**Perché dovrebbe essere prezzata** (la domanda del paper-trader): non lo è —
PEAD è una delle anomalie più persistenti documentate, **ma in erosione**. La
forma "large-cap" (S7 ALPHA-A5) è **competuta** (efficienza del mercato +
costi). La forma "small-cap + transcript tone qualitativo" (ALPHA-A3) è
dove l'edge sopravvive accademicamente — MA S7 non raggiungeva quell'universo.

## Variante specifica testata da S7

S7 implementa una **variante specifica** del PEAD canonico:

1. **Long-only beat**: `direction == "beat"` solo. Il PEAD canonico è
   **simmetrico** (drift positivo dopo beat, drift negativo dopo miss). S7
   monetizza solo la gamba positiva (come S4). → **gamba debole** della
   anomalia (Heston-Sinha: positive news incorporata più velocemente).

2. **Surprise classificata da LLM**: non surprise numerica da consensus reale
   (Zacks/Refinitiv) ma **LLM parsing dell'8-K SEC** (DK-CoT) →
   `EarningsLLMOutput.surprise_pct` calcolato dal modello. L'edge dichiarato è
   **transcript tone** (ALPHA-A3), non surprise numerica (ALPHA-A2). L'LLM
   dovrebbe estrarre alpha qualitativo che fattori numerici non catturano.

3. **Hold 20 giorni**: orizzonte **medio** (non tattico giornaliero come S4, non
   momentum 252g come S1). Corrisponde al PEAD canonico (Bernard-Thomas: drift
   visibile a 30-60g, ma concentrato nei primi 1-5g; Wang 2014: drift
   persistente a 60g ma attenuato). S7 hold 20d è un compromesso ragionevole
   tra catturare il drift e limitare l'esposizione.

4. **Gates multipli**: `confidence≥0.70` (LLM certo), `|surprise_pct|≥0.05`
   (sorpresa materiale), `direction∈{beat,miss}` (evento informativo reale).
   Gate `surprise_pct null → reject` (consensus assente → no edge).

5. **Cap sleeve 25%**: S7 è una **sleeve** dedicata (max 25% del book), non
   overlay a tutto il book. → isola il PEAD risk budget.

## Divergenze chiave dall'ipotesi canonica

| Dimensione | PEAD canonico | S7 implementato | Implicanza |
|---|---|---|---|
| Direzione | simmetrico (beat+miss) | long-only beat | gamba debole |
| Surprise source | consensus numerico (Zacks) | LLM 8-K tone | edge qualitativo (A3 vs A2) |
| Universo | small/mid (edge vivo) | large-cap ALPHA-A5 (competuto) | edge competuto |
| Orizzonte | 1-60g drift | hold 20d | ragionevole |
| Sizing | risk-adjusted | pari peso 5%, cap 25% | semplice |

**Tesi di S7** (esplicita): "L'LLM estrae tone qualitativo dall'8-K che predice il
drift 20g meglio del fattore numerico (surprise %). L'edge qualitativo è
**ortogonale** a S1/S4 (event-driven, non momentum/sentiment news)." Questa è
l'alpha-specifico di S7 — la differenziazione dichiarata vs gli altri fattori.

## Falsificabilità (come il progetto l'ha testata)

S7 è **rimossa** sulla base di 4 valutazioni pre-registrate (lifecycle doc §3):

1. **ALPHA-A5 large-cap** (n=76): drift = beta SPY (NON alpha), hit 51% <55%
   gate, no dose-response (surprise size ↮ drift magnitude), media excess
   +0.05%, mediana −1.07%. **FAIL**: l'edge numerico su large-cap è competuto.

2. **POC-2 transcript tone** (n=73, **decision-grade**): l'edge **qualitativo
   dichiarato** (A3) testato a campione sufficiente.
   - `IC(tone, excess_20d) = +0.012` (~0, **non-predittivo**),
   - tercile spread −0.93% (**invertito** — alto tone → drift negativo),
   - split-half −0.230 / +0.244 (**opposti**, segno incoerente),
   - **cross-model agreement kimi↔glm ρ=+0.858** (FAIL robusto: non artefatto
     di un modello, due LLM indipendenti concordano sul FAIL).

3. **POC-1 small/mid** (n=15): **INCONCLUSIVE_DATA** (n<30, copertura IEX
   insufficiente — l'universo dove l'edge vivo non è raggiungibile).

4. **Finnhub** (n=0): nessun evento (calendar ~30g back insufficiente).

**PO-5 (pre-registrato, condizionale)**: "Se POC-2 FAIL → REMOVE S7." POC-2
FAIL → **REMOVE applicata** (commit `d1e6de6`, 2026-07-15, #38 chiuso).

## Sintesi dell'ipotesi

S7 scommetteva su **un'ipotesi accademicamente valida (PEAD) MA in una forma
specificamente più debole di quella testata dal progetto**:

- L'edge **numerico** (raw surprise) su large-cap è **competuto** (beta, non
  alpha) → ALPHA-A5 FAIL.
- L'edge **qualitativo** (transcript tone, l'alpha-specifico di S7) è
  **confutato cross-modello** a sample decision-grade (IC≈0, n=73) → POC-2 FAIL.
- L'universo dove l'edge accademico sopravvive (small/mid) non è **raggiungibile**
  con copertura sufficiente → POC-1 INCONCLUSIVE_DATA.

**L'ipotesi non è confermata** — anzi, la variante alpha-specifica (tone
qualitativo) è attivamente confutata. Il progetto ha correttamente **rimosso**
S7 sulla base dell'evidenza pre-registrata, invece di mantenerla in research
indefinitamente. Questo è un **risultato metodologico positivo**: il kill
disciplinato di un'ipotesi FAIL è la поведение corretta, non il fallimento.

**Confronto con S1/S4**: S1 (momentum) e S4 (sentiment) sono DECAYED/NEGATIVE
**ma ancora live** (la governance non le ha rimosse). S7 è l'unica strategia
che il progetto ha **effettivamente killato** sull'evidenza. Per la cross_review,
S7 è il **caso di studio** di come il processo di decisione dovrebbe funzionare
(POC pre-registrato, FAIL → REMOVE) — da confrontare con S1/S4 che persistono
nonostante IC<0 / decay.

---
**Stato fase:** 02_hypothesis = **done**. Prossimo cursore: `S7:03_literature`.