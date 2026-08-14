# S4 — decisione sull'orizzonte: risposta (Claude Opus 5)

**Data:** 2026-08-14 · **Prompt:** `docs/S4_DECISIONE_ORIZZONTE_PROMPT_ESTERNO_2026-08-13.md` · **Issue:** #242

> Risposta prodotta senza accesso al repo o al DB, sul solo contenuto del documento, e senza leggere
> le risposte degli altri modelli presenti nella stessa cartella.

---

## Risposta compatta (formato richiesto)

```
SCELTA:            B — orizzonte dichiarato 2 sedute, close-to-close, con regola d'uscita esplicita.
                   A è esclusa su meccanismo (§3.4) e su aritmetica dei costi (vedi §D2 qui sotto);
                   C è prematura perché anticipa un criterio pre-registrato che non ha ancora sparato
                   e perché su conto carta l'esecuzione è lo strumento più economico che abbiamo per
                   scoprire difetti d'implementazione.

CONFIDENZA:        media sull'esclusione di A (argomento di meccanismo, non statistico)
                   bassa su "B batte C" (nessuna delle due è sostenuta da evidenza di alpha;
                   B vince per valore d'osservazione e per coerenza col criterio, non per attesa di P&L)

CRITERIO DI FALSIFICAZIONE:
                   quattro criteri pre-registrati (F-B1..F-B4, §2). Tre su quattro sono decidibili
                   entro il 28/09 perché misurano l'implementazione e i costi, non l'alpha.
                   Il quarto (struttura a termine dell'IC) NON è decidibile entro il 28/09 e lo
                   dichiaro esplicitamente.

RIMISURA DELL'IC:  popolazione = quella *negoziata* (solo-ensemble ∩ |score| ≥ 0,30), non "tutti i
                   segnali ensemble"; prezzi = eseguibili (fill o prima barra 15m successiva), non
                   prezzo al timestamp del segnale; orizzonti = {1h, 4h, close, 1g, 2g, 3g, 5g};
                   SE corretta per sovrapposizione (Newey-West o campionamento non sovrapposto);
                   n minimo per t=2: ~120 sedute con N≈20 nomi/giorno, ~55 sedute se N sale a 40.

L'EVIDENZA BASTA?  No per la domanda "S4 ha alpha" — e non basterà nemmeno il 28/09, né a n=73.
                   Sì per la domanda "quale orizzonte", che si decide su meccanismo e costi.
                   La misura mancante di gran lunga più utile è retrospettiva e già disponibile in DB:
                   la struttura a termine dell'IC sulla popolazione negoziata a prezzi eseguibili,
                   con lo split articolo-singolo/articolo-multiplo. Costa giorni, non settimane, e
                   zero esposizione.

SEQUENZA DI DEPLOY: (0) studio retrospettivo IC — nessun deploy, nessuna discontinuità;
                   (1) riscrittura pre-registrata di #179 *prima* del deploy;
                   (2) un unico deploy datato che contiene insieme le correzioni di qualità del dato
                       (#236/#246) e il pacchetto orizzonte (clock DAILY su S4 + regola d'uscita
                       esplicita + fix QS-07/FIX-D), con lato-ingresso congelato;
                   (3) freeze totale fino al 28/09, con reportistica settimanale sulle sole metriche
                       che convergono a piccolo n.
                   Motivo del bundle in §5.

COSA HO IGNORATO:  §3.1 come misura economica, il confronto +209/−769, la t=−4,96, la magnitudine
                   del controfattuale "all'apertura", il NAV +221, la tabella settimanale come trend.
                   Dettagli e ragioni in §6.

DISSENSO:          sei punti in §7. I due che contano: (D2) il documento **sottostima** l'argomento
                   dei costi contro A — espresso in unità di IC l'ostacolo a 4h è ≈0,038, cioè
                   grosso modo pari al miglior IC mai osservato; (D3) il criterio #179 è debole non
                   per l'n ma per la **popolazione**: misura un insieme il cui IC è ~6× più piccolo
                   di quello che S4 negozia davvero.
```

---

## 1. La scelta, e perché

### 1.1 Riformulo la domanda

Il documento presenta tre opzioni simmetriche. Non lo sono. La domanda vera è composta da due
domande separabili, che il documento tiene incollate:

1. **Dove può stare l'alpha, se c'è?** — domanda di meccanismo. Si risponde senza test di
   significatività.
2. **Vale la pena eseguire mentre lo scopriamo?** — domanda di valore dell'informazione, non di P&L
   atteso.

La prima esclude A. La seconda decide fra B e C. Tenerle unite è ciò che rende la decisione più
difficile di quanto sia.

### 1.2 A è esclusa, e non serve la statistica per farlo

La §3.4 è il fatto portante dell'intero documento, e non dipende da nessun test:

- 70–84% del movimento **intraday** è già avvenuto al primo punteggio utile;
- su ORCL e NOK la frazione supera il 100%: al primo segnale il prezzo aveva già oltrepassato la
  chiusura;
- il 08-12, il 99% mediano del movimento stava nel **gap di apertura**, con la gamba intraday piatta
  o negativa su 7 su 9;
- il controllo di latenza chiude la porta all'obiezione tecnica: il giorno con la migliore latenza
  mai misurata (39,6 min contro ~100) ha comunque frazione 82%.

Una strategia con orizzonte 1–4 ore su news editoriale compra il movimento già avvenuto. Questa è
una conclusione di meccanismo: per rovesciarla non serve più `n`, serve una fonte diversa. Il che
significa che **A non è un cambio di orizzonte, è un progetto nuovo** — nuove fonti (filing,
earnings, revisioni), nuova pipeline di latenza, nuova validazione. Non è realizzabile né misurabile
entro il 28/09, e proporlo come uno dei tre rami di una decisione di orizzonte inflaziona
artificialmente il ventaglio.

C'è un secondo argomento contro A, quantitativo, che il documento accenna ma sottostima. Lo sviluppo
in §7 (D2): espresso come IC richiesto, il costo di transazione a 4h è ≈0,038, cioè circa pari al
miglior IC che sia mai stato osservato in tutta la tabella §3.5.

### 1.3 Perché non C

C è l'opzione seria, e va presa sul serio. La sua forma più forte è questa:

> Tutto ciò che decide la sorte di S4 — l'IC a qualunque orizzonte, la qualità della popolazione di
> segnali, la sovrapposizione con S1 in termini di *intenti* — è calcolabile **senza eseguire un solo
> ordine**. L'esecuzione produce solo P&L realizzato, che il documento stesso dichiara troppo rumoroso
> per decidere qualcosa (§6.1, §6.6). Quindi l'esecuzione non compra informazione e costa. Shadow
> domina.

L'argomento è quasi corretto. Gli manca un pezzo, e il pezzo è decisivo:

**Su un conto carta, l'esecuzione è lo strumento più economico che abbiamo per scoprire difetti di
implementazione, e ogni scoperta sostanziale di questo documento viene da lì.** Il difetto
QS-07/FIX-D (uscite `unknown`), la collisione col guard anti-pyramiding (21 intenti su 30), l'effetto
del percentile d'ingresso (64,3° mediano), il fatto che tre uscite su quattro siano artefatti: niente
di tutto questo sarebbe emerso in shadow. In shadow avremmo avuto la tabella §3.5 e nient'altro.

Il prezzo di quella osservabilità: ~99 $ di costi su ~23 sedute = ~4,3 $/giorno, su una sleeve da
~11.000 $. Sotto B il turnover crolla e il costo scende verso ~1,2 $/giorno. Per denaro finto, è
poco per continuare a vedere come si rompe il sistema.

**Se il conto fosse denaro vero e in scala, la risposta sarebbe C.** Questa distinzione va scritta
nella decisione, perché è la condizione sotto cui la mia raccomandazione si inverte.

Il secondo argomento contro C è di disciplina, e conta: il criterio di kill è pre-registrato al
2026-08-06, *prima del dato*, e prevede shadow se la media degli IC solo-ensemble è ≤ 0 a n ≥ 73.
Oggi vale +0,0078 e n = 38. Passare a shadow adesso significa **inasprire ex post un criterio
pre-registrato dopo aver visto la settimana peggiore della storia della sleeve (n=9)**. È esattamente
il fallimento che la pre-registrazione esiste per prevenire, e il fatto che la direzione sia
"prudente" non lo rende meno un fallimento: un criterio che può essere anticipato quando i dati
recenti sono brutti non è un criterio.

Nota importante e non simmetrica: questo argomento vieta di *anticipare* C, non di *riscrivere* il
criterio. Riscrivere #179 per renderlo coerente (orizzonte, popolazione, prezzi, SE) è legittimo e
necessario — a condizione che la riscrittura avvenga **prima** di guardare i dati riscritti, e che sia
depositata come nuova pre-registrazione. È il punto (1) della sequenza in §5.

### 1.4 Perché B, e quale B esattamente

B è l'unica opzione sotto cui il criterio #179 smette di essere un errore di categoria. Oggi il
criterio misura 1/3/5 giorni e la strategia dura 4h15: non è un criterio poco potente, è un criterio
che misura un'altra cosa. Allineare la strategia all'orizzonte misurato è il movimento minimo che
rende valido il test già depositato.

Ci sono tre segnali indipendenti che puntano tutti nella stessa direzione (più lungo, non più corto):

1. **La struttura a termine dell'IC sulla popolazione che negoziamo cresce con l'orizzonte:**
   alta convinzione ≥0,30 → +0,0434 (1g) → +0,0465 (3g) → +0,0624 (5g). Monotona. Non significativa,
   ma è l'unico segnale di forma presente nella tabella, ed è quello del sottoinsieme che effettivamente
   riceve ordini.
2. **Il meccanismo lo prevede.** Se la notizia arriva a movimento avvenuto (§3.4), l'unico alpha
   residuo plausibile non è il salto — è la deriva post-evento, che si misura in giorni.
3. **I costi lo premiano.** L'ostacolo in unità di IC scende da ≈0,038 (4h) a ≈0,021 (2 sedute) a
   ≈0,013 (5 sedute) — derivazione in §7/D2. A 2 sedute l'IC osservato coprirebbe i costi ~2×;
   a 4 ore li copre a malapena.

**La forma concreta di B che raccomando:**

| elemento | valore | nota |
|---|---|---|
| orizzonte dichiarato | **2 sedute**, uscita alla chiusura di D+2 | dentro la forcella 1–3g su cui l'IC è già misurato |
| `rebalance_frequency` | DAILY, **applicata** — S4 entra nel clock | oggi dichiarata e non applicata |
| `max_signal_age_hours` | resta come filtro di **ingresso**, cessa di essere driver d'uscita | non si liquida perché Benzinga ha smesso di pubblicare |
| regola d'uscita esplicita | time-stop a 2 sedute **OR** contro-segnale ≤ −0,30 **OR** stop di rischio | il time-stop è la regola primaria; le altre sono eccezioni |
| QS-07/FIX-D | corretto | senza questo l'orizzonte non è tenibile: un filtro di freschezza chiuderebbe comunque |
| lato ingresso | **congelato** — `bucket_pct`, `n_top`, `fixed_slot_sizing`, soglia 0,30, coppia LLM | unica variabile che cambia = l'uscita |

Perché 2 sedute e non 3 o 5, dato che l'IC cresce fino a 5g: (a) l'IC a 5g è la riga meno affidabile
di tutta la tabella per sovrapposizione dei rendimenti forward (§4/M4); (b) con 5 slot e capitale
bloccato più a lungo la sovrapposizione con S1 peggiora, ed è già l'ipotesi non smentita più
minacciosa del documento (§5.6); (c) 2 sedute produce ~2,5 ingressi/giorno, flusso sufficiente ad
accumulare `n` per la misura. È una scelta di compromesso dichiarata, non derivata.

**Cosa B non è.** B non è una scommessa sul fatto che S4 abbia alpha. Non ho evidenza per crederlo e
non la avrò entro il 28/09. B è la configurazione sotto cui, se un giorno l'evidenza arriverà, sarà
interpretabile: uscite deliberate invece che artefatti, costi che non mangiano un terzo del lordo,
orizzonte uguale a quello del criterio.

---

## 2. Criterio di falsificazione

Pre-registrati qui, prima del deploy. Tre su quattro sono decidibili entro il 28/09 **perché non
misurano l'alpha**: misurano se B è stata davvero implementata e se l'economia della sleeve migliora.
Quello che misura l'alpha non è decidibile entro il 28/09 e lo dichiaro.

### F-B1 — implementazione (n = 15 sedute post-deploy; decidibile ~05/09)

Sulle prime 15 sedute dopo il deploy, tutte e tre:

- tenuta mediana ≥ **1,5 sedute** (oggi 4h15);
- chiusure/settimana ≤ **10** (oggi ~18: 81 chiusure / ~4,5 settimane);
- mix dei motivi d'uscita: ≥ **80%** attribuibile alla regola dichiarata (time-stop / contro-segnale /
  stop) e < **5%** a `expired` o `unknown`.

Se una delle tre fallisce, B non è stata implementata — non è stata falsificata. Rimedio: correggere
l'implementazione, non cambiare opzione. Se falliscono dopo una seconda correzione, si passa a C:
significa che l'architettura non consente di tenere una posizione per un orizzonte dichiarato, che è
di per sé un motivo sufficiente per non eseguire.

### F-B2 — economia del turnover (n = 30 sedute; decidibile ~26/09)

Costi espliciti ≤ **15%** del lordo realizzato della sleeve (oggi 99,02/209,11 = **47%**), equivalente
a ≤ ~1,5 $/giorno di costi sulla sleeve.

Se i costi restano > 30% del lordo, B fallisce sull'economia anche se l'IC fosse positivo: significa
che l'orizzonte non si è allungato abbastanza per cambiare l'aritmetica. Rimedio: 5 sedute, o C.

### F-B3 — struttura a termine dell'IC (**non decidibile entro il 28/09** — lo dichiaro)

Sulla popolazione negoziata, a prezzi eseguibili, con SE corretta per sovrapposizione:

- se **IC(4h) − IC(2g) > +0,02** → B è falsificata **in direzione di A**, e la conclusione operativa
  non è "torna a 4 ore con le fonti attuali" ma "l'alpha è nel salto, quindi serve la pipeline
  event-driven di A prima di eseguire qualunque cosa";
- se **media[IC(1g), IC(2g), IC(3g)] ≤ 0** con n ≥ **120 sedute** (o n ≥ 55 se N/giorno ≥ 40) → B è
  falsificata **in direzione di C**.

La parte retrospettiva di F-B3 (dati già in DB, §4) va calcolata **prima** del deploy e **prima** che
questo criterio venga considerato depositato: se lo studio retrospettivo mostra già IC(4h) ≫ IC(2g),
il deploy non va fatto e la risposta diventa "nessuna delle tre finché non esiste la fonte di A".

### F-B4 — diversificazione (n ≥ 150 intenti, ~20 sedute; decidibile entro il 28/09)

Se > **50%** degli intenti S4 continua a puntare su nomi già detenuti da S1 (oggi 21/30 = 70% su n=30,
non conclusivo), S4 non diversifica: replica S1 con un orizzonte più corto e costi più alti. Rimedio
pre-registrato: carve-out d'universo (S4 negozia solo i nomi che S1 non detiene) — da decidere dopo il
28/09, non ora, per non introdurre una seconda variabile.

### Interruttore di rischio (non è evidenza)

P&L netto realizzato cumulato di S4 post-deploy < **−400 $** (≈ −0,36% del NAV, ~4× la settimana
peggiore) → sospensione e revisione. Va registrato come controllo di rischio, non come falsificazione:
a questi `n` non distingue sfortuna da difetto.

---

## 3. Come va rimisurato l'IC

Il problema di #179 non è principalmente `n`. Sono quattro cose, in ordine di importanza.

### M1 — la popolazione (il problema più grave)

#179 misura **"solo ensemble"**, media dei tre orizzonti = **+0,0078**. S4 negozia **"solo ensemble ∩
score ≥ 0,30"**, che nella tabella §3.5 vale **+0,0434 / +0,0465 / +0,0624**: circa **6× più grande**.
Il criterio che deciderà la sorte di S4 misura una popolazione che S4 non compra.

La misura primaria deve essere sulla popolazione negoziata. La popolazione "tutti gli ensemble" resta
come diagnostica secondaria — è informativa sul modello, non sulla strategia.

Serve inoltre la tabella 2×2 completa che il documento non riporta: {ensemble, fallback} ×
{≥0,30, <0,30}, con conteggi. Oggi non sappiamo se la riga "alta convinzione" sia contaminata dal
fallback FinBERT (IC −0,03/−0,08/−0,08). Se lo è, il vero IC ensemble ad alta convinzione è ancora
più alto di quello riportato — e la sottostima di #179 è ancora peggiore di 6×.

### M2 — i prezzi (rende la misura una misura della *strategia*)

L'IC va calcolato dal **prezzo eseguibile**: il fill effettivo, o in mancanza la chiusura della prima
barra 15m successiva al segnale. Non dal prezzo al timestamp del segnale.

Motivo: la §3.3 dimostra che l'ingresso avviene sistematicamente al 64,3° percentile mediano del range
di giornata. Un IC calcolato dal prezzo al segnale misura la notizia; un IC calcolato dal prezzo
eseguibile misura la strategia. La differenza fra i due **è** lo slippage strutturale della sleeve, e
va riportata come numero separato — è probabilmente la voce di costo più grande e oggi non è nel
conto dei 99 $.

### M3 — gli orizzonti

`h ∈ {1h, 4h, close-del-giorno, 1g, 2g, 3g, 5g}`, tutti insieme, riportati come **curva**, non come tre
punti scelti. La forma della curva è l'informazione: monotona crescente → B; picco a 4h e decadimento
→ A (e quindi, in pratica, nessun deploy); piatta attorno a zero ovunque → C.

Rendimenti misurati contro la media della sezione trasversale di giornata — cosa che lo Spearman
cross-sectional già fa per costruzione, e che va mantenuta perché su 96 large-cap long-only il beta
domina tutto.

### M4 — l'errore standard e la potenza (qui sta l'aritmetica scomoda)

Sotto H₀, la deviazione standard di uno Spearman giornaliero su N nomi è ≈ 1/√(N−1). L'MDE dichiarato
dal documento (0,10–0,12 a t=3 con n=38) implica **N ≈ 20 nomi/giorno effettivi**:
`3 × 0,229 / √38 = 0,111` ✓. La cifra del documento è internamente coerente, e la uso per proiettare.

| scenario | SE della media | MDE a t=3 | MDE a t=2 |
|---|---:|---:|---:|
| n=38, N≈20 (oggi) | 0,037 | 0,111 | 0,074 |
| **n=73, N≈20 (il gate di #179)** | **0,027** | **0,080** | **0,054** |
| n=120, N≈20 | 0,021 | 0,063 | 0,042 |
| n=73, **N≈40** | 0,019 | 0,057 | 0,038 |
| n=120, N≈40 | 0,015 | 0,044 | 0,029 |

Tre conseguenze:

1. **A n=73, con la popolazione di #179, il test resta muto.** MDE a t=3 = 0,080, contro un valore
   osservato di +0,0078. Il gate n=73 non compra potenza: compra l'aspetto di una decisione. È un
   test di segno su una media rumorosa, e va chiamato così nel testo del criterio.
2. **Cambiare popolazione compra più potenza che aspettare.** Con la popolazione negoziata (IC 0,043–0,062)
   e t=2, a n=73 l'MDE è 0,054: il valore a 5g (0,0624) ci passa sopra. Non è dimostrazione, ma per la
   prima volta il test ha qualcosa da vedere.
3. **Portare N da ~20 a ~40 vale più di qualunque parametro.** Con 51 simboli su 96 senza una riga di
   news in giornata (§3.6), la copertura è il collo di bottiglia statistico dell'intero progetto:
   raddoppiare N a n=73 porta l'MDE a t=2 da 0,054 a 0,038. **Riparare la copertura news è il singolo
   intervento con il maggior ritorno in potenza statistica disponibile.**

E la correzione che nessuno ha applicato: **i rendimenti forward a 3 e 5 giorni su osservazioni
giornaliere si sovrappongono.** Le SE ingenue sottostimano di ~√3 e ~√5. Con Newey-West (lag = h) o
con campionamento non sovrapposto, l'`n` effettivo a 5g è ~38/5 ≈ 8. **La riga IC 5g è la meno
affidabile della tabella, non la più promettente**, ed è proprio quella su cui la forma monotona
sembra più forte. È una ragione concreta per fissare l'orizzonte a 2 sedute e non a 5.

### n minimo, dichiarato

- **Test primario** (popolazione negoziata, h=2g, prezzi eseguibili, SE corretta, N≈20):
  **n ≥ 120 sedute** per t=2 su un IC vero di 0,05. Con N ≥ 40: **n ≥ 55 sedute**.
- **Test di significatività pieno** (t=3): n ≥ 250 sedute a N≈20, ~120 a N≈40.
- **Nessuno dei due è raggiungibile entro il 28/09** (~31 sedute residue). Va scritto nel criterio.

### Riscrittura proposta di #179

> A n ≥ 120 sedute con N ≥ 20 nomi/giorno, sulla popolazione negoziata (ensemble ∩ score ≥ 0,30), a
> prezzi eseguibili, con SE Newey-West lag=h: se la media di IC(1g), IC(2g), IC(3g) è ≤ 0, S4 passa a
> shadow. Il gate intermedio a n=73 non è un test di significatività (MDE a t=2 = 0,054 con la
> popolazione negoziata, 0,080 con quella originale) e produce solo un verdetto di segno: può
> raccomandare, non decidere. La decisione al 28/09 si prende sui criteri F-B1, F-B2 e F-B4, che
> misurano implementazione, costi e diversificazione, non alpha.

---

## 4. L'evidenza basta?

**No** per "S4 ha alpha" — e la parte importante è che **non basterà nemmeno il 28/09, né a n=73**
(§3/M4). Chi pianifica la decisione aspettandosi che il tempo la risolva sta pianificando su una
premessa falsa.

**Sì** per "quale orizzonte", perché quella domanda si decide su meccanismo (§3.4) e su aritmetica dei
costi (§7/D2), e nessuno dei due ha bisogno di significatività.

### Misure mancanti, ordinate per valore diviso tempo

| # | misura | dati | tempo | cosa cambierebbe |
|---|---|---|---|---|
| 1 | **Struttura a termine dell'IC** sulla popolazione negoziata, a prezzi eseguibili, h ∈ {1h,4h,close,1g,2g,3g,5g}, SE corretta per sovrapposizione | già in DB (`sentiment_signals` + barre Alpaca) | **1–3 giorni, zero esposizione** | è il gate del deploy. Picco a 4h → non deployare B |
| 2 | **Split articolo-singolo vs multi-ticker** (405 su 816 righe = 49,6% sono liste/rassegne/13F), + esclusione MS/GS finché il resolver non è corretto | stessi dati, stessa esecuzione | incluso in (1) | quantifica quanta parte dell'IC≈0 è rumore a monte. `n` si dimezza ma il rumore potrebbe calare di più |
| 3 | **Distribuzione di N nomi/giorno** nella sezione trasversale | stessi dati | incluso in (1) | senza questo tutti i calcoli di potenza sono stime |
| 4 | **Slippage strutturale**: differenza fra IC a prezzo-segnale e IC a prezzo-eseguibile | stessi dati | incluso in (1) | è il costo che oggi non compare nei 99 $ |
| 5 | **Sovrapposizione S1∩S4** su tutta la storia, non 2 giorni (n ≥ 300 intenti) | decision log | giorni | il 70% su n=30 diventa un fatto o sparisce |
| 6 | **Tabella 2×2** {ensemble,fallback} × {≥0,30,<0,30} con conteggi | s4_ic.json + query | ore | dice se la riga "alta convinzione" è contaminata dal fallback |
| 7 | IC post-correzioni resolver (#236/#246) | richiede deploy | settimane; `n` utile non prima del 2027 | non arriva in tempo per questa decisione |

I punti 1–4 sono la stessa esecuzione. **È il lavoro più redditizio dell'intero documento e non
richiede di deployare né di esporre capitale.** Va fatto prima di qualunque deploy, e il suo esito è
un gate sul deploy stesso (§2/F-B3).

Il punto 7 è la ragione per cui S4 non può essere ucciso "sui dati": qualunque IC misurato oggi è
misurato su una popolazione in cui il 97% delle righe MS e il 97% delle righe GS non parlano di quelle
società, e in cui un articolo su Lumentum chiude una posizione su Nvidia. Non stiamo misurando
l'assenza di alpha nella news: stiamo misurando un'attribuzione rotta. Le due cose sono
indistinguibili con i dati attuali, e questa è l'affermazione più solida che posso fare sull'intera
§3.5.

---

## 5. Sequenza di deploy

Vincolo §5.5: osservazione fino al 28/09 (~31 sedute residue dal 14/08), un unico cambiamento datato,
lasciare almeno un segmento confrontabile.

### Passo 0 — studio retrospettivo (giorni 0–3, nessun deploy, nessuna discontinuità)

Misure 1–4 e 6 di §4. Esito con tre rami:

- curva IC monotona crescente da 4h a 2g → si procede al passo 1;
- picco a 4h con decadimento → **non si deploya**, e la risposta a #242 diventa "né B né C: l'alpha
  è nel salto, serve la pipeline event-driven di A, che non è costruibile entro il 28/09";
- curva piatta e indistinguibile da zero anche sulla popolazione pulita e negoziata → si procede
  comunque al passo 1, perché il piatto è il caso atteso a questo `n` e non è informativo.

### Passo 1 — riscrittura pre-registrata di #179 (prima del deploy, prima di guardare i risultati)

Il testo proposto in §3. È fondamentale che avvenga **prima** che i risultati del passo 0 vengano
letti: un criterio riscritto dopo aver visto i dati non è un criterio.

### Passo 2 — un solo deploy datato, con dentro tutto

Contenuto, in un'unica data:

1. correzioni qualità del dato (#236/#246): resolver, dedup, articoli multi-ticker;
2. S4 nel clock di ribilanciamento (DAILY applicata, non più 15 min);
3. regola d'uscita esplicita: time-stop 2 sedute / contro-segnale ≤ −0,30 / stop;
4. `max_signal_age_hours` degradato da driver d'uscita a filtro d'ingresso;
5. fix QS-07/FIX-D;
6. **lato ingresso congelato**: `bucket_pct`, `n_top`, `fixed_slot_sizing`, soglia 0,30, coppia LLM
   — nessuno di questi si tocca.

**Perché tutto insieme, incluse le correzioni dati.** L'obiezione ovvia è che le correzioni dati
cambiano la popolazione d'ingresso e il pacchetto orizzonte cambia l'uscita: unirli impedisce di
attribuire. Rispondo con tre argomenti:

- **Nessuno dei due segmenti è comunque decidibile.** 31 sedute residue divise in due fanno due
  segmenti da ~15. A n=15 non è misurabile nulla, nemmeno con un ordine di grandezza di margine
  (§3/M4). Separare i deploy per attribuire su segmenti che non possono attribuire niente compra zero
  e costa una discontinuità in più.
- **La separazione si ottiene analiticamente, non temporalmente.** Il passo 0 misura l'IC su dato
  sporco e su dato pulito *sugli stessi giorni storici*. Questo è un confronto pulito che due deploy
  separati non produrrebbero comunque (perché cadrebbero su periodi diversi con mercati diversi).
- **Lasciare vive per sei settimane 122 righe MS di cui 4 vere e 65 righe GS di cui 2 non è
  neutralità: è avvelenare deliberatamente l'unica finestra di osservazione rimasta.** Ogni trade su
  MS e GS — i due ticker più coperti dell'intera watchlist — è rumore puro che entra nella serie che
  vogliamo osservare.

Il segmento confrontabile richiesto dalla §5.5 c'è ed è quello **pre-deploy**: 13/07 → data del
deploy, ~23 sedute con lato ingresso identico. È l'unico confronto che si può costruire, ed è la
ragione per cui il lato ingresso va congelato.

### Passo 3 — freeze fino al 28/09, con la reportistica giusta

Nessun altro cambiamento su S4. Report settimanale sulle sole metriche che convergono a piccolo `n`,
cioè quelle di F-B1/F-B2/F-B4:

- chiusure/settimana, tenuta mediana, mix dei motivi d'uscita;
- costi / lordo realizzato;
- percentuale di intenti S4 che collidono con il book S1;
- percentile d'ingresso mediano (deve peggiorare o restare uguale sotto B — non è il target, ma è la
  diagnostica dello slippage).

**Il P&L settimanale va riportato e non va usato per decidere.** Va scritto esplicitamente accanto al
numero, ogni settimana, altrimenti verrà usato.

### Passo 4 — 28/09

Decisione su F-B1, F-B2, F-B4. **Non** su P&L, **non** su IC (che a quella data avrà n ≈ 60 sedute
totali, sotto il minimo di 120). Il carve-out d'universo contro S1 si valuta qui, se F-B4 ha sparato.

---

## 6. Cosa ho ignorato

| numero | uso che ne ho fatto | perché |
|---|---|---|
| §3.1 — 9 chiusure, 8 in perdita, −89,12 $ | usato **solo** per la forma (6 uscite su 9 a 1h45 o 4h15 esatte = 7 o 17 cicli: firma di un'uscita meccanica, non decisa) | §6.1: settimana peggiore su cinque, n=9. La magnitudine non è stimabile |
| +209,11 $ (S4) contro −769 $ (S1) | **scartato del tutto** | §6.6: il realizzato di S1 è avversamente selezionato. Non compare in nessun mio argomento, nemmeno in quello contro C |
| t = −4,96 sull'ora d'ingresso | **non usato** | §6.7: 87 su 129 osservazioni sono coorte legacy, 33 da un solo giorno |
| controfattuale "all'apertura" (+186,42 / delta +196,68) | usato come **segno**, non come magnitudine: conferma ordinalmente la §3.4 | §6.4: usa informazione futura. Il segno resta informativo perché concorda con una misura indipendente |
| NAV +221 $ | non usato | dominato dal MTM di S1, non dice nulla su S4 |
| tabella settimanale (5 punti) | usata solo per confermare che l'ultima settimana è la coda, mai come trend | 5 punti settimanali non mostrano decadimento |
| tenuta mediana S1 (~5 giorni / 24h — le due cifre nel documento non concordano) | non usata | discrepanza interna al documento, §3.1 dice ~5 giorni e §3.2 dice 24h. Segnalata, non usata |
| 21/30 sovrapposizione S1∩S4 | usata come **ipotesi da testare** (F-B4), non come fatto | §6.5: n=30 su 2 giorni |
| IC "tutti i segnali" e "solo fallback" | usati come diagnostica del modello, non come input della decisione | non è la popolazione negoziata |

---

## 7. Dissenso

Obbligatorio, e ne ho sei. I primi due cambiano la sostanza.

### D1 — le tre opzioni non sono simmetriche, e presentarle così gonfia A

B e C condividono infrastruttura, fonti e strumento di misura: differiscono solo per un interruttore
(eseguire o no). A richiede fonti nuove, latenza nuova, pipeline nuova e criterio nuovo. La struttura
reale è: **{A = progetto nuovo, non realizzabile entro il 28/09} vs {B, C = stessa misura, eseguo o
non eseguo}**. Il documento presenta un trilemma dove c'è una decisione binaria più una proposta di
progetto futuro, e questo ha probabilmente allungato la discussione.

### D2 — il documento **sottostima** l'argomento dei costi contro A (dissenso in direzione opposta all'attesa)

La §4/A dice che «la sensibilità ai costi cresce» e cita il 32% del lordo. Tradotto in unità di IC
l'argomento è molto più forte, e il documento non lo traduce.

Derivazione, dai soli numeri del documento più due assunzioni dichiarate:

- costo per giro: 99,02 $ / 81 chiusure = **1,22 $**; posizione = 2% × 110.000 = **2.200 $** →
  **5,6 bp per giro**;
- selezione top-5 su N ≈ 20 → media degli z dei primi 5 su 20 ≈ **1,27**
  (media della normale standard sopra il 75° percentile: φ(0,674)/0,25);
- dispersione cross-sectional giornaliera dei rendimenti large-cap: **σ ≈ 1,5%** (assunzione);
- edge atteso ≈ IC × 1,27 × σ(h).

| orizzonte | σ(h) | edge ≈ IC × … | **IC richiesto per pareggiare 5,6 bp** | IC osservato (≥0,30) |
|---|---:|---:|---:|---:|
| 4 ore | 1,16% | IC × 1,47% | **0,038** | non misurato |
| 1 giorno | 1,50% | IC × 1,90% | **0,029** | 0,0434 |
| 2 sedute | 2,12% | IC × 2,69% | **0,021** | ~0,045 (interp.) |
| 5 sedute | 3,35% | IC × 4,26% | **0,013** | 0,0624 |

Sensibilità: con σ = 2% invece di 1,5% gli ostacoli scendono di ~25% (0,028 / 0,022 / 0,016 / 0,010) —
la conclusione ordinale non cambia.

Lettura: **all'orizzonte attuale l'ostacolo di costo (0,038) è grosso modo pari al miglior IC mai
osservato in tutta la tabella §3.5 (0,0434 a 1g).** Non "i costi crescono": *a 4 ore il lordo atteso di
S4 è all'incirca il suo costo*. E i 5,6 bp non includono lo slippage strutturale del 64,3° percentile
d'ingresso, quindi il numero vero è peggiore.

Corollario meno comodo: lo stesso calcolo dice che, a 2–5 sedute, i costi **non** sono il vincolo
stringente (coperti ~2–5×). Il vincolo lì è se l'IC esiste. I due argomenti vanno tenuti separati: i
costi escludono A, non sostengono B.

### D3 — #179 è debole per la **popolazione**, non per l'`n`, e il documento diagnostica la cosa sbagliata

Il documento dice: «il criterio misura un orizzonte che la strategia non ha mai avuto». Vero, ma
incompleto. Il difetto più grande è che misura **"tutti i segnali ensemble" (IC medio +0,0078)** mentre
S4 negozia **"ensemble ∩ score ≥ 0,30" (IC +0,043 / +0,047 / +0,062)** — una popolazione con IC ~6×
maggiore. Correggere l'orizzonte lasciando la popolazione sbagliata produrrebbe un criterio ancora
inutile.

E il gate n=73 non fa quello che si crede: MDE a t=3 = 0,080 con la popolazione di #179, contro un
valore osservato di +0,0078. **Il 28/09, e poi a n=73, il test sarà sostanzialmente altrettanto muto
di oggi.** #179 così com'è è un test di segno travestito da test di significatività, e la cosa va
scritta nel corpo del criterio prima che spari, non dopo.

### D4 — «in nessuno dei quattro casi il modello ha detto vendi» diagnostica il difetto sbagliato

Per un overlay long-only su news, l'assenza di un segnale di vendita è *attesa*: non si può pretendere
che il flusso di notizie produca un'uscita a comando. Il difetto non è che manchi il "vendi": è che
**l'uscita è delegata alla cadenza editoriale di un terzo**. La formulazione del documento suggerisce
che il rimedio sia un segnale di vendita; il rimedio corretto è una regola d'uscita derivata
dall'orizzonte che **non dipende affatto dal segnale**. È una differenza operativa, non retorica:
determina cosa si costruisce.

### D5 — la qualità del dato non può essere dichiarata «non oggetto di questa decisione»

La §3.6 la mette fuori perimetro. Con il 49,6% delle righe da articoli multi-ticker, il 97% di falsi
positivi sui due ticker più coperti dell'universo, e un articolo su Lumentum che chiude una posizione
su Nvidia, **la popolazione di segnali di S4 non è la popolazione che qualcuno ha progettato.** Scegliere
un orizzonte per un segnale la cui definizione è rotta è, in linea di principio, prematuro.

Non blocco la decisione su questo, per due ragioni: lo studio retrospettivo del passo 0 può ricostruire
analiticamente la popolazione pulita senza deployare, e le correzioni entrano comunque nel deploy del
passo 2. Ma la conseguenza va accettata: **nessun IC misurato prima di quel deploy è evidenza
sull'alpha della news**, e questo include il +0,0078 su cui #179 sta per decidere.

### D6 — la §3.4 è ben supportata ma generalizza oltre il misurato (dissenso contro il mio stesso argomento portante)

«L'articolo viene scritto *perché* il movimento è avvenuto» è convincente per la news editoriale ed è
supportato dal controllo di latenza. Ma è asserito come proposizione generale su tutta la fonte, e
Benzinga veicola anche materiale primario (earnings, guidance, halt) dove il timestamp precede la
diffusione. Non è stato fatto lo split per tipo di articolo.

Questo conta perché la §3.4 è il fatto su cui io escludo A. Il test corretto — frazione del movimento
già avvenuta, **separata per tipo di articolo** — va aggiunto al passo 0. Se esistesse una sottoclasse
di articoli primari con frazione ≪ 70%, allora A tornerebbe in gioco *ristretta a quella sottoclasse*,
e la conclusione non sarebbe più «S4 non può essere intraday» ma «S4 può essere intraday solo su una
frazione delle sue fonti attuali, e va misurato quanto sia grande quella frazione».

Lo dichiaro come la condizione più probabile per cui la mia risposta sia sbagliata.

---

## 8. Riepilogo in una pagina

1. **A è esclusa su meccanismo**: la notizia arriva dopo il 70–99% del movimento, e la latenza non
   c'entra. Confermato dall'aritmetica: a 4 ore l'ostacolo di costo in unità di IC (≈0,038) è pari al
   miglior IC osservato.
2. **C è prematura**: anticipa un criterio pre-registrato che non ha sparato, dopo la settimana
   peggiore con n=9; e su conto carta l'esecuzione è lo strumento più economico che abbiamo per
   trovare difetti d'implementazione — ogni scoperta di questo documento viene da lì. *Su denaro vero
   e in scala la risposta sarebbe C.*
3. **B a 2 sedute**, con regola d'uscita esplicita, clock DAILY applicato, fix QS-07/FIX-D, e lato
   ingresso congelato. Non è una scommessa sull'alpha: è la configurazione sotto cui una misura
   futura sarebbe interpretabile.
4. **Prima del deploy**, tre giorni di studio retrospettivo su dati già in DB: struttura a termine
   dell'IC sulla popolazione negoziata, a prezzi eseguibili, con split articolo-singolo/multiplo e
   per tipo di articolo. È il gate del deploy e la misura più redditizia disponibile.
5. **#179 va riscritto prima**, cambiando prima di tutto la **popolazione** (×6 di IC), poi
   l'orizzonte, poi i prezzi, poi la correzione per sovrapposizione. E va scritto dentro il criterio
   che a n=73 il test non è decisivo.
6. **Un solo deploy datato**, con dentro anche le correzioni dati: due segmenti da 15 sedute non
   decidono niente, e la separazione si ottiene analiticamente al passo 0 invece che temporalmente.
7. **Il 28/09 si decide su implementazione, costi e sovrapposizione** — le uniche cose che convergono
   a questo `n`. Non su P&L, non su IC.
