# Alpha Miss enrichment audit

Data dell'audit: 2026-09-08

## Aggiornamento dopo il backfill completo

Il backfill read-only eseguito successivamente a questo primo censimento ha
esteso `signals.jsonl` dai soli 644 segnali presenti nel ledger S4 a tutti i
**3.748 segnali** generati nella finestra 2026-08-03--2026-09-04. Di conseguenza,
tutti i **91 riferimenti dotati di `signal_id`** nei 24 dossier ora si uniscono
esattamente a una riga del DB; i controlli su ticker, data e score non mostrano
discordanze. I 140 riferimenti rimanenti non hanno invece un `signal_id` nel
dossier legacy e restano `UNKNOWN`: il backfill non autorizza un fuzzy match.

Il ledger degli intenti nasce il 25 agosto e conserva un `causal_event_id` per
50 dei 91 riferimenti espliciti. Per gli altri 41 il segnale DB e' identificato,
ma non va inventato un evento S4 retroattivo. Inoltre 3.667 dei 3.748 segnali
hanno una timeline di dossier completa; gli 81 segnali del 28 agosto non hanno
uno snapshot di prezzo congelato, perche' il dossier di quella seduta manca.

Gli artefatti aggiornati sono
[`full-signals-2026-08-03_2026-09-05`](snapshots/full-signals-2026-08-03_2026-09-05/manifest.json)
e
[`alpha-miss-2026-08-03_2026-09-04-v1`](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/manifest.json).
I conteggi delle sezioni successive descrivono intenzionalmente il primo
snapshot ristretto al ledger e restano come traccia della progressione
dell'audit; questo aggiornamento ne sostituisce i limiti di copertura.

## Esito

L'arricchimento e' possibile senza inferenze post-hoc, ma deve avere due grane
distinte:

1. un **caso Alpha Miss** e' identificato da `(session_date, ticker)`;
2. i suoi eventuali segnali formano una relazione uno-a-molti identificata da
   `(session_date, ticker, signal_id)`.

Non esiste in generale un solo `causal_event_id` per caso: un candidato puo'
avere zero, uno o molti segnali. Il `causal_event_id` va copiato soltanto da una
riga dello snapshot con lo stesso `signal_id`; per `NO_NEWS` e per i segnali che
non compaiono nel ledger resta `UNKNOWN`. Questa regola segue la grana dichiarata
dallo snapshot (una riga per segnale in `signals.jsonl`, una per intento in
`intents.jsonl`) e la grana dei candidati del dossier. Fonti:
[`manifest.json`](snapshots/ledger-2026-08-25_2026-09-05/manifest.json),
[`export_s4_entry_funnel_snapshot.py`](../../../scripts/export_s4_entry_funnel_snapshot.py),
[`alpha_miner_dossier.py`](../../../scripts/alpha_miner_dossier.py).

## Corpus e sovrapposizione temporale

Il repository contiene 30 report Alpha Miss e 24 dossier congelati. I dossier
coprono 144 casi `candidati_miss`, 231 riferimenti a segnali e sei versioni di
schema (`2.0`, `2.1`, `2.5`, `2.6`, `2.7`, `2.8`). Lo snapshot S4 copre invece
otto sedute, dal 2026-08-25 al 2026-09-03, con 11.881 intenti e 644 segnali
distinti. Fonti: `docs/ALPHA_MISS_REPORT_*.md`,
[`docs/evidence/dossier/`](../../evidence/dossier/),
[`manifest.json`](snapshots/ledger-2026-08-25_2026-09-05/manifest.json).

Sette sedute hanno contemporaneamente dossier, report e snapshot: 25, 26, 27 e
31 agosto; 1, 2 e 3 settembre. Contengono 39 dei 144 casi del corpus (27,1%);
gli altri 105 casi sono fuori dalla sovrapposizione. Il 28 agosto ha 1.711
intenti nello snapshot ma non ha un dossier o report congelato nel tree; il
fallimento del job che doveva produrli e' registrato dalla sintesi settimanale.
Il 4 settembre ha dossier e report, ma zero `intenti_ingresso_s4`, e il manifest
termina al 3 settembre; il ledger dei finding attribuisce il buco alla migrazione
060 non applicata. Fonti:
[`WEEKLY_FINDINGS_2026-36.md`](../../WEEKLY_FINDINGS_2026-36.md),
[`2026-09-04.json`](../../evidence/dossier/2026-09-04.json),
[`ALPHA_MISS_REPORT_2026-09-04.md`](../../ALPHA_MISS_REPORT_2026-09-04.md),
[`findings.json`, F-068](../../evidence/findings.json),
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl).

La Week 34 e' interamente precedente allo snapshot e quindi non offre join di
riga; la Week 36 copre 22 casi nelle quattro sedute 31 agosto-3 settembre, tutte
nello snapshot. Le sintesi settimanali restano utili come classificazione
revisionata, non come chiave di join. Fonti:
[`WEEKLY_FINDINGS_2026-34.md`](../../WEEKLY_FINDINGS_2026-34.md),
[`WEEKLY_FINDINGS_2026-36.md`](../../WEEKLY_FINDINGS_2026-36.md).

## Risultato quantitativo dei join esatti

I conteggi seguenti sono stati ricalcolati sui sette dossier sovrapposti usando
solo uguaglianze esatte. `signal_id` e `intent_id` vengono letti da
`candidati_miss[].segnali[]` e `intenti_ingresso_s4[]`; le controparti provengono
da `signals.jsonl` e `intents.jsonl`. Fonti:
`docs/evidence/dossier/2026-08-{25,26,27,31}.json`,
`docs/evidence/dossier/2026-09-{01,02,03}.json`,
[`signals.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/signals.jsonl),
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl).

| Misura | Join possibile | Join impossibile / `UNKNOWN` |
|---|---:|---:|
| Casi con chiave esatta `(session_date, ticker)` | 39/39 (100%) | 0 |
| Casi con almeno un segnale nel dossier | 23/39 | 16/39 senza segnale |
| Riferimenti `signal_id` dei casi | 46/62 (74,2%) | 16/62 (25,8%) |
| Casi con segnali e almeno un `signal_id` risolto | 21/23 (91,3%) | 2/23 senza alcun segnale risolto |
| Casi con tutti i propri `signal_id` risolti | 13/23 (56,5%) | 8 parziali + 2 senza join |
| Righe `intenti_ingresso_s4` | 10.170/10.170 (100%) | 0 |
| Riferimenti a segnale con `causal_event_id` esplicito | 46/62 (74,2%) | 16/62 (25,8%) |
| Riferimenti con intento nella stessa seduta del caso | 45/62 (72,6%) | 17/62 |

Le 46 corrispondenze di segnale superano quattro controlli indipendenti: 46/46
hanno ticker uguale, giorno di `generated_at` uguale alla data del dossier,
score numericamente identico e `canonical_article_id` uguale a
`"content:" + content_hash`. Inoltre, nello snapshot ognuno dei 644
`signal_id` ha esattamente un `causal_event_id` e un ticker, e gli 11.881
`intent_id` sono unici e privi di null nelle chiavi critiche. Fonti:
[`signals.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/signals.jsonl),
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl),
[`manifest.json`](snapshots/ledger-2026-08-25_2026-09-05/manifest.json),
`docs/evidence/dossier/2026-08-{25,26,27,31}.json`,
`docs/evidence/dossier/2026-09-{01,02,03}.json`.

Dettaglio per seduta, derivato dalle stesse fonti:

| Seduta | Schema | Casi | Riferimenti segnale | Segnali risolti | Casi con almeno un join | Intenti dossier/snapshot |
|---|---:|---:|---:|---:|---:|---:|
| 2026-08-25 | 2.5 | 4 | 7 | 4 | 2 | 1.494 / 1.494 |
| 2026-08-26 | 2.5 | 5 | 3 | 1 | 1 | 1.518 / 1.518 |
| 2026-08-27 | 2.5 | 8 | 9 | 8 | 4 | 1.700 / 1.700 |
| 2026-08-31 | 2.6 | 4 | 8 | 5 | 3 | 1.237 / 1.237 |
| 2026-09-01 | 2.6 | 5 | 9 | 9 | 3 | 1.189 / 1.189 |
| 2026-09-02 | 2.6 | 5 | 5 | 5 | 3 | 1.438 / 1.438 |
| 2026-09-03 | 2.7 | 8 | 21 | 14 | 5 | 1.594 / 1.594 |

Un solo segnale risolto non ha una disposizione nella seduta del caso: ADBE
`signal_id=9170`, generato il 27 agosto, compare nel ledger soltanto dal 28
agosto con `causal_event_id=news:9170`. L'identita' segnale-evento e' quindi
esatta, ma la disposizione relativa al caso del 27 agosto resta `UNKNOWN`.
Fonti: [`2026-08-27.json`](../../evidence/dossier/2026-08-27.json),
[`signals.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/signals.jsonl),
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl).

## Perche' 16 segnali non si uniscono

`signals.jsonl` non e' l'intera tabella `sentiment_signals`: l'exporter costruisce
la popolazione dai soli `signal_id` presenti negli eventi candidati S4 nella
finestra. Percio' l'assenza di un segnale dal file prova soltanto che quel
segnale non e' entrato in questa popolazione; non prova se sia stato
sovrascritto, filtrato a monte o escluso per un'altra ragione. La causa resta
`UNKNOWN`. Fonte:
[`export_s4_entry_funnel_snapshot.py`, CTE `population`](../../../scripts/export_s4_entry_funnel_snapshot.py).

I riferimenti non risolti sono:

| Seduta | Ticker | `signal_id` |
|---|---|---:|
| 2026-08-25 | HOOD | 8879, 8906, 8908 |
| 2026-08-26 | HOOD | 8982, 9036 |
| 2026-08-27 | INTC | 9168 |
| 2026-08-31 | TSLA | 9326, 9371 |
| 2026-08-31 | BABA | 9307 |
| 2026-09-03 | NOW | 9655 |
| 2026-09-03 | SPCX | 9735 |
| 2026-09-03 | ORCL | 9721 |
| 2026-09-03 | TSLA | 9619, 9744, 9747 |
| 2026-09-03 | META | 9689 |

Fonti: `docs/evidence/dossier/2026-08-{25,26,27,31}.json`,
`docs/evidence/dossier/2026-09-03.json`,
[`signals.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/signals.jsonl).

## NO_NEWS e intenti stantii

Dei 16 casi senza segnali, cinque hanno comunque uno o piu' intenti sullo stesso
ticker e nella stessa seduta: NVO 25 agosto, DB 26 agosto, PLTR e BIDU 27 agosto,
PLTR 1 settembre. Sono intenti che puntano a segnali precedenti, non al mover
senza news. Collegarli al caso come causa sarebbe un errore. Possono essere
conservati soltanto come contesto `same_session_ticker_intent`, con
`causal_link=false`; gli altri 11 casi senza segnali non hanno neppure questo
contesto. Fonti: `docs/evidence/dossier/2026-08-{25,26,27}.json`,
[`2026-09-01.json`](../../evidence/dossier/2026-09-01.json),
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl).

In totale 28 dei 39 casi hanno almeno un intento dello stesso ticker nella
stessa seduta, ma soltanto 21 hanno almeno un `signal_id` del caso risolto nello
snapshot. Il primo numero misura contesto operativo; il secondo misura un link
causale difendibile. Fonti: gli stessi sette dossier e
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl).

## Finding e sintesi settimanali

`findings.json` contiene 179 occorrenze la cui fonte e' un Alpha Miss: 103 sono
precedenti allo snapshot, 73 cadono nelle otto sedute dello snapshot e tre sono
del 4 settembre. Le 73 occorrenze contemporanee possono essere collegate in
modo deterministico **solo alla seduta**. Ogni oggetto `occorrenze[]` ha infatti
soltanto `data`, `costo_usd`, `nota` e `fonte`: non esistono campi strutturati per
ticker, `signal_id`, `causal_event_id` o `intent_id`. Fonte:
[`findings.json`](../../evidence/findings.json).

Alcune note narrative contengono ID letterali, ticker o titoli, ma un parser di
testo non e' un contratto di identita'. Un ID letterale puo' essere promosso a
link soltanto con una riga di bridge curata che conservi `source_path`, sezione,
testo letterale e verifica di esistenza nello snapshot. Un finding aggregato
come F-001 (copertura di seduta) o una conclusione settimanale non va replicato
su ogni segnale della seduta: quello introdurrebbe pseudo-osservazioni e una
causalita' non dichiarata. Fonti:
[`findings.json`](../../evidence/findings.json),
[`WEEKLY_FINDINGS_2026-34.md`](../../WEEKLY_FINDINGS_2026-34.md),
[`WEEKLY_FINDINGS_2026-36.md`](../../WEEKLY_FINDINGS_2026-36.md).

La Week 36 afferma inoltre che la categoria meccanica del dossier e la rilettura
dell'analista divergono sugli stessi 22 casi. Vanno quindi conservate in colonne
separate (`dossier_cause`, `analyst_cause`, `analyst_source`), senza
sovrascrivere la prima con la seconda. Fonte:
[`WEEKLY_FINDINGS_2026-36.md`, sezione "Miss causes"](../../WEEKLY_FINDINGS_2026-36.md).

## Contratto deterministico consigliato

La tabella di arricchimento dovrebbe essere normalizzata in tre artefatti:

### `alpha_miss_cases`

- `case_id = "alpha-miss:" + session_date + ":" + ticker`;
- `session_date`, `ticker`, rendimento, causa meccanica e opportunity vengono
  copiati da `candidati_miss[]`;
- `analyst_cause` resta separata e cita il report o la sintesi che la assegna;
- `case_missingness` elenca almeno `NO_SIGNAL`, `NO_OVERLAPPING_SNAPSHOT` e
  `MISSING_FROZEN_DOSSIER`.

Fonte della grana e dei campi:
[`alpha_miner_dossier.py`](../../../scripts/alpha_miner_dossier.py),
[`docs/evidence/dossier/`](../../evidence/dossier/).

### `alpha_miss_case_signals`

- una riga per `case_id, signal_id` presente nel dossier;
- join allo snapshot esclusivamente con uguaglianza su `signal_id`;
- dopo il join, controllo obbligatorio di ticker, giorno generazione, score e
  `canonical_article_id/content_hash`;
- `causal_event_id` copiato dalla relazione univoca osservata in
  `intents.jsonl`, mai costruito assumendo che `signal_id == news_log_id`;
- se il segnale non compare nello snapshot, `causal_event_id=UNKNOWN` e
  `missing_reason=SIGNAL_NOT_IN_INTENT_POPULATION`.

Fonti:
[`signals.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/signals.jsonl),
[`intents.jsonl`](snapshots/ledger-2026-08-25_2026-09-05/intents.jsonl),
[`export_s4_entry_funnel_snapshot.py`](../../../scripts/export_s4_entry_funnel_snapshot.py).

### `alpha_miss_annotations`

- `annotation_id`, `finding_id`, `source_path`, `source_locator`;
- `scope_kind` in `CASE`, `SIGNAL`, `INTENT`, `SESSION`, `WINDOW`;
- chiavi nullable: `session_date`, `ticker`, `signal_id`, `causal_event_id`,
  `intent_id`;
- `link_method` in `STRUCTURED_DOSSIER_KEY`, `EXACT_ID_LITERAL`,
  `SESSION_ONLY`, `UNKNOWN`;
- nessuna espansione automatica da `SESSION`/`WINDOW` verso segnali o intenti.

Fonti del bisogno di distinguere le grane:
[`findings.json`](../../evidence/findings.json),
[`WEEKLY_FINDINGS_2026-34.md`](../../WEEKLY_FINDINGS_2026-34.md),
[`WEEKLY_FINDINGS_2026-36.md`](../../WEEKLY_FINDINGS_2026-36.md).

## Join vietati

Per preservare la natura forward e non introdurre scelta ex post, non sono
difendibili:

- associare un caso al segnale temporalmente piu' vicino;
- associare un `NO_NEWS` a un intento stantio dello stesso ticker;
- scegliere fra piu' segnali quello con score o outcome piu' favorevole;
- fare fuzzy match sul titolo quando manca `signal_id`;
- assumere che `signal_id`, `news_log_id` e il suffisso di `causal_event_id`
  coincidano per costruzione;
- propagare un finding di seduta o settimana a tutte le righe sottostanti.

Questi divieti discendono dai casi uno-a-molti nei dossier, dalla popolazione
ristretta dell'exporter e dall'assenza di chiavi strutturate nelle occorrenze dei
finding. Fonti:
[`alpha_miner_dossier.py`](../../../scripts/alpha_miner_dossier.py),
[`export_s4_entry_funnel_snapshot.py`](../../../scripts/export_s4_entry_funnel_snapshot.py),
[`findings.json`](../../evidence/findings.json).

## Conclusione operativa

Il backfill richiesto e' ora completato: i 144 casi sono materializzati, tutti
i 91 riferimenti dotati di ID hanno un join DB esatto e le 179 annotazioni Alpha
Miss sono conservate alla loro grana di seduta. Restano due limiti non
recuperabili con un join automatico: i 140 riferimenti dei dossier legacy privi
di `signal_id` e gli 81 segnali del 28 agosto privi di dossier congelato. La
catena S4 puo' inoltre essere dichiarata soltanto per i 50 riferimenti che hanno
un `causal_event_id` osservato nel ledger; gli altri non vengono ricostruiti per
prossimita'. Fonti:
[`manifest completo`](snapshots/full-signals-2026-08-03_2026-09-05/manifest.json),
[`manifest arricchimento`](enrichment/alpha-miss-2026-08-03_2026-09-04-v1/manifest.json),
[`WEEKLY_FINDINGS_2026-36.md`](../../WEEKLY_FINDINGS_2026-36.md),
[`findings.json`, F-068](../../evidence/findings.json).
