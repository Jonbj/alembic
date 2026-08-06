# GLOBAL_ISSUES — Difetti trasversali dell'audit strategie

**Audit:** Alembic Strategy Audit
**Data:** 2026-08-04
**Scope:** S1, S2, S3, S4, S7 (5 strategie auditate)
**Metodo:** sintesi cross-strategy dei REPORT_S1..S7 + fasi 05-07.

Questo documento raccoglie i **difetti trasversali** che emergono confrontando
le 5 strategie: pattern che si ripetono, deficit di governance comuni, e
deficit di design alpha condivisi. Ogni issue è classificata per severità e
traccia le strategie colpite.

## Verdetti riassunti (per contesto)

| Strategia | Implementazione | Fenomeno | Live? | Bug critici |
|---|---|---|---|---|
| S1 TimeSeriesMomentum | DECAYED | DECAYED | sì (paper) | dead config, look-ahead pannello, gate banale |
| S2 VRPStrategy | NEGATIVE | DECAYED | no (dead config) | look-ahead fwd_21d, dead config, IV stale |
| S3 CrossSectionalMomentum | UNPROVEN (non fedele) | UNPROVEN (NON decaduto) | no (morto) | pannello bilanciato look-ahead, survivorship, dead config |
| S4 NewsDrivenTactical | NEGATIVE (IC) | DECAYED | **sì (paper, esegue)** | gate drift backtest, fallback sintetico |
| S7 PEAD | NEGATIVE | DECAYED | no (rimossa) | carburante zero, universo competuto, forma debole |

---

## GI-1 — Dead config `from_yaml` mai chiamato (HIGH, trasversale)

**Strategie colpite:** S1 (BUG-1), S2 (BUG-D), S3 (BUG-B). **Non S4** (wired via
`trading.yaml`), **non S7** (rimossa).

**Pattern:** ogni strategia definisce una classe `XxxConfig` con un metodo
classmethod `from_yaml` che parsifica `config/strategies.yaml`, MA il metodo
**non ha call site** nel codice runtime. Le strategie vengono istanziate con
`XxxConfig()` (default) o non istanziate affatto. → la config yaml è
**documentazione morta**: modificare i parametri in `strategies.yaml` non
cambia il comportamento runtime.

**Conferma (S3 repro_2, AST walk):** `from_yaml` definito, **0 call site**,
istanziazioni con `XxxConfig()` bare.

**Impatto:** l'operatore crede di poter tarare le strategie via yaml (sleeve
cap, soglie, orizzonti) MA i default hard-coded governano. Qualsiasi
esperimento di tuning via yaml è **silenziosamente ininfluente**. Questo è il
**difetto di controllabilità più grave** del sistema.

**Raccomandazione:** audit di tutti i `from_yaml` call site (grep); o wired
li al runtime, o rimuovili e documenta esplicitamente "config morta,
modificare i default in `src/strategies/<id>/strategy.py`". S4 è il modello
corretto (`trading.yaml risk.s4_fixed_slot_sizing_enabled` realmente letto).

## GI-2 — Backtest invalidato da look-ahead / survivorship (HIGH, backtest)

**Strategie colpite:** S1 (BUG-2 pannello bilanciato), S2 (BUG-A fwd_21d),
S3 (BUG-A pannello bilanciato, BUG-C survivorship). **S4** ha gate drift
backtest (BUG-A) + fallback sintetico (BUG-B). **S7** mai backtest WF.

**Pattern:** i backtest delle strategie **non sono rappresentativi** del live
per difetti sistematici:
- **Pannello bilanciato look-ahead** (S1, S3): la data di primo ingresso
  (`first_admitted_date`) è gated da ticker IPO future, non da informazioni
  PIT-osservabili → look-ahead nella costruzione del pannello.
- **Forward window futuri** (S2): `fwd_21d` usa prezzi futuri non disponibili
  alla data decisionale.
- **Survivorship bias** (S3): universo di 50 sopravvissuti (ticker ancora
  esistenti nel 2026) → backtest sovrastima.
- **Gate drift backtest/live** (S4): backtest non replica l'entry gate ratchet
  live (0.30), usa solo `min_score=0.10` → over-admit.
- **Fallback sintetico** (S4): backtest su segnali RNG casuali senza flag →
  misura rumore indistinguibile da alpha.

**Impatto:** qualunque OOS Sharpe / metrica calcolata dai backtest S1/S2/S3/S4
è **non affidabile**. Le decisioni di promozione basate su questi backtest
sono a rischio. Il progetto lo riconosce parzialmente (`promotion_blocked=true`
per S4) MA S1 è live basandosi su backtest invalidati.

**Raccomandazione:** prima di qualunque decisione di promozione/riduzione,
validare i backtest con un audit look-ahead/survivorship formale (PIT-strict).
Il backtest S4 (gate drift + fallback) va chiuso prima di ri-validare l'IC.

## GI-3 — Soglie gate banali min_sharpe=0.0 (MEDIUM, governance)

**Strategie colpite:** S1 (milestone_c `oos_sharpe≥0.0`), S3 (BUG-D
`milestone_c` accetta Sharpe=0.0). **S4** ha gate IC>placebo (P0-13) MA non
confermato. **S7** ha kill criterion decision-grade (PO-5) — il modello corretto.

**Pattern:** i gate di promozione di alcune strategie ammettono
**Sharpe=0.0** (no-op) come PASS. Un gate che accetta "nessun rendimento" non
è un gate — è un'approvazione automatica. S7 è l'eccezione: PO-5
pre-registrato "Se POC-2 FAIL → REMOVE" con threshold IC>0.10 (vs POC-2
IC=+0.012 → FAIL pulito).

**Impatto:** gate banali permettono la promozione di strategie senza edge
misurato. S1 è live con gate `oos_sharpe≥0.0`. S3 sarebbe stata promossa con
Sharpe=0.0 se fosse stata wired.

**Raccomandazione:** tutti i gate di promozione devono avere threshold
**pre-registrati >0** (Sharpe min, IC min, hit-rate min) con kill criterion
esplicito. S7/PO-5 è il modello. Applicare a S1/S4 (che sono live con
Sharpe≈0 / IC<0).

## GI-4 — Forma debole trasversale: long-only + polarity + large-cap + orizzonte mismatch (HIGH, design alpha)

**Strategie colpite:** S1 (long-only momentum, orizzonte 252g, large-cap),
S4 (long-only sentiment, polarity, tattico giornaliero, large-cap), S7
(long-only beat, polarity tone, hold 20d, large-cap). **S3** long-only (non
fedele al residual momentum long-short). **S2** long-SPY (non VRP).

**Pattern:** **tutte** le strategie implementano la **gamba debole** del
rispettivo fenomeno:
- **Long-only** (S1, S4, S7): monetizzano solo la gamba positiva, che è la
  **debole** in ogni fenomeno (momentum short più forte, sentiment positive
  incorporata veloce, PEAD negatività predice più forte — Druz 2015, Heston-Sinha).
- **Polarity/sentiment** (S4, S7): usano polarity sentiment, che **decade OOS
  post-2020** (Chung 2023). L'edge vivo è embedding contestuale (SBERT).
- **Large-cap** (S1, S4, S7): universe large-cap dove gli edge sono
  **competuti** (PEAD morto dal 2006 Martineau, momentum large-cap decimato
  post-2018, sentiment large-cap vicino-efficiente). L'edge vivo è
  small/mid-cap (non raggiunto da S7, non isolato in S1/S4).
- **Orizzonte mismatch** (S4 tattico giornaliero vs drift 60-180g; S7 hold 20d
  vs tone 5-10g): orizzonti fuori dal picco dell'edge.

**Impatto:** il **design alpha del progetto è sistematicamente sulla forma
debole** di ogni fenomeno. Non è un caso isolato — è un pattern. La
combinazione "long-only + polarity + large-cap + orizzonte sbagliato" è il
**deficit di design trasversale** più importante. Nessuna strategia è
configurata sulla forma viva (simmetrica, embedding, small-cap, orizzonte
ottimale).

**Raccomandazione:** il prossimo investimento di ricerca alpha dovrebbe
**invertire** ogni dimensione: short leg (simmetrico), embedding contestuale
(non polarity), small/mid-cap (con copertura dati adeguata), orizzonte al
picco dell'edge. Le strategie attuali (S1/S4) non sono la base su cui
costruire — sono la forma debole da cui allontanarsi.

## GI-5 — Governance asimmetrica: S7 misurata+killata, S1/S4 live senza kill criterion (HIGH, governance)

**Strategie colpite:** S7 (best-practice), S1/S4 (deficit). S2/S3 (morti, N/A).

**Pattern:** il progetto ha **due regimi di governance** opposti:
- **S7**: POC pre-registrato (PO-5 "Se POC-2 FAIL → REMOVE"), misurazione a
  sample decision-grade (n=73), kill criterion applicato, rimozione pulita,
  guard anti-reintro (`test_p0_13`) viva. **Best-practice.**
- **S1/S4**: live nonostante evidenza negativa. S4 ha `promotion_blocked=true`
  (governance parziale — non promuove a live MA **esegue in paper** con IC<0).
  S1 è live senza IC misurato a decision-grade. **Nessun kill criterion
  pre-registrato.** Nessuna guard anti-reintro.

**Impatto:** il sistema **esegue** su alpha misurato negativo (S4 IC<0, P&L
+$329 = beta + noise) e su alpha decaduto non misurato (S1). La governance
trattiene S4 da `mode=live` MA l'esposizione in paper è comunque un costo
(attenzione operatore, churn, rischio di promozione futura su backtest
non-rappresentativo). S7 dimostra che il progetto **sa** come killare
correttamente — non lo applica a S1/S4.

**Raccomandazione:** applicare lo **stesso disciplinamento PO-5 a S1/S4**:
misurare IC a decision-grade (n≥73, cross-model), pre-registrare un kill
criterion (es. "Se IC≤0 a n≥73 → ridurre a shadow o rimuovere"), applicarlo.
S7 è il template. La guard `test_p0_13` dovrebbe estendersi a S1/S4 se
killate. L'asimmetria di governance è il **rischio sistemico** principale:
promuovere/mantenere strategie su base non-evidence.

## GI-6 — Carburante assente / dati upstream non wired (MEDIUM, integrazione)

**Strategie colpite:** S7 (consensus ALPHA-A2 mai wired → carburante zero),
S3 (universe builder potenzialmente non wired, dead config), S1/S2 (IV stale
S2 BUG-C, regime_mult chiavi assenti per S1). **S4** ha ensemble reliability
collo #1 (70-86% fallback FinBERT non-predittivo).

**Pattern:** diverse strategie dipendono da **dati upstream mai integrati**:
- S7 consensus provider (ALPHA-A2) mai wired → zero ordini.
- S2 IV (VIX) stale, regime/VIX keys assenti → regime_mult ×0.2 limita S1.
- S4 ensemble fallback FinBERT 70-86% del volume → segnali non-predittivi.
- S3 universe builder dead config → backtest su default.

**Impatto:** le strategie soffrono di **carburante debole/assente** anche
quando la logica è corretta. Il difetto non è nella strategia ma nella
**pipeline dati**. Per S7 questo ha reso la strategia operativamente nulla.

**Raccomandazione:** mappare tutte le dipendenze dati upstream per strategia;
verificare che siano wired e fresche; per S4, indirizzare il collo #1
(pair swap / 3° modello) come prerequisito per qualunque speranza di IC>0.

## GI-7 — Backtest non-run o non-rappresentativo come decision gate (MEDIUM, processo)

**Strategie colpite:** S3 (backtest 0.148 invalidato), S4 (backtest non-run o
su sintetico), S7 (mai backtest WF, MA POC IC corretto), S1/S2 (backtest
invalidati da look-ahead).

**Pattern:** il backtest come **decision gate** è inaffidabile per la maggior
parte delle strategie. S7 è l'eccezione: ha usato un **POC IC** (misurazione
del segnale) come gate invece del backtest WF — metodologicamente **più
corretto** (kill sul segnale, non sul backtest che può overfit).

**Impatto:** le decisioni basate su backtest (S1 promozione, S3 valutazione
0.148) sono a rischio. S4 ha `promotion_blocked` quindi non decide sul
backtest — MA se il blocco viene rimosso, il backtest non-rappresentativo
(BUG-A/B) potrebbe illudere di validazione.

**Raccomandazione:** adottare il **modello S7** per le decisioni future: POC
IC pre-registrato a decision-grade come gate, non backtest WF. Se backtest,
validarlo look-ahead/survivorship prima di usarlo per decidere.

## GI-8 — Mancanza di IC cross-sectionale misurato a decision-grade (MEDIUM, misurazione)

**Strategie colpite:** S1 (nessun IC misurato), S4 (IC misurato MA n=34
small-sample, negativo), S7 (IC POC-2 n=73 decision-grade, FAIL). S2/S3
(morti/N/A).

**Pattern:** solo S7 ha un IC misurato a sample decision-grade. S4 ha IC<0 MA
a 34 giorni (small-sample, anche se la direzione è coerente). S1 non ha IC
cross-sectionale misurato (è time-series, non cross-sectionale, MA non c'è
metrica equivalente decision-grade). Senza misurazione decision-grade, non
c'è base per killare/promuovere.

**Impatto:** S1/S4 sono "live senza sapere" se il segnale predice. S7
"sapeva e ha killato". L'asimmetria di **misurazione** sottende l'asimmetria
di governance (GI-5).

**Raccomandazione:** misurare IC (o metrica equivalente) a decision-grade
(n≥73) per S1/S4 prima di qualunque decisione di promozione/mantenimento. S4
ha già il dato (s4_ic.json, 34gg) — estendere a 73gg+. S1 richiede una
metrica time-series decision-grade.

## GI-9 — Persistenza/audit trail DB incompleta (LOW, osservabilità)

**Strategie colpite:** S7 (`pead_signals` table mai materializzata BUG-D),
S3 (no lifecycle row, dead). S4 OK (`sentiment_signals`, `execution_decisions`
attivi). S1 OK (`trades`).

**Pattern:** le strategie non-live (S2/S3/S7) non hanno audit trail DB. S7
non ha nemmeno la table. Questo rende la forensic e la misurazione
difficili/assenti per le strategie non-live.

**Impatto:** LOW per le strategie morte (zero ordini) MA se una strategia
viene rivitalizzata, la mancanza di persistenza strutturale impedisce
misurazione. S4/S1 hanno persistenza attiva → forensic possibile.

**Raccomandazione:** per qualunque revival (S3 residual momentum è il
candidato più promettente per fenomeno NON decaduto), wired prima la
persistenza (table, lifecycle row) come prerequisito.

## GI-10 — Cross-strategy reversal S1↔S4 (per PORTFOLIO_INTERACTIONS)

Vedi `PORTFOLIO_INTERACTIONS.md` per l'analisi dettagliata delle interazioni
a livello portfolio (sleeve caps, reversal S1↔S4, momentum beta duplication,
signal_id coupling, shared risk overlays). Qui sintesi: il sistema ha due
strategie live (S1, S4) che possono **inversionarsi** (S1 momentum SELL su un
ticker, S4 sentiment BUY sullo stesso ticker) e **duplicare momentum beta**
(sentiment+ ≈ momentum+). Non c'è un layer di **conciliazione** esplicito
fra segnali strategie.

---

## Priorità di azione (sintesi)

| Priorità | Issue | Azione |
|---|---|---|
| **P1** | GI-5 governance asimmetrica | Applicare PO-5 a S1/S4 (misurare IC decision-grade, kill criterion) |
| **P1** | GI-4 forma debole trasversale | Nuovo research alpha: invertire ogni dimensione (short, embedding, small-cap) |
| **P2** | GI-2 backtest invalidati | Audit look-ahead/survivorship prima di decidere su S1/S4 |
| **P2** | GI-1 dead config | Wired `from_yaml` o documentare config morta |
| **P2** | GI-8 IC decision-grade | Estendere IC S4 a 73gg+; metrica S1 |
| **P3** | GI-3 gate banali | Threshold pre-registrati >0 per tutti i gate |
| **P3** | GI-6 carburante upstream | Mappa dipendenze dati per strategia |
| **P3** | GI-7 backtest come gate | Adottare POC IC (modello S7) |
| **P4** | GI-9 persistenza | Prerequisito per revival S3 |

**Il messaggio centrale**: il progetto ha **un caso di best-practice (S7) e
quattro casi di deficit (S1/S2/S3/S4)**. La priorità non è "fixare S1/S4" ma
**estendere la governance di S7 a tutto il sistema** e **costruire la
prossima strategia sulla forma viva** del fenomeno, non sulla forma debole
che tutte le strategie attuali condividono.

---

## Correzioni post-audit (2026-08-06, verifica sul codice)

Rilette contro il codice, due affermazioni di questo documento non reggono.
Registrate qui invece di riscrivere il testo sopra, così resta tracciabile
cosa l'audit aveva concluso e perché è stato corretto.

### GI-3 è sostanzialmente da ritirare

**S1 non ha alcun gate banale.** `src/strategies/s1/backtest.py:99` è
`milestone_b_pass = oos_sharpe >= 0.5` — soglia reale. L'attribuzione a S1 di
un `milestone_c oos_sharpe≥0.0` non trova riscontro: `milestone_c` esiste solo
in S3.

**Le soglie condivise erano già state sistemate.** `src/backtest/gates/runner.py:21`
e `gate_1_significance.py:39` hanno `min_sharpe = 0.5` e `min_oos_sharpe = 0.3`,
con commento esplicito *"B12: real threshold (master roadmap); 0.0 was
tautological"*. S1 e S3 usano entrambi questi default (`gate_config=None`).

**La banda banale di S3 non è sfruttabile.** `s3/backtest.py:97` è
`(0.0 <= oos_sharpe <= 1.0) and gate_report.overall_passed`: il secondo termine
impone le soglie reali, e una strategia a Sharpe 0 fallisce il gate 1 (0.5)
prima di arrivarci. Il repro `S3/repro_3_trivial_gate.py` dimostra il difetto
solo perché **forza** `overall_passed=True`, combinazione che i gate reali non
producono per Sharpe 0.

Resta una incoerenza cosmetica fra commento (`[0.4, 0.6]`) e codice
(`[0.0, 1.0]`) in una strategia morta a runtime. Severità **LOW**, non MEDIUM,
e non è un difetto di governance. Tracciata in #178.

### GI-6 / carburante: nessuna correzione, ma un'aggiunta

L'analisi delle perdite del 2026-08-05 ha trovato un difetto trasversale che
questo documento non copre: **il path live non consulta mai
`rebalance_frequency`** (`grep -c` su `portfolio_scheduler.py` → 0), mentre S1
dichiara `MONTHLY` e S4 `DAILY`, e il backtest le rispetta. È la causa
meccanica del churn intraday e rende backtest e live due sistemi diversi.
Tracciata in #185.

---
**Stato:** GLOBAL_ISSUES = done (1/4 cross_review). Prossimo: `EVIDENCE.md`.