# S2 — 03 Letteratura

**Strategia:** S2 `VRPStrategy`
**Data:** 2026-08-04
**Metodo:** `WebSearch` su paper canonici VRP, repliche OOS, decay, costi/capacità,
regime, alternative-beta. Le fonti della teoria interna
(`docs/strategies/s2-vrp-theory.md` §5, già 16 fonti peer-reviewed) sono integrate,
non duplicate. Qui si aggiungono repliche recenti (2024-2026) e la prospettiva
alternative-beta. Nessuna citazione è inventata; i DOI/URL sono verificati via
ricerca.

---

## 1. Fonti fondazionali (già in teoria §5 — richiamo breve)

| Fonte | Anno | Contributo per S2 |
|---|---|---|
| [Coval-Shumway](https://doi.org/10.1111/0022-1082.00352) | 2001 | Rendimenti opzioni coerenti con premi per rischio; straddle ATM zero-beta ~−3%/settimana per il compratore → esistenza del VRP lato seller. |
| [Carr-Wu](https://doi.org/10.1093/rfs/hhn038) | 2009 | Seller-sign VRP molto negativo per il compratore su 5 indici; meno uniforme su single-name. Base teorica della definizione in varianza. |
| [Bollen-Whaley](https://doi.org/10.1111/j.1540-6261.2004.00647.x) / [GPP](https://doi.org/10.1093/rfs/hhp005) | 2004/2009 | Pressione di domanda + rischio non copribile → IV e skew. Vincoli intermediari. |
| [Bollerslev-Todorov](https://doi.org/10.1111/j.1540-6261.2011.01695.x) | 2011 | Componente jump/tail materiale nel VRP. |
| [Dew-Becker, Giglio, Le, Rodriguez](https://stefanogiglio.org/papers/dew-becker-giglio-le-rodriguez-jfe-2017.pdf) | 2017 | Solo la **varianza realizzata inattesa e transitoria** è prezzata (Sharpe −1.3); la **varianza news a orizzonte lungo è costless**. Il VRP non è monotono nel VIX. |
| [Bekaert-Engstrom-Ermolov](https://www.nber.org/papers/w27108) | 2023 | VRP Q-P positivo, moderatamente persistente, legato alla coda sinistra dei consumi. |

## 2. Decay post-pubblicazione / OOS recente (cruciale per S2)

| Fonte | Anno | Resultato | Impatto su S2 |
|---|---|---|---|
| [Chicago Fed WP 2025-17 — Dew-Becker & Giglio](https://www.chicagofed.org/publications/working-papers/2025/2025-17) | 2025 | **Negli ultimi 15 anni alpha delle opzioni indistinguibile da zero**; "synthetic options" su 100 anni non mostrano alpha negativo del compratore; modello intermediary-based spiega il decay. | **Decisivo**: il periodo in cui S2 opererebbe (post-2010) è proprio quello in cui il premio netto è collassato. La teoria interna lo cita (§5) come "indicativa ma cruciale". |
| [Yugam2508 SPX VRP 1990-2026](https://github.com/Yugam2508/variance-risk-premium) | 2026 | VRP medio ~4 vol pts ma **decade per decennio**: 1990s 3.96 pts (Sharpe 3.45) → 2000s 2.06 (0.77) → 2010s 2.36 (1.24) → **2020s 1.93 (Sharpe 0.52)**. Skew −6.0, kurtosis 49 (COVID crash: −87.9 vol pts in un periodo). | Il Sharpe 2020s (0.52) è coerente con l'OOS Sharpe −0.613 di S2 — che **sottoperforma** persino il benchmark VRP 2020s perché non cattura il VRP (long-SPY equity, §6 fase 01). |
| [FlashAlpha VRP short-put spreads 7y](https://flashalpha.com/articles/vrp-short-put-spreads-honest-7-year-backtest) | 2026 | Replica OOS "onesta" (post-and-wait, non mid-fill) 2019-2026 su 6 simboli: win rate 64-72% ma **Sharpe da +0.23 a −0.35**, 2/4 simboli OOS in perdita, SPXW flagship Sharpe −0.39. Fill rate 3-14%, adverse selection ~$0.04 vs mid. | **Convergenza**: l'OOS onesto di short-put reali è ~zero; S2 (−0.613) è nella stessa palla. Le repliche "positive" dipendono da fill mid irrealistici (caveat esplicito). |
| [Wysocki — Kelly/VIX put-writing](https://arxiv.org/pdf/2508.16598) | 2025 | Put-writing 0-5 DTE SPXW, OOS 2024: ambiente difficile per premium compresso in bull market; alcune config 14-23% annualizzato OOS con vol più bassa di B&H. | Premium compression 2024 — il "free lunch" del short-put è regime-dipendente. |

## 3. Costi di transazione, capacità / AUM

| Fonte | Anno | Resultato | Impatto su S2 |
|---|---|---|---|
| [Bondarenko — Historical Put-Writing (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3393940) / [Cboe PUT white paper](https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/) | 2019 | PUT index 1986-2018: CAGR 9.54%, vol 9.95%, Sharpe 0.65, beta 0.56, max DD −32.7%; premium mensile ~1.6% (≈18% annuo per il compratore). Usa **VWAP pricing** (11:30-12:00 ET) per riflettere prezzi eseguibili. | Il benchmark istituzionale ha Sharpe 0.65 con fill VWAP realistici e T-bill collateral. S2 non replica né il collateral né i fill VWAP: modella long-SPY equity. |
| [Santa-Clara-Saretto](https://doi.org/10.1016/j.finmar.2009.01.002) | 2009 | Margini, bid-ask, margin call riducono rendimento e capacità delle strategie su opzioni USA. | S2 non modella né bid-ask né margini (catena sintetica, mid-price, BS reprice). |
| [Neuberger Berman — Simply Put(Writing)](https://cdn.cboe.com/resources/indices/whitepapers/Neuberger_Berman_Simply_PutWriting.pdf) | 2022 | AUM crescente in short-vol passivo → **premium yield compression**; loop negativo (più venditori = premi minori); raccomanda gestione attiva; allocazioni tipiche 5-10% equity. | S2 `max_collateral_pct=0.20` è 2× l'allocazione tipica consigliata, e S2 è passivo (nessuna selezione attiva di strike/scadenza oltre delta target). |
| FlashAlpha (sopra) | 2026 | Fill rate 3-14% sotto post-and-wait; adverse selection ~$0.04/contratto. | S2 assume fill a mid su catena sintetica → ignora il costo che erode il VRP reale a ~zero. |

## 4. Regime dependency / non-monotonicità

| Fonte | Anno | Resultato | Impatto su S2 |
|---|---|---|---|
| [Kuang et al. — VRP predicts returns](https://ideas.repec.org/a/taf/apeclt/v31y2024i13p1227-1233.html) | 2024 | VRP **fattore prezzato in mercati bull**, non bear; orizzonte predittivo **più corto in bear**. | S2 `regime_scales[high_vol]=0.0` blocca entry in bear/high_vol — coerente con "VRP meno prezzabile in bear", ma il gate è su **RV passata**, non su VRP condizionale. |
| [Barras-Malkhozov — Two prices of variance risk](https://doi.org/10.1016/j.jfineco.2016.02.014) | 2016 | VRP equity vs VRP opzioni **non identici**; differenza legata a **broker-dealer leverage** e PBI return; quando gli intermediary deleveraging, VRP opzioni cresce, VRP equity no. | S2 scambia lato **equity** (long SPY) — cattura il VRP equity, **non** il VRP opzioni. La teoria (§7) distingue: proxy equity ≠ VRP opzioni. |
| [Koeter — What Drives Variance Swap Prices](https://www.fma.org/assets/docs/Derivatives2025/Koeter.pdf) | 2024 | Term structure: short-term prices = expected variance; long-term = VRP. **Intermediary constraints** drivano VRP, più sul lungo. | S2 DTE 30-45 = short-term → cattura più expected-variance che VRP puro. Coerente con Dew-Becker 2017 (varianza transitoria prezzata). |
| [Cheng 2020 (VIX futures COVID)](https://doi.org/10.1093/rapstu/raaa010) | 2020 | Premi ex ante diventano **negativi** negli shock; prezzi sottoreagiscono. | S2 SIGNAL_FLIP (IV−RV<0) tentativo di gestire questo, ma usa IV di entry stale (DV-7 fase 01). |
| [Chevallier-Vo — Portfolio allocation across VRP](https://ideas.repec.org/eme/jrfpps/jrf-06-2019-0107.html) | 2019 | Modello Markov-switching a 2 stati su VRP; ottimizzazione regime-dipendente. | S2 usa 4 regimi ad-hoc su RV passata, non Markov-switching su VRP. |

## 5. Alternative-beta exposure (è alpha o solo beta di mercato/skew/downside?)

| Fonte | Anno | Resultato | Impatto su S2 |
|---|---|---|---|
| [Schneider-Wagner-Zechner — Low-Risk Anomalies?](https://doi.org/10.1111/jofi.12910) | 2020 | **Alpha dei low-risk anomalies (BaB, BaV) = compensazione per coskewness negativa**, non alpha. Controllando per skewness factor (option-implied), alpha di BaB 125→33 bps/mese, FF4 73→21. >90% varianza LRA da un componente comune spiegato ~80% da fattori skewness. | **Centrale per S2**: il VRP/short-put è short skewness → apparente "alpha" è compensazione per coda negativa. La teoria interna lo dice (M04); Schneider et al. lo dimostrano empiricamente. S2 long-SPY equity + soft-stop al 5% **replica parzialmente** il payoff short-skew ma senza l'incasso di premio. |
| [Patel-Raquel-Chadwick — Cash-secured put-write & VRP](https://link.springer.com/article/10.1057/s41260-023-00333-0) | 2024 | PUTW outperforma fattori 1/3/5; outperformance **spiegata da VRP** aggiunto al fattore mercato; VRP = risk aversion + disaster impact (skew negativa). | Conferma: put-writing = market beta + VRP (skew). S2 NON implementa il lato VRP (long-SPY), quindi mantiene solo market beta senza il premio VRP. |
| [Bollerslev-Paton-Quaedvlieg — Realized semibetas](https://public.econ.duke.edu/~ap172/BPQ_semibeta_2022_JFE.pdf) | 2022 | Beta 4-way: solo **β^N (downside-down) prezzata positivamente**, β^{M−} negativamente; β^P/β^{M+} non prezzate. Long-short semibeta: 8.17% eccesso, Sharpe 0.92. | S2 long-SPY al 20% ha beta mercato uniforme, non isolata sul downside semibeta — nessun edge semibeta. |

## 6. Sintesi per S2

1. **Il fenomeno VRP è reale** (Coval-Shumway, Carr-Wu, Bekaert et al.) ma **decade**:
   Chicago Fed 2025 (alpha ≈0 ultimi 15 anni), Yugam2508 (Sharpe 3.45→0.52 per decennio),
   FlashAlpha (OOS onesto short-put ≈0). Il periodo 2020s in cui S2 opererebbe ha
   Sharpe VRP ~0.52 — basso ma **ancora positivo**; S2 ottiene −0.613 perché **non
   cattura il VRP** (long-SPY equity, §6 fase 01).
2. **Costi/capacità erodono il VRP a ~zero** in replica onesta (FlashAlpha fill rate
   3-14%, adverse selection; Santa-Clara-Saretto margini; Neuberger compression AUM).
   S2 non modella nessuno di questi (catena sintetica, fill a mid, niente margini).
3. **Regime**: VRP prezzato in bull, debole in bear (Kuang 2024); S2 blocca high_vol
   ma su RV passata, non VRP condizionale. Term structure: short-DTE cattura
   expected variance più che VRP puro (Koeter, Dew-Becker 2017).
4. **Alternative-beta dominante**: VRP = compensazione per coskewness/downside
   (Schneider et al. 2020; Patel et al. 2024). Il rendimento di put-writing non è
   alpha dopo controlli skewness. S2, scambiando long-SPY, ha **solo market beta** —
   né il premio VRP né l'esposizione skew short che lo giustificherebbe.
5. **Proxy equity ≠ VRP**: Barras-Malkhozov 2016 distinguono VRP equity vs VRP opzioni;
   la teoria interna (§7, M05) vieta la proxy equity come "VRP". S2 è la proxy vietata.

**Convergenza letteratura → verdetto (fase 04):** la letteratura supporta che il VRP
**esiste ma decade a ~zero netto post-2020**, e che il rendimento apparente è
alternative-beta (skew/downside) non alpha. La letteratura **non** supporta l'uso di
`IV−RV` passata come definizione del premio né di long-SPY come strumento VRP —
entrambi esplicitamente sconsigliati. L'implementazione S2 adopera entrambi.

---

### Fonti web verificate in questa fase

- [Chicago Fed WP 2025-17](https://www.chicagofed.org/publications/working-papers/2025/2025-17)
- [Yugam2508/variance-risk-premium (GitHub)](https://github.com/Yugam2508/variance-risk-premium)
- [FlashAlpha — VRP short-put spreads 7y](https://flashalpha.com/articles/vrp-short-put-spreads-honest-7-year-backtest)
- [Wysocki — Kelly/VIX put-writing (arXiv)](https://arxiv.org/pdf/2508.16598)
- [Bondarenko — Historical Put-Writing (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3393940)
- [Cboe PUT white paper](https://www.cboe.com/insights/posts/white-paper-shows-volatility-risk-premium-facilitated-higher-risk-adjusted-returns-for-put-index/)
- [Neuberger Berman — Simply Put(Writing)](https://cdn.cboe.com/resources/indices/whitepapers/Neuberger_Berman_Simply_PutWriting.pdf)
- [Kuang et al. 2024](https://ideas.repec.org/a/taf/apeclt/v31y2024i13p1227-1233.html)
- [Barras-Malkhozov 2016](https://doi.org/10.1016/j.jfineco.2016.02.014)
- [Koeter 2024](https://www.fma.org/assets/docs/Derivatives2025/Koeter.pdf)
- [Chevallier-Vo 2019](https://ideas.repec.org/eme/jrfpps/jrf-06-2019-0107.html)
- [Schneider-Wagner-Zechner 2020](https://doi.org/10.1111/jofi.12910)
- [Patel-Raquel-Chadwick 2024](https://link.springer.com/article/10.1057/s41260-023-00333-0)
- [Bollerslev-Paton-Quaedvlieg 2022](https://public.econ.duke.edu/~ap172/BPQ_semibeta_2022_JFE.pdf)
- [Dew-Becker, Giglio, Le, Rodriguez 2017](https://stefanogiglio.org/papers/dew-becker-giglio-le-rodriguez-jfe-2017.pdf)

---
**Stato fase:** 03_literature = **done**. Prossimo cursore: `S2:04_alpha_assessment`.