# ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18

> **Passata 5 di 5** — Master Plan operativo. Fonte unica per decidere cosa fare, cosa non fare, in che ordine, con quali test e gate.
> Ruolo: Principal Program Architect + Chief Risk Officer + Head of Quant Research + Product Safety Owner + Engineering PM + Governance Owner.
> Modalità: **read-only**. Nessun codice/patch/commit; nessun worker/pipeline/ordine/broker eseguito. Questo documento **non autorizza** implementazioni: apre il lavoro a ticket.
> Sintesi di: Functional/Quant/Product Review (2026-06-17), Functional Remediation Blueprint (P1), Quant Trading Validity Memo (P2), Kimi Technical Verification Matrix (P3), Opus Review-of-Kimi (P4).
> Tassonomia RB **canonica** = quella del Functional Remediation Blueprint (la re-numerazione di Kimi RB-007..014 è scartata, come stabilito in P4).
> Data: 2026-06-18.

---

## 1. Executive Summary

Alembic ha uno **scheletro architetturale valido** (LLM mai nel hot path, catena di audit di esecuzione reale, frontend tipizzato, componenti di risk presenti) ma è **operato sopra la sua classe di maturità**: S1 è **live al 50% di capitale reale** su una validazione che, verificata nel codice da tre passate indipendenti, **non valida** (same-bar fill, survivorship, costi ≈0, DSR `n_trials=1`, stress circolare, regime hindsight, walk-forward decorativo). In più, il path live **non ha stop-loss funzionante**, il **kill-switch ha una race window** ed è revocabile con una sola API key, il **regime detector è hardcoded a 1.0**, gli slider UI **smontano i risk control senza audit**, una **API key è in chiaro** in uno script cron che lancia un agente LLM a permessi pieni, e il backtest **non è riproducibile** (33→109 test non verdi).

Non esiste una **source of truth**: roadmap, `strategies.yaml`, docstring e UI si contraddicono. Le cinque passate convergono: la priorità non è nuovo alpha, è (0) smettere di peggiorare e ridurre l'esposizione reale, (1) ripristinare execution safety e security, (2) rendere onesta e riproducibile la validazione, (3) costruire source-of-truth e cockpit veritiero, (4) riqualificare le strategie, (5) paper controllato 90gg, (6) riconsiderare il live.

**Verdetto: Research-grade (scheletro), early-paper, attualmente mis-operato come Live. NON live-ready, NON paper-ready come oggi governato.** Azione immediata: freeze, demuovere S1 da live, ruotare i secret, contenere S7. Nessuna promozione e nessun nuovo alpha finché i P0 non sono chiusi.

---

## 2. Final System Verdict

**RESEARCH-GRADE (scheletro) / EARLY PAPER-READY — operato impropriamente come Live.**

- *Sopra "Prototype"*: paradigma Alpha Miner rispettato, audit chain forte, UI strutturata, componenti di risk esistenti. C'è un'ossatura su cui costruire.
- *Non "Paper-ready" (come oggi governato)*: un paper è affidabile solo se lo stato è veritiero, i risk control dichiarati sono applicati, la config non è alterabile senza audit e la divergenza paper↔live è misurata. Nessuna condizione è soddisfatta → il paper attuale produce P&L rumoroso, non evidenza decisionale.
- *Emphatically non "Live-ready"*: nessuno stop-loss live, kill-switch race+revocabile, regime non applicato, calendario fail-open, duplicate-BUY, validazione non riproducibile né onesta.
- *Mis-operato come Live*: è il fatto di governance più grave — capitale reale è esposto **ora** su basi che non lo giustificano.

Classe-obiettivo a 30 giorni: **Supervised Paper** (paper reso veritiero), non live.

---

## 3. Operating Policy Effective Immediately

**FREEZE (in vigore da subito, fino a chiusura dei P0 di safety):**
- **No nuovo capitale reale.** **Demuovere S1 da live** a supervised paper (atto di governance esplicito, non solo disable engine).
- **No promozioni** di alcuna strategia; **no parameter tuning**; **no nuovo alpha**.
- **Congelare i config change pericolosi** (clamp/blocco degli slider di rischio finché non c'è validazione server-side).
- **No claim di "backtest validato"** finché la validazione non è riproducibile e onesta.

**Bloccare:**
- Engine di esecuzione in modalità live (`run-execution` e `portfolio-cycle`) finché Phase 1 non è completa.
- Modifiche dirette a `config/strategies.yaml` senza PR + review.
- L'agente LLM cron `--dangerously-skip-permissions` (disabilitare o sandboxare).

**Resta permesso:**
- Paper trading **osservativo** (con la consapevolezza che non è validazione) una volta abilitato lo stop-loss (`ALPACA_BRACKET_ENABLED=true`) e con kill-switch manuale documentato.
- Sviluppo dei fix di remediation con test-before-fix.
- Ricerca/backtest R&D **etichettati** e separati dall'operativo.

**Richiede approvazione del Project Owner (vedi §13):**
- Qualsiasi ritorno a live; rotazione credenziali; capitale massimo durante remediation; scelta data provider/ADV; provider consensus EPS; meccanismo 2FA kill-switch.

---

## 4. Final Priority Model

- **P0 — Freeze / Safety / Capital Protection.** Da chiudere prima di qualunque live o aumento capitale. Può richiedere freeze operativo.
- **P1 — Validation / Governance / Observability.** Da chiudere prima di promuovere strategie o fidarsi dei risultati.
- **P2 — Product / Process / Hardening.** Importante, non blocca la safety immediata.
- **P3 — R&D / Future Alpha / Cleanup.** Solo dopo P0/P1.

Regola trasversale: per ogni item quant esiste una **distinzione fix vs decisione** — il *fix codice* può essere P1, ma la *decisione di non promuovere / demuovere* è P0 quando c'è capitale reale.

---

## 5. Workstream Master Plan

### WS-00 — Operational Freeze and Safety Policy
- **Priorità:** P0
- **Obiettivo:** smettere di peggiorare; ridurre l'esposizione reale durante la remediation.
- **Problema risolto:** capitale reale su sistema research-grade; promozioni/tuning che aggiungono rischio.
- **Sorgente:** P1 Phase 0; P2 §13; P4 §15.
- **Capability:** policy di freeze auditata + stato "supervised paper".
- **Scope incluso:** demozione S1; stop promozioni/tuning/alpha; lock config; runbook kill manuale.
- **Scope escluso:** fix tecnici (altri WS).
- **Dipendenze:** nessuna (prima azione).
- **Ticket inclusi:** demote-S1-live; freeze-promotions; lock-strategies-yaml; manual-killswitch-runbook.
- **Test prima:** n/a (policy); verificare che gli engine live siano effettivamente disattivati.
- **Test/regressioni dopo:** check che nessun ordine live parta finché Phase 1 incompleta.
- **Acceptance:** S1 non più live 50%; engine live off; promozioni bloccate; documento di freeze firmato.
- **Owner:** Product/Risk.
- **Rischi se fatto male:** freeze parziale che lascia un path live attivo.
- **Cosa NON fare:** non lasciare S1 a capitale reale "in attesa".
- **Chiusura:** policy attiva e verificata.

### WS-01 — Secrets and Immediate Security
- **Priorità:** P0
- **Obiettivo:** eliminare leak credenziali e azioni autonome non controllate.
- **Problema risolto:** API key in chiaro (`scripts/daily_analysis.sh:51`); LLM cron full-perms; JWT fallback efimero.
- **Sorgente:** Review F-07/F-08; P1 RB-014; P3 §11; P4.
- **Capability:** Secrets & Ops Safety Baseline (no secret in repo, JWT fail-fast, cron sandbox).
- **Scope incluso:** rotazione di tutti i secret esposti; spostamento in `.env` gitignored; pre-commit/CI secret scan; neutralizzare/sandbox agente cron; JWT obbligatorio fail-fast.
- **Scope escluso:** docker hardening completo (WS-14).
- **Dipendenze:** nessuna.
- **Ticket:** rotate-api-key; remove-secret-from-repo; jwt-failfast; cron-llm-sandbox; secret-scan-ci.
- **Test prima:** `test_no_default_api_key`; `test_no_hardcoded_api_key_in_scripts`.
- **Dopo:** secret scan in CI verde; JWT senza fallback.
- **Acceptance:** nessun secret nel repo; JWT fail-fast; cron non può compiere azioni distruttive.
- **Owner:** DevOps/Security.
- **Rischi se fatto male:** rotazione parziale; chiave vecchia ancora valida.
- **Cosa NON fare:** non rimandare la rotazione "dopo".
- **Chiusura:** secret ruotati + scan attivo.

### WS-02 — Paper/Live Explicit Mode and Strategy Source of Truth
- **Priorità:** P0 (paper/live) + P1 (SoT)
- **Obiettivo:** un'unica verità per modo e stato strategie; passaggio live esplicito.
- **Problema risolto:** modo dedotto da substring URL (dual-source); roadmap/config/docstring/UI contraddittori; `_validate_allocations` solo warning; S3/S7 non registrati.
- **Sorgente:** Review D-01/D-04/D-05/F-14; P1 RB-001/RB-003; P2; P3 §8; P4.
- **Capability:** Strategy Status SoT + Explicit Paper/Live Mode.
- **Scope incluso:** tabella `strategy_lifecycle` (strategy_id, mode, target_mode, gate_report_id, promoted_by, promoted_at, approved); registry legge da DB (YAML bootstrap); modo paper/live esplicito a fonte unica con conferma+audit; enforcement hard delle allocazioni; UI e report derivano dalla SoT.
- **Scope escluso:** promotion gate (WS-15); cockpit (WS-10).
- **Dipendenze:** WS-13 (audit_log/test) utile in parallelo.
- **Ticket:** strategy-lifecycle-table; registry-read-db; paper-live-single-source; validate-allocations-raise; reconcile-status-sources.
- **Test prima:** `test_registry_enforces_mode_from_yaml`; `test_validate_allocations_raises_on_over_allocation`; `test_paper_live_mode_single_source_of_truth`.
- **Dopo:** nessuna contraddizione di stato tra fonti.
- **Acceptance:** un solo posto definisce stato/modo; passaggio live richiede conferma elevata+audit; over-allocation solleva.
- **Owner:** Backend + Product/Risk.
- **Rischi se fatto male:** ennesimo YAML scritto a mano = altra fonte divergente.
- **Cosa NON fare:** non risolvere con un nuovo file di stato manuale.
- **Chiusura:** SoT in DB, derivata ovunque, modo esplicito.

### WS-03 — Execution Safety Contract
- **Priorità:** P0
- **Obiettivo:** nessun ordine reale senza protezione downside e gestione corretta di pending/partial.
- **Problema risolto:** stop-loss live inesistente (legacy morto + bracket off); duplicate-BUY (no pending check); partial fill batch-only; due execution path con safety diverse.
- **Sorgente:** Review F-12/E-06/E-07; P1 RB-004; P2 §4.7; P3 §7/§9; P4.
- **Capability:** Execution Safety Baseline (fail-closed).
- **Scope incluso:** stop-loss/bracket attivo e verificato e2e su ogni nuovo BUY; pending-order check anti duplicate-BUY; gestione partial fill/reject prima del ciclo successivo; unificare o ritirare esplicitamente il path legacy.
- **Scope escluso:** kill-switch (WS-04); calendario (in WS-04/WS-03 confine: calendario fail-closed qui).
- **Dipendenze:** WS-02 (paper/live esplicito).
- **Ticket:** stop-loss-fail-closed; pending-order-guard; partial-fill-handling; unify-execution-paths; market-calendar-fail-closed.
- **Test prima:** `test_new_buy_always_has_stop_loss`; `test_portfolio_scheduler_skips_duplicate_buy_when_pending`; `test_market_clock_failure_aborts_cycle`.
- **Dopo:** drill gap-down → posizione chiusa; pending → nessun duplicato; clock fail → no ordini.
- **Acceptance:** nessun path live attivo senza i tre controlli; calendario fail-closed.
- **Owner:** Backend + Product/Risk.
- **Rischi se fatto male:** stop "presente" ma in codice morto/disattivato.
- **Cosa NON fare:** non considerare esistente uno stop in `execution.py` legacy disattivato.
- **Chiusura:** drill e2e superati.

### WS-04 — Kill-Switch and Halt Governance
- **Priorità:** P0
- **Obiettivo:** safety net senza finestre inattive né vie di fuga facili.
- **Problema risolto:** check una volta a inizio ciclo, mai prima di `submit_order`; recovery auto-on-drawdown; revoca con sola API key.
- **Sorgente:** Review RT-8; P1 RB-005; P3 §7; P4.
- **Capability:** Kill-Switch Governance (fail-closed, re-check, human-gated, 2FA).
- **Scope incluso:** re-check killswitch prima di ogni submit; recovery human-gated (no auto); 2FA/cooldown sulla revoca; audit dell'evento halt/recovery.
- **Scope escluso:** meccanismo 2FA specifico = decisione PO (§13).
- **Dipendenze:** WS-02 (audit), WS-13.
- **Ticket:** killswitch-recheck-presubmit; killswitch-human-recovery; killswitch-2fa-cooldown; killswitch-audit.
- **Test prima:** `test_kill_switch_prevents_order_submission`; `test_killswitch_recovery_requires_human`.
- **Dopo:** drill halt mid-cycle → ordini non partono.
- **Acceptance:** halt mid-cycle ferma il ciclo; recovery solo umana; revoca con 2FA; tutto auditato.
- **Owner:** Backend + Product/Risk.
- **Rischi se fatto male:** re-check parziale che lascia una finestra.
- **Cosa NON fare:** non lasciare la recovery automatica come unico meccanismo.
- **Chiusura:** drill superato + audit attivo.

### WS-05 — Config Validation and Audit Workflow
- **Priorità:** P0
- **Obiettivo:** i risk control non devono essere disabilitabili senza controllo.
- **Problema risolto:** `update_config` deep-merge senza validazione/bound; slider UI fino a drawdown 20%/stop 50%; nessun audit.
- **Sorgente:** Review RT-7; P1 RB-007 (canonico); P3 §11.C; P4.
- **Capability:** Validated Config Change Workflow.
- **Scope incluso:** schema + bound server-side; clamp frontend ai limiti reali; audit di ogni change (chi/quando/da→a); indebolimento di un risk control richiede approvazione elevata.
- **Scope escluso:** cockpit (WS-10).
- **Dipendenze:** WS-13 (audit_log).
- **Ticket:** config-schema-validation; config-server-bounds; config-change-audit; ui-bounded-inputs.
- **Test prima:** `test_config_rejects_out_of_bound`; `test_config_change_writes_audit`; `test_ui_inputs_clamped`.
- **Dopo:** impossibile portare drawdown cap/stop oltre i limiti via UI.
- **Acceptance:** valori fuori bound rifiutati lato server; ogni change auditato.
- **Owner:** Backend + Frontend.
- **Rischi se fatto male:** bound solo lato frontend (bypassabili via API).
- **Cosa NON fare:** non affidare i bound solo all'UI.
- **Chiusura:** validazione+audit attivi e testati.

### WS-06 — Backtest Timing and Lookahead Remediation
- **Priorità:** P1 (fix) / P0 (decisione: nessuna promozione su numeri same-bar)
- **Obiettivo:** rendere il backtest implementabile e privo di lookahead.
- **Problema risolto:** same-bar fill; S3 lookahead full-sample sizing; S1 stress/regime circolari (hindsight); walk-forward decorativo; Adj Close come fill.
- **Sorgente:** P2 §4.1-4.4; P3 §10; P4 §7.
- **Capability:** No-lookahead / t+1 execution policy (parte di Backtest↔Live Parity).
- **Scope incluso:** fill a t+1 (open[t+1]) + gap; S3 vol PIT (expanding/rolling causale); stress storico reale (2008/2020/2022) o "non testabile"; regime split causale; raw close + dividendi espliciti; walk-forward con fitting reale su IS.
- **Scope escluso:** validità statistica puntuale → esperimenti quant (§15).
- **Dipendenze:** WS-08 (reproducibility), WS-13 (test verdi).
- **Ticket:** t1-fill-gap; s3-pit-vol; s1-real-stress; s1-causal-regime; raw-close-dividends; wf-is-fitting.
- **Test prima:** `test_orchestrator_uses_t_plus_1_fill`; `test_s3_uses_expanding_window_vol`; `test_stress_period_independent`; `test_regime_labels_point_in_time`; `test_injected_future_signal_fails_backtest`.
- **Dopo:** un segnale futuro fa fallire il backtest (no-lookahead test).
- **Acceptance:** decisione e fill su barre distinte; nessun input full-sample/hindsight nei gate.
- **Owner:** Quant + Backend.
- **Rischi se fatto male:** "riparare lo script" lasciando il design contaminato.
- **Cosa NON fare:** non promuovere su risultati same-bar; non tarare parametri.
- **Chiusura:** no-lookahead test verde + WS-06 fix mergeati.

### WS-07 — Cost Model and Paper/Live Realism
- **Priorità:** P1
- **Obiettivo:** net-Sharpe onesto e parità BT↔live.
- **Problema risolto:** ADV default 10M shares / 20B USD → impatto ≈0; fixed cost $1440/anno escluso; cost model non usato nel sizing live; kill-switch non modellato nel backtest.
- **Sorgente:** P2 §4.6; P3 Q3/Q9; P4 §7.
- **Capability:** Backtest↔Live Parity Governance (lato costi).
- **Scope incluso:** ADV storico reale nel cost model; fixed cost nel net-Sharpe; cost-aware sizing nel path live; kill-switch modellato nel backtest o risultati etichettati "pre-risk-control".
- **Scope escluso:** metrica divergenza paper-live runtime (WS-10, NEEDS_RUNTIME_DATA).
- **Dipendenze:** WS-06.
- **Ticket:** real-adv-cost; fixed-cost-net-sharpe; cost-aware-sizing; backtest-killswitch-model.
- **Test prima:** `test_cost_model_uses_real_adv`; `test_fixed_cost_in_net_sharpe`; `test_cost_model_used_in_portfolio_sizing`.
- **Dopo:** confronto Sharpe lordo vs net documentato.
- **Acceptance:** net-Sharpe include costi reali + fisso; sizing cost-aware.
- **Owner:** Quant + Backend.
- **Rischi se fatto male:** ADV grezzo che sovrastima i costi.
- **Cosa NON fare:** non ignorare il fisso su conto piccolo.
- **Chiusura:** net-Sharpe onesto prodotto.

### WS-08 — Validation Gates and Reproducibility
- **Priorità:** P0 (reproducibility) / P1 (gate lifecycle)
- **Obiettivo:** validazione riproducibile e gate onesti nel design.
- **Problema risolto:** `n_trials=1` (no correzione multipla); Gate 2 denominatore esclude no-trade; Gate 4 clamp 3→2; Gate 3 (CV su 3 perturbazioni, no SPA); S4 gate script rotto (D-02); no pin data/modello/seed.
- **Sorgente:** Review D-02; P2 §5; P3 §10; P4 §7 (Gate 3 non verificato; reproducibility elevata).
- **Capability:** Reproducible Validation Manifest + Gate Report Lifecycle.
- **Scope incluso:** manifest (hash dati, versione modello, seed); re-run deterministico + CI di confronto; gate report eseguibili/riproducibili/datati (rotto ⇒ promozione bloccata per definizione); fix gate (n_trials, denominatore, clamp) + correzione multipla (White/Hansen SPA) per Gate 3; fix script S4 gate.
- **Scope escluso:** verdetto statistico (esperimenti §15).
- **Dipendenze:** WS-13 (test verdi).
- **Ticket:** reproducibility-manifest; ci-reference-backtest; gate1-n-trials; gate2-denominator; gate4-no-clamp; gate3-spa; s4-gate-script-fix; gate-report-lifecycle.
- **Test prima:** `test_backtest_rerun_deterministic`; `test_gate_1_n_trials_configurable`; `test_gate_2_counts_zero_return_windows`; `test_gate_4_does_not_clamp_threshold`; `test_gate_3_multiple_comparison`.
- **Dopo:** due run su macchine diverse → metriche identiche.
- **Acceptance:** ogni gate report linka un manifest; gate non bypassabili; SPA applicata.
- **Owner:** Quant + Backend + DevOps.
- **Rischi se fatto male:** riparare gli script lasciando input contaminati.
- **Cosa NON fare:** non accettare "near identical" senza tolleranza dichiarata.
- **Chiusura:** manifest + re-run deterministico + gate corretti.

### WS-09 — Portfolio/Risk/Combiner Correctness
- **Priorità:** P1 (P0 per regime hardcoded)
- **Obiettivo:** i risk control sono invarianti, non suggerimenti.
- **Problema risolto:** vol targeter post-constraint (ri-viola cap 50%); combiner additivo senza net-cap né risoluzione conflitti BUY/SELL; **regime_mult=1.0 hardcoded** (P0).
- **Sorgente:** Review F-01/F-02/F-03; P1 RB-006; P3 §9; P4.
- **Capability:** Risk Control Truthfulness (runtime).
- **Scope incluso:** vol targeter pre-constraint (o ri-validazione cap dopo); net-exposure cap + risoluzione conflitti nel combiner; cablare il regime dal detector (con moltiplicatori **pre-specificati**, no overfit) o dichiararlo esplicitamente off in UI.
- **Scope escluso:** validazione OOS dei moltiplicatori regime → esperimento (§15).
- **Dipendenze:** WS-02, WS-10 (verità UI).
- **Ticket:** vol-targeter-preconstraint; combiner-net-cap; combiner-conflict-resolution; wire-regime-multiplier.
- **Test prima:** `test_net_exposure_cap_enforced`; `test_vol_targeter_before_constraints`; `test_regime_multiplier_applied` / `test_regime_not_hardcoded`.
- **Dopo:** cap mai violato post-trasformazione; conflitti risolti deterministicamente.
- **Acceptance:** net-exposure ≤ cap sempre; regime applicato o dichiarato off.
- **Owner:** Quant + Backend.
- **Rischi se fatto male:** moltiplicatori regime tarati sul drawdown storico (overfit del risk control).
- **Cosa NON fare:** non tarare i moltiplicatori sul passato.
- **Chiusura:** cap invariante + regime cablato/dichiarato.

### WS-10 — Product Cockpit Truthfulness
- **Priorità:** P1
- **Obiettivo:** la UI mostra la verità operativa; l'operatore non riceve falsa sicurezza.
- **Problema risolto:** regime finto in UI (fallback backend), PEAD presentato come attivo, schedule mirror divergente, "No data" ambiguo; nessuna promotion-readiness; **nessun cockpit né monitoring** (capability cadute nella matrice Kimi, P4).
- **Sorgente:** Review F-13/E-19/E-20/D-08; P1 RB-012 + RB-013; P3 §11.C; P4 (CRITICAL miss).
- **Capability:** Operator Safety Cockpit + Monitoring & Alerting.
- **Scope incluso:** cockpit che deriva tutto dalla SoT (stato reale strategie/risk control, stale-data flag, readiness, why-trade, banner paper≠live); schedule derivato dal beat; **alerting** su fallback rate/PSI/ensemble correlation/worker-beat lag/cap-violation; metrica divergenza paper↔live (NEEDS_RUNTIME_DATA).
- **Scope escluso:** raccolta dati runtime (§14).
- **Dipendenze:** WS-02 (SoT), WS-09 (risk reali).
- **Ticket:** operator-cockpit; readiness-dashboard; ui-truthfulness; schedule-from-beat; alerting-safety; paper-live-divergence-metric.
- **Test prima:** `test_ui_does_not_show_inactive_as_active`; `test_alert_fires_on_threshold`; `test_schedule_derived_from_beat`.
- **Dopo:** nessun elemento UI mostra capability inattive; alert storicizzati.
- **Acceptance:** cockpit veritiero + alert di safety attivi.
- **Owner:** Frontend + Backend + Data/LLM.
- **Rischi se fatto male:** cockpit che resta una copia divergente.
- **Cosa NON fare:** non trattare l'UI come fonte di verità; non mostrare protezioni inesistenti.
- **Chiusura:** cockpit derivato dalla SoT + alerting live.

### WS-11 — LLM/News/S4 Validation and Containment
- **Priorità:** P1
- **Obiettivo:** stabilire se S4 ha edge prima di qualsiasi promozione; chiudere le lacune pipeline.
- **Problema risolto:** nessuno studio IC; gate report ineseguibile; RAG/supervisor assenti (spec non rispettata); S4 accumula segnali stale (no recency); LOO ICIR non verificato; cap 10% soft.
- **Sorgente:** Review S4; P2 §3-S4/§6; P3 Q2/RB-014; P4 (S4 verdetto ripristinato; LOO ICIR; sanitizer falso-negativo).
- **Capability:** Data/LLM Governance + R&D-leaning containment per S4.
- **Scope incluso:** finestra di recency sui segnali; RAG + supervisor nel path produzione; enforcement hard cap 10%; verifica LOO ICIR (no overlapping/future); dedup news. *Nota:* la **sanitizzazione esiste** (`src/text/sanitizer.py`) — non re-implementare; verificare solo che sia nel path.
- **Scope escluso:** verdetto edge → esperimenti (§15: placebo/IC/decay).
- **Dipendenze:** WS-08 (gate), WS-06 (timing), WS-10 (alerting).
- **Ticket:** s4-signal-recency; rag-supervisor; s4-cap-hard; loo-icir-verify; news-dedup.
- **Test prima:** `test_s4_signal_ttl_filter`; `test_s4_cap_raises_above_10pct`; `test_loo_icir_no_lookahead`.
- **Dopo:** supervisor rejection rate monitorato.
- **Acceptance:** pipeline S4 PIT, recency, RAG/supervisor presenti; LOO ICIR pulito.
- **Owner:** Data/LLM + Quant.
- **Rischi se fatto male:** trattare S4 come quasi-pronto senza IC.
- **Cosa NON fare:** non promuovere S4 senza placebo/IC net (§15); non re-implementare la sanitizzazione esistente.
- **Chiusura:** pipeline contenuta e verificata; promozione resta bloccata fino a §15.

### WS-12 — S7/PEAD R&D Containment
- **Priorità:** P1 (UI/containment) / P3 (sviluppo)
- **Obiettivo:** togliere S7 dalla superficie operativa; non cablarlo.
- **Problema risolto:** roadmap "done" falso; no `__call__`; EDGAR solo metadati; consensus allucinabile; no consumer; **esposto in UI come attivo**. *Correzione a Kimi (P4): contenere, NON cablare.*
- **Sorgente:** Review D-01/F-05/F-06/F-13; P1 RB-011; P2 §3-S7; P4 (RB-011 invertito da Kimi).
- **Capability:** R&D Strategy Containment.
- **Scope incluso:** marcare S7/PEAD "R&D · non in trading" o nasconderlo; de-flaggare in roadmap; nessun consumer cablato; stato R&D esplicito in SoT.
- **Scope escluso:** sviluppo PEAD (P3, richiede consensus EPS PIT esterno).
- **Dipendenze:** WS-02, WS-10.
- **Ticket:** pead-ui-disclaimer; s7-roadmap-deflag; s7-no-consumer; s7-rd-status.
- **Test prima:** `test_s7_not_in_operational_registry`; `test_pead_ui_shows_rd_label`.
- **Dopo:** nessun segnale S7 raggiunge il signal store operativo.
- **Acceptance:** S7 non appare come attivo; contenuto.
- **Owner:** Frontend + Backend + Product.
- **Rischi se fatto male:** cablare S7 (errore di Kimi) portando rumore in operativo.
- **Cosa NON fare:** **non** aggiungere S7 al registry con allocazione.
- **Chiusura:** S7 contenuto e fuori dall'operativo.

### WS-13 — CI/Test Suite/Quality Gates
- **Priorità:** P0 (baseline) / P1 (espansione)
- **Obiettivo:** suite verde come precondizione di fiducia; CI che intercetta regressioni e secret.
- **Problema risolto:** 33→109 test non verdi (discrepanza da risolvere); `pytest-asyncio` non nel dev group; `ib_insync` mancante; audit_log morta; CI minima.
- **Sorgente:** Review F-10/F-11; P1 RB-015; P3 §12; P4 (discrepanza conteggio).
- **Capability:** Test & Audit Integrity.
- **Scope incluso:** fix dependency groups; suite collezionabile e verde + deterministica; audit_log scritta su ogni order/allocation/mode change; CI con mypy + pip-audit + secret scan + coverage; clean run riproducibile per fissare il conteggio reale.
- **Scope escluso:** test specifici dei singoli WS (vivono nei rispettivi WS).
- **Dipendenze:** abilita WS-08 (reproducibility).
- **Ticket:** fix-dep-groups; ib-insync-resolve; green-suite; audit-log-writers; ci-expand; deterministic-seeds.
- **Test prima:** `test_pytest_dependency_groups_consistent`; `test_audit_log_write_on_order_submit`; `test_ci_runs_security_scanner`.
- **Dopo:** CI verde con scan; conteggio test stabile.
- **Acceptance:** suite verde deterministica; audit chain documentata; CI espansa.
- **Owner:** DevOps + Backend.
- **Rischi se fatto male:** costruire sopra una suite rossa.
- **Cosa NON fare:** non disabilitare i test per farli "passare".
- **Chiusura:** suite verde + CI espansa + audit_log viva.

### WS-14 — Ops Hardening and Disaster Recovery
- **Priorità:** P2 (P0 per gli item già in WS-01)
- **Obiettivo:** deployment production-grade + DR.
- **Problema risolto:** docker insicuro (password, Grafana anonimo `alembic123`, no USER non-root, no limits, Redis no appendonly); nessuna DR/backup; reconcile solo batch.
- **Sorgente:** Review F-09; P1 RB-014; P3 §11; P4 (DR low-miss).
- **Capability:** Ops Safety Baseline (residuo) + DR.
- **Scope incluso:** docker hardening; resource limits; healthcheck worker; Redis appendonly; backup PG pianificato e testato (restore drill); reconcile più frequente.
- **Scope escluso:** secret/JWT/cron (WS-01).
- **Dipendenze:** WS-01.
- **Ticket:** docker-hardening; worker-healthcheck; pg-backup-restore; redis-appendonly.
- **Test prima:** restore drill documentato.
- **Dopo:** backup freshness monitorato.
- **Acceptance:** deployment hardened + DR testata.
- **Owner:** DevOps/Security.
- **Rischi se fatto male:** backup mai testato.
- **Cosa NON fare:** non rimandare la DR a dopo il live.
- **Chiusura:** hardening + restore drill superato.

### WS-15 — Strategy Requalification and Promotion Policy
- **Priorità:** P1
- **Obiettivo:** ogni cambio di stato dipende da criteri verificabili.
- **Problema risolto:** promozioni discrezionali; nessun gate di readiness.
- **Sorgente:** P1 RB-002; P2 §8; P4.
- **Capability:** Promotion Readiness Gate.
- **Scope incluso:** gate formale che blocca il cambio stato finché non sono soddisfatti i safeguard (gate riproducibili PASS, N giorni paper, riproducibilità, DR, cap capitale); record di evidenza; riclassificazione di S1/S2/S3/S4/S7 dopo WS-03/06/07/08 + esperimenti §15.
- **Scope escluso:** esecuzione esperimenti (§15).
- **Dipendenze:** WS-02, WS-06, WS-07, WS-08; esperimenti §15.
- **Ticket:** promotion-gate; promotion-evidence-record; requalify-strategies.
- **Test prima:** `test_promotion_requires_gate_report`; `test_promotion_blocked_without_paper_days`.
- **Dopo:** nessun passaggio paper→live senza criteri.
- **Acceptance:** gate non bypassabile; promozioni con evidenza.
- **Owner:** Product/Risk + Quant.
- **Rischi se fatto male:** gate che si può saltare via YAML.
- **Cosa NON fare:** non promuovere alcuna strategia prima che il gate esista.
- **Chiusura:** gate attivo + strategie riclassificate.

### WS-16 — Future R&D Alpha Program
- **Priorità:** P3
- **Obiettivo:** nuovi alpha solo dopo safety/validation/governance.
- **Problema risolto:** rischio di costruire alpha su validazione che non valida.
- **Sorgente:** Review FASE 6; P2 §6; P1 Phase 6.
- **Capability:** pipeline di ricerca disciplinata (5 gate onesti + containment).
- **Scope incluso:** N1–N4 e estensioni, ciascuno con manifest, gate onesti, falsification.
- **Scope escluso:** tutto finché Phase 0–4 non sono chiuse.
- **Dipendenze:** WS-06/07/08/15.
- **Ticket:** (nessuno ora) — backlog.
- **Test prima:** n/a.
- **Acceptance:** un nuovo alpha entra solo passando il Promotion Gate.
- **Owner:** Quant.
- **Rischi se fatto male:** nuovo alpha prima della safety.
- **Cosa NON fare:** non iniziare prima di Phase 4.
- **Chiusura:** n/a (programma continuativo).

---

## 6. Final P0 List

| ID | Titolo | WS | Motivo | Dipendenze | Test bloccante | Acceptance | Go/No-Go impact |
|---|---|---|---|---|---|---|---|
| P0-01 | Operational freeze + demote S1 | WS-00 | Capitale reale su sistema research-grade | — | engine-live-off check | S1 non live; promozioni bloccate | Blocca ogni live |
| P0-02 | Secret rotation + cron sandbox + JWT fail-fast | WS-01 | Leak credenziali + azioni autonome | — | `test_no_hardcoded_api_key` | nessun secret in repo | Blocca live |
| P0-03 | Paper/live explicit single source | WS-02 | Passaggio live inconsapevole | — | `test_paper_live_single_source` | modo esplicito+audit | Blocca live |
| P0-04 | Strategy Status SoT + alloc enforcement | WS-02 | Stato contraddittorio; cap soft | P0-03 | `test_validate_allocations_raises` | SoT unica; over-alloc solleva | Blocca promozione |
| P0-05 | Execution Safety Contract (stop-loss/pending/partial) | WS-03 | Downside non protetto; duplicate-BUY | P0-03 | `test_new_buy_always_has_stop_loss`; `test_skip_duplicate_buy` | drill gap-down/pending superati | Blocca live |
| P0-06 | Kill-switch fail-closed + re-check + human recovery | WS-04 | Race window; revoca facile | P0-04 | `test_kill_switch_prevents_submission` | halt mid-cycle ferma ordini | Blocca live |
| P0-07 | Market calendar fail-closed | WS-03 | Ordini a mercato chiuso | P0-05 | `test_clock_failure_aborts_cycle` | clock fail → no ordini | Blocca live |
| P0-08 | Config validation + audit | WS-05 | Risk control smontabili via UI | P0-04 | `test_config_rejects_out_of_bound` | bound server-side+audit | Blocca live |
| P0-09 | Regime multiplier applied (no 1.0 hardcode) | WS-09 | Nessun de-risking; UI falsa | P0-04 | `test_regime_multiplier_applied` | regime cablato o off dichiarato | Blocca live |
| P0-10 | Reproducibility manifest + deterministic re-run | WS-08 | Nessun numero verificabile | P0-12 | `test_backtest_rerun_deterministic` | re-run identico | Blocca promozione |
| P0-11 | No-lookahead / t+1 decision (no promote on same-bar) | WS-06 | Backtest non implementabile | P0-10 | `test_injected_future_signal_fails` | no-lookahead test verde | Blocca promozione |
| P0-12 | Test suite baseline verde + audit_log | WS-13 | Suite rossa = nessuna fiducia | — | suite verde in CI | suite verde deterministica | Blocca promozione |
| P0-13 | S4 promotion block + S7 R&D containment | WS-11/WS-12 | Alpha non valutabile; R&D in operativo | P0-04 | `test_s7_not_in_operational_registry` | S4 bloccata; S7 contenuto | Blocca promozione |

## 7. Final P1 List

| ID | Titolo | WS | Motivo | Dipendenze | Test bloccante | Acceptance | Go/No-Go impact |
|---|---|---|---|---|---|---|---|
| P1-01 | Cost model ADV reale + fixed cost + cost-aware sizing | WS-07 | Net-Sharpe disonesto | P0-11 | `test_cost_model_uses_real_adv` | net-Sharpe con costi reali+fisso | Blocca promozione |
| P1-02 | Stress test storico reale | WS-06/08 | Stress circolare | P0-10 | `test_stress_period_independent` | 2008/2020/2022 o "non testabile" | Blocca promozione |
| P1-03 | Gate fixes (n_trials, denominator, clamp) + Gate 3 SPA | WS-08 | Gate non validano | P0-10 | `test_gate_*` + `test_gate_3_spa` | gate onesti | Blocca promozione |
| P1-04 | S4 gate script runnable + lifecycle | WS-08 | Soglia promozione indefinita | P1-03 | gate report S4 gira | report riproducibile | Blocca promozione S4 |
| P1-05 | Combiner net-cap + conflict + vol-targeter order | WS-09 | Cap violabile; conflitti silenti | P0-09 | `test_net_exposure_cap_enforced` | cap invariante | Blocca live multi-strategia |
| P1-06 | Operator cockpit + readiness + alerting | WS-10 | Falsa sicurezza; degrado silenzioso | P0-04 | `test_ui_no_inactive_as_active` | cockpit veritiero + alert | Blocca paper affidabile |
| P1-07 | S3 sizing PIT + survivorship-free | WS-06 | Lookahead full-sample | P0-11 | `test_s3_expanding_window_vol` | sizing causale | Blocca riapertura S3 |
| P1-08 | Survivorship-free universe (active_at) S1 | WS-06 | OOS solo bull | P0-11 | `test_universe_filtered_by_inception` | universo PIT | Blocca promozione S1 |
| P1-09 | LLM/S4 pipeline (recency, RAG/supervisor, LOO ICIR, dedup) | WS-11 | Rumore/allucinazione | P1-03 | `test_s4_signal_ttl_filter` | pipeline PIT contenuta | Blocca promozione S4 |
| P1-10 | Promotion Readiness Gate + requalification | WS-15 | Promozioni discrezionali | P0-10, P1-01..04 | `test_promotion_requires_gate` | gate non bypassabile | Blocca ogni promozione |
| P1-11 | CI expansion (mypy/pip-audit/coverage/secret) | WS-13 | Regressioni/supply-chain | P0-12 | CI verde con scan | scan attivi | Blocca deploy |
| P1-12 | Paper/live divergence monitoring | WS-10 | Parità non misurata | P1-06 | (NEEDS_RUNTIME_DATA) | metrica attiva ≥soglia | Blocca live |
| P1-13 | Walk-forward con fitting reale su IS | WS-06 | WF decorativo | P0-11 | `test_wf_is_fitting` | degrado OOS misurato | Blocca promozione |

## 8. P2/P3 Backlog

**P2:** Docker hardening completo + DR/backup (WS-14); reconcile più frequente; broker-adapter abstraction (de-lock-in Alpaca); VWAP/limit execution; sensitivity report re-framing (no "near-optimum"); roadmap-vs-code consistency check.
**P3:** S2 con dati opzioni reali (diagnosi −0.55); S7 sviluppo con consensus EPS PIT esterno; nuovi alpha N1–N4; tax-aware P&L; estensioni cross-sectional/overnight.

---

## 9. Strategy Status Table

| Strategia | Stato attuale | Stato raccomandato ora | Perché | Consentito | Vietato | Condizione per avanzare | Test/gate richiesti | Kill criteria | Owner |
|---|---|---|---|---|---|---|---|---|---|
| **S1** | live 50% | **Backtest candidate** (demuovere da live → supervised paper) | Validazione non valida (same-bar, survivorship, costi≈0, DSR n_trials=1, stress/regime circolari); no stop-loss live | backtest onesto, paper osservativo | live, capitale reale, tuning | P0-05/06/07 + P0-10/11 + P1-01/02/08/13 + SPA positiva | t+1, survivorship-free, costi reali, SPA, stress reale | OOS net <0.3 o non significativo post-SPA; DD>soglia in bear reale | Quant + Product/Risk |
| **S2** | disabled 0% | **R&D only / Disabled** | Backtest su **option chain sintetiche** → −0.55 non informativo | ricerca con dati reali | qualsiasi allocazione | dati opzioni reali storici + S2-F1/F2 | gate su dati reali; tail stress | VRP net ≤0 reale; CVaR inaccettabile | Quant |
| **S3** | disabled 0% | **R&D only** | Lookahead full-sample nel sizing (`s3:88`); survivorship | ricerca, rerun PIT | allocazione, riapertura su numeri attuali | P1-07 (vol PIT) + survivorship-free | sizing causale, rank stability | 0.15 sparisce con vol PIT | Quant |
| **S4** | paper 10% | **Paper only (contenuto), promozione BLOCCATA** | Nessuno studio IC; gate ineseguibile; RAG/supervisor assenti; segnali stale | paper osservativo a cap hard 10% | promozione, aumento cap | P1-04/09 + placebo/IC net>0 (§15) | IC vs placebo, decay, timestamp PIT | IC ≤ placebo; edge < costi | Data/LLM + Quant |
| **S7/PEAD** | "done"/orfano | **R&D only / Disabled + fuori dalla UI** | No `__call__`, EDGAR metadata-only, consensus allucinabile, no consumer | ricerca | **cablaggio**, allocazione, UI "attivo" | consensus EPS PIT esterno + filing body + S7-F1..F4 | event study, survivorship-free | drift non significativo net | Quant + Data/LLM |

Regola: **nessuna strategia è Live-ready** finché restano P0 di execution/backtest/safety aperti. Paper = osservabile, non validata.

---

## 10. Phased Roadmap

### Phase 0 — Immediate Freeze and Risk Containment (0–3 giorni)
- **Obiettivo:** smettere di peggiorare.
- **WS:** WS-00, WS-01 (rotazione+cron), parte di WS-12 (UI S7 disclaimer).
- **Entry:** approvazione freeze del PO.
- **Exit:** S1 non live; secret ruotati; cron neutralizzato; S7 fuori UI; promozioni congelate.
- **Artefatti:** policy di freeze firmata; inventario secret ruotati.
- **Decisioni:** §13 #1, #2, #3, #5.
- **Rischi:** freeze parziale.
- **Non fare:** non lasciare un path live attivo.

### Phase 1 — Execution Safety and Security (1–2 settimane)
- **Obiettivo:** un path che non può ferire silenziosamente.
- **WS:** WS-03, WS-04, WS-05, resto WS-01, WS-13 (baseline verde + audit_log).
- **Entry:** Phase 0 completa.
- **Exit:** P0-02/05/06/07/08/12 chiusi; drill superati.
- **Artefatti:** drill report (gap-down, halt mid-cycle, clock fail, pending).
- **Decisioni:** §13 #6 (2FA), #4.
- **Rischi:** safety in codice morto.
- **Non fare:** no live; no promozioni.

### Phase 2 — Validation Truth and Reproducibility (2–4 settimane)
- **Obiettivo:** validazione onesta e riproducibile.
- **WS:** WS-06, WS-07, WS-08, WS-02 (SoT), WS-09 (regime/cap).
- **Entry:** Phase 1 completa.
- **Exit:** P0-04/09/10/11 + P1-01/02/03/04/05/07/08/13 chiusi; no-lookahead test verde.
- **Artefatti:** reproducibility manifest; net-Sharpe onesto; gate corretti.
- **Decisioni:** §13 #7 (data provider/ADV).
- **Rischi:** riparare script lasciando design contaminato.
- **Non fare:** no tuning; no promozione su numeri vecchi.

### Phase 3 — Governance and Product Truth Layer (2–4 settimane)
- **Obiettivo:** cockpit veritiero + monitoring + promotion gate.
- **WS:** WS-10, WS-15, WS-11 (containment), WS-12, WS-14, WS-13 (espansione).
- **Entry:** Phase 2 completa.
- **Exit:** P1-06/09/10/11 chiusi; cockpit deriva dalla SoT; gate attivo.
- **Artefatti:** Operator cockpit; promotion gate; alerting.
- **Decisioni:** §13 #8 (EPS provider), #9.
- **Rischi:** cockpit copia divergente.
- **Non fare:** non cablare S7; non promuovere.

### Phase 4 — Strategy Requalification (4–8 settimane)
- **Obiettivo:** riclassificare le strategie su numeri onesti + esperimenti quant.
- **WS:** WS-15 + esperimenti §15.
- **Entry:** Phase 2–3 complete.
- **Exit:** verdetti S1/S3/S4 su backtest onesto + falsification; stati aggiornati.
- **Artefatti:** report di falsification per strategia.
- **Decisioni:** quali strategie passano a paper-candidate.
- **Rischi:** confondere paper P&L con edge.
- **Non fare:** no nuovo alpha.

### Phase 5 — Controlled Paper Program (90 giorni)
- **Obiettivo:** osservare esecuzione e divergenza paper↔live su sistema reso veritiero.
- **WS:** WS-10 (divergenza), monitoring.
- **Entry:** Phase 4; strategie in paper-candidate; safety completa.
- **Exit:** ≥90gg paper con divergenza <soglia; kill criteria mai violati.
- **Artefatti:** paper evidence pack; metrica divergenza.
- **Decisioni:** §13 #10 (accettare 90gg).
- **Rischi:** interpretare P&L paper come prova di edge.
- **Non fare:** no live; no aumento cap.

### Phase 6 — Live Reconsideration (dopo paper evidence)
- **Obiettivo:** decidere il live solo con evidenza.
- **WS:** Promotion Gate (WS-15) applicato al live.
- **Entry:** Phase 5 superata + tutti i P0 chiusi.
- **Exit:** go-live con cap minimo (≤5%) e human-gated, o no-go.
- **Artefatti:** decisione go/no-go documentata.
- **Decisioni:** §13 #1 (live), capitale.
- **Rischi:** go-live prematuro.
- **Non fare:** no live se un solo P0 è aperto.

---

## 11. Test and Acceptance Strategy

Principio: **test-before-fix** per ogni P0/P1 quando il failure mode è esprimibile; test che *falsificano* il rischio, non che lo confermano.

| Categoria | Perché serve | Cosa cattura | Fixture | Quando | Acceptance |
|---|---|---|---|---|---|
| Execution safety | Protezione capitale | stop-loss assente, posizione scoperta | broker mock | prima del fix WS-03 | gap-down → posizione chiusa |
| Kill-switch | Halt affidabile | race window, recovery auto | broker mock + Redis | prima WS-04 | halt mid-cycle → no ordini |
| Broker/order sim | Realismo ordini | reject/partial non gestiti | broker mock | prima WS-03 | reject non perso |
| Duplicate/idempotency | Over-exposure | duplicate-BUY da pending | broker mock | prima WS-03 | pending → no duplicato |
| Config validation | Anti-sabotaggio | bound bypassati + no audit | API client | prima WS-05 | fuori bound rifiutato+audit |
| Paper/live mode | Live inconsapevole | dual-source drift | config harness | prima WS-02 | fonte unica coerente |
| Backtest timing | Lookahead | same-bar fill | PIT fixture | prima WS-06 | fill t+1 |
| Anti-lookahead | Leakage | future nel signal | PIT fixture + segnale futuro | prima WS-06 | backtest fallisce con futuro |
| Cost model | Net-Sharpe | ADV finta, fisso escluso | ADV storico fixture | prima WS-07 | costi reali nel net |
| Validation gate | Falsa conferma | n_trials/denominator/clamp/CV | gate fixture | prima WS-08 | gate onesti + SPA |
| Reproducibility | Auditabilità | run non deterministico | manifest fixture | prima WS-08 | re-run identico |
| Frontend truthfulness | Falsa sicurezza | UI mostra inattivo come attivo | frontend test | prima WS-10 | nessun falso "attivo" |
| Security | Leak/auth | secret in repo, JWT fallback | CI scan | prima WS-01 | scan verde |
| Audit trail | Compliance | order senza audit row | DB fixture | prima WS-13 | ogni order → audit |
| LLM/news/S4 | Rumore/leakage | stale signal, timestamp, LOO | signal fixture | prima WS-11 | recency+PIT+LOO puliti |
| PEAD/S7 containment | R&D leakage | S7 in operativo/UI | registry+frontend test | prima WS-12 | S7 contenuto |

Esperimenti quant (§15) NON sono unit test: vanno **dopo** i fix di parità/costi e producono verdetti di promozione.

---

## 12. Go/No-Go Policies

1. **Continuare paper:** precondizione = stop-loss attivo + kill-switch manuale + freeze; verifica = nessun ordine live; approvazione = Product/Risk; evidenza = engine-live-off; kill = qualunque ordine live non previsto → halt.
2. **Capitale reale:** precondizione = tutti i P0 chiusi + Phase 1–3 complete + ≥90gg paper con divergenza <soglia; verifica = drill safety + manifest; approvazione = PO; evidenza = paper evidence pack; kill = DD>cap o divergenza>soglia.
3. **Promuovere S1:** precondizione = P0-10/11 + P1-01/02/08/13 + SPA positiva; verifica = backtest onesto riproducibile; approvazione = Quant + PO; evidenza = falsification report; kill = SR net non significativo post-SPA.
4. **Promuovere S4:** precondizione = P1-04/09 + IC>placebo net + timestamp PIT; verifica = event study; approvazione = Quant + PO; evidenza = IC study; kill = IC ≤ placebo.
5. **Riaprire S3:** precondizione = P1-07 (vol PIT) + survivorship-free; verifica = rerun; approvazione = Quant; kill = edge sparisce con vol PIT.
6. **Sviluppare S7:** precondizione = consensus EPS PIT esterno disponibile + pipeline riparata; verifica = event study; approvazione = PO (provider) + Quant; kill = drift non significativo net.
7. **Nuove alpha:** precondizione = Phase 0–4 complete; verifica = 5 gate onesti + manifest; approvazione = Quant; kill = non passa il Promotion Gate.
8. **Config change pericoloso:** precondizione = schema+bound server-side + audit; verifica = test bound; approvazione = elevata se indebolisce risk control; kill = change non auditabile rifiutato.
9. **Deploy:** precondizione = CI verde (test+scan) + suite deterministica; verifica = pipeline CI; approvazione = DevOps; kill = scan rosso o test rossi.

---

## 13. Project Owner Decisions

1. **Live durante remediation:** confermare freeze e demozione S1 (raccomandato: sì).
2. **Rotazione credenziali:** autorizzare rotazione immediata di tutti i secret esposti.
3. **S4/S7 in UI:** confermare marcatura R&D / nascondere (raccomandato: contenere).
4. **Capitale massimo durante remediation:** definire (raccomandato: 0 reale / solo paper).
5. **Agente LLM cron:** disabilitare o sandboxare (raccomandato: disabilitare full-perms).
6. **Meccanismo 2FA kill-switch:** Telegram confirm / TOTP / admin UI?
7. **Data provider / ADV / adjusted data:** quale fonte per prezzi raw+dividendi e ADV storico?
8. **Provider consensus EPS** per PEAD (Refinitiv/Estimize/Bloomberg) — in scope o S7 resta R&D?
9. **Policy paper/live single source:** env var o broker URL come unica fonte?
10. **Accettare 90 giorni paper** prima di qualsiasi live.
11. **Priorità safety vs nuove alpha:** confermare safety-first (raccomandato).
12. **Stile enforcement cap S4:** eccezione hard o workflow di approvazione.

---

## 14. Runtime Data Still Needed

`NEEDS_RUNTIME_DATA`:
- **Divergenza paper↔live** (slippage, fill rate, cost diff) ≥90gg.
- **Conteggio reale fallimenti test** (33 vs 109): clean run riproducibile in ambiente controllato.
- **Fallback rate FinBERT / PSI / ensemble correlation** in esercizio (per dimensionare gli alert).
- **Comportamento reale kill-switch mid-cycle** (drill operativo).
- **Uso effettivo di audit_log** dopo abilitazione dei writer.
- **ADV storico reale** per ticker dell'universo (per il cost model).

## 15. Future Quant Experiments

`NEEDS_QUANT_EXPERIMENTS` (post-fix, non confondere con i fix tecnici):
- **S1:** rerun t+1 + costi reali+fisso + survivorship-free + SPA/Hansen (S1-F1..F6). **Primo backtest da rifare.**
- **S3:** rerun sizing PIT + survivorship-free (S3-F1/F2).
- **S4:** shuffled-news/placebo + IC decay + timestamp publish-time (S4-F1..F3).
- **S2:** con dati opzioni reali storici: segno/payoff + tail stress (S2-F1/F2).
- **S7:** event study con consensus EPS PIT esterno + filing body reale (S7-F1..F4).
- **Regime-aware sizing:** moltiplicatori **pre-specificati** validati OOS (no overfit del risk control).
- **Verifica LOO ICIR:** contaminazione overlapping/future nella pesatura ensemble.

## 16. What Not To Do

- Non fare **parameter tuning** (è data mining, non validazione).
- Non **promuovere** alcuna strategia prima del Promotion Gate.
- Non aggiungere **nuove alpha** prima di Phase 4.
- Non sistemare **solo l'UI** lasciando il backend falso (verità deriva dalla SoT).
- Non trattare **paper come live** né **paper P&L come prova di edge**.
- Non usare **backtest non riproducibili / same-bar / adjusted-close / survivorship** per decidere.
- Non implementare **fix senza test** (test-before-fix sui P0/P1).
- Non lasciare **R&D visibile come operativo** (S7).
- Non **cablare S7** (errore corretto in P4): contenerlo.
- Non ignorare **costi/slippage/impatto/fisso**.
- Non consentire **config change pericolosi** senza validazione+audit.
- Non considerare **esistente** una capability in codice morto (stop-loss legacy).
- Non **riparare gli script gate** lasciando intatti input/design contaminati.
- Non **re-implementare la sanitizzazione** (esiste già `src/text/sanitizer.py`): verificarne solo il path.
- Non consentire **live** se un solo P0 di safety/validation è aperto.

## 17. 7-Day Action Plan

1. **Freeze firmato + demuovere S1 da live** (WS-00, P0-01).
2. **Ruotare tutti i secret esposti** + spostare in `.env` + **disabilitare/sandbox cron LLM** (WS-01, P0-02).
3. **Disattivare gli engine di esecuzione live**; abilitare stop-loss (`ALPACA_BRACKET_ENABLED=true`) per il solo paper; runbook kill manuale.
4. **Marcare S7/PEAD R&D e toglierlo dalla UI**; de-flaggare in roadmap (WS-12, parte P0-13).
5. **Lock di `config/strategies.yaml`** dietro PR+review.
6. **Avviare WS-13:** fix dependency groups, clean run riproducibile per fissare il conteggio test reale, iniziare a rendere la suite verde.
7. **Decisioni PO §13 #1-#6** raccolte.

## 18. 30-Day Action Plan

1. **Completare Phase 1 (Execution Safety + Security):** stop-loss/pending/partial (P0-05), kill-switch fail-closed+re-check+human recovery (P0-06), calendario fail-closed (P0-07), config validation+audit (P0-08), suite verde+audit_log (P0-12). Drill superati.
2. **Avviare Phase 2 (Validation Truth):** reproducibility manifest (P0-10), t+1/no-lookahead (P0-11), S3 vol PIT (P1-07), survivorship-free S1 (P1-08), gate fixes+SPA (P1-03), cost model reale+fisso (P1-01), stress reale (P1-02).
3. **Paper/live esplicito + Strategy Status SoT** (P0-03/04); **regime cablato** (P0-09).
4. **S4 promotion block confermato**; pipeline recency/RAG/supervisor avviata (P1-09).
5. **Primo backtest S1 onesto** (esperimento §15) preparato per Phase 4.

## 19. Definition of Done for Remediation

La remediation è completa quando:
- Tutti i **P0 chiusi** con test verdi e drill superati (safety, security, kill-switch, config, calendario, SoT, reproducibility, no-lookahead, suite verde).
- Tutti i **P1 chiusi** (cost model onesto, gate corretti+SPA, combiner net-cap, cockpit+monitoring, promotion gate, S3/S1 PIT, CI espansa).
- **Promotion Readiness Gate** attivo e non bypassabile; ogni strategia ha uno stato giustificato da gate riproducibili + esperimenti quant.
- **Reproducibility manifest** su ogni run; re-run deterministico in CI.
- **Cockpit veritiero** + **alerting** attivi; divergenza paper↔live misurata.
- **≥90 giorni di paper** con divergenza <soglia e kill criteria mai violati.
- **S7 contenuto**, S2/S3 R&D, S4 bloccata fino a IC>placebo.
- Nessun secret nel repo; deployment hardened; DR testata.

## 20. Final Recommendation

**Safety-first, validation-second, alpha-last.** Eseguire Phase 0 entro 7 giorni (freeze, demote S1, secret, contenere S7), poi Phase 1–2 entro 30 giorni (execution safety + validation truth). Trattare S1 come *backtest candidate* da rivalidare onestamente; S4 paper-bloccata; S2/S3/S7 R&D. **Nessun ritorno a capitale reale** finché tutti i P0 non sono chiusi, gli esperimenti quant non danno un verdetto su numeri onesti, e ≥90 giorni di paper non confermano una divergenza accettabile. Nuovo alpha solo in Phase 6. Aprire ora i ticket P0 (in ordine di dipendenza) con test-before-fix.

## 21. Stop Point

Questo Master Plan non modifica codice e non autorizza automaticamente implementazioni. Il prossimo passo è aprire ticket P0/P1 e implementarli uno alla volta, con test prima del fix e review dopo ogni fase.

---

*Fine ALEMBIC_REMEDIATION_MASTER_PLAN_2026-06-18 (Passata 5/5). Read-only rispettato: nessun file di sistema modificato, nessun codice/patch/commit, nessun worker/pipeline/ordine eseguito. Sintesi delle 5 review; tassonomia RB canonica (blueprint); capability vs patch preservata; nessuna strategia promossa; nessun parameter tuning. Priorità a safety, auditabilità, riproducibilità, idempotenza, chiarezza paper/live, verità della validazione e protezione del capitale.*
