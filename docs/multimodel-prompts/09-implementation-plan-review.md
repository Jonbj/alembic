# Prompt 09 — Revisione Piano di Implementazione Fase 1

## Contesto del sistema

Sistema Python di trading algoritmico multi-asset che integra LLM offline (paradigma "Alpha Miner"). I segnali LLM vengono calcolati da Celery workers, scritti in Redis/PostgreSQL, e consumati da QuantConnect Lean via custom `PythonData` feed. Il sistema non chiama mai LLM nel loop critico di esecuzione.

**Stack:** Python 3.11, FastAPI, Celery 5.4, Redis 7, PostgreSQL 16, Pydantic v2, FinBERT, subprocess per Claude CLI, QuantConnect Lean (Python interface)

**Fase corrente:** spec approvata e piano di implementazione scritto. Il piano usa TDD (red → green → commit per ogni task). Questo prompt chiede di revisionare il piano prima che inizi l'implementazione, identificando errori tecnici, test mancanti, e rischi nascosti.

---

## Materiale da revisionare

### Struttura file proposta dal piano

```
src/
├── config.py
├── text/sanitizer.py
├── models/{news,signals,performance}.py
├── connectors/{base,deduplicator,rss,gdelt,sec_edgar}.py
├── llm/{client,opus,qwen35,deepseek,finbert,ensemble}.py
├── store/{redis_store,pg_store}.py
├── api/{main,auth,routes/{signals,admin,performance}}.py
├── workers/{celery_app,sentiment,performance}.py
├── performance/{ic,weights,drift,postmortem,threshold}.py
└── notifications/telegram.py
quantconnect/{signal_data,intraday_strategy}.py
tests/{text,models,connectors,llm,store,api,performance,workers}/
```

---

### Componenti critici da revisionare

**A1 — LLMClient (subprocess Claude CLI)**
```python
class OpusClient(LLMClient):
    model_id = "opus"

    async def complete(self, prompt: str, response_schema: type[T]) -> T:
        loop = asyncio.get_event_loop()
        for attempt in range(self.max_retries + 1):
            result = await loop.run_in_executor(None, self._call_cli, prompt)
            try:
                raw = result.strip()
                start = raw.find("{")
                end = raw.rfind("}") + 1
                if start >= 0 and end > start:
                    raw = raw[start:end]
                return response_schema.model_validate_json(raw)
            except (ValidationError, json.JSONDecodeError, ValueError):
                if attempt == self.max_retries:
                    raise
        raise RuntimeError("Exhausted retries")

    def _call_cli(self, prompt: str) -> str:
        proc = subprocess.run(
            [config.CLAUDE_CLI_PATH, "--model", self.model_id, "--print"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"Claude CLI error: {proc.stderr[:200]}")
        return proc.stdout
```
`Qwen35Client` e `DeepseekClient` sono sottoclassi identiche che cambiano solo `model_id = "qwen3.5:cloud"` e `model_id = "deepseek-v4-pro:cloud"`.

**A2 — EnsembleAggregator**
```python
class EnsembleAggregator:
    def aggregate(self, outputs: list[ModelOutput]) -> AggregatedResult | None:
        eligible = [o for o in outputs if o.confidence >= self.min_confidence]
        if not eligible:
            return None
        std = float(np.std([o.polarity for o in eligible]))
        if std >= self.divergence_threshold:
            return None  # divergence → FinBERT fallback
        total_conf = sum(o.confidence for o in eligible)
        weighted_polarity = sum(o.polarity * o.confidence for o in eligible) / total_conf
        mean_confidence = total_conf / len(eligible)
        best = max(eligible, key=lambda o: o.confidence)
        return AggregatedResult(
            symbol=eligible[0].symbol,
            polarity=max(-1.0, min(1.0, weighted_polarity)),
            confidence=mean_confidence,
            reasoning=best.reasoning,
            model_ids=[o.model_id for o in eligible],
            ensemble_std=std,
        )
```

**A3 — IC composito (B4)**
```python
def composite_ic(scores, returns, confidences) -> float:
    spearman = float(spearmanr(scores, returns).statistic)
    whr = weighted_hit_rate(scores, returns, confidences)
    brier = float(np.mean((np.array(confidences) - (np.array(returns) > 0).astype(float)) ** 2))
    return 0.5 * spearman + 0.3 * whr + 0.2 * (1.0 - brier)

def weighted_hit_rate(scores, returns, confidences) -> float:
    s, r, c = np.array(scores), np.array(returns), np.array(confidences)
    correct = (np.sign(s) == np.sign(r)).astype(float)
    total_conf = c.sum()
    if total_conf == 0:
        return 0.0
    return float((correct * c).sum() / total_conf)
```

**A4 — Leave-one-out ICIR**
```python
def compute_purified_icir(model_signals, forward_returns, confidences,
                           current_weights, window=30, step=5) -> dict[str, float]:
    purified = {}
    for target in model_signals:
        others = [m for m in model_signals if m != target]
        other_weight_sum = sum(current_weights[m] for m in others) or 1.0
        loo_scores = [
            sum(model_signals[m][i] * current_weights[m] / other_weight_sum for m in others)
            for i in range(len(forward_returns))
        ]
        ic_series = []
        for w in range(0, len(loo_scores) - window + 1, step):
            ic_series.append(composite_ic(loo_scores[w:w+window],
                                          forward_returns[w:w+window],
                                          confidences[w:w+window]))
        purified[target] = float(np.mean(ic_series) / (np.std(ic_series) + 1e-8))
    return purified
```

**A5 — Weight update (smoothing + guardrail)**
```python
def compute_new_weights(purified_icir, current_weights, alpha=0.25) -> dict[str, float]:
    raw = {m: max(0.0, icir) for m, icir in purified_icir.items()}
    total = sum(raw.values()) or 1.0
    target = {m: v / total for m, v in raw.items()}
    blended = {m: (1 - alpha) * current_weights[m] + alpha * target[m] for m in target}
    clipped = {m: max(0.10, min(0.70, w)) for m, w in blended.items()}
    clipped = {m: max(current_weights[m]-0.10, min(current_weights[m]+0.10, w))
               for m, w in clipped.items()}
    total = sum(clipped.values())
    return {m: w / total for m, w in clipped.items()}
```

**A6 — PSI + CUSUM + circuit breaker**
```python
def compute_psi(baseline: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    lo, hi = min(baseline.min(), current.min()), max(baseline.max(), current.max())
    if lo == hi:
        return 0.0
    edges = np.linspace(lo, hi, bins + 1)
    exp = np.histogram(baseline, edges)[0] / len(baseline) + 1e-9
    act = np.histogram(current,  edges)[0] / len(current)  + 1e-9
    return float(np.sum((exp - act) * np.log(exp / act)))

def check_drift(baseline_90d, baseline_12m, current,
                psi_yellow=0.10, psi_red=0.25, psi_12m_threshold=0.10) -> DriftLevel:
    psi_90 = compute_psi(baseline_90d, current)
    psi_12 = compute_psi(baseline_12m, current)
    if psi_90 > psi_red and psi_12 > psi_12m_threshold:
        return DriftLevel.RED
    if psi_90 > psi_yellow:
        return DriftLevel.YELLOW
    return DriftLevel.STABLE

def should_freeze_weight_update(ctx: MarketContext) -> tuple[bool, str]:
    if ctx.vix > 40.0 or ctx.vix_1d_change > 0.30:
        return True, "vix_spike"
    if ctx.portfolio_drawdown > 0.05:
        return True, "system_drawdown"
    if ctx.consecutive_negative_ic_days >= 5:
        return True, "ic_negative_run"
    return False, ""
```

**A7 — Post-mortem trigger e diagnosi**
```python
def should_trigger_postmortem(loss_pct: float, score: float, ensemble_std: float) -> bool:
    if loss_pct >= 0.03:
        return True
    if loss_pct >= 0.02 and (abs(score) >= 0.50 or ensemble_std >= 0.30):
        return True
    return False

def diagnose_postmortem(loss_pct, score, confidence, ensemble_std,
                         regime, reasoning, drift_active, news_age_min) -> str:
    if drift_active:             return "model_drift_active"
    if news_age_min > 30.0:      return "news_staleness"
    if confidence < 0.4:         return "low_confidence_passed"
    if ensemble_std >= 0.30:     return "ensemble_divergence_ignored"
    if abs(abs(score) - 0.30) < 0.03:  return "threshold_boundary"
    if regime in ("risk_off", "high_vol") and score > 0:  return "regime_mismatch"
    return "unknown"
```

**A8 — Redis Store**
```python
class RedisStore:
    def write_sentiment(self, result: SentimentResult) -> None:
        key = f"signal:{result.symbol}:sentiment"
        self._r.setex(key, 4 * 3600, result.model_dump_json())

    def activate_killswitch(self) -> None:
        self._r.set("killswitch_active", 1)

    def log_divergence(self, symbol, std, model_scores) -> None:
        entry = json.dumps({"symbol": symbol, "std": std, "scores": model_scores,
                            "ts": datetime.now(timezone.utc).isoformat()})
        self._r.lpush("ensemble:divergence:log", entry)
        self._r.expire("ensemble:divergence:log", 24 * 3600)
```

**A9 — PostgreSQL Store (insert + query for IC)**
```python
_FETCH_FOR_IC = """
    SELECT score, NULL as forward_return, generated_at, model_id, fallback_used
    FROM sentiment_signals
    WHERE symbol = %s
      AND generated_at >= now() - INTERVAL '%s days'
      AND fallback_used = FALSE
    ORDER BY generated_at ASC
"""

def fetch_signals_for_ic(self, symbol: str, days: int) -> list[tuple]:
    with self._conn.cursor() as cur:
        cur.execute(_FETCH_FOR_IC, (symbol, days))
        return cur.fetchall()
```
*(nota: la colonna `forward_return` viene aggiunta dalla migration 002 come ALTER TABLE, non è nella migration 001 originale)*

**A10 — SentimentWorker (loop principale)**
```python
async def process_news_batch(news_items, clients, aggregator, finbert,
                              redis_store, pg_store) -> list[SentimentResult]:
    for item in news_items:
        # staleness check (30 min)
        if datetime.now(timezone.utc) - item.timestamp > timedelta(minutes=30):
            continue

        symbol = item.asset_tags[0] if item.asset_tags else "UNKNOWN"
        prompt = _DK_COT_PROMPT.format(text=item.body[:2000], symbol=symbol)

        tasks = [client.complete(prompt, LLMSentimentOutput) for client in clients]
        raw_outputs = []
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            try:
                out = await coro
                raw_outputs.append(ModelOutput(symbol=symbol, polarity=out.polarity,
                    confidence=out.confidence, reasoning=out.reasoning,
                    model_id=clients[i].model_id))
            except Exception as e:
                log.warning("Client %d failed: %s", i, e)

        aggregated = aggregator.aggregate(raw_outputs) if raw_outputs else None
        # ... [FinBERT fallback, write to Redis + PG]
```

**A11 — FastAPI main (app + lifespan + dependency injection)**
```python
_redis_client: Redis | None = None

def get_redis_store() -> RedisStore:
    return RedisStore(_redis_client)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_client
    _redis_client = Redis.from_url(config.REDIS_URL)
    yield
    _redis_client.close()

app = FastAPI(title="LLM Trading Signal API", lifespan=lifespan)
```

**A12 — LLMSignalData (QuantConnect custom feed)**
```python
class LLMSignalData(PythonData):
    def Reader(self, config, line, date, isLive):
        data = json.loads(line)
        signal = LLMSignalData()
        signal.Time = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
        signal.Value = float(data.get("score", 0.0))
        signal["sentiment_score"]   = float(data.get("score", 0.0))
        signal["regime_multiplier"] = float(data.get("regime_multiplier", 1.0))
        signal["confidence"]        = float(data.get("confidence", 0.0))
        return signal

    @staticmethod
    def is_fresh(signal, algorithm_time) -> bool:
        gen_at = datetime.fromisoformat(signal["generated_at"].replace("Z", "+00:00"))
        age_min = (algorithm_time - gen_at).total_seconds() / 60
        return age_min <= 30
```

---

## Il tuo compito

Sei un senior Python engineer con esperienza in sistemi distribuiti, quantitative finance, e TDD. Analizza il piano di implementazione riportato sopra e rispondi alle domande seguenti.

### Parte A — Correttezza tecnica del codice

1. **LLMClient subprocess (A1):** `asyncio.as_completed` itera sui futures ma usa `clients[i]` per recuperare il `model_id` — questo è corretto? Cosa succede se i future completano in ordine diverso dall'ordine di creazione? Come correggeresti per associare correttamente output → client → model_id?

2. **Parsing JSON da Claude CLI (A1):** il piano estrae JSON dalla risposta cercando il primo `{` e l'ultimo `}`. Quali casi patologici possono far fallire questo approccio? (es. JSON annidati con `{}`, risposta con testo prima e dopo, JSON malformato con un singolo `}` finale in più) Proponi un parsing più robusto.

3. **EnsembleAggregator (A2):** se tutti i modelli tranne uno vengono esclusi per bassa confidence, `std` viene calcolata su un solo valore → `std = 0.0` → consensus sempre valido. È il comportamento desiderato? Un solo modello eligible dovrebbe essere considerato ensemble valido o dovrebbe fallare al FinBERT?

4. **IC composito — weighted_hit_rate (A3):** `np.sign(0.0) == np.sign(0.0)` restituisce `True` in NumPy, ma uno score di 0.0 non esprime una direzione. Questo bias il hit_rate verso l'alto quando ci sono molti score vicino a zero? Come correggeresti?

5. **Leave-one-out ICIR (A4):** la normalizzazione dei pesi degli "altri" modelli usa `other_weight_sum = sum(current_weights[m] for m in others)`. Se il sistema ha 3 modelli e uno viene escluso, i pesi rimanenti non sommano a 1 — questo distorce il LOO score. Come dovresti normalizzare correttamente?

6. **compute_new_weights e modelli con tutti ICIR negativi (A5):** se tutti e 3 i modelli hanno `purified_icir < 0`, `raw` è tutto zero → `total = 1.0` → `target` è tutto zero → il blending porta i pesi verso zero → dopo il clipping al floor 10% i pesi sono tutti 10%, normalizzati a ~33%. Questo è il comportamento corretto? Documenta esplicitamente questo corner case.

7. **PSI con distribuzione degenere (A6):** se `baseline` e `current` hanno lo stesso valore (es. tutti 0.5 dopo il flash crash), `lo == hi` e la funzione restituisce 0.0 (stabile). È corretto? Una distribuzione collassata su un punto è un segnale di allarme, non di stabilità.

8. **_FETCH_FOR_IC — SQL injection (A9):** `INTERVAL '%s days'` usa l'interpolazione Python, non un parametro psycopg2. Questo espone a SQL injection. Come correggeresti? (hint: `INTERVAL %s * INTERVAL '1 day'` non funziona direttamente — considera `now() - (%s || ' days')::interval` o usare `timedelta` in Python)

9. **FastAPI global mutable state (A11):** `_redis_client` è una variabile globale a livello di modulo. Quali problemi crea questo durante i test (quando `lifespan` non viene eseguito)? Il piano usa `app.dependency_overrides` nei test — questo funziona correttamente con il pattern attuale?

10. **LLMSignalData freshness check (A12):** `is_fresh` usa `algorithm_time` (il tempo di QuantConnect, che durante il backtest è nel passato) per confrontare con `generated_at` (timestamp reale del segnale). Durante il backtest questo confronto non funziona — ogni segnale risulterebbe "stale" se il backtest usa dati storici. Come dovresti gestire la freshness check in modalità backtest vs live?

---

### Parte B — Qualità e completezza dei test

Il piano include test per ogni componente. Analizza la suite di test proposta e rispondi:

1. **Test async con `asyncio.as_completed` (Task 13):** il test di `process_news_batch` usa `AsyncMock` per i clients. Tuttavia il codice usa `asyncio.as_completed(tasks)` dove `tasks` sono coroutine, non futures. `AsyncMock.complete()` restituisce un `MagicMock` sincrono — il test passa o fallisce? Come struttureresti correttamente il mock?

2. **Test Redis con mock (Task 8):** i test usano `MagicMock` per Redis. Identifica 3 edge case che i mock non possono catturare e che richiederebbero un test di integrazione con Redis reale.

3. **Test IC (Task 16):** il test `test_composite_ic_random_returns_near_zero` usa `assert abs(ic) < 0.3` per 100 campioni random con seed 42. Questo test può fallire su altre piattaforme o versioni di NumPy? Come renderlo deterministico in modo più robusto?

4. **Test mancanti critici:** identifica i componenti per cui il piano non ha test e che consideri rischiosi:
   - Staleness filter in `process_news_batch` — c'è un test esplicito?
   - Il comportamento di `compute_new_weights` quando un modello non appare in `purified_icir` (chiave mancante)?
   - Il comportamento di `RedisStore.read_sentiment` quando il JSON in Redis è corrotto?
   - Il comportamento di `LLMSignalData.Reader` quando `line` è un JSON valido ma mancano campi attesi?

5. **Test di integrazione assenti:** il piano non include un test end-to-end del flusso completo (news → sentiment → Redis → API → QC). Proponi il minimo test di integrazione che verificherebbe il path critico, utilizzando Docker Compose come ambiente di test.

---

### Parte C — Problemi architetturali e di sistema

1. **Connection pooling PostgreSQL:** il piano usa `psycopg2.connect(config.DATABASE_URL)` direttamente nei Celery task (`run_sentiment_worker`, `run_daily_report`, ecc.). Ogni invocazione Celery apre una nuova connessione senza pool. Con 4 worker × 10 task/min, questo può esaurire le connessioni PostgreSQL. Proponi una strategia di connection pooling compatibile con Celery.

2. **Celery task idempotency:** i Celery task `run_sentiment_worker` e `run_daily_report` non sono idempotenti — se eseguiti due volte (retry su failure), producono dati duplicati. Come garantire l'idempotency? (hint: considera idempotency key su `sentiment_signals` o `performance_metrics`)

3. **Race condition Redis:** due invocazioni parallele di `run_sentiment_worker` (es. retry + nuovo task) possono scrivere lo stesso simbolo in Redis quasi simultaneamente. La seconda scrittura sovrascrive la prima silenziosamente. È un problema? In che scenario causa danni reali?

4. **FinBERT lazy loading in Celery worker:** `FinBERTClient._get_pipeline()` carica il modello transformer la prima volta che viene chiamato. In un Celery worker con `concurrency=4`, il modello viene caricato 4 volte (una per processo). Con FinBERT (~400MB), questo consuma ~1.6GB di RAM. Come ottimizzeresti? (considera `prefork` vs `gevent` per Celery, o un worker separato dedicato per FinBERT)

5. **Budget LLM non implementato:** il piano non implementa il controllo del budget giornaliero LLM (`LLM_DAILY_BUDGET_USD` è in config ma non viene usato nei client). La spec richiede blocco chiamate + fallback completo FinBERT quando il budget è esaurito. In quale file e con quale meccanismo implementeresti il contatore?

6. **Consecutive fallback counter:** la spec richiede "3 consensus fallback consecutivi → Alert Telegram + QC sizing ×0.5". Il piano non implementa questo contatore. Dove vivrebbe questo stato? (Redis key? Celery task state?) Come verrebbe resetato?

---

### Parte D — Sicurezza e robustezza

1. **subprocess injection (A1):** `subprocess.run([config.CLAUDE_CLI_PATH, "--model", self.model_id, "--print"], input=prompt, ...)` — il `prompt` contiene testo da news esterne. Anche se il prompt arriva come stdin (non come argomento), ci sono rischi di injection nel CLI? Il `model_id` può essere manipolato da variabili d'ambiente? Valuta il rischio.

2. **API Key in environment (config.py):** il piano usa `os.environ["ADMIN_API_KEY"]` — se la variabile non è settata, il server crasha all'avvio. Questo è il comportamento corretto (fail-fast) o preferiresti una gestione più esplicita? Proponi un pattern di validazione delle variabili d'ambiente obbligatorie all'avvio.

3. **audit_log — colonna `action` duplicata:** nello schema SQL del piano (migration 001), la tabella `audit_log` ha la colonna `action` definita due volte:
   ```sql
   action VARCHAR(50),   -- prima definizione
   ...
   action audit_action_enum NOT NULL   -- seconda definizione
   ```
   Questo causa un errore SQL. Qual è la definizione corretta?

4. **Telegram bot token exposure:** `format_performance_report` costruisce un messaggio che include `PSI_90gg=0.13` e pesi dei modelli — queste informazioni possono essere sensibili se il canale Telegram non è privato. Il piano non menziona alcun controllo sull'accesso al canale. È un rischio operativo reale?

---

### Parte E — Performance e scalabilità Fase 1

Il sistema in Fase 1 gestisce equity USA + ETF (stime):
- ~50 simboli monitorati
- ~200 news/ora durante orario di mercato
- ~10 segnali/simbolo/giorno
- Celery beat ogni 15 minuti → 4-5 invocazioni/ora
- Batch di 10 news per invocazione

1. **Stima latenza ensemble:** ogni news item richiede 3 chiamate Claude CLI parallele via subprocess. Latenza tipica Claude CLI: 3-8 secondi per chiamata. Con `asyncio.as_completed` e executor pool il bottleneck è la latenza massima del batch (≈ max dei 3). Quanto tempo ci vuole per elaborare un batch di 10 news? È compatibile con l'intervallo di 15 minuti?

2. **`asyncio.as_completed` con run_in_executor:** `asyncio.as_completed` non funziona direttamente su coroutine — funziona su futures. Nel codice del piano, `tasks = [client.complete(prompt, ...) for client in clients]` restituisce coroutine, non futures. `asyncio.as_completed` le converte internamente in tasks — ma poi `for i, coro in enumerate(asyncio.as_completed(tasks))` usa `i` come indice del client, che **non corrisponde** all'ordine di completamento. Questo è un bug confermato. Proponi il fix corretto.

3. **PostgreSQL BRIN index per backtest:** il piano crea `CREATE INDEX idx_sentiment_time_brin ON sentiment_signals USING BRIN (generated_at)`. Un BRIN index è efficiente per range scan su tabelle grandi ma non per query frequenti su tabelle piccole (< 100k righe). In Fase 1 con ~500 segnali/giorno, quando diventa utile il BRIN rispetto a un B-tree standard?

---

### Parte F — Gap tra spec e piano

Confronta il piano con la spec originale e identifica:

1. **Componenti nella spec non presenti nel piano:**
   - La spec menziona `semantic cache su Redis` per "stessa notizia riformulata → risposta cached" — il piano non la implementa. È un NICE-TO-HAVE o bloccante per Fase 1?
   - La spec menziona il contatore "3 consensus fallback consecutivi → alert + QC sizing ×0.5" — manca nel piano. Aggiungi il task mancante.
   - La spec richiede `GET /api/signals/history` (per QC backtest) — il piano implementa solo `GET /api/signals/{symbol}` (live Redis). Come implementeresti la route history che legge da PostgreSQL?
   - Il kill-switch deve anche "Celery workers: stop accettazione nuovi job" (step 5 nella spec). Il piano attiva il kill-switch Redis e imposta mode=halted, ma non fa revocare i task Celery in-flight. Come implementeresti lo stop dei worker?

2. **Comportamenti impliciti non testati:**
   - Cosa succede quando `RedisStore.write_sentiment` viene chiamato durante il kill-switch attivo? (la spec non lo specifica — il worker deve smettere di scrivere o continuare?)
   - Cosa succede se PostgreSQL non è raggiungibile all'avvio del Celery worker? (il piano non ha retry logic per la connessione)
   - Cosa succede se `config.DATABASE_URL` non è settato? (crash al primo import? o solo al primo uso?)

3. **Configurazione YAML non letta:** il piano crea `config/workers.yaml` e `config/trading.yaml` ma nessun codice li legge — tutti i parametri sono hardcoded nel codice (`min_confidence=0.4`, `window=30`, ecc.). Proponi il design di un `ConfigLoader` che legga questi YAML e li esponga come oggetti Pydantic, integrandosi con `src/config.py`.

---

## Formato risposta atteso

1. **Parte A — Bug confermati:** lista numerata dei bug trovati (A1-A12), per ognuno: bug confermato sì/no, spiegazione, fix proposto con codice corretto
2. **Parte B — Test gaps:** lista test mancanti critici con codice pytest per ognuno
3. **Parte C — Problemi architetturali:** per ogni punto (C1-C6), soluzione raccomandata con codice o pseudocodice
4. **Parte D — Sicurezza:** valutazione rischio (alto/medio/basso) + fix per ogni punto
5. **Parte E — Performance:** risposta quantitativa con calcoli per E1 e E2; raccomandazione per E3
6. **Parte F — Gap spec/piano:** lista gap prioritizzati (bloccante/importante/nice-to-have) + task aggiuntivi da aggiungere al piano
7. **Raccomandazione finale:** il piano è implementabile così com'è o ci sono blockers critici da risolvere prima? Elenca max 5 fix prioritari da applicare subito.
