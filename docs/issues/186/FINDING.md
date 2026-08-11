# Issue #186 — Perché un peso S4 è 0 con segnale preservato, sopra soglia e nei top-5?

> Investigazione, NON fix. Il fix è un'issue separata, da aprire al termine
> del freeze #171 (2026-08-03 → 2026-09-28). Tutte le quantificazioni sono
> fatte sul DB live (`alembic-postgres-1`, 40 giorni di observation window).

## TL;DR

Il filtro di freshness a `src/strategies/s4/strategy.py:167-169` (QS-07, b4421f2,
"backtest/live parity") scarta i segnali FIX-D-preserved quando lo strategy
viene chiamato dall'orchestrator. Il segnale passa il filtro `_filter_stale_signals`
e `_preserve_stale_signals_for_open_positions` (entrambi in `portfolio_scheduler.py`),
finisce in `signals_df`, ma viene buttato fuori da `_signals_as_of` perché
`generated_at >= ts - max_signal_age_hours (4h)` non passa per segnali di 19+ ore.

Il ranker vede quindi solo i fresh (DIS nel caso 14:22). Per ogni posizione non
in `target_weights`, `NewsDrivenTactical.__call__:101-114` emette SELL. Etichetta
storica `expired` (pre-#184); il fix #184 la corregge a `unknown` quando il
ciclo è in piedi, ma il meccanismo di uscita resta lo stesso.

## Riproduzione

Test `tests/strategies/test_s4_fix_d_parity_defect.py` (6 test, 5 rossi, 1 verde
di "bug witness"). Setup del 2026-08-05 14:22 replicato punto per punto.

```
$ /home/stefano/.venv/bin/pytest tests/strategies/test_s4_fix_d_parity_defect.py -v
test_2026_08_05_14_22_fix_d_preserved_signals_are_dropped_before_ranking PASSED
test_signals_as_of_preserves_signals_already_admitted_by_caller FAILED
test_fix_d_preserved_signal_loses_zero_weight[MCD-0.393-0.725-19.87]  FAILED
test_fix_d_preserved_signal_loses_zero_weight[NVO-0.656-0.85-19.62]   FAILED
test_fix_d_preserved_signal_loses_zero_weight[PFE-0.514-0.8-19.87]    FAILED
test_fix_d_preserved_signal_loses_zero_weight[PLTR-0.383-0.675-18.87] FAILED
5 failed, 1 passed in 0.31s
```

Il test "verde" documenta che il bug è in produzione (DIS sopravvive, gli
altri 4 no). I 5 rossi documentano il comportamento atteso post-fix.

## Meccanismo (passo per passo)

File coinvolti:
- `src/workers/portfolio_scheduler.py:3621-3624` — FIX-D preserva MCD/NVO/PFE/PLTR
- `src/workers/portfolio_scheduler.py:3644-3656` — `signals_df` include i preservati
- `src/strategies/s4/strategy.py:156-169` — `_signals_as_of` ri-filtra per età
- `src/strategies/s4/strategy.py:97-114` — `target_weights = {}` → SELL per ogni
  posizione non inclusa

I numeri del caso 14:22:

| Simbolo | Score | Conf | generated_at | tick_time | Age | In signals_df | Dopo _signals_as_of | In target_weights | Trade |
|---------|-------|------|--------------|-----------|-----|---------------|---------------------|-------------------|-------|
| DIS     | +0.572| 0.775| 14:15:09     | 14:22:00  |  7m | sì (fresh)    | sì                  | sì                | BUY   |
| NVO     | +0.656| 0.85 | 18:45:26 (-1d)| 14:22:00 | 19h37m | sì (preserved) | **no**              | **no**            | SELL  |
| PFE     | +0.514| 0.80 | 18:30:57 (-1d)| 14:22:00 | 19h51m | sì (preserved) | **no**              | **no**            | SELL  |
| MCD     | +0.393| 0.725| 18:30:18 (-1d)| 14:22:00 | 19h51m | sì (preserved) | **no**              | **no**            | SELL  |
| PLTR    | +0.383| 0.675| 19:30:21 (-1d)| 14:22:00 | 18h51m | sì (preserved) | **no**              | **no**            | SELL  |

Il QS-07 filter a `strategy.py:167-169` è applicato **in** `_signals_as_of`,
che è chiamato dal `__call__` dello strategy. A quel punto `signals_df`
contiene già i 4 preservati, ma vengono scartati dall'età.

## Quantificazione su 40 giorni (DB live)

Conteggio `exit_mechanism = 'expired'` in `execution_decisions` per simboli S4
negli ultimi 40 giorni. **27 occorrenze totali**, distinte in due sotto-categorie:

| Sotto-categoria | n  | Avg hold (h) | Min hold (h) | Max hold (h) | Net P&L |
|-----------------|----|--------------|--------------|--------------|---------|
| Preserved-stale (age > 18h) | 20 | 57.4 | 18.5 | 625.5 | +$4.47 |
| Just-over-threshold (age 4.1-4.4h) | 7 | 4.1 | 3.3 | 4.3 | -$103.70 |

La prima sotto-categoria è il caso del 14:22 (4 simboli nello stesso ciclo,
tutti 19+ ore di età). 20/27 = **74% delle "expired" exits** sono in realtà
preserved-stale (la cui uscita è il bug del QS-07).

La seconda è la "vera" scadenza: il segnale è scivolato oltre le 4h di
freshezza, non c'è una posizione aperta che FIX-D possa preservare (o la
posizione è già chiusa per altra ragione, es. stop). 7/27 = 26%.

**P&L aggregato non è discriminante**: i preserved-stale hanno +$4.47 totali
(~0, dispersi), i just-over-threshold hanno -$103.70. Il meccanismo di uscita
non guarda il prezzo, guarda solo il fatto che il ranker non produce più
quei simboli — quindi la stessa logica può chiudere in profitto o in perdita
in cicli successivi, indipendentemente dal sottostante.

## Periodo di detenzione effettivo di S4 (input per #179/#180)

Calcolato su tutti i trade S4 chiusi negli ultimi 40 giorni (`stop_strategy = 'S4'`,
`exit_time IS NOT NULL`, `exit_time > NOW() - INTERVAL '40 days'`).

| Metrica | Valore |
|---------|--------|
| N trade | 75 |
| Avg hold | 15.21 h |
| **Median hold** | **4.25 h** |
| Total net P&L | +$298.01 |

Il **median = 4h15m** corrisponde esattamente al `max_signal_age_hours = 4h`
+ 15min del ciclo scheduler. La distribuzione è bimodale:

- Modo 1: ~4h15m (closed per "expired" — 7 just-over-threshold + parte di
  preserved-stale che escono al primo ciclo utile dopo la mezzanotte)
- Modo 2: ~18-24h (closed per "expired" — preserved-stale del ciclo 14:22
  successivo, con età che ha superato le 4h dal segnale precedente)
- Outlier: 1 trade a 625h = 26 giorni (WDC, preservato da FIX-D per un mese
  intero — `FORENSIC_DAILY_REPORT_2026-08-07` §WDC)

**Significato per #179/#180**: il kill criterion basato su IC di S4 è
calcolato su segnali con emivita di 4h, ma il periodo di detenzione reale
è 4-24h (1-6 cicli). La misura di IC dovrebbe essere:
- Stratificata per "freschi" (< 4h) e "preserved" (4-24h)
- Il bucket "preserved" ha P&L ~0 e IC probabilmente negativo — è il bucket
  che spinge l'IC aggregato di S4 in territorio negativo

## È un difetto o un comportamento voluto?

QS-07 (`docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md` riga 26, "DONE
deployed solo backtest, zero impatto live") era una scelta deliberata per
parità backtest/live: il commento a `strategy.py:163-169` dice testualmente
"the live cycle drops signals older than max_signal_age_hours at each tick".

Ma il commento **descrive solo metà del live**: il live cycle droppa gli
stale a meno che FIX-D non li preservi, e quando FIX-D li preserva entrano
in `signals_df`. Il parity check presume che `signals_df` contenga solo
freschi, ma in realtà contiene freschi + preserved.

Il naming del filter ("_signals_as_of" + comment "the live cycle drops
signals older than max_signal_age_hours") e la sua posizione (in `_signals_as_of`,
chiamato dal `__call__`) lo fanno sembrare un secondo check live-equivalente.
Non lo è: il check live è già passato una volta in `_build_strategy_instance`,
e questo secondo check **riscrive** quella decisione senza sapere chi l'ha
presa.

**Verdetto**: difetto di design, non volontà esplicita. La volontà
(documentata) era "parità con il live cycle" — non "filtra tutto ciò che
è più vecchio di 4h, due volte". Il filter QS-07 fu introdotto prima di
FIX-D (`b4421f2` vs FIX-D aggiunto dopo); quando FIX-D ha esteso il
significato di `signals_df`, il filter non è stato aggiornato.

## Fuori scope (esplicito)

- Fix del filter: vietato dal freeze #171 (correttezza OK, ma il filter
  è un meccanismo di sizing, non un bug evidente per un operatore in
  observation window). Issue di fix separata da aprire a fine freeze.
- Modifica dell'etichetta `expired`/`unknown`: già fatto da #184 (merged
  ma non ancora deployato — vedi "Stato del fix" sotto).
- Cambio di comportamento di S4: il DoD di #186 dice "indagine, non fix".

## Stato del fix #184

Il fix #184 (commit `df45cb1`) è mergiato sul branch ma NON deployato. Il DB
live mostra 27 `expired` e **0 `unknown`**: i 27 record sono tutti scritti
prima del deploy del fix. Quando il fix verrà deployato, i prossimi casi
preserved-stale saranno etichettati `unknown` (test in
`tests/workers/test_exit_mechanism_observed.py:139-160`).

## File toccati da questo lavoro

- **Creato**: `tests/strategies/test_s4_fix_d_parity_defect.py` — 6 test
  riproducibili (5 rossi, 1 verde di witness). Da mantenere per il freeze
  #171 e da usare come acceptance test del fix.
- **Creato**: `docs/issues/186/FINDING.md` — questo file.
- Non modificato: `src/strategies/s4/strategy.py` (freeze #171, sizing non
  ritoccabile), `src/workers/portfolio_scheduler.py` (correttezza OK),
  `docs/evidence/findings.json` (vietato), `docs/evidence/OBSERVATION_CHARTER.md`
  (vietato), `scripts/roadmap_queue.txt` (vietato).

## Verifica su questo lavoro

```bash
# test del difetto: devono essere 5 rossi + 1 verde
.home/stefano/.venv/bin/python -m pytest tests/strategies/test_s4_fix_d_parity_defect.py -v

# query SQL di riproduzione conteggi (output nel §"Quantificazione"):
docker exec alembic-postgres-1 psql -U trading -d trading -c "
SELECT exit_mechanism, COUNT(*)
FROM execution_decisions
WHERE decision = 'SELL' AND score = 0 AND reason LIKE '%S4%'
  AND tick_time > NOW() - INTERVAL '40 days'
GROUP BY exit_mechanism
ORDER BY exit_mechanism;
"

# quantificazione periodo di detenzione effettivo:
docker exec alembic-postgres-1 psql -U trading -d trading -c "
SELECT COUNT(*) AS n,
       ROUND(AVG(EXTRACT(EPOCH FROM (exit_time - entry_time))/3600.0)::numeric, 2) AS avg_h,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM (exit_time - entry_time))/3600.0))::numeric, 2) AS median_h
FROM trades
WHERE stop_strategy = 'S4' AND exit_time IS NOT NULL
  AND exit_time > NOW() - INTERVAL '40 days';
"
```
