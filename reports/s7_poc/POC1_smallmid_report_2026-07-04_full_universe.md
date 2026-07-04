# S7 Revival — POC-1 Small/Mid PEAD Report (Full Universe Rerun)

> **Supersede il run 2026-07-04** (`POC1_smallmid_report_2026-07-04.md`, 600 simboli
> alfabetici su 6.177 → `INCONCLUSIVE_DATA`, n=15 < 30). Questo run copre l'**intero
> universo** di simboli emersi dal calendario earnings, stessi gate pre-registrati
> (n≥30, mean net ≥ +1.5%, hit > 55%).

**Run date:** 2026-07-04 (rerun serale)
**Window:** 2026-01-01 – 2026-05-15 · **Harness:** `scripts/backtest_s7_smallmid.py` (`MAX_CAP_LOOKUPS=7000`)
**Vendor:** FMP Starter (`from`/`to` earnings-calendar unlocked)

Raw run log: `/tmp/poc1_full_run.log`. CSV: `reports/s7_poc/poc1_smallmid_events_2026-07-04.csv` (sovrascrive il file del run 600-alfabetico; l'originale resta recuperabile dal commit `9e99444`).

## Parametri (invariati dal run 600-alfabetico)

| Parametro | Valore |
|---|---|
| Soglia surprise | \|surprise\| ≥ 5% |
| Cap bucket | small/mid = $300M–$10B (FMP `/stable/profile` `marketCap`) |
| Filtro liquidità | ADV 20g pre-evento ≥ $5M |
| Benchmark | IWM, stesso holding 20 sedute |
| Costo | 30bps round-trip (haircut su excess) |
| Entry/exit | giorno di trading dopo l'evento, +20 sedute (no look-ahead) |
| Prezzi | Alpaca daily bars, feed IEX |

## Cosa cambia rispetto al run 600-alfabetico

`_MAX_CAP_LOOKUPS` reso overridabile via env (`MAX_CAP_LOOKUPS=7000`); con 6.180 simboli
unici nel campione di eventi, il lookup di market-cap ora copre **l'intero universo**,
non i primi 600 in ordine alfabetico. Nessuna modifica ai gate, alle soglie di
liquidità/surprise o alla logica di calcolo — solo l'ampiezza del campionamento.

## Funnel

| Step | n |
|---|---|
| Eventi \|surprise\|≥5% (calendario FMP, tutta la finestra) | 8.442 |
| Simboli unici totali nel campione di eventi | 6.180 |
| Simboli campionati per market-cap lookup | **6.180 (100%, era 600/6.177 = 9,7%)** |
| Eventi small/mid ($300M–$10B) | 4.151 su 3.066 simboli comuni (125 preferred/rights esclusi pre-fetch: ticker con `-`) |
| Scartati: nessuna barra IEX | 1.420 |
| Scartati: illiquidi (ADV20g < $5M) | 2.525 |
| **Eventi con barre + liquidità (finale)** | **206** |

## Risultato

| Direzione | n | mean lordo | mean netto (−30bps) | mediana lorda | hit netto | Verdetto |
|---|---|---|---|---|---|---|
| BEAT (long, gate primario) | 125 | −3.17% | **−3.47%** | −4.28% | 36% | **FAIL** |
| MISS (short, non gate primario)* | 81 | +3.21% | **+2.91%** | +3.31% | 63% | (informativo) |

\*segno invertito per convenzione short (drift atteso negativo = "corretto" per un vero effetto PEAD)

**Verdetto gate POC-1 (piano 2026-07-04): `FAIL`** — n=125 ≥ 30 (gate ora **conclusivo**,
non più INCONCLUSIVE_DATA). Mean netto −3.47% è ben sotto la soglia +1.5% richiesta, e in
direzione opposta all'ipotesi PEAD; hit netto 36% è ben sotto la soglia >55%.

## Range di market cap effettivo dei sopravvissuti

$669M – $9.991B. A differenza del run 600-alfabetico (dove i 15 sopravvissuti erano
concentrati $3.78B–$9.9B, di fatto "upper-mid-cap"), il campione completo include ora
veri small-cap vicino al floor $300M — la limitazione "non è un vero campione small-cap"
del run precedente è risolta dal rerun.

## Interpretazione

Il risultato non è solo "nessun drift misurabile": nel campione small/mid 2026 H1, il
segno **si inverte** rispetto all'ipotesi PEAD — i BEAT hanno un drift netto negativo
(mean −3.47%, hit 36%) mentre gli short su MISS (fuori gate primario, solo informativo)
avrebbero performato positivamente (mean netto +2.91%, hit 63%). Questo è compatibile con
un regime di **reversal/overreaction** post-earnings nella finestra osservata, non con
underreaction (PEAD classico). Con n=125 il risultato non è più attribuibile a rumore
campionario ridotto come nel run precedente (n=15) — è un FAIL statisticamente
sostanziale sul gate pre-registrato, non un dato mancante.

## Costo del rerun

Nessun costo vendor aggiuntivo (FMP Starter, stessa quota mensile) — solo runtime
(~80 minuti totali: calendario + 6.180 lookup market-cap + ~3.067 simboli di barre
Alpaca), entro la finestra 45–90 min stimata dal piano.
