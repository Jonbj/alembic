# Pre-registrazione — il sentiment sulle news fuori orario predice il gap di apertura

Scritta il **2026-09-16**, prima del test confermativo. L'ipotesi nasce da un pilota
esplorativo dello stesso giorno: quel pilota **non è il test** e i suoi numeri non sono
riportabili come risultato. Questo documento fissa campione, regola e criterio *prima*
che il test venga eseguito.

Issue: #606 · Analisi esplorativa: `docs/research/2026-09-16-s4-event-study-latenza.md`

## 1. Da dove nasce l'ipotesi (e perché non è essa stessa il risultato)

Un event study sulle news Benzinga **in orario** (742 eventi, 25 sedute, barre al minuto
SIP) non trova **nessuna** reazione di prezzo attorno al `published_at`: curva media
piatta a ogni offset fra T−60 e T+60 minuti, e — controllo decisivo — **nessun picco di
volatilità** a T (0,89× il fondo; 0,58× sui soli |score| ≥ 0,5, n=35). Un evento vero
produce 2-5×. La volatilità è più alta *prima* dell'articolo che dopo.

Lettura: lo stream Benzinga intraday che consumiamo è in larga parte cronaca
retrospettiva — l'articolo segue il movimento. Comprarci sopra è comprare a movimento
fatto, che produce meccanicamente l'IC leggermente negativo osservato da giugno.

La stessa misura sulle news **fuori orario** si comporta all'opposto. È questa
l'ipotesi che si porta al test.

**Difetto trovato e corretto dentro il pilota, registrato qui perché non si ripeta:** la
prima passata dava +0,936% con n=68. L'attrito 380→68 non era casuale — Alpaca rifiuta
l'**intera** richiesta con `subscription does not permit querying recent SIP data` quando
la finestra tocca l'embargo sul dato recente, quindi cadevano esattamente i simboli con
news recenti, cioè i più liquidi. Con la finestra troncata a `now − 3 giorni` il campione
sale a 330 e l'effetto **scende**. Qualunque implementazione di questa misura deve
troncare la finestra dati e **fallire rumorosamente** se un fetch non riesce, mai
proseguire su ciò che resta.

## 2. Ipotesi

**H1.** Per le news pubblicate a mercato chiuso, il segno del sentiment predice il segno
del **gap di apertura** della prima seduta utile, in eccesso sul mercato.

**H0.** Il gap in eccesso allineato al segno del sentiment ha media zero.

**H2 (separata, non confonderla con H1).** Ciò che resta **dopo** l'apertura — la gamba
intraday `open → close` — non ha contenuto predittivo. H2 è la domanda di
*raccoglibilità*, non di esistenza del segnale: H1 può essere vera e H2 anche, e in quel
caso il segnale esiste ma non è incassabile entrando all'apertura.

## 3. Campione

- **Popolazione:** righe `sentiment_signals` con `news_log.source = 'alpaca_benzinga'`,
  `published_at` non nullo, e `published_at` **fuori** dalla finestra
  09:30–16:00 America/New_York nei giorni feriali.
- **Soglia di ammissione:** `abs(score) >= 0.10`. Dichiarata ora e non rivedibile: è la
  soglia del pilota, non ottimizzata.
- **Riduzione:** una osservazione per `(simbolo, seduta di reazione)`, con
  `scelta_produzione()` di `scripts/measure_169_dedup_rules.py` **importata, non
  riscritta** (regola #169/#467).
- **Finestra dati:** barre giornaliere Alpaca **SIP**, `adjustment=all`, troncate a
  `now − 3 giorni` (vedi §1). Un fetch fallito **aborta la misura**, non riduce il
  campione.
- **Seduta di reazione:** la prima seduta di borsa che apre dopo `published_at`.

## 4. Outcome

- **Primario:** `gap_eccesso = sign(score) × [ (open_succ − close_prec)/close_prec
  − (open_SPY − close_SPY)/close_SPY ]`.
- **Secondario (H2):** `intraday_eccesso`, stessa forma su `(close_succ − open_succ)/open_succ`.
- **Diagnostico, non outcome:** quota dei segnali scoriati **dopo** l'apertura della
  seduta di reazione.

L'aggiustamento di mercato è **parte della definizione**, non un controllo opzionale: è
il difetto che ha invalidato l'analisi esterna del 2026-09-16.

## 5. Statistica — dichiarata prima

- Unità di inferenza = **la giornata**, non l'evento. Gli eventi della stessa seduta
  condividono il fattore di mercato e non sono indipendenti.
- Media delle medie giornaliere; `t` sugli errori standard fra giornate.
- **Barra: |t| ≥ 3.** È la soglia di casa (`config/s4_kill_criterion.yaml`), non una
  scelta di comodo per questo test.
- `effetto_rilevabile_a_t3` va **pubblicato con l'esito**. Se l'effetto osservato è sotto
  quella soglia, l'esito è `INSUFFICIENT_N`, che batte PASS/FAIL per costruzione.

### Potenza, calcolata ora

Dal pilota: dispersione giornaliera stimata ≈ **1,67%**, con 49 giornate utili.

| | valore |
|---|---|
| giornate necessarie per |t| ≥ 3 sull'effetto del pilota | **≈ 80** |
| giornate già disponibili | 49 |
| giornate mancanti | **≈ 31** |

A ritmo osservato (49 giornate con eventi in ~3 mesi) la soglia cade **verso metà
novembre 2026**. È il motivo per cui questo test merita di esistere: a differenza del
criterio S4 su `s4_ic.json` — che con 213 sedute richieste non decide prima di metà 2027
(#601) — **questa domanda è decidibile in settimane.**

## 6. Cosa NON fa questo test

1. Non misura S4. Misura una **popolazione che S4 oggi mescola** con lo stream intraday.
2. Non misura l'ensemble contro FinBERT. Quel confronto è separato: nel campione
   generale i due hanno IC indistinguibili (−0,0394 contro −0,0377).
3. **Non dimostra che il gap sia incassabile.** Entrando all'apertura il gap è già
   avvenuto. H1 vera e H2 vera insieme significano *segnale reale, non raccolto*.
4. Non autorizza nessuna modifica al path dei segnali. Separare le popolazioni e anticipare
   lo scoring sono **taratura**: restano congelate, e la decisione è del 2026-09-28 (#607).

## 7. Esiti possibili, dichiarati prima

| esito | condizione | conseguenza |
|---|---|---|
| **PASS** | gap in eccesso, |t| ≥ 3, segno positivo | H1 sostenuta: la separazione delle popolazioni (#607) ha una base misurata |
| **FAIL** | |t| ≥ 3 con segno negativo o nullo a effetto rilevabile | il sentiment non predice nemmeno gli eventi veri: S4 come strategia d'ingresso è ritirata |
| **INSUFFICIENT_N** | effetto sotto `effetto_rilevabile_a_t3` | si continua a raccogliere fino a ≈80 giornate, senza rileggere l'esito per strada |

**Nessuna lettura intermedia.** L'esito si guarda quando il conteggio delle giornate
raggiunge 80, non prima. Guardare per strada e fermarsi quando piace è la mossa che
questa pre-registrazione esiste per impedire.

## 8. Vincolo di freeze

La misura è **strumentazione**: sola lettura su `sentiment_signals`, `news_log` e barre
storiche; nessuna scrittura su `news_log`, `sentiment_signals` o Redis; nessuna soglia,
peso, flag o cooldown toccato; nessun ordine. Registrata in
`docs/evidence/OBSERVATION_CHARTER.md` alla data del 2026-09-16.
