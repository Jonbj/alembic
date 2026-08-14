# S4 — analisi indipendente delle strategie di uscita

**Modello:** Claude Opus 5 (`claude-opus-5`), Claude Code
**Data della ricerca:** 2026-08-14
**Accesso Web:** sì (WebSearch + WebFetch; API Crossref e Semantic Scholar per la verifica dei DOI)
**Accesso al repository:** sì — verifica diretta del codice al commit `d7599cf` (2026-08-14 09:23 +0200)
**Allegati ricevuti:** `00_README_INVIO.md`, `01_PROMPT_MULTI_LLM.md`, `02_ANALISI_PRELIMINARE_LETTERATURA.md`,
`03_DECISIONE_PRECEDENTE_CONSOLIDATA.md`, `04_PREREGISTRAZIONE_D2.md`; inoltre, per verifica autonoma:
`src/strategies/s4/{config,ranking,strategy}.py`, `src/portfolio/{exit_classification,stop_policy,fractional_stop_orders}.py`,
`src/workers/portfolio_scheduler.py`, `src/config.py`, `config/trading.yaml`,
`docs/evidence/{s4_ic.json,economic_pnl.json}`, `docs/stop_loss_calibration_handback_2026-07-15.md`,
`docs/ALPHA_MISS_REPORT_2026-08-{06,10,12}.md`.

**Limiti dichiarati.**

- Non ho letto le risposte degli altri modelli, benché due file (`glm52_*`, `qwen35_*`) fossero già
  presenti in `risposte/`. Sono stati deliberatamente ignorati per non produrre convergenza artificiale.
- Non ho esportato l'issue GitHub `#242`: non disponevo di accesso autenticato. Le affermazioni sulla
  decisione del 2026-08-14 poggiano su `03`/`04`, non su una lettura primaria dell'issue.
- Molte fonti accademiche sono dietro paywall. Dove ho potuto leggere **solo abstract, snippet o
  metadati verificati** lo dichiaro esplicitamente nella tabella §3 e nella bibliografia §10. Nessun
  DOI, numero o risultato di questo documento è inventato: ogni DOI citato è stato risolto via
  Crossref e ne ho verificato titolo, rivista, volume e pagine.
- **Cutoff.** Durante la sessione, nell'albero di lavoro sono comparse modifiche non committate a
  `src/strategies/s4/strategy.py` e a `tests/strategies/test_s4_fix_d_parity_defect.py` che citano
  `#236`. Sono **posteriori al cutoff** e non sono state usate come base dell'analisi; l'audit §2
  descrive il commit `d7599cf`. Ne parlo una sola volta, in §8, perché riguarda esattamente un difetto
  che avevo isolato in modo indipendente.

**Legenda delle etichette:** `EVIDENZA ESTERNA` (letteratura primaria) · `EVIDENZA ALEMBIC` (codice,
config o dati del repository, verificati da me) · `INFERENZA` (deduzione mia dalle due precedenti) ·
`IPOTESI` (congettura da testare) · `NON DECIDIBILE` (non risolvibile con i dati disponibili).

---

## 1. Executive verdict

**Verdetto sulla decisione D+2: `MODIFY`.** Confidenza **alta** sulla direzione, **media** sui parametri.

Il time-stop D+2 va **mantenuto come policy primaria**, ma per una ragione diversa da quella registrata
e con tre riparazioni di specifica.

La ragione registrata è "allineare l'uscita all'orizzonte economico". È corretta ma secondaria. La
ragione forte è che oggi S4 **non ha un limite superiore alla tenuta**. Le nove chiusure 08-06→08-12
descrivono una moda a 1h45; ma WDC è stata tenuta **16 sedute** (`EVIDENZA ALEMBIC`) perché FIX-D
preservava un vecchio segnale positivo, e da sola vale **−201,67 $** in un giorno, contro **−305,45 $**
di P&L economico S4 sull'intera finestra di otto sedute. La distribuzione della tenuta è **bimodale**,
non concentrata: churn a 1h45 su un lato, tenuta illimitata sull'altro. Il P&L vive nel secondo lato.
D+2 non "allunga" S4: la **limita**. È il completamento di FIX-D, non un'alternativa.

Due risultati esterni indipendenti rafforzano la direzione: quasi tutto il guadagno azionario USA
matura *overnight*, mentre il rendimento medio intraday è piatto o negativo
([Glasserman et al. 2025](https://arxiv.org/abs/2507.04481); [Lou, Polk & Skouras 2019](https://doi.org/10.1016/j.jfineco.2019.03.011));
e gli anomaly con turnover > 50% mensile quasi mai sopravvivono ai costi
([Novy-Marx & Velikov 2016](https://doi.org/10.1093/rfs/hhv063)). Una tenuta mediana di 1h45 sta nella
finestra sbagliata e paga il massimo di costo.

Le tre modifiche: **(a)** la metrica primaria pre-registrata (IC ≥ 0,05, `t` ≥ 3, ~213 sedute) **non è
un test dell'uscita** e, alla varianza osservata, non lo diventerà; la domanda sull'uscita è
rispondibile in 30–50 sedute con un confronto **appaiato a ingressi congelati**, e va pre-registrata
separatamente. **(b)** Il valore del contro-segnale è ambiguo fra codice (−0,20) e documento (−0,30):
va risolto **prima** dell'avvio del campione. **(c)** Su titoli non-fractionable esiste una gamba
take-profit +6% che il percorso di cancellazione non tocca — può impedire l'esecuzione della SELL D+2.

Falsificatore: se la decomposizione dei rendimenti post-fill di S4 mostra componente overnight media
negativa, il mio argomento principale cade e D+2 va respinto in favore di una chiusura in seduta.

*(297 parole)*

---

## 2. As-is audit

### 2.1 I rami di uscita realmente presenti al commit `d7599cf`

Ho verificato ogni riga della tabella nel codice. Dove la mia lettura diverge dal packet, lo segnalo.

| # | Ramo | Trigger | Clock | Bypassa | È bypassato da | Stato verificato |
|---|---|---|---|---|---|---|
| **A** | **Weight-drop → full close** | il simbolo sparisce dai target aggregati del portafoglio | ciclo 15 min | — | min-hold 90′, isteresi 2 cicli, protezione segnale fresco, damper anti-whipsaw (off) | **attivo**. `strategy.py:101-114` chiude l'intera posizione assente dal target; nel percorso live la decisione è dell'orchestrator |
| **B** | **Contro-segnale (sentiment reversal)** | `score < soglia`, segnale ensemble non-fallback, età ≤ 60′ | ciclo 15 min | min-hold, isteresi, **e la cancellazione dei soli stop** | — | **attivo**. `config.py:267` default **−0,20**; `portfolio_scheduler.py:4090-4130`; cooldown re-entry 2h (`config.py:284`) |
| **C** | **Stop protettivo sintetico** | `price ≤ trigger` | ciclo 15 min | min-hold, isteresi | disabilitato | **DISATTIVATO**. `trading.yaml:182` `stop_loss: 0.0` + `stop_loss_mode: fixed` → `_stop_loss_breached_symbols` ritorna `{}` (`portfolio_scheduler.py:1347-1348`) |
| **D** | **Disaster stop broker su posizioni frazionarie** | ordine STOP GTC a `avg_entry × (1 − d_hard)`, `d_hard ∈ [0,12; 0,20]` | riconciliato ogni ciclo | tutto (è lato broker) | posizioni con `floor(qty) < 1` | **ATTIVO, non shadow.** `config.ALPACA_FRACTIONAL_STOP_ENABLED` default `true` (`config.py:234`), chiamato a `portfolio_scheduler.py:2772-2776` |
| **E** | **Bracket TP/SL su BUY non-fractionable** | TP limit `+6%`, SL stop `−d_hard` | GTC, persiste overnight | tutto | non applicabile ai titoli fractionable | **attivo condizionatamente**. `portfolio_scheduler.py:3962-3981` |
| **F** | **Alert su perdita non protetta ≥ 15%** | perdita su posizione senza stop | giornaliero, dedup per simbolo | — | — | **attivo, ma non è un ordine** |
| **G** | **Kill-switch di portafoglio** | VIX 40, ΔVIX 30%, drawdown 5% | ciclo | — | — | attivo, **livello portafoglio**, non una exit per-trade S4 |

### 2.2 Findings verificati, con la distinzione richiesta dal §8 del prompt

**[F-A] Il commento YAML e il runtime divergono sul disaster stop.** `config/trading.yaml:178-181`
dichiara che `broker_disaster_stop` resta *"SHADOW telemetry only … no enforced floor"*. Il codice
dice il contrario: `#62/#63 (2026-07-16 PO decision)` promuove `d_hard` a **ordine GTC reale** per le
posizioni frazionarie, con default `true` (`src/config.py:230-236`), e il sync è chiamato ogni ciclo.
Il commento YAML è datato 2026-07-15, la decisione #62/#63 è del 2026-07-16: **il commento è
semplicemente più vecchio della decisione**, non c'è conflitto reale. Ma è codice-corrente contro
documentazione, e il packet lo riporta come divergenza aperta. `EVIDENZA ALEMBIC` · **risolto: il
runtime enforce.** Resta `NON DECIDIBILE` senza accesso al broker se gli ordini esistano davvero su
ogni posizione oggi.

**[F-B] La soglia di contro-segnale è −0,20 nel codice, −0,30 nel documento.** `src/config.py:267-272`
legge `SENTIMENT_REVERSAL_EXIT_THRESHOLD` con default **−0,20**. `04_PREREGISTRAZIONE_D2.md` §2
registra **≤ −0,30**. Il valore effettivo dipende dall'env del container, che **non posso leggere**.
`NON DECIDIBILE` dal repository — ma è bloccante: due soglie diverse selezionano popolazioni di uscita
diverse, e la pre-registrazione vieta di cambiarle in corsa. **Va risolto prima di `n = 0`, non dopo.**

**[F-C] La cancellazione pre-SELL non tocca la gamba take-profit.** `cancel_open_stop_sells`
(`fractional_stop_orders.py:200-231`) filtra `OrderType.STOP`. La gamba TP di un bracket è una **SELL
LIMIT**. Su un titolo non-fractionable con bracket aperto, una SELL a quantità piena — inclusa la
futura SELL del time-stop D+2 — può quindi essere respinta da Alpaca con `40310000` per quantità
riservata. `EVIDENZA ALEMBIC` (lettura del codice; non ho log broker che lo dimostrino accaduto).
Mitigante: un commento del 2026-07-16 afferma che il libro era allora **100% fractionable**, quindi il
ramo E potrebbe essere di fatto dormiente. `NON DECIDIBILE` senza il conteggio storico dei BUY S4
non-fractionable.

**[F-D] Il fallback dello stop nel bracket è il 3%, cioè esattamente lo stop di rumore disabilitato
altrove.** `config.py:226` `ALPACA_STOP_LOSS_PCT` default `0.03`; in
`portfolio_scheduler.py:3966-3976` quel valore è usato **se `stop_policy` è `None` o se il calcolo di
`d_hard` solleva**. Un fallimento del lookup di volatilità può quindi attaccare a un BUY uno stop al 3%
su un libro dove lo stop protettivo è stato deliberatamente spento a 0,0. `INFERENZA` da codice
verificato.

**[F-E] `unknown` non è un'incertezza: è una classificazione onesta di un difetto noto.**
`exit_classification.py` documenta che una disposizione `STALE_PRESERVED` — cioè un segnale che FIX-D
ha *esplicitamente riammesso in quel ciclo* — produce comunque peso zero, e che «il meccanismo che l'ha
azzerato non è registrato». Sui report alpha-miss il pattern è ricorrente e testuale: SONY e HOOD il
08-11, **IBM il 08-12** con la reason identica parola per parola, realizzato **−26,47 $** su 19,25h di
tenuta, seguito da un recupero di **+13,71 $** sulla stessa size. `EVIDENZA ALEMBIC`.

**[F-F] La tenuta è bimodale e il P&L sta nella coda lunga, non nel churn.** Il packet riporta tenuta
mediana 1h45 e sei uscite su nove a 1h45/4h15. Vero, ma incompleto: **WDC è entrata da S4 il 21/07 ed
era ancora aperta il 12/08** — 16 sedute. Il 2026-08-06 ha gappato **−17,39% in apertura** e vale da
sola **−201,67 $** di MTM, «il 100% dell'MTM S4 del giorno»
(`docs/ALPHA_MISS_REPORT_2026-08-06.md:18,177-178`). Sull'intera finestra 08-03→08-12,
`docs/evidence/economic_pnl.json` dà P&L economico S4 cumulato **−305,45 $**, di cui **−241,80 $
maturati nel solo 08-06**. `EVIDENZA ALEMBIC`. **Conseguenza:** una policy di uscita giudicata sulle
nove chiusure realizzate (−89,12 $) misura la parte economicamente minore del problema.

**[F-G] Il canale di contro-segnale è contaminato dallo stesso difetto di entity resolution
dell'ingresso.** Il 08-12 NVDA è stata venduta su `score=+0,023` generato da un articolo su
**Lumentum**, che ha sovrascritto il +0,343 su cui la posizione era nata 1h45 prima; NVDA ha chiuso
+3,03%. Lo stesso giorno, **73 delle 157 righe scorate (46,5%)** provengono da articoli taggati a 2+
ticker, in linea con la serie 51%–66%–53%–55%–51,5%–48,8% delle sedute precedenti. `EVIDENZA ALEMBIC`.

**[F-H] Il gate di potenza registrato non è raggiungibile nell'orizzonte del progetto.**
`docs/evidence/s4_ic.json` al 2026-08-14 (42 giorni): popolazione `ensemble` pura, IC 1g **+0,0018**
(t 0,05), 3g **+0,0236** (t 0,71), 5g **+0,0192** (t 0,61); dev. std. giornaliera 0,237 a 1g. Il campo
`ic_rilevabile_a_t3` calcolato dallo script stesso vale **0,110 / 0,100 / 0,094**. Cioè: con i giorni
attualmente disponibili, l'IC minimo rilevabile a `t = 3` è **circa il doppio della soglia R2 di
0,05**. `EVIDENZA ALEMBIC`.

### 2.3 Diagramma dei rami e delle interazioni

```
                     ┌──────────────────────────────────────────────┐
  segnale/ciclo ───► │  ranker S4 (ultimo segnale per ticker)       │
                     │  prefiltri 0,10 / 0,30 → top-5 → peso 1/5    │
                     └───────────────┬──────────────────────────────┘
                                     │ target weights
                                     ▼
        ┌────────────────────────────────────────────────────────────┐
        │  orchestrator: simbolo assente dal target aggregato → SELL │  ← RAMO A
        └───────────────┬────────────────────────────────────────────┘
                        │
      ┌─────────────────┼──────────────────┬─────────────────────┐
      ▼                 ▼                  ▼                     ▼
 min-hold 90'   protezione segnale   isteresi 2 cicli    anti-whipsaw (OFF)
      │           fresco > gate            │                     │
      └─────────────────┴──────────────────┴─────────────────────┘
                        │ sopravvive → SELL a mercato
                        ▼
     reason ∈ {below_entry_gate, whipsaw, expired, unknown,
               fallback_filtered, entry_freshness_filtered, no_signal}

  ── percorsi che BYPASSANO tutti i guard sopra ─────────────────────
  RAMO B  contro-segnale ≤ soglia, età ≤ 60', no fallback  → force SELL + cooldown 2h
  RAMO D  stop GTC broker a −d_hard (12–20%) su floor azioni intere  → fill lato broker
  RAMO E  bracket GTC: TP +6% / SL −d_hard, solo BUY non-fractionable
```

### 2.4 Failure mode, in ordine di costo economico atteso

1. **Tenuta illimitata su segnale positivo stantio.** FIX-D è concettualmente corretto — «signal expiry
   means no new information, not exit» — ma senza limite superiore trasforma il silenzio in un *hold*
   perpetuo. Costo osservato: WDC. `EVIDENZA ALEMBIC`.
2. **Uscita su rumore di pipeline.** Il ramo A chiude su rank truncation, filtri, collisione o
   sovrascrittura dell'ultimo articolo. Nessuno di questi eventi è una falsificazione della tesi.
   Costo osservato: IBM −26,47 $ poi +13,71 $ di recupero; NVDA venduta su articolo di terzi.
3. **Exit dipendente dalla frazionabilità.** Il ramo E applica una policy diversa in funzione di un
   attributo di esecuzione. Rende il libro non omogeneo e l'attribuzione ambigua.
4. **Protezione di coda inefficace contro il rischio vero.** Il ramo D non protegge il residuo sotto
   un'azione, e — punto più importante — **non protegge da un gap di apertura**, che è la forma in cui
   la perdita massima si è effettivamente materializzata. Vedi §6.6.
5. **`unknown` come categoria residua.** Finché una quota non trascurabile delle uscite è `unknown`, il
   gate R1 (`expired + unknown < 5%`) non è soddisfacibile e nessun confronto fra policy è attribuibile.

---

## 3. Literature evidence table

Ogni DOI è stato risolto e verificato via Crossref. `FT` = ho letto il testo pieno o una versione
autore integrale; `ABS` = solo abstract/metadati verificati; `SNIP` = solo snippet indicizzati, con la
citazione riportata come tale.

### 3.1 Decadimento dell'informazione da news

| Fonte | Accesso | Universo / periodo | Definizione di uscita o orizzonte | Effetto | Trasferibilità a S4 |
|---|---|---|---|---|---|
| **Ke, Kelly & Xiu**, *Predicting Returns with Text Data*, NBER WP 26186 — [nber.org/papers/w26186](https://www.nber.org/papers/w26186) | SNIP | Dow Jones Newswires, azioni USA | orizzonte di assimilazione, non regola di trading | «gli effetti della news **stantia** sono pienamente riflessi nei prezzi **entro due giorni**; per la news **fresca** servono **quattro giorni**»; risposta ~4× più grande e ~2× più lenta su titoli piccoli/volatili | **ALTA.** È la fonte singola più vicina alla domanda D+2. Il flusso S4 è editoriale, derivato e in larga parte *stantio* (46,5% di righe da articoli multi-ticker, `EVIDENZA ALEMBIC`) → il ramo "due giorni" è quello pertinente |
| **Heston & Sinha**, *News vs. Sentiment*, FAJ 73(3):67–83 — [10.2469/faj.v73.n3.3](https://doi.org/10.2469/faj.v73.n3.3) | ABS | >900.000 storie, azioni USA | predittività a 1–2 giorni (daily), un trimestre (weekly) | news giornaliera predice **1–2 giorni**; positive incorporate rapidamente, **negative con reazione lunga e ritardata**, molta della quale attorno all'earnings successivo | **ALTA** sull'orizzonte. **MEDIA** sull'asimmetria: S4 è long-only e non trada la gamba negativa |
| **Jiang, Li & Wang**, *Pervasive underreaction*, JFE 141(2):573–599 — [10.1016/j.jfineco.2021.04.003](https://doi.org/10.1016/j.jfineco.2021.04.003) | ABS | news Dow Jones ad alta frequenza, azioni USA | drift post-news, holding di giorni/settimana | i prezzi driftano nella direzione della reazione iniziale **per vari giorni senza reversal**; profittevole al netto dei costi nel campione; drift più forte quando gli investitori sono distratti | **MEDIA-ALTA.** Sostiene una tenuta multi-day. Ma il segnale è la **reazione di prezzo iniziale** decomposta ad alta frequenza, non un punteggio LLM su testo: S4 non replica l'input |
| **Tetlock, Saar-Tsechansky & Macskassy**, *More Than Words*, JF 63(3) — [10.1111/j.1540-6261.2008.01362.x](https://doi.org/10.1111/j.1540-6261.2008.01362.x) | ABS | news firm-specific, azioni USA | sotto-reazione di breve, soprattutto il giorno successivo | le parole negative predicono utili e rendimenti; i profitti ad alta frequenza **possono sparire con costi ragionevoli** | **MEDIA.** Conferma la brevità dell'orizzonte e il rischio di costi; input testuale diverso |
| **Tetlock**, *All the News That's Fit to Reprint*, RFS 24(5):1481–1512 — [10.1093/rfs/hhq141](https://doi.org/10.1093/rfs/hhq141) | ABS | news USA, misura di *staleness* testuale | il rendimento del giorno di news **stantia** predice **reversal** la settimana seguente | reazione più piccola alla news stantia; reversal successivo, più forte con alto trading retail | **ALTA e sfavorevole a orizzonti lunghi.** È l'evidenza che una tenuta oltre pochi giorni su news derivata rischia di stare **dentro** la finestra di reversal |
| **Chan**, *Stock price reaction to news and no-news*, JFE 70(2) — [10.1016/S0304-405X(03)00146-6](https://doi.org/10.1016/S0304-405X\(03\)00146-6) | ABS | azioni USA, headline | drift dopo news, reversal dopo no-news | drift soprattutto dopo **cattive** news; più forte su titoli piccoli/illiquidi | **MEDIA.** Rilevante per la domanda "il silenzio è informativo?": lo è debolmente, e nella direzione opposta a un SELL |
| **Boudoukh, Feldman, Kogan & Richardson**, *Information, Trading, and Volatility*, RFS 32(3) — [10.1093/rfs/hhy083](https://doi.org/10.1093/rfs/hhy083) | ABS | news firm-specific identificate testualmente | — (varianza, non uscita) | l'informazione **fondamentale identificata** spiega **49,6%** della volatilità idiosincratica **overnight** contro **12,4%** nelle ore di contrattazione | **ALTA come vincolo di design.** Distinguere news fondamentale da rumore editoriale è ciò che separa segnale da rumore; e l'effetto è concentrato overnight, cioè fuori dalla finestra in cui S4 tiene |
| **Jeon, McCurdy & Zhao**, *News as sources of jumps*, JFE 145(2) — [10.1016/j.jfineco.2021.08.002](https://doi.org/10.1016/j.jfineco.2021.08.002) | ABS | 21 mln articoli, >9.000 titoli | — (jump intensity) | intensità e dimensione dei salti legate a frequenza e contenuto del flusso di news; effetto **cresciuto nei decenni recenti** | **MEDIA.** Motiva perché il rischio di coda di una news-strategy è *jump risk*, non varianza gaussiana — con conseguenze dirette sull'inefficacia degli stop (§3.4) |
| **Didisheim, Kelly, Pourmohammadi & Tian**, *The Inefficient Pricing of News*, NBER WP 35093 (apr. 2026, rev. mag. 2026) — [nber.org/papers/w35093](https://www.nber.org/papers/w35093) | ABS | news testuali, cross-section USA | predittività mensile fino a **18 mesi** | la news **grezza** è in larga parte prevedibile dalle caratteristiche del titolo; la *pure news* residualizzata **più che raddoppia** il potere predittivo e predice fino a 18 mesi; deriva da sotto-reazione a temi negativi/quantitativi e **sovra-reazione** a temi ad alta attenzione e ambigui | **ALTA e scomoda.** È la fonte più recente e la più critica per S4: dice che un punteggio su news *grezza* è in gran parte una replica di caratteristiche già note — cioè, plausibilmente, **di S1** |
| **Lopez-Lira & Tang**, *Can ChatGPT Forecast Stock Price Movements?*, arXiv:2304.07619 v6 (28 ott. 2025), forthcoming JFE — [arxiv.org/abs/2304.07619](https://arxiv.org/abs/2304.07619) | FT (abstract v6) | headline post-cutoff, azioni USA | reazione iniziale + drift successivo | GPT-4 cattura la reazione iniziale (≈90% hit rate portfolio-day, **non tradabile**) e predice il **drift successivo**, soprattutto su small cap e news negative; **i rendimenti della strategia calano al crescere dell'adozione LLM** | **ALTA.** È l'unico lavoro che usa lo stesso tipo di input di S4. Due implicazioni dure: la parte più forte del segnale è nella reazione **non tradabile**, e l'edge decade con l'adozione |

### 3.2 Overnight contro intraday — la famiglia che il packet non copre

| Fonte | Accesso | Universo / periodo | Risultato | Trasferibilità a S4 |
|---|---|---|---|---|
| **Lou, Polk & Skouras**, *A tug of war*, JFE 134(1):192–213 — [10.1016/j.jfineco.2019.03.011](https://doi.org/10.1016/j.jfineco.2019.03.011) | ABS | azioni USA, 14 strategie | forte continuazione firm-level **separatamente** overnight e intraday, con reversal incrociato; per 14 strategie i profitti sono guadagnati **interamente overnight** (reversal e momentum) **o interamente intraday**; esempio riportato: hedge portfolio intraday a un mese con rendimento overnight **−1,81% al mese**, `t = −8,44` | **ALTA.** Una policy che tiene 1h45 intraday e non attraversa mai una chiusura sceglie implicitamente la componente sbagliata per una strategia di tipo momentum/news |
| **Glasserman, Krstovski, Laliberte & Mamaysky**, *Does Overnight News Explain Overnight Returns?*, arXiv:2507.04481 (6 lug. 2025) | FT (abstract) | 2,4 mln articoli, ~30 anni USA | «negli ultimi 30 anni **quasi tutti** i guadagni del mercato azionario USA sono stati guadagnati overnight, mentre i rendimenti medi intraday sono stati **negativi o piatti**»; buona parte spiegata da temi di news; previsione OOS di quali titoli faranno bene overnight e male intraday | **ALTA.** È l'argomento più forte, e indipendente dall'alpha di S4, per una tenuta close-to-close |

`INFERENZA`. Queste due fonti implicano un fatto che nessun documento del packet enuncia: **la
configurazione attuale di S4 sarebbe sfavorevole anche se il suo sentiment avesse alpha**, perché
posiziona sistematicamente il capitale nella finestra a rendimento medio non positivo e lo ritira prima
di quella a rendimento positivo. Questo è un argomento a favore di *qualunque* uscita close-to-close,
D+1 incluso, e non richiede di dimostrare nulla sul segnale.

### 3.3 Time stop, holding period, costi e turnover

| Fonte | Accesso | Risultato | Trasferibilità |
|---|---|---|---|
| **Novy-Marx & Velikov**, *A Taxonomy of Anomalies and Their Trading Costs*, RFS 29(1):104–147 — [10.1093/rfs/hhv063](https://doi.org/10.1093/rfs/hhv063) | SNIP | la tecnica di mitigazione dei costi **più efficace** è il **buy/hold spread**: requisiti più stringenti per **aprire** che per **mantenere** una posizione. «La maggior parte degli anomaly con **meno del 50% di turnover mensile** genera spread netti significativi; **pochi** con turnover superiore lo fanno» | **ALTA.** Doppio uso: (i) giustifica formalmente una soglia d'uscita asimmetrica rispetto all'ingresso — cioè la struttura ±0,30 e l'isteresi; (ii) colloca S4, con tenuta mediana 1h45, molto oltre la soglia di turnover dove gli anomaly sopravvivono ai costi |
| **Gârleanu & Pedersen**, *Dynamic Trading with Predictable Returns and Transaction Costs*, JF 68(6):2309–2340 — [10.1111/jofi.12080](https://doi.org/10.1111/jofi.12080) | ABS | con costi, la posizione ottimale si muove **gradualmente** verso un target che anticipa i target futuri attesi ("aim in front of the target"), non da pieno investimento a zero | **MEDIA.** Sostiene concettualmente il de-risking parziale e le bande; le assunzioni (costi quadratici, segnale con decadimento noto) non sono verificate per S4 |
| **Davis & Norman**, *Portfolio Selection with Transaction Costs*, MOR 15(4):676–713 — [10.1287/moor.15.4.676](https://doi.org/10.1287/moor.15.4.676) | ABS | con costi proporzionali l'ottimo è una **regione di non-intervento** delimitata da barriere | **MEDIA.** Fondamento teorico della no-trade band; nessuna calibrazione trasferibile |
| **Mei, DeMiguel & Nogales**, JBF 69:108–120 — [10.1016/j.jbankfin.2016.04.002](https://doi.org/10.1016/j.jbankfin.2016.04.002) | ABS | in multi-periodo multi-asset, ignorare i costi e agire miopicamente genera perdite rilevanti; la soluzione è una regione di non-intervento state-dependent | **MEDIA** |

### 3.4 Stop di prezzo, trailing, take-profit

| Fonte | Accesso | Risultato | Trasferibilità |
|---|---|---|---|
| **Kaminski & Lo**, *When Do Stop-Loss Rules Stop Losses?*, JFM 18:183–201 — [10.1016/j.finmar.2013.07.001](https://doi.org/10.1016/j.finmar.2013.07.001) | FT (abstract integrale) | sotto Random Walk una regola stop-loss 0/1 **riduce sempre** il rendimento atteso; può aggiungere valore con momentum sufficiente; framework per lo *stopping premium* | **ALTA come vincolo negativo.** Dice quando uno stop *non può* funzionare |
| **Lo & Remorov**, *Stop-loss strategies with serial correlation…*, JFM 34 — [10.1016/j.finmar.2017.02.003](https://doi.org/10.1016/j.finmar.2017.02.003) | SNIP | su un ampio campione di azioni USA singole, gli **stop stretti sottoperformano** buy-and-hold in ottica media-varianza **per eccesso di costi**; l'outperformance richiede autocorrelazione sufficientemente alta; la riduzione del downside c'è ma **non è sostanziale** | **ALTA.** Coerente con il replay interno; non pronuncia nulla su stop di catastrofe |
| **Dai, Huang, Liu, Wang, Zhou?** — *Risk reduction using trailing stop-loss rules*, IRF 21(4):1334–1352 — [10.1111/irfi.12328](https://doi.org/10.1111/irfi.12328) | ABS integrale (Crossref) | i trailing hanno rendimento medio **inferiore** al benchmark media-varianza ma «sono efficaci nel fermare le perdite»; riducono rischio totale e downside, specie in mercati in calo; i costi penalizzano gli stop stretti, **le soglie larghe restano utili al netto dei costi** | **MEDIA.** Orizzonte e universo (buy-and-hold azionario di lungo periodo) non sono quelli di un evento a 2 giorni |
| **Han, Zhou & Zhu**, *Taming Momentum Crashes*, SSRN 2407199 | SNIP | con stop al 10% su momentum 1926–2013, la perdita mensile massima passa da −49,79% a −11,36% (EW) e da −64,97% a −23,28% (VW); Sharpe più che raddoppiati | **BASSA.** È momentum **long-short mensile**; i crash di momentum sono un fenomeno della **gamba short**, che S4 non tratta. Working paper non pubblicato in rivista peer-reviewed |
| **Arratia & Dorador**, *On the efficacy of stop-loss rules in the presence of overnight gaps*, QF 19(11):1857–1873 — [10.1080/14697688.2019.1605188](https://doi.org/10.1080/14697688.2019.1605188) | SNIP | anche modellando gap overnight e flash crash, in mercati in salita gli stop migliorano il rendimento risk-adjusted secondo la maggior parte delle metriche; la regola a percentuale fissa risulta fra le più potenti in termini risk-adjusted | **BASSA-MEDIA.** È uno studio di **simulazione su modelli di prezzo**, applicato a una posizione buy-and-hold, non a un trade evento a 2 giorni. Va citato come **controevidenza**, non ignorato |
| **Glynn & Iglehart**, *Trading Securities Using Trailing Stops*, MS 41(6):1096–1106 — [10.1287/mnsc.41.6.1096](https://doi.org/10.1287/mnsc.41.6.1096) | ABS | distribuzione, media, varianza e durata di un trailing stop sotto moto browniano con drift | **BASSA** operativamente, **ALTA** come promemoria che la distanza del trailing è un parametro del processo |
| **Imkeller & Rogers**, *Trading to Stops*, SIFIN 5(1):753–781 — [10.1137/130911706](https://doi.org/10.1137/130911706) | ABS | livelli di stop e take-profit sono una **soluzione congiunta**, non manopole indipendenti | **ALTA come vincolo metodologico** |
| **Leung & Li**, *Optimal mean reversion trading with transaction costs and stop-loss exit*, IJTAF 18(3):1550020 — [10.1142/S021902491550020X](https://doi.org/10.1142/S021902491550020X) | ABS | in un OU mean-reverting, alzare lo stop-loss **abbassa** il take-profit ottimale | **BASSA.** Assume mean reversion; S4 postula il contrario. Esempio del tipo "elegante ma non trasferibile" richiesto dal §3.7 del prompt |
| **Leung & Zhang**, *Optimal Trading with a Trailing Stop*, AMO 83(2):669–698 — [10.1007/s00245-019-09559-0](https://doi.org/10.1007/s00245-019-09559-0) | ABS | ingresso/uscita con trailing come double-stopping path-dependent; in alcuni modelli è ottimale affiancare un take-profit | **BASSA** operativamente |
| **Osler**, JF 58(5):1791–1819 — [10.1111/1540-6261.00588](https://doi.org/10.1111/1540-6261.00588); **Osler**, JIMF 24(2):219–241 — [10.1016/j.jimonfin.2004.12.002](https://doi.org/10.1016/j.jimonfin.2004.12.002) | ABS | clustering di take-profit su numeri tondi e di stop appena oltre; attorno ai cluster di stop i movimenti sono più rapidi, ampi e persistenti | **BASSA** (mercato FX, dealer). Utile solo come monito sul clustering dei livelli |
| **Broadie, Glasserman & Kou**, MF 7(4):325–349 — [10.1111/1467-9965.00035](https://doi.org/10.1111/1467-9965.00035) | ABS | correzione di continuità ∝ `σ√Δt` fra barriere monitorate in continuo e in discreto | **MEDIA come vincolo di simulazione**: un replay a barre 15 min classifica gli hit diversamente da un feed tick |

### 3.5 Signal exit, regime, e valutazione

| Fonte | Accesso | Risultato | Trasferibilità |
|---|---|---|---|
| **Brock, Lakonishok & LeBaron**, JF 47(5) — [10.1111/j.1540-6261.1992.tb04681.x](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x) | ABS | valore predittivo di segnali buy/sell tecnici sul DJIA 1897–1986 | **BASSA** oggi, dato il seguito |
| **Bajgrowicz & Scaillet**, JFE 106(3):473–491 — [10.1016/j.jfineco.2012.06.001](https://doi.org/10.1016/j.jfineco.2012.06.001) | ABS | con controllo delle false discovery, persistenza e costi, le regole migliori **non sono selezionabili ex ante** e piccoli costi ne annullano la performance | **ALTA come monito**: vale identicamente per una griglia di exit |
| **Moreira & Muir**, JF 72(4) — [10.1111/jofi.12513](https://doi.org/10.1111/jofi.12513) | ABS | ridurre esposizione in alta volatilità aumenta Sharpe e utilità su più fattori | **MEDIA** |
| **Barroso & Santa-Clara**, JFE 116(1):111–120 — [10.1016/j.jfineco.2014.11.010](https://doi.org/10.1016/j.jfineco.2014.11.010) | ABS | il risk management elimina quasi i crash di momentum e quasi raddoppia lo Sharpe | **BASSA-MEDIA**: long-short, gestione di *size*, non di uscita per-trade |
| **Cederburg, O'Doherty, Wang & Yan**, JFE 138(1):95–117 — [10.1016/j.jfineco.2020.04.015](https://doi.org/10.1016/j.jfineco.2020.04.015) | ABS | su 103 strategie **nessun beneficio OOS sistematico** dal volatility management; instabilità e performance real-time spesso peggiore | **ALTA come controevidenza** al regime-gating |
| **DeMiguel, Martin-Utrera & Uppal**, JF 79(6):3859–3891 — [10.1111/jofi.13395](https://doi.org/10.1111/jofi.13395) | ABS | le versioni semplici di volatility management possono fallire OOS o dopo i costi; serve un modello condizionale multifattoriale | **MEDIA** |
| **Vaicenavicius**, AMO 81(3):757–784 — [10.1007/s00245-018-9518-5](https://doi.org/10.1007/s00245-018-9518-5) | ABS | con drift ignoto, la liquidazione ottimale dipende dalla **credenza aggiornata** sull'edge e dal regime di volatilità, non dal solo P&L realizzato | **MEDIA-ALTA concettualmente**: è la formalizzazione del "posterior exit" |
| **McLean & Pontiff**, JF 71(1):5–32 — [10.1111/jofi.12365](https://doi.org/10.1111/jofi.12365) | ABS | i rendimenti degli anomaly decadono dopo la pubblicazione | **MEDIA**: coerente con il decadimento riportato da Lopez-Lira & Tang all'aumentare dell'adozione LLM |
| **Hirshleifer, Lim & Teoh**, JF 64(5) — [10.1111/j.1540-6261.2009.01501.x](https://doi.org/10.1111/j.1540-6261.2009.01501.x) | ABS | la distrazione degli investitori aumenta la sotto-reazione | **MEDIA**: coerente con Jiang et al.; suggerisce una covariata di stato per l'orizzonte |
| **White**, ECTA 68(5):1097–1126 — [10.1111/1468-0262.00152](https://doi.org/10.1111/1468-0262.00152) · **Hansen**, JBES 23(4):365–380 — [10.1198/073500105000000063](https://doi.org/10.1198/073500105000000063) · **Sullivan, Timmermann & White**, JF 54(5) — [10.1111/0022-1082.00163](https://doi.org/10.1111/0022-1082.00163) | ABS | Reality Check e SPA per l'inferenza dopo data snooping | **ALTA**, con la riserva di §6.7 |
| **Bailey & López de Prado**, JPM 40(5):94–107 — [10.3905/jpm.2014.40.5.094](https://doi.org/10.3905/jpm.2014.40.5.094) · **Bailey, Borwein, López de Prado & Zhu**, JCF — [10.21314/JCF.2016.322](https://doi.org/10.21314/JCF.2016.322) | ABS | DSR corregge per numero di trial e non-normalità; CSCV/PBO misurano la probabilità di overfitting | **MEDIA**: DSR è definito su serie di Sharpe, non su delta appaiati per trade |
| **Harvey & Liu**, *Backtesting*, JPM 42(1):13–28 — [10.3905/jpm.2015.42.1.013](https://doi.org/10.3905/jpm.2015.42.1.013) · *Evaluating Trading Strategies*, JPM 40(5):108–118 — [10.3905/jpm.2014.40.5.108](https://doi.org/10.3905/jpm.2014.40.5.108) · **Harvey, Liu & Zhu**, RFS 29(1):5–68 — [10.1093/rfs/hhv059](https://doi.org/10.1093/rfs/hhv059) | ABS | haircut dello Sharpe in funzione del numero di test; soglie `t` più severe | **ALTA**, e più applicabile del DSR al nostro caso |
| **Almgren & Chriss**, JOR 3(2):5–39 — [10.21314/JOR.2001.041](https://doi.org/10.21314/JOR.2001.041) | ABS | frontiera ottimale fra impatto e rischio di esecuzione | **BASSA** alla size attuale; separa comunque *quando* uscire da *come* uscire |
| **Joubert**, *Meta-Labeling: Theory and Framework*, JFDS 4(3):31–44 — [10.3905/jfds.2022.1.098](https://doi.org/10.3905/jfds.2022.1.098) | SNIP | un secondo modello sopra la strategia primaria per dimensionare e filtrare i falsi positivi; separazione **side/size** | **MEDIA.** È la formalizzazione più vicina a "il contro-segnale deve usare un modello diverso da quello d'ingresso" |
| **Grądzki et al.**, *Financial Innovation* 11(1) — [10.1186/s40854-025-00866-w](https://doi.org/10.1186/s40854-025-00866-w) | ABS | triple barrier labeling superiore al next-bar labeling nel loro esperimento su crypto | **BASSA** come prova; **ALTA** come struttura di *labeling* per generare outcome coerenti |

### 3.6 Cosa la letteratura **non** dice

`INFERENZA`. Ho cercato e non ho trovato: (a) alcun lavoro peer-reviewed che stimi il decadimento
dell'alpha di un **punteggio LLM su news** stratificato per orizzonte intraday/D+1/D+2/D+3 su un
universo large-cap — Lopez-Lira & Tang è il più vicino ma non pubblica quella curva; (b) alcuna
evidenza che una **soglia di contro-segnale** su un punteggio di sentiment domini un time-stop; (c)
alcuna evidenza che un **take-profit fisso** migliori una strategia news long-only. Queste tre lacune
non sono un dettaglio: sono esattamente i tre punti su cui il design di S4 sta prendendo decisioni.

---

## 4. Strategy catalog

Complessità: **B** basso (solo replay), **M** medio (nuovo stato per posizione), **A** alto (nuovo
modello o dato point-in-time). Trial cost: quanti gradi di libertà consuma nel test.

| ID | Policy | Razionale | Vantaggi | Failure mode | Compl. | Trial cost |
|---|---|---|---|---|---|---|
| **E0** | uscita corrente a target-weight zero | baseline | nessuno da difendere | non è una policy: confonde falsificazione, rank truncation, filtro e bug; tenuta bimodale non limitata | — | 0 (benchmark) |
| **E1** | D+2 close + contro-segnale + catastrophe stop | candidata registrata | dichiara un orizzonte; bounda l'esposizione overnight; riduce il turnover di ~1 ordine di grandezza | il catastrophe stop non protegge dal gap (§6.6) e aggiunge un parametro non necessario | B | 1 |
| **E1′** | **D+2 close come tenuta MASSIMA + contro-segnale asimmetrico + nessuno stop ordinario** | come E1, ma togliendo lo stop che il replay interno e Lo-Remorov già sconsigliano, e rendendo esplicito che D+2 è un **tetto**, non un obiettivo | massima parsimonia: **un solo parametro nuovo**; separa nettamente falsificazione (contro-segnale) da scadenza (clock) | se la coda di perdita è gap-driven, non la elimina — la limita a 2 estrazioni | B | 1 |
| **E2** | D+1 e D+3 | diagnostica della term structure | mostra se il risultato è un plateau o un picco | tentazione di sceglierne uno ex post | B | 0 se **pre-dichiarate come robustezza**, 2 se candidate |
| **E3** | contro-segnale only con tenuta massima dichiarata | test della falsificazione della tesi | isola il contributo del contro-segnale | con `max_hold` lungo degenera in E1 con altro nome; con `max_hold` infinito riproduce il failure WDC | B | 1 |
| **E4** | time-stop + uscita su **segnale aggregato/decaduto** invece dell'ultimo articolo | separa exit design da input churn | attacca il difetto documentato "l'ultimo articolo vince" (NVDA/Lumentum) | l'aggregazione è essa stessa un modello da specificare ex ante; rischio di leakage se usa novelty calcolata a posteriori | M | 1 |
| **E5** | time-stop + catastrophe/volatility stop largo | protezione di coda senza noise stop | risponde alla domanda del PO sulla coda | **previsione registrata: non migliorerà il P&L medio**; sui dati Alembic la coda è arrivata via gap, che uno stop non intercetta | B | 1 |
| **E6** | trailing attivato solo dopo MFE predefinita | protegge i vincitori | può proteggere la MFE | MAE mediana dei vincitori S4 = 0,39σ (`EVIDENZA ALEMBIC`): qualunque trailing utile è o troppo stretto o inattivo; tronca la coda destra che finanzia la strategia | M | 1 |
| **E7** | policy per event-type / segno | la letteratura mostra eterogeneità (Chan, Heston-Sinha, Tetlock 2011) | potenzialmente il vero modello | **non identificabile**: servirebbe un classificatore point-in-time di tipo evento che oggi non esiste, e una numerosità per cella che S4 non ha | A | 3+ |
| **E8** | replacement exit su costo-opportunità | separa capacità top-5 e validità della tesi | economicamente la formulazione corretta | richiede stima di valore atteso per candidato, che è precisamente ciò che non sappiamo stimare | A | 2 |
| **E9** | de-risking parziale / posterior expected-edge | Gârleanu-Pedersen, Vaicenavicius, Davis-Norman | teoricamente dominante sul full-close binario | alla size S4 (slot ~2% del NAV) una riduzione al 50% è un ordine da poche centinaia di dollari: i costi fissi e il rumore di misura dominano il beneficio teorico | A | 2 |
| **E10** *(aggiunta)* | **buy/hold spread esplicito**: soglia di *mantenimento* più permissiva della soglia di *ingresso*, con D+2 come tetto | [Novy-Marx & Velikov 2016](https://doi.org/10.1093/rfs/hhv063): è la mitigazione dei costi più efficace | ha una fonte primaria diretta, cosa che nessuna delle altre ha; generalizza min-hold e isteresi in un unico parametro economico | rischio di trattenere un segnale davvero invalidato — mitigato dal contro-segnale che resta un'eccezione | M | 1 |

**Perché aggiungo E10 e non altro.** Il prompt chiede di giustificare ogni trial aggiuntivo. E10 è
l'unica policy del catalogo la cui forma — non solo la direzione — è raccomandata esplicitamente da una
fonte primaria pubblicata su una rivista di primo livello, e con un risultato quantitativo sul turnover
che colloca S4 fuori dalla regione in cui gli anomaly sopravvivono ai costi. In più, **S4 la implementa
già in forma implicita e non calibrata**: min-hold 90′ + isteresi 2 cicli *sono* un buy/hold spread,
espresso in unità di tempo anziché di punteggio. Renderlo esplicito non aggiunge un meccanismo: ne
sostituisce uno arbitrario con uno motivato.

**Perché non aggiungo nulla su regime.** Cederburg et al. e DeMiguel et al. mostrano che il volatility
management semplice non regge OOS. S4 ha già `regime_mult` e un drawdown cap di portafoglio. Una exit
per-trade guidata dal regime confonderebbe rischio comune e invalidazione della news. `IPOTESI` non
prioritaria.

---

## 5. Shortlist

Tre policy al confronto confirmatorio, più il benchmark. Tutto il resto è diagnostico o respinto.

### 5.1 Le tre candidate

| Rango | ID | Specifica esatta | Ruolo |
|---|---|---|---|
| **1** | **E1′** | uscita a mercato alla chiusura di **D+2** se la posizione è ancora aperta; **contro-segnale** (valore da fissare, §5.3) come unica uscita anticipata; **nessuno stop protettivo ordinario**; il disaster stop broker resta com'è ed è **escluso dal confronto** perché comune a tutte le varianti; `max_signal_age` solo come filtro d'ingresso; clock DAILY applicato | **challenger primaria** |
| **2** | **E10** | E1′ + soglia di mantenimento asimmetrica: una posizione è mantenuta finché `score ≥ h_hold` con `h_hold < h_entry`, invece che finché è nel top-5. `h_hold` **fissato ex ante** a `h_entry / 2`, non calibrato | **challenger secondaria** — testa se il buy/hold spread aggiunge oltre il time-stop |
| **3** | **E5** | E1′ + stop di catastrofe a `min(8σ, 12%)` sotto il fill, monitorato a barre 15 min, con **previsione pre-registrata di NON migliorare il P&L medio** | **challenger di coda** — valutata su ES e perdita massima per trade, non sulla media |
| — | **E0** | uscita corrente, replay fedele | **benchmark** |
| — | **E2** | D+1 e D+3 | **robustezza pre-dichiarata**: il segno del delta E1′−E0 non deve essere contraddetto. Non promuovibili |

### 5.2 Diagnostici (non confirmatori)

**E4** (segnale aggregato per il contro-segnale), **E9** (de-risking parziale) e la decomposizione
**intraday/overnight** dei rendimenti post-fill. E4 in particolare è ad alto valore informativo ma è un
cambio di *input*: se il suo replay diagnostico mostrasse un effetto grande, la mossa corretta è una
**nuova** pre-registrazione, non la promozione di E4 dentro questo test.

### 5.3 Respinte, con motivo

- **E6 (trailing dopo MFE)** — respinta. `EVIDENZA ALEMBIC`: MAE mediana dei vincitori S4 = **0,39%**
  contro σ mediana all'ingresso 2,72%, cioè **0,14σ**. Un trailing che non stoppi i vincitori dovrebbe
  essere talmente largo da non attivarsi quasi mai. Non c'è spazio parametrico.
- **E7 (event-type)** — respinta per **non identificabilità**: manca un classificatore point-in-time.
- **E8 (replacement)** — respinta: richiede una stima di valore atteso per candidato che oggi non
  esiste. Il ramo A è già, di fatto, un replacement exit implicito — ed è il difetto da rimuovere.
- **E3 (counter-signal only)** — respinta come candidata separata: con un `max_hold` dichiarato è E1′
  con altro nome; senza, riproduce WDC.
- **Take-profit fisso** — respinto: nessuna fonte primaria lo supporta per una news long-only, e la
  letteratura sulle barriere congiunte (Imkeller & Rogers) dice che non è un parametro isolabile. Il
  +6% oggi presente va **neutralizzato o registrato come confound**, non promosso.

### 5.4 Il valore del contro-segnale — la decisione bloccante

`NON DECIDIBILE` dal repository, `bloccante` per il campione. Codice `−0,20`, documento `−0,30`.
La raccomandazione, motivata e non arbitraria: **adottare `−0,30`**, perché rende la banda di
non-intervento simmetrica alla soglia d'ingresso di `+0,30` e realizza quindi la struttura di
buy/hold spread raccomandata da Novy-Marx & Velikov — mentre `−0,20` crea una banda asimmetrica **nella
direzione sbagliata** (più facile uscire che entrare), che è la ricetta per il churn che i dati
mostrano. Ma la scelta va **fatta e timestampata prima** di guardare il segmento, e va verificata
sull'env del container, non dedotta.

---

## 6. Empirical protocol

### 6.1 Il principio: la domanda sull'uscita è appaiata, quella sull'alpha no

`INFERENZA` — è il punto metodologico centrale di questa analisi.

La pre-registrazione fonde due domande con proprietà statistiche opposte:

| | Domanda alpha (R2) | Domanda uscita |
|---|---|---|
| stimatore | IC cross-sezionale medio | delta **appaiato** per trade |
| varianza | dev. std. giornaliera **0,237** (`EVIDENZA ALEMBIC`, `s4_ic.json`) | varianza del *differenziale* fra due uscite sullo **stesso** ingresso |
| sorgenti di rumore | rendimento di mercato, fattori, selezione, segnale | **solo** ciò che accade fra un'uscita e l'altra |
| numerosità necessaria | `(3 × 0,243 / 0,05)² ≈ 213` sedute | da stimare; plausibilmente **un ordine di grandezza meno** |

Nel confronto appaiato il rendimento di mercato, il beta, il fattore e la qualità del segnale **si
cancellano**, perché entrambe le varianti detengono lo stesso titolo, comprato allo stesso prezzo, alla
stessa ora, nella stessa size. Resta solo il rendimento del segmento temporale in cui una variante è
investita e l'altra no. Tenere l'uscita ostaggio del gate IC significa non decidere per dieci mesi una
cosa decidibile in due.

**Raccomandazione operativa:** lasciare R1–R4 **intatti** come gate di riattivazione del capitale — è
la decisione giusta e non va toccata — e registrare **separatamente** questo protocollo, il cui unico
output è *quale uscita spedire, se e quando B verrà riattivata*. Non è un indebolimento della
disciplina: è togliere dal percorso critico di R2 una domanda che non gli appartiene.

### 6.2 Event ledger point-in-time

Una riga per **intento di ingresso**, non per articolo. Campi minimi:

**Identità e provenienza**
`intent_id` · `signal_id` (dalla `provenance` pinnata dal ranker, non da una riquery del "latest") ·
`article_id` · `ticker_risolto` + `metodo_di_risoluzione` (`extraction_method`, QT-03) ·
`n_ticker_taggati_sull_articolo` · `source` · `published_at` / `ingested_at` / `generated_at` /
`decision_at` (quattro timestamp distinti, mai collassati) · `model_id` · `fallback_used` ·
`ensemble_std` · `score` · `confidence`.

**Esecuzione**
`fill_price` eseguibile · `fill_ts` · `notional` · `qty` · `is_fractionable` · `bracket_attached` ·
`collisione_S1` (bloccato / non bloccato / già a libro) · `entry_threshold` attivo in quel ciclo ·
`regime_mult` · spread e volume al fill.

**Contesto di prezzo**
barre 15 min e daily con `adjustment="all"` (#192) · **percentile del range giornaliero al fill**
(Alembic lo calcola già: mediana mobile 20 giorni 0,535, ingressi osservati 0,71–0,92) ·
σ a 20 e 63 giorni · gap di apertura di ogni seduta successiva.

**Outcome path-dependent, per ogni orizzonte candidato**
MAE, MFE, tempo a MAE e a MFE · rendimento **decomposto in componente intraday e componente
overnight** · prezzo realisticamente eseguibile all'uscita di ciascuna policy · quale barriera è stata
toccata **per prima**.

**Post-exit**
drift a 1h, close, D+1, D+2, D+3, D+5 dopo l'uscita effettiva di ciascuna policy.

**Censura**
motivo di dato mancante, halt, delisting, corporate action, barra assente, fill parziale.

**Vincolo anti-look-ahead.** Novelty, tipo evento e validazione ticker possono entrare in una policy
solo se esiste una versione **calcolata al `decision_at`**. In assenza, entrano solo come stratificazione
diagnostica *dichiarata prima* di leggere i risultati.

### 6.3 Costruzione dei controfattuali

Ingressi **congelati e identici**: stessi `intent_id`, stessi `fill_price`, stessa size. Le policy
divergono **solo** dopo il fill. Regole di risoluzione da fissare ex ante:

1. **Ordine intrabar.** Se in una stessa barra 15 min sono soddisfatte più condizioni, l'ordine di
   priorità è: contro-segnale → stop → time barrier. Registrare separatamente quante volte l'ordine
   conta: è la forma pratica del problema dei *competing risks*.
2. **Monitoraggio discreto.** Le barriere sono valutate su barre 15 min. Broadie-Glasserman-Kou implica
   che questo **sottostima** gli hit rispetto a un feed continuo: riportare la sensibilità sostituendo
   il close della barra con il low/high della barra e mostrare entrambe le classificazioni.
3. **Prezzo di uscita.** Time-stop = ultimo prezzo eseguibile RTH della sessione D+2, non il close
   ufficiale. Contro-segnale e stop = primo prezzo eseguibile del ciclo successivo alla condizione, non
   il prezzo che l'ha innescata.
4. **Gap.** Se una barriera è saltata da un gap, il fill è al **prezzo di apertura**, mai al trigger.
   Questa singola regola determina l'esito del confronto su E5.
5. **Bracket.** Su titoli non-fractionable con bracket aperto, registrare esplicitamente se la SELL
   della policy sarebbe stata eseguibile (vedi **[F-C]**). Le uscite non eseguibili sono un **dato**,
   non un'omissione.
6. **Weekend e festivi.** D+2 conta **sedute di borsa**, mai ore di parete. È lo stesso errore di unità
   che `max_signal_age_hours=4` commette oggi sull'ingresso.

### 6.4 Metriche

**Rendimento** — P&L netto totale · **delta appaiato per trade in bps del notional** (primaria) ·
excess return contro E0 e contro un benchmark equal-weight della watchlist · expectancy · mediana ·
hit rate · profit factor · payoff win/loss.

**Rischio** — dev. std. dei delta · downside deviation · **Expected Shortfall al 95% sui delta per
trade** (più informativo del VaR su questo `n`) · perdita massima su singolo trade · max drawdown e
durata sulla serie shadow · **skewness e contributo della coda destra**: quota del P&L totale prodotta
dal miglior 10% dei trade, e quanti di quei trade ciascuna policy tronca.

**Costo e capitale** — turnover · costi espliciti · **slippage strutturale**, misurato come differenza
fra IC da prezzo-segnale e IC da prezzo eseguibile (la pre-registrazione lo chiede già ed è la misura
giusta) · **capitale-giorni occupati** · **P&L per capitale-giorno**, che è il vincolo vero data la
collisione con S1.

**Diagnostica dell'uscita** — false-stop rate (uscita in perdita seguita da recupero entro l'orizzonte
della tesi: il pattern IBM/SONY/HOOD è già una serie osservata) · giveback dalla MFE · perdita evitata
rispetto alla MAE · **decomposizione intraday/overnight del P&L di ciascuna policy**.

**Stratificazioni pre-dichiarate** (diagnostiche, mai per selezionare) — segno · quintile di score ·
articolo single-ticker vs multi-ticker · `extraction_method` · source · ora del fill · percentile del
range al fill · gap sì/no · σ all'ingresso · sovrapposizione con S1.

**Regola sul reporting.** Rendimento, rischio e utilità economica vanno mostrati **separatamente**. Una
policy che riduce la volatilità abbassando il P&L atteso non è un miglioramento dei guadagni, e
viceversa. Questo vincolo del prompt è particolarmente rilevante per E5, che è progettata proprio per
comprare rischio di coda con rendimento medio.

### 6.5 Inferenza e potenza

**Unità di clustering.** Non il trade. Il **giorno**, e dentro il giorno l'**evento**: più articoli
sullo stesso ticker-giorno, e più ticker mossi dallo stesso tema (la rotazione settoriale documentata
nelle sedute 08-03→08-11) non sono osservazioni indipendenti. **Block bootstrap stazionario a blocchi
giornalieri**, con la lunghezza media del blocco scelta ex ante e non ottimizzata.

**Sovrapposizione.** I forward return a D+3 e D+5 si sovrappongono. HAC/Newey-West con lag coerente
sull'orizzonte per le serie; per i delta appaiati per trade, il block bootstrap è preferibile perché
non richiede assunzioni sulla forma della dipendenza.

**Multiple testing.** L'universo dichiarato è **{E1′, E10, E5}** contro E0, più **{D+1, D+3}** come
robustezza non promuovibile. Cinque configurazioni, dichiarate prima. Test SPA di Hansen sull'universo,
riportando anche il Reality Check di White come confronto — SPA è più potente e meno sensibile alle
alternative irrilevanti, ma su cinque alternative la differenza sarà piccola e mostrarla entrambe è
onesto. **Il DSR è meno adatto qui** e va riportato solo come sanity check: è definito su Sharpe di
serie di rendimenti, mentre la statistica primaria è una media di delta appaiati.

**Registro dei trial.** Va pubblicato il conteggio **completo**, incluse le analisi che il team ha già
visto: il replay stop-loss su 245 trade con le sue 5 configurazioni di cap/k, le 5 righe di
sensibilità su `MIN_SIMBOLI_GIORNO` di E4 nella pre-registrazione, e ogni variante scartata. Senza
questo, SPA e DSR sottocorreggono per costruzione — è esattamente il monito di Bajgrowicz & Scaillet.

**Power analysis — metodo, non numero.** Il minimum detectable effect va calcolato **così**, e i numeri
qui sotto sono un ordine di grandezza illustrativo da rifare sui dati, non un risultato:

```
MDE ≈ t* × sd(delta_appaiato) / sqrt(n_effettivo)
n_effettivo ≈ n_giorni  (non n_trade, per il clustering)
```

`IPOTESI` illustrativa: se `sd(delta) ≈ 3%` per trade e ~3 trade/giorno con correlazione intra-giorno
alta, con 40 sedute pulite `n_effettivo ≈ 40` e `MDE(t=2) ≈ 0,95%` per trade. Un effetto dell'ordine
dell'1% per trade su una tenuta di 2 sedute **è economicamente sensato** e sarebbe rilevabile.
Con la stessa aritmetica il gate IC richiede ~213 sedute. **Il rapporto fra i due numeri è la
giustificazione quantitativa di §6.1**, ma va rifatto: `sd(delta)` è ignoto finché non si costruisce il
ledger, e potrebbe essere molto maggiore del 3% se dominato da pochi gap.

**Se il campione non decide, l'esito è `INCONCLUSIVE`** e va scritto così, non convertito in "nessuna
differenza".

### 6.6 Perché il rischio di coda di S4 non è un problema di stop

`INFERENZA` da evidenza verificata, ed è la conclusione che più mi allontana dal catalogo del prompt.

La perdita massima osservata su S4 non è arrivata attraverso una discesa intraday che uno stop possa
intercettare. È arrivata come **gap di apertura del −17,39%** su WDC il 2026-08-06. Un `d_hard` al 12%
avrebbe avuto trigger sopra il prezzo di apertura: l'ordine sarebbe stato convertito in market e
riempito **al prezzo del gap**, cioè peggio del trigger, senza evitare nulla di sostanziale. E Jeon,
McCurdy & Zhao mostrano che questa non è sfortuna: per le strategie news il rischio è **jump risk**, con
intensità legata al flusso stesso di notizie, e in crescita nei decenni recenti.

Ne segue che gli strumenti che realmente controllano la coda di S4 sono tre, e nessuno è uno stop:
**(i)** il numero di *estrazioni overnight* a cui il capitale è esposto — che è precisamente ciò che un
time-stop dichiarato limita, da illimitato a 2; **(ii)** la size dello slot; **(iii)** la
diversificazione fra slot. Questo è il motivo per cui classifico E5 come challenger *di coda* con
previsione registrata di fallimento sulla media: serve a chiudere la domanda del PO con un dato, non
perché mi aspetti che vinca.

### 6.7 Limiti dichiarati del protocollo

- **SPA su cinque alternative con `n` piccolo ha potenza bassa.** Il rischio dominante qui non è il
  falso positivo da data snooping — l'universo è piccolo e dichiarato — ma il **falso negativo**.
  Riportare la potenza stimata insieme al p-value.
- **Il block bootstrap giornaliero con 30–40 giorni ha pochi blocchi.** Gli intervalli saranno larghi.
  Dichiararlo prima, non scoprirlo dopo.
- **Il replay non riproduce l'impatto di mercato né la latenza reale.** Alla size attuale è
  probabilmente trascurabile, ma l'ingresso tardivo (percentile 0,71–0,92 del range) suggerisce che lo
  slippage *strutturale* superi i costi espliciti. Va misurato, non assunto.
- **`n_effettivo` non è `n_trade`.** Qualunque tabella che riporti `n = numero di trade` senza il
  numero di giorni sovrastima la potenza.

---

## 7. Pre-registration draft

> Bozza da timestampare **prima** di leggere qualunque segmento post-fix. Non sostituisce
> `04_PREREGISTRAZIONE_D2.md`: lo affianca, con un oggetto diverso (l'uscita) e un gate diverso.
> R1–R4 di quel documento restano il gate di riattivazione del **capitale** e non sono toccati.

**Oggetto.** Quale regola di uscita spedire con S4, se e quando B verrà riattivata.

**Ipotesi primaria — una sola.**
> Su un insieme di intenti d'ingresso congelati, la policy **E1′** (uscita alla chiusura di D+2 come
> tenuta massima; contro-segnale come unica uscita anticipata; nessuno stop protettivo ordinario)
> produce un **P&L netto per trade superiore** alla policy corrente **E0**.

**Benchmark.** E0, replay fedele del comportamento corrente sugli stessi ingressi. In secondo piano,
un benchmark equal-weight della watchlist per contestualizzare, **non** per il test.

**Metrica primaria.** Media del **delta appaiato per trade**, `(P&L netto E1′ − P&L netto E0)`, espressa
in **bps del notional d'ingresso**, al netto di costi e slippage conservativi.

**Vincolo co-primario.** Il **P&L per capitale-giorno** di E1′ non deve essere inferiore a quello di E0
oltre una tolleranza pre-registrata. Senza questo vincolo, D+2 può "vincere" semplicemente occupando
più bilancio, che è precisamente la risorsa contesa con S1.

**Robustezza pre-dichiarata, non promuovibile.** Il segno del delta non deve essere contraddetto a
**D+1** e **D+3**.

**Universo dei trial dichiarato.** {E1′, E10, E5} contro E0, più {D+1, D+3} come robustezza. Nessuna
altra variante entra. Ogni aggiunta successiva invalida la pre-registrazione o richiede una nuova.

**Gate congiunto — tutte le condizioni.**

| | Condizione | Soglia |
|---|---|---|
| **G1 — integrità** | lifecycle shadow ricostruibili end-to-end | ≥ 95% |
| | uscite `unknown` + `expired` | < 5% |
| | divergenze fra configurazione dichiarata e applicata | zero materiali |
| **G2 — economia** | limite inferiore unilaterale al 95% del delta appaiato medio (block bootstrap giornaliero) | **> 0** |
| **G3 — coda** | ES 95% dei delta per trade e perdita massima su singolo trade | non peggiori di E0 oltre una tolleranza fissata ex ante |
| **G4 — costi** | G2 deve reggere con costi e slippage al **doppio** della stima centrale | sì |
| **G5 — stabilità** | segno del delta coerente fra prima e seconda metà del campione, e fra i sottoperiodi di regime dichiarati | sì |
| **G6 — molteplicità** | SPA di Hansen sull'universo dichiarato | p ≤ 0,10 (soglia più permissiva del solito **perché il rischio dominante è il falso negativo**, §6.7; dichiarata ora, non dopo) |
| **G7 — S1** | overlap degli intenti e capitale-giorni impegnati entro la soglia già registrata (≤ 50%, #181/#182); oltre, valore incrementale dimostrato | sì |

**Sample start.** `n = 0` parte **solo** quando sono simultaneamente vere: (a) shadow end-to-end attivo
con lo stesso codice dell'esecuzione fino al confine broker; (b) valore effettivo del contro-segnale
verificato sull'env e timestampato (**[F-B]**); (c) clock DAILY realmente applicato; (d) il ledger §6.2
si popola con tutti i campi obbligatori.

**Stopping rule.** Il campione si chiude al raggiungimento della numerosità derivata dalla power
analysis di §6.5, **ricalcolata sulla `sd(delta)` osservata nelle prime 15 sedute** e congelata a quel
punto. Nessun early stop se non per un effetto pre-registrato di dimensione ≥ 3× l'MDE, verificato su
almeno 20 sedute.

**Condizioni di invalidazione e riavvio.**
- qualunque modifica a fonte, resolver, gate, ranking, soglia, universo, sizing, slot, cost model,
  orizzonte o regola d'uscita durante la raccolta;
- scoperta di un difetto di implementazione che possa aver alterato le osservazioni (§8 di `04`);
- divergenza fra configurazione dichiarata e applicata rilevata a posteriori;
- se un fix a monte (#243/#244 o simili) cambia la **popolazione** dei segnali: il segmento pre-fix e
  quello post-fix **non si concatenano**.

**Esito negativo.** Se G2 fallisce con intervallo che include lo zero e l'MDE è stato raggiunto: E1′
non è superiore a E0 e la decisione di uscita torna aperta — il che, dato quanto E0 è difettoso,
implicherebbe che il problema di S4 non è l'uscita. Se l'MDE **non** è stato raggiunto: `INCONCLUSIVE`,
e va scritto così.

**Previsioni registrate ora, per poterle sbagliare pubblicamente.**

1. E1′ batte E0 sul delta appaiato medio. *(confidenza media-alta)*
2. E5 **non** migliora il P&L medio rispetto a E1′, e migliora al più marginalmente l'ES. *(alta)*
3. Il delta di E1′ è **in maggioranza attribuibile alla componente overnight** del rendimento. *(media)*
4. E10 aggiunge poco **oltre** E1′: il time-stop cattura la maggior parte del guadagno da riduzione del
   turnover. *(media-bassa)*

---

## 8. Unknowns and data requests

### 8.1 Non decidibile dai materiali forniti

| # | Questione | Perché non decidibile | Cosa serve |
|---|---|---|---|
| U1 | **Valore effettivo della soglia di contro-segnale** | codice `−0,20`, documento `−0,30`, env non leggibile | `docker exec <worker> env \| grep SENTIMENT_REVERSAL`, più i log di ogni force-sell con la soglia effettivamente applicata |
| U2 | **Gli stop `d_hard` esistono davvero al broker su ogni posizione?** | il codice li crea, ma il commento YAML dice il contrario e non ho accesso al broker | elenco degli ordini STOP aperti per simbolo, con `stop_price`, `qty` e confronto con `avg_entry × (1 − d_hard)` |
| U3 | **Il ramo bracket (E) ha mai agito su S4?** | il codice dice "100% fractionable al 2026-07-16"; il ramo potrebbe essere dormiente | conteggio dei BUY S4 con `is_fractionable = false`, e ogni fill di gamba TP/SL |
| U4 | **`unknown` copre quale quota delle uscite S4?** | la tabella del packet ne mostra 3 su 9 in una settimana selezionata | distribuzione di `exit_mechanism` su tutta la vita di S4, per settimana |
| U5 | **Distribuzione completa della tenuta** | il packet dà mediana 1h45; WDC dice 16 sedute | istogramma della tenuta di **tutti** i round trip S4, non della settimana selezionata. È il dato che decide se la bimodalità di **[F-F]** è generale |
| U6 | **Quanta parte del P&L S4 è gap-driven?** | il caso WDC è uno solo | decomposizione intraday/overnight del P&L di ogni posizione S4, dalla vita intera |
| U7 | **Overlap con S1 misurato su finestra lunga** | 30 intenti su 2 giorni sono un allarme, non una misura; la memoria di progetto riporta 74% al 2026-08-14 su 39 intenti, che resta corto | serie degli intenti per strategia su ≥ 40 sedute |

### 8.2 Richieste di dato, in ordine di valore informativo per costo

1. **Decomposizione intraday/overnight dei rendimenti post-fill di S4** (retrospettiva, una tantum).
   **È la richiesta numero uno.** Testa direttamente il mio argomento esterno più forte
   (Glasserman et al., Lou-Polk-Skouras) sulla popolazione di S4, e può falsificare la mia
   raccomandazione con un solo grafico. Costo: basso — le barre sono già disponibili con
   `adjustment="all"`.
2. **Istogramma completo della tenuta e del P&L per decile di tenuta.** Stabilisce se il P&L vive nel
   churn o nella coda. Se vive nella coda (come **[F-F]** suggerisce), tutta l'attenzione al churn a
   1h45 è mal riposta.
3. **Term structure post-fill `{15m, 1h, 4h, close, D+1, D+2, D+3, D+5}`** su prezzi eseguibili,
   stratificata per single-ticker vs multi-ticker e per `extraction_method`. Esplorativa una tantum,
   **non** conta come OOS.
4. **Quota del P&L totale prodotta dal miglior 10% dei trade.** Se le code destre finanziano la
   strategia, qualunque troncamento (take-profit, trailing) è distruttivo per costruzione, e la §5.3
   diventa non negoziabile.
5. **Conteggio completo dei trial già effettuati.** Senza, §6.5 sottocorregge.

### 8.3 Una nota sul cutoff

Durante questa analisi sono comparse nell'albero di lavoro modifiche non committate a
`src/strategies/s4/strategy.py` che citano `#236` e descrivono il difetto per cui `_signals_as_of`
ri-filtrava per età i segnali che FIX-D aveva **esplicitamente riammesso**, azzerandone il peso e
provocando la SELL senza contro-segnale su SONY, HOOD, IBM, SPCX. È **esattamente** il meccanismo che
avevo isolato in modo indipendente come **[F-E]** leggendo i report alpha-miss.

Non ho usato quel codice come base dell'analisi — è posteriore al cutoff — e non ne valuto la
correttezza. Ma il fatto ha una conseguenza per la pre-registrazione, e la scrivo: **quel difetto è
proprio del tipo che invalida un campione** ai sensi di §8.4 di `04_PREREGISTRAZIONE_D2.md`. Se il fix
entra durante la raccolta, il segmento va riavviato; se entra prima, cambia la popolazione delle
uscite osservate e quindi **la baseline E0 stessa non è confrontabile fra i due lati del fix**.
L'ordine corretto è: fix, poi congelamento, poi `n = 0`.

---

## 9. Challenge to the existing D+2 decision

### 9.1 Il miglior argomento **a favore** di D+2

Non è quello registrato. L'argomento registrato — «allineare l'uscita all'orizzonte economico» —
presuppone che esista un orizzonte economico noto, e la letteratura non lo consegna: Ke-Kelly-Xiu
danno 2 giorni per la news stantia e 4 per quella fresca, Heston-Sinha 1–2 giorni, Jiang et al. «vari
giorni», Didisheim et al. fino a 18 mesi per il residuo puro. Difendere D+2 come *il numero giusto*
significa scegliere un punto in un intervallo largo.

L'argomento forte è un altro, ed è di **struttura, non di calibrazione**:

> Oggi la tenuta di S4 non ha né un limite superiore né un limite inferiore. La determina la densità di
> copertura giornalistica sul ticker — quante volte arriva un articolo, se ne arriva uno di terzi che
> sovrascrive il precedente, se FIX-D preserva il vecchio positivo. Questo produce simultaneamente
> churn a 1h45 e una posizione tenuta 16 sedute che perde 201,67 $ in un giorno. Sono lo stesso
> difetto: **l'orizzonte è una variabile esogena della pipeline editoriale, non una scelta**.
> Un time-stop dichiarato non ottimizza l'orizzonte: lo rende **una decisione**. Ed è la precondizione
> di qualunque misura successiva, incluso il gate IC a 2 sedute che la pre-registrazione già richiede —
> misurare l'IC a D+2 mentre la strategia esce a 1h45 misura due cose diverse.

A questo si aggiunge un argomento esterno che **non dipende dall'esistenza di alpha in S4**: quasi
tutti i guadagni azionari USA maturano overnight, con rendimento medio intraday piatto o negativo
(Glasserman et al. 2025; Lou, Polk & Skouras 2019). Una policy che tiene 1h45 intraday sta nella
finestra sbagliata **anche se il segnale fosse puro rumore**. E con turnover ben oltre il 50% mensile,
Novy-Marx & Velikov collocano S4 fuori dalla regione in cui gli anomaly sopravvivono ai costi.

Infine, D+2 è **il valore più basso difendibile** nell'intervallo della letteratura, il che lo rende
la scelta conservativa corretta: minimizza l'esposizione al reversal della news stantia documentato da
Tetlock (2011) e minimizza il capitale-giorni sottratto a S1, pur uscendo dalla trappola intraday.

### 9.2 Il miglior argomento **contro** D+2

Il migliore non è «due giorni potrebbe essere il numero sbagliato». È questo:

> **D+2 potrebbe essere una risposta corretta a una domanda irrilevante.** Didisheim, Kelly,
> Pourmohammadi & Tian (2026) mostrano che la news **grezza** è in larga parte prevedibile dalle
> caratteristiche del titolo, e che solo il residuo *pure news* ha potere predittivo grande e
> duraturo. S4 usa news grezza su una watchlist large-cap. Se la componente prevedibile domina il
> punteggio, allora S4 sta comprando — in ritardo, con costi e con un ingresso al 71°–92° percentile
> del range giornaliero — una replica rumorosa di caratteristiche che **S1 già trada**. L'overlap
> osservato con S1 non sarebbe un'inefficienza di coordinamento: sarebbe la conseguenza attesa del
> design. In quel mondo nessuna regola d'uscita salva S4, e sette settimane di shadow su D+2
> misurerebbero con grande rigore la durata ottimale di una posizione che non andava aperta.

Argomenti secondari, tutti veri e nessuno decisivo:

- **Numerosità.** La pre-registrazione richiede ~213 sedute per il gate IC; con 30 sedute al 28/09,
  la finestra utile non produce evidenza confirmatoria. `EVIDENZA ALEMBIC`: `ic_rilevabile_a_t3` a 42
  giorni vale già 0,110, il doppio della soglia registrata.
- **D+2 aumenta l'esposizione ai gap rispetto al churn intraday** — 2 estrazioni overnight invece di
  0. È vero, e va detto: rispetto alla **moda** attuale D+2 aggiunge rischio di gap; rispetto alla
  **coda** attuale lo riduce drasticamente. Il beneficio netto dipende dalla forma della distribuzione
  di tenuta, che è **U5**, un dato che non abbiamo.
- **Confound irrisolti.** Il take-profit +6% sui non-fractionable e il disaster stop broker restano
  attivi durante la misura e non sono parte della policy sotto test.

### 9.3 Verdetto

## `MODIFY`

**Cosa mantengo, senza riserve.** Il time-stop D+2 come policy primaria; il contro-segnale come unica
eccezione ordinaria; `max_signal_age` relegato a filtro d'ingresso; il clock DAILY realmente applicato;
lo shadow **end-to-end** con lo stesso codice dell'esecuzione; il congelamento del lato ingresso;
R1–R4 come gate di riattivazione del capitale.

**Cosa modifico.**

1. **Separare il test dell'uscita dal test dell'alpha.** Sono domande con varianze diverse di un ordine
   di grandezza (§6.1). Il gate IC a ~213 sedute è appropriato per decidere se **allocare capitale** a
   S4 e va lasciato intatto; è inappropriato come percorso critico per decidere **quale uscita
   spedire**. Registrare il protocollo §6–§7 separatamente, con metrica primaria = delta appaiato per
   trade e vincolo co-primario su P&L per capitale-giorno.
2. **Risolvere U1 prima di `n = 0`.** La soglia di contro-segnale è ambigua fra `−0,20` e `−0,30`. La
   mia raccomandazione è `−0,30`, per la simmetria buy/hold spread (§5.4), ma la decisione va presa,
   verificata sull'env e timestampata **prima** che parta il campione, non ricostruita dopo.
3. **Togliere il "catastrophe stop" dalla definizione della policy primaria** e retrocederlo a
   challenger separato (E5) con previsione registrata di non migliorare la media. Motivo: il replay
   interno e Lo-Remorov lo sconsigliano nella forma stretta, e l'evidenza Alembic mostra che la coda è
   arrivata via **gap**, che uno stop non intercetta (§6.6). Includerlo dentro E1 significa confondere
   il test del time-stop con il test dello stop.
4. **Neutralizzare o registrare esplicitamente i due confound di esecuzione**: il take-profit +6% sui
   non-fractionable e il fatto che la cancellazione pre-SELL non tocchi la gamba TP (**[F-C]**, **[F-D]**).
5. **Rendere `D+2` esplicitamente una tenuta MASSIMA**, non un obiettivo. La formulazione «uscita alla
   chiusura di D+2» è compatibile con l'idea sbagliata che la posizione *debba* durare due sedute.
6. **Aggiungere la decomposizione intraday/overnight** come prima richiesta di dato: è ciò che
   falsifica o conferma l'argomento esterno più forte a favore della decisione.

**Cosa NON raccomando, benché il catalogo lo permetta.** Nessun take-profit fisso. Nessun trailing.
Nessuna policy condizionata per tipo evento. Nessun de-risking parziale alla size attuale. Ognuna
consuma un trial senza una fonte primaria che la sostenga per una news-momentum long-only, e la
letteratura sulle barriere congiunte dice che non sono manopole isolabili.

### 9.4 Cosa falsificherebbe questa raccomandazione

In ordine di potere falsificante:

1. **Componente overnight media negativa sui fill di S4.** Se i rendimenti post-fill di S4, decomposti,
   mostrano overnight medio ≤ 0, il mio argomento esterno principale non si applica a questa
   popolazione e D+2 va respinto in favore di una chiusura in seduta. *Verificabile subito,
   retrospettivamente.*
2. **Delta E1′−E0 concentrato in meno di 3 trade.** Se il vantaggio di D+2 viene da uno o due eventi di
   gap, non è una policy: è una lotteria, e il segno cambierà nel campione successivo.
3. **Segno del delta che si inverte fra prima e seconda metà del campione** (G5).
4. **Distribuzione della tenuta non bimodale.** Se **U5** mostra che la coda lunga tipo WDC è un caso
   isolato e la tenuta è davvero concentrata a 1h45, l'argomento «D+2 limita l'esposizione» perde la
   sua gamba economica principale e resta solo l'argomento overnight/costi — più debole da solo.
5. **Contro-segnale che risulta il vero motore.** Se in E1′ la quasi totalità delle uscite avviene per
   contro-segnale e quasi nessuna al time-stop, allora ho classificato male la policy: sarebbe E3, e il
   D+2 sarebbe decorativo.

---

## 10. Bibliography

DOI verificati singolarmente via Crossref il 2026-08-14. `FT` = testo pieno o abstract integrale letto;
`ABS` = abstract/metadati verificati; `SNIP` = solo snippet indicizzati.

**News, sentiment, decadimento dell'informazione**

1. Ke, Z. T., Kelly, B. T., & Xiu, D. *Predicting Returns with Text Data.* NBER Working Paper 26186.
   <https://www.nber.org/papers/w26186> — `SNIP` (claim su stale/fresh news da snippet indicizzati del
   PDF NBER; il PDF non è estraibile in testo con gli strumenti a disposizione)
2. Heston, S. L., & Sinha, N. R. (2017). *News vs. Sentiment: Predicting Stock Returns from News
   Stories.* Financial Analysts Journal, 73(3), 67–83. <https://doi.org/10.2469/faj.v73.n3.3> — `ABS`.
   *Nota: il packet cita la versione FEDS 2016-048 (<https://doi.org/10.17016/FEDS.2016.048>); questa è
   la versione pubblicata e va preferita nelle citazioni.*
3. Jiang, H., Li, S. Z., & Wang, H. (2021). *Pervasive underreaction: Evidence from high-frequency
   data.* Journal of Financial Economics, 141(2), 573–599.
   <https://doi.org/10.1016/j.jfineco.2021.04.003> — `ABS`
4. Tetlock, P. C. (2007). *Giving Content to Investor Sentiment: The Role of Media in the Stock
   Market.* Journal of Finance, 62(3), 1139–1168.
   <https://doi.org/10.1111/j.1540-6261.2007.01232.x> — `ABS`
5. Tetlock, P. C., Saar-Tsechansky, M., & Macskassy, S. (2008). *More Than Words: Quantifying Language
   to Measure Firms' Fundamentals.* Journal of Finance, 63(3), 1437–1467.
   <https://doi.org/10.1111/j.1540-6261.2008.01362.x> — `ABS`
6. Tetlock, P. C. (2011). *All the News That's Fit to Reprint: Do Investors React to Stale
   Information?* Review of Financial Studies, 24(5), 1481–1512.
   <https://doi.org/10.1093/rfs/hhq141> — `ABS`
7. Chan, W. S. (2003). *Stock price reaction to news and no-news: drift and reversal after headlines.*
   Journal of Financial Economics, 70(2), 223–260.
   <https://doi.org/10.1016/S0304-405X(03)00146-6> — `ABS`
8. Boudoukh, J., Feldman, R., Kogan, S., & Richardson, M. (2019). *Information, Trading, and
   Volatility: Evidence from Firm-Specific News.* Review of Financial Studies, 32(3), 992–1033.
   <https://doi.org/10.1093/rfs/hhy083> — `ABS`
9. Jeon, Y., McCurdy, T. H., & Zhao, X. (2022). *News as sources of jumps in stock returns: Evidence
   from 21 million news articles for 9000 companies.* Journal of Financial Economics, 145(2).
   <https://doi.org/10.1016/j.jfineco.2021.08.002> — `ABS`
10. Didisheim, A., Kelly, B. T., Pourmohammadi, M., & Tian, H. (2026). *The Inefficient Pricing of
    News.* NBER Working Paper 35093 (aprile 2026, rev. maggio 2026).
    <https://www.nber.org/papers/w35093> — `ABS` (abstract letto integralmente sulla pagina NBER)
11. Lopez-Lira, A., & Tang, Y. (2025). *Can ChatGPT Forecast Stock Price Movements? Return
    Predictability and Large Language Models.* arXiv:2304.07619, v6 del 28 ottobre 2025.
    <https://arxiv.org/abs/2304.07619> — `FT` (abstract v6 letto integralmente; indicato come
    forthcoming JFE da fonti secondarie, **non verificato su fonte primaria**)
12. Hirshleifer, D., Lim, S. S., & Teoh, S. H. (2009). *Driven to Distraction: Extraneous Events and
    Underreaction to Earnings News.* Journal of Finance, 64(5), 2289–2325.
    <https://doi.org/10.1111/j.1540-6261.2009.01501.x> — `ABS`

**Overnight contro intraday**

13. Lou, D., Polk, C., & Skouras, S. (2019). *A tug of war: Overnight versus intraday expected
    returns.* Journal of Financial Economics, 134(1), 192–213.
    <https://doi.org/10.1016/j.jfineco.2019.03.011> — `ABS`. Versione autore accessibile:
    <https://personal.lse.ac.uk/polk/research/TugOfWar.pdf>
14. Glasserman, P., Krstovski, K., Laliberte, P., & Mamaysky, H. (2025). *Does Overnight News Explain
    Overnight Returns?* arXiv:2507.04481, 6 luglio 2025. <https://arxiv.org/abs/2507.04481> — `FT`
    (abstract letto integralmente)

**Costi, turnover, no-trade region**

15. Novy-Marx, R., & Velikov, M. (2016). *A Taxonomy of Anomalies and Their Trading Costs.* Review of
    Financial Studies, 29(1), 104–147. <https://doi.org/10.1093/rfs/hhv063> — `SNIP`
16. Gârleanu, N., & Pedersen, L. H. (2013). *Dynamic Trading with Predictable Returns and Transaction
    Costs.* Journal of Finance, 68(6), 2309–2340. <https://doi.org/10.1111/jofi.12080> — `ABS`
17. Davis, M. H. A., & Norman, A. R. (1990). *Portfolio Selection with Transaction Costs.* Mathematics
    of Operations Research, 15(4), 676–713. <https://doi.org/10.1287/moor.15.4.676> — `ABS`
18. Mei, X., DeMiguel, V., & Nogales, F. J. (2016). *Multiperiod portfolio optimization with multiple
    risky assets and general transaction costs.* Journal of Banking & Finance, 69, 108–120.
    <https://doi.org/10.1016/j.jbankfin.2016.04.002> — `ABS`
19. Almgren, R., & Chriss, N. (2001). *Optimal execution of portfolio transactions.* Journal of Risk,
    3(2), 5–39. <https://doi.org/10.21314/JOR.2001.041> — `ABS`

**Stop-loss, trailing, barriere**

20. Kaminski, K. M., & Lo, A. W. (2014). *When do stop-loss rules stop losses?* Journal of Financial
    Markets, 18, 183–201. <https://doi.org/10.1016/j.finmar.2013.07.001> — `FT` (abstract integrale)
21. Lo, A. W., & Remorov, A. (2017). *Stop-loss strategies with serial correlation, regime switching,
    and transaction costs.* Journal of Financial Markets, 34, 1–15.
    <https://doi.org/10.1016/j.finmar.2017.02.003> — `SNIP`
22. Dai, B., et al. (2021). *Risk reduction using trailing stop-loss rules.* International Review of
    Finance, 21(4), 1334–1352. <https://doi.org/10.1111/irfi.12328> — `ABS` (abstract integrale via
    Crossref)
23. Han, Y., Zhou, G., & Zhu, Y. *Taming Momentum Crashes: A Simple Stop-Loss Strategy.* SSRN
    <https://ssrn.com/abstract=2407199> — `SNIP`. **Working paper non peer-reviewed**; citato come
    controevidenza, non come prova
24. Arratia, A., & Dorador, A. (2019). *On the efficacy of stop-loss rules in the presence of overnight
    gaps.* Quantitative Finance, 19(11), 1857–1873.
    <https://doi.org/10.1080/14697688.2019.1605188> — `SNIP`
25. Glynn, P. W., & Iglehart, D. L. (1995). *Trading Securities Using Trailing Stops.* Management
    Science, 41(6), 1096–1106. <https://doi.org/10.1287/mnsc.41.6.1096> — `ABS`
26. Imkeller, P., & Rogers, L. C. G. (2014). *Trading to Stops.* SIAM Journal on Financial Mathematics,
    5(1), 753–781. <https://doi.org/10.1137/130911706> — `ABS`
27. Leung, T., & Li, X. (2015). *Optimal mean reversion trading with transaction costs and stop-loss
    exit.* International Journal of Theoretical and Applied Finance, 18(3), 1550020.
    <https://doi.org/10.1142/S021902491550020X> — `ABS`
28. Leung, T., & Zhang, H. (2021). *Optimal Trading with a Trailing Stop.* Applied Mathematics &
    Optimization, 83(2), 669–698. <https://doi.org/10.1007/s00245-019-09559-0> — `ABS`. Preprint:
    <https://arxiv.org/abs/1701.03960>
29. Broadie, M., Glasserman, P., & Kou, S. (1997). *A Continuity Correction for Discrete Barrier
    Options.* Mathematical Finance, 7(4), 325–349. <https://doi.org/10.1111/1467-9965.00035> — `ABS`
30. Osler, C. L. (2003). *Currency Orders and Exchange Rate Dynamics.* Journal of Finance, 58(5),
    1791–1819. <https://doi.org/10.1111/1540-6261.00588> — `ABS`
31. Osler, C. L. (2005). *Stop-loss orders and price cascades in currency markets.* Journal of
    International Money and Finance, 24(2), 219–241.
    <https://doi.org/10.1016/j.jimonfin.2004.12.002> — `ABS`

**Optimal stopping, exit su stato**

32. Vaicenavicius, J. (2020). *Asset Liquidation Under Drift Uncertainty and Regime-Switching
    Volatility.* Applied Mathematics & Optimization, 81(3), 757–784.
    <https://doi.org/10.1007/s00245-018-9518-5> — `ABS`
33. Joubert, J. F. (2022). *Meta-Labeling: Theory and Framework.* Journal of Financial Data Science,
    4(3), 31–44. <https://doi.org/10.3905/jfds.2022.1.098> — `SNIP`
34. Grądzki, P., et al. (2025). *Algorithmic crypto trading using information-driven bars, triple
    barrier labeling and deep learning.* Financial Innovation, 11(1).
    <https://doi.org/10.1186/s40854-025-00866-w> — `ABS`

**Regime e volatility management**

35. Moreira, A., & Muir, T. (2017). *Volatility-Managed Portfolios.* Journal of Finance, 72(4),
    1611–1644. <https://doi.org/10.1111/jofi.12513> — `ABS`
36. Barroso, P., & Santa-Clara, P. (2015). *Momentum has its moments.* Journal of Financial Economics,
    116(1), 111–120. <https://doi.org/10.1016/j.jfineco.2014.11.010> — `ABS`
37. Cederburg, S., O'Doherty, M. S., Wang, F., & Yan, X. S. (2020). *On the performance of
    volatility-managed portfolios.* Journal of Financial Economics, 138(1), 95–117.
    <https://doi.org/10.1016/j.jfineco.2020.04.015> — `ABS`
38. DeMiguel, V., Martin-Utrera, A., & Uppal, R. (2024). *A Multifactor Perspective on
    Volatility-Managed Portfolios.* Journal of Finance, 79(6), 3859–3891.
    <https://doi.org/10.1111/jofi.13395> — `ABS`

**Validazione, data snooping, decadimento degli anomaly**

39. White, H. (2000). *A Reality Check for Data Snooping.* Econometrica, 68(5), 1097–1126.
    <https://doi.org/10.1111/1468-0262.00152> — `ABS`
40. Hansen, P. R. (2005). *A Test for Superior Predictive Ability.* Journal of Business & Economic
    Statistics, 23(4), 365–380. <https://doi.org/10.1198/073500105000000063> — `ABS`
41. Sullivan, R., Timmermann, A., & White, H. (1999). *Data-Snooping, Technical Trading Rule
    Performance, and the Bootstrap.* Journal of Finance, 54(5), 1647–1691.
    <https://doi.org/10.1111/0022-1082.00163> — `ABS`
42. Bajgrowicz, P., & Scaillet, O. (2012). *Technical trading revisited: False discoveries, persistence
    tests, and transaction costs.* Journal of Financial Economics, 106(3), 473–491.
    <https://doi.org/10.1016/j.jfineco.2012.06.001> — `ABS`
43. Brock, W., Lakonishok, J., & LeBaron, B. (1992). *Simple Technical Trading Rules and the Stochastic
    Properties of Stock Returns.* Journal of Finance, 47(5), 1731–1764.
    <https://doi.org/10.1111/j.1540-6261.1992.tb04681.x> — `ABS`
44. Bailey, D. H., & López de Prado, M. (2014). *The Deflated Sharpe Ratio.* Journal of Portfolio
    Management, 40(5), 94–107. <https://doi.org/10.3905/jpm.2014.40.5.094> — `ABS`. Versione autore:
    <https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf>
45. Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2016). *The probability of backtest
    overfitting.* Journal of Computational Finance. <https://doi.org/10.21314/JCF.2016.322> — `ABS`
46. Harvey, C. R., & Liu, Y. (2015). *Backtesting.* Journal of Portfolio Management, 42(1), 13–28.
    <https://doi.org/10.3905/jpm.2015.42.1.013> — `ABS`
47. Harvey, C. R., & Liu, Y. (2014). *Evaluating Trading Strategies.* Journal of Portfolio Management,
    40(5), 108–118. <https://doi.org/10.3905/jpm.2014.40.5.108> — `ABS`
48. Harvey, C. R., Liu, Y., & Zhu, H. (2016). *… and the Cross-Section of Expected Returns.* Review of
    Financial Studies, 29(1), 5–68. <https://doi.org/10.1093/rfs/hhv059> — `ABS`
49. McLean, R. D., & Pontiff, J. (2016). *Does Academic Research Destroy Stock Return Predictability?*
    Journal of Finance, 71(1), 5–32. <https://doi.org/10.1111/jofi.12365> — `ABS`

**Fonti Alembic usate come evidenza interna** (non letteratura)

`src/strategies/s4/{config,ranking,strategy}.py` · `src/portfolio/{exit_classification,stop_policy,fractional_stop_orders}.py` ·
`src/workers/portfolio_scheduler.py` · `src/config.py` · `config/trading.yaml` ·
`docs/evidence/s4_ic.json` (generato 2026-08-14T06:44Z, 42 giorni, 2396 osservazioni symbol-day) ·
`docs/evidence/economic_pnl.json` (generato 2026-08-14, finestra 08-03→08-12) ·
`docs/stop_loss_calibration_handback_2026-07-15.md` §3.1 e §5 ·
`docs/ALPHA_MISS_REPORT_2026-08-{06,10,12}.md`. Tutti letti al commit `d7599cf`.

---

### Nota finale

Ogni proposta di questo documento ha una condizione di falsificazione dichiarata (§7 "Previsioni
registrate", §9.4). La raccomandazione più forte non è "D+2 è il numero giusto" — non lo so, e la
letteratura non lo consegna. È che **l'orizzonte di S4 oggi è una variabile della pipeline editoriale
e non una decisione**, e che questo va corretto prima di poter misurare qualunque altra cosa. Se la
decomposizione intraday/overnight richiesta in §8.2 dovesse mostrare componente overnight negativa sui
fill di S4, questa raccomandazione va scartata: sarebbe la prova che il problema di S4 sta a monte
dell'uscita, e nessuna regola di uscita lo risolve.
