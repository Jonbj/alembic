# Copertura dell'archivio news 2024-2025 (issue #610)

Generato il **2026-09-17**, **prima di qualunque esito**. È il punto 3 della DoD di
Fase 1, e l'ordine non è formale: un buco di copertura letto qui è un buco; scoperto
dopo, somiglia a un risultato.

Dati: `docs/evidence/copertura_news_610.json` ·
Pre-registrazione: `docs/evidence/PREREGISTRAZIONE_BACKTEST_NEWS_2024_2025.md`

**Nessuna ipotesi è stata valutata.** Qui non c'è nessun `t`, nessun effetto, nessun
verdetto: solo che cosa c'è nell'archivio.

## Le quattro popolazioni

| popolazione | articoli | quota della precedente |
|---|---:|---:|
| **archivio** — tutto ciò che Alpaca ha servito per le finestre di fetch | 127.000 | — |
| di cui **fuori finestra** su `created_at` | 34.294 | 27,0% |
| **popolazione** — creati fra 2024-01-01 e 2025-12-31 | **92.706** | 73,0% |
| di cui **senza corpo** (la pipeline non li vede affatto) | 39.910 | 43,1% |
| di cui **stantii all'arrivo** | 811 | 0,9% |
| di cui **duplicati** sulla chiave di produzione | 2.297 | 2,5% |
| **ricostruita** — ciò che la pipeline avrebbe processato | **49.688** | 53,6% |

24 mesi pieni, da 3.152 (2024-12) a 4.856 (2025-10) articoli al mese: **nessun mese
mancante e nessun mese anomalo**. La copertura non ha buchi temporali.

### Il 27% fuori finestra non è rumore

Sono gli articoli che l'API restituisce perché filtra su `updated_at`, mentre la
popolazione è definita su `created_at` (§1.2 della pre-registrazione). Sono evergreen e
listicle ri-serviti anni dopo la creazione — «3 Outdoor Stocks To Watch For Summer
2020», «NFT Craze A Reminder Of Tulip Mania?» — cioè **la stessa classe che H-A e H-B
devono misurare**.

Se fossero entrati nella popolazione avrebbero caricato un gruppo solo, nella direzione
che rende H-A più facile da far passare. Vale la pena notare che in produzione questi
articoli **vengono già scartati**: arrivano con timestamp vecchio e `_is_stale_news` li
elimina. Il difetto sarebbe stato della misura, non del sistema.

### Il 43% senza corpo è il fatto più grande dell'archivio

Quarantatremila articoli su 92.706 hanno `summary` e `content` entrambi vuoti.
`AlpacaNewsConnector._parse_article` restituisce `None` per questi: **la pipeline live non
li vede affatto**, oggi e da sempre.

È cosa **diversa** dai template `CONTENT_EMPTY`, che il testo ce l'hanno e che il detector
riconosce dal titolo. Tenerli nello stesso gruppo confonderebbe ciò che il sistema scarta
per assenza di materiale con ciò che il detector classifica per forma.

## Quote sulla popolazione

| | quota |
|---|---:|
| fuori orario (fuori 09:30-16:00 ET, o weekend) | **46,6%** |
| multi-ticker (più di un simbolo) | **44,9%** |
| senza corpo | **43,1%** |
| riconosciuti dal detector `CONTENT_EMPTY` | **2,5%** |

### Il 2,5% è il numero da portare al tavolo del 28/09

La Leva A di #607 è *«filtrare gli articoli CONTENT_EMPTY / RETROSPECTIVE»*. Su questo
archivio il detector ne riconosce il **2,5%**.

Questo non dice se il detector separa bene — **è H-A a doverlo stabilire**, e non è ancora
stata eseguita. Dice però quanto flusso la leva toccherebbe se il detector fosse perfetto:
due articoli e mezzo su cento, non gli ~80% di cui parla la diagnosi del 2026-09-16.
Sono due grandezze diverse e vanno tenute separate: *«l'80% del flusso intraday non muove
il prezzo»* è un'affermazione sugli effetti, *«il detector ne riconosce il 2,5%»* è
un'affermazione sullo strumento.

Se la decisione del 28/09 poggia sull'idea che la Leva A ripulisca la maggior parte del
flusso, questo numero va guardato prima.

## Copertura dell'universo

**94 dei 96 simboli** hanno almeno un articolo. Nessun simbolo coperto sta sotto i 50
articoli: chi c'è, c'è in quantità utilizzabile.

I due assenti:

- **`BRK.B`** — zero articoli. Quasi certamente una questione di notazione del ticker
  (Benzinga usa `BRK-B`), non assenza di copertura. Va verificato prima di trattarlo come
  un buco di dati, ed è esattamente il tipo di cosa che questo artefatto esiste per far
  emergere ora.
- **`SPCX`** — zero articoli, ed è uno dei cinque nomi aggiunti alla watchlist il
  2026-06-30 *perché producevano segnali forti*. Un simbolo senza copertura Benzinga nel
  2024-2025 che genera segnali nel 2026 merita una spiegazione.

I cinque selezionati sull'esito, per volume: HOOD 1.417, RDDT 694, ROKU 504, WDC 440,
SPCX 0. Ogni esito andrà pubblicato **anche** senza di loro (§6 della pre-registrazione).

Primi cinque per volume nell'universo: SPY 17.284, TSLA 9.540, NVDA 9.368, AAPL 7.191,
MSFT 6.241.

`tag_distinti_totali` è 8.038, ma **non è copertura**: i `symbols` di Benzinga portano
ogni ticker taggato nell'articolo, compresi gli 8.000 fuori watchlist. La prima versione
di questo artefatto riportava «8038 simboli coperti» su un universo di 96 — corretto prima
della pubblicazione.

## Un limite dichiarato

La popolazione ricostruita applica `_is_stale_news` con `now = updated_at`, cioè il momento
in cui Alpaca ha servito l'articolo. **È una ricostruzione, non un dato**: l'archivio non
registra la latenza di consegna reale della pipeline. La scelta è difendibile — è quando
la pipeline lo avrebbe ricevuto — ma il conteggio degli 811 stantii va letto come stima,
non come misura.

## Cosa manca della Fase 1

H-A (la sola che deve arrivare al 28/09), poi H-B, H-C, H-E, H-F e la secondaria
sull'eterogeneità per titolo.
