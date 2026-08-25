# Carta di osservazione — periodo di sola osservazione

Scritta il 2026-08-01, **prima** che l'osservazione cominci. Scopo unico: togliere a noi stessi la
possibilità di razionalizzare a posteriori.

Design di riferimento: `docs/superpowers/specs/2026-08-01-osservazione-evidenze-roadmap-pesata-design.md`

## Durata

- **Inizio:** lunedì 2026-08-03
- **Minimo:** 40 giorni di borsa
- **Scadenza attesa:** 2026-09-28 (contando il Labor Day del 2026-09-07). Da confermare con la
  `GetCalendarRequest` di Alpaca che `scripts/daily_alpha_miss_analysis.sh` già usa.
- **Controllo di metà periodo:** ~2026-08-28 (giorno 20). Non decide nulla: verifica solo che il
  ledger sia vivo.

Motivo dei 40 giorni: sotto quella soglia la finestra non contiene abbastanza giornate ad alta
dispersione per distinguere un difetto ricorrente da una coincidenza. Riscontro empirico: la
finestra 17-31 luglio 2026, 10 giorni di borsa, ha prodotto ±$100 su $110K — rumore.

## Cosa è congelato

Tutta la **taratura**: soglie, pesi, flag, cooldown, parametri di strategia.

## Cosa è esente

Solo i **difetti di correttezza**, con questo test da applicare a ogni candidato:

> Se non lo correggo, l'evidenza che raccolgo nelle prossime settimane è sbagliata?

Esempio che passa il test: il gate S4 disarmato (#163, corretto il 2026-07-30) — con il gate spento
il sistema comprava a soglie diverse da quelle di design, quindi ogni giorno osservato sarebbe stato
inutilizzabile. Esempio che non lo passa: un cooldown da tarare.

## Registro delle deroghe

Ogni eccezione applicata va annotata qui con data, motivo e commit.

| data | deroga | motivo | commit |
|---|---|---|---|
| 2026-08-01 | Script deterministico di precalcolo per il report alpha-miner (`scripts/alpha_miner_dossier.py`, fase 2) | Senza precalcolo i numeri della roadmap pesata sono ri-derivati ogni mattina da un LLM diverso, e la sessione rischia il timeout silenzioso che farebbe fallire l'osservazione stessa. È strumentazione, non un difetto di correttezza: quindi deroga. | nessuno: deroga registrata in anticipo, fase 2 non ancora rilasciata |
| 2026-08-04 | Conversione di `costo_usd` da `0.0` a `null` sulle 7 occorrenze già scritte, più il campo `occorrenze_non_stimate` | Il prompt dei cron non chiedeva di stimare il costo, quindi le sessioni scrivevano `0.0`. Ma le soglie di questa carta sono in dollari: con tutte le occorrenze a zero **nessuna evidenza avrebbe mai attraversato una soglia**, e la roadmap pesata del 28/09 sarebbe uscita vuota per un difetto dello strumento, non per assenza di evidenza. Passa il test di esenzione: se non lo correggo, l'evidenza raccolta è sbagliata. Unica modifica retroattiva ammessa su `findings.json`. | commit del 2026-08-04 |
| 2026-08-01 | Riscrittura retroattiva di `market_daily.jsonl` all'innesto della fase 2 | Le righe scritte prima dell'innesto sono calcolate dalla sessione, quelle successive dallo script: lo script le ricalcola tutte perché la serie abbia una sola provenienza. Unica eccezione ammessa al "solo append"; **non si applica mai a `findings.json`**. | nessuno: deroga registrata in anticipo, fase 2 non ancora rilasciata |
| 2026-08-06 | Il path live rispetta `rebalance_frequency` (#185) | S1 dichiara `MONTHLY`, il backtest la rispetta, il live ribilancia **ogni 15 minuti**. La domanda di uscita n.2 chiede se S1 abbia un edge: senza la correzione, i 40 giorni misurerebbero un oggetto diverso da quello della domanda, e dai dati stessi non ci sarebbe modo di accorgersene. Stesso profilo del gate S4 disarmato (#163). **Perimetro:** solo l'allineamento alla frequenza già dichiarata; `signal_threshold` e qualunque banda morta parametrica restano congelati. | vedi #185 |
| 2026-08-06 | Alert sulle posizioni non proteggibili (#161) | Le 13 posizioni sotto 1 azione non possono avere stop e contengono tutto il rosso del libro (−$452 contro +$660). La condizione di revisione scritta in `config/trading.yaml:180-182` si è verificata su quattro di esse e nessuno se n'è accorto perché niente la sorvegliava. È **strumentazione**: non cambia cosa compriamo né con che size, quindi non è propriamente una deroga — registrata qui per tracciabilità. La correzione strutturale (size minima ≥ 1 azione) è **taratura** e resta al 28/09. | vedi #161 |

| 2026-08-07 | Il ratchet non alza il gate d'ingresso di S4 sopra il baseline 0,30 (#191) | La leva era salita da sola a **0,45** scartando il 93-97% dei segnali. Il freeze aveva congelato la taratura *manuale*, non questa leva *automatica*. Senza la deroga, la domanda di uscita n.1 si auto-risponde: con S4 che quasi non tratta, il suo P&L economico resta dentro ±$200 **per costruzione**, e al 28/09 concluderemmo «la news non ha alpha» quando la causa è il gate. Lo strumento risolverebbe la domanda al posto del fenomeno. **Perimetro:** solo il tetto della leva; `threshold_step`, il trigger, il decay e il ramo `regime_scale` restano intatti. | vedi #191 |
| 2026-08-14 | **#236 deployato**: il filtro QS-07 non riscarta più i segnali che FIX-D ha ri-ammesso | Dentro la deroga d'ambito concessa il 2026-08-13. È un difetto di correttezza e passa il test di esenzione: FIX-D decide di tenere aperta una posizione perché la scadenza di un segnale non è un contro-segnale, e un filtro a valle annullava quella decisione sull'orologio — 30 uscite a peso-zero in 40 giorni, fra cui IBM (−26,47 $ realizzati, +13,71 $ lasciati sul tavolo). Finché S4 esegue, ogni giorno di attesa ne produce altre, quindi il deploy è anticipato rispetto al batch unico. **Perimetro:** solo l'esenzione per provenienza; il filtro d'età resta intatto per i segnali non marcati (backtest) e il ramo `below_entry_gate` (#170) non è toccato. | vedi #236 |
| 2026-08-07 | Stopgap manuale sulla chiave Redis `feedback:entry_threshold:S4`, da 0,45 a 0,30 | La correzione di codice di #191 richiede rebuild e redeploy (`config/trading.yaml` è baked, non montato). Ogni giorno di attesa è un giorno di finestra speso al 5% dei segnali. **Temporaneo:** al prossimo trigger il ratchet la rialza finché #191 non è deployata. | nessuno: intervento su Redis, non sul repo |

Il **ritiro di F8** deciso lo stesso giorno (#134) non compare qui: `apply_regime_scale: false`
significa che la leva era già spenta, quindi è rimozione di codice inerte e non tocca il
comportamento osservato.

### Discontinuità nella serie osservata

Due deroghe introducono una discontinuità, e vanno trattate separatamente alla sintesi del giorno 40
invece che mediate sull'intera finestra:

- **#185** — le evidenze su S1 raccolte dal 2026-08-03 alla data del deploy non sono confrontabili
  con quelle successive.
- **#236 (2026-08-14)** — da questo deploy in avanti S4 non chiude più una posizione perché il
  suo segnale è invecchiato mentre FIX-D lo teneva in vita. Il mix delle uscite cambia per
  costruzione: le righe `expired`/`unknown` a peso-zero devono calare, e la tenuta mediana salire.
  Confrontare la durata delle posizioni o il conteggio delle uscite attraverso questa data misura
  il deploy, non la strategia. Il P&L realizzato di S4 prima e dopo non è sommabile.
- **#191** — le evidenze su S4 dal 2026-08-03 al 2026-08-07 provengono da un gate salito fino a 0,45,
  cioè da una strategia che scartava ~19 segnali su 20. Il conteggio dei giorni di ricorrenza su
  F-009 (*il gate scarta segnali col segno corretto*) è il più esposto: quelle occorrenze sono state
  generate da una soglia che non era quella di design.

- **#293 / trial exit S4 (deroga registrata in anticipo, 2026-08-22)** — **data** = `n=0` del trial
  exit, non ancora fissata: coincide col batch atomico che apre la raccolta (§ Sequenza punto 3 della
  decisione del 2026-08-14 su #242). **Perimetro** = solo il ramo shadow: P0/P1 (e P2, se ammessa)
  sono valutate su lifecycle virtuali costruiti sugli stessi intenti, fill e costi del runtime.
  **Il comportamento live non cambia, quindi la serie osservata non si spezza**: le evidenze S4
  raccolte prima e dopo `n=0` restano confrontabili e sommabili, a differenza di #185, #236 e #191.
  Registrata qui in anticipo, col pattern delle voci del 2026-08-01, perché al giorno 40 la presenza
  di un trial in corso non venga scambiata per una discontinuità che non c'è. Se il trial dovesse
  mai toccare il ramo live, quella sarebbe una modifica materiale ai sensi del
  `CONTRATTO_TRIAL_EXIT_S4_2026-08-22.md` § Modifiche materiali, imporrebbe restart del campione e
  **andrebbe annotata qui come discontinuità vera**.

- **#315 / significato di `score` su `SKIP_PYRAMIDING` (2026-08-19)** — **perimetro** = la sola
  colonna `score` sulle righe `decision='SKIP_PYRAMIDING'` di `execution_decisions`; nessun'altra
  decisione, nessun'altra colonna. Prima del 19/08 `score` porta il peso target dello slot dopo
  scalatura sleeve/regime (osservato 0,020–0,031); dal 19/08 porta `quantity*price/nav`, la frazione
  di NAV davvero non impiegata (osservato 0,0024–0,0170). **Non sommabili.** Il calo di livello è il
  cambio di definizione, non un calo del fenomeno: chi confronta le due metà della serie sta
  misurando la ridefinizione, non il pyramiding scartato. Vale anche l'inverso: prima del 19/08
  `counterfactual_return_1h` è NULL su `SKIP_PYRAMIDING` **per costruzione** (la decisione era
  esclusa dal filtro della query che alimenta il controfattuale), non per dato mancante — quei NULL
  non vanno letti come fallimenti di calcolo né imputati.
  **Il comportamento live non cambia, quindi la serie osservata non si spezza**: come per #293, e a
  differenza di #185, #236 e #191, ciò che si spezza è la serie della *misura*, non quella del
  fenomeno. Le decisioni di pyramiding prese prima e dopo il 19/08 restano confrontabili fra loro.

Questa sezione esiste perché fra sette settimane nessuno se ne ricorderebbe.

## Soglie: cosa guadagna diritto a lavoro alla scadenza

| confidenza | definizione | soglia |
|---|---|---|
| **misurata** | perdita reale tracciabile a righe di DB | ≥ $100 cumulativi, ricorrenza irrilevante |
| **attribuita** | il trade esiste, il controfattuale è corto | ≥ $250 cumulativi **e** ≥ 5 giorni distinti |
| **congetturale** | alpha mancato, nessun trade avvenuto | ≥ $1.000 cumulativi **e** ≥ 10 giorni distinti |

**Findings senza costo stimabile.** Un'osservazione strutturale (per esempio «la copertura news è
bassa») tipicamente non ha un costo giornaliero quantificabile, e la sua occorrenza porta
`costo_usd: null`. Evidenze così non attraverserebbero mai una soglia in dollari, ma non per questo
sono irrilevanti: **un finding con `occorrenze_non_stimate` ≥ 15 giorni distinti entra comunque in
roadmap**, valutato per ricorrenza invece che per costo. Va discusso, non pesato.

Distinzione che regge tutto l'impianto: `costo_usd: null` significa «non stimato», `0.0` significa
«è costato zero». Confonderli rende impossibile distinguere un difetto innocuo da uno mai
quantificato.

L'asimmetria è voluta: un controfattuale deve valere dieci volte un bug misurato per pesare uguale.
Sugli alpha mancati non sappiamo se saremmo entrati, con che size, né quando saremmo usciti. Il
report del 2026-07-30 lo dimostra: MSFT catturato su un giorno a +15,5% ha prodotto $13,03
realizzati, perché l'uscita è scattata 2h45 dopo l'ingresso.

## Definizione: P&L economico

Termine usato nei criteri di uscita, da non confondere con il P&L realizzato. Per ogni posizione, il
movimento di prezzo attribuibile alla finestra: si marca dal close del primo giorno della finestra
(o dal prezzo di ingresso, se successivo) al prezzo corrente (o al prezzo di uscita, se anteriore),
moltiplicato per la quantità. Somma su tutte le posizioni, aperte e chiuse.

Serve perché il P&L realizzato di S1 è strutturalmente distorto: la sua regola d'uscita chiude solo
le posizioni che hanno perso rango momentum, cioè quelle scese, mentre le vincenti restano aperte
(#134). Sulla finestra 17-31 luglio la differenza era −$564 realizzati contro −$2,81 economici.

## Domande di uscita, pre-registrate

**1. Esiste alpha nella news editoriale su questa watchlist?**

Falsificazione: se alla scadenza `NO_NEWS` resta la causa di miss dominante in **≥60% dei giorni**
**e** il P&L economico di S4 sulla finestra resta dentro **±$200**, la risposta è no.

Conseguenza pre-registrata: S4 cambia fonte dati (vettori strutturati Tier A in
`docs/RESEARCH_SYNTHESIS_ALPHA_AND_TOOLING_2026-07-26.md`) oppure esce. Nessuna ulteriore taratura.
Precedente: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`.

**1-bis. Condizione pre-registrata sul momento del movimento (#246).**

Se al 28/09 la mediana per seduta di `quota_movimento_precedente_al_segnale` resta ≥ 70% su ≥ 15
sedute a denominatore non degenere, e il trial d'uscita (#301) non produce PROMOTE su P1, la
conseguenza pre-registrata è il cambio di fonte verso vettori event-driven — non un'altra taratura
di S4 (soglia #170, orizzonte #242, copertura #159).

Dove si legge: `ingressi[].quota_movimento_precedente_al_segnale` e
`ingressi[].denominatore_degenere` nei dossier `docs/evidence/dossier/*.json`. Il denominatore è la
gamba intraday (close − open); è dichiarato degenere sotto lo 0,5% del prezzo di apertura
(`SOGLIA_DENOMINATORE_DEGENERE` in `src/analysis/dossier/book.py`), e le sedute degeneri non
contano verso le 15. `quota_nel_gap` è una misura **diversa**, con un altro denominatore: non entra
in questo criterio e non va mediata con la prima.

**2. S1 ha un edge una volta corretta la misura?**

Criterio: P&L **economico** di S1 sulla finestra confrontato con SPY, con la serie **realizzata
esplicitamente ignorata**.

**Esito legittimo previsto:** se alla scadenza nessun criterio è soddisfatto, la conclusione corretta
è **estendere la finestra**, non agire comunque.

## Stop di rischio, pre-registrato

Registrato il **2026-08-25** (#329), al giorno 15 di 40. Tutti i criteri sopra sono **epistemici** —
*c'è alpha?* Questo è l'unico **di rischio**: *quanto siamo disposti a perdere per scoprirlo?*

> **Se il P&L economico cumulato della sleeve S4 sulla finestra tocca −$1.000, S4 passa a shadow
> immediatamente.** Continua a produrre segnali e a misurarsi, smette di eseguire. Nessuna
> discussione, nessuna deroga, nessuna taratura come alternativa.

Dove si legge: `pnl_economico.cumulato.S4` in `docs/evidence/economic_pnl.json` — la stessa grandezza
e la stessa fonte della domanda 1. **Non** sul realizzato, che per S1 è strutturalmente distorto e
per S4 non è sommabile attraverso il deploy #236.

Taratura del livello, dichiarata ora e non a posteriori: ≈0,9% del NAV (~$110k) e ≈9% del capitale
della sleeve (~$11k). Alla registrazione S4 vale **−$505,34** (2026-08-24, giorno 15/40), quindi lo
stop dista ≈$495, cioè ≈2,0× la perdita in essere. Il livello è scelto in valore assoluto sul
capitale a rischio, **non** come multiplo della perdita corrente: se fosse un multiplo si
sposterebbe insieme alla perdita, che è il modo esatto in cui uno stop smette di essere uno stop.

**Lo stop è di rischio, non di merito.** Se scatta non dice che la news editoriale non ha alpha —
dice che non lo scopriremo con questi soldi. La domanda 1 resta in quel caso **aperta e senza
risposta**, e va registrata come tale alla sintesi del giorno 40: un'uscita per stop di rischio non
è una falsificazione, e il campione troncato non va confuso con un campione completo.

### Nota sulla banda ±$200

La banda della domanda 1 **non è uno stop di perdita** e non va letta come tale: misura «S4 ha mosso
l'ago?», e la falsificazione richiede di stare **dentro** la banda *insieme* a `NO_NEWS ≥60%`.
Uscire dalla banda è la gamba che *non* si avvera. Al 2026-08-24 entrambe le gambe falliscono
(S4 −$505,34, fuori banda; `no_news_dominant` 5/15 = 33%): sul criterio scritto S4 non è
falsificata. Confondere le due cose — leggere il breach come un kill trigger — è l'errore che questa
sezione esiste per impedire, ed è l'errore da cui è nata #329.

## Stato

| data | evento |
|---|---|
| 2026-08-01 | Carta scritta e committata. Ledger inizializzati. Protocollo attivo su entrambi i cron. Promemoria OSS_MIDPOINT e OSS_SCADENZA programmati. Prova end-to-end eseguita sul giorno di borsa 2026-07-31. |
| 2026-08-03 | Inizio del periodo di osservazione. |

### Nota sulla riga del 2026-07-31

`market_daily.jsonl` contiene una riga per il **2026-07-31**, e `findings.json` i record **F-001** e
**F-002**, prodotti dalla prova end-to-end del protocollo. Sono dati veri, generati dal protocollo
reale su un giorno di borsa reale — non fixture — ma cadono **prima** dell'inizio della finestra.

Alla sintesi del giorno 40 vanno trattati così:
- La riga di mercato del 2026-07-31 **non entra** nel conteggio dei giorni della finestra.
- Le occorrenze datate 2026-07-31 su F-001 e F-002 **non contano** verso le soglie di ricorrenza né
  verso i costi cumulati.
- I due findings restano aperti con i loro id: se ricompaiono dal 2026-08-03 in poi, le nuove
  occorrenze contano normalmente.
