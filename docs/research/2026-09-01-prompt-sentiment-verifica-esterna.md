# Verifica esterna delle varianti del prompt sentiment — 2026-09-01

Appendice a `docs/research/2026-09-01-prompt-sentiment-ottimizzazione.md` (prompt
principale in `prompts/ottimizza_prompt_sentiment.md`). Verifica fatta con **ricerca
web** (fonti citate sotto); dove un punto riposa solo su conoscenza di training è
dichiarato esplicitamente.

Esito in sintesi: la verifica **conferma** l'impianto di entrambe le varianti, ha
portato a **3 correzioni alla Variante B** (schema field order, esempio few-shot
negativo mancante, clausola sul segno invertito per competitor diretti) e lascia
**5 conflitti irrisolti** documentati in fondo, di cui 2 richiedono misura sul
golden set QX-01 e non sono risolvibili lato prompt.

---

## Best practice trovate (con fonte)

### BP1 — Calibrazione della confidence "verbalizzata"

- **[Tian et al., EMNLP 2023 "Just Ask for Calibration"](https://aclanthology.org/2023.emnlp-main.330.pdf)**: nei modelli post-RLHF la confidence *verbalizzata* (numero nel testo) è meglio calibrata dei log-prob; chiedere più ipotesi alternative ("considering the opposite") migliora ulteriormente la calibrazione.
- **[Xiong et al., ICLR 2024](https://arxiv.org/abs/2306.13063v1)**: la confidence verbalizzata è **sistematicamente overconfident** (cluster 80–100%, ECE >37% su GPT-3/3.5/Vicuna); CoT e prompting multi-step migliorano; i metodi ibridi sono i migliori.
- **[Yang et al., 2024 "On Verbalized Confidence Scores"](https://arxiv.org/pdf/2412.14737)**: l'affidabilità dipende fortemente da *come* si chiede; per modelli grandi la combinazione migliore è **descrizione esplicita della scala + few-shot + formulazione "probabilità che la risposta sia corretta"**.
- **[Kim & Kang, protocol sensitivity](https://arxiv.org/html/2605.27752v1)** e **[saturazione al ceiling nei 3–9B](https://arxiv.org/html/2604.22215v1)**: la misura è protocol-dipendente e i modelli piccoli saturano a confidence ≥95%.
- Implicazione operativa: chiedere `confidence` come numero nudo senza semantica è la formulazione peggiore (Yang); le ancore numeriche e la richiesta bull/bear (= "considering the opposite", Tian) sono le mitigazioni note *dentro* il prompt.

### BP2 — Few-shot per sentiment finanziario

- **[Wei & Liu, 2025, ICL per financial sentiment](https://doi.org/10.48550/arxiv.2503.04873)** (10 LLM su FiQA/Twitter): l'ICL batte lo zero-shot; l'efficacia è **altamente sensibile alla selezione degli esempi**; la selezione per difficoltà/cluster è migliore di quella random; i casi **ambigui/neutri** sono quelli che beneficiano di più.
- **[Fatemi & Hu, 2023](https://doi.org/10.48550/arxiv.2312.08725)**: 1-shot migliora quasi sempre, ma **5-shot e 10-shot spesso peggiorano** (gestione del contesto lungo, sensibilità al sampling random). Zona dolce: pochi esempi, semanticamente scelti.
- **[BlackRock, ICAIF "Reasoning or Overthinking"](https://dl.acm.org/doi/10.1145/3768292.3770341)**: nel loro eval **evitano il few-shot del tutto** per il bias di selezione esempi e label leakage; notano bias sistematico verso la classe positiva su alcuni modelli.
- **[Fei et al., label bias nell'ICL](https://arxiv.gg/abs/2305.19148)** e **[Maximum Information Gain, EMNLP 2023 Findings](https://doi.org/10.18653/v1/2023.findings-emnlp.1060)**: il set di esempi introduce bias di label (vanilla/context/domain) — un set sbilanciato verso un segno/classe degrada le predizioni su quella opposta.

### BP3 — Spillover / eventi di terzi in compiti issuer-specific

- **[Nature Scientific Reports 2021](https://www.nature.com/articles/s41598-021-82338-6)**: il sentiment media su un'azienda **si propaga alle aziende collegate** (stesso settore e oltre), con abnormal returns e volatilità elevate anche sui vicini di rete — effetto asimmetrico (più forte sul negativo).
- **[HERALD, Applied Intelligence 2026](https://link.springer.com/article/10.1007/s10489-026-07407-7)**: usa un LLM per inferire da headline l'**insieme dei titoli colpiti** con i path di spillover (competitor, peer, fornitore/cliente); gli insiemi efficaci restano piccoli (5–10 titoli); **il segno direzionale dello spillover è un gap di ricerca aperto** (notizia negativa su X può *beneficiare* il competitor).
- **[Cross-Stock Predictability, 2026](https://arxiv.org/html/2604.19476)**: nel loro framework gli edge di tipo *competitor* vengono **rimossi** perché il buon risultato di un competitor può muovere il titolo nostro in direzione opposta (market share).
- **[Kirtac, ACL 2026](https://aclanthology.org/2026.evaleval-1.4.pdf)**: per attribuzione pulita dei rendimenti limitano l'analisi alle news **single-firm**; il segnale è più forte dove le frizioni rallentano l'incorporazione del prezzo.
- **[BloombergGPT, 2023](https://arxiv.org/pdf/2303.17564)**: task di sentiment **aspect-specific** ("what is the sentiment *on {target}*") e l'insight citato nel paper: "taglio di 10.000 posti" è negativo in generale ma **positivo per la fiducia dell'investitore** — cioè il framing corretto è la prospettiva investitore/prezzo, non il sentiment generico. **[FinGPT](https://github.com/AI4Finance-Foundation/FinGPT/tree/master/fingpt/FinGPT_Sentiment_Analysis_v3)** usa etichette generate anche da **movimenti di prezzo** (RLSP: ±2%), stessa direzione: il ground truth rilevante è il movimento, non l'opinione.
- Implicazione operativa: il reframing di entrambe le varianti ("come il mercato prezzerà {symbol}" invece di "cosa cambia nei fondamentali") è **allineato** a BloombergGPT/FinGPT/HERALD; ma nessuno dei due prompt trattava il caso **competitor diretto con segno invertito** (buon risultato del competitor = negativo per noi).

### BP4 — Structured output cross-provider

- **[Requesty, 244 modelli / 23 provider](https://www.requesty.ai/blog/structured-outputs-across-llm-providers-the-compatibility-mess)**: pass rate sullo strict structured output varia per endpoint; ogni provider onora un **sottoinsieme diverso di JSON Schema**; raccomandazioni: schema **piatti, campi required, enum**, disegnati sull'intersezione, validazione al confine (Pydantic/parser).
- **[JSON mode vs function calling vs constrained decoding](https://dreaming.press/posts/json-mode-vs-function-calling-vs-constrained-decoding.html)**: JSON mode garantisce solo la sintassi; lo strict structured output (constrained decoding) arriva a ~100% di conformità; la garanzia per-schema **non esiste nel prompting puro**.
- Implicazione per noi: lo schema attuale (oggetto piatto, enum, array di stringhe, nessun nesting) è già nel sottoinsieme portabile; il parser deterministico in casa è la mitigazione giusta per l'assenza di garanzia nativa.

### BP5 — CoT nascosto vs esposto con output JSON-only

- **[JSONKit, "The Format Tax"](https://jsonkit.in/blog/format-tax-json-schema-llm-reasoning)**: forzare lo schema JSON dal primo token degrada il ragionamento di 15–35%; la causa è l'**ordine delle chiavi** — se i campi-numero (verdict, score) precedono il campo reasoning, il modello si impegna sulla risposta *prima* di ragionare. Miglior pattern a chiamata singola: **campo di reasoning come prima proprietà dello schema**; il migliore assoluto è two-phase (scratchpad libero → formattazione), che però raddoppia le chiamate.
- **[Fractured CoT, arXiv 2505.12992](https://ar5iv.labs.arxiv.org/html/2505.12992)**: un ragionamento *troncato* mantiene la maggior parte del beneficio — conferma che bull/bear da una frase ciascuno sono un compromesso ragionevole.
- **[Goldberg, gist](https://gist.github.com/yoavg/5b106275e38f4ccc796bc8ba7919060b)**: il CoT *dentro* un campo JSON è meno efficace del CoT fuori dai campi (ma meglio di niente) e sfuma la separazione codice/dati.
- **[Stack Underflow](https://thestackunderflow.com/tutorials/hide-reasoning-from-structured-output/)**: pattern a due stadi con thinking nascosto e tool call forzata; accoppia canali se reasoning e answer sono sibling nello stesso oggetto.
- Implicazione per noi: **lo schema attuale mette `polarity` e `confidence` PRIMA del campo di ragionamento** — esattamente l'anti-pattern del format tax, in produzione oggi e in entrambe le mie varianti al momento della consegna.

## Confronto con Variante A

| Best practice | Stato in A | Dettaglio |
|---|---|---|
| BP1 calibrazione confidence | **Non tratta** | Per design (patch minima sui soli difetti con evidenza empirica). La formulazione nuda di `confidence` resta quella peggiore secondo Yang et al. — accettato come limite esplicito di A. |
| BP2 few-shot | **Non tratta (zero-shot)** | Coerente con lo scope di A; BlackRock mostra che zero-shot è una scelta difendibile. |
| BP3 spillover | **Rispettata** | Il reframing "how the market will price {symbol}" + regola second-order è allineato a BloombergGPT (prospettiva investitore), FinGPT (ground truth = movimento) e Nature/HERALD (spillover reale e price-relevant). Manca la clausola competitor-inversion (vedi conflitto #4) — aggiunta solo in B. |
| BP4 structured output | **Rispettata** | Schema invariato: piatto, enum, nessun nesting — dentro il sottoinsieme portabile; zero rischio parser. |
| BP5 format tax | **Contraddetta, per vincolo di produzione** | A mantiene `polarity`/`confidence` prima del reasoning: la correzione richiede riordinare lo schema, cioè un diff di schema che A esclude per definizione (parser compat). Precedenza legittima documentata, non risolta in A. |

## Confronto con Variante B

Stato **alla consegna** (prima delle correzioni di questa verifica) → correzioni applicate:

| Best practice | Stato in B alla consegna | Correzione applicata |
|---|---|---|
| BP1 calibrazione | **Parzialmente rispettata**: ancore numeriche per polarity, descrizione qualitativa per confidence, few-shot con confidence variabili (la combo "descrizione + few-shot" è la migliore per modelli grandi secondo Yang). Il bull/bear obbligatorio implementa "considering the opposite" (Tian). | Nessuna prompt-side; resta il rischio di overshoot (vedi conflitto #1). |
| BP2 few-shot | **Parzialmente contraddetta**: 3 esempi (nella zona dolce 1–3 di Fatemi & Hu), selezionati per difficoltà (secondo ordine + conflitto, i casi ambigui che più beneficiano per Wei & Liu), ticker fittizi → nessun label leakage. MA: **nessun esempio a polarity negativa** → vanilla-label bias potenziale (Fei et al.; lo stesso bias positivo notato da BlackRock). | **Sì**: l'Esempio 1 è stato riscritto come evento diretto *negativo* (probe DOJ + ritiro guidance → −0.8). Segni ora bilanciati: −0.8 / +0.5 / 0.0. |
| BP3 spillover | **Rispettata sul caso documentato** (peer/sector lift, simpatia stessa-direzione), **non trattava il competitor con segno invertito** — il caso che Cross-Stock Predictability gestisce rimuovendo gli edge competitor e che HERALD dichiara gap aperto. | **Sì**: aggiunta clausola esplicita — il segno del read-through può invertirsi per competitor diretti (market share): valutare la direzione *per {symbol}*. |
| BP4 structured output | **Rispettata**: schema piatto/enum/required, parser invariato sulle chiavi. | Nessuna (il reorder di BP5 non tocca le chiavi, solo l'ordine — un parser per chiave non se ne accorge). |
| BP5 format tax | **Contraddetta**: anche B metteva `polarity`/`confidence` prima di `bull_case`/`bear_case`. | **Sì**: schema riordinato — `bull_case` e `bear_case` ora sono le prime proprietà, i numeri dopo; aggiunta istruzione "set bull_case and bear_case before the numeric scores". Il two-phase scratchpad (il migliore per JSONKit) è **respinto per budget**: raddoppia le chiamate per articolo per modello su un batch di decine di migliaia di articoli/mese. |

Le tre correzioni sono applicate a `prompts/sentiment_variante_B.txt` e dichiarate nel
suo header (changelog) — nessuna riscrittura silenziosa. Nessuna correzione tocca la
Variante A, che resta la patch minima sui difetti 1 e 2.

## Conflitti irrisolti (se presenti)

1. **Direzione della distorsione sulla confidence: la letteratura dice overconfident, la nostra produzione osserva compressione.** Xiong et al. documentano cluster 80–100%; il nostro difetto documentato è magnitudine compressa. Le ancore di B potrebbero **overshottare** verso l'overconfident una volta rimosso l'hedging. Non risolvibile lato prompt senza misura: la risoluzione è il confronto pre/post su golden set QX-01 (`news_labels`) prima del rollout di B. A è immune (non tocca la calibrazione).
2. **Prompt-based JSON vs structured output nativo del provider.** La best practice (Requesty, constrained decoding) sarebbe usare lo strict structured output nativo; noi manteniamo JSON-in-testo con prompt identico sui provider, perché (a) l'ensemble è 2 modelli cloud + FinBERT fallback e il prompt identico è il vincolo di comparabilità, (b) non tutti i path supportano function calling uniforme. Precedenza di produzione legittima; costo accettato: nessuna garanzia grammaticale, mitigata dal parser deterministico esistente e dalle statistiche `parse_fail` già raccolte.
3. **CoT dentro i campi JSON vs CoT fuori (Goldberg).** Goldberg mostra che il CoT in-field è meno efficace; il pattern a due stadi (scratchpad libero → JSON) è il migliore ma raddoppia le chiamate — escluso per budget. Il reorder reasoning-first è la mitigazione massima raggiungibile a chiamata singola. Perdita residua accettata e documentata.
4. **Segno dello spillover competitor = gap di ricerca aperto (HERALD).** Chiedere al modello di giudicare il segno per {symbol} è esattamente l'area che la letteratura dichiara non risolta. Mitigato in B dalla clausola + confidence ridotta sul read-through; non eliminabile. Da monitorare sul golden set per sottogruppo `directness=competitor_readthrough`.
5. **Few-shot sì/no: evidenza letteratura conflittuale.** Wei & Liu / Fatemi & Hu trovano benefici; BlackRock evita il few-shot nei loro eval per bias di selezione e leakage. Non decidibile sulla carta: è il motivo per cui la raccomandazione operativa resta **A prima (zero-shot, quasi gratis, attacca i difetti con evidenza), B dietro validazione misurata sul golden set**. Se il golden set resta a n=0 (situazione attuale per enforcement), B non va in produzione.

---

### Fonti

- [Tian et al., Just Ask for Calibration, EMNLP 2023](https://aclanthology.org/2023.emnlp-main.330.pdf)
- [Xiong et al., Can LLMs Express Their Uncertainty?, ICLR 2024](https://arxiv.org/abs/2306.13063v1)
- [Yang et al., On Verbalized Confidence Scores for LLMs, 2024](https://arxiv.org/pdf/2412.14737)
- [Kim & Kang, Asking Is Not Enough: Protocol Sensitivity](https://arxiv.org/html/2605.27752v1)
- [Verbal Confidence Saturation in 3–9B LLMs](https://arxiv.org/html/2604.22215v1)
- [Wei & Liu, Are LLMs Good In-context Learners for Financial Sentiment Analysis?, 2025](https://doi.org/10.48550/arxiv.2503.04873)
- [Fatemi & Hu, Fine-Tuned vs Few-Shot LLMs for Financial Sentiment, 2023](https://doi.org/10.48550/arxiv.2312.08725)
- [BlackRock, Reasoning or Overthinking, ACM ICAIF](https://dl.acm.org/doi/10.1145/3768292.3770341)
- [Fei et al., Mitigating Label Biases for In-context Learning](https://arxiv.gg/abs/2305.19148)
- [Maximum Information Gain Example Selection, EMNLP 2023 Findings](https://doi.org/10.18653/v1/2023.findings-emnlp.1060)
- [Sentiment correlation in financial news networks, Nature Sci Rep 2021](https://www.nature.com/articles/s41598-021-82338-6)
- [HERALD: Event-Driven Hypergraph Networks, Applied Intelligence 2026](https://link.springer.com/article/10.1007/s10489-026-07407-7)
- [Cross-Stock Predictability via LLM-Augmented Semantic Networks, 2026](https://arxiv.org/html/2604.19476)
- [Kirtac, LLM News Sentiment under Liquidity and Market Frictions, ACL 2026](https://aclanthology.org/2026.evaleval-1.4.pdf)
- [BloombergGPT, 2023](https://arxiv.org/pdf/2303.17564) · [FinGPT Sentiment v3](https://github.com/AI4Finance-Foundation/FinGPT/tree/master/fingpt/FinGPT_Sentiment_Analysis_v3)
- [Requesty, Structured Outputs Across LLM Providers: 244 Models Tested](https://www.requesty.ai/blog/structured-outputs-across-llm-providers-the-compatibility-mess)
- [JSON Mode vs Function Calling vs Constrained Decoding](https://dreaming.press/posts/json-mode-vs-function-calling-vs-constrained-decoding.html)
- [JSONKit, The Format Tax](https://jsonkit.in/blog/format-tax-json-schema-llm-reasoning)
- [Fractured Chain-of-Thought Reasoning, arXiv 2505.12992](https://ar5iv.labs.arxiv.org/html/2505.12992)
- [Goldberg, Structured CoT breaks language-use principles](https://gist.github.com/yoavg/5b106275e38f4ccc796bc8ba7919060b)
- [The Stack Underflow, Hide Reasoning From Structured Output](https://thestackunderflow.com/tutorials/hide-reasoning-from-structured-output/)