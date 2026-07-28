# Spec — #138: `GET /api/health` riporta `mode` hardcoded

Part of #21 · Issue: #138 · Branch: `fix/138-health-mode-hardcoded`

## Contesto

`/api/health` restituisce un campo `mode` che è una **stringa letterale**, non uno stato letto:

```python
# src/api/main.py:152-155
@app.get("/api/health")
async def health() -> dict[str, str]:
    """Return the API liveness state."""
    return {"status": "ok", "mode": "backtest"}
```

Risponde `"backtest"` sempre: in paper, in live, a kill-switch attivo. Lo stato reale oggi è
paper trading (`ALPACA_PAPER_MODE` default `true` in `src/config.py:179`, `execution.engine:
portfolio` in `config/trading.yaml:142`).

Esiste già la fonte autorevole per la stessa domanda: **`GET /api/admin/mode`**
(`src/api/routes/admin.py:45`) che ritorna `store.get_mode()`, usata dal frontend in
`Admin.tsx:70`.

## Decisione già presa (non riaprirla)

**Rimuovere il campo `mode` da `/api/health`.** `/api/health` è una liveness probe; il mode ha
già il suo endpoint. Si elimina la doppia fonte di verità invece di sincronizzarla.

Non implementare la variante "leggi `store.get_mode()` dentro health": aggiungerebbe una
dipendenza da store a una probe di liveness, che inizierebbe a fallire per motivi scorrelati
dalla liveness. È stata valutata e scartata.

## Blast radius (già verificato — non ri-verificarlo, usalo)

L'unico consumatore di `/api/health` nel repo è l'healthcheck di docker-compose
(`docker-compose.yml:52`), che apre l'URL e **ignora il body**:

```yaml
test: ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')\""]
```

Nessun consumatore in `frontend/src`, nessuno in `src/mobile_monitoring/`.

## Scope

1. `src/api/main.py`: la risposta diventa `{"status": "ok"}`. Aggiorna il type hint e la
   docstring in modo che dicano cosa fa davvero (liveness, non stato di trading).
2. Se esiste un test che asserisce la presenza o il valore di `mode` su `/api/health`,
   aggiornalo.
3. Aggiungi un test di regressione che **fallisce se il campo torna**: la risposta di
   `/api/health` non deve contenere la chiave `mode`. Motivazione da mettere nel docstring del
   test: il campo era un letterale che contraddiceva `/api/admin/mode`.

## Fuori scope

- Non toccare `/api/admin/mode` né `store.get_mode()`.
- Non cambiare l'healthcheck di docker-compose (funziona già e non legge il body).
- Non aggiungere altri campi a `/api/health`.

## Metodo

TDD: prima il test che asserisce l'assenza di `mode`, verificalo rosso, poi la modifica.

## Criteri di accettazione

- `GET /api/health` → `{"status": "ok"}`, HTTP 200.
- Test di regressione presente e verde.
- `docker compose up -d api` → container `healthy` (l'healthcheck deve restare verde).
- Suite: nessuna regressione. Nota: `tests/store/test_pg_store_stop_methods.py::test_fixed_mode_freezes_audit_fields` fallisce già su main (issue #112) — non è tua e non va sistemata qui.

## Consegna

Branch `fix/138-health-mode-hardcoded`, un commit, PR con `closes #138`.
**Non mergiare e non deployare**: la review e il merge li faccio io.
