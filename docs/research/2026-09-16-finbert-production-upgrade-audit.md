# FinBERT in produzione: audit di aggiornamento e alternative

Data: 2026-09-16  
Ambito: ispezione read-only del repository e del container `alembic-worker-inference-1`; nessuna modifica a configurazione o produzione.

## Addendum hardware

La macchina dispone di circa 61 GiB di RAM utilizzabile e di una NVIDIA GeForce RTX
3050 da 8 GiB. Questo rende realistico sperimentare in shadow anche un modello 7–8B
quantizzato, soprattutto con contesto corto, e rimuove il vincolo di considerare
soltanto encoder BERT CPU.

La GPU non è però attualmente disponibile al servizio: `nvidia-smi` non comunica con
il driver, il compose del `worker-inference` non dichiara una GPU e PyTorch nel
container riporta `cuda_available=False` e zero device. L'hardware amplia quindi il
roster di ricerca, ma non quello immediatamente deployabile. Anche dopo l'abilitazione
CUDA conviene mantenere un piccolo encoder CPU come fallback ultimo, indipendente da
GPU e runtime generativi.

## Sintesi

Il FinBERT attuale **non ha un aggiornamento upstream da installare**: Alembic carica
`ProsusAI/finbert` da `main` e la cache di produzione punta già alla revisione
`4556d13015211d73dccd3fdd39d39232506f3e43`, che coincide con l'attuale revisione
pubblicata da Hugging Face. L'API ufficiale indica inoltre come ultimo aggiornamento il
23 maggio 2023. Quindi ricostruire oggi l'immagine non porta nuovi pesi; espone invece
al rischio che `main` cambi in futuro senza una decisione esplicita.

Non raccomando una sostituzione immediata. I modelli generativi adattati con QLoRA
classificano meglio il sentiment nei benchmark linguistici recenti, ma non mostrano un
vantaggio economico robusto; con la nuova RAM/GPU sono challenger shadow plausibili,
ma non sostituti operativi in-place del classificatore BERT. La scelta migliore durante
il freeze è **fissare la revisione corrente**. Se si
vuole riaprire il confronto, il solo challenger leggero sensato è
`yiyanghkust/finbert-tone`, da valutare in shadow point-in-time. La distillazione
Alembic è già stata provata e ha ricevuto un verdetto **NO FLIP**; FinGPT e i modelli
QLoRA 7–8B possono essere challenger di ricerca, non fallback operativi.

## Cosa gira realmente

- Modello: `ProsusAI/finbert`, non parametrizzato da env e non revision-pinned
  (`src/llm/finbert.py`).
- Revisione risolta in cache: `4556d13015211d73dccd3fdd39d39232506f3e43`;
  `refs/main` punta alla stessa revisione restituita dall'[API ufficiale del
  modello](https://huggingface.co/api/models/ProsusAI/finbert).
- Runtime osservato nel container: Python stack con PyTorch `2.12.0+cu130` e
  Transformers `5.9.0`. Questo non coincide con l'intento del Dockerfile
  (`torch==2.6.0+cpu`): `uv sync` ha risolto lo stack dal lock successivamente. È un
  problema riproducibilità/deployment distinto dal checkpoint.
- Architettura: `BertForSequenceClassification`, tokenizer BERT uncased, massimo 512
  token; mapping corrente `{0: positive, 1: negative, 2: neutral}`. La [model card
  ufficiale](https://huggingface.co/ProsusAI/finbert) dichiara l'addestramento sul
  Financial PhraseBank e le tre classi positive/negative/neutral; il lavoro originario
  è [Araci, 2019](https://arxiv.org/abs/1908.10063).
- Caricamento lazy su CPU, seguito da quantizzazione dinamica int8 dei layer lineari.
- L'input live è titolo più corpo, ma viene tagliato prima a **512 caratteri** in
  `src/workers/sentiment.py`, quindi il limite effettivo è molto inferiore ai 512 token
  del modello.
- Output Alembic: `polarity=(p_pos-p_neg)*(1-p_neutral)` e confidence entropica
  `1-H(p)/log(3)`. Un cambio checkpoint cambia distribuzione e calibrazione delle
  probabilità, quindi anche score e soglie: non è semanticamente in-place.
- Ruolo: fallback deterministico quando l'ensemble non produce un risultato valido.
  Viene persistito come `model_id='finbert'` e `fallback_used=True`; nel flusso S4
  corrente i fallback sono esclusi dal ranking BUY e dalle reversal SELL. Rimane però
  importante per continuità, audit e misurazioni.
- Incidenza osservata: 154 segnali FinBERT su 3.202 negli ultimi 30 giorni (4,8%) e
  27 su 1.020 negli ultimi 7 giorni (2,6%), misurati il 2026-09-16 sul database di
  produzione. Il basso utilizzo e l'esclusione dal BUY riducono l'urgenza del cambio.

## Alternative verificate

| Candidato | Evidenza primaria | Drop-in | Valutazione per Alembic |
|---|---|---:|---|
| ProsusAI corrente, revisione fissata | [model card/API](https://huggingface.co/ProsusAI/finbert) | Sì | Baseline raccomandata; nessun nuovo peso upstream |
| `yiyanghkust/finbert-tone` | [model card](https://huggingface.co/yiyanghkust/finbert-tone), [paper](https://arxiv.org/abs/2006.08097) | Quasi | BERT finanziario addestrato su comunicazioni finanziarie e classifier a tre classi. Deve passare mapping, calibrazione, int8 e test Alembic; non esiste evidenza sufficiente che domini ProsusAI sulle news del sistema |
| Financial-RoBERTa | checkpoint valutato nel [benchmark 2026](https://arxiv.org/abs/2608.04200) | No | Nel benchmark eterogeneo off-the-shelf è leggermente peggiore di FinBERT: macro-F1 0,6679 contro 0,6753. Non giustifica una migrazione |
| FinGPT sentiment Llama2-13B LoRA | [repository e benchmark ufficiali](https://github.com/AI4Finance-Foundation/FinGPT), [setup ufficiale](https://github.com/AI4Finance-Foundation/FinGPT/blob/master/SETUP.md) | No | Classificazione forte sui dataset pubblicati, ma richiede modello base Llama2 13B, PEFT e tipicamente GPU; output generativo anziché probabilità calibrate. Troppo pesante e fragile come fallback locale |
| QLoRA su Mistral-7B/Llama3-8B/Qwen2.5-7B | [benchmark 2026](https://arxiv.org/abs/2608.04200) | No | Mistral-7B QLoRA raggiunge macro-F1 0,8771 e Llama3 0,8753, molto sopra FinBERT 0,6753, ma sono adattamenti sperimentali 7–8B, non checkpoint BERT CPU sostituibili direttamente |
| FinBERT distillato per Alembic | [issue #466](https://github.com/Jonbj/alembic/issues/466), PR #505 | No flip | Esperimento già completato: sul holdout cronologico di 1.037 esempi (4.145 train) ha ridotto la MAE verso il teacher da 0,4001 a 0,2116, ma ha peggiorato IC da -0,0359 a -0,0397 e hit-rate da 47,54% a 46,96%. Non va riproposto senza una nuova ipotesi sostanziale |

## Cosa dice il benchmark recente

Il preprint del 2026 [*From Financial Sentiment Classification to Return
Predictability*](https://arxiv.org/abs/2608.04200) separa correttamente due obiettivi:

- nella classificazione a tre classi, i 7–8B adattati QLoRA ottengono macro-F1 circa
  0,86–0,88, contro 0,6753 di FinBERT off-the-shelf;
- nella verifica economica temporalmente separata su headline Benzinga, FinBERT ha il
  maggiore IC medio a un giorno (`0,0143`), ma nessuno dei 28 test modello/orizzonte
  resta significativo dopo Newey-West e correzione FDR.

Quindi "classifica meglio" non equivale a "produce un segnale più utile per Alembic".
Il confronto decisivo deve usare la popolazione live del progetto e metriche sia
semantiche sia economiche.

## Raccomandazione e piano compatibile con il freeze

1. **Nessun flip live ora.** Il modello attuale è già all'ultima revisione ProsusAI.
2. Alla prima finestra ammessa, fissare modello e tokenizer alla revisione
   `4556d13015211d73dccd3fdd39d39232506f3e43`; registrare revision, digest,
   Transformers e Torch nell'evidenza di deployment.
3. Correggere separatamente la deriva tra Dockerfile CPU e ambiente realmente risolto.
   Se si vuole includere un 7–8B nel benchmark, ripristinare prima il driver NVIDIA,
   esporre esplicitamente la GPU al worker e verificare CUDA con un test di avvio;
   senza mescolare questo lavoro infrastrutturale al confronto qualitativo dei modelli.
4. Congelare un dataset Alembic point-in-time, deduplicato per articolo/ticker e con
   split cronologico. Eseguire in shadow sullo stesso input esatto:
   - ProsusAI pinned fp32 e int8;
   - `yiyanghkust/finbert-tone`;
   - opzionalmente un solo challenger QLoRA, fuori dal requisito di fallback CPU.
   Il checkpoint distillato esistente resta una baseline negativa documentata, non un
   candidato alla promozione, salvo formulazione e preregistrazione di una nuova ipotesi.
5. Misurare macro-F1/calibrazione su etichette umane disponibili, stabilità fp32/int8,
   latenza/RSS/cold start e failure rate; sul piano economico IC, hit-rate e coverage
   con intervalli temporali e costi, senza scegliere sullo stesso holdout.
6. Promuovere soltanto un candidato che domini la baseline su metrica primaria
   preregistrata, non degradi calibrazione/operatività e superi un periodo shadow. Il
   cambio richiede anche ricalibrazione della trasformazione probabilità→score e delle
   soglie; il solo cambio di `_MODEL_NAME` non è sufficiente.

**Decisione:** aggiornabile tecnicamente, ma non esiste oggi un "FinBERT nuovo" da
installare. Mantenere ProsusAI pinned; se il costo di ricerca è giustificato, testare
solo `finbert-tone` come challenger leggero. Non promuovere il checkpoint distillato
già respinto e non usare FinGPT o un 7–8B QLoRA come fallback live finché non esistono
una prova Alembic-specifica e un profilo operativo accettabile.
