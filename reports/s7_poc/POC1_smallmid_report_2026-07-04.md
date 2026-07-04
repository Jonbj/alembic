# S7 Revival — POC-1 Small/Mid PEAD Report

**Run date:** 2026-07-04
**Window:** 2026-01-01 – 2026-05-15 · **Harness:** `scripts/backtest_s7_smallmid.py`
**Vendor:** FMP Starter (`from`/`to` earnings-calendar unlocked; confirmed Task 1)

Raw run log: `/tmp/poc1_run.log`. CSV: `reports/s7_poc/poc1_smallmid_events_2026-07-04.csv`.

## Parametri

| Parametro | Valore |
|---|---|
| Soglia surprise | \|surprise\| ≥ 5% |
| Cap bucket | small/mid = $300M–$10B (FMP `/stable/profile` `marketCap`) |
| Filtro liquidità | ADV 20g pre-evento ≥ $5M |
| Benchmark | IWM, stesso holding 20 sedute |
| Costo | 30bps round-trip (haircut su excess) |
| Entry/exit | giorno di trading dopo l'evento, +20 sedute (no look-ahead) |
| Prezzi | Alpaca daily bars, feed IEX |

## Due bug trovati e corretti durante l'esecuzione (trasparenza)

Il codice del piano (Task 3, riusa helper da `backtest_s7_pead.py` + `s7_poc_helpers.py`) conteneva due bug che, non corretti, avrebbero prodotto un falso "0 eventi small/mid" già al primo run:

1. **Mismatch di unità cap.** `_market_caps()` ritorna il market cap in **USD grezzi** (es. AAPL → 4.53e12), mentre `classify_cap()` (Task 2, pre-registrato) usa soglie in **milioni di USD** (300–10.000). Senza conversione, praticamente ogni azienda reale supera banalmente la soglia "large" (10.000 USD grezzi) → bucket small/mid sempre vuoto. Fix: `caps = {s: v/1_000_000 for s,v in ...}` prima della classificazione.
2. **Crash di batch su ticker preferred.** `_alpaca_bars()` fa richieste da 100 simboli e il suo `except` azzera **l'intero batch** se anche un solo ticker è invalido per Alpaca (es. `ABR-PD`, azione preferred). Poiché l'universo small/mid include preferred shares (ticker con `-`), un solo ticker "cattivo" per batch cancellava ~100 simboli buoni. Fix: escludere pre-fetch i ticker non-common-equity (contenenti `-`) — corretto anche nel merito, dato che il PEAD è un'anomalia da equity comune, non da preferred.

Entrambi i fix sono meccanici (conversione di unità, filtro asset class), non toccano le soglie del gate pre-registrato.

## Funnel

| Step | n |
|---|---|
| Eventi \|surprise\|≥5% (calendario FMP, tutta la finestra) | 8.440 |
| Simboli unici totali nel campione di eventi | 6.177 |
| Simboli campionati per market-cap lookup (budget Starter, ordine alfabetico) | 600 |
| Simboli small/mid ($300M–$10B) nel campione di 600 | 330 (314 common-equity + 16 preferred/rights esclusi) |
| Eventi small/mid (common-equity) | 442 |
| Scartati: nessuna barra IEX | 141 |
| Scartati: illiquidi (ADV20g < $5M) | 286 |
| **Eventi con barre + liquidità (finale)** | **15** |

## Risultato

| Direzione | n | mean lordo | mean netto (−30bps) | mediana lorda | hit netto | Verdetto |
|---|---|---|---|---|---|---|
| BEAT (long) | 7 | −0.26% | **−0.56%** | +1.02% | 57% | FAIL (n<30) |
| MISS (short, non gate primario) | 8 | −1.88%* | **−2.18%*** | −4.53% | 50% | FAIL (n<30) |

\*segno invertito per convenzione short (drift atteso negativo = "corretto")

**Verdetto gate POC-1 (piano 2026-07-04): `INCONCLUSIVE_DATA`** — n=15 totale, sotto la soglia minima n≥30 pre-registrata ("eventi small/mid con barre < 30 → INCONCLUSIVE_DATA"). Nessun confronto con la soglia di drift/hit-rate è quindi conclusivo.

## Onestà sui limiti (3 osservazioni)

1. **Non è un vero campione "small-cap".** I 15 eventi sopravvissuti hanno market cap $3.78B–$9.9B — tutti nella metà alta del bucket $300M–$10B, vicini al confine large-cap. Nessuna azienda sotto ~$2B ha superato sia il filtro barre IEX sia il filtro liquidità $5M ADV: il POC ha di fatto testato "upper-mid-cap", non small-cap propriamente detto.
2. **Il campionamento alfabetico dei primi 600 simboli (su 6.177 totali) non è casuale.** È il budget pre-registrato nel piano per la quota FMP Starter, ma introduce un bias di selezione non misurato (nessuna garanzia che i simboli A–C siano rappresentativi del PEAD small/mid nel suo complesso).
3. **Con n=7/8, i segni negativi di questo run (BEAT mean netto −0.56%, mediana +1.02%) non sono evidenza contro l'ipotesi** — sono compatibili con rumore puro data la numerosità. Il risultato onesto è "non misurato", non "misurato e negativo".

## Costo di una risposta conclusiva

Per arrivare a n≥30 servirebbe ampliare il campionamento di market-cap lookup ben oltre i 600 simboli alfabetici (es. tutti i 6.177, o un campione casuale stratificato) — entro la quota Starter (300 call/min) è fattibile in termini di rate limit, richiede solo più runtime (~10x, stimabile in 30-60 min) e non ha bisogno di ulteriore budget vendor. Il vero collo di bottiglia resta la copertura IEX/liquidità: molti small/mid-cap non hanno barre Alpaca o hanno ADV <$5M, indipendentemente da quanti se ne campionano.
