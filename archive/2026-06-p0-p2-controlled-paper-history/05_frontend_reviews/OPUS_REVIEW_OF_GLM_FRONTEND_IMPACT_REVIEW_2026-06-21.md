# OPUS_REVIEW_OF_GLM_FRONTEND_IMPACT_REVIEW_2026-06-21

**Data:** 2026-06-21 · **Modalità:** read-only · **Ruolo:** Strategic Product / Frontend Architecture Arbiter
**Scope:** Review critica della review GLM (`docs/FRONTEND_IMPACT_AND_CUSTOMER_JOURNEY_REVIEW_2026-06-21.md`) + decisione esecutiva sul frontend/operator surface verso il controlled paper.

> Questa NON è una duplicazione della review GLM. È una validazione critica + arbitrato di priorità. Read-only: nessun file di codice modificato, nessuna patch, nessuna autorizzazione a controlled paper / live / promotion.

---

## 1. Executive Summary

La review GLM è **tecnicamente competente e largamente corretta sul gap AS-IS del frontend**: il backend sa molto più di quanto l'UI mostri (readiness, lifecycle, promotion gate, decisions); endpoint readiness/promote/portfolio-status/analytics esistono ma non sono cablati; la catena news→signal→decision→order→PnL non è ricostruibile nell'UI. Questi finding strutturali sono **validi**.

Ma la review GLM contiene due errori sistematici che vanno corretti:

1. **Ha esaminato uno snapshot pre-reconciliation.** Quattro delle sue "contraddizioni" (README P2-05 *Pending*, ARCHITECTURE *NOT_IMPLEMENTED*, `/api/strategies` S1 `"validated"` Sharpe 0.51, P2_STATUS S2 `paper`) erano **già chiuse dal commit `9e1039e`** (e `55cbf56` per il codice P2-05 sottostante). Il suo ticket faro F0-06 ("Reconcile strategy API truth") è **fatto a livello backend**. Quel che resta è un *piccolo residuo FE-only di copy*, non una riconciliazione BE+FE.

2. **Sovrastima "F0 = required before controlled paper".** L'autorità del progetto — `P2_STATUS §Authorization Gates` e `CONTROLLED_PAPER_PREFLIGHT_RUNBOOK §14/§18` — definisce i gate del controlled paper come **dry-run cycle + readiness all-green (via API) + kill-switch rehearsal + evidence package (15 artefatti) + PO sign-off**, tutti via curl. Il runbook §18 *stabilisce esplicitamente che l'assenza di una cockpit UI è accettabile per il dry-run e la fase iniziale di paper*. **Quindi nessun item frontend GLM è un vero blocker del controlled paper.**

**Verdetto netto:** il controlled paper può partire con **zero frontend F0**, purché il preflight runbook passi. Il lavoro frontend è **operator-experience e safety-hygiene**, non un gate. Gli unici item che chiederei al PO di richiedere prima che un operatore **usi la dashboard durante il paper** sono fix FE-only, cheap, safety/copy (non lasciare che l'UI contraddica la verità di autorizzazione che il runbook impone). La proposta più pericolosa di GLM — **promote/approve/demote come F0** — la **respingo per la fase paper**: la promotion non è autorizzata, e una superficie di promotion one-click contraddice la postura fail-closed.

---

## 2. GLM Review Validation (TASK 1)

| GLM Finding | Still Valid? | Already Fixed? | Evidence | Impact | Notes |
|---|---:|---:|---|---|---|
| No readiness UI (`/api/system/readiness` mai chiamato) | ✅ Sì | No | `rg readiness frontend/src` → 0 hit | Operatore non vede degraded/blocked in UI | Runbook §18 accetta curl come interim |
| No strategy governance UI (mode/promotion_blocked/gate_report_id…) | ⚠️ Parziale | Parziale | API ora ritorna `status/mode/promotion_blocked/live_authorized/data_quality_warning` (`strategies.py:63-77`), ma il tipo FE `Strategy` (`api/strategies.ts:3-14`) li omette | UI non mostra nessuna verità di autorizzazione | Verità BE fissata da `9e1039e`; **FE non la consuma** |
| No news-to-trade trace | ✅ Sì | No | `signals.py` ritorna dict sentiment Redis, nessun join `news_id` | Catena di audit spezzata | Reale; richiede `news_id` (BE) |
| Order lifecycle superficiale | ✅ Sì | No | `Trading.tsx` solo status badge | Niente reject/partial/stop-loss leg | Richiede BE enrichment |
| Missing reject/partial/stop-loss visibility | ✅ Sì | No | idem | Gap di audit | BE enrichment |
| Missing PnL attribution by strategy/news/signal | ✅ Sì | No | Nessun endpoint, nessuna pagina | Attribution cieca | BE nuovo + FE |
| why-trade/why-skip non strutturato | ✅ Sì | No | `execution_decisions` espone solo `reason` free-text (campi runbook §10) | Decisioni non auditabili a macchina in UI | Viewer read-only è FE-only; struttura è BE |
| No operator inbox/alerts | ✅ Sì | No | Nessun endpoint alerts | Niente alerting azionabile in UI | Endpoint BE + FE |
| Safety risks in Config/Admin | ✅ Sì | No | `Admin.tsx:8` MODES include `full_auto` one-click; `Config.tsx:102` slider stop-loss `max=0.5` (50%), save immediato | Indebolimento accidentale dei risk controls | Guardrail FE-only |
| Dead client APIs non cablate | ✅ Sì | No | `analytics.ts` by-symbol/by-dimension **non importato da nessuna pagina** (confermato); `/portfolio/status`, `postmortem` senza client/pagina | Capacità persa | FE-only per cablare |
| **`/api/strategies` hardcoda S1 "validated" Sharpe 0.51** | ❌ No | **✅ FIXED** | `strategies.py:63-77` ora `status:"supervised_paper", promotion_blocked:True, live_authorized:False, data_quality_warning`; commit `9e1039e` | — | **Finding stale.** Residuo: HelpButton FE dice ancora "VALIDATA" |
| **README P2-05 Pending** | ❌ No | **✅ FIXED** | `README.md:27` "P2-05 … Complete (`55cbf56`)"; `9e1039e` | — | Finding stale |
| **ARCHITECTURE P2-05 NOT_IMPLEMENTED** | ❌ No | **✅ FIXED** | `ARCHITECTURE.md:618` "Resolved Safety Items (IMPLEMENTED)"; `9e1039e` | — | Finding stale |
| **P2_STATUS S2 = paper** | ❌ No | **✅ FIXED** | `P2_STATUS:55-58` S2 `disabled`; `9e1039e` | — | Finding stale |
| Badge test count 2353 vs 2386/2393 | ❌ No | **✅ FIXED** | `README.md` 2393; `9e1039e` | — | Finding stale |
| Docs.tsx hardcoded (S2 −0.55) può divergere | ✅ Sì (latente) | N/A | `Docs.tsx:234` S2 "−0.55 disabled" — attualmente *coerente* con la verità | Basso ora; rischio di divergenza futuro | Rischio di manutenibilità, **non un errore live** |
| API.md stale (7+ endpoint fantasma, path portfolio errato, shape health) | ⚠️ Probabilmente valido | Non verificato | GLM Appendice A; non ri-auditato in questo pass | Solo docs; non blocca paper (il runbook è il doc operativo) | Confermare in un pass docs |

**Rischio residuo sul set "già fixato":** la verità API è riconciliata, ma il **frontend presenta ancora la vecchia storia** (Strategies HelpButton: *"S1 … VALIDATA (OOS Sharpe 0.51, 5/5 gate passati)"*, *"S4 … in esecuzione live"*). Quindi la conseguenza *misleading-UX* che GLM segnalava (§11.1) **è ancora live nell'UI**, anche se l'API è corretta. Questo è il singolo item più azionabile, ed è FE copy-only.

---

## 3. Findings Already Fixed vs Still Valid

- **Già fixato (chiudere, non azionare):** F0-06 riconciliazione backend; contraddizioni README/ARCHITECTURE/P2_STATUS su P2-05 + S2; badge test-count; S1 "validated" all'API.
- **Fixato a BE, residuo a FE (azionare, cheap):** consumare `promotion_blocked`/`data_quality_warning`; eliminare copy hardcoded "VALIDATA"/"S4 live".
- **Ancora pienamente valido (azionare, prioritizzato sotto):** no readiness UI; no governance display; news-to-trade trace spezzato; order lifecycle superficiale; attribution mancante; why-trade non strutturato; no alerts; safety surface; cablaggio analytics/postmortem/portfolio-status morto.
- **Valido ma latente/basso (rimandare):** Docs.tsx hardcoding; staleness API.md.

---

## 4. Controlled Paper Blocker Assessment (TASK 2)

Anchor: **Runbook §14 Go/No-Go + §18** definiscono i gate; nessuno menziona la React app.

| Proposta GLM | Classificazione | Razionale |
|---|---|---|
| F0-06 reconcile API truth | **DONE (non un blocker)** | Chiuso da `9e1039e` |
| Fix copy misleading "VALIDATED"/paper-vs-live + surface promotion_blocked | **STRONGLY_RECOMMENDED_BEFORE_DAY_1** | L'UI non deve contraddire l'autorizzazione che il runbook impone; cheap, FE-only |
| F0-07 guardrail Config/Admin safety surface | **STRONGLY_RECOMMENDED_BEFORE_DAY_1** | Superficie mutante; account paper limita il blast radius → non blocker duro |
| F0-01 readiness dashboard/banner | **RECOMMENDED_DURING_FIRST_30_DAYS** (banner minimo: before day 1) | Runbook §18 accetta alias curl come interim; il banner elimina lo step manuale più error-prone |
| F0-04 why-trade/why-skip strutturato | **RECOMMENDED_DURING_FIRST_30_DAYS** | Audit durante paper usa `/api/system/decisions` + DB; viewer read-only presto, struttura dopo |
| F0-05 order lifecycle reject/partial/stop-loss | **RECOMMENDED_DURING_FIRST_30_DAYS** | Alpaca paper dashboard + DB coprono l'audit; richiede BE enrichment |
| F0-02 governance table (read-only) | **REQUIRED_BEFORE_OR_DURING_PREFLIGHT** (sottoinsieme campi già ritornati) | Si fonde nel fix copy; campi ricchi = primi 30 giorni |
| F0-03 promote/approve/demote **UI** | **REJECT_OR_DEFER (BEFORE_LIVE_RECONSIDERATION, gated)** | Promotion esplicitamente NON autorizzata; superficie one-click insicura in questa fase |
| F0-08 de-hardcode Docs.tsx | **LATER** (sottoinsieme copy si fonde nel fix F0) | Attualmente coerente; basso valore pre-paper |
| Attribution / news-trace / alerts / paper-program dashboard | **BEFORE_LIVE_RECONSIDERATION** | Auditabilità avanzata; non serve per una giornata di paper supervisionato |

**Conclusione:** set `BLOCKS_CONTROLLED_PAPER` dal frontend = **∅ (vuoto)**. I blocker sono i gate operativi del runbook stesso (dry-run, kill-switch rehearsal, evidence, PO sign-off).

---

## 5. Minimum Viable Operator Surface (TASK 3)

**Q1 — Serve una cockpit UI prima del controlled paper?** **No.** API + runbook + `ADMIN_API_KEY` + gli alias curl documentati (runbook §18) bastano per dry-run e paper iniziale. È la decisione del progetto stesso, e concordo.

**Q2 — Se si usa una UI minima, quali schermate sono indispensabili?** Solo schermate che **non devono ingannare**: (a) un readiness banner, (b) una vista strategie che mostri lo stato reale di autorizzazione, (c) una superficie Admin/Config che non si possa toccare per sbaglio indebolendo la safety. Tutto il resto è opzionale durante il paper.

**Q3 — Dati che devono essere visibili per non ingannare l'operatore:** strategy `mode`/`promotion_blocked`/`data_quality_warning`; "le metriche sono uno snapshot storico stale — NON autorizzano promotion/paper/live"; stato paper-vs-live esplicito; "HTTP 200 ≠ healthy" su readiness; gross-vs-net sul PnL.

**Q4 — Azioni UI da tenere disabilitate/protette:** promote/approve/demote (nascoste in paper phase); mode `full_auto` (disabilitato o double-confirm); kill-switch reset (solo OTP, mai one-click); save Config di stop-loss>10%/drawdown>10% (confirm dialog); toggle single-model ensemble (confirm).

**Q5 — Copy safety-critical:** "supervised_paper", "promotion_blocked", "R&D", "paper ≠ live", "BACKTEST = storico, non capitale reale", "degraded (HTTP 200 ma flag unhealthy)".

| Minimum Surface | Required Before Paper? | Existing API? | FE-only? | Backend Needed? | Rationale |
|---|---:|---:|---:|---:|---|
| Strategy authorization truth (status/promotion_blocked/data_quality_warning) | Before day-1 (recommended) | ✅ (ritornato post-`9e1039e`) | ✅ | No | UI deve combaciare con la verità del runbook |
| Readiness banner (semantica degraded/blocked) | Recommended (curl interim OK) | ✅ `/api/system/readiness` | ✅ | No | Elimina lo step manuale più error-prone |
| Safety-surface guardrails (full_auto, slider, kill reset) | Before day-1 (recommended) | ✅ admin/config | ✅ (tiny BE opt) | No | Previene indebolimento accidentale |
| Paper-vs-live + label gross/net | Before day-1 (recommended) | n/a | ✅ | No | Copy anti-inganno |
| Decisions viewer (read-only) | First 30 days | ✅ `/api/system/decisions` | ✅ | No | Audit senza curl |
| Governance rich fields / order lifecycle / attribution | First 30 days → pre-live | ⚠️/❌ | ❌ | Sì | Richiede enrichment |

---

## 6. Review of GLM F0 Backlog (TASK 4)

| GLM F0 Item | Opus Decision | New Priority | Reason | Dependency | Acceptance Criteria |
|---|---|---|---|---|---|
| F0-01 Readiness Dashboard + banner | **Split** | Banner=before day-1; full dashboard=F1 | Il banner è la slice cheap ad alto valore; la dashboard può aspettare | `/api/system/readiness` (pronto) | Banner globale: ready/degraded/blocked; HTTP 200+unhealthy rende **degraded**, non verde |
| F0-02 Strategy Governance table | **Split / downgrade** | Campi read-only già ritornati=F0; campi ricchi=F1(BE) | La verità BE esiste per i campi base | strategies API (base pronto; ricchi = BE) | Mostra mode, promotion_blocked, data_quality_warning; niente "validated" |
| F0-03 Promote/Approve/Demote UI | **Reject for paper / defer** | BEFORE_LIVE_RECONSIDERATION (gated) | Promotion NON autorizzata; one-click promotion contraddice il fail-closed | promotion endpoints (esistono) | Nascoste in paper; quando abilitate: confirm + audit + 422 esposto |
| F0-04 Why-Trade/Why-Skip strutturato | **Split** | Viewer read-only=F1(FE); struttura=F1/F2(BE) | Audit decisioni coperto da API/DB durante paper | `/api/system/decisions` (pronto); enrichment (BE) | MVP: tabella tick_time/symbol/decision/reason cablata |
| F0-05 Order lifecycle + reject/partial/stop-loss | **Downgrade** | RECOMMENDED_DURING_FIRST_30_DAYS | Alpaca paper + DB coprono l'audit; richiede BE | orders enrichment (BE) | reject_reason/partial_qty/stop-loss leg visibili quando BE pronto |
| F0-06 Reconcile strategy API truth | **Già fatto (BE); tieni residuo FE** | F0 (FE copy-only) | `9e1039e` ha fixato l'API; il copy FE dice ancora "VALIDATA" | nessuna | Rimuovere hardcode "VALIDATA/Sharpe 0.51/S4 live"; consumare i campi reali |
| F0-07 Guardrail Config/Admin safety | **Keep** | STRONGLY_RECOMMENDED_BEFORE_DAY_1 | Superficie safety mutante | nessuna (opt BE) | Confirm su stop-loss>10%/dd>10%; disable/confirm `full_auto`; reset kill solo OTP |
| F0-08 De-hardcode Docs.tsx | **Downgrade/split** | Sottoinsieme copy=F0; de-hardcode completo=F2/F3 | Attualmente coerente; basso valore pre-paper | API claims (dopo) | Sottoinsieme ad alto valore confluito nel fix copy F0 |

---

## 7. Safety / Misleading UX Risks (TASK 5)

| Risk | Surface | Consequence | Severity | Fix | Priority |
|---|---|---|---|---|---|
| "S1 … VALIDATA (Sharpe 0.51, 5/5 gate)" hardcoded | Strategies HelpButton (`Strategies.tsx:135`) | L'operatore crede S1 autorizzata nonostante `supervised_paper`/`promotion_blocked` | **Critical** | Rimuovere copy; mostrare status reale + data_quality_warning | F0 |
| "S4 … in esecuzione live con allocazione 10%" | Strategies HelpButton | "live" implica capitale reale; S4 è paper/promotion_blocked | **High** | Riformulare a paper; rimuovere "live" | F0 |
| Tipo FE omette `promotion_blocked`/`data_quality_warning` | `api/strategies.ts` | Verità di autorizzazione invisibile anche se l'API la ritorna | **High** | Estendere tipo; render badge + warning | F0 |
| `full_auto` one-click | `Admin.tsx:8` MODES | Ordini eseguono senza approvazione; pericoloso se le cred passano a live | **High** | Disabilitare o double-confirm; richiedere abilitazione esplicita | F0 |
| Slider stop-loss `max=0.5` (50%), save immediato | `Config.tsx:102` | Risk control indebolito silenziosamente | **High** | Cap a max sano; confirm >10%; save esplicito | F0 |
| Reset kill-switch non OTP-guarded in UI | Admin | Bypass di cooldown/audit | Medium | Reset solo OTP; mai toggle raw | F1 |
| Tabella gates tutta-PASS senza contesto staleness | Strategies | "all gates passed" letto come autorizzazione corrente | Medium | Banner: "stale snapshot — non autorizza" | F0/F1 |
| HTTP 200 mostrato come healthy | (futura readiness UI) | Stato degraded letto come OK | **High** (quando costruita) | Render degraded/blocked dai flag, non dallo status code | F1 banner |
| Gross PnL senza net/costi | Overview/Performance | Profittabilità sovrastimata | Medium | Label "Gross (pre-costi)"/"Net"; mostrare cost drag | F1 |
| `paper`/`supervised_paper` ambiguo | Sidebar/Admin | Paper confuso con live-ready | Medium | Tooltip glossario; label consistenti | F0 copy |
| Claim statici Docs.tsx | Docs page | Divergenza futura da config/API | Low | De-hardcode da API | F2/F3 |

---

## 8. Backend Dependency Review (TASK 6)

### FE-only quick wins
Readiness banner (`/api/system/readiness`), strategy authorization fields (già ritornati), decisions viewer (`/api/system/decisions`), analytics by-symbol/by-dimension (client morto → cablare), trade postmortem (`/api/trades/postmortem/{id}`), portfolio status (`/portfolio/status`), label/copy più sicuri, hiding/confirm dei controlli pericolosi.

### Backend enrichment required
why-trade/why-skip strutturato; `news_id`; strategy attribution nelle decisions; health-state-at-decision; `gate_report_id`/`degradation_ratio`/`historical_stress_status` nello strategies API; order reject reason/partial/stop-loss leg; alerts endpoint; divergence endpoint; PnL by strategy/signal/news; exposure cap-violation feed.

| Capability | Existing Backend? | Existing Frontend? | FE-only? | Backend Required? | Priority | Suggested Owner |
|---|---:|---:|---:|---:|---|---|
| Readiness banner | ✅ | ❌ | ✅ | No | F0/F1 | FE |
| Strategy authorization fields | ✅ (post `9e1039e`) | ❌ | ✅ | No | F0 | FE |
| Decisions viewer (read-only) | ✅ | ❌ | ✅ | No | F1 | FE |
| Analytics by-symbol/by-dimension | ✅ | ⚠️ client morto | ✅ | No | F1 | FE |
| Trade postmortem | ✅ | ❌ | ✅ | No | F1 | FE |
| Portfolio status | ✅ | ❌ | ✅ | No | F1 | FE |
| Governance rich fields (gate_report_id/degradation/stress) | ⚠️ in registry/DB | ❌ | ❌ | **Sì** | F1 | BE→FE |
| why-trade strutturato + news_id + health-at-decision | ❌ | ❌ | ❌ | **Sì** | F1/F2 | BE |
| Order reject/partial/stop-loss leg | ⚠️ | ⚠️ badge | ❌ | **Sì** | F1 | BE→FE |
| Alerts inbox | ❌ | ❌ | ❌ | **Sì** | F1/F2 | BE+FE |
| Divergence feed | ⚠️ interno+Telegram | ❌ | ❌ | **Sì** | F2 | BE+FE |
| PnL by strategy/signal/news | ❌ | ❌ | ❌ | **Sì** | F2 | BE+FE |
| Exposure cap-violation feed | ⚠️ enforce interno | ❌ | ❌ | **Sì** | F2 | BE+FE |

---

## 9. Final Prioritized Backlog (TASK 7)

### F0 — Before PO sign-off / before operator uses dashboard in paper (4 ticket — solo indispensabili)

| ID | Title | Type | Owner | User Value | Scope | Acceptance Criteria | Blocks Paper? |
|---|---|---|---|---|---|---|---|
| F0-1 | Surface strategy authorization truth + delete misleading copy | Safety/Governance + Docs/Copy | FE | L'operatore non può scambiare S1/S4 per autorizzate | Estendere tipo `Strategy` con mode/promotion_blocked/live_authorized/data_quality_warning; render badge+warning; rimuovere testo HelpButton "VALIDATA/Sharpe 0.51/S4 live"; gates mostrano "stale snapshot — non autorizza" | FE-only; usa campi che l'API già ritorna | No (recommended pre-sign-off) |
| F0-2 | Readiness banner | FE-only | FE | Vede degraded/blocked a colpo d'occhio | Banner globale da `/api/system/readiness`; HTTP 200+unhealthy ⇒ degraded (non verde); link al runbook | Banner rende 3 stati + tooltip flag | No |
| F0-3 | Guardrail mutating safety surface | Safety/Governance | FE | Non può indebolire i risk controls per sbaglio | Disable/double-confirm `full_auto`; confirm stop-loss>10%/dd>10%; cap slider stop-loss; reset kill solo OTP; confirm toggle single-model | Tutti e quattro i guard presenti + test | No |
| F0-4 | Paper-vs-live + gross/net labeling pass | Docs/Copy | FE | Nessun inganno su capitale/performance | Tooltip consistenti paper/supervised_paper/R&D; "BACKTEST = storico"; label Gross vs Net PnL | Checklist copy audit passa | No |

### F1 — During first 30 days of controlled paper (max 8)

| ID | Title | Type | Owner | User Value | Scope | Acceptance Criteria | Blocks Paper? |
|---|---|---|---|---|---|---|---|
| F1-1 | Decisions viewer (read-only) | FE-only | FE | Why-trade/why-skip senza curl | Cablare `/api/system/decisions` a una tabella | tick_time/symbol/decision/reason; filtro per decision | No |
| F1-2 | Governance rich fields | FE+BE | BE→FE | Vede gate_report_id/last_validation/degradation/stress | Ritornare i campi dal registry; render read-only | Campi presenti in API + tabella | No |
| F1-3 | Wire analytics by-symbol/by-dimension | FE-only | FE | Attribution by symbol/regime/hour | Ripristinare tab Analytics usando gli endpoint esistenti | Tab rende entrambe le dimensioni | No |
| F1-4 | Trade postmortem drill-down | FE-only | FE | Diagnosi per-trade | Cablare `/api/trades/postmortem/{id}` | Drill-down mostra diagnosi | No |
| F1-5 | Order reject/partial/stop-loss visibility | FE+BE | BE→FE | Audit ordini | Enrich orders; render lifecycle | reject_reason/partial_qty/stop-loss leg visibili quando BE pronto | No |
| F1-6 | Structured why/skip + news_id + health-at-decision | BE-enrichment | BE | Decisioni auditabili a macchina | Aggiungere colonne alle decisions | Colonne popolate; test | No |
| F1-7 | Fallback-rate + beat-lag surfaced | FE+BE | BE→FE | Vede trend fallback/lag modelli | Piccolo endpoint/serie + widget SystemLog | Rate visibile, non free-text | No |
| F1-8 | Alerts / operator inbox | FE+BE | BE+FE | Alert azionabili in-app | Alerts endpoint + pagina | active/historical, severity, link runbook | No |

### F2 — Before live reconsideration (max 8)

| ID | Title | Type | Owner | User Value | Scope | Blocks Paper? |
|---|---|---|---|---|---|---|
| F2-1 | PnL by strategy/signal/news | FE+BE | BE+FE | Quale sleeve fa/perde soldi | endpoint + pagina attribution | No |
| F2-2 | News-to-trade trace | FE+BE | BE+FE | Audit end-to-end | news_id join + timeline | No |
| F2-3 | Paper-program dashboard | FE+BE | BE+FE | Giorni/90, divergence, evidence export | nuova pagina | No |
| F2-4 | Divergence feed UI | FE+BE | BE+FE | drift paper/backtest/live | endpoint + view | No |
| F2-5 | Strategy governance **actions** (gated) | Safety/Governance | FE | Promote/approve/demote quando autorizzato | cablare endpoint dietro confirm+audit, nascoste fino a live reconsideration | No |
| F2-6 | Full Docs.tsx de-hardcode | FE-only | FE | Nessuna divergenza doc | claim da API | No |
| F2-7 | Audit-trail/evidence-pack export | FE+BE | BE+FE | Evidence riproducibile | export endpoint + UI | No |
| F2-8 | Kill-switch OTP/recovery + cooldown UI | FE-only | FE | Flow di recovery sicuro | UI recovery-token | No |

### F3 — Later
Grafana unification, feedback-loop history, counterfactual per-trade, multi-strategy sensitivity compare, multi-account view.

### Reject / Defer
- **GLM F0-03 promote/approve/demote UI come F0 pre-paper → REJECT.** La promotion è esplicitamente non autorizzata; esporre solo a F2-5, gated.
- **GLM "readiness/governance/why-trade sono blocker del controlled paper" → REJECT della classificazione.** Runbook §18 accetta già l'operatività via API.
- **GLM F0-04 why-trade strutturato completo come pre-paper → DEFER** l'enrichment BE a F1/F2; spedire il viewer read-only (F1-1) presto.
- **GLM F0-08 de-hardcode Docs.tsx completo come F0 → DEFER** a F2/F3 (solo sottoinsieme copy in F0-1/F0-4).

---

## 10. Recommended Implementation Sequence (TASK 8)

1. **F0-1 — Strategy authorization truth + copy.** *Perché prima:* massimo valore safety, FE-only, usa campi che l'API già ritorna post-`9e1039e`; chiude il rischio misleading-UX ancora live. *Files:* `frontend/src/api/strategies.ts`, `frontend/src/pages/Strategies.tsx`. *Tests:* render test verifica che `promotion_blocked`/`data_quality_warning` siano mostrati e nessuna stringa "validated/VALIDATA". *Stop point:* PR merged; nessun cambio behavior/BE.
2. **F0-2 — Readiness banner.** *Perché:* elimina lo step curl manuale più error-prone. *Files:* nuovo metodo `api/system.ts`, componente banner, `Layout.tsx`. *Tests:* rendering degraded quando un flag è false sotto HTTP 200. *Stop:* merged.
3. **F0-3 — Safety-surface guardrails.** *Perché:* previene indebolimento accidentale prima di qualsiasi sessione paper. *Files:* `Admin.tsx`, `Config.tsx`. *Tests:* i confirm dialog scattano; full_auto gated. *Stop:* merged.
4. **F0-4 — Labeling pass.** *Perché:* copy anti-inganno, nessuna logica. *Files:* copy Overview/Performance/Sidebar/Admin. *Tests:* snapshot/string check. *Stop:* merged.
5. **F1-1 — Decisions viewer (read-only).** *Perché:* il maggior guadagno di auditabilità, FE-only. *Files:* `api/system.ts`, nuovo tab Decisions. *Tests:* tabella rende da mock. *Stop:* merged.
6. **F1-3 / F1-4 — Cablare analytics morto + postmortem.** *Perché:* recuperare capacità già costruita, FE-only. *Tests:* tab/drill-down render. *Stop:* merged.
7. **Poi i BE-dependent F1-2 / F1-5 / F1-6 / F1-7 / F1-8**, ciascuno come PR a sé con test BE prima, FE dopo. *Regola:* readiness/decisions/governance prima dell'attribution sofisticata.
8. **F2** solo dopo ri-audit di riconciliazione doc + dry-run all-green + PO sign-off. Le governance **actions** (F2-5) per ultime e gated.

Vincoli rispettati: PR piccoli, no big-bang dashboard, no cambio behavior backend se il ticket non è esplicitamente BE, test per ticket, no live/promotion, copy distingue authorization state da performance metrics.

---

## 11. Go / No-Go Impact (TASK 9)

1. **Il controlled paper può partire senza frontend F0, se il preflight API/runbook passa?** **Sì.** Per `P2_STATUS §Authorization Gates` e runbook §14/§18, i gate sono dry-run + readiness(API) + kill-switch rehearsal + evidence package + PO sign-off — tutti curl-based. Nessun item frontend è una precondizione del runbook.
2. **Quali frontend F0 sono davvero precondizioni per il PO?** **A rigore, nessuna.** *Raccomando* al PO di richiedere **F0-1 (authorization truth/copy)** e **F0-3 (safety guardrails)** *solo se l'operatore guarderà la dashboard durante il paper* — così l'UI non contraddice l'autorizzazione che il runbook impone, e non può essere fat-fingered indebolendo la safety. Se l'operatore lavora esclusivamente via curl, anche queste slittano a day-1.
3. **Primi 30 giorni di paper:** F0-2 readiness banner, F1-1 decisions viewer, F1-2 governance rich fields, F1-3 analytics wiring, F1-4 postmortem, F1-5 order reject/partial visibility, F1-7 fallback-rate, F1-8 alerts.
4. **Solo prima della live reconsideration:** F2-1 attribution by strategy/news, F2-2 news-to-trade trace, F2-3 paper-program dashboard, F2-4 divergence UI, F2-5 gated governance actions, F2-7 evidence export, F2-8 kill-switch OTP UI.

Non autorizzo il controlled paper. Raccomando al PO di trattare F0-1/F0-3 come *igiene richiesta*, non come gate aggiuntivi — i gate esistenti del runbook restano il percorso di autorizzazione.

---

## 12. Recommendations to Sonnet

- Inizia da **F0-1**; è l'unico item che fixa un difetto safety/UX *attualmente live* ed è FE puro usando campi che l'API già ritorna post-`9e1039e`. Non "ri-riconciliare" lo strategy API — quel lavoro backend è fatto.
- Tratta readiness/decisions/governance display come **read-only** fino alla live reconsideration. **Non** aggiungere pulsanti promote/approve/demote in questa fase.
- Ogni PR: un ticket, test inclusi, nessun cambio behavior backend se il ticket non è esplicitamente BE-enrichment.
- Regola copy: mai rendere "validated", "production" o "live" per una strategia `promotion_blocked`/`supervised_paper`/`paper`. Accoppia sempre le metriche di backtest con il warning di stale-snapshot.
- Rendi la readiness dai **flag**, mai dallo status HTTP; HTTP 200 + un flag unhealthy deve mostrare **degraded**.
- Non costruire la dashboard paper-program unificata presto; sequenzia superfici piccole (banner → decisions → governance) prima.

---

## 13. Stop Point

Questa è una review strategica read-only della review GLM e del frontend/operator surface. Non ho modificato file, non ho scritto codice, non ho autorizzato controlled paper, non ho autorizzato live trading, non ho promosso strategie e non ho iniziato P3/P4.

> *Nota: l'unico file scritto è questo documento di report, esplicitamente richiesto dall'utente. Nessun file di codice frontend/backend, config o migration è stato toccato.*
