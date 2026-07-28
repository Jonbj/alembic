# Spec — #44 (B9): `SentimentResult.model_dump_json` sovrascrive l'API Pydantic v2

Part of #21 · Issue: #44 · Branch: `fix/44-sentiment-result-serialization`

## Contesto

`SentimentResult` (`src/models/signals.py:8`) è un `BaseModel` Pydantic v2 che **sovrascrive**
`model_dump_json`, il metodo del framework, con una firma incompatibile e un dump JSON scritto
a mano:

```python
# src/models/signals.py:28
def model_dump_json(self) -> str:  # type: ignore[override]
    """Serialize to JSON string for Redis storage."""
    import json
    return json.dumps({
        "symbol": self.symbol,
        ...
        "signal_id": self.signal_id,
    })
```

Il `# type: ignore[override]` è il sintomo: la firma reale di Pydantic v2 è
`model_dump_json(*, indent=None, include=None, exclude=None, ...)`, qui è senza argomenti.

## Perché è un problema (due difetti distinti)

1. **Firma incompatibile.** Qualunque chiamante che passi un kwarg legittimo di Pydantic
   (`indent`, `exclude`, …) esplode con `TypeError`. Il metodo ha il nome del framework ma non
   il contratto del framework.
2. **Manutenzione manuale silenziosa.** Ogni campo nuovo del modello va aggiunto a mano al
   `json.dumps`, altrimenti **sparisce dalla serializzazione senza errori**. Oggi i campi
   coincidono (verificato: tutti e 10 sono presenti), quindi non si sta perdendo nulla — ma è
   una trappola armata, e questo modello è già cresciuto due volte (`published_at` FIX-03,
   `signal_id` B33-follow-up).

## Vincolo non negoziabile: compatibilità di filo

Il JSON prodotto finisce in Redis (chiavi `signal:{symbol}:sentiment`, e code di lavoro) e viene
riletto da altri processi. **Valori già presenti in Redis al momento del deploy devono restare
leggibili**, e il nuovo output deve restare leggibile dai lettori attuali.

Prima di scrivere codice: **trova tutti i punti di scrittura e di lettura** di questo payload
(cerca `signal:.*:sentiment`, `json.loads` su quei valori, e ogni ricostruzione
`SentimentResult(...)` da dizionario). Elencali nella PR. Se un formato cambia, la PR deve dire
esplicitamente perché è compatibile.

Attenzione ai `datetime`: oggi sono serializzati con `.isoformat()` e `None` per
`published_at` assente. La serializzazione nativa di Pydantic v2 produce anch'essa ISO-8601 —
**verificalo**, non darlo per scontato, e confronta le due stringhe su un caso reale.

## Scope

Rimuovi l'override e ottieni la serializzazione per Redis senza collidere con l'API del
framework. Due strade accettabili, scegli tu e motiva in una riga nella PR:

- **(a)** Eliminare il metodo e usare `model_dump_json()` nativo di Pydantic ai call-site, se
  l'output è identico campo per campo.
- **(b)** Rinominare il metodo in qualcosa di non-framework (es. `to_redis_json()`),
  aggiornando i chiamanti, se serve mantenere un formato su misura.

Preferisci **(a)** se e solo se dimostri l'identità dell'output.

## Cerca i consumatori anche in `docs/`

**Lezione da #138 (2026-07-28).** In quella spec avevo verificato i consumatori solo nel
codice. Il fix era corretto, ma `docs/API.md` continuava a descrivere lo stesso endpoint con
una risposta inventata e con un comportamento (`503` sulle dipendenze) che non è mai esistito —
e il runbook mandava l'operatore proprio lì. Il difetto che stavamo togliendo dal codice era
rimasto nella documentazione.

Quindi, se il tuo intervento cambia una **risposta API, un formato serializzato, uno schema o un
contratto osservabile dall'esterno**, la ricerca dei consumatori deve includere:

- `docs/` (in particolare `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/operations.md`)
- `README.md` e `CONTEXT.md`
- il frontend (`frontend/src`), incluse le pagine di testo come `Docs.tsx`

Se trovi una descrizione diventata falsa, **correggila nello stesso branch** e dillo nella PR.
Se non cambi nulla di osservabile dall'esterno, scrivi una riga nella PR che lo dichiara —
serve a far vedere che il controllo è stato fatto, non saltato.

## Fuori scope

- Non aggiungere né rimuovere campi da `SentimentResult`.
- Non cambiare le chiavi Redis, i TTL o lo schema DB.
- Non toccare gli altri modelli che usano `model_dump_json()` nativo (`src/workers/ingestion.py`,
  `src/workers/performance.py:824`): quelli non sovrascrivono nulla e vanno lasciati stare.

## Metodo

TDD. Test richiesti, prima dell'implementazione:

1. **Round-trip**: `SentimentResult` → JSON → dict → `SentimentResult` preserva tutti i campi,
   compresi `published_at=None` e `signal_id=None`.
2. **Compatibilità all'indietro**: una stringa JSON nel formato *attuale* (incollala come
   letterale nel test, non generarla) deve restare deserializzabile.
3. **Anti-regressione sul difetto 2**: un test che fallisce se un campo del modello non compare
   nell'output serializzato. Deve derivare l'elenco dei campi dal modello
   (`model_fields`), non da una lista scritta a mano — altrimenti riproduce la trappola che
   stiamo togliendo.
4. Se scegli (a): un test che dimostra che l'API nativa accetta i kwargs standard senza
   `TypeError`.

## Criteri di accettazione

- Nessun `# type: ignore[override]` residuo su questo modello.
- I quattro test sopra presenti e verdi.
- Elenco dei punti di lettura/scrittura del payload riportato nella PR, con la motivazione della
  compatibilità.
- Suite completa senza regressioni (nota: `test_fixed_mode_freezes_audit_fields` fallisce già su
  main, issue #112 — non è tua).

## Consegna

Branch `fix/44-sentiment-result-serialization`, un commit, PR con `closes #44`.
**Non mergiare e non deployare**: review e merge li faccio io.
