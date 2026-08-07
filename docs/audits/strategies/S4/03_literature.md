# S4 — 03 Letteratura

**Strategia:** S4 `NewsDrivenTactical` (news-driven tactical sentiment overlay)
**Data:** 2026-08-04
**Metodo:** `WebSearch` su PEAD/sentiment drift, textual sentiment predictability,
LLM-based sentiment (FinBERT/ChatGPT). La review interna
(`docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md`) traccia lo stato della
pipeline; qui aggiungo la prospettiva accademica su decay, costi, orizzonti,
LLM-vs-dizionari, alternative-beta. Nessuna citazione inventata.

---

## 1. Fonti fondative: PEAD e news sentiment drift

| Fonte | Anno | Contributo per S4 |
|---|---|---|
| [Tetlock — Giving Content to Investor Sentiment](https://business.columbia.edu/sites/default/files-efs/pubfiles/3096/More_Than_Words_tetlock.pdf) | 2007 | Pioniere: parole negative nei media predicono rendimenti di mercato a breve, poi **reversal**. Stabilisce il framework sentimento (transitorio, reversal) vs informazione (persistente). |
| [Tetlock-Saar-Tsechansky-Macskassy — More Than Words](https://business.columbia.edu/sites/default/files-efs/pubfiles/3096/More_Than_Words_tetlock.pdf) | 2008 | Esteso a firme S&P500: parole negative **predicono utili bassi** oltre consensus; prezzi **sottoreagiscono** con ritardo ~1 giorno; long-short guadagna 9-12 bps/giorno **pre-cost**. **Molto più forte per notizie fondamentali** (parola "earn"). |
| [García — Sentiment during Recessions](https://www.jstor.org/stable/journal10.2301.2) (JF) | 2013 | Pessimismo media **3× più forte in recessione** che in espansione → sentimento **time-varying**, dipendente dal regime. |
| [Heston-Sinha — News vs Sentiment](https://doi.org/10.17016/feds.2016.048) | 2016/2017 | 900k+ Reuters. **News giornaliera predice solo 1-2 giorni**; aggregazione settimanale fino a 13 settimane. **News positiva incorporata velocemente (~1 sett.)**, news negativa **ritardo lungo (fino a un trimestre)** per short-sale constraints. |
| [Loughran-McDonald — When Is a Liability Not a Liability](https://www.jstor.org/stable/journal10.2301.2) | 2011 | ~75% delle parole "negative" Harvard-IV-4 **non sono negative in contesto finanziario** → dizionari lessicali rumor; lista finance-specific 2349 parole. Motiva l'uso di LLM. |

## 2. Decay post-pubblicazione (cruciale per S4)

| Fonte | Anno | Risultato | Impatto su S4 |
|---|---|---|---|
| [Kettell-McInnis-Zhao — Why Has PEAD Declined](https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf) | 2022 | PEAD è **declinato significativamente** 1974-2020 ed è **indistinguibile da zero dopo il 2017**. Driver: persistenza decrescente degli earnings surprise (SUE), non solo arbitrage. | **Decay forte** del fenomeno parente di S4 (PEAD). S4 generalizza il drift a tutte le news, ma l'anomalia canonica è vicina allo zero post-2017. |
| [Chung-Tanaka-Ishii — PEAD with Textual/Contextual Factors](https://doi.org/10.1145/3604237.3626861) | 2023 | **Feature testuali (sentiment) mostrano alpha decay out-of-sample** (peggiorano vs baseline); feature **contestuali/embedding** migliorano OOS (+53-354 bps). ChatGPT-summarization aiuta contestuali MA **distrugge sentiment cues**. | S4 usa sentiment testuale (polarity) → è il tipo di feature che mostra decay OOS. L'edge contestuale/embedding non è sfruttato. |
| [Lopez-Lira-Tang — Sharpe decline](https://doi.org/10.48550/arxiv.2304.07619) | 2023/24 | Sharpe del long-short ChatGPT **declinato 6.54 (2021Q4) → 2.33 (2023)** → l'adozione degli LLM riduce l'underreaction. | **Decay attivo in corso** dell'edge LLM-sentiment; S4 opera in un regime dove l'edge si sta erodendo. |

## 3. Costi di transazione, capacità (cruciale per S4)

| Fonte | Anno | Risultato | Impatto su S4 |
|---|---|---|---|
| [Chordia-Goyal-Sadka-Sadka-Shivakumar — Liquidity and PEAD](https://www.tandfonline.com/doi/abs/10.2469/faj.v65.n4.3) | 2009 | PEAD concentrato in **stock illiquide**: 0.04%/mese (liquid) vs 2.43%/mese (illiquide). **Costi consumano 70-100% dei profitti** long-short. | **S4 usa universo S1 (large/mid liquido)** → è sul lato a basso PEAD (0.04%/mese). Dopo costi, near-zero. |
| [Ng-Rusticus-Verdi — Transaction Costs for PEAD](https://doi.org/10.1111/j.1475-679x.2008.00290.x) | 2008 | Costi di transazione **constraining** → drift più alto per firme ad alto costo. I costi spiegano **persistenza ed esistenza** del PEAD. | L'edge sentiment sopravvive soprattutto dove i costi impediscono l'arbitraggio → su stock liquido (S4) è prezzato via. |
| [Zhang-Cai-Keasey — Profitability, Costs, Risk of PEAD](https://link.springer.com/article/10.1007/s11156-013-0386-4) | 2014 | Event-study **overstima** alpha; dopo costi espliciti **nessun alpha** in multi-factor regressions. Robusto a sub-period. | S4 backtest non modella costi (fase 01 §7); il paper-live ha slippage. Risultato atteso: edge pre-cost → ~zero post-cost. |
| Tetlock-Saar-Tsechansky-Macskassy 2008 (sopra) | 2008 | 9-12 bps/giorno **pre-cost**. | A 9-12 bps/giorno, anche 5-10 bps di costi round-trip cancellano l'edge su stock liquido. |

## 4. Orizzonti (cruciale per S4 — S4 è tattico giornaliero)

| Fonte | Anno | Risultato | Impatto su S4 |
|---|---|---|---|
| Heston-Sinha 2016/2017 (sopra) | 2016 | **News giornaliera → predice 1-2 giorni**; settimanale → 13 settimane. | S4 `rebalance_frequency=DAILY`, `max_signal_age_hours=4` → opera sull'orizzonte **1-2 giorni**, dove l'edge è **minimo e rumor** (1-2 giorni di predictability). Il PEAD classico (60-180g) è molto più forte. |
| Tetlock 2007 (sopra) | 2007 | Effetto sentimento **reversal** a breve (transitorio). | S4 holding tattico breve può catturare reversal transitorio invece di drift informativo → segno dell'edge incerto a orizzonte giornaliero. |
| Kettell-McInnis-Zhao 2022 (sopra) | 2022 | **Immediate-window PEAD [+2,+6] è cresciuto**; later-window [+7, next EAD] è indebolito. | L'unica parte di PEAD che sopravvive è quella **immediata (giorni 2-6)** → coerente con orizzonte tattico di S4, MA solo per earnings, non per news generiche. |

## 5. LLM vs dizionari (cruciale — S4 usa FinBERT fallback + glm52/gptoss)

| Fonte | Anno | Risultato | Impatto su S4 |
|---|---|---|---|
| [Lopez-Lira-Tang — Can ChatGPT Forecast Stock Returns](https://doi.org/10.48550/arxiv.2304.07619) / [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788) | 2023/24 | ChatGPT long-short **38 bps/giorno, Sharpe 3.28 (GPT-4)**. **Solo LLM avanzati** predicono; **FinBERT ha Sharpe −0.43** (negativo!), BERT −0.61, GPT-1/2 −0.31. Ranking: GPT-4 > GPT-3.5 > DistilBart > RavenPack > BART > BERT-Large > ... > **FinBERT peggio di tutti**. | **CRITICO per S4**: FinBERT è il **fallback** di S4. La letteratura documenta FinBERT con Sharpe **negativo**. Quando l'ensemble diverge (70-86% fallback, vedi memoria collo #1), S4 produce segnali con un modello documentato come non-predittivo. glm52/gptoss non sono testati accademicamente → prior incerto. |
| Lopez-Lira-Tang (sopra) | 2023 | **News negativa (short leg) 29 bps/giorno vs long leg 9 bps/giorno**; small stocks 6× più forti. | **S4 è long-only positivo** → è sulla gamba **più debole** (9 vs 29 bps). L'edge maggiore è sulla gamba short negativa che S4 **non commercializza**. E su large-cap (S4) vs small-cap → più debole. |

## 6. Regime dependency

| Fonte | Anno | Risultato | Impatto su S4 |
|---|---|---|---|
| García 2013 (sopra) | 2013 | Sentiment 3× più forte in **recessione**. | S4 non condiziona per regime macro → cattura poco dell'edge in espansione (regime attuale). |
| Lopez-Lira-Tang 2023 (sopra) | 2023 | Edge più forte per stock piccoli e news negative (limits-to-arbitrage). | S4 large-cap long-only positivo → **doppio svantaggio** (grande + positivo). |
| Heston-Sinha 2017 (sopra) | 2017 | Asimmetria incorporazione: positiva veloce, negativa lenta. | S4 long-only positivo cattura la gamba **velocemente incorporata** → edge rimosso in ~1 settimana → orizzonti tattici brevi sono competitivi ma rumor. |

## 7. Alternative-beta exposure

| Fonte | Anno | Risultato | Impatto su S4 |
|---|---|---|---|
| Tetlock-Saar-Tsechansky-Macskassy 2008 (sopra) | 2008 | Sentiment predice **utili futuri** oltre consensus → contenuto informativo fondamentale, non puro sentimento. | S4 polarity × confidence è partly "fundamentals news" beta, partly noise sentiment → non pulito. |
| Lopez-Lira-Tang 2023 (sopra) | 2023 | ChatGPT **subsume** RavenPack sentiment (solo coefficiente ChatGPT resta significativo). | LLM-sentiment è partly **news-beta** prezzabile; la questione è se glm52/gptoss isolino alpha oltre il "comprare news positive" (criterio P0-13 IC>placebo, non confermato). |
| Event-beta (earnings season) | — | News concentrate cluster di eventi → volatilità elevata non modellata. | S4 expone a earnings-season vol; non hedged. |
| Market/momentum beta | — | Long-only → beta mercato positivo; overlap S1 (sentiment+ = momentum+). | **Duplicazione S1** — risk chiave per `cross_review`: S4 può essere partly momentum-beta duplicato, non incrementale. |

## 8. Sintesi per S4

1. **Il fenomeno parente (PEAD) è decaduto** a ~zero post-2017 (Kettell-McInnis-
   Zhao 2022). S4 generalizza a news generiche, ma l'anomalia canonica è vicina
   allo zero.
2. **I costi consumano 70-100% dell'edge** PEAD (Chordia 2009, Ng-Rusticus-Verdi
   2008, Zhang-Cai-Keasey 2014). S4 opera su **stock liquidi** (universo S1), dove
   PEAD è 0.04%/mese (vs 2.43% illiquido) → edge near-zero post-cost. Il backtest
   S4 non modella costi.
3. **Orizzonte tattico giornaliero = edge minimo**: news giornaliera predice solo
   1-2 giorni (Heston-Sinha 2017); S4 `max_signal_age_hours=4` opera su questo
   orizzonte rumor, non sul PEAD 60-180g forte.
4. **Long-only positivo = gamba debole**: Lopez-Lira-Tang 2023: long leg 9 bps/giorno
   vs short leg 29 bps; Heston-Sinha: positiva incorporata veloce, negativa lenta.
   S4 è sulla gamba debole due volte (positiva + large-cap).
5. **FinBERT fallback = documentato non-predittivo**: Lopez-Lira-Tang: FinBERT
   Sharpe **−0.43** (peggio di tutti). L'ensemble divergence order drought (70-86%
   fallback, memoria collo #1) → S4 produce spesso segnali con un modello
   accademicamente non-predittivo. glm52/gptoss non testati → prior incerto.
6. **LLM edge in decay attivo**: Sharpe ChatGPT 6.54→2.33 (2021-2023); adozione
   riduce underreaction. S4 opera in regime di eroding edge.
7. **Alternative-beta**: S4 è partly news-beta prezzabile, partly fundamentals-
   info beta, con duplicazione momentum (overlap S1) e market beta (long-only).

**Convergenza letteratura → verdetto (fase 04):** la letteratura è
**sfavorevole** per l'implementazione S4 specifica: fenomeno parente decaduto,
costi consumano l'edge su stock liquidi, orizzonte tattico breve = edge minimo,
long-only positivo = gamba debole, FinBERT fallback non-predittivo, LLM edge in
decay attivo. Il criterio di promozione del progetto stesso (IC>placebo, P0-13)
**non è confermato** — coerente con la letteratura. Il verdetto propende verso
`UNPROVEN`/`NEGATIVE`: non c'è evidenza accademica che l'implementazione S4
(large-cap, long-only positivo, tattico giornaliero, FinBERT fallback) generi
alpha netto post-cost; il contrario, l'evidenza dice che ogni scelta
dell'implementazione cade sul lato debole/noto-non-predittivo.

---

### Fonti web verificate in questa fase

- [Tetlock 2007 — Giving Content to Investor Sentiment](https://business.columbia.edu/sites/default/files-efs/pubfiles/3096/More_Than_Words_tetlock.pdf)
- [Tetlock-Saar-Tsechansky-Macskassy 2008 — More Than Words](https://business.columbia.edu/sites/default/files-efs/pubfiles/3096/More_Than_Words_tetlock.pdf)
- [García 2013 — Sentiment during Recessions (JF)](https://www.jstor.org/stable/journal10.2301.2)
- [Heston-Sinha 2016 — News vs Sentiment (FEDS)](https://doi.org/10.17016/feds.2016.048)
- [Loughran-McDonald 2011 — When Is a Liability Not a Liability](https://www.jstor.org/stable/journal10.2301.2)
- [Kettell-McInnis-Zhao 2022 — Why Has PEAD Declined](https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf)
- [Chung-Tanaka-Ishii 2023 — PEAD with Textual/Contextual Factors](https://doi.org/10.1145/3604237.3626861)
- [Chordia et al. 2009 — Liquidity and PEAD](https://www.tandfonline.com/doi/abs/10.2469/faj.v65.n4.3)
- [Ng-Rusticus-Verdi 2008 — Transaction Costs for PEAD](https://doi.org/10.1111/j.1475-679x.2008.00290.x)
- [Zhang-Cai-Keasey 2014 — Profitability, Costs, Risk of PEAD](https://link.springer.com/article/10.1007/s11156-013-0386-4)
- [Lopez-Lira-Tang 2023 — Can ChatGPT Forecast Stock Returns](https://doi.org/10.48550/arxiv.2304.07619) / [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4412788)

---
**Stato fase:** 03_literature = **done**. Prossimo cursore: `S4:04_alpha_assessment`.