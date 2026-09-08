# Pre-registrazione — residuo di copertura del calendario earnings (#507 step 5)

**Scritta il 2026-09-08**, prima che esista una sola seduta post-fix nel dossier: il fix #533 è
stato mergiato oggi (12:29 CEST) e il primo dossier con blocco `calendario_earnings` uscirà al
primo giro del cron successivo al merge. Nessun dato della finestra sotto misura è stato guardato,
perché non esiste ancora.

> **Scopo di questo documento.** Fissare campione, regola ed esito della misura prima di vedere il
> risultato, come chiede `OBSERVATION_CHARTER.md`. L'issue #507 step 5 dice: *«count, over a
> 20-session window, how many watchlist symbols with a known earnings reaction were flagged True.
> If FMP `stable/earnings-calendar` misses most of them, the source choice itself needs
> revising — this issue should not be closed on the wiring fix alone»*. Questo documento rende
> eseguibile quella frase. Vale la stessa disciplina della pre-registrazione S4: quello che è
> scritto qui vincola, quello che non è scritto qui non è un criterio.

**Perimetro freeze:** misura read-only, strumentazione. Nessuna soglia, peso, flag o parametro di
strategia. L'esito non entra in nessuna decisione di trading: decide soltanto se la #507 si può
chiudere sul wiring fix o resta aperta per la decisione sulla fonte (operatore).

---

## 1. Cosa si misura e perché adesso

Il wiring fix (#533) ripristina la discriminazione `True`/`False` di `giorno_di_earnings`, ma la
questione aperta è un'altra: **la fonte FMP vede, il giorno stesso, gli eventi earnings della
watchlist che contano?** Il difetto secondario dell'issue lo documenta già sul 2026-09-02: la
seduta in cui DELL +15,81%, PANW −9,28% e SNOW −4,37% si muovevano tutti su earnings, la query
FMP di quella seduta restituiva `[]`.

Diagnostica pre-finestra (2026-09-08, fuori campione, serve solo a motivare il protocollo — con
la chiave del `.env`, HTTP 200 su tutte le query):

| query FMP `stable/earnings-calendar` | righe | record watchlist |
|---|---:|---|
| `from=2026-09-01&to=2026-09-03` | 2 | NIO (09-01), DOCU (09-03) — **DELL, PANW, SNOW assenti** |
| `from=2026-09-02&to=2026-09-02` | 0 | — |
| `from=2026-09-04&to=2026-09-08` | 0 | — |
| `to=2026-09-03` (walk trailing del #S7) | 77 | record più recente **2026-08-26** (NVDA) |

Due fatti, entrambi rilevanti per il disegno:

1. **Non è un difetto della forma della query.** Il walk trailing che `scripts/backtest_s7_pead.py`
   documenta come accessibile nel free tier restituisce gli stessi buchi: i record DELL/PANW/SNOW
   di inizio settembre non esistono nel dataset FMP in *nessuna* forma, sette giorni dopo
   l'evento. Nessun fix di correttezza a `_corporate_calendar` può recuperare dati che la fonte
   non ha.
2. **Il dataset FMP ha un lag di ingestione visibile.** Il record più recente disponibile il
   09-08 è dell'08-26. Quindi il confronto «flag same-day contro dataset FMP letto il giorno
   stesso» non misura la copertura: misura il lag. La verità FMP va letta **retrospettivamente**.

## 2. Campione

- **Le prime 20 sedute con dossier post-#533** (attese dal 2026-09-08 in avanti), in ordine di
  data, con blocco `calendario_earnings` presente.
- Una seduta vale come **usabile** quando `calendario_earnings.status == "OBSERVED"`. Le sedute
  `UNKNOWN` restano fuori dal denominatore e sono conteggiate a parte: una seduta cieca non dice
  nulla sulla copertura della fonte.
- **Se più di 4 sedute su 20 sono UNKNOWN**, la misura non decide: il difetto *primario* (cecità)
  è ricomparso, l'allerta del cron deve essere scattata, e l'esito è `INSUFFICIENT_N` con motivo
  «cecità ricomparsa». Non si legge come copertura.
- **Se alla data del run esistono meno di 20 dossier post-#533**, la finestra non è completa:
  `INSUFFICIENT_N`, si aspetta. Nessuna scorciatoia che accorcia la finestra.
- Fine finestra attesa ≈ 2026-10-05 (20 sedute feriali da 09-08, salvo festivi), ma
  **comanda la serie dei dossier, non il calendario**.

## 3. Verità a confronto (ground truth)

Per «simbolo watchlist con earnings noto nella seduta» si fissano due fonti, con ruoli diversi:

### GT-1 — primaria, curata, indipendente da FMP

Le reazioni earnings documentate nei report alpha-miss della finestra
(`docs/ALPHA_MISS_REPORT_YYYY-MM-DD.md`) e nelle segnalazioni collegate: ogni simbolo watchlist
citato come mover per un rilascio earnings **proprio** (report o pre-annuncio) riferito alla
seduta o alla serata precedente (AMC). Regola di estrazione fissa: si compila a mano la tabella
`seduta, simbolo, citazione` al momento della misura, **dal testo dei report così come sono stati
committati giorno per giorno durante la finestra** — non si riscrive nulla a posteriori. Precedente
noto, già dentro l'issue: 2026-09-02 DELL/PANW/SNOW.

Questa è l'unica verità che può vedere un evento che FMP non ingerisce mai: per questo è primaria.

### GT-2 — secondaria, deterministica, dichiaratamente circolare

I record FMP `stable/earnings-calendar` (`from=…&to=…`, la stessa forma della produzione) per le
date della finestra, letti **al momento della misura, non same-day**: il run avviene ≥14 giorni
dopo la fine della finestra per tollerare il lag di ingestione osservato (§1). Circolare per
costruzione rispetto alla fonte sotto misura — un evento mai ingerito non compare né nel flag né
nella GT-2 — e per questo **non decide**, quantifica: la sua recall misura quanto il fetch
same-day della produzione vede di ciò che FMP stesso finisce per sapere.

## 4. Regola

- **Unità:** la coppia (simbolo, seduta) della ground truth dentro la finestra.
- **Esito dell'unità:** la produzione l'ha marcata `True`, cioè il simbolo è in
  `calendario_earnings.simboli_flaggati` del dossier della seduta (nei dossier privi del campo,
  fallback: `giorno_di_earnings == true` su un intento del simbolo — è comunque l'output
  persistito della produzione, con il confondo noto che conta solo i simboli con intenti).
- **Metrica primaria:** recall su GT-1 = (# unità GT-1 marcate True) / (# unità GT-1).
- **Numerosità minima GT-1: 5 unità.** Sotto, GT-1 non può dire «most» e l'esito è
  `INSUFFICIENT_N`. (Attesa: ~89 simboli watchlist × ~4 report/anno ≈ 1,4 earnings per seduta;
  la finestra attraversa l'avvio della stagione Q3, ma il criterio va fissato prima di vedere
  quanto ne arriva.)
- **Soglia di adeguatezza: recall GT-1 ≥ 50%.** È la traduzione letterale dell'issue («misses
  most of them»): sotto la metà degli eventi noti, la fonte è dichiarata **inadeguata** →
  `INADEGUATA` e la #507 **resta aperta** sulla decisione della fonte. A ≥ 50% la fonte resta e
  il residuo è quantificato ed esplicito → `ADEGUATA`. Il 50% non è una soglia di qualità: è il
  confine di «most»; qualunque valore diverso scelto dopo il run sarebbe post-hoc. Il testo
  dell'issue è la fonte della soglia, non una scelta nostra.

Esiti possibili, in ordine di precedenza: `INSUFFICIENT_N` → `INADEGUATA` → `ADEGUATA`.

## 5. Come e quando si gira

Una volta sola, non da cron:

    python scripts/measure_earnings_calendar_coverage.py

- Prerequisito: ≥14 giorni di calendario dopo la fine della finestra (run indicativo:
  ~2026-10-19), `FMP_API_KEY` nell'ambiente, tabella GT-1 compilata.
- Lo script legge i dossier persistiti (`docs/evidence/dossier/`) — **l'output della regola di
  produzione, non una sua reimplementazione** (#169): il flag True è quello che il dossier ha
  scritto il giorno stesso. Solo GT-2 interroga FMP, a run avvenuto.
- Scrive `docs/evidence/earnings_calendar_coverage_507.json`: finestra, conteggio sedute
  usabili/UNKNOWN, tabella per evento (fonte GT, flag, citazione), recall GT-1 e GT-2, esito,
  data del run.
- **Nessun ri-run dopo aver visto l'esito.** Se la fonte viene cambiata, o il criterio vuole
  cambiare, serve una nuova pre-registrazione con il motivo annotato qui sotto — non un secondo
  giro silenzioso.

## 6. Cosa NON conta come esito

Pre-registrato per non poterlo invocare dopo:

- Le verifiche spot del 2026-09-05 (corpo dell'issue) e la diagnostica del 2026-09-08 (§1):
  **fuori campione**. Motivano il protocollo, non lo decidono.
- La seduta 2026-08-26 (24 intenti NVDA `True`): l'unico caso noto in cui la fonte discriminava
  bene. Un caso non è una recall.
- Le sedute cieche 08-31 → 09-03: misurate dal fix #533, non da questa misura.
- Il backfill (step 4): deliberatamente saltato in #533 — con questa fonte convertirebbe UNKNOWN
  in `False` sbagliato sui simboli che contano. La decisione sulla fonte di questa
  pre-registrazione è il presupposto per qualunque backfill futuro, non il contrario.

## 7. Rischi dichiarati

- **GT-1 dipende da cosa i report notano.** Un earnings watchlist senza impatto sul prezzo può
  non essere mai citato: GT-1 è biased verso i mover, cioè esattamente i casi che l'issue chiama
  «i simboli che contano». Dichiarato, non mitigato: è la domanda giusta.
- **Lag di ingestione FMP non costante.** Se il lag supera i 14 giorni di tolleranza, GT-2
  sottoconta; GT-1 non ne dipende. Il lag osservato al run va riportato (data dell'ultimo record
  disponibile).
- **`simboli_flaggati` nasce con questa pre-registrazione**: nessun dossier schema 2.9 esisteva
  alla stesura, quindi nessuna serie pubblicata cambia significato — il campo è nella serie dal
  suo primo elemento.
- **Stagionalità**: la finestra attraversa l'avvio della stagione Q3; se arriva poca earnings
  news, `INSUFFICIENT_N` per numerosità è l'esito onesto, non un fallimento del protocollo.

## Registro delle modifiche a questo documento

| data | modifica | motivo |
|---|---|---|
| 2026-09-08 | versione iniziale | step 5 di #507 pre-registrato prima della prima seduta post-fix |