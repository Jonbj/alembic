# Contratto del trial exit S4 — parametri congelati e contratto decisionale

**Firmato il 2026-08-22, prima di `n=0`.** Chiude [#293](https://github.com/Jonbj/alembic/issues/293).

Base documentale: `docs/s4-exit-research-2026-08-14/consolidato_exit.md` **§5–§8**. Decisione a monte:
[#242](https://github.com/Jonbj/alembic/issues/242) — opzione C, shadow reversibile
(`docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md`).

> **Scopo.** Togliere a noi stessi la possibilità di scegliere le regole dopo aver visto i risultati.
> Vale la stessa disciplina di `OBSERVATION_CHARTER.md`: **quello che è scritto qui vincola, quello
> che non è scritto qui non è un criterio.** Dopo `n=0`, ogni modifica *materiale* (§ Modifiche
> materiali) impone il restart del campione.

Questo documento **non autorizza alcun cambiamento alle uscite live**. Il perimetro è il solo ramo
shadow; la discontinuità è registrata in anticipo in `OBSERVATION_CHARTER.md` § Discontinuità.

Controparte macchina, letta dal gate di #301: **`config/s4_exit_trial.yaml`**. In caso di divergenza
fra i due, è una divergenza materiale e va risolta *prima* di `n=0`, non arbitrata dopo.

---

## 1. Parametri congelati

| # | parametro | valore congelato | fonte |
|---|---|---|---|
| 1 | **Famiglia confirmatory** | **P0 / P1**. `P2` (D+2 + contro-segnale qualificato) è marcata **`omitted` a `n=0`**: dichiarata nella famiglia ma non attivata. | §6 |
| 2 | **P0** | E0 congelata: comportamento as-is versionato al sample start (target-weight zero e relativi guard), riprodotto in shadow sugli stessi ingressi. Benchmark operativo reale, **non** una candidata da promuovere. | §6 |
| 3 | **P1** | D+2 time-only: tenuta massima D+2; nessuna uscita per silenzio fonte, `max_signal_age`, assenza dal top-5, rank drop, `expired`, `unknown`, crossing sotto l'entry gate o target-weight zero; nessun counter ordinario. | §5.1, §6 |
| 4 | **`MDE_time`** | **25 bps netti sul notional iniziale**, unilaterale. Scelto dal capital owner ex ante, **non** ricavato dal miglior backtest. | §7.1 |
| 5 | **`MDE_counter`** | **Non fissato ora.** Segue P2: si fissa nella pre-registrazione che eventualmente attiverà P2, prima di guardare qualunque dato di P2. A `n=0` non esiste e non può essere dedotto. | §7.1 |
| 6 | **Unità economica primaria** | **Media dei delta appaiati netti, in bps del notional iniziale.** `Δ1_i = r_net(P1)_i − r_net(P0)_i`. Denominatore = notional iniziale dell'intento, identico fra le policy. | §8.3, §7.1 |
| 7 | **Cluster** | **event-day**. Ticker-day e articoli dello stesso evento non sono repliche indipendenti. Block/stationary bootstrap con schema e lunghezza fissati ex ante, coerenti con l'orizzonte D+2; intervallo unilaterale al 95%. | §8.4 |
| 8 | **Budget false exit** | **Diagnostico, non gate a `n=0`** (P2 è `omitted`, quindi il confronto che lo renderebbe vincolante non esiste). **Calcolato e pubblicato comunque per P0 e P1**: false-exit rate, recovery entro l'orizzonte, giveback da MFE. | §7.1, §8.3 |
| 9 | **`D0`** | **Primo fill RTH eseguibile.** Non la data dell'articolo, non `decision_at`, non l'ack del broker. | §5.1 |
| 10 | **Uscita P1** | **Close di `D0`+2 sedute sul calendario Alpaca** (`GetCalendarRequest`, la stessa usata da `scripts/daily_alpha_miss_analysis.sh`). | §5.1, §8.2 |
| 11 | **Prezzo d'uscita** | Ordine di chiusura **solo se realmente presentabile entro il cutoff**; altrimenti **primo prezzo eseguibile successivo**, mai il closing print teorico. Gap oltre stop: fill al primo prezzo eseguibile, non al trigger. | §5.1, §8.2 |
| 12 | **Half-day e festivi** | Seguono la **close effettiva del calendario**. `max_signal_age` wall-clock non determina mai l'uscita nel test. | §5.1, §8.2 |
| 13 | **`d_hard`** | **Identico e attivo nelle tre policy** (P0, P1 e P2 se attivata). Overlay di rischio, **non** attribuito alla policy di alpha. | §5.1 |
| 14 | **TP / trailing / scale-out** | **Disattivati in tutte le policy.** Stop sintetico stretto idem. — *vedi § Nota Q7: verifica da eseguire prima del flip.* | §5.1 |
| 15 | **`N_cluster`** | Stimare `σ_Δ` sul **segmento pre-fix** in **modalità blinded (solo varianza** — mai la media, mai il ranking fra le policy). Fissare `N_cluster` con **α 5% unilaterale e potenza 90%**, con inflazione per dipendenza e missingness. **Pre-registrata una sola ri-stima blinded al 50% di `N_cluster`.** | §8.4 |
| 16 | **Le 213 sedute** | **NON sono `N_cluster`.** Sono una stima di numerosità per l'**IC** (#179 / pre-registrazione del 14/08), non un requisito per il paired exit delta, che ha varianza propria. | §8.4 |
| 17 | **Stopping** | **Nessun early efficacy stop.** Analisi decisionale **una sola volta**, a `N_cluster`. Review intermedie solo su integrità, sicurezza e statistiche blinded. Unica interruzione ammessa: **safety halt per danno operativo**, documentato. | §8.4 |
| 18 | **Molteplicità** | Ordine gerarchico chiuso: **prima P1 vs P0**; P2 vs P1 solo se P1 supera il gate **e** P2 è stata attivata con una pre-registrazione propria. | §8.4 |
| 19 | **Esiti dichiarati** | P1 promuovibile solo se `LCB95(Δ1) > MDE_time` **e** tutti i gate non-inferenziali di §8.5 tengono. Falsificata se `UCB95(Δ1) ≤ MDE_time`. Se l'intervallo attraversa l'MDE l'esito è **`INCONCLUSIVE`**: non si promuove, non si dichiara equivalenza, **non** si cerca D+1/D+3 sullo stesso campione. | §7.1 |
| 20 | **Controfattuali** | Stessi intenti, fill, notional e costi d'ingresso per tutte le policy. Nessuna policy può cambiare chi entra o il prezzo iniziale. Primo trigger osservabile vince; caso ambiguo → marcato ambiguo, **mai** il percorso favorevole. Capitale liberato **non** reinvestito nel test trade-level. | §8.2 |

**Fuori dalla famiglia confirmatory, esplicitamente diagnostici e non promuovibili:** D+1 e D+3,
decomposizione intraday/overnight, E4 aggregata, posterior/VIX, trailing, event-type, de-risking.
Le analisi D+1/D+3 **non diventano out-of-sample per rinomina** (§8.4, trial ledger).

---

## 2. Nota Q7 — verifica del TP live, da pubblicare prima del flip di `n=0`

Il parametro 14 congela «TP disattivato in tutte le policy». La verifica eseguita il 2026-08-22 sul
codice attuale trova un take-profit **live e attivo di default**, ma **su un perimetro opposto a
quello ipotizzato in Q7**. Il fatto va registrato così com'è, non com'era atteso.

**Q7 ipotizzava:** il runtime invia un bracket con TP sui submit **frazionabili**.

**Il codice attuale dice l'inverso** (`src/workers/portfolio_scheduler.py:4219`):

```python
if _cfg_order.ALPACA_BRACKET_ENABLED and price and price > 0 and not is_fractionable:
    tp_price = round(price * (1 + _cfg_order.ALPACA_TAKE_PROFIT_PCT), 2)
```

Il bracket — e con esso la gamba TP — è attaccato **solo ai submit NON frazionabili** (whole-share).
Sui frazionabili il ramo `if is_fractionable:` (riga 4185) invia un ordine `notional` semplice, senza
bracket: Alpaca rifiuta i bracket su quantità frazionarie/notional (errore 42210000). L'inversione
risale al commit `54d3be3` («skip bracket order for notional/fractional orders», BUG-DAY1-01), che ha
aggiunto `and not is_fractionable` alla condizione originale di `4ba95e7`.

**Il rischio resta reale**, perché il TP è acceso per default e non è mai stato dichiarato nel design
dell'uscita:

- `ALPACA_BRACKET_ENABLED` → default **`true`** (`src/config.py:220-222`)
- `ALPACA_TAKE_PROFIT_PCT` → default **`0.06`** (`src/config.py:223-225`)

Un TP a +6% che scatta prima della close di D+2 tronca il lifecycle e lo attribuisce a P0 come se
fosse comportamento E0, quando è un overlay d'esecuzione mai messo a contratto.

**Obbligo prima del flip di `n=0`** (formulazione dell'obbligo invariata rispetto a Q7, perimetro
corretto):

> Prima del flip di `n=0`, pubblicare quanti lifecycle P0 sarebbero stati toccati dal TP live.
> Se **>5% degli intenti**, P0 non è più il benchmark operativo reale e la definizione va corretta.

Nel conteggio, il perimetro da misurare è quello **whole-share / non frazionabile**. Il commento di
`ALPACA_FRACTIONAL_STOP_ENABLED` (`src/config.py:230-233`) afferma che le posizioni frazionarie sono
«100% del libro»: se l'affermazione è ancora vera al sample start, gli intenti toccati sono ~0 e
l'obbligo si chiude con un numero, non con una correzione. **Va comunque misurato e pubblicato: a
`n=0` il numero non è noto, e l'assunzione non sostituisce la misura.**

Se il conteggio supera il 5%, la correzione ammessa è **una sola**: ridefinire P0 includendo
esplicitamente il TP come parte del benchmark operativo, oppure disattivare `ALPACA_BRACKET_ENABLED`
prima di `n=0`. Entrambe sono modifiche materiali se applicate dopo `n=0`.

---

## 3. Modifiche materiali

Dopo `n=0`, una modifica **materiale** impone il **restart del campione**. Una modifica non materiale
va comunque annotata nel registro qui sotto, ma non azzera nulla.

**È materiale** un cambiamento a: **source**, **resolver**, **modello**, **gate**, **ranking**,
**sizing**, **slot**, **cost model**, **calendario**, **fill**, **orizzonte**.

**Non è materiale** la **strumentazione che non tocca le decisioni**: logging, telemetria, dashboard,
export, test, rinomina di campi non letti dal decisore, backfill di colonne diagnostiche.

Il test da applicare a ogni candidato, nella stessa forma di `OBSERVATION_CHARTER.md` § Cosa è esente:

> Se applico questa modifica, un intento già raccolto sarebbe stato deciso diversamente, o il suo
> outcome per policy sarebbe diverso?

Se la risposta è sì, o se è «non lo so», la modifica è materiale. L'incertezza si risolve verso il
restart, non verso la prosecuzione.

---

## 4. Registro delle modifiche

Ogni modifica al contratto va annotata qui con data, natura (materiale / non materiale), motivo e
commit. Il registro è append-only.

| data | modifica | materiale? | motivo | commit |
|---|---|---|---|---|
| 2026-08-22 | **Creazione del contratto.** Congelati i 20 parametri di §1 e la definizione di modifica materiale di §3. Aggiunta la nota Q7 (§2) con l'obbligo di pubblicazione pre-`n=0`. | — (precede `n=0`) | #293: registrare una decisione unica e verificabile prima di `n=0`. | questo commit |

---

## 5. Riferimenti

- `docs/s4-exit-research-2026-08-14/consolidato_exit.md` — **§5** raccomandazione consolidata,
  **§6** shortlist di policy, **§7** criterio di falsificazione, **§8** protocollo empirico
  (§8.1 ledger point-in-time, §8.2 controfattuali, §8.3 metriche, §8.4 inferenza e potenza,
  §8.5 gate di deployment separati dal test dell'uscita)
- `docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md` — decisione C, shadow reversibile
- `docs/evidence/OBSERVATION_CHARTER.md` — § Registro delle deroghe, § Discontinuità
- `config/s4_exit_trial.yaml` — controparte macchina, letta dal gate di #301
- Issue sbloccate da questa firma: **#297**, **#299**, **#300**, **#301**
