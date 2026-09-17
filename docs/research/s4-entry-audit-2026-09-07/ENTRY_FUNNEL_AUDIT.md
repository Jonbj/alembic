# S4 entry funnel — audit interno point-in-time

Data di avvio: 2026-09-07

## Scopo

L'audit deve stabilire **dove** il lato ingresso di S4 perde qualità o
opportunità, senza cambiare soglie, fonti live, ranking, sizing o money path.
L'oggetto non è il solo trade eseguito, ma l'intera catena osservabile:

`fonte -> articolo -> evento -> ticker -> scoring -> ammissibilità -> ranking -> decisione -> ordine/fill -> outcome`

Il lavoro è diagnostico e read-only. Le varianti candidate saranno eventualmente
valutate in shadow e pre-registrate; nessun risultato esplorativo autorizza una
taratura live.

## Fonti interne e regola di precedenza

La baseline integra:

- 30 `ALPHA_MISS_REPORT` dal 2026-07-24 al 2026-09-04, per casi, spiegazioni e
  ricorrenze;
- 24 dossier JSON congelati dal 2026-08-03 al 2026-09-04, per i conteggi
  riproducibili;
- `WEEKLY_FINDINGS_2026-34.md` e `WEEKLY_FINDINGS_2026-36.md`, che consolidano e
  in alcuni casi correggono la lettura giornaliera;
- il codice corrente di ingestion, sentiment, ranking e portfolio scheduler;
- [Observation Charter](../../evidence/OBSERVATION_CHARTER.md), che contiene i
  criteri pre-registrati già attivi.

In caso di conflitto, il numero viene dal dossier congelato; la classificazione
causale viene dalla revisione settimanale più recente. Una issue descrive un
meccanismo, ma non sostituisce la verifica sui dati. I dossier cambiano schema da
2.0 a 2.8: una metrica viene aggregata solo sulla finestra in cui la sua
definizione è compatibile.

## Baseline quantitativa provvisoria

### Copertura

Nei 24 dossier disponibili, in media **46,6 ticker su 96** per seduta non hanno
alcuna riga news (48,6%; intervallo 38-60). Sui nove dossier che espongono anche
la copertura `effective_timely`, la media scende a **19,8 ticker su 96** (20,6%):
la presenza di una riga grezza sovrastima quindi molto la copertura realmente
tempestiva e issuer-specifica.

Sulla stessa finestra di nove sedute, 13 ticker non ricevono mai una riga raw e
38 non ricevono mai un articolo `effective_timely`. Questo aggiorna, senza
sostituirlo, il censimento congelato della issue #511 (16 e 40 ticker sulla
precedente finestra di otto sedute).

### Sintomi del funnel sui mover mancati

I 24 dossier contengono **144 candidati miss**. La tassonomia meccanica, non
ancora armonizzata fra le versioni, li distribuisce così:

| Etichetta dossier | N | Quota | Lettura prudente |
|---|---:|---:|---|
| `NO_NEWS` | 59 | 41,0% | nessuna catena news-segnale osservabile |
| `BELOW_GATE` | 51 | 35,4% | score insufficiente secondo il classificatore |
| `NON_CLASSIFICATO` | 17 | 11,8% | perdita di informazione causale nella tassonomia legacy |
| `OFF_TOPIC_NON_DECIDIBILE` | 15 | 10,4% | articolo presente ma attribuzione/pertinenza non decidibile |
| altre etichette | 2 | 1,4% | versioni transitorie della tassonomia |

Questi non sono ancora conteggi causali finali. Gli Alpha Miss mostrano infatti
che `BELOW_GATE` può nascondere un segnale del segno sbagliato, un fan-out, un
segnale ribassista non azionabile da una sleeve long-only o un vero near-miss.

### Momento dell'ingresso

Su 19 sedute con almeno un ingresso S4 e denominatore intraday non degenere, la
mediana per seduta di `quota_movimento_precedente_al_segnale` è almeno 70% in
**17 sedute su 19**. La mediana delle 19 mediane è **96,9%**. Nel pool di 51
ingressi S4 leggibili, 41 superano il 75% della gamba open-close e 23 superano il
100%.

Questa metrica non prova da sola che ogni trade sia cattivo: usa la chiusura
conosciuta ex post e descrive il timing, non una regola tradabile. Tuttavia ha già
superato la numerosità minima del primo braccio del criterio pre-registrato
`1-bis` dell'Observation Charter. La conseguenza resta condizionata alla data del
2026-09-28 e all'esito del trial d'uscita: non va anticipata.

## Riconciliazione diretta del DB

Query eseguite il 2026-09-07 dentro transazioni PostgreSQL `READ ONLY`. Il DB
contiene 9.352 righe `news_log`, 9.832 segnali, 18.944 decisioni e 502 trade dal
2026-06-15. Il ledger strutturato degli intenti copre otto sedute, dal
2026-08-25 al 2026-09-03.

Il ledger contiene 23.762 eventi: **11.881 candidati e 11.881 disposizioni**,
quindi ogni osservazione ha una chiusura di funnel. Sono rappresentati 644
`signal_id`/`causal_event_id` distinti e 85 simboli. Non risultano null nei campi
critici `signal_id`, `causal_event_id`, `published_at`, `first_seen_at`,
`model_generated_at` e `decision_at`, né inversioni cronologiche fra questi
timestamp.

Le disposizioni per decision slot sono:

| Disposizione | Slot | Quota |
|---|---:|---:|
| `SKIP_ENTRY_FRESHNESS` | 4.570 | 38,5% |
| `SKIP_ENTRY_GATE` | 3.981 | 33,5% |
| `SKIP_STALE` | 1.824 | 15,4% |
| `SKIP_PYRAMIDING` | 697 | 5,9% |
| `SKIP_FALLBACK` | 668 | 5,6% |
| `RANK_OUTSIDE_TOP_N` | 58 | 0,5% |
| `SKIP_IDEMPOTENCY` | 40 | 0,3% |
| `SUBMITTED` | 23 | 0,2% |
| `RANK_LONG_ONLY` | 20 | 0,2% |

Queste righe non sono osservazioni statistiche indipendenti: lo stesso segnale
ricompare in più cicli. Mostrano però che la maggior parte del volume operativo
si ferma su età/freschezza o gate, prima che top-N ed esecuzione siano vincolanti.

Sui 644 segnali distinti, le latenze mediane sono 9,9 minuti da pubblicazione a
first-seen, 30,6 minuti da first-seen a modello e 6,5 minuti da modello alla
prima decisione osservata; i p90 sono rispettivamente 41,0, 75,6 e 1.142 minuti.
L'ultimo p90 è dominato dai segnali vecchi riproposti o preservati. Nei 23
segnali effettivamente `SUBMITTED`, la latenza pubblicazione-decisione ha mediana
35,2 minuti e p90 108,3 minuti; la sola inferenza ha mediana 16,2 minuti.

Dei 644 segnali distinti, 577 sono ensemble e 67 fallback/single/FinBERT
(10,4%). Dodici hanno `ensemble_std >= 0,30`. I 23 submitted non includono
fallback, ma includono un caso ad alta divergenza; lo score medio dei submitted
è 0,486 e l'`ensemble_std` medio 0,109. Per 627 segnali esistono due output raw
dei modelli; i 17 senza output raw coincidono con il percorso FinBERT da
verificare puntualmente.

Le feature arricchite sono presenti soltanto a livello `llm_responses`, non nel
segnale aggregato consumato dal ranker. Fra il 25 agosto e il 4 settembre sono
presenti 1.770 risposte raw, ma 196 non hanno `event_type`/`directness` e sono
osservate anche categorie non canoniche. Prima di testare materiality, novelty,
directness o event type come gate serve quindi un contratto di aggregazione fra
modelli e una normalizzazione delle categorie; usare direttamente una delle due
risposte introdurrebbe una scelta post-hoc.

## Evidenza qualitativa ricorrente dagli Alpha Miss

I report giornalieri e settimanali rendono visibili almeno sette famiglie di
problemi che il solo conteggio del dossier non separa:

1. **Copertura strutturale, non casuale** (`F-001`, #511/#324): gli stessi ticker
   restano ripetutamente ciechi.
2. **Fan-out e attribuzione errata** (`F-012`, `F-020`, `F-057`, `F-067`, #405):
   articoli su terzi possono produrre segnali, mentre headline chiaramente
   issuer-specifiche possono restare `TAG_UNCONFIRMED`.
3. **Informazione diluita o sovrascritta** (`F-008`, `F-023`, #169): l'ultimo
   segnale per ticker può cancellare un evento più forte o più diretto.
4. **Latenza e avvio operativo tardivo** (`F-019`, `F-021`, `F-030`, #404/#512):
   acquisizione, scoring e ciclo di portafoglio consumano una parte rilevante
   della finestra utile.
5. **Qualità/modo del modello** (`F-010`, `F-049`, #403/#443): fallback,
   single-model e divergenza ensemble non sono equivalenti, ma la varianza
   ensemble non è un gate d'ingresso.
6. **Perdita o censura dopo lo score** (`F-031`, `F-056`, #230/#400/#431):
   anti-pyramiding, top-N e scelta del segnale possono bloccare candidati senza
   rappresentare il loro valore incrementale.
7. **Contesto di mercato assente** (#335/#507): il gate non usa in modo affidabile
   calendario earnings né quota di movimento già avvenuta.

## Domande che l'audit deve decidere

L'analisi successiva deve produrre una risposta separata per ogni stadio:

1. Quanta parte dei mover eleggibili ha una notizia osservabile in tempo utile?
2. Quanta copertura raw sopravvive a pertinenza, directness, qualità e
   deduplicazione per evento?
3. Il resolver assegna correttamente soggetto, ticker e canale di read-through?
4. Quanto tempo passa fra `published_at`, `first_seen`, scoring, decisione e
   primo prezzo eseguibile?
5. Polarity, confidence, materiality, novelty, directness, event type e
   `ensemble_std` sono calibrati rispetto a abnormal return futuri?
6. L'ultimo segnale è migliore di uno stato aggregato per evento/ticker?
7. Il gate 0,30 aggiunge precisione netta, o seleziona soltanto magnitudine
   semantica?
8. S4 aggiunge informazione rispetto a S1, mercato e settore?
9. Il candidato sopravvive a ranking, cap, anti-pyramiding e disponibilità di
   capitale per ragioni coerenti e completamente osservabili?
10. Il rendimento resta positivo dal primo prezzo eseguibile, dopo spread,
    slippage e costi?

## Prossima estrazione read-only

La fase successiva riconcilia DB e dossier in una tabella immutabile per
`causal_event_id`/ticker. Ogni riga deve conservare:

- fonte, URL/hash, `published_at`, `first_seen_at`, `generated_at` e tick;
- rilevanza, directness, event type, materiality, novelty e risk flags;
- output/versione di ciascun modello, ensemble, divergenza e fallback;
- score scelto e segnali concorrenti scartati;
- ogni disposizione del funnel e il relativo reason code;
- prezzo a first-seen, score, primo ciclo e primo fill;
- market/sector-adjusted return, MFE/MAE e outcome a orizzonti congelati;
- contributo S1/S4, esposizione già esistente e costi ricostruibili.

Le mancanze restano `UNKNOWN`: non vengono riempite con assunzioni. I risultati
esplorativi servono a scegliere poche policy shadow; la decisione richiede poi
un campione forward untouched e controllo della molteplicità.

## Stato dell'estrazione al 2026-09-08

La fase di estrazione e arricchimento storico e' completata. Il backfill
read-only copre 3.748 segnali, 11.881 intenti, 144 casi Alpha Miss e 3.667
timeline point-in-time. Gli artefatti sono congelati con conteggi e hash nei
rispettivi manifest:

- [snapshot completo](snapshots/full-signals-2026-08-03_2026-09-05/manifest.json);
- [arricchimento Alpha Miss e outcome](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/manifest.json);
- [metriche riproducibili](analysis/entry-funnel-v1/metrics.json);
- [risultati e limiti](ENTRY_FUNNEL_FINDINGS_2026-09-08.md);
- [audit dei join Alpha Miss](ALPHA_MISS_ENRICHMENT_AUDIT.md).

Il 28 agosto resta privo di dossier congelato: gli 81 segnali DB di quella
seduta sono presenti nello snapshot ma non ricevono prezzi o MFE/MAE ricostruiti
ex post. Nei dossier legacy, 140 riferimenti a segnali non portano `signal_id` e
restano anch'essi `UNKNOWN`. Nessuna di queste lacune e' stata riempita mediante
matching fuzzy o selezione in base all'outcome.
