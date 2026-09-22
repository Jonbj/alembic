# Cancello di riproducibilità del replay uscite — #614 Fase 2

**Data:** 2026-09-22
**Pre-registrazione:** `docs/evidence/PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md` §4
**Artefatto:** `docs/research/2026-09-22-gate-riproducibilita-uscite.json`
**Report di ricerca Fase 1:** `docs/research/2026-09-16-letteratura-uscite-controfattuale.md`

## Esito

> **SUPERATO**: replay 110.066,32 vs broker 110.025,01 → delta **+41,31 (+0,0375%)**, tolleranza pre-registrata ±2%.

La DoD 3 della issue ("cancello implementato e superato") è chiusa. Nessun ramo
controfattuale è stato eseguito (DoD 5: serve la riga in OBSERVATION_CHARTER.md,
che è dell'operatore).

## Finestra e dati

| | |
|---|---|
| Finestra | 2026-08-03 .. 2026-09-21 (35 sedute), ancoraggio 2026-07-31 |
| Fill applicati | 251 (122 buy / 129 sell / 0 post-campana) |
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
- Test: `tests/backtest/test_exit_replay.py` (19), `tests/scripts/test_replay_gate_614.py` (8).

Convenzioni dichiarate nel modulo (ereditate dalle raccomandazioni Fase 1):
mark carry-forward per close mancanti (come `economic_pnl.py`), fill post-campana
rotolati alla seduta dopo, equity money-weighted cash+posizioni (Q2/GIPS 1.A.35),
fallimento esplicito su close mancante all'ancoraggio (nessun prezzo inventato).

## La differenza, spiegata (§4: "non solo dichiarata sotto soglia")

Il delta terminale di +41,31 è **interamente una differenza di cash, non di
marcazione delle posizioni**, verificato con un dato indipendente dal cancello:

- cash broker al 22/09 (dopo i 3 fill di oggi, netti +431,08): **73.323,81**
- cash replay al 21/09 + fill di oggi: 72.933,98 + 431,08 = **73.365,06**
- scarto: **−41,25**, cioè il delta del cancello (−41,31) entro 6 centesimi.

Come nasce: il replay impone `cash₀ = equity_broker(31/07) − Σqty·close_RAW(31/07)`,
quindi ogni scarto fra quel mark iniziale e il cash vero del conto si propaga come
**costante additiva** per tutta la finestra — i fill passano identici sui due lati.
Coerentemente:

- il delta giornaliero replay−broker resta a 41,29–41,32 (±3 centesimi) per tutte
  le 8 sedute dall'11/09 mentre i prezzi si muovono: se fosse mark delle posizioni,
  oscillerebbe con loro;
- il delta non cresce col numero di fill (251 fill applicati, nessun drift di
  contabilità): la serie giornaliera è nell'artefatto (`serie_replay`/`serie_broker`);
- dividendi esclusi: nessuna ex-date sui simboli della finestra
  (`dividendi_annunciati_su_simboli_finestra: []` nell'artefatto).

Il segno (broker con ~41 $ di cash in meno della contabilità ricostruita) e il
gradino di +14,3 il 10→11/09 sono compatibili con attività cash del broker
(interessi/fee sul paper) e con l'incertezza del mark all'ancoraggio. Identificare
la voce esatta al centesimo richiederebbe lo statement cash del conto, che l'API
paper non espone: la decomposizione sopra esclude che la differenza venga dai
fill, dai dividendi o dal mark terminale, che è ciò che il cancello deve garantire
prima di fidarsi del replay su rami controfattuali.

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
