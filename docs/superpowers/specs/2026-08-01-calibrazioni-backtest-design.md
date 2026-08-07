# Calibrazioni C1-C3 del programma di backtest — Design

Data: 2026-08-01
Stato: design, decisioni prese e auto-approvate su raccomandazione

Vincolato da: `docs/evidence/PREREGISTRAZIONE_BACKTEST_S1.md` (§4) e
`docs/evidence/OBSERVATION_CHARTER.md`

## 1. Perché queste tre e perché adesso

La pre-registrazione impone che le calibrazioni siano completate **prima** di qualunque ipotesi
confermativa, perché determinano se le confermative siano interpretabili. Non sono test: non c'è
un'ipotesi nulla da rifiutare, producono una stima e il suo intervallo.

Sono anche l'unico lavoro disponibile a rischio zero mentre il periodo di osservazione è in corso:
girano offline, non toccano il sistema di trading, e la carta le permette esplicitamente («ricerca
libera subito, applicazione live solo alla scadenza»).

**Non è in scope** la issue #174 (orchestratore del dossier), che modifica lo script di produzione e
resta bloccata fino alla verifica del 2026-08-04.

## 2. Le tre calibrazioni

### C1 — Ordine di grandezza dell'effetto sulla gamba long

Replicare il segnale 12-2 **long-only** sull'universo Alembic e stimare l'extra-rendimento rispetto
al benchmark, con intervallo di confidenza.

**Atteso:** 0,2-0,4%/mese con |t| ≈ 1,2. Cioè **non dimostrabile**. Il risultato utile è
l'intervallo, non un verdetto: serve a fissare l'ordine di grandezza che tutte le confermative
dovranno battere.

### C2 — Diluizione da universo ristretto

Quanto lo spread top-meno-benchmark sui nostri ~96 nomi differisce da quello dei decili CRSP sullo
stesso periodo, e quanti simboli erano effettivamente disponibili anno per anno.

Il secondo numero **è** la misura del bias di sopravvivenza che la pre-registrazione chiede di
misurare invece di assumere: se dei 96 di oggi solo N erano quotati e con dati nel 2010, il backtest
su tutti e 96 sta usando informazione che nel 2010 non avevamo.

### C3 — Costi di transazione

Costo per rotazione dell'universo, usando i modelli già presenti in `src/backtest/costs/`
(`spread_tiers.py`, `impact_model.py`, `realistic.py`) invece di inventarne di nuovi.

**Perché è una calibrazione e non un dettaglio:** l'holding attuale di ~14 giorni implica ~18
rotazioni l'anno contro le 2 di una 6/6. Senza C3, F2 (holding period) e F3 (settoriale) non sono
interpretabili — è proprio il turnover che mettono in discussione.

## 3. Decisioni di progetto

Prese e auto-approvate. Ognuna con il motivo, così è contestabile.

### D1 — Il loader Alpaca si aggiunge, non sostituisce

`src/backtest/data/loader.py` (yfinance) è usato da **cinque backtest di strategia**
(`src/strategies/s{1,2,3,4}/backtest.py`, `s3/universe.py`) e da `scripts/download_initial_data.py`.
Sostituirlo in place li toccherebbe tutti, durante un periodo in cui il vincolo è non rompere niente.

Si aggiunge `src/backtest/data/alpaca_loader.py` accanto, che riusa la `ParquetCache` esistente.
Chi vuole Alpaca lo importa esplicitamente; il resto continua a funzionare com'è.

### D2 — Moduli puri più orchestratore sottile

Stesso schema della fase 2 del dossier, che ha funzionato: la logica di calcolo sta in moduli che
**non fanno I/O** e sono testabili con fixture in memoria; l'orchestratore è l'unico punto che tocca
rete e disco.

Conseguenza pratica: la parte delegabile non richiede credenziali né connettività, e la parte che
richiede entrambe è piccola e la scrive il revisore.

### D3 — C1 misura la letteratura sul nostro universo, non simula S1

C1 usa **ribilanciamento mensile**, non il ciclo a 15 minuti di S1. Non è una svista: C1 deve
stabilire quanto vale l'effetto documentato *sul nostro paniere*, e l'unico modo di confrontarlo con
la letteratura è usare la stessa cadenza della letteratura.

Il disallineamento fra questa cadenza e quella di S1 non è un difetto di C1: **è l'oggetto
dell'ipotesi F2**, che chiede se l'holding a 14 giorni sia fuori finestra. Confondere le due cose
renderebbe F2 non falsificabile.

### D4 — Benchmark primario: equal-weight dell'universo investibile a quella data

Non SPY. Motivo: confrontare i vincitori del nostro paniere contro SPY mescola due effetti — la
selezione per momentum e il fatto che il nostro paniere non sia il mercato. L'equal-weight dello
stesso universo isola la selezione, che è ciò che C1 deve calibrare.

SPY viene riportato come secondario, per continuità con il modo in cui leggiamo il P&L live.

### D5 — Point-in-time per disponibilità di dati, non per inception dichiarata

`universe.py` ha già un `active_at()` basato su una data di inception dichiarata in
`config/universe.yaml`. Per queste calibrazioni si usa invece la **disponibilità effettiva delle
barre**: un simbolo entra nel paniere di un mese solo se ha abbastanza storia per calcolare il
segnale a quella data.

Motivo: l'inception dichiarata è un metadato che può essere sbagliato o mancante, mentre la presenza
della barra è un fatto. E il conteggio dei simboli disponibili per anno è esattamente il numero che
serve a C2.

### D6 — Riuso dei modelli di costo esistenti

C3 non inventa una stima di costo: usa `src/backtest/costs/`. Se quei modelli sono inadeguati, il
risultato di C3 è «i modelli di costo esistenti dicono X», che è comunque un'informazione onesta e
tracciabile. Scrivere un secondo modello di costo accanto a uno esistente creerebbe due verità.

### D7 — Output versionato e tracciabile

Un JSON per esecuzione in `docs/evidence/calibration/`, più un breve report Markdown. Stessa
filosofia del dossier: ogni numero citato deve essere risalibile alla riga che l'ha prodotto.

## 4. Struttura

| file | responsabilità | chi |
|---|---|---|
| `src/analysis/calibration/momentum.py` | segnale, formazione portafoglio, rendimenti di periodo, statistiche riassuntive — **puro** | esecutore |
| `tests/analysis/test_calibration_momentum.py` | test con fixture in memoria | esecutore |
| `src/backtest/data/alpaca_loader.py` | download barre giornaliere da Alpaca con cache parquet | revisore |
| `scripts/run_calibration.py` | orchestratore: carica, cicla i mesi, scrive output | revisore |

## 5. Cosa NON è in scope

- Le ipotesi confermative F1-F5: la pre-registrazione le blocca finché le calibrazioni non sono fatte.
- La issue #174: modifica lo script di produzione, bloccata fino al 2026-08-04.
- Qualunque modifica a strategie, configurazione o parametri live: il freeze le vieta.
- L'acquisto di dati storici: la pre-registrazione dice di comprare solo se C2 mostra che il bias morde.

## 6. Rischi

| rischio | mitigazione |
|---|---|
| Alpaca ha storia limitata all'indietro e C1 copre meno anni del previsto | L'orchestratore riporta esplicitamente il periodo effettivamente coperto; se è troppo corto, è un risultato da registrare, non da aggirare con un'altra fonte |
| Con decili di ~10 nomi la varianza è alta e l'intervallo di C1 sarà largo | È il punto: C2 quantifica proprio questo, e la pre-registrazione già dichiara che C1 non è dimostrabile |
| I modelli di costo esistenti sono tarati su ipotesi non documentate | C3 riporta quale modello ha usato e con quali parametri; il numero è tracciabile e contestabile |
| Il nuovo loader diverge dal vecchio su prezzi rettificati | L'orchestratore confronta un campione di simboli fra i due loader e riporta le differenze invece di sceglierne uno in silenzio |
