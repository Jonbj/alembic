# Audit — “I Love Swing Trading. I Hated Running It. So I Built a Machine That Does It for Me.”

**Data:** 2026-09-14  
**Articolo:** Willow the Trader, 1 settembre 2026 ([testo](https://medium.com/@techacademies/i-love-swing-trading-i-hated-running-it-so-i-built-a-machine-that-does-it-for-me-e0972687ca03))  
**Metodo:** verifica dei claim metodologici contro fonti primarie e confronto con codice, audit e
issue Alembic. Nessuna performance è stata replicata: l'articolo non fornisce dati, repository,
commit, specifiche versionate o URL del record live necessari a farlo.

## Verdetto

È uno degli articoli retail più disciplinati esaminati: dichiara lo screening, conserva i fallimenti,
usa next-open, cerca dati PIT, fa un test di dipendenza dal miglior trade e congela un giudizio
forward. Ma **non è ancora una validazione indipendente di v1.4**. Ogni nuova versione nasce dopo
aver osservato i risultati della precedente; i ticker “holdout” condividono gli stessi anni e regimi;
habitat growth, indice, filtro qualità, top-20, cap a cinque slot e size/liquidity floors sono stati
scelti usando l'intera catena di risultati storici.

La sola evidenza realmente nuova per v1.4 è quindi il forward record iniziato dopo il freeze. Il
backtest storico è utile come sviluppo/falsificazione, non come conferma dell'edge. La pagina pubblica
può migliorare accountability, ma non è auditabile dall'esterno sulla sola base dell'articolo.

**Per Alembic:** non aprire una nuova issue. Le correzioni necessarie sono già quasi integralmente
specificate in `#84`, `#171`, `#31/#65`, `#438` e `#565`. L'articolo è una buona checklist narrativa,
non una nuova campagna alpha.

## 1. Freeze e screening di quasi 3.000 varianti

| Claim | Valutazione |
|---|---|
| “Ho congelato v1.0 prima di testarla” | **Vero in senso limitato:** il candidato era congelato prima dei 18 nuovi ticker, ma nasceva da osservazioni 2026 e da circa 3.000 varianti su quattro nomi. È preregistrazione della fase successiva, non della scoperta. |
| “Il migliore barely cleared chance” | Intuizione corretta, ma senza distribuzione dei 3.000 trial, correlazione fra varianti, metrica primaria e codice non è verificabile. Il numero effettivo dei trial va conservato. |
| “Ogni versione successiva è frozen” | Il freeze impedisce tuning *dentro* quel test; non rende nuovi i dati già letti. v1.1 usa l'autopsia 2022 di v1.0; l'habitat growth usa il fallimento sui settori difensivi; v1.4 usa il falsification harness per scegliere membership, top-20 e filtri. |

[White (2000)](https://doi.org/10.1111/1468-0262.00152) definisce data snooping proprio come
riuso degli stessi dati per selezione/inferenza e testa il miglior modello dell'intera specification
search. Il [Deflated Sharpe Ratio](https://doi.org/10.2139/ssrn.2460551) corregge selection bias e
non-normalità, mentre [Harvey, Liu e Zhu](https://www.nber.org/papers/w20592) mostrano che una nuova
anomalia finanziaria richiede hurdle molto più alto del t convenzionale (circa `|t| > 3`).

Protocollo corretto: ledger immutabile di tutti i 3.000+ trial e delle modifiche v1.0–v1.4;
metriche/costi/split fissati; Reality Check/DSR sul catalogo completo; holdout temporale sigillato
mai visto prima dalla versione finale. Il live forward già avviato può svolgere quest'ultimo ruolo.

## 2. Holdout per ticker non è holdout temporale

I primi 18 ticker non visti testano trasporto ad altri nomi **dentro gli stessi shock di mercato**.
I successivi 18 difensivi testano un altro dominio e scoprono che la regola non vi si trasferisce.
Sono analisi utili, ma non osservazioni indipendenti: i titoli condividono 2020, 2022 e 2025,
fattori, correlazioni e condizioni di liquidità. Dopo aver usato quel fallimento per restringere il
dominio ai growth names, il campione non può anche confermare la restrizione.

Un holdout per ticker risponde “generalizza cross-section nello stesso passato?”; un holdout per
tempo risponde “generalizza al futuro?”. Per un sistema regime-sensitive servono entrambi, con il
tempo come test finale. Il doppio portafoglio live è quindi più informativo del backtest, purché
criteri, roster e regole siano davvero bloccati e tutti i risultati restino visibili.

## 3. Universo, index membership e survivorship

“Membro di un major growth index” è una regola riproducibile solo specificando indice, versione
della metodologia, date effettive di add/remove e fonte storica. Per esempio il
[Nasdaq-100](https://indexes.nasdaq.com/docs/Methodology_NDX.pdf) ricostituisce la membership e
applica criteri a reference/effective dates; Nasdaq conferma annual reconstitution e quarterly
rebalance ([product guide](https://www.nasdaq.com/docs/nasdaq-100-index-product-guide)). Usare la
lista corrente retroattivamente lascia solo i survivor.

Il requisito PIT minimo è:

1. membership `valid_from/valid_to` disponibile al decision timestamp;
2. security master permanente, ticker reuse/cambi simbolo e corporate actions;
3. IPO con history locale, delisting e delisting return; nessun forward-fill pre-listing;
4. ranking volatility, size e liquidity calcolato solo con dati già arrivati alla rebalance date;
5. rimozioni intra-anno trattate con regola congelata, non facendo sparire il titolo.

[Shumway (1997)](https://doi.org/10.1111/j.1540-6261.1997.tb03818.x) mostra che omissioni dei
delisting returns distorcono soprattutto portafogli di titoli piccoli/distressed. È direttamente
rilevante perché il primo ranking di volatilità selezionava cruise, airline e nomi terminal-risk.
L'affermazione “PIT checks looked beautiful” non è verificabile senza manifest e dataset storico.

## 4. Volatility top-20, qualità ed extreme winners

Il falsification harness ha prodotto una diagnosi plausibile: raw volatility seleziona distress.
La letteratura non giustifica però high-vol come premio positivo: [Ang, Hodrick, Xing e Zhang
(2006)](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2006.00836.x) trovano rendimenti
medi molto bassi per azioni ad alta volatilità idiosincratica. L'index membership può ridurre junk,
ma incorpora size/listing/reconstitution e non equivale economicamente a “credible business”.

Il risultato dipende dichiaratamente da pochi +60%/+1.000% winner. È compatibile con la forte
positive skew delle singole azioni: [Bessembinder (2018)](https://doi.org/10.1016/j.jfineco.2018.06.004)
trova che il miglior 4% spiega la creazione netta di ricchezza del mercato USA. Ma questo non prova
l'edge: un book di soli cinque slot può perdere il raro winner per rumore di ranking o fill.

Servono almeno: quota P&L top-1/top-5, leave-one-name/year-out, median trade, payoff ratio,
block-bootstrap per cluster temporali, probabilità di mancato winner, drawdown/expected shortfall e
confronto con un benchmark growth-index investibile. “Togli il miglior trade” è un buon inizio, non
una misura completa di robustezza delle code.

## 5. “Arrival order is information”

Il confronto 5 vs 8/10 slot è stato eseguito durante la finalizzazione dopo aver visto
oversubscription e performance. Dimostra che, su quei test, aggiungere segnali tardivi peggiorava;
non identifica causalmente l'arrival order. È confuso con intensità del segnale, ticker, liquidità,
timestamp/bar alignment, numero di slot libero e dimensione posizione.

Prima di chiamarlo alpha occorre congelare: tie-break, timestamp di ogni timeframe, gestione segnali
simultanei, universo e costi; poi confrontare `first-arrival` contro ranking preregistrati e random
allocation su un nuovo periodo. La regola first-come può restare come ipotesi v1.5; non va attribuita
retroattivamente alla prova v1.4.

## 6. Next-open fills e costi

Usare il prossimo open dopo un segnale calcolato a close è corretto e migliore del same-bar fill.
Ma “ogni fill books at the next session's open” richiede coerenza fra ordine live e dato backtest.
Le [docs Alpaca](https://docs.alpaca.markets/docs/orders-at-alpaca) distinguono MOO/LOO: cutoff,
primary-exchange auction, cancellazione degli unfilled e prezzo regolato dalle auction rules. Un
market order ordinario o il paper broker non garantiscono l'official open.

L'articolo non pubblica cost model o risultati dello stress. Vanno inclusi spread/auction slippage,
market impact vs ADV, partial/rejected fills, gaps, latency webhook, split/dividend adjustment e
2× cost stress. Per score 4h/daily/weekly ogni barra deve essere chiusa e disponibile prima del
decision timestamp; altrimenti next-open non elimina il lookahead della feature.

## 7. Record pubblico e auditabilità

Pubblicare ogni trade e drawdown è positivo, ma la pagina è descritta come riservata a utenti
registrati e l'articolo non fornisce URL, spec v1.0–v1.4, repository, commit, raw fills, data manifest
o checksum. “Ogni numero traces to a version-controlled script” è quindi un'attestazione, non una
replica. Una pagina modificabile giornalmente non prova da sola che record o criteri non siano stati
riscritti.

Un record auditabile richiede release/spec timestampata prima del primo trade, append-only event
log, broker order/fill IDs riconciliati, snapshot giornalieri firmati/hashati, revision history,
dataset provenance e pubblicazione anche di reject/cancel/data-failure. Il giudizio va computato da
un evaluator separato sul criterio congelato.

## 8. Confronto stretto con Alembic e duplicati

| Tema | Alembic oggi | Implicazione |
|---|---|---|
| Preregistrazione e holdout | `#84` prescrive manifest, PIT 1998–2025, walk-forward fino al 2022, holdout 2023–2025 aperto una volta, trial registry e review indipendente. `#171` congela cinque confermative, `|t|≥3` con Holm e vieta tuning live. | L'articolo conferma la direzione; **nessuna nuova issue**. |
| PIT/survivorship | `#84` richiede membership/eligibility a ogni rebalance, delisting, corporate actions, security master e golden synthetic PIT test. Gli audit S1/S3 documentano ancora universe/lookahead non risolti. | “Index members only” non è una scorciatoia: serve completare `#84`. |
| Backtest/gate | `src/backtest/` ha next-open, cost model, walk-forward e cinque gate (significance/DSR, robustness, regime, stress), ma `GateConfig.n_trials` ha default `1`; `#84` impone trial count reale e 2× costs. | Alembic ha un harness più forte sulla carta, ma non deve scambiare presenza del codice per evidenza valida. |
| Stop | `#31` tiene il vol-scaled stop flag-off dopo replay OOS sottile; nessun flip senza shadow e PO. | Il two-strikes breaker dell'articolo è un'ipotesi post-hoc, non un motivo per cambiare stop. |
| Winner dependence/cap | `#65` ha già rilevato che 11/118 trade producono più dell'intero netto e avverte che take-profit può tagliare i winner; copre anche rebalance e correlation-aware sizing. | Duplicato diretto della lezione “non tagliare i monster trades”. |
| Execution evidence | `#438` registra che lo slippage live non è misurato correttamente. | Chiudere questa evidenza prima di accettare parity backtest/live. |
| Immutabilità | `#565` documenta serie “frozen” riscritte da rerun. | Il bisogno di append-only/hash è già un finding concreto, non una nuova idea. |

## Raccomandazione

Non creare una campagna “swing machine”. Se interessa il pattern, archiviarlo come ipotesi futura,
senza consumare il holdout di `#84` e senza modificare il programma congelato `#171`. Il contributo
utile dell'articolo è procedurale: pubblicare fallimenti, separare discovery da judgment e usare
forward data. La correzione necessaria è più severa: **v1.4 parte statisticamente da zero alla data
del freeze; il suo esito vive nel record forward, non nel backtest che l'ha generata.**
