# Audit del chat template Qwen 3.8 locale (#653)

Data: 2026-09-24. Modello: `/home/stefano/llm/models/Qwen3.8-27B-Q8_0.gguf`.
llama.cpp: build `5d4a3be`. Service: `~/.config/systemd/user/llama-server{,-notte}.service`.

## Domanda

Il `chat_template.jinja` incluso nel GGUF riscrive i prompt dei nostri tre chiamanti?
L'issue lo sospettava per `triage_log_locale.py` e `s4_cluster_literature.py`, perché
non indicano un `reasoning_effort` e il server gira con `--reasoning-effort xhigh`.

## Metodo

1. Template estratto da `tokenizer.chat_template` con `gguf-py`, sha256
   `c3cf9e34…1041`, ora in `tests/fixtures/llm/qwen3.8-27b-q8_0.chat_template.jinja`.
2. Unione dei kwargs letta nel sorgente di llama.cpp, non ipotizzata:
   - `common/arg.cpp`: `--reasoning-effort X` → `default_template_kwargs.reasoning_effort`;
     `--reasoning-preserve` → `default_template_kwargs.preserve_reasoning = true`.
   - `tools/server/server-common.cpp`: prima i kwargs del server, poi i
     `chat_template_kwargs` della richiesta, poi il campo OAI `reasoning_effort`
     (`"none"` spegne il thinking).
   - `common/chat.cpp` (`common_chat_template_direct_apply_impl`): `enable_thinking` è
     **sempre** definito nel contesto; `preserve_reasoning` diventa la variabile
     `preserve_thinking` (`common/jinja/caps.cpp`).
3. Rendering dei tre payload reali con il motore Jinja di llama.cpp
   (`build/bin/test-chat-template --no-common`) e con jinja2: stessi byte in tutti i casi.

## Risultato

Il template inietta la frase **solo se il thinking è acceso**. Con
`enable_thinking: false` il ramo che sceglie le istruzioni di effort non viene eseguito
(riga 46 del template). La premessa dell'issue sui due chiamanti senza effort era quindi
sbagliata: nessuno dei tre riceve testo che non abbiamo scritto.

| Chiamante | Payload rilevante | Prompt renderizzato |
|---|---|---|
| `review_notturna_locale.py` (timer 01:07) | `reasoning_effort: "medium"`, solo messaggio user | `<\|im_start\|>user … <\|im_start\|>assistant\n<think>\n` (nessun system) |
| `triage_log_locale.py` (timer 02:15) | `chat_template_kwargs: {enable_thinking: false}` | solo il proprio `SISTEMA`, poi `<think>\n\n</think>\n\n` |
| `s4_cluster_literature.py` (nodi .184/.164) | `chat_template_kwargs: {enable_thinking: false}` | come il triage |
| chiamata nuda (nessuno oggi) | nessun override | `<\|im_start\|>system\nReasoning effort is set to xhigh. Please think carefully…` |

Altri fatti verificati:
- `reasoning_effort: "high"` (valido per llama.cpp, e il default di Claude Code) fa
  sollevare `raise_exception` al template: il server risponde 500. Il template accetta
  solo `xhigh`, `medium` e `low`.
- `--reasoning-preserve`: tutti e tre i chiamanti sono a turno singolo, quindi oggi non ha
  effetto. Diventerebbe un problema solo con un uso multi-turno (48K di contesto).
- `scripts/ensemble.py` passa da Ollama/OpenRouter, non da llama-server: è fuori
  perimetro.

## Che cosa cambia nel repo

Non cambia nessun prompt e nessun parametro di campionamento, quindi non c'è discontinuità
da registrare. Si aggiunge `tests/scripts/test_qwen_chat_template_contract.py`, che
cattura il payload vero di ogni chiamante, lo unisce ai default del service e lo
renderizza col template del modello. Fallisce se:
- un chiamante perde il proprio `reasoning_effort` o `enable_thinking: false` (compare la
  frase iniettata);
- il prompt di un chiamante dipende dal `--reasoning-effort` del service;
- la fixture non è più il template del modello (controllo sullo sha256).

C'è anche un "controllo del controllo": il test verifica che il renderer riproduca davvero
l'iniezione su una chiamata nuda, così i test sui chiamanti non passano perché il
renderer è rotto.

## Decisioni lasciate all'operatore (fuori dal repo)

1. **`--reasoning-preserve` nel service**: si può togliere senza effetti oggi, perché i
   chiamanti sono tutti a turno singolo. Toglierlo evita la trappola del primo uso
   multi-turno. Diff proposto per entrambi i service:
   `--reasoning-preserve` → `--no-reasoning-preserve`.
2. **Presence penalty: non aggiungerla al service.** La raccomandazione di Qwen (1,5 in
   non-thinking) è pensata per la chat libera. Triage e cluster-literature girano con
   `temperature 0.0` e output vincolato da schema JSON. Lì una penalità sui token già
   emessi colpisce proprio la punteggiatura e le chiavi JSON che si ripetono per
   costruzione, e cambierebbe gli output di serie già in corso. Per la review notturna,
   dove il loop di ragionamento è il difetto misurato (`misura_ripetizione`),
   `presence_penalty` è un esperimento sensato ma va misurato contro il ledger dei loop,
   non attivato alla cieca.
