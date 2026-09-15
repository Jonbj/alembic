# Provenienza di trasporto per riga (#541) — schema e query di attribuzione

**Data:** 2026-09-15 · **Issue:** #541 · **Migrazione:** `075_news_transport_provenance.sql`
**Perimetro:** persistenza e telemetria. Nessuna soglia, nessun peso, nessun gate, nessun parametro
di taratura (freeze `docs/evidence/OBSERVATION_CHARTER.md` fino al 2026-09-28). Il destino di nessuna
news cambia.

---

## 1. Il problema in una riga

`source` dice **chi ha pubblicato** (`alpaca_benzinga`), non **da dove è arrivato**. Alpaca/Benzinga
ha due consegne per lo stesso contenuto — WebSocket 24/7 e poller REST a 15 minuti — e #455 le ha
unificate sotto un solo contratto di dedup/telemetria. Scelta corretta, ma una volta persistita la
riga non dice più quale dei due l'ha vista per primo.

Due misure aperte ne dipendono:

- **#455 / decisione sul polling REST.** Il 2026-09-08, 3 articoli su ~120 (~2,5%) non sono mai stati
  consegnati dal WebSocket pur avendo simboli sottoscritti. Il numero è stato ricostruito a mano dai
  log dei container, che ruotano: non è riproducibile domani, quindi la decisione «spegnere il
  polling o tenere l'affiancamento» resta sospesa su un campione di una giornata sola.
- **Gradino del 10/09.** `docs/research/stale_cohort_fetch_latency_2026-09-15.md` §4.1 attribuisce il
  salto `already_stale_at_fetch` 18 → 263 fra il 09 e il 10/09 al passaggio del primo avvistamento
  dal REST al WS — ma **per inferenza dalla latenza** (`raw_ingested_at − published_at ≈ 0 ⇒ WS`),
  non per osservazione. Con la colonna, la stessa domanda si risponde guardando il ledger.

## 2. Regola di scrittura: registra chi osserva

Il trasporto è una proprietà dell'**avvistamento**, non dell'articolo.

| ledger | cosa contiene la colonna |
|---|---|
| `news_log.transport` | il trasporto del **primo** avvistamento — solo il primo supera il dedup e arriva fin qui, quindi vale per costruzione |
| `news_queue_drops.transport` | il trasporto dell'avvistamento che ha prodotto **quella** riga di scarto |

Lo stesso articolo produce quindi una riga `ws` (accodata, sopravvissuta) e N righe `rest`
(`duplicate_id` ai poll successivi, più l'eventuale eco `stale` alla scadenza della TTL di dedup).
È proprio quella coppia a rendere attribuibile il gradino.

`NULL` significa **«path non strumentato»**, ed è un'informazione vera e distinta da `rest`: i
connettori senza variante WebSocket (GDELT, MarketAux, Finnhub, RSS, EDGAR) restano NULL di
proposito, e le righe anteriori al deploy pure.

**Nessun backfill.** Lo storico non ha la provenienza e non è ricostruibile. Dedurla dalla latenza è
l'euristica di *analisi* dichiarata nel documento del 15/09; scriverla nel ledger la
trasformerebbe in un dato misurato che non è. La serie comincia al deploy, dichiarato.

**Il dedup resta uno solo.** Il trasporto non entra in nessuna chiave di dedup
(`compute_dedup_hash` → titolo+corpo, `is_duplicate_by_id` → `item.id`): se ci entrasse, WS e REST
smetterebbero di deduplicarsi a vicenda e ogni articolo entrerebbe due volte nella pipeline. Il
contratto unico di #455 è presidiato da un test
(`tests/workers/test_news_transport_provenance.py::test_il_dedup_non_e_partizionato_per_trasporto`).

## 3. Lo snapshot della sottoscrizione

La DoD richiede che il tasso sia calcolato **solo sui simboli effettivamente sottoscritti in quel
momento**: un articolo su un titolo fuori watchlist recuperato dal REST non è un articolo perso dal
WebSocket. Quella condizione non era verificabile a posteriori — `WATCHLIST_SYMBOLS` è baked
nell'immagine e non lascia traccia storica.

`news_stream_subscriptions` la persiste: `registra_sottoscrizione()` scrive uno snapshot all'avvio di
`worker-news-stream`, cioè l'unico momento in cui la sottoscrizione cambia (il processo sottoscrive
una volta e resta connesso). È fail-safe: se Postgres non risponde lo stream parte lo stesso, e una
finestra senza snapshot vale «non sottoscritto» — **nessun miss dichiarato, mai un miss inventato**.

## 4. Le query

### 4.1 DoD: quanti articoli ha perso il WebSocket ieri, su quali simboli, con che ritardo

```sql
SELECT * FROM news_ws_missed_daily WHERE day = CURRENT_DATE - 1;
```

Una sola query, nessun log di container. Definizione di miss: primo avvistamento `rest` **e** simbolo
nella sottoscrizione attiva al momento della **pubblicazione**. Le righe senza trasporto sono
escluse da entrambi i gruppi: una riga non attribuita non è né un miss né una consegna riuscita, e
metterla in uno dei due falserebbe il tasso in una direzione precisa.

Articoli e coppie `(articolo × ticker)` sono contati **separatamente** (`articoli_ws_missed` vs
`coppie_ws_missed`). È la lezione di §2.3 del documento del 15/09: «i 313 scarti sono 69 articoli»,
rapporto 4,5:1 dall'espansione per ticker. Una serie che conta coppie chiamandole articoli è gonfia
per costruzione.

### 4.2 Attribuzione WS/REST degli scarti stale — il gradino del 10/09

```sql
SELECT date(raw_ingested_at)                        AS coorte,
       COALESCE(transport, '(non strumentato)')     AS trasporto,
       count(*)                                     AS righe,
       count(DISTINCT article_id)                   AS articoli,
       round(avg(EXTRACT(EPOCH FROM (raw_ingested_at - published_at)) / 3600.0)::numeric, 2)
                                                    AS latenza_fetch_media_ore
FROM news_queue_drops
WHERE discarded_reason = 'stale'
  AND enqueued_off_session IS NOT TRUE          -- coorte in-seduta (#432)
GROUP BY 1, 2
ORDER BY 1 DESC, 2;
```

Sostituisce l'inferenza «latenza ≈ 0 ⇒ WS» con una lettura. Se l'ipotesi di §4.1 del 15/09 è giusta,
un gradino futuro deve mostrarsi come uno spostamento del primo avvistamento verso `ws` con le eco
`rest` che seguono 4h dopo. **Applicabile solo dal deploy in avanti**: le righe del 10/09 restano
`NULL`, e questa query le mostra come tali invece di attribuirle d'ufficio.

### 4.3 Primo avvistamento per coppia

```sql
SELECT * FROM news_transport_first_sighting
WHERE published_at >= CURRENT_DATE - 1
ORDER BY published_at DESC;
```

Vista di appoggio: unisce `news_log` e `news_queue_drops` e tiene l'avvistamento più antico per
`(url, simbolo)`. È il mattone su cui poggia `news_ws_missed_daily`.

## 5. Cosa serve prima di riaprire la decisione sul polling

La DoD di #541 chiede **≥ 10 sedute** di serie prima che la decisione «spegnere il polling REST»
torni in discussione. Fino ad allora `news_ws_missed_daily` si accumula e basta. Il costo di tenere
l'affiancamento nel frattempo resta quello misurato: i doppioni vengono scartati prima dello
scoring, e il documento del 15/09 ha provato che il costo in alpha degli scarti in-seduta è zero
(100% degli articoli già visti freschi entro 15 minuti).
