# Code Review Issues - 2026-06-06

Review focalizzata su superfici operative del progetto: API/auth, frontend/backend contract, execution worker, store PostgreSQL/Redis, configurazione runtime e dati mostrati in dashboard.

## Verifica eseguita

- `npm run build` in `frontend/`: passato.
- `pytest tests/api/test_api.py tests/api/test_trading_routes.py -q`: non eseguito fino ai test perché l'ambiente locale non ha `fastapi` installato (`ModuleNotFoundError: No module named 'fastapi'`).
- Worktree iniziale: `docs/ARCHITECTURE.md` già modificato, non toccato.

## Issue Trovate

### 1. Critical - La pagina Admin usa endpoint kill switch inesistenti o incompatibili

**Evidenza**

- Frontend: `frontend/src/api/admin.ts:9-13` chiama:
  - `GET /api/admin/killswitch`
  - `POST /api/admin/killswitch`
  - `DELETE /api/admin/killswitch`
- Backend: `src/api/routes/admin.py:99-119` espone solo `POST /api/admin/killswitch`.
- La pagina Admin legge `ks?.active` da `fetchKillswitchStatus` in `frontend/src/pages/Admin.tsx:22` e decide se mostrare Activate/Deactivate in `frontend/src/pages/Admin.tsx:44-90`.
- Il `POST` backend ignora il `reason` inviato dal frontend e salva sempre `"manual operator halt via API"` (`src/api/routes/admin.py:117`).
- `RedisStore.get_killswitch_reason()` legge solo `killswitch_reason`, non `system:halted_by_operator_reason` (`src/store/redis_store.py:203-210`), mentre l'halt manuale usa `system:halted_by_operator_reason` (`src/store/redis_store.py:176-181`).

**Impatto**

Il pannello di emergenza non puo' sapere in modo affidabile se il kill switch e' attivo, il pulsante di disattivazione chiama un endpoint non implementato e la reason inserita dall'operatore viene persa. In un sistema di trading questa e' una superficie di sicurezza operativa critica.

**Fix consigliato**

Allineare il contratto:

- aggiungere `GET /api/admin/killswitch` che ritorni `{ active, activated_at, reason }`;
- aggiungere `DELETE /api/admin/killswitch` che chiami sia `deactivate_killswitch()` sia `deactivate_operator_halt()` e imposti un mode coerente;
- modellare il body del `POST` con Pydantic e passare la reason a `activate_operator_halt(reason)`;
- aggiornare test API e test frontend/contract per coprire i tre metodi.

### 2. High - I parametri risk salvati dalla UI non controllano l'execution worker

**Evidenza**

- La pagina Config legge e salva `risk.portfolio_drawdown` e `risk.stop_loss` (`frontend/src/pages/Config.tsx:17-25`), dichiarando che modificano Max Drawdown e Stop Loss (`frontend/src/pages/Config.tsx:40-46`).
- `config/trading.yaml` contiene `risk.portfolio_drawdown: 0.05` e `risk.max_position_pct: 0.10` (`config/trading.yaml:123-131`).
- L'execution worker usa invece costanti hardcoded:
  - `STOP_LOSS_PCT = 0.02`
  - `MAX_DRAWDOWN_PCT = 0.10`
  - `MAX_POSITION_PCT = 0.10`
  in `src/workers/execution.py:47-52`.
- Il drawdown cap usa `MAX_DRAWDOWN_PCT` hardcoded (`src/workers/execution.py:331-338`).
- Lo stop loss usa `STOP_LOSS_PCT` hardcoded (`src/workers/execution.py:371-388`).

**Impatto**

L'operatore puo' credere di aver impostato un drawdown cap al 5% o uno stop loss diverso, mentre il motore continua a usare 10% e 2%. Questo crea una discrepanza pericolosa tra dashboard, configurazione persistita e comportamento reale.

**Fix consigliato**

Centralizzare i parametri risk in un loader unico, validato, e far leggere all'execution worker i valori runtime. Aggiungere un test che modifica `risk.portfolio_drawdown`/`risk.stop_loss` e verifica che `run_execution_cycle()` usi quei valori.

### 3. High - I dati delle strategie esposti dall'API sono incoerenti e in parte generati casualmente

**Evidenza**

- Il file dichiara "accurate data" nel docstring (`src/api/routes/strategies.py:1`), ma l'equity curve S1 e' generata con `random.gauss()` a import time (`src/api/routes/strategies.py:205-219`).
- S3 ha `oos_sharpe: 0.1483` (`src/api/routes/strategies.py:133-141`) e il gate "Significance" dice `OOS Sharpe > 0.5`, ma `passed` e' `True` (`src/api/routes/strategies.py:162-170`).
- S1 walk-forward ha `metric_value: 0.71`, `threshold: 0.8`, ma `passed: True` (`src/api/routes/strategies.py:96-103`).
- La sensitivity S3 e' dichiarata placeholder (`src/api/routes/strategies.py:234-245`).

**Impatto**

La dashboard puo' mostrare validazioni e curve non riproducibili o logicamente contraddittorie. Questo puo' influenzare decisioni operative su strategie live/R&D.

**Fix consigliato**

Rimuovere dati random e placeholder dagli endpoint produttivi. Caricare curve, gate e sensitivity da report versionati o DB; rendere `passed` derivato da metriche/threshold con regole esplicite; aggiungere test di consistenza sui gate.

### 4. Medium - `/api/strategies` e' fuori dal modello auth applicato al resto delle API operative

**Evidenza**

- `src/api/routes/strategies.py:9` crea `APIRouter(prefix="/api/strategies")` senza `Depends(require_api_key)`.
- Endpoint come list/detail/backtest/gates/sensitivity sono pubblici (`src/api/routes/strategies.py:267-319`).
- Altri router operativi proteggono l'intero router, per esempio signals (`src/api/routes/signals.py:14`) e trading (`src/api/routes/trading.py:9`).
- `list_strategies()` chiama `_check_live_data()`, che apre una connessione DB e legge `portfolio_cycles` (`src/api/routes/strategies.py:19-35`).

**Impatto**

Chiunque raggiunga l'API puo' leggere metriche, universi, stato live/backtest delle strategie e puo' generare query DB ripetute. Anche se non e' un write path, e' incoerente con il resto della postura di sicurezza e aumenta la superficie di information disclosure.

**Fix consigliato**

Applicare `dependencies=[Depends(require_api_key)]` anche al router strategies, oppure documentare esplicitamente quali endpoint sono pubblici e rimuovere query live DB dagli endpoint pubblici.

### 5. Medium - News "recent" usa `created_at`, mentre ingestione/retention usano `fetched_at`

**Evidenza**

- `news_log` ha sia `fetched_at` sia `created_at` (`migrations/006_add_news_log.sql:5-15`).
- L'inserimento salva `fetched_at` dal timestamp dell'item (`src/store/pg_store.py:167-170`).
- La retention cancella usando `fetched_at` (`src/store/pg_store.py:1141-1148`).
- `get_news_recent()` pero' seleziona `created_at AS fetched_at` e ordina per `created_at` (`src/store/pg_store.py:550-574`).

**Impatto**

La UI mostra un campo chiamato `fetched_at` che in realta' e' `created_at`, mentre la retention usa un'altra semantica. Articoli vecchi processati oggi possono apparire recenti in UI ma essere candidati alla retention in base al timestamp sorgente, oppure l'ordine della lista puo' non riflettere la data articolo attesa.

**Fix consigliato**

Decidere una semantica unica:

- se `fetched_at` e' "quando l'articolo e' stato processato", salvarlo con `now()` e usare un campo separato per `published_at`;
- se `fetched_at` e' il timestamp sorgente, allora `get_news_recent()` deve selezionare e ordinare per `fetched_at`, non `created_at`.

### 6. Medium - Trade P&L puo' restare NULL per ordini notional o fill non riconciliati entro 24h

**Evidenza**

- `open_trade()` permette `qty=None` (`src/store/pg_store.py:325-345`).
- Il path execution con `price is None` invia un ordine `notional` e lascia `qty=None` (`src/workers/execution.py:482-503`, `src/workers/execution.py:523-532`).
- `close_trade()` calcola `gross_pnl` e `net_pnl` moltiplicando per `qty` (`src/store/pg_store.py:312-320`), quindi con `qty NULL` il P&L resta `NULL`.
- `reconcile_trade_fills()` aggiorna `entry_price` e `qty` solo per trade con `entry_price IS NULL` e `entry_time > now() - '24 hours'::interval` (`src/store/pg_store.py:490-518`).

**Impatto**

Se un trade notional viene chiuso prima della riconciliazione, o se la riconciliazione non gira entro 24 ore, le analytics possono perdere P&L reale. Il problema e' particolarmente insidioso per incidenti operativi: proprio quando un worker salta una finestra, i dati diventano incompleti.

**Fix consigliato**

Salvare sempre una quantita' nota al close usando la posizione Alpaca (`pos.qty`) o il fill dell'ordine di uscita; non limitare la riconciliazione a 24 ore senza una coda di retry; aggiungere un vincolo/test che un trade chiuso non abbia `net_pnl NULL`.

### 7. Low - Il caricamento config usa path relativi al current working directory in piu' punti

**Evidenza**

- Config API: `_CONFIG_PATH = "config/trading.yaml"` e `open(_CONFIG_PATH)` (`src/api/routes/config_routes.py:11-17`).
- Signals API: `open("config/trading.yaml")` (`src/api/routes/signals.py:17-22`).
- Retention worker: `open("config/trading.yaml")` (`src/workers/retention.py:43-48`).

**Impatto**

In Docker funziona perche' il `WORKDIR` e' `/app`, ma esecuzioni locali, test, cron o worker avviati da una directory diversa possono leggere una config sbagliata o cadere sui default. La failure in `signals._watchlist()` e retention e' silenziosa, quindi la diagnosi diventa difficile.

**Fix consigliato**

Usare `Path(__file__).resolve().parents[...] / "config" / "trading.yaml"` o un singolo `ConfigLoader` condiviso. Evitare fallback silenziosi almeno sui worker operativi: loggare warning con path assoluto tentato.

## Note di Copertura

La review non ha potuto eseguire pytest per dipendenze Python mancanti nell'ambiente locale. Prima di chiudere questi finding, conviene eseguire in un ambiente completo:

```bash
pip install -e '.[dev]'
pytest
```

oppure via container, se quello e' il flusso standard del progetto.
