# Ollama Cloud: audit dei modelli per lo sviluppo delle issue Alembic

Data della verifica: 2026-09-15. Fonti: [catalogo Ollama Cloud](https://ollama.com/search?c=cloud), schede modello Ollama, [listino ufficiale](https://ollama.com/pricing), [annuncio del pricing a token](https://ollama.com/blog/transparent-pricing). Il catalogo è stato anche verificato con una richiesta HTTP diretta al sito Ollama. Non sono state usate le descrizioni dei modelli riportate dall'installazione locale. Non è stato eseguito alcun modello: questa è una selezione documentale, non una misura di qualità su Alembic.

## Esito

La configurazione corrente del loop Alembic usa **`minimax-m3:cloud`** per implementazione e review (`scripts/roadmap_agent_loop.sh`, funzioni `esegui_agente` e `esegui_revisore`). Mantenerlo come default fino a un replay accoppiato su issue Alembic. I challenger indipendenti più sensati sono **`kimi-k2.7-code:cloud`** (specializzato coding), **`deepseek-v4-flash:cloud`** (economico e 1M) e **`deepseek-v4-pro:cloud`** (casi difficili). Non sostituire un default operativo sulla base dei soli benchmark pubblicati dal produttore. [Schede MiniMax M3](https://ollama.com/library/minimax-m3), [Kimi K2.7 Code](https://ollama.com/library/kimi-k2.7-code), [DeepSeek Flash](https://ollama.com/library/deepseek-v4-flash), [DeepSeek Pro](https://ollama.com/library/deepseek-v4-pro).

**`glm-5.3-flash:cloud`** è economicamente allettante per task ordinari: 1M di contesto esposto, immagini, tool e thinking; listino $0,15 input / $0,03 cached / $0,50 output per milione di token. La scheda riporta risultati di coding e agentic coding migliori di GLM-5.2, ma sono dichiarazioni del fornitore. Poiché il motore principale è già su z.ai, la famiglia GLM su Ollama **non è appropriata come reviewer indipendente**: può introdurre errori correlati. [Scheda GLM-5.3-Flash](https://ollama.com/library/glm-5.3-flash), [listino](https://ollama.com/pricing).

Se Ollama deve diventare un **secondo giudizio indipendente** su implementazioni o revisioni prodotte da z.ai, il candidato iniziale è **`deepseek-v4-flash:cloud`**: 1M, tool e thinking, $0,22/$0,007/$0,66 a tariffa base. Ha però tariffa di picco doppia dalle 12:00 alle 18:00 UTC nei giorni feriali: $0,44/$0,014/$1,32. Per casi difficili va messo a confronto con **`deepseek-v4-pro:cloud`**, $0,66/$0,022/$1,98 base e tariffa di picco doppia, 1M e tool. [Scheda Flash](https://ollama.com/library/deepseek-v4-flash), [scheda Pro](https://ollama.com/library/deepseek-v4-pro), [listino e fascia di picco](https://ollama.com/pricing).

**MiniMax resta un incumbent da misurare, non da sostituire sulla carta.** `minimax-m2.7:cloud` è 200K, solo testo, tool/thinking, $0,30/$0,06/$1,20. `minimax-m3:cloud` aggiunge immagini e Ollama garantisce 512K, a $0,60/$0,12/$2,40. La scheda M3 parla di supporto fino a 1M dal fornitore, ma il limite operativo pubblicato da Ollama è 512K: usare **512K** per la pianificazione, salvo prova contrattuale diversa. [Scheda M2.7](https://ollama.com/library/minimax-m2.7), [scheda M3](https://ollama.com/library/minimax-m3).

## Inventario pertinente

Tutti i nomi sotto compaiono nel [catalogo Cloud con filtro `c=cloud`](https://ollama.com/search?c=cloud). Prezzi sono input/output per 1M token, a tariffa base dove indicato; consultare [il listino](https://ollama.com/pricing) per cached input e tariffe aggiornate. `:cloud` è il tag di esecuzione mostrato dalle schede; le eccezioni famiglia sono indicate.

| Modello/tag Ollama | Contesto Cloud pubblicato | Input/output USD | Valutazione documentale per Alembic |
|---|---:|---:|---|
| [`glm-5.3-flash:cloud`](https://ollama.com/library/glm-5.3-flash) | 1M | 0,15 / 0,50 | Primo sfidante economico, vision/tool; stesso produttore di z.ai. |
| [`glm-5.3:cloud`](https://ollama.com/library/glm-5.3) | 1M | 1,40 / 4,40 | Candidato per issue difficili; ridondante col motore z.ai già in uso. |
| [`glm-5.2:cloud`](https://ollama.com/library/glm-5.2) | 976K | 1,40 / 4,40 | Versione precedente, non scelta iniziale a parità di prezzo. |
| [`glm-5.1:cloud`](https://ollama.com/library/glm-5.1) | 198K | 1,00 / 3,20 | Versione precedente. |
| [`deepseek-v4.1-flash:cloud`](https://ollama.com/library/deepseek-v4.1-flash) | 1M | 0,15 / 0,60 | Nuovo candidato vision/tool: scheda orientata anche alla ricerca; testare prima di promuovere. Picco 2×. |
| [`deepseek-v4-flash:cloud`, `:0731-cloud`](https://ollama.com/library/deepseek-v4-flash) | 1M | 0,22 / 0,66 | Secondo giudizio economico indipendente. Picco 2×. |
| [`deepseek-v4-pro:cloud`, `:0813-cloud`](https://ollama.com/library/deepseek-v4-pro) | 1M | 0,66 / 1,98 | Secondo giudizio per issue difficili. Picco 2×. |
| [`minimax-m3:cloud`](https://ollama.com/library/minimax-m3) | 512K garantiti | 0,60 / 2,40 | Testare contro MiniMax attuale; vision/tool. |
| [`minimax-m2.7:cloud`](https://ollama.com/library/minimax-m2.7) | 200K | 0,30 / 1,20 | Incumbent possibile, testo/tool. |
| [`kimi-k2.7-code:cloud`](https://ollama.com/library/kimi-k2.7-code) | 256K | 0,95 / 4,00 | Alternativa specializzata coding, vision/tool; rapporto costo/contesto meno favorevole. |
| [`kimi-k2.6:cloud`](https://ollama.com/library/kimi-k2.6) | 256K | 0,95 / 4,00 | Predecessore a pari prezzo. |
| [`kimi-k3:cloud`](https://ollama.com/library/kimi-k3) | 1M | 3,00 / 15,00 | Forte claim agentic, ma costo da riservare a esperimenti difficili. |
| [`nemotron-3-ultra:cloud`](https://ollama.com/library/nemotron-3-ultra) | 256K | 0,10 / 3,00 | Claim 1M nella readme, ma Ollama espone 256K; costo output alto. |
| [`nemotron-3-super:cloud`](https://ollama.com/library/nemotron-3-super) | 256K | 0,015 / 0,60 | Budget challenger possibile; non prima scelta senza eval locale. |
| [`nemotron-3-nano:30b-cloud`](https://ollama.com/library/nemotron-3-nano) | 1M | 0,06 / 0,24 | Task piccoli, non issue complesse. |
| [`qwen3.5:cloud`, `:397b-cloud`](https://ollama.com/library/qwen3.5) | 256K | 0,60 / 3,60 per 397b | Candidato diverso; attenzione a distinguere tag locale da cloud e prezzo della variante. |
| [`gemma4:cloud`, `:31b-cloud`](https://ollama.com/library/gemma4) | 256K | 0,14 / 0,40 | Famiglia di tag, non un singolo modello; più utile come baseline economica. |
| [`mistral-large-3:675b-cloud`](https://ollama.com/library/mistral-large-3) | 256K | 0,50 / 1,50 | Alternativa generale multimodale, senza claim specifici sufficienti per prima scelta. |
| [`gpt-oss:20b-cloud`, `:120b-cloud`](https://ollama.com/library/gpt-oss) | 128K | 0,07 / 0,30 (20b), 0,15 / 0,60 (120b) | Baseline tool/thinking, ma contesto più stretto. |

La tabella non è una graduatoria di qualità: i costi e i limiti sono osservabili, mentre la capacità su Alembic resta da misurare. Nell'esempio di **100K input + 20K output non cached**, il costo teorico a tariffa base è circa $0,025 per GLM-5.3-Flash, $0,035 per DeepSeek-V4-Flash, $0,054 per MiniMax M2.7, $0,106 per DeepSeek-V4-Pro, $0,108 per MiniMax M3, $0,175 per Kimi K2.7 Code e $0,228 per GLM-5.3. Sono calcoli dal [listino ufficiale](https://ollama.com/pricing), non costi osservati; thinking, cache e picco possono cambiare il totale.

## Condizioni operative, non deducibili dalla sola scheda modello

Dal 31 agosto 2026 Ollama **offre nuovi piani** con listino a token e crediti: Free ha crediti starter per un sottoinsieme di modelli e si possono comprare crediti per sbloccare tutti; nuovo Pro costa $20/mese con $60 di crediti, nuovo Max $100/mese con $300. I crediti inclusi non si accumulano fra mesi. Concorrenza dei nuovi piani: Free 1, Pro 3, Max/Team 10; richieste in eccesso vanno in coda finché la coda non è piena. **Account legacy Pro/Max possono rimanere sul pricing precedente**: non assumere che l'account Alembic abbia già i nuovi crediti o le nuove soglie; verificare fatturazione e piano prima di simulare il budget. [Pricing e FAQ Ollama](https://ollama.com/pricing), [annuncio Ollama](https://ollama.com/blog/transparent-pricing).

Ollama dichiara che i modelli Cloud con supporto tool vengono testati per tool calling e workflow agentici, e che le richieste possono essere servite in USA, Europa e in alcuni casi Singapore; dichiara inoltre no logging/no training/zero data retention. Questo non equivale automaticamente ai requisiti privacy, sicurezza e data residency specifici del progetto: verificare prima di inviare segreti o dati sensibili. [FAQ pricing Ollama](https://ollama.com/pricing), [privacy Ollama](https://ollama.com/privacy).

Per uso via daemon locale occorre autenticarsi con `ollama signin`; per API Ollama remota serve una chiave. Il tag `:cloud` nella scheda indica che il modello viene offloadato al cloud, non che i pesi girano localmente. La [documentazione Cloud](https://docs.ollama.com/cloud) mostra sia API locale sia remota e i comandi `ollama pull/run`; la [documentazione sull'autenticazione](https://docs.ollama.com/api/authentication) distingue le due modalità. Non abbiamo modificato il daemon o il flusso issue.

## Prova decisionale consigliata, prima di qualsiasi sostituzione

Congelare 6–10 issue Alembic già concluse ma non presenti nei prompt, diversificate fra bug Python, test/integrazione, backend Android, refactor, documentazione e issue ambigue. Eseguire nello **stesso harness**, stessi tool e budget, MiniMax M3 se confermato come default, Kimi K2.7 Code, DeepSeek-V4-Flash e DeepSeek-V4-Pro sui casi difficili. Misurare successo dei test, conformità alla spec/AGENTS.md, errori di tool calling, regressioni, richieste di chiarimento appropriate, costo osservato e tempo; reviewer cieco sui diff. Usare confronti **accoppiati sulle medesime issue**, non aggregati storici di log: epoche e mix di issue differenti confondono qualunque classifica. Nessuna auto-promozione sulla base dei benchmark pubblicati dai produttori. **Mantenere MiniMax M3 come default fino al replay** e preferire un modello non-GLM come reviewer delle implementazioni prodotte su z.ai.

## Limiti dell'audit

Le pagine Ollama riassumono benchmark forniti dai produttori; differiscono per harness, versioni e scoring, e non forniscono un confronto validato su Alembic. Il catalogo è dinamico: `:cloud`, data, prezzo e accesso vanno riverificati il giorno della prova. Le schede talvolta distinguono contesto massimo del modello da contesto effettivamente esposto da Ollama: per pianificazione va scelto il valore della scheda Ollama. Nessuna velocità o latenza reale è stata misurata.
