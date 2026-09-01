# Fonti news — consolidato di due analisi indipendenti (2026-09-01)

Consolida `docs/research/2026-09-01-news-provider-alternatives.md` (survey ampia su
candidati esterni, licenze/ToS) e `files/fonti_news_analisi_2026-09-01.md` (diagnosi
live sul sistema attuale + rimisura diretta delle API). Le due analisi si incrociano
sugli stessi numeri di produzione in modo indipendente (1.899 righe `alpaca_benzinga`,
1.391 `gdelt_gkg` su 30gg — identici), ma **divergono su un punto rilevante**, corretto
sotto.

## Correzione a #159, non un flip-flop

Ho chiuso #159 (GDELT DOC) oggi citando il mini-spike di luglio (lag ≥2 giorni,
rilevanza bassa). La seconda analisi ha **rimisurato oggi con una chiamata reale**
all'API GDELT DOC (query NVIDIA, `timespan=24h`): lag mediano **12,7h** (min 0,4h, non
più ≥2 giorni), e **10/10 articoli genuinamente pertinenti** (contro l'"Eli
Lilly/Carvana" di luglio). La premessa che ho usato per chiudere l'issue **non descrive
più il comportamento reale di GDELT DOC oggi**.

**La conclusione operativa non cambia** — GDELT DOC resta inutilizzabile — ma per un
motivo diverso e più preciso: il filtro di freschezza live di Alembic è **2 ore**, non
12 come assumevo (`MAX_NEWS_AGE_HOURS` default `2`, `src/config.py:316-318`, verificato
anche con `printenv` nel container; il default del connettore GDELT DOC dice ancora
`timespan="12h"` — stale). Con un filtro a 2h, anche il GDELT DOC di oggi (lag mediano
12,7h) passerebbe solo ~2 articoli su 10. **Il blocco è nostro (una variabile
d'ambiente locale), non più "strutturale lato GDELT" come avevo scritto.** Vado a
correggere il commento di chiusura su #159 per non lasciare un fatto sbagliato nel
registro.

Nota a margine, indipendente da GDELT: se il filtro reale è 2h e non 12h come
documentato altrove nel repo (`gdelt_doc.py` docstring, commenti nel CHANGELOG), vale
la pena chiedersi quante fonti *legittime* con lag anche solo di 2-3h vengono scartate
oggi senza che nessuno se ne accorga — punto per una issue di misura a parte.

## Cosa i due report confermano insieme (alta fiducia)

1. **Solo 2 fonti attive**, entrambe sotto-sfruttate:
   - `alpaca_benzinga`: il connettore non chiede `include_content=true` — riceve
     ~160 caratteri (summary) quando l'API, con le stesse chiavi, restituirebbe
     3.930-15.757 caratteri (content). **Zero costo, due righe di codice**
     (`src/connectors/alpaca_news.py`), quantificato da entrambe le analisi
     indipendentemente sugli stessi numeri.
   - `gdelt_gkg`: il "corpo" **è** il titolo nel 100% delle righe (`body=title`,
     `src/connectors/gdelt_gkg.py:208`) — non è una fonte di articoli, è una fonte di
     titoli.
2. **Il WebSocket Alpaca esiste, è testato, è spento.** `src/connectors/alpaca_news_stream.py`
   + `src/workers/news_stream.py` sono scritti e registrati nel beat
   (`celery_app.py:32`), ma **nessun worker consuma la coda `news_stream`**
   (verificato: `docker-compose.yml` ha solo `-Q celery`/`-Q inference`). Accenderlo
   porterebbe il lag da p50 ~1,2h a <1s ed eliminerebbe **16.254 scarti
   `duplicate_id`** + **2.640 scarti `stale`** su 30gg (dato dal funnel
   `news_queue_drops`) — puro spreco di re-fetch della stessa finestra ogni 15 min.
3. **SEC EDGAR: connettore rotto, non fonte da scartare.** Legge un campo
   `ticker_symbol` inesistente nell'API EDGAR → zero segnali da sempre. Il ticker è
   dentro `display_names` (`"NEWS CORP (NWS, NWSA, NWSLL) (CIK 0001564708)"`,
   verificato oggi sull'API reale) o mappabile con `company_tickers` — la stessa mappa
   già usata dal ticker resolver. Fix a costo zero, tagging deterministico, eventi
   8-K/6-K ad alto rapporto segnale/rumore.
4. **Non riattivare**: NewsAPI, TheNewsAPI, StockNewsAPI, GNews, Google News RSS, FMP
   (bloccato/non verificabile), MarketAux (verificato di nuovo oggi: stesso problema di
   rilevanza anche col fix di luglio). Finnhub solo con licenza commerciale — e
   comunque ~50% del suo contenuto duplica Benzinga che già ingeriamo.

## Un disaccordo reale fra le due analisi — da risolvere prima di agire

**Massive/Polygon.io** (news incluso nel piano Basic gratuito, 5 req/min):
- La prima analisi lo verifica sui **termini di licenza** e trova che il piano Basic è
  esplicitamente **"Individual use"**, con termini che vietano **non-display/derivati,
  inclusa esplicitamente una strategia d'investimento**.
- La seconda lo raccomanda come **"il miglior candidato nuovo"** senza citare questo
  vincolo di licenza.

Prima di qualunque POC su Massive/Polygon.io va riletto il testo esatto della licenza
Basic — se il divieto "strategia d'investimento" è confermato, il candidato è
**scartato indipendentemente dalla qualità tecnica**, non solo rimandato.

## Shortlist per sviluppo, in ordine di rapporto valore/rischio

### Priorità 0 — zero fonti nuove, solo usare meglio quello che c'è

1. `include_content=true` su Alpaca + preferire `content` a `summary`
   (`src/connectors/alpaca_news.py`) — 160→migliaia di caratteri sul flusso primario.
2. Accendere il worker `news_stream` (Alpaca WebSocket) — codice pronto, elimina
   ~19.000 scarti/30gg fra duplicati e stale.
3. Correggere il mapping ticker di `src/connectors/sec_edgar.py:93`
   (`display_names` o `company_tickers`) — fonte event-driven gratuita, deterministica.

### Priorità 1 — POC in shadow, dopo aver chiuso Massive/Polygon.io

4. Twelve Data `press_releases` — POC 10-20 simboli, corpo HTML completo, ma senza
   `url`/fonte documentati nello schema: serve policy di mapping prima del POC.
5. Tiingo Starter — POC **esclusivamente in memoria** (i termini vietano persistere il
   payload su Starter): elabora, misura, scarta il payload, conserva solo
   segnali/metriche derivati non ricostruibili.
6. Massive/Polygon.io — **solo dopo** aver chiarito il vincolo di licenza sopra.

## Avvertenza sul freeze (entrambe le analisi lo dicono, concordano)

Ognuno dei tre punti di Priorità 0 cambia il volume ingerito o la freschezza — cioè la
serie osservata dal freeze #171. Non sono difetti di correttezza nel senso della carta
di osservazione (nulla si comporta diversamente dal proprio design; sono
arricchimento/copertura, non bug) — quindi **servono una deroga esplicita come quella
di oggi per #399/#408**, non rientrano da soli nel perimetro "correttezza" già esente.
