# Intercettazione degli errori di esecuzione → issue GitHub (`error_watch`) — Spec di design

**Data:** 2026-09-12
**Stato:** design approvato dall'operatore, pronto per il piano di implementazione
**Origine:** brainstorming del 2026-09-12. Motivato da una classe ricorrente di guasti già
costata sedute: #396 (eccezione → `exit 0` silenzioso, dossier morto per 3 sedute), #510
(pipeline evidenza che falliva senza rumore), #538 (il fix non raggiungeva il cron e nessuno
se ne accorgeva), outage Ollama del 2026-08-26 (ensemble giù per il 65% della seduta).
**Freeze:** strumentazione e osservabilità pure — nessuna soglia di strategia, peso, prompt o
flag di trading viene toccato. Lavorabile sotto `docs/evidence/OBSERVATION_CHARTER.md` (#171).

## Il problema

Oggi in Alembic un'eccezione di esecuzione non ha destinatario.

- I servizi Docker (`api`, `worker`, `worker-inference`, `worker-news-stream`, `beat`) scrivono
  su log durevoli giornalieri (`logs/containers/<servizio>-YYYY-MM-DD.log`, 60 giorni di
  retention, ~109 MB al 2026-09-12) grazie a `scripts/run_with_durable_logs.py`.
- Gli script cron sull'host scrivono in `logs/*.log`.
- **Nessuno legge questi file cercando traceback.** Non c'è Sentry né alcun aggregatore.

Il substrato di raccolta esiste già: manca il lettore. Un errore viene scoperto solo quando
qualcuno nota l'effetto a valle (un dossier mancante, un ordine non passato), tipicamente giorni
dopo.

## Perimetro

**Dentro:** traceback Python e righe `ERROR`/`CRITICAL` nei log durevoli dei cinque servizi
Docker, più i job cron sull'host (`roadmap_agent_loop`, `daily_analysis`, `daily_alpha_miss_analysis`,
`deploy_reconcile`, `daily_s4_ic`, `check_s4_trial_milestones`, `deadline_reminder`,
`s4_cluster_monitor`, `auto_arm_shadow_monday`) con il loro exit code.

**Fuori (esplicitamente):** i guasti *semantici* silenziosi — `exit 0` con output atteso mancante
(dossier non scritto, ledger non aggiornato, zero righe prodotte). Sono un progetto a sé, perché
richiedono un contratto di output dichiarato per ogni job. Questa spec non li affronta; il ledger
dei run che introduce (`runs.jsonl`) è però la base su cui costruirli in seguito.

## Architettura

Un solo processo, **fuori dallo stack**: `scripts/error_watch.py`, invocato da
`scripts/error_watch.sh` in crontab ogni 15 minuti. Nessun container, nessuna migrazione,
nessuna modifica al path di esecuzione del trading.

```
logs/containers/*-YYYY-MM-DD.log   ─┐
logs/*.log  (cron host)            ─┼→ collector → fingerprint → ledger → gate → reporter → gh issue create
logs/error_watch/runs.jsonl        ─┘   (offset)     (pura)      (JSONL)  (policy)    │
        ↑                                                                             └→ Telegram
  scripts/run_watched.sh (wrapper crontab: registra inizio/fine/exit code)
```

**Perché fuori dallo stack e non come task Celery.** Un sorvegliante di errori di esecuzione non
deve condividere il destino del processo che sorveglia. L'alternativa considerata — beat task +
tabella Postgres + motore incidenti di `src/mobile_monitoring/incidents.py`, visibile su `/quality`
— è più integrata e interrogabile, ma se il worker muore muore anche chi doveva accorgersene, e
aggiunge una migrazione in una zona dove tre branch si sono già scontrati sullo stesso numero
(066/067/068). Lo stato su file è il compromesso deliberato: si rinuncia alla dashboard per
ottenere indipendenza dal guasto. La promozione dello stato su Postgres resta un progetto
successivo, se il ledger dimostrerà di valere.

### Unità

Cinque moduli, ognuno con un compito solo e testabile in isolamento. Solo `reporter` scrive
all'esterno: tutto il resto è puro o locale, quindi l'intera catena può girare su log storici in
`--dry-run` senza toccare niente.

| Unità | Cosa fa | Dipende da |
|---|---|---|
| `collector` | legge i file da un offset per-file, emette record grezzi `(servizio, ts, livello, blocco_traceback)` | filesystem |
| `fingerprint` | normalizza un traceback in una chiave stabile | niente (funzione pura) |
| `ledger` | JSONL append-only: prima/ultima occorrenza, conteggio, stato, issue collegata | filesystem |
| `gate` | decide `ignora` / `commenta` / `apri` / `riapri-regressione` | ledger + `gh` in lettura |
| `reporter` | redige la issue via LLM, la apre, notifica Telegram | `gh`, LLM, Telegram |

### Stato su disco

`logs/error_watch/` (gitignored):

- `offsets.json` — `{percorso_file: byte_offset}`. Un file che rimpicciolisce (rotazione, troncamento)
  fa ripartire il suo offset da 0.
- `ledger.jsonl` — una riga per evento di stato del fingerprint (`primo_avvistamento`,
  `conteggio_aggiornato`, `issue_aperta`, `silenziato`, `regressione`). Append-only: lo stato
  corrente si ricostruisce rileggendolo. Nessuna riscrittura in place, così un'interruzione a metà
  giro non corrompe la memoria.
- `runs.jsonl` — una riga per esecuzione di job cron, scritta da `run_watched.sh`.
- `silenziati.txt` — denylist di fingerprint gestita a mano dall'operatore, con un commento per riga.
- `heartbeat` — timestamp dell'ultimo giro riuscito.

### `run_watched.sh` (unica modifica invasiva sull'host)

I cron oggi loggano solo stdout: l'exit code non compare da nessuna parte. E la lezione di #396 è
che un'eccezione può comunque uscire con `exit 0`.

`scripts/run_watched.sh <nome-job> -- <comando>` esegue il comando, ne propaga l'exit code invariato,
e appende a `runs.jsonl` un record `{job, start, end, exit_code, n_righe_stderr, traceback_visto}`.
Le voci di crontab esistenti vanno riscritte una volta per passarci attraverso. È reversibile riga
per riga e non cambia il comportamento del job: se il wrapper stesso fallisce, esegue comunque il
comando.

## Fingerprint

```
sha1(servizio + tipo_eccezione + ultimo_frame_del_repo + messaggio_normalizzato)
```

Tre scelte che contano:

1. **Ultimo frame *del repo*, non l'ultimo frame in assoluto.** Un `KeyError` che esplode dentro
   `asyncpg` ma origina in `portfolio_scheduler.py:_size_position` va attribuito a noi, non alla
   libreria.
2. **`file:funzione`, mai `file:linea`.** Con la linea nella chiave, ogni refactor ribattezza vecchi
   errori come nuovi e il ledger perde la memoria proprio quando serve (una regressione dopo un fix).
3. **Messaggio normalizzato prima dell'hash**: numeri, UUID, timestamp, path assoluti, indirizzi
   esadecimali e simboli ticker → segnaposto. `KeyError: 'NVDA'` e `KeyError: 'TXN'` sono lo stesso
   difetto e devono collassare su una riga sola.
4. **Gli exit code sono l'eccezione alla regola 3**: `exit status 1` (fallimento generico),
   `137` (OOM-kill) e `124` (timeout) sono difetti categoricamente diversi, e la regola generica
   sui numeri li fonderebbe. Un OOM resterebbe invisibile dietro l'issue di un fallimento banale
   già triagato, quindi il codice sopravvive alla normalizzazione.
5. **In un'eccezione concatenata vince l'ultimo anello**: quando il log mostra
   `During handling of the above exception…` o `…was the direct cause of…`, il fingerprint usa
   tipo, frame e messaggio dell'eccezione **finale**, quella che il chiamante ha effettivamente
   visto. La regola va fissata qui e non lasciata al parser: se oscillasse fra anello interno ed
   esterno, lo stesso difetto avrebbe due chiavi a seconda di come è stato loggato.

## Gate

In ordine; vince la prima condizione che matcha.

| # | Condizione | Azione |
|---|---|---|
| 1 | fingerprint silenziato (baseline o `silenziati.txt`) | niente |
| 2 | fingerprint nuovo su **superficie critica** (def. sotto) | apri subito |
| 3 | fingerprint nuovo altrove | apri a **3 occorrenze in 24h**, o se ricompare in **due giorni distinti** |
| 4 | issue già aperta per il fingerprint | commenta **solo** se il conteggio raddoppia o se riappare dopo 7 giorni di silenzio |
| 5 | fingerprint di issue **chiusa** che riappare | issue nuova, titolo marcato `regressione`, che cita la chiusa |
| 6 | più di **3 aperture in 24h** | tappo: una sola issue digest + Telegram |

**Superficie critica** = il modulo dell'ultimo frame del repo appartiene a
`src/workers/execution.py`, `src/workers/portfolio_scheduler.py`, `src/workers/sentiment.py`,
`src/workers/news_stream.py` o `src/portfolio/`; oppure, quando non c'è alcun frame del repo
(crash del processo, OOM, errore di avvio), il servizio è `beat` o `worker-inference`. La
distinzione conta: i *servizi* sono `api`/`worker`/`worker-inference`/`worker-news-stream`/`beat`,
mentre `execution` e `portfolio_scheduler` sono *moduli* che girano dentro `worker`. Definire la
criticità sul modulo — con il servizio come ripiego — evita sia di marcare critico tutto ciò che
passa da `worker`, sia di perdere un crash che non ha frame nostri.

La riga 3 usa "due giorni distinti" e non "due giri consecutivi": due giri distano 30 minuti, quindi
un errore visto una volta per giro scatterebbe a 2 occorrenze, scavalcando la soglia di 3 che la
riga stessa dichiara. La condizione serve a catturare l'errore *raro ma persistente* (una volta al
giorno per due giorni), non ad abbassare la soglia di nascosto.

La riga 4 esiste perché senza di essa un errore ricorrente produrrebbe un commento ogni 15 minuti.
La riga 6 è la difesa contro il caso reale del 2026-08-26: un guasto a monte che genera molti
fingerprint *diversi* (quelli identici li assorbe già il fingerprint stesso).

I due numeri — 3 occorrenze/24h e 3 aperture/giorno — sono parametri di configurazione, non
costanti sparse nel codice, e vivono in `config/error_watch.yaml`.

## Redattore LLM

Interviene **solo dopo** che il gate ha deciso di aprire. Non decide mai *se* aprire.

**Input:** traceback integrale dell'ultimo esemplare, conteggio e finestra, servizio, 40 righe di
log attorno all'occorrenza, il sorgente della funzione incriminata letto dal repo, e i titoli delle
issue aperte (per il controllo duplicati).

**Output:** JSON `{titolo, corpo, labels}`.

**Tre vincoli:**

1. Non decide se aprire — quello l'ha già deciso il gate deterministico.
2. Il corpo tiene separate, con intestazioni esplicite, l'**evidenza verbatim** e l'**ipotesi**. Una
   diagnosi plausibile ma sbagliata dentro una issue è peggio di nessuna diagnosi: manda in
   direzione sbagliata chi la lavora.
3. Timeout, errore o JSON non valido → **template deterministico** e la issue si apre lo stesso. Il
   redattore è un miglioramento della leggibilità, mai un punto di fallimento.

Gira su Ollama Cloud tramite il client già presente in `src/llm/client.py`; modello e tetto di
budget dichiarati in `config/error_watch.yaml`.

## Destino delle issue

Label alla nascita: `observability` + `freeze-ok` + `needs-triage`. **Nessun tier** — lo assegna
l'operatore in triage. Le issue **non** entrano da sole in `scripts/roadmap_queue.txt`: l'ammissione
al loop roadmap resta una decisione umana, così un errore mal diagnosticato non consuma un giro di
agente. Notifica Telegram a ogni apertura.

## Bootstrap: baseline muta, poi enforcement

Ci sono 60 giorni di log già pieni di errori noti. Accendere il gate su quello storico aprirebbe
decine di issue in un colpo e affogherebbe il segnale.

1. **Primo giro in sola lettura su tutto lo storico.** Censisce i fingerprint esistenti con
   conteggi, prima e ultima occorrenza, servizio. Produce
   `docs/evidence/error_watch_baseline_<data-del-run>.md`. **Non apre nulla.**
2. **L'operatore legge la classifica** e decide: quali fingerprint sono rumore noto (→ `silenziati.txt`
   con motivazione) e quali meritano una issue subito (aperte a mano, poi collegate nel ledger).
3. **Da lì in poi il gate si accende** solo sui fingerprint nuovi o su quelli non silenziati.

È lo stesso schema "misura prima di applicare" di QX-01: nessuna applicazione di regola prima di
avere visto cosa produce sul campione reale.

## Chi sorveglia il sorvegliante

All'avvio, `error_watch` legge il proprio `heartbeat`: se l'ultimo giro riuscito è più vecchio di
90 minuti, la **prima** cosa che fa è mandare un Telegram «sono stato fermo N ore». Un sorvegliante
muto è indistinguibile da un sistema sano — che è esattamente il modo in cui #538 era passato
inosservato.

Il wrapper `run_watched.sh` registra anche il proprio exit code, quindi un crash di `error_watch`
lascia traccia in `runs.jsonl` per il giro successivo.

## Gestione degli errori del sorvegliante stesso

| Guasto | Comportamento |
|---|---|
| log illeggibile / permessi | salta il file, registra, continua sugli altri |
| `gh` non disponibile o rate-limited | non consuma lo stato: il fingerprint resta "da aprire" e riprova al giro dopo |
| LLM giù | template deterministico, issue aperta lo stesso |
| Telegram giù | registra e continua: non deve impedire l'apertura della issue |
| `ledger.jsonl` corrotto a metà riga | l'ultima riga incompleta viene scartata in lettura |

Principio: il sorvegliante non deve mai fallire in modo tale da *nascondere* un errore. Ogni suo
guasto parziale è degradante, non bloccante, e lascia il lavoro da fare al giro successivo.

## Test

- **`fingerprint` e `gate` sono funzioni pure** → corpus di traceback veri estratti dai 60 giorni di
  log come fixture, più un ledger sintetico che copre **ogni riga** della tabella del gate.
- **Normalizzazione**: test che `KeyError: 'NVDA'` e `KeyError: 'TXN'` collassino sullo stesso
  fingerprint, e che due `KeyError` da call site diversi **non** collassino.
- **Stabilità al refactor**: spostare una funzione di 10 righe nel file non deve cambiare il
  fingerprint.
- **End-to-end in `--dry-run`** sullo storico, con snapshot del report di baseline.
- **Il doppio di `gh` nei test fallisce se invocato** — non è un mock permissivo. Un mock che accetta
  qualunque chiamata trasformerebbe il test «non apre issue in dry-run» in un assert che passa
  sempre.
- **`run_watched.sh`**: test che l'exit code del comando sia propagato invariato (un wrapper che
  mangia gli exit code reintrodurrebbe #396 al livello sopra).

## Non obiettivi

- Nessuna dashboard, nessuna pagina web, nessuna tabella Postgres (valutabili dopo la baseline).
- Nessuna correzione automatica e nessun accodamento automatico al loop roadmap.
- Nessun rilevamento di guasti semantici (`exit 0` con output mancante).
- Nessun hook in-process nei servizi: la raccolta è solo pull dai log.

## Deliverable

| File | Ruolo |
|---|---|
| `scripts/error_watch.py` | catena collector → fingerprint → ledger → gate → reporter |
| `scripts/error_watch.sh` | wrapper cron (lock, log, heartbeat) |
| `scripts/run_watched.sh` | wrapper crontab che registra gli exit code dei job |
| `config/error_watch.yaml` | servizi critici, soglie, tappo, modello e budget LLM |
| `tests/scripts/test_error_watch.py` | unit + end-to-end dry-run |
| `docs/evidence/error_watch_baseline_<data-del-run>.md` | censimento del bootstrap |
| voce in crontab | `*/15 * * * *` |
