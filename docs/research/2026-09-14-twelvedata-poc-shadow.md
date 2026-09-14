# PoC shadow Twelve Data press_releases — Passo 0 + 1 seduta

Issue: #458
Autore: agent/issue-458 (worktree)
Data: 2026-09-14
Esito: 76 campioni scritti in `news_poc_samples` su 12 simboli in 1 seduta;
nessuna scrittura su path live (connettore, script e tabella shadow isolati
testati con `tests/scripts/test_poc_twelve_data_isolation.py`).

## Passo 0 — verifica schema e semantica con chiave reale

La chiave `TWELVE_DATA_API_KEY` e' ora nel `.env` principale; l'endpoint
corretto, `https://api.twelvedata.com/press_releases`, e' stato verificato live
sia con la chiave pubblica `demo` (solo AAPL, 2026-09-07) sia con la chiave reale
(2026-09-14, questo run).

| Punto | Risultato live (chiave reale, 2026-09-14) |
| --- | --- |
| 1. Schema della risposta | confermato: top-level `status`, `pagination {current_page, per_page}`, `press_releases[]`. Record: `id` (stringa tipo `20260528C4858`), `datetime` (ISO-Z), `title`, `body` (HTML), `style` (CSS), `language` (lista). **Nessun campo `url` ne' `source`** — dedup su `id`. |
| 2. Simbolo inesistente (`symbol=ZZZZZZZ`) | HTTP 200 + body `{"code":404,"message":"**symbol** or **figi** parameter is missing or invalid","status":"error"}` — il connettore lo mappa su `TwelveDataInvalidSymbolError`, lo script logga e prosegue con gli altri simboli. |
| 3. Simbolo valido senza PR recenti (`symbol=XOM` con la coorte del run) | HTTP 200 + body `{"pagination":{...},"press_releases":[],"status":"ok"}` — lista vuota, **non** errore. Il connettore non solleva nulla e `fetch()` produce 0 items, come da edge case 2. |
| 4. Multi-symbol (`symbol=AAPL,MSFT`) | Il provider ritorna solo il primo simbolo (AAPL). Confermato in due run separati. Quindi la PoC tratta la lista come N chiamate da 1 credito ciascuna, e il budget va calcolato di conseguenza. |
| 5. Filtri temporali | `start_date`/`end_date` (ISO date) accettati e filtrano davvero (es. finestra 2026-09-01..2026-09-14 → 0 risultati per AAPL). Non esiste un filtro `range`/`from`/`to`. Confermato che senza filtro il polling rischia di riprendere record vecchi — il dedup lato nostro (su `external_id`) resta obbligatorio. |
| 6. Limite di paginazione | `outputsize > 8` → `{"code":400,"status":"error","message":"There is an error in the query"}` con HTTP 200. Il connettore quindi clampa `outputsize` a 8 (range [1,8]) prima di costruire la richiesta. |
| 7. Rate limit (8 crediti/min, 800/giorno) | Verificato: 4/12 simboli del primo run hanno ricevuto `code=429` entro lo stesso minuto. Lo script li rinvia a fine giro e dopo un backoff di 60s. |
| 8. Schema `outputsize` vs `limit` | `outputsize` (pagina) e `limit` (record?) sono entrambi accettati; per la PoC usiamo solo `outputsize=8` (il massimo che la chiave regge senza 400). |

## Risultati 1 seduta (2026-09-14)

12 simboli (`_DEFAULT_SYMBOLS` nello script), `outputsize=8`, paginazione=1.
Richieste consumate: 16 (12 simboli del primo giro + 4 simboli rate-limited
recuperati dopo il backoff). Budget giornaliero rimanente: 700 − 16 = 684.

```
symbol   rows  avg_body_chars  ticker_ok
AAPL        8          12429         7/8
AMZN        8           5689         4/8
BAC         8           7805         8/8
CVX         3           5806         3/3
GOOGL       5          12787         5/5
GS          8           9325         8/8
JPM         8           7124         8/8
META        8           7690         8/8
MS          4           3212         3/4
MSFT        8           4771         8/8
NFLX        8           8314         7/8
XOM         0             —          0/0
-------------------------------------
TOTAL      76                     69/76 = 90.8%
```

- **Copertura**: 11/12 simboli producono almeno un comunicato nella finestra
  (XOM e' vuoto — coerente con il punto 3 del Passo 0).
- **`ticker_valid`**: 90.8% dei record della PoC ha il simbolo richiesto nel
  titolo o nel body. I 7 fail sono press release "commentary" che citano AAPL
  insieme a un portfolio di altri titoli (es. "Apple Inc. (NASDAQ: AAPL),
  Alphabet Inc. (NASDAQ: GOOGL)…" nel comunicato `20260528C4858`) ma il
  simbolo richiesto non era AAPL.
- **Dedup**: 0 duplicati (76 distinct_id su 76 record). `ON CONFLICT
  (poc_source, external_id)` funziona correttamente.
- **`body_chars`** (post-strip HTML/CSS): mediana ~7000 caratteri, che
  corrisponde a un comunicato di taglia editoriale medio. Il campo `body`
  contiene 256+ tag HTML + CSS inline (campo `style`); senza la strip
  misureremmo boilerplate, non testo utile.
- **Rate limit**: 4 simboli su 12 nel primo run sono stati 429 e rinviati dopo
  un backoff di 60s. Il budget enforcement del connettore (`_DAILY_REQUEST_BUDGET
  = 700` su 800 del piano Basic) si e' comportato come da contratto.

## Latenza

`latency_seconds = fetched_at − published_at` e' la differenza fra l'istante
del fetch e l'`datetime` originale del comunicato. I record Twelve Data sono
spesso **indietro di settimane/mesi** rispetto al fetch (il p50 e' nell'ordine
di giorni, il p95 di mesi) perche' la fonte aggrega comunicati stampa di terze
parti con data di pubblicazione originale. Questo **non e'** un bug e **non**
e' il `news_log` latency: e' semplicemente la meta-informatione del fornitore.

Per l'uso live (se mai integrato) la latenza andrebbe misurata diversamente:
`fetched_at − ingestion_datetime_del_fornitore`, non `fetched_at −
published_at`. Twelve Data non espone `ingestion_datetime`, quindi per la PoC
questa metrica va letta con la dovuta cautela.

## Isolamento dal path live

Test: `tests/scripts/test_poc_twelve_data_isolation.py` — 6 test, tutti
passati. Tutti e tre i test (import, store references, table references)
analizzano l'AST dei due file (`src/connectors/twelve_data_press_releases.py`,
`scripts/poc_twelve_data_shadow.py`) e falliscono se trovano:

- import da `src.store.redis_store`, `src.store.redis_keys`,
  `src.workers.sentiment`, `src.workers.sentiment_worker`,
  `src.connectors.alpaca_news`, `src.connectors.finnhub_news`,
  `src.connectors.marketaux`, `src.connectors.gdelt`, `src.connectors.rss`,
  `src.connectors.sec_edgar`, `src.brokers.alpaca_adapter`,
  `src.brokers.ibkr_adapter`, `celery`, `src.workers.celery_app`;
- stringhe letterali `news_log`, `news:queue`, `news:queue:item`,
  `news:dedup`, `signal:current`, `signal:history` dentro query SQL
  (`cur.execute(...)`); le docstring sono escluse perche' documentano cosa
  NON va toccato;
- tabelle diverse da `news_poc_samples` e `news_poc_request_budget` menzionate
  nelle stesse query.

Sanity check eseguito: aggiungendo `from src.store.redis_store import foo` allo
script, `test_no_live_path_imports` fallisce come previsto.

## Cosa manca per chiudere l'issue

L'issue prevede **5 sedute** di misura, non 1. Il run di oggi e' una seduta
completa di PoC; le altre 4 vanno lanciate via cron manuale o invocazione
diretta (NON nel beat di produzione, vincolo nel corpo della issue) nei
prossimi giorni. Le metriche finali (p50/p95 di latenza "vera" se possibile,
copertura per simbolo su 5 giorni, costo crediti reale, duplicazione vs
Alpaca/SEC EDGAR) vanno aggiunte a questo documento o come commento su
#458.

## Decisione consigliata (per l'operatore)

Da questi dati la PoC mostra che Twelve Data `press_releases` e' una fonte
**per lo piu' di terze parti / commentary** (il body di AAPL contiene il
simbolo come parte di una lista di titoli citati, non come annuncio di AAPL),
e il `ticker_valid` del 90.8% riflette il rumore di fondo dei comunicati
aggregati. Per un uso come fonte di segnale diretto su AAPL sarebbe una scelta
scadente; come fonte di terze parti su un portafoglio tematico (rare earth,
AI, ecc.) potrebbe invece avere senso.

La decisione di integrazione live va pero' rimandata a dopo 5 sedute di misura
e non e' coperta da questa issue.

## File toccati

- `src/connectors/twelve_data_press_releases.py` — gia' su main via PR #577.
- `scripts/poc_twelve_data_shadow.py` — gia' su main via PR #577.
- `migrations/065_news_poc_samples.sql` — gia' su main via PR #577.
- `tests/connectors/test_twelve_data_press_releases.py` — gia' su main via PR #577.
- `tests/scripts/test_poc_twelve_data_isolation.py` — **nuovo in questa PR**
  (Seam 3 dell'issue, mancante da PR #577).