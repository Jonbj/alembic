# Report alpha-miner simmetrico: dossier deterministico + giudizio LLM — Design

Data: 2026-08-01
Stato: design approvato, implementazione non iniziata
Documento gemello: `2026-08-01-osservazione-evidenze-roadmap-pesata-design.md`

**Rilascio in due tempi** (deciso il 2026-08-01). Le due modifiche toccano lo stesso prompt ma NON
vengono rilasciate insieme:

| quando | cosa | tipo di lavoro |
|---|---|---|
| **lunedì 2026-08-03** | protocollo ledger del documento gemello: lettura di `findings.json`, match degli ID, append di `market_daily.jsonl` | solo prompt |
| **appena pronto** | questo documento: script del dossier, sezioni nuove, aggregazioni | script + prompt |

Conseguenza favorevole: **i findings e la serie di mercato partono dal giorno 1**, quindi cade
l'inserimento manuale retroattivo previsto in §8. Resta da ricalcolare solo ciò che dipende dallo
script.

## 1. Problema

`scripts/daily_alpha_miss_analysis.sh` gira alle 10:00 lun-ven e produce
`docs/ALPHA_MISS_REPORT_YYYY-MM-DD.md` tramite una sessione Claude non interattiva. Tre limiti
emersi leggendo i cinque report prodotti fra il 24 e il 30 luglio.

**Il report può trovare solo ciò che abbiamo mancato.** È asimmetrico per costruzione: chiede "quali
titoli sono saliti e non abbiamo preso". Ma l'analisi del 2026-07-31 ha mostrato che il **90% della
perdita realizzata di S4 e il 76% di quella di S1 si concentrano negli ingressi dell'ora 14:00 UTC**
— cioè in posizioni aperte e sbagliate, non in occasioni mancate. Un report sui soli miss non può
vederle.

**La qualità di cattura è aneddotica.** Il report del 2026-07-30 ha trovato che il problema di quel
giorno non erano i miss ma la cattura degradata: MSFT catturato su una giornata a +15,5% e portato a
casa per $13,03, perché l'uscita è scattata 2h45 dopo l'ingresso. È stata una scoperta fortuita di
un report, non una metrica che il formato produce sempre.

**I numeri sono ri-derivati da un LLM ogni mattina.** La soglia mover è stata motivata in modo
diverso in report diversi (σ cross-sectional il 24, "banda di rumore tipica" il 27-30). Il §6
"confronto con i giorni precedenti" è prosa a memoria: il report del 2026-07-28 ha dichiarato
esplicitamente di non aver riletto gli altri e di basarsi sulla memoria di sessione.

A questo si aggiunge un rischio operativo: la memoria di progetto registra che il cron gemello
(forensic) può **fallire in silenzio per timeout**. Aggiungere due dimensioni analitiche a una
sessione già lunga aumenta quel rischio, e se il report muore muore l'osservazione dei 40 giorni.

## 2. Decisioni prese

Prese con l'operatore il 2026-08-01:

1. **Scopo**: report **simmetrico** — miss, falsi positivi e qualità di cattura, non solo miss.
2. **Attribuzione temporale**: due sezioni — *decisioni di oggi* (provvisorio, mark-to-market a fine
   giornata) e *chiusure di oggi* (definitivo).
3. **Affidabilità**: **deroga esplicita al freeze** — uno script deterministico calcola, l'LLM solo
   interpreta. Da annotare nella carta di osservazione come eccezione, con data e commit.
4. **Calendario**: l'osservazione **parte lunedì 2026-08-03 con lo strumento attuale**; script e
   prompt nuovi si innestano appena pronti.

## 3. Architettura: lo script calcola, l'LLM giudica

Il confine non è arbitrario. Classificare un miss come `THIN_NEUTRAL` invece che `NO_NEWS` richiede
di leggere l'articolo e decidere se è un roundup macro generico o un catalyst specifico sul titolo:
è giudizio irriducibile, e un LLM lo fa bene. Calcolare dove cade un prezzo d'ingresso nel range
della giornata è aritmetica, e un LLM che la rifà ogni mattina la rifà ogni mattina in modo
leggermente diverso.

```
scripts/alpha_miner_dossier.py   (nuovo, deterministico)
        |
        v
docs/evidence/dossier/YYYY-MM-DD.json     <- tutti i numeri, versionato
        |
        v
sessione Claude (prompt rivisto)  <- legge dossier + findings.json
        |
        +--> docs/ALPHA_MISS_REPORT_YYYY-MM-DD.md   (interpretazione, classificazione, §7)
        +--> docs/evidence/market_daily.jsonl        (append riga del giorno)
        +--> docs/evidence/findings.json             (match ID o nuovo record)
```

Il dossier è **versionato e non effimero**: ogni numero del report deve essere risalibile alla riga
di dossier che lo ha prodotto. Sono ~40 file JSON sull'arco della finestra di osservazione.

## 4. Il dossier

`scripts/alpha_miner_dossier.py <data>` produce `docs/evidence/dossier/<data>.json`. Legge barre
Alpaca (feed IEX, coerente con il resto del sistema), `alembic-postgres-1` e `alembic-redis-1`.
Read-only su entrambi.

```json
{
  "data": "2026-07-30",
  "mercato": {
    "spy": 0.0165, "qqq": 0.0333,
    "dispersione_sigma": 0.0512,
    "rendimenti": {"MU": 0.1836, "MSFT": 0.1551, "…": 0.0},
    "mover_3pct": 40, "up": 29, "down": 11,
    "watchlist_zero_news": 39
  },
  "ingressi": [
    {"symbol": "MSFT", "strategia": "S4", "ora_utc": "14:37",
     "entry_price": 450.72, "qty": 2.82,
     "low": 437.10, "high": 452.30, "close": 451.55, "open": 438.47,
     "entry_percentile": 0.89, "mtm_eod": 2.34, "vs_apertura": 36.89,
     "signal_score": 0.765}
  ],
  "chiusure": [
    {"symbol": "MSFT", "strategia": "S4", "entry_time": "2026-07-30T14:37Z",
     "exit_time": "2026-07-30T17:22Z", "ore_tenuta": 2.75,
     "entry_price": 450.72, "exit_price": 455.56, "qty": 2.82,
     "pnl_net": 13.03, "exit_reason": "portfolio_sell",
     "close_giorno_uscita": 451.55, "drift_post_uscita": -11.31}
  ],
  "candidati_miss": [
    {"symbol": "AVGO", "return": 0.0473,
     "news_count": 2, "segnali": [{"ora": "16:10", "score": 0.150, "fallback": true}],
     "in_portafoglio": false}
  ],
  "aggregati": {
    "per_ora_ingresso": [{"ora": 14, "n": 65, "win": 27, "somma_pnl": -502.09,
                          "media": -7.72, "dev_std": 29.52, "t_stat": -2.11}],
    "miss_cumulati": {"NO_NEWS": 29, "THIN_NEUTRAL": 19, "WRONG_SIGN": 2, "FILTERED": 8},
    "mediane_mobili_20g": {"drift_post_uscita": 1.42, "entry_percentile": 0.71}
  }
}
```

I `candidati_miss` sono **candidati**, non miss classificati: lo script raccoglie l'evidenza
(rendimento, conteggio news, segnali con score e flag fallback, presenza in portafoglio) e la
sessione decide la categoria leggendo il testo degli articoli.

## 5. Metriche — definizioni

Tutte calcolate dallo script, mai dall'LLM.

| metrica | formula | note |
|---|---|---|
| `entry_percentile` | `(entry_price − low) / (high − low)` | 0 = comprato sul minimo del giorno, 1 = sul massimo. Se `high == low`, vale `null` |
| `mtm_eod` | `(close − entry_price) × qty` | esito provvisorio di un ingresso |
| `vs_apertura` | `(close − open) × qty` | termine di paragone: quanto avrebbe reso comprare all'apertura la stessa quantità |
| `drift_post_uscita` | `(close_giorno_uscita − exit_price) × qty` | positivo = soldi lasciati sul tavolo; negativo = perdita evitata |
| `dispersione_sigma` | dev. std cross-sectional dei rendimenti dei 96 simboli | già usata nel report del 24/07 per motivare la soglia mover |

L'`entry_percentile` è la misura diretta dell'inseguimento. Riscontro: S1 ha comprato F a 16,02 il
2026-07-29, giornata con range 15,16-16,29 → percentile 0,7611; il titolo ha chiuso a 15,28 e la
posizione è stata liquidata il giorno dopo a −$52,00.

Il `drift_post_uscita` sistematizza un'osservazione che i report facevano a occhio ("uscita a 46,07
contro close 46,38, ~$8 lasciati sul tavolo"). Se la sua mediana mobile è stabilmente positiva,
usciamo troppo presto — ed è misurabile, a differenza di un miss.

## 6. Struttura del report

Tre domande, in quest'ordine.

**1. Cosa abbiamo mancato.** Invariata nella sostanza: soglia mover, tabella rendimenti,
classificazione con la tassonomia esistente (`NO_NEWS`, `THIN_NEUTRAL`, `WRONG_SIGN`, `FILTERED`,
`OUT_OF_STRATEGY_SCOPE`). Novità: ogni miss porta un costo stimato, sempre a confidenza
**congetturale** per definizione — non sappiamo se saremmo entrati, con che size, né quando saremmo
usciti.

**2. Cosa abbiamo comprato che non doveva essere comprato.** Sezione *decisioni di oggi*, dal blocco
`ingressi` del dossier. Riporta le metriche **senza emettere verdetti**: su un book dove la
posizione media S1 dura 14 giorni, il mark-to-market di fine giornata non è un giudizio sulla
decisione. Serve a rendere visibile il pattern, non a condannare il singolo trade.

**3. Quanto abbiamo estratto da ciò che abbiamo preso.** Sezione *chiusure di oggi*, dal blocco
`chiusure`. Qui il verdetto è legittimo perché l'esito è completo.

### Regola anti-doppio-conteggio

Una posizione compare in due report diversi: il giorno in cui apre (provvisorio) e il giorno in cui
chiude (definitivo). **Il ledger delle evidenze conta solo il verdetto definitivo.** L'esito
provvisorio non genera mai occorrenze con costo diverso da zero.

## 7. Aggregazioni

Tre tabelle calcolate dallo script leggendo `market_daily.jsonl` e il DB, non ri-derivate a prosa:

- **Per ora d'ingresso.** È dove è emerso il finding più forte della settimana. Diventa una riga
  fissa invece di una scoperta fortuita.
- **Per causa di miss, cumulata.** La serie NO_NEWS/THIN_NEUTRAL nel tempo, che oggi richiede di
  rileggere cinque report a mano.
- **`entry_percentile` e `drift_post_uscita`, mediane mobili a 20 giorni.** La qualità di esecuzione
  come serie, non come aneddoto: la prima dice se stiamo sistematicamente inseguendo in ingresso, la
  seconda se stiamo sistematicamente uscendo troppo presto.

Nota: non esiste una metrica unica di "capture ratio". Un rapporto fra P&L ottenuto e movimento
disponibile richiederebbe un denominatore arbitrario (il massimo del giorno? la chiusura? il massimo
favorevole intra-posizione, che serve barre a minuti e qui è fuori scope) e sarebbe instabile quando
il denominatore tende a zero. Le due mediane sopra misurano le due metà del problema senza inventare
un rapporto fragile.

Il §6 "confronto con i giorni precedenti" smette di essere prosa a memoria e diventa lettura del
ledger.

### Onestà statistica, da imporre nel prompt

Le aggregazioni per sottogruppo (ora d'ingresso, strategia, causa) sono **analisi post-hoc su molti
bucket**. Il prompt deve imporre alla sessione di riportare la numerosità e di non dichiarare
significativo un risultato che non sopravviverebbe a una correzione per confronti multipli. Esempio
concreto dal 2026-07-31: l'ora 14 su S4 dà t = −2,11 (p ≈ 0,04) su 8 bucket orari — con correzione
non sopravvive, e va detto.

## 8. Innesto e recupero dei primi giorni

L'osservazione parte lunedì 2026-08-03 con lo strumento attuale; script e prompt si innestano appena
pronti. La carta di osservazione registra la **data dell'innesto**.

Grazie al rilascio in due tempi (vedi intestazione), il recupero è molto più semplice di quanto
previsto in origine:

- I **findings partono dal giorno 1**: il protocollo di match è attivo dal 3 agosto perché è solo
  prompt. Nessun inserimento manuale retroattivo.
- Le **righe di mercato partono dal giorno 1**, scritte dalla sessione: sono gli stessi numeri che
  il report già calcola per la sua tabella.
- Restano da ricalcolare solo le metriche introdotte da questo documento (`entry_percentile`,
  `mtm_eod`, `vs_apertura`, `drift_post_uscita`). Sono **ricostruibili al 100%** da barre Alpaca e
  DB, entrambi storici: lo script accetta una data arbitraria proprio per questo e ribobina fino al
  2026-08-03.

Un'avvertenza: le righe di mercato scritte prima dell'innesto sono calcolate dalla sessione, quelle
successive dallo script. Allo stesso passaggio lo script deve **ricalcolare e riscrivere** le righe
del periodo precedente, così l'intera serie ha una sola provenienza. È l'unica eccezione ammessa
alla regola "solo append" del documento gemello, e va annotata nella carta.

## 9. Deroga al freeze

La carta di osservazione (`docs/evidence/OBSERVATION_CHARTER.md`) prevede che si tocchino solo i
difetti di correttezza. Questo script **non** è un difetto di correttezza: è strumentazione. Va
quindi annotato nella carta come **deroga esplicita**, con data, motivo e commit — coerentemente con
la regola che ogni eccezione resti ricostruibile.

Motivo da registrare: senza precalcolo deterministico, i numeri su cui si baserà la roadmap pesata
sono ri-derivati ogni mattina da un LLM diverso, e la sessione rischia il timeout silenzioso che
farebbe fallire l'osservazione stessa.

## 10. Fuori scope

- **Nessuna modifica al perimetro di analisi.** Resta la watchlist dei 96 simboli; non diventa uno
  scan whole-market.
- **Nessuna proposta di fix nel report.** Resta la regola attuale: la sessione descrive, non propone
  rimedi; la decisione se aprire una issue è dell'operatore. Il ledger aggiunge identità e costo,
  non giudizio su cosa fare.
- **Nessuna modifica al report forensic** oltre al protocollo di match degli ID già previsto nel
  documento gemello.
- **Nessuna analisi intraday sotto il giorno.** Le metriche usano barre giornaliere (open, high,
  low, close). Massimo favorevole e minimo sfavorevole intra-posizione richiederebbero barre a
  minuti: valutabili dopo, non ora.

## 11. Rischi

| rischio | mitigazione |
|---|---|
| Lo script diventa esso stesso un progetto e ritarda l'innesto | Perimetro chiuso: calcola le metriche di §5 e le aggregazioni di §7, niente altro. L'osservazione intanto è già partita |
| Il dossier e il report divergono (l'LLM ricalcola invece di leggere) | Il prompt vieta esplicitamente di ricalcolare ciò che il dossier contiene; ogni numero nel report cita il campo di dossier |
| Le sezioni nuove allungano il report e riportano il rischio timeout | Il precalcolo accorcia la sessione: l'LLM non scarica più barre né interroga il DB per i numeri |
| L'LLM emette verdetti sulle decisioni provvisorie | Regola esplicita in §6: la sezione provvisoria riporta metriche, non verdetti |
| Le aggregazioni per sottogruppo vengono lette come scoperte | Vincolo di onestà statistica nel prompt (§7) |

## 12. Riferimenti

- Script attuale: `scripts/daily_alpha_miss_analysis.sh`
- Report letti per l'analisi: `docs/ALPHA_MISS_REPORT_2026-07-{24,27,28,29,30}.md`
- Documento gemello: `docs/superpowers/specs/2026-08-01-osservazione-evidenze-roadmap-pesata-design.md`
- Evidenza sull'ora 14:00 UTC e sul divario realizzato/economico: analisi di sessione 2026-07-31,
  riassunta nel commento a #134
