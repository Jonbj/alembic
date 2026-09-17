# Audit: migrazione da Yahoo Finance / yfinance a EODHD

**Data:** 2026-09-14  
**Articolo esaminato:** “I Replaced Yahoo Finance with EODHD — Here’s What Changed”, Kevin Meneses González, 2026-05-11  
**Metodo:** verifica claim-per-claim su documentazione ufficiale Yahoo, documentazione e codice sorgente ufficiali `yfinance`, documentazione/termini/prezzi EODHD e stato corrente del repository Alembic. L'articolo è uno spunto da verificare, non una fonte probatoria.

## Verdetto

La conclusione generale — non usare `yfinance` come se fosse un feed contrattualizzato di produzione — è ragionevole. Le motivazioni e la migrazione proposte dall'articolo, però, contengono errori materiali:

- Yahoo Finance Gold controlla ufficialmente il **download CSV nell'interfaccia web**. Le fonti Yahoo non dicono che l'endpoint JSON usato da `yfinance` richieda Gold. L'articolo trasforma un limite UI/licenza in una spiegazione causale non dimostrata degli errori `possibly delisted`.
- `yfinance` è non ufficiale, per uso personale/ricerca e senza SLA, ma chiamarlo semplicemente “scraper HTML” è impreciso: il percorso della price history usa l'endpoint JSON pubblico `v8/finance/chart`; altre funzionalità includono effettivamente scraping.
- Il piano EODHD da **$19,99/mese** è il feed EOD. I fondamentali sono un piano distinto da **$59,99/mese**; l'All-in-One costa **$99,99/mese**. Tutti i piani self-service sono indicati come personal use.
- EODHD offre API/documentazione più stabili, ma i termini self-service negano che il servizio sia error-free o uninterrupted e non garantiscono l'accuratezza. Gli SLA sono presentati per soluzioni custom/B2B, non come proprietà automatica del piano da $19,99.
- Gli esempi non sono semanticamente equivalenti: `yfinance.history()` ha `auto_adjust=True` per default e `end` esclusivo; EODHD restituisce OHLC raw, un solo `adjusted_close`, e interpreta `to` come inclusivo.
- Il codice EODHD dei fondamentali usa il ramo `annual`, mentre lo schema corrente documenta `Financials::Income_Statement::yearly`. Con il token demo, il 2026-09-14 la query dell'articolo ha restituito `"NA"`, quindi lo snippet fallisce quando chiama `.items()`.
- La presenza di ticker delisted in EODHD non rende automaticamente un dataset point-in-time. La qualificazione già svolta per Alembic #84 resta negativa per i requisiti S3 1998–2025.

**Valutazione:** non usare l'articolo come specifica di migrazione o fonte dati. È utile solo come segnalazione del debito già registrato in Alembic (R-09). Un cambio provider va qualificato separatamente per il singolo caso d'uso.

## Audit dei claim principali

| Claim dell'articolo | Valutazione | Evidenza ufficiale |
|---|---|---|
| Nel 2025 Yahoo ha messo l'historical data dietro Gold e questo ha rotto `yfinance` | **Parzialmente vero, causalità non dimostrata** | Yahoo dichiara che Gold abilita il download storico come file CSV dall'interfaccia web; continua a distinguere la visualizzazione dei dati dal download offline ([Yahoo Help](https://help.yahoo.com/kb/sln2311.html)). La pagina ufficiale dei piani descrive “Download historical data as CSV”, non accesso a un'API per sviluppatori ([Yahoo Finance Gold](https://finance.yahoo.com/__about/plans/select-plan/historicalStatistics/)). Nessuna delle due fonti documenta il blocco dell'endpoint chart JSON. |
| Gold costa circa $50/mese o $500/anno | **Stale/impreciso per gli USA al 2026-09-14** | Il listino USA corrente è $39,95/mese oppure $479,40/anno; i prezzi variano per paese ([piani Yahoo](https://finance.yahoo.com/__about/plans/select-plan/historicalStatistics/)). |
| Gli errori “possibly delisted” provano il paywall | **No** | L'issue `yfinance` #2340 è una segnalazione utente che inferisce la causa dalla pagina Yahoo; non presenta debug log o prova del paywall ed è chiusa ([issue #2340](https://github.com/ranaroussi/yfinance/issues/2340)). La stessa stringa è un errore generico di mancato recupero, non una risposta di entitlement. Nel febbraio 2025 il progetto ha anche corretto un outage cambiando gli user-agent headers, una causa tecnica diversa dal paywall ([PR #2277](https://github.com/ranaroussi/yfinance/pull/2277)). |
| `yfinance` è uno scraper fragile | **Fragilità corretta; descrizione tecnica troppo ampia** | Il progetto si dichiara non affiliato né verificato da Yahoo, per ricerca/educazione, e rinvia ai termini Yahoo per i diritti sul dato ([README ufficiale](https://github.com/ranaroussi/yfinance)). Il codice corrente della price history chiama il JSON `query2.finance.yahoo.com/v8/finance/chart/{ticker}`; alcune altre feature usano scraping HTML ([sorgente `base.py`](https://github.com/ranaroussi/yfinance/blob/main/yfinance/base.py)). Rimane quindi un client non supportato verso interfacce pubbliche soggette a cambiamenti, rate limit e restrizioni d'uso. |
| EODHD a $19,99 include prezzi, fondamentali, dividendi, split e archivio completo | **Falso come bundle** | Il listino separa EOD All World $19,99, Fundamentals $59,99 e All-in-One $99,99 al mese. L'EOD include corporate actions/adjusted data, ma non il feed completo dei fondamentali ([pricing EODHD](https://eodhd.com/pricing)). |
| Passare a EODHD dà un contratto/SLA chiaro | **Solo per licenze commerciali negoziate** | I pacchetti della pagina self-service sono personal use; il commerciale richiede onboarding/licenza separata ([licenze EODHD](https://eodhd.com/financial-apis/commercial-vs-personal-license-use)). I piani commerciali partono da $399/mese e il contratto dati firmato è associato al piano Custom ([commercial pricing](https://eodhd.com/commercial-pricing)). Gli SLA sono pubblicizzati insieme a custom volumes/dedicated support; i termini generali promettono solo commercially reasonable efforts, escludono responsabilità per interruzioni e negano garanzia di servizio error-free/uninterrupted o dato necessariamente accurato ([termini EODHD](https://eodhd.com/financial-apis/terms-conditions)). |
| I campi yfinance ed EODHD mappano 1:1 | **Falso senza un adapter semantico** | `yfinance.history()` usa OHLC automaticamente adjusted di default, con `start` inclusivo ed `end` esclusivo ([documentazione `PriceHistory`](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html)). EODHD usa `from` e `to` inclusivi; OHLC e close sono raw, `adjusted_close` include split e dividendi, volume è split-adjusted ([EOD API](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes)). |
| I dati delisted EODHD risolvono il survivorship bias | **Disponibilità utile, ma non prova sufficiente di PIT completeness** | EODHD documenta EOD-only per società delistate prima del 2018, fundamentals/dividends/splits solo dal 2018 e intraday dal 2021 ([delisted data](https://eodhd.com/financial-apis/delisted-stock-companies-data-2)). Il market cap storico azionario è solo NYSE/Nasdaq, settimanale e parte dal 2021-07-09 ([historical market cap](https://eodhd.com/financial-apis/historical-market-capitalization-api)). Questo non soddisfa da solo universo, classificazioni, market cap e trattamento economico del delisting point-in-time per 1998–2025. |

## Paywall Yahoo: cosa è dimostrato e cosa no

La documentazione Yahoo consente una conclusione stretta:

1. i dati storici restano visualizzabili nell'interfaccia;
2. l'esportazione come CSV richiede Gold per gli strumenti coperti;
3. Yahoo invita gli sviluppatori interessati a un piano/API a contattarla, ma non documenta un'API gratuita o un entitlement Gold per l'endpoint `query2`;
4. `yfinance` non è un prodotto Yahoo e non dà un diritto autonomo all'uso del dato.

Non consente invece di concludere che ogni richiesta storica di `yfinance` senza Gold sia stata bloccata. Il fatto che il client continui a usare l'endpoint JSON senza credenziali Gold e che l'errore indicato nell'articolo non rappresenti un codice di entitlement rende la spiegazione “paywall” al massimo una congettura. Il rischio operativo resta reale — Yahoo può cambiare, limitare o rimuovere quell'interfaccia — ma va nominato correttamente.

La distinzione conta per Alembic: acquistare Yahoo Gold non trasformerebbe `yfinance` in un'API ufficiale, non fornirebbe un contratto programmatico e non risolverebbe i rischi R-09.

## Contratto semantico: una sostituzione meccanica cambia i risultati

| Aspetto | `yfinance.Ticker.history()` | EODHD `/api/eod` | Conseguenza |
|---|---|---|---|
| Inizio range | Inclusivo | Inclusivo | Compatibile |
| Fine range | Esclusivo | Inclusivo | La stessa data può aggiungere una barra EODHD; l'esempio usa il 1° gennaio festivo e nasconde il bug |
| OHLC default | Tutti auto-adjusted (`auto_adjust=True`) | Tutti raw | Open/high/low/close non sono confrontabili direttamente |
| Close total-return adjusted | `Close` dopo auto-adjust | `adjusted_close` | Serve mapping esplicito e test su split/dividendi |
| Volume | Semantica Yahoo/processamento `yfinance` | EODHD dichiara split-adjusted | Va verificato su corporate actions, non assunto identico |
| Corporate actions | `actions=True` di default nella history | Endpoint separati; `adjusted_close` già le incorpora | Rischio di doppio aggiustamento |
| Date/time | Indice pandas timezone-aware per mercato, poi normalizzabile | Data EOD `YYYY-MM-DD` | Serve calendario/exchange timezone esplicito |
| Correzioni dati | `repair=False` default; opzione documentata per errori 100×, missing e bad dividend adjustment | Nessuna equivalenza nello snippet | Serve quality/reconciliation policy |

Per una migrazione corretta l'adapter deve dichiarare almeno: raw versus adjusted, tipo di adjustment, intervallo `[start, end)` interno, timezone/calendario, valuta, corporate-action policy, deduplica, missing bars e revision policy. Un test deve includere almeno uno split e un dividendo; AAPL 2023, come nell'articolo, non esercita il caso più pericoloso.

## Audit del codice dell'articolo

### EOD price history

Il frammento usa un endpoint reale, `fmt=json` e una chiave da environment: buone basi. Non è production-ready perché:

- manca `timeout`;
- manca `response.raise_for_status()` e gestione di 401/429/5xx;
- manca validazione di content type e schema; error payload o `"NA"` possono diventare DataFrame fuorvianti;
- mancano retry con backoff/jitter e limiti di concorrenza;
- non ordina né verifica esplicitamente date, duplicati, calendario o barre mancanti;
- seleziona `close` raw dopo aver mostrato un esempio `yfinance` che, per default, restituisce OHLC adjusted;
- replica `to=end` senza compensare la diversa inclusività;
- non riconcilia split/dividendi e non registra provider/schema/versione per la riproducibilità.

Passare il token nella query è il metodo documentato da EODHD, ma il client deve evitare di loggare URL completi, tracing e messaggi d'errore contenenti `api_token`.

### Fundamentals

Il codice usa:

```text
filter=Financials::Income_Statement::annual
```

Lo schema corrente EODHD documenta `Financials::Income_Statement::yearly` e raccomanda `/api/v1.1/fundamentals/` per nuove integrazioni ([Fundamentals API](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds)). La verifica live col token demo il 2026-09-14 ha restituito `"NA"` per il filtro dell'articolo; il successivo `income_data.items()` solleva quindi `AttributeError`.

Anche correggendo il filtro:

- `list(income_data.items())[:3]` confida nell'ordine del JSON invece di ordinare per data;
- `values.get("totalRevenue", 0)` trasforma un campo assente in un falso zero economico e non gestisce `null`;
- manca la valuta;
- non viene usato `filing_date`, sebbene ogni record annuale/trimestrale la esponga;
- non è documentata una storia delle versioni/revisioni del filing: una risposta scaricata oggi non va trattata automaticamente come snapshot disponibile in passato.

### Dividendi

Il codice fornisce solo `from` e lascia aperto il termine finale. L'output cambia nel tempo, quindi non è una fixture riproducibile. Occorrono `from`, `to`, ordinamento, valuta, trattamento special dividends e test contro `adjusted_close` per prevenire il doppio conteggio.

## Point-in-time, delisted e survivorship

EODHD ha un vantaggio concreto rispetto a un universo solo-current: espone elenchi delisted e mantiene prezzi fino alla data di delisting. Ma l'affermazione della sua documentazione secondo cui ciò fornisce da solo un “complete, point-in-time universe” è più ampia delle caratteristiche documentate.

Per un backtest PIT servono congiuntamente:

- membership storica dell'universo al decision timestamp;
- identificatore stabile e storia ticker/merger/spin-off;
- stato/security type/exchange disponibili in quella data;
- fondamentali secondo `filing_date` e, se rilevante, vintage/revisioni;
- market cap contemporaneo con copertura e frequenza richieste;
- prezzo finale più ritorno/payout economico di delisting, non solo l'ultima barra;
- date di disponibilità e lag applicati prima del ranking.

Nel caso Alembic #84, EODHD era già stato qualificato come **non sufficiente**: il requisito S3 è daily 1998–2025 con universe/security type/listing e market cap PIT, oltre a trattamento economico del delisting. La copertura ufficiale EODHD lascia prima del 2018 solo EOD sui delisted e fa partire il market cap settimanale dal luglio 2021. L'articolo non aggiunge evidenza che chiuda questi gap.

## Impatto concreto su Alembic

### 1. Macro runtime: rischio reale ma migrazione stretta

[`src/connectors/macro.py`](../../src/connectors/macro.py) usa `yfinance` a runtime per sole due mensilità di SPY e calcola il momentum su 20 sedute. Il rischio è già registrato come R-09 in [`docs/RESIDUAL_RISK_REGISTER.md`](../RESIDUAL_RISK_REGISTER.md): affidabilità/licenza/availability possono degradare il regime detector.

Questo caso è molto più stretto di una piattaforma generale di market data. Non richiede fondamentali, universo delisted o 30 anni. La decisione corretta non è “comprare EODHD All-in-One”, ma sostituire il fetch dietro un adapter con:

- fonte già contrattualizzata e coerente con l'esecuzione, se disponibile (il risk register indica Alpaca come candidata);
- `start/end` interno half-open e close-adjustment esplicito;
- fallback controllato e freshness check;
- fixture su split/dividendi e confronto giornaliero tra provider durante shadow;
- nessun acquisto/promozione senza verifica della licenza per l'uso Alembic.

### 2. Backtest legacy: cambiare URL non risolve la validità

[`src/backtest/data/loader.py`](../../src/backtest/data/loader.py) usa `yfinance` con `auto_adjust=False` e tre tentativi. Se manca `Adj Close`, assegna però `Close` raw a `Adj Close`, nascondendo una differenza economica invece di fallire. Inoltre l'audit S1 documenta un universo S&P 500 corrente privo dei delisted ([`docs/audits/strategies/S1/07_bugs.md`](../audits/strategies/S1/07_bugs.md)).

Una sostituzione con EODHD potrebbe migliorare availability, ma non rende il backtest PIT senza rifare universo, identifiers, corporate actions, delisting returns e as-of filtering. #84 resta il gate pertinente.

### 3. EODHD News: #579 è indipendente

#579 valuta EODHD **solo** come possibile news feed sui ticker ciechi di #511 e richiede coverage, licenza/persistenza, timestamp, stable ID e deduplica. Il presente articolo riguarda prezzi/fondamentali e non fornisce misure sul feed news. Non cambia lo stato né il gate di #579 e non giustifica un acquisto congiunto.

## Decisione raccomandata

1. **Non accodare l'articolo come fonte affidabile** e non usarlo per decidere il vendor.
2. **Non aprire una migrazione globale Yahoo→EODHD.** Il problema immediato di Alembic è il singolo fetch SPY a runtime; va trattato come seam piccolo e testabile.
3. **Non acquistare il piano EODHD da $19,99 aspettandosi i fondamentali** e non assumere SLA o licenza commerciale.
4. **Mantenere #84 come fonte di verità per la qualificazione PIT.** La disponibilità dei delisted EODHD non soddisfa i requisiti storici S3.
5. **Mantenere #579 separata.** Un eventuale pilot news deve essere giudicato sui suoi acceptance criteria, non sul marketing price-data.
6. Se si valuta EODHD per il macro runtime, eseguire un breve shadow benchmark EODHD vs provider attuale/licenziato su SPY, con contratto semantico e fault injection, prima di modificare la fonte primaria.

## Fonti primarie/ufficiali essenziali

1. Yahoo Help, [Download historical data in Yahoo Finance](https://help.yahoo.com/kb/sln2311.html).
2. Yahoo Finance, [Gold plan e downloadable CSV](https://finance.yahoo.com/__about/plans/select-plan/historicalStatistics/).
3. `yfinance`, [README ufficiale e limitazioni d'uso](https://github.com/ranaroussi/yfinance) e [documentazione `PriceHistory`](https://ranaroussi.github.io/yfinance/reference/yfinance.price_history.html).
4. EODHD, [pricing](https://eodhd.com/pricing), [licenza personal/commercial](https://eodhd.com/financial-apis/commercial-vs-personal-license-use) e [termini](https://eodhd.com/financial-apis/terms-conditions).
5. EODHD, [EOD price semantics](https://eodhd.com/financial-apis/api-for-historical-data-and-volumes) e [Fundamentals API](https://eodhd.com/financial-apis/stock-etfs-fundamental-data-feeds).
6. EODHD, [delisted coverage](https://eodhd.com/financial-apis/delisted-stock-companies-data-2) e [historical market cap](https://eodhd.com/financial-apis/historical-market-capitalization-api).

