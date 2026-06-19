# OPUS_FUNCTIONAL_REMEDIATION_BLUEPRINT

> **Passata 1 di 5** — Functional Remediation Blueprint
> Ruolo: Chief Product Officer + Chief Risk Officer + Governance Reviewer + Product Safety Reviewer + Operating Model Designer.
> Modalità: **read-only**. Nessun file di sistema modificato, nessun codice scritto, nessuna patch, nessun commit, nessuna pipeline/worker/ordine eseguito. Questo documento è l'unico artefatto prodotto.
> Fonte primaria: `docs/FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md` (fasi 1–7 + appendice red-team + R&D backlog), riconciliata con `config/strategies.yaml` e `config/trading.yaml`.
> Data: 2026-06-18.

**Cosa questo documento NON è:** non è una code review, non è una quant validity memo, non valida l'alpha di S1/S3/S4/S7, non propone patch né tuning di parametri. Le verifiche tecniche sono delegate alla §12 (Passata 3 — Kimi). Le verifiche statistiche/quant sono delegate alla §11 (Passata 2 — Quant Validity Memo).

---

## 1. Executive Summary

Alembic ha uno **scheletro architetturale sano** (LLM mai nel hot path — rispettato; formula sentiment corretta; catena di audit `execution_decisions → trades → portfolio_cycles → daily_state` robusta; frontend tipizzato con badge LIVE/BACKTEST). Sopra questo scheletro, però, **manca quasi tutto il tessuto di governance, safety e verità operativa** che rende un sistema di trading governabile con capitale reale.

Il problema dominante non è un bug: è un **disallineamento tra la classe di rischio con cui il sistema è operato e la classe di maturità che effettivamente possiede.** Oggi S1 è **live al 50% di capitale reale**, ma: (a) la sua validazione "5/5 gate" non valida (same-bar lookahead, stress circolare, robustness data-mined, survivorship, denominatore gate gonfiato — tutto da confermare in Passata 2); (b) **in live non esiste alcuno stop-loss funzionante**; (c) il **kill-switch ha una race window** ed è revocabile in un click; (d) il **regime detector è calcolato ma non applicato** (nessun de-risking); (e) il **frontend mostra come attivi risk control che non lo sono** e permette di **disabilitarli via slider** senza validazione né audit; (f) il backtest **non è riproducibile** e **33 test sono rossi**; (g) una **API key è hardcoded** in uno script che gira in cron con un agente LLM a permessi pieni.

Non esiste una **source of truth** per lo stato delle strategie: roadmap, `config/strategies.yaml`, docstring e UI si contraddicono a vicenda (S7 "done" ma orfano; S4 "capped until gate report" ma il gate report è inottenibile; S2 "all gates failed" inesatto). Il sistema **non sa dire la verità su sé stesso**, e il frontend amplifica questa falsa sicurezza verso l'operatore.

**Verdetto:** *Research-grade nello scheletro, Prototype nella safety operativa, attualmente mis-operato come Live.* Il percorso non è "aggiungere feature": è (0) smettere di peggiorare e ridurre l'esposizione reale, (1) costruire una source of truth, (2) ripristinare la safety di esecuzione, (3) rendere onesta la validazione, (4) rendere veritiero il cockpit, (5) riqualificare le strategie. Nuovo alpha solo dopo.

---

## 2. System Verdict

**Classificazione: RESEARCH-GRADE (scheletro) / PROTOTYPE (safety operativa) — NON paper-ready come oggi governato, NON live-ready. Attualmente mis-operato come Live.**

Perché non è un semplice "Research-grade":

- **Sopra Prototype** perché: il paradigma Alpha Miner è rispettato (nessun LLM sincrono in esecuzione), la catena di audit dei dati di esecuzione è reale e forte, il frontend è strutturato e tipizzato. C'è un'ossatura su cui costruire.
- **Non Paper-ready (come oggi governato)** perché un paper trading è "affidabile" solo se: lo stato del sistema è veritiero, i risk control dichiarati sono quelli applicati, la configurazione non è alterabile senza audit, e la divergenza paper↔live è misurata. Nessuna di queste condizioni è soddisfatta. Un paper su cui l'operatore può spostare il drawdown cap al 20% via slider, che mostra un regime-multiplier finto, e che non misura la propria divergenza, **non produce evidenza affidabile** — quindi non è "vero paper" in senso decisionale.
- **Emphatically NOT Live-ready** perché: nessuno stop-loss live, kill-switch con race window e revocabile senza secondo fattore, regime non applicato, calendario fail-open, duplicate-BUY da ordini pending, validazione non riproducibile e non onesta. Ognuna di queste, da sola, è bloccante per il capitale reale.
- **Mis-operato come Live** è il finding di governance più grave: il sistema è **già esposto** (S1 50%) su una base di validazione e safety che non lo giustifica. Questo non è un rischio futuro, è un'esposizione presente.

La classe-obiettivo realistica per i prossimi 30 giorni non è "live", è **"Supervised Paper"**: paper reso veritiero (truth + safety + cockpit) prima ancora di parlare di promozione.

---

## 3. What Is Worth Preserving

Da **non rompere** durante la remediation:

1. **Paradigma Alpha Miner / LLM offline.** Vincolo non-negoziabile rispettato e verificato. È l'asset architetturale più importante. Qualsiasi nuova capability deve preservarlo.
2. **Catena di audit di esecuzione.** `execution_decisions (+reason) → trades → portfolio_cycles → daily_state` è una base di auditabilità reale e forte. Va documentata come catena ufficiale (la `audit_log` morta va chiarita, non confusa con questa).
3. **Formula sentiment `score = polarity × confidence`.** Corretta e coerente con la spec.
4. **Separazione dei worker** (`general` vs `inference` concurrency=1) per isolare FinBERT/Ollama. Disciplina di isolamento sana.
5. **Frontend tipizzato e modulare** (client API per dominio, componenti condivisi, badge LIVE/BACKTEST, ModeBadge). L'ossatura UX esiste; il problema è la *veridicità* di ciò che mostra, non la struttura.
6. **Sanitizzazione input LLM** (omoglifi/BiDi) — capability difensiva già presente.
7. **Esistenza (anche se non cablata/onesta) delle macchine di risk:** ConstraintEnforcer, PortfolioRiskMonitor, VolTargeter, DecayMonitor, kill-switch, loss-feedback, Brinson. I componenti ci sono; vanno cablati, ordinati e resi veritieri — non riscritti da zero.
8. **Esistenza di un cost model strutturato** (spread a tier, square-root impact). La struttura è buona; il problema è che l'input (volume/ADV) non è alimentato.

**Principio:** la remediation è prevalentemente *cablaggio, governance e verità*, non riscrittura. Lo scheletro buono va protetto.

---

## 4. Functional Blockers

### 4.1 Triage per tema funzionale

I finding del documento sorgente sono raggruppati negli 11 temi richiesti, con stato di triage e priorità funzionale.

| # | Tema funzionale | Finding sorgente (D/F/E + red-team) | Stato triage | P |
|---|---|---|---|---|
| T1 | **System Truth Layer** (nessuna source of truth; roadmap/config/docstring/UI si contraddicono) | D-01, D-02, D-03, D-04, D-05, F-14, RT-15 | **SYSTEMIC_BLOCKER** | P0 |
| T2 | **Strategy Lifecycle Governance** (stati non verificabili; promozione senza gate; S7/S4 stato falso) | D-01, D-02, D-04, F-13, §3-S1..S7 | **SYSTEMIC_BLOCKER / PROMOTION_BLOCKER** | P0 |
| T3 | **Paper/Live Separation** (modo deciso da substring URL; nessun interruttore esplicito) | E-17, E-20, RT (paper-live) | **LIVE_BLOCKER / PRODUCT_RISK** | P0 |
| T4 | **Execution Safety as Product Requirement** (stop-loss inesistente in live; partial fill; duplicate-BUY; calendario fail-open; market order ciechi) | F-12, E-06, E-07, E-08, RT-9..13, Agent-exec 1/4/5/6 | **LIVE_BLOCKER** | P0 |
| T5 | **Risk Controls: dichiarati vs reali** (regime non applicato; vol targeter post-constraint; combiner senza net-cap; kill-switch race; recovery auto) | F-01, F-02, F-03, E-14, E-16, RT-6/8, R1/R3/R4 | **SYSTEMIC_BLOCKER / LIVE_BLOCKER** | P0 |
| T6 | **Backtest / Validation Governance** (same-bar lookahead; stress circolare; robustness data-mined; gate denominator; DSR n_trials=1; survivorship; non riproducibile; kill-switch non modellato) | F-04, E-18, RT-1/2/3/4/5, App2-premessa | **SYSTEMIC_BLOCKER / PROMOTION_BLOCKER** | P0 |
| T7 | **Product / Frontend Truthfulness** (regime finto in UI; PEAD tab fuorviante; slider che disabilitano risk control; promotion-readiness assente) | F-13, E-19, E-20, RT-6/7, M5/M6 | **PRODUCT_RISK / LIVE_BLOCKER** | P0 |
| T8 | **Data / LLM Pipeline Governance** (EDGAR rotto; consensus allucinabile; dedup news; fallback non auditato; PSI non blocca) | F-05, F-06, E-11, E-12, E-13, E-02 | **PAPER_BLOCKER / PROMOTION_BLOCKER (per S4/S7)** | P1 |
| T9 | **Security / Ops as Functional Blockers** (API key in repo; LLM `--dangerously-skip-permissions` in cron; JWT fallback; docker insicuro; DR assente) | F-07, F-08, F-09, RT-14, T4, T7 | **LIVE_BLOCKER / SYSTEMIC_BLOCKER** | P0 |
| T10 | **Auditability & Reproducibility** (no pin data/modello/seed; 33 test rossi; config change non auditato; audit_log morta) | E-18, F-11, M4, M5, T6 | **SYSTEMIC_BLOCKER** | P0 |
| T11 | **R&D Containment** (S7 orfano ma esposto come prodotto; S3/S2 da tenere fuori) | D-01, F-13, F-05/06, §S2/S3/S7 | **R&D_CONTAINMENT / PRODUCT_RISK** | P1 |

### 4.2 Dettaglio per tema (perché conta · danno · impatto · prerequisito)

**T1 — System Truth Layer · SYSTEMIC_BLOCKER · P0.**
Perché conta: senza una fonte unica e verificabile dello stato (strategie, gate, allocazioni, modo, readiness), ogni decisione — promozione, halt, allocazione — è presa su dati che si contraddicono. Danno: si crede attivo ciò che è morto (S7) e validato ciò che non lo è (S4 gate). Impatta: tutti gli operatori e tutte le strategie. Prerequisito di: T2 (lifecycle), T7 (cockpit), qualsiasi promozione.

**T2 — Strategy Lifecycle Governance · SYSTEMIC_BLOCKER · P0.**
Perché conta: non esiste un meccanismo che leghi lo *stato* di una strategia a *condizioni verificabili*. S1 è "live" per asserzione, non per gate riproducibile; S4 è "paper capped until gate" ma il gate è inottenibile → la soglia è indefinita. Danno: promozioni arbitrarie / blocchi arbitrari. Impatta: S1 (sovra-promossa), S4 (bloccata indefinitamente), S7 (falsamente "done"). Prerequisito: T1.

**T3 — Paper/Live Separation · LIVE_BLOCKER + PRODUCT_RISK · P0.**
Perché conta: il modo (paper vs live) è dedotto da una substring nell'URL Alpaca, non da un interruttore esplicito con conferma e audit. Danno: una modifica di config/env può spostare l'intero sistema su live senza un gate cosciente. Impatta: tutte le strategie attive (S1, S4) e l'operatore.

**T4 — Execution Safety · LIVE_BLOCKER · P0.**
Perché conta: in live oggi **nessuno stop-loss funziona** (worker legacy morto + bracket off di default), gli ordini sono market ciechi su ADV finta, i partial fill/reject sono gestiti solo in batch notturno, e ordini pending generano duplicate-BUY. Danno: perdita downside non protetta su gap, over-exposure, P&L peggiore delle attese. Impatta: ogni euro di capitale reale già esposto (S1). Questo è il blocco più grave perché è *attivo ora*.

**T5 — Risk Controls dichiarati vs reali · SYSTEMIC_BLOCKER + LIVE_BLOCKER · P0.**
Perché conta: i risk control esistono nel codice ma non sono nel path effettivo (regime `=1.0` hardcoded; vol targeter dopo i constraint può ri-violare il cap 50%; combiner senza net-cap; kill-switch ricontrollato una sola volta a inizio ciclo). Danno: il sistema espone come in bull anche in bear; supera i limiti dichiarati; un halt durante un ciclo non ferma gli ordini. Impatta: tutte le strategie e l'integrità dei limiti dichiarati.

**T6 — Backtest / Validation Governance · SYSTEMIC_BLOCKER + PROMOTION_BLOCKER · P0.**
Perché conta (governance, non quant): la validazione che certifica S1 **non è rieseguibile né onesta nel design** (same-bar fill, stress dentro l'OOS, robustness = max su grid senza correzione, denominatore gate-2 ripulito, DSR con n_trials=1, universo survivorship-contaminated, adjusted-close come prezzo eseguibile, no pin data/modello/seed). Danno: ogni decisione di promozione poggia su numeri non verificabili. Impatta: S1 (promozione), e per estensione la fiducia nell'intero processo. *La validità statistica puntuale è demandata alla Passata 2; qui è un blocco di fiducia e riproducibilità.*

**T7 — Product / Frontend Truthfulness · PRODUCT_RISK + LIVE_BLOCKER · P0.**
Perché conta: il frontend mostra un regime-multiplier che non è applicato (`Performance.tsx`), presenta PEAD come attivo (è morto), e consente di disabilitare risk control via slider senza validazione né audit (`Config.tsx` + `update_config` senza bound). Danno: doppia falsa sicurezza (codice + UI) e una via per smontare la safety con un click. Impatta: l'operatore, che prende decisioni su una realtà falsa.

**T8 — Data / LLM Pipeline Governance · PAPER/PROMOTION_BLOCKER (S4/S7) · P1.**
Perché conta: EDGAR invia solo metadati all'LLM (S7), il consensus EPS è chiesto all'LLM stesso (allucinabile), il fallback FinBERT non è auditato, PSI non blocca. Danno: segnali rumorosi o allucinati entrano (o entrerebbero) nel signal store. Impatta: S4 (qualità), S7 (intera pipeline).

**T9 — Security / Ops · LIVE_BLOCKER + SYSTEMIC_BLOCKER · P0.**
Perché conta: API key in chiaro in script tracciato, eseguito in cron da un agente LLM con `--dangerously-skip-permissions` (azioni distruttive possibili); JWT con fallback efimero; docker con default insicuri; nessuna DR. Danno: compromissione credenziali, azioni autonome non controllate, sessioni instabili. Impatta: l'intero sistema e i secret di trading.

**T10 — Auditability & Reproducibility · SYSTEMIC_BLOCKER · P0.**
Perché conta: senza pin (data/modello/seed) e con 33 test rossi, nessun risultato è riproducibile e nessuna regressione è intercettata; i config change non sono auditati. Danno: impossibile dimostrare che "ciò che gira" è "ciò che è stato validato". Prerequisito di: ogni promozione e ogni claim.

**T11 — R&D Containment · R&D_CONTAINMENT + PRODUCT_RISK · P1.**
Perché conta: codice R&D (S7, e in parte S3/S2) raggiunge superfici operative (tab UI, scrittura Redis) pur non essendo cablato/validato. Danno: confusione tra ricerca e operativo; falsa completezza. Impatta: operatore e igiene del sistema.

### 4.3 Tabella blocchi (sintesi per §9/§10)

| Blocker | Tipo | Impatto | P | Strategie impattate | Remediation |
|---|---|---|---|---|---|
| Nessuna source of truth | SYSTEMIC | Decisioni su dati falsi | P0 | tutte | RB-001 |
| Lifecycle senza gate | SYSTEMIC/PROMOTION | Promozioni arbitrarie | P0 | tutte | RB-002, RB-009 |
| Paper/live implicito | LIVE/PRODUCT | Passaggio live inconsapevole | P0 | S1, S4 | RB-003 |
| Stop-loss live assente | LIVE | Downside non protetto | P0 | S1 (live) | RB-004 |
| Kill-switch race + revocabile | SYSTEMIC/LIVE | Safety net bucata | P0 | tutte | RB-005 |
| Regime non applicato | SYSTEMIC/LIVE | Nessun de-risking | P0 | tutte | RB-006 |
| Vol targeter post-constraint / no net-cap | LIVE | Cap esposizione violabile | P0 | tutte | RB-006 |
| UI mostra/disabilita risk control finti | PRODUCT/LIVE | Falsa sicurezza + sabotaggio | P0 | tutte | RB-006, RB-007, RB-012 |
| Validazione non riproducibile/non onesta | SYSTEMIC/PROMOTION | Numeri non verificabili | P0 | S1 (+tutte) | RB-008, RB-009, RB-010 |
| Secret in repo + LLM cron full-perms | LIVE/SYSTEMIC | Compromissione/azioni autonome | P0 | tutte | RB-014 |
| 33 test rossi / no determinismo | SYSTEMIC | Nessuna garanzia di regressione | P0 | tutte | RB-015 |
| Calendario fail-open | LIVE | Ordini a mercato chiuso | P0 | tutte | RB-016 |
| EDGAR/consensus rotti (PEAD) | PROMOTION (S7) | Pipeline rumore | P1 | S7 | RB-011 |
| PEAD tab / R&D esposti | PRODUCT/R&D | Falsa completezza | P1 | S7 | RB-011, RB-012 |

---

## 5. Strategy Lifecycle Governance

Valutazione **di governance** (lifecycle/stato/readiness), non di alpha. La validità statistica è demandata alla Passata 2.

### Strategia S1 — Time-Series Momentum Multi-Asset
- **Stato attuale dichiarato:** live, 50% capitale (`config/strategies.yaml`), "all gates passed, OOS Sharpe ~0.51".
- **Stato funzionale consigliato:** **Paper only (demozione immediata da live).** Riduzione dell'esposizione reale a minima/flat fino a chiusura dei blocchi safety.
- **Motivazione di governance:** è l'unica strategia "promossa", ma su una validazione che (red-team) non valida e senza i 4 safeguard della spec (90gg paper, riproducibilità, DR, ≤5% capitale). In più, in live non ha stop-loss né de-risking. È live per asserzione, non per gate verificabile.
- **Cosa manca per avanzare:** source of truth (RB-001), promotion gate riproducibile (RB-002/009), safety di esecuzione (RB-004/005/016), validazione onesta e riproducibile (RB-008/010), regime applicato (RB-006).
- **Finding bloccanti:** F-01, F-02, F-04, E-14, E-18, RT-1/2/3/4/5, T4/T6/T9.
- **Capability funzionali richieste:** Strategy Status SoT, Promotion Readiness Gate, Execution Safety Baseline, Reproducible Validation Manifest, Risk Control Truthfulness.
- **Chiedere alla Quant Validity Memo:** S1 sopravvive a t+1 + survivorship-free + costi reali + correzione multipla? Quanto OOS è vero bear?
- **Chiedere alla Technical Verification:** stop-loss realmente cablato nel path portfolio? regime davvero hardcoded a 1.0? same-bar fill confermato?
- **Raccomandazione finale:** trattare S1 come **paper supervisionato**; nessun ritorno a live finché safety (Phase 2) e quant memo (Passata 2) non lo riqualificano.

### Strategia S2 — VRP
- **Stato attuale dichiarato:** disabled, 0%, research ("all gates failed", OOS Sharpe −0.55).
- **Stato funzionale consigliato:** **Disabled / R&D only (confermato).**
- **Motivazione di governance:** la disabilitazione è corretta; il problema è di *truth* (la nota config "all gates failed" è inesatta — gate 5 passato). Non è opportunità di tuning ma ipotesi da falsificare ex-novo.
- **Cosa manca per avanzare:** diagnosi della fonte del segno negativo *prima* di qualsiasi riabilitazione; correzione della nota stato in SoT.
- **Finding bloccanti:** D-04 (truth), Sharpe negativo.
- **Capability richieste:** Strategy Status SoT (per correggere la nota), R&D Containment.
- **Chiedere alla Quant Memo:** il −0.55 è inversione di segno o mis-specifica? VRP è falso alpha in questo setup?
- **Chiedere alla Technical Verification:** la voce gate in config è derivata o scritta a mano? dove vive lo stato gate reale?
- **Raccomandazione finale:** mantenere disabled; correggere la verità dello stato; nessuna riabilitazione senza diagnosi.

### Strategia S3 — Cross-Sectional Residual Momentum
- **Stato attuale dichiarato:** disabled, 0%, research (gate 3/5 falliti, sospetto sizing lookahead).
- **Stato funzionale consigliato:** **R&D only (confermato disabled).**
- **Motivazione di governance:** disabilitazione corretta. Il sospetto lookahead nel sizing è un blocco di credibilità: finché non falsificato, l'OOS 0.15 è inattendibile.
- **Cosa manca per avanzare:** test di contaminazione lookahead; universo PIT survivorship-free.
- **Finding bloccanti:** gate 3/5, sospetto lookahead, survivorship.
- **Capability richieste:** Reproducible Validation Manifest, no-lookahead policy (RB-010), R&D Containment.
- **Chiedere alla Quant Memo:** il lookahead nel sizing è reale? rimuovendolo l'edge sopravvive o è artefatto?
- **Chiedere alla Technical Verification:** il sizing usa prezzo a t per size a t? il path S3 usa `active_at` PIT?
- **Raccomandazione finale:** R&D; falsificare il lookahead prima di ogni sviluppo.

### Strategia S4 — News-Driven Tactical LLM
- **Stato attuale dichiarato:** paper, 10% ("capped until gate report").
- **Stato funzionale consigliato:** **Paper only contenuto — promozione BLOCCATA.** Trattare come R&D-leaning finché gate script + RAG/supervisor non sono verificati.
- **Motivazione di governance:** la soglia di promozione è **indefinita** perché il gate report è inottenibile (script rotto). La spec richiede RAG + supervisor per produzione, non verificati in esecuzione. Enforcement del cap 10% è soft (solo warning).
- **Cosa manca per avanzare:** gate report eseguibile e riproducibile (RB-009); RAG/supervisor verificati; enforcement hard del cap; dedup news.
- **Finding bloccanti:** D-02, D-05, F-13(indiretto), E-11/E-12, S4-1/S4-3.
- **Capability richieste:** Gate Report Lifecycle, LLM Governance (RAG/supervisor/fallback audit), enforcement allocazioni, Strategy Status SoT.
- **Chiedere alla Quant Memo:** S4 ha edge (IC vs forward returns) o è rumore LLM? l'ensemble è realmente diversificato (correlazione)?
- **Chiedere alla Technical Verification:** RAG e supervisor sono nel path di produzione? il cap 10% è enforced (raise) o solo warning? il gate script gira?
- **Raccomandazione finale:** mantenere in paper contenuto; nessuna promozione finché il gate è riproducibile e RAG/supervisor verificati.

### Strategia S7 — PEAD
- **Stato attuale dichiarato:** roadmap "done"; in realtà non registrato, non `__call__`-compatibile, EDGAR rotto, nessun consumer, consensus allucinabile. **Esposto in UI come attivo.**
- **Stato funzionale consigliato:** **R&D only + RIMOZIONE dalla superficie operativa (disclaimer o nascondere il tab).**
- **Motivazione di governance:** è un **arto morto presentato come prodotto** → falsa completezza e falsa sicurezza. La roadmap mente. Non candidabile a nessuno stato operativo.
- **Cosa manca per avanzare:** consensus EPS esterno point-in-time (non LLM); fetch reale 8-K; consumer; registrazione; `__call__`; poi validazione 5 gate survivorship-free.
- **Finding bloccanti:** D-01, F-05, F-06, F-13.
- **Capability richieste:** R&D Containment (immediata), Data/LLM Governance, Strategy Status SoT.
- **Chiedere alla Quant Memo:** anche riparato, PEAD ha edge fuori da survivorship/microstruttura? (P2)
- **Chiedere alla Technical Verification:** confermare non-registrazione, assenza consumer, EDGAR solo-metadati, roadmap `[x]` falso.
- **Raccomandazione finale:** marcare R&D, togliere dalla superficie operativa **subito**; de-flaggare in roadmap; nessuna allocazione.

---

## 6. Flow Correctness Review

Per ogni flusso: correttezza logica · dove si rompe · falsa sicurezza · invarianti mancanti · metriche mancanti · cosa demandare a code/quant · P.

**Flusso 1 — Research → Backtest → Gates → Paper → Live.**
Correttezza: **rotto a livello di governance.** Non è un pipeline con gate verificabili: i gate non sono riproducibili (no pin), il passaggio paper→live non è un evento esplicito (substring URL), e "live" è stato raggiunto senza i safeguard della spec. Si rompe: tra "gate passati" (asserzione) e "live" (capitale reale) non c'è un cancello cosciente. Falsa sicurezza: "5/5 gate" suggerisce una pipeline disciplinata che non esiste. Invarianti mancanti: *nessuna promozione senza gate riproducibile + N giorni paper + DR + cap capitale*. Metriche mancanti: paper days, reproducibility hash, capital %, DR flag. Demandare a code (Kimi): dove vive lo stato di promozione? a quant (P2): i gate validano? **P0.**

**Flusso 2 — News ingest → LLM scoring → Signal aggregation → Decision → Order.**
Correttezza: l'ossatura è corretta (LLM offline, score=pol×conf). Si rompe: dedup news non garantito (segnale gonfiabile), consensus allucinabile (S7), fallback FinBERT non auditato, threshold non cost-aware. Falsa sicurezza: l'ensemble "riduce il rischio" ma la diversità reale (correlazione modelli) non è misurata. Invarianti mancanti: *nessun segnale entra senza dedup + sanitizzazione + fonte consensus esterna*. Metriche mancanti: fallback rate, PSI, ensemble correlation, dedup rate. Demandare a code: RAG/supervisor in path? a quant: l'IC di S4 regge net-of-cost? **P1.**

**Flusso 3 — Strategy outputs → Portfolio combiner → Risk constraints → Vol targeting → Orders.**
Correttezza: **ordine logico errato.** Il vol targeter è applicato *dopo* i constraint → può ri-violare il cap 50%; il combiner somma pesi senza risoluzione conflitti BUY/SELL né net-exposure cap. Si rompe: segnali opposti si compensano silenziosamente o saturano; il cap dichiarato non è garantito. Falsa sicurezza: "max_portfolio_exposure 0.50" in config suggerisce un limite che non è invariante. Invarianti mancanti: *net-exposure ≤ cap sempre, post-ogni-trasformazione*; *risoluzione deterministica dei conflitti*. Metriche mancanti: net-exposure reale post-combiner, cap violation count. Demandare a code: ordine effettivo orchestrator; a quant: impatto dei conflitti sul P&L. **P0.**

**Flusso 4 — Risk monitoring → Kill-switch → Halt/recovery.**
Correttezza: **non fail-closed e con race window.** Il kill-switch è controllato una sola volta a inizio ciclo e non prima di `submit_order`; un halt durante un ciclo (~10 min) non ferma gli ordini di quel ciclo. La recovery è auto-on-drawdown (non human-gated); revocabile senza secondo fattore. Si rompe: nella finestra di un evento critico, gli ordini partono comunque. Falsa sicurezza: l'esistenza del kill-switch suggerisce una protezione che ha un buco temporale. Invarianti mancanti: *re-check halt prima di ogni submit*; *recovery human-gated*; *halt fail-closed e audited*. Metriche mancanti: halt audit trail, tempo halt→stop effettivo. Demandare a code: ri-check pre-submit, 2FA su DELETE. **P0.**

**Flusso 5 — Config change → Validation → Audit → Runtime effect.**
Correttezza: **rotto.** `update_config` fa deep-merge + dump senza validazione né bound; gli slider UI permettono drawdown 20%/stop 50%; nessun audit della modifica. Si rompe: un operatore (o una API key compromessa) può disabilitare i risk control con un click. Falsa sicurezza: l'UI presenta i controlli come "regolabili in sicurezza". Invarianti mancanti: *schema + bound server-side*; *nessun indebolimento risk control senza approvazione elevata*; *ogni change auditato*. Metriche mancanti: config change audit log. Demandare a code: dove validare; quali chiavi sono "dangerous". **P0.**

**Flusso 6 — Frontend display → Operator decision → System state.**
Correttezza: **fuorviante.** Mostra regime-multiplier non applicato, PEAD attivo (morto), schedule mirror divergente, "No data" ambiguo (`except: pass`). Si rompe: l'operatore decide su una realtà falsa. Falsa sicurezza: è il cuore del PRODUCT_RISK. Invarianti mancanti: *ogni capability mostrata "attiva" deve essere runtime-attiva*; *stato derivato dalla SoT, non da copie*. Metriche mancanti: stale-data flag, readiness, why-trade. Demandare a code: quali viste sono "mirror" vs derivate dalla fonte reale. **P0.**

**Flusso 7 — Daily/weekly/monthly reports → Strategy promotion/demotion.**
Correttezza: **incompleto.** Non esiste un legame formale tra report e cambi di lifecycle; la promozione/demozione non è guidata da criteri verificabili. Si rompe: le decisioni di stato sono discrezionali. Invarianti mancanti: *promozione/demozione solo via Promotion Readiness Gate*. Metriche mancanti: trigger di demozione (decay, drawdown, divergenza). Demandare a quant: quali soglie di demozione. **P1.**

**Flusso 8 — Runtime events → Audit trail → Reproducibility.**
Correttezza: **parziale.** La catena `execution_decisions→trades→cycles→daily_state` è forte (preservare), ma manca la riproducibilità (no pin data/modello/seed) e l'audit dei config change / halt. `audit_log` è morta e confonde. Si rompe: impossibile dimostrare che il runtime corrisponde al validato. Invarianti mancanti: *ogni decisione riconducibile a input pinnati*; *ogni change/halt auditato*. Metriche mancanti: reproducibility score. Demandare a code: completare audit di config/halt, chiarire audit_log. **P0.**

---

## 7. Remediation Principles

Principi guida di Alembic (ognuno con il *perché*):

1. **Paper e live devono essere stati espliciti, non dedotti.** Perché: un passaggio a capitale reale non deve mai poter avvenire come effetto collaterale di una stringa o di un env. Deve essere una decisione cosciente, confermata e auditata.
2. **Ogni strategia ha uno stato unico e verificabile.** Perché: roadmap, config, docstring e UI non possono contraddirsi; le decisioni di rischio richiedono una sola verità.
3. **Ogni gate deve essere rieseguibile e dare lo stesso risultato.** Perché: un gate non riproducibile non certifica nulla; è un'opinione storica.
4. **Ogni decisione deve essere riproducibile (input pinnati).** Perché: senza pin data/modello/seed non si può dimostrare che ciò che gira è ciò che è stato validato.
5. **Ogni risk control mostrato in UI come attivo deve essere realmente applicato a runtime.** Perché: una UI che mostra protezioni inesistenti è peggio di nessuna UI — induce a rischiare di più.
6. **Ogni risk control deve essere un invariante, non un suggerimento.** Perché: un cap "di solito rispettato" (warning) non è un cap; deve essere enforced (raise/clamp) e ri-validato dopo ogni trasformazione.
7. **Ogni config change pericoloso deve essere validato (schema+bound), auditato e, se indebolisce la safety, approvato in modo elevato.** Perché: i risk control non devono essere disabilitabili con un click.
8. **Nessun LLM nel hot path** (già rispettato — da preservare). Perché: latenza e non-determinismo non devono mai stare tra segnale e ordine.
9. **Ogni backtest usato per promozione deve essere point-in-time, t+1, cost-aware, survivorship-free e riproducibile.** Perché: un backtest same-bar / adjusted-close / survivorship misura un mondo non tradable. *(Validità statistica → Passata 2.)*
10. **Ogni halt deve essere fail-closed e ricontrollato prima di ogni ordine.** Perché: la safety net non deve avere finestre temporali in cui è inattiva.
11. **Ogni strategia R&D deve essere fisicamente separata dall'operativo.** Perché: codice non validato non deve raggiungere superfici (UI, Redis consumer) che ne suggeriscono l'attività.
12. **Nessuna dashboard mostra come attiva una capability non attiva, né permette di disattivare la safety.** Perché: il cockpit è uno strumento di sicurezza, non un pannello di tuning libero.
13. **La verità di sistema vive in una source of truth, non in copie.** Perché: ogni mirror manuale (schedule, stato) diverge.
14. **La suite di test verde è precondizione di fiducia.** Perché: 33 test rossi rendono inattendibile ogni claim "funziona".

---

## 8. Functional Remediation Blueprint

Capability e criteri di accettazione **funzionali** (non implementazioni). Ordinate per priorità.

### [RB-001] Strategy Status Source of Truth
- **Categoria:** Auditability / Strategy Governance.
- **Problema:** stato strategie sparso e contraddittorio (roadmap/config/docstring/UI).
- **Finding sorgente:** D-01, D-02, D-03, D-04, F-14, RT-15.
- **Perché:** ogni decisione di rischio richiede una sola verità verificabile.
- **Priorità:** P0. **Dipendenze:** nessuna (prerequisito di RB-002, RB-009, RB-012).
- **Capability richiesta:** fonte unica e autorevole che per ogni strategia espone: stato lifecycle, allocazione, modo, stato di ogni gate (con data e riproducibilità), paper days, capital %, DR flag, ultima validazione. Tutte le altre superfici (UI, docstring, roadmap) derivano da qui.
- **Criteri di accettazione funzionali:** (a) un solo posto definisce lo stato; (b) UI e report leggono *solo* da lì; (c) discrepanza roadmap/config/codice è impossibile o segnalata automaticamente; (d) ogni stato ha provenienza (chi/quando/perché).
- **Chiedere a Technical Verification:** dove implementarla (tabella DB? YAML generato?); qual è oggi lo store autorevole.
- **Chiedere a Quant Memo:** quali campi di validazione devono comparire (gate, p-value corretto, OOS sample).
- **Cosa NON fare:** non risolvere con un altro file YAML scritto a mano.

### [RB-002] Promotion Readiness Gate
- **Categoria:** Strategy Governance.
- **Problema:** promozione/demozione discrezionale, senza condizioni verificabili.
- **Finding sorgente:** §S1 (live senza safeguard), D-02, Flusso 1/7.
- **Perché:** i cambi di stato devono dipendere da criteri, non da asserzioni.
- **Priorità:** P0. **Dipendenze:** RB-001, RB-008, RB-009.
- **Capability:** un gate formale che blocca il cambio di stato finché non sono soddisfatti i safeguard della spec (gate riproducibili PASS, ≥N giorni paper, riproducibilità verificata, DR verificata, cap capitale rispettato).
- **Criteri di accettazione:** (a) nessun passaggio paper→live possibile se un criterio manca; (b) il gate è esso stesso riproducibile; (c) ogni promozione lascia un record di evidenza.
- **Chiedere a Technical Verification:** dove intercettare il cambio di stato; come renderlo non bypassabile.
- **Chiedere a Quant Memo:** quali soglie quantitative e quali criteri di demozione (decay/divergenza).
- **Cosa NON fare:** non promuovere alcuna strategia finché il gate non esiste.

### [RB-003] Explicit Paper/Live Mode
- **Categoria:** Execution Safety / Product Truthfulness.
- **Problema:** modo dedotto da substring URL.
- **Finding sorgente:** E-17, E-20, Flusso/Q-7.
- **Perché:** il passaggio a capitale reale non deve avvenire implicitamente.
- **Priorità:** P0. **Dipendenze:** RB-001.
- **Capability:** interruttore esplicito paper/live, con conferma cosciente, audit, e visibilità prominente nel cockpit.
- **Criteri di accettazione:** (a) il modo è un dato esplicito, non derivato; (b) passare a live richiede conferma elevata + audit; (c) il modo corrente è inequivocabile in UI.
- **Chiedere a Technical Verification:** dove vive oggi la decisione paper/live; quali path la leggono.
- **Cosa NON fare:** non lasciare che env/URL determinino silenziosamente l'esposizione reale.

### [RB-004] Execution Safety Baseline
- **Categoria:** Execution Safety.
- **Problema:** nessuno stop-loss live funzionante; partial fill/reject batch-only; duplicate-BUY; market order ciechi.
- **Finding sorgente:** F-12, E-06/07/08, RT-11/12/13, Agent-exec 1/4/5/6.
- **Perché:** nessun ordine reale deve esistere senza protezione downside verificata e senza gestione corretta di pending/partial.
- **Priorità:** P0. **Dipendenze:** RB-003.
- **Capability:** un baseline di sicurezza di esecuzione: stop-loss attivo e verificato e2e in live; guardia contro duplicate-BUY (consapevolezza ordini pending); gestione di partial fill/reject prima del ciclo successivo.
- **Criteri di accettazione:** (a) un gap-down simulato chiude la posizione; (b) un ordine pending non genera duplicato al ciclo successivo; (c) un reject non è silenziosamente perso; (d) nessun path live attivo senza questi tre.
- **Chiedere a Technical Verification:** stop-loss realmente attaccato? bracket on? dove fetchare pending? reconcile real-time vs batch.
- **Cosa NON fare:** non considerare "esistente" uno stop-loss in codice morto/disattivato.

### [RB-005] Kill-Switch Governance
- **Categoria:** Risk Control.
- **Problema:** race window, recovery auto, revocabile senza 2FA.
- **Finding sorgente:** RT-8, R4, Flusso 4.
- **Perché:** la safety net non deve avere finestre inattive né vie di fuga facili in tilt.
- **Priorità:** P0. **Dipendenze:** RB-004.
- **Capability:** kill-switch fail-closed, ricontrollato prima di ogni submit, con recovery human-gated, secondo fattore/cooldown sulla revoca, e audit dell'evento.
- **Criteri di accettazione:** (a) halt mid-cycle ferma gli ordini di quel ciclo; (b) la recovery richiede intervento umano (non auto-on-drawdown); (c) la revoca richiede secondo fattore + cooldown; (d) ogni halt/recovery è auditato.
- **Chiedere a Technical Verification:** dove inserire il re-check pre-submit; come persistere lo stato; come auditare.
- **Cosa NON fare:** non lasciare la recovery automatica come unico meccanismo.

### [RB-006] Risk Control Truthfulness (runtime + UI)
- **Categoria:** Risk Control / Product Truthfulness.
- **Problema:** regime non applicato (mostrato attivo in UI); vol targeter post-constraint; combiner senza net-cap.
- **Finding sorgente:** F-01, F-02, F-03, E-14/16, RT-6, R1/R2/R3.
- **Perché:** un risk control mostrato come attivo deve esserlo; un cap deve essere invariante.
- **Priorità:** P0. **Dipendenze:** RB-001 (per la verità UI).
- **Capability:** ogni risk control dichiarato (regime, cap esposizione, net-exposure) è applicato a runtime e ri-validato dopo ogni trasformazione; la UI mostra lo stato *reale* (incl. "regime: non applicato" se è il caso).
- **Criteri di accettazione:** (a) net-exposure ≤ cap sempre, post-vol-targeting e post-combiner; (b) il regime-multiplier mostrato è quello applicato; (c) conflitti BUY/SELL risolti deterministicamente; (d) se un controllo è off, l'UI lo dice.
- **Chiedere a Technical Verification:** ordine effettivo nell'orchestrator; regime davvero hardcoded; dove ri-validare il cap.
- **Chiedere a Quant Memo:** i moltiplicatori regime devono essere pre-specificati e validati OOS (no overfit del risk control).
- **Cosa NON fare:** non tarare i moltiplicatori regime sul drawdown storico.

### [RB-007] Validated Config Change Workflow
- **Categoria:** Risk Control / Ops Safety.
- **Problema:** `update_config` senza validazione né audit; slider UI smontano la safety.
- **Finding sorgente:** RT-7, M5, Flusso 5.
- **Perché:** i risk control non devono essere disabilitabili senza controllo.
- **Priorità:** P0. **Dipendenze:** nessuna.
- **Capability:** ogni config change passa per validazione schema + bound server-side, è auditato, e l'indebolimento di un controllo di rischio richiede approvazione elevata.
- **Criteri di accettazione:** (a) valori fuori bound rifiutati lato server; (b) slider UI clampati ai limiti reali; (c) ogni modifica registrata (chi/quando/da→a); (d) impossibile portare drawdown cap/stop oltre i limiti di sicurezza via UI.
- **Chiedere a Technical Verification:** dove validare; quali chiavi sono "dangerous"; dove auditare.
- **Cosa NON fare:** non affidare i bound solo al frontend.

### [RB-008] Reproducible Validation Manifest
- **Categoria:** Validation Governance / Auditability.
- **Problema:** nessun pin data/modello/seed; risultati non riproducibili.
- **Finding sorgente:** E-18, M4, App2-premessa.
- **Perché:** senza riproducibilità nessun numero è verificabile → nessuna promozione difendibile.
- **Priorità:** P0. **Dipendenze:** RB-015 (test verdi).
- **Capability:** ogni run di validazione produce un manifest (hash dati, versione modello, seed) e può essere rieseguito ottenendo metriche identiche.
- **Criteri di accettazione:** (a) due run su macchine diverse → metriche identiche; (b) ogni gate report linka al suo manifest; (c) una promozione senza manifest è impossibile.
- **Chiedere a Technical Verification:** dove pinnare; come confrontare run-riferimento in CI.
- **Chiedere a Quant Memo:** quali metriche devono essere byte-identiche vs entro tolleranza.
- **Cosa NON fare:** non accettare "near identical" senza una tolleranza dichiarata.

### [RB-009] Gate Report Lifecycle
- **Categoria:** Validation Governance.
- **Problema:** gate report S4 inottenibile (script rotto) → soglia promozione indefinita; gate S1 non onesti nel design.
- **Finding sorgente:** D-02, S4-3, RT-2/3/4.
- **Perché:** un gate non eseguibile/riproducibile non è un gate.
- **Priorità:** P0. **Dipendenze:** RB-008.
- **Capability:** ogni strategia ha un gate report eseguibile, riproducibile e datato; un gate report rotto o stale **blocca** la promozione per definizione.
- **Criteri di accettazione:** (a) ogni gate report gira end-to-end; (b) ha una data di freschezza; (c) lo stato gate in SoT deriva dall'esecuzione, non da nota manuale.
- **Chiedere a Technical Verification:** stato attuale degli script gate; cosa li rompe.
- **Chiedere a Quant Memo:** il *design* dei gate (stress reale, robustness con correzione multipla, denominatore, DSR) è valido.
- **Cosa NON fare:** non "sistemare lo script" senza prima validare il design del gate (rimando Passata 2).

### [RB-010] Backtest↔Live Parity Governance
- **Categoria:** Validation Governance.
- **Problema:** same-bar fill, adjusted-close, kill-switch non modellato, costi ~0 → backtest e live misurano cose diverse.
- **Finding sorgente:** F-04, RT-1/5, S1-2/S1-3/S1-9.
- **Perché:** un backtest non implementabile non può promuovere.
- **Priorità:** P0. **Dipendenze:** RB-008.
- **Capability:** politica di parità: no-lookahead (t+1), cost-aware (ADV reale + fixed cost), kill-switch modellato o risultati etichettati "pre-risk-control"; raw close + dividendi espliciti.
- **Criteri di accettazione:** (a) iniettare un segnale futuro fa fallire il backtest (no-lookahead test); (b) i risultati di promozione sono net-of-cost e t+1; (c) i risultati pre-risk-control sono etichettati come tali.
- **Chiedere a Technical Verification:** conferma same-bar fill, adjusted-close come fill, ADV hardcoded.
- **Chiedere a Quant Memo:** quanto cambia lo Sharpe con t+1 + costi + survivorship-free (il "costo di realismo").
- **Cosa NON fare:** non promuovere su risultati same-bar.

### [RB-011] R&D Strategy Containment
- **Categoria:** R&D Containment.
- **Problema:** S7 orfano esposto come prodotto; codice R&D su superfici operative.
- **Finding sorgente:** D-01, F-05/06, F-13.
- **Perché:** codice non validato non deve apparire attivo.
- **Priorità:** P1 (la parte UI di S7 è P0). **Dipendenze:** RB-001.
- **Capability:** le strategie R&D sono quarantenate: nessuna presentazione "attiva" in UI, nessun consumer cablato, etichetta R&D esplicita.
- **Criteri di accettazione:** (a) S7/PEAD non appaiono come attivi; (b) nessun segnale R&D raggiunge il signal store operativo; (c) lo stato R&D è esplicito in SoT e UI.
- **Chiedere a Technical Verification:** confermare assenza consumer; mappare le superfici dove R&D trapela.
- **Cosa NON fare:** non lasciare il tab PEAD com'è.

### [RB-012] Operator Safety Cockpit
- **Categoria:** Product Truthfulness.
- **Problema:** UI fuorviante (regime finto, PEAD attivo, schedule mirror, "No data" ambiguo); manca promotion-readiness.
- **Finding sorgente:** F-13, E-19/20, D-08, M1/M6, RT-6/7.
- **Perché:** il cockpit è uno strumento di sicurezza; deve mostrare la verità operativa.
- **Priorità:** P0 (verità) / P1 (readiness dashboard). **Dipendenze:** RB-001, RB-006.
- **Capability:** un cockpit che mostra stato reale di strategie e risk control, dati stale, readiness di promozione, why-trade, e un banner paper≠live prominente — tutto derivato dalla SoT.
- **Criteri di accettazione:** (a) nessun elemento mostra come attivo ciò che non lo è; (b) stale data segnalato esplicitamente; (c) promotion-readiness visibile per ogni strategia; (d) schedule derivato dalla fonte reale (no mirror).
- **Chiedere a Technical Verification:** quali viste sono mirror; come derivare lo schedule dal beat.
- **Cosa NON fare:** non trattare la UI come fonte di verità né lasciarla mostrare protezioni inesistenti.

### [RB-013] Monitoring & Alerting Capability
- **Categoria:** Ops Safety / Data Governance.
- **Problema:** fallback rate, PSI red, ensemble correlation, worker/beat lag, cap violation, divergenza paper-live non alertati.
- **Finding sorgente:** E-09/10/11, M2/M3, F-10.
- **Perché:** il degrado silenzioso è il modo in cui i sistemi di trading falliscono.
- **Priorità:** P0 (alerting safety) / P1 (divergenza). **Dipendenze:** RB-001.
- **Capability:** alerting su soglie per: LLM fallback/PSI/ensemble correlation, staleness dati, worker/beat lag, net-exposure cap violation, divergenza paper↔live.
- **Criteri di accettazione:** (a) ogni soglia critica genera un alert; (b) gli alert sono storicizzati; (c) la divergenza paper-live è misurata e allertata >soglia.
- **Chiedere a Technical Verification:** quali metriche sono già calcolate; dove instradare gli alert.
- **Cosa NON fare:** non lasciare PSI/fallback come semplice classificazione senza azione.

### [RB-014] Secrets & Ops Safety Baseline
- **Categoria:** Ops Safety / Security.
- **Problema:** API key in repo; LLM `--dangerously-skip-permissions` in cron; JWT fallback; docker insicuro; DR assente.
- **Finding sorgente:** F-07/08/09, RT-14, T4/T7.
- **Perché:** sono blocchi funzionali al live tanto quanto un bug di esecuzione.
- **Priorità:** P0. **Dipendenze:** nessuna.
- **Capability:** baseline ops/security: rotazione secret esposti, nessun secret in repo, JWT fail-fast, hardening docker, nessun agente LLM a permessi pieni non sandboxed in cron, DR/backup documentata.
- **Criteri di accettazione:** (a) nessun secret nel repo; (b) JWT obbligatorio (fail-fast); (c) l'agente cron non può compiere azioni distruttive non controllate; (d) esiste e è testata una procedura di backup/restore.
- **Chiedere a Technical Verification:** inventario secret esposti; superfici di azione dell'agente cron.
- **Cosa NON fare:** non rimandare la rotazione della chiave esposta.

### [RB-015] Test & Audit Integrity
- **Categoria:** Auditability.
- **Problema:** 33 test rossi; audit_log morta; roadmap-vs-code drift.
- **Finding sorgente:** E-18, F-11, T6, D-01/02/03.
- **Perché:** test rossi e audit ambiguo rendono inattendibile ogni claim.
- **Priorità:** P0. **Dipendenze:** nessuna (abilita RB-008).
- **Capability:** suite verde come precondizione di fiducia; catena di audit documentata e completa; consistenza roadmap↔codice verificata.
- **Criteri di accettazione:** (a) suite verde e deterministica; (b) catena di audit ufficiale documentata (audit_log chiarita); (c) un drift roadmap↔codice è rilevato automaticamente.
- **Chiedere a Technical Verification:** causa dei 33 rossi; cosa serve per il determinismo.
- **Cosa NON fare:** non costruire altro sopra una suite rossa.

### [RB-016] Schedule / Calendar Truthfulness
- **Categoria:** Execution Safety / Product Truthfulness.
- **Problema:** calendario fail-open; DST drift; schedule mirror divergente.
- **Finding sorgente:** RT-9/10, D-08, R6, E-04/05.
- **Perché:** ordini a mercato chiuso e schedule falsi sono rischi operativi diretti.
- **Priorità:** P0. **Dipendenze:** nessuna.
- **Capability:** calendario di mercato fail-closed; schedule derivato dalla fonte reale; gestione DST/mezze sedute.
- **Criteri di accettazione:** (a) su fail del clock il sistema non tradisce; (b) lo schedule mostrato è quello reale; (c) le transizioni DST non sfasano il trading dalla sessione.
- **Chiedere a Technical Verification:** dove rendere fail-closed; come derivare lo schedule dal beat.
- **Cosa NON fare:** non lasciare "proceeds anyway" su fail del clock.

---

## 9. Roadmap by Phase

### Phase 0 — Stop worsening the system
- **Obiettivo:** smettere di aumentare il rischio finché i P0 non sono compresi.
- **Include:** congelare promozioni e tuning; **ridurre/azzerare l'esposizione reale di S1** fino alla Phase 2; rotazione immediata della API key esposta; **disabilitare/sandboxare** l'agente LLM cron a permessi pieni; marcare S7/PEAD come R&D e toglierlo dalla superficie operativa; congelare i config change pericolosi.
- **Esclude:** qualsiasi nuova feature, nuovo alpha, ottimizzazione.
- **Prerequisiti:** nessuno (è la prima azione).
- **Output atteso:** sistema in stato "supervised paper", secret ruotati, nessuna nuova esposizione.
- **Completamento:** S1 non più a 50% live; secret ruotati; agente cron neutralizzato; PEAD non più presentato come attivo.
- **Rischi se saltata:** si continua a esporre capitale reale su una safety inesistente — il rischio più grave.

### Phase 1 — Establish truth
- **Obiettivo:** una source of truth per stato strategie, gate, config, allocazioni, modo, readiness.
- **Include:** RB-001, RB-015 (test verdi + audit chiarito), RB-008 (manifest riproducibilità), riconciliazione roadmap/config/docstring.
- **Esclude:** modifiche al comportamento di esecuzione (Phase 2) e alla UI ricca (Phase 4).
- **Prerequisiti:** Phase 0.
- **Output atteso:** il sistema sa dire la verità su sé stesso; ogni claim è riproducibile.
- **Completamento:** nessuna contraddizione di stato; suite verde deterministica; manifest presente.
- **Rischi se saltata:** ogni fix successivo poggia su uno stato non verificabile.

### Phase 2 — Restore safety
- **Obiettivo:** execution safety e risk control reali.
- **Include:** RB-003 (paper/live esplicito), RB-004 (stop-loss/pending/partial/duplicate), RB-005 (kill-switch governance), RB-006 (regime applicato, vol-targeter ordering, net-cap), RB-007 (config validation), RB-016 (calendario fail-closed), RB-013 (alerting safety), RB-014 (ops baseline residuo).
- **Esclude:** validità statistica dell'alpha (Phase 3 + Passata 2).
- **Prerequisiti:** Phase 1.
- **Output atteso:** un path di esecuzione che non può ferire silenziosamente.
- **Completamento:** drill superati (gap-down chiude posizione; halt mid-cycle ferma ordini; cap mai violato; fail-closed).
- **Rischi se saltata:** il live resta impossibile; il paper resta non rappresentativo.

### Phase 3 — Restore validation credibility
- **Obiettivo:** validazione riproducibile e onesta nel design (governance).
- **Include:** RB-009 (gate lifecycle), RB-010 (no-lookahead/t+1/cost-aware/survivorship-free, kill-switch modellato).
- **Esclude:** il verdetto statistico puntuale (se l'alpha *esiste*) → **Passata 2 — Quant Validity Memo**.
- **Prerequisiti:** Phase 1 (manifest), Phase 2 (per modellare i risk control nel backtest).
- **Output atteso:** gate eseguibili, riproducibili, onesti nel design; risultati net-of-cost e t+1.
- **Completamento:** no-lookahead test fallisce con segnale futuro; gate report rieseguibili; risultati etichettati per realismo.
- **Rischi se saltata:** si promuove su numeri che misurano un mondo non tradable.

### Phase 4 — Product cockpit truthfulness
- **Obiettivo:** dashboard che mostra la verità operativa.
- **Include:** RB-012 (cockpit), RB-002 (promotion readiness gate + dashboard), RB-013 (divergenza paper-live), completamento RB-006/UI.
- **Esclude:** nuove pagine non legate alla verità/safety.
- **Prerequisiti:** Phase 1 (SoT), Phase 2 (risk control reali).
- **Output atteso:** l'operatore vede stato reale, readiness, why-trade, stale data, paper≠live.
- **Completamento:** nessun elemento UI mostra capability inattive; readiness visibile per ogni strategia.
- **Rischi se saltata:** falsa sicurezza residua anche con backend corretto.

### Phase 5 — Strategy requalification
- **Obiettivo:** riclassificare S1/S4/S3/S7/S2 dopo safety + quant memo.
- **Include:** applicazione del Promotion Readiness Gate a ciascuna strategia, integrando i verdetti della Passata 2.
- **Esclude:** nuovo alpha.
- **Prerequisiti:** Phase 2, Phase 3, **Passata 2 completata**.
- **Output atteso:** stati lifecycle aggiornati e difendibili.
- **Completamento:** ogni strategia ha uno stato giustificato da gate riproducibili + quant memo.
- **Rischi se saltata:** si resta con stati arbitrari.

### Phase 6 — R&D and alpha expansion
- **Obiettivo:** nuovi alpha solo dopo safety/validation/governance.
- **Include:** N1–N4 e le estensioni, ciascuna con i 5 gate onesti e containment R&D.
- **Esclude:** qualsiasi promozione che salti le fasi precedenti.
- **Prerequisiti:** Phase 1–5.
- **Output atteso:** pipeline di ricerca disciplinata.
- **Completamento:** un nuovo alpha può entrare solo passando il Promotion Readiness Gate.
- **Rischi se saltata:** si costruiscono nuove strategie su una base che non valida.

---

## 10. Go/No-Go Recommendation

**Raccomandazione netta:** **NO-GO al live. NO-GO al paper "decisionale" finché Phase 1–2 non sono chiuse.** S1 va **demosso da live a supervised paper immediatamente** (Phase 0). Nessuna promozione finché esiste il Promotion Readiness Gate (RB-002) e la safety è ripristinata (Phase 2).

| Capability / Strategy | Stato consigliato | Motivo | Condizione per avanzare |
|---|---|---|---|
| **S1** | **Supervised Paper** (demozione da live) | Validazione non riproducibile/onesta; no stop-loss live; no de-risking | Phase 2 (safety) + Passata 2 (quant) + Promotion Gate |
| **S2** | Disabled / R&D | OOS −0.55; nota config errata | Diagnosi del bias (Passata 2) + truth fix |
| **S3** | R&D only (disabled) | Sospetto lookahead; survivorship | Falsificazione lookahead (Passata 2) + PIT |
| **S4** | Paper contenuto — promozione bloccata | Gate inottenibile; RAG/supervisor non verificati; cap soft | RB-009 + RAG/supervisor verificati + IC net-of-cost |
| **S7 / PEAD** | R&D only + **fuori dalla UI** | Orfano end-to-end; esposto come prodotto | RB-011 + consensus esterno + pipeline + 5 gate |
| **Live execution path** | **Bloccato** | No stop-loss, kill-switch race, calendario fail-open, duplicate-BUY | RB-004/005/016 + drill superati |
| **Config UI (slider risk)** | **Bloccato/clampato** | Disabilita risk control senza audit | RB-007 |
| **Regime de-risking** | Da cablare (o dichiarare off in UI) | Calcolato ma non applicato | RB-006 + moltiplicatori pre-specificati (Passata 2) |
| **Promozione (qualsiasi)** | **Congelata** | Manca il gate di readiness | RB-002 attivo |
| **Nuovo alpha (N1–N4)** | Rinviato | Safety/validation non pronte | Phase 6 |
| **Cron LLM full-perms** | **Disabilitato/sandbox** | Azioni distruttive autonome | RB-014 |

**Cosa serve prima di usare capitale reale (non negoziabile):** SoT veritiera (RB-001), suite verde + riproducibilità (RB-015/008), stop-loss e kill-switch verificati e2e (RB-004/005), calendario fail-closed (RB-016), config non smontabile via UI (RB-007), secret ruotati (RB-014), validazione t+1/cost-aware/survivorship-free riproducibile (RB-010), e verdetto positivo della Passata 2 sull'alpha.

---

## 11. What To Ask The Quant Validity Memo Next (Passata 2)

1. **La validazione di S1 regge con esecuzione t+1** (fill a open[t+1] + gap) invece di same-bar? Qual è il "costo di realismo" sullo Sharpe?
2. **Quali risultati invalida lo same-bar execution** (RT-1)? Lo Sharpe 0.51 è interamente artefatto del fill alla stessa barra?
3. **I gate 3 (robustness) e 5 (stress) sono statisticamente validi?** La grid `max_sharpe` senza correzione multipla (White/Hansen SPA) e lo stress "dentro l'OOS" certificano qualcosa?
4. **Il gate 1 (DSR) con `n_trials=1` su 40 combo + 7 strategie ha significato?** Con correzione multipla, lo Sharpe sopravvive?
5. **Il gate 2 regge sul denominatore raw** (25 finestre, no-trade incluse) o passa solo per artefatto (0.48→0.75)?
6. **S1 sopravvive a un universo survivorship-free PIT** (`active_at`, delisting) + **raw close + dividendi espliciti** + **costi reali (ADV) + fixed cost 1440**?
7. **Quanto OOS è economicamente significativo?** Quanti anni e quanti *veri* bear regime (non flash 2020)? Lo stress 2008 è testabile se i segnali iniziano ~2011?
8. **S4 ha edge o è rumore LLM?** IC vs forward returns net-of-cost; l'ensemble è realmente diversificato (correlazione tra modelli) o un modello solo?
9. **S3 e S7 sono probabili falsi alpha?** Il lookahead di sizing di S3 è l'alpha? PEAD regge fuori da survivorship/microstruttura?
10. **Costi/slippage/liquidità cambiano il verdetto** su S1/S4 (alpha "thin" eroso dai costi)?
11. **I moltiplicatori regime (1.0/0.7/0.4/0.2)** sono validabili OOS pre-specificati, o tararli è data mining del risk control?
12. **Quali strategie vanno falsificate** (non solo "validate") prima di qualsiasi avanzamento di stato? Quali soglie di **demozione** (decay/divergenza)?

---

## 12. What To Ask The Technical Verification Next (Passata 3 — Kimi)

1. **Dove implementare la Source of Truth** (RB-001): qual è oggi lo store autorevole dello stato strategie? Tabella DB vs YAML generato? Dove le superfici (UI/report) leggono lo stato?
2. **Quali risk control sono solo UI vs realmente runtime?** Confermare: regime `=1.0` hardcoded (`portfolio_scheduler.py:543,626`); vol targeter post-constraint (`orchestrator.py:220-223`); combiner additivo senza net-cap (`orchestrator.py:135`); regime mostrato in `Performance.tsx` non applicato.
3. **Quali config change non sono validati/auditati?** `update_config` (`config_routes.py:29-44`) deep-merge senza bound; quali chiavi sono "dangerous"; dove inserire schema/bound/audit.
4. **Dove mancano idempotenza e audit?** Duplicate-BUY da ordini pending (no `get_orders(OPEN)`); kill-switch race (re-check assente prima di `submit_order`); config/halt non auditati; `audit_log` morta vs catena reale.
5. **Lo stop-loss è realmente cablato nel path portfolio?** `execution.py` morto? bracket `ALPACA_BRACKET_ENABLED` off? esiste uno stop software sul path attivo?
6. **Il kill-switch è fail-closed e ricontrollato prima di ogni submit?** Dove persistere lo stato e auditare halt/recovery.
7. **Il calendario è fail-closed?** `get_clock` fail-open (`portfolio_scheduler.py:260-261`); come derivare lo schedule reale dal beat (no mirror `system_routes.py`).
8. **Paper/live:** dove vive la decisione (substring URL); quali path la leggono; come renderla esplicita e auditata.
9. **LLM in hot path:** riconfermare l'assenza di chiamate sincrone in esecuzione (vincolo preservato).
10. **Test:** causa dei 33 rossi (rotazione A-05/A-08; pytest-asyncio); cosa serve per verde + determinismo (seed pinning).
11. **Riproducibilità:** dove pinnare data/modello/seed; come confrontare un backtest di riferimento in CI.
12. **Per ogni RB-XXX:** quali test (unit/integration/drill) servono come criterio di accettazione tecnico (es. gap-down→close; halt mid-cycle→no orders; cap mai violato; segnale futuro→backtest fallisce).
13. **Ops/security:** inventario secret esposti (`daily_analysis.sh:51`, `docker-compose.yml`); superfici di azione dell'agente cron `--dangerously-skip-permissions`; JWT fail-fast.

---

## 13. What Not To Do

- **Non fare parameter tuning** (lookback, soglie, moltiplicatori) come remediation: maschera i problemi di safety/validazione e introduce overfit.
- **Non promuovere S4** finché il gate report non è eseguibile/riproducibile e RAG/supervisor non sono verificati.
- **Non riabilitare S7/PEAD** né lasciarlo nella superficie operativa: è R&D orfano.
- **Non usare backtest non riproducibili / same-bar / adjusted-close / survivorship** per nessuna decisione di promozione.
- **Non trattare l'UI come fonte di verità** né lasciarla mostrare risk control inattivi o disabilitarli senza audit.
- **Non fare fix casuali senza test** su una suite già rossa: prima il verde, poi i fix con regressione.
- **Non mischiare R&D e operativo** (consumer cablati, tab "attivi").
- **Non usare codice per compensare governance assente:** la source of truth e i gate sono prerequisiti, non patch.
- **Non implementare nuovi alpha (N1–N4)** prima che safety (Phase 2) e validazione (Phase 3 + Passata 2) siano chiuse.
- **Non lasciare capitale reale su S1** durante la remediation.
- **Non considerare "esistente" una capability che è in codice morto/disattivato** (stop-loss, enforcement allocazioni).
- **Non tarare i moltiplicatori regime sul drawdown storico** (overfit del risk control).
- **Non eseguire lo script gate "così com'è"** senza prima validare il design del gate (rimando Passata 2).

---

## 14. Final Recommendation

**Prossimi 7 giorni (Phase 0 — Stop worsening):**
1. **Ridurre/azzerare l'esposizione reale di S1** (da live 50% a supervised paper). Questa è l'azione di rischio numero uno.
2. **Ruotare immediatamente la API key esposta** e tutti i secret nel repo/compose (RB-014, parziale).
3. **Disabilitare o sandboxare** l'agente LLM cron a permessi pieni.
4. **Togliere S7/PEAD dalla superficie operativa** (disclaimer R&D / nascondere il tab) e de-flaggarlo in roadmap.
5. **Congelare** promozioni, tuning e config change pericolosi (clamp/blocco temporaneo degli slider di rischio).

**Prossimi 30 giorni (Phase 1 → Phase 2):**
1. **Phase 1 — Truth:** Strategy Status Source of Truth (RB-001); suite test verde + audit chain documentata (RB-015); manifest di riproducibilità (RB-008); riconciliare roadmap/config/docstring.
2. **Phase 2 — Safety:** paper/live esplicito (RB-003); execution safety baseline — stop-loss, pending, partial, duplicate-BUY (RB-004); kill-switch governance (RB-005); risk control reali — regime, vol-targeter ordering, net-cap (RB-006); config validation + UI bounds + audit (RB-007); calendario fail-closed (RB-016); alerting safety (RB-013).

**Da rimandare (dopo i 30 giorni):**
- Phase 3 (validation credibility, in parallelo con Passata 2), Phase 4 (cockpit), Phase 5 (riqualificazione strategie), Phase 6 (nuovo alpha). Nessun nuovo alpha prima della Phase 6.

**Documento da produrre dopo questo:**
- **Passata 2 — `OPUS_QUANT_TRADING_VALIDITY_MEMO`**: rispondere alle 12 domande della §11 (in particolare: S1 regge a t+1 + survivorship-free + correzione multipla? S4 ha edge? S3/S7 sono falsi alpha?).
- A seguire: **Passata 3 — Kimi Technical Verification Matrix** (§12), poi **Passata 4 — Review della code review**, poi **Master Plan finale**.

---

*Fine OPUS_FUNCTIONAL_REMEDIATION_BLUEPRINT (Passata 1/5). Modalità read-only rispettata: nessun file di sistema modificato, nessun codice/patch/commit, nessuna pipeline/worker/ordine eseguito. Le verifiche tecniche sono in §12, quelle quant in §11. Priorità a safety, auditabilità, riproducibilità, governance e verità funzionale.*
