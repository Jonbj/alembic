# FinBERT distillation — esito offline della #466

## Verdetto

**NO FLIP.** Il checkpoint distillato imita molto meglio la polarity soft
dell'ensemble, ma sullo stesso holdout temporale peggiora sia l'IC rispetto al
forward return a un giorno sia l'hit-rate. Non c'e' quindi evidenza per sostituire
il fallback FinBERT base, ne' durante il freeze ne' dopo senza un esperimento nuovo.

Questa conclusione non cambia soglie, pesi, flag, cooldown o parametri di strategia.
Il checkpoint non e' importato da `FinBERTClient`, non e' caricato dai worker e non
ha alcun percorso verso Redis, PostgreSQL o l'esecuzione.

## Premessa verificata contro il codice

Il gap principale della issue esiste: `ProsusAI/finbert` resta il classificatore
3-class generico e non esisteva alcuna pipeline di distillazione Alembic. Una
premessa secondaria del documento sorgente era invece invecchiata: dal commit
`bf5bef2e` (#399/#408) il fallback riceve gia' il titolo concatenato al corpo. La
pipeline nuova conserva quel budget di 512 caratteri e aggiunge il ticker in testa,
come richiesto dalla #466; non modifica di nuovo il path live.

## Dataset e split

La query read-only seleziona soltanto segnali con tutte queste proprieta':

- verdict cloud persistito come `model_id LIKE 'ensemble:%'` e
  `fallback_used = FALSE`;
- almeno una riga figlia in `llm_responses`, per escludere segnali privi di una
  risposta cloud osservabile;
- `forward_return` a un giorno non nullo;
- confidence positiva, necessaria per ricostruire la polarity aggregata come
  `score / confidence`;
- titolo e body disponibili in `news_log`.

La prima osservazione cronologica per coppia `(news_log_id, symbol)` elimina 16
scoring ripetuti e impedisce che lo stesso articolo/ticker attraversi entrambi gli
split. Dopo i requisiti di testo restano 5.182 esempi. Lo split 80/20 e' strettamente
temporale:

| split | n | inizio UTC | fine UTC |
|---|---:|---|---|
| train | 4.145 | 2026-06-15 17:31:34 | 2026-08-17 16:46:44 |
| validation | 1.037 | 2026-08-17 17:00:19 | 2026-09-02 19:46:10 |

Il modello riceve `Ticker`, `Headline` e `News` sanitizzati. La stringa complessiva
e' limitata a 512 caratteri prima del tokenizer, allineata al budget del fallback
attuale. Il manifest generato contiene ID, timestamp, target e return, ma non copia
il testo degli articoli.

## Training

- base: `ProsusAI/finbert`;
- tutti i parametri addestrati per un epoch sull'intero train set;
- batch size 64, learning rate `2e-5`, seed 466, CPU;
- loss: `MSE(predicted_polarity, teacher_polarity) +
  cross_entropy(predicted_direction, sign(teacher_polarity))`;
- loss media dell'epoch: `0.9788073891`.

La polarity prevista non assume l'ordine fisso delle classi: gli indici
positive/negative/neutral sono letti da `model.config.label2id`.

## Confronto sullo stesso holdout

| modello | n | IC Spearman vs return 1d | hit-rate | MAE vs teacher |
|---|---:|---:|---:|---:|
| FinBERT base | 1.037 | -0,0359 | 47,54% | 0,4001 |
| FinBERT tuned | 1.037 | -0,0397 | 46,96% | 0,2116 |

Il tuned riduce la MAE del 47,1%, quindi la distillazione ha imparato il teacher.
Ma l'obiettivo economico non migliora: IC scende di 0,0038 e hit-rate di 0,58 punti
percentuali. Questo distingue un successo di imitazione da un successo predittivo e
porta al verdetto NO FLIP.

## Checkpoint e riproduzione

Il run completo ha salvato un checkpoint HuggingFace standard da 419 MB in:

```text
/tmp/alembic-466-full/checkpoint
```

SHA-256 dell'intera directory, includendo nomi e contenuti in ordine lessicografico:

```text
f81f4e1293e124b90f7a63e25214b72b511d5c9d2a2ae99b900fa24265cd5714
```

SHA-256 del solo `model.safetensors`:

```text
1962b7dd17a18caae656446f35f29fc587846a5094275d40b0c56e3d95e6522e
```

Il binario non e' versionato: supera il limite ordinario di GitHub per singolo file
e il repository non configura Git LFS. Il codice, la query, gli iperparametri e il
seed necessari a rigenerarlo sono versionati. Dal repository principale, con il DB
esposto su localhost, il comando completo e':

```bash
.venv/bin/python scripts/train_finbert_distillation.py \
  --epochs 1 --batch-size 64 \
  --output-dir reports/finbert_distillation --device cpu
```

Per verificare in pochi secondi soltanto popolazione e split, senza caricare o
addestrare il modello:

```bash
.venv/bin/python scripts/train_finbert_distillation.py \
  --dataset-only --output-dir /tmp/finbert-distillation-dataset
```

Sul medesimo snapshot DB stampa `total_n=5182`, `train_n=4145` e
`validation_n=1037`. Nuovi forward return possono aumentare i conteggi in run
successivi; il manifest conserva lo snapshot usato per il risultato sopra.

## Perimetro freeze

Non e' stato aggiunto `FINBERT_TUNED` al runtime. Quel flag avrebbe creato un nuovo
ramo attivabile nel money path, mentre il candidato ha fallito il confronto e ogni
flip e' congelato fino al 28 settembre. L'esito NO FLIP rende inoltre inutile
predisporre ora un ramo live per un checkpoint respinto. Rimangono ammessi soltanto
la pipeline offline e il report di misura qui documentati.
