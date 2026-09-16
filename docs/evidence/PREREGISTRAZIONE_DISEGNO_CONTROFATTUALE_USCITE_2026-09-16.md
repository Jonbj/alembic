# Pre-registrazione — disegno del controfattuale sulle uscite

Scritta il **2026-09-16**, prima di qualunque ricerca bibliografica e prima di scrivere
una riga del controfattuale. Non è una pre-registrazione di misura: è una
pre-registrazione **di disegno**. Fissa le scelte metodologiche e i criteri di
accettazione *prima* di vedere un solo numero controfattuale, perché la caratteristica di
questo strumento è che **può essere costruito in modo da dare la risposta che si
preferisce**, senza che nulla sembri sbagliato.

Issue: #614

Domanda a valle che alimenta: il ribilanciatore (`portfolio_sell`) sta chiudendo troppo
presto? Nella finestra di osservazione porta **63 uscite su 114 e −$447,81 su −$463,93**,
cioè il 97% della perdita realizzata, ed è lo stesso meccanismo che produce i **0,7
giorni** di detenzione mediana di S4.

## 1. La domanda metodologica, in una frase

> Come si costruisce un controfattuale di uscita che rispetti il vincolo di capitale, in
> modo che il risultato non sia determinato dal disegno?

## 2. Gli artefatti attesi, elencati PRIMA di cercare

Se dopo la ricerca ne emergessero altri, si aggiungono e si annota che sono emersi dopo.
Questi sei sono dichiarati ora:

1. **Benchmark a capitale infinito.** Confrontare «tenuto X» contro «venduto X e cash»
   prezza un portafoglio che può comprare tutto. Dice quasi sempre che avremmo dovuto
   tenere, perché i mercati salgono in media.
2. **Displacement ignorato.** Il ribilanciatore vende **per fare posto**. Il confronto
   onesto è «tenuto X» contro «comprato Y col ricavato», e Y è noto: è ciò che ha
   comprato davvero quel giorno.
3. **Capitale-tempo non normalizzato.** Tenere X per 10 sedute in più impegna capitale per
   10 sedute. Confrontare P&L grezzi favorisce strutturalmente la detenzione.
4. **Costi contati una volta sola.** Tenere **risparmia** un round-trip, ma **impedisce**
   l'acquisto sostitutivo e il suo costo. Contare solo il risparmio gonfia il tenere.
5. **Finestre sovrapposte.** Detenzioni estese si sovrappongono fra loro e sul fattore di
   mercato: l'inferenza ingenua è fortemente ottimistica.
6. **Selezione sull'uscita.** Il ribilanciatore vende secondo un criterio. Se quel
   criterio ha una qualunque abilità, un controfattuale che ignora *perché* ha venduto
   misura l'abilità, non la cadenza.

## 3. Le scelte di disegno che si fissano ORA

Queste **non** dipendono dall'esito della ricerca e si congelano qui.

- **Il controfattuale è a livello di PORTAFOGLIO, non di singolo trade.** Si rigioca
  l'intero portafoglio con la regola modificata e si confronta l'equity terminale. Un
  controfattuale per-trade è la fonte diretta degli artefatti 1, 2, 3 e 4: il replay di
  portafoglio li gestisce per costruzione, perché il vincolo di budget vincola davvero.
- **Si riusa `src/backtest/engine/portfolio.py`**, non si riscrive la contabilità di
  portafoglio (regola #169/#467).
- **Costi da `src/backtest/costs/`**, mai zero, su **entrambi** i rami.
- **Orizzonti di estensione dichiarati ora:** 1, 2, 5, 10, 21 sedute. Nessun altro.
- **La regola modificata non può leggere il futuro.** I prezzi futuri entrano solo nella
  valutazione, mai nella decisione.
- **Newey-West** con lag pari all'orizzonte ovunque si pubblichi un `t`.

## 4. Criterio di accettazione — il cancello che viene prima di tutto

> **Con la regola invariata, il replay deve riprodurre la storia realmente accaduta.**

Se il simulatore girato con la regola vera non restituisce il P&L vero entro una
tolleranza dichiarata prima, **nessun risultato controfattuale a valle è credibile** e il
lavoro si ferma lì.

Tolleranza dichiarata: **±2% sull'equity terminale della finestra**, e la differenza va
spiegata, non solo dichiarata sotto soglia.

Precedente che rende questo cancello non negoziabile: la riconciliazione del P&L del
2026-09-16. Il ponte fra `net_pnl` realizzato e `economic_pnl.json` chiude al centesimo,
ma **solo** dopo aver scoperto che `BOOK` è il totale e non un bucket, e che mescolare
`net_pnl` (basato sui fill, costi inclusi) con un marking di prezzo produce un residuo del
58%. Un controfattuale che parte da una contabilità non riconciliata eredita quell'errore
e lo amplifica.

## 5. La ricerca bibliografica — perimetro chiuso

Strumento: la skill `alembic-strategy-audit`, che è già progettata per la ricerca di
letteratura autorevole per strategia. **Non** la campagna sui due nodi: quella è una
pipeline di estrazione su corpus fisso, con resa misurata di ~2 claim per chiamata
(`docs/research/s4-web-validation-2026-08-28/PROBE_RESULT_2026-09-14.md`) e 1 esito utile
in 11 notti.

**Lista chiusa delle domande.** Una domanda aggiunta dopo aver letto le fonti va
etichettata come tale.

- Q1 — Qual è il benchmark corretto per un controfattuale di uscita sotto vincolo di
  capitale, e come tratta la letteratura il displacement dell'acquisto sostitutivo?
- Q2 — Come si normalizza per capitale-tempo quando le durate differiscono fra i rami?
- Q3 — Che inferenza si usa con detenzioni sovrapposte e clustering per giornata?
- Q4 — Qual è l'evidenza replicata sull'efficacia degli **stop-loss** nelle strategie
  cross-sectional, e in quali condizioni distruggono rendimento?
- Q5 — Cosa dice la letteratura sull'**orizzonte ottimale** per segnali news/PEAD, e sul
  loro decadimento?

**Regola anti-selezione:** le fonti si registrano in un manifest **mentre** si leggono,
con l'esito (a favore, contro, non pertinente) annotato **prima** di passare alla
successiva. Una fonte non può essere rimossa dal manifest dopo essere stata letta.

**Barra di qualità:** pubblicazioni peer-reviewed o working paper di istituzioni
riconoscibili. Post di blog e materiale di vendor ammessi solo come segnalazione di una
fonte primaria, mai come evidenza.

**Q4 e Q5 hanno una proprietà che Q1-Q3 non hanno**, e va sfruttata: a differenza della
letteratura sull'alpha — che decade dopo la pubblicazione, ed è il motivo per cui il
corpus S4 esistente è pieno di cautele — l'efficacia degli stop e il decadimento PEAD sono
risultati replicati e poco soggetti ad arbitraggio. Sono quindi **utilizzabili come prior**,
non solo come contesto.

## 6. Cosa questo documento NON autorizza

- Nessuna modifica al path live. Cadenza di ribilanciamento, stop e orizzonti sono
  **taratura**: restano congelati fino al 2026-09-28 e la decisione è dell'operatore.
- Nessuna misura eseguita: qui si fissa il disegno. Il controfattuale vero, quando sarà
  scritto, avrà bisogno della propria riga in `docs/evidence/OBSERVATION_CHARTER.md`.
- Nessuna conclusione su S4. Il ribilanciatore chiude posizioni di tutte le strategie:
  questa domanda **sopravvive** a qualunque esito del 28/09 su S4.
