# Prompt 3 — Struttura Moduli e Contratti di Interfaccia

## Contesto del sistema

Sistema Python (monolite modulare) per trading algoritmico basato su LLM. Stack: FastAPI + Celery + Redis + PostgreSQL + QuantConnect Lean. Il codice è un singolo repository progettato per essere decomposto in microservizi in futuro senza riscrittura.

## Componenti e interfacce definite nella spec

### Interfacce astratte

```python
# Connettori dati
class NewsConnector(ABC):
    async def fetch() -> AsyncIterator[NewsItem]

@dataclass
class NewsItem:
    id: str
    source: str
    timestamp: datetime
    title: str
    body: str          # già sanitizzato
    url: str
    language: str      # "en" dopo traduzione
    asset_tags: list[str]

# Client LLM
class LLMClient(ABC):
    async def complete(prompt: str, response_schema: type[BaseModel]) -> BaseModel

# Output worker sentiment
class SentimentResult(BaseModel):
    symbol: str
    polarity: float
    confidence: float
    score: float           # polarity × confidence
    reasoning: str
    source_ids: list[str]
    generated_at: datetime
    model_id: str
    worker_version: str

# Output worker regime
class RegimeResult(BaseModel):
    label: Literal["risk_on", "risk_off", "high_vol", "trending", "ranging", "uncertain"]
    confidence: float
    key_factors: list[str]
    valid_until: datetime
    position_multiplier: float

# Output Alpha Miner
class AlphaCandidate(BaseModel):
    strategy_code: str
    hypothesis: str
    sharpe: float
    max_drawdown: float
    win_rate: float
    status: Literal["candidate", "approved", "rejected"]
    iterations: int
    backtest_period: tuple[date, date]
```

### API FastAPI (Signal Bridge)
```
GET  /api/signals/{symbol}
GET  /api/signals/history
GET  /api/regime
POST /api/admin/mode
POST /api/admin/killswitch
GET  /api/health
```

### Config files
- `connectors.yaml` — definizione connettori news
- `workers.yaml` — configurazione worker Celery
- `trading.yaml` — parametri strategia e risk management

### Struttura moduli proposta (implicita nella spec)
```
src/
├── connectors/       # RSS, NewsAPI, SEC, GDELT, Macro, Email, Telegram
├── llm/              # LLMClient ABC + ClaudeClient, OpenAIClient, GeminiClient
├── workers/          # SentimentWorker, RegimeDetector, AlphaMiner
├── signal_store/     # Redis handler, PostgreSQL handler
├── api/              # FastAPI routes + auth
├── quantconnect/     # LLMSignalData, strategie, risk manager
└── config/           # YAML loaders + Pydantic validation
```

---

## Il tuo compito

Sei un software architect Python con esperienza in sistemi event-driven e fintech. Analizza la struttura proposta e rispondi:

### Parte A — Valutazione struttura moduli

1. La struttura proposta è coesa? Ci sono moduli che stanno facendo troppo o troppo poco?
2. Dove vedi le maggiori probabilità di coupling nascosto (due moduli che si dipendono implicitamente senza che l'interfaccia lo dichiari)?
3. La separazione `signal_store/` come modulo separato è corretta, o dovrebbe essere parte di `workers/`?
4. Il modulo `quantconnect/` conterrà sia le strategie (logica di business) che il data feed (infrastruttura). È un problema? Come lo separeresti?

### Parte B — Contratti di interfaccia mancanti o deboli

Per ogni interfaccia elencata, identifica:
1. **Pre-condizioni mancanti:** cosa deve essere vero prima di chiamare il metodo?
2. **Post-condizioni mancanti:** cosa garantisce il metodo al chiamante?
3. **Errori non dichiarati:** quali eccezioni può lanciare e non sono documentate?
4. **Invarianti:** quali proprietà devono essere sempre vere sull'oggetto?

Concentrati sulle interfacce più critiche: `NewsConnector.fetch()`, `LLMClient.complete()`, `SentimentResult` (come DTO tra worker e signal store).

### Parte C — Proposta struttura alternativa o migliorata

Proponi la struttura di directory che adotteresti, con:
- Nomi di file/modulo per i componenti principali
- Dove vanno i Celery task (definizione vs logica)
- Come gestire la configurazione (un modulo `config/` con Pydantic settings?)
- Come strutturare i test (`tests/` mirror di `src/`? separati per tipo?)
- Dove vivono le migrazioni Alembic

### Parte D — Contratti formali critici

Scrivi le definizioni complete (con type hints, docstring, eccezioni) per:

1. `NewsConnector.fetch()` — includi gestione timeout, retry, e cosa succede se la fonte è irraggiungibile
2. `LLMClient.complete()` — includi gestione rate limit, timeout, e validation dell'output
3. `SignalStore.write(signal: SentimentResult) -> None` — includi atomicità (Redis + PostgreSQL), idempotency, e gestione Redis down

### Parte E — Decomposizione in microservizi

Se in Fase 3 dovessimo estrarre il `SentimentWorker` come microservizio separato:
- Quali dipendenze interne andrebbero risolte?
- Quale sarebbe l'interfaccia di comunicazione ideale (REST, gRPC, message queue)?
- Cosa non si può separare facilmente (coupling strutturale)?

---

## Formato risposta atteso

1. Valutazione struttura con problemi specifici (Parte A)
2. Tabella contratti mancanti per interfaccia critica (Parte B)
3. Struttura directory proposta come albero commentato (Parte C)
4. Codice Python completo per i 3 contratti (Parte D)
5. Piano decomposizione microservizi (Parte E) — max 200 parole
