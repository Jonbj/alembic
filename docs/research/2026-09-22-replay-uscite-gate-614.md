# Cancello di riproducibilità del replay uscite — #614 Fase 2

**Data:** 2026-09-22
**Pre-registrazione:** `docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md` §4
**Artefatto:** `docs/research/2026-09-22-gate-riproducibilita-uscite.json`
**Report di ricerca Fase 1:** `docs/research/2026-09-16-letteratura-uscite-controfattuale.md`

## Esito

> **SUPERATO**: replay 110.028,23 vs broker 110.025,01 → delta **+3,22 (+0,0029%)**, tolleranza pre-registrata ±2%.
>
> **Correzione del 2026-09-24 (review della PR #645).** La prima esecuzione dava +41,31 (+0,0375%) e attribuiva lo scarto a una costante di cash. La spiegazione era sbagliata: il runner scaricava gli ordini con un margine di 7 giorni su `submitted_at` e perdeva uno **stop GTC su UNH sottomesso il 22/07 e riempito l'11/09**. Con il margine portato alla vita massima di un GTC Alpaca (90 giorni → 100) i fill passano da 251 a 252 e lo scarto scende a +3,22. L'esito del cancello non cambia; cambiano i numeri e la spiegazione qui sotto. Nessuna serie a valle usava ancora questo artefatto.

La DoD 3 della issue ("cancello implementato e superato") è chiusa. Nessun ramo
controfattuale è stato eseguito (DoD 5: serve la riga in OBSERVATION_CHARTER.md,
che è dell'operatore).

## Finestra e dati

| | |
|---|---|
| Finestra | 2026-08-03 .. 2026-09-21 (35 sedute), ancoraggio 2026-07-31 |
| Fill applicati | 252 (122 buy / 130 sell / 0 post-campana) |
| Posizioni | 50 iniziali → 45 finali |
| Equity broker | 109.530,66 → 110.025,01 |
| Fonti | ordini chiusi Alpaca (`GET /v2/orders?status=closed`), portfolio history 1D del broker (ground truth indipendente), barre giornaliere RAW, calendario sedute |

Strumenti:

- `src/backtest/engine/exit_replay.py` — motore puro (ricostruzione stato iniziale
  per inversione dei fill, replay sulle sedute, cancello ±tolleranza). La
  contabilità è quella di `src/backtest/engine/portfolio.py` (`VirtualPortfolio`),
  riusata e non riscritta (regola #169/#467).
- `scripts/replay_gate_614.py` — runner di sola lettura (nessuna scrittura su
  DB/Redis; unico output l'artefatto JSON).
- Test: `tests/backtest/test_exit_replay.py` (19), `tests/scripts/test_replay_gate_614.py` (10).

Convenzioni dichiarate nel modulo (ereditate dalle raccomandazioni Fase 1):
mark carry-forward per close mancanti (come `economic_pnl.py`), fill post-campana
rotolati alla seduta dopo, equity money-weighted cash+posizioni (Q2/GIPS 1.A.35),
fallimento esplicito su close mancante all'ancoraggio (nessun prezzo inventato).

## La differenza, spiegata (§4: "non solo dichiarata sotto soglia")

Il delta replay−broker giornaliero (serie `serie_replay`/`serie_broker` nell'artefatto)
parte da −6,01 il 03/08, si porta a +0,06 il giorno dopo e poi **cresce in modo
regolare di circa 0,1 $ per seduta** fino a +3,22, senza salti in corrispondenza dei
fill: 0,74 l'11/08, 2,06 il 28/08, 3,20 l'11/09, piatto a 3,20–3,23 nelle ultime
sei sedute.

- Non viene dai fill: una contabilità sbagliata dei fill produrrebbe gradini nei
  giorni di negoziazione, non una deriva liscia. Il gradino da +41 della prima
  esecuzione era proprio il fill UNH mancante.
- Non viene dai dividendi: nessuna ex-date sui simboli della finestra
  (`dividendi_annunciati_su_simboli_finestra: []`).
- Una deriva lineare di pochi centesimi al giorno è compatibile con una voce di cash
  del broker che il replay non modella (interessi o commissioni regolatorie sul
  paper). Per identificarla al centesimo servirebbe lo statement cash del conto, che
  l'API paper non espone (`/v2/account/activities` restituisce 404).

Tre dollari su 110.000 non sono un problema di riproducibilità: il replay rigioca i
fill reali in modo fedele, che è quanto il cancello deve garantire prima di usarlo
sui rami controfattuali.

## Cross-check di contesto (DB diagnostico, sola lettura)

Uscite chiuse nella finestra (tabella `trades`): `portfolio_sell` 71,
`hold_minimum_expiry` 39, `sentiment_reversal` 17, `stop_loss` 0. È la
popolazione su cui il controfattuale vero (quando pre-registrato) misurerà il
"chiude troppo presto?".

## Cosa resta (operatore)

1. La riga del controfattuale in `OBSERVATION_CHARTER.md` (DoD 5) — vietata a
   questo intervento.
2. Pre-registrazione dei rami controfattuali: condizionamento per motivo di
   uscita (Q5-rec-6), braccio sS (Q1-rec-5), orizzonti 1/2/5/10/21, costi da
   `src/backtest/costs/` su entrambi i rami (§3 della pre-registrazione).
3. Il gate è ripetibile: due run sulla stessa finestra danno lo stesso esito al
   centesimo (l'artefatto differisce solo per `generato_il`).
