# RegimeDetector — Design Spec

**Data:** 2026-05-05
**Status:** Approved
**Feature:** Feature A — RegimeDetector con 2 LLM paralleli su dati macro

---

## 1. Contesto

Il sistema di trading legge `qc:sizing_multiplier` da Redis ad ogni tick per scalare le posizioni in QuantConnect. Attualmente il moltiplicatore è fisso a 1.0, salvo quando il circuit breaker dei fallback lo porta a 0.5 per 24h.

Il RegimeDetector aggiunge una classificazione macro giornaliera (bull / sideways / bear / high_vol) che aggiorna il moltiplicatore in base al contesto di mercato. Gli LLM vengono chiamati **offline** (Celery beat pre-market), mai nel loop di esecuzione.

---

## 2. Architettura e Flusso Dati

```
Celery beat (07:00 UTC, ogni giorno feriale)
  └─► detect_regime()
        │
        ├─► macro.py
        │     ├─ fetch_vix_from_fred()        FRED: VIXCLS
        │     ├─ fetch_yield_curve()           FRED: T10Y2Y
        │     └─ fetch_spy_momentum_20d()      yfinance: SPY 1 mese
        │
        ├─► 2× LLM in parallelo (asyncio.gather)
        │     ├─ LLM-1 → RegimeOutput {regime, confidence, reasoning, data_quality, regime_secondary}
        │     └─ LLM-2 → RegimeOutput {regime, confidence, reasoning, data_quality, regime_secondary}
        │
        ├─► consensus
        │     ├─ accordo          → usa quel regime
        │     └─ disaccordo       → multiplier minore dei due + Telegram ⚠️
        │
        └─► Redis
              ├─ regime:current          TTL 25h — RegimeState JSON
              └─ qc:sizing_multiplier    TTL 25h — float string

QuantConnect (ogni tick):
  redis.GET qc:sizing_multiplier  →  scala position size
```

`detect_regime` può essere triggerato anche standalone (shell, test) senza dover passare dal beat.

---

## 3. Regimi e Moltiplicatori

| Regime | Moltiplicatore | Contesto tipico |
|--------|---------------|-----------------|
| `bull` | ×1.0 | VIX basso, yield curve normale/positiva, SPY in uptrend |
| `sideways` | ×0.7 | VIX moderato, mercato laterale, segnali macro misti |
| `bear` | ×0.4 | VIX elevato, yield curve invertita, SPY in downtrend |
| `high_vol` | ×0.2 | VIX > 30, spike estremo, crisi in corso |

I valori sono configurabili via env vars (vedi sezione 7). Il kill-switch esistente (`vix_spike: 40.0` in `trading.yaml`) rimane attivo e indipendente.

---

## 4. Prompt LLM

Risultato dell'analisi multi-modello (6 modelli consultati). Prompt in inglese per migliore qualità sul dominio finanziario.

```
You are a buy-side macro strategist. Analyze the following market data and classify
the current regime into one of: bull, sideways, bear, high_vol.

Market Data:
- VIX: {vix:.1f}  (CBOE Volatility Index)
- Yield Curve (10Y-2Y spread): {yield_curve:.2f}%  (negative = inverted)
- SPY 20d momentum: {spy_momentum:+.1f}%

Quantitative Guidelines (use as anchors, not rigid rules):
- VIX > 30 → high_vol candidate
- T10Y2Y < -0.5% → recession signal (bear)
- SPY 20d < -8% → risk-off (bear)
- SPY 20d in [-3%, +3%] + VIX < 25 → sideways candidate

Reasoning (2 steps max):
1. Classify each signal as bullish/bearish/neutral
2. Synthesize with priority: high_vol > bear > sideways > bull
   Note any signal interactions that justify overriding guidelines.

Output ONLY valid JSON:
{
  "regime": "bull"|"sideways"|"bear"|"high_vol",
  "confidence": <float 0.0-1.0>,
  "reasoning": "<one sentence on macro picture>",
  "data_quality": "complete"|"partial",
  "regime_secondary": "<optional: second-most-likely regime or null>"
}

Few-shot Examples:

Example 1 (high_vol):
VIX=38, T10Y2Y=-0.8%, SPY=-12%
→ {"regime": "high_vol", "confidence": 0.92, "reasoning": "Extreme volatility with inverted curve and sharp selloff indicates panic regime", "data_quality": "complete"}

Example 2 (sideways):
VIX=16, T10Y2Y=+0.4%, SPY=+1.2%
→ {"regime": "sideways", "confidence": 0.68, "reasoning": "Low volatility and flat momentum suggest range-bound consolidation", "data_quality": "complete", "regime_secondary": "bull"}

Example 3 (bear):
VIX=24, T10Y2Y=-0.6%, SPY=-7%
→ {"regime": "bear", "confidence": 0.78, "reasoning": "Inverted yield curve and negative momentum with elevated volatility", "data_quality": "complete"}
```

**Gestione `data_quality: "partial"`**: se uno o entrambi gli LLM restituiscono `data_quality: "partial"`, il task non aggiorna Redis e invia Telegram ⚠️ "dati macro incompleti — regime invariato".

**`regime_secondary`**: salvato in `RegimeState` per audit, non influenza il moltiplicatore.

---

## 5. Consensus Logic

```
r1, r2 = risultati dei 2 LLM (None se il modello ha fallito)

CASO 1 — entrambi falliscono:
    → nessuna modifica Redis, Telegram 🚨, return

CASO 2 — uno solo fallisce:
    → usa l'output dell'altro, disagreement=False

CASO 3 — entrambi ok, data_quality "partial" in almeno uno:
    → nessuna modifica Redis, Telegram ⚠️ "dati macro incompleti", return

CASO 4 — entrambi ok, accordo (r1.regime == r2.regime):
    → regime = r1.regime, disagreement=False

CASO 5 — entrambi ok, disaccordo:
    → regime = argmin(MULTIPLIERS[r1.regime], MULTIPLIERS[r2.regime])
    → disagreement=True
    → Telegram ⚠️ "Disaccordo LLM: {r1.regime} vs {r2.regime} → applico {regime}"
```

**Fail-safe:** dato mancante o LLM crash = nessuna modifica al moltiplicatore. Non degradare mai verso un multiplier più alto in caso di incertezza.

**Fail-safe:** dato mancante o LLM crash = nessuna modifica al moltiplicatore. Non degradare mai verso un multiplier più alto in caso di incertezza.

---

## 6. Modelli Pydantic — `src/models/regime.py`

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

# Default multipliers — il worker legge i valori effettivi da config (REGIME_MULTIPLIER_*)
# Questa costante serve solo come fallback e per i test unitari dei modelli
REGIME_DEFAULTS: dict[str, float] = {
    "bull": 1.0,
    "sideways": 0.7,
    "bear": 0.4,
    "high_vol": 0.2,
}

RegimeLabel = Literal["bull", "sideways", "bear", "high_vol"]

class RegimeOutput(BaseModel):
    """Output di un singolo LLM."""
    regime: RegimeLabel
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str
    data_quality: Literal["complete", "partial"] = "complete"
    regime_secondary: RegimeLabel | None = None

class MacroSnapshot(BaseModel):
    """Dati macro al momento della detection."""
    vix: float
    yield_curve: float
    spy_momentum_20d: float

class RegimeState(BaseModel):
    """Stato regime persistito in Redis."""
    regime: RegimeLabel
    multiplier: float
    macro_snapshot: MacroSnapshot
    llm_outputs: list[dict]
    disagreement: bool = False
    detected_at: datetime
```

---

## 7. Configurazione — `src/config.py`

```python
# Regime detection
REGIME_LLM_MODEL_1: str = Field(default_factory=lambda: os.environ.get("REGIME_LLM_MODEL_1", "claude-opus-4-7"))
REGIME_LLM_MODEL_2: str = Field(default_factory=lambda: os.environ.get("REGIME_LLM_MODEL_2", "gpt-4o"))
REGIME_MULTIPLIER_BULL: float = Field(default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_BULL", "1.0")))
REGIME_MULTIPLIER_SIDEWAYS: float = Field(default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_SIDEWAYS", "0.7")))
REGIME_MULTIPLIER_BEAR: float = Field(default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_BEAR", "0.4")))
REGIME_MULTIPLIER_HIGH_VOL: float = Field(default_factory=lambda: float(os.environ.get("REGIME_MULTIPLIER_HIGH_VOL", "0.2")))
REGIME_REDIS_TTL_SECONDS: int = Field(default_factory=lambda: int(os.environ.get("REGIME_REDIS_TTL_SECONDS", "90000")))  # 25h
```

`config/workers.yaml` riceve il blocco documentativo:
```yaml
regime:
  schedule: "0 7 * * 1-5"     # 07:00 UTC, lun-ven
  llm_model_1: claude-opus-4-7
  llm_model_2: gpt-4o
  multipliers:
    bull: 1.0
    sideways: 0.7
    bear: 0.4
    high_vol: 0.2
```

---

## 8. Redis — `src/store/redis_store.py`

Nuovi metodi:

```python
def set_regime(self, state: RegimeState, ttl: int) -> None:
    """Persiste RegimeState in Redis."""
    self._r.setex("regime:current", ttl, state.model_dump_json())

def get_regime(self) -> RegimeState | None:
    """Legge RegimeState da Redis. Ritorna None se assente o corrotto."""
    raw = self._r.get("regime:current")
    if raw is None:
        return None
    try:
        return RegimeState.model_validate_json(raw)
    except Exception:
        return None

def set_qc_sizing_multiplier(self, value: float, ttl: int) -> None:
    """Scrive qc:sizing_multiplier con TTL."""
    self._r.setex("qc:sizing_multiplier", ttl, str(value))
```

---

## 9. Notifiche Telegram — `src/notifications/telegram.py`

Nuova funzione `format_regime_message()`:

| Scenario | Notifica |
|----------|----------|
| Regime **cambiato** | `📊 Regime: BULL → BEAR (×0.4)\nVIX: 28.4 \| T10Y2Y: -0.6% \| SPY 20d: -7.1%\nReasoning: <testo LLM>` |
| Regime **invariato** | Nessuna notifica |
| Disaccordo LLM | `⚠️ Disaccordo LLM: bull vs bear → applico bear (×0.4)` (aggiunto alla notifica principale) |
| Dati parziali | `⚠️ RegimeDetector: dati macro incompleti — regime invariato` |
| Entrambi LLM falliscono | `🚨 RegimeDetector fallito — regime invariato. Controllare i log.` |

---

## 10. File Coinvolti

| File | Azione | Descrizione |
|------|--------|-------------|
| `src/connectors/macro.py` | Modifica | Aggiunge `fetch_yield_curve()` + `fetch_spy_momentum_20d()` |
| `src/models/regime.py` | Crea | `RegimeOutput`, `MacroSnapshot`, `RegimeState`, `MULTIPLIERS` |
| `src/workers/regime.py` | Crea | `detect_regime()` Celery task + `_build_macro_context()` helper |
| `src/store/redis_store.py` | Modifica | Aggiunge `set_regime()`, `get_regime()`, `set_qc_sizing_multiplier()` |
| `src/notifications/telegram.py` | Modifica | Aggiunge `format_regime_message()` |
| `src/config.py` | Modifica | Aggiunge `REGIME_*` fields |
| `config/workers.yaml` | Modifica | Aggiunge blocco `regime:` documentativo |
| `tests/connectors/test_macro.py` | Modifica | Aggiunge test per `fetch_yield_curve()` + `fetch_spy_momentum_20d()` |
| `tests/models/test_regime.py` | Crea | Test per `RegimeOutput`, `RegimeState`, `MULTIPLIERS` |
| `tests/workers/test_regime_worker.py` | Crea | `TestDetectRegime` — 7 scenari |
| `tests/test_redis_store.py` | Modifica | Aggiunge test per i 3 nuovi metodi Redis |
| `tests/notifications/test_telegram.py` | Modifica | Aggiunge test per `format_regime_message()` |

---

## 11. Test Coverage Richiesta

`TestDetectRegime` deve coprire:

1. Tutti i segnali ok, accordo LLM → regime applicato, multiplier scritto in Redis, Telegram se regime cambiato
2. Disaccordo LLM → multiplier conservativo (minore), `disagreement=True`, Telegram ⚠️
3. LLM-1 fallisce (timeout/parse error) → usa LLM-2, regime applicato normalmente
4. Entrambi LLM falliscono → Redis invariato, Telegram 🚨
5. `data_quality: "partial"` da almeno un LLM → Redis invariato, Telegram ⚠️
6. Regime invariato rispetto al precedente → nessun Telegram (silenzioso)
7. Primo avvio (nessun regime in Redis) → regime applicato senza confronto, Telegram inviato

---

## 12. Vincoli Non Negoziabili

- Gli LLM non vengono mai chiamati nel loop di esecuzione QC — solo nel Celery task pre-market.
- Fail-safe: dato mancante, parse error, o `data_quality: "partial"` = regime invariato, mai upgrade del multiplier in caso di incertezza.
- Il task è idempotente: se triggerato due volte con gli stessi dati, il secondo run trova il regime invariato e non invia Telegram (silenzioso).
- `qc:sizing_multiplier` e `regime:current` hanno lo stesso TTL (25h) per garantire coerenza.
- I moltiplicatori della tabella in sezione 3 sono i valori di default; le env vars li sovrascrivono senza deploy.
