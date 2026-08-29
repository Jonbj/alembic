# Copertura news: il punto cieco lato uscita — misura del 2026-08-28 (#324)

Scritta dentro il periodo di sola osservazione (#171). **Nessuna taratura toccata**: qui
c'e' solo cio' che si e' misurato e cio' che resta all'operatore. Le query sono
read-only su `alembic-postgres-1`; i prezzi vengono da Alpaca SIP.

## 1. La premessa della issue regge, con una correzione

`compute_miss_candidates` (`src/analysis/dossier/market.py`) costruisce i candidati miss
sui soli mover **non** in portafoglio (`sym not in in_portafoglio`). Verificato sul
dossier del 2026-08-19: 8 candidati, 6 classificati `NO_NEWS`, e GE (-5,03%),
DELL (-6,64%), WDC (-6,87%) — due dei tre peggiori mover della seduta — **assenti da ogni
riga del dossier**, perche' erano nel libro. Le loro zero righe `news_log` non venivano
contate da nulla, mentre le stesse zero righe su un simbolo non detenuto producevano un
candidato `NO_NEWS`. Il punto cieco esiste ed e' strutturale, non accidentale.

Sul 2026-08-19, 48 posizioni erano vive all'open RTH e **18 avevano zero righe
`news_log` nella seduta** (ABBV, ARM, ASML, BAC, CVX, DELL, GE, GM, JNJ, MMM, PBR, ROKU,
SBUX, SNOW, UBS, UNH, VALE, WDC).

**Correzione alla issue.** I tre nomi che la issue cita come «posizioni in perdita
marcata» sono qualificati sul **ritorno di seduta**, non sulla perdita dall'ingresso. Al
close del 2026-08-19:

| ticker | ritorno seduta | ritorno dall'ingresso | copertura nulla | cieco lato uscita |
|---|---|---|---|---|
| GE | -5,03% | **+4,25%** | sì | no |
| DELL | -6,64% | **+2,31%** | sì | no |
| WDC | -6,87% | **-15,87%** | sì | **sì** |
| UNH | — | -9,13% | sì | **sì** |
| VALE | — | -5,05% | sì | **sì** |

Una posizione che perde il 5% in giornata ma e' ancora in profitto dall'ingresso non ha
la stessa domanda d'uscita di una che perde il 16% dall'ingresso. La misura introdotta
qualifica sulla **perdita dall'ingresso fino al termine della detenzione nella seduta**
(prezzo d'uscita intraday, close se ancora aperta) — la formulazione del punto 3 della
issue stessa — e riporta entrambe le grandezze separate, cosi' che l'errore non si ripeta.
Sul 2026-08-19 la misura trova **3 posizioni cieche** (WDC, UNH, VALE), non le tre
nominate: una si sovrappone, due sono nuove, due erano falsi positivi.

## 2. Punto 2 della issue: nessun ticker e' senza fonte configurata

La domanda era distinguere *fonte non configurata* da *fonte configurata a resa zero*.
Dal codice la risposta e' univoca: le fonti per-ticker vive interrogano **l'intera
watchlist**. `run_alpaca_ingestion_worker` costruisce `AlpacaNewsConnector(symbols=
config.WATCHLIST_SYMBOLS)`, e `WATCHLIST_SYMBOLS` e' caricato da
`config/trading.yaml -> symbols.watchlist` (`src/config.py:328`); il connettore passa
tutti i simboli nel parametro `symbols` della query (`src/connectors/alpaca_news.py:132`).
Non esiste un bucket «senza fonte»: **tutti e 96 i simboli sono configurati**.

Le fonti vive sono due, e coprono in modo molto diverso:

| fonte | interrogazione | ticker distinti 17-21/08 |
|---|---|---|
| `alpaca_benzinga` | per-ticker, tutta la watchlist | 72 |
| `gdelt_gkg` | broadcast, ticker estratti dal testo | 33 |

GDELT DOC per-ticker (`src/connectors/gdelt_doc.py`) e' implementato ma **non
schedulato** in `src/workers/celery_app.py` (issue #159).

## 3. La copertura non e' un insieme fisso di ticker al buio: ruota

Sulle 5 sedute 2026-08-17..21, contando le sedute con almeno una riga per simbolo di
watchlist:

| sedute coperte su 5 | simboli |
|---|---|
| 5 | 26 |
| 4 | 18 |
| 3 | 10 |
| 2 | 16 |
| 1 | 14 |
| 0 | 12 |

**84 simboli su 96 hanno prodotto almeno un articolo in una settimana**, ma solo 26 in
tutte le sedute. Il 40% a zero copertura *giornaliera* non e' quindi un insieme stabile
di ticker mai raggiunti: e' un problema di **ampiezza per seduta**, e l'insieme scoperto
cambia ogni giorno. La lettura «40% della watchlist non e' coperta» va corretta in «il
60% della watchlist e' coperto in una data seduta qualunque, ma quasi tutta la watchlist
e' raggiungibile».

I 12 simboli a zero righe su tutte e 5 le sedute: **BP, IBM, JNJ, MCD, PG, QCOM, RDDT,
ROKU, SAP, TMUS, VALE, WFC**. Fra questi ci sono mega-cap con un flusso di notizie
certamente non nullo, quindi l'assenza non e' assenza di notizia nel mondo.

Distribuzione delle righe `alpaca_benzinga` sulla stessa finestra, primi simboli: NVDA 42,
AMZN 34, GOOGL 29, META 18, MSFT 17, WMT 17, AAPL 16, TSLA 14. Il flusso e'
**concentrato sui mega-cap tech**. Osservazione di codice compatibile con quella
concentrazione, non ancora falsificata: `AlpacaNewsConnector.fetch()` chiede **una sola
pagina da 50 articoli**, `sort=desc`, senza `start` e **senza seguire
`next_page_token`** (`src/connectors/alpaca_news.py:64-81`); la finestra dei 50 piu'
recenti su 96 simboli e' dominata dai nomi ad alta frequenza. Contro-evidenza da
registrare: nella finestra si contano ~45 URL distinti al giorno su ~32 poll, cioe' ~1,4
articoli per poll, quindi il tetto di 50 **non risulta saturo**. Le due letture non sono
ancora separate dai dati disponibili.

## 4. Cosa e' stato lasciato fuori, e perche'

Tutto quanto segue e' **fuori dal perimetro del freeze #171** e resta all'operatore:

- **Accensione di GDELT DOC per-ticker (#159).** Schedulare un task in
  `celery_app.py` cambia il volume di news, quindi i segnali, quindi la serie osservata:
  e' una discontinuita' vera, come #185 e #236, e va pre-registrata nella carta.
  #159 e' inoltre `ready-for-human`.
- **Paginazione di `AlpacaNewsConnector.fetch()`.** Stesso profilo: cambierebbe il
  volume ingerito a meta' finestra. Va deciso insieme a #159 e alla capacita' del worker
  di sentiment (#149), non separatamente.
- **Alert live sulle posizioni cieche.** L'alert #161 sulle posizioni non proteggibili e'
  registrato nel «Registro delle deroghe» della carta; un alert nuovo richiede la stessa
  annotazione, e la carta e' modificabile solo dall'operatore.
- **Backfill del 2026-08-19 dopo l'accensione (punto 5 della issue).** Dipende dal primo
  punto.

## 5. Come si rilegge questa misura

Da schema dossier **2.6** in avanti, `docs/evidence/dossier/*.json` porta la chiave
`copertura_uscita` (righe per posizione + `aggregato`, replicato in
`aggregati.copertura_uscita`). I dossier precedenti non hanno la chiave: **assente
significa «non misurato», non «zero»**. La sessione alpha-miss la legge nella FASE 3b di
`scripts/daily_alpha_miss_analysis.sh` e la riporta in una sezione dedicata.
