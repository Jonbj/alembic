# Telegram Approval Flow — Design Spec

**Data:** 2026-05-05
**Status:** Approved
**Feature:** Feature C — Telegram inline keyboard per approvare/rifiutare weight suggestions

---

## 1. Contesto

Quando il performance worker calcola nuovi pesi e i guardrail bloccano l'auto-apply, viene inviata una notifica Telegram che termina con `"👉 Approva manualmente: POST /api/weights/approve"`. L'operatore deve aprire un terminale e fare una chiamata HTTP con l'API key.

La Feature C elimina questo friction: il messaggio di freeze include due bottoni inline (`✅ Approva` / `❌ Rifiuta`) direttamente cliccabili in Telegram. Un Celery task polling riceve i tap e applica o cancella la suggestion.

**Scope:** i bottoni compaiono **solo** sul messaggio di freeze (guardrail bloccato). Il messaggio di auto-apply riuscito resta invariato (nessuna azione richiesta).

---

## 2. Architettura e Flusso Dati

```
Performance worker (Celery)
  └─► guardrail bloccato
        └─► TelegramNotifier.send_message_with_keyboard()
              ├─ testo freeze (invariato)
              └─ InlineKeyboardMarkup
                   ├─ ✅ Approva  callback_data: "approve:<token>"
                   └─ ❌ Rifiuta  callback_data: "reject:<token>"

Celery beat (ogni 5s, lun-dom)
  └─► poll_telegram_updates()        ← src/workers/telegram_poller.py
        │
        ├─► GET /getUpdates (offset da Redis: telegram:update_offset)
        ├─► filtra callback_query
        ├─► verifica user_id in TELEGRAM_ALLOWED_USER_IDS
        ├─► verifica token == sha256(suggestion.computed_at)[:8]
        │
        ├─► APPROVA
        │     ├─ RedisStore.set_ensemble_weights(weights, source="telegram")
        │     ├─ RedisStore.delete_weight_suggestion()
        │     ├─ PgStore.log_weight_update(source="telegram", applied_weights=weights, ...)
        │     ├─ answerCallbackQuery("✅ Pesi applicati")
        │     └─ editMessageReplyMarkup (rimuove keyboard)
        │
        └─► RIFIUTA
              ├─ RedisStore.delete_weight_suggestion()
              ├─ PgStore.log_weight_update(source="rejected_via_telegram", applied_weights={}, ...)
              ├─ answerCallbackQuery("❌ Suggestion rifiutata")
              └─ editMessageReplyMarkup (rimuove keyboard)
```

---

## 3. Token Anti-Replay

`callback_data` = `"approve:<token>"` o `"reject:<token>"`

`token = sha256(suggestion["computed_at"].encode())[:8]` (hex)

Al momento del callback, il poller:
1. Legge la suggestion corrente da Redis
2. Se `None` → suggestion scaduta/già processata → `answerCallbackQuery("Già processata")`
3. Calcola il token atteso dalla suggestion corrente
4. Se token non corrisponde → stessa risposta silenziosa
5. Solo se corrisponde → esegue l'azione

Questo previene:
- Tap su bottoni di messaggi vecchi (suggestion sostituita da nuovo run)
- Double-tap: dopo il primo tap la suggestion viene cancellata, il secondo tap trova `None`

---

## 4. Configurazione — `src/config.py`

```python
TELEGRAM_ALLOWED_USER_IDS: list[str] = Field(
    default_factory=lambda: [
        uid.strip()
        for uid in os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
        if uid.strip()
    ]
)
```

Se `TELEGRAM_ALLOWED_USER_IDS` è vuota, il poller salta il processing dei callback (nessun bottone funzionante). Il task continua a girare e aggiornare l'offset — in questo modo non si accumula un backlog di update non letti.

---

## 5. TelegramNotifier — Nuovi Metodi (`src/notifications/telegram.py`)

```python
async def send_message_with_keyboard(
    self,
    message: str,
    keyboard: list[list[dict]],  # [[{"text": "✅ Approva", "callback_data": "approve:abc123"}]]
    parse_mode: str = "HTML",
) -> int | None:
    """Invia messaggio con InlineKeyboardMarkup. Ritorna message_id o None se fallisce."""

async def edit_message_reply_markup(
    self,
    chat_id: str,
    message_id: int,
    keyboard: list[list[dict]] | None = None,
) -> bool:
    """Modifica la keyboard di un messaggio esistente. keyboard=None rimuove i bottoni."""
```

`format_freeze_message_with_keyboard()` — funzione standalone che restituisce `(text: str, keyboard: list[list[dict]])`. Il performance worker la chiama e passa entrambi a `send_message_with_keyboard()`.

---

## 6. Redis — `src/store/redis_store.py`

Nuovi metodi:

```python
def get_telegram_update_offset(self) -> int:
    """Legge l'offset corrente per /getUpdates. Ritorna 0 se non presente."""

def set_telegram_update_offset(self, offset: int) -> None:
    """Aggiorna l'offset dopo aver processato gli update. Senza TTL."""

def delete_weight_suggestion(self) -> bool:
    """Cancella ensemble:weights:suggestion e ensemble:weights:suggestion:snapshot.
    Ritorna True se la suggestion era presente, False se già assente."""
```

---

## 7. Celery Task — `src/workers/telegram_poller.py`

```python
@app.task(name="src.workers.telegram_poller.poll_telegram_updates")
def poll_telegram_updates() -> None:
    """Polling Telegram /getUpdates, processa callback_query per approve/reject."""
```

Il task è sincrono (Celery standard). Le chiamate HTTP a Telegram vengono fatte con `httpx.Client` (sincrono) — stesso pattern di altri worker che usano `asyncio.run()` solo se necessario.

Beat schedule in `celery_app.py`:
```python
"poll-telegram-updates": {
    "task": "src.workers.telegram_poller.poll_telegram_updates",
    "schedule": 5.0,  # ogni 5 secondi
},
```

---

## 8. Performance Worker — `src/workers/performance.py`

Modifica nella funzione che invia la notifica di freeze: sostituisce `send_alert(format_freeze_message(...))` con:

```python
import hashlib

token = hashlib.sha256(computed_at.encode()).hexdigest()[:8]  # computed_at dalla suggestion in Redis
text, keyboard = format_freeze_message_with_keyboard(
    suggested_weights=new_weights,
    current_weights=current_weights,
    freeze_reason=freeze_reason,
    suggestion_token=token,
)
asyncio.run(notifier.send_message_with_keyboard(text, keyboard))
# message_id ritornato non viene persistito:
# il poller lo riceve direttamente da callback_query.message.message_id al momento del tap
```

---

## 9. Fail-Safe e Edge Case

| Scenario | Comportamento |
|----------|--------------|
| Token stale (suggestion scaduta o sostituita) | `answerCallbackQuery("Già processata")`, nessuna scrittura |
| Double-tap | Secondo tap → suggestion già `None` → stale guard |
| User non in allowlist | Risposta silenziosa (`answerCallbackQuery("")`), nessun log |
| Telegram API down su `/getUpdates` | Log errore, offset non aggiornato, task termina; retry al prossimo run (5s) |
| Redis down durante approve | Task fallisce con exception; offset non aggiornato; il callback verrà riprocessato al prossimo run (idempotency: suggestion ancora presente) |
| `TELEGRAM_ALLOWED_USER_IDS` vuota | Poller salta callback processing, aggiorna solo offset |

---

## 10. File Coinvolti

| File | Azione | Descrizione |
|------|--------|-------------|
| `src/workers/telegram_poller.py` | Crea | Celery task `poll_telegram_updates()` |
| `src/notifications/telegram.py` | Modifica | Aggiunge `send_message_with_keyboard()`, `edit_message_reply_markup()`, `format_freeze_message_with_keyboard()` |
| `src/workers/performance.py` | Modifica | Chiama `send_message_with_keyboard()` per i freeze |
| `src/config.py` | Modifica | Aggiunge `TELEGRAM_ALLOWED_USER_IDS` |
| `src/store/redis_store.py` | Modifica | Aggiunge `get/set_telegram_update_offset()`, `delete_weight_suggestion()` |
| `src/workers/celery_app.py` | Modifica | Beat schedule ogni 5s per `poll_telegram_updates` |
| `tests/workers/test_telegram_poller.py` | Crea | 5 scenari (vedi §11) |
| `tests/notifications/test_telegram.py` | Modifica | Test per `send_message_with_keyboard()` e `format_freeze_message_with_keyboard()` |
| `tests/test_redis_store.py` | Modifica | Test per i 3 nuovi metodi Redis |

---

## 11. Test Coverage Richiesta

`TestTelegramPoller` deve coprire:

1. Callback `approve` valido → `set_ensemble_weights` chiamato, suggestion cancellata, `log_weight_update(source="telegram")`, `answerCallbackQuery` con testo ✅, `editMessageReplyMarkup` chiamato
2. Callback `reject` valido → suggestion cancellata, `log_weight_update(source="rejected_via_telegram", applied_weights={})`, `answerCallbackQuery` con testo ❌
3. Token stale (suggestion diversa in Redis) → nessuna scrittura Redis/PG, `answerCallbackQuery("Già processata")`
4. User non in allowlist → nessuna azione, risposta silenziosa
5. Nessun `callback_query` in `/getUpdates` → offset aggiornato, nessun altra azione

---

## 12. Vincoli Non Negoziabili

- Il poller non chiama mai LLM — è pura logica di routing.
- Fail-safe: se Redis è down durante approve, il task fallisce senza aggiornare l'offset (retry automatico). Non si deve mai perdere un'approvazione per un errore transitorio.
- Se `TELEGRAM_ALLOWED_USER_IDS` è vuota il poller è disabilitato (nessun callback processato).
- Idempotency: un secondo tap sullo stesso bottone trova la suggestion assente e risponde "già processata" senza effetti collaterali.
- `pg_store.py` non richiede modifiche: la rejection usa `log_weight_update(source="rejected_via_telegram", applied_weights={})` sulla tabella esistente `weight_update_log`.
