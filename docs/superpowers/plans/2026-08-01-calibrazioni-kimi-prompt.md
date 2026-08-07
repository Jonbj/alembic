# Calibrazioni C1-C3 — Prompt di esecuzione per Kimi

> **Per l'agente esecutore:** non hai contesto pregresso su questo repo. Leggi questo documento una volta, poi esegui esattamente ciò che dice. NON improvvisare oltre il piano. Un revisore umano controlla prima del merge: il tuo compito è eseguire e restituire, non mergiare né deployare.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — sistema di trading algoritmico LLM in **paper trading**.

**Il tuo worktree (NON la directory principale):**

```
/home/stefano/Documents/Projects/Alembic/.worktrees/calibrazioni
```

**Branch:** `evidence/calibrazioni-momentum` (già creato e allineato). Lavora SOLO lì dentro.

⚠️ **La directory principale deve restare su `main` e non va toccata.** Ci girano cron di produzione che leggono gli script da lì: se cambi branch in quella directory, mandi in esecuzione la versione sbagliata di uno script che gestisce soldi. Non fare `cd` fuori dal tuo worktree per operazioni git.

**Il piano che devi eseguire:** `docs/superpowers/plans/2026-08-01-calibrazioni-momentum-plan.md` (già presente nel tuo worktree). Cinque task, **tutte tue**, in ordine: 1 → 2 → 3 → 4 → 5.

---

## Cosa costruisci

Un modulo Python **puro** con quattro funzioni: il segnale di momentum, la selezione del paniere, il rendimento equipesato di periodo, e le statistiche riassuntive.

"Puro" è il vincolo che rende questo lavoro delegabile: **nessun I/O**. Niente rete, niente database, niente lettura di file, niente credenziali. Le funzioni ricevono dizionari di prezzi e restituiscono numeri. I test usano fixture in memoria da poche righe.

Serve a calibrare un programma di backtest: stabilire **quanto vale l'effetto di momentum sul nostro universo**, prima di testare qualunque variante. Non è una strategia da mettere in produzione.

## Cosa NON devi fare

- **NON** creare `scripts/run_calibration.py` né `src/backtest/data/alpaca_loader.py`: li scrive il revisore.
- **NON** toccare `src/backtest/`, `src/workers/`, `src/strategies/`, `src/store/`, `config/`, `docs/evidence/`, `scripts/`.
- **NON** toccare `src/analysis/__init__.py`. Il pacchetto `src/analysis/` **esiste già** e contiene altro codice: tu crei solo il sottopacchetto `calibration/`. In una fase precedente un comando con `>` ha sovrascritto quel file distruggendone il contenuto — non ripetiamolo.
- **NON** fare merge, **NON** aprire PR, **NON** push forzati, **NON** riavviare container, **NON** toccare DB, Redis o il sistema di trading.
- **NON** aggiungere dipendenze: bastano `statistics` e `math` della libreria standard.

---

## Protocollo di sessione

1. **Test runner:** sempre `uv run pytest <path> -v`. Mai `pytest` nudo.
2. **TDD, rigorosamente.** Per ogni task: scrivi il test → **eseguilo e guardalo fallire per il motivo giusto** → implementa → guardalo passare → commit. Non saltare il passaggio del fallimento: se un test passa prima dell'implementazione, quel test è rotto.
3. **Un commit per task**, col messaggio già scritto nel piano.
4. **Copia il codice alla lettera dal piano.** Non riscriverlo, non riformattarlo, non "migliorarlo", non tradurre i commenti. I docstring contengono avvertenze metodologiche scelte parola per parola: una di esse spiega perché un risultato non significativo va registrato come «non dimostrata» e non come «falsa», ed è una distinzione su cui si baseranno decisioni.

### Verifica anti-corruzione, dopo ogni task di codice

In fasi precedenti di questo lavoro sono state introdotte corruzioni silenziose ricopiando testo dal piano: un underscore perso in un nome di file, una parola cambiata che invertiva il senso di una frase. Non erano visibili dalle verifiche normali.

Il confronto usa l'AST, quindi non produce falsi positivi se la formattazione differisce:

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/calibrazioni
python3 - <<'PY'
import ast, glob, re

plan = open('docs/superpowers/plans/2026-08-01-calibrazioni-momentum-plan.md').read()
blocchi = re.findall(r"```python\n(.*?)```", plan, re.S)
percorsi = ['src/analysis/calibration/momentum.py', *glob.glob('tests/analysis/test_calibration_momentum.py')]
nodi_reali = set()
for percorso in percorsi:
    try:
        modulo = ast.parse(open(percorso).read())
    except FileNotFoundError:
        continue
    nodi_reali.update(
        ast.dump(n, include_attributes=False)
        for n in modulo.body
        if not isinstance(n, (ast.Import, ast.ImportFrom))
    )

mancanti = []
for i, blocco in enumerate(blocchi, 1):
    for n in ast.parse(blocco).body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        if ast.dump(n, include_attributes=False) not in nodi_reali:
            mancanti.append((i, getattr(n, 'name', type(n).__name__)))

print('nodi del piano non ritrovati nel codice:', len(mancanti))
for i, nome in mancanti[:10]:
    print(f'  MANCANTE blocco {i}: {nome}')
PY
```

Durante l'esecuzione possono mancare i nodi delle task non ancora fatte. **Alla fine deve stampare zero.**

### Baseline della suite

Prima di cominciare:

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/calibrazioni
uv run pytest -q 2>&1 | tail -3
```

Baseline osservata in un worktree fresco al 2026-08-01: `1 failed, 3289 passed, 14 skipped`. Il fallimento singolo è il caso noto **#152** (`test_get_s1_backtest_returns_equity_curve` dipende da `reports/`, che è gitignored, quindi fallisce per costruzione in un worktree fresco). Alla fine deve essere identica, più i tuoi **21 test nuovi**. Un fallimento in più va indagato e riportato, mai ignorato.

---

## Note sui contenuti, perché tu capisca cosa stai scrivendo

Non sono istruzioni aggiuntive: servono a farti riconoscere un errore se lo commetti.

- **`None` non è `0`, e "saltare" non è "contare zero".** Il piano impone `None` in più punti: deviazione standard di un solo campione, t su deviazione nulla, rendimento di un paniere senza dati. E impone di **saltare** un simbolo senza prezzi invece di contarlo con rendimento zero — contarlo come zero affermerebbe che non si è mosso, che è falso. Se ti viene la tentazione di mettere uno zero "per sicurezza", rileggi il test.

- **Il tie-break alfabetico in `select_top` non è estetica.** Senza, l'ordine dipende dall'iterazione del dizionario e due esecuzioni sugli stessi dati possono restituire panieri diversi. Una calibrazione che non è riproducibile non serve a niente.

- **`select_top` NON filtra i punteggi negativi.** Long-only significa che non shortiamo i perdenti, non che escludiamo i vincitori relativi quando tutto il paniere scende. Il filtro di momentum assoluto è un'ipotesi separata (dual momentum), e trasformarlo in un default silenzioso falserebbe la calibrazione.

- **La soglia `|t| >= 3.0`** viene da un risultato pubblicato (Harvey-Liu-Zhu 2016): con le decine di anomalie testate in letteratura, la soglia convenzionale di 1.96 produce in maggioranza falsi positivi. Non abbassarla e non aggiungere una soglia alternativa.

## Se qualcosa non torna

Fermati e riporta. Non inventare una soluzione alternativa e non "aggiustare" un test per farlo passare: se un test del piano non passa con l'implementazione del piano, **c'è un errore nel piano e voglio saperlo**. È già successo — in una fase precedente il piano conteneva un valore aritmeticamente sbagliato, l'esecutore si è fermato e ha chiesto, ed era la cosa giusta da fare.

## Restituzione

1. I 5 commit prodotti (hash + messaggio)
2. L'output reale di `uv run pytest tests/analysis/test_calibration_momentum.py -v` (deve mostrare **21 test**)
3. L'output reale della suite completa, confrontato con la baseline
4. L'esito della verifica anti-corruzione (deve essere zero)
5. L'output di `git status --short src/analysis/` — deve mostrare **solo** `calibration/`
6. Qualunque cosa ti abbia sorpreso o su cui hai dovuto decidere da solo

Poi `git push origin evidence/calibrazioni-momentum` e fermati.
