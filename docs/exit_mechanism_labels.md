# `exit_mechanism`: cosa significa ogni etichetta

`execution_decisions.exit_mechanism` (migration 039, #60) spiega perché una posizione è
uscita con peso di portafoglio 0.0%. È la colonna su cui si appoggiano i report forensic
giornalieri, la misura del damper anti-whipsaw (#61/#83) e gli audit di strategia: se
mente, mentono anche loro.

## Le etichette pre-#184 non sono affidabili

Fino alla correzione di **#184**, l'etichetta non veniva osservata ma **dedotta dall'età
dell'ultimo segnale presente in DB**: `expired` se più vecchio di `max_signal_age_hours`,
`whipsaw` altrimenti. Bastava che il peso andasse a zero per qualunque altra ragione
perché il classificatore rispondesse comunque una delle due, in base all'orologio.

Caso documentato: il **2026-08-05 alle 14:22** FIX-D aveva *esplicitamente ri-ammesso* i
segnali di MCD, NVO, PFE e PLTR nello stesso ciclo in cui quelle quattro posizioni sono
state vendute con motivazione `expired` e con il testo «no counter-signal found, position
closed» — cioè descrivendo come causa la condizione che FIX-D usa per **non** chiudere.

**Conseguenza pratica:** ogni conteggio per `exit_mechanism` su righe precedenti al
deploy di #184 va letto come una stima per età, non come una misura del meccanismo. In
particolare vanno riconsiderate le conclusioni che si appoggiano al conteggio degli
`expired` e dei `whipsaw` (audit strategie del 2026-08-04, `docs/audits/strategies/S4/`).

### Come distinguere le righe pre- e post-fix

Senza bisogno di conoscere la data di deploy, il testo del motivo basta a separarle:

| | pre-#184 | post-#184 |
|---|---|---|
| `expired` | contiene `no counter-signal found` | contiene `discarded for age this cycle` |
| `whipsaw` | comincia con `[whipsaw] Portfolio rebalance:` | comincia con `[whipsaw] S4 signal reached the portfolio engine fresh` |

Le etichette `unknown`, `below_entry_gate`, `fallback_filtered` e
`entry_freshness_filtered` **esistono solo dopo** il fix: la loro presenza data la riga
da sola.

## Vocabolario (post-#184)

L'etichetta deriva dalla *disposizione* del segnale S4, cioè da cosa il ciclo ha fatto a
quel segnale, registrato nel punto in cui lo fa
(`src/portfolio/exit_classification.py`).

| etichetta | disposizione osservata |
|---|---|
| `no_signal` | nessun segnale S4 in DB per quel simbolo |
| `expired` | segnale scartato per età in questo ciclo, e FIX-D non l'ha preservato |
| `whipsaw` | segnale fresco arrivato al motore di portafoglio, peso 0 lo stesso (taglio del rank, `min_score`, o un vincolo di portafoglio) |
| `below_entry_gate` | segnale sotto la soglia `feedback:entry_threshold` attiva |
| `fallback_filtered` | segnale escluso dal ranking perché FinBERT-fallback (#108) |
| `entry_freshness_filtered` | segnale escluso dal gate di freschezza news (#150) |
| `unknown` | il ciclo non ha registrato nessuna disposizione, **oppure** il segnale è arrivato al motore preservato da FIX-D e il peso è comunque 0 |
| `s1_weight_drop`, `s2_weight_drop`, … | uscita di una posizione aperta da una strategia non-S4 (#72) — non passa dal classificatore S4 |

## Uscite che NON passano da questo classificatore

`exit_mechanism` spiega solo le uscite **per peso di portafoglio a 0**. Tre uscite arrivano da
altri percorsi e non hanno (né devono avere) un'etichetta qui — si leggono da
`trades.exit_reason`:

| `trades.exit_reason` | chi la scrive | nota |
|---|---|---|
| `sentiment_reversal` | `_sentiment_reversal_sells` → `_submit_reversal_force_sells` | contro-segnale **ensemble** ≤ −0.35 e più fresco di 60 min. Cicla su **tutte** le posizioni del broker senza filtrare per sleeve: liquida anche posizioni S1 (#182). Il P&L va alla sleeve proprietaria, non a S4. Dal 2026-09-03 queste uscite hanno un controfattuale (#450) |
| `stop_loss` | `_submit_stop_loss_exit_order` | **nessuna riga dal 2026-07-14**: `risk.stop_loss: 0.0` disattiva il controllo. Resta solo la telemetria shadow (`stop_shadow_log`) e l'allarme a −15% (#161) |
| `portfolio_sell` | ribilanciamento ordinario | è il caso in cui `exit_mechanism` è popolato, con il vocabolario qui sopra |

`unknown` non è un fallimento: è la risposta corretta quando il meccanismo non è stato
osservato. Le uscite su segnale preservato da FIX-D ricadono qui perché il motivo per cui
quei pesi vengono azzerati **non è ancora stabilito** — indagine separata, issue #186.

## Invariante

Un segnale preservato da FIX-D (`_preserve_stale_signals_for_open_positions`) non può
produrre un'uscita etichettata `expired`: è una contraddizione in termini. Coperto da
`tests/workers/test_exit_mechanism_observed.py`.
