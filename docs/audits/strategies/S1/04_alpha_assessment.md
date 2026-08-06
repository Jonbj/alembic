# S1 — 04 Valutazione: alpha netto genuino?

**Strategia:** S1 Multi-Lookback Relative Momentum
**Data:** 2026-08-04
**Input:** `02_hypothesis.md`, `03_literature.md`, `config/strategies.yaml` (note validità backtest), `MEMORY.md` (osservazione 2026-08-01, issue #171).

## Verdetto

**`DECAYED + LIKELY_BETA`** — S1 non è, allo stato attuale, una fonte plausibile di
**alpha netto genuino**. La combinazione di (a) decadimento post-pubblicazione
 dell'anomalia nel mercato US, (b) struttura long-only che la rende prevalentemente
beta di mercato, (c) backtest di progetto dichiarato invalido, e (d) choices di
design non allineate con la letteratura che improve lo Sharpe, porta a un alpha
atteso **basso o nullo** netto di costi. Non è `NEGATIVE` (nessuna evidenza che perda
sistematicamente), ma è **`UNPROVEN`** sul piano dell'evidenza di progetto e
**`LIKELY_BETA`** sul piano teorico-letterario.

## Motivazione (5 assi)

### Asse 1 — Decadimento dell'anomalia nel mercato di S1
Ben-David et al. (2021): rendimento mensile fattore momentum US **0.92%→0.16%
post-2002** (~6× più debole). S1 opera su equity US mega-cap — esattamente il
mercato dove il decay è documentato. Un qualsiasi backtest S1 che includa dati
pre-2002 sovrastima l'alpha atteso di un fattore grosso. Il progetto non ha
documentato un walk-forward post-2002 pulito (anzi: `config/strategies.yaml` dice
walk-forward "decorativo"). ⇒ **attenuazione forte** dell'alpha nominale.

### Asse 2 — Struttura long-only = beta dominante
Israel-Ross (2017), Chong (2017), Roncalli (2017): long-only momentum ha beta di
mercato ~0.9–1.0; alpha apparente 6.1% (CAPM) → 1.8% (4-fattori). S1 non shorta la
gamba dei perdenti → non isola il premio momentum puro. La memoria di progetto
(`MEMORY.md`, osservazione 2026-08-01) lo conferma empiricamente: "il momentum
long-short è morto ma il crollo è sulla gamba **short** che **non tradiamo**" —
cioè il progetto sa che la gamba che porterebbe alpha è quella che S1 non ha.
⇒ S1 è **principalmente beta di mercato con un tilt momentum**.

### Asse 3 — Scelte di design non catturano i miglioramenti documentati
- **No skip-month**: JT/MOP escludono l'ultimo mese per evitare il reversal 1m; S1
  include 21d (peso piccolo ma non nullo) → esposizione al reversal breve.
- **No vol-scaling aggregato**: BSC (2015) raddoppia Sharpe (0.53→0.97) vol-scalando
  l'intera sleeve; S1 fa solo sizing inverso-vol per-position → **non** cattura il
  beneficio aggregato anti-crash/anti-kurtosis.
- **Gate binario del segnale** (soglia 0, sizing indipendente dalla strength): la
  letteratura momentum scala l'esposizione per strength; S1 tratta z=0.01 e z=3.0
  uguale → perde il carry informativo del segnale.
- **Vol-normalizzazione per-asset del segnale** è proprietaria, non validata
  come fonte di alpha nella letteratura.

### Asse 4 — Validità del backtest di progetto
`config/strategies.yaml` (S1 note) dichiara il backtest **invalido**:
- same-bar fill (t+0) → **look-ahead di fill** (compro al close che genera il segnale)
- survivorship bias
- assunzione zero-cost
- stress/regime "circolare" (hindsight)
- walk-forward "decorativo"
- DSR con n_trials=1 (Deflated Sharpe non calcolato seriamente)
- no live stop-loss

In aggiunta, `01_specification.md` §4 ha trovato un **look-ahead ammesso dal
sorgente** (`signal.py:54-57`): il filtro di inclusione ticker usa statistiche
full-window (coverage 75%) → il backtest seleziona l'universo con informazione
futura. ⇒ **tutto l'evidenza di backtest di S1 è non-attendibile**; non si può
inferire alpha dai numeri di progetto.

### Asse 5 — Evidenza runtime/osservazione di progetto
Memoria (`MEMORY.md`, osservazione 2026-08-01, issue #171 tracciante): il progetto
ha congelato ogni taratura 03/08→28/09 perché **"alpha assoluto NON decidibile
con i nostri dati"** — le conclusive possibili sono solo confronti fra varianti.
S1 è in `supervised_paper` per osservazione, non per evidenza di alpha; è stato
**demoted** 2026-06-19 (P0-01). ⇒ il progetto stesso non claim-izza alpha per S1.

## Decomposizione fattoriale attesa (qualitativa)

| Componente | Stima qualitativa | Note |
|---|---|---|
| Beta di mercato | **alto** (~0.8–1.0) | long-only, no short leg |
| Fattore momentum (UMD/Carhart) | presente ma indebolito | versione long-only |
| Low-volatility tilt | moderato | sizing inverso-vol |
| Quality/growth tilt | piccolo, non testato | vincitori recenti |
| **Alpha residuo netto** | **basso–nullo** | decay US + costi + design |

## Possibili canali di sopravvivenza (accennati per onestà)

1. **Tilt long-only su mega-cap low-vol**: Brito-Ramos (2025) mostra alpha netto
   long-only **se** il trend è filtrato "puro". S1 opera su mega-cap e sizing
   inverso-vol → parzialmente sovrapponibile, **ma S1 non implementa il filtro
   "pure trend"** → non cattura esplicitamente questo canale.
2. **Crisis-alpha**: MOP-2012 mostra TSM positivo nei mercati estremi. S1 long-only
   non è TSMOM, ma un tilt momentum long su mega-cap può offrire payoff asimmetrico
   in regimi estremi. Non testato da progetto.

Nessuno dei due è sufficiente a spostare il verdetto senza evidenza di progetto
pulita.

## Condizioni che cambierebbero il verdetto

- Backtest rifatto con: fill t+1, costo reale, universo point-in-time (no look-ahead
  nel filtro), walk-forward vero, DSR con n_trials>1, walk-forward OOS post-2010.
- Dimostrazione di alpha netto > 0 post-costi in sample post-2010 US.
- Implementazione del vol-scaling aggregato (BSC) e/o filtro pure-trend (Brito-Ramos).

Fino ad allora: **`DECAYED + LIKELY_BETA`**.

---
**Stato fase:** 04_alpha_assessment = **done**. Prossimo cursore: `S1:05_code_mapping`.