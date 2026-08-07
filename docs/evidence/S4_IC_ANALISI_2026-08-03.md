# S4 — Il segnale di sentiment predice i rendimenti? Misura diretta

Data: 2026-08-03
Tipo: **calibrazione** (stima e intervallo), non test confermativo — nessun budget di test multipli consumato
Dati: `sentiment_signals` dal 2026-06-15 al 2026-07-31, solo lettura

## Perché questa analisi prima del preventivo sugli archivi

Il programma prevedeva uno *studio di fattibilità dati per S4*: quanto costerebbe un archivio news
storico per poter backtestare la strategia. Prima di preventivare l'acquisto conviene chiedersi se il
segnale che vorremmo backtestare abbia contenuto — e questo si misura **con i dati che abbiamo già**,
a costo zero.

## Metodo

`forward_return` è definito nel worker come rendimento a **n giorni di borsa**:
`(close_{T+n} − close_T) / close_T`, con n ∈ {1, 3, 5}. Sono già popolati: 5.790 segnali su 6.084.

**Una scelta che decide la validità del risultato.** Ci sono più segnali per lo stesso simbolo nello
stesso giorno, e condividono lo stesso forward return: trattarli come indipendenti gonfierebbe la
significatività di un ordine di grandezza. Ho quindi:

1. ridotto a **una osservazione per simbolo-giorno**, tenendo l'**ultimo** segnale del giorno — che è
   esattamente quello che il ranker usa in produzione;
2. calcolato lo **Spearman cross-sectional giorno per giorno** (l'IC standard);
3. mediato sui giorni, con t = media / (dev.std / √giorni).

Risultato: **2.002 osservazioni simbolo-giorno su 34 giorni** — circa 59 simboli al giorno, coerente
con la copertura news nota (55-60 ticker su 96).

## Risultati

| sottoinsieme | orizzonte | giorni | IC medio | dev.std | t |
|---|---|---:|---:|---:|---:|
| tutti | 1g | 34 | −0,0181 | 0,139 | −0,76 |
| tutti | 3g | 32 | −0,0104 | 0,142 | −0,42 |
| tutti | 5g | 30 | −0,0264 | 0,133 | −1,09 |
| solo ensemble | 1g | 34 | −0,0064 | 0,254 | −0,15 |
| solo ensemble | 3g | 32 | +0,0150 | 0,220 | +0,39 |
| solo ensemble | 5g | 30 | +0,0173 | 0,192 | +0,49 |
| solo fallback | 1g | 31 | −0,0202 | 0,249 | −0,45 |
| solo fallback | 3g | 29 | −0,0612 | 0,266 | −1,24 |
| solo fallback | 5g | 27 | −0,0632 | 0,232 | −1,42 |
| \|score\| ≥ 0,30 | 1g | 26 | +0,0270 | 0,272 | +0,51 |
| \|score\| ≥ 0,30 | 3g | 25 | +0,0296 | 0,309 | +0,48 |
| \|score\| ≥ 0,30 | 5g | 25 | +0,0637 | 0,308 | +1,03 |

**Nessun IC raggiunge la significatività.** Le stime puntuali oscillano attorno a zero e il segno
cambia fra sottoinsiemi e orizzonti.

### Due letture direzionali, non significative ma coerenti col disegno

I segnali **fallback hanno IC negativo su tutti e tre gli orizzonti** (−0,020, −0,061, −0,063). È
l'argomento empirico a favore della regola **#108**, che li esclude dal ranking BUY: finora quella
regola poggiava su un incidente singolo (SPCX, 2026-07-01), ora c'è una misura che va nella stessa
direzione. Resta non significativa.

I segnali **ad alta convinzione (|score| ≥ 0,30) sono gli unici positivi**, e crescono con
l'orizzonte (+0,027 → +0,030 → +0,064). Se il segnale avesse contenuto, ci si aspetterebbe proprio
questo. Con t = 1,03 al massimo, non è evidenza — è la direzione che varrà la pena riguardare quando
il campione sarà cresciuto.

## Il vincolo di potenza — il vero risultato

Con la deviazione standard giornaliera dell'IC misurata (≈0,14), l'IC minimo rilevabile a |t| = 3:

| campione | giorni | IC rilevabile |
|---|---:|---:|
| **oggi** | 34 | **0,072** |
| 1 anno | 250 | 0,027 |
| 5 anni | 1.250 | 0,012 |
| 10 anni | 2.500 | 0,008 |

L'IC tipico di un segnale azionario in letteratura è **0,02-0,05**.

**Con 34 giorni non potremmo rilevare un segnale tipico nemmeno se ci fosse in pieno.** L'esito
corretto non è «il sentiment non funziona», ma: *l'IC è probabilmente sotto 0,07, e sotto quella
soglia questi dati non distinguono nulla.*

## Conseguenze

**Per la domanda di uscita n.1 della pre-registrazione** («esiste alpha nella news editoriale su
questa watchlist?»): **non è rispondibile entro il 2026-09-28**. Alla scadenza dei 40 giorni avremo
~75 giorni di campione, che rileva IC > 0,048 — ancora sopra il grosso della banda tipica. La domanda
richiede almeno un anno di raccolta.

**Per lo studio di fattibilità degli archivi storici:** il valore di un archivio è esattamente questo
guadagno di potenza. Ma esiste un'alternativa molto più economica che non era stata considerata —
**continuare a raccogliere**. Il sistema genera ~59 osservazioni simbolo-giorno al giorno da solo, e
in un anno di funzionamento raggiungerebbe la stessa potenza di un archivio storico di un anno, senza
costruire nulla, senza acquistare nulla e senza ri-scorare anni di articoli con l'ensemble (che era
la voce di costo dominante del preventivo).

L'archivio storico conserva un vantaggio: darebbe **subito** cinque anni invece di aspettarne uno. La
domanda diventa quindi se valga la pena pagare per anticipare la risposta di ~4 anni, sapendo che nel
frattempo il sistema gira comunque.

## Limiti dichiarati

- **34 giorni sono pochi**, ed è il punto dell'analisi. Ogni numero qui è una stima con un intervallo
  ampio, non una conclusione.
- L'analisi gira su dati che abbiamo già esaminato a lungo (i report alpha-miss). L'IC è però una
  domanda diversa dalla classificazione dei miss, ed è la metrica standard, non una scelta
  post-hoc fra molte.
- Il periodo coperto (metà giugno - fine luglio 2026) contiene una stagione di trimestrali e una
  forte rotazione settoriale: non è necessariamente rappresentativo.
- `forward_return` salta i simboli senza barre giornaliere disponibili (alcuni ETF e ADR), quindi il
  campione è leggermente diverso dall'universo tradato.
- Non ho misurato l'IC **al netto dei costi**: un IC positivo ma piccolo può essere economicamente
  nullo dopo spread e commissioni.
