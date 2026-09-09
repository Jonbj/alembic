# Stage-2: riverifica del `parse_fail` dopo #368

**Issue:** #34

**Data di misura:** 2026-09-09

**Finestra armata:** 2026-09-07T07:00:02Z

**Cutoff riproducibile:** 2026-09-09T20:01:01.051074Z

**Fonte:** `llm_shadow_responses` su Postgres live, sola lettura

## Domanda pre-registrata

Il commento operatore del 2026-08-25 su #34 e
`scripts/check_shadow_parse_fail.sh` fissano prima di questa lettura la domanda e
il criterio: con il pool del semaforo sano e budget per modello a 90 secondi, il
peggiore `parse_fail` nelle ultime 24 ore deve essere al massimo 10%. La finestra
intera resta contesto e non sostituisce il verdetto sulle ultime 24 ore.

Questa verifica non cambia soglie, pesi, flag, cooldown, coppia live o toggle
shadow. E' una misura nel perimetro `freeze-ok` di #171.

## Precondizioni verificate

Alle 2026-09-09T21:05:32Z:

- `shadow:model_comparison:started_at` valeva
  `2026-09-07T07:00:02+00:00`;
- `config:sentiment_llm_models` valeva `glm52,gptoss`;
- il pool live aveva 2 slot disponibili su 2 e il pool shadow 3 su 3; la
  stessa lettura 2/2 e 3/3 era stata ottenuta anche prima della query;
- nel container `alembic-worker-inference-1`, sia
  `OllamaKimiClient._OLLAMA_TIMEOUT` sia
  `OllamaQwen35Client._OLLAMA_TIMEOUT` valevano `90`;
- gli SHA-256 di `src/llm/client.py` e `src/workers/sentiment.py` nel container
  coincidevano con quelli del checkout. Il runtime contiene quindi il recupero
  token di #368 e il budget simmetrico di #358 osservati nel codice corrente.

## Risultato

### Verdetto sulle ultime 24 ore

Finestra fissata al cutoff, quindi
`2026-09-08T20:01:01.051074Z < created_at <= 2026-09-09T20:01:01.051074Z`:

| modello | n | fallimenti | `parse_fail` | latenza media | cause registrate |
|---|---:|---:|---:|---:|---|
| `kimi-k2.6:cloud` | 199 | 160 | **80,4%** | 88.412 ms | `error:RuntimeError`, `timeout` |
| `qwen3.5:cloud` | 199 | 93 | **46,7%** | 75.757 ms | `error:RuntimeError`, `timeout` |

**Esito: SOPRA SOGLIA per entrambi i candidati.** Il peggiore `parse_fail` e'
80,4%, contro il massimo pre-registrato del 10%.

### Contesto dall'armamento al cutoff

| modello | n | fallimenti | `parse_fail` | latenza media |
|---|---:|---:|---:|---:|
| `kimi-k2.6:cloud` | 411 | 360 | **87,6%** | 88.216 ms |
| `qwen3.5:cloud` | 411 | 230 | **56,0%** | 77.762 ms |

Le 822 righe coprono 401 notizie distinte. I timeout espliciti si accumulano a
95.000-95.042 ms, coerenti con il budget interno di 90 secondi piu' i 5 secondi
di slack del bounded wait shadow. Il risultato non riproduce il vecchio guasto
di #368: durante la misura il pool shadow non era esaurito, e al controllo
finale aveva tutti i 3 slot disponibili.

## Verdetto e limite dell'evidenza

La riverifica richiesta da #34 e' stata eseguita, ma ha esito negativo: la
raccolta successiva ai fix #358 e #368 continua a selezionare i candidati in
base alla capacita' di completare entro il budget. Questa finestra non rende
quindi decidibile il pair swap di #28 e non deve essere usata per confrontare
IC o hit rate dei candidati con la coppia live.

La misura non stabilisce qui la causa dei `RuntimeError` e non propone di
allungare timeout o cambiare modelli: sarebbe un lavoro distinto e, per ogni
modifica di taratura, fuori perimetro durante il freeze.

## Riproduzione

Il comando seguente usa il cutoff fisso e riproduce il verdetto senza leggere
né modificare Redis:

```bash
docker exec alembic-postgres-1 psql -U trading -d trading -P pager=off -c "
with limiti as (
  select '2026-09-07T07:00:02+00:00'::timestamptz as inizio,
         '2026-09-09T20:01:01.051074+00:00'::timestamptz as fine
)
select model_id,
       count(*) as n,
       count(*) filter (where parse_error) as fail,
       round(100.0 * count(*) filter (where parse_error)
             / nullif(count(*), 0), 1) as fail_pct,
       round(avg(latency_ms)) as avg_ms,
       coalesce(string_agg(distinct failure_reason, ','), '-') as failure_reason
from llm_shadow_responses, limiti
where created_at > greatest(inizio, fine - interval '24 hours')
  and created_at <= fine
group by model_id
order by model_id;"
```

L'output atteso contiene 199 righe per modello, con `fail_pct` 80,4 per Kimi e
46,7 per Qwen. Un controllo operativo senza cutoff puo' invece usare
`scripts/check_shadow_parse_fail.sh`, che applica la stessa regola sulle ultime
24 ore ma scrive nel log di sessione e puo' inviare la notifica configurata.
