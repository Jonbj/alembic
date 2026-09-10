# Pre-registrazione — consumo shadow off-session della coda news (Opzione C)

Data di registrazione: **2026-09-10**. Origine: `docs/research/news_ingest_consumo_disaccoppiamento_2026-09-10.md`
§C (branch `research/news-ingest-consumo`), alert stale-drop #432.

Questa definizione è fissata **prima** del primo run che produce dati e non verrà
modificata dopo averne osservato i risultati. Se una parte dovesse cambiare, il
cambiamento va registrato qui come errata **datata**, insieme al motivo, e annotato
come discontinuità in `docs/evidence/OBSERVATION_CHARTER.md` — mai riscritto in
silenzio.

---

## 1. Domanda

Delle news che oggi vengono **scartate come stale fuori seduta** — la coorte che si
accumula in `news:queue` dalle 21:00Z e viene scaricata in blocco alla campana delle
13:30Z — quante avrebbero prodotto un segnale sopra il gate d'ingresso di S4
(`|score| > 0,30`), e qual è il loro **forward return a D+1**?

La domanda esiste per una decisione precisa e per nessun'altra: al **2026-09-28**
l'Opzione D (spostare il gate di seduta dal consumatore all'esecuzione) va decisa, e
oggi non sappiamo se la coorte notturna valga qualcosa. Le 157 e 195 news scartate
l'8 e il 9 settembre potrebbero essere in larga parte content-mill senza catalizzatore
— esattamente il materiale che #508 indica come gonfiante di ogni metrica di copertura.

**Cosa questa misura NON è.** Non è una stima del P&L dell'Opzione D. Il valore atteso
della D sta sul path **uscite** (i simboli detenuti saltano `_apply_entry_freshness_gate`
per l'esenzione #150), non sugli **ingressi**, che il gate a valle riscarterebbe
comunque. Qui si misura la materia prima — presenza e direzione del segnale — non
l'effetto di un cambiamento di policy.

## 2. Campione

**Popolazione.** Ogni item letto dalla coda `news:queue` da `run_sentiment_shadow_worker`
in una finestra di esecuzione fuori seduta, che superi la sanitizzazione e produca un
`SentimentResult`. Nessun ticker, nessuna fonte e nessuna notte vengono selezionati in
base al risultato.

**Unità di analisi.** Il **simbolo-giorno**: la coppia (`symbol`, data UTC di
`published_at`). Un simbolo con più articoli nella stessa notte conta **una** unità, con
lo score di magnitudine massima — la stessa riduzione che il ranker di produzione
applica, e per lo stesso motivo (evitare che una notte rumorosa su un solo titolo
generi da sola il campione).

**Finestra.** Dal primo run che produce dati (data del deploy, da annotare qui sotto
alla riga «Prima esecuzione») al **2026-09-28** incluso. La finestra non viene estesa
per raggiungere `n`: se `n` non basta, l'esito è `INSUFFICIENT_N` (§4).

**Tetto dichiarato.** Massimo **200 articoli per notte**
(`SENTIMENT_SHADOW_MAX_PER_NIGHT`, default 200). È un vincolo di budget di inference
dichiarato in anticipo, non una scelta post-hoc: raggiunto il tetto il worker esce e
riprende la notte successiva. Il tetto **tronca la coda in ordine di lettura**
(dalla testa, cioè dagli item accodati per primi), quindi in una notte oltre 200
articoli il campione è la coorte **più vecchia**, non un campione casuale. Questa è
una limitazione nota e dichiarata: va riportata nel risultato, mai corretta a
posteriori scegliendo un ordinamento diverso.

**Scadenza dura.** Il turno notturno si interrompe alle **13:15Z**, qualunque sia il
suo stato, per non contendere `worker-inference` (concurrency=1) nella finestra di
apertura. Un'interruzione per scadenza è un troncamento del campione, non un errore:
va conteggiata e pubblicata.

Prima esecuzione: `______` (da compilare al primo run reale, non prima).

## 3. Regola fissata

Per ogni item la classificazione usa **la pipeline di produzione**, non una sua
riscrittura: `run_inference()` in `src/workers/sentiment.py`, con gli stessi client,
gli stessi timeout, lo stesso prompt e gli stessi pesi d'ensemble del path live
(regola #169/#467 — la misura chiama la regola di produzione, non la reimplementa).
L'unica differenza è il **sink**: in modalità shadow nessuna scrittura raggiunge Redis,
`sentiment_signals` o `news_log` (§6).

```text
score            = polarity × confidence          (formula di produzione, invariata)
sopra_gate       = |score| > 0,30                 (soglia d'ingresso S4 vigente)
unita            = (symbol, published_at::date UTC), score di |·| massimo
```

**Il gate 0,30 è la soglia già in vigore, non una nuova taratura**, ed è fissato qui
prima di vedere i dati. Non verranno riportati esiti a soglie alternative (0,25 / 0,35
/ ...): una griglia di soglie letta dopo il risultato non è un risultato — servirebbe
una correzione dichiarata per molteplicità, e non ce n'è una.

**Outcome.** Forward return **a D+1** calcolato da `scripts/compute_label_forward_returns.py`
(barre **Alpaca historical**, close-to-close, point-in-time da `published_at` —
esplicitamente **non** yfinance). Righe senza barre disponibili restano `NULL` e
**non** diventano zero: entrano nel conteggio del campione come non valutabili e sono
pubblicate separatamente.

## 4. Criterio pre-registrato ed esito

> **`INSUFFICIENT_N` se `n < 30` simbolo-giorni con `|score| > 0,30` su tutta la
> finestra di misura.**

`INSUFFICIENT_N` **non significa «non c'è alpha»**. Significa che, da questa fonte, la
decisione sull'Opzione D **non ha supporto** per il 28/09 e va presa su altre basi (o
rinviata). È l'esito **più probabile** su ~2-3 settimane di notti, ed è dichiarato tale
qui, prima dei dati, proprio perché non venga riletto come una scoperta.

Coerentemente con `config/s4_kill_criterion.yaml` e con la prassi della carta,
**`INSUFFICIENT_N` sovraordina PASS/FAIL per costruzione**: se `n < 30` non viene
pubblicato alcun verdetto direzionale sul forward return, nemmeno come «tendenza».

Se `n ≥ 30`, si pubblicano — tutti, insieme:

- `n` simbolo-giorni totali osservati e `n` sopra gate;
- distribuzione degli `|score|` e ripartizione per `source` e per `fallback_used`;
- forward return D+1 medio e mediano dei sopra-gate, **segnato per direzione dello
  score** (long-side e short-side separati, mai aggregati in un unico numero che il
  segno rende privo di significato);
- `n` con forward return non disponibile;
- `t` (Newey-West/HAC, i forward return si sovrappongono) sulla correlazione
  score↔forward return, con la barra **|t| ≥ 3** della carta;
- `ic_rilevabile_a_t3`: l'effetto minimo che questo campione poteva distinguere da
  zero. Un IC sotto quella soglia si legge «non rilevabile», **mai** «assente».

## 5. Perché il criterio non è in `config/s4_kill_criterion.yaml`

`config/s4_kill_criterion.yaml` è un file **mono-criterio**: le sue tre chiavi
(`min_giorni`, `significativo_a_t`, `max_ic_rilevabile_a_t`) sono lette posizionalmente
da `_leggi_criterio()` in `scripts/compute_s4_ic.py:204-227`, e la sua intestazione lo
dichiara «la parte del criterio S4 che lo script sa valutare», con fonte autorevole in
`PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md`.

Aggiungerci un blocco off-session produrrebbe un file con **due criteri non correlati**,
di cui il secondo verrebbe **silenziosamente ignorato** dall'unico consumatore del file
— la forma peggiore di registrazione, perché sembra registrata e non lo è. La struttura
non lo consente: il criterio vive qui, per intero, come previsto dall'alternativa
esplicita.

## 6. Perimetro delle scritture (deroga registrata in carta)

La modalità shadow scrive su **una sola tabella**: `sentiment_signals_offsession_shadow`
(migrazione `068_sentiment_offsession_shadow.sql`).

**Zero** scritture su `sentiment_signals`, `news_log`, e **zero** scritture su Redis
(`redis_store`). La coda non viene mai consumata: `LRANGE`, mai `LMOVE`, mai
`rpush`, mai `delete("news:processing")`; la de-duplica per non ri-scorare lo stesso
item usa un set Redis dedicato `shadow:processed:<data>` con TTL 36h.

Questo perimetro è **asserito da test** (`tests/workers/test_sentiment_shadow.py`), non
da revisione a vista: qualunque scrittura live nel path shadow fa fallire la suite.

Il motivo per cui `news_log` in particolare **non** va scritto: cambierebbe il
denominatore di copertura di #511 e #508 a metà finestra di osservazione — una
discontinuità gratuita su una serie che serve al 28/09.

## 7. Cosa falsificherebbe la misura

- Comparsa di righe in `sentiment_signals` o `news_log` con `generated_at` fuori seduta
  attribuibili al worker shadow → il perimetro è rotto, i dati della finestra sono
  contaminati e vanno **scartati**, non corretti.
- Profondità di `news:queue` che cala durante una finestra shadow senza un consumatore
  live attivo → il worker sta consumando la coda; stessa conseguenza.
- Tasso di `fallback_used` (FinBERT) marcatamente più alto che nel path live a parità
  di modelli: il campione starebbe misurando la disponibilità notturna di Ollama Cloud,
  non il contenuto delle news. Va pubblicato **sempre**, non solo se anomalo.
