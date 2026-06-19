# OPUS_REVIEW_OF_KIMI_TECHNICAL_VERIFICATION

> **Passata 4 di 5** — Review della Technical Verification Matrix (Kimi, Passata 3).
> Ruolo: Principal Systems Reviewer + Chief Risk Officer + Head of Quant Research + Product Safety + Governance Reviewer (reviewer della review tecnica).
> Modalità: **read-only**. Nessun file di sistema modificato, nessun codice/patch/commit, nessuna pipeline/worker/ordine eseguito. Unico artefatto: questo documento.
> Input: i 4 documenti di review + ispezione read-only mirata per confermare/smentire punti critici di Kimi.
> Data: 2026-06-18.

**Cosa NON è questo documento.** Non è una nuova review funzionale, quant o code-review. Non difende automaticamente né Opus né Kimi. Valuta *qualità, copertura, priorità e allineamento* della matrice Kimi rispetto ai rischi funzionali e quant, e stabilisce se siamo pronti per il Master Plan.

**Base di giudizio.** Ho un ground-truth indipendente: nella Passata 2 ho letto personalmente `orchestrator.py`, `data_replay.py`, `realistic.py`, `s1/{signal,sizing,sensitivity,backtest}.py`, le 5 gate + `runner.py`, `universe.py`, `s3/strategy.py`, `s2/signal.py`, `s4/strategy.py`, `s7/strategy.py`, `forward_returns.py`. In questa passata ho verificato in più: `src/text/sanitizer.py`, `src/costs/calculator.py`, la presenza di LOO ICIR (`src/performance/ic.py`, `src/workers/sentiment.py`), e l'assenza di RAG/supervisor.

---

## 1. Executive Summary

La matrice Kimi è **tecnicamente accurata e ben ancorata** sui punti concreti di codice: conferma con `file:line` praticamente **tutte** le contaminazioni quant che avevo verificato indipendentemente nella Passata 2 (same-bar fill, ADV fallback, S3 lookahead, S2 sintetico, n_trials=1, Gate 2 denominatore, Gate 4 clamp, stress/regime circolari, survivorship, walk-forward decorativo, Adj Close). Su questi temi l'evidenza è STRONG e il tasso di falsi positivi è basso. Kimi mostra anche buona disciplina nel distinguere frontend da backend (§5 "False Positives" corregge "regime hardcoded in Performance.tsx" → è il fallback *backend*), codice-presente da comportamento (le due execution path con safety diverse), e documentazione da runtime.

Ci sono però **tre problemi sistemici** che rendono la matrice *buona ma da correggere prima del Master Plan*:

1. **Corruzione della tassonomia RB.** Da **RB-007 in poi Kimi ha re-numerato/ridefinito gli ID** rispetto al Functional Remediation Blueprint. RB-007 (=Validated Config Change Workflow nel blueprint) diventa "Backtest fill", RB-008 (=Reproducible Validation Manifest) diventa "Data integrity", RB-012 (=Operator Safety Cockpit) diventa "LOO ICIR", RB-013 (=Monitoring & Alerting) diventa "Gate runner", RB-014 (=Secrets/Ops Baseline) diventa "Input sanitization". Questo rompe la tracciabilità — il cuore di una verification matrix.
2. **Capability cadute nelle crepe.** A causa della re-numerazione, due capability funzionali vere sono **assenti come capability**: **Operator Safety Cockpit** e **Monitoring & Alerting** (fallback rate/PSI/lag/cap-violation/paper-live divergence). Altre (config-change workflow, gate-lifecycle governance, parity governance) sono verificate come *sintomi sparsi* ma non come capability nel roadmap.
3. **Sottostime quant/priorità.** La **riproducibilità** è degradata a P2 (è un prerequisito → P0/P1). Il verdetto quant centrale su **S4 (nessuno studio IC → alpha non valutabile)** è stato riformulato in un problema minore ("segnali stale"). **Gate 3 (robustness gate vero)** non è verificato. **LOO ICIR** — che esiste davvero ed è il meccanismo di pesatura ensemble di S4 — è lasciato non verificato.

**Verdetto: Good but incomplete / Useful but needs correction.** Pronti per il Master Plan **con gap colmabili** (READY_WITH_GAPS), non per partire ticket-by-ticket senza prima ri-mappare gli RB e reintegrare le capability mancanti.

---

## 2. Review Verdict

**Classificazione: Useful but needs correction** (vicino a "Good but incomplete").

- *Perché non "Strong and sufficient":* la corruzione della tassonomia RB e l'assenza di 2 capability (cockpit, monitoring/alerting) impediscono di usare la matrice come spina dorsale tracciabile del Master Plan senza rilavorazione.
- *Perché non "Not sufficient":* l'evidenza tecnica è solida e indipendentemente confermata; il 90% dei finding di codice è corretto e azionabile; il test-plan e la roadmap fasata sono materiale di alta qualità.
- *Perché non "Too implementation-focused" (anche se ci va vicino):* Kimi è giustamente molto operativa, e su SoT/promotion/execution-safety propone vere *capability* (tabella `strategy_lifecycle`, promotion API con sign-off, unificazione execution path) non semplici patch. Il difetto non è eccesso di implementazione, ma **omissione di alcune capability di governance/verità** (cockpit, monitoring, config-workflow, gate-lifecycle, parity).

La matrice **avvicina molto** il progetto al Master Plan, ma va **ri-allineata alla tassonomia del blueprint** e **completata** su 5-6 capability.

---

## 3. Coverage Matrix

| Area | Atteso dai doc Opus | Copertura Kimi | Qualità | Gap | Azione |
|---|---|---|---|---|---|
| Strategy Status SoT (RB-001) | Fonte unica verificabile | Coperto bene (propone `strategy_lifecycle` DB) | STRONG | Mode scartato dal registry confermato | Portare in MP come capability |
| Promotion Gate (RB-002) | Gate riproducibile per cambio stato | Coperto bene (promotion API + sign-off) | STRONG | — | Portare in MP |
| Explicit Paper/Live (RB-003) | Modo esplicito, non da URL | Coperto bene (P0, dual-source confermato) | STRONG | — | MP P0 |
| Execution Safety (RB-004) | Stop-loss/pending/partial/duplicate | Coperto bene (P0, due path divergenti) | STRONG | partial-fill atomic solo descritto | MP P0 + test |
| Kill-Switch Governance (RB-005) | Fail-closed, re-check, 2FA, human recovery | Coperto bene (P0, race + no 2FA confermati) | STRONG | — | MP P0 |
| Risk Control Truthfulness (RB-006) | Controlli reali + UI veritiera | Coperto bene (regime 1.0, vol-targeter ordering, additive) | STRONG | — | MP P0/P1 |
| **Validated Config Change Workflow (vero RB-007)** | Schema+bound server-side+audit+approvazione | **Coperto parzialmente** (config_routes:29-44 verificato in §11.C, ma fuori dalla tassonomia RB e assente dal roadmap fasato) | MODERATE | Capability non nel roadmap | **Reintegrare in MP** |
| **Reproducible Validation Manifest (vero RB-008)** | Pin data/modello/seed, re-run deterministico | **Coperto ma priorità discutibile** (citato come P2 additional finding) | MODERATE | Prerequisito declassato | **Elevare a P0/P1 in MP** |
| **Gate Report Lifecycle (vero RB-009)** | Gate eseguibili/riproducibili/datati; rotto = promozione bloccata | **Coperto parzialmente** (fix dei bug gate sì; *governance* del lifecycle no) | WEAK | Manca governance del ciclo gate | Reintegrare capability |
| **Backtest↔Live Parity (vero RB-010)** | No-lookahead/t+1/cost-aware + kill-switch modellato + divergenza paper-live | **Coperto parzialmente** (realismo backtest sì; divergenza paper-live e parity governance no) | MODERATE | Metrica divergenza assente | Reintegrare + NEEDS_RUNTIME_DATA |
| **R&D Containment (vero RB-011)** | R&D fuori dalle superfici operative (UI+consumer) | **Coperto parzialmente** (ridotto a "S7 not registered"; PEAD UI in §11.C) | MODERATE | Containment come capability non esplicito | Reintegrare in MP |
| **Operator Safety Cockpit (vero RB-012)** | Vista veritiera: stato reale, stale, readiness, why-trade, paper≠live | **NON coperto come capability** (slot occupato da "LOO ICIR") | UNSUPPORTED | Capability mancante | **CRITICAL: reintegrare** |
| **Monitoring & Alerting (vero RB-013)** | Alert fallback/PSI/ensemble corr/lag/cap-violation/divergenza | **NON coperto** (slot occupato da "Gate runner") | UNSUPPORTED | Capability mancante | **CRITICAL: reintegrare** |
| **Secrets & Ops Baseline (vero RB-014)** | Rotazione secret, JWT fail-fast, docker, DR, no LLM-cron full-perms | **Coperto bene ma mislabeled** (tutto in §11, slot RB-014 dato a "sanitization") | STRONG | DR/backup non trattato | Re-etichettare; aggiungere DR |
| Test & Audit Integrity (RB-015) | Suite verde + audit chain | Coperto bene (109 fail, audit_log morta, dep mismatch) | STRONG | Discrepanza conteggio test (33 vs 109) | MP P1 + clean run |
| Schedule/Calendar Truthfulness (RB-016) | Schedule reale + calendario fail-closed | Coperto bene (drift + fail-open confermati) | STRONG | — | MP P1 |
| Quant: same-bar/ADV/S3/S2/gates/stress/regime/survivorship/WF | Tutti i blocker Passata 2 | Coperto bene (confermati con file:line) | STRONG | Gate 3 vero, S4 IC, fixed cost, LOO ICIR | Vedi §7 |
| Security/Ops (API key, JWT, docker, CI) | Tutti | Coperto bene | STRONG | DR/backup, LLM-cron `--dangerously-skip-permissions` | Aggiungere a MP |
| Product/Frontend truthfulness | UI veritiera, PEAD disclaimer, promotion readiness | Coperto parzialmente (item sparsi, niente cockpit) | MODERATE | Cockpit + readiness dashboard | Reintegrare |
| Auditability/Reproducibility | audit_log + manifest | Coperto (audit_log morta) ma manifest P2 | MODERATE | Reproducibility priorità | Elevare |
| R&D Containment | S7 fuori operativo | Parziale | MODERATE | Vedi RB-011 | Reintegrare |

---

## 4. Evidence Quality Review

| Kimi finding | Evidence quality | Confidence | Note |
|---|---|---|---|
| Same-bar fill (`orchestrator.py:87-96`) | STRONG_EVIDENCE | Alta | Verificato indipendentemente in Passata 2 |
| ADV fallback 10M (`data_replay.py:38-45`) + 20B (`costs/calculator.py:29`) | STRONG_EVIDENCE | Alta | **Confermato anche calculator.py:29 = 20B** (verificato ora) |
| S3 lookahead vol (`s3/strategy.py:88`) | STRONG_EVIDENCE | Alta | Confermato; full-sample `.iloc[-1]` |
| S2 synthetic chain (`s2/signal.py:66,80`) | STRONG_EVIDENCE | Alta | Confermato |
| S4 stale signals (`s4/strategy.py:142-163`) | STRONG_EVIDENCE | Alta | Vero, ma è il problema *minore* di S4 (vedi §7) |
| Gate 1 n_trials=1 (`runner.py:20`) | STRONG_EVIDENCE | Alta | Confermato |
| Gate 2 denominatore (`gate_2:51-56`) | STRONG_EVIDENCE | Alta | Confermato |
| Gate 4 clamp (`gate_4:42`) | STRONG_EVIDENCE | Alta | Confermato |
| S1 stress/regime circolari (`s1/backtest.py:167-197`) | STRONG_EVIDENCE | Alta | Confermato |
| Survivorship (`universe.py:36` non usato) | STRONG_EVIDENCE | Alta | Confermato |
| Walk-forward decorativo (`runner.py:102-116`) | STRONG_EVIDENCE | Alta | Confermato |
| Paper/live dual-source (`portfolio_scheduler.py:229,251`) | STRONG_EVIDENCE | Alta | Confermato |
| Bracket off-by-default (`config.py:117-118`) | STRONG_EVIDENCE | Alta | Confermato |
| Kill-switch check once / no re-check (`:212-233` vs `:901`) | STRONG_EVIDENCE | Alta | Confermato |
| regime_mult=1.0 (`portfolio_scheduler.py:543,626,629`) | STRONG_EVIDENCE | Alta | Confermato, giusto P0 |
| API key hardcoded (`daily_analysis.sh:51`) | STRONG_EVIDENCE | Alta | Confermato, giusto P0 |
| **Input sanitization "not located"** | **UNSUPPORTED (falso negativo)** | Alta | **`src/text/sanitizer.py` ESISTE** ed è importato in `sentiment.py`, `finbert.py`, connectors. La review funzionale aveva ragione. |
| RAG/supervisor "not found" | STRONG_EVIDENCE | Alta | **Confermato assente** (grep vuoto in src/llm, src/workers) — coerente con spec non rispettata |
| **LOO ICIR contamination (RB-012/Q5)** | **NEEDS_MORE_CODE_VERIFICATION** | Bassa | Kimi onesto: "needs re-read". **Ma il meccanismo ESISTE** (`src/performance/ic.py compute_icir`; `sentiment.py:334-339` pesi LOO da Redis). Verificabile, non verificato. |
| cost model non in sizing (Q9, `calculator.py` usato in pg_store/exec/report, non in scheduler) | MODERATE_EVIDENCE | Media | Plausibile; non ho riletto tutti i call-site del scheduler |
| 109 failed + 2 errors (test run) | NEEDS_RUNTIME_DATA | Media | Discrepanza con "33 rossi" della review funzionale → serve clean run riproducibile |
| audit_log morta (`001_initial.sql:85-97`, nessun INSERT) | STRONG_EVIDENCE | Alta | Confermato |

**Sintesi qualità evidenza:** prevalentemente STRONG. Un solo **falso negativo** (sanitizer), un'**unverified ammessa** (LOO ICIR, ma reale → va chiusa), e una **discrepanza runtime** (conteggio test). Disciplina di evidenza complessivamente alta.

---

## 5. Priority Corrections

| Finding | Priorità Kimi | Priorità Opus rivista | Motivazione |
|---|---|---|---|
| Reproducible Validation Manifest | P2 | **P0/P1** | È *prerequisito* di ogni claim di validazione e di SPA/Hansen; senza, nessun gate report è difendibile. Declassarlo a debito ingegneristico è un errore di priorità. |
| S1 contaminata **mentre è LIVE 50%** | (implicito in "no live until Phase 3") | **P0 azione di governance: demuovere S1 ora** | Kimi disabilita gli engine (corretto) ma non nomina l'atto: capitale reale è esposto su una validazione che non valida. Va esplicitato come decisione P0. |
| S4 "no IC / alpha non valutabile" | non presente (riformulato come "stale signals" P1) | **P1 promotion blocker esplicito** | Il punto quant centrale di S4 non è la staleness ma l'assenza di edge dimostrato; senza placebo/IC, S4 non è promovibile. |
| Operator Safety Cockpit | assente | **P1** | Falsa sicurezza dell'operatore è PRODUCT_RISK/LIVE_BLOCKER nel blueprint. |
| Monitoring & Alerting | assente | **P0 (safety alert) / P1 (divergenza)** | Il degrado silenzioso (fallback/PSI/lag/cap-violation) è un modo tipico di fallire; serve almeno l'alerting di safety. |
| Validated Config Change Workflow | sparso (§11.C, "what to ask") | **P0** | Slider UI possono smontare i risk control senza audit: è un LIVE_BLOCKER, non una domanda aperta. |
| Input sanitization (RB-014 di Kimi) | P2 GAP | **Declassare/chiudere** | Falso negativo: la sanitizzazione esiste. La vera lacuna è **RAG/supervisor assenti** (P1 per S4) — riassegnare la priorità a quella. |
| LOO ICIR | P1 "gap pending" | **P1 + NEEDS_ADDITIONAL_TECHNICAL_VERIFICATION** | Reale e non verificato; tocca la pesatura ensemble di S4. |
| API key / kill-switch 2FA / regime_mult=1.0 | P0 | **P0 (confermato)** | Allineati al blueprint; nessuna correzione. |
| Same-bar / quant blockers | P1 | **P1 (confermato)** come fix-codice; **P0 come decisione "non promuovere"** | La distinzione fix(P1)/decisione(P0) va resa esplicita nel MP. |

---

## 6. Capability vs Patch Review

| Capability (blueprint) | Remediation Kimi | Risolve la capability? | Cosa manca | Implicazione Master Plan |
|---|---|---|---|---|
| RB-001 Strategy Status SoT | Tabella `strategy_lifecycle` + registry legge da DB | **Sì** | Migrazione + back-fill da YAML; sync UI | Adottare; è una vera capability |
| RB-002 Promotion Readiness Gate | Promotion admin API con sign-off + audit | **Sì** | Legare ai criteri quant (gate riproducibili, paper days, DR, cap) | Adottare; collegare a RB-008/009 |
| RB-003 Explicit Paper/Live | Source unica (env o URL) | **Sì** | Decisione PO su quale fonte; conferma+audit | Adottare |
| RB-004 Execution Safety Baseline | Unificare path, stop-loss fail-closed, pending check | **Sì (parz.)** | Partial-fill atomico e reconcile real-time solo descritti | Adottare + test e2e (gap-down, pending) |
| RB-005 Kill-Switch Governance | Fail-closed + re-check pre-submit + human recovery | **Sì** | Meccanismo 2FA (Telegram/TOTP) da decidere | Adottare |
| RB-006 Risk Control Truthfulness | Reorder vol-targeter, net-cap, cabla regime, rimuove costanti UI | **Sì** | Moltiplicatori regime *pre-specificati* (no overfit, vedi quant memo) | Adottare + vincolo no-tuning |
| **RB-007 Validated Config Change Workflow** | (sparso) range-check accennato | **Parzialmente** | Schema+bound server-side+audit+approvazione elevata, come *capability nel roadmap* | **Aggiungere fase dedicata** |
| **RB-008 Reproducible Validation Manifest** | "Add manifest" in Phase 5 | **Parzialmente** | Determinismo verificato (re-run identico), priorità, CI di confronto | **Anticipare e elevare a P0/P1** |
| **RB-009 Gate Report Lifecycle** | Fix dei bug delle singole gate | **No (solo sintomo)** | Governance: gate eseguibili+riproducibili+datati; rotto ⇒ promozione bloccata per definizione | **Aggiungere capability**; non solo bug-fix |
| **RB-010 Backtest↔Live Parity** | t+1, costi, kill-switch live (separati) | **Parzialmente** | Kill-switch *modellato nel backtest*; metrica divergenza paper-live; etichetta "pre-risk-control" | Aggiungere parity governance |
| **RB-011 R&D Containment** | Wire S7 in registry con paper mode | **No / rischioso** | Containment ≠ cablaggio: S7 va *contenuto* (fuori UI/consumer) finché pipeline+consensus PIT non esistono. Kimi propone di cablarlo: **contraddice il verdetto quant** (S7 non valutabile) | **Correggere**: contenere, non cablare |
| **RB-012 Operator Safety Cockpit** | (assente) | **No** | Vista veritiera unica (stato reale, stale, readiness, why-trade, paper≠live) | **Reintegrare capability** |
| **RB-013 Monitoring & Alerting** | (assente) | **No** | Alert fallback/PSI/ensemble-corr/lag/cap-violation/divergenza | **Reintegrare capability** |
| RB-014 Secrets & Ops Baseline | Rotazione, docker hardening, CI scan (in §11/Phase 1) | **Sì (parz.)** | DR/backup; neutralizzare LLM-cron full-perms; JWT fail-fast esplicito | Adottare + aggiungere DR e cron |
| RB-015 Test & Audit Integrity | Fix dep groups, CI verde, audit_log writes | **Sì** | Determinismo/seed; chiarire conteggio test reale | Adottare |
| RB-016 Schedule/Calendar | Calendario fail-closed + schedule da beat | **Sì** | — | Adottare |

**Conclusione capability-vs-patch:** Kimi è **forte** dove serviva una capability (SoT, promotion, execution safety, kill-switch) — propone soluzioni strutturali, non cerotti. È **debole o assente** su 5 capability di *governance/verità*: config-workflow, gate-lifecycle, parity, cockpit, monitoring/alerting — e su **RB-011 propone l'azione opposta** (cablare S7 invece di contenerlo), in contraddizione col verdetto quant. Questi sono i punti che il Master Plan deve correggere.

---

## 7. Quant Alignment Review

| Tema | Kimi ha verificato? | Evidenza sufficiente? | Il test falsifica il rischio? | Cosa entra nel MP |
|---|---|---|---|---|
| Same-bar execution | Sì (`orchestrator.py:87-96`) | Sì | Sì (test t+1 #12) | Fill t+1 + gap; ri-run S1 |
| t+1 fill | Sì (gap) | Sì | Sì | idem |
| S1 signal timing | Sì (implicito) | Sì | Parziale (manca test che il segnale non veda close[t] usato per fill) | Aggiungere assert decisione/fill |
| S3 lookahead sizing | Sì (`s3:88`) | Sì | Sì (#13 expanding-window) | Fix + rerun PIT (esperimento) |
| **S4 IC / decay / edge** | **No** (riformulato come "stale signals") | No | No (manca placebo/IC) | **Aggiungere: S4 non valutabile finché IC>placebo net** |
| S7 PEAD data validity | Sì (non registrato, no `__call__`) | Sì | n/a | Contenere; pipeline+consensus PIT prima |
| **Gate 3 robustness (vero gate)** | **No** (solo sensitivity report `sensitivity.py:152-160`) | No | No | **Verificare `gate_3_robustness.py`: CV su 3 perturbazioni — debole; aggiungere SPA/White** |
| Gate 5 stress | Sì (circolare) | Sì | Sì (#19) | Stress storico reale 2008/2020/2022 o "non testabile" |
| Cost model / ADV / slippage | Sì (10M e 20B default) | Sì | Parziale | ADV reale; **+ fixed cost $1440 nel net-Sharpe (mancante in Kimi)** |
| **Fixed costs ($1440/anno)** | **No** | No | No | Aggiungere al net-Sharpe |
| Kill-switch in backtest | No (solo live) | No | No | Modellare nel backtest (parity) |
| Walk-forward / OOS | Sì (decorativo) | Sì | Parziale (#nessun test di fitting IS) | WF con fitting reale su IS |
| Reproducibility | Sì (manifest assente) | Sì | Parziale | Elevare priorità; test re-run deterministico |
| Paper/live divergence | No | No | No (NEEDS_RUNTIME_DATA) | Metrica divergenza ≥90gg |
| **LOO ICIR** | **No** (ammesso) | No | No | NEEDS_ADDITIONAL_TECHNICAL_VERIFICATION |

**Note quant chiave:**
- Kimi **non promuove strategie** e **non propone tuning** — corretto.
- **Disallineamento principale:** il verdetto quant centrale "**S4 non ha edge dimostrato**" è stato sostituito da un problema secondario ("stale signals"). Il MP deve ripristinarlo: S4 resta paper-contenuto, promozione bloccata, finché placebo/IC net non lo dimostrano.
- **Gate 3 vero non verificato:** Kimi ha (correttamente) separato la sensitivity-report dalla gate, ma poi **non ha verificato la gate**. La gate usa CV su 3 sole perturbazioni: debole, va rafforzata con correzione multipla.
- **S2/S3/S7:** Kimi conferma i bug ma non trae la conclusione di governance (S2 *non valutabile* su dati sintetici, non "falso alpha"; S3 fix-sizing poi rivalutare; S7 contenere). Il MP deve ereditare i verdetti della Passata 2, non solo i bug.

---

## 8. Functional / Product / Governance Alignment Review

| Tema | Copertura | Qualità evidenza | Gap rimasto | Remediation a livello MP |
|---|---|---|---|---|
| Strategy status SoT | Buona | STRONG | — | `strategy_lifecycle` DB (capability) |
| Gate status SoT | Parziale | MODERATE | Nessuna tabella storica pass/fail | Legare a RB-008/009 |
| Allocation SoT | Buona | STRONG | `_validate_allocations` solo warning | Enforcement hard |
| Paper/live explicit mode | Buona | STRONG | Decisione fonte unica (PO) | RB-003 |
| Config validation | Buona (in §11.C) | STRONG | Non è capability nel roadmap | **Reintegrare RB-007** |
| Config audit | Parziale | MODERATE | Nessun audit dei change | Aggiungere |
| UI truthfulness | Parziale | MODERATE | Item sparsi (regime, PEAD, schedule), no cockpit | **Reintegrare RB-012** |
| Stale data | Non coperto | UNSUPPORTED | Nessun flag staleness operativo | Aggiungere a cockpit |
| Promotion readiness | Parziale | MODERATE | Nessuna dashboard readiness | RB-002 + cockpit |
| PEAD/S7 disclaimer | Coperto (§11.C) | STRONG | Containment come capability | RB-011 (contenere) |
| Risk controls dichiarati vs applicati | Buona | STRONG | — | RB-006 |
| Operator safety | Non coperto come capability | UNSUPPORTED | Cockpit assente | **RB-012** |
| R&D containment | Parziale | MODERATE | Ridotto a "S7 not registered" | RB-011 |

**Sintesi funzionale:** Kimi copre bene i temi *verificabili in un file* (SoT, allocazioni, config, paper/live, PEAD UI), ma i temi *trasversali di prodotto/operatore* (cockpit veritiero, stale data, readiness unificata, monitoring) sono dispersi o assenti. Sono proprio le capability che il blueprint marcava come PRODUCT_RISK. Il MP deve ricomporle.

---

## 9. Test Plan Review

Il test-plan di Kimi (§13, 27 test, **test-before-fix** — corretto) è **di buona qualità** e per i temi che copre è **largamente sufficiente**: cattura i failure mode reali (duplicate BUY, stop-loss assente, kill-switch pre-submit, t+1, expanding-window vol, gate denominator/clamp/n_trials, stress/regime PIT, survivorship, secret scan, audit row, dep consistency).

**Verdetto: test plan approvato per gli item coperti, ma insufficiente nel complesso.** Mancanze:

- **Test mancanti (da aggiungere):**
  - *Reproducibility determinism:* re-run dello stesso backtest → metriche identiche (manca; è il test chiave di RB-008).
  - *Config-change workflow:* non solo range, ma **audit del change** + rifiuto di indebolimento risk-control senza approvazione elevata.
  - *Monitoring/alerting:* alert scatta su fallback rate/PSI/lag/cap-violation/divergenza (assente).
  - *Operator cockpit truthfulness:* test che la UI non mostri come attivo ciò che non lo è (regime, PEAD, schedule) — acceptance test.
  - *Paper-live divergence:* harness di confronto (NEEDS_RUNTIME_DATA).
  - *LOO ICIR contamination:* test che i pesi LOO non usino dati overlapping/futuri.
  - *Gate 3 robustness:* test con correzione multipla (SPA/White), non solo CV su 3 punti.
  - *Backtest parity:* test che il kill-switch sia modellato nel backtest.
- **Test da spostare PRIMA del fix:** tutti quelli di safety (#5-#8) e quant-validity (#12-#21) — Kimi già li mette before-fix, corretto.
- **Test da eseguire DOPO il fix:** falsification quant (S1-F1..F8, S4 placebo/IC) — sono *esperimenti*, non unit test, e vanno dopo i fix di parità/costi (rimando alla Passata 2).
- **Test bloccanti per paper/live:** #5,#6,#7,#8 (paper/live + safety) bloccanti per live; #12-#21 bloccanti per "validated backtest"/promozione.
- **Distinzione mancante:** Kimi non distingue chiaramente **unit/integration/e2e** né segnala dove serve **broker mock**, **synthetic market data PIT fixture**, **frontend test**. Il MP deve assegnare il tipo a ciascun test.

---

## 10. What Kimi Missed

**CRITICAL_MISS**
1. **Tassonomia RB corrotta (RB-007..RB-014 ridefiniti).** Conta perché distrugge la tracciabilità capability→finding→fix→test, che è lo scopo della matrice. Sorgente: blueprint §8. Impatto: il MP rischia di implementare i finding giusti sotto etichette sbagliate e di perdere le capability non mappate. Azione: ri-mappare alla tassonomia canonica (vedi §15).
2. **Operator Safety Cockpit (vero RB-012) assente come capability.** Conta: falsa sicurezza dell'operatore = PRODUCT_RISK/LIVE_BLOCKER. Sorgente: blueprint RB-012. Impatto: si correggono i singoli falsi UI ma non si garantisce un cockpit veritiero. Azione: reintegrare.
3. **Monitoring & Alerting (vero RB-013) assente.** Conta: il degrado silenzioso (fallback/PSI/lag/cap-violation/divergenza) è un failure mode primario. Sorgente: blueprint RB-013. Impatto: paper non osservabile, live cieco al degrado. Azione: reintegrare.

**HIGH_MISS**
4. **Verdetto quant S4 "alpha non valutabile / serve IC>placebo".** Riformulato come "stale signals". Sorgente: quant memo §3/§6. Impatto: rischio di trattare S4 come quasi-pronto. Azione: ripristinare il blocco promozione + falsification.
5. **Reproducibility declassata a P2.** Sorgente: blueprint RB-008, quant memo §10. Impatto: claim di validazione non difendibili. Azione: P0/P1.
6. **Validated Config Change Workflow non è capability nel roadmap.** Sorgente: blueprint RB-007. Impatto: i risk control restano smontabili via UI. Azione: fase dedicata.
7. **Gate 3 (robustness gate vero) non verificato.** Sorgente: quant memo §5. Impatto: si crede coperta una gate che è debole (CV su 3 punti). Azione: verifica + SPA.
8. **RB-011 invertito:** Kimi propone di **cablare S7**, mentre il verdetto è **contenerlo**. Impatto: rischio di portare in operativo una pipeline rotta. Azione: correggere in "contain".

**MEDIUM_MISS**
9. **LOO ICIR non verificato pur essendo reale** (`src/performance/ic.py`, `sentiment.py:334-339`). Impatto: contaminazione possibile nella pesatura ensemble S4. Azione: NEEDS_ADDITIONAL_TECHNICAL_VERIFICATION.
10. **Falso negativo sanitizer** (`src/text/sanitizer.py` esiste). Impatto: priorità mal assegnata; la vera lacuna è RAG/supervisor. Azione: chiudere il falso negativo, ridirigere su RAG/supervisor.
11. **Fixed cost $1440/anno** non considerato nel net-Sharpe. Sorgente: quant memo §4.6. Impatto: net-Sharpe sovrastimato su conto piccolo. Azione: includere.
12. **S4 gate script rotto (D-02)** non pinnato con file:line dell'import/kwargs errati. Impatto: la soglia di promozione resta indefinita e la causa non è tracciata. Azione: pin + fix in MP.
13. **Discrepanza conteggio test (33 vs 109).** Impatto: incertezza sullo stato reale della suite. Azione: clean run riproducibile (NEEDS_RUNTIME_DATA).
14. **Backtest↔Live parity governance** (kill-switch nel backtest, etichetta "pre-risk-control", divergenza) parziale. Azione: capability di parity.

**LOW_MISS**
15. **DR/backup policy** non trattata (era area non analizzata nella review funzionale). Azione: aggiungere a RB-014.
16. **LLM-cron `--dangerously-skip-permissions`** citato come security ma non come *fragilità operativa autonoma* (azioni distruttive). Azione: neutralizzare/sandbox in Phase 0.
17. **Gate report freshness/lifecycle** (datazione, ri-eseguibilità) come governance. Azione: RB-009.

---

## 11. Items Requiring Runtime Data

`NEEDS_RUNTIME_DATA`:
- **Paper-live divergence** (slippage, fill rate, cost diff) ≥90gg — non determinabile staticamente.
- **Conteggio reale fallimenti test** e cause — Kimi riporta 109 fail/2 err (vs 33 della review funzionale): serve un *clean run* in ambiente controllato e riproducibile.
- **Fallback rate FinBERT / PSI / ensemble correlation** in esercizio — metriche runtime per dimensionare gli alert.
- **Uso effettivo di `audit_log`** una volta abilitati i writer (verifica che la catena alternativa resti coerente).
- **Comportamento reale del kill-switch mid-cycle** (drill operativo) — conferma e2e del fail-closed.

## 12. Items Requiring Additional Technical Verification

`NEEDS_ADDITIONAL_TECHNICAL_VERIFICATION`:
- **LOO ICIR contamination:** leggere `src/performance/ic.py` (`compute_icir`) e il flusso pesi in `src/workers/sentiment.py:334-352` — i pesi LOO usano ritorni overlapping o stato modello cross-fold?
- **S4 gate script (D-02):** pin esatto dell'import `load_universe` e dei kwargs `GateConfig` errati in `scripts/run_s4_gate_report.py`; conferma che non gira.
- **S4 `generated_at`:** è publish-time della news o tempo di scoring? (look-ahead potenziale a monte, ingestion).
- **`ALPACA_PAPER` boolean** esiste in `config.py` o c'è solo inferenza da URL? (domanda aperta #6 di Kimi, da chiudere).
- **`src/costs/calculator.py` call-sites:** confermare che NON entri nel sizing di `portfolio_scheduler` (Q9).
- **Gate 3 `gate_3_robustness.py`** + numero/scelta delle perturbazioni: verificare la debolezza CV-su-3 e l'assenza di correzione multipla.
- **Walk-forward fitting:** confermare che non esista alcun fitting per-window più in profondità nella classe.

## 13. Items Requiring Future Quant Experiments

`NOT_READY_NEED_QUANT_EXPERIMENTS` (esperimenti, non verifiche — post-fix, da Passata 2):
- **S1:** rerun t+1 + costi reali+fisso + survivorship-free + SPA/Hansen (S1-F1..F6); è il backtest da rifare per primo.
- **S3:** rerun con sizing PIT + universo survivorship-free (S3-F1/F2) per stabilire se l'edge sopravvive.
- **S4:** shuffled-news/placebo + IC decay + timestamp publish-time (S4-F1..F3) prima di qualsiasi promozione.
- **S2:** con dati opzioni *reali* storici, segno/payoff + tail stress (S2-F1/F2).
- **S7:** event study con consensus EPS PIT esterno + filing body reale (S7-F1..F4).
- **Regime-aware sizing:** moltiplicatori **pre-specificati** validati OOS (no overfit del risk control).

---

## 14. Master Plan Readiness

**Verdict: READY_WITH_GAPS.**

- **Decisioni già sufficientemente supportate** (STRONG evidence, pronte a diventare ticket): tutti i P0 di safety/security (API key, kill-switch 2FA, regime_mult=1.0, bracket off, paper/live dual-source, vol-targeter ordering); SoT + promotion gate (capability già disegnate); execution safety baseline; test infra + audit_log; schedule/calendar; tutti i bug quant di codice (same-bar, ADV, S3, S2, gate 1/2/4, stress/regime circolari, survivorship, WF).
- **Richiedono dati runtime** (§11): divergenza paper-live, conteggio test reale, metriche fallback/PSI per dimensionare alert.
- **Richiedono ulteriore verifica tecnica** (§12): LOO ICIR, S4 gate script, `ALPACA_PAPER`, calculator.py call-sites, Gate 3.
- **Richiedono esperimenti quant futuri** (§13): tutte le falsification S1/S3/S4/S2/S7 — *post-fix*.
- **Possono diventare ticket P0/P1 immediati:** Phase 0 (demuovere S1, ruotare secret, neutralizzare LLM-cron, marcare S7 R&D) + Phase 1 (test verdi, audit_log, docker, CI scan).

**Cosa fare prima di scrivere il Master Plan:** (1) **ri-mappare la tassonomia RB** alla versione canonica del blueprint; (2) **reintegrare RB-012 cockpit e RB-013 monitoring/alerting**; (3) **correggere RB-011 (contenere S7, non cablarlo)**; (4) **elevare reproducibility (RB-008)**; (5) **ripristinare il verdetto S4 (no IC → bloccato)**. Sono operazioni di editing/governance, non nuove verifiche: per questo il giudizio è READY_WITH_GAPS e non NOT_READY.

---

## 15. Recommendations for the Master Plan

**P0 finali consigliati (safety/governance, capitale reale a rischio ora):**
- Demuovere **S1 da live** a supervised paper (atto di governance, non solo disable engine).
- Ruotare la **API key** esposta; neutralizzare/sandbox l'**agente LLM cron** a permessi pieni.
- **Kill-switch fail-closed** + re-check pre-submit + 2FA/cooldown + recovery human-gated (RB-005).
- **Execution safety baseline**: stop-loss verificato e2e, pending-order check (no duplicate BUY), partial-fill (RB-004).
- **Paper/live esplicito** a fonte unica (RB-003).
- **Risk control truthfulness**: cabla regime, vol-targeter pre-constraint, net-cap (RB-006).
- **Validated Config Change Workflow**: bound server-side + audit (RB-007 vero).
- **Calendario fail-closed** (RB-016).
- **Reproducibility manifest** come prerequisito (RB-008 vero, elevato).

**P1 finali consigliati:**
- **Strategy Status SoT** (RB-001) + **Promotion Readiness Gate** (RB-002).
- **Gate Report Lifecycle** (RB-009 vero) + fix bug gate (n_trials, denominatore, clamp) + **Gate 3 SPA**.
- **Backtest↔Live Parity** (RB-010 vero) + metrica divergenza paper-live.
- **Operator Safety Cockpit** (RB-012 vero) + **Monitoring & Alerting** (RB-013 vero).
- **R&D Containment** (RB-011 vero: contenere S7, non cablare) + **RAG/supervisor** per S4.
- **Test & Audit Integrity** (RB-015) + clean run riproducibile.
- Verdetto quant ripristinato per **S4** (no IC → bloccato) e **S2/S3/S7** (R&D).

**Cosa congelare:** promozioni, tuning di parametri, allocazione 10% S4 (trattata come possibile rumore), riabilitazione S2/S3, **cablaggio S7**.

**Cosa può aspettare (P2):** DR/backup policy, refactor broker-adapter, tax-aware P&L, esecuzione VWAP/limit.

**Cosa NON implementare ancora:** nuovo alpha (N1–N4); cablaggio S7 in registry; qualsiasi promozione; "fix" degli script gate senza prima sistemare *input e design statistico* (darebbe falsa conferma).

**Ordine raccomandato delle fasi (allineato a blueprint + Kimi):** Phase 0 stop-worsening → Phase 1 truth (SoT, test verdi, reproducibility) → Phase 2 safety (execution, kill-switch, config, calendar) → Phase 3 validation credibility (parity, gate lifecycle, no-lookahead) → Phase 4 cockpit + monitoring → Phase 5 strategy requalification (post esperimenti quant) → Phase 6 R&D/alpha.

**Decisioni che richiedono il Project Owner:**
- Fonte unica paper/live: env var o URL?
- Stile enforcement cap S4: eccezione hard o workflow di approvazione?
- Meccanismo 2FA kill-switch: Telegram confirm / TOTP / admin UI?
- S7: research-only confermato (raccomandato) o intento paper?
- Costo nel sizing: sottrarre costo atteso all'alpha o budget nel ConstraintEnforcer?
- Policy denominatore gate / `n_trials` / `min_passing_regimes` target.

---

## 16. Final Stop Point

Non ho modificato file, non ho scritto codice, non ho creato patch. Prossimo passo consigliato: produrre **ALEMBIC_REMEDIATION_MASTER_PLAN** usando i quattro documenti di review e questa review-of-review — ri-mappando prima la tassonomia RB alla versione canonica del blueprint, reintegrando le capability mancanti (Operator Safety Cockpit, Monitoring & Alerting), correggendo RB-011 (contenere S7, non cablarlo), elevando la reproducibility e ripristinando il verdetto quant su S4.

---

*Fine OPUS_REVIEW_OF_KIMI_TECHNICAL_VERIFICATION (Passata 4/5). Read-only rispettato: nessun file di sistema modificato, nessun backtest/pipeline/ordine eseguito; sola ispezione mirata per confermare/smentire i punti critici di Kimi. Né Opus né Kimi difesi a priori. Priorità a safety, auditabilità, riproducibilità, idempotenza, chiarezza paper/live, verità della validazione e protezione del capitale.*
