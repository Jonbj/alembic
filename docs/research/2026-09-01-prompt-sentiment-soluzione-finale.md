# Ottimizzazione prompt sentiment — soluzione finale consolidata (2026-09-01)

**Aggiornamento 2026-09-01, post-deploy**: Variante A **deployata in produzione**
(commit `bf5bef2e`, `SENTIMENT_PROMPT_VARIANT=a` in `.env`, verificato attivo nei
container `worker`/`worker-inference`), con **autorizzazione esplicita dell'operatore
in deroga al freeze #171** — non si è aspettato il 28/09. Deroga registrata in
`docs/evidence/OBSERVATION_CHARTER.md` (voce 2026-09-01), commenti su #399/#408. La
sezione "Cosa NON fare ora" sotto descriveva lo stato pre-deroga; resta valida per
Variante B (non toccata, ancora bloccata su golden set QX-01 n=0).

Consolidamento di tre esecuzioni indipendenti di `prompts/ottimizza_prompt_sentiment.md`
(prompt principale + appendice di verifica esterna):

- **glm-5.3**: `docs/research/2026-09-01-prompt-sentiment-ottimizzazione.md` +
  `-verifica-esterna.md`, template in `prompts/sentiment_variante_{A,B}.txt`.
- **Codex (Opus 5)**: `files/ottimizzazione_prompt_sentiment.md` +
  `files/verifica_esterna_prompt_sentiment.md`, template in
  `files/sentiment_variante_{A,B}_opus5.txt`.
- **Opus 5 (run diretta)**: `files/ottimizzazione_prompt_sentiment_opus5.md` (diagnosi +
  varianti + appendice in un solo file) — l'unica delle tre ad aver **misurato la
  produzione reale** (`llm_responses`, `sentiment_signals`, 30 giorni) invece di fermarsi
  ai 5 difetti dichiarati nel prompt.

**Verifica indipendente fatta qui prima di consolidare**: i file esistono tutti; letto
`LLMSentimentOutput` (`src/models/news.py:85-118`) e i 5 punti che leggono `.reasoning`
a valle; **riverificate a mano sul DB live le 4 statistiche chiave del report Opus5**
(query dirette `alembic-postgres-1`, non fidandomi del solo testo):

| Claim (Opus5) | Valore dichiarato | Valore verificato |
|---|---|---|
| Copertura titolo, 30gg | 3288/3290 (99,94%) | **3288/3290** ✓ esatto |
| Confidenza media glm-5.2 | 0,273 | **0,273** ✓ esatto |
| Confidenza media gpt-oss | 0,397 | **0,397** ✓ esatto |
| \|polarity\| < 0,1 su `llm_responses` | 3407/6413 (53%) | **3407/6413** ✓ esatto |
| Segnali sopra gate 0.30 / banda 0.15-0.30, 30gg | 288 / 397 | 277 / 408 (~vicino, finestra dei 30gg scorsa fra le due misure) |

I numeri reggono. Il report Opus5 è la base più solida delle tre proprio perché non si
ferma all'ipotesi ma la misura — dove i tre report divergono, la sua evidenza empirica
prevale nel merito.

---

## Decisione

**Variante A: adottare, dietro flag, con shadow-scoring pre-rollout — nessun disaccordo
fra i tre modelli.**

**Variante B: NON adottare ora — nessun disaccordo fra i tre modelli**, con un motivo più
forte del previsto: non solo la letteratura è in conflitto sulla direzione della
calibrazione (Opus5, conflitto C1: la letteratura documenta *overconfidence*, la nostra
produzione mostra *compressione* — direzioni opposte, non decidibile a tavolino), ma il
golden set QX-01 che dovrebbe arbitrare è a **n=0**.

### Perché A non è un compromesso al ribasso

Il Difetto 2 (notizie di secondo ordine sotto-scorate) non è più un'ipotesi — Opus5 lo ha
misurato su `llm_responses` dal 26/08 (n=692, campo `directness` persistito):

| directness | \|polarity\| media (glm-5.2 / gpt-oss) | % sopra gate 0.30 |
|---|---|---|
| direct | 0,40 / 0,44 | 38% / 49% |
| competitor_readthrough | 0,18 / 0,20 | 6% / 9% |
| sector | 0,21 / 0,18 | 7% / 5% |
| macro | 0,18 / 0,14 | 5% / 0% |

Rapporto di magnitudine ≈ **2,2x**, rapporto di gate-pass ≈ **5-6x**, su **entrambi** i
modelli dell'ensemble → è il prompt, non l'idiosincrasia di un provider (correlazionale,
non causale — parte del gap può essere reale, le notizie di terzi in media muovono meno;
va comunque misurato in shadow, non dato per acquisito).

Il Difetto 1 (titolo mai incluso) non è un problema di disponibilità del dato — è
disponibile nel 99,94% dei casi e viene buttato via strutturalmente (nessun placeholder
nel template).

### Un punto di governance che nessuno dei tre report aveva enfatizzato abbastanza

**R1 (Opus5, quantificato)**: alzare la magnitudine del read-through anche solo di ~2x
(l'ordine di grandezza del gap misurato) porterebbe i candidati sopra gate da ~288 a
~600-700 (**≈2,4x**), a soglia 0.30 invariata. **Cambiare il prompt equivale, in pratica,
ad abbassare il gate — senza che il cambiamento appaia in `config/` o nell'`OBSERVATION_CHARTER.md`.**
Questo non cambia la decisione (A resta la scelta giusta), ma alza la barra per il
sign-off: il rollout di A va trattato con lo stesso rigore di una modifica di soglia, non
come "solo testo del prompt" — coerente con le freeze note già scritte in #399 e #408, ma
ora con un motivo quantificato invece che generico.

---

## Punti di consenso fra i tre modelli

1. **Schema JSON di A: invariato byte-per-byte.** Zero modifiche a Pydantic/parser/DB.
2. **Schema JSON di B: additivo, non un rename.** `bull_case`/`bear_case` si
   **aggiungono** a `LLMSentimentOutput` come campi opzionali; `reasoning` resta
   `required`, ridefinito come verdetto in una frase (non più "bull/bear in una frase").
   Codex e Opus5 arrivano indipendentemente allo stesso design — ed **Opus5 quantifica
   perché l'alternativa (rename, la scelta fatta inizialmente da glm-5.3) sarebbe grave**:
   `reasoning` è `required` e viaggia in ~15 punti di `pg_store.py`; rinominarlo rompe
   `model_validate_json` su **ogni** articolo → **100% fallback FinBERT al primo deploy**.
   Non serve nemmeno un `model_validator` di sintesi (mia proposta nella prima bozza di
   questo documento): bastano due `Field(default="")` opzionali, `reasoning` resta
   generato indipendentemente dal modello.
3. **Costo non è il vincolo reale.** Le stime di glm-5.3/Codex assumevano "decine di
   migliaia di articoli/mese"; il volume vero, misurato da Opus5, è **3.290/mese**
   (~6.600 chiamate LLM). Costo reale: A +$2,2/mese, B +$9-10/mese, contro un budget di
   **$50/giorno**. Il vincolo vero è la **latenza sotto il semaforo Redis globale**
   (`_OLLAMA_TIMEOUT=90s`), specialmente rilevante nelle sedute di outage (forense 08-26:
   81,6% fallback quel giorno) — non il costo per token.
4. **Read-through come segnale di prezzo di prima classe.** Confermato da letteratura
   indipendente in tutti e tre i report (Cohen & Frazzini JF 2008, Hou lead-lag, lavori
   2024 su complementarità produttiva — alpha ~122bp/mese su strategie basate sui
   rendimenti dei peer; BloombergGPT/FinGPT: il framing corretto è prospettiva
   investitore/prezzo, non sentiment generico sui fondamentali).
5. **Few-shot: nessuno dei tre lo consiglia in A.** Letteratura conflittuale su
   numero/selezione/ordine (Zhao et al. ICML 2021, Lu et al. ACL 2022, Fatemi & Hu 2023,
   BlackRock evita il few-shot nei loro eval per bias di selezione). Se e quando B verrà
   validata, i tre esempi vanno bilanciati per segno (+/−/0) — punto su cui Codex e Opus5
   convergono esplicitamente dopo la loro stessa auto-critica.

## Punti nuovi emersi solo da un modello, verificati e accolti

- **FinBERT non riceve mai il titolo, nemmeno dopo il fix di A** (Codex + Opus5, R6).
  FinBERT (`ProsusAI/finbert`, `src/llm/finbert.py`) è un classifier BERT fine-tuned, non
  un LLM instruction-following: non esegue il prompt DK-CoT. Il fallback chiama
  `finbert.analyze(clean_body[:512])` — solo body, mai titolo — sia oggi sia dopo A/B.
  **Il fix del prompt non copre le sedute in cui l'ensemble è giù** (esattamente quando il
  sistema si affida di più a FinBERT). Fix indipendente e quasi gratis: concatenare
  titolo+body prima del truncation anche sul path FinBERT.
- **`OllamaCloudClient.complete` non invia `format` (schema JSON) né `temperature=0`**
  (Opus5, verificato: `client.py:~773` invia solo `model/messages/stream`), nonostante la
  documentazione Ollama raccomandi esplicitamente entrambi. Candidato root-cause per la
  **deriva sugli enum** osservata in produzione (`supplier_readthrough` inesistente,
  `competitor_readthrough|macro` con separatore ricopiato, uno `unclear` con zero-width
  space dentro) e per il rischio R2 sotto. Ortogonale al testo del prompt — **da aprire
  come issue separata**, beneficio/rischio migliore di qualunque modifica testuale.
- **Rischio R2, specifico di B**: `LLMClient.parse_json_response` (`client.py:327`) estrae
  da `find("{")` a `rfind("}")+1`. Se un modello, avendo visto tre esempi JSON completi nel
  prompt, ne riemette uno prima della risposta vera, lo span diventa invalido → retry →
  degrado a `single:<model>` o FinBERT. Asimmetrico: colpisce solo B (A non ha few-shot).
  Da misurare in shadow (tasso `invalid` per modello, già bucketato in `ensemble.py`) prima
  di qualunque rollout di B — si aggraverebbe esattamente col fix `format=schema` sopra
  ancora mancante.
- **I due modelli dell'ensemble sono su scale di confidence diverse e vengono mediati come
  se non lo fossero** (Opus5, verificato: 0,273 vs 0,397 sugli stessi articoli). Non è un
  difetto del prompt in sé, ma una proprietà dell'aggregazione (`EnsembleAggregator`,
  soglia `ENSEMBLE_DIVERGENCE_STD=0.40` fissa) che il prompt da solo non risolve — le
  ancore di B potrebbero ridurre il gap o, se i modelli le interiorizzano in modo diverso,
  **aumentarlo** (R4 Opus5) e far scattare più spesso il fallback per divergenza. Da
  misurare, non assumere.

---

## Cosa fa scattare A dal design alla produzione

1. **Implementare dietro flag** (env var, default = comportamento attuale invariato).
   Modifica concentrata: `_DK_COT_PROMPT` (nuovo template A), le due call site
   `sentiment.py:356` e `:571` (nuovo argomento `title=`), `sanitize_text` applicato anche
   al titolo (vincolo CLAUDE.md omoglifi — il titolo non è mai passato dal sanitizer finora
   perché non entrava nel prompt).
2. **Fix companion, stesso commit o immediatamente dopo**: titolo anche sul path FinBERT
   fallback (`clean_body` → `title + ". " + body` prima del truncation a 512 char).
3. **Shadow-scoring**: infrastruttura già esistente (`_shadow_query_candidates`,
   `sentiment.py:531-636`) per scorare in parallelo senza toccare `news_log`/
   `sentiment_signals` prodotti dal prompt corrente.
4. **Misurare la distribuzione, non solo il segno**: confronto prima/dopo di
   `|score|` per bucket di `directness`, tasso di segnali sopra gate, tasso di divergenza
   ensemble — per quantificare l'effetto R1 (equivalente-a-abbassare-il-gate) prima del
   flip, non dopo.
5. **Decisione operatore esplicita prima del flip** a comportamento live di default — non
   prima del 2026-09-28, salvo autorizzazione esplicita a scorciare la finestra. Stesso
   standard di una modifica di soglia, per il motivo R1 sopra.

## Cosa NON fare ora

- Non toccare la soglia di gate 0.30 (fuori scope per costruzione in tutti e tre i report).
- Non integrare B in produzione, nemmeno dietro flag, prima che QX-01 abbia n>0 **e** prima
  di aver misurato in shadow il rischio R2 (parse failure da few-shot echo).
- Non backfillare gli score storici col prompt nuovo: la ricalibrazione dei pesi LOO
  ensemble è un effetto collaterale noto e accettato, da gestire a parte quando/se A va live.

## Prossimi passi da pianificare (separati)

1. **Implementazione A** (`sentiment.py`, `finbert` fallback, flag, test) — tocca il path
   di scoring live (dietro flag spento di default): confermo prima di procedere.
2. **Issue separata: `OllamaCloudClient` senza `format`/`temperature=0`** — nessuna
   dipendenza da A/B, beneficio indipendente (deriva enum, robustezza parser).
3. **Issue di misura**: R1 (distribuzione score/gate-pass prima-dopo A) e R2 (parse
   failure rate B) — entrambe freeze-ok, propedeutiche al flip di A e all'eventuale ripresa
   di B.
