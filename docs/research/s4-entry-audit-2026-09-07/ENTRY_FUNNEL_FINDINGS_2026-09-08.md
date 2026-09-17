# S4 entry funnel — risultati descrittivi del backfill

Data: 2026-09-08

Stato: analisi esplorativa, **nessuna modifica autorizzata alla strategia live**.

## Risultato in breve

Il backfill conferma che il problema d'ingresso non e' riconducibile a una sola
soglia. Il segnale arriva spesso dopo che gran parte del movimento intraday e'
gia' avvenuta; la copertura mancante resta la maggiore fonte di opportunita'
accessibile fra i mover persi; fallback e fan-out mostrano qualita' leggermente
peggiore, ma non una separazione sufficiente per scegliere nuove policy. Il gate
0,30 identifica un sottoinsieme un po' migliore nel residuo della stessa seduta,
ma lo score non mostra persistenza positiva a 1--5 giorni nel campione di
agosto.

Questi risultati restringono le ipotesi da testare in shadow. Non le convalidano
in modo confermativo: la finestra contiene solo 24 sedute, e' gia' stata
ispezionata attraverso gli Alpha Miss e comprende piu' famiglie di confronti.

## Popolazione e completezza

La base completa contiene 3.748 segnali generati fra il 3 agosto e il 4
settembre, 11.881 intenti S4 e 144 casi Alpha Miss. Sono disponibili outcome a
un giorno per 3.624 segnali (96,7%), a tre giorni per 3.362 (89,7%) e a cinque
giorni per 3.154 (84,2%). Le definizioni sono close-to-close su sedute di borsa e
usano barre aggiustate; non sono rendimenti dal momento intraday del segnale.
Fonti: [manifest del backfill](snapshots/full-signals-2026-08-03_2026-09-05/manifest.json),
[`run_forward_return_worker`](../../../src/workers/performance.py),
[`metrics.json`](analysis/entry-funnel-v1/metrics.json).

I dossier forniscono una timeline point-in-time per 3.667 segnali. Prezzo, MFE,
MAE e rendimento dal momento dello score alla chiusura sono presenti per 3.625
righe (98,9% delle timeline; 96,7% dell'intera popolazione DB). Quarantadue
timeline non hanno il prezzo allo score. Gli 81 segnali del 28 agosto non hanno
una timeline congelata perche' manca il dossier di quella seduta; non sono stati
ricostruiti ex post. Fonti:
[manifest arricchimento](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/manifest.json),
[`signal_stage_outcomes.jsonl`](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/signal_stage_outcomes.jsonl),
[`WEEKLY_FINDINGS_2026-36.md`](../../WEEKLY_FINDINGS_2026-36.md).

## 1. Il ritardo consuma gran parte della finestra utile

Sulle 897 righe per cui lo schema del dossier conserva tutte le latenze, la
mediana pubblicazione--score e' **46,0 minuti** e il p90 **92,8 minuti**. La
mediana pubblicazione--first-seen e' 10,9 minuti; il tratto
first-seen--ingestion vale altri 30,7 minuti. Il valore quasi nullo e leggermente
negativo fra ingestion e score e' un artefatto di ordine dei timestamp
millisecondi, non una latenza economica negativa. Fonte:
[`metrics.json`, `latency_minutes`](analysis/entry-funnel-v1/metrics.json).

Al momento dello score, la mediana della quota di movimento intraday gia'
trascorsa e' **88,8%**; 2.180 osservazioni su 3.622 (60,2%) sono almeno al 75%.
La metrica puo' essere negativa o superiore a uno quando il prezzo oltrepassa o
inverte il percorso open--close, quindi descrive il timing e non una regola di
trading. Sul tratto ancora disponibile fino alla chiusura, il rendimento mediano
e' -0,009% e la media +0,023%; MFE mediana +0,462% e MAE mediana -0,504%.
Fonti: [`metrics.json`, `scored_stage`](analysis/entry-funnel-v1/metrics.json),
[`alpha_miner_dossier.py`](../../../scripts/alpha_miner_dossier.py).

Lettura: ridurre il tempo di scoperta e lavorazione e' una leva distinta dalla
taratura del gate. Cambiare soltanto la soglia non recupera la parte di movimento
gia' avvenuta.

## 2. Il gate 0,30 separa modestamente lo stesso giorno, non la persistenza

Fra i segnali positivi con score almeno 0,30, 257 hanno un outcome intraday non
piatto: il 54,9% prosegue nella direzione positiva fino alla chiusura. Il
rendimento medio dal prezzo allo score alla chiusura e' +0,146%, la mediana
+0,058%. Fra i 1.268 segnali positivi sotto 0,30, l'hit rate e' 48,7%, la media
+0,046% e la mediana -0,010%. Fonte:
[`metrics.json`, `score_buckets`](analysis/entry-funnel-v1/metrics.json).

La separazione non basta a convalidare il gate. Riducendo a un solo ultimo
segnale per ticker/seduta, l'IC cross-sectional medio fra score e rendimento
residuo della stessa seduta e' +0,031 su 24 giorni (`t` descrittivo 0,77). Sui
forward return close-to-close l'IC medio e' invece -0,065 a un giorno, -0,066 a
tre e -0,070 a cinque, rispettivamente su 23, 21 e 19 giorni. I relativi `t`
descrittivi sono -2,59, -1,96 e -1,93, ma non sono corretti per molteplicita',
dipendenza temporale o ispezione precedente del campione. Fonte:
[`metrics.json`, `latest_signal_per_symbol_day`](analysis/entry-funnel-v1/metrics.json).

Lettura: nel campione corrente lo score alto sembra distinguere un po' il
residuo intraday, ma non dimostra continuation multi-day; la possibile
decadenza/reversal deve essere verificata su un campione forward untouched.

## 3. Fallback e fan-out sono segnali di qualita', non ancora gate dimostrati

Nella finestra completa 1.260 segnali su 3.748 (33,6%) sono fallback. Sulle
timeline con outcome, l'hit rate dei segnali long positivi e' 51,0% per
l'ensemble e 47,9% per il fallback; il rendimento mediano fino alla chiusura e'
rispettivamente +0,003% e -0,035%. Nel ledger recente nessuno dei 23 segnali
submitted e' fallback. Fonti:
[`metrics.json`, `fallback_groups`](analysis/entry-funnel-v1/metrics.json),
[`ENTRY_FUNNEL_AUDIT.md`](ENTRY_FUNNEL_AUDIT.md).

Il 55,6% delle timeline (2.038/3.667) deriva da un `content_hash` associato a piu'
ticker nella finestra. L'hit rate long positivo e' 48,9% per il gruppo
multi-ticker e 50,8% per il single-ticker. La differenza e' piccola e la
definizione e' un censimento per hash, non una stima causale del resolver.
Fonte: [`metrics.json`, `fanout_groups`](analysis/entry-funnel-v1/metrics.json).

Lettura: mantenere separati fallback, fan-out e directness e' giustificato; una
nuova esclusione automatica non lo e' ancora.

## 4. Le feature semantiche non sono ancora analizzabili sull'intera finestra

Le 3.748 righe-segnale conservano 7.295 output raw di modello. `event_type`,
`directness`, `materiality` e `novelty` sono presenti soltanto in 1.574 risposte
(21,6%). Si osservano inoltre categorie non canoniche, incluse combinazioni con
`|` e varianti Unicode di `unclear`. Senza un contratto di aggregazione fra i
due modelli e una normalizzazione delle categorie, usare una risposta raw come
feature del ranker sarebbe una scelta post-hoc. Fonti:
[`metrics.json`, `model_feature_coverage`](analysis/entry-funnel-v1/metrics.json),
[`llm_responses` migration](../../../migrations/054_llm_response_relevance.sql).

## 5. Gli Alpha Miss indicano prima copertura e timing, poi gate

I 144 candidati miss valgono 14.942,68 USD se misurati ingenuamente sull'intero
movimento close-to-close, ma soltanto 2.199,74 USD sul tratto dichiarato
accessibile dal primo ciclo e rispettando il vincolo long-only: il 14,7% del
lordo. La differenza mostra perche' il costo close-to-close non deve guidare una
taratura d'ingresso. Il netto e' disponibile solo per 71 casi e non va
confrontato con il totale lordo. Fonti:
[`metrics.json`, `alpha_miss_by_dossier_cause`](analysis/entry-funnel-v1/metrics.json),
[`opportunity.py`](../../../src/analysis/dossier/opportunity.py).

Dei 2.199,74 USD accessibili, i 59 casi `NO_NEWS` rappresentano 1.323,10 USD
(60,1%) e i 51 `BELOW_GATE` 621,78 USD (28,3%). Gli `OFF_TOPIC_NON_DECIDIBILE`
valgono 75,42 USD. Questi sono casi selezionati ex post perche' mover: misurano
dove si concentra il costo osservato, non il rendimento atteso di una nuova
policy. Fonte: [`metrics.json`](analysis/entry-funnel-v1/metrics.json).

Il backfill risolve esattamente tutti i 91 `signal_id` presenti nei dossier, ma
140 riferimenti dei vecchi schemi non portano un ID. Solo 50 dei 91 segnali
identificati hanno anche un `causal_event_id` nel ledger, che inizia il 25 agosto.
I casi `NO_NEWS`, gli ID mancanti e gli intenti stantii dello stesso ticker non
sono stati collegati per prossimita'. Fonti:
[`ALPHA_MISS_ENRICHMENT_AUDIT.md`](ALPHA_MISS_ENRICHMENT_AUDIT.md),
[`alpha_miss_case_signals.jsonl`](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/alpha_miss_case_signals.jsonl).

## 6. Cosa e' possibile concludere adesso

L'evidenza sostiene quattro decisioni di ricerca, non quattro cambiamenti live:

1. misurare separatamente discovery latency e processing latency, perche' il
   ritardo e' abbastanza grande da dominare il tratto catturabile;
2. concentrare la ricerca fonti sui buchi `NO_NEWS` ricorrenti e sui settori
   ciechi, che spiegano la maggior parte dell'opportunita' accessibile osservata;
3. definire prima il contratto di aggregazione/normalizzazione delle feature raw,
   poi testare directness, event type, materiality e novelty in shadow;
4. confrontare in shadow ultimo-segnale, stato aggregato evento/ticker e gate
   0,30 su un campione forward untouched, con famiglie di test pre-registrate.

I 23 segnali submitted sono troppo pochi per una decisione sull'esecuzione: 21
hanno una timeline di dossier e mostrano un hit rate intraday del 65%, ma la
numerosita' e la selezione del funnel impediscono di generalizzare. Fonte:
[`metrics.json`, `submission_groups`](analysis/entry-funnel-v1/metrics.json).

La conseguenza operativa immediata e' quindi mantenere S4 invariata, completare
la matrice di ipotesi con questi risultati e avviare una raccolta forward
versionata. La scelta di nuove fonti puo' procedere in parallelo, mirata alle
lacune documentate, senza attendere il verdetto statistico finale.
