# Contratto PoC del secondo broker e kill criteria — Spec decisionale

**Data:** 2026-08-28
**Stato:** contratto firmato, in attesa di controfirma dell'operatore sui punti marcati `OPERATORE`
**Origine:** ricerca broker del 2026-08-25 (`docs/research/2026-08-25-broker-provider-alternatives.md`, #359)
**Controparte macchina:** `config/broker_poc_contract.yaml` + `src/brokers/poc_contract.py`
**Consumatori:** #364 (PoC Saxo), #361 (PoC IBKR) → #362 (capability boundary) → #360 (gate PO)
**Freeze #171 (03/08→28/09):** documentazione e strumentazione, nessuna taratura toccata, nessun
comportamento live modificato. La issue #363 è etichettata `freeze-ok`.
**Roadmap:** Part of #21.

---

## 1. Problema

Due PoC stanno per partire in parallelo su due broker con profili di rischio molto diversi:
Saxo OpenAPI (Europa, server-native, OAuth retail) e IBKR (globalità massima, Gateway con GUI,
autenticazione manuale settimanale). Il gate #360 dovrà scegliere uno dei due, o nessuno.

Il modo tipico in cui una scelta così va male non è che il PoC fallisca: è che i due PoC
provino cose diverse, e che al momento del confronto il criterio venga scritto — o riscritto —
sapendo già chi si vuole scegliere. Tre esempi concreti di come succede, tutti presenti nel
materiale del 2026-08-25:

1. **Il paniere si adatta al broker.** Saxo copre bene l'Europa, IBKR copre bene l'APAC. Se
   ciascun PoC prova i mercati che il suo broker fa meglio, il confronto misura la scelta del
   paniere e non il broker.
2. **Il requisito unattended diventa un kill o un dettaglio a seconda del preferito.** IBKR
   richiede per progetto la riautenticazione domenicale. Renderla bloccante scarta IBKR prima
   di provarlo; ignorarla regala a IBKR un costo operativo che Saxo non ha.
3. **Ciò che non si è provato passa come se fosse andato bene.** Il costo contrattuale
   italiano, l'entitlement dei dati, il comportamento del refresh token su una settimana:
   sono le evidenze più costose da raccogliere, e quindi le prime a mancare. Se un'evidenza
   mancante non pesa, il candidato che ne raccoglie meno risulta il migliore.

Questo documento congela il contratto prima del primo accesso ai provider, e la sua
controparte macchina rende il verdetto calcolabile invece che argomentabile.

## 2. Cosa questo documento decide, e cosa no

**Decide:** il paniere minimo di strumenti, la matrice comune di prova, lo scenario
obbligatorio `submit → timeout ambiguo → reconcile`, i criteri misurabili, i kill criteria
comuni e per broker, e la regola di confronto fra due candidati che passano solo parzialmente.

**Non decide:** quale broker adottare (è #360), quale forma dovrà avere l'adapter (è #362),
né autorizza apertura o finanziamento di conti, acquisto di market data, ordini live o
qualunque modifica al percorso Alpaca. Nessuna dimensione del contratto è verificabile in
`LIVE_ORDER`, e il caricatore del contratto rifiuta un file che ne introducesse una.

## 3. Tre livelli di verificabilità, dichiarati per riga

La issue chiede di distinguere i fatti verificabili in SIM/paper, quelli che richiedono
LIVE/approvazione del conto, e le decisioni dell'operatore. Nel contratto è un campo,
`verifiable_in`, e il valutatore lo applica: **un fatto dichiarato provato in un ambiente che
il contratto non ammette per quella dimensione vale come non provato.**

| Ambiente | Significato | Esempi nel contratto |
|---|---|---|
| `SIM` | Dimostrabile in paper/sandbox, ripetibile | timeout ambiguo, fill parziali, restart, stream |
| `LIVE_READONLY` | Serve un conto live approvato, ma solo letture | catalogo effettivo del conto, entitlement dati |
| `OPERATOR` | Decisione o documento dell'operatore | budget market data, preventivo italiano, accettazione dell'intervento settimanale |
| `DOC` | Documentazione contrattuale del provider, citata testualmente | clausola ToS sull'automazione, differenze SIM/live dichiarate |

Il motivo per cui questo campo è nel contratto e non nella prosa: il costo contrattuale
italiano e l'entitlement dei dati sono esattamente le evidenze che un PoC tecnico è tentato di
dichiarare «verificate» sulla base di una pagina di listino. Sono `OPERATOR`/`DOC`, e un
`PASS` raccolto in SIM su quelle righe viene declassato a non testato con una nota.

## 4. Il paniere minimo

Lo **stesso** paniere per entrambi i candidati: otto slot obbligatori più uno opzionale.
Asset class e valuta sono espliciti per ogni slot. Gli ISIN sono deliberatamente `null`:
scriverli a memoria introdurrebbe un errore silenzioso su un identificatore che poi finisce in
un ordine. Vanno risolti al primo accesso, registrati nel report e **confrontati fra i due
PoC**: se i due PoC risolvono ISIN diversi per lo stesso slot, hanno provato strumenti
diversi.

| Slot | Mercato (MIC) | Asset class | Valuta | Perché è nel paniere |
|---|---|---|---|---|
| `IT-EQ` | Euronext Milan (XMIL) | azione cash | EUR | Mercato domestico dell'operatore |
| `DE-EQ` | Xetra (XETR) | azione cash | EUR | Prima borsa europea per volume, listino e calendario distinti |
| `FR-EQ` | Euronext Paris (XPAR) | azione cash | EUR | Stesso gruppo di Milano, MIC e permission separati |
| `GB-EQ` | LSE (XLON) | azione cash | GBP, quotato in GBX | Trappola di unità minore: chi confonde penny e sterline sbaglia il notional di cento volte, in silenzio |
| `US-EQ` | Nasdaq (XNAS) | azione cash | USD | Controllo: unico slot già negoziabile su Alpaca |
| `JP-EQ` | Tokyo (XJPX) | azione cash | JPY | Il mercato APAC richiesto; lotto 100 e valuta senza decimali |
| `EU-ETF` | Xetra (XETR) | ETF UCITS | EUR | Asset class distinta e unico percorso KID/disclaimer UCITS |
| `NEG-CTRL` | fuori entitlement | — | — | Controllo negativo: l'esito atteso è un **rifiuto** fail-closed |
| `HK-EQ` *(opz.)* | Hong Kong (XHKG) | azione cash | HKD | Secondo APAC con board lot variabile per titolo |

Due slot meritano una nota, perché non sono lì per la copertura.

**`US-EQ` è il termine di confronto.** È l'unico strumento del paniere che Alembic già negozia.
Serve a distinguere una differenza di broker da una differenza di mercato, e a dare al gate
#360 un confronto di costo dove esiste un baseline.

**`NEG-CTRL` è un controllo negativo, e il suo esito atteso è un rifiuto.** Un broker che
accetta un ordine su uno strumento che il conto non è abilitato a negoziare, o che degrada in
silenzio su un altro listing, è più pericoloso di uno che copre meno mercati: è il
`false_positive_ticker` del multi-mercato, e CLAUDE.md § Ticker Resolution lo classifica come
l'errore peggiore possibile. Uno slot che «funziona» quando doveva rifiutare è un fallimento
di `D-MAP`, non un successo.

Il caricatore del contratto verifica che il paniere obbligatorio copra Italia, Xetra, Euronext,
LSE, USA e almeno un mercato APAC: togliere lo slot giapponese dopo la firma rompe il
caricamento invece di passare inosservato.

## 5. La matrice comune

Diciannove dimensioni, identiche per i due candidati. Ogni riga dichiara la domanda, la
procedura, criteri di superamento **misurabili** (non «funziona bene»), l'evidenza da
allegare, l'ambiente in cui è verificabile, se alimenta il gate finale, e i kill criteria che
può fare scattare. La forma completa è in `config/broker_poc_contract.yaml`; qui la
classificazione, che è la parte decisionale.

**Bloccanti (9).** Il fallimento è un `FAIL`, non un successo parziale.

| ID | Cosa chiede | Perché bloccante |
|---|---|---|
| `D-AMBIG` | `submit → timeout ambiguo → reconcile`, 5 prove, 0 duplicati, 0 ritrasmissioni cieche | Vedi §6 |
| `D-MAP` | Ogni slot risolto a identificatore unico e stabile a 24h, ordinabile sul conto | Uno strumento sbagliato è l'errore peggiore possibile |
| `D-AUDIT` | Un revisore diverso ricostruisce quantità, prezzo medio e commissioni dal solo journal | Un P&L non spiegabile non è misurabile, e il gate si baserebbe su numeri non verificabili |
| `D-RECOVERY` | Stato completo ricostruibile dall'API dopo perdita di eventi | Senza ricostruzione il divieto di ritrasmissione cieca non è applicabile |
| `D-RESTART` | 0 ordini orfani e 0 ri-emessi dopo restart, incluso con un ordine in volo | Stessa classe di #121: un ordine non riconosciuto come proprio diventa capitale non sorvegliato |
| `D-PARTIAL` | Cumulativi e prezzo medio riconciliano, nessun doppio conteggio | Un fill parziale mal contato sposta la posizione senza che nulla lo segnali |
| `D-AUTH` | 7 giorni consecutivi misurati, revoca e recovery, esaurimento **fail-closed**, 0 perdite di sessione non rilevate | Vedi §7 |
| `D-SESSION` | Una sessione concorrente viene rilevata entro un ciclo; 0 ordini su sessione non confermata | Un username IBKR ha una sola brokerage session: la contesa è di progetto, non un incidente |
| `D-TOS` | La clausola che permette l'uso automatico personale, citata testualmente | È il criterio che ha escluso Trading 212 in #359: va verificato anche sui preferiti |

**Pesate (10).** Il fallimento è un rischio residuo che il gate #360 deve accettare
esplicitamente: `D-PAPER` (fedeltà SIM/live), `D-DATA` (entitlement market data), `D-PREVIEW`
(what-if o il controllo deterministico che lo sostituisce), `D-REPLACE` (cancel/replace in gara
con un fill), `D-PROTECT` (stop e take-profit lato broker, per slot), `D-STREAM` (reconnect
senza buchi silenziosi), `D-UNATTENDED` (interventi umani contati), `D-COST` (mese
rappresentativo sul contratto italiano vero), `D-RATE` (limiti dichiarati contro osservati),
`D-SUPPORT` (la configurazione provata è quella supportata).

## 6. Lo scenario obbligatorio: `submit → timeout ambiguo → reconcile`

È la dimensione per cui esiste il resto del contratto, e l'unica su cui non esiste
`CONDITIONAL`.

**Procedura**, identica per i due candidati: cinque prove, ciascuna con submit portato a termine
sotto una chiave d'esecuzione deterministica, poi interruzione della risposta lato client —
timeout forzato, socket chiuso, processo terminato in volo. Nessuna ritrasmissione è ammessa
prima di una query di stato per order reference. Almeno una prova deve includere il restart del
processo fra il submit e la riconciliazione.

**Criteri:** `duplicate_orders: 0`, `blind_resends: 0`, esiti ignoti risolti da query: 100%.
Anche **una sola** occorrenza di duplicato su cinque prove fa scattare `K-DUP`, e un duplicato
non ammette gradazione: è capitale mosso due volte su una decisione presa una volta.

**Cosa cambia fra i due broker** — la procedura è comune, i meccanismi da esercitare non lo
sono, e il report deve dire quale ha usato:

- **Saxo:** un timeout `TradeNotCompleted` significa che l'ordine *potrebbe* essere stato
  piazzato; `x-request-id` distingue le richieste, e operazioni identiche entro 15 secondi
  vengono rifiutate. Va provato che il rifiuto per identità non venga confuso con un errore
  che invita al retry.
- **IBKR:** la ricostruzione passa da order reference, ordini aperti ed esecuzioni. Va provato
  che un ordine emesso prima del restart venga riconosciuto come proprio e non ri-emesso.

Il journal dell'intero scenario è l'evidenza: request, timeout, query di riconciliazione, stato
finale e lista ordini lato broker. Senza journal la prova non conta, per `D-AUDIT`.

## 7. Unattended: pesata, e la ragione va detta

`D-UNATTENDED` è **deliberatamente pesata e non bloccante**, e questa è la decisione più
contestabile del documento.

IBKR richiede per progetto un'autenticazione manuale settimanale: TWS e Gateway sono
applicazioni con GUI, il funzionamento headless non è ufficialmente supportato, e ogni domenica
i token vengono invalidati. L'operatore ha già accettato questo costo (assessment del
2026-08-24). Rendere «zero intervento umano» un criterio bloccante scarterebbe IBKR **prima di
provarlo**, sulla base di un fatto già noto e già accettato: sarebbe esattamente l'adattamento
del contratto al candidato preferito che questo documento esiste per impedire — con il segno
invertito.

Ciò che resta bloccante non è l'assenza di intervento, ma la sicurezza della sessione:

- `D-AUTH` esige che l'esaurimento della sessione sia **fail-closed** e che nessuna perdita di
  sessione passi non rilevata;
- `KI-REAUTH` scatta se la finestra di riautenticazione non ha runbook con tempo umano
  delimitato, non è allertata, oppure se **durante** quella finestra una posizione resta senza
  sorveglianza né protezione broker-side;
- `D-UNATTENDED` chiede di contare gli interventi, misurarne la durata, e provare cosa succede
  quando uno viene mancato.

Il costo dell'intervento settimanale entra quindi nel gate come costo dichiarato e misurato,
non come squalifica e non come dettaglio nascosto.

## 8. Kill criteria

Un kill scattato è un `FAIL`, e nessun'altra evidenza lo compensa. Sei sono comuni; i restanti
nove sono per costruzione specifici, perché i due broker hanno rischi diversi. Un kill di un
broker registrato sul report dell'altro è un errore di compilazione, non un dato, e il
valutatore lo rifiuta.

**Comuni:** `K-DUP` (un ordine duplicato nello scenario di timeout ambiguo) · `K-RECON` (stato
non ricostruibile dopo perdita eventi o restart) · `K-MAP` (uno slot obbligatorio non
risolvibile in modo univoco e stabile, incluso il caso raggiungibile solo con una
disambiguazione non deterministica) · `K-AUDIT` (l'audit trail non basta a spiegare una
posizione o un fill) · `K-FAILOPEN` (un fail-open su auth, entitlement, dati stanchi, warning o
disclaimer) · `K-TOS` (l'uso automatico personale previsto non è permesso per iscritto).

**Saxo:** `KS-AUTH` — la catena OAuth/refresh non sopravvive 7 giorni più un downtime forzato,
oppure credenziali LIVE personali non ottenibili da un residente italiano (il certificate-based
login è riservato a Introducing Broker e White Label, quindi la via retail è l'unica in
perimetro) · `KS-DISCL` — un pre-trade disclaimer può bloccare il submit **senza segnale
rilevabile**; un disclaimer da accettare è un costo, uno che ferma l'automazione in silenzio no
· `KS-CAT` — gli strumenti obbligatori non sono nel catalogo **del conto**, che dipende dalle
abilitazioni e non dal listino pubblicato · `KS-COST` — il costo italiano contrattuale non è
ottenibile prima del gate: un costo ignoto non è un costo basso.

**IBKR:** `KI-REAUTH` (§7) · `KI-SESSION` — una sessione concorrente sottrae la connessione
senza segnale rilevabile · `KI-CONTRACT` — la contract qualification resta ambigua su uno slot
obbligatorio: più `conid` per lo stesso strumento senza regola deterministica di scelta è
ambiguità, non copertura · `KI-ENTITLE` — l'entitlement market data per i mercati del paniere
non è ottenibile nel budget **dichiarato dall'operatore**; il budget non è fissato qui, ed è
una decisione `OPERATOR` al gate · `KI-HEADLESS` — il PoC passa solo attraverso una
configurazione headless non supportata **presentata come supportata**: sperimentare un
controller di terze parti è legittimo, descriverlo come supportato non lo è, e se il `PASS`
dipende da quel percorso l'esito massimo è `CONDITIONAL` con il rischio nominato.

## 9. La regola per un candidato che passa solo parzialmente

Il verdetto per candidato ha tre esiti:

- **`FAIL`** — un kill scattato, oppure una dimensione bloccante fallita **o non testata**.
- **`CONDITIONAL_PASS`** — tutto il bloccante superato, almeno una pesata fallita o non
  testata. Il gate deve accettare i rischi residui uno per uno; sono elencati nel verdetto.
- **`PASS`** — tutto superato negli ambienti ammessi.

Tre regole rendono il verdetto non negoziabile a posteriori.

**«Non l'abbiamo provato» non è un successo.** Su una dimensione bloccante, `NOT_TESTED` è
indistinguibile da `FAIL`. Su una pesata è un rischio residuo. Omettere una dimensione dal
report non la fa sparire: viene contata come non testata con la nota `absent_from_report`.
È il criterio di accettazione di #360 — «tratta i gap non testati come rischio, non come
successo» — reso eseguibile.

**Il confronto fra due `CONDITIONAL_PASS` è lessicografico, non un punteggio.** Un punteggio
scalare unico è il modo più elegante di adattare il verdetto: bastano i pesi, scelti dopo aver
visto i risultati. L'ordine è congelato qui e letto dal contratto, non dal codice:

1. `graded_failed_count` (min) — la differenza più diretta fra due candidati che hanno superato
   tutto il bloccante;
2. `graded_not_tested_count` (min) — dopo un fallimento misurato, perché è meno informativo;
3. `mandatory_slots_resolved_count` (max) — copertura effettiva, verificata sul conto;
4. `unattended_days_measured` (max) — giorni misurati, non promessi: premia la misura;
5. `monthly_cost_usd` (min) — ultimo, e solo se calcolato sul contratto italiano vero: è la
   variabile più facile da rinegoziare e la meno legata alla sicurezza.

Una metrica di tie-break non misurata vale il **peggio possibile**: non misurare non può essere
un vantaggio.

**Un pareggio pieno non produce un vincitore.** Se i candidati sono pari su tutti e cinque i
tie-breaker, l'esito è `NO_DECISION` e la scelta torna all'operatore. Il valutatore non inventa
un preferito.

Se nessuno dei due è ammissibile, la raccomandazione è `ALPACA_ONLY`. Il valutatore **non**
produce mai `NEW CONTINGENCY MAP`: promuovere una contingenza è una decisione dell'operatore
(#360 — «queste alternative non sono automaticamente promosse da questo gate»), e il contratto
si limita a dichiararne i trigger.

## 10. Contingenze nominate, nessun PoC autorizzato

Tutte con `poc_authorized: false`; il caricatore rifiuta un file che ne autorizzasse una, così
che la promozione resti un atto esplicito del gate e non una riga cambiata in silenzio.

| Candidato | Perimetro | Trigger |
|---|---|---|
| Tradier | equities/ETF e opzioni USA | Entrambi i globali `FAIL` e serve un failover USA, o validare il seam a rischio minimo |
| tastytrade | derivati USA | Opzioni o futures diventano priorità prima dell'espansione geografica |
| TradeStation Europe | USA, API e SIM di qualità | Serve un secondo broker USA ricco di derivati e Tradier non basta |
| Directa | Italia più una selezione UE/USA | Entrambi i globali `FAIL` e l'obiettivo si restringe all'Italia; richiede abilitazione, non esiste conto API di prova |
| Schwab | prevalentemente USA | Solo con una sandbox Trader API verificabile e l'eleggibilità italiana confermata |

**Escluse:** Trading 212 (i termini API §4.2 vietano l'Algorithmic Trading e gli endpoint
ordine non sono idempotenti; riapribile solo con consenso scritto specifico o termini cambiati)
e Swissquote (REST e FIX titoli riservate a utenti professionali).

## 11. Quali evidenze alimentano il gate finale

Tutte e diciannove le dimensioni hanno `feeds_final_gate: true`, e il valutatore espone
l'elenco. Non è un modo di dire «tutto conta»: significa che al gate #360 nessuna riga della
matrice può essere presentata come irrilevante dopo che il suo esito è noto. Ciò che distingue
le righe è il **peso**, e quello è già fissato dalla classificazione bloccante/pesata di §5.

Il gate riceve, per ciascun candidato: il verdetto, l'elenco delle bloccanti fallite, delle
pesate fallite, delle non testate, dei kill scattati, i rischi residui da accettare uno per
uno, le note sui declassamenti di ambiente, e le cinque metriche di tie-break. Più il
raffronto lessicografico, con la motivazione riga per riga.

Due input del gate **non** vengono da questo contratto e vanno ricordati a #360: il costo di
migrazione reale dei 34 file che importano Alpaca direttamente (`src/brokers/base.py` espone
sei operazioni e non rappresenta il contratto operativo), che è materia di #362; e il budget
market data, che è una decisione `OPERATOR`.

## 12. Come si verifica che il contratto tiene

```
python3 -m pytest tests/brokers/test_poc_contract.py -q
```

Attesi 29 test verdi. Non provano che i PoC andranno bene — non ci sono ancora dati: provano
che il contratto rifiuta i modi tipici di aggiustare un verdetto. I test sono scritti come
tentativi di aggiustamento: un report con un hash di contratto diverso, una dimensione omessa,
un fatto `OPERATOR` dichiarato provato in SIM, un paniere incompleto con il mapping dichiarato
`PASS`, una metrica di tie-break non misurata, un pareggio pieno.

## 13. Fuori scope

- **La forma dell'adapter** — è #362, e per progetto deve nascere da evidenza reale dei PoC.
- **Il verdetto** — è #360.
- **Apertura/finanziamento conti, acquisto dati, ordini live, routing Alembic** — vincoli delle
  issue, non superabili da questo documento.
- **La taratura** — il freeze #171 vale fino al 2026-09-28. Questo documento non tocca soglie,
  pesi, flag, cooldown o parametri di strategia, e non modifica alcun comportamento live: è un
  file di configurazione nuovo, un modulo puro non cablato e documentazione.
- **Il budget market data e la controfirma dei punti `OPERATOR`** — non sono decisioni
  dell'agente.

## 14. Rischi di questo contratto

- **Il paniere può rivelarsi troppo ampio per un PoC.** Otto slot obbligatori su sei mercati
  sono un impegno reale. La mitigazione non è ridurlo dopo aver visto la difficoltà: è
  registrare gli slot non risolti come `D-MAP` fallita, che è un `FAIL` — e se il paniere è
  davvero sbagliato, è una modifica **materiale** al contratto, con version bump e changelog,
  non una potatura silenziosa.
- **Il contratto può essere completo e i PoC comunque incomparabili**, se un candidato prova in
  SIM ciò che l'altro deferisce a `OPERATOR`. È il primo tie-breaker a coprirlo solo
  parzialmente; il resto lo copre il declassamento di ambiente, che rende visibile il deferimento
  invece di lasciarlo passare per un pass.
- **`KI-ENTITLE` dipende da un budget non ancora dichiarato.** Finché l'operatore non lo fissa,
  quel kill non è valutabile e la dimensione `D-DATA` resterà `NOT_TESTED` — cioè un rischio
  residuo, che è l'esito corretto e non un buco.

## 15. Riferimenti

- Ricerca: `docs/research/2026-08-25-broker-provider-alternatives.md` (#359)
- Contratto in forma macchina: `config/broker_poc_contract.yaml`
- Valutatore: `src/brokers/poc_contract.py` · test: `tests/brokers/test_poc_contract.py`
- PoC: #364 (Saxo), #361 (IBKR) · Capability boundary: #362 · Gate: #360
- Freeze: `docs/evidence/OBSERVATION_CHARTER.md`
- Confine LLM: CLAUDE.md § Ticker Resolution, § Hallucination Mitigation
