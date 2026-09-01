Sei un prompt engineer esperto di sistemi di trading algoritmico e di LLM-as-judge per
sentiment financial analysis. Devi proporre una versione migliorata di un prompt di
produzione, non spiegazioni teoriche generiche.

## Contesto del sistema

Un sistema di trading algoritmico (long-only, azioni USA) usa un ensemble di 2 LLM in
parallelo per assegnare un punteggio di sentiment a ogni articolo di news, per un singolo
ticker alla volta. Il punteggio finale è:

    score = polarity × confidence

dove polarity ∈ [-1, +1] e confidence ∈ [0, 1]. Lo score alimenta un gate d'ingresso
(soglia tipica 0.30 in valore assoluto): sotto soglia, il trade non parte, indipendentemente
da quanto si sia mosso il titolo. Il sistema è long-only: un segno negativo forte su un
titolo non detenuto non genera un trade (nessuno short).

Vincoli non negoziabili sul design del prompt:
- Deve restare un prompt DK-CoT (Domain Knowledge Chain-of-Thought): ruolo assegnato,
  ragionamento step-by-step esplicito, richiesta di caso bull/bear, output finale
  strutturato.
- Il modello NON deve mai proporre un'azione di trading (no buy/sell/hold) — solo feature
  di segnale (polarity, confidence, ecc.).
- L'output deve essere JSON valido secondo uno schema fisso e parsabile deterministicamente
  (nessun testo fuori dal JSON).
- Il prompt gira, IDENTICO, su più provider LLM diversi in un ensemble (in produzione:
  due modelli cloud diversi + un fallback FinBERT locale) — deve produrre output
  comparabile e consistente su modelli diversi, non ottimizzato per le idiosincrasie di
  uno solo.
- Budget: il prompt attuale gira su un batch alto volume (decine di migliaia di articoli/
  mese), quindi lunghezza e costo/latenza contano — non proporre un prompt 5-10x più lungo
  senza giustificarlo esplicitamente.
- Deve restare issuer-specific: il compito è valutare l'impatto SOLO sul ticker indicato,
  non sentiment generico sulla news.

## Prompt attuale in produzione

    You are a buy-side equity analyst. Assess this news item's impact on the SPECIFIC issuer below.

    Think step-by-step:
    1. What does this mean for THIS company's revenue, cash flows and competitive position?
    2. Is the impact direct, or only an indirect read-through (customer/supplier/competitor/sector/macro)?
    3. How material and how novel (not already priced in) is it? What is the bull/bear case?
    4. What is your overall verdict?

    Rules:
    - Sentiment must be issuer-specific (about {symbol}, not the news in general).
    - Do NOT output a trading action (no buy/sell/hold) — only the signal features below.
    - Use only evidence in the article; if the market impact is unclear, set polarity=0, confidence low.

    News: {text}
    Ticker: {symbol}

    Respond ONLY with valid JSON matching this schema:
    {"polarity": <float -1.0..1.0>, "confidence": <float 0.0..1.0>, "reasoning": "<bull/bear analysis, one sentence>", "event_type": "earnings|guidance|mna|regulatory|lawsuit|analyst_rating|product|management|macro|other", "directness": "direct|customer_supplier|competitor_readthrough|sector|macro|unclear", "materiality": <0.0..1.0>, "novelty": <0.0..1.0>, "risk_flags": ["rumor"|"already_priced_in"|"ambiguous_entity"|"low_source_quality"], "evidence_sentences": ["<key sentence>"]}

Nota importante: {text} nel codice attuale è SOLO il corpo/snippet dell'articolo — il
titolo dell'articolo NON viene mai passato al modello, anche quando disponibile.

## Difetti empirici documentati in produzione (evidenza reale, non ipotetica)

1. **Titolo mai incluso.** Un articolo intitolato "Why Is Robinhood Stock Surging on
   Tuesday?" con un body_snippet salvato che parlava di un giorno diverso e di segno
   opposto ("stock traded lower Thursday after...") ha prodotto score -0,0098 su una
   giornata +8,17% — e quello score errato è rimasto lo stato del sistema per 2 sedute
   perché nessun articolo migliore lo ha sostituito.

2. **Notizie di "secondo ordine" sotto-scorate.** Quando il titolo nomina il nostro
   ticker ma la causa è di terzi (es. "Adobe stock is trading higher following quarterly
   earnings from Salesforce"), il segno assegnato è sempre corretto ma la magnitudine è
   sistematicamente un ordine di grandezza sotto la soglia di gate (es. polarity×confidence
   = 0,060 su un titolo che si è mosso +5,73% quel giorno). Ipotesi non confermata: il
   prompt chiede "cosa significa per i fondamentali di QUESTA azienda" — per una notizia
   di spillover la risposta onesta a quella domanda specifica è "poco", quindi il modello
   risponde bene alla domanda sbagliata per il caso d'uso (che è "quanto si muoverà il
   prezzo", non "quanto cambiano i fondamentali").

3. **Nessun few-shot example nel prompt** — zero esempi calibrati di cosa corrisponde a
   quale intervallo di polarity/confidence.

4. **Nessuna ancora di calibrazione esplicita** per la magnitudine (es. cosa distingue
   un 0.3 da un 0.7 in termini di materialità reale) — sospetto (non confermato) che il
   modello tenda a comprimersi verso valori centrali/bassi per hedging in assenza di punti
   di riferimento, coerente con l'osservazione del punto 2.

5. **Bull/bear case collassato in una sola frase** nel campo "reasoning" — meno
   tracciabile/auditabile di due campi distinti.

## Cosa devi produrre

1. **Diagnosi**: per ciascuno dei 5 difetti sopra, di' se e come il prompt attuale lo
   causa o lo aggrava strutturalmente (frase per frase, citando la parte del prompt).
2. **Prompt rivisto, testo completo**, pronto per sostituire quello attuale — con
   placeholder Python `.format()` per le variabili che introduci (dichiara esplicitamente
   quali variabili nuove servono lato codice, es. {title} oltre a {text}/{symbol}).
3. **Mappa esplicita modifica → difetto**: ogni cambiamento che proponi deve essere
   collegato a quale dei 5 punti risolve, o dichiarato come "miglioramento indipendente"
   se non risolve nessuno dei 5.
4. **Due varianti**, non una sola:
   - **Variante A (patch minima)**: il più piccolo diff che risolve i punti 1 e 2 (i due
     con evidenza empirica reale in produzione), lasciando tutto il resto invariato.
   - **Variante B (rewrite più ambizioso)**: incorpora anche few-shot e calibrazione,
     accettando un prompt più lungo — quantifica di quanto (token stimati) e giustifica
     il trade-off costo/latenza.
5. **Rischi che la tua proposta introduce**: es. few-shot che orientano/overfittano il
   modello verso i pattern degli esempi invece di generalizzare; JSON schema che rompe il
   parser esistente; comportamento diverso fra i provider dell'ensemble; verbosità che
   aumenta latenza/costo per articolo.
6. Non proporre di cambiare la soglia di gate (0.30) o altri parametri di rischio — è
   fuori scope, il compito è SOLO il testo del prompt.

Rispondi con questa struttura esatta: ## Diagnosi, ## Variante A, ## Variante B, ## Mappa
modifica→difetto, ## Rischi.

---

## Appendice — da mandare DOPO la risposta al prompt principale (secondo messaggio)

Prima di consegnare le tue Variante A e Variante B come definitive, fai una verifica
esterna:

1. **Cerca (con ricerca web se disponibile, altrimenti richiama dalla tua conoscenza
   addestrata, dichiarandolo esplicitamente) le best practice consolidate per il prompting
   di LLM su sentiment financial/news analysis.** In particolare, verifica se esistono
   tecniche note e documentate su:
   - Calibrazione di punteggi continui/probabilità elicitati da un LLM (il problema noto
     di "verbalized confidence" che tende a essere overconfident o compresso verso il
     centro a seconda del modello) — e come mitigarlo nel prompt stesso (ancore numeriche,
     rubric esplicita, esempi calibrati).
   - Few-shot prompting per classificazione/scoring finanziario: quanti esempi, come
     selezionarli per non introdurre bias verso i pattern degli esempi, se conviene
     includere esempi "difficili" (secondo ordine, spillover, sarcasmo/ironia) oltre a
     quelli ovvi.
   - Gestione esplicita di eventi "di terzi"/spillover in un compito issuer-specific
     (sympathy moves, notizie su un competitor/cliente/fornitore che muovono il titolo) —
     se la letteratura o le implementazioni note (es. FinBERT, FinGPT, BloombergGPT,
     paper accademici su news-driven trading con LLM) trattano questo caso in modo diverso
     da un semplice "assess impact on this issuer".
   - Structured output/JSON reliability da un ensemble di modelli diversi: tecniche note
     per aumentare la consistenza cross-model (function calling vs JSON-in-testo, schema
     più o meno rigido, temperatura/determinismo).
   - Uso di chain-of-thought "nascosto" vs "esposto" quando l'output finale deve essere
     solo JSON strutturato (rischio: forzare troppo presto il JSON tronca il ragionamento;
     lasciarlo troppo libero rischia di far trapelare un verdetto di trading vietato).

2. **Per ogni pratica trovata**, dichiara la fonte (paper, documentazione di un prodotto
   noto, post tecnico, o "conoscenza generale di training" se non citabile puntualmente) e
   di' esplicitamente se la tua Variante A/B già la rispetta, la contraddice, o non la
   tratta affatto.

3. **Se una pratica consolidata contraddice una scelta che hai fatto**, non riscrivere
   silenziosamente la variante: elenca il conflitto e proponi esplicitamente se e come
   risolverlo, motivando la scelta finale (a volte il vincolo di produzione — es. ensemble
   multi-provider, budget di token, JSON rigido — ha precedenza legittima sulla best
   practice generica).

4. Non introdurre in questo passaggio nuovi vincoli di business che non erano nel prompt
   principale (soglia di gate, sizing, execution) — resta scope solo sul testo del prompt
   e sulla sua fondatezza rispetto allo stato dell'arte.

Rispondi a questa appendice con: ## Best practice trovate (con fonte), ## Confronto con
Variante A, ## Confronto con Variante B, ## Conflitti irrisolti (se presenti).

