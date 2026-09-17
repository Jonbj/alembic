# Local Qwen research contract

## Objective

Estrarre soltanto claim dimostrabili dal corpus congelato e valutarne la trasferibilità alle
ipotesi H01–H22. Il lavoro non decide se S4 ha alpha e non propone tuning live.

## Node1 contract

- input massimo: un chunk, metadata e registry H01–H22;
- output: JSON valido, nessuna prosa esterna;
- ogni claim: hypothesis IDs, stance, claim prudente, exact evidence quote, limitations e
  transferability;
- vietato usare conoscenza non presente nel chunk;
- se il chunk non contiene risultati/metodo rilevanti: lista claim vuota;
- riferimenti suggeriti: solo titolo/autore come `UNVERIFIED_FOLLOWUP`.

## Deterministic gate

- protocollo corrente `4`, con `run_id`, source/chunk hash e hash del registry congelato;
- parsing JSON obbligatorio;
- JSON object vincolato anche dal server di inferenza;
- un output con sola sintassi JSON invalida riceve una singola richiesta di riparazione che deve
  preservare chiavi e valori e non può introdurre fatti, claim o review;
- `source_id` e `chunk_id` devono coincidere con l'input;
- ogni `evidence_quote` deriva dalle linee indicate, viene conservata integralmente e deve
  comparire byte-normalizzata nel chunk;
- stance ammessa: `SUPPORTS`, `CONTRADICTS`, `QUALIFIES`, `METHOD_ONLY`;
- hypothesis ID deve appartenere a H01–H22;
- claim invalidi vanno nel rejection ledger e non raggiungono il consolidato.

## Node2 contract

- input compatto: claim node1, quote e contesto meccanico circostante;
- non usa fonti esterne né introduce nuovi claim;
- classifica ogni claim `SUPPORTED`, `OVERSTATED`, `AMBIGUOUS`, `NOT_APPLICABLE`;
- riceve il registry H01–H22 completo e batch di massimo tre claim;
- ricerca salti causali, outcome mismatch, horizon mismatch, sample/provider dependence e
  long-short vs long-only mismatch;
- verifica esplicitamente direzione, confronti, numeri, denominatori e disuguaglianze;
- deve restituire esattamente una review per ogni `claim_id` ricevuto; copertura incompleta,
  duplicati, ID inventati e verdetti non ammessi vengono respinti;
- output JSON valido con reason code e correzione minima.

## Stop rule

- massimo due tentativi per chunk su parsing/quote failure;
- il limite di due tentativi persiste fra restart per la stessa versione di protocollo;
- una campagna di recupero nominata può assegnare due nuovi tentativi soltanto a source espliciti;
  ogni evento e artefatto conserva il nome della campagna e il ledger precedente resta intatto;
- un source con download/extraction failure diventa `SOURCE_UNAVAILABLE`, non viene sostituito
  automaticamente da una fonte secondaria;
- il primo pass termina quando ogni source è `REVIEWED`, `NO_RELEVANT_CLAIMS` o
  `SOURCE_UNAVAILABLE`;
- nessuna nuova ipotesi viene aggiunta durante il passaggio iniziale;
- i candidate follow-up vengono validati separatamente prima di entrare nel manifest.
- una fonte con chunk o batch di review falliti resta `SOURCE_INCOMPLETE` e non può essere marcata
  completa;
- se llama.cpp rifiuta un singolo chunk per context overflow, soltanto quel chunk viene diviso in
  child ID tracciati; `CHUNK_SPLIT` e `CHUNK_RECOVERED` dimostrano la copertura del parent senza
  cambiare i confini o gli hash degli altri chunk già validati;
- una sola istanza dell'orchestratore può detenere il lock dell'output directory.

## Resource policy

Il job è P1 perché richiesto dall'utente, read-only rispetto ad Alembic, append-only negli output e
interrompibile. Può impiegare giorni. I due server hanno un solo slot ciascuno; niente richieste
concorrenti sullo stesso nodo. L'orchestratore usa un solo worker per nodo: node1 continua
l'estrazione mentre l'unico worker node2 processa in ordine i batch già disponibili.
