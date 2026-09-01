# Ottimizzazione prompt sentiment — report 2026-09-01

Esecuzione di `prompts/ottimizza_prompt_sentiment.md` contro il prompt reale in
produzione (`src/workers/sentiment.py:270`, `_DK_COT_PROMPT`). Verifiche fatte sul
codice prima dell'analisi:

- `{text}` = `sanitize_text(item.body)[:600]` (`SENTIMENT_LLM_BODY_CHARS`, default 600) — confermato: **il titolo non entra mai nel prompt**.
- `NewsItem.title` esiste (`src/models/news.py:34`, default `""`) ed è usato solo come *proxy* del body quando il body manca — mai in aggiunta.
- Il prompt passa per `str.format()`: **le graffe del JSON schema nel template Python vanno raddoppiate** (`{{`…`}}`), come già fa `_DK_COT_PROMPT`.

Varianti pronte all'uso (testo puro, placeholder `.format()`):
- Variante A: `prompts/sentiment_variante_A.txt`
- Variante B: `prompts/sentiment_variante_B.txt`

**Verifica esterna successiva:** `docs/research/2026-09-01-prompt-sentiment-verifica-esterna.md`
(best practice da letteratura/web, confronto per variante, conflitti irrisolti). La
verifica ha prodotto 3 correzioni alla Variante B — schema reasoning-first, esempio
few-shot negativo, clausola competitor-inversion — documentate nel changelog del file
della variante. Le conclusioni e i numeri di quel file ** prevalgono** su questo dove
divergono (token B: ~1300, non ~1200).

---

## Diagnosi

### Difetto 1 — Titolo mai incluso (evidenza: Robinhood, score −0,0098 su +8,17%)

**Causa strutturale: difetto di interfaccia, non di ragionamento.** Il prompt offre
un solo slot testuale — `News: {text}` (riga 283 del template) — e il codice lo riempie
con il body snippet troncato a 600 caratteri. Non esiste nel prompt nessun posto dove
un titolo potrebbe entrare: il difetto è nella firma del template, non nelle istruzioni.

Il prompt lo aggrava con la regola *"Use only evidence in the article"*: il modello è
*obbligato* a fondarsi esclusivamente su uno snippet che può essere stantio o riferirsi
a un altro giorno (il caso Robinhood: headline "surging on Tuesday", snippet "traded
lower Thursday after…"). Il modello ha risposto *correttamente* alla domanda posta,
su un input sbagliato. Inoltre il truncation a 600 char rende più probabile che
l'informazione direzionale più fresca (quella nel titolo) non sia l'unico testo
disponibile — e quando body e titolo divergono, il sistema sceglie il meno recente
per costruzione.

### Difetto 2 — Notizie di secondo ordine sotto-scorate (evidenza: Adobe +5,73%, score 0,060)

**Causa strutturale: il prompt fa la domanda sbagliata per il caso d'uso.**

- Step 1: *"What does this mean for THIS company's revenue, cash flows and competitive
  position?"* — per una notizia di spillover (Adobe su dopo gli earnings di Salesforce)
  la risposta onesta a *questa* domanda è "poco": i fondamentali di Adobe non cambiano.
  Il modello risponde bene a una domanda sui fondamentali, ma il gate consuma un
  segnale di *movimento atteso del prezzo*. L'ipotesi della issue è confermata dalla
  formulazione stessa dello step 1.
- Step 3: *"How material and how novel (not already priced in) is it?"* — doppio
  sconto addizionale sullo spillover: meno materiale del directo, e il movimento
  "già partito" viene letto come già prezzato.
- La regola *"if the market impact is unclear, set polarity=0, confidence low"* è
  **asimmetrica**: spinge solo verso il basso. Non esiste nessuna istruzione simmetrica
  che autorizzi magnitudini alte quando l'impatto è chiaro, forte e nuovo.
- Il campo `directness` esiste già nello schema, ma il prompt non dice mai che un
  read-through **può e deve** avere un segno non-negligibile: `directness` è puro
  metadata, disconnesso dalla scala di polarity.

Risultato: segno giusto (il modello capisce la direzione), magnitudine compressa di
un ordine di grandezza sotto il gate 0.30 — esattamente il pattern documentato.

### Difetto 3 — Nessun few-shot example

Confermato per ispezione: zero esempi. Il design DK-CoT del progetto (§9 del design
doc, richiamato anche in CLAUDE.md) prevede "few-shot analogical examples" come punto 3
del metodo, ma `_DK_COT_PROMPT` non ne contiene nessuno. Senza esempi, ogni provider
dell'ensemble interpreta gli intervalli numerici con la propria prior — massima fonte
di divergenza cross-provider e di deriva rispetto a FinBERT (che è il fallback di
calibrazione implicita del sistema).

### Difetto 4 — Nessuna ancora di calibrazione per la magnitudine

Lo schema dichiara solo gli intervalli matematici (`<float -1.0..1.0>`,
`<float 0.0..1.0>`), non la *semantica* degli intervalli. Nulla nel prompt distingue
un 0.3 da un 0.7 in termini osservabili. Combinato con (a) l'asimmetria della regola
"unclear → 0/low" e (b) l'hedging naturale dei modelli senza punti di riferimento, il
bias strutturale è la compressione verso il centro-basso. Il difetto 2 è il sintomo
più visibile di questo difetto, ma il meccanismo è generale.

### Difetto 5 — Bull/bear collassato in una frase

Causato direttamente dallo schema di output: `"reasoning": "<bull/bear analysis, one
sentence>"`. Il prompt *chiede* il bull/bear case (step 3: "What is the bull/bear
case?") ma lo spazio di output gli concede **una sola frase per entrambi**. Il
collasso è nel JSON schema, non nella parte discorsiva — per questo una fix discorsiva
da sola non risolve: serve modificare lo schema (solo Variante B).

---

## Variante A — patch minima (risolve difetti 1 e 2)

Testo completo: `prompts/sentiment_variante_A.txt`. Diff riassunto:

1. **Nuova variabile `{title}`** — l'headline entra come riga separata (`Headline: {title}`) prima di `News: {text}`.
2. **Step 1 riscritto**: da "cosa significa per i fondamentali di QUESTA azienda" a "cosa significa per come il mercato *prezzerà* {symbol}", con esplicito invito a considerare i read-through di pari/competitore/settore come motori di prezzo legittimi.
3. **Step 4 riscritto**: verdict su "likely price impact", non generico.
4. **Nuova regola sul secondo ordine**: il read-through deve ricevere polarity proporzionale al movimento atteso, con confidence ridotta (non azzerata) rispetto a un evento diretto di pari taglio.
5. **Nuova regola headline-vs-body**: se headline e body divergono (giorni/eventi diversi), basare la polarity sull'informazione più recente e specifica e abbassare la confidence. È il fix diretto del caso Robinhood.
6. **Regola "evidence" estesa** a "(headline + body)".

Invariati: schema JSON identico byte-per-byte, struttura DK-CoT, no azioni di trading,
nessun few-shot, nessuna ancora di calibrazione. Stima token **misurata** (`.format()`
con input campione, chars/4): attuale ~315 → Variante A ~530 input (+~70%);
zero crescita dell'output (schema invariato). I due template sono stati verificati
con `.format()` effettivo: nessun `KeyError`.

Variabili nuove lato codice (dichiarazione esplicita):
- `{title}` — serve passare `sanitize_text(item.title)` con un proprio limite
  (suggerito: `SENTIMENT_LLM_TITLE_CHARS`, default 200). Gestire il caso
  `title == ""` (default del dataclass) formattando `"(no headline)"` — un `.format()`
  su titolo vuoto produrrebbe una riga vuota ambigua. Modifica concentrata in
  `run_inference` (`src/workers/sentiment.py:356`).

## Variante B — rewrite ambizioso (difetti 1–5)

Testo completo: `prompts/sentiment_variante_B.txt`. Tutto ciò che ha la Variante A, più:

1. **Tre few-shot example calibrati**, uno per gradino di `directness`, con output JSON
   completo nello schema di produzione:
   - evento diretto forte (beat + raise guidance) → polarity 0.85, confidence 0.85;
   - spillover di pari (peer cloud beat, il nostro ticker sale col settore) → polarity
     0.50, confidence 0.45 — **il calibro che manca al difetto 2, mostrato, non detto**;
   - conflitto headline/body → polarity 0.0, confidence 0.20, `risk_flags`
     `["ambiguous_entity"]`.
2. **Ancora di calibrazione esplicita** per polarity: semantica degli intervalli
   ancorata a move tipiche intraday attribuibili alla notizia
   (0.0–0.2 trascurabile, 0.2–0.4 modesto, 0.4–0.7 significativo, 0.7–1.0 maggiore),
   e per confidence ancorata a chiarezza/fonte/conflitto interno.
3. **Schema JSON modificato**: `reasoning` (una frase) → `bull_case` + `bear_case`
   (una frase ciascuno). Fix strutturale del difetto 5.

Token **misurati** (`.format()` con input campione, chars/4): attuale ~315 → Variante B
~1.200 input (≈3.8x). Giustificazione del trade-off:
- L'output resta ~lo stesso (i due campi da una frase costano ~1 frase in più del
  campo singolo): la **latenza, dominata dalla generazione, cresce poco**; il costo
  cresce quasi solo lato input.
- Con l'ensemble a 2 modelli e decine di migliaia di articoli/mese, il delta è
  ~880 token input × ~60k chiamate ≈ **~50M token/mese extra di solo input** —
  significativo ma non proibitivo; è il prezzo di ancore che agiscono su *tutti* gli
  articoli, non solo su quelli di secondo ordine.
- Raccomandazione operativa: **A prima, B dietro confronto misurato** — A è quasi
  gratis e attacca i due difetti con evidenza empirica; B va validato sul golden set
  QX-01 (`news_labels`) prima di andare in produzione, proprio perché cambia lo schema
  e la distribuzione degli score (vedi Rischi).

Variabili nuove lato codice: `{title}` come in A; **nessun'altra**. I few-shot sono
statici nel template (nessun placeholder).

## Mappa modifica → difetto

| # | Modifica | Variante | Difetto risolto | Note |
|---|----------|----------|-----------------|------|
| 1 | Slot `Headline: {title}` + regola headline-vs-body | A, B | **1** | Fix del caso Robinhood: l'informazione direzionale più fresca entra nel prompt e la divergenza viene gestita, non ignorata |
| 2 | Step 1 "how the market will price {symbol}" + considerazione esplicita dei read-through | A, B | **2** | Cambia la *domanda* da fondamentali a prezzo atteso — il mismatch documentato |
| 3 | Regola "second-order effects count" (polarity proporzionale al read-through, confidence ridotta) | A, B | **2** | Istruzione simmetrica alla regola "unclear → 0" che oggi spinge solo in giù |
| 4 | Tre few-shot calibrati (diretto / spillover / conflitto) | B | **3**, **4** | Il fatto che l'esempio spillover mostri polarity 0.50 aggancia anche il difetto 2 sul piano della magnitudine |
| 5 | Ancora di calibrazione per gli intervalli di polarity/confidence | B | **4** | Semantica osservabile degli intervalli, anti-compressione |
| 6 | `reasoning` → `bull_case` + `bear_case` | B | **5** | Cambia lo schema JSON → parser da aggiornare |
| 7 | Regola "evidence" estesa a "(headline + body)" | A, B | 1 (supporto) | Coerenza col nuovo input |
| — | Verdict su "likely price impact" (step 4) | A, B | 2 (supporto) | Riallinea la domanda finale al caso d'uso |

Nessuna modifica proposta è un "miglioramento indipendente" scollegato dai 5 difetti.

## Rischi

1. **Overfitting sui few-shot (B).** Gli esempi ancorano non solo la scala ma i
   pattern: se i tre esempi sono tutti tech/earnings, i modelli possono copiare le
   magnitudini invece di generalizzare. Mitigazione: esempi scelti su tre gradini
   *diversi* di `directness` (non tre eventi direttili), nessun ticker reale
   dell'universo tradito, validazione sul golden set prima del rollout. Rischio
   residuo comunque reale: è il motivo per tenere B dietro misura.
2. **Rottura del parser (B, modifica 6).** `bull_case`/`bear_case` rompe chi legge
   `reasoning` (worker, dashboard, eventuali consumatori storici). Serve aggiornare
   il parser e decidere la policy di backfill: gli score pre-B non sono direttamente
   confrontabili con i post-B nei report longitudinali (contaminazione dei trend ICIR
   e della LOO rebalancing dei pesi ensemble — quei pesi sono calibrati su score
   generati col prompt vecchio).
3. **Divergenza cross-provider (B > A).** I due modelli cloud e FinBERT interpretano
   le ancore verbali ("significant", "major") in modo diverso; i few-shot riducono la
   varianza ma non la azzerano. L'ensemble variance check esistente diventa più
   critico: monitorare la divergenza pre/post rollout per provider.
4. **Overweight dell'headline (A, B).** L'headline è editoriale e può essere
   clickbait o riferita a un tema macro non issuer-specific: dare freschezza al
   titolo può spostare il modello verso il sentiment del *titolo* invece che
   dell'issuer. Mitigazione: la regola headline-vs-body chiede confidence bassa in
   caso di conflitto, non fiducia cieca; il titolo va passato sanitizzato e troncato.
5. **Costo/latenza.** A: +~70% input (~315 → ~530 token), trascurabile. B: ~3.8x
   input (~50M token/mese con
   l'ensemble a 2 su decine di migliaia di articoli/mese); latenza poco peggiorata
   perché l'output resta compatto, ma il prefill cresce e su batch alto volume il
   costo è il vincolo reale.
6. **Disponibilità del titolo (A, B).** `NewsItem.title` ha default `""`: senza il
   fallback `"(no headline)"` il template rende una riga vuota ambigua; alcune sorgenti
   potrebbero non fornire affatto il titolo — il prompt non deve degradare in quel caso.
7. **Compatibilità storica degli score (A e B).** Anche la sola A cambia la
   distribuzione degli score (spillover ora sopra soglia): il gate vedrà trade che
   prima non partivano. È voluto (è la finalità), ma i confronti before/after e i
   pesi ensemble calibrati LOO vanno ricalcolati dalla data di rollout in poi.

Fuori scope, come da vincolo: nessuna proposta tocca la soglia di gate (0.30) o
altri parametri di rischio.