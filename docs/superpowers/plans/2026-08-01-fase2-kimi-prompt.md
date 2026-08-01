# Fase 2 dossier — Prompt di esecuzione per Kimi

> **Per l'agente esecutore:** non hai contesto pregresso su questo repo. Leggi questo documento una volta, poi esegui esattamente ciò che dice. NON improvvisare oltre il piano. Un revisore umano controlla prima del merge: il tuo compito è eseguire e restituire, non mergiare né deployare.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — sistema di trading algoritmico LLM in **paper trading**.

**Il tuo worktree (NON la directory principale):**

```
/home/stefano/Documents/Projects/Alembic/.worktrees/fase2-dossier
```

**Branch:** `evidence/fase2-dossier` (già creato e allineato). Lavora SOLO lì dentro.

⚠️ **La directory principale deve restare su `main` e non va toccata.** Ci girano dei cron che leggono gli script da lì: se cambi branch in quella directory, mandi in esecuzione la versione sbagliata di uno script di produzione. Non fare `cd` fuori dal tuo worktree per operazioni git.

**Il piano che devi eseguire:** `docs/superpowers/plans/2026-08-01-fase2-dossier-report-simmetrico.md` (già presente nel tuo worktree). Sei task, **tutte tue**, in ordine: A1 → A2 → A3 → B1 → B2 → B3.

---

## Cosa costruisci

Due moduli Python **puri** che calcolano le metriche di un report giornaliero: uno guarda il mercato (rendimenti, dispersione, mover, copertura news), l'altro guarda il portafoglio (metriche di ingresso e uscita, aggregazioni).

"Puri" è il vincolo di progetto che rende questo lavoro possibile: **non fanno I/O**. Ricevono dati già caricati come argomenti e restituiscono dizionari. Nessuna connessione a database, nessuna chiamata di rete, nessuna lettura di file. L'orchestratore che farà l'I/O lo scrive il revisore, dopo di te.

Non ti serve accesso al DB né credenziali: i test usano fixture in memoria.

## Cosa NON devi fare

- **NON** creare o modificare `scripts/alpha_miner_dossier.py` né `scripts/daily_alpha_miss_analysis.sh`: li scrive il revisore.
- **NON** toccare nulla sotto `src/workers/`, `src/strategies/`, `src/store/`, `config/`, `docs/evidence/`.
- **NON** fare merge, **NON** aprire PR, **NON** fare push forzati, **NON** riavviare container, **NON** toccare DB, Redis o il sistema di trading.
- **NON** aggiungere dipendenze: servono solo `statistics` (libreria standard) e `pytest`.

---

## Protocollo di sessione

1. **Test runner:** sempre `uv run pytest <path> -v`. Mai `pytest` nudo.
2. **TDD, rigorosamente.** Ogni task ha lo stesso ciclo: scrivi il test → **eseguilo e guardalo fallire per il motivo giusto** → implementa → eseguilo e guardalo passare → commit. Non saltare il passaggio del fallimento: serve a dimostrare che il test misura qualcosa. Se un test passa prima dell'implementazione, quel test è rotto.
3. **Un commit per task**, col messaggio già scritto nel piano.
4. **Copia il codice alla lettera dal piano.** Non riscriverlo con parole tue, non riformattarlo, non "migliorarlo", non tradurre i commenti. I docstring contengono avvertenze metodologiche precise, scelte parola per parola.

### Verifica anti-corruzione, obbligatoria dopo ogni task di codice

Nella fase precedente di questo lavoro un esecutore ha introdotto corruzioni silenziose ricopiando testo dal piano: un underscore perso in un nome di file, una parola cambiata che invertiva il senso di una frase. Non erano visibili dalle verifiche normali.

Dopo ogni task che copia codice dal piano, **confronta ciò che hai scritto con il piano**:

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/fase2-dossier
python3 - <<'PY'
import re
plan = open('docs/superpowers/plans/2026-08-01-fase2-dossier-report-simmetrico.md').read()
blocchi = re.findall(r"```python\n(.*?)```", plan, re.S)
sorgenti = open('src/analysis/dossier/market.py').read() + open('src/analysis/dossier/book.py').read() \
    if __import__('os').path.exists('src/analysis/dossier/book.py') else open('src/analysis/dossier/market.py').read()
tests = "".join(open(f).read() for f in __import__('glob').glob('tests/analysis/test_*.py'))
tutto = sorgenti + tests
mancanti = []
for b in blocchi:
    for riga in b.splitlines():
        r = riga.strip()
        if len(r) > 25 and not r.startswith('#') and r not in tutto:
            mancanti.append(r)
print("righe del piano non ritrovate nel codice:", len(mancanti))
for m in mancanti[:10]: print("  MANCANTE:", m[:100])
PY
```

Alcune righe possono legittimamente non comparire (per esempio quelle di blocchi di task che non hai ancora fatto). Quello che conta è che **nessuna riga di una task che hai già completato risulti mancante**: se una riga che hai appena scritto non viene ritrovata, l'hai copiata male.

### Baseline della suite

Prima di cominciare, cattura la baseline:

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/fase2-dossier
uv run pytest -q 2>&1 | tail -3
```

Attesa al 2026-08-01: `3281 passed, 1 skipped`. Alla fine deve essere identica, più i tuoi 13 test nuovi. **Un fallimento in più va indagato e riportato, mai ignorato.**

---

## Note sui contenuti, perché tu capisca cosa stai scrivendo

Non sono istruzioni aggiuntive: servono a farti riconoscere un errore se lo commetti.

- **`None` non è `0`.** Più volte il piano impone di restituire `None` invece di un numero: la deviazione standard di un solo campione, un percentile su un range degenere, una metrica su un simbolo senza barra di prezzo. È deliberato. Un `0.0` al posto di `None` significa "il valore è zero", che è un'affermazione falsa e che a valle diventa una statistica inventata. Se ti viene la tentazione di mettere uno zero "per sicurezza", è il momento di rileggere il test.

- **Due test contengono numeri di casi reali** (il titolo F comprato a 16,02 il 29 luglio, MSFT uscito a 455,56 il 30 luglio). Non sono valori inventati: sono trade realmente avvenuti, usati come ancoraggio. Se non tornano, è la tua implementazione a essere sbagliata, non il test.

- **`t_stat` è un campo che ordina le ipotesi, non che le dichiara vere.** Il docstring lo dice esplicitamente perché il dato viene consumato da un LLM che potrebbe leggerlo come una scoperta. Copialo così com'è.

## Se qualcosa non torna

Fermati e riporta. Non inventare una soluzione alternativa e non "aggiustare" un test per farlo passare: se un test del piano non passa con l'implementazione del piano, c'è un errore nel piano e voglio saperlo.

## Restituzione

Quando hai finito, riporta:

1. I 6 commit prodotti (hash + messaggio)
2. L'output reale di `uv run pytest tests/analysis/ -v` (deve mostrare 13 test)
3. L'output reale della suite completa, confrontato con la baseline
4. L'esito della verifica anti-corruzione
5. Qualunque cosa ti abbia sorpreso o su cui hai dovuto decidere da solo

Poi `git push origin evidence/fase2-dossier` e fermati.
