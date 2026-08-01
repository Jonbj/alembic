# Momentum azionario — catalogo di ipotesi falsificabili dalla letteratura primaria

**Data:** 2026-08-01
**Preparato per:** Alembic Trading System — programma di backtest con ipotesi pre-registrate su S1
**Scope:** quattro aree richieste (orizzonti/skip-month, crash e vol-scaling, decadimento post-pubblicazione, residual/industry momentum)
**Vincolo di metodo:** solo fonti primarie (journal, NBER, pagina autore, dati CRSP/French). Dove ho potuto leggere solo l'abstract, è dichiarato riga per riga.

---

## 0. Come leggere questo documento

### 0.1 Vincoli operativi che decidono "testabile / non testabile"

| Vincolo S1 | Conseguenza per la letteratura |
|---|---|
| **Long-only** (SELL solo per chiudere) | Tutti i risultati "winners-minus-losers" (WML) sono **non direttamente applicabili**. Serve sempre la scomposizione per gamba. |
| **Universo fisso 96 large-cap US + ETF settoriali** | Niente small/micro-cap. I decili CRSP (≈300-500 titoli ciascuno) non esistono da noi: un "decile" su 96 nomi sono ~10 titoli. Spread cross-sezionale più stretto e più rumoroso. |
| **Solo barre giornaliere** | Niente fondamentali point-in-time, niente short interest, niente earnings/analyst data, niente intraday. |
| **Ribilanciamento ogni 15 min, holding medio ~14 giorni** | **Questo è il disallineamento più grave con la letteratura**: JT93, Novy-Marx, HXZ, Barroso-Santa-Clara, Daniel-Moskowitz misurano tutti holding da 1 a 12 **mesi**. Nessuno di questi paper stabilisce alcunché su un holding di 14 giorni. |
| **Capitale ~$110K** | I costi di transazione contano in proporzione al turnover, non alla size. Un holding di 14 giorni implica ~18 rotazioni/anno vs 2 di una 6/6. |

### 0.2 Fonti di dati usate per i calcoli propri

Diversi numeri qui sotto sono **calcoli miei** su dati primari della **Kenneth R. French Data Library** (file `F-F_Momentum_Factor`, `10_Portfolios_Prior_12_2` (monthly + daily), `10_Portfolios_Prior_1_0`, `10_Portfolios_Prior_60_13`, `49_Industry_Portfolios`, `F-F_Research_Data_Factors`), versione costruita sul database CRSP 202605, **serie fino a maggio 2026**.
URL: <https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html>

Sono etichettati **[CALCOLO PROPRIO]**. Sono statistiche descrittive lorde (nessun costo di transazione, nessun impatto), servono a *datare il decadimento*, non a stimare un P&L. Non sostituiscono i paper.

**Tabella di riferimento — decadimento del momentum su dati French, VW, prior 12-2** [CALCOLO PROPRIO]

| Periodo | WML (win-los) %/mese | t | Decile winner − mercato %/mese | t | Decile loser − mercato %/mese | t |
|---|---|---|---|---|---|---|
| 1927-01 … 1993-12 (pre-pubbl. JT93) | **1.352** | 5.09 | **0.657** | 5.55 | −0.696 | −3.56 |
| 1994-01 … 2026-05 (post-pubbl.) | 0.731 | 1.66 | 0.373 | 1.91 | −0.358 | −1.03 |
| 2009-04 … 2026-05 | **0.277** | 0.46 | 0.296 | 1.15 | **+0.019** | 0.04 |
| 1927-01 … 2026-05 (full) | 1.150 | 5.01 | 0.564 | 5.53 | −0.586 | −3.38 |

Lettura: il long-short è morto (t=0.46 su 17 anni) **perché è morta la gamba short** — dal 2009 il decile loser non sottoperforma più il mercato (+0.02%/mese). La gamba long ha perso ~55% del suo edge ma resta positiva in ogni finestra. Per un book long-only questa asimmetria è la notizia più importante dell'intero documento.

### 0.3 Convenzione sui "prior"

- **forte** = effetto replicato out-of-sample da autori indipendenti, su large-cap, con la gamba giusta (long), e sopravvissuto a HXZ (2020) con t > 3.
- **medio** = effetto solido in-sample ma con almeno uno tra: decadimento documentato, dipendenza dalla gamba short, evidenza contraddittoria, universo diverso dal nostro.
- **debole** = effetto contestato, o già smontato, o testabile solo in forma degradata dai nostri vincoli.

---

## 1. AREA 1 — Orizzonti di formazione e detenzione

### 1.1 Cosa dicono davvero le fonti

**Jegadeesh & Titman (1993)** — *Returns to Buying Winners and Selling Losers*, Journal of Finance 48(1), 65-91.
Fonte letta integralmente: <https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf> (copia universitaria del paper).
Universo NYSE+AMEX, gennaio 1965 – dicembre 1989, decili **equal-weighted**, portafogli sovrapposti.

Tabella I, valori mensili (t fra parentesi):

| J/K | Panel A (nessun gap) | Panel B (gap di **1 settimana**) |
|---|---|---|
| 6/6 buy−sell | 0.95% (3.07) | 1.10% (3.61) |
| 6/6 **buy leg** | **1.74% (4.33)** | 1.78% (4.41) |
| 6/6 sell leg | 0.79% (1.56) | 0.68% (1.35) |
| 3/3 buy−sell | 0.32% (1.10) | **0.73% (2.61)** |
| 12/3 buy−sell | 1.31% (3.74) | **1.49% (4.28)** |

Due fatti che quasi tutte le sintesi di terze parti sbagliano:
1. **Il gap in JT93 è di UNA SETTIMANA, non di un mese.** Lo skip-month non è di JT93.
2. Il guadagno del gap è **concentrato sulle formazioni corte**: +0.41 pp/mese su J=3, +0.15 pp su J=6, +0.18 pp su J=12. È coerente con l'idea che il gap serve a evitare la reversal di brevissimo periodo, non ad "attivare" il momentum.

Tabella VII (event time, strategia 6-mesi): mese 1 = **−0.25% (t=−0.59)**, poi positivo per tutto l'anno 1; cumulato +9.51% a 12 mesi (t=3.67), che decade a +4.06% al mese 36. Il mese 1 negativo è la reversal *dentro* JT93.

Tabella VI, **sottocampione large-cap (S3)**, buy−sell 6/6 per quinquennio: 65-69 **1.29% (2.71)**, 70-74 1.15% (1.62), 75-79 0.18% (0.35), 80-84 0.76% (1.41), 85-89 **0.35% (0.73)**. Cioè: già *dentro* il campione originale, sui titoli grandi, il momentum era statisticamente non significativo negli ultimi due quinquenni. Chi cita "JT93 → 1%/mese" su un book large-cap sta citando il numero sbagliato.
Tabella IV, S3, febbraio-dicembre: 0.96%/mese (t=4.00); gennaio −1.61% (t=−1.28, non significativo per i grandi).

**Jegadeesh (1990)** — *Evidence of Predictable Behavior of Security Returns*, JF 45(3), 881-898.
**Solo abstract verificato** (il full text disponibile era una scansione senza layer di testo; Wiley HTTP 402). Serial correlation del primo ordine negativa e altamente significativa nei rendimenti mensili; serial correlation positiva a lag più lunghi, particolarmente a 12 mesi; spread fra decili estremi **2.49%/mese, 1934-1987**.
<https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1990.tb05110.x>

**Lehmann (1990)** — *Fads, Martingales, and Market Efficiency*, QJE 105(1), 1-28. **Solo abstract verificato.** Reversal **settimanale**: i vincitori e i perdenti di una settimana si invertono la settimana dopo, con profitti apparenti che sopravvivono a bid-ask spread e costi plausibili. <https://academic.oup.com/qje/article-abstract/105/1/1/1928416> · NBER w2533 <https://www.nber.org/papers/w2533>

**De Bondt & Thaler (1985)** — *Does the Stock Market Overreact?*, JF 40(3), 793-805. **Solo abstract verificato.** Reversal a 3-5 anni; l'effetto è **asimmetrico, molto più forte sui loser**; i loser hanno rendimenti di gennaio eccezionali fino a 5 anni dopo la formazione. <https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.1985.tb05004.x>
Nota di JT93 (nota 6): De Bondt-Thaler riportano rendimenti a 1 anno *coerenti* con il momentum, ma non analizzano l'orizzonte annuale in dettaglio.

**Novy-Marx (2012)** — *Is momentum really momentum?*, JFE 103(3), 429-453. **Full text non raggiungibile** (ScienceDirect 403; la pagina dell'autore rimanda al paywall). Dall'abstract dell'editore e dalla scheda EconPapers: il momentum è guidato dalla performance **t−12…t−7** ("intermediate horizon"), non dalla continuazione recente; la strategia value-weighted ristretta ai titoli grandi su quintili t−12…t−7 rende **≈10%/anno, gen 1927 – dic 2010**. Il numero del 10% l'ho visto solo in sintesi dell'abstract, **non l'ho verificato in tabella**.
<https://www.sciencedirect.com/science/article/abs/pii/S0304405X11001152> · <https://econpapers.repec.org/RePEc:eee:jfinec:v:103:y:2012:i:3:p:429-453>

**Goyal & Wahal (2015)** — *Is Momentum an Echo?*, JFQA 50(6), 1237-1267. Contraddice Novy-Marx fuori dagli USA: l'echo c'è negli USA, ma **in 37 paesi non-USA non c'è evidenza robusta**, né nei portafogli combinati sviluppati+emergenti, né nelle tre macro-regioni. <https://sites.google.com/view/agoyal145/> (pagina autore)

**Hou, Xue & Zhang (2020)** — *Replicating Anomalies*, RFS 33(5), 2019-2133. Letto integralmente: <https://global-q.org/uploads/1/2/2/6/122679606/houxuezhang2020rfs.pdf>. Campione **gen 1967 – dic 2016**, NYSE breakpoints + value-weighted (microcap neutralizzati).

| Segnale (definizione HXZ) | %/mese NYSE-VW | t |
|---|---|---|
| R¹¹1 — formazione t−12…t−2, hold 1m | **1.16** | 3.99 |
| R¹¹6 — formazione t−12…t−2, hold 6m | 0.80 | 3.13 |
| R¹¹12 — formazione t−12…t−2, hold 12m | 0.43 | 1.93 |
| R⁶1 — formazione t−7…t−2, hold 1m | 0.60 | 2.08 |
| R⁶6 — formazione t−7…t−2, hold 6m | 0.82 | 3.50 |
| R⁶12 — hold 12m | 0.55 | 2.91 |
| 52w1 — 52-week high, hold 1m | 0.13 | 0.38 |

E la replica diretta di JT93: nel campione originale con All-EW ottengono 1.18% (t=4.22); **nel campione esteso lo stesso segnale scende a 0.70% (t=2.63)**.
Nota: **anche il loro "R⁶" salta il mese t−1** (t−7…t−2), quindi non è la 6/6 di JT93. Vanno confrontati con cautela.

### 1.2 Ipotesi — Area 1

---

#### H1 — La componente a 21 giorni del segnale S1 ha segno sbagliato o è nulla

| campo | contenuto |
|---|---|
| **Enunciato** | Rimuovere la componente a 21 giorni dal segnale multi-lookback di S1 (o pesarla negativamente) non peggiora l'IC a 1-3 mesi; su un universo large-cap value-weighted la componente t−1…t−0 ha oggi coefficiente statisticamente indistinguibile da zero, non negativo. |
| **Fonte primaria** | Jegadeesh (1990) JF 45(3) 881-898 (abstract); Lehmann (1990) QJE 105(1) 1-28 (abstract); JT93 Tab. I Panel A vs B e Tab. VII mese 1 = −0.25% (t=−0.59); [CALCOLO PROPRIO] su `10_Portfolios_Prior_1_0` |
| **Periodo campionario** | J1990: 1934-1987 CRSP. Lehmann: 1962-1986 settimanale. JT93: 1965-1989 NYSE+AMEX EW. Calcolo proprio: 1926-2026 |
| **Effetto atteso** | Storicamente forte: spread decili 2.49%/mese (J1990, EW). **Oggi molto diverso.** [CALCOLO PROPRIO] decili prior 1-0, Hi−Lo: VW pre-1994 −1.17%/mese (t=−5.76) → 1994-2026 **+0.006% (t=0.02)** → 2009+ +0.05% (t=0.11). EW pre-1994 −3.15% (t=−14.72) → 1994-2026 −0.89% (t=−2.84) → 2009+ −0.33% (t=−0.89) |
| **Decadimento** | Massiccio e documentato. Chordia, Subrahmanyam & Tong (2014) JAE 58(1) 41-58: le anomalie si sono circa **dimezzate dopo la decimalizzazione**, con la reversal di breve fra le più colpite. Il mio calcolo dice che sul VW (large-cap) la reversal a 1 mese è **completamente sparita** dal 1994 |
| **Testabile da noi?** | **Sì.** Serve solo la serie dei prezzi giornalieri dell'universo. Nessuno short richiesto: si testa se il *peso* sulla componente 21g migliora o peggiora il ranking long-only |
| **Prior** | **medio-forte** che la componente a 21 giorni non aggiunga nulla; **debole** che sia negativa (la reversal large-cap è morta). L'implicazione pratica è "rimuovila o portala a zero", non "invertila" |

---

#### H2 — Lo skip-month migliora il segnale S1 meno di quanto dica il folklore

| campo | contenuto |
|---|---|
| **Enunciato** | Sostituire la formazione t−252…t−0 con t−252…t−21 (skip di un mese) non migliora significativamente l'IC a 1-3 mesi su 96 large-cap US nel periodo 2010-2026; l'effetto atteso è ≤ +0.15 pp/mese e non separabile dal rumore su questo campione |
| **Fonte primaria** | JT93 Tab. I Panel B (**gap di 1 settimana**, non un mese); Fama & French (1996) adottano t−12…t−2 come convenzione (segnale "R11" in HXZ); HXZ (2020) Tab. 3 |
| **Periodo campionario** | JT93 1965-1989; HXZ 1967-2016 |
| **Effetto atteso** | JT93: +0.15 pp/mese su J=6 (0.95→1.10), +0.18 pp su J=12. HXZ non offrono un confronto pulito skip/no-skip (entrambe le loro definizioni saltano t−1). La stima onesta del beneficio dello skip su formazione lunga è **+0.1÷0.2 pp/mese, in EW small-cap-inclusive, negli anni '60-'80** |
| **Decadimento** | Non misurato direttamente in letteratura. Indirettamente: se il beneficio dello skip deriva dall'evitare la reversal a breve (H1), e la reversal large-cap è sparita dal 1994 [CALCOLO PROPRIO], **il beneficio dello skip deve essere calato di conseguenza** |
| **Testabile da noi?** | **Sì**, banalmente (è una modifica di due indici nel calcolo del lookback) |
| **Prior** | **debole-medio.** È l'ipotesi più sopravvalutata dell'area: il paper che tutti citano usa una settimana, il beneficio è piccolo, ed è legato a un effetto (reversal) che sui large-cap non c'è più. Vale un test perché costa zero, non perché ci si aspetti molto |

---

#### H3 — L'holding period di ~14 giorni è fuori dalla finestra in cui il momentum esiste

| campo | contenuto |
|---|---|
| **Enunciato** | Allungare l'holding minimo di S1 da ~14 giorni a ≥60 giorni di trading (con un gate anti-riacquisto) aumenta l'IC medio per unità di turnover; la versione a 14 giorni non ha alcun supporto in letteratura e paga costi ~4× superiori per lo stesso segnale |
| **Fonte primaria** | JT93 Tab. VII (mese 1 = −0.25%, mesi 2-9 tutti > +0.85%); HXZ (2020) Tab. 3 (hold 1m, 6m, 12m); Moskowitz & Grinblatt (1999) JF 54(4) 1249-1290 (l'holding a 1 mese ha turnover che "sembra precludere i profitti dopo i costi di transazione") |
| **Periodo campionario** | 1965-1989; 1967-2016; 1963-1995 |
| **Effetto atteso** | JT93: il rendimento in event-time è **negativo al mese 1** e massimo ai mesi 2-9. HXZ: R¹¹1 = 1.16%/mese ma è un hold di 1 mese *ribilanciato mensilmente*; passando a hold 12m scende a 0.43% (t=1.93). Nessuna evidenza pubblicata a orizzonte di 2-3 settimane |
| **Decadimento** | N/A — non è un'anomalia, è un mismatch di orizzonte |
| **Testabile da noi?** | **Sì**, ma richiede un backtest con contabilità dei costi (spread + commissioni Alpaca) altrimenti il test è vuoto |
| **Prior** | **forte** che l'holding attuale sia troppo corto rispetto alla finestra documentata. È probabilmente l'ipotesi con il rapporto (valore atteso)/(costo del test) più alto dell'intero catalogo |

---

#### H4 — Echo / intermediate horizon (t−252…t−126) domina il recent horizon (t−126…t−21)

| campo | contenuto |
|---|---|
| **Enunciato** | Un segnale costruito solo sui rendimenti t−252…t−126 produce IC a 1-3 mesi maggiore di uno costruito solo su t−126…t−21, sullo stesso universo e periodo |
| **Fonte primaria** | Novy-Marx (2012) JFE 103(3) 429-453 — **solo abstract, full text non raggiungibile** |
| **Periodo campionario** | Gen 1927 – dic 2010, CRSP US; il risultato citato è specificamente **value-weighted, titoli grandi, quintili** — cioè il caso più vicino al nostro |
| **Effetto atteso** | ≈10%/anno per il long-short quintile VW large-cap (numero non verificato in tabella) |
| **Decadimento** | Contraddizione diretta: **Goyal & Wahal (2015) JFQA 50(6) 1237-1267** non trovano echo robusto in 37 paesi non-USA né nei portafogli globali. Se l'effetto è solo USA e solo in-sample fino al 2010, è un candidato classico a data-mining geografico |
| **Testabile da noi?** | **Sì** (solo prezzi) |
| **Prior** | **debole.** Una fonte primaria non verificabile in tabella + una contraddizione pubblicata su 37 mercati. Se lo si testa, va testato come *singola* ipotesi (non come griglia di finestre), altrimenti alza la soglia per tutti gli altri test senza motivo |

---

## 2. AREA 2 — Momentum crashes e scalatura per volatilità

### 2.1 Cosa dicono davvero le fonti

**Daniel & Moskowitz (2016)** — *Momentum crashes*, JFE 122(2), 221-247. Letto integralmente (open access CC-BY): <https://www.kentdaniel.net/papers/published/jfe_16.pdf>. Campione **1927:01 – 2013:03**, decili CRSP.

Tabella 1 (annualizzato, %):

| | Decile 1 (loser) | Decile 10 (winner) | WML | Mercato |
|---|---|---|---|---|
| r − rf | −2.5 | **15.3** | 17.9 | 7.7 |
| σ | 36.5 | 23.7 | 30.0 | 18.8 |
| α (CAPM) | −14.7 | **7.5** | 22.2 | 0 |
| t(α) | (−6.7) | **(5.1)** | (7.3) | — |
| β | 1.61 | 1.03 | −0.58 | 1 |
| Sharpe | −0.07 | **0.65** | 0.60 | 0.41 |
| skew mensile | +0.09 | **−0.82** | **−4.70** | −0.57 |

**Il punto decisivo per un book long-only** (sezione 2.3, punto 5, citazione letterale):
> "Closer examination reveals that the crash performance is mostly attributable to the short side or the performance of losers. For example, in July and August of 1932, the market rose by 82%. Over these two months, the winner decile rose by 32%, but the loser decile was up by 232%. Similarly, over the three-month period from March to May of 2009, the market was up by 26%, but the loser decile was up by 163%. Thus, to the extent that the strong momentum reversals we observe in the data can be characterized as a crash, they are a crash in which **the short side of the portfolio — the losers — crash up, not down**."

Beta asimmetrica in bear market: up-beta −1.51 vs down-beta −0.70, t della differenza = 4.5. Fuori dai bear market non c'è differenza affidabile.

Tabella 7 (Sharpe annualizzati, 1934:01 – 2013:03):

| Strategia | Sharpe | Appraisal ratio vs riga precedente |
|---|---|---|
| WML statica | 0.682 | — |
| cvol (scalata per volatilità realizzata 126gg) | 1.041 | 0.786 |
| scalata per **varianza** | 1.126 | 0.431 |
| dinamica, out-of-sample | 1.194 | 0.396 |
| dinamica, in-sample | 1.202 | 0.144 |

**Barroso & Santa-Clara (2015)** — *Momentum has its moments*, JFE 116(1), 111-120. Letto sulla versione "Forthcoming in JFE, this version November 2014" degli autori (copia mirrorata su un sito terzo con annotazioni di un lettore in cima — **il corpo del paper è quello degli autori, le annotazioni non lo sono**): <http://www.snifferquant.com/gyantal/Incode/papers/Momentum%20Has%20Its%20Moments(scaling%20Momentum%20by%20vol),2014.pdf>. Pagina editoriale: <https://econpapers.repec.org/RePEc:eee:jfinec:v:116:y:2015:i:1:p:111-120>

Campione **1927:03 – 2011:12**, dati Ken French, WML = decile alto meno decile basso su t−12…t−2.

| | WML raw | WML risk-managed |
|---|---|---|
| Media annua | 14.46% | — |
| σ annua | 27.53% | (target costante) |
| Excess kurtosis | 18.24 | **2.68** |
| Skewness | −2.47 | **−0.42** |
| Sharpe | 0.53 | **0.97** |
| Peggior mese | −78.96% | **−28.40%** |
| Max drawdown | −96.69% | **−45.20%** |

Meccanica: scalano il long-short per la **varianza realizzata dei rendimenti giornalieri della WML nei 6 mesi precedenti**. R² out-of-sample dell'AR(1) sulla varianza realizzata mensile = **57.82%**, 19.01 pp sopra la stessa autoregressione sulla varianza del mercato. La componente di mercato è solo **23%** del rischio totale del momentum (R² OOS 20.87%), la componente specifica è il 77% ed è molto più prevedibile (R² OOS 47.06%): è per questo che l'hedging con beta time-varying di Grundy-Martin fallisce e la vol-scaling funziona. Turnover della versione risk-managed ≈ turnover della raw.

**Nota critica, verificata nel testo:** né BSC né Daniel-Moskowitz testano **mai** una versione long-only. BSC lo dicono esplicitamente in nota 13, contrapponendo la persistenza del rischio della WML a quella di "a long-only portfolio of assets, such as the market". La domanda "la vol-scaling funziona anche long-only?" **non ha risposta in questi due paper.**

### 2.2 Evidenza che ho prodotto io sulla domanda long-only

[CALCOLO PROPRIO] Ho replicato la meccanica BSC (peso mensile = σ_target / σ̂, con σ̂ = volatilità realizzata annualizzata dei 126 giorni precedenti della *stessa* serie; ribilanciamento mensile; target 12%) su tre serie: la WML, il decile winner al netto del mercato (= gamba long attiva) e — variante realizzabile da un book long-only che non può levereggiare — la stessa scalata con **peso limitato a w ≤ 1** (si può solo *ridurre* e tenere cassa).

**Campione completo 1928-01 … 2026-05**

| Serie | ann.% | σ ann.% | Sharpe | skew | ex-kurt | peggior mese |
|---|---|---|---|---|---|---|
| WML raw | 13.54 | 27.5 | 0.49 | −2.13 | 15.43 | −77.66% |
| WML vol-scaled | 19.73 | 22.2 | **0.89** | −0.23 | 1.75 | −25.21% |
| Winner − mercato, raw | 6.60 | 12.2 | 0.54 | −0.30 | 5.07 | −21.06% |
| Winner − mercato, vol-scaled | 10.66 | 15.1 | **0.71** | +0.04 | 1.21 | −21.50% |
| Winner − mercato, vol-scaled **cap w≤1** | 6.56 | 10.5 | **0.63** | +0.04 | 2.32 | **−12.01%** |

**Sottocampione post-pubblicazione 1994-01 … 2026-05**

| Serie | ann.% | Sharpe | peggior mese |
|---|---|---|---|
| WML raw | 8.77 | 0.29 | −45.18% |
| WML vol-scaled | 11.18 | 0.53 | −25.21% |
| Winner − mercato, raw | 4.47 | 0.34 | −14.26% |
| Winner − mercato, vol-scaled | 6.03 | 0.44 | −11.49% |
| Winner − mercato, vol-scaled cap w≤1 | 4.52 | 0.39 | −11.49% |

**Risposta alla domanda posta:** la vol-scaling funziona anche long-only, **ma vale circa metà**. Sul campione pieno lo Sharpe della WML sale di +0.40 (0.49→0.89); quello della gamba long attiva sale di +0.17 senza vincoli e di **+0.09 con il cap realizzabile w≤1**. Post-1994: +0.24 sulla WML, +0.05 sulla long-only con cap. Il beneficio che *resta* long-only non è l'eliminazione del crash (quello è un fenomeno della gamba short, come dice Daniel-Moskowitz), ma la **normalizzazione delle code**: excess kurtosis 5.07 → 2.32 e peggior mese −21.1% → −12.0%. In termini di rendimento medio, la versione con cap ne lascia sul tavolo praticamente zero (6.60 → 6.56 annuo).

### 2.3 Ipotesi — Area 2

---

#### H5 — La vol-scaling long-only migliora lo Sharpe ma non il rendimento

| campo | contenuto |
|---|---|
| **Enunciato** | Scalare l'esposizione di S1 per la volatilità realizzata a 126 giorni della sua stessa serie di rendimenti attivi, con peso limitato a ≤1, riduce la kurtosi e il peggior mese di ≥40% lasciando il rendimento medio invariato entro ±10%; **non** aumenta il rendimento medio |
| **Fonte primaria** | Barroso & Santa-Clara (2015) JFE 116(1) 111-120; Daniel & Moskowitz (2016) JFE 122(2) 221-247 Tab. 7; **estensione long-only = [CALCOLO PROPRIO]**, perché nessuno dei due paper la testa |
| **Periodo campionario** | BSC 1927:03-2011:12; DM 1934:01-2013:03; calcolo proprio 1928-01…2026-05 e 1994-01…2026-05 |
| **Effetto atteso** | Long-short: Sharpe 0.53→0.97 (BSC), 0.682→1.041 (DM). **Long-only con cap w≤1: Sharpe 0.54→0.63 full sample, 0.34→0.39 post-1994; ex-kurt 5.07→2.32; peggior mese −21.1%→−12.0%; rendimento 6.60%→6.56% annuo** |
| **Decadimento** | Il beneficio della vol-scaling non è un'anomalia di pricing ma una proprietà della prevedibilità della varianza (R² OOS 57.82%, BSC) — non ci si aspetta decadimento. Infatti nel mio calcolo il miglioramento di Sharpe sopravvive post-1994 |
| **Testabile da noi?** | **Sì.** S1 ha già uno strato di vol-normalization e di `vol_scale`; il test è se scalare per la vol *della strategia* invece che per la vol *dei singoli titoli* cambia le code. Un book long-only non può levereggiare, quindi va testata **solo** la versione con cap |
| **Prior** | **forte** sul beneficio in code/Sharpe, **forte anche sul fatto che non sia un generatore di rendimento**. Attenzione a non venderla internamente come "raddoppia lo Sharpe": quel numero è della gamba short |

---

#### H6 — Il crash di momentum non è un rischio rilevante per un book long-only

| campo | contenuto |
|---|---|
| **Enunciato** | I mesi identificati in letteratura come "momentum crash" (rimbalzi di mercato dopo forti ribassi, con volatilità ex-ante alta) producono su un portafoglio long-only di vincitori una perdita relativa al mercato di ordine ≤ 1/3 di quella della corrispondente strategia long-short |
| **Fonte primaria** | Daniel & Moskowitz (2016) sez. 2.3 punto 5 e Tab. 1 (citazione letterale in §2.1) |
| **Periodo campionario** | 1927:01 – 2013:03 |
| **Effetto atteso** | Lug-ago 1932: mercato +82%, winners +32%, losers **+232%**. Mar-mag 2009: mercato +26%, losers **+163%**. [CALCOLO PROPRIO] peggiori 6 mesi: WML −77.7 / −62.4 / −45.2 / −44.4 / −41.8 / −39.2; winner−mercato −21.1 / −21.0 / −16.2 / −14.3 / −13.7 / −12.0. Skewness mensile: WML −4.70 (DM Tab. 1), winner decile −0.82, mia serie winner−mercato −0.30 |
| **Decadimento** | N/A (è una proprietà strutturale, non un'anomalia) |
| **Testabile da noi?** | **Sì** come test di robustezza/stress, non come generatore di alpha. Va testato su eventi datati (2009-03…05, 2020-03…06, 2022) |
| **Prior** | **forte.** Attenzione: il decile winner ha comunque skew −0.82 mensile (DM Tab. 1), *più negativa* di quella dei loser (+0.09). Il long-only non è privo di code, ha code **diverse e molto più piccole** |

---

#### H7 — Un gate di regime basato su (bear market × volatilità di mercato alta) migliora S1

| campo | contenuto |
|---|---|
| **Enunciato** | Ridurre l'esposizione di S1 quando il mercato è sotto il suo massimo a 24 mesi **e** la volatilità realizzata del mercato è nel quartile alto, migliora lo Sharpe rispetto a esposizione costante |
| **Fonte primaria** | Daniel & Moskowitz (2016), specificazione dell'indicatore di "panic state" I_B · σ²_m e Tab. 7 (dyn OOS Sharpe 1.194) |
| **Periodo campionario** | 1927:07 – 2013:03; coefficienti in expanding window da ott 1930 |
| **Effetto atteso** | Long-short: passando da cvol (1.041) a dinamica OOS (1.194), appraisal ratio 0.396. **Ma DM stessi scompongono questo guadagno in due metà**: metà viene dallo scalare per varianza invece che per deviazione standard, metà dal forecast della media. Il pezzo "regime" è quindi ~metà di ~0.15 di Sharpe |
| **Decadimento** | DM mostrano che il coefficiente di forecast sale *prima* dei crash 2001 e 2009 ma anche che nel 2001/2009 il segnale ha inizialmente sbagliato (il momentum andò bene mentre il mercato continuava a scendere). Fuori campione dopo il 2013 non è verificato da loro |
| **Testabile da noi?** | **Parziale.** Il meccanismo economico di DM è che in panic state i *loser* diventano opzioni out-of-the-money con beta esplosiva — **non abbiamo la gamba loser**. Quindi trasferiamo l'indicatore ma non il canale causale. Il test resterebbe un timing di esposizione generico |
| **Prior** | **debole per S1.** Alembic ha già un `regime_mult` e un `F8 regime_scale` con storia di problemi (shadow mai persistito, reset TTL nel weekend). Aggiungere una seconda leva di regime non testata contro un canale causale che non ci riguarda è il modo migliore per bruciare budget di test multipli |

---

## 3. AREA 3 — Decadimento post-pubblicazione (il filtro)

### 3.1 Cosa dicono davvero le fonti

**McLean & Pontiff (2016)** — *Does Academic Research Destroy Stock Return Predictability?*, Journal of Finance 71(1), 5-32.

**Attenzione: due versioni con numeri diversi.** Ho letto integralmente il working paper del 16 maggio 2013 (<https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf>): **82 caratteristiche**, decadimento out-of-sample ≈ **10%** (non statisticamente diverso da zero), decadimento post-pubblicazione ≈ **35%**. La versione pubblicata su JF 2016 riporta invece **97 predittori, −26% out-of-sample e −58% post-pubblicazione**, con la differenza di 32 pp attribuita al trading informato dalla pubblicazione. **Non sono riuscito ad accedere al testo pubblicato** (Wiley HTTP 402; RePEc non riporta l'abstract): i numeri 26/58 li ho solo da riassunti dell'abstract editoriale. Uso 26/58 come riferimento *dichiarando* che non l'ho verificato alla fonte, e segnalo la discrepanza con la bozza.
Pagina editoriale: <https://onlinelibrary.wiley.com/doi/10.1111/jofi.12365>

Un dettaglio del WP direttamente rilevante (sez. introduttiva, verificato nel testo): McLean & Pontiff citano come esempio di **messaggi contraddittori** il fatto che *"Jegadeesh and Titman (2001) show that the relative returns to high-momentum stocks **increased** after the publication of their 1993 paper"*.

**Jegadeesh & Titman (2001)** — *Profitability of Momentum Strategies*, JF 56(2), 699-720. Letto integralmente: <http://www-stat.wharton.upenn.edu/~steele/Courses/434/434Context/Momentum/MomentumStrategiesJF2001.pdf>. Tabella I, 6/6, equal-weighted, esclusi titoli < $5 e decile size più piccolo:

| Campione | All stocks P1−P10 | t | **Large cap P1−P10** | t |
|---|---|---|---|---|
| 1965-1998 | 1.23% | 6.46 | 0.86% | 4.34 |
| 1965-1989 (in-sample) | 1.17% | 4.96 | 0.85% | 3.55 |
| **1990-1998 (out-of-sample)** | **1.39%** | 4.71 | **0.88%** | 2.59 |

E la scomposizione per gamba, 1990-1998: i winner battono l'indice equal-weighted di **0.56%/mese**, i loser lo sottoperformano di **0.67%/mese** — "entrambi contribuiscono all'incirca allo stesso modo".
Post-holding, mesi 13-60: −0.07%/mese, non significativo.

**Hou, Xue & Zhang (2020)** RFS 33(5): con NYSE breakpoints e value-weighting, **65% delle 452 anomalie non superano |t| > 1.96**; alzando la soglia multiple-testing a 2.78 il tasso di fallimento sale all'**82%**. Il price momentum è fra i sopravvissuti (tabella in §1.1). Il loro stesso confronto mostra però il decadimento: JT93 replicato All-EW 1.18% (t=4.22) nel campione originale → **0.70% (t=2.63)** nel campione esteso.

**Harvey, Liu & Zhu (2016)** — *… and the Cross-Section of Expected Returns*, RFS 29(1), 5-68. Letto sul NBER WP 20592 (<https://www.nber.org/system/files/working_papers/w20592/w20592.pdf>): **316 fattori** censiti; un nuovo fattore deve superare **t > 3.0**; con Holm su 316 fattori la soglia è **3.64**, su 113 fattori "comuni" è **3.29**. Conclusione degli autori: "most claimed research findings in financial economics are likely false".

**Chen & Zimmermann (2020)** — *Publication Bias and the Cross-Section of Stock Returns*, Review of Asset Pricing Studies 10(2). **Solo abstract verificato** (<https://academic.oup.com/raps/article-abstract/10/2/249/5640503>). I rendimenti corretti per publication bias sono solo **12.3% più bassi** (s.e. 1.7 pp) di quelli in-sample: il bias di data-mining è **troppo piccolo** per spiegare il decadimento post-pubblicazione osservato → il decadimento è per lo più **reale** (arbitraggio), non un artefatto statistico. **Questo non contraddice McLean-Pontiff**, lo rafforza nella direzione peggiore per noi: se il calo è arbitraggio vero, non tornerà indietro.

**Chordia, Subrahmanyam & Tong (2014)** — JAE 58(1), 41-58. Abstract verificato: le anomalie si sono circa **dimezzate dopo la decimalizzazione**; il calo è collegato a AUM degli hedge fund, short interest e turnover aggregato.

**Israel & Moskowitz (2013)** — *The role of shorting, firm size, and time on market anomalies*, JFE 108(2), 275-301. Letto integralmente: <https://gritcap.com/enoalroa/2020/10/Israel-and-Moskowitz-The-role-of-shorting-firm-size-and-time-on-market-anomalies-2012.pdf>. Lug 1926 / gen 1927 – dic 2011.
- Le posizioni long fanno "quasi tutto" del size, il 60% del value e **circa metà** dei profitti di momentum.
- Il premio momentum **non ha relazione affidabile con la size** (a differenza del value, che è debole fra i titoli più grandi).
- **Long-only momentum: alpha CAPM 5.55%/anno, volatilità residua 7.60%, information ratio 0.73** — contro 0.26 per il long-only value e 0.19 per il long-only size.
- UMD: alpha 12.23%/anno 1927-62 e 9.21% 1963-2011; positiva e significativa in **tutti e quattro** i sotto-periodi ventennali, con alpha fra 8.9% e 10.3%.
- Non trovano evidenza che i rendimenti di size/value/momentum siano stati significativamente influenzati da cambi di costi di transazione o di ownership istituzionale/hedge fund.

### 3.2 Ipotesi — Area 3

---

#### H8 — Il momentum long-only large-cap è decaduto di circa metà ma non è morto

| campo | contenuto |
|---|---|
| **Enunciato** | Nel periodo 2010-2026 su large-cap US, un portafoglio long-only dei vincitori a 12-2 mesi batte il mercato di **0.2-0.4%/mese**, non di 0.6-0.7% come nel campione pre-1994; e il differenziale **non** raggiunge significatività statistica su un campione di 15 anni |
| **Fonte primaria** | [CALCOLO PROPRIO] su Ken French `10_Portfolios_Prior_12_2` VW, fino a 2026-05; corroborato da HXZ (2020) Tab. 3 e da JT93 Tab. VI sottocampione S3 |
| **Periodo campionario** | 1927-2026 con split a 1994 e 2009; HXZ 1967-2016; JT93 1965-1989 |
| **Effetto atteso** | Winner − mercato: 0.657%/mese (t=5.55) pre-1994 → 0.373% (t=1.91) 1994-2026 → **0.296% (t=1.15) dal 2009**. Nello stesso tempo la WML crolla da 1.352 (t=5.09) a **0.277 (t=0.46)** e il decile loser smette del tutto di sottoperformare (**+0.019%/mese, t=0.04, dal 2009**) |
| **Decadimento** | È l'ipotesi *sul* decadimento. McLean-Pontiff: −58% post-pubblicazione in media (numero non verificato alla fonte pubblicata) — il mio −55% sulla gamba long e −80% sul long-short sono coerenti. Chen-Zimmermann: solo ~12 pp del calo sono attribuibili a publication bias → il resto è arbitraggio reale. Chordia et al.: dimezzamento post-decimalizzazione. **Contraddizione storica**: JT2001 documentava che nel 1990-1998 il momentum era *aumentato* (1.39% vs 1.17%) — il decadimento è arrivato dopo il 2000, non subito dopo la pubblicazione |
| **Testabile da noi?** | **Sì**, ed è il test di calibrazione da fare **per primo**: fissa l'ordine di grandezza dell'effetto atteso e quindi la potenza richiesta a tutti gli altri test |
| **Prior** | **forte** sul decadimento; **medio** sulla sopravvivenza di un residuo positivo sulla gamba long. Nota che con t≈1.2 su 15 anni di dati mensili **non si può dimostrare che l'effetto esiste**: si può solo dimostrare che è ≤ una certa soglia |

---

#### H9 — Sull'universo Alembic (96 nomi) l'effetto atteso è ulteriormente diluito rispetto ai decili CRSP

| campo | contenuto |
|---|---|
| **Enunciato** | Replicando il segnale 12-2 sui 96 titoli dell'universo Alembic invece che sui decili CRSP, lo spread top-decile-meno-mercato risulta inferiore di ≥25% rispetto al benchmark CRSP VW sullo stesso periodo, per effetto della compressione cross-sezionale dell'universo |
| **Fonte primaria** | JT93 Tab. VI sottocampione S3 (large firms): 6/6 buy−sell scende a 0.35%/mese (t=0.73) nel 1985-89; JT2001 Tab. I large cap 0.86% vs 1.42% small cap; Israel & Moskowitz (2013) in senso *contrario* ("no reliable relation with size") |
| **Periodo campionario** | 1965-1989; 1965-1998; 1926-2011 |
| **Effetto atteso** | JT93/JT2001 suggeriscono un fattore ~0.6 large vs small. Israel-Moskowitz negano una relazione affidabile con la size. **Due fonti primarie in conflitto: lo riporto invece di scegliere.** La compressione da 96 nomi (decile ≈ 10 titoli) è una questione di potenza statistica, non di size, e su questa non ho trovato letteratura |
| **Decadimento** | N/A |
| **Testabile da noi?** | **Sì**, ed è un test di *calibrazione dell'aspettativa*, non di alpha. Va fatto prima di pre-registrare le soglie |
| **Prior** | **medio.** Il conflitto JT93/JT2001 vs Israel-Moskowitz è reale. Il pezzo davvero certo è che con 96 nomi la varianza campionaria dello spread è molto più alta |

---

#### H10 — Soglia di significatività da applicare a tutto il programma

| campo | contenuto |
|---|---|
| **Enunciato** | Nessun risultato del programma di backtest va considerato azionabile con \|t\| < 3.0; con 10-13 ipotesi pre-registrate la soglia corretta (Holm/Bonferroni al 5% su 13 test) è \|t\| ≈ 3.0-3.1 |
| **Fonte primaria** | Harvey, Liu & Zhu (2016) RFS 29(1) 5-68 (letto su NBER WP 20592): t > 3.0 come hurdle per un nuovo fattore; Holm su 113 fattori = 3.29, su 316 = 3.64. Hou, Xue & Zhang (2020): con soglia 2.78 l'82% delle anomalie fallisce |
| **Periodo campionario** | HLZ: censimento dei fattori 1967-2012, proiezione a 20 anni. HXZ: 1967-2016 |
| **Effetto atteso** | Non è un'ipotesi di rendimento, è il **vincolo di disegno** del programma |
| **Decadimento** | N/A |
| **Testabile da noi?** | **Non è testabile: è un vincolo.** Va scritto nel protocollo di pre-registrazione |
| **Prior** | **forte.** Implicazione operativa dura: con l'effetto atteso di H8 (≈0.3%/mese su vol mensile ~3.5%) servono **oltre 100 mesi** di dati per raggiungere t=3 anche se l'effetto fosse reale e stabile. **Un backtest su 5 anni non può falsificare né confermare H8.** Questo va detto prima di iniziare, non dopo |

---

## 4. AREA 4 — Residual/idiosyncratic momentum e momentum settoriale

### 4.1 Cosa dicono davvero le fonti

**Blitz, Huij & Martens (2011)** — *Residual Momentum*, Journal of Empirical Finance 18(3), 506-521. Letto sul manoscritto accettato depositato nel repository Erasmus: <http://repub.eur.nl/pub/22252/ResidualMomentum-2011.pdf>

Metodo: formazione **12-1M** (12 mesi escluso l'ultimo). I residui vengono da una regressione rolling a **36 mesi** dei rendimenti in eccesso del titolo sui **tre fattori Fama-French** (mercato, SMB, HML); il residuo cumulato è poi **standardizzato per la sua deviazione standard** sulla stessa finestra. Universo CRSP US, gen 1926 – dic 2009 (rendimenti di portafoglio da gen 1930), esclusi titoli sotto $1.

Risultati verificati nel testo:
- Le esposizioni ai fattori FF sono **3-5 volte più piccole** che nel momentum su rendimenti totali.
- I profitti risk-adjusted del residual momentum sono **circa il doppio** del momentum su rendimenti totali; Sharpe fra **0.4 e 0.9** a seconda dell'holding period; rendimenti comparabili "a metà del rischio".
- **Sottocampione large-cap** (il decile più grande per capitalizzazione), holding a 1 mese: momentum totale **Sharpe 0.36** vs residual **Sharpe 0.60**. Gli autori concludono che "le conclusioni principali restano quasi immutate" ristretti ai large cap.
- J=6, K=9: totale Sharpe 0.23 vs residuale 0.62.
- Versione **non standardizzata** (residuo grezzo, senza dividere per σ), holding 1 mese: 11.88%/anno, vol 13.28%, Sharpe 0.89 — quindi la standardizzazione aiuta soprattutto a *ridurre il rischio*, non ad aumentare il rendimento.

**Hou, Xue & Zhang (2020)** replicano il residual momentum su 1967-2016 NYSE-VW:

| | %/mese | t |
|---|---|---|
| ρ¹¹1 (residual 12-2, hold 1m) | 0.61 | 3.72 |
| ρ¹¹6 | 0.50 | 3.82 |
| ρ¹¹12 | 0.33 | 2.88 |
| ρ⁶6 | 0.45 | 3.74 |
| (confronto) R¹¹1 price momentum | 1.16 | 3.99 |
| (confronto) R¹¹6 price momentum | 0.80 | 3.13 |

Lettura onesta: il residual momentum ha rendimenti **grezzi più bassi** del price momentum, ma **t-stat uguali o superiori** e più stabili al crescere dell'holding period (ρ¹¹12 t=2.88 vs R¹¹12 t=1.93). Il vantaggio è di rischio, non di rendimento — esattamente quello che dicono BHM.

**Blitz, Hanauer & Vidojevic (2020)** — *The idiosyncratic momentum anomaly*, International Review of Economics & Finance 69, 932-957. **Solo abstract verificato** (ScienceDirect e SSRN inaccessibili). L'idiosyncratic momentum è un fenomeno **distinto** dal momentum convenzionale e non è spiegato da esso; è prezzato nel cross-section anche controllando per fattori recenti; crash risk e overconfidence **non** lo spiegano; robusto in mercati sviluppati ed emergenti.
<https://econpapers.repec.org/RePEc:eee:reveco:v:69:y:2020:i:c:p:932-957>

**Moskowitz & Grinblatt (1999)** — *Do Industries Explain Momentum?*, JF 54(4), 1249-1290. Letto integralmente (copia JSTOR ospitata da Wharton): <http://www-stat.wharton.upenn.edu/~steele/Courses/956/Resource/Momentum/MoskowitzGrinblatt99.pdf>. Luglio 1963 – luglio 1995, 20 industrie.

Risultati verificati:
- Industry momentum 6/6 **senza skip: 0.43%/mese**; **con skip di 1 mese: 0.40%/mese** — "differenza trascurabile". *Lo skip-month non serve al momentum settoriale.*
- **La profittabilità viene dal lato long**: Winners−Middle = **0.36%/mese**, Middle−Losers = **0.07%/mese**. Citazione: *"the profitability of the industry momentum strategy explored here is mostly due to the long side of the position… making short sales constraints less of an impediment"*.
- **Per contrasto, il momentum di singolo titolo è guidato soprattutto dalla vendita dei loser**, specialmente fra i titoli meno liquidi.
- Il momentum settoriale è **più forte a 1 mese/1 mese** (opposto alla reversal a 1 mese sui singoli titoli), ma lì il turnover "sembra precludere i profitti dopo i costi".
- Una volta aggiustati per l'industria, i profitti del momentum di singolo titolo sono "significativamente più deboli e, per lo più, statisticamente non significativi".

**Grundy & Martin (2001)** — *Understanding the Nature of the Risks and the Source of the Rewards to Momentum Investing*, RFS 14(1), 29-78. **Solo abstract/sintesi editoriale verificata** (Oxford Academic paywall). **Contraddicono Moskowitz-Grinblatt**: né gli effetti di industria né le differenze cross-sezionali nei rendimenti attesi sono la causa primaria del momentum; e le strategie basate sulla componente *stock-specific* sono **più** profittevoli di quelle su rendimenti totali.
<https://academic.oup.com/rfs/article-abstract/14/1/29/1587146>

**HXZ (2020) risolvono parzialmente la contraddizione**: replicano *entrambi* come sopravvissuti indipendenti. Industry momentum (Moskowitz-Grinblatt): Im1 0.68 (t=2.86), Im6 0.60 (t=3.01), Im12 0.63 (t=3.57). Residual momentum (Blitz-Huij-Martens): vedi tabella sopra. Cioè: **entrambi esistono; la tesi forte di MG99 ("l'industria spiega il momentum di singolo titolo") non è confermata, ma il momentum settoriale come fenomeno autonomo sì.**

### 4.2 Evidenza propria sul momentum settoriale recente

[CALCOLO PROPRIO] Su `49_Industry_Portfolios` (VW), top-6 vs bottom-6 industrie, portafogli sovrapposti:

| Strategia | Periodo | Hi−Lo %/mese | t | **Hi − mercato %/mese** | t |
|---|---|---|---|---|---|
| formazione 6m, no skip, hold 6m | pre-1994 | 0.618 | 3.87 | 0.451 | 5.00 |
| | 1994-2026 | 0.576 | **2.35** | **0.314** | **2.10** |
| | 2009-04+ | 0.410 | 1.29 | 0.230 | 1.35 |
| formazione 11m, **skip 1m**, hold 6m | pre-1994 | 0.571 | 3.00 | 0.432 | 4.47 |
| | 1994-2026 | 0.386 | 1.40 | 0.224 | 1.41 |
| | 2009-04+ | 0.209 | 0.59 | 0.055 | 0.30 |
| formazione 1m, hold 1m | pre-1994 | 0.385 | 2.30 | 0.367 | 3.03 |
| | 1994-2026 | 0.087 | 0.34 | 0.075 | 0.47 |

Due cose: (a) il momentum settoriale **senza skip** regge meglio di quello con skip nel periodo post-1994 — coerente con MG99; (b) la gamba long settoriale (Hi−mercato) post-1994 rende 0.314%/mese (t=2.10), **dello stesso ordine di grandezza della gamba long del momentum di singolo titolo** (0.373%, t=1.91). Il momentum settoriale a 1 mese, che MG99 trovavano il più forte, **è sparito dal 1994** (t=0.34).

### 4.3 Ipotesi — Area 4

---

#### H11 — Il residual momentum su residui FF3 migliora l'IC risk-adjusted, non il rendimento grezzo

| campo | contenuto |
|---|---|
| **Enunciato** | Rankare i 96 titoli sui residui cumulati (t−252…t−21) di una regressione rolling a 36 mesi sui tre fattori Fama-French, standardizzati per la σ residua, produce **stessa o minore** media di rendimento del ranking su rendimenti totali ma **volatilità della strategia inferiore di ≥30%**, con Sharpe superiore |
| **Fonte primaria** | Blitz, Huij & Martens (2011) JEmpFin 18(3) 506-521 (full text del manoscritto accettato); Hou, Xue & Zhang (2020) RFS 33(5) Tab. 3 Panel A |
| **Periodo campionario** | BHM: CRSP gen 1926 – dic 2009 (portafogli da gen 1930). HXZ: gen 1967 – dic 2016, NYSE-VW |
| **Effetto atteso** | **Large-cap, hold 1m: Sharpe 0.36 (totale) → 0.60 (residuale)** (BHM Tab. 8). HXZ: ρ¹¹1 0.61%/mese t=3.72 vs R¹¹1 1.16%/mese t=3.99 — rendimento grezzo **quasi dimezzato**, t praticamente uguale. Esposizioni ai fattori 3-5× più piccole |
| **Decadimento** | Sopravvive alla replica HXZ fino al 2016 con t fra 2.88 e 3.82 — **fra i pochi segnali momentum a superare la soglia HLZ di 3.0 su un campione recente**. Blitz-Hanauer-Vidojevic (2020, solo abstract) confermano robustezza internazionale e la distinzione dal momentum convenzionale. Nessuna evidenza post-2016 verificata |
| **Testabile da noi?** | **Sì.** È il risultato più sorprendente della ricerca: **non servono fondamentali**. Servono solo (i) i rendimenti giornalieri/mensili dei nostri 96 titoli e (ii) le serie storiche dei fattori FF3, che sono **scaricabili gratuitamente e senza autenticazione** dalla Ken French Data Library. Il vincolo "niente fondamentali point-in-time" **non** blocca questa ipotesi. Variante ancora più economica: residui rispetto al solo mercato (SPY/CRSP) — beta-adjusted momentum, zero dipendenze esterne |
| **Prior** | **forte.** Effetto replicato da autori indipendenti su campione esteso, con t > 3, esplicitamente verificato sul sottocampione large-cap, e con il beneficio (riduzione del rischio) che è proprio quello che serve a un book long-only concentrato per settore. **È la mia raccomandazione numero uno del catalogo.** Avvertenza: BHM/HXZ misurano long-short; la scomposizione per gamba del residual momentum **non l'ho trovata in nessuna fonte** — è un rischio non coperto |

---

#### H12 — Il momentum settoriale long-only sopravvive e non richiede skip-month

| campo | contenuto |
|---|---|
| **Enunciato** | Un tilt long-only verso i settori vincitori a 6 mesi (senza skip) all'interno dell'universo Alembic batte l'equal-weight dell'universo di ≥0.2%/mese nel periodo 2010-2026, e la variante con skip-month **non** lo migliora |
| **Fonte primaria** | Moskowitz & Grinblatt (1999) JF 54(4) 1249-1290 (full text); Hou, Xue & Zhang (2020) Tab. 3 (Im1/Im6/Im12); [CALCOLO PROPRIO] su `49_Industry_Portfolios` |
| **Periodo campionario** | MG99: lug 1963 – lug 1995, 20 industrie. HXZ: 1967-2016, 45 industrie FF (esclusi i finanziari). Calcolo proprio: 1926-2026, 49 industrie |
| **Effetto atteso** | MG99: 6/6 Wi−Lo 0.43%/mese; **lato long 0.36 su 0.43 (≈84%)**; con skip 0.40 vs 0.43 senza (differenza trascurabile). HXZ: Im6 0.60%/mese t=3.01, Im12 0.63 t=3.57. [CALCOLO PROPRIO] gamba long vs mercato: 0.314%/mese (t=2.10) nel 1994-2026 senza skip, contro 0.224% (t=1.41) con skip |
| **Decadimento** | Presente ma più contenuto del momentum di singolo titolo: Hi−Lo settoriale 0.618 → 0.576 (1994-2026) → 0.410 (2009+); il long-short di singolo titolo nello stesso arco va 1.352 → 0.731 → 0.277. **Il momentum settoriale a 1 mese invece è morto** (t=0.34 post-1994) |
| **Testabile da noi?** | **Sì, ed è il più naturale sull'universo attuale**: l'universo contiene già XLF/XLK/SOXX e altri ETF settoriali, e i 96 titoli sono mappabili su ~11 gruppi (esiste già una `sector_map` nel repo per il sector cap). **È l'unica area in cui una fonte primaria dice esplicitamente che il profitto sta sul lato long** |
| **Prior** | **medio-forte.** Il fatto che MG99 documenti l'asimmetria long/short a favore del long è il singolo dato più rilevante di tutto il documento per un book long-only. Il freno: **contraddizione Grundy & Martin (2001)**, che negano che l'industria sia la causa primaria; e HXZ mostrano che i due effetti coesistono, quindi la versione forte di MG99 non regge. Non testarlo come "sostituto" di S1, ma come segnale additivo o come vincolo di allocazione |

---

#### H13 — Il momentum di singolo titolo di S1 è in gran parte momentum settoriale mascherato

| campo | contenuto |
|---|---|
| **Enunciato** | Neutralizzando il segnale S1 per il settore (z-score calcolato **dentro** ogni gruppo settoriale invece che sull'intero universo), l'IC residuo scende di ≥40%; cioè la maggior parte del segnale attuale è un bet settoriale |
| **Fonte primaria** | Moskowitz & Grinblatt (1999): "once returns are adjusted for industry effects, momentum profits from individual equities are significantly weaker and, for the most part, statistically insignificant"; **contro** Grundy & Martin (2001) e Hou-Xue-Zhang (2020), che trovano il momentum di singolo titolo sopravvivere indipendentemente |
| **Periodo campionario** | 1963-1995 vs 1926-1995 vs 1967-2016 |
| **Effetto atteso** | MG99 prevede un crollo quasi totale; GM01 e HXZ prevedono una riduzione modesta. **Le fonti sono in aperto conflitto e lo riporto come tale** |
| **Decadimento** | HXZ replicano entrambi i segnali come sopravvissuti fino al 2016, il che è di per sé una falsificazione della versione forte di MG99 |
| **Testabile da noi?** | **Sì**, ed è diagnostico più che alpha-generante. Ha valore operativo diretto: il libro Alembic si concentra per settore (memoria del progetto: episodio semiconduttori ~6% NAV, sector cap implementato ma a 0.0). Se H13 è vera, il rischio di concentrazione settoriale **non è un effetto collaterale, è il segnale** |
| **Prior** | **medio.** Alto valore diagnostico, basso valore di alpha. Da eseguire come *analisi*, non come variante da mettere in produzione |

---

## 5. Ipotesi che NON vale la pena testare

Questa sezione esiste per ridurre il numero di test: con la correzione per test multipli (H10), **ogni ipotesi aggiuntiva alza la soglia \|t\| per tutte le altre**. Le seguenti vanno escluse dal programma.

| # | Ipotesi scartata | Motivo |
|---|---|---|
| **X1** | **Reversal a lungo termine di De Bondt & Thaler (3-5 anni)** come segnale contrarian su S1 | Due motivi indipendenti. (a) DBT stessi dicono che l'effetto è "much larger for losers than for winners" — è un'anomalia della gamba che **non possiamo tradare** (long-only). (b) [CALCOLO PROPRIO] su `10_Portfolios_Prior_60_13` VW: Hi−Lo pre-1994 −0.68%/mese (t=−2.80) → 1994-2026 **+0.08% (t=0.29)** → 2009+ **+0.42% (t=0.97)**. Sui large-cap l'effetto è sparito e ha cambiato segno. **Strada chiusa.** |
| **X2** | **Reversal settimanale di Lehmann (1990)** | Orizzonte settimanale, profitti che l'autore stesso quantifica al netto di spread *del 1986*. Dopo la decimalizzazione (Chordia-Subrahmanyam-Tong 2014) e con l'universo large-cap, è un'anomalia da market maker, non da un book con holding a 14 giorni. Inoltre il mio calcolo mostra che anche la reversal *mensile* VW è a zero dal 1994. |
| **X3** | **Momentum crash hedging via beta time-varying (Grundy-Martin)** | Barroso & Santa-Clara lo smontano con un numero: la componente di mercato è **solo il 23%** del rischio del momentum e ha R² OOS di previsione 20.87% contro 47.06% della componente specifica. "L'hedging con beta time-varying fallisce perché si concentra sulla parte più piccola e meno prevedibile del rischio". Testarlo significherebbe ri-falsificare una cosa già falsificata. |
| **X4** | **52-week high (George & Hwang)** come segnale alternativo | Hou-Xue-Zhang (2020), NYSE-VW: 52w1 = 0.13%/mese, **t=0.38**. Fallisce la replica anche alla soglia più permissiva. |
| **X5** | **Griglia esaustiva di lookback** (es. testare 15 combinazioni di finestre di formazione) | È esattamente il comportamento che Harvey-Liu-Zhu (2016) descrivono come causa del fatto che "most claimed research findings in financial economics are likely false". Con 15 varianti la soglia Holm al 5% sale oltre \|t\|=3.4 e nessuna variante la supererà mai su 15 anni di dati. Testare **al massimo due** varianti di lookback pre-dichiarate (H2 e H4), non una griglia. |
| **X6** | **Ottimizzazione dei pesi esponenziali fra lookback** | Nessuna fonte primaria stabilisce che i lookback vadano combinati con pesi esponenziali crescenti. È una scelta di implementazione senza mandato in letteratura: ottimizzarla è overfitting puro su un iperparametro non ancorato. |
| **X7** | **Time-series momentum (Moskowitz-Ooi-Pedersen) come sostituto del cross-sectional** | È un'evidenza costruita su **futures multi-asset con leva e short**; su un long-only equity a universo fisso degenera in un semplice filtro trend sul singolo titolo. Il paper non stabilisce nulla sul nostro caso. Se serve un filtro di trend assoluto, va giustificato come scelta di risk management, non come replica di TSMOM. |
| **X8** | **Momentum a gennaio / stagionalità di calendario** | JT93 Tab. IV documenta l'effetto gennaio, ma per **S3 (large firms) il gennaio non è statisticamente significativo** (−1.61%, t=−1.28) e le regolarità aprile/novembre/dicembre sono spiegate da flussi pensionistici e tax-loss selling degli anni '60-'80. Testarlo su 96 large-cap dal 2010 significa avere ~15 osservazioni per mese di calendario: potenza zero. |
| **X9** | **Dynamic momentum di Daniel-Moskowitz (forecast di media condizionale)** | Vedi H7: metà del guadagno viene dal forecast della *media della WML*, che long-only non esiste; l'altra metà dallo scalare per varianza invece che per σ, che è già coperto da H5. Aggiungerebbe un test senza aggiungere informazione. |
| **X10** | **Residual momentum con modelli fattoriali più ricchi** (q-factor, FF5, Barra) | I fattori di investimento e profittabilità richiedono **fondamentali point-in-time**, che non abbiamo. BHM ottengono il loro risultato con FF3, e HXZ lo replicano con FF3. Restare su FF3 (o su un residuo di solo-mercato) è sia l'unica cosa fattibile sia quella supportata dalle fonti. |

---

## 6. Cosa non sono riuscito a verificare

Elenco onesto dei limiti di questa ricerca.

1. **Novy-Marx (2012), full text.** ScienceDirect restituisce 403, la pagina dell'autore (`rnm.simon.rochester.edu`) reindirizza a `mysimon.rochester.edu` e per questo paper linka solo il paywall. Il numero "≈10%/anno per il quintile VW large-cap, 1927-2010" viene da riassunti dell'abstract editoriale, **non l'ho letto in tabella**. H4 va considerata poggiata su una fonte non verificata, ed è il motivo principale del suo prior debole.

2. **McLean & Pontiff (2016), versione pubblicata.** Wiley restituisce 402, RePEc non riporta l'abstract. Ho letto integralmente il **working paper del maggio 2013** (82 caratteristiche, −10% out-of-sample non significativo, −35% post-pubblicazione). I numeri della versione JF 2016 (**97 predittori, −26% e −58%**) provengono da riassunti dell'abstract editoriale. La discrepanza fra le due versioni è sostanziale e non l'ho potuta risolvere alla fonte.

3. **Jegadeesh (1990), Lehmann (1990), De Bondt & Thaler (1985), Harvey-Liu-Zhu (versione RFS), Chen & Zimmermann (2020), Grundy & Martin (2001), Blitz-Hanauer-Vidojevic (2020): solo abstract.** Per Harvey-Liu-Zhu ho letto integralmente il NBER WP 20592 (ottobre 2014), che è la versione pre-pubblicazione dello stesso lavoro. Per gli altri, i numeri riportati sono quelli degli abstract editoriali.

4. **Scomposizione per gamba del residual momentum: non trovata.** BHM e HXZ riportano solo long-short. Non ho trovato **nessuna** fonte che dica quanta parte del residual momentum stia sul lato long. Questo è il buco più serio per H11, che è al tempo stesso l'ipotesi che raccomando di più. Il test dovrà misurarlo da sé, e questo va scritto nella pre-registrazione come rischio noto.

5. **Barroso & Santa-Clara: ho letto una copia mirrorata.** Il PDF della versione novembre 2014 ("Forthcoming in the Journal of Financial Economics") era disponibile solo su un host terzo (`snifferquant.com`) con annotazioni manoscritte di un lettore sovrapposte alle prime pagine. Il corpo del testo e le tabelle sono quelli degli autori; le annotazioni non lo sono e le ho ignorate. Non ho potuto accedere alla versione JFE definitiva (SSRN 403). I numeri citati (Sharpe 0.53→0.97, kurtosi 18.24→2.68, ecc.) sono nella versione novembre 2014.

6. **Nessuna replica accademica post-2016 specificamente sul momentum US large-cap.** Ho cercato e non l'ho trovata. La replica sistematica più recente che copra il momentum è Hou-Xue-Zhang (2020), il cui campione **finisce a dicembre 2016**. Per il periodo 2017-2026 la mia unica evidenza sono i **calcoli propri sui dati French** (§0.2, §2.2, §4.2): sono dati primari CRSP, ma non sono un paper con peer review, non hanno costi di transazione, e le mie repliche del momentum settoriale (top-6/bottom-6 su 49 industrie) **non riproducono esattamente** il disegno di MG99 (top-3/bottom-3 su 20 industrie). Vanno trattati come indicatori di ordine di grandezza, non come stime.

7. **Costi di transazione: non coperti da questa ricerca.** Nessuno dei numeri riportati, né dei paper né miei, è al netto di spread e commissioni. Per H3 (holding period) e H12/H13 (rotazione settoriale) questo è dirimente: MG99 stessi dicono che l'industry momentum a 1 mese ha turnover che "sembra precludere i profitti dopo i costi". Il programma di backtest deve modellare i costi o i suoi risultati non sono interpretabili.

8. **Nessuna evidenza trovata su universi fissi di ~100 titoli.** Tutta la letteratura lavora su decili/quintili di CRSP (migliaia di titoli). La perdita di potenza e di dispersione cross-sezionale che deriva dall'avere decili di ~10 nomi non è quantificata da nessuna fonte che io abbia trovato. H9 tenta di stimarla empiricamente, ma parte senza ancoraggio in letteratura.

---

## 7. Bibliografia (fonti primarie)

**Orizzonti**
- Jegadeesh, N. & Titman, S. (1993). *Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency.* Journal of Finance 48(1), 65-91. <https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x> — full text: <https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf>
- Jegadeesh, N. & Titman, S. (2001). *Profitability of Momentum Strategies: An Evaluation of Alternative Explanations.* Journal of Finance 56(2), 699-720. <https://www.nber.org/papers/w7159> — full text: <http://www-stat.wharton.upenn.edu/~steele/Courses/434/434Context/Momentum/MomentumStrategiesJF2001.pdf>
- Jegadeesh, N. (1990). *Evidence of Predictable Behavior of Security Returns.* Journal of Finance 45(3), 881-898. *(solo abstract)* <https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1990.tb05110.x>
- Lehmann, B. (1990). *Fads, Martingales, and Market Efficiency.* QJE 105(1), 1-28. *(solo abstract)* <https://www.nber.org/papers/w2533>
- De Bondt, W. & Thaler, R. (1985). *Does the Stock Market Overreact?* Journal of Finance 40(3), 793-805. *(solo abstract)* <https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.1985.tb05004.x>
- Novy-Marx, R. (2012). *Is momentum really momentum?* JFE 103(3), 429-453. *(solo abstract)* <https://www.sciencedirect.com/science/article/abs/pii/S0304405X11001152>
- Goyal, A. & Wahal, S. (2015). *Is Momentum an Echo?* JFQA 50(6), 1237-1267. <https://sites.google.com/view/agoyal145/>

**Crash e vol-scaling**
- Barroso, P. & Santa-Clara, P. (2015). *Momentum has its moments.* JFE 116(1), 111-120. <https://econpapers.repec.org/RePEc:eee:jfinec:v:116:y:2015:i:1:p:111-120> — SSRN: <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2041429>
- Daniel, K. & Moskowitz, T. (2016). *Momentum crashes.* JFE 122(2), 221-247 (open access CC-BY). <https://www.kentdaniel.net/papers/published/jfe_16.pdf> — NBER w20439: <https://www.nber.org/papers/w20439>

**Decadimento e test multipli**
- McLean, R. D. & Pontiff, J. (2016). *Does Academic Research Destroy Stock Return Predictability?* Journal of Finance 71(1), 5-32. <https://onlinelibrary.wiley.com/doi/10.1111/jofi.12365> — WP 2013: <https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf>
- Harvey, C., Liu, Y. & Zhu, H. (2016). *… and the Cross-Section of Expected Returns.* RFS 29(1), 5-68. <https://www.nber.org/system/files/working_papers/w20592/w20592.pdf>
- Hou, K., Xue, C. & Zhang, L. (2020). *Replicating Anomalies.* RFS 33(5), 2019-2133. <https://global-q.org/uploads/1/2/2/6/122679606/houxuezhang2020rfs.pdf>
- Chen, A. & Zimmermann, T. (2020). *Publication Bias and the Cross-Section of Stock Returns.* RAPS 10(2), 249-289. *(solo abstract)* <https://academic.oup.com/raps/article-abstract/10/2/249/5640503>
- Chordia, T., Subrahmanyam, A. & Tong, Q. (2014). *Have capital market anomalies attenuated in the recent era of high liquidity and trading activity?* JAE 58(1), 41-58. *(solo abstract)* <https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2029057>
- Israel, R. & Moskowitz, T. (2013). *The role of shorting, firm size, and time on market anomalies.* JFE 108(2), 275-301. <https://www.sciencedirect.com/science/article/pii/S0304405X12002401>

**Residual e industry momentum**
- Blitz, D., Huij, J. & Martens, M. (2011). *Residual Momentum.* Journal of Empirical Finance 18(3), 506-521. <https://www.sciencedirect.com/science/article/abs/pii/S0927539811000041> — manoscritto accettato: <http://repub.eur.nl/pub/22252/ResidualMomentum-2011.pdf>
- Blitz, D., Hanauer, M. & Vidojevic, M. (2020). *The idiosyncratic momentum anomaly.* IREF 69, 932-957. *(solo abstract)* <https://econpapers.repec.org/RePEc:eee:reveco:v:69:y:2020:i:c:p:932-957>
- Moskowitz, T. & Grinblatt, M. (1999). *Do Industries Explain Momentum?* Journal of Finance 54(4), 1249-1290. <https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146> — full text: <http://www-stat.wharton.upenn.edu/~steele/Courses/956/Resource/Momentum/MoskowitzGrinblatt99.pdf>
- Grundy, B. & Martin, J. S. (2001). *Understanding the Nature of the Risks and the Source of the Rewards to Momentum Investing.* RFS 14(1), 29-78. *(solo abstract)* <https://academic.oup.com/rfs/article-abstract/14/1/29/1587146>

**Dati**
- Kenneth R. French Data Library (CRSP 202605, serie fino a 2026-05). <https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html>
