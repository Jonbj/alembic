# S2 — 04 Valutazione alpha

**Strategia:** S2 `VRPStrategy`
**Data:** 2026-08-04
**Verdetto:** **`NEGATIVE` (implementazione) + `DECAYED` (fenomeno VRP underlying)**

---

## 1. Verdetto e ragione sintetica

S2 **non genera alpha netto** e l'evidenza interna lo conferma (OOS Sharpe −0.613,
tutti i gate falliti tranne lo stress trivialmente passato). La ragione è però
**più forte di un semplice backtest negativo**: l'implementazione **non cattura il
VRP**. Opera una posizione **long-SPY equity** mensile gate-ata da volatilità
realizzata, mentre il segnale short-put (strike/delta/premium) è **decorativo** ai
fini del NAV — il suo P&L è calcolato ma non alimenta il portafoglio (fase 01 §6.1).
Quindi il backtest negativo **non falsifica il VRP**: falsifica una tesi di timing
equity con gating di volatilità, che è più debole e diversa dall'ipotesi teorica.

Il **fenomeno VRP underlying** è, separatamente, **DECAYED**: la letteratura
(Chicago Fed 2025: alpha ≈0 ultimi 15 anni; Yugam2508: Sharpe VRP 3.45→0.52 per
decennio; FlashAlpha: OOS onesto short-put ≈0) mostra che il premio netto è
collassato nel periodo post-2010 in cui S2 opererebbe. Anche un'implementazione
corretta (variance swap / replica model-free con costi realistici) produrrebbe
Sharpe ~0.5 nel 2020s, non alpha.

**Verdetto combinato: `NEGATIVE` per l'implementazione (alpha negativo documentato
e non-VRP), `DECAYED` per il fenomeno (VRP reale ma ~zero netto post-2020).**

## 2. Cinque assi di valutazione

### Asse 1 — Implementazione cattura il VRP? ❌ NO

- Strumento = long SPY equity (20% NAV · regime_scale). Il P&L del NAV è
  `cash + SPY_position_value` (portfolio.py:97); il P&L short-put (`compute_pnl`)
  è loggato, non scritto (fase 01 §6.1).
- Proxy di premio = `IV − RV passata` (signal.py:101, threshold 0.0) — la teoria
  (§3, M06) vieta `IV−RV` come definizione del VRP e lo declassa a proxy ex post.
- Lato P = RV63 rolling passata, non forecast `E^P[QV]` (teoria §3 tabella: "non
  sostituisce l'aspettativa fisica futura").
- Barras-Malkhozov 2016: VRP equity ≠ VRP opzioni; S2 cattura lato equity.
- **Conclusione**: l'implementazione non è esposta al VRP in varianza. Testa una
  tesi di timing equity, non H1–H10.

### Asse 2 — Il fenomeno VRP underlying genera alpha netto? ⚠️ DECAYED, non alpha

- Esistenza media robusta (Coval-Shumway, Carr-Wu, Bekaert et al.).
- **Decay**: Chicago Fed 2025 (alpha ≈0 ultimi 15 anni), Yugam2508 (Sharpe 0.52
  nel 2020s), Dew-Becker 2017 (varianza news a lungo costless).
- **Alternative-beta**: Schneider et al. 2020 (alpha low-risk = compensazione
  coskewness), Patel et al. 2024 (PUTW outperformance = VRP = skew/disaster risk).
  Il rendimento di put-writing non è alpha dopo controlli skewness/downside.
- **Costi/capacità**: FlashAlpha (fill rate 3-14%, OOS ≈0), Santa-Clara-Saretto
  (margini), Neuberger (compressione AUM) erodono il VRP teorico a ~zero netto.
- **Conclusione**: anche implementato correttamente, il VRP post-2020 è
  alternative-beta assicurativa a Sharpe ~0.5, non alpha.

### Asse 3 — Backtest attendibile? ❌ NO (multiplo bias)

- **P&L misurato ≠ P&L strategia**: OOS Sharpe −0.613 misura long-SPY, non
  short-put (fase 01 §6.1). Il numero non è interpretabile come evidenza VRP.
- **Regime split look-ahead**: `_split_regime_returns` (backtest.py:202-211)
  definisce bull/bear con `fwd_21d = cum_return.shift(-21)/cum_return - 1` —
  **uso di rendimenti futuri** per classificare il regime, identico alla famiglia
  di bias di S1 (OBS-4). Il gate 4 (regime) è valutato con hindsight intra-OOS.
- **Gate 3 robustness non eseguito**: summary riporta "no perturbed sharpe data
  provided" nonostante `run_robustness=True`. `_run_perturbation` (backtest.py:96)
  è condizionato a `len(oos_returns) > 20`; con 3 finestre OOS da 252g il concat
  dovrebbe superare 20 — da verificare in fase 06, ma il gate è fallito per dato
  mancante, non per risultato negativo.
- **Gate 5 stress trivialmente PASS**: worst_drawdown cum_return +0.0028 DD
  −0.0001, vix_2018 cum_return 0.0 — la posizione era quasi nulla in quei periodi,
  non resiliente. "Passato" ma non informativo.
- **Walk-forward 3 finestre** (1260/252): IS Sharpe −0.99, OOS −0.61 →
  degradation ratio 0.57; n_windows piccolo, DSR n_trials implicito piccolo
  (come S1).
- **Conclusione**: il backtest non è attendibile né come evidenza VRP né come
  evidenza di timing equity robusta (regime circolare, n piccolo, gate mancato).

### Asse 4 — Costi, capacità, perdita-limitata? ❌ NO

- **Nessun costo reale modellato**: catena sintetica, fill a mid, BS reprice con
  r=0.05 fisso e IV di entry stale. FlashAlpha mostra che fill realistici erodono
  il VRP a ~zero; S2 li ignora.
- **Perdita non finita**: long-SPY equity ha perdita non limitata al collaterale;
  il PO-decision (teoria §19) richiede "perdita massima contrattuale 2% NAV,
  margine stressato ≤50% sleeve, perdita finita per costruzione". S2 non ha
  nessuno di questi meccanismi.
- **Capacità**: S2 `max_collateral_pct=0.20` = 2× l'allocazione tipica consigliata
  (Neuberger 5-10%); passivo, non attivo. Compressione AUM non considerata.
- **Conclusione**: anche se il P&L fosse positivo, l'investibilità netta non è
  dimostrata e viola i vincoli PO.

### Asse 5 — Coerenza con teoria approvata? ❌ NO (sostituzione vietata)

- PO-decision (teoria §19): "Se nessuno strumento soddisfa contemporaneamente
  purezza, liquidità e perdita limitata, la decisione è `NO-GO`: nessuna
  sostituzione con proxy economicamente diverse."
- L'implementazione **è** la sostituzione vietata: long-SPY equity al posto di
  variance swap / replica model-free / delta-hedged index options.
- DV-1..DV-8 (fase 01 §11): 9 divergenze teoria↔codice, di cui DV-5 (proxy
  vietata) e DV-6 (perdita non finita) sono bloccanti per il design.

## 3. Sintesi vs evidenza di progetto

| Evidenza interna | Valore | Interpretazione |
|---|---|---|
| `reports/s2_backtest/summary.json` OOS Sharpe | −0.613 | Misura long-SPY equity, non VRP. Non falsifica il VRP. |
| Gate 1 significance | FAIL (Sharpe −0.505, p=0.0, DSR=0.0) | Coerente con "nessun edge". |
| Gate 2 walk-forward | FAIL (OOS −0.613, 2/3 positive) | n=3 finestre, non robusto. |
| Gate 3 robustness | FAIL ("no perturbed data") | Gate non eseguito, non negativo. |
| Gate 4 regime | FAIL (2/4 regimi >0) | Regime split con look-ahead fwd_21d. |
| Gate 5 stress | PASS (triviale: posizioni ~0) | Non informativo. |
| `config/strategies.yaml` note | "proxy implementation; OOS Sharpe -0.55, all gates failed — do not promote" | Il progetto lo sa. |
| `registry.py:231` | `raise ValueError` se S2 enabled | Hard-block; S2 non promotibile. |
| Lifecycle DB | `mode=disabled, approved=false` | Confermato. |

Il progetto **già classifica S2 come non-promotibile** e ne blocca l'enable.
L'audit **conferma** quella classificazione e aggiunge: la ragione non è solo
"backtest negativo" ma "l'implementazione non è una strategia VRP".

## 4. Condizioni che cambierebbero il verdetto

1. **Implementare il VRP, non una proxy equity**: variance swap / replica
   model-free di indice o portafoglio SPX delta-hedged via IBKR, con perdita
   finita per costruzione, max loss 2% NAV, margine stressato ≤50% sleeve
   (PO-decision §19). Senza questo, il verdetto resta `NEGATIVE` per
   inesposizione al fenomeno.
2. **Lato P come forecast**: sostituire RV63 passata con un modello di
   `E^P[QV]` ex ante robusto a più forecast (teoria §17), non un singolo
   rolling backward-looking.
3. **Backtest con P&L corretto**: il NAV deve riflettere il P&L short-put
   (premio incassato, costo di chiusura), non solo long-SPY equity.
4. **Regime split senza look-ahead**: definire regimi su informazioni disponibili
   al tempo t, non su `fwd_21d`.
5. **Costi realistici**: fill VWAP/post-and-wait (non mid), bid-ask, margini
   stressati. FlashAlpha: questi erodono il VRP a ~zero.
6. **Campione preregistrato** post-2020 con sottoperiodi 2008/Volmageddon
   2018/COVID 2020/2022, gate standalone e incrementali (PO-decision).
7. **Validazione H1–H10** (teoria §16) prima di qualsiasi design operativo.

**Fino ad allora: `NEGATIVE` (implementazione) + `DECAYED` (fenomeno).**

---
**Stato fase:** 04_alpha_assessment = **done**. Prossimo cursore: `S2:05_code_mapping`.