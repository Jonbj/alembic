# Alembic — Frontend Product / UX / QA Review

Data review: 2026-07-01  
Ambiente verificato: frontend locale `http://localhost:3000`, API locale via proxy `/api/*`, Grafana `http://localhost:3001`  
Metodo: lettura documentazione e codice, navigazione sistematica con Playwright su desktop/tablet/mobile, controlli API mirati, verifica screenshot, interazioni non distruttive.

## Checklist di esplorazione

- [x] Documentazione: scopo, target, casi d'uso, dominio, funzionalita dichiarate.
- [x] Inventario pagine, menu, tab, form, filtri, azioni e helper online.
- [x] Accesso frontend, API e helper online.
- [x] Overview e navigazione globale.
- [x] Operations/Admin: System, Config, Admin.
- [x] News.
- [x] Signals e Decision Log.
- [x] Quality, Validation, Labeling.
- [x] Trading e Performance.
- [x] Strategies, Auto-Improve, LLM, Backtest, Dashboard, Docs.
- [x] Stati applicativi, API, accessibilita, responsive, contenuti.
- [x] Report finale.

## 1. Executive summary

Il frontend di Alembic e gia utile come cockpit interno per un operatore tecnico: mostra readiness, segnali, decisioni, P&L, stato strategie, feedback gate e controlli amministrativi. La struttura principale e coerente con un sistema di trading algoritmico paper/supervised, e alcune aree sono mature: Overview, Signals, Performance giornaliero/settimanale, Operations e Auto-Improve hanno dati reali e microcopy abbastanza esplicativo.

Non e pero pronto per utenti reali non interni. I rischi principali sono:

- alcune funzioni sono rotte o fuorvianti: Dashboard/Grafana non deve restare superficie frontend, LLM weights non rispetta lo schema dell'API, Trading/Fills usa campi trade invece di veri fill, il toggle Economy/Full ensemble invia `glm` ma il worker accetta `glm52`;
- la documentazione e disallineata: cita una pagina Trades non piu navigabile, modelli LLM hardcoded/non dinamici, 10 sezioni quando il menu ne mostra 15, credenziali Grafana e stati strategia non correnti;
- il responsive mobile e di fatto non utilizzabile: sidebar fissa e tabelle/grafici tagliati;
- l'interfaccia espone molte metriche corrette ma spesso non dice all'utente "cosa fare dopo", soprattutto in Quality, News, Backtest e Dashboard.

Valutazione complessiva: **utilizzabile solo internamente**. Con la correzione dei P1 sotto, puo diventare utilizzabile da beta user tecnici; per utenti reali servono responsive, coerenza documentale, stati di errore migliori e flussi piu guidati.

## 2. Comprensione dello scopo dell'applicazione

Alembic e un sistema di trading algoritmico che usa LLM offline per generare segnali di sentiment su news finanziarie. Gli LLM non sono nel path sincrono di ordine: elaborano news in background, scrivono segnali in Redis/PostgreSQL, e il portfolio scheduler legge segnali pre-calcolati. Il sistema opera oggi in paper/supervised paper, con live trading non autorizzato.

### Decisioni prodotto confermate

Queste decisioni sono state confermate dopo la review e devono guidare le modifiche successive:

| Area | Decisione |
|---|---|
| Trades | Non ripristinare `Trades.tsx` per ora. Convergere su `Trading` e `Performance`, recuperando in quelle pagine gli eventuali analytics mancanti. |
| Model registry | I modelli live non devono essere scolpiti nella UI/documentazione. La UI deve leggere modelli disponibili/attivi in modo dinamico, perche l'API Ollama puo cambiare disponibilita modello nel tempo. I modelli storici vanno marcati come storico/retired quando non sono piu nel registry live. |
| Economy mode | Il toggle Economy deve selezionare GLM-5.2, usando il valore riconosciuto dal backend/worker. |
| Mobile | Mobile non deve essere un full cockpit. Deve essere una vista read-only/status, con alert principali e link di approfondimento. |
| Grafana | Grafana va eliminato per ora dal frontend come superficie utente. I summary React devono diventare fonte primaria di monitoraggio. |
| Operating mode | Ogni cambio operating mode deve richiedere conferma esplicita. |
| Labeling strength | `gt_sentiment_strength` resta signed `-1..1`, ma la UI deve vincolarlo alla direction: positive > 0, negative < 0, neutral = 0. |
| Auto-Improve Phase C | La pagina deve esporre last run del counterfactual worker e raw skip counts, per distinguere assenza dati da worker fermo. |

### Stato implementazione blocco 1

Aggiornamento 2026-07-01:

- Economy mode allineato a GLM-5.2 tramite chiave canonical `glm52`; alias legacy `glm` accettato solo lato backend.
- Aggiunto model registry backend condiviso per selezione sentiment, endpoint `/api/llm/models` e registry incluso in `/api/admin/status`.
- `/api/weights/current` ora filtra e normalizza i pesi sui modelli attivi, segnalando eventuali `dropped_models`.
- Pagina LLM aggiornata per leggere pesi correnti e suggestion con il contratto API reale.
- Labeling vincola relevance/ticker/direction/strength prima del salvataggio.
- Cambio operating mode richiede conferma esplicita.
- Trading/Fills ora deriva dagli ordini `filled` invece che dai record trade entry/exit.

Target utente:

- operatore tecnico/quant che deve controllare readiness, segnali, decisioni e P&L;
- sviluppatore o reviewer che deve verificare qualita del segnale, estrazione ticker e modelli;
- responsabile prodotto/rischio che deve capire se il sistema e sicuro, degradato, in paper, bloccato o pronto a proseguire la validazione.

Entita principali:

- News, ticker, sorgente, sentiment grezzo;
- LLM response, ensemble signal, FinBERT fallback, confidence, model weights;
- Decisione di portafoglio, ordine, posizione, trade/fill;
- Strategia S1/S3/S4/S7, lifecycle, promotion block, validation gate;
- Feedback gate Phase B, counterfactual Phase C;
- Readiness, scheduler, activity log, config, kill switch, operating mode.

Flussi core:

- controllo operativo giornaliero: Overview -> Operations/System -> Signals -> Trading/Performance;
- diagnosi news -> signal -> decisione -> ordine;
- verifica qualita ticker/sentiment: Quality -> Labeling -> Backtest;
- controllo rischio: Validation -> Performance -> Admin/Config;
- miglioramento automatico: Auto-Improve -> Signals/Decision Log -> Performance.

## 3. Review pagina per pagina

### Global navigation / Layout / Login

**Scopo atteso**  
Dare orientamento stabile, stato operativo globale, accesso rapido alle aree del sistema e controllo sessione.

**Cosa ho verificato**  
Menu laterale, login con credenziali errate, banner readiness, sessione autenticata con token locale, desktop/tablet/mobile.

**Risultato osservato**  
Login mostra errore chiaro per credenziali errate. Banner readiness comunica market closed, redis/db/kill-switch e segnali/beat in pausa fuori orario. Menu completo.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Responsive | Sidebar fissa anche su mobile; contenuto ridotto a circa meta viewport, tabelle e contenuti monitoring tagliati. | Mobile e tablet stretto non usabili. | Introdurre una vista mobile read-only/status con navigazione ridotta e senza full cockpit. |
| P1 | Funzionale/API | Toggle menu "Economy (GLM)" invia `glm`, ma il sentiment worker accetta `glm52`; con selezione non riconosciuta il worker ricade sul full ensemble. | L'utente crede di ridurre quota/costi, ma probabilmente non succede. | Allineare valori frontend/API/worker: `glm52` oppure alias backend `glm -> glm52`; aggiornare label a "Economy (GLM-5.2)". |
| P2 | UX | Ordine menu: `LLM` precede `Signals`, ma il flusso logico e News -> Signals -> Quality -> LLM. | L'utente entra nei dettagli modello prima di vedere il segnale aggregato. | Spostare LLM dopo Quality o dopo Labeling; mantenere Admin prima di Docs come richiesto. |
| P2 | Contenuto | Menu dice `Admin`, pagina aperta si intitola `Operations`. | Ambiguita: sembra una pagina diversa da quella selezionata. | Rinominare title a "Admin & Operations" oppure rendere il menu "Admin" ma default tab "Admin" solo se l'intento e amministrativo. |
| P2 | Accessibilita | Help drawer e bottoni iconici non hanno ruolo dialog/aria-label/focus trap; chiusura solo click esterno/X. | Tastiera e screen reader penalizzati. | Aggiungere `role="dialog"`, `aria-modal`, focus trap, Escape, `aria-label` su help/close. |

### Overview

**Scopo atteso**  
Prima pagina operativa: stato sistema, autorizzazione, P&L, posizioni, gate segnale e ultimi segnali.

**Cosa ho verificato**  
KPI, readiness cards, Authorization, Signal Gate, Signal Quality, Decision Summary, charts e Latest Signals.

**Risultato osservato**  
Overview e la pagina piu coerente del prodotto. Mostra P&L mensile, open positions, active signals, stato degraded, last signal/cycle stale, S1/S4 lifecycle, gate threshold 0.35, quality metrics e decision summary.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | UX | Molte metriche critiche non hanno severita/action esplicita: ticker precision 0.24, fallback 26.4%, near-zero 39.1%, 0 fresh signals. | L'utente vede il problema ma non sa la prossima azione. | Aggiungere "Action hints": "Go to Quality", "Open Labeling", "Check sentiment-worker". |
| P2 | Coerenza | Banner in market closed mostra `signals fresh` con trattino/opacity, mentre card Operational State dice stale. Tecnicamente corretto, ma ambiguo. | Possibile falsa rassicurazione. | Usare label "signals paused" fuori orario invece di "signals fresh". |

### Operations / System

**Scopo atteso**  
Verificare scheduler, activity log e segnali PEAD prima di agire.

**Cosa ho verificato**  
Tab card, tab System interni, scheduler, helper online, stati stale/no data.

**Risultato osservato**  
Scheduler mostra worker, schedule, last run e status. Fuori orario segnala sentiment-worker e portfolio-cycle stale, altri worker no data.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | Accessibilita | Le card-tab Operations e i tab interni hanno nomi simili; l'automazione clicca la card invece del tab `Activity Log`. | Navigazione con screen reader/test fragile. | Usare `role="tablist"`, `role="tab"`, `aria-controls`; differenziare label accessibili. |
| P2 | UX | Activity/PEAD sono nascosti dietro tab, ma Scheduler e solo il primo livello di diagnosi. | Operatore potrebbe fermarsi alla vista scheduler senza guardare eventi reali. | Aggiungere summary in alto: "last activity event", "PEAD active signals", link diretto ai tab con badge count. |

### Operations / Config

**Scopo atteso**  
Gestire watchlist e parametri rischio, con conferme per valori pericolosi.

**Cosa ho verificato**  
Watchlist, add/remove symbol, risk range, stop loss, high-risk confirmation, full config read-only.

**Risultato osservato**  
La pagina e utile e le conferme high-risk sono presenti. Full config aiuta i tecnici.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | Validazione | Add symbol accetta qualunque stringa uppercase; non valida ticker, watchlist tradabile, duplicati normalizzati oltre `Set`. | Config sporca o simboli non tradabili nel ciclo successivo. | Validare formato ticker e, se possibile, chiamare endpoint di symbol validation prima di salvare. |
| P2 | Accessibilita | Bottoni `x` per rimuovere ticker non hanno `aria-label` e target ridotto. | Rimozione non accessibile e click accidentali. | `aria-label="Remove AAPL from watchlist"`, target minimo 32px. |
| P3 | UX | Full Config occupa spazio operativo ma e read-only tecnico. | Carico cognitivo per operatori non sviluppatori. | Collassare in accordion "Raw config". |

### Operations / Admin

**Scopo atteso**  
Controlli ad alto impatto: kill switch e operating mode.

**Cosa ho verificato**  
Kill switch modal fino alla conferma, radio mode, full_auto disabilitato, helper.

**Risultato osservato**  
Kill switch ha conferma; deactivation richiede token backend. Full auto e disabilitato.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Safety UX | Cambio operating mode avviene direttamente al click radio per `paper`, `backtest`, `semi_auto`, `halted`. | Un click errato puo cambiare stato operativo. | Richiedere conferma per ogni cambio mode diverso da visualizzazione corrente; mostra diff "paper -> halted". |
| P2 | Feedback | Dopo cambio mode l'unico feedback e il radio aggiornato/sidebar. | Difficile capire se API ha persistito correttamente. | Toast "Mode changed to halted" + timestamp e stato backend. |

### News

**Scopo atteso**  
Audit trail delle notizie ingestite, filtro per ticker/source e contesto per capire i segnali.

**Cosa ho verificato**  
Lista, filtri ticker/source, espansione riga, URL sicuro, helper.

**Risultato osservato**  
Mostra fino a 200 articoli, fonte, ticker, sentiment e fetched/published time. Righe espandibili con snippet e URL.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | UX/prodotto | News non evidenzia quali articoli hanno generato segnali o decisioni. | Difficile seguire news -> signal -> order. | Aggiungere colonne/link `signal_id`, `used in decision`, score finale e link a Signals filtrato. |
| P2 | Performance percepita | 200 righe in tabella unica, senza paginazione o virtualizzazione. | Scan lento e carico cognitivo alto. | Default 50, virtualizzazione o pagination; sort/filtri per "actionable", "with signal", "fallback". |
| P2 | Contenuto | Sentiment News e raw sentiment possono essere confusi con score S4 finale. | Utente puo sovrastimare il valore di una news. | Label alternativa: "Raw article sentiment" e tooltip "non e il signal score usato dal portfolio". |

### Signals

**Scopo atteso**  
Mostrare segnali LLM aggregati e Decision Log del portfolio scheduler.

**Cosa ho verificato**  
Tab Signals/Decision Log, filtro ticker, filtro direction, gate threshold, virtual list, decision reasons.

**Risultato osservato**  
La pagina e funzionalmente solida. Il Decision Log e prezioso: spiega BUY/SELL/skip e ragioni.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | UX | Colonna `Usato` dice solo se usato, non spiega perche non usato. | L'utente deve aprire Decision Log e correlare manualmente. | Per segnali non usati mostra motivo derivato: stale, below threshold, no cycle yet, fallback ignored, outside window. |
| P2 | Navigazione | Nessun link da signal a news originali o LLM responses. | Diagnosi segnale richiede passaggi manuali. | Riga espandibile con reasoning, source news, link a News/LLM filtrati. |
| P3 | Contenuto | Soglia direction BUY/SELL a +/-0.1 differisce dal gate effettivo 0.35. | BUY visivo puo sembrare actionable anche se sotto gate. | Chiamare la direzione "polarity" e distinguere chiaramente "actionable gate pass". |

### Quality

**Scopo atteso**  
Evidenziare qualita sentiment, fallback, divergenza, bias modello, precision/recall ticker.

**Cosa ho verificato**  
Window 7/14/30d, metriche per modello, ensemble, extraction.

**Risultato osservato**  
Metriche reali e importanti: near-zero 39.1%, fallback 26.4%, ticker precision 0.240, recall 0.400, macro false positives 2.0/articolo.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Prodotto | Metriche critiche non vengono trasformate in stato/azione. Precision 0.24 dovrebbe essere allarme operativo. | L'utente puo ignorare degradazione che impatta ordini. | Aggiungere severity thresholds e CTA: "Open Labeling", "Inspect false positives", "Keep S4 promotion blocked". |
| P2 | Coerenza | Mostra ancora `qwen3.5:cloud` nei dati storici senza indicare che e stato rimosso dal path attuale. | Confusione tra performance storica e modelli live. | Badge "historical/retired model" e filtro "current models only". |

### Validation

**Scopo atteso**  
Monitorare paper run: deployment, regime, P&L netto, churn, turnover, exit reasons.

**Cosa ho verificato**  
Window selector, KPI, roundtrip symbols, exit reasons.

**Risultato osservato**  
Pagina leggibile e utile. Mostra deployment 0%, regime 0.7, realized net PnL, win rate, turnover e churn.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | UX | Non evidenzia se valori sono buoni/cattivi rispetto a soglie di runbook. | L'utente deve conoscere target a memoria. | Aggiungere soglie: churn alto, win rate basso, deployment troppo basso, stop-loss count. |
| P3 | Contenuto | Exit reasons tecnici (`portfolio_sell`, `sentiment_reversal`) non spiegati in pagina. | Ambiguita per utenti non dev. | Mappare label user-facing e tooltip. |

### Labeling

**Scopo atteso**  
Creare golden set blind per migliorare precision/recall ticker e sentiment.

**Cosa ho verificato**  
Progress, articolo, input ticker, relevance, direction, strength, save state.

**Risultato osservato**  
Flusso chiaro e adatto a labeling manuale. Mostra progresso e nasconde il ticker estratto dal sistema.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Validazione dati | `canSave` richiede solo relevance e direction; permette `company_specific` senza ticker, negative con strength positiva, positive con strength negativa o strength 0. | Golden set incoerente, metriche Quality contaminate. | Regole: company_specific/sector richiedono ticker; macro/irrelevant impongono ticker vuoto; direction positive richiede strength >0, negative <0, neutral =0. |
| P2 | UX | Strength slider da -1 a +1 mostra barra blu al 50% quando valore 0.0. | La forza neutra sembra "mezza piena". | Usare slider bidirezionale con zero centrale e colori per segno, o input stepper con sign coerente alla direction. |
| P2 | Contenuto | Label interne (`company_specific`, `sector`) sono tecniche e in inglese. | Meno naturale per annotatori. | Usare label "Societa specifica", "Settore", "Macro", "Irrilevante" salvando i valori tecnici sotto. |

### Trading

**Scopo atteso**  
Monitorare posizioni, ordini e fill eseguiti.

**Cosa ho verificato**  
Tab Positions, Orders, Fills, filtro symbol, empty positions, order data API.

**Risultato osservato**  
Positions empty state corretto; Orders mostra 200 ordini Alpaca. Fills pero usa dati da `trades` e non veri ordini/fill.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Funzionale/dati | Fills usa `exit_reason` come side e `entry_price/entry_time` come fill price/time. Non rappresenta un vero storico fill. | L'utente puo leggere lato, prezzo e data errati per esecuzioni. | Derivare Fills da `/api/orders` filtrando `status=filled` o creare endpoint `/api/fills`; mostra `filled_avg_price`, `filled_qty`, `filled_at`, side reale. |
| P2 | Dati/API | Alcuni BUY order hanno `qty: "None"` ma filled_avg_price valorizzato. | Quantita e notional non chiari. | Mostrare notional/fractional qty da Alpaca o normalizzare lato backend. |
| P2 | UX | Nessun riepilogo operativo in cima: total open exposure, last fill, failed/canceled. | La pagina richiede lettura tabellare. | Aggiungere KPI compatti sopra i tab. |

### Performance

**Scopo atteso**  
Misurare performance storica, giornaliera e report settimanale con costi, capital efficiency, feedback e pesi.

**Cosa ho verificato**  
P&L storico, Daily tab, Weekly Report, API weekly.

**Risultato osservato**  
Performance e una delle pagine piu ricche. Daily tab e utile; weekly report offre costi, cash drag, break-even e feedback.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Coerenza dati | Weekly Report mostra pesi correnti/suggeriti con modelli obsoleti (`qwen3.5:397b`, `deepseek-v4-pro`, `glm-5.1`) mentre path corrente e Kimi + GLM-5.2. | Decisioni su pesi LLM potenzialmente sbagliate. | Rigenerare report con registry modelli corrente; marcare report come stale se contiene modelli retired. |
| P2 | UX | P&L storico e Daily P&L possono divergere per fonti diverse, ma la spiegazione e solo in documentazione. | Confusione su numeri di P&L. | Inserire microcopy vicino ai tab: "Historical = Alpaca equity; Daily = local closed trades". |

### Strategies

**Scopo atteso**  
Mostrare strategie, lifecycle, autorizzazione, gate, backtest/live source e parametri.

**Cosa ho verificato**  
Strategy selector, badges authorization, warning, KPI, equity curve, gates, sensitivity.

**Risultato osservato**  
La pagina contiene molte informazioni corrette e importanti, inclusi promotion blocked e warning.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | Visual | Titolo `Strategies` e bianco su background chiaro, quasi invisibile. | Orientamento visivo compromesso. | Usare `var(--text)` oppure container dark coerente. |
| P2 | UX | Molte metriche storiche/backtest convivono con badge LIVE e warning; serve piu separazione. | Rischio di interpretare backtest come autorizzazione. | Separare sezioni "Runtime status" e "Historical evidence"; default focalizzato su S4 paper evidence. |
| P2 | Tecnico | Console Recharts segnala width/height -1 in Strategy chart. | Rischio chart non renderizzata in alcuni layout. | Impostare dimensioni stabili e verificare ResponsiveContainer con parent width. |

### Auto-Improve

**Scopo atteso**  
Monitorare feedback gate Phase B e counterfactual Phase C per capire se i filtri stanno aiutando o bloccando edge.

**Cosa ho verificato**  
Feedback status API, Phase B active state, Phase C empty state, helper.

**Risultato osservato**  
La pagina ha ancora senso. Phase B e attiva: threshold 0.35, baseline 0.30, regime scale 0.80 legacy, rolling P&L -40.39. Phase C e vuota per assenza di skip data processati.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | Naming/prodotto | "Auto-Improve" promette miglioramento automatico, ma oggi e soprattutto monitor/audit del feedback gate. | Aspettativa eccessiva sull'autonomia del sistema. | Valutare label "Feedback Gate" o "Adaptive Gate" nel menu, mantenendo docs su Phase B/C. |
| P2 | UX | Phase C vuota non mostra ultima esecuzione worker o se il worker ha girato. | Non si capisce se e vuota per assenza dati o worker fermo. | Mostrare last counterfactual-worker run, count SKIP_THRESHOLD raw, next run attesa. |
| P2 | Decision support | Non c'e soglia per "attivo da troppo tempo". | Operatore deve ricordare il runbook. | Alert se active >24h senza recovery e link a Signals/Performance. |

### LLM

**Scopo atteso**  
Mostrare output grezzo modelli e gestione pesi ensemble.

**Cosa ho verificato**  
Feedback tab, Weights tab, API `/api/weights/current`.

**Risultato osservato**  
Feedback modelli funziona e mostra Kimi/GLM-5.2 recenti. Weights tab non mostra pesi attivi per mismatch schema.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Funzionale/API | Frontend attende `{current, suggested...}`, API `/api/weights/current` restituisce `{weights, source}`. La tab mostra "No pending proposal" e non mostra active weights. | Operatore non vede i pesi realmente live. | Adeguare client a `weights` + chiamare `/api/weights/suggestion`, oppure cambiare API per restituire `current/suggested`. |
| P1 | Coerenza modello | Redis current weights puo contenere modelli non presenti nel set live disponibile via Ollama. | Pesi su modello non attivo o non disponibile, segnale ensemble poco interpretabile. | Introdurre model registry dinamico e validare weights keys contro i modelli live disponibili. |
| P2 | UX | Reasoning troncato senza modal/espansione. | Diagnosi modello incompleta. | Riga espandibile con reasoning completo e link al signal/news. |

### Backtest

**Scopo atteso**  
Valutare potere predittivo storico di score/modelli/ticker.

**Cosa ho verificato**  
Run selector, KPI, bucket analysis, P&L curve, IC by model/symbol.

**Risultato osservato**  
Pagina ricca e utile per quant/dev. Mostra run `alpaca-smallmid-2506`, IC 0.0392, ICIR -0.0035, hit rate 49.43%.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P2 | Visual | Titolo `Backtest Analysis` bianco su background chiaro, quasi invisibile. | Orientamento pagina scarso. | Usare colore testo standard. |
| P2 | Coerenza | IC by Model contiene modelli storici retired (`deepseek`, `glm-5.1`) senza etichetta. | Confusione con modelli live. | Badge historical/retired e filtro current models. |
| P2 | Product | Non interpreta chiaramente che IC 0.039 < soglia 0.05 e hit rate <50% non supportano promozione. | Utente potrebbe vedere grafici belli ma non capire esito. | Banner verdict: "Not enough evidence for promotion" con soglie. |

### Dashboard / Monitoring

**Scopo atteso**  
Monitor live per overview, risk e decay.

**Cosa ho verificato**  
Overview iframe, tab Risk Monitor, Decay Monitor, console errors, docs helper.

**Risultato osservato**  
Overview dashboard si renderizza. Durante l'interazione sono emersi errori Grafana: `Datasource alembic-pg was not found`. Dopo la decisione prodotto, Grafana non deve rimanere una superficie frontend: i summary React devono diventare il monitor primario.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Prodotto/funzionale | Grafana embed resta nel frontend ma non e piu la direzione prodotto; inoltre Decay dipende da datasource errato. | Monitoring rotto e superficie ridondante. | Eliminare la pagina/iframe Grafana dal frontend e sostituire con summary React nativi. |
| P1 | Responsive | Grafana embed e illeggibile su mobile: pannelli tagliati e legenda/grafici compressi. | Monitoring mobile non usabile. | Mobile solo read-only/status con card native. |
| P2 | Docs/helper | Helper dice credenziali admin/admin e parla di Grafana come superficie utente. | Istruzioni fuorvianti. | Rimuovere dal frontend helper utente; tenere eventuali istruzioni Grafana solo in docs tecniche di ops. |

### Docs / Helper online

**Scopo atteso**  
Guida integrata coerente con UI e stato corrente.

**Cosa ho verificato**  
Pagina Docs, HelpButton globale e helper per pagine principali, confronto con docs Markdown.

**Risultato osservato**  
L'helper e utile ma non sempre allineato. La pagina Docs e lunga e informativa, ma contiene riferimenti non piu corrispondenti al menu.

**Problemi trovati**

| Priorita | Tipo | Problema | Impatto | Raccomandazione |
|---|---|---|---|---|
| P1 | Gap docs/prodotto | User guide cita `Trades -> Analytics`, ma la pagina Trades non e nel menu ne nelle route attive. | Utente segue istruzioni impossibili. | Aggiornare guida: analytics ora sono in Performance/Trading o ripristinare route Trades. |
| P1 | Gap docs/modelli | Docs citano modelli statici, ma l'API Ollama puo cambiare disponibilita nel tempo. | Confusione operativa e rischio config errata. | Centralizzare model registry dinamico nei backend endpoint e generare UI/docs da quello. |
| P2 | Struttura | User guide dice 10 sezioni, menu ne mostra 15. | Guida percepita stale. | Aggiornare indice e ordine secondo sidebar. |
| P2 | UX contenuti | Docs e helper sono molto lunghi e tecnici, poco contestuali al task attuale. | Operatore deve leggere troppo. | Dividere in "What this page answers", "When to act", "Runbook links". |

## 4. Review dei flussi principali

### Flusso 1 — Morning health check

Obiettivo: capire se il sistema puo operare in paper durante la sessione.

Passaggi attuali: Overview -> Operations/System -> Signals -> Trading -> Performance/Validation.

Punti forti: Overview concentra molte metriche; Operations mostra scheduler e kill switch; banner readiness e market-aware.

Attriti:

- menu mette LLM prima di Signals;
- System richiede tab manuali per activity/PEAD;
- Quality/Validation non danno verdict operativo;
- mobile inutilizzabile.

Miglioria proposta: creare una checklist compatta in Overview: infra OK, market window, latest signal/cycle, active gate, open exposure, last order, quality status.

### Flusso 2 — Capire da una news a un ordine

Obiettivo: partire da una notizia e verificare ticker estratto, sentiment, signal, decisione e order.

Passaggi attuali: News filtro ticker -> Signals -> Decision Log -> Trading Orders -> LLM/Quality se serve.

Attriti:

- nessun cross-link da News a signal;
- nessun cross-link da Signal a news/LLM response;
- Decision Log spiega bene i BUY/SELL ma e separato;
- Trading Fills non e affidabile come storico esecuzioni.

Miglioria proposta: introdurre una drawer "Signal trace" con news source, extracted ticker, model outputs, aggregate score, gate decision, order/fill.

### Flusso 3 — Validare qualita ticker/sentiment

Obiettivo: capire se S4 produce segnali affidabili.

Passaggi attuali: Quality -> Labeling -> Backtest -> Strategies.

Attriti:

- Quality mostra problemi seri ma senza CTA;
- Labeling puo salvare label incoerenti;
- Backtest non mostra verdict forte su IC sotto soglia;
- modelli storici e correnti mescolati.

Miglioria proposta: dashboard Quality con semaforo e "next best action": annotate N more, inspect false positives, freeze promotion, regenerate backtest.

### Flusso 4 — Gestione rischio/amministrazione

Obiettivo: fermare/riprendere il sistema o cambiare configurazione.

Passaggi attuali: Admin/Operations -> Config/Admin.

Punti forti: kill switch ha conferma e recovery token; full_auto disabilitato.

Attriti:

- operating mode cambia con un solo click;
- config symbol non validato;
- Admin label e title Operations non perfettamente allineati.

Miglioria proposta: modal di conferma per mode change, validazione ticker, audit trail visibile delle ultime modifiche admin/config.

### Flusso 5 — Auto-Improve / Feedback gate

Obiettivo: capire se il sistema sta stringendo la soglia e se i filtri perdono opportunita.

Passaggi attuali: Auto-Improve -> Signals/Decision Log -> Performance.

Valutazione: la funzione ha ancora senso, ma non come "auto improve" generico. Oggi e un monitor di adaptive gate e counterfactual. Va mantenuta, ma con naming e verdict piu precisi.

## 5. Gap tra documentazione, helper online e frontend

| Area | Gap | Impatto | Raccomandazione |
|---|---|---|---|
| User guide | Dice che la dashboard ha 10 sezioni; sidebar ne ha 15. | Guida stale. | Aggiornare indice e ordine menu. |
| User guide / Docs | Cita `Trades -> Analytics`, ma route/menu Trades non sono attivi. | Istruzioni impossibili. | Rimuovere o ripristinare pagina Trades. |
| Modelli LLM | Docs/API citano Qwen/DeepSeek/GLM-5.1; worker corrente usa Kimi + GLM-5.2; Quality/Backtest mostrano modelli storici senza label. | Rischio decisioni e config errate. | Model registry unico e badge current/retired. |
| Sidebar toggle | UI dice Full ensemble/4 models e Economy GLM; worker accetta `glm52`. | Toggle potenzialmente inefficace. | Allineare valori e copy. |
| Dashboard | Helper credenziali/admin e datasource non coerenti; Grafana non e piu superficie frontend desiderata. | Monitoring rotto/fuorviante. | Rimuovere Grafana dal frontend e creare summary React nativi. |
| S4 status | Alcune docs parlano di S4 prevista/refactor; UI/API la mostrano paper promotion_blocked. | Stato prodotto ambiguo. | Aggiornare docs al lifecycle corrente. |
| Frontend operator guide | Inventory parla di 16 pagine, include Trading con mode/killswitch e Trades, non rispecchia menu attuale. | Mappa frontend non affidabile. | Rigenerare inventory da route/sidebar. |

## 6. Problemi principali ordinati per priorita

| Priorita | Area | Problema | Impatto | Raccomandazione | Sforzo |
|---|---|---|---|---|---|
| P1 | Dashboard | Decay dashboard usa datasource `alembic-pg` inesistente. | Monitor decay rotto. | UID `alembic-postgres`, verificare query. | Basso |
| P1 | LLM | Weights tab attende schema API sbagliato. | Pesi live non visibili. | Allineare client/API e aggiungere suggestion endpoint. | Medio |
| P1 | LLM/Menu | Economy toggle invia `glm`, worker accetta `glm52`. | Risparmio quota/costi non effettivo. | Allineare Economy a GLM-5.2 con valore backend/worker riconosciuto. | Basso |
| P1 | Trading | Fills non mostra veri fill. | Dati esecuzione fuorvianti. | Usare orders filled o endpoint fills. | Medio |
| P1 | Responsive | Mobile/tablet stretto non usabili. | Blocca uso fuori desktop. | Sidebar drawer + tabelle responsive. | Medio/Alto |
| P1 | Labeling | Salvataggio label incoerenti consentito. | Golden set e metriche contaminate. | Validazioni semantiche prima del submit. | Basso |
| P1 | Docs | Guida cita pagine/modelli/stati non correnti. | Perdita fiducia e istruzioni errate. | Aggiornamento docs impattate. | Medio |
| P1 | Admin | Cambio mode immediato su radio click. | Errore operativo possibile. | Conferma mode change e audit feedback. | Basso |
| P2 | Quality | Metriche critiche senza verdict/CTA. | Difficile agire su degradazione. | Soglie + action hints. | Medio |
| P2 | News/Signals | Nessuna trace news -> signal -> decision -> order. | Diagnosi lenta. | Drawer trace/cross-link. | Medio |
| P2 | Strategies/Backtest | Titoli bianchi su fondo chiaro. | Orientamento compromesso. | Colore testo standard. | Basso |
| P2 | Backtest | IC sotto soglia non tradotto in verdetto. | Rischio interpretazione troppo ottimista. | Banner verdict promotion evidence. | Basso |
| P2 | Help/accessibilita | Help drawer senza role/focus trap/Escape; bottoni iconici senza aria. | Accessibilita base insufficiente. | Aggiungere semantica dialog e aria-label. | Medio |
| P2 | News | 200 righe senza priorita/paginazione. | Carico cognitivo alto. | Pagination/virtualizzazione e filtri actionable. | Medio |

## 7. Quick wins

| Problema | Soluzione proposta | Impatto atteso | Sforzo |
|---|---|---|---|
| Titoli Strategies/Backtest invisibili | Cambiare `color: white` in `var(--text)`. | Orientamento immediato. | Basso |
| Dashboard Decay rotta | Sostituire UID datasource `alembic-pg` con `alembic-postgres`. | Ripristina monitor. | Basso |
| Economy toggle inefficace | Payload `glm52` o alias backend `glm`. | Risparmio quota/costi reale. | Basso |
| Labeling incoerente | Validare relevance/ticker/direction/strength. | Golden set piu affidabile. | Basso |
| Admin mode pericoloso | Modal conferma per cambio mode. | Riduce errori operativi. | Basso |
| LLM weights vuota | Mappare `weights` API a `current` e aggiungere fetch suggestion separato. | Pesi live visibili. | Basso/Medio |
| Quality senza azioni | Aggiungere CTA sotto KPI critici. | Migliore decision support. | Basso |
| Docs cita Trades | Rimuovere/rindirizzare riferimenti a Trades. | Riduce confusione. | Basso |
| Dashboard/Grafana | Rimuovere superficie Grafana dal frontend e sostituirla con summary React primari. | Evita dipendenza da iframe/datasource e chiarisce la UX. | Medio |
| News troppo lunga | Default limit 50 + filtro "with signal". | Scan piu veloce. | Medio |

## 8. Suggerimenti strategici di prodotto e UX

1. Introdurre una vista "Signal Trace" come oggetto centrale del prodotto: news, ticker evidence, model outputs, aggregate signal, gate, decision, order/fill. Questo riduce il salto manuale tra News, LLM, Signals, Trading.

2. Separare chiaramente "runtime state" da "historical evidence". Strategies, Backtest e Performance mischiano spesso live, paper, backtest e report storici. Ogni pagina dovrebbe dire: fonte dati, data aggiornamento, validita decisionale, cosa autorizza/non autorizza.

3. Trasformare metriche critiche in verdict. Quality e Backtest non devono solo mostrare numeri: devono dire "promotion blocked", "needs more labels", "model retired", "edge not significant".

4. Rivedere naming Auto-Improve. La pagina e utile, ma il nome promette un'ottimizzazione automatica piu ampia. "Feedback Gate" o "Adaptive Gate" sarebbe piu preciso.

5. Generare documentazione operativa dalla configurazione viva dove possibile: route/sidebar inventory, model registry dinamico e strategy lifecycle. Molti gap derivano da docs scritte manualmente che inseguono il prodotto.

6. Rendere desktop la baseline e mobile una modalita ridotta ma funzionante. Per un cockpit operativo non serve replicare tutte le tabelle su mobile: bastano status, alert e azioni critiche eventualmente confermate.

## 9. Valutazione finale

| Dimensione | Voto 1-5 | Motivo |
|---|---:|---|
| Chiarezza dello scopo | 4 | Overview e Docs comunicano bene il principio LLM offline/execution separata. |
| Completezza informativa | 4 | Molti dati importanti sono presenti. Mancano trace e verdict azionabili. |
| Facilita di navigazione | 3 | Menu completo ma ordine migliorabile e Admin/Operations ambiguo. |
| Qualita dei flussi principali | 3 | Flussi possibili ma richiedono conoscenza del dominio e molti passaggi. |
| Coerenza visuale | 3 | Buona base, ma titoli invisibili e dark/light non sempre coerenti. |
| Coerenza funzionale | 3 | Core pages funzionano; LLM weights, Fills e Dashboard Decay sono problemi reali. |
| Gestione errori/stati limite | 2 | Empty state presenti, errori spesso generici, loading minimale, pochi recovery hints. |
| Accessibilita | 2 | Mancano semantica dialog/tab, aria-label e supporto tastiera robusto. |
| Responsive design | 1 | Mobile non usabile per tabelle/monitoring e sidebar fissa. |
| Fiducia trasmessa all'utente | 3 | Buoni warning safety, ma docs stale e dati LLM/weights incoerenti riducono fiducia. |
| Aderenza alla documentazione | 2 | Mismatch importanti su pagine, modelli, Trades, dashboard e lifecycle. |
| Prontezza per utenti reali | 2 | Adeguato per uso interno tecnico, non per utenti reali esterni. |

Giudizio complessivo: **utilizzabile solo internamente**. Non pronto per produzione o beta non presidiata. Dopo la chiusura dei P1 puo essere considerato per beta user tecnici.

## 10. Domande aperte

Le domande principali emerse dalla review sono state risolte nelle "Decisioni prodotto confermate" in sezione 2. Restano aperti solo dettagli di implementazione:

1. Quale endpoint deve esporre il model registry dinamico per il frontend: estendere `/api/admin/status`, aggiungere `/api/llm/models`, o leggere una config esistente?
2. Dopo la rimozione di Grafana dal frontend, quali metriche minime devono comporre i summary React di monitoring: risk, decay, readiness, model health, costi?
3. Gli analytics mancanti da `Trades.tsx` vanno portati in `Performance`, in `Trading`, o in una nuova tab nativa "Analytics" dentro `Performance`?
4. Per mobile read-only/status, quali azioni restano consentite: logout soltanto, o anche kill switch/admin emergency?
5. Per Auto-Improve Phase C, esiste gia una fonte backend affidabile per last run e raw skip counts o va aggiunto un endpoint dedicato?
