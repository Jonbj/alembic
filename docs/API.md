# API Reference — LLM Trading System

**FastAPI REST Endpoints**  
**Versione:** 2.0.0  
**Data:** 2026-05-13

---

## Panoramica

Il sistema espone endpoint REST per:
- Consultare segnali di sentiment
- Gestire modalità operativa (admin)
- Attivare kill-switch (admin)
- Consultare performance e pesi

### Base URL

```
Development: http://localhost:8000
Production:  https://api.your-domain.com
```

### Autenticazione

| Endpoint | Auth Required | Header |
|----------|---------------|--------|
| `/api/signals/*` | ❌ No | — |
| `/api/performance/*` | ❌ No | — |
| `/api/weights/*` | ❌ No (GET), ✅ Sì (POST) | `X-API-Key` |
| `/api/admin/*` | ✅ Sì | `X-API-Key` |

### API Key

```bash
# Genera API key (min 32 caratteri)
openssl rand -hex 20

# Usa negli header
curl -H "X-API-Key: tua-api-key-here" ...
```

---

## Signal Endpoints

### GET `/api/signals/{symbol}`

Restituisce l'ultimo segnale di sentiment per un simbolo.

#### Path Parameters

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `symbol` | string | Asset symbol (es. "AAPL", "SPY") |

#### Response 200 OK

```json
{
  "symbol": "AAPL",
  "score": 0.42,
  "confidence": 0.78,
  "reasoning": "Strong bullish sentiment from positive earnings beat",
  "model_id": "ensemble:opus+qwen3.5:cloud+deepseek-v4-pro:cloud",
  "ensemble_std": 0.12,
  "fallback_used": false,
  "generated_at": "2026-05-04T10:30:00Z"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `symbol` | string | Asset symbol |
| `score` | float | Signal score [-1.0, 1.0] (polarity × confidence) |
| `confidence` | float | Confidence [0.0, 1.0] |
| `reasoning` | string | Breve spiegazione del verdict |
| `model_id` | string | Modello o ensemble usato |
| `ensemble_std` | float | Std dev tra modelli (solo ensemble) |
| `fallback_used` | boolean | True se usato FinBERT fallback |
| `generated_at` | datetime | Timestamp generazione segnale |

#### Response 404 Not Found

```json
{
  "detail": "No cached signal found for symbol 'AAPL'"
}
```

#### Esempio

```bash
curl http://localhost:8000/api/signals/AAPL
```

---

### GET `/api/signals/history`

Restituisce lo storico dei segnali per un simbolo (paginato).

#### Query Parameters

| Parametro | Tipo | Default | Descrizione |
|-----------|------|---------|-------------|
| `symbol` | string | — | Asset symbol (required) |
| `limit` | integer | 50 | Max risultati (1-500) |
| `offset` | integer | 0 | Offset per pagination |

#### Response 200 OK

```json
{
  "total": 1250,
  "limit": 50,
  "offset": 0,
  "signals": [
    {
      "symbol": "AAPL",
      "score": 0.42,
      "confidence": 0.78,
      "reasoning": "...",
      "model_id": "ensemble:...",
      "generated_at": "2026-05-04T10:30:00Z"
    },
    ...
  ]
}
```

#### Esempio

```bash
curl "http://localhost:8000/api/signals/history?symbol=AAPL&limit=100&offset=0"
```

---

## Admin Endpoints

### POST `/api/admin/killswitch`

Attiva l'emergency kill-switch per haltare immediatamente il trading.

#### Auth Required

✅ Sì — Header `X-API-Key`

#### Request Body (opzionale)

```json
{
  "reason": "VIX spike > 40"
}
```

#### Response 200 OK

```json
{
  "killswitch": "activated",
  "mode": "halted",
  "activated_at": "2026-05-04T14:30:00Z"
}
```

#### Effetti

1. Imposta `killswitch_active = 1` in Redis
2. Imposta `system:mode = "halted"`
3. Invia alert Telegram critico
4. QuantConnect legge halt e chiude posizioni

#### Esempio

```bash
curl -X POST http://localhost:8000/api/admin/killswitch \
  -H "X-API-Key: tua-api-key" \
  -H "Content-Type: application/json" \
  -d '{"reason": "System drawdown > 5%"}'
```

---

### POST `/api/admin/mode`

Imposta la modalità operativa del sistema.

#### Auth Required

✅ Sì — Header `X-API-Key`

#### Request Body

```json
{
  "mode": "paper"
}
```

| Modalità | Descrizione |
|----------|-------------|
| `backtest` | Solo backtesting, no ordini reali |
| `paper` | Paper trading (simulato) |
| `semi_auto` | Segnali automatici, ordini manuali |
| `full_auto` | Trading fully automatico |
| `halted` | Trading haltato (kill-switch) |

#### Response 200 OK

```json
{
  "mode": "paper",
  "status": "ok",
  "previous_mode": "full_auto"
}
```

#### Response 400 Bad Request

```json
{
  "detail": "Invalid mode. Must be one of: backtest, paper, semi_auto, full_auto, halted"
}
```

#### Esempio

```bash
curl -X POST http://localhost:8000/api/admin/mode \
  -H "X-API-Key: tua-api-key" \
  -H "Content-Type: application/json" \
  -d '{"mode": "semi_auto"}'
```

---

## Performance Endpoints

### GET `/api/performance/latest`

Restituisce l'ultimo performance report calcolato dal PerformanceWorker.

#### Auth Required

❌ No

#### Response 200 OK

```json
{
  "period_start": "2026-04-04",
  "period_end": "2026-05-04",
  "overall_ic": 0.0842,
  "icir": 1.23,
  "hit_rate": 0.58,
  "model_ic": {
    "opus": 0.0756,
    "qwen3.5:cloud": 0.0912,
    "deepseek-v4-pro:cloud": 0.0834
  },
  "model_icir": {
    "opus": 1.15,
    "qwen3.5:cloud": 1.34,
    "deepseek-v4-pro:cloud": 1.21
  },
  "recommended_weights": {
    "opus": 0.30,
    "qwen3.5:cloud": 0.38,
    "deepseek-v4-pro:cloud": 0.32
  },
  "weight_change_applied": false,
  "threshold_analysis": {
    "0.1-0.2": 0.02,
    "0.2-0.3": 0.05,
    "0.3-0.4": 0.08,
    "0.4-0.6": 0.12,
    "0.6-1.0": 0.18
  },
  "threshold_suggestion": 0.4,
  "drift_alerts": [],
  "post_mortems": [],
  "generated_at": "2026-05-04T03:00:00Z",
  "report_version": "1.0.0"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `period_start` | date | Inizio periodo analisi |
| `period_end` | date | Fine periodo analisi |
| `overall_ic` | float | Composite IC complessivo |
| `icir` | float | ICIR (IC / std) con Newey-West HAC |
| `hit_rate` | float | % segnali con segno corretto |
| `model_ic` | object | IC per modello |
| `model_icir` | object | ICIR per modello |
| `recommended_weights` | object | Pesi suggeriti (LOO ICIR) |
| `weight_change_applied` | boolean | True se pesi aggiornati |
| `threshold_analysis` | object | IC per score bucket |
| `threshold_suggestion` | float | Threshold suggerito |
| `drift_alerts` | array | Alert PSI/CUSUM |
| `post_mortems` | array | Analisi drawdown significativi |
| `generated_at` | datetime | Timestamp report |
| `report_version` | string | Versione schema report |

#### Response 404 Not Found

```json
{
  "detail": "No performance report available yet"
}
```

#### Esempio

```bash
curl http://localhost:8000/api/performance/latest
```

---

### GET `/api/weights/current`

Restituisce i pesi ensemble correnti.

#### Auth Required

❌ No

#### Response 200 OK

```json
{
  "weights": {
    "opus": 0.34,
    "qwen3.5:cloud": 0.33,
    "deepseek-v4-pro:cloud": 0.33
  },
  "source": "auto",
  "updated_at": "2026-05-01T04:00:00Z"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `weights` | object | Mappa model_id → weight |
| `source` | string | Origine pesi: `auto_apply`, `telegram`, `suggestion`, `override`, `default` |
| `updated_at` | datetime | Ultimo aggiornamento (non presente nel default) |

#### Default Fallback

Se nessun peso è configurato, ritorna pesi di default:

```json
{
  "weights": {
    "opus": 0.34,
    "qwen35": 0.33,
    "deepseek": 0.33
  },
  "source": "default"
}
```

#### Esempio

```bash
curl http://localhost:8000/api/weights/current
```

---

### GET `/api/weights/suggestion`

Restituisce il suggerimento pesi corrente calcolato da LOO ICIR, se presente.

#### Auth Required

❌ No

#### Response 200 OK

```json
{
  "suggested_weights": {
    "opus": 0.38,
    "qwen3.5:cloud": 0.32,
    "deepseek-v4-pro:cloud": 0.30
  },
  "purified_icir": {
    "opus": 1.15,
    "qwen3.5:cloud": 0.97,
    "deepseek-v4-pro:cloud": 1.08
  },
  "freeze_reason": "VIX = 32.4 >= 30.0",
  "computed_at": "2026-05-12T04:00:12Z",
  "expires_at": "2026-05-19T04:00:12Z"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `suggested_weights` | object | Nuovi pesi proposti (model_id → weight) |
| `purified_icir` | object | ICIR purificato per modello (LOO cross-validation) |
| `freeze_reason` | string | Guardrail che ha bloccato auto-apply (vuoto se nessuno) |
| `computed_at` | datetime | Timestamp calcolo suggerimento |
| `expires_at` | datetime | Scadenza suggerimento (7 giorni da computed_at) |

#### Response 404 Not Found

```json
{
  "detail": "No weight suggestion available"
}
```

#### Esempio

```bash
curl http://localhost:8000/api/weights/suggestion
```

---

### POST `/api/weights/approve`

Approva manualmente e imposta nuovi pesi ensemble.

#### Auth Required

✅ Sì — Header `X-API-Key`

#### Request Body

```json
{
  "override_weights": null,
  "note": "Approvazione manuale post-earnings NVDA"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `override_weights` | object o null | Se null: approva i pesi suggeriti. Se fornito: sovrascrive con pesi custom |
| `note` | string o null | Nota audit opzionale |

**Comportamento con `override_weights`:**
- `null` → approva il suggerimento Redis corrente (source="suggestion")
- Se il suggerimento ha `freeze_reason` e `override_weights` è null → HTTP 403
- `{...}` → forza pesi custom (source="override"); validi anche se guardrail fallito

**Validazione `override_weights`:**
- Ogni peso deve essere in `[0.10, 0.70]` (floor e cap da config)
- I pesi devono sommare esattamente a 1.0 (tolleranza ±0.001)
- Ogni model_id deve essere in MODEL_COSTS

#### Response 200 OK

```json
{
  "applied_weights": {
    "opus": 0.30,
    "qwen3.5:cloud": 0.40,
    "deepseek-v4-pro:cloud": 0.30
  },
  "source": "suggestion",
  "log_id": 42
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `applied_weights` | object | Pesi effettivamente applicati |
| `source` | string | `"suggestion"` (da LOO ICIR) o `"override"` (custom) |
| `log_id` | integer | ID riga PostgreSQL weight_update_log |

#### Response 403 Forbidden (freeze senza override)

```json
{
  "detail": "Weight update frozen: VIX = 32.4 >= 30.0"
}
```

#### Response 404 Not Found (nessun suggerimento)

```json
{
  "detail": "No weight suggestion available"
}
```

#### Response 422 Unprocessable Entity (validazione pesi)

```json
{
  "detail": "Weights must sum to 1.0 (got 0.8500)"
}
```

#### Esempio — approva suggerimento

```bash
curl -X POST http://localhost:8000/api/weights/approve \
  -H "X-API-Key: tua-api-key" \
  -H "Content-Type: application/json" \
  -d '{"override_weights": null}'
```

#### Esempio — forza pesi custom (override freeze)

```bash
curl -X POST http://localhost:8000/api/weights/approve \
  -H "X-API-Key: tua-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "override_weights": {
      "opus": 0.30,
      "qwen3.5:cloud": 0.40,
      "deepseek-v4-pro:cloud": 0.30
    },
    "note": "Override manuale - VIX falso positivo"
  }'
```

---

## Errori

### Error Response Format

Tutti gli errori ritornano un oggetto JSON con campo `detail`:

```json
{
  "detail": "Descrizione dell'errore"
}
```

### Codici di Stato

| Codice | Significato | Quando |
|--------|-------------|--------|
| 200 | OK | Richiesta completata con successo |
| 400 | Bad Request | Parametri invalidi, validazione fallita |
| 401 | Unauthorized | API key mancante o invalida |
| 404 | Not Found | Risorsa non trovata |
| 500 | Internal Server Error | Errore interno del server |

### Esempi di Errori

#### 401 Unauthorized

```json
{
  "detail": "Missing or invalid API key"
}
```

#### 404 Not Found

```json
{
  "detail": "No cached signal found for symbol 'AAPL'"
}
```

#### 400 Bad Request

```json
{
  "detail": "Invalid mode. Must be one of: backtest, paper, semi_auto, full_auto, halted"
}
```

---

## Rate Limiting

| Endpoint | Rate Limit |
|----------|------------|
| `/api/signals/*` | 100 req/min |
| `/api/performance/*` | 10 req/min |
| `/api/weights/*` | 10 req/min |
| `/api/admin/*` | 5 req/min |

**Nota:** I limiti sono per IP. In production, configurare Redis-based rate limiting.

---

## Health Check

### GET `/health`

Verifica lo stato di salute del sistema.

#### Response 200 OK

```json
{
  "status": "healthy",
  "redis": "connected",
  "postgres": "connected",
  "celery": "running",
  "version": "1.0.0"
}
```

#### Response 503 Service Unavailable

```json
{
  "status": "unhealthy",
  "redis": "disconnected",
  "postgres": "connected",
  "celery": "unknown",
  "version": "1.0.0"
}
```

#### Esempio

```bash
curl http://localhost:8000/health
```

---

## OpenAPI Schema

Lo schema OpenAPI completo è disponibile a:

```
http://localhost:8000/openapi.json
```

Per l'interfaccia Swagger UI:

```
http://localhost:8000/docs
```

Per l'interfaccia ReDoc:

```
http://localhost:8000/redoc
```

---

## Client Examples

### Python (httpx)

```python
import httpx

# Get signal
async def get_signal(symbol: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"http://localhost:8000/api/signals/{symbol}")
        resp.raise_for_status()
        return resp.json()

# Activate killswitch
async def activate_killswitch(api_key: str, reason: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:8000/api/admin/killswitch",
            headers={"X-API-Key": api_key},
            json={"reason": reason}
        )
        resp.raise_for_status()
        return resp.json()

# Get performance
async def get_performance() -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get("http://localhost:8000/api/performance/latest")
        resp.raise_for_status()
        return resp.json()
```

### cURL

```bash
# Get signal
curl http://localhost:8000/api/signals/AAPL

# Get performance
curl http://localhost:8000/api/performance/latest

# Activate killswitch
curl -X POST http://localhost:8000/api/admin/killswitch \
  -H "X-API-Key: tua-api-key" \
  -d '{"reason": "VIX spike"}'

# Set mode
curl -X POST http://localhost:8000/api/admin/mode \
  -H "X-API-Key: tua-api-key" \
  -d '{"mode": "paper"}'
```

---

## Changelog

| Versione | Data | Cambiamenti |
|----------|------|-------------|
| 2.0.0 | 2026-05-12 | Aggiunto GET /api/weights/suggestion; aggiornato POST /api/weights/approve (override_weights + source values); corretti source values in GET /api/weights/current |
| 1.0.0 | 2026-05-04 | Initial release |
