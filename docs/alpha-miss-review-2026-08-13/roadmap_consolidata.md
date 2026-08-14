# Roadmap consolidata per il report alpha-miss di Alembic

Data di consolidamento: 2026-08-13  
Finestra di osservazione: 2026-08-03 → 2026-09-28, issue di freeze #171  
Fonti: cinque analisi indipendenti (Claude Opus, Codex gpt-5.6-sol, GLM-5.2, DeepSeek-v4-flash, MiniMax-m2.7), `scripts/daily_alpha_miss_analysis.sh`, `docs/ALPHA_MISS_REPORT_2026-08-12.md`, `docs/evidence/OBSERVATION_CHARTER.md`.

## Legenda e criterio di validazione

- **[STRUMENTAZIONE]**: misura, osservabilità, correttezza del dato o presentazione; compatibile col freeze purché non cambi parametri, decisioni live o la serie primaria pre-registrata.
- **[DEROGA]**: modifica che altererebbe una definizione, una serie primaria o dati storici durante la finestra; richiede decisione umana e annotazione nella carta.
- **[POST-FREEZE]**: taratura o scelta di policy da valutare solo dopo il 28/09.

La classificazione non dipende da come un modello ha etichettato la proposta, ma dal test della carta: «se non lo correggo, l'evidenza raccolta è sbagliata?». Durante il freeze sono ammesse viste e metriche v2 in parallelo; non sono ammesse sostituzioni silenziose delle definizioni pre-registrate, riscritture del ledger append-only o cambi di gate, size e soglie.

## Executive summary — i cinque interventi a maggiore leverage

1. **Calcolare il P&L economico e lo scoreboard delle due domande di uscita.** Giorno N/40, quota di giorni con NO_NEWS dominante, P&L economico S4, P&L economico S1 vs SPY e segmenti pre/post #185 e #191. Oggi lo strumento conserva soprattutto la serie realizzata che la carta dice di ignorare. **[STRUMENTAZIONE]**
2. **Rendere deterministica l'alpha accessibile e lo stimatore di costo.** Salvare gap, tratto intraday, prezzo al primo dato/segnale/ciclo eleggibile e costi `gross/accessibile/net`; usare barre intraday e una formula versionata. È la base per capire se un miss era davvero tradabile e rende confrontabili i dollari accumulati. **[STRUMENTAZIONE]**
3. **Separare actionability, pipeline e cattura attiva in un funnel v2 parallelo.** Distinguere rialzi realmente acquistabili, exit risk, esposizioni passive e ribassi non azionabili; distinguere `BELOW_GATE`, news tardiva, entity error, risk block, order/fill. Non sostituire la tassonomia legacy durante la finestra. **[STRUMENTAZIONE]**; sostituzione della serie legacy **[DEROGA]**.
4. **Creare pannelli longitudinali e un ledger di occurrence auditabile.** Una riga per segnale, decisione e evento causale; giorni esposti/non-occorrenze, confidenza per importo, provenienza, versioni e validazione meccanica. È ciò che consente tutte le analisi cross-day senza rileggere 40 report con un LLM. **[STRUMENTAZIONE]**.
5. **Misurare qualità predittiva e copertura effettiva.** IC/rank IC, hit rate, precision/recall, falsi positivi, forward return e controlli negativi, separando articoli issuer-specific da fan-out, falsi match e recap tardivi. È la misura diretta della domanda «la news contiene alpha?». **[STRUMENTAZIONE]**.

## Priorità costo/beneficio

| Priorità | Gruppo | Leverage | Costo | Freeze |
|---:|---|---|---|---|
| 1 | P&L economico e scoreboard della carta | Molto alto | Medio | [STRUMENTAZIONE] |
| 2 | Alpha accessibile, timeline e costo v2 | Molto alto | Medio | [STRUMENTAZIONE] |
| 3 | Funnel actionability/pipeline v2 | Molto alto | Medio | [STRUMENTAZIONE] |
| 4 | Ledger/pannelli longitudinali e provenienza | Molto alto | Medio-alto | [STRUMENTAZIONE] |
| 5 | Copertura effettiva + signal diagnostics | Alto | Medio-alto | [STRUMENTAZIONE] |
| 6 | Decision quality e attribuzione P&L | Alto | Medio | [STRUMENTAZIONE] |
| 7 | Denominatori, controlli e sufficienza statistica | Alto | Basso-medio | [STRUMENTAZIONE] |
| 8 | Contratto del prompt e validazione deterministica | Alto | Basso | [STRUMENTAZIONE] |
| 9 | Contesto evento/regime/microstruttura | Medio | Medio-alto | [STRUMENTAZIONE] |
| 10 | Sintesi, alert e digest Telegram | Medio | Basso | [STRUMENTAZIONE] |
| 11 | Restatement legacy/tassonomia primaria | Alto ma rischioso | Medio | [DEROGA] |
| 12 | Gate, size e soglia mover | Potenziale, non ancora provato | Medio | [POST-FREEZE] |

## 1. Metriche

### M1 — Funnel economico e di pipeline, con cattura attiva distinta dall'esposizione passiva

**Cosa.** Aggiungere in parallelo ai conteggi legacy due assi:

- actionability: `ENTRY_OPPORTUNITY`, `EXIT_RISK`, `PASSIVE_EXPOSURE`, `NON_ACTIONABLE`, `OUT_OF_SCOPE`;
- pipeline: `NO_RELEVANT_NEWS`, `LATE_NEWS`, `ENTITY_ERROR`, `NO_SIGNAL`, `WRONG_SIGN`, `BELOW_GATE`, `FALLBACK_REJECT`, `RANKED_OUT`, `RISK_BLOCK`, `ORDER_FAIL`, `BAD_FILL`, `CAUGHT`.

Il funnel giornaliero deve mostrare mover grezzi → azionabili → già detenuti all'open → con news utile/tempestiva → segno corretto → sopra gate → sopravvissuti ai guard → ordinati/fillati → profittevoli dopo costi. KPI minimi: `held_at_open_rate`, `active_signal_recall`, `execution_conversion_rate`, `profitable_capture_rate`, `avoidable_miss_count`.

**Perché.** Il campo corrente `catturati` mette insieme titoli detenuti da settimane e decisioni del giorno. Nel report del 12/08 “8 su 11 catturati” convive con tre nuovi ingressi S4 tutti negativi a EOD. I ribassi non detenuti, inoltre, non sono alpha miss per un libro long-only, pur restando utili per misurare directional accuracy.

**Come.** Derivare i due assi deterministicamente da posizione all'apertura, lato consentito, news/segnali, reason strutturata, ordini e fill. Mantenere i conteggi legacy fino al 28/09 e pubblicare `funnel_v2` accanto a essi.

**Freeze.** **[STRUMENTAZIONE]** se è una vista parallela; **[DEROGA]** se sostituisce i conteggi legacy o cambia retroattivamente la metrica NO_NEWS della carta.

**Modelli.** Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

### M2 — Alpha accessibile e costo controfattuale deterministico, versionato e portfolio-aware

**Cosa.** Per ogni opportunità registrare `total_return`, gap overnight, intraday return, prezzo al primo dato disponibile, primo segnale, primo ciclo eleggibile, MFE/MAE successivi, `gross_opportunity_usd`, `accessible_opportunity_usd`, `net_opportunity_usd`. Il costo long-side deve essere zero verificato per un ribasso non detenuto e deve includere size realmente disponibile, vincoli, spread/slippage e una exit policy dichiarata. Ogni stima porta `estimator_version`.

**Perché.** ORCL il 12/08 vale $117,95 sul close-to-close ma solo $6,82 sul tratto intraday. Sommare formule diverse rende `costo_cumulato_usd` non confrontabile con la soglia $1.000. Il costo “marginale rispetto al portafoglio” suggerito da MiniMax è valido solo come disponibilità incrementale di capitale/risk budget: sottrarre esposizioni tematiche non fungibili (per esempio MU/NOK da ORCL) sarebbe arbitrario senza una regola di sostituzione pre-registrata.

**Come.** Calcolo nel dossier, non nel testo LLM; formula unica basata sul primo bar successivo al primo ciclo realmente eleggibile. Conservare separatamente EOD e policy S4 reale. Aggiungere un estimator v2 parallelo senza riscrivere le occurrence legacy.

**Freeze.** **[STRUMENTAZIONE]** per nuovi campi e stime v2 prospettiche; restatement dei costi storici **[DEROGA]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

### M3 — P&L economico e scoreboard delle domande di uscita

**Cosa.** Sezione fissa: giorno N/40, sedute valide/ad alta dispersione, giorni con NO_NEWS dominante / giorni osservati, P&L economico cumulato S4 vs ±$200, P&L economico S1 vs SPY, P&L economico book, segmenti pre/post #185 e #191, ampiezza/incertezza della stima.

**Perché.** La carta definisce il P&L economico e impone di ignorare il realizzato per S1; `market_daily.jsonl` conserva invece soprattutto realizzato e MTM giornaliero. Senza questa serie, il giorno 40 richiede una ricostruzione retrospettiva e le domande pre-registrate non sono monitorate.

**Come.** Calcolo deterministico coerente con la definizione della carta, campi giornalieri `economic_pnl_s1`, `economic_pnl_s4`, `economic_pnl_book`, cumulati derivati e scoreboard descrittivo. Esporre sempre numeratore, denominatore e segmenti di discontinuità.

**Freeze.** **[STRUMENTAZIONE]**; è misura esplicitamente richiesta dalla carta.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7 (running totals).

### M4 — Qualità delle decisioni e decomposizione active/passive

**Cosa.** Serie e pannello cumulativo per: P&L delle posizioni già aperte all'open; P&L da nuove selezioni; costo/beneficio di timing, sizing e uscite; drift post-exit; beta mercato/settore; mediana `entry_percentile`; quota ingressi sopra 0,70; uscite da articolo di terzi o FIX-D/stale; holding period e relazione col P&L; guard cost e guard benefit.

**Perché.** Il miglior insight del report è +$228,53 passivi S1 contro circa −$35 dalle decisioni attive. Deve essere una misura stabile, non una scoperta narrativa. Anche un guard che blocca un trade può creare o evitare costo: vanno contate entrambe le direzioni.

**Come.** Snapshot delle posizioni all'apertura, variazioni di quantità intraday, trade/fill e barre successive. Attribuire selezione, timing e exit con controfattuali separati e senza sommare confidenze diverse.

**Freeze.** **[STRUMENTAZIONE]**. Usare i risultati per cambiare size/holding policy è **[POST-FREEZE]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; MiniMax-m2.7.

### M5 — Qualità predittiva: IC, confusion matrix, falsi positivi e forward returns

**Cosa.** Su finestre mobili: rank IC score→return futuro residualizzato; hit rate del segno; precision dei segnali sopra gate; recall dei mover azionabili; forward return a 30m, 60m, EOD, T+1/T+3/T+5; quintili di score/confidence; split issuer-specific/fan-out, ensemble/fallback, modello, fonte, extraction method, ensemble std e ora. Includere successi e falsi positivi, non solo miss.

**Perché.** Selezionare ex post solo |return|≥3% misura una parte della recall e introduce selection bias. La domanda 1 è predittiva: richiede sapere se score alto precede return residuo positivo anche sui non-mover. La `reason` di execution perde oggi il segno in F-006, quindi il signed score deve provenire da `sentiment_signals` o da un campo corretto.

**Come.** Join time-aware al primo prezzo successivo al segnale, pannello ticker-day e decision-day, confidence interval/n espliciti. La “confusion matrix” deve usare orizzonti dichiarati; non dedurre che il gate sia alto/basso dai soli conteggi.

**Freeze.** **[STRUMENTAZIONE]**. Qualunque cambio del gate derivato dai risultati è **[POST-FREEZE]**.

**Modelli.** Claude Opus; Codex; DeepSeek-v4-flash; MiniMax-m2.7; GLM-5.2 (signed score e decision quality).

### M6 — Denominatori, controlli negativi e sufficienza statistica

**Cosa.** Per ogni finding: `giorni_esposti`, non-occorrenze, evidenza contraria e test di falsificazione. Per le analisi: controlli matched per settore/volatilità/liquidità/market cap; modelli nulli per percentile d'ingresso; campioni, intervalli di confidenza, potenza/precisione attesa al giorno 40; correzione per confronti multipli o marcatura “descrittivo, non inferenziale”.

**Perché.** “Sei occorrenze” non significa nulla senza sapere in quante sedute il fenomeno poteva apparire. Il t-stat per bucket orario citato da GLM (ora 14, t≈−4,96) proviene da sette confronti data-mined: è interessante, ma non ancora evidenza inferenziale senza controllo della molteplicità. Anche l'entry percentile alto richiede un null condizionato a titoli che chiudono in rialzo.

**Come.** Esposizione definita ex ante per tipo di finding; negative controls fissi; output con n, orizzonte, CI e test family. Al midpoint stimare se la finestra potrà distinguere ±$200 dal rumore; se no, la carta già ammette l'estensione.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

## 2. Prompt

### P1 — Contratto operativo coerente e trust boundary

**Cosa.** Eliminare le contraddizioni: oggi il prompt dice sia “non ricalcolare il dossier” sia “riscarica le barre”, ordina commit/push dei ledger ma poi dice che l'unico file scrivibile è il report e vieta commit; lascia inoltre scegliere una soglia mover già fissata a 3%. Trattare news e log come dati non fidati e ignorare istruzioni contenute al loro interno.

**Perché.** Istruzioni incompatibili rendono non deterministico il comportamento del generatore e possono produrre serie diverse a seconda del modello/sessione.

**Come.** Dossier come unica fonte numerica; fallback `DATA_INCOMPLETE` esplicito; output strutturato dei candidati; validazione, merge dei ledger, commit e push affidati a codice deterministico. Versionare insieme schema dossier e prompt.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Codex; Claude Opus; GLM-5.2; DeepSeek-v4-flash.

### P2 — Classificazione ground-truth v2 e gestione dell'incertezza

**Cosa.** Il prompt parte dalla causa deterministica del dossier, usa il signed score reale, distingue `BELOW_GATE` da news sottile/irrilevante e può promuovere a WRONG_SIGN/FILTERED solo con evidenza. Usa `UNKNOWN` quando non basta. `CAUGHT` deve specificare held-at-open/new-entry/incremental-add e direzione.

**Perché.** Il dossier produce `BELOW_GATE`, ma il report lo rimappa in modo variabile a THIN_NEUTRAL o FILTERED. Quella variabilità contamina la distribuzione delle cause. `execution_decisions.reason` con `abs(score)` può sottocontare WRONG_SIGN.

**Come.** Mappatura esplicita e due assi v2 in parallelo; il legacy resta invariato durante la finestra. Un reason enum strutturato è preferibile a parsing di testo.

**Freeze.** **[STRUMENTAZIONE]** per v2 parallelo e lettura del segno corretto; **[DEROGA]** per sostituire la tassonomia primaria.

**Modelli.** Codex; GLM-5.2; DeepSeek-v4-flash; Claude Opus (copertura specifica/causalità).

### P3 — Prompt falsificabile, non confermativo

**Cosa.** Per ogni finding toccato chiedere: esposizione del giorno, cosa si sarebbe visto se fosse falso, evidenza favorevole/contraria, non-occorrenza, prossimo test read-only decisivo, meccanismo e fonte. Evidenziare massimo tre finding nuovi/materialmente peggiorati/vicini alla soglia; il resto in appendice.

**Perché.** “Nel dubbio aggancia” senza denominatore e senza ritiro crea solo accumulo di record aperti. Il report deve poter smentire un'ipotesi, non soltanto confermarla.

**Come.** Checklist meccanica di tutti i finding aperti prima di §7; output strutturato `supported/contradicted/not_exposed`; distanza dalle soglie; due spiegazioni alternative scartate con evidenza. La proposta MiniMax di chiedere chain-of-thought va riformulata: serve una breve motivazione auditabile e dati citati, non ragionamento interno libero.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7 (rationale del controfattuale, riformulato).

### P4 — Struttura del report e digest operatore

**Cosa.** Decision card di tre fatti; data quality; funnel; opportunità azionabili; active/passive; signal diagnostics; pattern/regime; stato carta; finding materiali; appendice. Spostare i 96 rendimenti completi in appendice o rinviare al dossier; aggiungere 1–3 casi di successo; generare un digest Telegram di cinque righe e non troncare arbitrariamente i primi 3.800 caratteri.

**Perché.** L'attenzione dell'operatore è limitata; oggi la parte più informativa (§4) viene dopo una tabella di ~100 righe e Telegram riceve un muro parziale.

**Come.** Template fisso e stdout strutturato, con unità/orizzonti. Il report completo resta auditabile, ma §1 e la sezione finding devono reggersi da sole.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

## 3. Dati e cross-analisi

### D1 — Barre intraday e timeline end-to-end della notizia

**Cosa.** Barre 5 minuti (o minute dove serve), incluse pre/after-market se disponibili, e timestamp `published_at → first_seen/fetched_at → ingested_at → scored_at → ciclo → ordine → fill`; quota di movimento realizzata a ogni stadio.

**Perché.** Discrimina tra alpha già consumata prima della pubblicazione, perdita dovuta a ingest/scoring latency e perdita di execution. È la misura decisiva per F-019/F-030 e sblocca alpha accessibile, entry percentile reale, MFE/MAE e follow-up.

**Come.** Join deterministico per articolo/segnale/decisione e primo bar successivo; distribuire latenza e alpha residua, non solo citare un esempio.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Tutti e cinque.

### D2 — Copertura effettiva, attribuzione articolo e concentrazione fonti

**Cosa.** Distinguere righe grezze, articoli unici, issuer-specific, sector/macro relevant, false entity match, irrelevant fan-out, catalyst nuovo e timing anticipatory/concurrent/retrospective. Aggiungere canonical article id, fonte, concentration ratio, subject ticker, `max_score_own` vs `max_score_fanout`.

**Perché.** 11 righe NVDA con una sola davvero su Nvidia non sono copertura utile; F-001/F-012/F-020 sono tre viste dello stesso problema. Una metrica `effective_timely_coverage` misura ciò che può produrre alpha e rende diagnosticabili fonti e resolver.

**Come.** Deduplica syndication, classificazione di relevance e join article→signal. Report per fonte/settore/evento e costo/IC downstream. Non cambiare le fonti durante il freeze.

**Freeze.** **[STRUMENTAZIONE]**. Cambiare provider o regole di fan-out live è **[POST-FREEZE]**, salvo difetto di correttezza che contamina l'evidenza e deroga approvata.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

### D3 — Contesto evento, settore, regime e microstruttura

**Cosa.** Return residuo vs SPY/ETF settoriale; sector map deterministica; catalyst `earnings/guidance/analyst/M&A/macro/idiosyncratic`; calendario corporate actions; VIX/regime e tag tema; NBBO/spread, volume/ADV, volume surprise e halt.

**Perché.** Nove semi nello stesso rally non sono nove shock indipendenti. Residualizzare evita di attribuire beta settoriale alla news. Event type e microstruttura distinguono gap strutturalmente inaccessibili da errori del motore. VIX e regime sono utili, ma secondari finché non esistono denominatori e alpha accessibile.

**Come.** Usare mappe/config esistenti dove possibile; nuovi campi normalizzati, non narrativa libera; analisi per cluster con n e controllo di concentrazione.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; DeepSeek-v4-flash; MiniMax-m2.7.

### D4 — Snapshot di runtime e distribuzione dei segnali

**Cosa.** Snapshot giornaliero di gate effettivo, pesi ensemble, coppia modelli, regime keys, universo eleggibile, distribuzione score, fallback rate, ensemble std, concentrazione top-5 ticker e stabilità del segnale nel tempo.

**Perché.** La discontinuità #191 dimostra che il gate effettivo è contesto essenziale. Una distribuzione degenere attorno a zero cambia l'interpretazione di BELOW_GATE; modello/fallback/source spiegano drift di qualità.

**Come.** Snapshot read-only nel dossier, timeline score per ticker e segmentazione automatica pre/post discontinuità.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; DeepSeek-v4-flash; MiniMax-m2.7; GLM-5.2.

### D5 — Follow-up e controfattuali shadow

**Cosa.** Riempire T+1/T+3/T+5 di ingressi, uscite e miss; libro ombra read-only sui segnali realmente osservati; curve descrittive per gate 0,20/0,30/0,40, fan-out incluso/escluso, benchmark random/matched/equal-weight/open-entry; confronto con assunzioni del backtest e capture ratio storico come estimator alternativo.

**Perché.** EOD è disallineato con holding S4 di 4–20h e S1 di settimane. I null model impediscono di chiamare “timing scarso” un percentile alto che è meccanico sui titoli in rialzo. Lo shadow book misura il collo di bottiglia senza alterare il live.

**Come.** Policy controfattuali predefinite, dati point-in-time, nessun leakage, risultati con costi e CI. Durante il freeze descrivere la curva; non scegliere il gate ottimo né cambiare produzione.

**Freeze.** **[STRUMENTAZIONE]** per shadow e follow-up; decisioni di gate/fan-out/size **[POST-FREEZE]**.

**Modelli.** Claude Opus; Codex; DeepSeek-v4-flash; MiniMax-m2.7.

## 4. Ledger e findings

### L1 — Pannelli longitudinali e occurrence ledger normalizzato

**Cosa.** Conservare il panel daily e aggiungere: panel ticker-day, panel signal, panel decision/trade, `finding_definitions`, `finding_occurrences.jsonl`, `finding_status_events.jsonl` e viste derivate. Ogni occurrence ha `occurrence_id`, `causal_event_id`, simboli/ID DB, segmento, confidenza, `actual/attributed/missed/avoided_loss`, formula, primary finding e fonte.

**Perché.** Il ledger attuale mescola definizione e occurrence, può contare due volte lo stesso finding/giorno e F-030 combina nella stessa occurrence importi misurati e congetturali che hanno soglie diverse. Un ticker ledger rende meccanici i pattern JD/QCOM/SAP invece di affidarli alla memoria del report.

**Come.** Nuovi file append-only e viste derivate; `causal_event_id` deduplica alpha e forensic report; un solo finding primario riceve il costo, gli altri dichiarano la relazione esplicativa.

**Freeze.** **[STRUMENTAZIONE]** se aggiunto in parallelo e senza riscrivere `findings.json`; migrazione/backfill distruttivo **[DEROGA]**.

**Modelli.** Claude Opus; Codex; DeepSeek-v4-flash; MiniMax-m2.7.

### L2 — Metadati di falsificabilità, stato e contaminazione

**Cosa.** Campi/vista: `giorni_distinti_in_finestra`, `giorni_esposti`, non-occorrenze, `ultima_occorrenza`, distanza/proiezione verso soglia, `dimensione/classe`, strategia, meccanismo, prova decisiva, `contamina_evidenza`, relazione finding→causa, trend e stati `confermato/smentito/strumentale/fuso_in`.

**Perché.** Tutti i finding aperti e senza denominatore produrranno un backlog sovraffollato. F-002/F-006/F-011/F-027/F-028 non sono normali alpha miss: compromettono attribuzione, segno o tracciabilità e devono emergere subito. Lo stato e la non-occorrenza permettono di ritirare ipotesi.

**Come.** Derivare i conteggi senza alterare occurrence; canale separato “contamina evidenza”; ogni stato come evento append-only. Il backfill delle definizioni esistenti richiede una decisione esplicita se modifica il file primario.

**Freeze.** **[STRUMENTAZIONE]** per vista/canale/eventi nuovi; modifica retroattiva del ledger primario **[DEROGA]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

### L3 — Provenienza, versioni e validazione meccanica

**Cosa.** `schema_version`, hash dossier, prompt/model version, completeness status, estimator version e validatore per JSONL, ID unici, `prossimo_id`, somme costi, date/finestra, append-only e duplicati causali.

**Perché.** Una serie cumulativa è utile solo se sappiamo con quale formula e input è stata prodotta. Oggi il prompt è il principale enforcement di invarianti e contiene istruzioni contraddittorie.

**Come.** Il generatore LLM emette candidati; codice deterministico valida e materializza. Fail closed sui ledger se dossier incompleto o schema incompatibile, preservando comunque un report diagnostico.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash.

### L4 — Sintesi deterministica, weekly rollup e alert

**Cosa.** `SYNTHESIS.md` rigenerato dai ledger: stato carta, cambiamenti dal giorno prima, finding vicini/oltre soglia, non-occorrenze, contaminazioni, top simboli/cause e sufficienza statistica. Rollup del venerdì e digest Telegram breve.

**Perché.** Il giornaliero accumula dettagli ma non mostra il cumulato; l'operatore non deve rileggere 40 Markdown. Una sintesi derivata evita drift LLM.

**Come.** Rendering deterministico e idempotente. Al midpoint si può registrare una previsione dei top-5 finali come controllo anti-hindsight, chiarendo che non cambia soglie né selezione.

**Freeze.** **[STRUMENTAZIONE]**.

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash; MiniMax-m2.7.

## 5. Decisioni, deroghe e lavoro post-freeze

### O1 — Decisione umana su tassonomia primaria e restatement storico

**Cosa.** Decidere se: (a) aggiungere solo v2 parallelo; (b) promuovere BELOW_GATE e actionability a tassonomia primaria; (c) ricalcolare costi storici con estimator accessibile; (d) migrare/normalizzare retroattivamente ledger e stati.

**Perché.** La serie legacy è incoerente in cost estimation e troppo grossolana nelle cause, ma modificarla durante l'esperimento cambia l'oggetto pre-registrato e viola append-only. Il beneficio analitico non autorizza una riscrittura silenziosa.

**Come.** Raccomandazione: opzione (a) ora; conservare raw legacy e produrre una vista v2 separata. Le opzioni (b–d) richiedono decisione umana, piano di compatibilità, snapshot prima/dopo e registro deroga nella carta.

**Freeze.** **[DEROGA]** per (b–d); nessuna deroga per (a).

**Modelli.** Claude Opus; Codex; GLM-5.2; DeepSeek-v4-flash.

### O2 — Tarature da non eseguire ora

**Cosa.** Soglia mover σ-scaled; scelta del gate ottimo; modifica del gate in base a confusion matrix/score distribution; dynamic sizing; holding policy; cambio provider/fan-out; ricalibrazione delle soglie dollari della carta.

**Perché.** Sono decisioni di policy, non misure. I modelli propongono buoni esperimenti shadow, ma alcuni saltano troppo presto dalla descrizione alla taratura. In particolare, F-001 sopra $1.000 non basta: servono estimator coerente e soglia di giorni distinti.

**Come.** Raccogliere ora le curve e i controfattuali; aprire la decisione dopo la scadenza, usando dati segmentati e test predefiniti. Non scegliere un optimum durante la finestra.

**Freeze.** **[POST-FREEZE]**.

**Modelli.** DeepSeek-v4-flash (σ-scaled); MiniMax-m2.7 (gate e size); Claude Opus (soglie/capture estimator); Codex (timing/sizing); GLM-5.2 (segnali per ora, da trattare con cautela).

## Findings scartati o riformulati criticamente

- **Chain-of-thought obbligatoria (MiniMax): scartata nella forma letterale.** Non è un output stabile né necessario. È mantenuto il valore con campi auditabili: formula, cutoff informativo, dati citati, alternative ed evidenza contraria.
- **Costo marginale sottraendo esposizioni “simili” già in portafoglio (MiniMax): riformulato.** Titoli dello stesso tema non sono fungibili. Il costo è portfolio-aware solo per capitale/risk budget e vincoli realmente applicabili, salvo regola di sostituzione pre-registrata.
- **t-stat per ora d'ingresso come segnale già “statisticamente significativo” (GLM): declassato a descrittivo.** Sette bucket e ricerca ex post richiedono correzione di molteplicità e controllo out-of-sample.
- **Ricalibrare ora soglie/gate/size (Opus, DeepSeek, MiniMax): rinviato.** È taratura. È invece compatibile produrre estimator v2, curve shadow e decision context.
- **VIX, NBBO, ADV e microstruttura (MiniMax/Codex): mantenuti ma non prioritari.** Aggiungono contesto, ma non sbloccano le domande della carta quanto P&L economico, timeline e pannelli.
- **Cambiare la soglia mover da 3% a k·σ (DeepSeek): post-freeze.** Durante la finestra altererebbe il campione. Si può calcolare in parallelo come sensitivity analysis.
- **“Zero WRONG_SIGN implica gate ben calibrato” (MiniMax): scartato.** F-006 perde il segno nella reason e la selezione sui soli mover rende l'inferenza invalida.
- **Capture ratio storico come moltiplicatore ufficiale (DeepSeek): mantenuto solo come benchmark.** Il campione dei trade realizzati è selection-biased; per promuoverlo a estimator servono campione e metodo pre-registrati.

## Dipendenze — cosa sblocca cosa

```text
[D1 timeline/barre] ──> [M2 alpha accessibile] ──> [M5 signal quality]
         │                       │                         │
         └──────────────────────> [M4 decision quality] ──┤

[D2 coverage attribution] ─────> [M1 funnel v2] ─────────┤
         └──────────────────────> [M5 signal quality]     │

[L1 pannelli occurrence] ──────> [M3 scoreboard] ────────┤
         │                       [M6 statistical rigor]   │
         └─> [L2 metadata] ──> [L4 synthesis/alerts] <───┘

[L3 provenance/validation] sostiene D1, D2, L1 e il contratto prompt P1–P3.
[P4 report/digest] dipende dai KPI stabilizzati di M1–M6 e dalla sintesi L4.
[O1 decisione legacy] può usare tutte le viste v2, ma non blocca la strumentazione parallela.
[O2 taratura post-freeze] dipende da M2, M5, M6, D5 e dalla chiusura della finestra #171.
```

## Breakdown proposto per issue GitHub

| Ordine | Titolo | Include | Bloccata da | Label principali |
|---:|---|---|---|---|
| 1 | Alpha-miss: acquisire timeline end-to-end e barre intraday | D1, base M2 | — | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 2 | Alpha-miss: calcolare alpha accessibile e cost estimator v2 | M2 | 1 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 3 | Alpha-miss: misurare P&L economico e scoreboard della carta | M3 | — | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 4 | Alpha-miss: introdurre funnel actionability/pipeline v2 | M1, P2 | 2 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 5 | Alpha-miss: misurare copertura effettiva e attribution articoli | D2 | — | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 6 | Alpha-miss: costruire pannelli longitudinali e occurrence ledger | L1, L3 | 1, 5 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 7 | Alpha-miss: aggiungere signal diagnostics e controlli negativi | M5, M6, D4, D5 | 2, 5, 6 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 8 | Alpha-miss: attribuire P&L active/passive e qualità decisionale | M4, parte D5 | 2, 6 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 9 | Alpha-miss: rendere findings falsificabili e sintetizzabili | L2, L4 | 3, 6 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 10 | Alpha-miss: correggere contratto prompt e output operativo | P1, P3, P4 | 4, 6, 9 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |
| 11 | Decisione freeze: tassonomia primaria e restatement ledger | O1 | 2, 4, 6 | `wayfinder:decision`, `ready-for-human`, `paper-monitoring` |
| 12 | Post-freeze: valutare gate, mover threshold, size e holding policy | O2 | 7, 8, chiusura #171 | `wayfinder:task`, `paper-monitoring` |
| 13 | Alpha-miss: aggiungere contesto evento/regime/microstruttura | D3 | 1, 5 | `wayfinder:task`, `paper-monitoring`, `freeze-ok` |

Le issue sono volutamente verticali e verificabili. Le prime cinque costituiscono il nucleo ad alta leva; le altre sfruttano quella base senza cambiare il comportamento del trading system.
