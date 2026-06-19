# OPUS_QUANT_TRADING_VALIDITY_MEMO

> **Passata 2 di 5** — Quant / Trading Validity Memo
> Ruolo: Head of Quant Research + skeptical strategy reviewer + backtest contamination auditor + falsification-first researcher.
> Modalità: **read-only**. Nessun file modificato, nessun codice/patch/commit, nessun backtest/pipeline/worker/ordine eseguito. Unico artefatto prodotto: questo memo.
> Fonti: `docs/FUNCTIONAL_QUANT_PRODUCT_REVIEW_2026-06-17.md`, `docs/OPUS_FUNCTIONAL_REMEDIATION_BLUEPRINT_2026-06-18.md`, e ispezione diretta read-only del codice quant/backtest (file:line citati).
> Data: 2026-06-18.

**Premessa metodologica.** Questo memo non è una code review né un elenco di bug. È un giudizio quant: *questi risultati dimostrano edge o sono artefatti?* Ogni claim di contaminazione qui sotto è stato **verificato direttamente nel codice** (non ereditato dalla red-team su fiducia). Dove la red-team della Passata 0 era imprecisa, lo segnalo esplicitamente — un auditor quant deve correggere anche gli alleati. Costo del falso positivo assunto alto: in dubbio, una strategia resta R&D.

**Evidenza primaria verificata (file:line):**
- `src/backtest/engine/orchestrator.py:85-101` — fill alla stessa barra del segnale.
- `src/backtest/engine/data_replay.py:56-90` — `market_at` usa il close di `as_of`; `prices_until` include `as_of`.
- `src/backtest/costs/realistic.py:51` + `data_replay.py:38-45` — ADV default costante 10M se i volumi non sono passati → impatto ≈ 0.
- `src/backtest/walkforward/runner.py:102-116` — "walk-forward" senza fitting su IS (strategia precomputata).
- `src/backtest/gates/runner.py:20` — `n_trials = 1` (DSR senza deflazione multipla).
- `src/backtest/gates/gate_2_walkforward.py:51-56` — denominatore esclude finestre no-trade.
- `src/strategies/s1/backtest.py:183-197` — stress = ±15gg attorno al worst-drawdown **dentro l'OOS** (circolare).
- `src/strategies/s1/backtest.py:167-180` — regime split via mediana **full-OOS** (hindsight), solo 2 regimi vol.
- `src/backtest/gates/gate_4_regime.py:42` — clamp silenzioso `min_passing_regimes` 3→2.
- `src/backtest/data/universe.py:36` — `active_at()` esiste ma **non è chiamato** dal path S1 (`s1/backtest.py:211-216`); `screen()` usa "Adj Close".
- `src/strategies/s3/strategy.py:88` — `self._vol = ...rolling(...).std().iloc[-1]`: vol end-of-sample applicata a tutti i ribilanciamenti → **lookahead full-sample nel sizing**.
- `src/strategies/s2/signal.py:66,80` — chain di opzioni **sintetiche** (`OptionChainDataLoader.generate_chain`, underlying default 450) → backtest VRP non informativo.
- `src/strategies/s7/strategy.py` — nessun `__call__`, consuma `SurpriseSignal` da pipeline EDGAR/LLM rotta → nessun backtest.

---

## 1. Executive Summary

Dal punto di vista quant, **nessuna strategia di Alembic ha oggi un claim di edge difendibile**, inclusa l'unica in live (S1). Il problema non è che gli alpha siano falsi: è che **la validazione non valida**. La pipeline di gate che certifica S1 "5/5" contiene contaminazioni confermate nel codice: esecuzione *same-bar* (si decide e si riempie allo stesso close), universo *survivorship-contaminated* (i 15 ETF attuali proiettati all'indietro; `active_at` esiste ma non è usato), *adjusted-close* come prezzo eseguibile, modello costi con *impatto ≈ 0* (ADV costante 10M) e *costo fisso $1440/anno ignorato*, "walk-forward" *senza fitting* (etichetta decorativa), DSR con *n_trials=1* (nessuna correzione per le 40+ combinazioni esplorate), *stress circolare* (la peggiore finestra dentro l'OOS, non 2008/2020/2022), *regime split con hindsight* su sole 2 fasce di volatilità, e *denominatore Gate 2* che esclude le finestre no-trade.

S1 (time-series momentum) ha una **tesi economica solida** ma un OOS *marginale* (t≈2.04 pre-correzione, ~post-2014 bull) che, sottoposto a t+1 + costi reali + survivorship-free + correzione multipla, ha alta probabilità di scendere sotto soglia — il che sarebbe il risultato corretto. S2 (VRP) gira su **option chain sintetiche**: il −0.55 non dice nulla sul VRP reale → *non valutabile*. S3 (residual momentum) ha un **lookahead confermato nel sizing** (vol end-of-sample): il segnale è sano ma il numero riportato è contaminato. S4 (news/LLM) **non ha alcuno studio IC** e il gate report è ineseguibile → *non valutabile*. S7 (PEAD) non ha `__call__`, non ha backtest, ha input rotti → *non valutabile*.

**Verdetto quant: Research-only.** S1 al 50% live non è quant-giustificato. La priorità non è nuovo alpha: è rendere onesta e riproducibile la validazione di S1, poi falsificare il resto.

---

## 2. Quant Verdict

**Classificazione: RESEARCH-ONLY.**

Motivazione: il backtest, come oggi costruito, **non è un meccanismo di validazione affidabile** per nessuna strategia. Le contaminazioni non sono ipotesi ma fatti verificati nel codice, e colpiscono il *cuore* delle decisioni di promozione (timing del fill, universo, costi, correzione multipla, stress). Di conseguenza:

- Non "Early paper candidate": un paper basato su segnali la cui validità è ignota non produce evidenza interpretabile, solo P&L rumoroso. Paper è *osservazione*, non *validazione*; va bene per osservare l'esecuzione, non per inferire edge.
- Non "Paper-ready after fixes" come stato di sistema: alcuni fix (es. S3 sizing) sono prerequisiti, ma persino dopo i fix l'edge va *ri-dimostrato*, non assunto.
- Emphatically non "Live-candidate": l'unica strategia live (S1) poggia su gate contaminati; il suo Sharpe è marginale anche prima di correggere il timing e i costi.

Il sistema è **Research-only**: ha l'infrastruttura per fare ricerca quant seria (gate, walk-forward, cost model, forward-returns IC) ma la usa in modo che produce **falsa conferma**. La requalificazione di ogni strategia richiede prima la bonifica della validazione (Passata 1 RB-008/009/010) e poi un ri-test di falsificazione.

---

## 3. Strategy-by-Strategy Verdict

| Strategy | Tesi economica | Alpha plausibility | Validation quality | Main contamination risk | Recommended status | Falsification obbligatoria |
|---|---|---|---|---|---|---|
| **S1** TS-Momentum | Solida (TSMOM documentato) | **Plausible but unproven** | Bassa (gate contaminati) | Same-bar + survivorship + costi ≈0 + DSR n_trials=1 | **Revalidate before paper** | t+1, costi reali+fisso, survivorship-free, SPA |
| **S2** VRP | Solida (VRP premia robusto) | **Not evaluable** (dati sintetici) | Nulla (chain sintetiche) | Synthetic option data; segno −0.55 artefatto | **R&D only / Disabled** | Real option data, segno/payoff, stress tail |
| **S3** Cross-sec residual mom | Plausibile (residual mom) | **Fragile / unproven** | Bassa (lookahead sizing) | **Lookahead full-sample nel sizing** + survivorship | **R&D only** | Sizing PIT (t-1), survivorship-free, rank stability |
| **S4** News/LLM | Debole-plausibile (news drift, thin) | **Not evaluable** (nessun IC) | Nulla (gate rotto, no IC study) | Timestamp PIT? rumore LLM? costi single-name | **Paper only (contenuto), promozione bloccata** | Shuffled-news, placebo, IC decay, timestamp perm |
| **S7** PEAD | Solida (PEAD documentato) | **Not evaluable** (no backtest) | Nulla (no `__call__`, input rotti) | EDGAR metadata-only, consensus allucinato, survivorship | **R&D only / Disabled** | Consensus PIT esterno, filing body, event study |

### S1 — Time-Series Momentum Multi-Asset
- **Stato attuale dichiarato:** live 50%, "5/5 gate, OOS Sharpe ~0.51".
- **Tesi economica:** time-series/trend momentum multi-asset con vol targeting — uno degli anomaly più documentati (Moskowitz-Ooi-Pedersen). *Nota di precisione:* l'implementazione è in realtà un **momentum cross-sezionale z-scored** su 15 ETF (`signal.py:75-92`), long-only (`signal_threshold=0.0`), ribilanciato **mensile** — un ibrido tra TSMOM e cross-sectional, non TSMOM puro. La tesi resta plausibile ma l'etichetta è imprecisa.
- **Plausibilità:** **Plausible but unproven.**
- **Qualità della validazione:** bassa. Vedi §4 per il dettaglio; in sintesi ogni gate è alimentato da input contaminati o privi di correzione.
- **Contaminazioni confermate:**
  - *Same-bar execution* (`orchestrator.py:92-96` + `data_replay.py:57`): segnale a close[t], fill a close[t]. *Calibrazione quant:* con ribilanciamento **mensile** l'errore same-bar è ~1 gap overnight per mese, non per giorno → l'inflazione è **reale ma limitata**, meno catastrofica di quanto la red-team suggerisse per una strategia daily. Va comunque quantificata (test t+1).
  - *Survivorship* (`universe.py:36` `active_at` non usato; `signal.py:71-72` richiede tutti i ticker validi): OOS effettivo ~post-2014, regime quasi interamente bull. **Questo, non il same-bar, è probabilmente il bias dominante.**
  - *Adjusted-close come fill* (`universe.py:67`, loader): prezzo back-adjusted non tradable; parte del "rendimento" è dividendo riportato all'indietro.
  - *Costi ≈ 0* (`realistic.py:51`, ADV costante 10M) + *fisso $1440/anno escluso*: su $100k il solo fisso è 1.44%/anno — su un sleeve a 10% vol target con rendimento annuo modesto, può **dimezzare o azzerare** il net Sharpe.
  - *Walk-forward decorativo* (`runner.py:102-116`): nessun parametro stimato su IS; è una rolling-OOS di parametri fissi → non misura degrado out-of-sample.
  - *DSR n_trials=1* (`runner.py:20`): 40 combo sensitivity + 3 perturbazioni + più strategie esplorate, ma deflazione per 1 solo trial → DSR>0.5 privo di significato come correzione multipla.
- **Failure modes:** momentum crash (reversal violenti post-bear); dipendenza da un singolo regime bull; erosione da costi/turnover; gap overnight non modellato.
- **Cosa la invaliderebbe:** OOS Sharpe <0.5 (o non significativo dopo SPA) una volta applicati t+1 + costi reali+fisso + universo survivorship-free + raw close.
- **Test di falsificazione obbligatori:** vedi §6 (S1-F1…S1-F8).
- **Metriche minime da richiedere:** net Sharpe post-costi-reali-e-fissi; turnover; numero di anni OOS e quanti di bear vero; DSR con n_trials reale; Sharpe same-bar vs t+1 (costo di realismo); drawdown per regime causale.
- **Stato quant consigliato:** **Revalidate before paper.**
- **Raccomandazione finale:** demuovere da live; nessuna ripromozione finché il 0.51 non sopravvive al protocollo §6 con riproducibilità. È l'unico candidato con tesi seria — merita di essere *falsificato per bene*, non promosso per fiducia.

### S2 — Volatility Risk Premium
- **Stato attuale dichiarato:** disabled 0%, "all gates failed, OOS −0.55".
- **Tesi economica:** vendita di volatilità / variance risk premium (cash-secured SPY puts). Premia robusto e documentato.
- **Plausibilità:** **Not evaluable.** *Correzione alla Passata 0:* il −0.55 **non** rende il VRP "probable false alpha". Il backtest S2 gira su **option chain sintetiche** (`s2/signal.py:66,80` `OptionChainDataLoader.generate_chain`, underlying default 450, greeks da modello). Un backtest VRP su catene sintetiche misura il modello generatore, non il mercato → **non informativo in nessuna direzione**.
- **Qualità della validazione:** nulla (dati non reali).
- **Contaminazioni:** synthetic option data (la più grave); il segno negativo è quasi certamente un artefatto della generazione sintetica (IV/RV, spread, assignment non realistici).
- **Failure modes (del VRP reale, non testati qui):** tail risk asimmetrico (Volmageddon 2018, COVID 2020); assignment/early exercise; bid-ask e margin reali.
- **Cosa la invaliderebbe:** con **dati storici reali** di opzioni, un VRP net-of-cost negativo o un Sortino/CVaR inaccettabile.
- **Test di falsificazione obbligatori:** vedi §6 (S2-F1…S2-F4) — tutti richiedono dati opzioni reali.
- **Stato quant consigliato:** **R&D only / Disabled.**
- **Raccomandazione finale:** mantenere disabled; **non archiviare il VRP come falso alpha** — semplicemente non è stato testato. Nessun lavoro su S2 finché non esistono dati opzioni reali storici.

### S3 — Cross-Sectional Residual Momentum
- **Stato attuale dichiarato:** disabled 0%, "gate 3/5 falliti, sospetto sizing lookahead".
- **Tesi economica:** residual momentum (ritorno al netto del beta di mercato), long top decile / short bottom decile. Documentato (Blitz-Huij-Martens) come meno affollato e de-correlato dal momentum raw.
- **Plausibilità:** **Fragile / plausible but unproven.**
- **Qualità della validazione:** bassa per via di un lookahead confermato.
- **Contaminazioni confermate:**
  - *Lookahead full-sample nel sizing* (`s3/strategy.py:88`): `self._vol = daily_rets.rolling(beta_window).std().iloc[-1]` calcola la vol e prende **l'ultima riga** (fine campione), poi la usa come scalare per dimensionare **tutte** le posizioni storiche. Non è "sospetto": è un lookahead pieno. *Però è nel SIZING, non nel segnale* — il segnale residual-momentum (`signal.py:60-68`, `shift(lookback)` + beta rolling) è backward-looking e sano.
  - *Survivorship*: usa i single-name attuali; nessun universo PIT/delisting.
  - *Same-bar* + adjusted-close come per S1.
- **"Il bug è l'alpha?"** Qui **probabilmente no**: poiché il lookahead è nel dimensionamento e non nella direzione, rimuoverlo (vol PIT a t-1) cambia i pesi ma non distrugge necessariamente il ranking cross-sezionale. L'edge *potrebbe* sopravvivere — ma il 0.15 riportato è inattendibile e va buttato.
- **Failure modes:** crowding del momentum; instabilità del rank cross-sezionale; costi su single-name; neutralizzazione settoriale mancante.
- **Cosa la invaliderebbe:** con sizing PIT + universo survivorship-free, OOS non significativo o rank instability elevata.
- **Test di falsificazione obbligatori:** vedi §6 (S3-F1…S3-F5).
- **Stato quant consigliato:** **R&D only.**
- **Raccomandazione finale:** mantenere disabled; **prima** rimuovere il lookahead di sizing (vol PIT) e l'universo survivorship-free, **poi** decidere se c'è un segnale. Non riabilitare su numeri attuali.

### S4 — News-Driven Tactical LLM
- **Stato attuale dichiarato:** paper 10%, "capped until gate report" (gate report ineseguibile, D-02).
- **Tesi economica:** drift da news/sentiment su orizzonti brevi. Plausibile *in principio*, ma è un alpha **thin** (sottile), rumoroso, costoso su single-name e particolarmente esposto a look-ahead via timestamp delle news.
- **Plausibilità:** **Not evaluable.** Non esiste alcuno **studio IC** citato in doc o prodotto dal codice; l'infrastruttura forward-returns (`forward_returns.py`) è metodologicamente pulita (anchor al primo bar ≥ ts, nessuna interpolazione, return 24h = close giorno+1/close giorno) ma **nessun risultato IC è disponibile** e il gate report S4 non gira.
- **Qualità della validazione:** nulla (gate rotto, nessun IC).
- **Contaminazioni / rischi:**
  - *Timestamp PIT non verificato:* il backtest filtra `generated_at <= ts` (`s4/strategy.py:148`), point-in-time **rispetto all'istante di generazione del segnale** — ma se `generated_at` è il tempo di *scoring* anziché di *pubblicazione* della news, o se la news anticipa il movimento, c'è look-ahead. Da verificare a monte (ingestion).
  - *Accumulo segnali stale:* `_signals_as_of` ritorna **tutti** i segnali con `generated_at <= ts` senza finestra di recency (`s4/strategy.py:142-163`) → il ranker può mescolare sentiment vecchi e nuovi. Rischio di segnale degradato.
  - *Rumore LLM / diversità ensemble fittizia:* modelli della stessa epoca tendono a correlare; "ensemble variance" può essere un singolo modello travestito.
  - *Costi single-name + same-bar.*
- **Failure modes:** segnale = rumore LLM con bell'aspetto in-sample; duplicazione news; manipolazione; fallback deterministico proprio nei momenti di stress.
- **Cosa la invaliderebbe:** IC ≈ 0 o non distinguibile dal placebo (shuffled-news); edge che svanisce net-of-cost; IC che collassa con timestamp PIT corretti.
- **Test di falsificazione obbligatori:** vedi §6 (S4-F1…S4-F8) — **placebo e shuffled-news sono non-negoziabili** prima di qualunque claim.
- **Metriche minime:** IC (e IC decay) per orizzonte, net-of-cost; hit rate; correlazione tra modelli dell'ensemble; rejection rate del supervisor; turnover/costi.
- **Stato quant consigliato:** **Paper only (contenuto), promozione bloccata.** Il paper qui serve solo a osservare esecuzione e qualità segnale, non come prova di edge.
- **Raccomandazione finale:** nessuna promozione finché non esiste un IC study che batte il placebo net-of-cost e con timestamp PIT verificati.

### S7 — PEAD
- **Stato attuale dichiarato:** roadmap "done"; realtà: non cablato, no `__call__`, EDGAR metadata-only, consensus allucinabile, no consumer.
- **Tesi economica:** post-earnings announcement drift — anomaly robusta e documentata (sotto-reazione agli earnings surprise).
- **Plausibilità:** **Not evaluable.** `s7/strategy.py` ha `compute_target_weights` ma **nessun `__call__`** → incompatibile col motore di backtest; consuma `SurpriseSignal` da una pipeline rotta (EDGAR solo metadati, consensus EPS chiesto all'LLM = allucinabile). **Non esiste un backtest S7.**
- **Qualità della validazione:** nulla.
- **Contaminazioni (anche a pipeline riparata):** survivorship sulle aziende che battono *e* sopravvivono; microstruttura/spread sui nomi meno liquidi; timing dell'entry post-earnings (drift già prezzato?); consensus look-ahead se non strettamente PIT.
- **Cosa la invaliderebbe:** con consensus PIT esterno + filing body reale + universo survivorship-free, drift non significativo net-of-cost.
- **Test di falsificazione obbligatori:** vedi §6 (S7-F1…S7-F5).
- **Stato quant consigliato:** **R&D only / Disabled** + rimozione dalla superficie operativa (coerente con Passata 1 RB-011).
- **Raccomandazione finale:** non candidabile; serve prima un consensus EPS *esterno point-in-time* (Refinitiv/Estimize/Bloomberg) — collo di bottiglia reale — poi un event study, poi un backtest.

---

## 4. Backtest Validity Audit

### 4.1 Timing del segnale → **BROKEN (same-bar)**
- **Verdict:** il sistema decide a `close[t]` (`data_replay.market_at` usa il close, `prices_until(ts)` include t) e **riempie a `close[t]`** (`orchestrator.py:96` `simulate_fill(order, market)` con lo stesso `market`).
- **Rischio:** Sharpe ottimistico; il gap overnight (rischio dominante del momentum) non è mai sostenuto.
- **Cosa può invalidare:** se la differenza Sharpe same-bar vs t+1 è grande, ogni decisione di promozione cambia.
- **Test richiesto:** rifill a `open[t+1]` (o `close[t+1]`) con gap; riportare il "costo di realismo".
- **Calibrazione:** S1/S3 ribilanciano **mensile** → l'errore è ~1 gap/mese, **materiale ma non enorme**. S4 (settimanale/giornaliero) è più esposto.
- **Priorità:** P0.

### 4.2 Lookahead e leakage → **MIXED**
- *DataReplay* (`prices_until <= as_of`): nessun dato **futuro** nel segnale — corretto in linea di principio.
- *Segnale S1* (momentum `shift(lb)`, vol rolling, z-score cross-sez): backward-looking — OK.
- *Sizing S3* (`strategy.py:88` `.iloc[-1]`): **lookahead full-sample confermato.** P0.
- *Regime split S1* (`backtest.py:169` mediana full-OOS): **hindsight** nella definizione del regime. P1.
- *Stress S1* (`backtest.py:192` idxmin su tutto l'OOS): **hindsight** nella scelta della finestra. P1.
- *News S4*: timestamp `generated_at` PIT rispetto alla generazione, ma **publish-time non verificato** → possibile leakage a monte. Da verificare (tecnica).
- **Priorità:** P0 (S3), P1 (regime/stress hindsight), verifica tecnica (S4).

### 4.3 Stress test → **MISLEADING (circolare)**
- **Verdict:** `_extract_stress_periods` (`s1/backtest.py:183-197`) prende ±15gg attorno al **worst drawdown dentro l'OOS** e lo passa a `gate_5_stress` come unico "periodo". *La logica del gate (`gate_5_stress.py`) è sana* (si aspetta chiavi tipo `2008_gfc`, soglie cumret>-10%/mdd>-30%), ma **l'input è circolare** e l'universo ETF non ha dati nel 2008. → Lo "stress" è già dentro il campione che genera lo Sharpe.
- **Rischio:** falsa rassicurazione di sopravvivenza a crisi mai testate.
- **Test richiesto:** finestre storiche fisse 2008/2020/2022 su universo esistente allora; se i segnali non esistono, etichettare "non testabile" (non PASS).
- **Priorità:** P0.

### 4.4 Walk-forward e OOS → **MISLEADING (decorativo) + OOS troppo bull**
- **Verdict:** `WalkForwardRunner` (`runner.py:102-116`) slicea finestre IS+OOS ma la strategia è **precomputata a parametri fissi**: nessuna stima su IS → nessun test di degrado OOS reale. L'etichetta "walk-forward" sovrastima il rigore. Inoltre l'OOS effettivo è ~post-2014 (survivorship) → quasi tutto bull; t-stat ~2.04 pre-correzione.
- **Rischio:** si crede di avere robustezza out-of-sample che non è stata testata.
- **Test richiesto:** walk-forward con fitting reale su IS → test su OOS; contare anni OOS e regimi bear veri.
- **Priorità:** P0/P1.

### 4.5 Robustness / sensitivity → **USEFUL BUT INSUFFICIENT (con precisazione)**
- *Correzione alla Passata 0:* il **Gate 3** (`gate_3_robustness.py`) **non** sceglie il max di una grid — calcola il **coefficiente di variazione** di sole **3 perturbazioni** (`s1/backtest.py:142-146`) e passa se CV ≤ 0.5. È debole per ragioni diverse: 3 punti sono troppo pochi per stimare un CV; le perturbazioni sono arbitrarie; e un CV basso può semplicemente significare "uniformemente positivo in un bull market", non robustezza.
- *Separatamente,* il **report di sensitivity** (`sensitivity.py:154` `max_sharpe = lv.max().max()` + "NEAR-OPTIMUM") fa esattamente data-snooping framing su 40 combo, ed è ciò che il frontend colora — selection bias *esposto in UI*, ma **non è il gate**.
- **Manca:** correzione per confronti multipli (White Reality Check / Hansen SPA) sulle 40 combo + perturbazioni + strategie.
- **Test richiesto:** SPA/White sul set completo di combinazioni provate; reportare p-value corretto.
- **Priorità:** P0.

### 4.6 Cost model → **BROKEN in pratica**
- **Verdict:** struttura corretta (spread a tier + square-root impact + fee SEC/FINRA) ma **degenerata**: `adv_shares = market.adv_20d.get(symbol, 10_000_000)` e `DataReplay` mette ADV costante 10M quando i volumi non sono passati (il path sensitivity/WF costruisce `DataReplay(prices)` **senza volumi**) → impatto ≈ 0. Commissione default 0; fee trascurabili. → costo effettivo ≈ mezzo spread. Il **fisso $1440/anno non è nel backtest**.
- **Rischio:** Sharpe pre-costi-reali; su conto piccolo il fisso da solo è un drag enorme.
- **Test richiesto:** ADV storico reale nel cost model; fisso annuo nel net-Sharpe; sensitività turnover×costo.
- **Priorità:** P0.

### 4.7 Execution realism → **NON modellato (parità BT↔live assente)**
- **Verdict:** il backtest non modella kill-switch, stop-loss, partial fill, reject, pending/duplicate-BUY, calendario, slippage live. Il live (Passata 1, T4/T5) ha buchi opposti. → **backtest e live non misurano la stessa cosa.**
- **Rischio:** P&L live sistematicamente sotto il backtest.
- **Test richiesto:** parità BT↔live (kill-switch modellato o risultati etichettati "pre-risk-control"); metrica divergenza paper-live ≥90gg.
- **Priorità:** P0 (parità) / P1 (divergenza).

---

## 5. Validation Gates Review

| Gate | Cosa dovrebbe dimostrare | Cosa dimostra davvero | Assunzioni / dove fallisce | Classificazione | Sufficiente paper? | Sufficiente live? |
|---|---|---|---|---|---|---|
| **G1 Significance** | SR>0 significativo, deflazionato per ricerca | SR>0 con p asintotico; **DSR senza deflazione** (`n_trials=1`) nonostante 40+ combo | Normalità asintotica; n_trials reale ignorato | **Misleading as designed** | No | No |
| **G2 Walk-forward** | Consistenza OOS su finestre | Aggrega OOS concatenato; **denominatore esclude no-trade windows** (0.48→0.75) | Finestre "attive" arbitrarie; pochi window attivi | **Useful but insufficient** | Borderline | No |
| **G3 Robustness** | Stabilità sotto perturbazione | CV di **sole 3** perturbazioni ≤0.5 | 3 punti troppo pochi; nessuna SPA; CV basso = uniformemente bull | **Useful but insufficient** | No | No |
| **G4 Regime** | Tenuta in bull/bear/sideways | 2 fasce vol da **mediana full-OOS** (hindsight); **clamp 3→2** | Nessun bear vero; hindsight nel split | **Misleading as designed** | No | No |
| **G5 Stress** | Sopravvivenza a 2008/2020/2022 | **Worst-DD ±15gg dentro l'OOS** (circolare); 2008 inesistente nell'universo | Input circolare; universo post-2010 | **Broken** | No | No |
| **Gate S4** | Edge news/LLM (IC, decay) | **Ineseguibile** (script rotto, D-02); nessun IC | — | **Broken** | No | No |
| **Gate S7** | Edge PEAD | Inesistente (no `__call__`, no backtest) | — | **Not evaluable** | No | No |

*Nota di design (vale per tutti):* i gate **logici** (G1 p-value, G3 CV, G5 soglie cumret/mdd) sono in sé ragionevoli. Il problema è **cosa li alimenta** (n_trials=1, 3 perturbazioni, regime hindsight, stress circolare) e **l'assenza di correzione multipla**. Riparare gli script senza riparare *gli input e il design statistico* darebbe ancora falsa conferma (→ Passata 1 RB-009 "non eseguire lo script così com'è").

---

## 6. Alpha Falsification Plan

Per ogni test: scopo · H0 · criterio di PASS · significato del fallimento · dati · priorità · bloccante per paper/live.

### S1
- **S1-F1 t+1 execution test.** Scopo: misurare l'inflazione same-bar. H0: Sharpe t+1 = Sharpe same-bar. PASS: Sharpe t+1 resta ≥0.5 e significativo. Fallire = il numero era artefatto di timing. Dati: open/close esistenti. **P0, bloccante live.**
- **S1-F2 costi reali + fisso.** Scopo: net Sharpe onesto. H0: net = gross. PASS: net (ADV reale + $1440) ≥0.5. Fallire = edge cost-fragile. Dati: ADV storico. **P0, bloccante live.**
- **S1-F3 universo survivorship-free PIT.** Scopo: rimuovere selection bias. H0: PIT = full-sample. PASS: SR sopravvive con `active_at` + delisting. Fallire = era survivorship. Dati: inception/delisting. **P0, bloccante paper.**
- **S1-F4 raw close + dividendi espliciti.** Scopo: prezzo tradable. PASS: total return ricostruito ≈ adjusted. Fallire = parte del rendimento era dividendo riportato indietro. **P1.**
- **S1-F5 stress storico reale (2008/2020/2022).** Scopo: stress non circolare. PASS: sopravvive su universo esistente allora, o "non testabile" onesto. Fallire = stress fittizio. **P0, bloccante live.**
- **S1-F6 correzione multipla (White/Hansen SPA).** Scopo: deflazione per le 40+ combo. H0: il near-optimum non sopravvive. PASS: SR sopravvive a SPA. Fallire = data snooping. **P0, bloccante live.**
- **S1-F7 random/shuffled-signal baseline.** Scopo: quanto rende il "niente". PASS: la strategia batte nettamente segnali shuffle/random a parità di vol target e costi. Fallire = il vol-targeting+universo bull spiega tutto. **P1.**
- **S1-F8 regime split causale.** Scopo: niente hindsight. PASS: tenuta in bear *vero* con regime rolling causale. **P1.**

### S2 (tutti richiedono dati opzioni reali storici → prerequisito)
- **S2-F1 real-data sign/payoff.** H0: VRP ≤0 net. PASS: VRP>0 net su chain reali. Fallire = falso alpha reale. **P1 (dopo dati).**
- **S2-F2 tail stress (2018 Volmageddon, 2020).** PASS: CVaR/Sortino accettabili. Fallire = il premia è compensation per tail. **P0 per S2, bloccante.**
- **S2-F3 bid-ask/margin/assignment realism.** PASS: edge sopravvive a spread e assignment reali. **P1.**
- **S2-F4 benchmark coerente (es. PUT/short-vol index).** PASS: batte il benchmark passivo short-vol. **P2.**

### S3
- **S3-F1 sizing PIT (vol t-1).** Scopo: rimuovere il lookahead full-sample. H0: con vol PIT, il 0.15 sparisce. PASS: SR sopravvive con vol causale. **P0, bloccante.**
- **S3-F2 survivorship-free universe.** PASS: SR su universo PIT/delisting. **P0, bloccante paper.**
- **S3-F3 cross-sectional rank stability.** Scopo: stabilità del ranking. PASS: rank IC stabile nel tempo. **P1.**
- **S3-F4 sector/industry neutralization.** Scopo: non è solo bet settoriale. PASS: edge persiste neutralizzato. **P1.**
- **S3-F5 post-cost turnover sensitivity.** PASS: net-of-cost positivo a turnover reale. **P1.**

### S4
- **S4-F1 shuffled-news / placebo.** Scopo: il sentiment porta info? H0: news shuffle = news vere. PASS: IC vere ≫ IC shuffle. Fallire = rumore. **P0, bloccante (anche per paper "decisionale").**
- **S4-F2 timestamp permutation / publish-time PIT.** Scopo: niente look-ahead da timestamp. PASS: IC stabile con publish-time reale. Fallire = leakage. **P0.**
- **S4-F3 IC decay per orizzonte.** Scopo: l'edge è tradable? PASS: IC>0 e persistente net-of-cost a 24h. **P0.**
- **S4-F4 same-day vs next-day signal.** Scopo: il segnale anticipa o insegue? **P1.**
- **S4-F5 duplicate-news stress.** Scopo: dedup. PASS: IC stabile con dedup. **P1.**
- **S4-F6 model disagreement / single-model dominance / ensemble correlation.** Scopo: diversità reale. PASS: ensemble riduce variance vs singolo. **P1.**
- **S4-F7 event study attorno ai segnali.** Scopo: drift reale. **P1.**
- **S4-F8 paper/live comparison.** Scopo: slippage/fill su single-name. **P1 (dopo paper).**

### S7 (richiedono pipeline riparata → prerequisito)
- **S7-F1 EDGAR content validity.** PASS: il body 8-K reale arriva all'estrazione. Bloccante per qualunque test. **P0 per S7.**
- **S7-F2 consensus EPS point-in-time esterno.** PASS: consensus da fonte esterna PIT, non LLM. Bloccante. **P0 per S7.**
- **S7-F3 earnings calendar PIT.** PASS: date annuncio PIT. **P1.**
- **S7-F4 survivorship-free universe + event-window.** PASS: drift su universo esistente allora. **P0 per S7.**
- **S7-F5 PEAD benchmark comparison.** PASS: batte un PEAD passivo documentato net-of-cost. **P2.**

---

## 7. Portfolio-Level Quant Review

- **Correlazione tra strategie:** non misurata. Claim di diversificazione (S1 TS vs S3 cross-sec vs S4 news vs S2 vol) **non verificato** con dati. Oggi operativamente attive solo S1 (50%) + S4 (10% paper) → la "multi-strategia" è in larga parte teorica.
- **Overlapping exposure / stesso ticker:** S1 e S4 condividono l'universo equity/ETF; il combiner somma i pesi (`orchestrator.py:135` `merged_weights[sym] += wt*alloc`) **senza risoluzione conflitti né net-exposure cap** (Passata 1 RB-006). BUY(S1)+SELL(S4) sullo stesso nome si compensano silenziosamente o saturano.
- **Gross vs net exposure:** nessun controllo net; il vol targeter è applicato **dopo** i constraint → può ri-violare il cap 50%.
- **Vol targeting & regime sizing:** il regime è calcolato ma **non applicato** (mult=1.0) → nessun de-risking; il risk-contribution per strategia/regime non è misurato.
- **S4 aggiunge rumore a S1?** Rischio concreto: un S4 con IC non dimostrato (potenziale rumore) sovrapposto a S1 può **degradare** lo Sharpe di portafoglio invece di diversificarlo. Finché S4 non passa il placebo (S4-F1), il 10% S4 va trattato come **possibile rumore allocato**, non come diversificazione.
- **Diversificazione reale vs apparente:** apparente. Senza matrice di correlazione e risk-contribution, "4-5 strategie" è marketing, non diversificazione misurata.

**Portfolio-level risks:** combiner senza conflitti/net-cap; cap 50% violabile; nessun de-risking di regime; S4 come additivo rumoroso; concentrazione su un singolo regime bull a livello S1.
**Diversification claims da verificare:** correlazione S1/S3/S4 OOS; risk-contribution per strategia; drawdown-contribution per strategia/regime.
**Stress portfolio-level:** comportamento congiunto in un bear vero (mai testato).
**Verdetto portfolio:** la combinazione **non è dimostrata migliorare** l'edge e può peggiorarlo; trattare Alembic come "S1 in ricerca + overlay R&D", non come portafoglio multi-strategia validato.

---

## 8. Paper/Live Readiness Policy

| Strategy | Current status | Quant recommended status | Required tests before paper | Required tests before live | Kill criteria |
|---|---|---|---|---|---|
| **S1** | live 50% | **Backtest candidate** (demuovere da live) | S1-F1, S1-F2, S1-F3 (+riproducibilità) | S1-F1…F6 superati net-of-cost + parità BT↔live | OOS net <0.3, o non significativo post-SPA, o DD>soglia in bear reale |
| **S2** | disabled | **R&D only** | (prereq: dati opzioni reali) S2-F1 | S2-F1…F3 net-of-cost | VRP net ≤0 su dati reali; CVaR inaccettabile |
| **S3** | disabled | **R&D only** | S3-F1 (sizing PIT), S3-F2 | S3-F1…F5 net-of-cost | 0.15 sparisce con vol PIT; rank instability alta |
| **S4** | paper 10% | **Paper only (contenuto)** | S4-F1 (placebo), S4-F2, S4-F3 | IC net>0 persistente + parità paper/live ≥90gg | IC ≤ placebo; IC decay <24h; edge < costi |
| **S7** | "done"/orfano | **R&D only / Disabled** | (prereq: pipeline+consensus PIT) S7-F1, S7-F2 | S7-F1…F4 net-of-cost | drift non significativo net; consensus non PIT disponibile |

*Regole applicate:* "Live-ready" non è assegnato a nessuna strategia (deve essere raro). "Paper" = osservabile, non valido; S4 in paper ha kill criteria espliciti. Le R&D (S2/S3/S7) **non devono influenzare allocazioni operative** (S7 va anche tolto dalla UI, Passata 1 RB-011).

---

## 9. Quant Metrics Missing

- **Net Sharpe dopo costi realistici** (ADV reale) **e costo fisso $1440/anno**.
- **Sharpe same-bar vs t+1** (il "costo di realismo").
- **Turnover** per strategia e **capacity** (a quale AUM l'impatto erode l'edge).
- **DSR con n_trials reale** + p-value corretto (White/Hansen SPA) sull'intero set di combinazioni.
- **Drawdown per regime causale** (bull/bear/sideways, non 2 fasce vol hindsight).
- **IC e IC stability/decay** per S4 (e per ogni signal-based), net-of-cost.
- **Hit rate per regime.**
- **Correlazione tra strategie** + **risk-contribution** + **drawdown-contribution** per strategia.
- **Cost-adjusted contribution** di ciascuna strategia al portafoglio.
- **Paper/live divergence** (slippage, fill rate, cost diff) ≥90gg.
- **False-discovery correction** documentata (quante combo/strategie provate).
- **Numero di anni OOS e quanti includono un bear vero.**
- **Ensemble correlation** (S4) e **fallback rate** nei momenti di stress.

---

## 10. Top 10 Quant Blockers (per priorità)

1. **Same-bar execution** (`orchestrator.py:92-96`) — ogni Sharpe è pre-realismo. P0.
2. **Survivorship S1/S3** (`universe.py:36` inutilizzato) — OOS quasi solo bull. P0.
3. **Cost model impatto ≈0 + fisso escluso** (`realistic.py:51`) — net Sharpe sconosciuto. P0.
4. **DSR n_trials=1 / nessuna SPA** (`runner.py:20`) — significatività non deflazionata su 40+ combo. P0.
5. **Stress circolare** (`s1/backtest.py:183-197`) — sopravvivenza a crisi mai testata. P0.
6. **S3 lookahead full-sample nel sizing** (`s3/strategy.py:88`) — 0.15 contaminato. P0.
7. **S4 nessun IC / gate ineseguibile** — alpha non valutabile. P0.
8. **S2 dati opzioni sintetici** — backtest non informativo. P0 (per S2).
9. **Walk-forward decorativo + regime hindsight + Gate-2 denominatore** — robustezza sovrastimata. P1.
10. **Riproducibilità assente (no pin data/modello/seed; 33 test rossi)** — nessun numero verificabile. P0 (prerequisito di tutto).

---

## 11. What To Ask Technical Verification Next (Passata 3 — Kimi)

Domande mirate, non generiche:
1. **Same-bar:** confermare che nessun path di backtest (oltre `orchestrator.py:96`) introduca uno shift t+1; il fill usa lo stesso `MarketSnapshot` del segnale?
2. **S1 timing:** `compute_target_weights(data_replay.prices_until(ts))` usa `prices.index[-1]` = close[t]; confermare che non esista una variante che fillerebbe a t+1.
3. **Gate 5 stress:** confermare che `_extract_stress_periods` sia l'unico produttore di `stress_returns` e che non esista un path che inietti 2008/2020/2022 reali.
4. **Sensitivity:** il `max_sharpe`/"NEAR-OPTIMUM" (`sensitivity.py:154`) è usato solo nel report o influenza la selezione dei parametri base?
5. **ADV:** in produzione/backtest reale i volumi vengono mai passati a `DataReplay`, o l'ADV è sempre il default 10M? `TradeCostCalculator` entra mai nel sizing live o solo in accounting?
6. **Kill-switch nel backtest:** confermato non modellato? esiste un flag per simularlo?
7. **S4 gate report:** lo script `run_s4_gate_report.py` gira dopo i fix di import/kwargs? produce un IC?
8. **S3 sizing:** confermare che `self._vol = ...iloc[-1]` sia l'unica fonte di vol per il sizing (lookahead full-sample) e che non esista un path PIT.
9. **S4 timestamp:** `generated_at` è il **publish-time** della news o il tempo di scoring/inferenza? dove viene settato nell'ingestion?
10. **S4 recency:** `_signals_as_of` accumula tutti i segnali `<= ts` senza finestra; il `CrossSectionalRanker` applica un decay/recency o usa segnali stale?
11. **S7:** confermare assenza di `__call__`, EDGAR body solo-metadati (`sec_edgar.py:74`), consensus da LLM (`pead_worker.py:58-67`).
12. **Adjusted-close:** confermare che il prezzo di fill nel backtest sia "Adj Close" (`loader.py:131`, `universe.py:67`) e non raw close.
13. **Riproducibilità:** seed/pin presenti nei run di sensitivity/walk-forward? i 33 test rossi toccano i moduli backtest/gate?

---

## 12. What Not To Do

- **Non ottimizzare parametri** (lookback, soglie, vol window): non è validazione, è data mining; peggiora l'overfit già presente.
- **Non promuovere S1 senza t+1 + costi reali + survivorship-free + SPA**: il 0.51 attuale non è prova.
- **Non promuovere S4 senza IC/decay/placebo credibili**: senza placebo, è rumore LLM con bell'aspetto.
- **Non riabilitare S3 finché il lookahead di sizing non è escluso** (vol PIT).
- **Non usare PEAD/S7 senza consensus EPS point-in-time esterno** (no LLM-consensus).
- **Non trattare la sensitivity grid come prova di robustezza** senza correzione multipla (White/Hansen SPA).
- **Non usare stress test circolari**: 2008/2020/2022 reali o "non testabile" onesto.
- **Non ignorare costi/slippage/impatto/fisso**: il net Sharpe è ciò che conta.
- **Non confondere paper P&L con edge**: paper è osservazione, non validazione.
- **Non usare LLM sentiment come alpha senza placebo/shuffled-news.**
- **Non archiviare il VRP (S2) come falso alpha**: sui dati sintetici attuali è semplicemente *non valutabile*.
- **Non riparare gli script dei gate lasciando intatti input/design** (n_trials=1, regime hindsight, stress circolare): darebbe ancora falsa conferma.

---

## 13. Final Recommendation

**Prossimi 7 giorni:**
1. **Demuovere S1 da live** (allineato a Passata 1 Phase 0): il suo edge non è quant-giustificato.
2. **Congelare** ogni promozione/tuning e l'allocazione 10% S4 (trattarla come possibile rumore finché non passa S4-F1 placebo).
3. **Eseguire per primo il backtest S1 ri-fatto onesto**: t+1 (S1-F1) + costi reali e fissi (S1-F2) + universo survivorship-free PIT (S1-F3), con **manifest riproducibile**. Questo singolo run ricalibra ogni decisione di promozione.
4. **Mantenere disabled** S2/S3/S7; togliere S7 dalla superficie operativa.

**Prossimi 30 giorni:**
1. Completare il protocollo di falsificazione **S1** (S1-F1…F6) net-of-cost con SPA; decidere il verdetto su S1 su numeri onesti.
2. **S3:** rerun con sizing PIT (S3-F1) + survivorship-free (S3-F2) → decidere se esiste un segnale.
3. **S4:** IC study con placebo/shuffled-news (S4-F1/F2/F3) e timestamp publish-time PIT; nessuna promozione senza IC net>0 persistente.
4. **Portafoglio:** misurare correlazioni, risk-contribution, e l'effetto reale del combiner; verificare se S4 diversifica o degrada S1.

**Strategie da congelare ora:** S1 (live→backtest), S4 (promozione bloccata), S2/S3/S7 (R&D/disabled).
**Strategie da falsificare per prime:** S1 (massima priorità, è in capitale reale), poi S3 (lookahead noto), poi S4 (placebo).
**Backtest da rifare per primo:** S1 onesto (t+1 + costi reali+fisso + survivorship-free + SPA), riproducibile.
**Documento da produrre dopo:** **Passata 3 — Kimi Technical Verification Matrix** (rispondere alle 13 domande della §11 con conferma file:line ed elenco dei test mancanti per ciascun blocker).

---

*Fine OPUS_QUANT_TRADING_VALIDITY_MEMO (Passata 2/5). Modalità read-only rispettata: nessun file modificato, nessun backtest/pipeline/ordine eseguito; sola ispezione read-only del codice per fondare i giudizi quant. Ogni alpha è trattato come ipotesi da falsificare. Le contaminazioni sono verificate file:line; le imprecisioni della red-team (Gate 3 = CV non max; S2 = sintetico non "falso alpha"; S3 lookahead = full-sample confermato; same-bar su rebalance mensile = impatto limitato) sono corrette esplicitamente. Priorità a falsificazione, robustezza, costi realistici, timing corretto e riproducibilità.*
