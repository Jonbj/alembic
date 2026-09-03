# Review notturna delle PR sul modello locale — Spec di design

**Data:** 2026-09-03
**Stato:** design approvato dall'operatore, pronto per il piano di implementazione
**Origine:** valutazione del worker locale Qwen3.8-27B del 2026-09-01/02 (quattro probe più il run
notturno su PR #472)
**Componenti:** `scripts/review_notturna_locale.py` + `src/review_locale/{selezione,estrazione,referto}.py`
**Freeze #171 (03/08→28/09):** strumentazione e misura, nessuna taratura toccata. Il job legge PR e
issue e scrive un commento; **non ha alcun potere sul merge**.
**Roadmap:** Part of #21.

---

## 1. Problema

Il loop roadmap (`scripts/roadmap_agent_loop.sh`) affida la review di ogni PR a un motore cloud, e
quel verdetto decide il merge. Il 2026-09-02 alle 06:37Z la review di PR #472 è uscita
`NON_ESEGUITA`: il recensore assegnato era in rate limit. La PR è rimasta aperta e non esaminata, e
i rilievi che pure erano stati prodotti — da tredici subagenti lanciati dalla sessione stessa poco
prima di esaurire la finestra — sono finiti in un transcript che nessuno avrebbe letto.

Sulla stessa macchina esiste un worker locale inattivo per gran parte della giornata: nessun costo
per token, nessuna quota, nessun dato che esce di casa. La sua qualità è stata misurata, ed è
**asimmetrica in un modo che vincola tutto questo disegno**.

## 2. Cosa la misura dice, e cosa vieta

Quattro probe con chiave di correzione indipendente (le PR già mergiate), più un run completo sulla
PR #472:

| Probe | Compito | Esito |
|---|---|---|
| #372 | diagnosi su excerpt (chiave: PR #373) | 9/9 |
| #396 | due difetti dove il sintomo ne mostra uno (PR #435) | 7/7 |
| #397 | ragionamento quantitativo + schema (PR #445) | 6/7 |
| #324 | **controllo negativo**: issue con due premesse false | **fallito** |
| PR #472 | review di un diff reale, 42 KB | 1 rilievo ritrovato in forma migliore del cloud, 1 nuovo confermato, 6 mancati **di cui 2 esplicitamente assolti** |

Il verdetto è una riga: **su un difetto che esiste è eccellente, su un difetto che non esiste è
inaffidabile.**

Su #324 ha prodotto quattro obiezioni epistemiche buone — ha notato che «$639 quantified» viene da
una fonte che dice *costo congetturale* — ma ha **assorbito** la conflazione fra calo di giornata e
posizione in perdita, e ha classificato come *solida* la premessa adiacente alla rotazione della
copertura. Su #472 ha prodotto undici voci in `verificato_e_scartato`, di cui almeno due
dimostrabilmente false, e sono false **esattamente sui due punti dove i difetti erano reali**:

- «La SQL di `_risk_decisions` esclude **correttamente**...» — mentre `SKIP_STALE` passa il filtro.
- «La partizione actionability è **completa**... verificato per ogni combinazione» — mentre
  `OUT_OF_SCOPE` è strutturalmente irraggiungibile (`closes` si costruisce con `for s in simboli`
  e al funnel arriva `universo=simboli`, quindi `in_universo` è sempre `True`).

Da qui il principio che governa ogni scelta che segue: **è una lente che esamina, mai un cancello
che approva.** I suoi reperti valgono e vanno letti; le sue assoluzioni non valgono nulla e non
devono uscire dal disco.

### Costo, misurato

| Grandezza | Valore |
|---|---|
| Prefill | ~140 tok/s |
| Generazione | 1,55 tok/s su prompt da 7 KB, 1,28 su 42 KB, istantanee fino a 0,90 |
| Run completo su #472 | 16.453 token in 13.439 s (3h44m), `finish_reason: stop` |
| Tetto `max_tokens` | 32.768 → caso peggiore ~8h20m |

Il rapporto prefill/generazione è ~90:1: **leggere è quasi gratis, scrivere è carissimo**. Il
profilo adatto è quindi input lungo e output corto — che è esattamente la forma di una review.

Una nota di metodo che vale per la lettura dei referti futuri: la conclusione «un diff integrale non
è alla sua portata», scritta il 02/09 dopo due interruzioni a 3.968 e 6.008 token, era **sbagliata**.
Quelle interruzioni erano nostre, non sue: la soglia dei 6.000 token era un proxy inventato, e il
probe #324 aveva concluso a 6.098. Lasciato correre senza cappio, ha chiuso. Le soglie inventate
producono conclusioni inventate.

## 3. Decisioni di disegno

| Scelta | Decisione | Perché |
|---|---|---|
| Destinazione | commento sulla PR, **solo il campo `rilievi`** | mette l'informazione davanti a chi decide il merge nel momento in cui decide |
| Rapporto col loop | **completamente separato**, nessun potere sul merge | un fallback che sostituisce il recensore cloud trasformerebbe la lente in cancello: un suo "nessun rilievo" diventerebbe un via libera |
| Selezione | la PR più vecchia non esaminata, **una per notte** | a ~4h per PR il ritmo reale è una; riempire la notte con le più piccole rimanderebbe per sempre le grandi, dove i difetti si nascondono |
| Sede del codice | repo Alembic | il pezzo difficile è l'estrazione e il filtro, e quella logica ha bisogno di test e CI; la chiamata al modello è venti righe di curl |
| Ledger | fuori da git | è stato locale della macchina come i log del server; committarlo ogni notte sporcherebbe il repo per nulla |

## 4. Architettura

Un timer systemd utente alle **01:07** lancia un orchestratore Python. L'orario sta nel buco fra il
giro del loop roadmap delle 23:00 e quello delle 07:00 (`0 7,12,17,21` più `0 9,14,19,23`): l'avvio
alle 21:03 usato nella prova del 02/09 finiva addosso al giro delle 21.

Tre moduli puri portano tutta la logica verificabile; l'orchestratore concentra l'impuro e resta
magro.

### `src/review_locale/selezione.py`

Dato il contenuto del ledger e l'elenco delle PR aperte, restituisce la PR da esaminare o `None`.

- ordine: `createdAt` crescente fra le PR mai esaminate;
- una coppia `(pr, sha)` già `ESAMINATA_*` non torna eleggibile;
- **nuovi commit riaprono la PR**: l'identità dell'esame è `(numero, sha del head)`, non il numero;
- massimo **due tentativi per sha**: alla terza `NON_ESAMINATA` la coppia è esaurita e resta fuori
  finché non arriva un commit nuovo. È la stop rule del `NODE_CONTRACT` riusata identica.

### `src/review_locale/estrazione.py`

Dato il diff della PR e il corpo della issue collegata, costruisce uno o più prompt.

- **filtra ai soli file di codice.** Il caso che giustifica il modulo è PR #477: +69.343 righe di
  cui 58.339 sono `docs/evidence/dossier/2026-09-01.json` generato e 3.154 un altro JSON. Il codice
  vero è ~2.000 righe. Senza filtro la PR sarebbe trenta volte oltre il contesto e verrebbe saltata;
  con il filtro sta comoda.
- esclude i file di test dal diff dato al modello: il compito è giudicare il codice contro la issue,
  e i test consumano contesto senza aggiungere ipotesi. (Restano nel repo e nel giudizio umano.)
- **tetto di 35 KB.** Sotto il tetto: un prompt unico, che conserva la visione d'insieme — il
  rilievo migliore prodotto su #472 (la contraddizione fra il commento di `funnel.py:88` e l'ordine
  di valutazione reale) richiedeva di vedere il modulo intero. Sopra il tetto: un prompt per file di
  codice modificato.
- il prompt impone la forma d'uscita e nomina le classi di difetto da cercare: rami irraggiungibili,
  classificazioni sbagliate, evidenze false, doppi conteggi, non determinismo, scarti dalla issue.
  Chiede anche di dichiarare quando un difetto ne maschera un altro — su #472 quella nota è stata
  prodotta dai subagenti cloud e non dal locale, quindi la richiesta esplicita serve.

### `src/review_locale/referto.py`

Valida il JSON e decide se è pubblicabile.

- **scarta `verificato_e_scartato`** prima di qualunque altra cosa. Non viene pubblicato mai:
  nemmeno in fondo al commento, nemmeno marcato come non verificato. Resta nel file locale per
  diagnosi.
- pubblicabile solo se il JSON è valido **e** `rilievi` contiene almeno un elemento.
- rilievi vuoti → `ESAMINATA_SENZA_RILIEVI` nel ledger, **nessun commento**. Un commento «nessun
  rilievo» è precisamente l'assoluzione che la misura vieta, e sulla PR leggerebbe come un via
  libera.

### `scripts/review_notturna_locale.py`

Orchestratore. Avvia il server, attende `/health`, chiama `gh` per PR e issue, interroga il modello
in streaming, applica i rilevatori, scrive il ledger, pubblica il commento, spegne il server.

Il commento porta un'intestazione che dichiara l'origine — prodotto da un modello locale, non
verificato — perché chi lo legge deve poter pesare i rilievi sapendo da dove vengono.

## 5. Rilevatori: nessuna regola di orologio

Il server resta acceso finché il lavoro finisce, anche a mattina inoltrata; si spegne solo alla fine.
Un orologio non distingue un lavoro lento da un lavoro rotto, quindi il limite lo pongono due
rilevatori su ciò che il modello sta effettivamente producendo.

**Rilevatore di loop.** Ogni ~500 token generati, ricalcola sul ragionamento accumulato le righe
identiche ripetute e i 12-grammi ripetuti. Interrompe se i 12-grammi ripetuti superano **10**.

Calibrazione, su due campioni reali:

| Campione | Ragionamento | Righe ripetute | 12-grammi ripetuti | Esito |
|---|---|---|---|---|
| run interrotto 02/09 | 23.653 char, 95 righe sostanziali | 2 (due citazioni) | 1 | sano |
| run notturno 02/09 | 54.958 char | — | — | concluso |

Sano è 0–1 dodici-grammi ripetuti anche su 55 KB di ragionamento. La soglia a 10 è
**deliberatamente larga**: con due soli campioni non vale la pena uccidere un ragionamento sano che
ripete una citazione. Il rilevatore **logga sempre le sue misure nel ledger**, così ogni notte
aggiunge un punto di calibrazione e la soglia si sceglierà sui dati.

**Rilevatore di corsa condannata.** Non «troppo lunga» in ore, ma *aritmeticamente incapace di
finire*: se il ragionamento raggiunge **28.000 token con `content` ancora vuoto**, restano meno di
4.800 token sotto il tetto e il JSON di #472 è costato ~2.000. Proseguire produrrebbe
`finish_reason: length` e nessun referto, quindi si interrompe.

Con avvio all'01:07: caso tipico concluso verso le **04:50**; corsa condannata interrotta verso le
**08:10**; tetto `max_tokens` senza che i rilevatori scattino verso le **09:30**. Solo il ramo
patologico arriva a sovrapporsi ai giri del loop delle 07 e delle 09 — che girano su modelli cloud e
non contendono la GPU, ma lanciano `pytest`, quindi sei thread di llama e una suite di test si
rallentano a vicenda.

Se la calibrazione si rivelasse troppo larga e le corse condannate arrivassero regolarmente in
mattinata, la leva è **abbassare la soglia dei 28.000 token, non anticipare l'orario**: l'ora di
avvio non è il problema, la corsa che non può finire lo è.

## 6. Errori

| Caso | Comportamento |
|---|---|
| JSON invalido | **una sola** richiesta di riparazione, col vincolo del `NODE_CONTRACT`: preserva chiavi e valori, non introduce fatti, claim o review. Se fallisce, `NON_ESAMINATA` e riprovabile domani |
| Loop o corsa condannata | interruzione, ragionamento parziale su disco per diagnosi, **nessuna pubblicazione**. Mai un referto troncato su GitHub |
| Server non parte | `NON_ESAMINATA` con causa, nessun tentativo di ripiego su un modello cloud — il job è il modello locale, non «una review qualsiasi» |
| Nessuna PR eleggibile | esce 0 senza accendere il server |
| `gh` fallisce | `NON_ESAMINATA` con causa; il commento non viene ritentato a metà (un commento parziale è peggio di nessun commento) |

La regola comune: **su GitHub va solo un referto completo con almeno un rilievo.** Tutto il resto
vive nel ledger.

## 7. Dati

`/home/stefano/llm/notte/ledger.jsonl`, append-only, una riga per tentativo:

```json
{
  "pr": 472,
  "sha": "…",
  "iniziato": "2026-09-03T01:07:04+02:00",
  "concluso": "2026-09-03T04:51:12+02:00",
  "stato": "ESAMINATA_CON_RILIEVI",
  "causa": null,
  "prompt_kb": 42,
  "prompt_spezzato": false,
  "completion_tokens": 16453,
  "reasoning_char": 54958,
  "rilievi": 2,
  "misure_loop": {"righe_ripetute": 2, "dodici_grammi_ripetuti": 1},
  "commento": "https://github.com/…#issuecomment-…"
}
```

Il campo `misure_loop` è l'unico che non serve al job stesso: serve a noi, per calibrare la soglia
sui dati invece che a occhio.

## 8. Test

I tre moduli puri con test veri:

- **`selezione`**: ledger vuoto; riapertura su nuovo sha; coppia esaurita dopo due `NON_ESAMINATA`;
  ordinamento per `createdAt` a parità di stato.
- **`estrazione`**: il diff reale di PR #477 come fixture — è il caso che dimostra il filtro
  (69.343 righe → ~2.000 di codice); un diff sotto il tetto che resta un prompt unico; uno sopra il
  tetto che viene spezzato per file; un diff di soli file di dati che non produce alcun prompt e
  segna la PR come non esaminabile.
- **`referto`**: `rilievi` vuoto → non pubblicabile; JSON invalido → non pubblicabile;
  `verificato_e_scartato` presente → assente dall'output pubblicabile. Quest'ultimo è il test che
  protegge il principio dell'intera spec e va scritto per primo.

L'orchestratore prende un test d'integrazione con `gh` e il server finti: verifica che a referto non
pubblicabile **non** parta alcuna chiamata a `gh pr comment`.

## 9. Cosa questa spec non fa

- **Non tocca il merge.** Nessuna label, nessun `blocked_by`, nessun verdetto. La variante che dà al
  job il solo potere di *fermare* — mai di approvare — è stata considerata e rimandata: un falso
  positivo bloccherebbe una PR buona, e su due soli rilievi confermati non sappiamo quanti falsi
  positivi produca. Si valuterà dopo qualche settimana di referti.
- **Non fa la guardia sulle premesse delle issue**, che sarebbe l'uso di maggior valore — previene
  90 minuti di sessione cloud per issue — ma è esattamente ciò che il probe #324 dimostra che non sa
  fare. Si potrà riprovare **dandogli i dati** invece del solo testo (prezzi d'ingresso delle
  posizioni, copertura per simbolo su una settimana): entrambi i suoi errori su #324 erano confronti
  fra un'affermazione e un numero che non aveva.
- **Non entra nel percorso di esecuzione** né in nessun ciclo agentico: a 1,3 tok/s il
  `TIMEOUT_SESSIONE=5400` del loop copre ~8.000 token di output in tutto.
