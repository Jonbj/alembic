# Spec — #17: `compute_new_weights` ripiega su pesi uguali invece di proiettare

Part of #21 · Issue: #17 · Branch: `fix/17-weights-simplex-projection`

## ⚠️ La issue è parzialmente superata — leggi questo prima del testo della issue

La issue #17 (scritta il 2026-05-19) descrive una **violazione dell'invariante**: dopo la
rinormalizzazione finale i pesi potevano uscire da `[floor, cap]`. **Quel difetto è già stato
corretto**: `src/performance/weights.py` contiene ora una proiezione iterativa
(clip → renormalizza, max 5 giri) con controllo di convergenza.

Verificato eseguendo lo scenario esatto della issue (`{0.05, 0.05, 0.90}`, floor 0.10, cap 0.70)
con i parametri di default:

```
alpha=0.25 max_delta=0.10 -> [0.2739, 0.2739, 0.4522]   somma 1.0, dentro i bound
```

**Non riscrivere il fix dell'invariante. È fatto.** Il lavoro qui è un difetto diverso, che
quella correzione ha lasciato dietro.

## Il difetto reale

Quando l'iterazione `clip → renormalizza` **non converge in 5 giri**, la funzione ripiega su
**pesi uguali**:

```python
# fine di compute_new_weights
# Fallback: equal weights if projection fails to converge
n = len(constrained)
```

Cioè butta via completamente il segnale ICIR e torna a 1/n. Riproduzione:

```
alpha=1.0 max_delta=1.0 -> [0.3333, 0.3333, 0.3333]   equal-weight fallback
```

Il punto è che **una soluzione valida esiste**: per `{0.05, 0.05, 0.90}` con floor 0.10 e cap
0.70, i pesi `[0.15, 0.15, 0.70]` rispettano i bound e sommano a 1.0. L'euristica non la trova
perché il ciclo clip→renormalizza rigonfia a ogni giro l'elemento cappato, e oscilla.

Conseguenza: in uno stato di ensemble fortemente sbilanciato — proprio quello in cui la
ponderazione conta di più — il sistema può silenziosamente scartare l'informazione e tornare
all'equipesatura, senza che nulla lo segnali.

## Scope

Sostituisci l'euristica a 5 iterazioni **e** il fallback a pesi uguali con una **proiezione
deterministica sul simplesso con vincoli di box** (water-filling): dati i pesi target, floor,
cap, trova i pesi che sommano a 1.0, rispettano `floor ≤ w ≤ cap` e sono i più vicini al target.

Requisiti:

1. **Deterministica e senza iterazioni a tentativi**: niente "max N giri e poi ripiego".
2. **Gestione esplicita dell'infattibilità.** Il problema è irrisolvibile se `n*floor > 1.0`
   oppure `n*cap < 1.0` (es. 3 modelli con floor 0.40). In quel caso i vincoli sono in conflitto
   fra loro: **non ripiegare in silenzio**. Solleva un errore esplicito oppure logga a `WARNING`
   e ritorna i pesi correnti invariati — scegli tu, ma dev'essere un comportamento dichiarato
   nella docstring e coperto da un test.
3. **Invariante asserito** in uscita, come chiede la issue:
   `all(floor - eps <= w <= cap + eps)` e `abs(sum - 1.0) < 1e-9`.
4. Il resto della pipeline (raw da ICIR, normalizzazione, smoothing `alpha`, guardrail
   `max_delta`) **resta com'è**. Cambia solo il passo finale di proiezione.

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

- Non cambiare i default `alpha`, `floor`, `cap`, `max_delta`.
- Non toccare `compute_purified_icir` né chi consuma i pesi.
- Non modificare il comportamento nei casi che oggi già convergono: i pesi prodotti nello
  scenario di default devono restare gli stessi entro tolleranza numerica (vedi test 1).

## Metodo

TDD. Test richiesti, prima dell'implementazione:

1. **Non-regressione sui casi che già funzionano**: `{0.05,0.05,0.90}` con `alpha=0.25,
   max_delta=0.10` deve continuare a dare `[0.2739, 0.2739, 0.4522]` (±1e-3).
2. **Il caso che oggi ripiega**: `alpha=1.0, max_delta=1.0` sullo stesso input **non** deve più
   dare `[1/3, 1/3, 1/3]`; deve dare la proiezione corretta (per quell'input, `[0.15, 0.15,
   0.70]` ±1e-6). Il docstring del test deve dire che l'equipesatura era il vecchio fallback.
3. **Invariante su input casuali**: genera N ≥ 200 vettori ICIR con seed fisso, verifica bound e
   somma su ognuno. Nessun caso deve produrre equipesatura a meno che il target non fosse già
   uniforme.
4. **Infattibilità**: 3 modelli con `floor=0.40` (somma minima 1.20 > 1.0) → il comportamento
   dichiarato al punto 2 dello Scope, verificato.
5. **Cap saturo**: un solo modello con ICIR positivo e gli altri a zero → il vincitore si ferma
   a `cap`, il resto si distribuisce sopra `floor`.

## Criteri di accettazione

- I cinque test verdi.
- Nessun percorso di codice ritorna più pesi uguali come ripiego silenzioso.
- Assert dell'invariante presente nel codice di produzione, non solo nei test.
- Suite completa senza regressioni (nota: `test_fixed_mode_freezes_audit_fields` fallisce già su
  main, issue #112 — non è tua).

## Contesto d'impatto (per calibrare l'attenzione, non da implementare)

I pesi dell'ensemble sono letti dall'aggregatore: sbagliarli sposta il peso relativo dei modelli
nel punteggio di sentiment che alimenta S4. Non è codice di sizing, ma è a monte di esso.

## Consegna

Branch `fix/17-weights-simplex-projection`, un commit, PR con `closes #17`.
**Non mergiare e non deployare**: review e merge li faccio io.
