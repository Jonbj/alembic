# REPORT S2 — Volatility Risk Premium

**Audit:** Alembic Strategy Audit · **Strategia:** S2 `VRPStrategy`
**Data report:** 2026-08-04
**Status:** `mode=disabled` (lifecycle DB), `approved=false`, `enabled=false` (yaml),
`allocation_pct=0.00`; **hard-block** nel registry (`registry.py:231`: `raise
ValueError` se S2 abilitato). **Mai in produzione** (DB: zero `stop_strategy='S2'`).
**Fonti:** fasi 01–07 in `docs/audits/strategies/S2/`.

---

## 1. Sintesi esecutiva

S2 è presentata come strategia di **variance risk premium (VRP)**: vende put
cash-secured su SPY per incassare il premio di varianza. La realtà è diversa e
più grave di un backtest negativo: **l'implementazione non cattura il VRP**.

**Verdetto alpha: `NEGATIVE` (implementazione) + `DECAYED` (fenomeno underlying).**

Cinque fatti convergenti:

1. **Tre oggetti non equivalenti.** La teoria approvata (PO 2026-07-15) definisce
   il VRP come `E^Q[QV] − E^P[QV]` (varianza, seller-sign), con variance swap /
   replica model-free come strumenti coerenti. La docstring dei moduli descrive
   "short-put selling". L'**implementazione** scambia una posizione **long-SPY
   equity** mensile gate-ata da volatilità realizzata. Sono tre cose diverse.
2. **Il segnale put è decorativo.** `compute_pnl` calcola il P&L short-put ma non
   lo scrive nel NAV del portafoglio (`portfolio.py:97` = cash + equity). Il NAV
   misura solo il long-SPY. **L'OOS Sharpe −0.613 misura long-SPY regime-gated,
   non VRP** (BUG-E, `repro_3`).
3. **Proxy vietata.** Il PO-decision (teoria §19) vieta esplicitamente la
   "sostituzione con proxy economicamente diverse" e richiede perdita finita per
   costruzione (max 2% NAV, margine stressato ≤50% sleeve). L'implementazione **è**
   la sostituzione vietata (long-SPY equity, perdita non limitata) — BUG-E/DV-5.
4. **VRP underlying decaduto.** Chicago Fed 2025: alpha delle opzioni ≈0 negli
   ultimi 15 anni; Yugam2508: Sharpe VRP 3.45→0.52 per decennio; FlashAlpha: OOS
   onesto short-put ≈0. Anche implementato correttamente, il VRP post-2020 è
   alternative-beta a Sharpe ~0.5, non alpha (Schneider 2020: α low-risk =
   compensazione coskewness).
5. **Backtest non valido.** Look-ahead nel regime gate (BUG-A, `repro_1`), IV
   stale nelle uscite (BUG-C), survivorship ereditato da S1, gate 3 non eseguito,
   gate 5 trivialmente PASS, n=3 finestre WF.

Il progetto **già classifica S2 come non-promotibile** e ne blocca l'enable
(`registry.py:231` hard-block, `config/strategies.yaml` "do not promote",
lifecycle `disabled/approved=false`). L'audit **conferma** e aggiunge: la ragione
non è solo "backtest negativo" ma "l'implementazione non è una strategia VRP".

## 2. Specificazione (estratto — vedi `01_specification.md`)

- **Teoria:** VRP = `E^Q[QV(t,T)] − E^P[QV(t,T)]`, seller-sign, varianza, 30g calendario.
- **Implementazione:**
  - Realized vol = `pct_change().rolling(63).std()·sqrt(252)` (passato, non forecast P).
  - Regime da RV: bull(<0.12, scale 1.0)/sideways(0.20, 0.75)/bear(0.35, 0.25)/high_vol(0.0).
  - Event filter: FOMC (3° mer) / NFP (1° ven) entro 1 giorno; sentiment inerte (None).
  - `select_put`: delta −0.20±0.05, DTE 30-45, OI≥100, vol≥10, filtro `IV−RV≥0` (threshold 0.0), su **catena sintetica**.
  - Sizing equity: `shares = NAV·0.20·regime_scale / spy_price` (indipendente dal put).
  - Exit (priorità): EXPIRY(DTE≤2) → STOP_LOSS(loss>2×premio o underlying>5%) → TARGET_PROFIT(50%) → TIME_DECAY(DTE<7) → SIGNAL_FLIP(IV−RV<0).
  - Reprice put: Black-Scholes con `sigma=signal.implied_vol` (IV di entry), `r=0.05` fisso.
  - Backtest: WF 1260/252 → 3 finestre, start 2007, universo S1.

## 3. Ipotesi scientifica (vedi `02_hypothesis.md`)

L'**ipotesi teorica** è il VRP azionario di indice — risk premium assicurativo,
non alpha, con evidence robusta sull'esistenza media ma debole su investibilità
netta post-2020. L'**implementazione** non testa H1–H10: opera su `IV−RV` come
proxy vietata, usa RV passata come "P", e scambia long-SPY equity. La tesi
effettivamente testata (long-SPY mensile gate-da-RV) è più debole e già
falsificata dall'OOS Sharpe negativo — che però **non falsifica il VRP**.

## 4. Letteratura (vedi `03_literature.md` — 29 fonti, 15 nuove)

- **Fondazione:** Coval-Shumway 2001, Carr-Wu 2009, Bekaert et al. 2023.
- **Decay:** Chicago Fed 2025 (α≈0 ultimi 15y), Yugam2508 (Sharpe 3.45→0.52/decennio), FlashAlpha 2026 (OOS onesto ≈0).
- **Costi/capacità:** Bondarenko 2019 (PUT Sharpe 0.65 con VWAP), Santa-Clara-Saretto (margini), Neuberger (compressione AUM).
- **Regime:** Kuang 2024 (VRP prezzato in bull, debole in bear), Koeter 2024 (term structure, short-DTE = expected variance non VRP puro), Barras-Malkhozov 2016 (VRP equity ≠ VRP opzioni).
- **Alternative-beta:** Schneider 2020 (α low-risk = coskewness, non alpha), Patel 2024 (PUTW outperformance = VRP = skew/disaster).

## 5. Mappatura codice e divergenze (vedi `05_code_mapping.md`)

- Segnale: `signal.py:44-138` · Regime: `regime.py:31-41` · Exit: `exit.py:48-105` · Sizing equity: `strategy.py:176-186` · Live build: `portfolio_scheduler.py:3074` · Hard-block: `registry.py:231`.
- **11 divergenze (DV-1..DV-11)**, di cui BLOCCANTI: DV-1 (IV−RV come VRP), DV-2 (RV passata come P), DV-3 (long-SPY come strumento), DV-5 (sostituzione vietata PO), DV-6 (perdita non finita).

## 6. Audit implementazione (vedi `06_implementation_audit.md`)

| Asse | Verdetto |
|---|---|
| Data timing | ✅ OK (bar-time daily) |
| Look-ahead | ❌ FAIL (regime bull/bear `fwd_21d` — BUG-A) |
| Leakage | ⚠️ PARTIAL (regime/stress calcolati su OOS con hindsight) |
| Survivorship | ❌ FAIL (universo S1 non delisting-aware) |
| Backtest metodologia | ⚠️ PARTIAL (T+1+costi ok, ma P&L sbagliato, n=3) |
| Signal generation | ⚠️ DRIFT (catena sintetica, filtro VRP quasi tautologico) |
| Portfolio allocation | ⚠️ PARTIAL (apply_regime_scale dead — BUG-B; no 2% NAV/max-loss) |
| Risk controls | ⚠️ AMBER (exit ben strutturata ma IV stale — BUG-C; no kill-switch) |
| Execution | ✅ OK (backtest) / N/A (live morto) |
| Accounting | ❌ FAIL (put P&L non nel NAV — BUG-E) |
| Paper-trading | N/A (mai in paper) |
| Runtime | ✅ CONFIRMED DEAD (DB: zero S2 in trades) |

## 7. Bug confermati (vedi `07_bugs.md`)

| ID | Bug | Sev | Conferma |
|---|---|---|---|
| BUG-A | look-ahead classificazione bull/bear (gate 4) | CRITICAL | `repro_1_regime_lookahead.py` ✅ (controesempio) |
| BUG-B | `apply_regime_scale` dead code (mai chiamato) | MED | `repro_2_deadconfig.py` ✅ (ast, 0 call site) |
| BUG-C | reprice/SIGNAL_FLIP con IV di entry stale | HIGH | traccia statica ✅ |
| BUG-D | dead config (no from_yaml, no yaml file) | HIGH | `repro_2_deadconfig.py` ✅ (ast+glob) |
| BUG-E | accounting divergence (put P&L non nel NAV) | CRITICAL | `repro_3_accounting.py` ✅ (controesempio) |

**Riproduzioni eseguite 2026-08-04:**
- `repro_1`: data giorno 20, label `bull` se futuri +1%/g, `bear` se futuri −1%/g → il regime di t dipende da t+1..t+21.
- `repro_2`: S2Config senza `from_yaml`, nessun `config/s2*.yaml`, `apply_regime_scale` 0 call site in src/.
- `repro_3`: due scenari di uscita identici tranne mark put (P&L put +$1900 vs −$3000, differenza $4900) → NAV backtest identico ($119,800), differenza $0 → il P&L put è invisibile al NAV.

## 8. Runtime (traccia DB read-only)

- `trades` ultimi 30g per `stop_strategy`: S1=75, S4=64, NULL=56 — **zero S2**.
- Un trade SPY (2026-07-10) è NULL-attributed (pre-wiring stop_strategy), non S2.
- Lifecycle DB: `S2 mode=disabled, approved=false, gate_report_id=NULL, promoted_at=NULL`.
- Registry: `enabled=false` + `raise ValueError` se abilitato.
- ⇒ S2 è **morto in produzione per costruzione**; nessun rischio capitale attivo.

## 9. Conclusioni e raccomandazioni (read-only — nessuna azione durante freeze)

S2 è **un'implementazione che non cattura il fenomeno che dice di catturare**, su
un fenomeno (VRP) che è **reale ma decaduto a alternative-beta ~0 netto post-2020**,
con **backtest non valido** (accounting divergence, regime look-ahead, IV stale).
La promozione a live è correttamente bloccata su tre livelli (yaml, registry
hard-block, lifecycle). Il backtest −0.613 non falsifica il VRP — falsifica una
tesi di timing equity più debole.

**L'audit non raccomanda azione durante il freeze 03/08→28/09** (e S2 non
promotibile in ogni caso). Per un eventuale futuro rilancio, le condizioni che
cambierebbero il verdetto:

1. **Implementare il VRP, non una proxy equity**: variance swap / replica
   model-free di indice o portafoglio SPX delta-hedged via IBKR, con perdita finita
   per costruzione, max loss 2% NAV, margine stressato ≤50% sleeve (PO §19). Senza
   questo, il verdetto resta `NEGATIVE` per inesposizione al fenomeno.
2. **Lato P come forecast** `E^P[QV]` ex ante robusto a più forecast, non RV passata.
3. **Backtest con P&L corretto**: il NAV deve riflettere il P&L short-put
   (premio incassato, costo di chiusura), non solo long-SPY equity (BUG-E).
4. **Regime senza look-ahead**: classificare su informazioni disponibili a t
   (BUG-A); idealmente Markov-switching su VRP (Chevallier-Vo 2019), non RV passata.
5. **Costi realistici**: fill VWAP/post-and-wait, bid-ask, margini stressati
   (FlashAlpha: erodono il VRP a ~zero).
6. **Campione preregistrato** post-2020 con 2008/Volmageddon/COVID/2022, gate
   standalone e incrementali, validazione H1–H10.
7. **Rimuovere il dead code** (BUG-B `apply_regime_scale`) e **creare un loader
   config** o documentare esplicitamente che S2 è defaults-only (BUG-D).

**Fino ad allora: `NEGATIVE` (implementazione) + `DECAYED` (fenomeno).**