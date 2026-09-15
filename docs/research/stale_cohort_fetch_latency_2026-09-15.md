# Stale news queue — coorte B, 11/09 e 14/09: la latenza di fetch non e' un ritardo di ingest

**Data:** 2026-09-15 · **Branch:** `research/stale-fetch-latency` · **Issue di riferimento:** #432 (coorte B, PR #560), #541 (provenienza trasporto), #48
**Perimetro:** sola analisi. Nessuna modifica a codice di produzione, nessuna scrittura su Redis o Postgres, nessuna PR.
**Fonti:** `stale_drop_metrics_daily`, `news_queue_drops`, `news_log`, `ingestion_stats_daily`, `news_queue_census`, `docker inspect`/`docker logs`, sorgenti a `28bb6d1`.

---

## 0. Esito in una riga

Il breach in-seduta del 25% **non e' un guasto della pipeline e non e' un ritardo di ingest**: e' l'eco del
deduplicatore. `_DEDUP_TTL_SECONDS = 4 * 3600` (`src/connectors/deduplicator.py:22`) e' **il doppio** di
`MAX_NEWS_AGE_HOURS = 2`. Ogni articolo visto per primo dal WebSocket a latenza ~0 viene **risollevato una volta
sola**, esattamente 4h dopo, dal poller REST a 15 minuti — e a quel punto il gate di freschezza lo uccide per
costruzione. **Il 100% (65/65 l'11/09, 69/69 il 14/09) degli articoli distinti dietro gli scarti in-seduta era
gia' stato visto fresco dalla pipeline entro 15 minuti dalla pubblicazione.** Nessun segnale e' andato perso.

La "fetch latency 3,9h" pubblicata nell'alert non misura il provider: misura la TTL del deduplicatore.

---

## 1. Verifica dei numeri dell'alert

I due alert sono riprodotti esattamente da `stale_drop_metrics_daily`.

| | 11/09 (ven) | 14/09 (lun) |
|---|---|---|
| In-session stale drops | 292/779 (37,5%) | 313/883 (35,4%) |
| Total stale drops | 482/779 (61,9%) | 430/883 (48,7%) |
| Already stale at fetch | 292 | 305 |
| Went stale in queue | 0 | 8 |
| Enqueued off-session | 190 | 117 |
| Unclassified | 0 | 0 |
| Fetch latency avg | 3,86h | 3,90h |
| Queue wait avg | 5,12h | 1,39h |

Ricalcolati da `news_queue_drops` con la logica di `collect_stale_drop_measurements` riprodotta verbatim:
coincidono su ogni casella. `enqueued_off_session` e' popolata su **tutte** le righe dal 07/09 in poi
(0 NULL), quindi la classificazione causale e' completa. Unica differenza: `queued` era 883 alle 22:55Z del
14/09 e 885 alle 23:15Z in `ingestion_stats_daily` (2 item accodati fra le due scritture) — differenza di
istante di lettura, non di definizione.

### 1.1 Discontinuita' non annotata nella serie pubblicata

**Le righe 08/09, 09/09 e 10/09 in `stale_drop_metrics_daily` sono ancora quelle dello strumento
pre-#560** (`measured_at` = il giorno stesso, `went_stale_off_session = 0`). Solo 11/09→14/09 sono coorte B
(`measured_at = 2026-09-14 22:55Z`). La serie pubblicata mescola oggi **due strumenti diversi senza
annotazione**. Ricalcolando i giorni vecchi con lo strumento attuale (sola lettura, nessuna scrittura):

| coorte | queued | in-seduta pubblicato | **in-seduta coorte B** | asf | wsq | off | fetch lat | queue wait |
|---|---|---|---|---|---|---|---|---|
| 08/09 mer | 542 | 29,0% (breach) | **4,8%** | 16 | 10 | 144 | 0,47h | 7,08h |
| 09/09 gio | 526 | 37,1% (breach) | **3,4%** | 18 | 0 | 162 | 1,28h | 6,54h |
| 10/09 gio | 855 | 53,1% (breach) | **30,8%** | 263 | 0 | 230 | 4,25h | 4,13h |
| 11/09 ven | 779 | 37,5% | 37,5% | 292 | 0 | 190 | 3,86h | 5,12h |
| 12/09 sab | 70 | 0% | 0% | 0 | 0 | 70 | — | 46,31h |
| 13/09 dom | 94 | 0% | 0% | 0 | 0 | 94 | — | 20,15h |
| 14/09 lun | 885 | 35,4% | 35,4% | 305 | 8 | 117 | 3,90h | 1,39h |

**Conseguenza per il confronto col 09/09 nel mandato.** La premessa "allora *went stale in queue* dominava
(169/195, wait 7,33h)" e' una lettura dello strumento **vecchio**. Sotto coorte B il 09/09 vale
`went_stale_in_queue = 0` e **3,4% in-seduta, sotto soglia**: i 177 scarti su 195 di quel giorno sono caduti
tutti alle 13:xx UTC e sono tutti coorte off-session — la spazzata della campana sull'arretrato notturno,
cioe' esattamente il gruppo che la coorte B esiste per **escludere**.

> **Quindi la causa dominante non si e' spostata.** A strumento costante, `went_stale_in_queue` e' ~0 da
> sempre. Quello che e' cambiato e' reale ma e' un'altra cosa: un gradino su `already_stale_at_fetch`
> (16 → 18 → **263** → 292 → 305) fra il 09/09 e il 10/09. Vedi §3.

### 1.2 Il criterio di accettazione della deroga #432 Opzione B non e' soddisfatto

La deroga del 2026-09-10 dichiara, prima dell'esecuzione: *«l'outage Ollama del 2026-09-09 15-16Z deve
restare in breach sul gruppo in_session; se non allerta piu', la correzione e' sbagliata e va revertata»*.

Sui dati veri quella finestra **non esiste nel ledger**: il 09/09 gli scarti stale si distribuiscono su due
sole ore di `dropped_at`, le 13:xx (177 righe, **tutte** off-session, wait 8,03h) e le 14:xx (18 righe,
in-seduta, wait 0,41h). Alle 15-16Z: zero. Il "breach 09/09" attribuito a un outage del consumatore era la
campana che smaltiva l'arretrato notturno, letta dallo strumento con denominatore cross-day.

**Non raccomando il revert.** Il criterio e' fallito perche' la sua *premessa* era un artefatto dello
strumento che la correzione ha rimosso — la correzione ha fatto il suo mestiere. Ma il criterio era
pre-registrato e il suo esito e' un fatto: **va registrato esplicitamente nella carta** con questa
motivazione, non lasciato implicito. Decisione dell'operatore; questa e' un'analisi, non una modifica.

---

## 2. Il meccanismo: la TTL del dedup (4h) e' il doppio della finestra di freschezza (2h)

### 2.1 La distribuzione della latenza non e' una distribuzione, e' una riga verticale

Distribuzione di `raw_ingested_at - published_at` sugli scarti stale **in-seduta**, per fascia oraria UTC:

| coorte | ora UTC | n | p50 | p90 | max |
|---|---|---|---|---|---|
| 11/09 | 14 | 149 | 6,60h | 15,85h | 17,48h |
| 11/09 | 15 | 8 | 4,13h | 4,13h | 4,14h |
| 11/09 | 16 | 17 | 4,18h | 4,23h | 4,25h |
| 11/09 | 17 | 36 | 4,42h | 4,88h | 4,88h |
| 11/09 | 18 | 45 | 4,16h | 8,33h | 8,42h |
| 11/09 | 19 | 37 | 4,09h | 8,32h | 8,38h |
| 14/09 | 14 | 85 | 5,67h | 18,56h | 18,56h |
| 14/09 | 15 | 21 | 4,04h | 4,21h | 4,21h |
| 14/09 | 16 | 50 | 4,14h | 4,22h | 4,22h |
| 14/09 | 17 | 47 | 4,10h | 4,23h | 4,23h |
| 14/09 | 18 | 63 | 4,16h | 5,37h | 8,43h |
| 14/09 | 19 | 47 | 4,21h | 4,23h | 4,25h |

Nelle ore di regime (15-19Z) la latenza sta in **[4,04h ; 4,25h]** — una banda larga 13 minuti, cioe' un
intervallo di poll. Non e' congestione, non e' jitter di rete, non e' un provider lento. E' una **costante**.
Istogramma a bucket orario, in-seduta: il bucket 4h vale **240/305 (79%)** il 14/09 e 207/263 (79%) il 10/09.

Righe grezze del 14/09 (poll alle :00:01, :15:01, :45:01, :15:01 — cadenza 15 minuti):

```
published_at          raw_ingested_at        fetch_lat  qwait
2026-09-14 10:57:23Z  2026-09-14 15:00:01Z     4,044h   0,138h
2026-09-14 11:13:52Z  2026-09-14 15:15:01Z     4,019h   0,279h
2026-09-14 11:32:12Z  2026-09-14 15:45:01Z     4,214h   0,108h
2026-09-14 12:04:38Z  2026-09-14 16:15:01Z     4,173h   0,105h
```

### 2.2 Il circuito chiuso

1. `run_alpaca_ingestion_worker` gira `crontab(minute="*/15", hour="14-21", day_of_week="1-5")`
   (`src/workers/celery_app.py:166`) e chiama `AlpacaNewsConnector.fetch()`, che richiede l'ultima pagina
   `sort=desc, limit=50` **senza filtro temporale** (`src/connectors/alpaca_news.py:70`). La stessa pagina
   torna a ogni giro.
2. `worker-news-stream` e' sottoscritto 24/7 al WebSocket Benzinga su 96 simboli e vede l'articolo alla
   pubblicazione: `raw_ingested_at ≈ published_at`. Il `Deduplicator` scrive `SET ... NX ex=14400`.
3. Per le 4 ore successive ogni poll REST ri-vede l'articolo e lo scarta `duplicate_id`. Sono le **6.650
   (11/09) e 7.568 (14/09)** righe `duplicate_id` allo stage `ingestion`.
4. `SET NX` **non rinfresca la TTL**: la chiave scade a T+4h esatte. Il primo poll REST dopo la scadenza
   ripassa il dedup e accoda l'articolo. Eta' alla riconsegna ∈ [4h, 4h15m].
5. `_is_stale_news` allo stage `sentiment` scarta tutto cio' che supera `MAX_NEWS_AGE_HOURS = 2`.
   **L'articolo risollevato e' vecchio il doppio della soglia per costruzione: probabilita' di
   sopravvivenza zero.**

Le TTL vive lette su Redis confermano il 4h (campioni: 10804s, 6636s, 3537s — tutti ≤ 14400). I docstring del
modulo dicono ancora "2-hour TTL" alle righe 51-52 e 69: il commento e' rimasto indietro rispetto alla
costante, cambiata il 2026-06-27 (`731530b`).

### 2.3 La prova decisiva: nessun articolo perso

Per ogni articolo distinto dietro gli scarti stale in-seduta, primo avvistamento nella pipeline
(`MIN(raw_ingested_at)` su `news_log` ∪ `news_queue_drops`) contro `published_at`:

| coorte | righe scarto | **articoli distinti** | gia' visti freschi (<15 min dalla pubblicazione) | % |
|---|---|---|---|---|
| 10/09 | 263 | 60 | 59 | 98,3% |
| 11/09 | 292 | 65 | **65** | **100,0%** |
| 14/09 | 313 | 69 | **69** | **100,0%** |

Due cose insieme:

- **I "313 scarti" sono 69 articoli.** Il rapporto e' ~4,5 righe per articolo: il numeratore conta coppie
  (articolo × ticker) dopo l'espansione per simbolo, non notizie. Il numero pubblicato e' gonfio di un
  fattore 4,5 rispetto al fenomeno che nomina.
- **Tutti e 69 erano gia' entrati freschi.** Lo scarto e' la seconda consegna, non la prima.

Controprova dal lato opposto — la resa netta del poller REST. Su `news_log` (cio' che sopravvive ed e'
scorato), latenza di fetch per giorno:

| giorno | righe `news_log` | p50 | p90 | **latenza > 5 min** | **latenza > 1h** |
|---|---|---|---|---|---|
| 08/09 | 185 | 0,00h | 0,00h | 0 | 0 |
| 09/09 | 191 | 0,00h | 0,00h | 2 | 0 |
| 10/09 | 180 | 0,00h | 0,00h | 4 | 4 |
| 11/09 | 166 | 0,00h | 0,00h | 4 | 4 |
| 14/09 | 206 | 0,00h | 0,00h | **0** | **0** |

Il 14/09 **zero** righe su 206 hanno piu' di 5 minuti di latenza di fetch. Tutta la news che arriva davvero
a un segnale arriva dal WebSocket. Il contributo netto del poller REST alla serie osservata, nelle sedute
esaminate, e' **7.568 duplicati + 313 righe di eco stale + 0 articoli nuovi**.

### 2.4 Cosa e' stato escluso

- **Riavvii / riconnessioni del container.** `alembic-worker-news-stream-1`: `RestartCount = 0`,
  `StartedAt = 2026-09-14T22:20:13Z` (ricostruzione notturna programmata). Zero occorrenze di
  `reconnect|disconnect|closed|error` nei log del ciclo di vita corrente; l'unica traccia di connessione e'
  la sottoscrizione iniziale ai 96 simboli. Stessa cosa per `alembic-worker-1` e `-inference-1`.
  **Limite dichiarato:** la ricostruzione delle 22:20Z distrugge i log — quelli dell'11/09 e del 14/09 in
  seduta **non sono piu' ispezionabili** (e' il difetto #544 gia' noto). Le conclusioni di §2.1-2.3 non
  poggiano sui log ma sul ledger Postgres, che sopravvive.
- **Backlog di coda.** `news_queue_census` (#561, dal 12/09): profondita' massima 405 item, media 139 il
  14/09, **dead-letter 0** in ogni campione. Nessun accumulo patologico.
- **Attesa in coda in seduta.** 0,17h / 0,19h / 0,23h il 10, 11 e 14/09 (§3). Il consumatore non e' in
  ritardo.

---

## 3. Perche' la queue wait crolla il 14/09 (1,39h) e non l'11/09 (5,12h): e' il weekend

La media pubblicata `avg_queue_wait_hours` e' calcolata su **tutta** la coorte, in-seduta e off-session
insieme. Separandole:

| coorte | gruppo | n | **media** | p50 | max |
|---|---|---|---|---|---|
| 10/09 | in-seduta | 263 | **0,17h** | 0,03h | 0,61h |
| 10/09 | off-session | 230 | 8,66h | 6,18h | 17,51h |
| 11/09 | in-seduta | 292 | **0,19h** | 0,26h | 0,31h |
| 11/09 | off-session | 190 | 12,71h | 4,73h | **65,54h** |
| 14/09 | in-seduta | 313 | **0,23h** | 0,05h | 0,72h |
| 14/09 | off-session | 117 | 4,48h | 3,58h | 10,22h |

**L'attesa in coda in seduta e' ~12 minuti in tutte e tre le sedute e non varia.** La differenza 5,12h vs
1,39h vive interamente nel gruppo off-session, e li' e' aritmetica di calendario. Coorte 11/09 off-session,
per ora di accodamento:

| accodato (UTC) | n | attesa media |
|---|---|---|
| ven 11, 01–11Z (pre-apertura) | 166 | 5,20h |
| **ven 11, 20–23Z (dopo la campana)** | **24** | **62,0–65,3h** |

Quei 24 item sono stati accodati **venerdi' sera** e scartati **lunedi' 14/09 alle 13:32Z**: hanno attraversato
il weekend. Escludendoli, la media dell'intera coorte 11/09 passa da **5,12h a 2,00h**, contro 1,39h del
14/09. Il 14/09 e' un lunedi': la sua coorte off-session e' solo la finestra domenica-notte→lunedi'-mattina,
massimo 10,22h.

> **Nessuna differenza di regime, nessun drenaggio, nessun cambio di volume.** Il 5,12h dell'11/09 e' 24 item
> su 482 (5% della coorte) che hanno aspettato il lunedi'. E' fisiologia di un consumatore con guardia di
> seduta, gia' descritta dalla deroga di coorte B — solo che **la media pubblicata la rimescola dentro**
> proprio mentre la riga sopra la separa. Vedi raccomandazione R2.

---

## 4. Il breach e' vero o e' il riflesso di un collo a monte?

**Ne' l'uno ne' l'altro — e' l'eco dello strumento stesso.** Le tre letture possibili, contro l'evidenza:

| lettura | verdetto |
|---|---|
| «La pipeline di consumo e' rotta / in ritardo» | **Falsa.** Attesa in coda in seduta 0,17–0,23h, DLQ 0, profondita' max 405. Il consumatore sta al passo. |
| «C'e' un collo a monte: l'ingest e' lento» | **Falsa.** La news che conta entra dal WebSocket a latenza 0,00h (p90) — il 14/09 **0 righe su 206** in `news_log` superano i 5 minuti. Nessun articolo arriva in ritardo: arriva **due volte**, e la seconda copia e' vecchia di 4h. |
| «E' un artefatto della misura» | **Vera, ma non della coorte B.** La coorte B ha fatto esattamente il suo lavoro: ha isolato il gruppo in-seduta e messo a nudo un gradino che prima era mascherato dal rumore notturno. L'artefatto sta **a monte della misura**, nella TTL del dedup a 4h contro un gate a 2h. |

Il breach quindi **non e' un incidente operativo e non ha costo in alpha**: zero articoli persi in tre sedute.
Ma non e' nemmeno benigno da ignorare — e' **spreco misurabile e rumore sull'evidenza**:

- ~7.500 chiamate/giorno di espansione+dedup e ~300 righe/giorno di ledger per zero resa;
- una serie pubblicata (`stale_drop_metrics_daily`) che al 28/09 entra nella roadmap pesata dichiarando
  «il 35-38% della news in seduta viene scartata come vecchia», affermazione che un lettore ragionevole
  interpreta come perdita di copertura e che **e' falsa**;
- `avg_fetch_latency_hours` e' etichettata come latenza di ingest e misura invece una TTL di configurazione.

### 4.1 Cosa resta aperto

Il gradino del 10/09 (`already_stale_at_fetch` 18 → 263, articoli distinti 7 → 60) **non e' spiegato**.
Escluso: riavvii dei container (RestartCount 0), deploy su `alpaca_news.py` / `ingestion.py` /
`celery_app.py` fra il 07/09 e l'11/09 (nessuno; i commit di quei giorni sono #544/#512/#468/#469, estranei
all'ingest). Misurato: `fetched` 976 → 1557 e `duplicate_id` 4.359 → 7.016 a **articoli distinti costanti**
(93 → 94), cioe' piu' righe per articolo, non piu' notizie. Ipotesi principale: il WebSocket wired in
produzione con #526 (merge `bd6c2c3`, 07/09, live alla ricostruzione delle 22:20Z) ha spostato il primo
avvistamento dal REST al WS, e quando il WS e' il primo avvistatore la scadenza della TTL cade **dentro** la
finestra di poll 14–21Z invece che fuori. Non e' dimostrabile da qui: **manca la provenienza del trasporto
per riga, che e' esattamente #541**. Fino ad allora l'attribuzione resta un'ipotesi dichiarata.

---

## 5. Raccomandazioni

Tutte e tre rispettano il freeze di `docs/evidence/OBSERVATION_CHARTER.md` fino al **2026-09-28**:
nessuna tocca `MAX_NEWS_AGE_HOURS` (=2, stessa costante del gate d'ingresso S4), nessuna tocca il gate 0,30,
nessuna tocca soglie, pesi, cooldown o il money path. Sono strumentazione e ingest-side, nel profilo gia'
ammesso per #161, #324 e #561.

### R1 — Sbloccare l'attribuzione: provenienza del trasporto per riga (#541) · **impatto alto · sforzo basso (~2-3h)**

Una colonna `transport` (`'ws' | 'rest'`) su `news_queue_drops` e `news_log`, scritta dal chiamante
(`news_stream.py` vs `ingestion.py`) al momento dell'accodamento. Puramente additiva: nessuna serie esistente
cambia definizione, nessun consumatore va toccato.

**Perche' prima di tutto il resto.** Ogni conclusione di questo documento sul ruolo del WebSocket e' inferita
dalla latenza (`raw_ingested_at - published_at ≈ 0` ⇒ WS) invece che osservata. Regge sui numeri visti, ma e'
inferenza, e §4.1 mostra dove si ferma: il gradino del 10/09 resta non attribuito. Senza questo campo
qualunque intervento su R3 sarebbe valutato sulla stessa inferenza che ha prodotto il problema.

### R2 — Separare le medie per gruppo nell'alert e annotare la discontinuita' della serie · **impatto medio · sforzo basso (~1-2h)**

Tre cose, tutte sul solo strumento:

1. `format_stale_drop_alert` pubblica `Fetch latency avg` e `Queue wait avg` **per gruppo** (in-seduta /
   off-session) invece che in aggregato. Oggi la riga "Queue wait avg: 5,12h" e' una media fra 0,19h e 12,71h
   e non descrive nessuno dei due: 24 item su 482 la spostano di 3 ore (§3). E' la stessa classe di difetto
   che la coorte B ha corretto un livello sopra, rimasta sulle medie.
2. Aggiungere agli scarti in-seduta il conteggio di **articoli distinti** accanto alle righe
   (`313 righe / 69 articoli`): il rapporto 4,5:1 e' l'espansione per ticker, e oggi il numero pubblicato
   nomina notizie e conta coppie.
3. **Ribackfillare 08/09-10/09 con lo strumento attuale** (`run_stale_drop_alert('2026-09-08','2026-09-10')`,
   gia' idempotente per costruzione) e **annotare la discontinuita' nella carta**, insieme all'esito del
   criterio di accettazione di §1.2. Riscrivere quelle righe cambia tre valori pubblicati (29,0%→4,8%,
   37,1%→3,4%, 53,1%→30,8%): **e' una revisione di serie e va dichiarata, mai fatta in silenzio.** Non la
   eseguo in questa analisi — richiede la decisione dell'operatore e una voce in carta.

### R3 — Chiudere il circuito: allineare la TTL del dedup alla finestra di freschezza · **impatto alto sullo spreco, nullo sull'alpha · sforzo basso (~1h) ma NON freeze-ok cosi' com'e'**

La correzione strutturale e' una riga: `_DEDUP_TTL_SECONDS` da 4h a un valore ≥ `MAX_NEWS_AGE_HOURS`, cosi'
che un articolo non possa mai riemergere dal dedup gia' oltre il gate. Elimina ~300 righe/giorno di eco e
azzera il breach senza toccare la soglia 0,25.

**Ma: non la propongo per il deploy prima del 28/09.** La TTL del dedup e' un parametro che governa quali
news entrano nella serie osservata — cambiarlo a meta' finestra e' una discontinuita' sul denominatore di
copertura (#508/#511), lo stesso motivo per cui la deroga dell'Opzione C ha vietato scritture su `news_log`.
E l'esenzione "difetto di correttezza" non e' automatica: il sistema si comporta come configurato, e la
prova che il costo in alpha e' **zero** (100% degli articoli gia' visti freschi, §2.3) toglie proprio
l'urgenza che giustificherebbe l'anticipo. Rimedio da registrare per il **28/09**, con due note per chi lo
eseguira':

- correggere insieme i docstring di `deduplicator.py` (righe 11, 51-52, 69 dicono "2-hour TTL" da prima del
  cambio del 2026-06-27: chi legge il modulo oggi legge il contrario della costante);
- **rimisurare la copertura news prima e dopo**: se una quota degli articoli non venisse piu' riconsegnata
  affatto, la serie di copertura avrebbe un gradino, e va segmentato before/after, non mediato.

Un'alternativa piu' economica e senza deroga, se serve muoversi prima: il poller REST **salta** il market-hours
gate solo per non riaccodare cio' che il WS ha gia' visto — ma richiede R1 per essere implementabile, ed e' il
motivo per cui R1 viene per prima.

---

## 6. Limiti dichiarati

- **Finestra corta.** Tre sedute (10, 11, 14/09) sotto lo strumento coorte B. Non e' un campione per
  nessuna affermazione statistica; le conclusioni qui sono **meccaniche** (un circuito identificato nel
  codice e verificato riga per riga sul ledger), non inferenziali.
- **Log non ispezionabili per le sedute analizzate.** La ricostruzione delle 22:20Z ha distrutto i log di
  `worker-news-stream` dell'11 e del 14/09 (difetto #544). L'assenza di riconnessioni e' verificata solo sul
  ciclo di vita corrente. Ogni conclusione poggia su Postgres.
- **Provenienza del trasporto non persistita (#541).** La separazione WS/REST e' inferita dalla latenza.
- **`news_queue_census` parte dal 12/09**, quindi non copre l'11/09 ne' il gradino del 10/09.
- **Nessuna scrittura effettuata.** Le tabelle ricalcolate in §1.1 sono query di sola lettura: la riga
  pubblicata di 08/09-10/09 in `stale_drop_metrics_daily` **non e' stata toccata** (vedi R2.3).
