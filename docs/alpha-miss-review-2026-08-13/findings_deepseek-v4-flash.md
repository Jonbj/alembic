"deepseek-v4-flash:cloud" is not a model this version of Claude Code recognizes, so auto-compact will keep this session within 200k tokens (the context window it assumes). If the model accepts more, append [1m] to the model name for 1M, or set CLAUDE_CODE_MAX_CONTEXT_TOKENS to its real window; to make it recognized, map it in the modelOverrides setting or update Claude Code; CLAUDE_CODE_DISABLE_UNKNOWN_MODEL_WINDOW_ENFORCEMENT=1 restores the previous wait-for-the-API behavior.
Ho letto tutto: script, dossier, moduli puri, entrambi i report, i due ledger, la carta e la config. Prima di elencare i suggerimenti, una diagnosi secca.
## Diagnosi
Il report è già di alta qualità — l'analisi gap/intraday del 08-12 è il tipo di insight che serve. Ma ha un difetto strutturale: **i numeri che contano per le domande di uscita della carta sono in parte ri-derivati dall'LLM ogni mattina, con metodologia incoerente tra giorni**. Il dossier (#174) ha risolto la ri-derivazione dei rendimenti, ma non di ciò che è diventato il cuore analitico del report: la scomposizione gap/intraday, il costo catturabile dei miss, la frazione di movimento già avvenuta al primo segnale (F-030), la tabella di confronto §6. Tutti questi sono calcolati a mano dalla sessione.
Secondo difetto: **la tassonomia dei miss non sa nominare la causa dominante**. Il classificatore deterministico produce `BELOW_GATE` (il caso più frequente: ORCL, META, HD il 08-12), ma la tassonomia del report e del ledger ha solo `THIN_NEUTRAL`/`FILTERED`, e l'LLM mappa `BELOW_GATE` → `THIN_NEUTRAL` in modo non riproducibile. La metrica su cui la carta falsificherà la domanda n.1 è la *distribuzione delle cause di miss* — ed è costruita su una tassonomia che non può esprimere la causa più comune.
Terzo: **il report non traccia il progresso verso le domande di uscita**. La carta pre-registra criteri falsificabili (NO_NEWS dominante in ≥60% dei giorni **e** P&L economico S4 entro ±$200), ma il report non dice mai "siamo al giorno X di 40, NO_NEWS è dominante in Y giorni, il P&L economico S4 è $Z". L'operatore deve ricostruirlo da prosa.
---
## 1. Nuove metriche e sezioni
### 1.1 Scomposizione gap/intraday nel dossier (deterministico)
**Cosa:** aggiungere a ogni simbolo del dossier `gap_pct = open/close_prec − 1`, `intraday_pct = close/open − 1`, `quota_gap = gap/return`, più l'aggregato `mover_gap_quota_mediana`.
**Perché:** il dossier ha già OHLC (`_barre` in `alpha_miner_dossier.py:148-152`); il calcolo è banale. Oggi la tabella "quota nel gap" del 08-12 è stata costruita a mano dalla sessione — non riproducibile, e la metrica F-030 è degenerata proprio perché ricalcolata al volo. È la metrica di contesto esecutivo più importante del report.
**Come:** funzione pura in `src/analysis/dossier/market.py`; il prompt cita il campo invece di ricalcolarlo.
### 1.2 Costo catturabile per miss (deterministico)
**Cosa:** per ogni candidato miss, `costo_catturabile = max(0, intraday_return) × size_S4` (libro long-only), accanto al costo su return pieno.
**Perché:** le soglie della carta sono in dollari, ma la metodologia di stima varia tra giorni: il 08-03/08-04 usava il return pieno, il 08-12 la porzione intraday. Un costo deterministico e coerente rende l'evidenza cumulativa comparabile — oggi non lo è.
**Come:** nel dossier, dato `intraday_return` e la size S4 tipica (costante o da config). L'LLM aggiusta solo i casi speciali (es. "sarebbe stato bloccato da pyramiding") e motiva la deviazione.
### 1.3 Sezione "progresso verso le domande di uscita"
**Cosa:** un blocco che dice: giorno X di 40, giorni in cui NO_NEWS è stata dominante (soglia falsificazione ≥60%), P&L economico S4 cumulato, costo cumulato per causa di miss.
**Perché:** è lo scopo reale del report. Il dossier ha già `aggregati.miss_cumulati` (dal ledger) ma il report non lo mette in relazione con i criteri pre-registrati. L'operatore deve assemblare da prosa ciò che la carta ha reso meccanico.
**Come:** il dossier calcola i numeri (giorni trascorsi, giorni con NO_NEWS dominante da `market_daily.jsonl`, P&L economico — vedi 4.2); l'LLM scrive l'interpretazione ("trend verso falsificazione / lontano").
### 1.4 Sezione "contaminazione della misura"
**Cosa:** una sezione dedicata in §7 per ogni finding che corrompe le metriche su cui la carta falsificherà: F-006 (segno perso nel decision log), F-003 (drawdown incoerenti), F-004 (decay monitor), F-012/F-020 (fan-out che gonfia la copertura).
**Perché:** questi sono i finding a priorità massima — invalidano l'evidenza stessa. Oggi sono sepolti tra gli altri. La carta regge tutta su metriche pulite.
**Come:** regola nel prompt: "se un finding di oggi tocca l'osservabilità della distribuzione delle cause o dello split P&L, elencalo in una sezione dedicata in cima a §7".
### 1.5 IC giornaliero del segnale
**Cosa:** correlazione (Spearman) tra tutti gli score di sentiment del giorno e i rendimenti same-day della watchlist.
**Perché:** la domanda n.1 è "la news ha alpha?". L'IC same-day è contaminato dal gap (gli score arrivano dopo il movimento) — ma quella contaminazione *è* il finding. Oggi il report ci gira intorno (F-030) senza mai dare il numero pulito.
**Come:** il dossier ha già tutti i segnali e tutti i rendimenti; una funzione pura in `market.py`.
### 1.6 Ranking dei miss per costo catturabile, non per |return|
**Cosa:** la tabella dei miss ordinata per `costo_catturabile` decrescente.
**Perché:** oggi un mover a +9% tutto gap (vale $6) sta sopra un +3% tutto intraday (vale $66). L'actionability è in dollari catturabili.
**Come:** conseguenza automatica di 1.2.
---
## 2. Modifiche al prompt
### 2.1 Mappatura esplicita tassonomia dossier → report
Il dossier produce `NO_NEWS / NO_SIGNAL / THIN_NEUTRAL / BELOW_GATE / NON_CLASSIFICATO / IN_PORTAFOGLIO`; il report usa `NO_NEWS / THIN_NEUTRAL / WRONG_SIGN / FILTERED / OUT_OF_STRATEGY_SCOPE / CAUGHT`. Oggi l'LLM ri-classifica da zero (il 08-12: dossier `BELOW_GATE` → report `THIN_NEUTRAL`). Il prompt deve imporre: **parti dalla `causa` del dossier, e puoi solo *upgradare* a WRONG_SIGN/FILTERED con evidenza dal testo degli articoli** (le uniche due che richiedono lettura). `BELOW_GATE` e `NO_SIGNAL` restano come sono. Meglio ancora: aggiungi `BELOW_GATE` come categoria di primo livello (vedi 4.1).
### 2.2 Metodologia costo obbligatoria
Imporre: `costo = max(0, intraday_return) × 2200` per i miss long-side; `0.0 verificato` per i mover al ribasso su libro long-only; `null` solo se davvero non stimabile. Citare i numeri usati. Oggi la stima è un hand-wave che varia tra giorni — e le soglie della carta sono in dollari.
### 2.3 Checklist strutturata dei finding aperti
Prima di scrivere §7, obbligare a: elencare tutti i finding aperti da `findings.json` e marcarli "ricorrente / non ricorrente / nessuna evidenza oggi". Sostituisce il vago "puoi guardare i report precedenti se presenti" (riga 207-208 dello script). La ricorrenza è il segnale centrale della carta (≥5/≥10 giorni distinti); una checklist meccanica rende affidabili le affermazioni "sesta giornata del pattern".
### 2.4 Sezione "top-3 azionabili"
Obbligare una lista finale di 3 finding per priorità, ordinati per (costo × ricorrenza × fixabilità), ognuno con una riga "cosa serve decidere". Forza la sintesi invece dell'enumerazione.
### 2.5 Vietare la ri-derivazione dei numeri chiave
Esplicitare: se il dossier fornisce gap/intraday/costo/IC, citare il campo — non ricalcolarlo. Il 08-12 ha ancora ricalcolato a mano la tabella del gap, che è esattamente ciò che #174 voleva eliminare.
### 2.6 Digest Telegram strutturato
Chiedere che stdout termini con un digest di 5 righe (top miss + costo, tema, P&L del giorno, un finding) che lo script invii verbatim. Oggi il messaggio è un dump di 3800 caratteri dell'executive summary.
---
## 3. Dati aggiuntivi e cross-analisi
### 3.1 Barre intraday ai timestamp dei segnali
Per ogni mover con segnali, il prezzo al momento del primo segnale → F-030 deterministico ("frazione del movimento già realizzata al primo segnale"). È il finding più ricorrente della finestra (6+ occorrenze) ma è calcolato ad-hoc e degenera sui giorni di gap. Minute bars per 96 simboli × 1 giorno è economico. Il dossier le scarica e fa il join con `sentiment_signals.generated_at`.
### 3.2 Terzo ledger: ticker-level
Un `ticker_miss.jsonl`: per ticker per giorno, mover?, mancato?, causa, costo catturabile. Oggi le ricorrenze sistematiche ("QCOM NO_NEWS 3ª volta in 4 sedute", "SAP mancato 6 volte") sono prosa a memoria — e il docstring del dossier ammette che un report ha dichiarato di non aver riletto gli altri. Un ledger strutturato rende "sistematico vs casuale" meccanico e alimenta la sintesi del giorno 40.
### 3.3 Cross-analisi news → prezzo (lead-lag)
Per ogni mover con news: timestamp del primo articolo vs open del giorno. Se il primo articolo è dopo l'open, la news non può aver guidato il gap. Quantifica il problema "la notizia arriva a movimento avvenuto" e separa "buco di dati" da "buco di timing". `news_log` ha `fetched_at`/`raw_ingested_at`; il dossier ha l'open.
### 3.4 Settore dal config
Usare la mappa `sectors` di `config/trading.yaml:124-135` per calcolare rendimenti medi e conteggio mover per settore. Oggi la sezione "Pattern" è lettura LLM dei nomi dei ticker; la tassonomia esiste già nel config. La rende riproducibile e confrontabile tra giorni.
### 3.5 Snapshot Redis (gate, pesi, regime, coppia modelli)
Catturare a fine giornata `feedback:entry_threshold:S4`, `ensemble:weights:current`, le chiavi regime e la coppia di modelli. Il dossier legge già il gate (`_soglia_gate_s4`); estendere agli altri. Il valore del gate spiega la distribuzione dei miss attraverso la discontinuità del ratchet (#191); la coppia modelli spiega i cambi di qualità del segnale.
### 3.6 Capture ratio storico per calibrare i costi
Dai trade passati chiusi in giornata: realizzato vs movimento del giorno → un capture ratio storico. I costi stimati (2200 × return) sono upper bound; l'esempio MSFT della carta (giorno +15,5% → $13 realizzati) mostra che l'alpha catturato è una frazione del movimento. Un ratio calibrato rende le stime oneste.
---
## 4. Struttura di findings e ledger
### 4.1 `BELOW_GATE` come categoria di primo livello
La tassonomia della carta non può esprimere la causa più comune. Il report la mappa a `THIN_NEUTRAL` o `FILTERED` in modo incoerente. Poiché la metrica di falsificazione è la distribuzione delle cause, la tassonomia deve saper nominare la causa dominante. Aggiungere `BELOW_GATE` al report e al dict `miss` di `market_daily.jsonl`, e pre-registrare nella carta la soglia di falsificazione aggiornata.
### 4.2 `market_daily.jsonl`: campi mancanti
Aggiungere: `pnl_economico` (definizione della carta — alimenta la domanda n.2), `gate_s4` (soglia effettiva del giorno — spiega la discontinuità #191), `modelli` (coppia ensemble), `costo_miss_catturabile` (numero headline), `gap_quota_mediana`. Sono i fatti deterministici che la sintesi del giorno 40 richiede; oggi sono sparsi in prosa o assenti.
### 4.3 `findings.json`: campi derivati e validazione meccanica
Aggiungere `giorni_distinti` (derivato, per valutare le soglie ≥5/≥10), `ultima_occorrenza`, e `trend` (peggiora/stabile/migliora) per i finding quantitativi come F-020. Aggiungere un validatore meccanico (come il check JSONL già nel prompt) per gli invarianti: id unici, `prossimo_id` coerente, `costo_cumulato_usd` = somma dei non-null, solo-append. Oggi l'append-only è imposto dal prompt, che è più debole di un check.
### 4.4 Formalizzare la relazione finding ↔ causa di miss
Un campo `relazione` (es. F-012 "spiega" THIN_NEUTRAL, F-030 "spiega" BELOW_GATE) per prevenire il doppio conteggio e rendere interpretabile la distribuzione delle cause. Il report già evita il doppio conteggio a mano (nota F-012 del 08-12); formalizzarlo rende la contabilità auditabile.
---
## 5. Altre idee
### 5.1 Sintesi settimanale
Un rollup del venerdì: finding della settimana, progresso verso le domande di uscita, quali finding hanno attraversato le soglie. Il report giornaliero accumula ma non sintetizza; la carta ha un checkpoint di metà periodo (28/08) che un rollup settimanale alimenterebbe.
### 5.2 Confronto con le assunzioni del backtest
Quando un pattern come "i mover gappano e l'intraday è piatto" si ripete, verificare se il backtest assumeva catturabilità. Se le condizioni live divergono dalle assunzioni del backtest, l'evidenza per la domanda n.1 è contaminata — il confronto sarebbe tra mele e arance.
### 5.3 Soglia mover σ-scaled
`mover = |return| ≥ k×σ` (es. 1,5σ) invece del 3% fisso. I report già calcolano il rapporto σ ad-hoc (1,27σ il 08-12, 2σ il 08-11). Rende "mover" confrontabile tra giorni a dispersione diversa e toglie la prosa di giustificazione.
### 5.4 "Miss evitabili" come numero chiave
Un campo derivato `evitabile: bool` per miss = (aveva news) ∧ (segnale sopra gate) ∧ (non filtrato) ∧ (non pyramiding) ∧ (lato long). È il numero che conta per la domanda di uscita: la tassonomia attuale mescola buchi di dati (niente da fare) con buchi di pipeline (correggibili).
---
## Priorità
Se dovessi scegliere cinque interventi, in ordine:
1. **1.1 + 1.2** — gap/intraday e costo catturabile nel dossier. Il più alto ritorno: rende deterministico ciò che oggi è il cuore analitico del report e allinea i costi alle soglie in dollari della carta.
2. **4.1 + 2.1** — `BELOW_GATE` come categoria e mappatura esplicita. La metrica di falsificazione deve poter nominare la causa dominante.
3. **1.3** — sezione progresso verso le domande di uscita. È lo scopo del report.
4. **3.2** — ledger ticker-level. Rende meccanica la distinzione sistematico/casuale.
5. **2.2 + 2.3** — metodologia costo obbligatoria e checklist dei finding aperti nel prompt. Due regole a costo zero che stabilizzano la qualità.
Cosa non toccare: l'architettura dossier-orchestratore è giusta, la disciplina append-only dei ledger è giusta, e la qualità di lettura dei report (soprattutto il 08-12) è già il benchmark da preservare.
