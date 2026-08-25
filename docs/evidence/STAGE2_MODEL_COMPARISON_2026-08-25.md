# Stage-2: confronto modelli in shadow — ricostruzione e verdetto

**Issue:** #34 (raccolta), #28 (decisione pair swap), #36 (ensemble a 3 modelli)
**Data:** 2026-08-25
**Finestra letta:** 2026-07-15 → 2026-08-24 (17.438 righe, 5.007 forward return)
**Fonte:** `llm_shadow_responses` + `llm_responses` su Postgres live (`alembic-postgres-1`, sola lettura)
**Riproduzione:** `build_comparison` / `render_markdown` di `src/performance/model_comparison.py`,
gli stessi che usa `run_shadow_comparison_report`

## Perché questo documento esiste

Il report Stage-2 veniva prodotto e **inviato solo via Telegram**, poi il toggle si
disarmava. Nessuna copia restava nel repo, nelle issue o nel database. Tre finestre
sono state armate (2026-07-27, 2026-08-10, 2026-08-24, via il cron del lunedì in
`scripts/auto_arm_shadow_monday.sh`) e **#28 risultava ancora in attesa di un report
che era già stato prodotto e perso**.

## Il report

| model | n | parse_fail | IC | hit rate |
|---|---:|---:|---:|---:|
| qwen3.5:cloud | 3504 | **95%** | 0,117 | 18% |
| glm-5.2:cloud | 5216 | 0% | 0,009 | 26% |
| gpt-oss:20b-cloud | 5214 | 0% | −0,010 | 22% |
| kimi-k2.6:cloud | 3504 | **89%** | −0,039 | 10% |

| pair (replay alla soglia live) | n | divergenza | pair IC |
|---|---:|---:|---:|
| glm-5.2+qwen3.5 | 183 | 0% | 0,054 |
| glm-5.2+kimi-k2.6 | 378 | 1% | −0,050 |
| kimi-k2.6+qwen3.5 | 115 | 1% | **0,124** |
| **glm-5.2+gpt-oss** *(coppia live)* | 5170 | 1% | −0,004 |
| gpt-oss+kimi-k2.6 | 377 | 2% | −0,089 |
| gpt-oss+qwen3.5 | 183 | 3% | 0,031 |

## Il verdetto: il confronto non è valido, e non è una questione di potenza

I due candidati falliscono il parsing nel **89-95%** dei casi. I loro IC sono calcolati
sul 5-11% sopravvissuto, che non è un campione casuale delle notizie: è il sottoinsieme
per cui il modello è **riuscito a rispondere in tempo**. La riga più attraente della
tabella — `kimi+qwen` a IC 0,124 — poggia su **n=115** selezionati in quel modo.

La coppia live, sulla stessa finestra, ha parse_fail **0%** su ~5.200 osservazioni per
modello. Non stiamo confrontando quattro modelli: stiamo confrontando due modelli con
due rumori.

### Il degrado è totale da quattro settimane

| settimana | kimi-k2.6 fail | qwen3.5 fail |
|---|---:|---:|
| 2026-07-13 | 68,0% | 82,6% |
| 2026-07-20 | 74,9% | 91,0% |
| 2026-07-27 | 94,4% | 96,6% |
| 2026-08-03 | **100%** | **100%** |
| 2026-08-10 | **100%** | **100%** |
| 2026-08-17 | **100%** | **100%** |
| 2026-08-24 | **100%** | **100%** |

**Le finestre armate il 10/08 e il 24/08 hanno prodotto zero dati utilizzabili.**
L'unica evidenza non degenere viene da metà luglio, dove il fallimento era comunque
fra il 68% e il 96%.

## La causa: non è un parse error, è un timeout — e non è lo stesso per tutti

`parse_error` maschera un timeout. Le latenze lo dicono senza ambiguità:

| esito | n | latenza media | max |
|---|---:|---:|---:|
| successo | 562 | 32.424 ms | 44.934 ms |
| fallimento | 6.446 | 44.837 ms | **45.047 ms** |

Tutti i fallimenti si accumulano contro un tetto netto di 45 secondi. I successi
stanno appena sotto.

Il tetto è **cablato nel path shadow**, `src/workers/sentiment.py:527`:

```python
out = await asyncio.wait_for(
    client.complete(prompt, response_schema=LLMSentimentOutput),
    timeout=45,
)
```

I modelli **live** girano invece con timeout per-modello di **90 secondi**
(`OLLAMA_*_TIMEOUT_SECONDS`, default 90 in `src/config.py:42-56`).

**I candidati ricevono metà del budget di tempo dei modelli con cui vengono
confrontati.** Il confronto è handicappato per costruzione: lo strumento di misura
penalizza sistematicamente il lato che deve misurare, e i modelli candidati sono
abbastanza lenti da cadere sempre dalla parte sbagliata della soglia.

## Conseguenze

1. **#28 non è decidibile** su questi dati. Nessuna delle coppie candidate ha un
   campione onesto. Non è «il pair swap non conviene»: è «non lo sappiamo».
2. **#36** (ensemble a 3 modelli) poggia sulla stessa base di evidenza, quindi eredita
   lo stesso vuoto.
3. **#34** ha prodotto il report, ma il report misura il timeout, non i modelli. La
   raccolta va rifatta dopo il fix.
4. Sei settimane di spesa su Ollama Cloud sono state consumate quasi interamente per
   risposte scartate.

## Cosa NON conta come evidenza da qui in avanti

Pre-registrato per evitare di rileggere questi numeri come se fossero validi:

- gli IC e gli hit rate di `qwen3.5:cloud` e `kimi-k2.6:cloud` in questa tabella;
- il pair IC di 0,124 su `kimi+qwen` (n=115, selezionato per sopravvivenza al timeout);
- qualunque confronto fra un candidato e la coppia live prima che il budget di tempo
  sia lo stesso per entrambi.

La riga della coppia live (`glm-5.2+gpt-oss`, n=5.170, parse_fail 0%, pair IC −0,004)
**resta leggibile**: non è affetta dal timeout. Va letta come conferma indipendente che
l'ensemble vivo non ha edge misurabile su questa finestra, non come termine di paragone
contro i candidati.
