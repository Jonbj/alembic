# S3 — 02 Ipotesi scientifica / investment hypothesis

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Riferimenti:** `docs/RESEARCH_S3_STRATEGY_REVIEW_2026-07-20.md`, §1 di questa audit.

---

## 1. L'ipotesi teorica

S3 scommette sul **momentum residuale cross-sectionale**: la componente
**idiosincratica** del momentum azionario — netta del contributo beta×momentum di
mercato — persiste nel breve termine e non è spiegata dal beta di mercato.

**Formula teorica** (Blitz-Hanauer-Vidojevic 2011; Gutman 2023):

$$\mathrm{rm}_{i,t} = r_{i,[t-252,t]} - \beta_{i,t}\, r_{\mathrm{SPY},[t-252,t]}$$

dove $r_{i,[t-252,t]}$ è il rendimento lordo dell'azione sull'orizzonte 12 mesi e
$\beta_{i,t}$ è il beta rolling OLS contro SPY. Il **residuo** dovrebbe catturare il
momentum **specchio dell'idiosincrasia**, meno correlato al fattore mercato e —
secondo l'ipotesi — **più stabile** del momentum lordo perché meno esposto ai
crash del mercato (che distruggono il momentum TS/CS tradizionale nei regimi
bear+rebound, Daniel-Moskowitz 2016).

**Perché dovrebbe essere prezzato (meccanismi):**

1. **Underreaction idiosincratica** — gli investitori reagiscono lentamente alle
   notizie specifiche dell'azienda (earnings, guida analisti) non coperte dal beta
   di mercato; il residuo cattura questa underreaction lenta (Jegadeesh-Titman
   1993, base del momentum).
2. **Meno esposizione ai crash** — Blitz et al. 2011 mostrano che il residual
   momentum ha Sharpe ~doppio del momentum lordo e **crash meno severi** nei
   regimi di mercato avversi, perché la componente beta (che domina nei crash) è
   sottratta.
3. **Distinto dal momentum tradizionale** — Gutman 2023 mostra che il residual
   momentum è una **fattore distinto** che sopravvive al controllo per il momentum
   lordo e per i fattori Fama-French, con Sharpe incrementale.

**Classificazione teorica:** anomalía comportamentale (underreaction) con
componente risk-based (compensazione per volatilità idiosincratica). La letteratura
lo tratta come **anomalia genuina ma attenuata** rispetto al momentum lordo, non
come risk premium puro.

## 2. Come il codice operazionalizza l'ipotesi

Il codice corrente implementa la **formula del residual momentum** in modo
corretto (signal.py:39-68), ma diverge dal design originale su 6+ dimensioni
(§11 fase 01) che cambiano l'ipotesi testata:

1. **12-0 vs 12-1 (DV-1/DV-2)**: il design originale usa `log(P[t-21]/P[t-252])`
   (12-1, skip ultimo mese) per evitare la **reversal a breve** del momentum
   (Jegadeesh-Titman: il momentum 12-1 esclude il mese più recente dove opera la
   short-term reversal). Il codice usa `P[t]/P[t-252]-1` (12-0), **includendo il
   mese corrente** dove il reversal è noto. Questo contamina il segnale con la
   componente reversal (sign flip su orizzonti <1m). La letteratura JT-1993
   stabilisce esplicitamente la finestra 12-1; il 12-0 è un'esposizione diversa.
2. **Long-short vs long-only (DV-3)**: il design originale è **long-only** (top
   decile); il codice è **long-short** per default. Il long-short ha payoff, costi
   di prestito, exposure ai short-squeeze e profilo di crash **diversi**. Il
   residual momentum long-short di Blitz et al. 2011 è l'oggetto studiato, ma il
   design Alembic scelse long-only esplicitamente — il codice lo inverte.
3. **Sizing non normalizzato (DV-4)**: il design normalizza i pesi (somma=1);
   il codice no → gross exposure variabile e non controllato, dipendente dal
   numero di nomi nel decile. Su 50 nomi, ~5 per decile → gross ~5×(target_vol/vol)
   cap 20% = fino a 100% per gamba. Non è il sizing del design.
4. **Universo survivor (DV-6)**: `active_at(end)[:50]` → 50 sopravvissuti liquidi
   OGGI usati su 2000-today. L'ipotesi residual-momentum richiede un pannello
   large/mid US liquido **PIT**; il codice testa "residual momentum dei 50
   sopravvissuti grandi-cap", una selezione ad-hoc che confonde il test.
5. **Pannello bilanciato (DV-7)**: date droppate se un ticker ha NaN → l'universo
   di date è determinato dai future-listed, come S1 BUG-2.

**Ne consegue**: l'ipotesi effettivamente testata dal codice è *"momentum lordo
12-0 (con reversal), long-short, sizing non normalizzato, sui 50 sopravvissuti"*
— non *"residual momentum 12-1 long-only PIT"*. Sono ipotesi diverse. L'OOS Sharpe
0.148 non falsifica il residual momentum 12-1: falsifica una variante confusa.

## 3. Esposizione alternative-beta a priori

- **Momentum beta**: il residual momentum è, per costruzione, **correlato al
  momentum lordo** (condividono il termine `P[t]/P[t-252]-1`). Anche sottraendo
  `beta·market_mom`, rimane correlato al fattore momentum (Blitz et al. 2011
  mostrano correlazione ~0.5 con momentum lordo). Gutman 2023 mostra però
  che il residuo ha **incremental alpha** oltre il momentum lordo — quindi non è
  puro momentum beta.
- **Market beta**: ridotta per costruzione (sottrazione `beta·market_mom`). Ma
  il long-short dollar-neutral ha comunque exposure al mercato via differenziali
  di beta tra long e short leg.
- **Volatility/low-vol beta**: il sizing inverse-vol 252d tilta verso titoli
  low-vol → esposizione al fattore low-vol (Betting Against Volatility, Schneider
  2020) — come S1.
- **Size beta**: universo limitato a 50 large-cap → tilt verso size large.
- **Short-leg risk**: short decile 1 (perdenti residui) expone a short-squeeze e
  costo di borrow; non modellato.

## 4. Sintesi

L'**ipotesi teorica** (residual momentum 12-1 long-only, Blitz/Gutman) ha un
prior accademico **forte** e distinto dal momentum lordo, con evidence di
incremental Sharpe e minore crash exposure. Il **codice corrente** non la testa
fedelmente: usa 12-0 (contaminato da reversal), long-short (non long-only),
sizing non normalizzato, su 50 sopravvissuti. La review interna (2026-07-20)
giustamente raccomanda un POC A/B offline che misuri la **variante originale**
contro un benchmark, e **non** interpreta il 0.148 come falsificazione.

Il verdict di alpha (fase 04) dovrà distinguere **"residual momentum non è testato
fedelmente"** (codice diverge) da **"residual momentum testato fedelmente e non
genera alpha"**. La prima è la conclusione supportata: l'evidenza 0.148 è di una
variante economicamente diversa. Separatamente, il residual momentum (come tutte
le anomalie momentum) è soggetto a **decay post-publication** (Ben-David 2021 per
il momentum lordo; il residual momentum, essendo correlato, condivide la
pressione al decay), e il backtest è invalidato da survivorship + pannello
bilanciato + soglie banali (min_sharpe=0.0).

---
**Stato fase:** 02_hypothesis = **done**. Prossimo cursore: `S3:03_literature`.