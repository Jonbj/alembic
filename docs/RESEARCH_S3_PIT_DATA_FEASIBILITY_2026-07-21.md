# S3 PIT data feasibility — 2026-07-21

## Decisione

**NO-GO infrastrutturale provvisorio; nessun acquisto autorizzato.** Alla data della verifica non è stato possibile qualificare, usando documentazione pubblica ufficiale, un singolo dataset che soddisfi contemporaneamente tutti i requisiti della issue #84 e il limite iniziale di EUR 1.000 senza rinnovo automatico.

La sola **shortlist commerciale condizionata** è:

1. **CRSP US Stock Database**, benchmark funzionale: la documentazione pubblica copre quasi tutta la semantica richiesta, ma prezzo, termine non rinnovabile e diritto di conservare uno snapshot locale non sono pubblici e CRSP dichiara di servire istituzioni, agenzie e investment practitioners, non individual investors.
2. **Nasdaq Data Link / Sharadar**, candidato API: potrebbe ridurre la complessità di ingestione, ma le pagine correnti non provano copertura completa dal 1998, prezzo entro budget, market cap giornaliero causalmente PIT, anagrafica storica sufficiente o rendimento economico di delisting. I termini Nasdaq prevedono inoltre il rinnovo annuale di default salvo disdetta con almeno 90 giorni di anticipo.

Questa non è una raccomandazione d'acquisto. È una raccomandazione a richiedere due risposte commerciali scritte e, solo se una risposta chiude tutti i punti aperti entro il cap, a rieseguire il gate dati prima di scrivere il POC.

## Ambito e metodo

La verifica usa soltanto fonti primarie del vendor o dell'ente proprietario, consultate il **21 luglio 2026**. Non sono stati aperti trial, creati account, contattati vendor o acquistati dati. `PASS` significa che una fonte ufficiale pubblica documenta il requisito; `FAIL` indica un'incompatibilità esplicita; `COND` indica che serve prova su sample/trial o conferma contrattuale.

Requisiti hard congelati dalla #84:

- azioni ordinarie con primary listing USA, con esclusione PIT di ETF, ADR, preferred, fondi e OTC;
- daily 1998-2025, open affidabile oppure esecuzione al close successivo, volume e ADV;
- market cap PIT per applicare ogni mese la soglia USD 2 miliardi;
- membership/eligibility PIT e almeno 200 nomi eleggibili;
- corporate actions e delisting con ultimo valore/rendimento economico, non scomparsa retroattiva;
- uso locale riproducibile con release/provenance e checksum calcolabile;
- spesa iniziale/licenza non superiore a EUR 1.000, senza rinnovo automatico.

Per confrontare listini in USD si usa il fixing ECB del 21 luglio 2026, **EUR 1 = USD 1,1418**; quindi EUR 1.000 corrispondono a USD 1.141,80 prima di IVA e commissioni. Il cambio ECB è informativo e non garantisce il cambio applicato dal merchant ([ECB, reference rates 2026-07-21](https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html)).

## Matrice sintetica

| Candidato | 1998-2025 daily / execution | Volume / ADV | Cap PIT | Type + listing PIT | Breadth ≥200 | Corporate actions | Delisting economico | Locale / provenance | Budget + no auto-renew | Esito |
|---|---|---|---|---|---|---|---|---|---|---|
| CRSP US Stock | PASS, next-close | PASS | PASS | PASS | **COND**: da provare sull'estratto | PASS | PASS/COND per missing flag | PASS/COND licenza | **COND**: prezzo non pubblico | **Shortlist condizionata** |
| Nasdaq/Sharadar bundle | **COND**: fonte corrente dice “20 years” | PASS probabile, schema gated | COND | COND | **COND**: non verificabile | COND | COND | PASS API / COND retention | **FAIL/COND**: prezzo gated, auto-renew di default | **Shortlist condizionata** |
| Norgate US Platinum | PASS, open/close | PASS | **FAIL**: fundamentals solo correnti | PASS per major listing; type storico incompleto | **COND**: non verificabile con i filtri richiesti | PASS | **FAIL/COND**: nessun payout/delist return documentato | **FAIL** per Linux/retention | PASS prezzo/no renewal | Non qualificato |
| EODHD All-In-One | PASS OHLCV | PASS | **FAIL**: equity cap dal 2021-07-09 | FAIL per universo storico completo | **FAIL**: cap PIT insufficiente | PASS splits/dividends | **FAIL**: pre-2018 solo EOD, nessun delist return | **FAIL**: delete dopo scadenza | Prezzo sotto cap, rinnovo da disattivare | Non qualificato |
| Kibot All Stocks | PASS OHLCV 1998+ | PASS | **FAIL** | **FAIL** | **FAIL**: campi di filtro assenti | PASS aggiustamenti | **FAIL/COND**: ultimo bar, non payout | PASS CSV/archivio | COND: USD 990 può superare cap con IVA | Non qualificato |
| QuantConnect + AlgoSeek local | PASS 1998+ | PASS | PASS con Morningstar | PASS/COND | **COND**: da provare sul bundle | PASS | COND: evento + liquidazione, non payout documentato | PASS ma stack LEAN | **FAIL**: almeno USD 2.736/anno prima dei fundamentals | Non qualificato |

`PASS/COND` non equivale a qualificazione: basta un solo `FAIL` o `COND` irrisolto su un requisito hard per impedire il GO.

## 1. CRSP US Stock Database — benchmark di completezza

### Copertura funzionale

CRSP dichiara daily e monthly market data e corporate actions per oltre 32.000 titoli USA attivi e inattivi ([CRSP, About Us](https://www.crsp.org/about-us/)). Il formato CIZ documenta:

- `DlyPrc`, `DlyRet`, `DlyRetx`, `DlyVol` e `DlyCap`; `DlyCap` è closing price o bid/ask medio moltiplicato per shares outstanding ([CRSP US Stock Database Guide 2.0](https://www.crsp.org/wp-content/uploads/guides/CRSP_US_Stock_%26_Indexes_Database_Guide_Flat_File_Format_2.0.pdf));
- anagrafica con intervalli `SecInfoStartDt`/`SecInfoEndDt`, `SecurityType`, `SecuritySubType`, `ShareType`, `PrimaryExch`, `ExchangeTier` e trading status; i codici distinguono common, ETF, ADR e altre classi ([CRSP guide e flag dictionary](https://www.crsp.org/wp-content/uploads/FlagType_TOC.html));
- permanent identifier `PERMNO`, pensato per seguire una security attraverso cambi di ticker e ristrutturazioni ([CRSP Research Data Products](https://www.crsp.org/research/));
- un vero `Delisting Return`, calcolato confrontando il valore post-delisting — prezzo su altro mercato o distribuzioni agli azionisti, anche zero se worthless — con l'ultimo prezzo di negoziazione. CRSP segnala esplicitamente i casi in cui le informazioni sono insufficienti e il valore resta missing ([CRSP calculations guide](https://www.crsp.org/crsp_pdf/crsp-us-stock-indexes-databases-calculations-index-methodologies-guide-flat-file-format-2-0/)).

CRSP non documenta un open giornaliero nel subset principale, ma la #84 consente l'esecuzione al **close della seduta successiva** quando l'open non è affidabile. `DlyPrc` e i relativi flag consentono di distinguere trade close e bid/ask average, quindi questo seam è compatibile. Il numero di securities complessivo rende plausibile la breadth minima, ma la condizione “almeno 200 dopo price/cap/ADV/history filter a ogni rebalance” deve comunque essere provata su estratto reale: resta `COND`, non può essere dedotta da un conteggio totale.

CRSP consegna zip locali via MOVEit e pubblica release versionate in ASCII/SAS/R; la release annuale gennaio 2026 elenca, per esempio, i pacchetti daily dal 1925/1962 e i relativi nomi/versioni ([CRSP January 2026 release notes](https://www.crsp.org/crsp_pdf/crsp-us-stock-database-release-notes-2025-12-annual/)). Alembic potrebbe conservare il nome release e calcolare SHA-256 sui file ricevuti. Va però verificato contrattualmente il diritto di trattenere lo snapshot e di usarlo nel repository privato.

### Blocco commerciale

CRSP non pubblica il prezzo. La pagina di richiesta precisa che i database sono destinati a licensee presso istituzioni accademiche, agenzie governative e investment practitioners, e indirizza gli individual investors altrove ([CRSP Subscription Information](https://www.crsp.org/subscription-information/)). WRDS richiede un proprio abbonamento e precisa che CRSP richiede comunque una licenza vendor separata ([WRDS, What is WRDS?](https://wrds-www.wharton.upenn.edu/pages/about/what-wrds/)).

**Verdetto:** migliore benchmark tecnico, ma non qualificato entro EUR 1.000 finché Morningstar/CRSP non offre per iscritto: snapshot 1998-2025, uso interno locale, prezzo totale entro cap, termine senza rinnovo automatico e retention sufficiente alla riproduzione.

## 2. Nasdaq Data Link / Sharadar — candidato API condizionato

Sharadar dichiara dati curati per public companies USA, fundamentals con **20 anni** di storia, copertura active e delisted “nearly completely free from survivorship bias”, e un dataset complementare di daily stock prices con la stessa estensione ([Sharadar Data](https://www.sharadar.com/data)). Nasdaq descrive Sharadar come prezzi, fondamenti e holdings USA con dati “going back over 20 years” ([Nasdaq Data Link overview](https://www.nasdaq.com/solutions/data/nasdaq-data-link)). Queste formulazioni correnti **non provano** il requisito completo 1998-2025: nel 2026 servono quasi 28 anni.

Le API Tables supportano bulk download e limiti elevati per abbonati premium ([Nasdaq Data Link rate limits](https://docs.data.nasdaq.com/docs/rate-limits-1)), quindi delivery locale e checksum sono fattibili in linea di principio. Tuttavia le pagine prodotto e gli schemi dettagliati sono gated e il portale corrente richiede contatto sales per prodotti istituzionali; non è pubblicato un prezzo verificabile per il bundle necessario. Le fonti pubbliche non consentono di confermare:

- earliest date effettiva per prezzi e fondamentali di tutte le active/delisted;
- campo open e volume per tutto il campione;
- market cap giornaliero costruito solo con shares outstanding disponibili in quella data;
- intervalli storici di primary exchange e security type, non soltanto stato corrente;
- payout o return economico post-delisting, oltre alla semplice inclusione del ticker delisted;
- almeno 200 nomi dopo i filtri esatti della #84.

I termini Nasdaq consentono ricezione, processing e storage per internal business use secondo l'Order Form, ma l'Order Form si rinnova per ulteriori annualità salvo preavviso di non rinnovo almeno 90 giorni prima; prezzo e retention dipendono dall'Order Form ([Nasdaq Data Link License Terms, §§1 e 6](https://data.nasdaq.com/terms)). Questo non soddisfa “nessun rinnovo automatico” senza deroga scritta.

**Verdetto:** seconda e ultima voce della shortlist, ma `COND` su quasi tutti i punti decisionali. Non comprare né iniziare integrazione prima di sample schema + risposta contrattuale completa.

## 3. Norgate Data US Stocks Platinum — economico ma non conforme

Il Platinum costa **USD 346,50 per 6 mesi** o **USD 630 per 12 mesi** (circa EUR 303/552 al fixing ECB, prima di imposte), include daily back to 1990, delisted securities e historical index constituents. Gli abbonamenti non si rinnovano automaticamente ([Norgate packages](https://norgatedata.com/stockmarketpackages.php), [Norgate overview](https://norgatedata.com/)).

Norgate documenta open come primo prezzo da qualsiasi venue/ECN, close come closing auction del listing exchange (o ultimo prezzo se assente), price/volume consolidati, delisted e un indicatore giornaliero di major-exchange listing dal 1995 ([Norgate data content](https://norgatedata.com/data-content-tables.php)). Documenta inoltre splits, capital returns, special e ordinary dividends nelle adjustment series ([Norgate Updater FAQ](https://norgatedata.com/ndu-faq.php)). Sono punti forti per OHLCV, ADV, corporate actions e survivorship.

Tre incompatibilità sono decisive:

1. I fundamentals sono esplicitamente **solo correnti**, non storici; `mktcap` è current price × current shares outstanding ([Norgate Data Packages FAQ](https://norgatedata.com/data-package-faq.php), [field definitions](https://norgatedata.com/fundamental-field-definitions.php)). Le membership Russell/S&P storiche non sono un sostituto causale della soglia mensile esatta USD 2 miliardi.
2. Norgate documenta `LastQuotedDate` e suggerisce di uscire sull'ultimo giorno di trading; non documenta un CRSP-like post-delisting payout/return. Usare ex post la seconda ultima barra per forzare l'uscita incorporerebbe conoscenza futura ([Norgate AmiBroker FAQ](https://norgatedata.com/amibroker-faq.php)).
3. Database e Python sono supportati solo su Windows; l'export ASCII contiene soltanto price data, non membership/indicatori. Alla scadenza il database diventa inaccessibile e la EULA impone di distruggere Data e software, impedendo la riproduzione futura dello snapshot nel normale ambiente Linux Alembic ([Norgate accessibility](https://norgatedata.com/accessibility.php), [Norgate EULA §§7, 8 e 21](https://norgatedata.com/subscribe/eula.php)).

**Verdetto:** `FAIL`; non va incluso nella shortlist di acquisto. Sarebbe utilizzabile solo rilassando requisiti hard, cosa non autorizzata.

## 4. EODHD All-In-One — API accessibile, finestra PIT insufficiente

EODHD offre daily OHLCV con open/high/low/close raw, adjusted close e split-adjusted volume, spesso per oltre 30 anni ([EOD Historical Data API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)). Offre inoltre listed/delisted common-stock lists, ticker change history, prices, dividends e splits. Ma per titoli delistati prima del 2018 dichiara **EOD only**; fundamentals/dividends/splits per delisted sono disponibili solo dopo il 2018 ([EODHD Delisted Data](https://eodhd.com/financial-apis/delisted-stock-companies-data-2)).

Il blocco inequivocabile è il market cap: l'endpoint equity è settimanale, solo NYSE/Nasdaq, e parte il **2021-07-09** ([EODHD Historical Market Cap](https://eodhd.com/financial-apis/historical-market-capitalization-api)). Ricostruirlo combinando prezzi con balance-sheet shares dal 2005/2009 non coprirebbe 1998 e richiederebbe una policy as-of non garantita dal vendor. L'API non documenta inoltre un delisting return/payout: l'ultima barra non rappresenta necessariamente il valore economico ricevuto dopo merger, bankruptcy o liquidation.

Il listino del 21 luglio 2026 mostra All-In-One a USD 899,91/anno e separatamente EOD a USD 179,10 + Fundamentals a USD 539,91/anno, entrambi sotto EUR 1.000 prima di imposte ([EODHD pricing](https://eodhd.com/pricing)). Tuttavia i termini consentono storage solo durante la subscription e impongono cancellazione di ogni copia entro un mese dalla scadenza ([EODHD Terms, Data Storage and Deletion](https://eodhd.com/financial-apis/terms-conditions)).

**Verdetto:** `FAIL` indipendentemente dal prezzo.

## 5. Kibot — buon archivio OHLCV, non un security master PIT

Kibot vende CSV di listed e delisted US stocks dal 1998, con open/high/low/close/volume e serie raw, split-adjusted e dividend-adjusted. Il bundle All Stocks & ETFs costa **USD 990 una tantum** e dichiara lifetime access; il formato daily è semplice `Date,Open,High,Low,Close,Volume` ([Kibot Buy Data](https://www.kibot.com/buy.html), [format reference](https://www.kibot.com/file-format/data-format-reference.html)). La licenza consente copie archivistiche, ma uso privato su due computer e nessuna redistribuzione ([Kibot license](https://www.kibot.com/license.html)).

Kibot non documenta historical market cap/shares, intervalli PIT per security type e primary listing, né payout/delisting returns. La lista comprende strumenti con suffissi da unit/warrant (`U`, `W`) e richiederebbe un secondo security master. Tale composizione non isola in modo affidabile common shares né risolve la soglia USD 2 miliardi. Inoltre USD 990 valgono circa EUR 867 prima di IVA; con IVA italiana al 22% arriverebbero a circa EUR 1.058, quindi serve un invoice quote per sapere se il cap è rispettato.

**Verdetto:** `FAIL`; evitare una composizione Kibot + altro vendor, perché proprio i campi mancanti determinano causalità dell'universo e delisting.

## 6. QuantConnect/AlgoSeek + Morningstar — tecnicamente plausibile, fuori budget

QuantConnect documenta un Security Master di circa 27.500 US equities dal gennaio 1998 con splits, dividends, mergers, ticker changes e delistings, oltre a un coarse universe giornaliero di circa 8.000 titoli per data con close auction, price e volume ([Security Master](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-security-master), [Coarse Universe](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/quantconnect/us-equity-coarse-universe)). Il dataset Morningstar Fundamentals copre dal 1998, esclude ETF/ADR/OTC, usa “As Original Reported” e fornisce `MarketCap` come close × latest reported shares outstanding ([Morningstar US Fundamental Data](https://www.quantconnect.com/docs/v2/writing-algorithms/datasets/morningstar/us-fundamental-data)).

Per uso locale, tuttavia, serve LEAN CLI, un paid organization tier, il Security Master e i prezzi AlgoSeek. Il listino ufficiale indica **USD 600/anno** per Security Master Quant Researcher e **USD 2.136/anno** per bulk daily US Equities, totale minimo USD 2.736 prima del costo Morningstar e della piattaforma ([QuantConnect local US Equity pricing](https://www.quantconnect.com/docs/v2/lean-cli/datasets/quantconnect/us-equity)). È oltre il doppio del cap. Le delisting docs descrivono warning sull'ultimo trading day e liquidazione automatica, non un payout post-delisting comparabile a CRSP ([QuantConnect Corporate Actions](https://www.quantconnect.com/docs/v2/writing-algorithms/securities/asset-classes/us-equity/corporate-actions)).

**Verdetto:** `FAIL` per costo e, secondariamente, per scope: adattare il POC Alembic allo stack LEAN sarebbe una pipeline parallela oltre il timebox.

## Perché non comporre vendor retail

Una composizione “OHLCV economico + fundamentals/constituents altrove” sembra conveniente ma è il rischio centrale del POC:

- ticker riutilizzati e symbol changes possono unire securities diverse;
- security type e primary exchange “correnti” contaminano il passato;
- shares outstanding con filing/revision timestamps diversi alterano il cap PIT;
- adjusted prices e corporate actions possono essere contati due volte;
- l'ultima barra di un delisted non equivale al pagamento economico finale;
- licenze diverse possono impedire di conservare lo snapshot unificato.

Perciò un multi-vendor build non è una scorciatoia accettabile entro due agent-days. Richiederebbe identifier mapping, as-of policy e riconciliazione proprie, cioè un nuovo progetto dati non autorizzato.

## Conferme commerciali minime

Inviare lo stesso questionario a CRSP/Morningstar e Nasdaq/Sharadar, chiedendo risposta scritta e sample schema, senza ordine:

1. prezzo totale, IVA/fees incluse, per un singolo snapshot 1998-2025 entro EUR 1.000;
2. termine fisso senza rinnovo automatico e senza notice trap;
3. diritto di scaricare e conservare localmente lo snapshot per riprodurre il POC, con checksum interno;
4. daily close, volume e, se disponibile, official open per active e inactive securities;
5. market cap o shares outstanding con `available_at`/filing timestamp sufficiente a calcolo causalmente PIT;
6. security type/share type/primary exchange con intervalli di validità storici;
7. splits, cash/special dividends, mergers, ticker changes e stable security identifier;
8. delisting date, last trade e post-delisting payout/return con missing-status esplicito;
9. sample di almeno tre casi: bankruptcy/worthless, cash acquisition e exchange migration/OTC;
10. conteggio mensile 1998-2025 dopo i filtri USD 5, USD 2bn, ADV USD 10m e 252 sessions, oppure diritto a calcolarlo in trial.

### Regola di riapertura

Il gate passa da `NO-GO` a `GO dati` solo se **un singolo vendor** risponde `sì` a tutti i punti 1-8, il sample dimostra il mapping causale e il conteggio prova almeno 200 nomi a ogni rebalance primario. Se nessuno lo fa entro il cap, #84 deve tornare al product owner come `NO-GO infrastrutturale`; non si sostituisce il dataset con la lista survivor corrente e non si apre il holdout 2023-2025.
