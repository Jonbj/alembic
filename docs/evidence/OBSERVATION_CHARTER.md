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

**2. S1 ha un edge una volta corretta la misura?**

Criterio: P&L **economico** di S1 sulla finestra confrontato con SPY, con la serie **realizzata
esplicitamente ignorata**.

**Esito legittimo previsto:** se alla scadenza nessun criterio è soddisfatto, la conclusione corretta
è **estendere la finestra**, non agire comunque.

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
