# Periodo di osservazione, ledger delle evidenze e roadmap pesata — Design

Data: 2026-08-01
Stato: design approvato, implementazione non iniziata

## 1. Problema

Il sistema produce già due report giornalieri automatici:

| cron | orario | output |
|---|---|---|
| `scripts/daily_alpha_miss_analysis.sh` | 10:00, lun-ven | `docs/ALPHA_MISS_REPORT_YYYY-MM-DD.md` |
| `scripts/daily_analysis.sh` | 14:30, lun-ven | `docs/FORENSIC_DAILY_REPORT_YYYY-MM-DD.md` |

Entrambi terminano con una sezione di segnalazioni all'operatore ("§7 — Segnalazioni all'operatore
(nessun fix proposto)"). Il prompt dell'alpha-miss vieta esplicitamente alla sessione di proporre
fix: la decisione se aprire una issue è dell'operatore.

Il risultato è che esistono ~5 report alpha-miss e ~15 forensic, tutti in prosa libera, e **nessuna
segnalazione è contabile**. Non si può rispondere a "quante volte è ricomparso questo difetto" né
"quanto ci è costato in totale", quindi non si può ordinare il lavoro per peso — si ordina per
quale report si è letto per ultimo.

Due evidenze raccolte il 2026-07-31 motivano l'urgenza:

- Su due settimane (17-31 luglio) il conto si è mosso di ~$100 su $110K facendo 52 round trip. A
  quel rapporto segnale/rumore, ogni taratura fatta oggi è overfitting su rumore.
- La taratura più recente valutata (flip del cooldown di re-entry S1, #85) sarebbe stata
  **sbagliata**: bloccare i 3 rientri intercettati sarebbe costato $34.

## 2. Decisioni prese

Quattro decisioni prese con l'operatore il 2026-08-01, che vincolano il design:

1. **Uscita dal periodo di osservazione**: durata minima fissa **più** criteri pre-registrati. Non
   una soglia reattiva (farebbe ripartire lo sviluppo sul primo pattern rumoroso) né una durata
   secca (senza criteri decisi prima, alla scadenza si sceglie a sensazione).
2. **Perimetro del freeze**: si toccano **solo i difetti di correttezza**, mai la taratura.
3. **Contabilizzazione**: ledger con **ID stabili**, il report giornaliero fa il match.
4. **Peso di un'evidenza**: **dollari stimati + livello di confidenza** della stima.

Approccio architetturale scelto: **carta + due file versionati, zero codice nuovo**. I due cron
esistenti vengono estesi nel prompt. Nessuno script, nessuna migrazione, nessuna tabella.

> **Aggiornamento 2026-08-01, stesso giorno.** Un design successivo
> (`2026-08-01-report-alpha-miner-simmetrico-design.md`) introduce uno script deterministico di
> precalcolo, come **deroga esplicita** al freeze (vedi §3.1). Non invalida questo documento: il
> protocollo del ledger resta di solo prompt e viene rilasciato **lunedì 2026-08-03**, in anticipo
> rispetto allo script. Quel documento introduce anche l'unica eccezione ammessa alla regola "solo
> append": al momento dell'innesto lo script ricalcola le righe di `market_daily.jsonl` scritte
> prima, perché l'intera serie abbia una sola provenienza. L'eccezione non si applica mai a
> `findings.json`.

Motivo: il freeze vieta la taratura, ma il senso è più ampio — l'atto di costruire lo strumento non
deve consumare le settimane che servono a osservare. Due file JSON e un prompt esteso si fanno in
un'ora; una tabella Postgres con migrazione, script di aggregazione e pannello sono giorni, e
sarebbero essi stessi sviluppo durante un freeze sullo sviluppo. Se il ledger si dimostra utile, la
migrazione a DB si valuta a freeze concluso.

## 3. Componenti

### 3.1 La carta di osservazione

File: `docs/evidence/OBSERVATION_CHARTER.md`, scritto e committato **prima** che l'osservazione
cominci. Scopo unico: togliere a noi stessi la possibilità di razionalizzare a posteriori.

**Durata.** Inizio **lunedì 2026-08-03**, minimo **40 giorni di borsa**. Contando il calendario US
(Labor Day cade il 2026-09-07), il giorno 40 è **2026-09-28**; la data esatta va confermata con la
stessa `GetCalendarRequest` che `daily_alpha_miss_analysis.sh` già usa per scegliere il giorno da
analizzare.

Sotto i 40 giorni la finestra non contiene abbastanza giornate ad alta dispersione per distinguere
un difetto ricorrente da una coincidenza. Il riscontro empirico è la finestra 17-31 luglio: 10
giorni hanno prodotto ±$100, cioè rumore.

**Cosa è esente dal freeze.** Solo i difetti di correttezza, con un test esplicito da applicare a
ogni candidato:

> Se non lo correggo, l'evidenza che raccolgo nelle prossime settimane è sbagliata?

Il gate S4 disarmato (#163, corretto il 2026-07-30) passava questo test: con il gate spento il
sistema comprava a soglie che non erano quelle di design, quindi ogni giorno osservato sarebbe stato
inutilizzabile. Un cooldown da tarare non lo passa.

Ogni eccezione applicata va annotata nella carta con data, motivo e commit, così la finestra resta
ricostruibile a posteriori.

**Cosa guadagna diritto a lavoro, alla scadenza.**

| confidenza | definizione | soglia |
|---|---|---|
| **misurata** | perdita reale tracciabile a righe di DB | ≥ $100 cumulativi, ricorrenza irrilevante |
| **attribuita** | il trade esiste, il controfattuale è corto | ≥ $250 cumulativi **e** ≥ 5 giorni distinti |
| **congetturale** | alpha mancato, nessun trade avvenuto | ≥ $1.000 cumulativi **e** ≥ 10 giorni distinti |

L'asimmetria è voluta: un controfattuale deve valere dieci volte un bug misurato per pesare uguale.
Sugli alpha mancati non sappiamo se saremmo entrati, con che size, né quando saremmo usciti. Il
report del 2026-07-30 lo dimostra: MSFT è stato catturato su un giorno a +15,5% e ha prodotto $13,03
realizzati, perché l'uscita è scattata 2h45 dopo l'ingresso.

**Definizione: P&L economico.** Termine usato nei criteri di uscita, da non confondere con il P&L
realizzato. Per ogni posizione, il movimento di prezzo attribuibile alla finestra: si marca dal
close del primo giorno della finestra (o dal prezzo di ingresso, se successivo) al prezzo corrente
(o al prezzo di uscita, se anteriore), moltiplicato per la quantità. Somma su tutte le posizioni,
aperte e chiuse.

Serve perché il P&L **realizzato** di S1 è strutturalmente distorto: la sua regola d'uscita chiude
solo le posizioni che hanno perso rango momentum, cioè quelle che sono scese, mentre le vincenti
restano aperte (#134). Sulla finestra 17-31 luglio la differenza era −$564 realizzati contro −$2,81
economici. Usare il realizzato come criterio di uscita significherebbe decidere su un numero che la
meccanica della strategia rende negativo a prescindere.

**Le domande di uscita, pre-registrate.**

1. *Esiste alpha nella news editoriale su questa watchlist?*
   Falsificazione: se alla scadenza NO_NEWS resta la causa di miss dominante in **≥60% dei giorni**
   **e** il P&L economico di S4 sulla finestra resta dentro **±$200**, la risposta è no. Conseguenza
   pre-registrata: S4 cambia fonte dati (i vettori strutturati Tier A già identificati in
   `docs/RESEARCH_SYNTHESIS_ALPHA_AND_TOOLING_2026-07-26.md`) oppure esce. Nessuna ulteriore
   taratura. È il protocollo che ha già portato alla rimozione di S7.
2. *S1 ha un edge una volta corretta la misura?*
   Criterio: P&L **economico** di S1 sulla finestra confrontato con SPY, con la serie **realizzata
   esplicitamente ignorata** (è strutturalmente distorta — vedi #134).

### 3.2 Il ledger delle evidenze

File: `docs/evidence/findings.json`. Array di record, un ID stabile mai riutilizzato.

```json
{
  "id": "F-012",
  "titolo": "il ranker usa l'ultimo segnale per ticker, non il più forte",
  "tipo": "difetto",
  "confidenza": "attribuita",
  "primo_avvistamento": "2026-07-30",
  "occorrenze": [
    {
      "data": "2026-07-30",
      "costo_usd": 0,
      "nota": "MU: 20 segnali in 6h, picco +0.565 sovrascritto da +0.005; MU +18.4% quel giorno",
      "fonte": "ALPHA_MISS_REPORT_2026-07-30.md §6.4"
    }
  ],
  "costo_cumulato_usd": 0,
  "stato": "aperto",
  "issue": null
}
```

Campi:

- `id` — `F-NNN`, progressivo, mai riutilizzato nemmeno dopo archiviazione.
- `tipo` — `difetto` | `alpha_miss` | `osservazione`.
- `confidenza` — `misurata` | `attribuita` | `congetturale`. Determina la soglia applicabile.
  Può essere **promossa** (es. da congetturale ad attribuita) se emerge evidenza migliore; la
  promozione va annotata come nota nell'occorrenza che la giustifica.
- `occorrenze` — lista append-only. Ogni voce ha data, costo stimato, nota, e `fonte` che punta al
  report e alla sezione che la giustifica. Nessun numero nel ledger è orfano.
- `costo_cumulato_usd` — derivato (somma di `occorrenze[].costo_usd`), memorizzato per leggibilità.
- `stato` — `aperto` | `in_roadmap` | `risolto` | `archiviato`.
- `issue` — numero della issue GitHub se e quando ne viene aperta una, altrimenti `null`.

**Cosa NON diventa un finding.** Le *cause* di miss (NO_NEWS, THIN_NEUTRAL, WRONG_SIGN, FILTERED,
OUT_OF_STRATEGY_SCOPE) non generano record: sarebbero centinaia, uno per simbolo per giorno. Sono
contate in aggregato nel ledger di mercato. Diventa un finding solo l'affermazione **strutturale**:
"39 simboli su 96 non hanno copertura news in un giorno tipico" è un finding; "ADBE non aveva news
il 29" è un conteggio.

### 3.3 Il ledger di mercato

File: `docs/evidence/market_daily.jsonl`, una riga JSON per giorno di borsa (append-only).

```json
{"data":"2026-07-30","spy":0.0165,"qqq":0.0333,"dispersione_sigma":0.0512,
 "mover_3pct":40,"up":29,"down":11,"watchlist_zero_news":39,
 "tema":"melt-up semis post-earnings MSFT/Azure",
 "miss":{"NO_NEWS":1,"THIN_NEUTRAL":2,"WRONG_SIGN":1,"FILTERED":1},
 "catturati":24,
 "book":{"equity":109240.07,"realizzato":-53.03,"mtm":862.0,
         "s1_realizzato":-95.69,"s4_realizzato":42.66}}
```

Definizioni:

- `dispersione_sigma` — deviazione standard cross-sectional dei rendimenti giornalieri dei 96
  simboli della watchlist. Il report del 2026-07-24 la calcolava già (σ = 3,08%) per motivare la
  soglia mover.
- `mover_3pct` / `up` / `down` — conteggio dei simboli con |return| ≥ 3%, e sua ripartizione.
- `watchlist_zero_news` — quanti dei 96 simboli hanno zero righe in `news_log` quel giorno.
- `tema` — una riga di testo libero, la stessa lettura che il report mette nella sua sezione
  "Pattern osservato". Ammesso il valore `"non chiaro"`.
- `miss` — conteggio per categoria, dalla tabella dei miss classificati del report.
- `book` — equity di fine giornata e P&L; `mtm` è la variazione mark-to-market del book aperto.

Il report alpha-miss **calcola già tutto questo** ogni mattina per costruire la sua tabella a 96
righe, e poi lo scarta. Persisterlo costa una manciata di righe nel prompt.

Serve come denominatore. Senza, la ricorrenza è cieca all'opportunità: cinque NO_NEWS in giornate
piatte pesano quanto uno in una giornata a dispersione 5%. Con, a fine periodo si può chiedere
"NO_NEWS costa di più nelle giornate ad alta dispersione?" — che è la domanda che decide se valga la
pena comprare dati migliori.

### 3.4 Il protocollo giornaliero

Nessuno script nuovo. Si estendono i prompt dei due cron esistenti.

**`daily_alpha_miss_analysis.sh`** — due aggiunte al prompt:

- *Fase 0*, prima dell'analisi: leggi `docs/evidence/findings.json`.
- *Fase finale*, dopo aver scritto il report: appendi la riga a `docs/evidence/market_daily.jsonl`,
  e per ogni voce della §7 o agganciala a un ID esistente (append di un'occorrenza) o creane uno
  nuovo. La §7 in prosa resta invariata per il lettore umano, ma ogni voce riporta il suo ID.

**`daily_analysis.sh`** (forensic) — stesso protocollo di match per le proprie segnalazioni. Non
scrive il ledger di mercato (lo fa già l'alpha-miss).

I due cron girano alle 10:00 e alle 14:30: non si sovrappongono, quindi non serve alcun lock.

Due regole da inserire testualmente nei prompt, che sono ciò che tiene in piedi l'intero impianto:

1. **Solo append.** Una sessione non può modificare né cancellare un'occorrenza già scritta. Può
   solo aggiungerne, o creare un nuovo record. La cronologia git resta l'audit.
2. **Nel dubbio, aggancia.** Creare un ID nuovo va giustificato nella nota. Due record duplicati si
   fondono a fine periodo; un'evidenza spezzata in cinque ID diversi ha ricorrenza 1 ciascuno e
   sparisce sotto tutte le soglie — un errore silenzioso e non recuperabile.

I file vanno committati dalla sessione stessa, altrimenti la cronologia git non è un audit di nulla.

### 3.5 Controllo di metà periodo

Verso il **giorno 20** (~2026-08-28) una verifica che **non decide nulla**: controlla solo che il
ledger sia vivo — che `market_daily.jsonl` abbia una riga per ogni giorno di borsa trascorso e che
`findings.json` sia stato toccato.

Motivo: la memoria di progetto registra che il cron forensic "può fallire silenziosamente per
timeout 600s". Scoprire al giorno 40 che il ledger è fermo dal giorno 3 costerebbe l'intero periodo.

### 3.6 Sintesi finale

Alla scadenza, una sessione produce `docs/evidence/WEIGHTED_ROADMAP_<data>.md`:

1. Applica **meccanicamente** le soglie della carta a ogni record di `findings.json`.
2. Ordina per costo cumulato ciò che le ha superate, raggruppando per componente toccato.
3. Risponde alle due domande di uscita pre-registrate, con i numeri del ledger di mercato.
4. Elenca **esplicitamente ciò che non è passato** e viene quindi lasciato cadere, con il suo
   conteggio. Questa lista è metà del valore: la disciplina serve anche a non fare le cose.
5. Fonde eventuali record duplicati, annotando la fusione.

## 4. Fuori scope

- **Nessuna migrazione DB, nessuna tabella, nessun pannello dashboard.** Valutabili a freeze
  concluso, se il ledger si dimostra utile.
- **Nessun recupero retroattivo** dei ~20 report già esistenti. Il ledger parte vuoto il 2026-08-03.
  I findings già noti e già tracciati come issue GitHub (#134, #163, #165, #85) restano dove sono;
  se ricompaiono nei report durante la finestra, prenderanno un ID come tutti gli altri e il campo
  `issue` verrà valorizzato con la issue esistente.
- **Nessuna modifica al perimetro o al contenuto analitico dei report.** Cambia solo cosa
  persistono, non cosa analizzano.

## 5. Rischi

| rischio | mitigazione |
|---|---|
| La sessione giornaliera crea ID nuovi invece di agganciare, e la ricorrenza non emerge mai | Regola "nel dubbio aggancia" nel prompt; fusione dei duplicati alla sintesi finale; controllo al giorno 20 |
| Il cron fallisce in silenzio e il ledger si ferma | Controllo di metà periodo (§3.5) |
| I costi stimati derivano nel tempo perché li stima un LLM diverso ogni giorno | Il livello di confidenza ancora la stima; le soglie sono ordini di grandezza, non valori precisi; ogni occorrenza porta la `fonte` per il ricalcolo |
| Si accumula pressione a "sistemare subito" e il freeze salta | La carta è committata prima; ogni eccezione va annotata con motivo e commit |
| 40 giorni si rivelano comunque troppo pochi per la potenza statistica | La carta pre-registra anche questa possibilità: se alla scadenza nessun criterio è soddisfatto, l'esito legittimo è "estendere", non "agire comunque" |

## 6. Riferimenti

- Report esistenti: `docs/ALPHA_MISS_REPORT_2026-07-{24,27,28,29,30}.md`,
  `docs/FORENSIC_DAILY_REPORT_*.md`
- Issue correlate: #134 (feedback S1 su serie distorta), #163 (gate S4 disarmato, corretto),
  #165 (book S1 non ruota), #85 (cooldown re-entry, evidenza contraria al flip)
- Precedente di rimozione su criterio pre-registrato: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`
- Vettori dati alternativi per S4: `docs/RESEARCH_SYNTHESIS_ALPHA_AND_TOOLING_2026-07-26.md`
