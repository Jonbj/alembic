#!/usr/bin/env bash
set -euo pipefail

REPO="Jonbj/alembic"
TASK_LABELS="wayfinder:task,paper-monitoring,freeze-ok,ready-for-agent"
DECISION_LABELS="wayfinder:decision,ready-for-human,paper-monitoring"
POST_LABELS="wayfinder:task,paper-monitoring"

create_issue() {
  local title="$1"
  local labels="$2"
  gh issue create --repo "$REPO" --title "$title" --label "$labels" --body-file -
}

U1=$(create_issue "Alpha-miss: acquisire timeline end-to-end e barre intraday" "$TASK_LABELS" <<'BODY'
Part of #21.

## What to build

Estendere il dossier alpha-miss con barre intraday e una timeline point-in-time completa: `published_at → first_seen/fetched_at → ingested_at → scored_at → ciclo eleggibile → ordine → fill`. Per ogni stadio esporre prezzo e quota del movimento già realizzata; includere MFE/MAE e pre/after-market dove disponibile.

## Perché

Il 12/08 la quota mediana del movimento nel gap era 99%. Senza event time non si distingue alpha già consumata prima della pubblicazione da latenza interna o execution. Questa misura sblocca F-019/F-030, entry timing e costi catturabili coerenti.

## Freeze

Solo acquisizione e misura read-only: nessun parametro o comportamento live cambia. Compatibile col freeze #171.

## Acceptance criteria

- [ ] Ogni mover/segnale ha timestamp e primo prezzo successivo per tutti gli stadi disponibili, con missingness esplicita.
- [ ] Gap, intraday, MFE/MAE e quota di movimento per stadio sono deterministici e testati.
- [ ] Nessun look-ahead: ogni join usa solo informazione disponibile al cutoff.
- [ ] Il dossier espone schema/versione e provenienza dei dati.

## Blocked by

None — can start immediately.

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, D1/M2. Modelli: tutti e cinque.
BODY
)
I1=${U1##*/}

U2=$(create_issue "Alpha-miss: misurare P&L economico e scoreboard della carta" "$TASK_LABELS" <<'BODY'
Part of #21.

## What to build

Calcolare deterministicamente il P&L economico S1, S4 e book secondo la definizione dell'Observation Charter e mostrare uno scoreboard: giorno N/40, giorni NO_NEWS-dominant / osservati, S4 vs ±$200, S1 vs SPY, numerosità e segmenti pre/post #185 e #191.

## Perché

La carta decide sul P&L economico e dice di ignorare il realizzato S1, mentre il ledger corrente espone soprattutto realizzato e MTM giornaliero. Senza questa serie le due domande pre-registrate non sono realmente monitorate.

## Freeze

Misura richiesta dalla carta; nessuna taratura. Compatibile col freeze #171.

## Acceptance criteria

- [ ] La formula implementa esattamente il mark definito nella carta e documenta attribution/missingness.
- [ ] Sono disponibili serie giornaliera e cumulata per S1/S4/book.
- [ ] Lo scoreboard riporta numeratori, denominatori e discontinuità #185/#191.
- [ ] Le posizioni senza attribuzione di strategia sono esposte come contaminazione, non assegnate arbitrariamente.

## Blocked by

None — can start immediately.

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, M3. Modelli: Opus, Codex, GLM-5.2, DeepSeek, MiniMax (running totals).
BODY
)
I2=${U2##*/}

U3=$(create_issue "Alpha-miss: misurare copertura effettiva e attribution articoli" "$TASK_LABELS" <<'BODY'
Part of #21.

## What to build

Produrre metriche di copertura effettiva distinguendo articoli unici e issuer-specific da sector/macro, false entity match e fan-out irrilevante; classificare timing anticipatory/concurrent/retrospective. Aggiungere canonical article id, fonte, subject ticker, concentrazione e `max_score_own` vs `max_score_fanout`.

## Perché

Il 12/08 NVDA aveva 11 righe ma una sola realmente su Nvidia. Le righe `news_log` sovrastimano copertura e contaminano F-001/F-012/F-020. La metrica utile è `effective_timely_coverage`.

## Freeze

Misura e data quality soltanto. Non cambiare provider o regole live durante #171.

## Acceptance criteria

- [ ] Deduplica di syndication e canonical ID sono riproducibili.
- [ ] Relevance e timing hanno categorie esplicite e `UNKNOWN` quando non determinabili.
- [ ] Sono esposte copertura per ticker/settore/fonte e concentrazione top-5/HHI.
- [ ] È possibile attribuire ogni segnale a issuer-specific o fan-out senza doppio conteggio.

## Blocked by

None — can start immediately.

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, D2. Modelli: tutti e cinque.
BODY
)
I3=${U3##*/}

U4=$(sed "s/__I1__/$I1/g" <<'BODY' | create_issue "Alpha-miss: calcolare alpha accessibile e cost estimator v2" "$TASK_LABELS"
Part of #21.

## What to build

Calcolare per ogni opportunità `gross_opportunity_usd`, `accessible_opportunity_usd` e `net_opportunity_usd` dal primo bar successivo al primo ciclo realmente eleggibile. Applicare size/capitale/vincoli realmente disponibili, exit policy dichiarata e costi; versionare la formula e mantenere la serie legacy intatta.

## Perché

ORCL il 12/08 valeva $117,95 close-to-close ma $6,82 intraday. Il ledger somma stime storiche prodotte con formule diverse, quindi i dollari non sono comparabili con le soglie della carta.

## Freeze

Estimator v2 prospettico e parallelo: freeze-ok. Nessun restatement di occurrence legacy in questa issue.

## Acceptance criteria

- [ ] Ogni stima dichiara cutoff, entry, exit, size, vincoli, costi, formula e `estimator_version`.
- [ ] Ribassi non detenuti in un libro long-only hanno costo zero verificato, non `null`.
- [ ] Gli importi misurati, attribuiti e congetturali restano separati.
- [ ] Il calcolo non tratta titoli tematicamente simili come fungibili senza una regola pre-registrata.

## Blocked by

- #__I1__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, M2. Modelli: tutti e cinque.
BODY
)
I4=${U4##*/}

U5=$(sed -e "s/__I3__/$I3/g" -e "s/__I4__/$I4/g" <<'BODY' | create_issue "Alpha-miss: introdurre funnel actionability e pipeline v2" "$TASK_LABELS"
Part of #21.

## What to build

Aggiungere in parallelo alla serie legacy un funnel a due assi. Actionability: ENTRY_OPPORTUNITY, EXIT_RISK, PASSIVE_EXPOSURE, NON_ACTIONABLE, OUT_OF_SCOPE. Pipeline: NO_RELEVANT_NEWS, LATE_NEWS, ENTITY_ERROR, NO_SIGNAL, WRONG_SIGN, BELOW_GATE, FALLBACK_REJECT, RANKED_OUT, RISK_BLOCK, ORDER_FAIL, BAD_FILL, CAUGHT.

## Perché

`catturati` confonde posizioni vecchie e decisioni nuove; THIN_NEUTRAL/FILTERED fondono cause diverse; ribassi non detenuti non sono miss economici. Il 12/08 il dossier indicava BELOW_GATE mentre il report riportava THIN_NEUTRAL.

## Freeze

Vista v2 parallela soltanto. Non sostituire i conteggi legacy o la metrica NO_NEWS pre-registrata.

## Acceptance criteria

- [ ] Funnel mover→azionabile→held/news/sign/gate/guard/order/fill/net profitable deterministico.
- [ ] KPI distinti per held-at-open, active signal recall, execution conversion e profitable capture.
- [ ] Signed score proviene dal campo firmato, non da reason con `abs(score)`.
- [ ] Mapping legacy↔v2 documentato e nessun dato storico riscritto.

## Blocked by

- #__I3__
- #__I4__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, M1/P2. Modelli: Codex, GLM-5.2, DeepSeek, Opus/MiniMax.
BODY
)
I5=${U5##*/}

U6=$(sed -e "s/__I1__/$I1/g" -e "s/__I3__/$I3/g" <<'BODY' | create_issue "Alpha-miss: costruire pannelli longitudinali e occurrence ledger" "$TASK_LABELS"
Part of #21.

## What to build

Aggiungere panel ticker-day, signal e decision/trade, più finding definitions, occurrences append-only, status events e viste derivate. Ogni evento ha occurrence/causal event ID, simboli e DB IDs, segmento, confidenza per importo, actual/attributed/missed/avoided loss, formula, primary finding e fonte.

## Perché

Il ledger corrente mescola definizione e occurrence, può duplicare lo stesso evento tra report alpha/forensic e combina importi con soglie di confidenza diverse. Un ticker panel rende meccanici i pattern cross-day.

## Freeze

Nuovi pannelli paralleli e append-only. Nessun backfill distruttivo o riscrittura di `findings.json`.

## Acceptance criteria

- [ ] Una riga per unità osservativa con chiavi e schema versionati.
- [ ] Causal event ID impedisce doppio conteggio; un solo finding primario riceve il costo.
- [ ] Definition, occurrence e status sono separati senza cancellare evidenza.
- [ ] Validator controlla ID, somme, date/finestra, duplicati, append-only, dossier hash e completeness.

## Blocked by

- #__I1__
- #__I3__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, L1/L3. Modelli: Opus, Codex, DeepSeek, MiniMax, GLM.
BODY
)
I6=${U6##*/}

U7=$(sed -e "s/__I3__/$I3/g" -e "s/__I4__/$I4/g" -e "s/__I6__/$I6/g" <<'BODY' | create_issue "Alpha-miss: aggiungere signal diagnostics e controlli negativi" "$TASK_LABELS"
Part of #21.

## What to build

Costruire rank IC time-forward e residualizzato, hit rate, precision dei segnali, recall dei mover azionabili, forward return 30m/60m/EOD/T+1/T+3/T+5, quintili e split per fonte/modello/fallback/extraction/ensemble std. Includere falsi positivi, controlli matched, score stability e shadow curves descrittive.

## Perché

La sola coda |return|≥3% è selezionata ex post e non misura falsi positivi. IC close-to-close rispetto a un segnale tardivo ha reverse causality; servono ritorni successivi al timestamp osservabile e negative controls.

## Freeze

Misure e curve shadow soltanto. Nessuna scelta del gate, modello o fonte live.

## Acceptance criteria

- [ ] Metriche time-forward senza leakage, residualizzate vs SPY/settore e con n/CI.
- [ ] Controlli matched riproducibili; benchmark di libro separati dai controlli del segnale.
- [ ] Molteplicità gestita o statistiche marcate descrittive.
- [ ] Sweep gate/fan-out è predefinita e descrittiva, senza ottimizzazione operativa.

## Blocked by

- #__I3__
- #__I4__
- #__I6__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, M5/M6/D4/D5. Modelli: tutti e cinque.
BODY
)
I7=${U7##*/}

U8=$(sed -e "s/__I4__/$I4/g" -e "s/__I6__/$I6/g" <<'BODY' | create_issue "Alpha-miss: attribuire P&L active/passive e qualità decisionale" "$TASK_LABELS"
Part of #21.

## What to build

Produrre una decomposizione stabile di P&L: esposizione preesistente, nuove selezioni, timing, sizing, exit, beta mercato/settore, drift post-exit, entry percentile, holding period e costo/beneficio dei guard.

## Perché

Il 12/08 S1 passivo ha prodotto +$228,53 mentre le decisioni attive S4 circa −$35. È più informativo del capture count e deve diventare una serie, non un insight occasionale.

## Freeze

Attribuzione e controfattuali read-only. Cambiare size/holding/exit policy è fuori scope fino al 28/09.

## Acceptance criteria

- [ ] Snapshot all'apertura e variazioni intraday separano passivo e attivo.
- [ ] Selection/timing/sizing/exit hanno controfattuali e confidenze separati.
- [ ] Guard cost e avoided loss sono entrambi misurati senza doppio conteggio.
- [ ] Holding e size sono analizzati, ma non viene emessa alcuna taratura live.

## Blocked by

- #__I4__
- #__I6__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, M4/D5. Modelli: Opus, Codex, GLM-5.2, MiniMax.
BODY
)
I8=${U8##*/}

U9=$(sed -e "s/__I1__/$I1/g" -e "s/__I3__/$I3/g" <<'BODY' | create_issue "Alpha-miss: aggiungere contesto evento, regime e microstruttura" "$TASK_LABELS"
Part of #21.

## What to build

Arricchire il dossier con return residuo vs SPY/ETF settoriale, catalyst type, corporate calendar, VIX/regime/tag tema e, in una seconda tranche, NBBO/spread, volume/ADV, volume surprise e halt.

## Perché

Nove semi nello stesso rally non sono nove shock indipendenti. Residualizzazione ed event type distinguono beta settoriale, gap strutturalmente inaccessibili e problemi del motore. La microstruttura è necessaria per passare da opportunity gross a net.

## Freeze

Solo contesto e misura. Nessun cambio a universo, soglie o gestione ordini.

## Acceptance criteria

- [ ] Return residuali e cluster settoriali usano mapping deterministico.
- [ ] Event/regime/tag hanno enum e missingness espliciti.
- [ ] Le occasioni correlate per tema non sono trattate come indipendenti nelle statistiche.
- [ ] Dati microstrutturali hanno provenance e sono separabili dalla prima versione basata su barre.

## Blocked by

- #__I1__
- #__I3__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, D3. Modelli: Opus, Codex, DeepSeek, MiniMax.
BODY
)
I9=${U9##*/}

U10=$(sed -e "s/__I2__/$I2/g" -e "s/__I6__/$I6/g" <<'BODY' | create_issue "Alpha-miss: rendere findings falsificabili e sintetizzabili" "$TASK_LABELS"
Part of #21.

## What to build

Aggiungere viste/campi per giorni distinti in finestra, giorni esposti, non-occorrenze, evidenza contraria, distanza da soglia, classe/dimensione, strategia, meccanismo, prova decisiva, contamination flag, relazione finding→causa e status events. Generare SYNTHESIS e weekly rollup deterministici.

## Perché

Occorrenze senza denominatore e tutti i finding “aperti” producono confirmation bias e backlog sovraffollato. I finding che contaminano attribuzione/segno/tracciabilità devono emergere prima dei normali alpha miss.

## Freeze

Viste e status events paralleli. Nessuna cancellazione, fusione distruttiva o modifica retroattiva del ledger primario.

## Acceptance criteria

- [ ] Il 31/07 è escluso dai conteggi della finestra come da carta.
- [ ] Ogni finding può registrare supported/contradicted/not-exposed e una prova decisiva read-only.
- [ ] Contamination flags propagano alle metriche dipendenti.
- [ ] SYNTHESIS/weekly/digest mostrano solo cambi, soglie, P&L economico e integrità dati.

## Blocked by

- #__I2__
- #__I6__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, L2/L4. Modelli: tutti e cinque.
BODY
)
I10=${U10##*/}

U11=$(sed -e "s/__I5__/$I5/g" -e "s/__I6__/$I6/g" -e "s/__I10__/$I10/g" <<'BODY' | create_issue "Alpha-miss: correggere contratto prompt e output operativo" "$TASK_LABELS"
Part of #21.

## What to build

Rendere coerente il prompt: dossier unica fonte numerica, fallback DATA_INCOMPLETE esplicito, soglia mover non ri-derivata, news/log trattati come dati non fidati, output candidati strutturato e materializzazione ledger deterministica. Richiedere esposizione, evidenza contraria, next evidence e massimo tre finding materiali. Ridisegnare report e digest Telegram.

## Perché

Lo script oggi ordina sia di non ricalcolare sia di riscaricare le barre; ordina ledger/commit/push e poi vieta commit e scritture diverse dal report. Le contraddizioni producono comportamento dipendente dalla sessione.

## Freeze

Correttezza della strumentazione e presentazione. Nessuna modifica a decisioni live.

## Acceptance criteria

- [ ] Non esistono istruzioni operative contraddittorie nel prompt.
- [ ] Schema dossier e prompt sono versionati e compatibili.
- [ ] Il generatore non materializza direttamente ledger non validati.
- [ ] Decision card, stato carta, top-3 e digest di cinque righe sono autonomamente leggibili; tabella completa è appendice.
- [ ] Il rationale è auditabile con dati/formule, senza richiedere chain-of-thought libero.

## Blocked by

- #__I5__
- #__I6__
- #__I10__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, P1–P4. Modelli: tutti e cinque.
BODY
)
I11=${U11##*/}

U12=$(sed -e "s/__I4__/$I4/g" -e "s/__I5__/$I5/g" -e "s/__I6__/$I6/g" <<'BODY' | create_issue "Decisione freeze: tassonomia primaria e restatement alpha-miss" "$DECISION_LABELS"
Part of #21.

## Decisione richiesta

Scegliere se mantenere soltanto v2 parallelo (raccomandato), promuovere BELOW_GATE/actionability a tassonomia primaria, ricalcolare costi storici con estimator accessibile e/o migrare retroattivamente ledger e stati.

## Perché serve una decisione umana

La serie legacy è incoerente nel cost estimator e grossolana nelle cause, ma cambiarla durante l'esperimento modifica l'oggetto pre-registrato e può violare append-only. Il beneficio analitico non autorizza una riscrittura silenziosa.

## Opzioni

1. Raccomandata: raw legacy invariato + viste v2 separate.
2. Deroga limitata: promozione della tassonomia primaria, con doppio reporting.
3. Deroga ampia: restatement costi/backfill, con snapshot, migration log e compatibility report.

## Acceptance criteria

- [ ] È scelta e motivata una delle opzioni.
- [ ] Se si sceglie 2 o 3, la deroga è registrata nell'Observation Charter prima dell'implementazione.
- [ ] È definito come restano confrontabili NO_NEWS, soglie e occurrence legacy.
- [ ] Nessun agente implementa la decisione finché l'operatore non la approva.

## Blocked by

- #__I4__
- #__I5__
- #__I6__

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, O1. Modelli: Opus, Codex, GLM-5.2, DeepSeek.
BODY
)
I12=${U12##*/}

U13=$(sed -e "s/__I7__/$I7/g" -e "s/__I8__/$I8/g" <<'BODY' | create_issue "Post-freeze: valutare gate, mover threshold, size e holding policy" "$POST_LABELS"
Part of #21.

## What to evaluate after 2026-09-28

Usare le misure raccolte per decidere: gate S4, soglia mover 3% vs sensibilità σ-scaled, dynamic sizing, holding/exit policy, provider/fan-out e eventuale ricalibrazione delle soglie economiche. Valutare anche coerenza con le assunzioni del backtest.

## Perché non ora

Sono tarature o cambi di policy. Durante #171 sono ammesse curve shadow e sensitivity analysis, non la scelta dell'optimum o il cambio live.

## Acceptance criteria

- [ ] La finestra #171 è chiusa o una deroga separata è approvata.
- [ ] Le decisioni usano dati point-in-time, segmenti #185/#191, costi e uncertainty.
- [ ] Nessun “zero WRONG_SIGN” è interpretato come gate corretto senza decontaminare F-006 e selection bias.
- [ ] Ogni cambio ha criterio, expected impact e piano di validazione separati.

## Blocked by

- #__I7__
- #__I8__
- #171 (chiusura della finestra di osservazione)

Fonte consolidata: `/tmp/alpha_miss_roadmap_consolidata.md`, O2. Modelli: Opus, Codex, GLM-5.2, DeepSeek, MiniMax.
BODY
)
I13=${U13##*/}

link_dependency() {
  local child="$1"
  local blocker="$2"
  local blocker_id
  blocker_id=$(gh api "repos/$REPO/issues/$blocker" --jq .id)
  gh api --method POST "repos/$REPO/issues/$child/dependencies/blocked_by" -F issue_id="$blocker_id" >/dev/null
}

link_subissue() {
  local child="$1"
  local child_id
  child_id=$(gh api "repos/$REPO/issues/$child" --jq .id)
  gh api --method POST "repos/$REPO/issues/21/sub_issues" -F sub_issue_id="$child_id" >/dev/null
}

for child in "$I1" "$I2" "$I3" "$I4" "$I5" "$I6" "$I7" "$I8" "$I9" "$I10" "$I11" "$I12" "$I13"; do
  link_subissue "$child"
done

link_dependency "$I4" "$I1"
link_dependency "$I5" "$I3"
link_dependency "$I5" "$I4"
link_dependency "$I6" "$I1"
link_dependency "$I6" "$I3"
link_dependency "$I7" "$I3"
link_dependency "$I7" "$I4"
link_dependency "$I7" "$I6"
link_dependency "$I8" "$I4"
link_dependency "$I8" "$I6"
link_dependency "$I9" "$I1"
link_dependency "$I9" "$I3"
link_dependency "$I10" "$I2"
link_dependency "$I10" "$I6"
link_dependency "$I11" "$I5"
link_dependency "$I11" "$I6"
link_dependency "$I11" "$I10"
link_dependency "$I12" "$I4"
link_dependency "$I12" "$I5"
link_dependency "$I12" "$I6"
link_dependency "$I13" "$I7"
link_dependency "$I13" "$I8"
link_dependency "$I13" 171

printf '%s\n' \
  "$I1|$U1|$TASK_LABELS" \
  "$I2|$U2|$TASK_LABELS" \
  "$I3|$U3|$TASK_LABELS" \
  "$I4|$U4|$TASK_LABELS" \
  "$I5|$U5|$TASK_LABELS" \
  "$I6|$U6|$TASK_LABELS" \
  "$I7|$U7|$TASK_LABELS" \
  "$I8|$U8|$TASK_LABELS" \
  "$I9|$U9|$TASK_LABELS" \
  "$I10|$U10|$TASK_LABELS" \
  "$I11|$U11|$TASK_LABELS" \
  "$I12|$U12|$DECISION_LABELS" \
  "$I13|$U13|$POST_LABELS"
