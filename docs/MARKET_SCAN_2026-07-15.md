# Market Scan — Progetti Pubblici Simili (2026-07-15)

**Executive summary:** esistono diversi progetti open-source LLM+trading attivi e ben documentati (TradingAgents, FinGPT, e alcuni progetti più piccoli su Alpaca+Backtrader+sentiment). Nessuno replica esattamente l'architettura specifica di questo progetto (LLM rigorosamente offline in un worker background, esecuzione separata che legge segnali pre-calcolati da Redis/Postgres, risoluzione ticker deterministica separata dal sentiment, golden-label-set come gate di misurazione prima dell'enforcement) — questi ultimi tre punti sembrano pratiche più rigorose/specifiche di quanto si trovi comunemente nominato in questi repo. La collaborazione più realistica è di tipo "consumer/contributor" verso FinGPT (già referenziato in CLAUDE.md) o studio architetturale di TradingAgents (community enorme, canali attivi), non una fusione di codebase.

---

## Progetti trovati

### 1. TauricResearch/TradingAgents
- **URL:** https://github.com/TauricResearch/TradingAgents
- **Licenza:** Apache-2.0
- **Stelle:** ~93.1k, 18k fork — di gran lunga il progetto più popolare del genere trovato
- **Ultimo rilascio:** v0.3.1 (2026-07-05, Alpha Vantage filtering + supporto Claude Sonnet 5) — attivissimo
- **Architettura:** framework multi-agente su LangGraph. Team di analisti (fondamentali, sentiment, news, tecnico) lavorano in parallelo, poi un team researcher bull/bear dibatte, un trader agent sintetizza, infine risk management/portfolio manager approvano. Le fasi di analisi sembrano girare offline/asincrone rispetto all'esecuzione finale, ma il pattern è "pipeline di agenti dentro un grafo", non "worker background scrive su Redis/Postgres, executor separato legge al tick" — somiglianza di **principio** (analisi separata da esecuzione), non di meccanismo.
- **Supporto locale:** sì, Ollama supportato con profilo Docker dedicato.
- **Community:** Discord attivo, 147 issue aperte, CONTRIBUTING.md, canale WeChat/X. Canale di contatto realistico e maturo.
- **Fonte:** repo GitHub verificato direttamente (README, releases, community links).

### 2. AI4Finance-Foundation/FinGPT
- **URL:** https://github.com/AI4Finance-Foundation/FinGPT
- **Licenza:** MIT
- **Stelle:** ~20.9k, 689 commit, aggiornamenti recenti (2024-2025) — già referenziato in `CLAUDE.md` come riferimento del progetto attuale.
- **Architettura:** piattaforma a 5 livelli (data source → data engineering → LLM fine-tuned via LoRA su modelli open — Llama-2, Falcon, ChatGLM2 → task layer sentiment/relation-extraction → application layer). **Non include esecuzione di trading** — è un layer di sentiment/forecasting da consumare, non un sistema end-to-end come questo progetto. FinGPT-Forecaster fa previsione prezzi (DOW30), FinGPT-RAG aggiunge retrieval-augmented generation.
- **Community:** Discord, 79 issue aperte, 17 PR aperte, CONTRIBUTING.md + Code of Conduct.
- **Fonte:** repo GitHub verificato direttamente.
- **Nota:** questo è il progetto con cui una collaborazione ha più senso PRATICO — è un componente (sentiment/forecasting layer) che questo sistema potrebbe consumare o a cui potrebbe contribuire un adapter, non un concorrente diretto.

### 3. risabhmishra/algotrading-sentimentanalysis-genai
- **URL:** https://github.com/risabhmishra/algotrading-sentimentanalysis-genai
- **Licenza:** Apache-2.0
- **Stelle:** 24 — progetto piccolo, singolo mantainer, manutenzione saltuaria
- **Architettura:** stack tecnico sorprendentemente vicino — Alpaca (dati/news) + Backtrader (backtest) + client LLM (OpenAI/Llama) per sentiment, strategie tecnica-pura vs ibrida-con-sentiment. **Nessuna evidenza** di disciplina offline/live, risoluzione ticker deterministica, o golden-label gate — sembra un progetto dimostrativo/di apprendimento, non uno con lo stesso rigore di misurazione-prima-di-enforcement.
- **Fonte:** repo GitHub verificato direttamente.

### 4. Altri progetti minori censiti (non approfonditi in dettaglio — segnalati per completezza)
- `Ronitt272/LLM-Enhanced-Trading` — FinGPT + segnali su 4 strategie tecniche, scala piccola.
- `Hangyul-Son/llm-sentiment-trading-system` — multi-agente per prospettive di sentiment diverse, GPT-based.
- `qrak/LLM_trader` — crypto, vision AI su grafici, dashboard live — dominio diverso (crypto, non equity).
- `AI4Finance-Foundation/FinRL-Trading` (FinRL-X) — piattaforma RL-centrica con preprocessing LLM sentiment, più orientata a reinforcement learning per stock selection che a un pipeline sentiment-driven come questo.

---

## Cosa NON ho trovato

- Nessun progetto pubblico con la stessa combinazione specifica: (a) LLM **mai** nel path di esecuzione live, (b) risoluzione ticker **deterministica separata** dal giudizio del solo LLM, (c) un **golden label set** come gate esplicito di misurazione-prima-di-enforcement per calibrare precision/recall dell'estrazione ticker e la confidence del sentiment. Questi tre punti insieme sembrano una pratica di rigore ingegneristico più specifica di quanto emerga nei repo pubblici surveyed — non è detto che non esista, ma non è emerso nelle ricerche mirate fatte.
- Nessun academic-paper-con-repo-companion trovato che implementi esattamente il pattern "DK-CoT + ensemble + fallback locale + golden label calibration" insieme; il DK-CoT come termine specifico compare in letteratura accademica (framework proposto per financial news sentiment) ma senza un'implementazione open-source companion diretta trovata.

---

## Valutazione e raccomandazione

1. **FinGPT** è il candidato più concreto per una collaborazione reale: licenza permissiva (MIT), community attiva con canali chiari (Discord, issue, PR), e un ruolo complementare (componente di sentiment) piuttosto che concorrente. Un contributo realistico sarebbe: usare/valutare i loro modelli fine-tuned come ulteriore candidato "shadow" nel confronto Stage-2 già esistente in questo progetto, o contribuire indietro un adapter se si trova valore.
2. **TradingAgents** vale uno studio architetturale (93k star = validazione di mercato enorme del pattern multi-agente), ma la sua architettura (agenti-in-un-grafo-decisionale) è concettualmente diversa dal pattern "alpha miner offline" di questo progetto — una vera integrazione di codice richiederebbe più adattamento che collaborazione diretta.
3. Il resto dei progetti trovati sono più piccoli/dimostrativi e non aggiungono granché oltre a conferma che lo stack (Alpaca+Backtrader+LLM sentiment) è un pattern comune, non un'invenzione isolata.
4. **Non ho trovato ragioni per ritenere che il rigore specifico di misurazione (QX-01 style) di questo progetto sia già risolto altrove** — potrebbe essere un punto di forza/differenziazione da non "diluire" in una collaborazione, più che un gap da colmare guardando fuori.
