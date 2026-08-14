# S4 — consolidamento critico delle strategie di uscita

**Data di consolidamento:** 2026-08-14

**Perimetro:** sintesi critica dei quattro report indipendenti di Claude Opus, Codex gpt-5.6-sol, GLM-5.2 e Qwen3.5. Non sono state aggiunte fonti esterne.

**Decisione operativa in una frase:** usare **D+2 come tenuta massima**, non come durata obbligatoria; eliminare come trigger ordinari silenzio, scadenza editoriale, rank drop e target-weight zero; consentire un'uscita anticipata solo a un contro-segnale qualificato; mantenere l'eventuale `d_hard` come overlay di rischio comune e separato dal test dell'alpha.

**Report analizzati:** [Claude Opus](risposte/opus_analisi_exit_s4_2026-08-14.md) · [Codex gpt-5.6-sol](risposte/codex_analisi_exit_s4_2026-08-14.md) · [GLM-5.2](risposte/glm52_analisi_exit_s4_2026-08-14.md) · [Qwen3.5](risposte/qwen35_analisi_exit_s4_2026-08-14.md).

## 1. SINTESI DELLE RACCOMANDAZIONI

| Modello | Policy raccomandata | Confidenza dichiarata | Valutazione critica della raccomandazione |
|---|---|---|---|
| **Claude Opus** | `MODIFY`: **D+2 close come tenuta massima**, contro-segnale asimmetrico, nessuno stop protettivo ordinario. Il disaster stop broker resta comune alle varianti e fuori dal confronto primario. Propone `−0,30` per il contro-segnale e separa il test dell'uscita dal test dell'alpha. | Alta sulla direzione; media sui parametri. | È la proposta più parsimoniosa e quella che identifica meglio l'effetto dell'uscita. È anche la più esplicita sul rischio reale osservato: un gap non viene neutralizzato da uno stop. La giustificazione della soglia `−0,30` tramite simmetria con l'ingresso è però debole: long-only, costi e asimmetria delle news non implicano una soglia simmetrica. |
| **Codex gpt-5.6-sol** | `MODIFY`: **E1M**, D+2 in session clock, nessuna uscita per silenzio/rank drop, contro-segnale nuovo, ensemble, entity-resolved e collegato alla tesi; catastrophe stop largo determinato dal risk budget; nessun take-profit. Metrica primaria: delta netto appaiato contro E0. | Media. | È il disegno più rigoroso sul piano decisionale: introduce un MDE economico e distingue `PROMOTE`, `REJECT` e `INCONCLUSIVE`. Il limite è operativo: novelty e thesis linkage point-in-time non sono oggi dimostrati disponibili; includere anche lo stop nella primaria crea un trattamento composto se lo stop non è identico al benchmark. |
| **GLM-5.2** | `MODIFY`: **E1-mod**, D+2 + contro-segnale costruito come posteriore della tesi con persistenza di almeno due cicli e banda state-dependent sul VIX + `d_hard`; confronto con D+2 senza contro-segnale e con E0. Mantiene il gate IC e circa 213 sedute. | Moderata sul processo e sul time-stop; bassa sul contro-segnale implementato. | Ha la migliore ablation del contro-segnale: questo componente deve “guadagnarsi il posto” contro il time-stop puro. Il posteriore e la banda VIX sono però più sofisticati dei dati disponibili: con news sparse il posteriore rischia di essere il prior travestito da misura, mentre il regime-gating aggiunge una seconda ipotesi non identificata. Il vincolo di 213 sedute deriva dall'IC e non dalla varianza del confronto di uscita. |
| **Qwen3.5** | **Shadow reversibile immediato** della configurazione D+2 + contro-segnale `≤−0,30` + catastrophe stop; D+2 resta ipotesi primaria e non verità economica. Shortlist E1, counter-signal only ed E5. | Media sullo shadow; media-bassa su D+2 come optimum. | È correttamente prudente sul deployment e insiste sullo shadow end-to-end. È meno rigoroso nell'identificazione: assume l'IC D+2 come metrica primaria dell'uscita, propone un early stop a `t≥3` e confronta policy che non isolano bene i componenti. La condizione chiamata “falsificazione” falsifica lo stato di shadow, non la tesi economica di D+2. |

La convergenza nominale su D+2 non va letta come quattro conferme indipendenti del parametro. I report condividono in larga parte le stesse fonti e lo stesso packet Alembic. Il valore della convergenza è quindi **strutturale** — serve un orizzonte espresso in sedute — non probatorio sul numero esatto di sedute.

## 2. CONVERGENZE

### 2.1 Convergenze forti

1. **La policy corrente E0 non è una vera exit policy.** Il target-weight zero aggrega eventi economicamente diversi: invalidazione della tesi, scadenza/freshness, rank truncation, replacement, collisione S1, filtro, dato perso e bug. Una SELL così prodotta non può essere interpretata come prova che l'alpha sia decaduto.
2. **D+2 è una baseline ragionevole, non un optimum dimostrato.** Il punto robusto è sostituire le scadenze software di 4 ore e i cicli da 15 minuti con un clock di sedute. D+2 rende l'orizzonte una decisione economica e impone un limite alla coda di holding; non dimostra che il rendimento marginale D+1→D+2 sia positivo.
3. **Target-weight/rank drop non deve essere una thesis exit.** Se il capitale è scarso, il replacement va misurato ed etichettato come decisione di capacità, non fatto passare per falsificazione della news originaria.
4. **Separazione fra tesi, tempo e rischio.** Il contro-segnale risponde a “la tesi è stata smentita?”; il time-stop a “l'orizzonte è terminato?”; il catastrophe stop a “il rischio residuo è compatibile col mandato?”. Fondere questi rami impedisce di sapere quale componente ha prodotto il risultato.
5. **Il silenzio non è un segnale contrario.** `max_signal_age` è appropriato per l'eleggibilità dell'ingresso. L'assenza di una nuova storia non deve vendere una posizione, a meno che il mancato update sia definito ex ante come evento informativo e source uptime/coverage siano osservabili.
6. **Stop stretti, take-profit fisso e trailing non sono candidati di prima linea.** Il replay interno e gli argomenti dei report non sostengono lo stop ordinario 2%; il take-profit +6% dipendente dalla frazionabilità è un confound; trailing e scale-out aggiungono parametri e rischiano di troncare la coda destra.
7. **Il test corretto dell'uscita è appaiato a ingressi congelati.** Stesso intento, fill, timestamp, notional e costo d'ingresso per ogni policy; soltanto il lifecycle post-fill può divergere. L'IC resta diagnostica dell'ingresso e non identifica il contributo della regola di uscita.
8. **Serve shadow end-to-end e non un calcolo offline dell'IC.** Il percorso deve replicare selection, ranking, collisione S1, fill virtuale, ordini concorrenti, costi, clock e reason code fino al confine broker.
9. **Dipendenza e multiple testing non sono dettagli.** Gli articoli sullo stesso evento/ticker-giorno non sono unità indipendenti; forward return sovrapposti richiedono trattamento coerente; tutti i trial già osservati devono entrare nel registro.

### 2.2 Convergenze con riserve

- Un **contro-segnale** è concettualmente legittimo solo se rappresenta informazione nuova e pertinente alla tesi. Non c'è invece evidenza sufficiente che il crossing di un singolo ultimo score a `−0,20`, `−0,30` o `−0,35` sia già tale.
- Un **catastrophe stop largo** può essere legittimo come controllo operativo della coda, ma non come fonte di expected return. La perdita WDC citata nei report è gap-driven: uno stop-market non garantisce il trigger e può non ridurre materialmente la perdita.
- **D+1 e D+3** sono utili per vedere se D+2 è su un plateau o su un picco fragile, ma non devono diventare vincitori promuovibili sullo stesso campione usato per esplorarli.

## 3. DISSENSI

### 3.1 Criterio di falsificazione

- **Opus** falsifica la tesi soprattutto con la decomposizione intraday/overnight: overnight medio non positivo rende debole l'argomento principale per D+2. È un ottimo diagnostico economico immediato, ma non basta come test della policy complessiva.
- **Codex** usa il criterio decisionale più esigente: a numerosità pianificata, il limite superiore dell'intervallo del delta appaiato non deve raggiungere l'MDE per dichiarare la policy economicamente inutile; il limite inferiore deve superarlo per promuovere. È il criterio più pulito perché distingue assenza di evidenza, irrilevanza economica e beneficio dimostrato.
- **GLM** richiede che E1-mod batta la variante senza contro-segnale e conserva IC `≥0,05`, `t≥3` e circa 213 sedute. L'ablation è rigorosa; il gate IC, invece, risponde principalmente alla domanda “S4 ha alpha?”, non “questa uscita è migliore?”.
- **Qwen** condiziona il passaggio da shadow a live agli stessi gate IC/economia e propone anche early stopping. È prudente come governance, ma statisticamente meno pulito: un `t≥3` osservato in anticipo senza alpha-spending predefinito aumenta l'errore di primo tipo.

### 3.2 Orizzonte e definizione del clock

- D+2 è sostenuto come prior da tutti i report, ma **Codex e GLM** insistono maggiormente sul rischio che per la gamba long positiva D+1 sia sufficiente; **Opus** sottolinea invece il valore di attraversare la componente overnight e di porre un tetto a holding illimitati.
- “D+2” non è sempre semanticamente esplicitato allo stesso modo. La definizione consolidata deve essere: `D0` è la seduta del primo fill RTH eseguibile; time-exit alla close della **seconda seduta successiva a D0**, usando un'esecuzione realmente ottenibile.
- GLM consente che una diagnostica pre-confirmatoria sposti la primaria a D+1. È ammissibile solo se usa un campione separato e la scelta viene congelata prima di `n=0`; altrimenti è selezione ex post.

### 3.3 Forma del contro-segnale

- **Opus** preferisce una soglia semplice `−0,30`; **Codex** richiede novelty, entity resolution e thesis linkage; **GLM** aggiunge posteriore, persistenza e banda VIX; **Qwen** mantiene una soglia puntuale `≤−0,30`.
- Il posteriore GLM è teoricamente elegante ma non oggi identificato: la densità di news per ticker può essere insufficiente e la funzione di aggiornamento non è specificata. Una soglia semplice è implementabile ma vulnerabile all'ultimo-articolo-rumoroso. La soluzione consolidata è un **proxy minimo qualificato**, non un falso posteriore: ensemble non-fallback, ticker-valid, nuova informazione riferibile all'evento/tesi, soglia congelata, conferma operativa su due valutazioni consecutive. Quest'ultima è solo un *debounce* contro glitch transitori: lo stesso record ripetuto non conta come seconda evidenza.
- I report identificano **tre valori concorrenti** della soglia (`−0,20`, `−0,30`, `−0,35`). Nessun risultato è interpretabile finché config dichiarata, runtime e shadow non coincidono.

### 3.4 Catastrophe stop

- Opus lo rimuove dalla definizione della challenger primaria; Codex, GLM e Qwen lo includono. La differenza è più di governance che economica.
- La soluzione identificabile è tenerlo **identico in tutte le policy**, se il risk owner lo richiede, e misurarne separatamente fill, gap slippage e copertura. Se varia fra policy, il confronto non identifica più il time-stop o il contro-segnale.

### 3.5 Shortlist e protocollo

- Opus propone tre challenger (`E1′`, buy/hold spread, stop largo); Codex una sola challenger primaria contro E0; GLM E1-mod contro D+2 senza counter e contro E0; Qwen E1, counter-only ed E5.
- La shortlist GLM è la più informativa causalmente perché contiene l'ablation del contro-segnale. Quella Opus consuma trial su un hold-threshold fissato in modo arbitrario; quella Qwen non contiene un confronto pulito D+2 con/senza counter; quella Codex minimizza correttamente la molteplicità ma non stima il valore incrementale del counter.
- Opus e Codex separano power dell'exit e power dell'IC; GLM e Qwen mantengono le circa 213 sedute del test IC. Questa è la divergenza metodologica più importante.

## 4. ANALISI CRITICA

### 4.1 Robustezza delle policy

**Più robusta come nucleo: D+2 time-only, con E0 come benchmark.** È semplice, auditabile, non dipende dalla frequenza editoriale e affronta due failure mode opposti della policy corrente: churn intraday e holding senza limite. Ha un solo parametro sostanziale, espresso in sedute. Il suo difetto è assumere un orizzonte uniforme per news eterogenee; per questo D+2 deve essere chiamato prior falsificabile e non optimum.

**Più robusta come policy operativa candidata: D+2 + contro-segnale qualificato.** Ha senso permettere l'uscita anticipata quando arriva informazione realmente contraria. Tuttavia, la robustezza deriva dalla qualificazione, non dal numero `−0,30`: un singolo score non pertinente può replicare il problema “last article wins”. Entity resolution, provenance, novelty e linkage devono essere disponibili point-in-time; in loro assenza il counter va escluso dalla prima versione, non ricostruito post hoc.

**Catastrophe stop: robusto come controllo, debole come exit alpha.** Un limite largo può proteggere da discesa continua quando l'applicazione è indisponibile, ma non limita il prezzo di fill dopo un gap. Inoltre la copertura sembra dipendere da quantity/fractionability e può lasciare residui. Deve essere governato dal risk budget e non ottimizzato sul rendimento medio.

**E1-mod con posteriore e VIX: promettente ma prematura.** È la formulazione teoricamente più ricca, ma aggiunge stato non osservato, una funzione di filtro, una persistenza e una frontiera di regime. La banda VIX confonde rischio comune e validità della tesi; la letteratura citata dagli stessi report non sostiene in modo stabile il volatility management OOS. Senza una serie densa di update e un posterior calibrato, la complessità è decorativa e abbassa la falsificabilità.

**Counter-only: non robusta senza un massimo holding.** Se il contro-segnale è raro, produce zombie positions e blocco di capitale; con un massimo holding finito diventa una variante del time-stop. È utile come diagnostica del meccanismo, non come policy deployabile indipendente.

**Buy/hold spread e de-risking parziale: buone idee di seconda generazione.** Una soglia di mantenimento più permissiva dell'ingresso è coerente con costi e no-trade regions, ma `h_hold=h_entry/2` non è derivato dai dati S4. Il de-risking parziale richiede un expected-edge/posterior calibrato e, alla size attuale, può moltiplicare ordini senza valore misurabile.

**D+1/D+3 e policy event-type: informazione, non decisione immediata.** D+1 è la vera alternativa economica a D+2 perché testa il rendimento marginale dell'overnight aggiuntivo. D+3 verifica persistenza. Entrambe devono restare diagnostiche sul primo campione. Le policy per event type potrebbero essere superiori in teoria, ma oggi frammenterebbero un campione già piccolo e richiedono un classifier point-in-time non validato.

**Take-profit e trailing: non giustificati.** Nessun report porta evidenza S4-specifica sufficiente a compensare il rischio di troncare pochi grandi vincitori. Il TP +6% applicato solo a strumenti non-fractionable rende inoltre il trattamento non omogeneo.

### 4.2 Rigore dei criteri di falsificazione

Il criterio MDE/intervallo di Codex è superiore a un semplice `p<0,05`, a un IC threshold e a una decomposizione descrittiva. Obbliga il decisore a dire **prima** quale beneficio minimo giustifica capitale, complessità e rischio. Produce tre esiti corretti:

- `PROMOTE`: limite inferiore unilaterale del delta appaiato netto sopra l'MDE, con gate di rischio/costi/integrità soddisfatti;
- `REJECT`: limite superiore sotto o uguale all'MDE, quindi anche lo scenario favorevole non è abbastanza utile;
- `INCONCLUSIVE`: l'intervallo attraversa la regione decisionale; non è prova di equivalenza né autorizzazione a scegliere il backtest migliore.

La decomposizione overnight proposta da Opus resta il **miglior falsificatore diagnostico del razionale D+2**: se il contributo overnight post-fill è stabilmente non positivo, la motivazione per sostenere due chiusure perde forza. Non sostituisce però il test paired netto e i gate di capitale/rischio.

Il confronto GLM `con counter` vs `senza counter` è il miglior falsificatore del **componente counter**. Va incorporato gerarchicamente dopo avere testato il nucleo time-stop, non fuso in un confronto omnibus che non dica quale componente funziona.

## 5. RACCOMANDAZIONE CONSOLIDATA

### 5.1 Policy

Se S4 supera separatamente i gate per meritare capitale, la policy di uscita raccomandata è:

1. **D+2 come tenuta massima.** `D0` è la seduta del primo fill RTH eseguibile; uscita alla close della seconda seduta successiva. Half-day, festività e cutoff broker sono trattati con calendario di mercato. Se la close non è ottenibile, si usa il primo prezzo successivo realisticamente eseguibile, non il closing print teorico.
2. **Nessuna SELL per:** silenzio della fonte, `max_signal_age`, assenza dal top-5, rank drop, `expired`, `unknown`, semplice crossing sotto l'entry gate o target-weight zero. Questi eventi possono impedire un nuovo ingresso, non falsificano quello esistente.
3. **Unica uscita ordinaria anticipata:** contro-segnale qualificato, definito ex ante come ensemble non-fallback, ticker-valid, basato su informazione nuova e pertinente alla tesi/evento originario, score `≤−0,30`, confermato su due valutazioni consecutive. La soglia `−0,30` è una convenzione congelata per il test, non una soglia ottima; config, runtime e shadow devono coincidere.
4. **Risk overlay separato:** l'eventuale `d_hard` broker resta attivo solo se richiesto dal risk budget, con identica regola in E0 e in tutte le challenger. Non è attribuito alla policy di alpha. Stop sintetico stretto, TP fisso, trailing e scale-out restano disattivati nel test.
5. **Replacement separato:** se un nuovo candidato compete per uno slot, registrare opportunity cost e reason `replacement`; non confonderlo con una thesis exit nel test primario. Il test di uscita congela gli ingressi e non reinveste automaticamente il capitale liberato.

### 5.2 Decisione immediata

- Avviare solo **shadow end-to-end**, dopo un batch atomico che chiuda le divergenze soglia/clock/ordini e congeli la pipeline a monte.
- Non attendere il gate IC per scegliere il disegno dell'uscita: il paired exit test ha una varianza propria. Il gate IC resta necessario per decidere se S4 merita capitale.
- Se il contro-segnale qualificato non è implementabile point-in-time al sample start, partire con la variante **D+2 time-only**; non usare label o linkage ricostruiti dopo l'evento.

## 6. SHORTLIST DI POLICY

Per limitare la molteplicità, il confirmatory comprende **esattamente tre policy, inclusa la baseline**. L'overlay `d_hard`, se imposto dal risk owner, è identico in tutte e tre.

| Policy | Specifica | Domanda identificata | Motivazione |
|---|---|---|---|
| **P0 — E0 congelata** | Comportamento as-is versionato al sample start: target-weight zero e relativi guard, riprodotto in shadow sugli stessi ingressi. | Quanto vale sostituire il comportamento emergente corrente? | È il benchmark operativo reale. Non è una candidata da promuovere e va scartata come benchmark se i lifecycle non sono ricostruibili. |
| **P1 — D+2 time-only** | D+2 massimo; nessuna uscita per silenzio/rank/freshness; nessun counter ordinario. | Il clock economico da solo batte E0? | È il trattamento più parsimonioso e isola il valore del time-stop. Evita che un counter rumoroso faccia fallire una buona regola temporale. |
| **P2 — D+2 + counter qualificato** | P1 + contro-segnale qualificato come definito in §5.1. | Il contro-segnale aggiunge valore rispetto al time-stop puro? | È la candidata operativa completa, ma il componente counter viene mantenuto solo se supera P1 nel confronto appaiato. |

**Fuori dalla famiglia confirmatoria:** D+1 e D+3 sono robustness diagnostics non promuovibili; la decomposizione intraday/overnight è diagnostica; E4 aggregata, posterior/VIX, trailing, event-type e de-risking richiedono una nuova pre-registrazione e un nuovo campione.

Questa shortlist è preferibile a tre challenger senza baseline: con pochi eventi, spendere trial su buy/hold spread, trailing o stop calibrati riduce potenza senza rispondere alla prima domanda causale — se un time-stop deterministico è migliore dell'E0 corrente.

## 7. CRITERIO DI FALSIFICAZIONE

### 7.1 Criterio primario

Definire prima del sample start un **MDE netto economicamente rilevante** in bps del notional per trade, scelto dal capital/risk owner e non ricavato dal miglior backtest. Per ciascun intento `i`:

`Δ1_i = r_net(P1)_i − r_net(P0)_i`

`Δ2_i = r_net(P2)_i − r_net(P1)_i`

L'inferenza usa cluster event-day e un intervallo unilaterale al 95% ottenuto con block bootstrap pre-specificato.

- **P1 è falsificata come miglioramento utile** se, al numero di cluster pianificato, `UCB95(Δ1) ≤ MDE_time`. È promuovibile solo se `LCB95(Δ1) > MDE_time` e tutti i gate non-inferenziali tengono.
- **Il counter è falsificato** se `UCB95(Δ2) ≤ MDE_counter` o se peggiora il false-exit budget. Entra nella policy finale solo se `LCB95(Δ2) > MDE_counter`; altrimenti si adotta P1, non si elimina il time-stop.
- Se l'intervallo attraversa l'MDE, l'esito è **`INCONCLUSIVE`**. Non si promuove, non si dichiara equivalenza e non si cerca D+1/D+3 sullo stesso campione.

`MDE_counter` può essere zero solo se il counter non aggiunge complessità/costi materiali; in caso contrario deve coprirli. Un gate di coda può bocciare P1/P2 anche in presenza di rendimento medio positivo, ma un miglior ES non può compensare il fallimento del rendimento se l'obiettivo dichiarato è alpha.

### 7.2 Falsificatori diagnostici

- rendimento overnight post-fill medio non positivo e contributo marginale D+1→D+2 non positivo dopo costi;
- beneficio concentrato in meno di tre eventi o nel solo miglior 5% dei trade senza stabilità cronologica;
- segno del delta invertito fra sottoperiodi predefiniti;
- quasi tutte le uscite P2 determinate dal counter e nessuna dal time-stop, oppure counter con recovery frequente entro l'orizzonte della tesi;
- valore incrementale netto rispetto a S1 non positivo dopo capitale-giorni e overlap.

Questi diagnostici possono impedire la promozione o motivare una nuova ipotesi; non autorizzano a riscrivere la primaria sul campione osservato.

## 8. PROTOCOLLO EMPIRICO

### 8.1 Ledger point-in-time

L'unità base è un **entry intent eleggibile**, non un articolo e non un round trip selezionato ex post. Il ledger deve essere append-only/versionato e contenere almeno:

- **Identità e provenance:** `intent_id`, `signal_id`, `event_id`, `article_id`, ticker risolto, versione/metodo del resolver, relazione articolo-ticker, source primaria/derivata, hash del contenuto, numero di ticker associati.
- **Timestamp originali:** `published_at`, `first_seen/ingested_at`, `model_generated_at`, `decision_at`, `intent_at`, broker ack e `fill_at`, con timezone e sessione. Non collassare questi tempi.
- **Stato informativo:** score, confidence, modelli ensemble, fallback, novelty point-in-time, thesis/event linkage, score successivi e identificativo dell'articolo che li ha prodotti. Conservare tutta la sequenza, non soltanto l'ultimo score.
- **Eleggibilità e contesto:** universo, gate, top-5/rank, slot, size, collisione/overlap S1, candidati esclusi e reason, source uptime/coverage, regime, volatilità, liquidità, spread e percentile del range al fill.
- **Esecuzione:** decision price, prima quote/bar eseguibile, fill virtuale, qty/notional, partial fill, fee, spread, slippage, fractionability, bracket/stop parent e legs, status/cancel/reject, quantità effettivamente protetta.
- **Path:** barre intraday abbastanza fini, daily total return con corporate actions, MAE/MFE e tempi, gap overnight, halt/LULD/delisting, primo trigger e tutti i trigger concorrenti.
- **Outcome per policy:** decision/fill/price/reason di P0/P1/P2, P&L lordo e netto, capitale-giorni, componente intraday/overnight, post-exit drift a 1h/close/D+1/D+2/D+3/D+5.
- **Censura e qualità:** missingness e motivo, ambiguità intrabar, lifecycle ricostruibile, differenza shadow/runtime, label disponibili al tempo della decisione e label solo post-hoc.

### 8.2 Costruzione dei controfattuali

1. Stessi intenti, fill, notional e costi d'ingresso per P0/P1/P2. Nessuna policy può cambiare chi entra o il prezzo iniziale.
2. Il capitale liberato prima non viene automaticamente reinvestito nel test trade-level; l'opportunity cost è riportato separatamente a livello di portafoglio.
3. Primo trigger osservabile vince. Se i dati OHLC non ordinano counter/stop/time, usare dati più fini o marcare il caso ambiguo; mai scegliere il percorso favorevole.
4. Time-exit a prezzo d'asta solo se l'ordine era realmente presentabile entro il cutoff; altrimenti primo fill conservativo successivo.
5. Gap oltre stop: fill al primo prezzo eseguibile, non al trigger. Stop-limit non eseguito resta rischio aperto.
6. Half-day, festivi e weekend seguono il calendario di borsa; `max_signal_age` wall-clock non determina l'uscita.
7. Corporate actions, delisting e halt sono esiti economici o censure esplicite, mai osservazioni eliminate silenziosamente.

### 8.3 Metriche

**Primaria:** media dei delta appaiati netti `Δ1` e, gerarchicamente, `Δ2`, in bps del notional iniziale.

**Economia:** P&L totale e per trade, mediana, hit rate, expectancy, payoff, profit factor, turnover, costi, slippage, capitale-giorni, return on occupied capital, opportunity cost degli slot, excess return contro equal-weight watchlist e contributo marginale rispetto a S1.

**Rischio:** volatilità, downside deviation, max drawdown/durata, empirical VaR ed Expected Shortfall con intervalli, perdita massima per trade, gap loss, skewness e quota di P&L generata dal top 1/5/10% dei trade.

**Qualità dell'uscita:** false-exit rate, recovery entro l'orizzonte, giveback da MFE, perdita evitata rispetto a MAE, frequenza/cumulative incidence delle cause time/counter/risk/operational, quota `unknown`/`expired`.

**Diagnostiche:** IC post-fill a D+1/D+2/D+3, term structure, decomposizione intraday/overnight, source/novelty/event type/ora/gap/liquidità/regime. Gli split non possono salvare una primaria fallita.

### 8.4 Inferenza, potenza e multiple testing

- **Clustering:** giorno/evento come unità effettiva; ticker-day e articoli dello stesso evento non sono repliche indipendenti. Usare block/stationary bootstrap con schema e lunghezza fissati ex ante, coerenti con l'orizzonte D+2.
- **Forward sovrapposti:** IC e term structure richiedono HAC/Newey-West con lag coerente o una trasformazione non-overlapping; il bootstrap paired è preferibile per i delta di uscita.
- **Potenza:** stimare `σ_Δ` su storico/pilot usando soltanto la varianza, non la media o il ranking delle policy. Fissare `α` unilaterale, potenza almeno 80% (preferibilmente 90%), MDE e inflazione per dipendenza/missingness. Una sola revisione blinded della varianza può essere pre-registrata. Le circa **213 sedute** sono una stima per l'IC, non un requisito automatico per il paired exit delta.
- **Stopping:** nessun early stop per efficacia. Review intermedie solo su integrità, sicurezza e statistiche blinded. Se si desidera sequential monitoring, soglie e alpha-spending devono essere fissati prima; in assenza, l'analisi decisionale avviene una volta a `N_cluster`.
- **Molteplicità:** ordine gerarchico chiuso: prima P1 vs P0; solo se supera il gate si testa P2 vs P1. Questo è più potente e interpretabile di scegliere il massimo fra molte policy. SPA di Hansen è un controllo secondario sull'intera famiglia dichiarata; White RC come sensitivity. DSR vale soltanto per statistiche tipo Sharpe ed è secondario; PBO/CSCV è poco stabile con campione piccolo.
- **Trial ledger:** registrare ogni orizzonte, soglia, stop e analisi già vista, inclusi replay e diagnostiche dei quattro report. Le analisi D+1/D+3 non diventano OOS per rinomina.

### 8.5 Gate di deployment, separati dal test dell'uscita

Una policy statisticamente superiore non rende automaticamente S4 investibile. Servono congiuntamente:

1. almeno 95% dei lifecycle ricostruibili e zero divergenze materiali config/runtime/shadow;
2. `unknown` + uscite spurie sotto una tolleranza pre-registrata;
3. costi/slippage conservativi, incluso uno scenario stressato, che non annullino il delta;
4. ES, perdita massima, gap exposure e drawdown entro il risk budget fissato ex ante;
5. valore incrementale rispetto a S1 dopo overlap e capitale-giorni;
6. gate alpha di S4 valutato separatamente. Se l'ingresso non ha edge, una migliore uscita non giustifica l'attivazione.

## 9. PRE-REGISTRAZIONE

### 9.1 Oggetto e ipotesi

**Oggetto:** selezionare la regola di uscita per S4, condizionatamente al fatto che S4 superi i propri gate di investibilità.

**H1-time:** sugli stessi ingressi, P1 migliora P0 di almeno `MDE_time` bps netti per trade.

**H1-counter, gerarchica:** solo se H1-time supera il gate, P2 migliora P1 di almeno `MDE_counter` bps netti per trade senza violare il false-exit budget.

`MDE_time`, `MDE_counter`, risk budget e costo stressato sono valori del proprietario di capitale, registrati prima di vedere il forward. Non sono stimati dal miglior risultato storico.

### 9.2 Policy congelate

- **P0:** E0 versionata al sample start.
- **P1:** D+2 massimo, nessun counter, nessuna exit per silence/rank/freshness.
- **P2:** P1 + counter ensemble non-fallback, ticker-valid, new/thesis-linked, `score≤−0,30`, conferma per due valutazioni consecutive.
- `d_hard` identico in P0/P1/P2 se richiesto; nessun stop ordinario, TP, trailing, scale-out o regime exit per-trade.
- D+1, D+3, term structure e intraday/overnight sono diagnostiche non promuovibili.

### 9.3 Campione e sample start

`n=0` parte nella prima seduta completa successiva a un batch atomico timestampato che congela: resolver/entity validation, source mix, ensemble/fallback, gate, universo, sizing, collisione S1, cost model, calendar/clock, soglia counter, order semantics, shadow end-to-end e reason codes. Prima del batch:

- risolvere e verificare nel runtime la soglia `−0,20/−0,30/−0,35`;
- verificare che il clock DAILY/session-based sia realmente applicato a S4;
- riconciliare commento/config/codice e ordini broker per `d_hard` e TP +6%; neutralizzare il TP o renderlo identico/inattivo in tutte le policy;
- verificare che novelty/entity/thesis linkage usati da P2 esistano point-in-time; altrimenti P2 è rimossa **prima** di `n=0` e il test riguarda solo P1 vs P0.

Il segmento pre-fix serve a failure analysis e stima blinded della varianza; non si concatena al forward post-fix.

### 9.4 Analisi e stopping rule

- Metrica primaria: media di `Δ1`; metrica gerarchica: media di `Δ2`.
- Inferenza: block bootstrap event-day, CI unilaterale 95%, schema congelato.
- Numerosità: `N_cluster` derivato da MDE, `σ_Δ`, potenza e dipendenza; fissato prima di aprire i risultati, salvo una sola re-estimation blinded pre-specificata.
- Nessun early efficacy stop. Review di sicurezza possono interrompere per danno operativo, senza promuovere una policy.
- `PROMOTE P1` se `LCB95(Δ1)>MDE_time` e tutti i gate tengono. `ADD COUNTER` se inoltre `LCB95(Δ2)>MDE_counter` e false-exit/tail sono nei limiti.
- `REJECT` il relativo componente se `UCB95≤MDE`; `INCONCLUSIVE` negli altri casi.

### 9.5 Invalidazione e riavvio

Riavvio obbligatorio per qualunque modifica materiale a source, resolver, modello, score, gate, universo, sizing, collisione S1, fill model, costo, clock, soglia, exit, reason code o broker semantics; bug capace di cambiare osservazioni; divergenza shadow/runtime; missingness oltre tolleranza; uso di label future. Un outage completamente osservato, senza nuovi ingressi né alterazione dei lifecycle aperti, può produrre una pausa senza riavvio se questa regola è registrata.

### 9.6 Esiti dichiarati ex ante

- P1 utile, P2 utile: policy finale D+2 + counter qualificato.
- P1 utile, P2 non utile/inconclusive: policy finale D+2 time-only.
- P1 non utile: nessuna promozione; D+1/D+3 non vengono selezionate sullo stesso campione. Nuova ipotesi e nuovo forward.
- Gate alpha/S1 fallito: S4 resta spenta anche se una exit domina E0.

## 10. RISCHI E AVVERTENZE

1. **Una buona uscita non crea alpha.** I report segnalano timing tardivo, entity-resolution, articoli multi-ticker, fonte derivata/stale, fallback e overlap S1. Se l'ingresso è rumoroso o ridondante, ottimizzare la durata è una precisione applicata alla domanda sbagliata.
2. **Rischio di gap.** D+2 aggiunge esposizioni overnight rispetto al churn intraday, pur limitandole rispetto a holding senza tetto. Il disaster stop non garantisce il prezzo e può non attenuare un gap come WDC.
3. **Divergenze runtime bloccanti.** I report riportano `−0,20/−0,30/−0,35`, clock DAILY dichiarato ma non necessariamente applicato, `d_hard` descritto come shadow ma forse live e TP +6% dipendente dalla frazionabilità. Finché non sono riconciliati, E0 e le challenger non sono definiti.
4. **Benchmark E0 instabile.** Se bug e fix cambiano la popolazione o i reason code, E0 pre-fix e post-fix non sono la stessa policy. Va versionata al sample start.
5. **Contro-segnale raro o non osservabile.** Con news sparse, P2 può avere pochissimi eventi; due cicli non equivalgono a due news indipendenti. Un risultato inconclusivo non dimostra che il counter sia inutile.
6. **Right-tail concentration.** Una strategia news può dipendere da pochi grandi vincitori. Medie positive concentrate in pochissimi eventi, oppure TP/trailing che li tagliano, rendono il risultato fragile anche con un p-value favorevole.
7. **Capitale e S1.** D+2 occupa slot più a lungo. Il delta per trade può migliorare mentre il rendimento sul capitale occupato o il valore marginale rispetto a S1 peggiora.
8. **Bassa potenza e falsa precisione.** `n_trade` non è `n_effettivo`; la dipendenza per giorno/evento e i gap allargano gli intervalli. Le 213 sedute dell'IC non devono essere copiate sul test exit, ma nemmeno sostituite con 30–50 sedute senza una power analysis reale.
9. **Multiple testing retroattivo.** Le quattro analisi, le soglie discusse, il replay stop e le term structure sono trial informativi già visti. Devono essere registrati; cambiare policy dopo averli osservati richiede un nuovo forward.
10. **Shadow realism.** Closing auction, ordini GTC/OCO, partial fills, stop residuali, halts e reject broker possono rendere non eseguibile una policy che appare buona sulle barre.
11. **Eterogeneità delle news.** Un unico D+2 media eventi con decay diversi. La policy condizionata è rinviata per evitare overfitting, non perché l'eterogeneità sia irrilevante.
12. **Qualità disomogenea dei report.** Alcuni report contengono descrizioni non perfettamente coerenti fra audit e conclusioni, o dettagli bibliografici divergenti. Le conclusioni consolidate si basano sugli argomenti replicati e sulle evidenze Alembic comuni, non sull'autorità del modello né sul conteggio delle raccomandazioni.

**Conclusione operativa:** il passo corretto non è “attivare D+2 perché quattro modelli concordano”, ma congelare e testare una famiglia minima che dica *quale componente* crea valore. Prima il time-stop deterministico contro E0; poi, gerarchicamente, il contro-segnale qualificato contro il time-stop puro. Il rischio resta governato in parallelo e l'investibilità di S4 resta una decisione separata.
