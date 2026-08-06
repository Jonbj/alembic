# S1 — 03 Letteratura scientifica

**Strategia:** S1 Multi-Lookback Relative Momentum
**Data:** 2026-08-04
**Metodo:** WebSearch su fonti accademiche primarie (JFE, NBER, SSRN). Nessuna citazione fabbricata; ogni voce ha URL verificabile.

## 3.1 Fondazione accademica (l'anomalia originale)

- **Jegadeesh & Titman (1993)**, "Returns to Buying Winners and Selling Losers", *Journal of Finance* — fondazione del **momentum cross-sectionale**: long vincitori / short perditori basato su rendimento passato 3–12m produce anomalia non spiegata dal CAPM. S1 implementa il lato long di questo con z-score cross-sectionale.
- **Moskowitz, Ooi & Pedersen (2012)**, "Time Series Momentum", *JFE* 104(2):228–250 — [DOI 10.1016/j.jfineco.2011.11.003](https://doi.org/10.1016/j.jfineco.2011.11.003). TSM su 58 strumenti: il rendimento passato 12m predice positivamente il rendimento futuro ~1 anno, poi parzialmente si inverte. Sharpe >1.0, alpha ~1.58%/mese. **S1 non è TSMOM canonico** (nessun segnale 12-1, nessuna gamba short, lookback multipli).

## 3.2 Repliche e risultati contrastanti (la sfida alla TSM)

- **Huang, Li, Wang & Zhou (2020)**, "Time Series Momentum: Is it There?", *JFE* 135(3):774–794 — [IDEAS](https://ideas.repec.org/a/eee/jfinec/v135y2020i3p774-794.html). **Sfida diretta**: asset-by-asset la TSM è statisticamente debole; il t-stat pooled non è affidabile (sotto le critical values bootstrap). La strategia TSM è "profittevole" ma **virtualmente identica a una strategia basata sulla media campionaria storica** — non richiede prevedibilità. → L'evidenza "forte" di S1 sul momentum TS è più debole di quanto il paper del 2012 suggerisca.
- **Ahn, Hambusch & Hong (2026)**, "How Overlapping Returns Inflate Measured Time Series Momentum", *JRFM* 19(1):46 — [DOI 10.3390/jrfm19010046](https://doi.org/10.3390/jrfm19010046). I rendimenti sovrapposti generano autocorrelazione meccanica → il profilo monotono di TSM cresce col lookback **artefattualmente**. Con rendimenti **non-sovrapposti** l'effetto è più debole e non monotono. → S1 usa `prices / prices.shift(lb) - 1` (rendimenti sovrapposti su lookback 21/63/126/252) — esattamente la meccanica che il paper segnala come artefatto.
- **Grobys (2024)**, "Science or Scientism? On the Momentum Illusion", *Annals of Finance* — [Springer](https://link.springer.com/article/10.1007/s10436-024-00446-5). Critica radicale: le varianze del momentum seguono power-law con esponente α<2 → media/varianza teorica **infinita** → t-stat e Sharpe **non definiti**. → Da prendere cum grano (metodologia contestata), ma relevante perché S1 riporta Sharpe/backtest senza testare heavy tails.

## 3.3 Decadimento post-pubblicazione (decay)

- **Ben-David, Li, Rossi & Song (2021)**, "Discontinued Positive Feedback Trading and the Decline of Momentum Profitability", NBER WP 28624 — [PDF](https://www.nber.org/system/files/working_papers/w28624/revisions/w28624.rev2.pdf). **Cruciale per S1**: il rendimento mensile del fattore momentum US è crollato da **0.92% (pre-2002) a 0.16% (post-2002)**; il factor-momentum da 0.61% a 0.14%. Il decadimento è **US-specifico** (mercato di S1). ~27–34% del declino spiegato dal canale McLean-Pontiff (arbitraggio post-pubblicazione); il resto da una riforma Morningstar 2002 che ha rotto il feedback-trading via flussi fondi. → L'anomalia su cui S1 scommette è **decaduta ~5–6×** nel mercato dove S1 opera. Un backtest S1 che include dati pre-2002 sovrastima massivamente l'alpha atteso oggi.
- **McLean & Pontiff (2016)** (citato indirettamente sopra) — le anomalie pubblicamente note decadono ~30% OOS per arbitraggio. S1 è noto internamente e la sua specifica è standard → atteso decay.

## 3.4 Costi di transazione e capacità

- **Frazzini, Israel & Moskowitz (2015)**, "Trading Costs of Asset Pricing Anomalies", SSRN — [PDF AQR](https://spinup-000d1a-wp-offload-media.s3.amazonaws.com/faculty/wp-content/uploads/sites/3/2021/08/Trading-Cost-of-Asset-Pricing-Anomalies.pdf). Su $1T di dati live, i costi reali sono ~10× inferiori alle stime TAQ; momentum US break-even ~$56B (non ottimizzato), ~$160B ottimizzato; turnover ~119%/mese, costi ~3%/anno a $5B+. → A scala carta Alembic la capacità non è un vincolo; ma i **3%/anno di costi** sì.
- **Patton & Weller (2020)**, "What you see is not what you get: The costs of trading market anomalies", *JFE* — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304405X20300453). **Contraddice** Frazzini-et-al: costi all-in **7.2–7.6%/anno** per fondi mutualistici che implementano momentum → elimina gran parte dei profitti; ~metà del costo è l'impossibilità di shortare. → Per S1 **long-only** la metà "impossibilità di shortare" non si applica (non shorta), ma i costi di turnover elevato restano.
- **Ratcliffe, Miranda & Ang (2017)**, "Capacity of Smart Beta Strategies", BlackRock, SSRN 2861324 — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2861324). Capacità momentum ~$65B (1d) → $320B (5d). Non vincolante per Alembic.
- **Israel, Moskowitz, Ross & Serban (2017)**, "Implementing Momentum: What Have We Learned?", AQR, SSRN 3081165 — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3081165). 7 anni di dati live: il momentum cattura il premio **anche netto di costi/spese/tasse**. → Evidenza pro-S1, ma per momentum long-short istituzionale, non long-only retail.

**Tensione centrale:** studi su dati live AQR → momentum netto-positivo; studi su dati di fondo Patton-Weller → momentum ~neutro netto per fondi tipici. S1 è più vicino al caso "fondo tipico" che al caso "AQR istituzionale".

## 3.5 Dipendenza di regime / crash

- **Daniel & Moskowitz (2016)**, "Momentum Crashes", *JFE* 122(2):221–247 — [DOI 10.1016/j.jfineco.2015.12.002](https://doi.org/10.1016/j.jfineco.2015.12.002), [NBER 20439](https://www.nber.org/papers/w20439), [PDF Kent Daniel](https://www.kentdaniel.net/papers/published/jfe_16.pdf). Crashed momentum: skewness mensile −4.70; 14/15 peggiori mesi con mercato a 2 anni negativo. Meccanismo: in bear market il portafoglio WML diventa **long titoli a bassa beta / short titoli a alta beta** → si comporta come **short call** sul mercato; i perdenti (high beta) salgono 3–5× al rebound. → **Per S1 long-only** il meccanismo short-leg NON si applica direttamente (S1 non shorta i perdenti), MA: (a) S1 resta esposto al beta di mercato long-only nei drawdown; (b) il regime "bear + rebound" dove il momentum inverte penalizza comunque il segnale long (i "vincitori" di un bear market sono titoli difensivi che sottoperformano al rebound). S1 **non ha** il meccanismo di mitigazione che Daniel-Moskowitz propongono (vol-scaling dinamico).
- **Barroso & Santa-Clara (2015)**, "Momentum has its moments", *JFE* 116(1):111–120 — [DOI 10.1016/j.jfineco.2014.11.010](https://doi.org/10.1016/j.jfineco.2014.11.010). Vol-scaling del momentum a volatilità costante **quasi raddoppia** lo Sharpe (0.53→0.97) ed **elimina** quasi i crash (kurtosis 18.24→2.68). → **S1 fa una versione debole di questo**: vol-normalizza il *segnale per-asset* (divide rendimento per σ realizzata) e fa sizing inverso-vol per-position, ma **non** vol-scales l'intera sleeve a volatilità costante. Il beneficio di BSC deriva dal scaling aggregato del portafoglio nei regimi di alta volatilità, non dalla normalizzazione per-asset del segnale. → S1 **cattura solo parzialmente** il benefit documentato.

## 3.6 Esposizione a alternative-beta (è alpha o è beta?)

- **Israel & Ross (2017)**, "Measuring Factor Exposures", AQR — [PDF AQR](https://www.aqr.com/-/media/AQR/Documents/Insights/White-Papers/JAI_Summer_2017_AQR.PDF). Portafogli style **long-only** hanno beta di mercato ~0.96; l'alpha apparente (6.1% CAPM) collassa a **1.8%** nel modello a 4 fattori. → S1, essendo long-only, è strutturalmente **dominato dal beta di mercato**; l'alpha residuo dopo decomposizione fattoriale è modesto.
- **Roncalli (2017)**, "Keep Up The Momentum", Amundi — [PDF](https://research-center.amundi.com/files/nuxeo/dl/b233d158-ea1a-4409-8d56-364cfb78f040). TSM/trend-following è **net long** (~52% equity exposure) → la sua resa è **beta time-varying + risk premia leverage**, non alpha. Il momentum è "una strategia di beta, non di alpha".
- **Chong et al. (2017)**, "Profitability of CAPM Momentum Strategies" — [DOI 10.33736/ijbs.545.2017](https://doi.org/10.33736/ijbs.545.2017). Long-only winners: beta ~0.9–1.0; market-neutral (con short leg) Sharpe >1.5. La gamba short **isola** l'alpha puro; senza, il rendimento è per lo più beta.
- **Brito-Ramos, Renò, Tédongap & Zhang (2025)**, "Pure Momentum", Amundi/ESSEC — [PDF](https://research-center.amundi.com/files/nuxeo/dl/d7bc1c57-7420-4526-8dd4-af51d5ff5fb3?inline=). **Evidenza favorevole al long-only**: filtrando trend "puri" (salti/volatilità esclusi), long-only winners netti dei costi hanno Sharpe **0.55** (significativo); la gamba short **non** è profittevole netta dei costi. I "pure winners" sono titoli **large, liquidi, low-vol, high-volume** → sovrapponibile al tilt di S1 (universo mega-cap + sizing inverso-vol). → Unico segnale letterario che giustifica alpha netto long-only per S1, **ma** richiede filtraggio del trend "puro" che S1 **non** implementa.

## 3.7 Sintesi valutata per S1

| Dimensione | Verdetto letteratura | Implicazione per S1 |
|---|---|---|
| Anomalia originale | Robusta in-sample (JT-1993, MOP-2012) | S1 è un'istanza legitima ma non canonica |
| Replica OOS | Debole asset-by-asset (Huang 2020); artefatto overlapping (Ahn 2026) | S1 usa rendimenti sovrapposti → segnale parzialmente artefatto |
| Decadimento | Momentum US 0.92%→0.16%/mese post-2002 (Ben-David 2021) | **Decisivo**: mercato di S1, anomalia ~6× più debole oggi |
| Costi | 3–7.6%/anno (Frazzini vs Patton-Weller); long-only evita il costo short | S1 esposto a costo di turnover, no costo short |
| Capacità | $56–320B | Non vincolante per Alembic |
| Regime/crash | Crashes in bear+rebound (Daniel-Moskowitz 2016); vol-scaling aiuta (BSC 2015) | S1 no short-leg (meno crash mechanism) ma no vol-scaling aggregato → non cattura il miglioramento Sharpe |
| Alternative-beta | Long-only = beta mercato ~0.96 + tilt momentum; alpha 6.1→1.8% (Israel-Ross) | **S1 è prevalentemente beta**, non alpha |
| Long-only alpha netto | Possibile solo con filtraggio "pure trend" (Brito-Ramos 2025) | S1 **non** filtra trend puri → non cattura questo canale |

## 3.8 Mappatura delle scelte di design di S1 vs letteratura

| Scelta di S1 | Letteratura | Allineamento |
|---|---|---|
| Lookback 252d **senza skip-month** | JT/MOP usano 12-1 (skip ultimo mese) per evitare reversal 1m | ⚠️ S1 include 21d (peso piccolo) → esposizione al reversal breve |
| Vol-normalizzazione del segnale per-asset | Non standard; simile a Moreira-Muir vol-management ma per-asset | ⚠️ Proprietaria; non validata come alpha |
| Z-score cross-sectionale + soglia 0 (gate binario) | JT-1993 ranking; ma lo **strength** del segnale scala l'esposizione | ⚠️ S1 non scala per strength (gate binario) → perde carry informativo |
| Long-only, no short leg | Israel-Ross/Chong: long-only = beta dominante | ⚠️ S1 strutturalmente beta-esposto |
| Sizing inverso-vol per-position (target_vol 0.10) | BSC vol-scale l'**intera sleeve**, non per-position | ⚠️ S1 fa risk-parity naive, non vol-targeting aggregato → non cattura raddoppio Sharpe BSC |
| Rebalance MONTHLY | Coerente con momentum mensile | ✅ |
| Universo mega-cap | Brito-Ramos: pure winners = large/low-vol/liquid | ✅ allineato al canale long-only-profitable |

## 3.9 Esposizione fattoriale attesa di S1 (pre-04)

Sintesi a priori (da confermare in `04_alpha_assessment` contro evidenza di progetto):
- **Beta di mercato: alto** (long-only, no short).
- **Fattore momentum (Carhart/UMD): per costruzione presente** ma nella versione long-only, indebolito.
- **Low-volatility tilt: indiretto** (sizing inverso-vol sovrappesa titoli a bassa σ).
- **Alpha netto atteso: basso–modesto**, dominato dal decadimento US post-2002 e dai costi di turnover; possibili solo se il tilt long-only su mega-cap low-vol cattura il canale Brito-Ramos, che S1 **non** filtra esplicitamente.

---
**Stato fase:** 03_literature = **done**. Prossimo cursore: `S1:04_alpha_assessment`.