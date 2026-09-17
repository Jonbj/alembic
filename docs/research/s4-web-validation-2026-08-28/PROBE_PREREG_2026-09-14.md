# Pre-registrazione — probe differenziale estrattore (node1) 2026-09-14

Scritta **prima** di eseguire il probe e prima di guardare qualunque output nuovo.

## Domanda

I vuoti del corpus v4 (H16 e H17 a zero claim, H11 a uno) sono un fatto della letteratura
o un artefatto dello strumento? Oggi node1 gira **Q4_K_XL su 14 GB di RAM** (17,5 GB di
modello: paginazione continua, stallo I/O al 37-58%) con **contesto 8.192** e finestra di
chunking **9.000 caratteri / 500 di overlap**. Un claim la cui evidenza sta a cavallo di due
chunk non e' estraibile e non lascia traccia: non viene rifiutato, semplicemente non esiste.

## Campione (fissato ora, non modificabile dopo)

`MET005` e `ACA010`: le due fonti piu' piccole gia' `SOURCE_PASS_COMPLETE` con testo in
`source-cache/`. Baseline di produzione gia' a ledger:

| fonte | char | chunk | claim validi | claim rifiutati |
|---|---|---|---|---|
| MET005 | 42.499 | 6 (2 splittati) | 12 | 6 |
| ACA010 | 48.373 | 6 | 12 | 6 |

Integrita' verificata prima di iniziare: ricostruendo i chunk dal testo in cache con la
funzione di produzione, gli hash coincidono 6/6 su ACA010 e 4/4 sui chunk non splittati di
MET005. La pipeline del probe riproduce esattamente quella di produzione.

## Bracci

| | modello | contesto | finestra | max_tokens |
|---|---|---|---|---|
| **A** (baseline, gia' registrato) | Q4_K_XL, nodo1 | 8.192 | 9.000/500 | 1.200 |
| **B** (quant + finestra) | Q8_0, macchina locale | 49.152 | **30.000**/500 | 4.000 |
| **A'** (solo quant, *condizionale*) | Q8_0, macchina locale | 49.152 | 9.000/500 | 1.200 |

`max_tokens` di B scala con la finestra perche' il budget di uscita non deve diventare il
vincolo attivo. Tutto il resto e' identico: stesso `node1_prompt`, stesso
`node1_response_format`, stesso `validate_card`, `temperature 0.0`, `top_p 0.9`,
`enable_thinking: False`. **Il probe importa le funzioni di produzione, non le riscrive.**

## Esito primario

Numero di claim che superano `validate_card` per fonte, e insieme delle ipotesi coperte —
in particolare se compaiono H11, H16 o H17.

## Esito secondario

Tasso e motivi di rifiuto (`INVALID_LINE_RANGE` e altri); quanti dei claim nuovi di B hanno
`evidence_lines` che attraversano un confine di chunk di A, cioe' quanti erano
strutturalmente irraggiungibili prima.

## Regola di decisione (fissata ora)

- **B ≤ A+2 su entrambe le fonti e nessuna ipotesi nuova** → nessuna evidenza che lo
  strumento sia il vincolo. Nodo1 resta dov'e', la campagna finisce coi suoi tempi, la
  macchina locale e' libera per altro. A' **non** viene eseguito.
- **B ≥ A+3 su almeno una fonte, oppure compare almeno una delle ipotesi a zero** → il
  corpus e' limitato dallo strumento. Si esegue A' per attribuire la causa: se A' ≈ A il
  merito e' della **finestra**, se A' ≈ B e' del **quant**. Solo allora si apre la
  questione di un passaggio v5 a finestre larghe.

## Confondenti dichiarati

Build llama.cpp diverso (locale `5d4a3be` contro `ece963f` dei nodi); quant diverso; backend
diverso (GPU 8 GB contro 4 GB e swap). **Una sola esecuzione per braccio**: una differenza di
1-2 claim e' rumore, non segnale — la soglia di 3 e' scelta per questo.

## Vincoli

Nessuna scrittura in `node-output/`, nessun contatto con la campagna in corso, nessun
`retry_campaign` registrato. Gli output del probe vivono fuori dal ledger. Questo probe non
decide niente su S4.
