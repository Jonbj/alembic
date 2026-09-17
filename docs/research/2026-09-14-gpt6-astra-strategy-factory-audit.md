# Audit — “How to Use GPT-6 Astra to Find Profitable Trading Strategies 24/7”

**Data:** 2026-09-14  
**Oggetto verificato:** versione dell'articolo attribuita a Moonsat e incollata dall'utente,
pubblicata nel settembre 2026  
**Metodo:** confronto claim-per-claim con documentazione ufficiale OpenAI, Moonshot/Kimi e xAI,
paper originali e stato corrente di Alembic. Le pagine commerciali non sono usate come prova di
alpha. Questo documento è una research note; lo stato della roadmap resta nella issue `#21`.

## Verdetto

L'articolo combina **prodotti reali** con una **tesi finanziaria non dimostrata**. GPT-6 Astra,
Kimi K3/K3 Swarm, Kimi Work e Grok Bot hanno davvero contesti lunghi, tool use, lavoro prolungato,
scheduling o coordinamento multi-agent. Non segue però che possano diventare, tramite prompt,
una fabbrica autonoma di strategie profittevoli e live-safe.

La parte utile per Alembic è limitata a due pattern già presenti: generazione di candidati offline
e separazione proposer/reviewer. Le tesi quantitative più concrete sono incomplete o miscitate;
la procedura di validazione proposta soffre di data snooping massivo; il passaggio automatico da
backtest a live contraddice sia le buone pratiche statistiche sia le guide di sicurezza dei prodotti.

**Decisione:** non aprire una nuova issue sulla base dell'articolo e non adottare il suo stack
operativo. Conservare l'articolo solo come spunto non autorevole. Le idee alpha e i controlli sono
già coperti da issue/documenti esistenti; qualsiasi esperimento va innestato lì, offline e con
promozione umana.

## 1. Prodotti e architettura

| Claim dell'articolo | Verifica primaria | Esito |
|---|---|---|
| Astra: 1,05 M token; `$10` input e `$50` output/M token | La [model card ufficiale](https://developers.openai.com/api/docs/models/gpt-6-astra) conferma 1.050.000 token, 128k output e quei prezzi base. Oltre 272k token l'intera richiesta costa 2× input/cache e 1,5× output; Fast costa 2×. | **Vero ma incompleto.** Il budget omette il sovrapprezzo long-context/Fast. |
| Astra “opera broker UI/API direttamente”, senza middleware | Astra supporta computer use, shell, MCP e function calling, ma i tool sono esposti e governati dall'applicazione tramite Responses API; l'integrazione deve gestire credenziali, stato, sandbox, retry e autorizzazioni ([guida modello](https://developers.openai.com/api/docs/guides/latest-model), [computer use](https://developers.openai.com/api/docs/guides/tools-computer-use)). | **Fuorviante.** Capacità di tool use non equivale a connettore broker nativo né ad autorizzazione live. |
| ChatGPT Pro “dà accesso API” ad Astra | Il [quickstart API](https://platform.openai.com/docs/quickstart/make-your-first-api-request) richiede API key e billing/crediti della Platform. L'articolo non documenta che un abbonamento ChatGPT finanzi l'uso API. | **Non dimostrato / operativamente errato.** API e prodotto ChatGPT sono flussi distinti. |
| Pipeline Astra 24/7 a `$200–400/mese` | A listino, `$200` comprano al massimo 20 M token input uncached **oppure** 4 M output, prima di tool, long-context e Fast. Il costo dipende da token, cache, tool calls, retry e frequenza, assenti nell'articolo. | **Non riproducibile.** È un numero promozionale, non un preventivo. |
| Kimi K3: 2,8 T MoE, contesto 1 M, `$3/$15` | La [scheda ufficiale K3](https://www.kimi.com/en/blog/kimi-k3) conferma 2,8 T parametri, 1 M token e `$3` input cache-miss / `$15` output per M token (`$0,30` cache-hit). | **Sostanzialmente vero.** |
| “K3 Swarm Max”, 300 agenti, contesto 1 M *per agente* | Moonshot documenta [Agent Swarm](https://www.kimi.com/en/help/agent/agent-swarm) fino a 300 sub-agent e oltre 4.000 tool call, oggi basato su K3. Non documenta un prodotto ufficiale chiamato “K3 Swarm Max”, 300 stream di mercato persistenti né un budget garantito di 1 M per ciascuno. | **Nucleo vero, interpretazione gonfiata.** 300 è capacità massima per task, non un trading cluster 24/7. |
| Kimi Work offre scheduling e fonti finance native | [Kimi Work](https://www.kimi.com/en/help/kimi-work/overview) è un agent locale beta: usa file/browser, scheduled tasks e database esterni; Moonshot avverte che stabilità e qualità stanno ancora migliorando. Il [Kimi Datasource](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/plugins) offre query finance/news, non garantisce feed PIT, order book, options surface o licenza per trading. | **Parzialmente vero.** Manca il contratto dati necessario al backtest/live. |
| Grok Bot: bot persistenti, paralleli, stesso cloud computer | Le [docs ufficiali](https://docs.x.ai/grok-bot/overview) lo confermano. Tutti condividono computer, filesystem e login: non sono un confine di sicurezza. | **Vero.** |
| Configurare `gpt-6-astra` nei singoli Grok Bot e sincronizzare `/workspace` con Kimi Work | Le [impostazioni Grok Bot](https://docs.x.ai/grok-bot/settings-and-notifications) dicono che la selezione del modello è gestita da Cursor e non c'è model picker. Kimi Work è locale; Grok Bot usa un cloud computer. Non esiste nelle fonti un sync nativo fra i due workspace. | **Non supportato.** Servirebbero orchestratore, storage e identity layer esterni. |
| Validare e mandare automaticamente live | xAI raccomanda least privilege, read-only iniziale e approvazione per invii, acquisti, cancellazioni e produzione ([security guide](https://docs.x.ai/grok-bot/approvals-security-and-privacy)). | **Unsafe e contrario alla guida ufficiale.** |

La frase “nessun middleware” è quindi il principale errore architetturale. Lo stack descritto
richiede almeno: market-data adapters, event-time/PIT store, experiment registry, backtest engine,
cost model, broker adapter, secrets/permissions, osservabilità, kill switch e promotion gate.
Questi componenti sono il sistema finanziario; gli LLM non li sostituiscono.

## 2. Claim finanziari

### Engle–Granger, pairs trading e Ornstein–Uhlenbeck

[Engle e Granger (1987)](https://www.jstor.org/stable/1913236) formalizzano rappresentazione,
stima e test di serie cointegrate. Non introducono Coke/Pepsi, non provano profitto e non sono
“l'inizio dello statistical arbitrage”. Il lavoro empirico classico sul pairs trading è
[Gatev, Goetzmann e Rouwenhorst](https://www.nber.org/papers/w7032), che seleziona coppie per
distanza dei prezzi normalizzati, non per la pipeline inventata dall'articolo.

Stimare uno spread OU è plausibile, ma “theta più alto = trade migliore” è falso come regola:
theta stimato è incerto e instabile; turnover, bid-ask, borrow, slippage, break strutturali e tempo
di esecuzione possono annullare la maggiore velocità di mean reversion. Lo screening di molte
coppie richiede inoltre una correzione per test multipli/FDR.

### Heston e “IV 4%, realized 2%: vendi opzioni”

[Heston (1993)](https://doi.org/10.1093/rfs/6.2.327) deriva un modello stochastic-volatility e
una formula di prezzo per opzioni europee. Non dimostra che `IV > realized volatility` sia
arbitraggio, né che vendere opzioni sia automaticamente profittevole. La differenza incorpora
premi per rischio di volatilità e salto; [Santa-Clara e Yan](https://www.nber.org/papers/w10912)
mostrano che il premio per il rischio implicito nelle opzioni può differire sostanzialmente dal
rischio realizzato.

Il claim “ogni desk usa Heston o una variante” non è verificabile dal paper e non aggiunge
validità. Mancano surface per strike/scadenza, Greeks, smile dynamics, jump/gap risk, margin,
liquidità e costi. Per Alembic l'idea è già nel programma S2/VRP e dipende da dati e infrastruttura
opzioni reali, non da un prompt.

### Fama–French 5-factor: residuo non equivale ad alpha

Il [modello a cinque fattori](https://doi.org/10.1016/j.jfineco.2014.10.010) usa market, size,
value, profitability e investment. In una regressione, **alpha** è l'intercetta non spiegata dal
modello; il **residuo** è lo shock idiosincratico periodo per periodo. Chiamare ogni residuo
“opportunità” confonde i due oggetti. Anche un alpha in-sample può essere errore campionario,
model misspecification o esposizione omessa: serve OOS, costi e correzione per selezione.

### Insider trading: formula e 5,3% non provengono dal paper citato

[Cohen, Malloy e Pomorski (2012)](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2012.01740.x)
classificano ogni insider come *routine* o *opportunistic* dalla sua storia. Il risultato principale
è circa **82 bps/mese value-weighted** per il portafoglio opportunistic; i routine non hanno segnale.
Il paper non propone la formula `(numero di insider che comprano in 5 giorni × valore in dollari)
/ volume medio giornaliero insider`, né una soglia `>3`, né il “5,3% annual alpha”, né l'esempio di tre executive Nvidia prima degli
earnings. Queste cifre sono presentate come derivate dal paper ma non lo sono: è la falsità
bibliografica più grave dell'articolo.

I Form 4 sono in genere depositati entro due business day ([SEC Form 4](https://www.sec.gov/about/forms/form4.pdf)),
ma il backtest deve usare `accepted/filing timestamp`, non transaction date o database ricostruito
oggi. Restatement, amendment, transaction code, 10b5-1, derivative/non-derivative, ownership e
risoluzione CIK→ticker PIT sono essenziali.

## 3. Perché i gate proposti non validano una “strategy factory”

I gate `Sharpe > 1,5`, `t-stat > 2`, hit rate `>55%`, drawdown `<15%` e cinque anni di storia
non correggono il processo adattivo che genera e scarta migliaia di ipotesi. Se si osserva il
risultato di tutti i tentativi e si pubblica il migliore, il t-stat nominale e lo Sharpe sono
selezionati ex post.

- [White's Reality Check](https://doi.org/10.1111/1468-0262.00152) è stato creato proprio per
  verificare se il miglior modello sopravvive al data snooping.
- Il [Deflated Sharpe Ratio](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) corregge
  non-normalità e selection bias dovuto a molte prove. Richiede il **numero effettivo di trial**;
  una swarm che non registra anche i fallimenti rende il calcolo impossibile.
- La [Probability of Backtest Overfitting](https://doi.org/10.21314/JCF.2017.322) mostra perché
  scegliere la configurazione migliore da molti backtest può produrre risultati OOS scarsi.

Un protocollo minimo dovrebbe avere:

1. ledger immutabile di **ogni** ipotesi, prompt, variante, dataset, commit e risultato;
2. dati as-of/PIT, universe delisting-aware e corporate actions; nessun uso retroattivo di revisioni;
3. train/validation walk-forward con purge/embargo, poi holdout finale sigillato e usato una volta;
4. costi, spread, slippage, latency, borrow, capacity, margin e fill rules coerenti con live;
5. DSR/Reality Check o altra family-wise/FDR correction sul catalogo completo dei trial;
6. confronto con baseline semplice e misure con intervalli/blocco-bootstrap, non soli cut-off;
7. paper/shadow trading, canary, kill switch e **approvazione umana** per ogni promozione.

“Maker-checker” e tre fonti sono utili, ma non creano indipendenza quando agenti condividono
modello, prompt, upstream data e metriche. Possono trovare bug; non curano leakage o p-hacking.
Il “primo alert entro sei ore” non è un criterio scientifico e spinge verso selezione opportunistica.

## 4. Confronto con Alembic e duplicati

| Idea dell'articolo | Stato Alembic | Decisione |
|---|---|---|
| Fabbrica autonoma / audit continuo | Esiste già `docs/prompt/Alembic Autonomous Strategy Audit Loop.md`, con workspace persistente, inventario, audit, blocco sui trade live e progress state. | **Duplicato.** Non creare issue piattaforma da questo articolo. |
| Generatore + reviewer multi-agent | Alembic ha ensemble/reviewer e governance human-in-loop (`#36`, `#520/#521`); la separazione LLM/esecuzione è principio architetturale documentato. | Riutilizzare solo come pattern, non come motore decisionale. |
| Pairs/stat-arb | Già consolidato come candidato B1 in `docs/RESEARCH_SYNTHESIS_ALPHA_AND_TOOLING_2026-07-26.md`; backlog alpha `#51`. | Nessuna nuova issue; eventuale scope sotto il backlog esistente. |
| Volatility surface / Heston / VRP | S2 è già auditata; la fattibilità strumento/dati/IBKR è lavoro esistente (`#57` nel programma storico, adapter IBKR dormiente). | Non duplicare; prima chiudere data/instrument feasibility. |
| Fama–French / residual momentum | Già coperto da S1/S3, dal POC PIT `#84` e dalla preregistrazione S1; il repo ha già rilevato il rischio `DSR n_trials` insufficiente. | Inserire solo come variante preregistrata nell'esperimento esistente. |
| Insider opportunistic | Già A3 nella sintesi alpha, ALPHA-B2 nella roadmap dati e S8 nel design; richiede parser Form 4 e storico per routine/opportunistic. | Non aprire una issue “cluster score”: la formula dell'articolo è senza fonte. |
| Backtest/PIT/data snooping | Engine Alembic già include walk-forward, costi e gate, ma gli audit segnalano survivorship/look-ahead e DSR insufficiente; `#84` prescrive universo PIT e A/B preregistrato. | Rafforzare i ticket esistenti; l'articolo non colma i gap. |
| Z.ai / roadmap automation | `#578` integra Z.ai nel **roadmap agent loop**, non nel runtime di trading. | Non confondere automazione di sviluppo con autorità di trading. |

## 5. Raccomandazione finale

Non mettere live la pipeline né affidarle credenziali broker. Non creare una nuova issue: provare
eventualmente i modelli solo come generatori/reviewer read-only dentro `#84`, S2/VRP, `#51` e
A3/S8. Prima di scalarli, serve un registry completo dei trial con DSR/multiple-testing reale.

**Classificazione:** interessante come fotografia del tooling 2026; **non affidabile come guida
quantitativa o operativa**. Il valore per Alembic è confermativo, non incrementale.
