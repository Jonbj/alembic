# Piano: Alpaca Feature Roadmap

**Data creazione:** 2026-06-15  
**Aggiornato:** 2026-06-16  
**Sessione:** Alpaca feature discovery, poi implementazione incrementale P0→P3  
**File principale modificato:** `src/workers/portfolio_scheduler.py`  
**Stato:** P0 ✅ P1 ✅ P2 ✅ (P2-A, P2-D) — P2-B, P2-C, P2-E da fare — P3 non pianificato

## Commit history
- `a4fc500` feat(alpaca): P0 — bulk cancel, clock check, adjustment=ALL, account flags, fill reconciliation
- `d4a0005` feat(alpaca): P1 — Snapshot API, fractionable pre-flight  
- `4ba95e7` feat(alpaca): P2 — bracket orders (opt-in), WebSocket news streaming

---

## Contesto

Alembic usa Alpaca solo per un sottoinsieme minimale delle funzionalità disponibili. Questa roadmap implementa le features utili in ordine di ROI/effort.

### Stato attuale dell'integrazione Alpaca

```
File: src/workers/portfolio_scheduler.py → _run_cycle_inner()

API usate:
- StockHistoricalDataClient.get_stock_bars()  → riga ~183 (NO adjustment param)
- TradingClient.get_account()                 → riga ~230 (legge solo .cash e .equity)
- TradingClient.get_all_positions()           → riga ~279
- TradingClient.submit_order(MarketOrderRequest) → righe ~607, ~625 (solo market day)
- AlpacaNewsConnector (src/connectors/alpaca_news.py) → REST polling news

API NON usate ma disponibili nell'SDK alpaca-py:
- trading_client.get_clock()
- trading_client.get_calendar()
- trading_client.cancel_orders()             # bulk cancel
- trading_client.close_all_positions()
- trading_client.get_account().buying_power / .trading_blocked / .account_blocked
- StockBarsRequest(adjustment="all")
- StockHistoricalDataClient.get_stock_snapshot()
- TradingClient.get_activities(GetActivitiesRequest(activity_types=["FILL"]))
- GetPortfolioHistoryRequest                 # importato in api/routes/performance.py ma non in scheduler
- OrderClass.BRACKET / .OTO / .OCO
- TrailingStopOrderRequest
- NewsDataStream (WebSocket news)
- StockDataStream (WebSocket bars)
```

---

## P0 — Alto impatto, implementazione semplice (< 1 giorno)

### P0-A: Bulk cancel all orders + close all positions nel kill-switch

**Problema:** Il kill-switch Redis ferma i NUOVI ordini, ma non cancella gli ordini DAY pendenti già submittati nel ciclo corrente. Se il kill-switch si attiva a metà ciclo, quegli ordini si eseguono comunque.

**Dove:** `src/workers/portfolio_scheduler.py`, blocco kill-switch a riga ~140-155.

**Modifica:** Dopo aver rilevato `_ks_active == True`, PRIMA di fare `return`, chiamare:
```python
try:
    trading_client.cancel_orders()        # DELETE /v2/orders  — cancella tutti gli ordini pendenti
    log.info("Kill-switch: cancelled all pending orders")
except Exception as _ksc_exc:
    log.warning("Kill-switch: failed to cancel orders: %s", _ksc_exc)
```

**Problema:** `trading_client` non è ancora inizializzato a riga 140 (viene creato a riga 224). Soluzione: creare una funzione helper `_emergency_cancel(api_key, secret_key, paper)` che istanzia il client localmente.

**Test:** Aggiungere test in `tests/workers/test_portfolio_scheduler.py` che verifica che `cancel_orders()` venga chiamato quando `killswitch_active=1` in Redis.

**API Alpaca:**
- `TradingClient.cancel_orders()` → `DELETE /v2/orders`
- `TradingClient.close_all_positions(cancel_orders=True)` → `DELETE /v2/positions`

---

### P0-B: Market clock pre-flight check

**Problema:** Il ciclo Celery gira su schedule UTC fisso (ogni 15 min, 9:00–21:00 UTC) e non verifica se NYSE è aperto. Nei giorni di early close (Black Friday: chiude 13:00 ET = 18:00 UTC) il ciclo piazza ordini DAY dopo la chiusura — vengono rifiutati o restano pending overnight.

**Dove:** `src/workers/portfolio_scheduler.py`, funzione `_run_cycle_inner()`, PRIMA della fetch dei bars (riga ~169).

**Modifica:**
```python
# Market clock check: skip cycle if market is closed
try:
    from alpaca.trading.client import TradingClient as _TClock
    from src.config import config as _cfg_clock
    _tc_clock = _TClock(
        api_key=_cfg_clock.ALPACA_API_KEY,
        secret_key=_cfg_clock.ALPACA_SECRET_KEY,
        paper="paper-api" in _cfg_clock.ALPACA_BASE_URL,
    )
    clock = _tc_clock.get_clock()
    if not clock.is_open:
        log.info("Market closed (next open: %s) — skipping portfolio cycle", clock.next_open)
        return {"skipped": True, "reason": "market_closed", "next_open": str(clock.next_open)}
except Exception as _clk_exc:
    log.warning("Could not fetch market clock: %s — proceeding anyway", _clk_exc)
```

**Nota:** Usare un client separato (lazy-import) o riusare il `trading_client` principale se già istanziato. Dipende dall'ordine nel codice — preferire lazy init per non rompere il flow.

**Alternativa Redis:** Un secondo Celery task `refresh_market_clock` (ogni 5 min) scrive `market:is_open` in Redis, e `_run_cycle_inner()` legge da Redis. Più efficiente in termini di chiamate API.

**Test:** Mock `get_clock().is_open = False` → assert return `{"skipped": True, "reason": "market_closed"}`.

---

### P0-C: Price series adjustment="all"

**Problema:** `StockBarsRequest` a riga ~183 non ha il parametro `adjustment`. Alpaca per default ritorna prezzi `raw` (non corretti per split/dividendi). Post-split (es. NVDA 10:1 giugno 2024), l'EMA calcolata su prezzi storici non-adjusted è distorta.

**Dove:** `src/workers/portfolio_scheduler.py`, riga ~183.

**Modifica:**
```python
# PRIMA:
request = StockBarsRequest(
    symbol_or_symbols=symbols,
    timeframe=TimeFrame.Day,
    start=start, end=end,
    feed=DataFeed.IEX,
)

# DOPO:
from alpaca.data.enums import Adjustment
request = StockBarsRequest(
    symbol_or_symbols=symbols,
    timeframe=TimeFrame.Day,
    start=start, end=end,
    feed=DataFeed.IEX,
    adjustment=Adjustment.ALL,   # corregge split + dividendi
)
```

**Nota:** Verificare che `alpaca.data.enums.Adjustment` esista nell'SDK versione installata:
```bash
python -c "from alpaca.data.enums import Adjustment; print(Adjustment.ALL)"
```
In alternativa usare il valore stringa `adjustment="all"`.

**Test:** Non richiede nuovo test. La modifica è trasparente — se i dati tornano adjusted, le EMA sono più accurate. Verificare con backtest spot.

---

### P0-D: Account blocking flags nel pre-flight check

**Problema:** `get_account()` a riga ~230 legge solo `.cash` e `.equity`. I campi `.trading_blocked`, `.account_blocked`, `.pattern_day_trader` non vengono letti. Se l'account è bloccato (es. margin call, compliance flag) Alembic tenta comunque di piazzare ordini che verranno rifiutati silenziosamente.

**Dove:** `src/workers/portfolio_scheduler.py`, blocco account fetch ~230-238.

**Modifica:**
```python
account = trading_client.get_account()
cash = float(account.cash)
equity = float(account.equity)

# Pre-flight: verifica che l'account non sia bloccato
if getattr(account, "trading_blocked", False) or getattr(account, "account_blocked", False):
    msg = "🚨 Portfolio cycle: account bloccato da Alpaca — ciclo abortito"
    _fire_alert(notifier, msg, AlertLevel.CRITICAL)
    log.error("Alpaca account blocked — aborting cycle")
    return {"skipped": True, "reason": "account_blocked"}

# Log buying_power per debug (campo diverso da cash per account margin)
buying_power = float(getattr(account, "buying_power", cash))
log.debug("Account: equity=%.2f, cash=%.2f, buying_power=%.2f", equity, cash, buying_power)
```

**Test:** Mock `account.trading_blocked = True` → assert `{"skipped": True, "reason": "account_blocked"}`.

---

### P0-E: Account Activities API per fill reconciliation

**Problema:** La maggior parte dei trade in DB ha `net_pnl=NULL` perché `reconcile_trade_fills` non è implementata correttamente o non viene invocata. L'API Account Activities ritorna tutti i fill con prezzo, qty e commissioni esatte.

**Dove:** Creare task Celery separato `reconcile_fills_from_alpaca` in `src/workers/portfolio_scheduler.py` (o file dedicato).

**Implementazione:**
```python
@app.task(name="workers.reconcile_fills")
def reconcile_fills_from_alpaca() -> dict:
    """Fetch FILL activities from Alpaca and update net_pnl on closed trades."""
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import GetActivitiesRequest
    from src.config import config
    from src.store.pg_store import PostgreSQLStore

    tc = TradingClient(
        api_key=config.ALPACA_API_KEY,
        secret_key=config.ALPACA_SECRET_KEY,
        paper="paper-api" in config.ALPACA_BASE_URL,
    )
    # Fetch last 7 days of fill activities
    since = datetime.now(timezone.utc) - timedelta(days=7)
    activities = tc.get_activities(
        GetActivitiesRequest(activity_types=["FILL"], after=since)
    )
    store = PostgreSQLStore()
    updated = 0
    for act in activities:
        # act.symbol, act.price (fill price), act.qty, act.side, act.transaction_time
        try:
            rows = store.get_open_trades_by_symbol(act.symbol)
            for trade in rows:
                if act.side == "sell" and trade["exit_order_id"] is not None:
                    pnl = (float(act.price) - trade["entry_notional"] / trade["quantity"]) * float(act.qty)
                    store.update_trade_pnl(trade["id"], pnl, float(act.price))
                    updated += 1
        except Exception as exc:
            log.warning("Fill reconciliation error for %s: %s", act.symbol, exc)
    store.close()
    return {"updated": updated}
```

**Schedule:** Aggiungere in `celery_beat_schedule`: ogni ora, oppure triggerare manualmente via FastAPI endpoint `POST /api/reconcile-fills`.

**Nota importante:** Prima di implementare, verificare quali metodi esistono in `PostgreSQLStore` (`src/store/pg_store.py`) per aggiornare il P&L. Se non esistono, aggiungerli.

**Test:** Mock `get_activities()` con 2 fill fake → assert `updated == 2`.

---

## P1 — Alto valore, difficoltà media (2–3 giorni)

### P1-A: Snapshot API per prezzi più freschi

**Problema:** `_build_market_cache()` in `execution.py` usa bars storici giornalieri per il pricing intraday. Il prezzo usato per calcolare il notional degli ordini è il `close` del giorno precedente, non il prezzo corrente.

**Dove:** `src/workers/portfolio_scheduler.py`, blocco ~210-221 (costruzione `MarketSnapshot`).

**Modifica:** Dopo aver calcolato `latest_prices` dai bars, fetchare lo snapshot per aggiornare con i prezzi correnti:
```python
try:
    snapshots = data_client.get_stock_snapshot(symbols)
    for sym, snap in snapshots.items():
        if snap.latest_trade and snap.latest_trade.price:
            latest_prices[sym] = float(snap.latest_trade.price)
        elif snap.minute_bar and snap.minute_bar.close:
            latest_prices[sym] = float(snap.minute_bar.close)
except Exception as exc:
    log.warning("Snapshot fetch failed: %s — using bar closes", exc)
```

**API:** `StockHistoricalDataClient.get_stock_snapshot(symbols)` → ritorna `dict[str, SnapshotData]`

**Test:** Mock snapshot con prezzo diverso dal bar close → assert `market.prices[sym]` usa il prezzo snapshot.

---

### P1-B: Asset API pre-flight per fractionable check

**Problema:** Alembic usa `notional` per tutti gli ordini BUY. Se un simbolo ha `fractionable=False` su Alpaca, l'ordine notional viene rifiutato silenziosamente (o con errore non gestito).

**Dove:** `src/workers/portfolio_scheduler.py`, prima della submit degli ordini (riga ~570).

**Implementazione:** Caricare la fractionability all'avvio del worker (o cache Redis con TTL 24h):
```python
def _get_fractionable_symbols(trading_client, symbols: list[str]) -> set[str]:
    """Return set of symbols that support fractional/notional orders."""
    fractionable = set()
    try:
        for sym in symbols:
            asset = trading_client.get_asset(sym)
            if getattr(asset, "fractionable", True):  # default True = safe to try
                fractionable.add(sym)
    except Exception as exc:
        log.warning("Asset fractionable check failed: %s — assuming all fractionable", exc)
        return set(symbols)
    return fractionable
```

In `_submit_portfolio_orders`: se `order.symbol not in fractionable_symbols` e `side == BUY`, passare a qty intera invece di notional.

**Test:** Mock `get_asset("XYZ").fractionable = False` → assert ordine BUY usa qty intera.

---

### P1-C: Market calendar check per early close

**Problema:** Il market clock check (P0-B) risponde solo a "mercato aperto/chiuso ora". Non prevede early close (es. Black Friday: chiude alle 13:00 ET invece delle 16:00 ET).

**Dove:** Integrare in `P0-B` o come check separato.

**Implementazione:**
```python
from alpaca.trading.requests import GetCalendarRequest
calendar = trading_client.get_calendar(
    GetCalendarRequest(start=date.today().isoformat(), end=date.today().isoformat())
)
if calendar:
    today = calendar[0]
    market_close_et = today.close  # es. "13:00" per early close
    # Confronta con ora corrente ET e saltare se troppo vicino alla chiusura
```

**Alternativa semplice:** Il clock check P0-B è già sufficiente per casi normali. Il calendar è utile solo per implementare logica "non fare entry nelle ultime 30 minuti prima della chiusura", che è una feature P2.

---

### P1-D: Portfolio History come source primario dell'equity curve

**Problema:** L'equity curve viene calcolata aggregando trade records nel DB PostgreSQL, con mark-to-market impreciso (usa fill prices, non prezzi correnti). Alpaca calcola già equity curve mark-to-market accurata.

**Dove:** `src/api/routes/performance.py` riga ~214 — **già implementato** (`get_portfolio_history` con `GetPortfolioHistoryRequest`). Verificare che sia il source primario o se coesiste con un calcolo DB.

**Azione:** Fare audit dell'endpoint `/api/performance` per capire se `get_portfolio_history` è il source primary o fallback. Se secondario, promuoverlo a primario.

---

## P2 — Valore medio, richiede refactoring significativo (1 settimana+)

### P2-A: Bracket orders completi (entry + take-profit + stop-loss)

**Problema:** Alembic usa `MarketOrderRequest` semplici. Un bracket order automatizza take-profit + stop-loss lato broker — nessun polling necessario.

**Dove:** `src/workers/portfolio_scheduler.py`, `_submit_portfolio_orders()` riga ~600-608.

**Modifica per BUY:**
```python
from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderClass

# Parametri configurabili (aggiungere a config.py o S4Config)
TAKE_PROFIT_PCT = 0.06   # +6%
STOP_LOSS_PCT   = 0.03   # -3%  → risk/reward 1:2

req = MarketOrderRequest(
    symbol=order.symbol,
    notional=notional,
    side="buy",
    time_in_force="day",
    order_class=OrderClass.BRACKET,
    take_profit=TakeProfitRequest(limit_price=round(price * (1 + TAKE_PROFIT_PCT), 2)),
    stop_loss=StopLossRequest(stop_price=round(price * (1 - STOP_LOSS_PCT), 2)),
)
```

**Dipendenze:** Richiede prezzo entry accurato (che P1-A risolve). Senza P1-A, il prezzo è il close del giorno precedente → bracket calcolato su prezzo sbagliato.

**Sequenza:** Implementare DOPO P1-A.

---

### P2-B: Trailing stop orders

**Problema:** Lo stop-loss fisso (3%) non cattura i profitti durante i trend. Un trailing stop si sposta verso l'alto automaticamente.

**Dove:** `_submit_portfolio_orders()`, leg stop-loss del bracket order.

**Modifica:** Sostituire `StopLossRequest` con `TrailingStopOrderRequest(trail_percent=2.0)` nel bracket. 

**Nota:** Trailing stop su Alpaca richiede `OrderClass.OTO` (non BRACKET) per wrapping, oppure ordine separato post-fill. Verificare compatibilità SDK.

---

### P2-C: SSE trade events per fill immediato

**Problema:** Alembic scopre i fill al ciclo successivo (15 min dopo). Con Server-Sent Events, il fill aggiorna Redis immediatamente.

**Implementazione:** Un secondo Celery worker persistente (tipo daemon) che si connette a `/v2/events/trades` e aggiorna `position:{symbol}:last_fill` in Redis.

**Complessità:** Alta — richiede gestione connessione SSE persistente, reconnect logic, e integrazione con il sistema di reconciliazione.

---

### P2-D: WebSocket streaming news (riduzione latenza news→segnale)

**Problema:** Il polling REST news (ogni 15 min) introduce latenza. Con WebSocket streaming, le news arrivano in <1s.

**File da creare:** `src/connectors/alpaca_news_stream.py`

```python
from alpaca.data.live import NewsDataStream

class AlpacaNewsStreamConnector:
    def __init__(self, api_key, secret_key, symbols, on_news_callback):
        self.stream = NewsDataStream(api_key=api_key, secret_key=secret_key)
        self.stream.subscribe_news(on_news_callback, *symbols)
    
    def run(self):
        self.stream.run()
```

**Integrazione:** Celery worker che avvia lo stream e per ogni news chiama `run_sentiment_task.delay(article)`.

---

### P2-E: Xetra EU equities (universe expansion)

**Problema:** 40 simboli EU nel universe Zeygos non sono accessibili su Alpaca US. Alpaca EU Broker supporta Xetra live.

**Requisiti tecnici:**
1. Timezone: Xetra opera 09:00–17:30 CET (8:00–16:30 UTC) — schedule Celery separato
2. Symbol format: Xetra usa simboli locali (SAP.DE) o ISIN
3. API endpoint diverso per EU Broker
4. News coverage: Benzinga/Alpaca ha coverage limitata su titoli EU — potrebbe richiedere sorgente alternativa (es. Reuters, GDELT per EU)

**Sequenza:** Valutare DOPO paper trading US profittevole. Alta complessità architetturale.

---

## P3 — Bassa priorità / uso futuro

### P3-A: MOO/MOC auction orders

**Problema:** Ordini market-on-open (TIF `opg`) garantiscono fill all'asta di apertura. Per segnali overnight, potrebbe migliorare l'esecuzione.

**Implementazione:** Cambiare `time_in_force="day"` in `time_in_force="opg"` per ordini BUY generati dopo le 16:00 ET. Richiede logica per distinguere orario dell'ordine.

**Complessità:** Bassa tecnica, media logica (schedule-aware).

---

### P3-B: Extended hours trading

**Problema:** News ad alto impatto arrivano spesso dopo le 16:00 ET (earnings, FDA, macro). Poter posizionarsi in after-hours riduce il gap.

**Requisiti:** Solo limit orders in extended hours. Richiede pricing logic bid/ask (Snapshot API). Schedule Celery esteso 16:00–20:00 ET.

---

### P3-C: Screener Most Actives per universe dinamico

**API:** `GET /v2/screener/stocks/most-actives` → ritorna top N per volume.

**Utilizzo:** Ogni mattina alle 9:25 ET, fetchare i 20 titoli più attivi e aggiungerli temporaneamente alla watchlist del giorno.

**Trade-off:** Aumenta il segnale ma introduce lookforward bias se non gestito correttamente nel backtest.

---

### P3-D: Crypto (Bitcoin/Ethereum come diversificazione)

**Valutazione:** Alpaca US supporta crypto spot. L'EU Broker (Italia) potrebbe avere limitazioni.

**Pre-requisiti da verificare prima di pianificare:**
1. `GET /v2/assets?asset_class=crypto` sull'account EU — verifica disponibilità
2. Schedule 24/7 — richiede modifiche al Beat scheduler
3. Vol targeting ricalibrato (crypto 3–5× più volatile)
4. News sources crypto (CoinDesk, etc.) non coperte da Benzinga/Alpaca
5. MiCA framework EU — compliance crypto per retail investors italiani

**Status:** Non pianificare fino a verifica disponibilità EU Broker + paper trading equities profittevole.

---

## Sequenza di implementazione raccomandata

```
SPRINT 1 (ora):
  P0-C  adjustment="all"                    ← 5 min, 1 riga
  P0-D  account blocking flags              ← 15 min, 5 righe
  P0-B  market clock pre-flight             ← 30 min, 10 righe
  P0-A  bulk cancel nel kill-switch         ← 45 min, helper function
  P0-E  fill reconciliation Activities API  ← 2h, nuovo task Celery

SPRINT 2 (sessione successiva):
  P1-A  Snapshot API per prezzi freschi     ← 1h
  P1-B  Asset fractionable pre-flight       ← 1h
  P1-D  Portfolio History audit             ← 30 min

SPRINT 3:
  P2-A  Bracket orders                      ← dopo P1-A
  P2-D  WebSocket streaming news            ← worker separato

SPRINT 4:
  P3-D  Crypto (solo se EU Broker lo supporta)
  P2-E  Xetra EU equities
```

---

## File coinvolti

| File | Sezione |
|------|---------|
| `src/workers/portfolio_scheduler.py` | P0-A, P0-B, P0-C, P0-D, P0-E, P1-A, P1-B, P2-A, P2-B |
| `src/store/pg_store.py` | P0-E (aggiungere `update_trade_pnl`) |
| `src/connectors/alpaca_news_stream.py` | P2-D (file nuovo) |
| `src/api/routes/performance.py` | P1-D (audit) |
| `src/workers/celery_app.py` | P0-E (aggiungere beat schedule per reconciliation) |
| `src/config.py` | P2-A (aggiungere TAKE_PROFIT_PCT, STOP_LOSS_PCT) |

---

## Note critiche di sicurezza

- Le credenziali Alpaca NON devono mai essere hardcodate in stringhe bash o test. Sempre `config.ALPACA_API_KEY` da environment variables.
- Tutti i nuovi task Celery devono avere `try/except` con `log.warning` — mai far crashare il ciclo principale per una feature opzionale.
- Il bulk cancel (P0-A) è un'operazione distruttiva: aggiungere log `log.warning("EMERGENCY: cancelling all pending orders")` prima di eseguirlo.
