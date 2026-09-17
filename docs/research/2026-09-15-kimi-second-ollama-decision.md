# Kimi K2.7 Code come secondo motore Ollama nel loop issue: decisione

Verifica 2026-09-15. Questa è una valutazione documentale e del codice del loop, non una prova del modello su Alembic. Non modifica configurazione, issue, cron o account.

## Raccomandazione

**Pilot controllato, non aggiunta immediata alla rotazione produttiva.** `kimi-k2.7-code:cloud` è un challenger credibile per implementazioni complesse, ma condivide la quota Ollama usata da MiniMax e dal sentiment di trading. Nella rotazione attuale un quarto motore porterebbe la quota di implementazioni su Ollama da un terzo a metà dei giri, senza rendere Kimi normalmente un reviewer. Prima: replay accoppiato e costo/latency osservati, verifica del piano/quota dell'account e riserva esplicita per il trading. [Codice del loop](../../scripts/roadmap_agent_loop.sh), [pricing Ollama](https://ollama.com/pricing).

## Cosa è verificato dalle fonti ufficiali

La [scheda Ollama Kimi K2.7 Code](https://ollama.com/library/kimi-k2.7-code) espone il tag **`kimi-k2.7-code:cloud`**, contesto **256K**, input testo/immagine, tool e thinking, e invocazione Claude Code tramite `ollama launch claude --model kimi-k2.7-code:cloud`. Il prezzo pubblicato è **$0,95 input / $0,19 cached input / $4,00 output per milione di token**. La scheda riferisce miglioramenti nel coding long-horizon e circa il 30% di thinking-token in meno rispetto a Kimi K2.6, con benchmark dichiarati dal produttore (Kimi Code Bench v2 62,0 vs 50,9; MCP Atlas 76,0 vs 69,4). Questi numeri **non** mostrano superiorità rispetto a MiniMax M3 sullo stesso harness Alembic. [Scheda Kimi](https://ollama.com/library/kimi-k2.7-code), [pagina originale Moonshot del modello](https://huggingface.co/moonshotai/Kimi-K2.7-Code).

Per confronto, [MiniMax M3 su Ollama](https://ollama.com/library/minimax-m3) pubblica **512K garantiti** e **$0,60 / $0,12 / $2,40**. Kimi costa circa **1,58× sull'input non cached** e **1,67× sull'output**, con metà del contesto Cloud esposto. Entrambi appartengono allo stesso conto Ollama, anche se i modelli hanno capacità e rate limits propri. Il [listino ufficiale](https://ollama.com/pricing) ora usa crediti e concorrenza per piano: Free 1, nuovo Pro 3, nuovo Max 10 richieste; una coda piena può rifiutare richieste. Il [comunicato Ollama del 31 agosto](https://ollama.com/blog/transparent-pricing) specifica che account Pro/Max legacy possono restare sul vecchio regime: **non assumere** $60/$300 di nuovi crediti o nuove soglie senza controllare l'account usato da Alembic.

## Impatto matematico sul loop, se tutti i motori sono disponibili

Nel [loop corrente](../../scripts/roadmap_agent_loop.sh) `MOTORI=(codex glm53 minimax)` e MiniMax è chiamato esplicitamente come `minimax-m3:cloud` sia per implementazione sia per review. La selezione è round-robin fra motori disponibili, con avanzamento anche quando il lavoro termina in no-op. Se si aggiungesse Kimi come quarto motore con pari disponibilità, senza pesi:

| Metrica per giro | Tre motori ora | Quattro motori con Kimi | Variazione |
|---|---:|---:|---:|
| MiniMax implementatore | 1/3 | 1/4 | −25% della propria frequenza |
| Kimi implementatore | 0 | 1/4 | nuova frequenza |
| Implementazioni su Ollama (MiniMax + Kimi) | 1/3 | 1/2 | **+50% dei giri** |
| Implementazioni su quota z.ai | 1/3 | 1/4 | −25% |
| Implementazioni su Codex | 1/3 | 1/4 | −25% |

La quota Ollama di implementazione sale quindi di **1/6 del totale dei giri**. Per il solo esempio tariffario di **100K input non cached + 20K output per sessione**, MiniMax costa ~$0,108 e Kimi ~$0,175 secondo il [listino](https://ollama.com/pricing): il costo medio Ollama per giro passerebbe da `(1/3)×0,108 = $0,036` a `(1/4)×(0,108+0,175) = $0,0708`, cioè **circa +97%**. È un'illustrazione, non una misura reale: sessioni agentiche possono avere molte più chiamate, cache e thinking token. Il trading si alimenta dallo stesso budget Ollama secondo il [commento di migrazione z.ai nel loop](../../scripts/roadmap_agent_loop.sh) e il [client diretto Ollama del sentiment](../../src/llm/client.py); il reale consumo simultaneo va rilevato dall'account.

## Kimi non diventerebbe automaticamente una seconda review

Il loop sceglie il **primo** motore disponibile diverso dall'implementatore, scorrendo l'array in ordine, non ruota i reviewer. Con `[codex, glm53, minimax, kimi]` tutti disponibili, Kimi sarebbe implementatore nel 25% dei giri ma **reviewer ordinario nello 0%**: per una PR di Codex sceglierebbe GLM; per una PR degli altri tre sceglierebbe Codex. Kimi potrebbe fare review solo in indisponibilità, forzatura/tie-breaker o con una politica di review modificata. [Funzioni `scegli_recensore` e `motore_tiebreaker`](../../scripts/roadmap_agent_loop.sh).

L'aggiunta non è comunque solo una riga nell'array: `motore_installato`, `esegui_agente` ed `esegui_revisore` accettano oggi solo l'etichetta `minimax` per Ollama. Un'etichetta `kimi` senza casi dedicati sarebbe esclusa o fallirebbe; la panchina da rate limit è **per etichetta di motore**, non per account. Se la quota comune è esaurita, MiniMax e Kimi potrebbero essere provati e messi separatamente in panchina per tre ore, mentre il sentiment va in fallback FinBERT. [Loop e commento quota condivisa](../../scripts/roadmap_agent_loop.sh), [client sentiment Ollama](../../src/llm/client.py).

## Prova minima prima della promozione

1. Congelare 8–12 issue già concluse, stratificate per difficoltà e stack; stesso prompt, Claude Code harness, worktree, tool, tempo e criteri per MiniMax M3 e Kimi K2.7 Code. Distinguere implementazione da reviewer.
2. Valutare blind su aderenza issue, test nuovi/rotti, freeze, qualità del diff e no-op appropriato. Rilevare token/costo effettivi, timeout e rate-limit per account, non solo per modello.
3. Eseguire il pilot in finestre che non competono con il sentiment live, oppure con budget Ollama esplicitamente riservato al trading. Verificare prima il piano legacy/nuovo, crediti residui e concorrenza.
4. Promuovere Kimi solo se il guadagno accoppiato è stabile e paga l'aumento di spesa/contesa; in caso contrario usarlo su issue difficili **forzate manualmente**, non nella rotazione uniforme.

I vecchi aggregati del loop non sono evidenza di confronto causale: GLM ha cambiato versione e provider nel tempo, e i motori hanno ricevuto mix di issue e momenti operativi differenti. La comparazione deve assegnare **le stesse issue** ai due modelli in condizioni controllate. [Commento sulle epoche GLM nel loop](../../scripts/roadmap_agent_loop.sh).
