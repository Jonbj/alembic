# Pre-registrazione — misura del controfattuale sulle uscite

Scritta il **2026-09-24**, prima di eseguire qualunque ramo controfattuale e prima di
vedere qualunque numero controfattuale. È la pre-registrazione di **misura** che la
pre-registrazione di [disegno](PREREGISTRAZIONE_DISEGNO_CONTROFATTUALE_USCITE_2026-09-16.md)
§6 lasciava al futuro: «il controfattuale vero, quando sarà scritto, avrà bisogno della
propria riga in OBSERVATION_CHARTER.md».

Issue: #614. Pre-condizioni verificate: cancello di riproducibilità **superato**
(`docs/research/2026-09-22-replay-uscite-gate-614.md`, PR #645); raccomandazioni Q1–Q5
chiuse nel report di ricerca
(`docs/research/2026-09-16-letteratura-uscite-controfattuale.md`).

**Questo documento da solo non autorizza la misura**: resta bloccata finché
l'operatore non registra la propria riga in `docs/evidence/OBSERVATION_CHARTER.md`
(DoD 5 della issue). Il runner è **fail-closed** su questo: rifiuta di eseguire i rami
se la riga non c'è.

## 1. Domanda

> Il ribilanciatore (`portfolio_sell`) sta chiudendo troppo presto?

Operazionalmente: se ogni uscita `portfolio_sell` della finestra fosse stata ritardata
di N sedute — con il vincolo di budget rispettato, cioè senza il cash che quella vendita
avrebbe liberato — l'equity terminale del book sarebbe stata diversa, e quanto?

## 2. Campione e finestra

- Finestra: dalla prima seduta del freeze **2026-08-03** all'**ultima seduta completa**
  al momento dell'esecuzione, ancoraggio 2026-07-31. La finestra non si sceglie dopo
  aver visto i rami: è "tutto il freeze osservato finora", dichiarata nell'artefatto.
- Il cancello §4 del disegno viene **riverificato sulla stessa finestra nello stesso
  run**, prima dei rami. Se il cancello fallisce sulla finestra allargata, i rami non
  vengono né eseguiti né pubblicati: l'artefatto contiene solo il fallimento del cancello.
- Etichette dei motivi di uscita: dalla tabella `trades` del DB diagnostico, join per
  id ordine broker tramite `unnest(exit_order_ids)` (verificato il 2026-09-24: 127/127
  trade chiusi della finestra 2026-08-03..2026-09-22 hanno l'array popolato, 0 righe
  senza id). Un fill SELL senza etichetta non è un `portfolio_sell`: **resta reale**
  (fail-open sull'etichetta significherebbe ritardare vendite di altro motivo).

## 3. I rami

Ramo di controllo **C**: replay con la regola invariata — i fill reali, com'è e come
sta. È lo stesso replay del cancello.

Rami di trattamento **H_N**, N ∈ {1, 2, 5, 10, 21} (§3 del disegno: orizzonti
dichiarati allora, nessun altro):

1. Ogni fill SELL con etichetta `portfolio_sell` è **soppresso**.
2. La vendita ipotetica scatta alla **campana della seduta D+N** (dopo i fill reali
   di quella seduta), quantità `min(qty soppressa, qty allora detenuta)`; mai corto.
3. Se D+N cade oltre l'ultima seduta della finestra l'estensione è **censurata**: la
   posizione resta detenuta e viene marcata all'ultimo close. Il numero di censure è
   pubblicato per ramo: per N grande il ramo converge verso "tieni", e chi legge il
   numero deve saperlo.
4. I fill reali restanti sono riapplicati in ordine di timestamp con i vincoli di
   budget, che è dove il displacement (artefatto 2) entra per costruzione:
   - un **BUY** è applicato solo se il cash disponibile copre il costo entro una
     tolleranza di **1,00 $** (arrotondamenti del paper); oltre quella soglia è
     **saltato** e la sua assenza è registrata nell'artefatto (log del displacement);
   - un **SELL** reale è applicato per `min(qty del fill, qty detenuta)`; l'eccedenza
     è troncata e registrata. Un sell su posizione mai comprata nel ramo sparisce,
     com'è giusto che sia.
5. Nessuna lettura del futuro (§3 del disegno): la decisione dipende solo
   dall'etichetta del motivo d'uscita — nota a tempo di decisione — e dal calendario.
   I prezzi futuri entrano solo nella valutazione (mark e vendita ipotetica a D+N).

Il braccio **sS** (soglia asimmetrica compra/tieni, `Q1-NOVYMARX-VELIKOV`) è
**escluso da questa misura**. La ricerca lo indica come l'asse giusto, ma richiede la
mappa dei dati di ranking per simbolo-seduta (che il ranker ha usato quando ha
declassato X), che non è mai stata fatta; fare ora le scelte che quella mappa imporrebbe
significherebbe decidere dopo aver guardato. Se verrà fatto, avrà la propria
pre-registrazione, separata. Registrato qui perché la sua assenza non possa essere
dimenticata a posteriori: è la raccomandazione Q1-rec-5, rinviata, non respinta.

## 4. Costi (§3 del disegno: mai zero, su entrambi i rami)

- Fill **reali** (ramo C e fill reali dei rami H_N): prezzi realizzati, costi
  incorporati per costruzione.
- Fill **ipotetici** (le vendite ritardate): passano da `src/backtest/costs/`
  (`RealisticCostModel`: half-spread per tier, impatto sqrt, commissioni e fee
  regolatorie sulle vendite), prezzati sul close della seduta D+N, carry-forward se
  la barra manca (stessa convenzione del mark, dichiarata nel modulo del cancello).

## 5. Metriche e inferenza

- Metrica principale: **equity terminale money-weighted** (cash + posizioni marcate)
  di ogni ramo, e il delta H_N − C (Q2: la metrica ammessa per un pool a capitale
  fisso; il TWR non racconta questa domanda).
- Pubblicati per ogni ramo, come richiesto da Q2-rec-4: **capitale medio impiegato**
  (media di valore posizioni / equity) e **cash drag medio** (media di cash / equity).
  Senza questi due numeri l'equity terminale è ambigua.
- Statistica di inferenza: la serie delle differenze giornaliere
  `equity(H_N) − equity(C)` seduta per seduta. t = media / SE con **Newey-West,
  lag = N** (§3 del disegno), riusando `src/performance/ic.py` (regola #169/#467:
  non si riscrive).
- Barra: **|t| ≥ 3** (Q3, `Q3-HARVEY-LIU-ZHU`), con l'avvertenza Q3-rec-4: il t
  pubblicato è un limite superiore alla significatività, non una stima neutrale.
- **INSUFFICIENT_N** (Q3-rec-5): il campione utile è il numero di sedute della
  finestra, non il numero di trade. L'effetto minimo rilevabile è `3·SE_NW`,
  calcolato al run e pubblicato nell'artefatto. Se il delta osservato è sotto
  quella soglia l'esito è **non decidibile**, mai «nessun effetto». Con ~35 sedute
  ci si aspetta che quasi tutto sia non decidibile: dichiararlo è l'esito onesto,
  e il motivo per cui questa misura è strumentazione per la decisione dell'operatore,
  non un verdetto.

## 6. Predizioni falsificabili, fissate ORA

1. **P1 (da Q1-rec-2):** il delta H_N − C sarà dominato da costo di transazione e
   beta di mercato, non da alpha. Se un ramo vince, l'onere della prova è suo.
2. **P2 (da Q5-rec-3):** i rami N=10 e N=21 non testano «l'alpha vive più a lungo».
   Se vincono, il guadagno va attribuito a costo o beta finché non è dimostrato il
   contrario.
3. **P3 (da Q5-rec-5):** la magnitudine attesa dell'effetto è dell'ordine dei
   basipoint al giorno (~3,2 bps per σ di segnale). Un delta molto più grande di
   quest'ordine è più probabilmente un artefatto di disegno che alpha.

## 7. Cosa questo documento NON autorizza

- Nessuna modifica al path live: cadenza, stop, orizzonti restano congelati fino al
  2026-09-28 e oltre, finché l'operatore non decide.
- Nessun esecuzione dei rami prima della riga in `OBSERVATION_CHARTER.md`: il runner
  rifiuta (fail-closed) finché quella riga non esiste.
- Nessun ramo fuori dagli orizzonti pre-registrati, nessuna griglia aggiunta dopo
  aver visto i risultati. Eventuali follow-up = nuova pre-registrazione.
