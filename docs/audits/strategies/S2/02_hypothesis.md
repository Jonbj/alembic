# S2 — 02 Ipotesi scientifica / investment hypothesis

**Strategia:** S2 `VRPStrategy`
**Data:** 2026-08-04
**Riferimenti:** `docs/strategies/s2-vrp-theory.md` (teoria approvata PO 2026-07-15), §1 di questa audit.

---

## 1. L'ipotesi teorica (oggetto 1 di §0)

S2 scommette sul **variance risk premium (VRP) azionario di indice**, definito — in
convenzione seller-sign e in varianza — come:

$$\mathrm{VRP}_t(T) = \mathbb{E}_t^{\,Q}[\mathrm{QV}(t,T)] - \mathbb{E}_t^{\,P}[\mathrm{QV}(t,T)]$$

dove `QV(t,T)` è la variazione quadratica annualizzata dell'underlying sull'orizzonte
`T−t` (30g calendario nel perimetro PO), `Q` è la misura risk-neutral incorporata
nei prezzi di opzioni/variance swap, `P` è la misura fisica condizionale. Il premio
è positivo in media quando, in aspettativa, **chi vende varianza è remunerato per
detenere rischi costosi negli stati avversi**.

**Perché dovrebbe essere prezzato (meccanismi complementari, teoria §4):**

1. **Domanda di protezione / avversione al crash** — investitori avversi al rischio
   pagano payoff convessi (put, straddle) negli stati a elevata utilità marginale;
   la domanda netta di protezione downside inclina la superficie Q sopra `P`.
2. **Salti, coda e downside** — la componente downside è controciclica; eventi rari
   spiegano una parte rilevante del prezzo Q (Bollerslev-Todorov 2011).
3. **Vincoli degli intermediari** — dealer che assorbono domanda di protezione
   detenendo rischio non perfettamente copribile richiedono compenso per capitale,
   funding, margini (Gârleanu-Pedersen-Poteshman 2009; Bollen-Whaley 2004).
4. **Correlazione in crisi** — l'indice concentra correlazione e downside
   sistemático; spiega un premio più forte nei prodotti indice che nei single-name
   (Driessen-Maenhout-Vilkov 2009).
5. **Hedging, vol-of-vol, liquidità** — il delta hedging non elimina gamma, salti,
   basis, liquidità; il premio copre il rischio residuo.

**Classificazione teorica:** **alternative-beta assicurativa / risk premium**, non
alpha (teoria §8, M04). L'eventuale alpha è solo il residuo, dopo costi, collateral,
capitale e dopo aver controllato esposizioni lineari e non lineari (market, downside,
jump, liquidity, gamma/vega, skew, vol-of-vol, timing). Uno Sharpe alto **non prova
alpha** in presenza di skew negativo e pochi eventi estremi.

**Falsificabilità (teoria §16, H1–H10).** Le ipotesi rilevanti per S2:
- **H1** — `E^Q[QV] > E^P[QV]` in media su indici liquidi (esistenza).
- **H3** — un'esposizione diretta conserva rendimento netto economicamente positivo
  dopo spread, hedge, collateral, capitale (investibilità).
- **H7** — livello VIX / IV-RV passata **non** predicono monotonamente il premio
  futuro.
- **H10** — il rendimento **non è alpha** dopo fattori non lineari e costi.

## 2. Come l'implementazione operazionalizza l'ipotesi (oggetto 3 di §0)

L'implementazione S2 **non** opera sul VRP in varianza. Opera su tre approssimazioni
che la teoria stessa declassa:

1. **Proxy di premio = `IV − RV` in punti di volatilità** (`vrp_entry_threshold=0.0`,
   entra se `IV ≥ RV`, signal.py:101). La teoria (§6, M06) dice esplicitamente che
   `IV − RV passata` è *al massimo* una proxy ex post, **non** la definizione del
   premio e **non** direttamente monetizzabile. Jensen + vol-of-vol + orizzonti
   disallineati (IV da catena sintetica a DTE 30–45 vs RV a 63g) rendono il confronto
   distorto.
2. **Lato P = RV63 rolling passata** (strategy.py:88). La teoria (§3 tabella) dice
   che la varianza realizzata passata **non sostituisce** `E^P[QV]` (aspettativa ex
   ante). Qui il "P" è un backward-looking rolling — esattamente ciò che la teoria
   vieta come stima di P.
3. **Strumento = long SPY equity** (§6 della fase 01). La teoria (§7, M05) classifica
   put-writing come "esposizione mista" (beta + skew + jump + gap) e la **proxy
   azionaria senza derivati come "non chiamabile VRP"** senza identificazione
   empirica separata. Il PO-decision (§19) vieta esplicitamente la sostituzione con
   proxy economicamente diverse: "Se nessuno strumento soddisfa
   purezza/liquidità/perdita-limitata → NO-GO". L'implementazione è la sostituzione
   vietata.

Ne consegue che **l'ipotesi testata dall'implementazione non è H1–H10**, ma una
tesi empirica diversa e più debole:

> *"Una posizione long-SPY mensile, gate-ata da regime di volatilità realizzata ed
> event-filter FOMC/NFP, con uscite su target-profit/stop/time/signal-flip derivati
> da una put sintetica non tradata, genera rendimento netto positivo."*

Questa **non è** la tesi VRP. È una tesi di **timing equity con gating di volatilità**,
che condivide con il VRP solo l'idea qualitativa che la volatilità realizzata sia
informativa. L'OOS Sharpe −0.613 (summary.json) non falsifica il VRP: falsifica
questa tesi di timing equity.

## 3. Esposizione alternative-beta a priori

Anche ignorando la divergenza strumento, l'esposizione attesa è:
- **Market beta ~0.20** (long SPY al 20% NAV · regime_scale): il rendimento è
  dominato dal drift di SPY nel mese di detenzione. Il "premio" messurato coincide
  in gran parte con l'equity risk premium su SPY, non con un premio di varianza.
- **Short-vol / convexity beta**: la logica di uscita (target-profit 50%, stop 2×,
  underlying stop 5%) replica la struttura di payoff di una short put **ma sul
  P&L equity**: l'underlying-stop al 5% taglia la coda sinistra del long-SPY,
  simulando una "protezione" che tuttavia **non è pagata come premio** (nessuna
  cassa premio entra nel NAV — §6.1 fase 01). Il payoff risultante è long-SPY con
  un soft-stop al −5% mensile: asimmetrico (taglia upside? no — taglia solo downside
  oltre 5%), ma senza il corrispettivo incasso di premio che giustificherebbe
  l'asimmetria.
- **Vol-timing beta**: il gate `high_vol → 0.0` disinveste quando la RV supera
  0.35. Questo è un timing di volatilità (vender quando RV alta), che la teoria
  (§9, H7) dice non monotono e non affidabile come predittore del premio.

Non c'è, nell'implementazione, esposizione isolata alla varianza. La decomposizione
alternative-beta a priori è quindi: **market-beta dominante + vol-timing beta +
soft-stop equity**, non VRP.

## 4. Sintesi

L'**ipotesi teorica** è il VRP azionario di indice — fenomeno reale, risk premium
assicurativo, non alpha, con evidence robusta sull'esistenza media ma debole su
investibilità netta post-2020 (teoria §5; Chicago Fed 2025-17: "negli ultimi 15 anni
alpha indistinguibile da zero"). L'**implementazione S2** non testa questa ipotesi:
opera su `IV−RV` come proxy vietata, usa RV passata come "P", e scambia long-SPY
equity come strumento. La tesi effettivamente testata (long-SPY mensile gate-da-RV)
è più debole e già falsificata dall'OOS Sharpe negativo. Il verdict di alpha (fase
04) dovrà distinguere **"il VRP non è implementato"** da **"il VRP è implementato e
non genera alpha"** — la prima è la conclusione supportata dal codice.

---
**Stato fase:** 02_hypothesis = **done**. Prossimo cursore: `S2:03_literature`.