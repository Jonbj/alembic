# Audit: “Should You Buy, Hold, or Sell a Stock? Build an AI Stock Analyzer with Python”

**Data:** 2026-09-14  
**Articolo esaminato:** Kevin Meneses González, “Should You Buy, Hold, or Sell a Stock? Build an AI Stock Analyzer with Python”, 2026-08-15  
**Perimetro:** schema EODHD, eseguibilità e matematica, comparabilità, point-in-time (PIT), ruolo dell'LLM e utilità per Alembic. L'articolo è l'oggetto dell'audit, non una fonte probatoria.

## Verdetto

**Non adottare il codice, l'overall score o le etichette buy/hold/sell in Alembic.** L'idea architetturale più utile è corretta: calcoli deterministici prima, LLM solo dopo per spiegare. L'implementazione mostrata, però, non è end-to-end e produce errori o punteggi economicamente invertiti su casi comuni.

I problemi decisivi sono:

- il codice pubblicato non costruisce `growth` e non mostra il calcolo dell'overall score: non è un'applicazione eseguibile completa;
- promette di escludere e ripesare i dati mancanti, ma usa pesi fissi e lascia `None` nelle somme; altrove converte il dato mancante in `0` o addirittura in `1`;
- FCF negativo, P/E negativo, equity negativa o EBITDA negativo possono ricevere il punteggio migliore;
- cinque multipli di valutazione e vari riusi di FCF, ricavi, utili e prezzo contano più volte quasi la stessa informazione;
- floor, ceiling e pesi sono dichiarazioni soggettive non calibrate su un target, un campione o un benchmark; il numero 0–100 non è una probabilità e non dimostra capacità predittiva;
- lo stesso schema non è confrontabile fra banche, assicurazioni, REIT, utility e società industriali/tecnologiche;
- il payload EODHD corrente contiene insieme snapshot, stime future e bilanci storici. Il codice ignora `filing_date`, vintage/revisioni e timestamp di osservazione, quindi non è valido per backtest PIT;
- dire al modello che gli score sono “ground truth” gli impedisce di segnalare proprio i difetti e la stale/missing data che dovrebbe rendere visibili.

Per Alembic non emerge una nuova issue: il requisito PIT e il validation harness sono già in [#84](https://github.com/Jonbj/alembic/issues/84); l'eventuale valutazione EODHD News è separata in [#579](https://github.com/Jonbj/alembic/issues/579). Il solo uso ragionevole dell'articolo è come checklist negativa per un futuro dashboard di ricerca umana, non come nuova fonte o segnale.

## 1. Schema e unità EODHD

Il fetch base è plausibile: token da environment, `timeout=30`, `raise_for_status()` e JSON. Usa però l'endpoint legacy `/api/fundamentals/`; EODHD raccomanda `/api/v1.1/fundamentals/`. La v1.1 corregge anche una collisione che poteva eliminare silenziosamente il Q4 dall'Earnings Trend. La stessa documentazione avverte che non tutte le società hanno tutti i campi e che le sezioni cambiano per tipo di strumento ([EODHD Fundamentals API](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds)).

Il controllo live del payload demo `AAPL.US` il 2026-09-14 conferma:

| Campo | Valore osservato | Semantica rilevante |
|---|---:|---|
| `Highlights.MarketCapitalization` | `4,849,207,869,440` | valore assoluto; esiste anche `MarketCapitalizationMln` |
| `ReturnOnEquityTTM` | `1.4875` | rapporto decimale, cioè 148,75%, non 1,4875% |
| `OperatingMarginTTM` | `0.3262` | rapporto decimale |
| `QuarterlyRevenueGrowthYOY` | `0.164` | rapporto decimale, cioè 16,4% |
| `Financials...freeCashFlow` | stringa `"98767000000.00"` | valore assoluto, valuta del record `USD` |
| `Earnings.History...surprisePercent` | `7.4468` | punti percentuali, non rapporto `0.074468` |
| bilancio FY 2025 | `date=2025-09-30`, `filing_date=2025-10-31` | periodo economico distinto dalla data di disponibilità |

I nomi principali usati dall'articolo — `Financials.*.yearly`, `freeCashFlow`, `totalRevenue`, `netIncome`, `AnalystRatings`, `Technicals`, `ForwardPE` — esistono per AAPL. Questo non prova universalità: EODHD dichiara esplicitamente campi vuoti e strutture diverse per ETF, fondi e indici. Il codice deve rifiutare tipi diversi da `Common Stock` oppure applicare uno schema dedicato.

Per società non USA va inoltre verificata la valuta record per record. `General.CurrencyCode` è la valuta della quotazione; ogni statement ha `currency_symbol`. Dividere market cap e FCF senza un'asserzione di valuta/unità è sicuro nel caso demo USD/USD, non in generale.

## 2. Audit di eseguibilità e matematica

### Incompletezza

- `score_growth(f, growth)` riceve un dizionario `growth`, ma l'articolo non pubblica la funzione che calcola CAGR, crescita YoY e consistenza.
- Non viene mostrata una funzione che applica i pesi 25/20/20/20/15 e genera il report finale passato a Claude.
- Non ci sono validazione dello schema, retry/backoff per 429/5xx, cache, provenance, test né gestione della risposta non JSON.

### Missing, zero e `NaN`

| Codice/pattern | Esito |
|---|---|
| `h.get(field) or 0` | confonde campo assente, `null` e zero economico reale |
| `current_liabilities = ... or 1` | trasforma dato mancante o passività realmente zero in `1`, creando ratio enormi e score ottimistici |
| `sum(x * w for ...)` con `normalize(None, ...)` | `TypeError`: la promessa di escludere/ripesare i missing non è implementata |
| `sum(...)/len(net_income)` | `ZeroDivisionError` quando la serie è vuota |
| `fcf[-1]`, `revenue[-1]` | `IndexError` se il campo non è disponibile |
| `fcf / revenue` | divisione per zero e mancato allineamento per data fra le due serie |
| `price_position=(price-low)/(high-low)` | divisione per zero se high=low; `KeyError`/`TypeError` sui missing |
| `float(...)` | accetta `nan`/`inf`; `min`/`max` non costituiscono una policy robusta per valori non finiti |

Serve un solo contratto: parser tipizzato che distingua `MISSING`, `NOT_APPLICABLE`, `ZERO`, `NEGATIVE` e `NON_FINITE`; componenti validi filtrati esplicitamente; pesi rinormalizzati solo quando la policy lo consente; soglia minima di coverage; reason code se lo score non è calcolabile.

### Rapporti con segno economicamente errato

- `P/FCF = market_cap / negative_fcf` produce un multiplo negativo; l'inversione `100 - normalize(...)` gli assegna **100**, cioè la valutazione migliore.
- P/E o PEG negativi subiscono lo stesso errore: non sono “più economici” di un multiplo positivo basso; sono in genere non significativi per questo confronto.
- Debt/equity con equity negativa diventa negativo e l'inversione può premiarlo come leva minima.
- Net debt/EBITDA con EBITDA negativo non ha l'ordinamento economico assunto dalla funzione.
- Se il debito è zero, impostare sempre `fcf_to_debt=1.0` premia anche un FCF negativo.

Questi casi devono essere `NOT_MEANINGFUL` o trattati da regole dedicate, mai mandati nella stessa trasformazione monotona.

### Floor, ceiling, pesi e doppio conteggio

I tagli lineari sono plausibili come preferenze esplicite di un utente, ma non come “misura oggettiva”: non sono stimati, preregistrati o validati rispetto a rendimento/rischio futuro. Clipping e trasformazioni arbitrarie rendono 64 e 71 numeri ordinali fragili, non probabilità di buy/hold/sell.

Il doppio conteggio è sostanziale:

- FCF entra in margin/consistency, growth, FCF/debt e P/FCF;
- ricavi entrano in margin, growth/CAGR/consistency, P/S e di nuovo nel momentum;
- utili/profittabilità entrano in ROE/margini, EPS growth, surprise, P/E, PEG ed EV/EBITDA;
- il prezzo entra in tutti i multipli e nelle misure di momentum.

Un composito difendibile richiede target, popolazione, orizzonte, loss function, trattamento delle correlazioni, baseline e vera validazione OOS. Come contrasto, il F-score originale di Piotroski è una regola precisamente definita e testata **solo** nell'universo high book-to-market; il paper non autorizza un composito universale per “any stock” ([Piotroski, 2000](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf)).

## 3. Comparabilità cross-sector

Applicare soglie globali è materialmente errato:

- per banche e assicurazioni, debito e liquidità sono parte del modello operativo; current ratio, net debt/EBITDA e FCF industriale non sono comparabili;
- per REIT, net income/PE non sostituiscono FFO/AFFO e la leva va letta sul modello immobiliare;
- utility e telecom hanno struttura del capitale diversa da software e servizi asset-light;
- margini e reinvestimento variano strutturalmente per settore e fase del ciclo;
- accounting standard, valuta, fiscal year e ADR/listing estere richiedono normalizzazione.

Minimo accettabile: peer group PIT per settore/industry e regione, metriche applicabili per business model, winsorization cross-sectional preregistrata e rank/percentili costruiti solo sul set contemporaneamente disponibile. La frase dell'articolo secondo cui cambierebbe solo il ticker, non la logica, va respinta.

## 4. Look-ahead, stime e prezzi adjusted

### Bilanci e fondamentali

Ordinare gli statement per fiscal-period key non basta. Ogni entry EODHD espone `date` e `filing_date`; una decisione storica può usare il record solo dopo il filing (più un eventuale lag operativo). La risposta corrente non documenta i vintage di ogni successiva rettifica/restatement. `General.UpdatedAt` è una data dell'oggetto, non un timestamp `available_at` field-level.

Il parametro EODHD `historical=1` documentato nella pagina Fundamentals riguarda **solo membership storica degli indici**, non versioni storiche di `Highlights`, `Valuation`, `Technicals`, `AnalystRatings` o delle stime. Quindi il payload scaricato oggi non è automaticamente un dataset PIT per un backtest.

### Analyst estimates/ratings

`ForwardPE`, `PEGRatio`, Earnings Trend e `AnalystRatings` sono forward-looking/current snapshot. Il payload demo include già un periodo futuro (`2026-09-30`, `reportDate=2026-10-29`) con `epsEstimate` ma `epsActual=null`. Il filtro sugli actual evita di contarlo nelle surprise, ma non risolve la storia delle revisioni. Senza observation timestamp e vintage, usare oggi quelle sezioni a date passate è look-ahead.

La percentuale “positive ratings / total” perde inoltre intensità, target, dispersione, età e soprattutto variazione della raccomandazione; non è una probabilità di rendimento. Se mantenuta in un dashboard live deve mostrare data, coverage e provenienza, non entrare automaticamente nel segnale.

### Adjusted versus unadjusted

La pagina Fundamentals elenca 52-week high/low e MA ma non specifica nella loro descrizione la base di adjustment. L'EOD API, invece, dichiara chiaramente: OHLC raw, `adjusted_close` corretto per split e dividendi e volume split-adjusted ([EODHD EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)). Non è quindi lecito mescolare `Technicals` e una serie prezzi Alembic senza contratto e test su split/dividendi. Per momentum di prezzo va scelta una serie coerente; per livelli eseguibili non si deve usare un total-return adjusted price come se fosse il prezzo negoziabile.

## 5. Ruolo corretto e sicurezza dell'LLM

La separazione calcolo/spiegazione è la parte migliore dell'articolo. L'LLM non dovrebbe calcolare ratio, correggere dati o prendere decisioni. Dovrebbe trasformare un oggetto già validato in un riassunto che cita i singoli campi.

Il prompt mostrato ha comunque quattro difetti:

1. `str(report)` non è un contratto dati né un output schema; usare JSON validato, allowlist di campi e structured output.
2. “Use scores as ground truth” è scorretto: gli score sono output fallibili. Il modello deve poter dire `INSUFFICIENT_DATA`, `NOT_COMPARABLE` o “stale”.
3. La prosa d'esempio attribuisce causalità (“CapEx caused the FCF dip”, “the market has not priced...”) che i soli score non dimostrano. Ogni frase deve essere riconducibile a un campo o marcata come ipotesi.
4. Mancano provider, endpoint/schema version, ticker/identifier stabile, instrument type, currency/unit, statement `date`/`filing_date`, fetch/as-of timestamp, hash del payload, missing flags e versione di formula/configurazione.

Nel report numerico mostrato il rischio di prompt injection è limitato; diventa concreto appena si aggiungono `Description`, news o altro testo di terzi. Anthropic raccomanda di distinguere contenuto non fidato dalle istruzioni, dichiararne fonte/natura, usare structured outputs, privilegio minimo e test/red-team contro indirect injection ([Anthropic, prompt-injection guidance](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks)). Un LLM narrativo non deve avere tool di trading o credenziali broker.

## 6. Mapping su Alembic e duplicati

### Cosa esiste già

- [#84](https://github.com/Jonbj/alembic/issues/84) è il gate pertinente: universo US common-stock PIT, `available_at`, delisting/corporate actions, holdout sigillato, trial registry, costi e validazione OOS. EODHD era già risultato non sufficiente, da solo, per quel contratto storico 1998–2025.
- [#579](https://github.com/Jonbj/alembic/issues/579) valuta EODHD esclusivamente come **news feed** sui ticker ciechi; non qualifica Fundamentals, AnalystRatings o Technicals.
- [#571](https://github.com/Jonbj/alembic/issues/571) riguarda provenance/PIT di linkage e novelty delle news; conferma il principio Alembic che un output LLM measurement-only non è prova deterministica, ma non è un ticket per fondamentali.
- L'audit vendor esistente [`2026-09-14-yfinance-eodhd-migration-audit.md`](2026-09-14-yfinance-eodhd-migration-audit.md) separa già EODHD price/fundamentals/news e documenta adjustment e insufficienza PIT.

La ricerca titoli sulle issue open/closed non ha trovato un analyzer fondamentale o score composito equivalente. Questo non giustifica crearne uno: manca prima una decisione prodotto e, soprattutto, una fonte PIT qualificata.

### Decisione raccomandata

1. **Non aprire issue e non accodare una nuova campagna.** L'articolo non aggiunge evidenza predittiva né risolve un gap prioritario.
2. **Non inserire l'overall score nel ranker/gate S1, S3 o S4.** Creerebbe un nuovo segnale non preregistrato e correlato senza validation harness.
3. Se in futuro serve un analyst dashboard, farlo read-only e human-facing: componenti atomici con date/provenance/missingness, peer comparison, nessun BUY/SELL, nessun accesso broker.
4. Un eventuale uso quantitativo deve passare prima da #84: dataset PIT qualificato, formula preregistrata, neutralizzazione/peer groups, ablation dei componenti, benchmark semplici, walk-forward/holdout, costi e DSR/trial count.
5. Conservare la lezione architetturale: **dati e matematica deterministici; LLM solo narratore vincolato e citabile**. Non conservare soglie, pesi o codice dell'articolo.

## Fonti primarie e ufficiali essenziali

1. EODHD, [Fundamental Data API: schema, v1.1, campi mancanti, filing dates e index-history-only](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds).
2. EODHD, [payload demo ufficiale AAPL.US](https://eodhd.com/api/v1.1/fundamentals/AAPL.US?api_token=demo&fmt=json), osservato 2026-09-14.
3. EODHD, [EOD price adjustment semantics](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes).
4. Joseph D. Piotroski, [“Value Investing: The Use of Historical Financial Statement Information to Separate Winners from Losers”](https://www.ivey.uwo.ca/media/3775523/value_investing_the_use_of_historical_financial_statement_information.pdf), *Journal of Accounting Research* 38 (2000), 1–41.
5. Anthropic, [Mitigate jailbreaks and prompt injections](https://platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks).
