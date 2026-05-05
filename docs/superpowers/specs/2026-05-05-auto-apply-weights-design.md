# Auto-Apply Pesi con Guardrail — Design Spec

**Data:** 2026-05-05
**Status:** Approved
**Feature:** Fase 2 — Auto-apply ensemble weights con guardrail VIX/IC/delta

---

## 1. Contesto

`run_weekly_weights()` (Celery beat, settimanale) calcola i pesi ottimali via LOO ICIR e li salva come suggestion in Redis (`ensemble:weights:suggestion`, TTL 7d). Attualmente i pesi non vengono mai applicati senza approvazione manuale tramite `POST /api/weights/approve`.

Questa feature aggiunge un task `check_and_apply_weights` che applica automaticamente la suggestion se tutti i guardrail sono soddisfatti, oppure blocca e notifica via Telegram se qualcuno fallisce.

---

## 2. Architettura e Flusso Dati

```
Celery beat (lunedì 06:00 UTC)
  └─► run_weekly_weights()
        └─► Redis: ensemble:weights:suggestion  (TTL 7d)
        └─► Redis: ensemble:weights:suggestion:snapshot  (TTL 9d)
        └─► apply_async: check_and_apply_weights() [countdown=5s]
              │
              ├─► [G1] auto_apply_enabled? (workers.yaml)
              ├─► [G2] VIX < vix_threshold? (FRED → Redis cache 1h)
              ├─► [G3] IC variance < ic_variance_threshold? (suggestion payload)
              ├─► [G4] max(|Δweight|) < weight_delta_max? (vs pesi correnti in Redis)
              │
              ├─► TUTTI PASS → set_ensemble_weights() + log source='auto_apply' + Telegram ✅
              └─► QUALCUNO FAIL → nessuna modifica + log source='freeze' + Telegram ⚠️
```

`countdown=5` dà 5 secondi di margine per la propagazione in Redis tra i due task.

`check_and_apply_weights` può essere triggherato anche standalone (es. via shell o test) senza dover ricalcolare i pesi.

---

## 3. Configurazione — `config/workers.yaml`

Aggiungere il blocco seguente:

```yaml
auto_apply:
  enabled: true                  # toggle on/off senza deploy
  vix_threshold: 30.0            # blocca se VIX >= soglia
  ic_variance_threshold: 0.15    # blocca se std(IC ultimi 4 run) >= soglia
  weight_delta_max: 0.15         # blocca se qualche peso cambia di >= 15pp
  vix_redis_ttl_seconds: 3600    # cache VIX in Redis (1h)
  vix_fred_series: "VIXCLS"      # serie FRED per il VIX giornaliero
```

Tutte le soglie sono lette da `config` (Pydantic settings) all'avvio del task — nessuna costante hardcoded.

---

## 4. Guardrail — Logica e Ordine

I guardrail vengono valutati in sequenza. Al primo fallimento il task si ferma, logga la ragione, e manda l'alert Telegram.

| # | Guardrail | Fonte dati | Comportamento se dati mancanti |
|---|-----------|------------|-------------------------------|
| G1 | `auto_apply_enabled == true` | `workers.yaml` | **exit silenzioso** (no log, no Telegram — è uno stato operativo normale, non un errore) |
| G2 | `VIX < vix_threshold` | FRED API → Redis TTL 1h | freeze (fail-safe) |
| G3 | `std(purified_icir.values()) < ic_variance_threshold` | campo `purified_icir` già nel payload suggestion | freeze se `purified_icir` assente o vuoto |
| G4 | `max(abs(new_w - cur_w)) < weight_delta_max` | suggestion vs `get_current_weights_stored()` | freeze se pesi correnti assenti |

**Nota G3:** `purified_icir` è già nel payload di `run_weekly_weights()` — nessun campo nuovo da aggiungere. La std dei valori IC cross-modello misura il disaccordo tra modelli: alta std = stime inaffidabili = freeze.

**Principio fail-safe:** dato mancante o corrotto = guardrail fallisce = nessuna modifica ai pesi. Non applicare mai con dati incompleti.

---

## 5. VIX — Fetch e Cache

Nuovo metodo `fetch_vix_from_fred()` in `src/connectors/macro.py`:
- Chiama FRED API serie `VIXCLS` (ultimo valore disponibile)
- Ritorna `float` (es. `18.4`)

Nuovi metodi in `src/store/redis_store.py`:
- `get_vix_cached() -> float | None` — legge `macro:vix:latest` da Redis
- `set_vix_cached(value: float, ttl: int) -> None` — scrive con TTL configurabile

Il task `check_and_apply_weights`:
1. Prova a leggere il VIX dalla cache Redis
2. Se assente, chiama FRED e aggiorna la cache
3. Se FRED fallisce → guardrail G2 fallisce (freeze)

---

## 6. Audit Trail — `weight_update_log`

Entrambi i percorsi (auto-apply e freeze) scrivono su `weight_update_log` tramite `PostgreSQLStore.log_weight_update()`.

| Scenario | `source` | `applied_weights` | `note` | `approved_by` |
|----------|----------|-------------------|--------|---------------|
| Auto-apply ok | `'auto_apply'` | nuovi pesi applicati | JSON con valori guardrail | `'system'` |
| Freeze | `'freeze'` | pesi correnti (invariati) | motivo del freeze | `'system'` |

Il CHECK constraint su `source` nella tabella `weight_update_log` va esteso con `ALTER TABLE`:

```sql
-- Migration 003: estende source CHECK constraint per auto_apply e freeze
ALTER TABLE weight_update_log
  DROP CONSTRAINT weight_update_log_source_check;

ALTER TABLE weight_update_log
  ADD CONSTRAINT weight_update_log_source_check
  CHECK (source IN ('suggestion', 'override', 'expired', 'auto_apply', 'freeze'));
```

---

## 7. Notifiche Telegram

### Auto-apply riuscito

```
✅ Pesi aggiornati automaticamente

📊 Nuovi pesi:
  opus                  45% (+11pp)
  qwen3.5:cloud         35% (=)
  deepseek-v4-pro:cloud 20% (-11pp)

🛡️ Guardrail superati:
  VIX: 18.4 < 30.0
  IC variance: 0.08 < 0.15
  Δmax peso: 11pp < 15pp

🕐 Prossima revisione: 2026-05-12
```

### Freeze — approvazione manuale richiesta

```
⚠️ Auto-apply bloccato — approvazione manuale richiesta

🚫 Guardrail fallito: VIX = 38.2 ≥ 30.0

📊 Pesi suggeriti (NON applicati):
  opus                  45% (+11pp)
  qwen3.5:cloud         35% (=)
  deepseek-v4-pro:cloud 20% (-11pp)

👉 Approva manualmente: POST /api/weights/approve
```

Nuove funzioni in `src/notifications/telegram.py`:
- `format_auto_apply_message(new_weights, current_weights, guardrail_values, next_review_date) -> str`
- `format_freeze_message(suggested_weights, current_weights, freeze_reason) -> str`

---

## 8. File Coinvolti

| File | Azione | Descrizione |
|------|--------|-------------|
| `migrations/003_extend_source_check.sql` | Crea | ALTER TABLE per auto_apply e freeze |
| `config/workers.yaml` | Modifica | Aggiunge blocco `auto_apply:` |
| `src/config.py` | Modifica | Aggiunge `AutoApplyConfig` Pydantic model |
| `src/connectors/macro.py` | Modifica | Aggiunge `fetch_vix_from_fred()` |
| `src/store/redis_store.py` | Modifica | Aggiunge `get_vix_cached()` + `set_vix_cached()` |
| `src/workers/performance.py` | Modifica | Aggiunge `check_and_apply_weights()` + chain in `run_weekly_weights()` |
| `src/notifications/telegram.py` | Modifica | Aggiunge 2 formattatori messaggio |
| `tests/workers/test_performance_worker.py` | Modifica | Aggiunge `TestCheckAndApplyWeights` |
| `tests/notifications/test_telegram.py` | Modifica | Aggiunge test per i 2 nuovi formati |
| `tests/connectors/test_macro.py` | Modifica | Aggiunge test per `fetch_vix_from_fred()` |
| `tests/test_redis_store.py` | Modifica | Aggiunge test per VIX cache methods |

---

## 9. Test Coverage Richiesta

`TestCheckAndApplyWeights` deve coprire:
1. Tutti i guardrail passano → pesi applicati, log `auto_apply`, Telegram ✅ inviato
2. G1 fallisce (`enabled: false`) → nessuna modifica, log `freeze`
3. G2 fallisce (VIX alto) → nessuna modifica, log `freeze`, motivo VIX in nota
4. G3 fallisce (IC variance alta) → freeze
5. G4 fallisce (Δpeso > soglia) → freeze
6. FRED non risponde → G2 fallisce per fail-safe → freeze
7. Suggestion assente in Redis → task termina silenziosamente (nessun log, nessun alert)
8. `check_and_apply_weights` trigherato standalone (senza chain) funziona correttamente

---

## 10. Vincoli Non Negoziabili

- Il task non blocca mai l'esecuzione in attesa di dati esterni: timeout FRED = 10s, poi freeze.
- `approved_by = 'system'` nel log — mai il token API, mai `None`.
- I guardrail vengono rivalutati a ogni run del task, non cachati tra run.
- Il task è idempotente: se applicato due volte con la stessa suggestion, il secondo run trova G4 (Δpeso = 0) e non fa nulla (i pesi correnti = pesi suggestion → delta = 0 → sotto soglia → apply di nuovo con stesso valore, ma il log ha due righe). Accettabile.
