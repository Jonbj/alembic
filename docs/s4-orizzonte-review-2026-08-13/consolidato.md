# S4 — consolidamento della decisione sull'orizzonte economico

**Data:** 2026-08-14  
**Oggetto:** consolidamento critico di quattro analisi indipendenti su S4, strategia news-driven tactical

## 1. SINTESI DELLE SCELTE

| Modello | Scelta | Confidenza dichiarata | Ragione principale |
|---|---|---|---|
| Claude Opus | **B — 2 sedute, close-to-close** | Media nell'esclusione di A; **bassa** su B rispetto a C | In conto paper, eseguire B compra osservabilità a basso costo: i difetti più importanti sono emersi dal ciclo ordini reale. Inoltre B allinea finalmente la regola d'uscita all'orizzonte economico e riduce il drag dei costi. |
| Codex | **C — shadow reversibile** | Media | L'IC si può misurare senza tradare; impegnare capitale più a lungo con dati sporchi, uscite rotte e alpha non dimostrato non aggiunge informazione sufficiente. |
| GLM-5.2 | **C — stage 1 di una decisione a due stadi** | Media | Prima si misura su dati puliti in shadow, simulando B; solo dopo si sceglie l'orizzonte o si chiude. Il P&L live attuale non rappresenta né A né B. |
| Qwen3.5 | **C — shadow immediato** | Media (alta sulla direzione, media sui tempi) | S4 non possiede oggi un orizzonte economico: la tenuta di 1h45/4h15 è una scadenza software. Shadow è reversibile, elimina turnover e preserva la misura. |

Il voto è 3–1 per C, ma non va interpretato come 75% di probabilità che C sia corretta: le analisi non sono campioni indipendenti in senso statistico e condividono gli stessi fatti di partenza. Il loro valore sta nella convergenza degli argomenti, non nel conteggio.

## 2. CONVERGENZE

### Concordanza sostanziale di tutti e quattro i modelli

- **A non è una scelta operativa difendibile con la pipeline attuale.** Al primo segnale utile il 70–84% del movimento intraday risulta già avvenuto, fino al 99% nel gap di apertura in alcuni casi. Una S4 a 1–4 ore comprerebbe prevalentemente dopo il movimento e sopporterebbe il massimo drag di turnover. Per rendere A credibile servirebbero fonti primarie/event-driven e un'infrastruttura diversa; sarebbe un nuovo progetto, non un semplice cambio di parametro.
- **L'evidenza non basta per affermare che S4 abbia alpha.** L'IC corrente è sotto-potenza, calcolato su un campione piccolo e contaminato, e non diventerà automaticamente probatorio al raggiungimento di `n=73`.
- **L'orizzonte effettivo attuale non è economico.** Le uscite concentrate a 1h45 e 4h15 riflettono freschezza della news, cadenza dei cicli e difetti QS-07/FIX-D. Descrivono il software, non il decadimento atteso dell'alpha.
- **Il dato a monte è troppo sporco per un verdetto sull'alpha.** Articoli multi-ticker, resolver errato, copertura incompleta e falsi positivi su ticker molto coperti alterano la popolazione osservata. Un IC pre-fix non è una misura pulita della strategia progettata.
- **Il P&L realizzato non decide la questione.** Il `+209 $` lifetime di S4, il confronto con il realizzato di S1, la settimana peggiore da nove trade, il controfattuale “compra all'apertura” e la `t=-4,96` sull'ora d'ingresso non isolano l'alpha e non devono guidare la decisione.
- **Serve una regola d'uscita esplicita e indipendente dalla cadenza editoriale.** Se S4 tornerà in esecuzione, un time-stop coerente con l'orizzonte deve essere primario; freschezza del segnale deve governare l'ingresso, non liquidare implicitamente la posizione.
- **Il criterio #179, nella forma corrente, non è decision-grade.** Mescola orizzonti non coerenti con la strategia eseguita, usa un gate di numerosità senza potenza adeguata e non gestisce correttamente qualità del dato e dipendenza dei forward return.
- **Shadow non equivale a kill.** Per i tre modelli pro-C è uno stato sperimentale reversibile; anche Opus riconosce che C sarebbe preferibile con capitale reale e in scala.

### Concordanza di almeno tre modelli

- **C è il regime immediato più prudente**, purché abbia un criterio di uscita e non diventi un parcheggio indefinito.
- **La decisione corretta è a due stadi:** prima rendere coerente la misura, poi decidere se attivare B o abbandonare S4.
- **Il 28/09 non può essere presentato come data di prova dell'alpha.** Può essere una review di qualità, funzionamento e direzione del segnale, non un test confirmatorio conclusivo.
- **La sovrapposizione con S1 è un rischio strategico reale ma ancora non dimostrato.** I 21 intenti bloccati su 30 sono un allarme da misurare su una finestra più ampia, non una prova definitiva di ridondanza.

## 3. DISSENSI

### B contro C

Il dissenso centrale non riguarda dove sia l'alpha, ma **quale informazione aggiunga l'esecuzione**.

- Opus sostiene che in conto paper B sia un esperimento economico: il ciclo completo di esecuzione ha rivelato guard anti-pyramiding, uscite `unknown`, percentile d'ingresso e altre rotture che un semplice logging dei segnali non avrebbe mostrato.
- Codex, GLM e Qwen sostengono che l'informazione decisiva — IC, forward return e P&L simulato di B — sia ottenibile senza esecuzione. Poiché l'implementazione corrente è rotta, il suo P&L live è anzi una misura contaminata.

La divergenza si riduce molto se “shadow” significa **shadow execution end-to-end**, con intenti, ranking, collisioni, fill virtuali, costi, regole d'uscita e reason code prodotti dallo stesso codice dell'esecuzione, fermandosi soltanto prima dell'invio al broker. Uno shadow limitato al calcolo dell'IC darebbe ragione a Opus; uno shadow che replica l'intero lifecycle recupera gran parte dell'osservabilità senza assumere esposizione.

### Statuto del criterio #179

- Per Opus, anticipare C prima che il criterio pre-registrato raggiunga `n=73` è una violazione di disciplina, soprattutto dopo aver osservato la settimana peggiore. #179 va corretto e nuovamente pre-registrato, non semplicemente ignorato.
- Per gli altri tre, #179 è già nullo come criterio probatorio: misura la cosa sbagliata e può promuovere o bocciare rumore. Non deve impedire il passaggio immediato a C.

La posizione coerente è intermedia ma netta: **#179 non va fatto “sparare” come se fosse valido, né aggirato informalmente**. Va formalmente ritirato o sostituito, con motivazione ex ante basata su errori di specificazione documentati; il nuovo criterio va registrato prima di osservare il segmento post-fix. Il passaggio a shadow è una misura di controllo del rischio e di validità sperimentale, non l'esito negativo di #179.

### Tempistica

- Opus propone prima uno studio retrospettivo di 1–3 giorni, poi la riscrittura del criterio e infine un singolo deploy di B con fix dati e uscite.
- GLM propone un batch unico: fix dati, shadow e nuova pre-registrazione.
- Codex propone shadow subito; se i fix non sono pronti, il conteggio `n=0` parte solo dopo il loro deploy atomico.
- Qwen propone shadow immediato, poi fix e review dopo circa 40 sedute.

La distinzione decisiva è fra **mettere in sicurezza il regime** e **far partire il campione confirmatorio**: si può passare a shadow subito, ma nessuna osservazione entra nel test finché dati, configurazione e simulatore B non sono congelati e validati.

### Popolazione di misura

- Opus insiste correttamente sulla popolazione effettivamente negoziata: `solo-ensemble ∩ |score| ≥ 0,30`, dopo i filtri operativi. Considera “tutti gli ensemble” solo una diagnostica.
- Codex usa `solo-ensemble` come primaria, ma chiede un report separato sul sottoinsieme acquistabile dopo gate e collisione con S1.
- GLM separa ensemble e FinBERT e stratifica per alta convinzione; propone un pooled symbol-day come misura primaria e la serie degli IC giornalieri come conferma.
- Qwen usa ensemble ad alta confidenza, senza fallback.

Per valutare **la strategia**, Opus ha l'impostazione più corretta: la popolazione primaria deve coincidere con quella tradabile. La popolazione più ampia è utile per diagnosticare il modello, non per decidere l'allocazione.

### Orizzonte, test e numerosità

- Opus vuole l'intera term structure `{1h, 4h, close, 1g, 2g, 3g, 5g}`, con 2 sedute come candidato primario e `n≈120` per un test a `t=2` con circa 20 nomi/giorno.
- Codex vuole 1 seduta come test primario, 3 sedute solo diagnostiche, `t≥3` e circa 213 sedute pulite alla varianza osservata.
- GLM privilegia 1/3/5 giorni, pooled IC con cluster bootstrap e conferma time-series; indica circa 60/90 sedute per le due letture.
- Qwen propone close, 1 giorno e 4 giorni, `n=73` come gate ma circa 160 sedute per rilevare IC 0,05 con potenza 80%.

La divergenza riflette finalità diverse: esplorare la forma della curva, prendere una decisione economica o produrre evidenza confirmatoria. Queste finalità non vanno fuse in un unico numero.

## 4. ANALISI CRITICA: B CONTRO C

### B — 2 sedute close-to-close

**Punti a favore**

- È l'unica opzione che trasforma S4 in una strategia definita: time-stop esplicito, clock DAILY e separazione netta fra validità del segnale d'ingresso e durata della posizione.
- È coerente con il solo meccanismo di alpha ancora plausibile con news editoriale tardiva: post-event drift o reversione multi-day, non cattura del salto intraday.
- Riduce turnover e costi. La stima di Opus porta l'IC di pareggio da circa 0,038 a 4 ore a circa 0,021 a 2 sedute; l'ostacolo economico diventa plausibilmente meno stringente.
- Produce osservabilità sul comportamento reale dell'architettura, particolarmente utile in conto paper.
- Evita di modificare il regime sulla base dell'ultima settimana negativa e tutela il principio di pre-registrazione.

**Punti contro**

- Non esiste ancora evidenza pulita che l'IC multi-day sia positivo. Allungare la tenuta corregge il contenitore, ma non dimostra che contenga alpha.
- Impegna il 10% della sleeve e aumenta l'overlap temporale con S1 proprio mentre la diversificazione di S4 è dubbia.
- Un deploy simultaneo di fix dati e nuova uscita rende impossibile attribuire temporalmente eventuali miglioramenti, anche se la scarsità di campione limita comunque il valore di una separazione in due finestre corte.
- Se l'esecuzione è reale e non paper, il vantaggio informativo non compensa il rischio di finanziare un esperimento sotto-potenza.

**Argomento più forte per B:** l'esecuzione paper è una sonda di integrazione a basso costo e B è la prima configurazione in cui l'orizzonte dichiarato, la regola d'uscita e la misura economica coincidono. Non è una prova di alpha; è una prova del sistema completo.

### C — shadow reversibile

**Punti a favore**

- Separa la domanda “esiste alpha?” dalla decisione di esporre capitale. IC, forward return e portafoglio B simulato sono misurabili senza ordine reale.
- Impedisce che turnover, uscite difettose e collisioni contaminino ulteriormente il P&L usato come evidenza.
- È reversibile e conserva optionality: S4 può tornare come B se supera un criterio pre-registrato.
- Consente un segmento post-fix pulito e congelato, indispensabile per una lettura out-of-sample.
- È dominante in presenza di capitale reale; anche Opus lo riconosce.

**Punti contro**

- Uno shadow ingenuo non scopre problemi di routing, fill, stato ordini, race condition o reason code. Può produrre un backtest elegante ma non deployabile.
- Posticipa il test operativo di B e può perdere un edge debole ma reale durante una finestra di mercato limitata.
- Senza una deadline statistica e una regola di riattivazione rischia di diventare un limbo permanente.
- Un P&L simulato può sottostimare slippage e costi, soprattutto perché S4 entra già tardi nel movimento.

**Argomento più forte per C:** la variabile che deve decidere l'allocazione — alpha netto a un orizzonte esplicito — è osservabile senza rischio; l'esecuzione corrente misura invece una strategia diversa e rotta. Quindi continuare a eseguire non è necessario per rispondere alla domanda economica.

### Valutazione

L'argomento di Opus è il migliore sul piano dell'**engineering observability**; quello dei tre modelli pro-C è migliore sul piano dell'**identificazione economica e del controllo del rischio**. La soluzione non è mediare le due opzioni, ma costruire C in modo da assorbire il vantaggio di B: shadow end-to-end, con lo stesso codice di selezione, portfolio construction, collisione S1, fill virtuale, cost model, aging e uscita che verrebbe usato in produzione.

## 5. RACCOMANDAZIONE CONSOLIDATA

**Raccomandazione: C immediata come stato sperimentale reversibile, con B a 2 sedute implementata integralmente in shadow.** Non è un kill di S4 e non è una conclusione che l'alpha sia nullo. È lo stage 1 di una decisione pre-registrata: validare su dati puliti la strategia che si vorrebbe eventualmente eseguire.

Questa è la scelta più prudente e coerente perché:

1. evita esposizione su una strategia oggi non identificabile;
2. non usa il rumore corrente per dichiarare S4 fallita;
3. conserva la serie e l'optionalità di riattivazione;
4. incorpora l'obiezione più forte di Opus facendo girare in shadow l'intero ciclo operativo di B, non soltanto il calcolo dell'IC;
5. tratta formalmente #179 come criterio mal specificato da sostituire, non come regola da anticipare opportunisticamente.

La configurazione shadow candidata deve essere una sola e congelata: ingresso al primo prezzo RTH eseguibile dopo il segnale, universo e gate ex ante, `solo-ensemble`, `|score| ≥ 0,30`, sizing e slot invariati, time-stop primario alla chiusura di D+2, contro-segnale e stop di rischio come sole eccezioni. La freschezza del segnale resta un filtro d'ingresso. Il lato ingresso non va ottimizzato durante la raccolta.

**Eccezione:** se S4 opera esclusivamente in conto paper e lo shadow non può tecnicamente riprodurre il lifecycle degli ordini, B paper per un periodo breve e predefinito è giustificabile come test di integrazione, ma i suoi risultati economici non devono essere usati come prova di alpha.

## 6. CRITERIO DI FALSIFICAZIONE

Tra quelli proposti, il criterio più robusto è il **gate congiunto di Codex**: un effetto IC minimo con significatività HAC e, contemporaneamente, una performance shadow netta superiore a un benchmark con limite inferiore dell'intervallo di confidenza sopra zero. È più solido del solo segno medio di #179, del solo P&L e delle soglie `t≥2` su campioni brevi.

Va però corretto con due elementi di Opus: popolazione effettivamente tradabile e gate di integrità operativa.

### Criterio consolidato di riattivazione di B

C è falsificata — e B può essere attivata — solo se **tutte** le condizioni seguenti sono soddisfatte su un segmento pulito, congelato e post-fix:

1. **Integrità:** almeno il 95% dei lifecycle shadow è ricostruibile end-to-end; uscite `expired/unknown` < 5%; nessuna divergenza materiale fra configurazione dichiarata e applicata.
2. **Alpha:** sulla popolazione tradabile, IC medio all'orizzonte primario di 2 sedute `≥ +0,05`, con `t Newey–West ≥ 3` e segno non contraddetto a 1 e 3 sedute.
3. **Economia:** il portafoglio shadow B, dopo fill eseguibili, costi e slippage conservativi, batte il benchmark equal-weight della watchlist; il limite inferiore unilaterale al 95% dell'excess return deve essere `> 0`.
4. **Indipendenza:** overlap degli intenti con S1 e capacità impegnata restano entro una soglia pre-registrata. Una soglia prudente è overlap `≤ 50%`; oltre tale livello S4 deve dimostrare valore incrementale rispetto a S1, non soltanto P&L standalone.

Il criterio deve essere congiuntivo: IC positivo senza monetizzazione non basta; P&L positivo senza relazione segnale-rendimento può essere fortuna o artefatto dell'uscita.

Il mancato superamento a `n=73` non falsifica B e non giustifica un kill. Per il test confirmatorio, alla varianza osservata da Codex servono circa **213 sedute pulite** per rilevare IC 0,05 con `t=3`; il numero va ricalcolato ex ante sulla varianza post-fix e può solo aumentare se questa peggiora. Review intermedie possono verificare pipeline e rischio, non promuovere la strategia.

## 7. PIANO DI RIMISURA IC

### Popolazione

- **Primaria:** osservazioni che sarebbero realmente tradabili da S4: solo ensemble, `|score| ≥ 0,30`, ticker validato, dato disponibile al decision timestamp, dopo gate di universo, liquidità, capacità e collisione con S1.
- **Secondarie diagnostiche:** tutti i segnali ensemble; ensemble sotto soglia; fallback FinBERT; articoli single-ticker contro multi-ticker; tipologia editoriale contro fonte primaria. Queste stratificazioni spiegano il segnale, ma non sostituiscono il test primario.
- Devono essere riportati ogni giorno numero di simboli effettivi, copertura e motivo di esclusione. Aumentare `n` aggiungendo osservazioni che la strategia non potrebbe tradare produce falsa potenza.

### Orizzonti

- **Esplorazione una tantum, prima della pre-registrazione:** curva completa `{1h, 4h, close, 1g, 2g, 3g, 5g}` per identificare forma, picco e decadimento.
- **Test confirmatorio:** 2 sedute, coerente con la B candidata, senza mediare ex post più orizzonti.
- **Robustezza predefinita:** 1 e 3 sedute. 5 sedute resta diagnostico perché la sovrapposizione dei forward return riduce fortemente l'`n` effettivo. Un eventuale picco intraday non autorizza A con la pipeline attuale: apre un progetto separato su fonti event-driven.

### Prezzi e rendimenti

- Prezzo iniziale: fill shadow generato dal primo prezzo RTH realisticamente eseguibile dopo il decision timestamp; in assenza, chiusura della prima barra 15 minuti successiva.
- Prezzo finale: close di D+2 per il test primario, con total return e corporate action correttamente trattate.
- Riportare separatamente l'IC da prezzo-segnale e quello da prezzo eseguibile: la differenza misura slippage/ritardo strutturale e non va nascosta nei costi espliciti.
- Nessun controfattuale con informazione futura e nessun cambio ad hoc di timestamp, universo o winsorization dopo aver osservato i risultati.

### Stima e standard error

- Spearman cross-sectional per giorno; inferenza sulla serie temporale degli IC giornalieri.
- Newey–West/HAC con lag coerente con l'orizzonte per gestire autocorrelazione e forward return sovrapposti.
- Cluster bootstrap per giorno come controllo di robustezza, non come scorciatoia per trasformare migliaia di symbol-day correlati in altrettante osservazioni indipendenti.
- Riportare media IC, mediana, intervallo di confidenza, `t`, numero di giorni, numero mediano di nomi/giorno e `n` effettivo.

### Numerosità minima

- `n=40` o `n=73`: solo diagnostica e verifica di pipeline.
- Circa `n=120`: soglia minima indicativa per un IC 0,05 con `t≈2` e circa 20 nomi/giorno, secondo l'aritmetica di Opus; non sufficiente per la riattivazione prudenziale.
- Circa **`n=213` sedute pulite**: riferimento confirmatorio per `IC=0,05` e `t≥3` alla varianza osservata da Codex. Va rifatta una power analysis con la varianza post-fix e il numero effettivo di nomi/giorno prima di congelare il protocollo.

## 8. SEQUENZA DI DEPLOY

1. **Snapshot e audit, senza cambiare comportamento:** congelare configurazione, timestamp, universo e segmento pre-deploy; aggiungere telemetria non comportamentale. Eseguire la term structure retrospettiva su popolazione pulibile, prezzi eseguibili e split per fonte/tipologia. Questo studio informa il protocollo, non conta come out-of-sample.
2. **Pre-registrazione:** ritirare formalmente #179 spiegandone gli errori di specificazione; registrare popolazione, orizzonte primario, prezzi, cost model, SE, numerosità e gate congiunto. Non leggere il segmento post-fix prima che il protocollo sia congelato.
3. **Un solo deploy datato:** attivare insieme i fix di correttezza del dato e lo shadow end-to-end di B a 2 sedute. Se i fix non sono tutti pronti, passare comunque a shadow per sicurezza, ma far partire `n=0` solo con il successivo batch atomico completo.
4. **Validazione tecnica iniziale:** verificare lifecycle, fill virtuali, collisioni S1, reason code, clock DAILY e time-stop. Qualunque errore di implementazione azzera e riavvia il campione confirmatorio se può averne alterato le osservazioni.
5. **Freeze:** nessun cambio a fonte, resolver, gate, ranking, soglia, universo, sizing, slot, cost model o orizzonte durante la raccolta. Report settimanale separato per integrità, IC diagnostico, economia shadow e overlap; niente decisioni su P&L settimanale.
6. **Review del 28/09:** classificare l'esito come tecnico/diagnostico. Salvo effetto enorme previsto da un early-stop pre-registrato, non riattivare B e non killare S4 per insufficienza di significatività.
7. **Decisione confirmatoria:** riattivare B solo al superamento del gate congiunto. In caso contrario, continuare fino a `n` minimo; al raggiungimento del campione, IC economicamente nullo o performance netta non positiva implica kill o redesign, non ulteriore shadow indefinito.
8. **Canary prima della scala:** dopo il superamento del gate, breve riattivazione paper o a capitale minimo per verificare che fill, stato ordini e uscite reali replichino lo shadow; scala solo dopo riconciliazione.

Questa sequenza minimizza le discontinuità senza confondere il segmento storico sporco con il campione confirmatorio pulito.

## 9. RISCHI E AVVERTENZE

- **Falsa precisione del voto 3–1.** I modelli condividono dati e framing; la maggioranza rafforza una scelta di governance, non una probabilità statistica.
- **Shadow troppo semplificato.** Se non usa lo stesso codice dell'esecuzione fino al confine broker, l'obiezione di Opus resta valida e la riattivazione sarà esposta a difetti mai osservati.
- **Simulazione ottimistica.** Fill, slippage, market impact e costi devono essere conservativi. L'ingresso tardivo suggerisce che lo slippage strutturale possa superare i costi espliciti oggi contabilizzati.
- **Multiple testing.** Guardare sette orizzonti e scegliere il migliore ex post inflaziona il segnale. La curva completa serve solo all'esplorazione iniziale; il test successivo deve avere un unico orizzonte primario.
- **Dipendenza temporale.** I forward return a 3 e 5 giorni si sovrappongono; SE ingenue e conteggi nominali sovrastimano la potenza.
- **Cambio di popolazione.** I fix al resolver possono migliorare l'IC semplicemente selezionando un'altra popolazione. È corretto per costruire la strategia futura, ma vieta di concatenare ingenuamente il segmento pre-fix con quello post-fix.
- **Qualità non osservabile completamente.** La pulizia automatica deve essere verificata su un campione etichettato; “post-fix” non significa automaticamente “corretto”.
- **Overlap con S1.** Se S4 compra gli stessi nomi più tardi, il suo P&L standalone sovrastima il contributo incrementale al portafoglio. Serve misurare valore marginale, capitale occupato e correlazione degli intenti.
- **Ritardo decisionale.** Un test prudente può richiedere circa dieci mesi di sedute. Il costo è perdere un eventuale edge debole; ridurre arbitrariamente `n` per rispettare una scadenza amministrativa trasferisce però il rischio dalla pazienza al falso positivo.
- **Regime shift.** Accumulare più giorni non garantisce stazionarietà. Vanno riportati stabilità per sottoperiodo e decadimento, senza usare tali split per ottimizzare ex post.
- **Governance di #179.** Cambiare criterio dopo aver visto dati sfavorevoli è pericoloso; mantenerne uno noto come incoerente lo è altrettanto. La sostituzione deve essere esplicita, motivata e timestampata.
- **Confusione tra test tecnico e test economico.** Tenuta mediana, mix delle uscite e turnover dicono se B è implementata; non dimostrano alpha. IC e P&L netto dicono se l'alpha è monetizzabile; non garantiscono che il sistema live funzioni.
- **A non è definitivamente confutata per ogni tipo di news.** La conclusione riguarda soprattutto news editoriale tardiva. Uno split per fonte primaria potrebbe identificare una sottoclasse intraday, ma richiederebbe una nuova ipotesi, dati e pipeline dedicati.

## Decisione per l'operatore

Mettere S4 in **shadow reversibile**, eseguendo virtualmente una sola configurazione B a **2 sedute**, dopo fix e pre-registrazione. Non usare il 28/09 come verdetto sull'alpha. Riattivare soltanto con integrità operativa dimostrata, `IC ≥ 0,05` con inferenza HAC robusta e performance netta incrementale con intervallo di confidenza positivo. Fino ad allora, B resta l'ipotesi economica più plausibile, non una strategia validata.
