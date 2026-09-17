# Audit di compatibilità del protocollo forward S4

**Fotografia:** 2026-09-08T10:23:57+02:00  
**Perimetro:** sola lettura di codice, configurazione, tracker e viste PostgreSQL shadow.  
**Esclusioni:** nessuna modifica al comportamento live; nessun uso di Llama/Ollama; nessun
risultato intermedio P0/P1 letto o pubblicato.

## Esito

La strumentazione shadow P0/P1 è attiva e sta producendo coppie coerenti, ma **il campione
confirmatory non è ancora iniziato**. Le righe oggi disponibili sono telemetria pre-`n=0`, utile
per collaudare e stimare la varianza in cieco, non evidenza forward su cui promuovere, respingere o
tarare S4.

I blocchi formali sono quattro:

1. `sample.n0_date` è `null` e `n0_fixed` è `false`;
2. `power.N_cluster.value` è `null`;
3. il gate atomico #301 è ancora `waiting` e dipende dal valutatore #299, tuttora aperto;
4. il ledger d'ingresso live non riceve nuove righe dal 2026-09-04 perché il codice scrive due
   colonne della migrazione 060 che nel DB non esistono.

Separatamente, il vecchio verdetto IC di `compute_s4_ic.py` resta esplicitamente non conforme alla
pre-registrazione: legge popolazione `tutti` a 1 giorno, non la popolazione tradabile solo-ensemble
con `|score| >= 0,30` a 2 sedute.

## Matrice di compatibilità

| Area | Requisito congelato | Evidenza osservata | Stato | Azione necessaria |
|---|---|---|---|---|
| Contratto | Un solo protocollo datato, shadow-only | `s4_exit_trial.yaml` v1.0.0, firmato 2026-08-22; nessuna uscita live autorizzata | **PASS** | Non modificarlo fuori dal registro formale |
| Policy | P0 benchmark as-is; P1 D+2 time-only; P2 omitted | P0 e P1 `active`, P2 `omitted`; P1 è collegata al reconciler intraday | **PASS** | Conservare la famiglia P0/P1 fino al gate |
| Semantica temporale | D0 = primo fill RTH; uscita P1 alla close di D0+2; calendario Alpaca | Implementata nel lifecycle/P1 runtime e coperta dai test | **PASS tecnico** | Il gate #301 deve congelarne hash e provenance a `n=0` |
| Integrità lifecycle | Almeno 95% ricostruibile | 23/23 lifecycle correnti ricostruibili, su 7 date D0 | **PASS provvisorio (100%)** | Ripetere sul segmento post-`n=0`; la vista corrente include correzioni retroattive |
| Comparabilità | Stessi intenti, fill, notional e costi fra P0/P1 | 23/23 intenti hanno entrambe le policy comparabili; 14 coppie sono chiuse | **PASS tecnico** | Validare nel gate atomico, non attribuire valore confirmatory alle righe attuali |
| Unità inferenziale | Cluster event-day, bootstrap a blocchi, intervalli unilaterali | Bridge usa D0-session come proxy conservativo; blocchi di 2 sedute, 10.000 resample, seed fissato | **PASS con limite** | Aggiungere un vero `causal_event_id` al ledger futuro; oggi eventi distinti nello stesso giorno collassano |
| Numerosità exit | `N_cluster` derivato in cieco da MDE, varianza, potenza e dipendenza | 14 coppie chiuse su 6 cluster; soglia di proposta monitor = 20 osservazioni; `N_cluster=null` | **BLOCKED** | Attendere almeno 20 coppie chiuse, proporre `N_cluster` dalla sola varianza e farlo approvare/congelare |
| Avvio campione | Snapshot atomico immutabile con `n0` e tutte le versioni | `n0_date=null`, `n0_fixed=false`; #301 `waiting` | **BLOCKED** | Completare #299, poi implementare/eseguire #301 e solo allora iniziare il conteggio forward |
| Valutatore exit | PROMOTE/REJECT/INCONCLUSIVE, no early stop, ledger varianti e metriche complete | Modulo deterministico e bridge presenti; 59 test mirati passano. #299 è però aperto e alcune metriche/ledger sono pure ma non risultano ancora persistiti nel report operativo | **GAP roadmapped** | Chiudere i criteri residui di #299 con PR `closes #299`; nessuna analisi decisionale prima |
| Ledger d'ingresso | Popolazione, rank, aging, collisione e motivi osservabili end-to-end | DB senza `held_at_rank` e `signal_age_at_slot`; 3.188 righe il 03/09, zero dal 04/09 | **BLOCKED correttezza** | Applicare/automatizzare la migrazione 060 e verificare un'intera seduta; il 04/09 resta non recuperabile |
| IC ingresso R2 | Solo-ensemble tradabile, `|score|>=0,30`, ultimo simbolo-giorno, D+2, HAC | `_esito()` legge ancora `sintesi["tutti"]["1g"]` | **BLOCKED** | Allineare il valutatore prima di qualunque verdetto; non reinterpretare l'IC retrospettivo come OOS |
| Economia R3 | Excess return netto vs equal-weight watchlist, LCB95 unilaterale > 0 | L'audit corrente misura l'opportunità e il funnel, ma non implementa questo gate forward | **GAP** | Inserire benchmark e intervallo nel dataset/report congelato di #301 |
| Indipendenza R4 | Overlap intenti S1 <= 50%, altrimenti valore incrementale | Misura storica disponibile ma censurata/limitata; non esiste ancora una misura forward congelata | **GAP** | Congelare definizione e calcolare overlap sul medesimo segmento post-`n=0` |
| Modifiche fonti | Qualunque cambio source/resolver/model/gate dopo `n=0` forza restart | Audit fonti completato; le PoC SEC/Twelve non sono ancora eseguite e `n=0` non è fissato | **PASS procedurale** | Misurare e decidere le fonti prima di `n=0`, oppure registrare esplicitamente il restart |

## Fotografia quantitativa del DB shadow

Query eseguite dentro una transazione `READ ONLY` sul DB locale:

| Misura | Valore |
|---|---:|
| lifecycle correnti | 23 |
| lifecycle ricostruibili | 23 (100%) |
| date D0 coperte | 7 (`2026-08-25` – `2026-09-03`) |
| righe correnti P0/P1 | 46 |
| intenti appaiati P0/P1 | 23 |
| coppie chiuse su entrambe le policy | 14 |
| cluster D0 con coppie chiuse | 6 |
| righe raw `s4_exit_policy_events` | P0 90; P1 102 |
| righe raw eccedenti gli intenti distinti | P0 67; P1 79 |
| ultime righe `s4_intent_events` | 3.188 il 2026-09-03; zero dal 2026-09-04 |
| colonne migrazione 060 presenti | 0/2 |

Le molte righe raw ripetute non gonfiano oggi il report perché
`s4_exit_policy_current` sceglie una sola proiezione per `(intent_id, policy_id)`. Restano però un
difetto del ledger append-only: un consumer che contasse direttamente gli eventi sovrastimerebbe le
osservazioni. La correzione va inclusa nei controlli del gate #301.

## Relazione con l'audit dell'ingresso

L'audit retrospettivo appena completato ha chiarito dove formulare le domande, non ha creato un
campione OOS. In particolare:

- publish-to-score mediano 46,0 minuti e p90 92,8 minuti;
- il punto di scoring cade in mediana all'88,8% del movimento intraday;
- il gate `score >= 0,30` separa poco il lato long nel campione storico;
- i forward return a 1/3/5 giorni mostrano IC medi negativi, ma sono esplorativi e non sostituiscono
  la metrica preregistrata D+2 sulla popolazione realmente tradabile;
- `NO_NEWS` pesa il 60,1% dell'opportunità accessibile degli Alpha Miss, quindi il rischio di supply
  è abbastanza grande da dover essere affrontato prima di congelare le fonti a `n=0`.

Queste evidenze giustificano un audit delle fonti e la riparazione della strumentazione; **non**
giustificano oggi cambiare soglia, holding, sizing o universo. Quelle decisioni restano nel ticket
post-freeze #289.

## Sequenza operativa raccomandata

1. Ripristinare il ledger d'ingresso applicando la migrazione 060 e aggiungere una guardia di deploy
   che fallisca se codice e schema divergono. Conservare il 04/09 come outage, non imputarlo.
2. Portare #299 a chiusura formale: integrare nel report le metriche e il ledger delle varianti che
   oggi esistono solo come primitive, verificando che i criteri della issue siano tutti soddisfatti.
3. Alla soglia blinded di 20 coppie chiuse, derivare una proposta di `N_cluster` senza pubblicare
   media, segno o ranking P0/P1; l'approvazione è un atto umano sul contratto.
4. Eseguire le prove shadow raccomandate dall'audit `NO_NEWS`: SEC EDGAR e Twelve Data sulla coorte
   cieca; trattare Alpaca WebSocket come test di latenza separato. Scegliere le fonti prima del gate:
   un cambio dopo l'avvio sarebbe materiale e imporrebbe restart.
5. Implementare #301: snapshot atomico di versioni, policy hash, source/model/resolver, universo,
   gate, rank/sizing, collisione S1, calendario, fill e cost model; fissare `n0` solo se ogni controllo
   passa.
6. Dal primo dato successivo a `n0`, raccogliere il vero segmento forward senza guardare gli effetti;
   monitorare solo integrità, sicurezza e statistiche blinded fino a `N_cluster`.
7. Solo al termine valutare congiuntamente R1–R4 e passare l'esito a #289. Nessun risultato modifica
   automaticamente il live.

## Riferimenti interni

- `docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md`, §§2–5 e §8.
- `config/s4_exit_trial.yaml`, contratto macchina del trial exit.
- `config/s4_kill_criterion.yaml`, avvertenza sul disallineamento del verdetto IC.
- `src/workers/performance.py`, wiring shadow P0/P1 nel reconciler intraday.
- `src/strategies/s4/evaluator_bridge.py`, adattamento coppie e blocco fail-closed senza `N_cluster`.
- `docs/research/s4-entry-audit-2026-09-07/ENTRY_FUNNEL_FINDINGS_2026-09-08.md`.
- `docs/research/s4-entry-audit-2026-09-07/NO_NEWS_SOURCE_AUDIT_2026-09-08.md`.
- Issue roadmap: #299 (valutatore), #301 (gate `n=0`), #289 (decisioni post-freeze), #511
  (blind spot persistente delle fonti).
