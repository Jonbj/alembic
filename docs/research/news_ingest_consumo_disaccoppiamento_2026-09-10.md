# Disaccoppiamento ingest/consumo della coda news — analisi e opzioni

**Data:** 2026-09-10 · **Stato:** documento di progettazione, nessuna modifica al codice
**Origine:** alert stale-drop #432 in breach l'8 e il 9 settembre su `alpaca_benzinga`
**Vincolo dominante:** freeze di osservazione #171 fino al **2026-09-28**

---

## 1. Sintesi

Il difetto descritto dall'operatore è reale, ma la catena causale verificata sul codice è
diversa da quella ipotizzata in tre punti che cambiano quali opzioni funzionano:

1. **Il beat REST non ingerisce fuori seduta.** `run_alpaca_ingestion_worker`
   (`src/workers/ingestion.py:502`) ha già la guardia `is_market_open()` fail-closed, oltre
   alla crontab `14-21` (`src/workers/celery_app.py:162`). L'ingest 24/7 è **esclusivamente**
   il WebSocket (`src/workers/news_stream.py`, nessuna guardia in `_on_news:52` né in
   `run_news_stream:102`). L'asimmetria è WS-vs-beat, non ingest-vs-consumo in generale — ed
   è la spiegazione diretta del `gdelt_gkg 0%`: GDELT ha solo il path a beat, quindi non può
   accumulare fuori seduta per costruzione.

2. **Fermare il WS fuori seduta non elimina il fenomeno.** `AlpacaNewsConnector.fetch()`
   (`src/connectors/alpaca_news.py:64`) chiama `_build_params(limit=50)` **senza `start`**:
   restituisce i 50 articoli più recenti, `sort=desc`, senza filtro temporale. Il dedup ha
   TTL 4h (`src/connectors/deduplicator.py:22`). Un articolo delle 20:02Z ha la chiave di
   dedup scaduta alle 00:02Z: il primo run REST delle 14:00Z lo ri-pesca come nuovo, lo
   riaccoda, e il consumatore lo scarta stale identicamente. Una "stop-ingest fuori seduta"
   sposterebbe la coorte dal WS al REST, non la eliminerebbe.

3. **L'apertura non aspetta il beat.** `_on_news` fa `app.send_task(run_sentiment_worker,
   queue="inference")` su ogni articolo accodato (`news_stream.py:88`), 24/7. Fuori seduta
   quel task esce subito su `market_closed` (`sentiment.py:1121`), ma **alle 13:30Z, alla
   campana, il primo articolo WS innesca un run che trova la guardia aperta** e scansiona
   fino a `_MAX_QUEUE_SCAN_PER_RUN=5000` item scartandoli in blocco (`sentiment.py:1229-1253`).
   Il beat sentiment parte solo alle 14:00Z (`celery_app.py:79`): i 30 minuti fra apertura e
   primo beat sono coperti solo dal trigger WS. È questo che produce i "177 scarti in un'ora"
   prima delle 14:00, non il beat.

A questi si aggiungono due difetti **della misura**, non del processo, che vanno corretti
prima di qualunque intervento sul processo — altrimenti non sapremo se il fix ha funzionato:

4. **Il denominatore dell'alert è cross-day.** In `collect_stale_drop_measurements`
   (`stale_drop_alert.py:88`) il numeratore è raggruppato su `dropped_at::date` e il
   denominatore è `ingestion_stats_daily.queued`, incrementato al momento dell'**accodamento**.
   La coorte notturna sta al numeratore del giorno D+1 e al denominatore del giorno D. Le quote
   pubblicate (29,0% e 37,1%) non sono rapporti sulla stessa coorte: sono già un artefatto di
   misura prima ancora di essere un artefatto di processo. La cosa è visibile nei dati stessi —
   il wait medio in coda passa da 19,4h a 7,33h fra due giorni consecutivi senza che nulla sia
   cambiato nel sistema, perché sta misurando due mescolanze diverse di coorti.

5. **La causa che serve non è fra quelle registrate.** La migrazione 062 registra
   `already_stale_at_fetch` (arrivata già vecchia) e `went_stale_in_queue` (invecchiata in
   coda). Per il WS `raw_ingested_at ≈ published_at`, quindi **tutta** la coorte notturna cade
   in `went_stale_in_queue` — la stessa casella in cui cade un outage del consumatore a
   mercato aperto. Le due hanno fix opposti (la prima non è un guasto, la seconda sì) e l'alert
   non le distingue: è per questo che è diventato un falso allarme strutturale pur restando
   formalmente corretto.

**Il discrimine per il freeze.** A valle, `_apply_entry_freshness_gate`
(`portfolio_scheduler.py:1246`, chiamato a `:4158`) applica lo **stesso** bound
`MAX_NEWS_AGE_HOURS` su `published_at`, ma — per #150 — **solo ai simboli senza posizione
aperta**. Conseguenza precisa: classificare la coorte notturna all'apertura sarebbe quasi un
no-op per gli **ingressi** (il gate a valle li riscarterebbe comunque), ma **non** per i
simboli **detenuti**, che saltano quel gate e finiscono in `_filter_stale_signals`/FIX-D, cioè
nel path delle **uscite**. Qualunque opzione che faccia arrivare quelle news a
`sentiment_signals` cambia il comportamento delle uscite: **non è freeze-ok**. È la linea che
separa le opzioni A/B/C dalla D.

**Nota di completezza:** `news_log` è scritto in un solo punto, `log_news_item`
(`sentiment.py:753`), dentro il path di classificazione. L'ingest persiste solo contatori e
scarti (`_persist_ingestion_observability`, `ingestion.py:189`). Quindi la coorte notturna
**oggi è già invisibile al dossier alpha-miss**, che interroga `news_log` per la domanda
"avevamo la notizia?" (`scripts/alpha_miner_dossier.py:403,1521`). Il timore di "perdere news
pre-open che il dossier usa" descrive una perdita **già avvenuta**: quelle news non sono nel
dossier nemmeno adesso, esistono solo in `news_queue_drops` e nella lista Redis.

---

## 2. Opzioni

### A — Censimento della coda (osservabilità pura, 24/7)

**Idea in una riga:** campionare periodicamente profondità ed età di `news:queue` e persistere
la serie, così l'accumulo notturno e il suo svuotamento all'apertura diventano un dato invece
di un'inferenza dai log.

**Cosa cambia nei file**
- Nuovo `src/workers/news_queue_census.py`: task che legge `LLEN news:queue`,
  `LLEN news:processing`, `LLEN news:dead-letter` e, con un `LRANGE` campionato a testa/coda
  (mai `LMOVE`, mai consumo), ricava l'istogramma delle età per `published_at` e la ripartizione
  per `source`. Riusa `_is_stale_news` (`sentiment.py:169`) **importandolo**, non
  riscrivendo la soglia (regola #169/#467).
- Nuova migrazione `migrations/066_news_queue_census.sql`: tabella `news_queue_census`
  (`sampled_at`, `queue_depth`, `processing_depth`, `dead_letter_depth`, `source`,
  `n_fresh`, `n_stale`, `oldest_age_hours`, `p50_age_hours`).
- `src/workers/celery_app.py`: voce beat ogni 5 min **senza** restrizione oraria e **senza**
  `is_market_open()` — la parte interessante è proprio la notte.

**Freeze-ok?** **Sì.** Non legge nulla il money path, non consuma la coda, non cambia il
destino di nessuna news. Stesso profilo di #161 e #324: strumentazione, da registrare nella
carta per tracciabilità e nient'altro.

**Rischi e side-effect**
- `LRANGE` su una coda di migliaia di item ogni 5 min: I/O trascurabile, ma va **campionato**
  con un tetto esplicito (es. 500 item), non letto per intero, o il censimento diventa esso
  stesso un carico.
- Rischio di doppia verità: se il censimento riconta le età con una formula propria diverge da
  `build_stale_drop_row`. Mitigazione = riuso obbligato dell'helper.
- Nessun impatto su #508/#511: non tocca `news_log` né le metriche di copertura.

**Come si misura che funziona**
- La serie mostra il dente di sega: crescita monotona dalle 21:00Z, picco pre-apertura, crollo
  a ~0 entro un'ora dalla campana. Se il dente sparisce dopo un fix, il fix ha funzionato.
- Risolve un pezzo di **#544** senza aspettarlo: l'evidenza vive in Postgres, non nei log dei
  container, quindi una ricostruzione alle 22:20Z non la distrugge più.

---

### B — Alert per coorte e per causa (correzione della misura)

**Idea in una riga:** far parlare numeratore e denominatore della stessa coorte e aggiungere il
terzo gruppo causale che manca (`off_session`), così la soglia Telegram scatta sui guasti e non
sulla fisiologia.

**Cosa cambia nei file**
- `src/workers/stale_drop_alert.py::collect_stale_drop_measurements` (`:88`): raggruppare per
  **coorte di accodamento** (`raw_ingested_at AT TIME ZONE 'UTC'`)::date invece che per
  `dropped_at::date`, allineandola al giorno su cui `ingestion_stats_daily.queued` è
  incrementato. Il `WHERE` sulla finestra resta su `dropped_at` (per non perdere i drop tardivi),
  ma l'aggregazione no.
- Stessa funzione: terzo `COUNT(*) FILTER` per `went_stale_off_session` — accodato quando la
  seduta era chiusa. Il predicato deve venire dal **calendario vero**, non da una crontab
  ricopiata: la via pulita è persistere il flag di seduta al momento dell'accodamento (una
  colonna booleana su `news_queue_drops`, o la tabella di A), non ri-derivarlo in SQL con
  `14-21` cablato — quello sarebbe esattamente la reimplementazione della regola che #169/#467
  vietano, e sbaglierebbe su DST e chiusure anticipate.
- `build_stale_drop_measurement` (`:42`): nuovo campo nella dataclass; il `ValueError` sulla
  somma delle cause va esteso a quattro addendi.
- `format_stale_drop_alert` (`:229`) e `alert_required`: la quota off-session viene
  **pubblicata** ma **non** concorre alla soglia del 25%; la soglia si applica a
  `already_stale_at_fetch + went_stale_in_queue` **entro seduta**.
- Nuova migrazione `migrations/067_stale_drop_off_session.sql`: colonna
  `went_stale_off_session` su `stale_drop_metrics_daily` e aggiornamento del `CHECK` sulla
  somma (la 062 lo impone a tre addendi).
- Backfill: `run_stale_drop_alert(start_day, end_day)` è già idempotente
  (`ON CONFLICT DO UPDATE`, `:178`) — ricalcolare l'intera serie 08→10/09 è una sola chiamata.

**Freeze-ok?** **Sì**, ed è il caso più chiaro: l'oggetto modificato *è* lo strumento di
misura. Rientra nel test di esenzione della carta nella stessa forma della deroga 2026-08-04
(`costo_usd` a `null`): se non lo correggo, **l'evidenza raccolta è sbagliata**, e al 28/09 la
serie stale-drop entra nella roadmap pesata come se il 29% e il 37% fossero rapporti veri.

**Rischi e side-effect**
- **Discontinuità dichiarata**: cambia la definizione della serie già pubblicata su
  `stale_drop_metrics_daily`. Va annotata nell'artefatto **e** nella carta, e la serie va
  ricalcolata per intero da una sola provenienza — mai due definizioni nella stessa colonna.
- Rischio opposto al problema attuale: se la classificazione `off_session` è troppo generosa
  assorbe anche i guasti veri. Mitigazione: `off_session` è una proprietà del **momento di
  accodamento**, non del momento di scarto — un outage a mercato aperto resta `in_session` per
  costruzione, qualunque cosa succeda dopo.
- Nessun impatto su #508/#511: la copertura efficace si misura su `news_log`, che qui non si
  tocca.

**Come si misura che funziona**
- Righe 08/09 e 09/09 su `alpaca_benzinga`: `alert_required = false`, con
  `went_stale_off_session` che assorbe la quasi totalità dei 157 e 195 scarti.
- L'outage di ieri 15-16Z resta in breach sul gruppo `in_session`: è il test di sensibilità.
  Se dopo la correzione quella finestra **non** allerta più, la correzione è sbagliata e va
  respinta.
- Metrica di rumore: numero di alert Telegram/settimana prima e dopo, con la finestra di
  outage esclusa dal conteggio.

---

### C — Consumo continuo in shadow fuori seduta (il controfattuale)

**Idea in una riga:** far girare la classificazione anche fuori seduta scrivendo su una tabella
shadow che nessuno legge, per quantificare — prima del 28/09 — quanto alpha c'è davvero nella
coorte che oggi buttiamo.

**Cosa cambia nei file**
- Nuovo `src/workers/sentiment_shadow.py`: task **fuori seduta** (beat 21:15Z-13:15Z) che
  legge la coda **senza consumarla** (`LRANGE` + marcatura per `item_id`, mai `LMOVE`, mai
  `delete("news:processing")`), chiama `process_news_batch` in una modalità che **non**
  scrive su Redis né su `sentiment_signals`, e persiste score, `published_at` e
  `fallback_used` su una nuova tabella `sentiment_signals_offsession_shadow`.
- Il punto delicato è che `process_news_item` (`sentiment.py:698`) oggi scrive negli store
  come parte del suo lavoro: serve un parametro di sink esplicito, non un flag globale, o si
  finisce col pubblicare per errore.
- `src/workers/celery_app.py`: voce beat sulla coda `inference`, ma **fuori** dalla finestra
  14-21 così non contende `worker-inference` (concurrency=1) con il path live.
- Nuova migrazione `migrations/068_sentiment_offsession_shadow.sql`.

**Freeze-ok?** **Sì sul money path** — nessun segnale entra in Redis né in `sentiment_signals`,
quindi né gli ingressi né le uscite cambiano. Ma è la deroga più impegnativa delle quattro,
perché consuma budget LLM reale e va registrata con perimetro esplicito ("scrive solo sulla
tabella shadow; nessuna scrittura su `sentiment_signals`, `news_log`, Redis").

**Rischi e side-effect**
- **Costo e capacità**: ~150-200 articoli/notte di inference Ollama Cloud in più. Va messo un
  tetto per notte, o il controfattuale diventa la voce di spesa dominante.
- **Contesa**: se il turno notturno sfora oltre le 13:30Z, contende il worker di inferenza
  proprio nella finestra di apertura, che è la più preziosa. Serve una scadenza dura, non una
  speranza.
- **`news_log` non va scritto**: se lo si scrive, cambia il denominatore di copertura di #511 e
  #508 a metà finestra di osservazione — una discontinuità gratuita su una serie che serve al
  28/09. Le righe restano nella tabella shadow.
- Rischio di scrittura accidentale nel path live: è il rischio serio, e va coperto da test che
  asseriscono zero scritture su Redis e su `sentiment_signals`, non da revisione a vista.

**Come si misura che funziona**
- La domanda a cui deve rispondere: delle news scartate off-session, quante avrebbero prodotto
  `|score| > 0,30`, e qual è il loro forward return a D+1 (via `compute_label_forward_returns`,
  barre Alpaca). Quel numero — e non un'intuizione — decide se la D vale la pena.
- Esito atteso onesto: **`INSUFFICIENT_N` è il verdetto più probabile** su ~2-3 settimane di
  notti. Va pre-registrato prima di vedere i dati (`docs/evidence/PREREGISTRAZIONE_*.md`,
  criterio in `config/s4_kill_criterion.yaml`), o non è riportabile.

---

### D — Disaccoppiamento vero: il gate di seduta si sposta dal consumatore all'esecuzione

**Idea in una riga:** togliere `is_market_open()` dal consumatore di sentiment e lasciarlo dove
appartiene — sull'esecuzione — così una notizia delle 20:02Z viene classificata alle 20:05Z
mentre è fresca, invece di marcire fino alle 13:30Z del giorno dopo.

**Cosa cambia nei file**
- `src/workers/sentiment.py:1121`: rimozione della guardia `is_market_open()`.
- `src/workers/celery_app.py:78`: `sentiment-worker` passa da `hour="14-21"` a 24/5 (o 24/7),
  con cadenza ridotta fuori seduta.
- **Nessuna modifica** a `run-execution` (`:151`), `portfolio-cycle` (`:221`) e
  `run-alpaca-ingestion` (`:162`): restano su `14-21` e mantengono le proprie guardie di seduta.
  È questo che rende il disaccoppiamento sicuro — il gate non sparisce, si sposta a valle, dove
  il rischio è l'ordine, non la classificazione.
- Va rivisto anche `_SENTIMENT_BATCH_SIZE=12` (`sentiment.py:78`): dimensionato sulla cadenza
  15-min di seduta, fuori seduta è arbitrario.

**Freeze-ok?** **No.** È la conclusione del §1: per i simboli **detenuti**, i segnali generati
dalla coorte notturna saltano `_apply_entry_freshness_gate` (#150) ed entrano nel path delle
uscite. È un cambiamento del money path, quindi **programmabile per il 28/09**, non prima —
salvo che C non produca un'evidenza abbastanza forte da giustificare una deroga esplicita, che
è precisamente il motivo per cui C esiste.

**Rischi e side-effect**
- **Carico di inference**: raddoppio circa delle chiamate/giorno. Con `worker-inference` a
  concurrency=1 va verificato che il turno notturno chiuda prima dell'apertura.
- **Cambia il regime di scoring in mezzo alla finestra osservata**, come già successo con la
  Variante A del prompt (deroga 2026-09-01): la lettura di ottobre su S4 andrà segmentata
  before/after, esplicitamente.
- **Effetto atteso sugli ingressi ≈ nullo**: il gate a valle scarterebbe comunque le news
  oltre le 2h per i simboli non detenuti. Il valore, se c'è, è tutto sul path uscite e sulla
  copertura `news_log` (che finalmente conterrebbe la coorte notturna, migliorando #511/#324).
  Questo va detto in anticipo: chi si aspetta più ingressi da questa opzione si aspetta la
  cosa sbagliata.
- **Interazione con `ensemble_priority_hours` (4h, #431)**: un segnale generato alle 20:05Z ha
  `generated_at` notturno e arriva all'apertura già a 17h di età. Va verificato che i consumatori
  a valle lo trattino come vecchio e non come prioritario.

**Come si misura che funziona**
- `stale_drop_metrics_daily`: `went_stale_off_session → ~0` e quota complessiva stabilmente
  sotto il 25% senza toccare la soglia.
- Censimento (A): il dente di sega notturno sparisce; profondità coda ~0 in ogni ora.
- Copertura `news_log` per ticker/seduta (#511): righe notturne presenti dove oggi c'è un buco.
- Test di non-regressione sulle uscite: confronto del numero di `sentiment_reversal` e del loro
  P&L nelle 4 settimane prima/dopo, segmentato — è l'unico punto dove l'opzione può fare danno.

---

## 3. Opzioni scartate, e perché

**"Stop-ingest fuori seduta"** (guardia di seduta su `_on_news`). Non funziona: come da §1.2,
il primo run REST delle 14:00Z ri-pesca gli stessi articoli (`fetch()` senza `start`,
`limit=50`, dedup scaduto a 4h) e li riaccoda, quindi la coorte stale riappare con un'etichetta
di fonte diversa. In più perde la telemetria di trasporto WS appena guadagnata con #455/#48
(1,87 consegne WS/articolo) e riporta la latenza p50 news→coda da <1s a ~1,2h nelle prime ore
di seduta. Costa evidenza e non risolve.

**"Finestra di freschezza adattiva"** (alzare `MAX_NEWS_AGE_HOURS` all'apertura). È **taratura
pura**, congelata fino al 28/09 senza appello. E c'è un secondo motivo, indipendente dal
freeze, per non farlo mai in questa forma: `MAX_NEWS_AGE_HOURS` è la **stessa** costante che
alimenta il gate d'ingresso di S4 (`portfolio_scheduler.py:4158`). Alzarla per far passare la
coda alzerebbe simultaneamente il gate d'ingresso — una modifica del money path travestita da
fix di coda, cioè esattamente il tipo di cambiamento non dichiarato che la carta vieta. Se un
giorno la finestra dovrà essere diversa fra ingest e ingresso, prima vanno separate le due
costanti, poi si discute il valore.

**"Drain-and-discard pre-apertura"** (task alle 13:15Z che svuota la coda registrando gli
scarti). Tecnicamente freeze-ok e facile, ma **non raccomandato da solo**: non recupera una
sola notizia, sposta solo `dropped_at` di 15 minuti — e nel farlo spegne l'unico segnale che
oggi rende il problema visibile. È il modo più rapido di far tacere l'alert senza aver
cambiato nulla. Se lo si vuole per igiene della coda, va fatto **dopo** A e B, mai al posto
loro, e riusando `_is_stale_news` e `build_stale_drop_row` per import.

---

## 4. Raccomandazione

**Ordine: B, poi A in parallelo, poi C. D il 28/09, con il numero di C in mano.**

**B per prima**, perché è l'unica delle quattro che risponde a tutti e tre i vincoli posti
dall'operatore contemporaneamente. Smette di essere un falso allarme strutturale (la coorte
notturna esce dalla soglia perché è classificata per quello che è) e **resta sensibile ai
guasti veri** (l'outage 15-16Z è `in_session` per costruzione, quindi continua ad allertare) —
e la sensibilità non è una speranza, è il criterio di accettazione: se dopo la modifica quella
finestra non allerta più, la modifica è sbagliata. In più è l'unica che va fatta **comunque**,
qualunque cosa si decida il 28/09: finché il denominatore è cross-day, non sapremo misurare se
un fix ha funzionato, e la serie che entra nella roadmap pesata è sbagliata. È anche l'unica
con una deroga già formulata nella carta nella stessa forma (2026-08-04).

**A in parallelo**, perché costa poco ed è il denominatore che manca a tutto il resto: senza
una serie di profondità/età della coda, l'effetto di qualunque intervento si legge solo di
rimbalzo, dagli scarti. E perché mette l'evidenza in Postgres invece che nei log dei container,
che i rebuild delle 22:20Z e 06:20Z hanno già distrutto una volta (#544).

**C subito dopo**, se il budget di inference regge un tetto notturno esplicito, perché è
l'unica cosa che trasforma la D da opinione in decisione. La domanda del 28/09 non è "l'ingest
e il consumo sono disaccoppiati?" — è **"la coorte notturna vale qualcosa?"**. Oggi non lo
sappiamo: le 157 e le 195 news scartate potrebbero essere in gran parte content-mill senza
catalizzatore, esattamente il materiale che #508 dice gonfiare ogni metrica di copertura. Se C
dice `INSUFFICIENT_N` — l'esito più probabile su tre settimane di notti — quello **non** è "non
c'è alpha", ma è comunque un'informazione che cambia la priorità della D. Il criterio va
pre-registrato prima di guardare i dati.

**D il 28/09**, non prima. È la sistemazione corretta — il gate di seduta appartiene
all'esecuzione, non alla classificazione — ma tocca il path uscite attraverso l'esenzione #150
per i simboli detenuti, e il freeze copre esattamente questo. Vale la pena essere espliciti su
cosa la D **non** darà, perché il rischio qui è aspettarsi la cosa sbagliata: non darà più
ingressi (il gate a valle riscarterebbe comunque quelle news per i simboli non detenuti). Darà
uscite più informate sui simboli detenuti e, per la prima volta, la coorte notturna dentro
`news_log`, dove il dossier alpha-miss può vederla.

Su quest'ultimo punto vale la pena chiudere il cerchio con la preoccupazione iniziale: **le
news pre-open che il dossier usa non sono a rischio di essere perse da queste opzioni, perché
sono già perse oggi.** `news_log` è scritto solo dal path di classificazione, e la coorte
notturna non lo attraversa mai. A, B e C non peggiorano la situazione di un centesimo; A e C la
rendono per la prima volta misurabile; solo D la corregge davvero.

---

## 5. Discontinuità e deroghe da registrare

Da annotare in `docs/evidence/OBSERVATION_CHARTER.md` prima dell'esecuzione, non dopo:

| Opzione | Tipo | Cosa registrare |
|---|---|---|
| A | Strumentazione (tracciabilità) | Nuova serie, nessuna modifica a serie esistenti. Perimetro: nessuna lettura dal money path, nessun consumo della coda. |
| B | **Deroga** — difetto di correttezza della misura | Discontinuità nella serie `stale_drop_metrics_daily`: cambia la chiave di aggregazione (coorte di accodamento) e si aggiunge un quarto gruppo causale. Serie ricalcolata per intero da una sola provenienza. Test di sensibilità sull'outage 15-16Z come criterio di accettazione. |
| C | **Deroga** — costo e perimetro | Perimetro esplicito: scrive solo `sentiment_signals_offsession_shadow`. Zero scritture su `sentiment_signals`, `news_log`, Redis — asserito da test, non da revisione. Tetto notturno di inference dichiarato. Criterio pre-registrato prima di guardare i dati. |
| D | **Taratura / money path** | Post-28/09. Segmentazione before/after obbligatoria sulla lettura S4, come per la Variante A del prompt (2026-09-01). |

## 6. Riferimenti verificati

| Fatto | Ancora |
|---|---|
| Guardia di seduta sul consumatore | `src/workers/sentiment.py:1121` |
| Scarto stale senza inference, scan cap 5000 | `src/workers/sentiment.py:1229-1253` |
| `_is_stale_news`, `build_stale_drop_row` | `src/workers/sentiment.py:169`, `:129` |
| `MAX_NEWS_AGE_HOURS=2` | `src/config.py:316` |
| `news_log` scritto solo in classificazione | `src/workers/sentiment.py:753` |
| WS senza guardia di seduta + trigger per articolo | `src/workers/news_stream.py:52`, `:88` |
| REST **con** guardia di seduta | `src/workers/ingestion.py:502` |
| `fetch()` senza finestra temporale, `limit=50` | `src/connectors/alpaca_news.py:64`, `:123` |
| Dedup TTL 4h | `src/connectors/deduplicator.py:22` |
| Beat: sentiment 14-21, alert 22:55 | `src/workers/celery_app.py:79`, `:212` |
| Aggregazione cross-day dell'alert | `src/workers/stale_drop_alert.py:88` |
| Cause registrate (3 gruppi) + `CHECK` sulla somma | `migrations/062_stale_drop_metrics_daily.sql` |
| Gate di freschezza a valle, esenzione simboli detenuti | `src/workers/portfolio_scheduler.py:1246`, `:4158` |
| Dossier legge `news_log` per la copertura | `scripts/alpha_miner_dossier.py:403`, `:1521` |
