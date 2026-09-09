# Confronto latenza news ingestion: pre vs post WebSocket (#455)

Misurato il 2026-09-08 con `scripts/characterize_news_ingestion_latency.py` (strumento
del #433: percentili per articolo al primo avvistamento, drop stale per queue item).
Il worker `worker-news-stream` (PR #526, merge `bd6c2c3`) è stato attivato sul cluster
live il 2026-09-07 ~13:00 UTC.

- **Pre**: finestra 2026-08-03T00:00Z → 2026-09-07T13:00Z (35,5 giorni, solo polling REST 15 min)
- **Post**: finestra 2026-09-07T13:00Z → 2026-09-08T22:00Z (33 ore, WebSocket + REST affiancati)

## 1. Latenza pubblicazione → ingestion (Alpaca/Benzinga)

| Metrica | Pre (35,5 gg) | Post (33 h) | Delta |
|---|---|---|---|
| Articoli distinti | 1.227 | 143 | — |
| p50 | 0,23 h (**13,8 min**) | **0,22 s** | ~3.800x |
| p75 | 0,66 h (**39,6 min**) | **0,3 s** | — |
| p95 | 3,24 h (**3 h 14 min**) | **0,6 s** | ~19.000x |
| Max | >26 h (span pagina 28/08) | 258,8 s (4,3 min) | — |
| Articoli >2 h | 95 (**7,7%**) | 0 (**0,0%**) | eliminato |

Percentili post calcolati anche in secondi esatti via SQL (first-sighting per
articolo, deduplicazione fan-out ticker): p50 = 0,2 s, p75 = 0,3 s, p95 = 0,6 s, max
258,8 s. 185 item dello score path (`news_log`) sono entrati <5 s dalla pubblicazione
(105 articoli distinti): il path WebSocket scrive `news_log` con lo stesso contratto
del path REST.

Il p95 post di 0,6 s conferma la latenza dichiarata del modulo (<1 s) contro il p50
pre di ~1,17 h del polling REST. Il singolo outlier a 4,3 min è un articolo
consegnato dal REST di recupero, non dal WebSocket.

## 2. Drop `stale` (gate freschezza 2 h)

| Metrica | Pre | Post |
|---|---|---|
| Queue item stale totali | 3.670 (35,5 gg, ~103/gg) | 157 (33 h) |
| di cui **nati stale** (fetch >2 h) | 561 misurabili (54% degli item con copertura), punte per sessione: 28/08 168 drop **73,2%** nati stale; 24/08 209 drop **73,7%**; 09-04 89 drop **86,5%** | 27/157 (**17,2%**) |
| fetch h media (nati stale) | 1,18–4,28 h per sessione | 4,0 h |
| queue h media | 0,36–67 h | 19,4 h (backlog, v. sotto) |

Composizione dei 27 born-stale post: **16 queue item derivano da soli 3 articoli
distinti** mai consegnati dal WebSocket (pubblicati 15:27–15:41 UTC del 09-08,
simboli citati compresi nella subscription: ABBV, MRK, LLY, XLV, JNJ, V, MA, AXP;
recuperati dal REST alle 19:30/19:45) e **11 item** sono backlog pre-finestra
(ingested 09-04, rimasti in coda sentiment ~90 h). Il problema strutturale del
polling (decine di articoli overnight nati stale a ogni apertura, es. 28/08:
123 born-stale) è **eliminato**: gli articoli fuori orario arrivano ora in tempo
reale via WebSocket.

I restanti **129 item stale post nascono fresh** (fetch <2 h, in gran parte <1 s)
e superano il gate 2 h solo in coda sentiment, con ritardi di elaborazione da 2 a
14 h in calo durante la giornata. Non è latenza di ingestion né un effetto del
WebSocket: è il backlog della coda `inference` — da trattare come problema
separato.

## 3. Drop `duplicate_id`

| Metrica | Pre | Post |
|---|---|---|
| Queue item/giorno (giorni di borsa) | 2.135–3.178 (media 711 su 35,5 gg) | 4.644 (09-08) |
| Item per articolo | ~20,6 | ~49 |

Il raddoppio è coerente con l'**affiancamento transitorio** documentato nel runbook
(`docs/operations.md`): il WebSocket fa il first-sighting immediato e il polling
REST ridondante continua a re-fetchare la stessa finestra ogni 15 minuti, generando
scarti `duplicate_id` in più senza costo di inferenza (la deduplica condivisa li
blocca prima dello scoring). La deduplica funziona: zero doppioni passati allo
scoring.

**Correzione (2026-09-09).** L'attribuzione al solo re-fetch REST era incompleta:
anche il WebSocket, da solo, ridistribuisce lo stesso articolo piu' volte. Conteggio
sui log durabili `logs/containers/worker-news-stream-2026-09-08.log` (giornata piena
di affiancamento): **298 eventi consegnati per 159 titoli distinti = 1,87 eventi per
articolo**, con code lunghe (12 consegne per `S&P 500, Nasdaq Slip...` e per
`Intel Hits 1 Million-Wafer Milestone...`, 10 per `Taiwan Semiconductor, ASML...`).
Sono gli update di contenuto Benzinga sullo stesso `news_id`, moltiplicati poi dal
fan-out per ticker. Ne segue che **spegnere il polling REST non azzera il gonfiaggio
di `duplicate_id`**: rimuove la quota di re-fetch, non la ridistribuzione WS, che ha
bisogno di un debounce lato consumer (issue #48 «B35: debounce news stream»). Il
costo resta comunque quasi nullo, perche' la deduplica blocca prima dello scoring.

## 4. Verifica operativa del deploy (2026-09-08 ~21:30 UTC)

- `docker compose ps worker-news-stream` → `Up` (container ricreato dal
  deploy_reconcile, `restarted=0`), connessione `wss://stream.data.alpaca.markets/v1beta1/news`
  attiva, subscription su 92 simboli;
- log durabili `logs/containers/worker-news-stream-2026-09-0{7,8}.log`: stream
  attivo dal 07, news consegnate in ogni ora di mercato 10–20 UTC del 08;
- path scoring verificato: 185 item `news_log` con latenza <5 s.

## 5. Acceptance criteria #455

- [x] Worker/coda `news_stream` attivo e consumato in produzione (verify §4).
- [x] Contratto dedup/telemetria WebSocket = REST: verificato in review PR #526 e
      confermato operativamente (stesso ledger `news_queue_drops`, stesse chiavi di
      dedup, `raw_ingested_at` paragonabile fra i due path).
- [x] Misura prima/dopo: §1 (p50/p95 lag) e §2–3 (tasso `stale`/`duplicate_id`).
- [x] Decisione esplicita REST affiancamento vs sostituzione: affiancamento
      transitorio documentato nel runbook; la disattivazione del polling resta
      decisione successiva a questo confronto (follow-up aperto).

## 6. Note residuali (fuori dal perimetro di #455)

1. **Backlog coda `inference`**: 129 item nati fresh scartati stale per ritardo di
   elaborazione (fino a 14 h di coda). Il WebSocket non c'entra: da prioritizzare
   a parte.
2. **3 articoli WS-missed su ~120** (~2,5%): pubblicati 15:27–15:41 UTC con simboli
   sottoscritti ma mai consegnati dal WebSocket; recuperati dal REST 4 h dopo.
   Da monitorare sul campione dei prossimi giorni prima di valutare il destino
   del polling REST.
3. **duplicate_id ~2x** durante l'affiancamento: solo in parte imputabile al
   re-fetch REST. Il WebSocket ridistribuisce lo stesso articolo 1,87 volte in media
   (max 12, misura §3), quindi la decisione sul polling REST riduce ma non elimina
   il gonfiaggio; la parte WS ricade su #48 (debounce).
