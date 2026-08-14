# Analisi di fattibilità tecnica — uscite S4

**Data dell'analisi:** 2026-08-14

**Baseline analizzata:** `main@4eebb89c71ec31e09ec5093de56f3ac42890693f`

**Branch della consegna:** `research/s4-exit-feasibility-20260814`

**Oggetto:** stato del runtime S4 e fattibilità di tutte le raccomandazioni delle
sezioni 5–9 di `consolidato_exit.md`. Questa consegna è solo documentale: non
modifica strategie, scheduler, ordini o configurazione live.

## Sintesi esecutiva

La policy raccomandata — D+2 come holding massima, counter qualificato come
unica uscita alpha anticipata e `d_hard` come overlay comune — **non è
implementata**. L'uscita S4 resta un comportamento emergente della
ricostruzione dei target: se un simbolo scompare dal top-5 o da uno dei gate, il
suo target può sparire e l'orchestrator vende la posizione. In parallelo, un
reversal su un singolo score negativo può liquidare l'intera posizione broker,
anche se condivisa con S1.

Il fix `#236` è invece presente nella baseline: la provenienza FIX-D viene
portata nel DataFrame e `_signals_as_of()` esenta le righe preservate dal
secondo filtro di età
(`src/workers/portfolio_scheduler.py:740-774,3658-3694`;
`src/strategies/s4/strategy.py:156-188`). Risolve una doppia filtratura, non
introduce il lifecycle D+2 e non neutralizza le altre exit spurie.

Il cambio fedele richiede:

1. stato persistente per intento e sleeve (`entry_fill`, D0,
   `due_session`, tesi e `policy_version`);
2. policy S4 che distingua ingresso, mantenimento e uscita;
3. session clock e confine di esecuzione nel scheduler;
4. ledger e broker virtuale per P0/P1/P2;
5. dati point-in-time aggiuntivi per il counter qualificato;
6. attribuzione per sleeve, perché il broker espone una posizione aggregata.

Le **circa 213 sedute** della pre-registrazione riguardano il gate IC che decide
se S4 merita capitale, non il paired exit test. Quest'ultimo richiede un
`N_cluster` distinto, derivato prima del sample start da MDE, varianza dei
delta e dipendenza per evento/giorno. Oggi non è quindi possibile promettere una
data per il verdetto sulle exit.

## 1. Stato di fatto

### 1.1 Perimetro Git e modifiche già presenti

L'audit è stato rifatto sul `main` locale corrente, commit completo
`4eebb89c71ec31e09ec5093de56f3ac42890693f`, invece che sul precedente
`agent/issue-278@4ac8fec`.

| Commit | Contenuto | Stato nella baseline | Impatto runtime exit |
|---|---|---|---|
| `8892f74` | Quattro analisi sull'orizzonte S4 e consolidamento precedente | presente | nessuno, evidence |
| `07ca087` | Nuova pre-registrazione, `config/s4_kill_criterion.yaml`, aggiornamento IC | presente | nessuna nuova exit; cambia governance/evaluator atteso |
| `9388baf` | Packet multi-LLM sulle exit S4 | presente | nessuno, documentazione |
| `d455133` | Dossier evidence 2026-08-13 e preservazione log | presente | nessuno sulla policy di uscita |
| `60c6ae0` | Fix `#236`: preserva la provenance FIX-D fino a `_signals_as_of()` | presente e registrato dal commit `4eebb89` | corregge la doppia scadenza, ma non implementa D+2 |
| `42320f0` / merge `d7599cf` | Rimisura overlap S1∩S4 | presente | diagnostica; nessun lifecycle per sleeve |

Le quattro risposte, `consolidato_exit.md` e questa analisi erano fuori da
`HEAD` nel worktree precedente; il presente branch esiste per renderli
tracciati. Non esiste un commit che implementi la nuova policy di uscita.

La query live `gh issue list --state open` è stata eseguita il 2026-08-14.
Sono aperte, fra le altre, `#179`, `#182`, `#242`, `#243`, `#244` e
`#246`. Le issue `ready-for-human` restano decisioni, non autorizzazione a
modificare il runtime.

### 1.2 Come S4 decide oggi

La configurazione dichiara `n_top=5`, bucket 10%, slot fissi, lookback 96 ore,
`max_signal_age_hours=4` e frequenza `DAILY`
(`src/strategies/s4/config.py:9-42`). Il ranker:

- conserva il segnale più recente per simbolo e applica i filtri di confidence
  e score (`src/strategies/s4/ranking.py:164-190`);
- ordina e tronca al top-5 (`src/strategies/s4/ranking.py:85-117`);
- assegna ogni slot a `1/n_top` con sizing fisso
  (`src/strategies/s4/ranking.py:128-147`).

Nel percorso live il worker aggiunge freshness d'ingresso, esclusione fallback,
signal-age, FIX-D, signal velocity e il gate dinamico
`feedback:entry_threshold:S4`
(`src/workers/portfolio_scheduler.py:3555-3763`). Questi gate sono nati per
l'ingresso ma, dato che il target viene ricostruito ad ogni ciclo, possono
ancora influenzare il mantenimento.

### 1.3 Trigger di uscita correnti

| Percorso | Trigger effettivo | Clock | Effetto |
|---|---|---|---|
| Target-weight zero | Simbolo assente dal target merged o peso zero (`src/portfolio/orchestrator.py:183-265`) | ogni portfolio cycle | SELL/trim sulla posizione aggregata |
| Rank/drop | Fuori top-5 o filtri del ranker falliti (`src/strategies/s4/ranking.py:85-117,164-190`) | ogni ciclo | il target sparisce; non esiste una branch “rank exit” |
| Freshness/silenzio | query vuota, segnale oltre 4h o gate falliti (`src/workers/portfolio_scheduler.py:3555-3763`) | wall clock, ogni ciclo | target zero/drop; FIX-D copre solo il caso preservato |
| Reversal | ultimo record non-fallback sotto la soglia env (`src/workers/portfolio_scheduler.py:4192-4264`) | ogni ciclo | cancella stop e vende tutta la quantità del simbolo (`:4072-4190`) |
| Stop sintetico | breach di `d_init` | ogni ciclo | oggi disattivato da `stop_loss: 0.0` (`config/trading.yaml:172-194`) |
| `d_hard` broker | stop GTC largo 12–20% | broker continuo | stop reale, whole-share floor (`src/config.py:230-236`; `src/portfolio/fractional_stop_orders.py:62-99`) |
| TP non-fractionable | bracket a prezzo +6% | broker | exit attiva soltanto su strumenti non fractionable (`src/workers/portfolio_scheduler.py:3955-4012`) |

Le reason label classificano a posteriori il comportamento; non governano il
lifecycle. La tassonomia corrente include `no_signal`, `expired`,
`whipsaw`, `unknown`, `fallback_filtered`,
`entry_freshness_filtered` e `below_entry_gate`
(`src/portfolio/exit_classification.py:24-89`).

### 1.4 Il clock dichiarato non è quello applicato

`S4Config.rebalance_frequency` è `DAILY`
(`src/strategies/s4/config.py:40-42`) e `_should_rebalance()` supporta una
decisione al giorno (`src/strategies/s4/strategy.py:206-215`). Tuttavia il
clock persistito comprende soltanto S1
(`src/workers/portfolio_scheduler.py:403-495`) e ogni task ricrea S4 senza
ripristinare `_last_rebalance` (`:3764-3770`).

S4 viene quindi rivalutata alle `:07/:22/:37/:52` fra le 14 e le 21 UTC
(`src/workers/celery_app.py:196-202`). Il market clock controlla soltanto
`is_open` e documenta il limite dei crontab UTC su DST ed early close
(`src/workers/market_clock.py:1-38`); non esiste un trigger “close di D+2”.

### 1.5 Uso di `economic_pnl.json`

Nel worktree sorgente `docs/evidence/economic_pnl.json` era modificato ma non
committato. È stato usato soltanto come controllo contestuale per verificare che
la serie S4 e `scoreboard.s4_vs_200` non cambiassero nella rigenerazione
osservata. **Il file non è stato copiato, aggiunto o committato in questo
branch.** Nessuna conclusione confirmatoria del dossier dipende da quella
versione non tracciata.

## 2. Fattibilità delle componenti principali

Scala: **S** ≤1 giorno-persona, locale e a basso impatto; **M** 2–3
giorni-persona; **L** >3 giorni-persona o cambio di architettura/dati. Le stime
assumono un solo implementatore e includono test mirati, ma escludono review,
deploy e raccolta del campione. Le attività condividono infrastruttura e non
vanno sommate meccanicamente.

### 2.1 D+2 time-stop — **L, 4–7 giorni-persona**

Non esistono `entry_session`, `due_session` o uno stato per policy. Lo
strategy produce target correnti (`src/strategies/s4/strategy.py:58-115`) e
l'orchestrator genera delta sull'aggregato
(`src/portfolio/orchestrator.py:129-265`). I timestamp dei trade sono legati
alla submission, non costituiscono da soli il fill broker necessario a definire
D0.

Servono lifecycle per intento/sleeve, fill reconciliation, market calendar,
ordine di close idempotente e quantità virtuale S4. Un timer nel solo scheduler
sarebbe un time-stop di simbolo, non dell'intento S4.

### 2.2 Counter qualificato — **L, 5–10 giorni-persona**

La soglia corrente ha default −0,20 (`src/config.py:264-279`), mentre il
consolidato congela `score <= -0,30`. Il reversal live usa l'ultimo record
Redis, filtra fallback/età, ma non verifica origine S4, ticker-valid, novelty,
tesi o due notizie distinte
(`src/workers/portfolio_scheduler.py:4192-4264`). La history Redis conserva
score, non identità e provenance complete
(`src/store/redis_store.py:112-134`).

Il data model LLM possiede feature quali event type, directness, materiality e
novelty (`src/models/news.py:85-118`), ma il contratto del segnale non le
porta tutte fino alla persistenza. P2 richiede due `signal_id` distinti,
ordinati e thesis-linked. Se questo contratto non è pronto prima di `n=0`, va
testata soltanto P1.

### 2.3 Neutralizzazione delle exit spurie — **L, 3–5 giorni-persona**

Silenzio, max age, freshness, fallback, entry gate, score non qualificato,
rank-drop e target zero devono restare gate d'ingresso, non falsificatori della
tesi aperta. Non è però sicuro rimuovere la SELL loop globale: lascerebbe zombie
position e romperebbe S1. Occorre separare `entry_eligible`, `desired_hold`
ed `exit_trigger`, con merge per sleeve.

### 2.4 Catastrophe stop e TP — **M, 1–3 giorni-persona**

`d_hard` è calcolato come overlay largo
(`src/portfolio/stop_policy.py:252-265`) con parametri 1,5×, 5σ e 12–20%
(`config/trading.yaml:202-206`). Nonostante il commento YAML lo descriva come
shadow, l'enforcement broker è true di default
(`src/config.py:230-236`). Il whole-share floor lascia residui frazionari
scoperti (`src/portfolio/fractional_stop_orders.py:62-99`), mentre i
non-fractionable ricevono anche il TP +6%.

Nel trial `d_hard` deve essere identico in P0/P1/P2, separato dall'alpha e
misurato al primo prezzo eseguibile; il TP deve essere neutralizzato.

### 2.5 Shadow end-to-end e ledger — **L, 5–10+ giorni-persona**

Non esiste un motore che percorra lifecycle, ordini, fill, costi e uscite P0/P1/P2
sugli stessi intenti. Il `dry_run` salta la submission ma non simula ack,
partial fill, stop e aging (`src/workers/portfolio_scheduler.py:2756-2770`).
Il paper broker Alpaca non equivale a tre challenger appaiate.

Servono ledger append-only, runner di policy, virtual broker, calendario,
corporate action, reason code e riconciliazione shadow/runtime. È il principale
blocco tecnico.

### 2.6 Replacement e opportunity cost — **L, 3–5 giorni-persona**

Il ranker tronca al top-5, ma non esiste un evento `replacement` distinto dal
semplice target drop. L'orchestrator vede soltanto il nuovo peso aggregato
(`src/strategies/s4/ranking.py:85-147`;
`src/portfolio/orchestrator.py:183-265`).

Il test trade-level deve congelare gli ingressi per mantenere identici i trade
fra P0/P1/P2 e non reinvestire automaticamente capitale liberato. In parallelo,
un simulatore portfolio-level deve registrare candidato sostitutivo, slot,
capitale-giorni e opportunity cost senza confonderli con una thesis exit.

### 2.7 IC tradabile e gate capitale — **M/L, 2–4 giorni di codice; campione separato**

`scripts/compute_s4_ic.py:47-122` lavora signal-level e calcola una Spearman
giornaliera con t-stat non HAC. `scripts/compute_s4_ic_2x2.py:44-137` separa
ensemble/fallback e gate 0,30, ma non applica tutti i gate runtime.

Per misurare la censura il ledger deve registrare i candidati **prima** di
rank, collisione e anti-pyramiding. La popolazione IC primaria è però quella
**tradabile dopo tutti i gate point-in-time**, inclusa la collisione S1, come
richiede la pre-registrazione
(`docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md:122-165`).
Questi due insiemi non vanno confusi.

Le circa 213 sedute
(`docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md:169-190`) sono una
stima del gate IC e della riattivazione del capitale. Non determinano la
numerosità del paired exit test.

### 2.8 Criterio `#179` — **M, 1–3 giorni-persona per evaluator/report**

Il criterio precedente è ritirato dalla pre-registrazione. Il nuovo criterio di
riattivazione è congiuntivo: R1 integrità, R2 IC tradabile D+2, R3 economia
netta e R4 overlap/incrementalità
(`docs/evidence/PREREGISTRAZIONE_S4_ORIZZONTE_2026-08-14.md:194-248`).
`config/s4_kill_criterion.yaml:1-46` rappresenta soprattutto R2; l'evaluator
esistente resta signal-level e non HAC.

L'evaluator può essere costruito prima dei risultati, ma non può produrre PASS
finché R1–R4 e i rispettivi campioni non sono maturi. `#179` è aperta e
`ready-for-agent` al momento dell'audit; questa analisi non la implementa né
la prende in carico.

### 2.9 Input e issue `#236/#243/#244/#246`

- **`#236` — S, già su main.** Il fix è presente
  (`src/workers/portfolio_scheduler.py:740-774,3658-3694`;
  `src/strategies/s4/strategy.py:156-188`). Occorre solo congelarne la
  versione nel sample start.
- **`#243` — resolver/entity, L.** Riguarda falsi positivi di
  `org_lookup`. Il resolver sa confrontare candidati
  (`src/connectors/ticker_resolver.py:83-123`), ma il call site shadow usa il
  primo `asset_tags[0]` e un solo evidence
  (`src/connectors/resolver_shadow.py:59-96`). Servono risoluzione
  article-level, join stabile e validazione.
- **`#244` — relazione articolo-società, L/decisione.** Riguarda articoli su
  società terze e separazione OFF_TOPIC, non il timing d'ingresso. È aperta e
  `ready-for-human`: il dossier può descrivere il blocco, non scegliere la
  policy.
- **`#246` — timing d'ingresso, M per diagnostica; decisione umana.** Riguarda
  il movimento già avvenuto prima che il motore possa vederlo, non il
  multi-ticker. La fattibilità richiede conservare
  `published_at/first_seen/model_generated_at/decision_at/fill_at`, barre
  intraday e primo prezzo eseguibile. È un gate sull'alpha/accessibilità e sui
  fill d'ingresso, separato dal resolver e dalla exit.

### 2.10 Overlap con S1 — **M, 2–4 giorni-persona per ledger robusto**

Il main registra `SKIP_PYRAMIDING` per parte dei BUY bloccati
(`src/workers/portfolio_scheduler.py:3347-3400`) e include
`scripts/measure_181_overlap.py`. È un proxy costruito su
`execution_decisions` (`migrations/016_trade_observability.sql:9-25`), non
un intent ledger completo.

Serve un evento stabile prima dei guard con snapshot S1, rank, candidati e
reason. La metrica primaria R4 usa la popolazione definita dalla
pre-registrazione; Jaccard dei target e collisione sul book restano
diagnostiche. Senza sleeve lots, S1 e S4 continuano a condividere la stessa
posizione al broker boundary.

## 3. Matrice completa di tracciabilità

Ogni riga sotto mappa una raccomandazione delle sezioni 5–9 del consolidato.
“Test” indica il minimo necessario prima di dichiarare la componente pronta;
non autorizza l'attivazione live.

### 3.1 Policy, runtime e controfattuali

| ID | Raccomandazione | Stato/superficie corrente | Complessità | Dipendenze | Test minimo |
|---|---|---|---:|---|---|
| P0 | E0 congelata e riprodotta | target/drop in `src/portfolio/orchestrator.py:129-265`; guard in `src/workers/portfolio_scheduler.py:3555-3763` | L | ledger, snapshot config, fill model | replay golden runtime=shadow; lifecycle ricostruibili ≥95% |
| P1 | D+2 time-only | nessun lifecycle; `src/strategies/s4/strategy.py:58-115` produce target correnti | L | fill, calendar, sleeve lots | weekend/holiday/half-day/restart; un solo close intent |
| P1-G | Nessuna SELL per silence/rank/freshness/gate | oggi i gate possono eliminare il target (`src/workers/portfolio_scheduler.py:3555-3763`) | L | P1 lifecycle, P0 comparabile | invarianti no-SELL per ogni disposition; data failure |
| P2 | Counter qualificato −0,30, due eventi | reversal semplice in `src/workers/portfolio_scheduler.py:4192-4264` | L | resolver, novelty/thesis, signal history, sleeve lots | due signal_id distinti; stale/fallback/off-topic reject; qty S4-only |
| RISK | `d_hard` identico e separato | `src/portfolio/stop_policy.py:252-265`; enforcement `src/config.py:230-236` | M | risk-owner, fill/gap model | stessa distanza/trigger P0-P2; gap fill; protected-ratio |
| TP | Stop/TP/trailing/scale-out fuori dal test | TP +6% su non-fractionable in `src/workers/portfolio_scheduler.py:3955-4012` | S/M | policy snapshot | nessuna leg TP in P0-P2; parity per fractionability |
| REPL | Replacement separato | top-5 in `src/strategies/s4/ranking.py:85-147`, nessun reason dedicato | L | intent/slot ledger, portfolio simulator | reason `replacement`; candidato e slot ricostruibili |
| NO-REINV | Ingressi congelati e nessun reinvestimento nel paired test | runner assente; regola in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:181-189` | M | ledger, P0-P2 runner | stessi intent_id/fill/notional; cash liberato non cambia ingressi |
| OPP | Opportunity cost portfolio-level | calcolo assente; metrica richiesta in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:183-195` | M | REPL, capitale-giorni | riconciliazione trade-level vs portfolio-level; slot-day accounting |
| SHADOW | Shadow end-to-end P0/P1/P2 | `dry_run` salta submit (`src/workers/portfolio_scheduler.py:2756-2770`) | L | virtual broker, costi, calendar | ack/partial/reject/cancel/stop/restart; runtime-shadow diff |
| CLOCK | Session clock e close D+2 | DAILY non persistito per S4 (`src/workers/portfolio_scheduler.py:403-495,3764-3770`) | M | calendar, lifecycle | DST/early close/cutoff/retry/idempotenza |
| LEDGER | Ledger point-in-time append-only | `execution_decisions` è simbolo/tick (`migrations/016_trade_observability.sql:9-25`) | L | migration, versioning | immutabilità; provenance completa; missingness reason |
| SLEEVE | Quantità/lifecycle per sleeve | merge aggregato in `src/portfolio/orchestrator.py:183-265` | L | ledger, reconciliation | S4 exit non vende lotto S1; somma sleeve=broker qty |
| FILL | Fill/costi realistici e primo trigger osservabile | simulatore assente; contratto richiesto in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:170-189` | L | market data, virtual broker | spread/slippage/stress; gap; ambiguità intrabar censurata |

### 3.2 Inferenza, diagnostica e governance

| ID | Raccomandazione | Stato/superficie corrente | Complessità | Dipendenze | Test minimo |
|---|---|---|---:|---|---|
| MDE | `MDE_time` e `MDE_counter` fissati ex ante | valori assenti; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:142-154` | S umano / S config | capital/risk owner | config immutabile pre-`n=0`; audit timestamp |
| POWER | `N_cluster` da MDE, `σΔ`, potenza e dipendenza | calcolo assente; 213 è solo IC (`docs/s4-exit-research-2026-08-14/consolidato_exit.md:203-210,254-261`) | M | pilot variance blinded, ledger | simulazione power; una sola re-estimation blinded |
| BOOT | Block bootstrap event-day, CI unilaterale | `scripts/compute_s4_ic.py:98-122` usa t ingenuo; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:203-207` | M | cluster/event_id, P0-P2 outcome | coverage su dati sintetici; seed/schema congelati |
| MULT | Gerarchia P1→P2 e controllo molteplicità | runner assente; ordine in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:208-210,254-261` | S/M | BOOT, trial ledger | P2 non testata se P1 fallisce; family registrata |
| TRIAL | Trial ledger di tutte le varianti viste | registro machine-readable assente; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:210` | M | policy registry | append-only; D+1/D+3 marcate diagnostiche |
| FALSE | False-exit budget e recovery | reason parziali in `src/portfolio/exit_classification.py:24-89`; gate in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:150-152` | M | path data, counter linkage | recovery window; denominator congelato; P2 gate |
| FALS | Overnight, concentrazione, sottoperiodi, incrementalità S1 | runner unico assente; lista in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:156-164` | M/L | outcomes, path, overlap | fixture per ciascun falsificatore; nessun cambio primaria |
| METRIC | Delta netto, economia, rischio, exit quality | suite paired assente; metriche in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:191-201` | M/L | FILL, ledger, cost model | unità/bps/notional; ES/drawdown; capital-days; reconciliation |
| DIAG | D+1/D+3, term structure, intraday/overnight | forward 1/3/5g signal-level in `scripts/compute_s4_ic.py:47-122` e `scripts/compute_s4_ic_2x2.py:44-137` | M | executable prices, total return | non promuovibili; label diagnostica nel report |
| IC | IC tradabile D+2 con HAC | signal-level, non HAC (`scripts/compute_s4_ic.py:47-122`) | M/L | popolazione post-gate, calendar | collisione S1 inclusa; HAC lag; prezzo segnale vs eseguibile |
| OVERLAP | Valore incrementale rispetto a S1 | proxy in `scripts/measure_181_overlap.py:532-571` | M | intent ledger, sleeve attribution | intent overlap e capital-days; segmenti pre/post fix separati |
| DECISION | Soglie PROMOTE/REJECT/INCONCLUSIVE | evaluator assente; regole in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:142-152,254-261` | S/M | MDE, BOOT, MULT | boundary test su LCB/UCB=MDE; nessuna equivalenza da inconclusive |
| START | Batch atomico e condizioni di sample start | gate assente; condizioni in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:243-252` | M | resolver, clock, costi, shadow, policy hash | `n=0` rifiutato se un campo manca; snapshot timestampato |
| SEGMENT | Esclusione del segmento pre-fix | enforcement assente; regola in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:252` | S/M | START, segment id | fixture pre-fix esclusa da primaria ma ammessa per variance blinded |
| DEPLOY | Gate integrità/costi/rischio/incrementalità/alpha | gate congiuntivo assente; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:212-221` | M | R1-R4, owner risk | ogni gate fail-closed; report motivato |
| STOP | Nessun early efficacy stop; safety review soltanto | monitoring plan assente; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:208,254-261` | S/M | N_cluster, monitoring plan | tentativo early promote rifiutato; safety halt registrato |
| RESTART | Restart su modifica materiale; pause solo per outage osservato | policy-version gate assente; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:263-265` | M | trial ledger, config hash | mutation test per source/model/gate/cost/clock; reset obbligatorio |
| OUTCOME | Albero degli esiti dichiarati ex ante | decision tree assente; norma in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:267-272` | S/M | DECISION, DEPLOY | quattro rami golden; gate alpha fallito mantiene S4 spenta |
| ISSUE | `#243/#244/#246` separati e congelati prima di `n=0` | resolver in `src/connectors/resolver_shadow.py:59-96`; freeze in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:243-250` | L + decisioni | GitHub/PO, labels, timestamp | entity precision; off-topic gate; entry-latency decomposition |
| GOV | Esito R1–R4 e aggiornamento `#179/#21` | evaluator incompleto; gate in `docs/s4-exit-research-2026-08-14/consolidato_exit.md:212-221,254-272` | M | tutti i gate, issue ownership | nessun PASS con campo mancante; context pointer verificato |

## 4. Tempi, dipendenze e blocchi

### 4.1 Critical path

```text
resolver/entity + timestamp/fill contract
                 │
                 ▼
intent/lifecycle ledger per sleeve ──► session clock + P1 D+2
                 │                          │
                 ├──► virtual broker P0/P1/P2
                 │                          ▼
                 ├──► overlap S1       reason/fill/costi
                 │                          │
                 └──► IC tradabile D+2 ◄────┘
                            │
                            ▼
                  inferenza + gate R1–R4
```

`d_hard` comune, neutralizzazione TP e specifica MDE possono procedere in
parallelo, ma devono entrare nel policy snapshot prima di `n=0`.

### 4.2 Cosa è realizzabile in tre giorni-persona

Tre giorni possono produrre contract e prototipi, non lo shadow confirmatory:

1. congelare la baseline post-`#236`;
2. definire schema ledger, reason enum e session semantics;
3. costruire un P1 time-only virtuale minimo senza dichiarare sample start;
4. normalizzare la telemetria `d_hard` e neutralizzare il TP nel test;
5. aggiungere invarianti no-SELL per silence/freshness/rank nella policy P1.

Non va dichiarato `n=0` finché mancano P0 comparabile, fill realistici,
calendar close, collisione S1, resolver congelato, policy version e almeno 95%
dei lifecycle ricostruibili.

### 4.3 Blocchi non tecnici

- Il capital/risk owner deve fissare MDE, risk budget, costo stressato e scelta
  `d_hard`.
- Va scelta la semantica di esecuzione alla close: ordine d'asta presentabile
  entro cutoff oppure primo prezzo successivo conservativo.
- `#244` e `#246` sono `ready-for-human`: richiedono decisione, non
  implementazione automatica.
- Entity, novelty e thesis linkage richiedono label point-in-time; “resolver
  deployato” non equivale a “resolver validato”.
- Il tempo di sviluppo non è il tempo del verdetto: paired exit e IC hanno
  numerosità e stopping rule distinti.

## 5. Raccomandazioni tecniche

1. Non aggiungere semplicemente S4 al clock DAILY: separare cadence d'ingresso,
   session aging e uscita.
2. Introdurre sleeve lots virtuali; una exit S4 non deve liquidare il lotto S1.
3. Usare uno state model idempotente: `eligible`, `submitted`,
   `partially_filled`, `open`, `counter_pending_1`,
   `counter_confirmed`, `time_due`, `risk_exited`, `closed`,
   `censored`.
4. Tipizzare almeno `time_stop`, `counter_qualified`,
   `risk_catastrophe`, `replacement`, `data_unavailable`,
   `broker_reject` e `calendar_fallback`; `unknown` deve essere errore
   d'integrità.
5. Fail-closed per nuovi ingressi in assenza dati; hold per una tesi aperta, con
   time-stop ancora attivo.
6. Registrare fill, quantità protetta e residuo scoperto; non inferire D0 dal
   tick di submission.
7. Usare una sola sorgente versionata per la soglia counter −0,30.
8. Versionare source, resolver, model, gate, ranking, sizing, collisione,
   calendar, cost model ed order semantics; ogni modifica materiale riavvia il
   sample.
9. Tenere separati i tre verdetti: qualità della exit, IC dell'ingresso e
   riattivazione del capitale.

## Conclusione

La raccomandazione consolidata è implementabile, ma il codice corrente ragiona
ancora in target aggregati per simbolo invece che in lifecycle S4. La priorità
non è cambiare una SELL: è rendere lo stesso intento osservabile e simulabile
attraverso P0/P1/P2 fino al confine broker. Il percorso minimo robusto è:
contratto dati e fill, ledger per sleeve, P0 riproducibile, P1 D+2 time-only,
`d_hard` comune, inferenza pre-registrata; P2 soltanto quando
entity/novelty/thesis linkage sono realmente point-in-time.
