# Latenza pubblicazione → ingestion per fonte (#433)

Misura read-only sulla finestra di osservazione dal **2026-08-03 00:00 UTC** al
**2026-09-04 00:00 UTC** (estremo destro escluso). Il risultato principale è che
per Alpaca/Benzinga domina il gap intenzionale fra una sessione e la successiva,
non un buco della cadenza intraday. La misura non autorizza a cambiare quella
cadenza durante il freeze.

## Metodo

Lo script [`scripts/characterize_news_ingestion_latency.py`](../../scripts/characterize_news_ingestion_latency.py)
unisce i due ledger: `news_log` per gli item arrivati allo scoring e
`news_queue_drops` per gli item scartati. Per la distribuzione usa una sola riga
per `(source, article)` al minimo `raw_ingested_at`: altrimenti il fan-out sui
ticker e le pagine sovrapposte moltiplicherebbero gli articoli più vecchi. La
tabella dei drop conserva invece deliberatamente una riga per queue item, lo
stesso denominatore di #149 e della tabella originale della issue.

`raw_ingested_at − published_at` è quindi la latenza fino al **primo avvistamento
del nostro connector**, non fino allo scoring. I percentili sono continui, con
interpolazione lineare. Un item è “nato stale” quando quella differenza supera
le 2 ore; il valore 2 è soltanto il confine della misura esistente, non viene
modificato.

## Distribuzione al primo avvistamento

| fonte | articoli distinti | p50 | p75 | p95 | >2h |
|---|---:|---:|---:|---:|---:|
| `alpaca_benzinga` | 1.170 | 0,23h | 0,60h | 2,78h | 79 (6,8%) |
| `gdelt_gkg` | 17.516 | 0,00h | 0,00h | 0,00h | 0 |
| `reuters` | 1 | 0,00h | 0,00h | 0,00h | 0 |

La riga Reuters non è evidenza di produzione: #434 dimostra che quell'unico URL
è una fixture di test che ha scritto nel DB live. È riportata per non nascondere
una fonte presente nei dati, ma resta fuori dal verdetto.

Per Alpaca/Benzinga la separazione per ora UTC è netta:

| ora del primo avvistamento | articoli | p50 | p75 | p95 | >2h |
|---:|---:|---:|---:|---:|---:|
| 14 | 492 | 0,82h | 1,44h | 4,02h | 78 (15,9%) |
| 15 | 182 | 0,21h | 0,24h | 0,30h | 1 (0,5%) |
| 16 | 157 | 0,19h | 0,24h | 0,29h | 0 |
| 17 | 204 | 0,16h | 0,20h | 0,27h | 0 |
| 18 | 88 | 0,18h | 0,23h | 0,28h | 0 |
| 19 | 47 | 0,19h | 0,23h | 0,29h | 0 |

Settantotto dei 79 articoli Alpaca sopra 2 ore (98,7%) compaiono alle 14 UTC,
al primo poll della sessione. Dopo l'apertura, p95 resta entro 18 minuti.

## Cadenza e finestra Alpaca/Benzinga

Il codice pianifica il task ogni 15 minuti durante le ore di mercato
([`celery_app.py`](../../src/workers/celery_app.py#L147-L164)). Il connector non
manda `start` o `end`: chiede la pagina più recente con `sort=desc` e limite 50
([`alpaca_news.py`](../../src/connectors/alpaca_news.py#L64-L81),
[`alpaca_news.py`](../../src/connectors/alpaca_news.py#L124-L140)). La “finestra”
è dunque la profondità temporale variabile dell'ultima pagina, non un lookback
configurato.

Dal primo giorno in cui i `duplicate_id` rendono osservabile ogni pagina non
vuota (24 agosto) al 3 settembre ci sono 216 cicli visibili. Tutti gli intervalli
intraday hanno p50, p95 e massimo di **15 minuti**: zero intervalli oltre 20
minuti. Le 207 coppie di cicli consecutive nella stessa sessione hanno tutte
finestre di pubblicazione sovrapposte e nessun gap. Il massimo osservato è 39
articoli distinti per ciclo, sotto il limite 50.

Dei 79 articoli >2h al primo avvistamento, 15 appartengono al primo giorno della
telemetria e non hanno una sessione precedente confrontabile. Fra i 64
classificabili, **62 (96,9%)** sono pubblicati dopo l'ultimo ciclo osservato della
sessione precedente e arrivano nel primo ciclo della nuova sessione; soltanto
due sono candidati a visibilità tardiva/backfill. Gli articoli vecchi sono
sbilanciati verso il bordo remoto della pagina (percentile mediano 0,737, dove 1
è il più vecchio; 38 nel quartile più vecchio), ma non sono prodotti da una
pagina troncata né da polling intraday saltato.

Il meccanismo dominante è quindi **nostro e intenzionale**: non si polla durante
il gap off-hours, mentre il provider continua a creare articoli. La fonte
restituisce poi quegli articoli nella pagina più recente al primo ciclo. Questo
spiega la latenza misurata; non implica che Benzinga abbia pubblicato in ritardo.

## Il picco del 28 agosto

Lo script riproduce i numeri della issue: 168 drop stale, latenza fetch media
4,28h, attesa in coda media 0,36h e **123/168 (73,2%)** già oltre 2 ore al fetch.

La scomposizione è:

- 156 queue item erano stati ingeriti alle 14:00; 112 erano già stale;
- la pagina delle 14:00 conteneva 39 articoli distinti, 28 sopra 2 ore al loro
  primo avvistamento; 27 erano stati creati dopo l'ultimo poll del 27 agosto e
  uno, già pubblicato prima, resta candidato a backfill/visibilità tardiva;
- gli altri 11 “nati stale” erano gli stessi `(url, ticker)` già osservati in
  precedenza quel giorno e ricomparsi alle 18:45, 19:15 e 19:30. Il deduplicatore
  scade dopo 4 ore ([`deduplicator.py`](../../src/connectors/deduplicator.py#L11-L22)),
  mentre la pagina latest continuava a contenerli: dopo la scadenza sono tornati
  in coda ormai vecchi.

Il picco è perciò spiegato quasi interamente dal primo poll dopo il gap notturno,
amplificato dal fan-out per ticker; una piccola coda è una ricomparsa dopo TTL.
Non c'è evidenza di un buco nella cadenza intraday il 28 agosto.

## Che cosa significa davvero `published_at`

**Alpaca/Benzinga.** Il connector copia `created_at` in `NewsItem.timestamp`
([`alpaca_news.py`](../../src/connectors/alpaca_news.py#L171-L197)). La
[documentazione Alpaca News](https://docs.alpaca.markets/reference/news-3)
definisce `created_at` come data di creazione dell'articolo e distingue
`updated_at`, che il connector non conserva. Non è documentato come “primo
istante in cui questo account lo vede nell'API”, né come timestamp originario
del publisher a monte. Perciò i due candidati tardivi non permettono di separare
backfill, aggiornamento dei simboli o semantica del timestamp.

**GDELT GKG.** Il connector legge la colonna `V2.1DATE`
([`gdelt_gkg.py`](../../src/connectors/gdelt_gkg.py#L167-L207)). Il
[codebook GKG 2.1 ufficiale](https://data.gdeltproject.org/documentation/GDELT-Global_Knowledge_Graph_Codebook-V2.1.pdf)
la descrive come data di pubblicazione del materiale usato per costruire il
file, uguale per tutte le righe del batch. Il connector scarica proprio l'ultimo
batch da 15 minuti; GDELT dichiara aggiornamenti ogni 15 minuti e processamento
entro 15 minuti da quando monitora un report nella
[descrizione ufficiale di GDELT 2.0](https://blog.gdeltproject.org/gdelt-2-0-our-global-world-in-realtime/).
Gli zeri osservati misurano quindi il prelievo del batch GDELT, non la latenza
dal publisher originario a GDELT: quella non è ricostruibile da questa colonna.

Per chiudere l'incertezza residua servirebbe persistere per ogni poll almeno
`updated_at`, identificativo del poll e insieme dei simboli restituiti, oppure
una sonda shadow che osservi l'API anche off-hours senza alimentare la coda. È
strumentazione nuova e non fa parte di questa issue; nessuna di queste opzioni
è stata attivata durante il freeze.

## Riproduzione

Da un checkout con accesso al Postgres esposto dal compose:

```bash
DATABASE_URL=postgresql://trading:trading@localhost:5432/trading \
python scripts/characterize_news_ingestion_latency.py \
  --since 2026-08-03T00:00:00+00:00 \
  --until 2026-09-04T00:00:00+00:00 \
  --focus-date 2026-08-28
```

Nel container aggiornato lo stesso run è:

```bash
docker compose exec worker python scripts/characterize_news_ingestion_latency.py \
  --since 2026-08-03T00:00:00+00:00 \
  --until 2026-09-04T00:00:00+00:00 \
  --focus-date 2026-08-28
```

L'output atteso contiene `alpaca_benzinga | 1170 | 0.23 | 0.60 | 2.78`, la
riga `2026-08-28 ... 168 | 4.28 | 0.36 | 123 | 73.2` e la diagnosi `62`
gap off-hours contro `2` candidati tardivi.

## Perimetro freeze

Non è stato modificato alcun codice di ingestion. Cadenza beat, pagina/latest
window, TTL, `MAX_NEWS_AGE_HOURS`, soglie, pesi, flag e parametri di strategia
restano identici. Un eventuale polling off-hours o cambio di finestra è lasciato
alla decisione operatore post-freeze in #149.
