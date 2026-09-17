# Audit delle fonti per i blind spot `NO_NEWS`

Data: 2026-09-08

Stato: ricerca e disegno di misura. Nessuna modifica a runtime, servizi, S4 o
configurazione live.

## Esito in breve

Il blind spot non si risolve accendendo una sola sorgente. Il corpus storico
contiene **59 casi `NO_NEWS` su 144 Alpha Miss (41,0%)**, distribuiti su 25
ticker; valgono **1.323,10 USD di opportunita' accessibile**, il 60,1% del
totale accessibile dei miss. Quasi meta' dei casi `NO_NEWS` e' nel settore
`tech` (28/59), ma la persistenza piu' netta attraversa emittenti esteri/ADR,
media, telecom, energia e materiali. Fonti: [casi arricchiti](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/alpha_miss_cases.jsonl),
[metriche](analysis/entry-funnel-v1/metrics.json),
[`config/trading.yaml`](../../../config/trading.yaml).

La conclusione operativa e' a due binari:

1. **SEC EDGAR e Twelve Data press releases** sono i primi test di copertura
   incrementale: possono aggiungere eventi issuer-specifici, con attribuzione
   deterministica o almeno richiesta per ticker.
2. **Alpaca WebSocket** resta il primo test di latenza, non una cura dimostrata
   del `NO_NEWS`: trasporta in tempo reale lo stesso feed news Alpaca/Benzinga
   che il REST gia' interroga. Se Benzinga non copre un emittente, lo stream non
   crea quella copertura.

Tiingo non va inserito nel ledger persistente con il piano Starter: i termini
attuali vietano esplicitamente di salvare il payload in database, file, log,
code o backup. Le fonti Investor Relations dirette sono promettenti, ma non
esiste oggi un connettore IR configurato e i diritti di automazione/retention
vanno verificati emittente per emittente; fino ad allora restano `UNKNOWN`.

## 1. Forma del buco osservato

### 1.1 I 59 casi storici

Aggregando senza fuzzy matching le 59 righe con `dossier_cause=NO_NEWS`:

| Settore | Casi | Ticker distinti | Opportunita' accessibile (USD) | Ticker |
|---|---:|---:|---:|---|
| tech | 28 | 12 | 624,89 | ADBE, BABA, BIDU, CRM, IBM, INFY, JD, NOW, ORCL, PLTR, SAP, SNOW |
| media | 10 | 2 | 189,30 | NFLX, RDDT |
| semis | 5 | 2 | 215,82 | ARM, QCOM |
| healthcare | 4 | 2 | 23,91 | AZN, NVO |
| consumer | 3 | 1 | 70,18 | F |
| financials | 3 | 2 | 56,24 | DB, HOOD |
| telecom | 3 | 2 | 74,14 | ERIC, TMUS |
| industrials | 2 | 1 | 65,19 | BA |
| energy | 1 | 1 | 3,42 | BP |

I ticker piu' ricorrenti sono **RDDT 9**, **SAP 6**, poi **ADBE, BIDU, CRM,
F, NOW, PLTR e QCOM con 3 casi ciascuno**. Questi conteggi descrivono soltanto
la disponibilita' di input nel sistema: un articolo trovato ex post non prova
che l'articolo abbia causato il movimento.

### 1.2 Il set persistentemente cieco

L'issue [#511](https://github.com/Jonbj/alembic/issues/511) misura, sulle otto
sedute congelate 24 agosto--3 settembre, 16 ticker senza una sola riga:

`ASML AZN BP ERIC GE IBM JD MMM PBR RDDT RIO SAP SBUX SONY T VALE`

La composizione e' informativa:

- 10/16 sono emittenti esteri o ADR/cross-listing: ASML, AZN, BP, ERIC, JD,
  PBR, RIO, SAP, SONY e VALE;
- i settori piu' rappresentati sono `tech` (4), `energy`, `industrials`,
  `materials` e `telecom` (2 ciascuno);
- RDDT e SAP sono anche i primi due ticker per ricorrenza nel corpus completo.

Esiste un'incongruenza da non propagare: #511 e la sintesi Week 36 affermano
che tutti i `NO_NEWS` della settimana appartengono ai 16 permanenti, ma la
tabella strutturata include **ARM**, che non e' nella lista dei 16. La matrice
seguente usa quindi due coorti separate: `PERSISTENT_16` e `NO_NEWS_25`, senza
forzare ARM nella prima. Fonte: [Week 36](../../WEEKLY_FINDINGS_2026-36.md),
[casi arricchiti](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/alpha_miss_cases.jsonl).

### 1.3 Tipi di catalizzatore: cosa sappiamo davvero

La causa economica della maggior parte dei 59 casi e' **`UNKNOWN`**. Questo e'
un limite del dato, non un campo da completare per intuizione. Gli elementi
difendibili sono:

- **evento societario gia' osservato ma non usato da S4**: NVO il 25 agosto
  aveva un `cash_dividend` nell'Alpaca Corporate Actions API;
- **contesto di mercato/settore**: alcune giornate sono rotazioni, per esempio
  QCOM nel rally semis/AI del 4 agosto e SAP nella rotazione fuori dal software
  del 1 settembre. Una fonte di sole press release non puo' coprire per
  costruzione tutto questo canale;
- **anomalia di microstruttura, non notizia**: ERIC il 26 agosto aveva volume
  pari a 2,25 volte l'ADV (surprise +1,25). Anche qui una nuova fonte news non
  e' necessariamente la risposta;
- per RDDT, ARM e la maggioranza degli altri casi l'evento causale resta
  `UNKNOWN`: trovare un articolo nello stesso giorno misura osservabilita', non
  causalita'.

Questa distinzione impedisce di sovrastimare il recall possibile: il test fonti
deve essere affiancato, non sostituito, dal backstop price/volume gia' discusso
in [#409](https://github.com/Jonbj/alembic/issues/409).

## 2. Capacita' verificate delle fonti

### Alpaca News REST e WebSocket (#455)

La documentazione ufficiale descrive il REST `/v1beta1/news` con filtri
`start`, `end`, lista comma-separated di `symbols`, paginazione e
`include_content`; e' quindi adatto a un replay storico controllato. Il payload
WebSocket espone `id`, `headline`, `summary`, `content`, `created_at`,
`updated_at`, `url`, `symbols` e `source`. `symbols` offre attribuzione nativa,
mentre `created_at` e `updated_at` consentono di separare tempo editoriale e
aggiornamento. Fonti: [Alpaca REST News](https://docs.alpaca.markets/us/reference/news-3),
[Alpaca real-time News](https://docs.alpaca.markets/us/docs/streaming-real-time-news).

Il workspace ha gia' corretto il REST per chiedere e preferire il contenuto
completo (#454 chiusa), mentre [#455](https://github.com/Jonbj/alembic/issues/455)
resta aperta. La qualifica ufficiale e' "real-time"; **non e' stato trovato un
SLA ufficiale che garantisca meno di un secondo**, quindi il valore `<1s`
presente nella documentazione locale va trattato come ipotesi da misurare.

Limite decisivo: REST e WebSocket sono due trasporti della stessa famiglia di
news Alpaca. Lo stream puo' ridurre `published_at -> first_seen_at` e gli scarti
`stale`, ma l'incremento di copertura sui 16 permanenti e' `UNKNOWN` e non va
assunto. I termini Alpaca consentono uso personale/non commerciale e vietano
redistribuzione o sfruttamento commerciale senza consenso; la retention
specifica del contenuto Benzinga non e' chiarita dalla pagina API, quindi per
un uso diverso dall'attuale account/internal use resta da verificare. Fonte:
[Alpaca Terms and Conditions](https://files.alpaca.markets/disclosures/library/TermsAndConditions.pdf).

### SEC EDGAR 8-K/6-K (#456)

EDGAR e' la fonte primaria piu' forte del set. Le API `data.sec.gov` non
richiedono chiavi, sono aggiornate in tempo reale durante la disseminazione e
il Submissions API conserva almeno un anno o 1.000 filing recenti, con file
aggiuntivi per la storia precedente. Il JSON contiene CIK, ticker/exchange e
storia delle submission; 8-K e 6-K sono inclusi. La SEC dichiara un tipico
ritardo di aggiornamento del Submissions API inferiore a un secondo, non una
garanzia. Fonti: [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces),
[SEC Developer Resources](https://www.sec.gov/about/developer-resources).

Questo e' particolarmente pertinente al cluster ADR/esteri: il 6-K e' il
canale SEC degli emittenti privati esteri registrati. L'attribuzione e'
deterministica via CIK->ticker e il timestamp di acceptance e' conservabile.
Non copre pero' rating degli analisti, rumor, flussi tematici o movimenti senza
filing.

Il mapping rotto e' stato corretto e #456 e' chiusa; il task resta flag-off in
attesa della prova shadow. L'accesso ai filing pubblici e' gratuito, ma gli
script devono usare un User-Agent dichiarato e restare sotto la linea guida SEC
di **10 richieste/secondo complessive**. Nessun problema di redistribuzione del
feed e' emerso dalle pagine pubbliche consultate; eventuale redistribuzione di
documenti completi non e' necessaria per questa PoC.

### Twelve Data `press_releases` (#458)

La documentazione ufficiale attuale descrive comunicati societari e
annunci corporate **globali e real-time**, filtrabili per simbolo, exchange,
`start_date`, `end_date` e lingua. Ogni record ha `id`, `datetime`, `title`,
`body` HTML e `language`; non espone `url`, `source` o un ticker restituito.
L'attribuzione e' dunque il **ticker richiesto**, non una conferma indipendente
nel payload, e il dedup deve usare `id`. Il costo dichiarato e' un credito per
richiesta e l'endpoint e' disponibile dal piano Basic individuale. Fonte:
[Twelve Data API, Press releases](https://twelvedata.com/docs/introduction/overview#press-releases),
[annuncio ufficiale del prodotto](https://twelvedata.com/news/march-2026-updates).

Il supporto ufficiale classifica i piani Individual come personali/interni e
non commerciali, senza redistribuzione o display commerciale; un passaggio a
produzione commerciale richiede un piano Business e, secondo il mercato,
licenze aggiuntive. Fonte: [Twelve Data, commercial and personal usage](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage).

Il workspace contiene gia' connettore e script PoC e la chiave e' presente,
ma #458 e' ancora aperta e manca il campione forward di cinque sedute. La
coorte predefinita corrente non e' adatta al problema: va sostituita, per il
test, con `PERSISTENT_16` e `NO_NEWS_25`. La profondita' storica massima e la
retention contrattuale del body non sono specificate nelle fonti pubbliche
consultate: **`UNKNOWN`**, da confermare prima di promuovere il payload fuori
dalla tabella shadow.

### Tiingo News (#459)

L'API ufficiale accetta piu' ticker e restituisce `id`, `title`, `url`,
`description`, `publishedDate`, `crawlDate`, `source`, `tickers` e `tags`.
`publishedDate` puo' provenire dall'editore oppure, se assente, dal crawler;
`crawlDate` e' sempre assegnato da Tiingo. Questa coppia e' utile per misurare
discovery latency, e il campo `tickers` rende osservabile l'attribuzione, pur
essendo prodotto da un algoritmo proprietario. Tiingo dichiara 8.000--12.000
articoli aggiunti al giorno; il volume non e' prova di recall sui ticker ciechi.
Fonte: [Tiingo Financial News API](https://www.tiingo.com/documentation/news).

Il vincolo contrattuale domina la valutazione. I termini aggiornati al 5 agosto
2026 vietano ai piani Starter/trial di persistere Tiingo Data in database,
file, log, code, archivi e backup; consentono solo elaborazione transiente in
memoria e prodotti derivati non ricostruibili. Anche gli esempi di derivati non
sono un safe harbor. L'uso API e' interno; un'organizzazione deve usare un piano
commerciale e la redistribuzione richiede permesso. Fonte:
[Tiingo Terms of Use, §§1.6 e 7.3](https://api.tiingo.com/tos/).

Non risulta una `TIINGO_API_KEY` configurata. Quindi schema e copertura reale
sulle due coorti restano `UNKNOWN`; #459 deve rimanere una PoC solo in memoria,
senza titoli, URL, ID o payload persistiti. Questo la rende meno riproducibile e
meno adatta del test Twelve/SEC al ledger causale corrente.

### Alpaca Corporate Actions e calendario FMP

L'API Alpaca `/v1/corporate-actions` filtra per simbolo e periodo e copre split,
dividendi, merger, spin-off, cambi di nome/simbolo, rights distribution,
redemption e altri eventi. Dal giugno 2026 supporta anche corporate action
globali tramite filtro di regione. Esiste inoltre uno stream SSE che puo'
replayare eventi storici con `since`/`since_id`. Fonti:
[Alpaca Corporate Actions](https://docs.alpaca.markets/us/reference/corporateactions-1),
[global corporate actions](https://docs.alpaca.markets/us/changelog/2026-06-03-market-data-9dddd18),
[Corporate Actions SSE](https://docs.alpaca.markets/us/reference/subscribetocorporateactionseventssse).

Non e' una fonte news: non porta il testo causale necessario al sentiment. E'
pero' una fonte strutturata di contesto che avrebbe reso esplicito NVO. La
stessa documentazione avverte che non esiste una garanzia sul tempo di creazione
e che ricezione/processamento possono essere ritardati: non va usata come
sostituto di una press release tempestiva.

Il calendario FMP e' gia' interrogato dal dossier, non da S4. In Week 36 la
chiave esisteva ma non veniva esportata dal cron, quindi quattro sedute sono
`UNKNOWN`; quando interrogato, il feed era comunque sottile sulla watchlist.
[#507](https://github.com/Jonbj/alembic/issues/507) deve ripristinare la misura,
ma un calendario earnings non copre i restanti catalizzatori e non e' una nuova
fonte news.

### Fonti Investor Relations dirette

Non esiste oggi alcun feed IR per emittente in `config/connectors.yaml`; gli RSS
generici Reuters/CNBC sono spenti e il codice stesso ne subordina un eventuale
revival a fonti IR ufficiali. La disponibilita' first-party e' reale almeno per
alcuni ticker importanti: Reddit pubblica un archivio News Releases e Novo
Nordisk pubblica company announcements con timestamp e PDF; il comunicato NVO
del 4 agosto mostra anche che il ticker ADR e' `NVO`. Fonti:
[Reddit Investor Relations](https://investor.redditinc.com/news-events/news-releases/),
[Novo Nordisk announcements](https://www.novonordisk.com/news-and-media/news-and-ir-materials.html),
[comunicato NVO del 4 agosto 2026](https://www.novonordisk.com/news-and-media/news-and-ir-materials/news-details.html?id=916589).

Un archivio web non equivale pero' a un feed lecitamente automatizzabile.
Formato machine-readable, timestamp di discovery, termini di scraping,
retention e stabilita' URL sono `UNKNOWN` per ciascun emittente. La strada
corretta e' un manifest curato per ticker che accetti soltanto RSS/API/email
ufficiali con termini verificati, non uno scraper generico.

## 3. Matrice prioritaria e testabile

| Priorita' | Fonte / test | Blind spot che puo' coprire | Attribuzione e tempi | Profondita' storica | Vincolo/licenza | Criterio di promozione |
|---:|---|---|---|---|---|---|
| **P0** | **SEC 8-K/6-K shadow replay + forward** | Filing materiali US e ADR/foreign private issuers; forte fit sui 10 esteri/cross-listed del `PERSISTENT_16` | CIK->ticker; filing/acceptance time | >=1 anno o 1.000 filing nel JSON, storia ulteriore referenziata | Pubblico/gratuito; User-Agent e <=10 req/s | Su `PERSISTENT_16` e `NO_NEWS_25`: recall incrementale, precisione ticker 100%, p50/p95 acceptance->fetch, overlap con Alpaca; nessuna scrittura live |
| **P0** | **Twelve Data PR shadow** | Earnings/guidance, partnership, management e altri annunci issuer-specifici globali | ticker richiesto; `id` e `datetime`; nessun ticker/url/source restituito | Range data supportato; limite massimo `UNKNOWN` | Individual solo interno/non commerciale; retention body `UNKNOWN` | Cambiare la coorte PoC alle 41 unioni delle due coorti; >=5 sedute, replay dei 59 casi; misurare coverage incrementale, latency, `ticker_valid`, body utile e crediti |
| **P1-latency** | **Alpaca REST replay + WebSocket forward (#455)** | Stesso universo Benzinga corrente; puo' recuperare `stale`, non e' dimostrato che recuperi ticker mai coperti | `symbols`, source, created/updated/fetch | REST ha start/end e paginazione; limite massimo `UNKNOWN` | personale/non commerciale; redistribuzione vietata; retention Benzinga da confermare | Prima: REST replay sui 59 casi. Poi 5 sedute REST-vs-WS con item-id: delta coverage deve essere separato dal delta latency; nessuna promessa `<1s` |
| **P1-context** | **Alpaca Corporate Actions SSE/REST** | Split, dividendi, merger, spin-off e azioni globali; caso-prova NVO | symbol + date; creation latency non garantita | replay SSE/periodo REST, limite massimo `UNKNOWN` | termini Alpaca; uso interno | `event_observed_before_cycle`, `event_type`, delay e overlap; entra come contesto, non come sentiment news |
| **P1-pilot** | **IR first-party manifest** | Comunicati che aggregatori non raccolgono, soprattutto RDDT/SAP/ASML/NVO e ADR | issuer deterministico; timestamp solo se fornito | per sito: `UNKNOWN` | automazione/retention per emittente `UNKNOWN` | Pilot 4 ticker; solo endpoint ufficiali machine-readable con termini verificati; zero inferenza quando manca timestamp/feed |
| **P2/HOLD** | **Tiingo in-memory (#459)** | Ampio discovery e tagging multi-ticker; possibile copertura di analisti/blog/tema | proprietary `tickers`; published/crawl date | accesso storico del piano corrente `UNKNOWN` | Starter: nessuna persistenza del payload; organizzazione=Commercial | Solo dopo chiave e decisione licenza; conservare esclusivamente aggregati non ricostruibili; nessun payload nel ledger |
| **supporto** | **FMP earnings calendar (#507)** | Solo eventi earnings programmati | ticker/data/time | `UNKNOWN` per il piano effettivo | contratto/piano effettivo `UNKNOWN` | Correggere l'export della chiave e ristabilire completezza; non contarlo come fonte news |

## 4. Protocollo minimo del confronto

Il primo lotto non deve partire dalla watchlist intera, ma da due coorti
versionate:

- `PERSISTENT_16`: i 16 ticker a zero su tutte le otto sedute;
- `NO_NEWS_25`: i 25 ticker presenti nei 59 casi storici;
- unione: **41 ticker nominali prima del dedup**, con eventuali sovrapposizioni
  mantenute nel manifest e non nel conteggio delle richieste.

Per ciascuna fonte e `(session_date, ticker)` vanno congelati:

- esito `FOUND / ZERO_RESULTS / PROVIDER_ERROR / LICENSE_BLOCKED / UNKNOWN`;
- identificatore sorgente, ticker richiesto e ticker restituiti, metodo di
  attribuzione;
- `published_at`, `provider_seen_at` quando esiste, `fetched_at` e relative
  latenze;
- classe manuale `issuer_specific / sector_readthrough / macro / irrelevant`;
- overlap per `content_hash` o ID stabile, senza inventare equivalenze;
- per Tiingo, soltanto aggregati giornalieri non ricostruibili.

Le metriche di decisione sono: copertura incrementale sui 59 casi, quota dei 16
permanenti con almeno un input timely issuer-specific, precisione ticker,
p50/p95 di discovery e processing, overlap con Alpaca, costo/richieste e quota
di errori. Un match dello stesso giorno resta "candidate coverage" finche' una
revisione non dimostra la relazione col mover.

## Raccomandazione

Eseguire in parallelo due prove shadow, senza toccare S4 live:

1. **SEC EDGAR** sui 16 permanenti e sui 25 ticker storici, perche' e'
   first-party, gratuita, riproducibile e il codice di mapping e' gia' corretto;
2. **Twelve Data press releases** sulla stessa coorte, per misurare la parte di
   annunci globali che SEC non vede e che sembra coerente con il bias ADR.

Usare il replay Alpaca REST come controllo e attivare #455 come esperimento
separato di latenza. Non attribuire allo stream un incremento di copertura prima
dei dati. Tenere Tiingo in `HOLD` finche' chiave, piano e retention non sono
risolti. In parallelo, costruire solo il manifest (non ancora il connettore) di
quattro fonti IR first-party ad alto valore: RDDT, SAP, ASML e NVO.

Questa sequenza distingue tre problemi che oggi sono mescolati sotto
`NO_NEWS`: **fonte assente**, **fonte presente ma lenta**, e **movimento senza
catalizzatore news osservabile**. Solo il primo e' risolvibile aggiungendo una
fonte.
