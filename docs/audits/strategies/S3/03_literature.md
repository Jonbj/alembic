# S3 — 03 Letteratura

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Metodo:** `WebSearch` su residual/idiosyncratic momentum canonico, repliche OOS,
decay, costi, regime, alternative-beta, convenzione 12-1. La review interna
(`docs/RESEARCH_S2_S3_S7_PRIMARY_LITERATURE_2026-07-15.md`) è antecedente; qui
aggiungo repliche 2017-2023 e la prospettiva alternative-beta/decay specifica del
residual momentum. Nessuna citazione inventata.

---

## 1. Fonti fondazionali del residual momentum

| Fonte | Anno | Contributo per S3 |
|---|---|---|
| [Blitz-Huij-Martens — Residual Momentum](https://doi.org/10.1016/j.jempfin.2011.01.003) | 2011 | **Paper fondativo.** Ranking su rendimenti residui (regressione FF3) invece di total return → riduce le esposizioni dinamiche ai fattori di 3-5×; **Sharpe del residual momentum ~doppio** del momentum lordo, ~metà volatilità. Persiste su holding 12m mentre il momentum lordo decade. 2000-2009: momentum lordo −8.5%/anno, **residual +4.7%/anno**. |
| [Blitz-Hanauer-Vidojevic — Idiosyncratic Momentum Anomaly](https://doi.org/10.1016/j.iref.2020.05.008) / [SSRN](https://doi.org/10.2139/ssrn.2947044) | 2020 | Residual momentum è un **fenomeno distinto**, non subsumed dal momentum convenzionale; sopravvive ai controlli per fattori moderni (inclusi quelli che spiegano anomalie momentum-correlate). Crash-risk e overconfidence **non** spiegano i profitti. **Dinamiche long-run supportano underreaction** (nessun reversal a lungo). Robusto sviluppati + emergenti OOS. |
| [Jegadeesh-Titman 1993](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=299107) | 1993 | Base del momentum CS: formation 3-12m, decili, holding. **Convenzione 12-1: skip 1 mese** tra formation e holding per isolare momentum dalla short-term reversal. |

## 2. Repliche OOS / decay (cruciale per S3)

| Fonte | Anno | Risultato | Impatto su S3 |
|---|---|---|---|
| [Huij-Lansdorp — Residual Momentum and Reversal Revisited](https://repub.eur.nl/pub/100801) | 2017 | Replica **post-pubblicazione** di BHM-2011 e BHLV-2013: findings principali **robusti** su universi globali e periodi OOS dopo la pubblicazione. **Poco decay**. | **Decisivo e differenziante**: a differenza del momentum lordo (Ben-David 2021: decay 0.92→0.16%/mese), il **residual momentum NON decade** significativamente post-pubblicazione. L'ipotesi S3 è, a priori, più solida di S1 sul decay. |
| Blitz-Hanauer-Vidojevic 2020 (sopra) | 2020 | Nessun reversal long-run → supporta underreaction persistente, non anomalia temporanea. | Corrobora: non è un artefatto che decade. |
| [Wiest — Momentum 30 years after JT](https://link.springer.com/article/10.1007/s11408-022-00417-8) | 2022 | Review: la convenzione 12-1 (skip ultimo mese) è **standard** (JT 1993, Carhart 1997, Asness 2013) per isolare momentum da short-term reversal (Jegadeesh 1990). | **Conferma DV-1/DV-2**: S3 usa 12-0 (include il mese della reversal), violando la convenzione canonica. Il segnale S3 è contaminato dalla reversal a 1m che il design 12-1 esclude. |

## 3. Costi di transazione, capacità

| Fonte | Anno | Risultato | Impatto su S3 |
|---|---|---|---|
| Blitz-Huij-Martens 2011 (sopra) | 2011 | Residual momentum ~metà turnover del momentum lordo (ranking su residui più stabile) → **costi di transazione minori**, più adatto all'implementazione. | A favore di S3: il residual momentum è più "tradeable" del momentum lordo per turnover. |
| [Novy-Marx — intermediate momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4059632) (cit. in Wiest 2022) | 2012 | t-12 to t-7 (intermediate) > t-6 to t-2: 1.20%/mese vs 0.67%/mese 1927-2010. | Il momentum è concentrato nell'orizzonte intermedio; il 12-0 di S3 include l'orizzonte breve (reversal) che **distrugge** il segnale. |
| Patton-Weller 2020 (cit. in S1 fase 03) | 2020 | Costi momentum 7.2-7.6%/anno per fondi tipici. | Applicabile a S3 (famiglia momentum); il residual ha turnover minore → costi inferiori ma non nulli. |

## 4. Regime dependency

| Fonte | Anno | Risultato | Impatto su S3 |
|---|---|---|---|
| Blitz-Huij-Martens 2011 (sopra) | 2011 | Residual momentum **crash meno severi** del momentum lordo nei regimi bear+rebound (Daniel-Moskowitz 2016 per il lordo) perché la componente beta è sottratta. 2000-2009: residual +4.7% vs lordo −8.5%. | **Vantaggio teorico chiave di S3**: il residual momentum dovrebbe sopravvivere ai crash meglio di S1. MA il codice S3 long-short + sizing non normalizzato reintroduce esposizione che il design long-only normalizzato evitava. |
| Daniel-Moskowitz 2016 (cit. S1 fase 03) | 2016 | Momentum lordo ha crash concentradì nei regimi bear+rebound. | S3 dovrebbe essere meno esposto (è la tesi), ma l'assenza di vol-scaling aggregato (BSC 2015) e il sizing non normalizzato riducono il vantaggio. |

## 5. Alternative-beta exposure

| Fonte | Anno | Risultato | Impatto su S3 |
|---|---|---|---|
| Blitz-Hanauer-Vidojevic 2020 (sopra) | 2020 | Residual momentum **non subsumed** dal momentum convenzionale né dai fattori moderni; **incremental alpha**. | A favore: non è puro momentum-beta. MA la correlazione con il momentum lordo rimane (~0.5, BHM 2011) → non è totalmente ortogonale. |
| [Factor Momentum — Ehsani-Linn](https://doi.org/10.1093/rfs/hhad006) / [Arnott et al.](https://doi.org/10.3386/w25551) | 2023/2020 | Gran parte del "momentum azionario" è **factor momentum** (time-series dei fattori). | Il residual momentum sottrae beta×market ma NON sottrae altri fattori (size, value, quality) → può contenere factor momentum residuo. La variante FF3-residual (Gutman) è più pulita; S3 usa solo beta-SPY (1-factor) → sotto-pulito. |
| Schneider 2020 (cit. S2 fase 03) | 2020 | Low-vol anomalies = compensazione coskewness, non alpha. | Sizing inverse-vol 252d di S3 tilta low-vol → esposizione low-vol beta, come S1. |

## 6. Sintesi per S3

1. **L'ipotesi teorica (residual momentum 12-1 long-only) ha prior accademico forte**
   e, crucialmente, **NON decade** post-pubblicazione (Huij-Lansdorp 2017;
   Blitz-Hanauer-Vidojevic 2020) — differenza chiave vs S1 (momentum lordo decaduto).
   Sharpe ~doppio del momentum lordo, crash meno severi, turnover minore.
2. **Il codice S3 non la testa fedelmente**: 12-0 (contaminato da short-term
   reversal, violando la convenzione canonica JT-1993/Carhart-1997), long-short
   (non long-only del design), sizing non normalizzato, su 50 sopravvissuti. La
   review interna (2026-07-20) raccomanda un POC A/B della **variante originale**.
3. **Decay**: a differenza di S1/S2, il residual momentum **non mostra decay
   significativo** → l'argomento "anomalia decaduta" è più debole per S3. Il
   verdetto non può basarsi sul decay (come S1) ma sul **non-test fedele** + bias
   di backtest (survivorship, pannello bilanciato, soglie banali).
4. **Costi/regime**: a favore di S3 (turnover minore, crash meno severi del
   momentum lordo). MA l'implementazione long-short + sizing non normalizzato
   reintroduce rischi che il design long-only evitava.
5. **Alternative-beta**: residual momentum non è puro momentum-beta (incremental
   alpha documentato), MA S3 usa solo beta-SPY 1-factor (non FF3) → sotto-pulito,
   può contenere factor momentum residuo (size/value/quality). Inverse-vol sizing
   → low-vol beta.

**Convergenza letteratura → verdetto (fase 04):** la letteratura **sostiene** il
residual momentum come anomalia genuina e non decaduta, ma **non supporta**
l'implementazione S3 (12-0, long-short, sizing non normalizzato, 50 sopravvissuti).
L'evidenza 0.148 di S3 è di una variante confusa, non della variante originale che
la letteratura convalida. Il verdetto deve essere `UNPROVEN` (non testato
fedelmente) + nota che il backtest è invalidato da bias, non `DECAYED` (la letteratura
dice il contrario sul residual momentum).

---

### Fonti web verificate in questa fase

- [Blitz-Huij-Martens 2011 — Residual Momentum](https://doi.org/10.1016/j.jempfin.2011.01.003)
- [Blitz-Hanauer-Vidojevic 2020 — Idiosyncratic Momentum](https://doi.org/10.1016/j.iref.2020.05.008) / [SSRN](https://doi.org/10.2139/ssrn.2947044)
- [Huij-Lansdorp 2017 — Residual Momentum Revisited](https://repub.eur.nl/pub/100801)
- [Wiest 2022 — Momentum 30 years after JT](https://link.springer.com/article/10.1007/s11408-022-00417-8)
- [Jegadeesh-Titman 1993 (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=299107)
- [Ehsani-Linn — Factor Momentum](https://doi.org/10.1093/rfs/hhad006)
- [Arnott et al. — Factor Momentum and the Momentum Factor](https://doi.org/10.3386/w25551)
- [Gutman — What Does Residual Momentum Tell Us (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4059632)

---
**Stato fase:** 03_literature = **done**. Prossimo cursore: `S3:04_alpha_assessment`.