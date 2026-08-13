# Issue #186 — Perché un peso S4 è 0 con segnale preservato, sopra soglia e nei top-5?

> Investigazione, NON fix. Il fix è tracciato dall'issue separata **#236**
> (`fix(#186): QS-07 freshness filter drops FIX-D preserved signals`), da
> eseguire al termine del freeze #171 (2026-08-03 → 2026-09-28). Tutte le
> quantificazioni sono fatte sul DB live (`alembic-postgres-1`) su una finestra
> di 40 giorni; le query sono riportate per intero in §"Quantificazione" e
> §"Verifica", e i numeri di questo documento sono il loro output.

## TL;DR

Il filtro di freshness a `src/strategies/s4/strategy.py:167-169` (QS-07, `b4421f2`,
"backtest/live parity") scarta i segnali FIX-D-preserved quando lo strategy
viene chiamato dall'orchestrator. Il segnale passa `_filter_stale_signals` e
`_preserve_stale_signals_for_open_positions` (entrambi in `portfolio_scheduler.py`),
finisce in `signals_df`, ma viene buttato fuori da `_signals_as_of` perché
`generated_at >= ts - max_signal_age_hours (4h)` non passa per segnali di 19+ ore.

Il ranker vede quindi solo i fresh (DIS nel caso 14:22). Il simbolo scartato
esce da `target_weights` di S4, il suo peso merged scende a 0 e
`src/portfolio/orchestrator.py:247-265` emette la SELL (`strategy_id="merged"`):
il loop "Sell any positions whose symbol dropped out of the merged target
entirely" vende ogni posizione il cui simbolo non è più in `merged_weights`.
Etichetta storica `expired` (pre-#184); #184 — **deployato**, ~2026-08-07 — la
corregge a `unknown`, ma il meccanismo di uscita resta identico.

## Il path di uscita in live (correzione a una bozza precedente)

Una bozza di questo finding attribuiva la SELL a `NewsDrivenTactical.__call__:101-114`.
È sbagliato: quel ramo è il path di **backtest** (lo strategy chiamato come
callable, che emette `Order` propri). In live il portfolio-cycle non chiama
`__call__`: l'orchestrator estrae i pesi via `_extract_target_weights`
(`src/portfolio/orchestrator.py:349-366`, che per `strategy_id == "S4"` chiama
`_signals_as_of(ts)` + `compute_target_weights` — la chiamata a `_signals_as_of`
è a `orchestrator.py:365`), li fonde in `merged_weights`
(`orchestrator.py:190`) e poi vende in `orchestrator.py:247-265` con
`strategy_id="merged"`.

Due conseguenze non ovvie, entrambe visibili solo sul path live:

1. **La SELL è marcata `"merged"`, non `"S4"`.** L'attribuzione a S4 va
   ricostruita dalla `reason` della decisione, non dal solo `strategy_id` —
   vedi §"Periodo di detenzione effettivo".
2. **Un simbolo pesato anche da S1 sopravvive.** Il drop-out di S4 azzera solo
   la sua quota: se un'altra sleeve pesa lo stesso simbolo, `merged_weights[sym]`
   resta > 0 e nessuna SELL viene emessa. Il difetto colpisce quindi solo i
   simboli **esclusivi di S4** — il che spiega perché non tutte le posizioni
   con segnale preservato vengono chiuse.

## Riproduzione

Test `tests/strategies/test_s4_fix_d_parity_defect.py` — **2 verdi + 5 xfail(strict)**.

```
$ .venv/bin/python -m pytest tests/strategies/test_s4_fix_d_parity_defect.py -v
test_2026_08_05_14_22_fix_d_preserved_signals_are_dropped_before_ranking PASSED
test_age_filter_still_drops_unmarked_stale_signals                       PASSED
test_signals_as_of_honours_fix_d_preserved_marker                        XFAIL
test_fix_d_preserved_signal_keeps_non_zero_weight[NVO]                   XFAIL
test_fix_d_preserved_signal_keeps_non_zero_weight[PFE]                   XFAIL
test_fix_d_preserved_signal_keeps_non_zero_weight[MCD]                   XFAIL
test_fix_d_preserved_signal_keeps_non_zero_weight[PLTR]                  XFAIL
2 passed, 5 xfailed in 0.38s
```

I test modellano il fix come un **marcatore di provenienza**: una colonna
booleana `fix_d_preserved` in `signals_df`, che `_signals_as_of` deve
rispettare. I due verdi fissano il presente e il vincolo che il fix non deve
rompere; i cinque xfail fissano il contratto post-fix:

- `..._dropped_before_ranking` (verde) — bug witness: col marcatore già presente,
  oggi sopravvive solo DIS.
- `..._age_filter_still_drops_unmarked_stale_signals` (verde) — **guardia di
  backtest**: senza marcatore il filtro d'età deve restare. In backtest nessuno
  filtra `signals_df` a monte, quindi QS-07 è l'unica difesa contro la
  contaminazione T0. Il fix deve esentare *solo* i segnali marcati; questo test
  deve restare verde prima e dopo.
- `..._honours_fix_d_preserved_marker` (xfail) — sul ciclo 14:22 completo tutti
  e 5 i segnali devono sopravvivere a `_signals_as_of`.
- `..._keeps_non_zero_weight[4 simboli]` (xfail) — check funzionale end-to-end:
  il segnale marcato deve arrivare fino a un peso > 0 dal ranker.

`strict=True`: se un xfail passa, il fix è arrivato e il test va promosso a verde.

## Meccanismo (passo per passo)

File coinvolti:
- `src/workers/portfolio_scheduler.py:3620-3628` — FIX-D preserva MCD/NVO/PFE/PLTR
- `src/workers/portfolio_scheduler.py:3651-3661` — `signals_df` include i preservati
- `src/strategies/s4/strategy.py:156-169` — `_signals_as_of` ri-filtra per età
- `src/portfolio/orchestrator.py:349-366` — `_extract_target_weights`, che chiama `_signals_as_of` (riga 365)
- `src/portfolio/orchestrator.py:247-265` — peso merged ≤ 0 → SELL `strategy_id="merged"`

I numeri del caso 14:22:

| Simbolo | Score | Conf | generated_at | tick_time | Age | In signals_df | Dopo _signals_as_of | In target_weights | Trade |
|---------|-------|------|--------------|-----------|-----|---------------|---------------------|-------------------|-------|
| DIS     | +0.572| 0.775| 14:15:09     | 14:22:00  |  7m | sì (fresh)    | sì                  | sì                | BUY   |
| NVO     | +0.656| 0.85 | 18:45:26 (-1d)| 14:22:00 | 19h37m | sì (preserved) | **no**              | **no**            | SELL  |
| PFE     | +0.514| 0.80 | 18:30:57 (-1d)| 14:22:00 | 19h51m | sì (preserved) | **no**              | **no**            | SELL  |
| MCD     | +0.393| 0.725| 18:30:18 (-1d)| 14:22:00 | 19h51m | sì (preserved) | **no**              | **no**            | SELL  |
| PLTR    | +0.383| 0.675| 19:30:21 (-1d)| 14:22:00 | 18h51m | sì (preserved) | **no**              | **no**            | SELL  |

## Quantificazione su 40 giorni (DB live)

Le uscite S4 per peso-zero si trovano in `execution_decisions`
(`decision='SELL' AND score=0 AND reason LIKE '%S4%'`), con `exit_mechanism`
`expired` (pre-#184) oppure `unknown` (post-#184). L'**età del segnale** che ha
causato l'uscita non ha una colonna propria, ma è recuperabile dalla `reason`
via regex `age=([0-9.]+)h`. Il **periodo di detenzione** e il P&L richiedono il
join con `trades`: non esiste una FK dalla decisione di uscita al trade, quindi
si aggancia per `symbol` dentro la finestra di uscita (`exit_time` nello stesso
ciclo della decisione), prendendo il round trip con l'entry più recente:

```sql
WITH s4_exits AS (
    SELECT d.id, d.symbol, d.tick_time, d.exit_mechanism,
           (substring(d.reason FROM 'age=([0-9.]+)h'))::numeric AS signal_age_h
    FROM execution_decisions d
    WHERE d.decision = 'SELL' AND d.score = 0 AND d.reason LIKE '%S4%'
      AND d.exit_mechanism IN ('expired', 'unknown')
      AND d.tick_time > NOW() - INTERVAL '40 days'
),
matched AS (
    -- Nessuna FK decisione-di-uscita → trade: si aggancia per simbolo dentro la
    -- finestra del ciclo (-15min/+60min dal tick), prendendo l'entry più recente.
    SELECT e.*,
           EXTRACT(EPOCH FROM (t.exit_time - t.entry_time))/3600.0 AS hold_h,
           t.net_pnl
    FROM s4_exits e
    LEFT JOIN LATERAL (
        SELECT t.* FROM trades t
        WHERE t.symbol = e.symbol AND t.exit_time IS NOT NULL
          AND t.exit_time BETWEEN e.tick_time - INTERVAL '15 minutes'
                              AND e.tick_time + INTERVAL '60 minutes'
        ORDER BY t.entry_time DESC LIMIT 1
    ) t ON TRUE
)
SELECT exit_mechanism,
       CASE WHEN signal_age_h > 18 THEN 'preserved-stale (age>18h)'
            ELSE 'just-over-threshold (age<=18h)' END AS bucket,
       COUNT(*) AS n,
       ROUND(AVG(signal_age_h), 2) AS avg_age_h,
       -- Il cap a 26h isola i round trip del ciclo corrente: sopra ci sono solo
       -- posizioni di legacy-book (GE 148h, XLF 28.8h, BP 625.5h) la cui entry
       -- precede di giorni il segnale che ne ha causato l'uscita.
       COUNT(*) FILTER (WHERE hold_h <= 26) AS n_core,
       ROUND(AVG(hold_h) FILTER (WHERE hold_h <= 26)::numeric, 2) AS avg_hold_h,
       ROUND(SUM(net_pnl) FILTER (WHERE hold_h <= 26)::numeric, 2) AS net_pnl
FROM matched
GROUP BY 1, 2 ORDER BY 1, 2;
```

Output (30 righe di uscita totali: 27 `expired` + 3 `unknown`):

| exit_mechanism | Sotto-categoria | n | Avg signal age (h) | n core (hold ≤ 26h) | Avg hold core (h) | Net P&L core |
|----------------|-----------------|---|--------------------|---------------------|-------------------|--------------|
| expired | Preserved-stale (age > 18h) | **19** | 20.61 | 18 | 19.39 | −$16.71 |
| expired | Just-over-threshold (age ≤ 18h) | **8** | 4.35 | 6 | 4.25 | −$88.35 |
| unknown | Preserved-stale (age > 18h) | 2 | 19.50 | 2 | 20.75 | −$31.94 |
| unknown | Just-over-threshold (age ≤ 18h) | 1 | 4.30 | 1 | 4.25 | −$8.82 |

Note di lettura:

- Lo split degli `expired` è **19/8**, non 20/7 come in una bozza precedente:
  19/27 = **70%** delle uscite "expired" sono preserved-stale.
- Le colonne "core" escludono i 3 round trip di legacy-book (GE 148h, XLF 28.8h,
  BP 625.5h); inclusi, i preserved-stale danno avg hold 51.29h / +$31.48 e i
  just-over 25.28h / −$130.71. Il segno del P&L aggregato **cambia** con
  l'inclusione: è la conferma che il P&L non è discriminante qui (n piccolo,
  code dominanti), non un risultato in sé.
- **#184 è deployato**: esistono 3 righe `unknown` (SONY 2026-08-11 14:22,
  HOOD 2026-08-11 18:22, IBM 2026-08-12 14:22). Una bozza precedente diceva
  "0 unknown, fix non deployato" — falso.
- **Eventi di difetto = 22** (19 `expired` preserved-stale + 3 `unknown`):
  l'etichetta cambia, il meccanismo no, quindi le `unknown` contano tutte.

### Distribuzione oraria (dove si concentra il difetto)

```sql
SELECT EXTRACT(HOUR FROM tick_time) AS hr, COUNT(*) AS n,
       ROUND(AVG((substring(reason FROM 'age=([0-9.]+)h'))::numeric), 2) AS avg_age_h
FROM execution_decisions
WHERE decision = 'SELL' AND score = 0 AND reason LIKE '%S4%'
  AND exit_mechanism = 'expired' AND tick_time > NOW() - INTERVAL '40 days'
GROUP BY 1 ORDER BY 1;
```

| Ora UTC | n | Avg signal age (h) |
|---------|---|--------------------|
| 14 | **16** | 20.16 |
| 15 | 1 | 22.60 |
| 16 | 1 | 22.10 |
| 18 | 5 | 8.30 |
| 19 | 4 | 4.40 |

**16/27 (59%) delle uscite cadono all'ora 14 UTC, con età media 20.16h**: è il
primo ciclo dopo il gap overnight, quando i segnali della sera prima hanno
appena superato le 4h. Le ore 18-19 raccolgono invece i casi just-over-threshold
(ora 19: età media 4.40h) — la scadenza "vera", intraday. Il difetto ha quindi
una firma temporale netta: **è un fenomeno di riapertura di sessione**, non un
rumore distribuito sulla giornata.

## Periodo di detenzione effettivo di S4 (input per #179/#180)

L'attribuzione a S4 non è univoca — vedi §"Il path di uscita in live": la SELL
merged non porta `strategy_id="S4"`, e `trades.stop_strategy` è valorizzato solo
per i trade con stop gestito da S4. Le due attribuzioni possibili danno numeri
diversi, e la differenza va dichiarata invece di scegliere in silenzio:

```sql
-- A: solo stop_strategy
SELECT COUNT(*) AS n,
       ROUND(AVG(EXTRACT(EPOCH FROM (exit_time - entry_time))/3600.0)::numeric, 2) AS avg_h,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (
           ORDER BY EXTRACT(EPOCH FROM (exit_time - entry_time))/3600.0))::numeric, 2) AS median_h,
       ROUND(SUM(net_pnl)::numeric, 2) AS pnl
FROM trades
WHERE stop_strategy = 'S4' AND exit_time IS NOT NULL
  AND exit_time > NOW() - INTERVAL '40 days';

-- B: COALESCE(stop_strategy, strategia dedotta dalla decisione d'ingresso)
SELECT COUNT(*) AS n,
       ROUND(AVG(EXTRACT(EPOCH FROM (t.exit_time - t.entry_time))/3600.0)::numeric, 2) AS avg_h,
       ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (
           ORDER BY EXTRACT(EPOCH FROM (t.exit_time - t.entry_time))/3600.0))::numeric, 2) AS median_h,
       ROUND(SUM(t.net_pnl)::numeric, 2) AS pnl
FROM trades t
LEFT JOIN execution_decisions d ON d.id = t.decision_id
WHERE COALESCE(t.stop_strategy, CASE WHEN d.reason LIKE '%S4%' THEN 'S4' END) = 'S4'
  AND t.exit_time IS NOT NULL AND t.exit_time > NOW() - INTERVAL '40 days';
```

| Attribuzione | N trade | Avg hold | Median hold | Total net P&L |
|--------------|---------|----------|-------------|---------------|
| A — `stop_strategy = 'S4'` | 78 | 15.21 h | **11.38 h** | +$257.25 |
| B — COALESCE con la decisione | 94 | 17.82 h | **18.50 h** | +$58.29 |

**La mediana di 4.25h di una bozza precedente non si riproduce con nessuna delle
due attribuzioni** ed è ritirata: era la mediana del solo sotto-insieme
just-over-threshold, non del portafoglio S4. Il valore corretto sta fra 11.4h (A)
e 18.5h (B), cioè fra 3 e 5 cicli di scheduler — comunque **molto oltre** le 4h
di emivita che il segnale dichiara.

**Significato per #179/#180**: il kill criterion basato su IC di S4 è calcolato
su segnali con emivita dichiarata di 4h, mentre la detenzione reale è 11-19h
mediani. La misura di IC dovrebbe essere stratificata per "freschi" (< 4h) e
"preserved" (> 4h); il bucket preserved è quello candidato a spingere l'IC
aggregato in territorio negativo. L'ampiezza dello spread A↔B (78 vs 94 trade,
+$257 vs +$58) è di per sé un finding: **l'attribuzione strategia→trade non è
affidabile**, e ogni metrica per-sleeve costruita su `stop_strategy` va riletta.

## È un difetto o un comportamento voluto?

QS-07 era una scelta deliberata per parità backtest/live: il commento a
`strategy.py:163-169` dice testualmente "the live cycle drops signals older than
max_signal_age_hours at each tick".

Ma il commento **descrive solo metà del live**: il live cycle droppa gli stale
*a meno che FIX-D non li preservi*, e quando FIX-D li preserva entrano in
`signals_df`. Il parity check presume che `signals_df` contenga solo freschi;
dopo FIX-D contiene freschi **+** preserved.

Il naming (`_signals_as_of`) e la posizione del filtro lo fanno sembrare un
secondo check live-equivalente. Non lo è: il check live è già passato una volta
in `_build_strategy_instance`, e questo secondo check **riscrive** quella
decisione senza sapere chi l'ha presa.

**Verdetto**: difetto di design, non volontà esplicita. La volontà documentata
era "parità con il live cycle", non "filtra due volte tutto ciò che è più vecchio
di 4h". QS-07 (`b4421f2`, 2026-06-30) è posteriore a FIX-D (`953a6a4`, 2026-06-25):
il filtro è stato aggiunto quando `signals_df` significava già "fresh + preserved",
ma il suo autore ha ragionato sul contratto pre-FIX-D.

> **Questo finding falsifica la riga QS-07 del backlog.**
> `docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md` riga 26 classifica QS-07 come
> "✅ DONE, deployed (solo backtest, **zero impatto live**)". L'impatto live esiste
> ed è misurato: 22 eventi di uscita in 40 giorni. La riga va corretta quando il
> freeze consentirà di toccare il backlog (parte di #236).

## Interazione col clock di rebalance (leva, non alternativa)

S4 dichiara `RebalanceFrequency.DAILY` (`src/strategies/s4/config.py:40`) ma non
è in `_REBALANCE_CLOCK_STRATEGIES` (`src/workers/portfolio_scheduler.py:413`,
oggi `frozenset({"S1"})`), e la sua istanza viene ricostruita a ogni ciclo con
`_last_rebalance=None` (`portfolio_scheduler.py:3732-3738`): in pratica S4 gira ogni
15 minuti, non una volta al giorno.

Clockare S4 ridurrebbe la frequenza con cui il difetto può scattare — ma **non è
un'alternativa neutra al fix**. L'esclusione di S4 dal clock è deliberata e
documentata sul posto (`portfolio_scheduler.py:408-413` e `3732-3737`): il
predicato DAILY è calendar-day based, quindi clockare S4 collasserebbe una
sleeve tattica news-driven a una decisione per sessione, **congelandone gli
ingressi intraday** — cioè esattamente il comportamento su cui è misurata la sua
domanda di osservazione. È quindi una **leva che richiede una deroga al freeze
#171 e una decisione dell'operatore**, non una scorciatoia al posto di #236.

## Omogeneità del periodo (limite dei conteggi)

I conteggi coprono ~2026-07-03 → 2026-08-12. FIX-D (`953a6a4`, 06-25) e QS-07
(`b4421f2`, 06-30) precedono l'inizio della finestra, quindi il meccanismo è
stabile per tutta la durata. **Non lo sono però le condizioni al contorno**:
dentro la finestra sono atterrati #150 (`6e33a34`, 07-28), #163 (07-30) e il
deploy di #184 (~08-07). I 22 eventi **non sono un campione regime-omogeneo**:
vanno letti come ordine di grandezza dell'esposizione al difetto, non come un
tasso stazionario da estrapolare.

## Fuori scope (esplicito)

- Fix del filtro: vietato dal freeze #171 → **issue #236**.
- Modifica dell'etichetta `expired`/`unknown`: già fatto e deployato da #184.
- Correzione della riga QS-07 nel backlog: parte di #236 (tocca un doc di stato).
- Cambio di comportamento di S4 (incluso il clock DAILY): decisione operatore.
- Il DoD di #186 dice "indagine, non fix".

## Verifica post-#233 (2026-08-13)

#233 ha consegnato l'indagine (questo documento + gli xfail test) lasciando
#186 aperto con `Part of #186`. Una ripassata post-merge conferma che ogni
affermazione del finding regge contro il codice e il DB live, e chiude #186:

- **Meccanismo verificato contro il codice.** Il filtro QS-07 a
  `src/strategies/s4/strategy.py:167-169` (`df = df[df["generated_at"] >= ts -
  timedelta(hours=max_age)]`) non guarda alcun marcatore di provenienza; il
  `signals_df` costruito in `portfolio_scheduler.py:3651-3661` non ha colonna
  `fix_d_preserved`. I preservati da FIX-D (age 19h) vengono quindi scartati.
  La SELL live nasce nel loop "dropped out of the merged target entirely" a
  `orchestrator.py:247-265`, non nel path backtest `__call__:101-114`.
- **Test riprodotti.** `pytest tests/strategies/test_s4_fix_d_parity_defect.py`
  dà `2 passed, 5 xfailed` (nessun XPASS: il fix #236 non è ancora applicato).
- **Conteggi DB riprodotti.** La query di §"Verifica" contro `alembic-postgres-1`
  restituisce `expired=27`, `unknown=3` — identico al finding (30 uscite S4 a
  peso-zero in 40gg, tutte `expired` o `unknown`; il breakdown preserved-stale /
  just-over-threshold di §"Quantificazione" è su `reason`, non su questa colonna).
- **DoD #186 tutta soddisfatta**: caso riprodotto (test) ✓, difetto di design
  stabilito ✓, occorrenze quantificate su 40gg con P&L ✓, issue di fix separata
  aperta con meccanismo descritto (**#236**) ✓, periodo di detenzione effettivo
  scritto (mediana 11-19h) ✓.
- **Correzioni di accuratezza**: i riferimenti di riga originali del finding a
  `orchestrator.py` puntavano fuori file (435-437 > 397 righe) e al blocco
  vol-targeter/log (271-288) anziché al loop di SELL (247-265); alcuni refs di
  `portfolio_scheduler.py` erano offset. Corretti in questo passaggio: il
  meccanismo descritto era già giusto, i puntatori no. Nessuna modifica al
  codice, solo a questo documento e ai docstring del test.

Il fix resta tracciato in **#236**, bloccato dal freeze #171. La modifica del
comportamento di S4 resta decisione dell'operatore. Con l'indagine completa e
verificata, #186 si chiude qui.

## File toccati da questo lavoro

- **Creato (#233)**: `tests/strategies/test_s4_fix_d_parity_defect.py` — 2 verdi +
  5 xfail(strict). Da mantenere per il freeze #171 e da usare come acceptance
  test di #236. Docstring corretti in questo passaggio (refs `orchestrator.py`).
- **Creato (#233)**: `docs/issues/186/FINDING.md` — questo file. Riferimenti di
  riga corretti in questo passaggio (§"Verifica post-#233").
- Non modificato: `src/strategies/s4/strategy.py` (freeze #171),
  `src/workers/portfolio_scheduler.py`, `docs/evidence/findings.json` (vietato),
  `docs/evidence/OBSERVATION_CHARTER.md` (vietato),
  `scripts/roadmap_queue.txt` (vietato),
  `docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md` (riga 26 da correggere in #236).

## Verifica su questo lavoro

```bash
# test del difetto: devono essere 2 verdi + 5 xfail (nessun XPASS: strict=True)
/home/stefano/Documents/Projects/Alembic/.venv/bin/python -m pytest \
    tests/strategies/test_s4_fix_d_parity_defect.py -v

# conteggio grezzo delle uscite S4 per peso-zero, per etichetta:
docker exec alembic-postgres-1 psql -U trading -d trading -c "
SELECT exit_mechanism, COUNT(*)
FROM execution_decisions
WHERE decision = 'SELL' AND score = 0 AND reason LIKE '%S4%'
  AND tick_time > NOW() - INTERVAL '40 days'
GROUP BY exit_mechanism
ORDER BY exit_mechanism;
"
```

Le query complete dietro le tabelle di §"Quantificazione" e §"Periodo di
detenzione" sono riportate per intero in quelle sezioni: eseguirle contro
`alembic-postgres-1` riproduce i numeri riga per riga (la finestra è relativa a
`NOW()`, quindi i conteggi scorrono nel tempo).
