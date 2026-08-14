# S4 exit research packet — istruzioni di invio

**Data cutoff comune:** 2026-08-14  
**Scopo:** far analizzare a più LLM le exit correnti di S4 e le alternative sostenute dalla
letteratura, mantenendo identici fatti, domande e vincoli.

## Cosa passare a ogni modello

Caricare insieme, in questo ordine, questi quattro file:

1. `01_PROMPT_MULTI_LLM.md` — istruzioni e formato obbligatorio della risposta;
2. `02_ANALISI_PRELIMINARE_LETTERATURA.md` — ricognizione iniziale con fonti primarie;
3. `03_DECISIONE_PRECEDENTE_CONSOLIDATA.md` — decisione multi-LLM precedente sull'orizzonte;
4. `04_PREREGISTRAZIONE_D2.md` — baseline D+2 già congelata, da sfidare senza riscriverla ex post.

I file 03 e 04 sono copie congelate per questo packet; gli originali autorevoli restano
rispettivamente in `docs/s4-orizzonte-review-2026-08-13/consolidato.md` e
`docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md`.

Il prompt è autosufficiente. Se il modello accetta un solo file, passare soltanto
`01_PROMPT_MULTI_LLM.md`; la qualità sarà inferiore perché non potrà verificare in dettaglio fonti,
decisione e protocollo.

## Messaggio da inviare insieme agli allegati

> Leggi prima `01_PROMPT_MULTI_LLM.md` e seguilo integralmente. Usa gli altri tre file come
> evidenza e contesto, non come conclusioni da confermare. Svolgi una ricerca Web approfondita su
> fonti primarie e cita DOI/URL diretti. La data cutoff comune è 2026-08-14: non usare modifiche
> successive del progetto. Non proporre codice. Restituisci un unico documento Markdown nel formato
> obbligatorio della sezione 7 del prompt.

Usare lo stesso testo, gli stessi quattro file e la stessa data cutoff con tutti i modelli. Non dare
a un modello le risposte degli altri prima che abbia terminato: produrrebbe convergenza artificiale.

## Allegati opzionali per modelli con molto contesto o accesso al repository

Questi materiali servono soprattutto a verificare l'audit tecnico e le singole osservazioni. Non
sono necessari per il primo giro; aggiungerli soltanto se il modello può leggerli senza sacrificare
la ricerca di letteratura.

### Priorità A — comportamento e configurazione

- `src/strategies/s4/config.py`
- `src/strategies/s4/ranking.py`
- `src/strategies/s4/strategy.py`
- `src/portfolio/orchestrator.py`
- `src/portfolio/exit_classification.py`
- `src/workers/portfolio_scheduler.py`
- `src/portfolio/fractional_stop_orders.py`
- `config/trading.yaml`
- `config/strategies.yaml`

Per `portfolio_scheduler.py` indicare al modello di concentrarsi su: rebalance clock, FIX-D e
freshness, hold minimo, exit hysteresis, zero-weight classification, sentiment reversal, stop
broker/sintetici e bracket take-profit.

### Priorità B — evidenza empirica

- `docs/stop_loss_calibration_handback_2026-07-15.md`
- `docs/ALPHA_MISS_REPORT_2026-08-06.md`
- `docs/ALPHA_MISS_REPORT_2026-08-07.md`
- `docs/ALPHA_MISS_REPORT_2026-08-10.md`
- `docs/ALPHA_MISS_REPORT_2026-08-11.md`
- `docs/ALPHA_MISS_REPORT_2026-08-12.md`
- `docs/evidence/s4_ic.json`
- export dell'issue GitHub `#242`, inclusi body e decisione del 2026-08-14

## Cosa non passare nel primo giro

- Il vecchio `docs/S4_PROMPT_ANALISI_ESTERNA_2026-08-03.md`: precede la decisione D+2 e contiene una
  fotografia ormai superata di diversi meccanismi.
- Interi archivi `docs/archive/` o tutti gli alpha-miss report: aumentano il rumore e favoriscono
  cherry-picking narrativo.
- Risposte già prodotte da altri modelli.
- Codice successivo alla data cutoff, se l'obiettivo è confrontare analisi sullo stesso stato.

## Come salvare le risposte

Salvare ogni risposta integrale, senza riscriverla, con questa convenzione:

```text
risposte/<modello>_analisi_exit_s4_2026-08-14.md
```

Annotare a inizio file:

- modello e versione;
- data della ricerca;
- accesso Web sì/no;
- allegati effettivamente ricevuti;
- eventuali limiti di contesto o fonti non raggiungibili.

Il consolidamento successivo deve confrontare fonti, assunzioni, shortlist e criteri di
falsificazione. Il numero di modelli favorevoli a una policy non è una probabilità.
