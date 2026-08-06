# S7 — 03 Letteratura

**Strategia:** S7 `PEADStrategy` (Post-Earnings Announcement Drift)
**Data:** 2026-08-04
**Metodo:** WebSearch su PEAD canonico, decay, transaction costs, transcript
tone, analyst revisions. Fonti citate con URL. Nessuna citazione fabbricata.

## PEAD — stato del fenomeno (decay / resurgence)

| Studio | Periodo | Finding | Impatto S7 |
|---|---|---|---|
| **Martineau 2021** "Rest in Peace PEAD" ([osf.io/z7k3p](https://doi.org/10.31235/osf.io/z7k3p)) | US, post-2006 | PEAD **inesistente** per large-cap dal 2006, microcap dal 2016. Prezzi 6× più reattivi al giorno dell'annuncio vs anni '80. | S7 ALPHA-A5 = large-cap → **edge competuto** (coerente con FAIL n=76). |
| **Kettell-McInnis-Zhao 2022** "Why Has PEAD Declined?" ([Columbia](https://business.columbia.edu/sites/default/files-efs/imce-uploads/CEASA/Events%20Page/PEAD_Declined_over_time.pdf)) | US multi-periodo | Declino PEAD spiegato da **persistenza SUE calante** (non solo arbitraggio). Controllando la persistenza, il trend al ribasso è insignificante. PEAD concentrato nei "stayers". | Edge numerico (raw surprise) declina perché le sorprese sono **meno persistenti** → il drift che S7 cercava è strutturalmente in erosione. |
| **Nyllinge-Oldenburg 2025** "Resurgence of PEAD" ([SSE](http://arc.hhs.se/download.aspx?MediumId=6317)) | US large-cap 2021-2024 | Large-cap 60d drift 0.52% (2005-20) → **1.99% (2021-24)**, +280%. Hedge returns ~2.17%→8.29%. Non spiegato da retail/passivo. | **Sfida il verdetto "competuto"** per large-cap post-2020. MA: S7 è rimossa 2026-07-15 (pre-resurgence, basata su dati 2026-07). Resurgence è 2021-24, n=4 anni, non ancora stabile; l'universo di S7 era large-cap ALPHA-A5, non lo stesso taglio. **Non salva S7**: il progetto non aveva questa evidenza al momento della decisione, e la resurgence è ambigua. |
| **Kaczmarek-Zaremba 2025** "Reviving PEAD with ML" ([RePEc](https://ideas.repec.org/a/eee/finlet/v86y2025ipes1544612325020057.html)) | US large-cap | Elastic net su storico multi-trimestre SUE → Sharpe ~raddoppia. Edge vivo nei large-cap quando si usa **storico** (non solo last surprise). | S7 usava **last surprise** (surprise_pct corrente) → forma debole. La forma "revival" (ML su storico) è diversa dall'implementazione S7. |

**Convergenza (stato fenomeno)**: PEAD canonico è **in declino strutturale**
(large-cap competuto dal 2006, Kettell 2022: persistenza SUE calante). Una
**possible resurgence post-2020** (Nyllinge 2025) è documentata MA ambigua
(4 anni, non robusta, meccanismo non chiaro). S7 era configurata sulla forma
**competuta** (large-cap, last surprise) — l'universo dove l'edge accademico
moderno è **minimo**. L'universo dove l'edge vivo sopravvive è **small-cap**
(v. sotto) — non raggiunto da S7 (POC-1 INCONCLUSIVE_DATA, n=15, copertura
IEX insufficiente).

## PEAD — transaction costs / capacità / universo

| Studio | Finding | Impatto S7 |
|---|---|---|
| **Ng-Rusticus-Verdi 2008** ([JAR](https://onlinelibrary.wiley.com/doi/10.1111/j.1475-679X.2008.00290.x)) | Costi di transazione **constraining** i trades informativi → PEAD persiste perché non sfruttabile dopo costi. ERC più bassi per firme ad alto costo. | S7 ALPHA-A5 large-cap: costi bassi → arbitraggio possibile → edge già competuto (coerente). MA S7 sizing pari-peso 5% su large-cap liquide → costi bassi non salvano un edge ~zero. |
| **Chordia-Goyal-Sadka-Shridhar 2009** ([FAJ](https://www.tandfonline.com/doi/abs/10.2469/faj.v65.n4.3)) | Long-short SUE: **0.04%/mese** (liquid) vs **2.43%/mese** (illiquido). Costi consumano **70-100%** dei profitti carta. PEAD persiste perché **unexploitable after costs**. | S7 large-cap = lato 0.04%/mese (near-zero). L'edge vivo è **small/mid illiquido** → costi consumano ma edge grosso → small-cap net 3.8% (Quant Decoded). S7 non raggiungeva small-cap. |
| **Zhang-Cai-Keasey 2014** ([Springer](https://link.springer.com/article/10.1007/s11156-013-0386-4)) | Event-study **overstated** PEAD; dopo costi, **nessun alpha** in multi-factor. | S7 backtest (mai runnato a OOS) avrebbe rischiato lo stesso overstatement. |
| **Quant Decoded 2025** ([quantdecoded.com](https://quantdecoded.com/en/post-earnings-drift-by-market-cap-size-matters)) | Net drift 60d: micro 2.8%, **small 3.8%** (massimo net), mid 2.8%, large 1.6%, mega 1.5%. Micro→mega ratio 3.2-4.3× stabile 2000-2025. | **L'universo S7 (large-cap ALPHA-A5) è il quintile col minore net drift (1.6%)**. L'edge vivo è small-cap — non raggiunto da S7. Conferma la FAIL su large-cap. |

**Convergenza (costi/universo)**: la letteratura è **coerente col FAIL di S7
su large-cap** (ALPHA-A5 n=76: drift=beta, hit 51%, no dose-response).
L'edge vivo (small-cap net 3.8%) richiede un universo che S7 non raggiungeva
(copertura IEX insufficiente, POC-1 n=15). **L'universo è la ragione strutturale
del FAIL numerico** di S7, non il segnale tone.

## Transcript tone — l'alpha-specifico di S7 (POC-2)

S7 dichiarava edge **qualitativo** (transcript tone via LLM, ALPHA-A3) — non
numerico. La letteratura tone è **mista e orizzonte-dipendente**:

| Studio | Finding | Impatto S7 |
|---|---|---|
| **Hameleers 2025** (Tilburg, LLaMA-3.1-70B, n=188.501 transcripts 2002-17) ([Tilburg](http://arno.uvt.nl/show.cgi?fid=188469)) | Q&A confidence predice CAR[2,60] **0.99pp**, robusto dopo controllo SUE. Long-short **Sharpe >1 a 5-10g**, alpha **decade a orizzonti lunghi**. Q&A > presentation. | S7 hold **20g** → orizzonte dove tone alpha **decade** (Hameleers: Sharpe>1 a 5-10g, decade dopo). S7 hold 20d è **troppo lungo** per il tone edge (che vive 5-10g). Mismatch di orizzonte. |
| **Chung-Tanaka-Ishii 2023** (ICAIF, ChatGPT+SBERT, S&P500 2010-22) ([ACM](https://doi.org/10.1145/3604237.3626861)) | Embedding contestuali (SBERT) → +53-354bps su baseline. **MA: textual features (readability, sentiment) da sole peggiorano OOS post-2020.** | S7 usava **polarity/tone sentiment** (textual) → la forma che **peggiora OOS post-2020**. L'edge vivo è **embedding contestuale**, non polarity. S7 implementava la forma debole (come S4). |
| **Druz-Wagner-Zeckhauser 2015** (NBER WP 20991, S&P500 2004-12) ([NBER](https://www.nber.org/system/files/working_papers/w20991/w20991.pdf)) | "Tone surprise" (negatività residua) predice future earnings + analyst uncertainty. **Eccesso di negatività > positività**. Drift **parziale (no reversal)** → under-reazione razionale incompleta. | S7 long-only **beat** = gamba **positiva** = la **debole** (negatività predice più forte). Anche il tone canonico favorisce short/miss — S7 monetizza il lato debole. |
| **Zhang-Yang 2026** (Finance Research Letters, Cina A-share) ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612326007622)) | Tone ottimista → reazioni short-window + revisioni analisti. Vaghezza/shift attenuano. | Coerente (tone positivo → drift), MA Cina A-share (mercato meno efficiente). Non US large-cap. |

**Convergenza (tone)**: la letteratura **supporta** un edge di tone **MA con
tre caveat critici per S7**:
1. **Orizzonte**: edge vivo a **5-10g** (Hameleers Sharpe>1), decade a 20g (S7
   hold = 20d → troppo lungo, alpha già decaduto).
2. **Feature**: edge vivo è **embedding contestuale** (SBERT), non polarity
   sentiment (Chung 2023: polarity peggiora OOS post-2020). S7 usava polarity.
3. **Direzione**: negatività predice più forte (Druz 2015), short/miss è la gamba
   forte. S7 long-only beat = gamba debole.

**POC-2 FAIL (IC +0.012, n=73) è coerente** con: polarity tone su US large-cap,
hold 20d, long-only → combinazione specificamente sulla forma debole/decaduta.
La **cross-model agreement kimi↔glm ρ=+0.858** (FAIL robusto) suggerisce che
non è un artefatto del modello — è la **forma** (polarity, large-cap, 20d) che
non ha edge. Due LLM indipendenti concordano sul "tone polarity non predice
excess_20d su US large-cap" → coerente con Chung 2023 (polarity peggiora OOS).

## Analyst revisions — il carburante del drift (Vettore D / ALPHA-D1)

| Studio | Finding | Impatto S7 |
|---|---|---|
| **Livnat-Nissim 2006** (JAR, [Wiley](https://onlinelibrary.wiley.com/doi/10.1111/j.1475-679X.2006.00196.x)) | PEAD calcolato da **analyst forecasts** vs time-series forecasts → differenze; analyst-based più informativo. | S7 usava LLM-parse (non consensus reale, ALPHA-A2 mai wired) → **carburante debole/assente**. |
| **Analyst Underreaction, Post-Forecast Revision Drift** (SSRN 2578757) | Drift post-**revision** analisti (sotto-reazione analisti → drift). | ALPHA-D1 (analyst revisions come trigger) era nel design S7 MA mai wired. |
| **Zhang 2008** "Analyst responsiveness & PEAD" ([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0165410108000220)) | Drift concentrato dove analisti **meno responsivi**. | Large-cap = alta responsività analisti → poco drift (coerente col FAIL S7). |

**Convergenza (analyst)**: il carburante del drift PEAD sono le **revisioni
analisti** (Vettore D). S7 non le usava (ALPHA-D1 mai wired, ALPHA-A2 consensus
mai wired) → il segnale era **tone polarity dall'8-K**, la forma meno predittiva.

## Sintesi letteratura

| Dimensione | Letteratura | Implementazione S7 | Allineamento |
|---|---|---|---|
| Fenomeno (PEAD large-cap) | competuto dal 2006 (Martineau, Kettell) | ALPHA-A5 large-cap | ❌ competuto (FAIL confermato) |
| Fenomeno (PEAD small-cap) | vivo, net 3.8% (Quant Decoded) | non raggiunto (POC-1 n=15) | ❌ universo sbagliato |
| Tone orizzonte | vivo 5-10g, decade 20g (Hameleers) | hold 20d | ❌ orizzonte troppo lungo |
| Tone feature | embedding contestuale vivo, polarity decade (Chung) | polarity sentiment | ❌ feature debole |
| Tone direzione | negatività > positività (Druz) | long-only beat | ❌ gamba debole |
| Carburante | analyst revisions (Livnat, Vettore D) | LLM-parse, consensus mai wired | ❌ carburante assente |
| Costi | consumano 70-100% (Chordia) su illiquido; ~null su large-cap | large-cap liquido | ⚠️ costi bassi ma edge ~zero |
| Resurgence post-2020 | ambigua, +280% large-cap (Nyllinge) | rimossa 2026-07 (pre-evidenza) | ⚠️ non salva S7 (decisione su dati 2026-07) |

**Conclusione letteratura**: la letteratura è **coerente col FAIL di S7 su ogni
dimensione che S7 poteva controllare** (universo large-cap competuto, orizzonte
troppo lungo per tone, feature polarity debole, direzione long-only debole,
carburante consensus/revisioni assente). L'unica potenziale via di salvezza
(small-cap + embedding contestuale + orizzonte 5-10g + direzione simmetrica) è
**l'opposto dell'implementazione S7**. La decisione di rimozione (PO-5,
POC-2 FAIL) è **congrua con la letteratura** — non un errore di esecuzione ma
la corretta conclusione su una strategia configurata sulla forma competuta
del fenomeno.

**Confronto con S1/S4**: S1 (momentum) e S4 (sentiment news) soffrono dello
stesso pattern (polarity, large-cap, long-only, orizzonte mismatch) MA sono
ancora live. S7 è stata rimossa perché il progetto l'ha **misurata a sample
decision-grade** (POC-2 n=73) e il FAIL era robusto cross-modello. La
differenza non è l'ipotesi (tutte e tre sono deboli) ma la **governance**: S7
ha avuto un POC pre-registrato con kill criterion; S1/S4 no.

---
**Stato fase:** 03_literature = **done**. Prossimo cursore: `S7:04_alpha_assessment`.