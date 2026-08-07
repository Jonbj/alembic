# S4 — 02 Ipotesi scientifica / investment hypothesis

**Strategia:** S4 `NewsDrivenTactical` (news-driven tactical sentiment overlay)
**Data:** 2026-08-04
**Riferimenti:** fase 01 di questa audit, `docs/strategies.md`, `CLAUDE.md`,
`docs/S4_NEWS_PIPELINE_RND_BACKLOG_2026-06-29.md`.

---

## 1. L'ipotesi teorica

S4 scommette sul **news sentiment drift** (drift post-annuncio): l'idea che i
mercati **sottoreagiscono** alle notizie testuali aziendali, e che un segnale di
sentiment estratto dalle news (dai testi, non dai prezzi) predica i rendimenti
successivi. È la generalizzazione testuale del **Post-Earnings-Announcement
Drift** (PEAD, Ball-Brown 1968; Bernard-Thomas 1989/1990): dopo un earnings
surprise, il prezzo continua a driftare nella direzione della sorpresa per
60-180 giorni perché gli investitori integrano l'informazione lentamente. S4
estende il meccanismo a tutte le news materiali (earnings, guidance, M&A,
regulatory, product, analyst rating, management), non solo agli earnings.

**Meccanismi proposti (perché dovrebbe essere prezzato):**

1. **Underreaction / limited attention** (Hong-Stein 1999; Barberis-Shleifer-
   Vishny 1998; Hirshleifer-Lim-Teoh 2009): gli investitori sono limitati
   nell'attenzione e nell'elaborazione; le news testuali, soprattutto
   qualitative/complesse, sono integrate gradualmente → drift persistente nella
   direzione del sentiment.
2. **Information discreta vs continua** (Engelberg 2008): le news sono eventi
   discreti con contenuto informativo non banale; i modelli di prezzo a
   informazione continua non catturano il componente testuale → il sentiment
   testuale ha contenuto informativo incrementale oltre i prezzi e i numeri
   (surprise quantitativi).
3. **Salience / tone** (Tetlock 2007 "Giving Content to Investor Sentiment";
   Garcia 2013): il tono emotivo dei media predice i rendimenti e l'attività di
   trading; il sentiment negativo sui giornali prevede rendimenti futuri bassi
   (e viceversa), specialmente in recessione.
4. **LLM extraction supera i dizionari** (Lopez-Lira-Mayew “Can ChatGPT
   Forecast Stock Returns?” 2023; FinBERT): un LLM fine-tuned/general estrae
   polarity e confidence con maggiore accuratezza dei dizionari lessicali → il
   segnale `polarity × confidence` dovrebbe avere IC superiore ai dizionari
   tradizionali.

**Classificazione teorica:** anomalia comportamentale (underreaction) con
componente information-based. Non è un risk premium puro — è un inefficienza da
slow information diffusion. La letteratura lo tratta come **anomalia genuina ma
attenuata** dopo i costi (Tetlock 2007; Heston-Sinha 2017), e soggetta a
**capacity limit** (le news più materiali sono poche).

## 2. La formula del segnale e l'ipotesi operazionalizzata

Il segnale (fase 01 §1):

$$\mathrm{score}_{i,t} = \mathrm{polarity}_{i,t} \times \mathrm{confidence}_{i,t}, \quad \mathrm{polarity}\in[-1,1],\ \mathrm{confidence}\in[0,1]$$

L'ipotesi operazionalizzata da S4 è: **ordinare cross-sectionalmente i ticker
per `score`, andare long i top-N (n_top=5) a pari peso, e chiudere quando il
segnale decade**. Il drift previsto è positivo per i top-N (sentiment positivo
forte + alta confidence) e negativo per il bottom (non commerciato — long-only).

La **confidence** entra due volte in modo intenzionale ma controllato:
- Nel `score` (polarity×confidence, worker) — scala il segnale per la certezza.
- Nell'entry gate `feedback:entry_threshold` (ratchet) — soglia dinamica su
  `score` stesso (che già contiene confidence). Questo è **intenzionale** (il
  gate ordina per il segnale confidence-scaled, non lo moltiplica di nuovo;
  `ranking.py:6-8`). Non è confidence².

## 3. Come il codice operazionalizza l'ipotesi (e dove diverge)

Il ranker S4 (`ranking.py`) implementa fedelmente la struttura del sentiment
drift long-only, MA l'**entry gate** reale è il `feedback:entry_threshold`
(portfolio_scheduler), non il `min_score` del ranker. Questo disaccoppiamento
cambia la natura del test:

1. **Long-only asimmetrico** (`ranking.py:187-189` `strength > 0`): S4 entra
   solo su sentiment positivo; i segnali bear (score < 0) **non vanno short** →
   monetizza solo metà del drift (la gamba long). La letteratura PEAD
   commercializza entrambe le gambe (surprise positiva → long, negativa →
   short). L'asimmetria riduce il alpha atteso ma è coerente con il vincolo
   long-only del sistema. **Risk**: i falsi positivi (news positiva che non
   driffta) non sono compensati dai veri negativi shortati.
2. **Tactical short-horizon, non drift 60-180g**: il design PEAD classico ha
   holding 60-180 giorni; S4 ha `rebalance_frequency=DAILY`
   (`config.py:40-42`) e `max_signal_age_hours=4` (`config.py:39`) → è un
   overlay **tattico intraday/giornaliero**, non un drift mensile. Questo
   cambia radicalmente l'ipotesi: S4 scommette su un drift a **breve**
   (ore/giorni), non sul PEAD classico a 60-180g. La letteratura su drift breve
   è più debole (Heston-Sinha 2017: news sentiment decays entro 1-5 giorni,
   non settimane).
3. **Entry gate dinamico (ratchet loss-feedback)**: la soglia di ingresso non è
   fissa ma si alza dopo le perdite (`feedback:entry_threshold`, baseline 0.30).
   Questo è un **adattamento adattivo** non presente nella letteratura PEAD
   canonica. Può migliorare il risk-adjusted return, MA introduce un rischio di
   overfitting/curve-fitting (la soglia si adatta alla storia del portafoglio,
   non a un criterio out-of-sample pulito).
4. **Fixed-slot sizing (#81)**: pari peso 1/n_top con slot vuoti non
   ridistribuiti (`config.py:37`, `ranking.py:128-133`). Coerente con
   un'allocazione tattica discrezionale; non è il sizing della letteratura
   (che usa signal-weighted o vol-scaled). Decisione operatore per fix
   lone-survivor, non neutra teoricamente.
5. **Confirmation gate, non alpha puro**: il commento di `config.py:14-19` è
   esplicito — il `min_score`/`min_confidence` sono **prefiltri**, e il gate
   d'ordine è upstream. S4 funge da **confirmation overlay** ai segnali S1, non
   da strategia alpha standalone: l'orchestratore combina S1 (momentum) + S4
   (sentiment) nello stesso portafoglio (sleeve cap 10%). L'ipotesi testata a
   livello di portafoglio è "S4 aggiunge alpha incrementale a S1", non "S4
   genera alpha da solo".

**Ne consegue**: l'ipotesi effettivamente testata è *"news sentiment positivo a
breve orizzonte (ore/giorni), long-only, con soglia adattiva, come overlay di
conferma al momentum S1"* — non *"PEAD/sentiment drift 60-180g long-short"*. È
un'ipotesi più debole e più breve di quella canonica, e l'alpha è incrementale
(non standalone).

## 4. Esposizione alternative-beta a priori

- **Market beta**: long-only → beta di mercato positivo (esposizione long
  generale). S4 non è dollar-neutral né beta-hedged. L'alpha apparente può
  contenere beta di mercato, specialmente in regimi bull.
- **Momentum beta (S1)**: l'orchestratore combina S4 con S1; i ticker top-N di
  S4 possono sovrapporsi ai long di S1 (momentum positivo correlato a sentiment
  positivo) → S4 può duplicare esposizione momentum, non essere ortogonale.
  Questo è cruciale per la fase `cross_review` (signal_id coupling, sleeve overlap).
- **Sentiment beta / news-beta**: S4 è, per costruzione, beta sul sentiment
  testuale; la domanda è se l'IC>placebo (criterio P0-13) isola alpha oltre il
  beta di "comprare le news positive" (che è parzialmente prezzato).
- **Size/liquidity beta**: universo `load_universe("s1")` (large/mid US
  liquidi) → tilt large-cap.
- **Event-beta**: S4 è concentrato su eventi news → esposizione a cluster di
  eventi (earnings season) con volatilità elevata; non modellato.

## 5. Il criterio alpha del progetto: IC > placebo (P0-13)

La promotion di S4 è bloccata (`promotion_blocked=true`) sul criterio esplicito
**P0-13: nessun gate report esiste e IC>placebo non è confermato**
(`config/strategies.yaml`). Questo significa che il progetto stesso **non ha
ancora validato** che il segnale S4 abbia Information Coefficient superiore a un
placebo (sentiment casuale). Il verdetto alpha (fase 04) deve confrontarsi con
questo: **lo stato ufficiale del progetto è "UNPROVEN"** — il segnale non ha
superato il proprio criterio di promozione. Questo è il punto di partenza più
forte per la valutazione: S4 è in paper **proprio perché il suo alpha non è
dimostrato**, non perché sia confermato.

**Riscontro memoria**: il functional audit 2026-07-22 (non filed) documentò
"BUY su FinBERT-fallback (guard asimmetrico)" e "ensemble affidabile solo 17%"
→ l'affidabilità del segnale stesso è dubbia nel sistema live. L'ensemble
divergence order drought (collo #1 di S4) documenta fallback 70-86% dal GLM-5.2
swap → la maggior parte dei segnali non è ensemble-concord ma fallback singolo
modello. Questo indebolisce l'ipotesi che il `score` sia un segnale robusto.

## 6. Sintesi

L'**ipotesi teorica** (news sentiment drift da underreaction) ha prior accademico
**moderato** — più debole del momentum/VRP al loro apice, e **decisamente più
debole a orizzonte breve** (S4 è tattico giornaliero, non drift 60-180g). La
letteratura (Tetlock 2007, Garcia 2013, Heston-Sinha 2017, Lopez-Lira-Wei 2023)
sostiene un contenuto informativo incrementale del sentiment testuale, MA
attenuato dopo i costi e con capacity limitata.

Il **codice** testa una variante più debole e più breve dell'ipotesi canonica
(long-only asimmetrico, tattico giornaliero, soglia adattiva, come overlay di
conferma a S1), e **il progetto stesso non ha confermato IC>placebo** (P0-13,
promotion blocked). L'alpha è incrementale a S1, non standalone, e la
duplicazione di esposizione momentum (S4 long + S1 long) è un rischio chiave
per la `cross_review`.

Il verdict di alpha (fase 04) dovrà probabilmente essere `UNPROVEN` —
allineato con lo stato ufficiale del progetto (promotion blocked su IC>placebo)
— con nota che l'implementazione è un overlay di conferma, non un test
standalone del sentiment drift, e che l'orizzonte tattico breve è più debole del
PEAD canonico.

---
**Stato fase:** 02_hypothesis = **done**. Prossimo cursore: `S4:03_literature`.