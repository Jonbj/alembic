# Fase 1 ledger evidenze — Prompt di esecuzione per Kimi

> **Per l'agente esecutore:** non hai contesto pregresso su questo repo. Leggi questo documento una volta, poi esegui esattamente ciò che dice. NON improvvisare oltre la spec. Un revisore umano controlla prima del merge: il tuo compito è eseguire e restituire, non mergiare né deployare.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — sistema di trading algoritmico LLM in **paper trading**.

**Il tuo worktree (NON la directory principale):**

```
/home/stefano/Documents/Projects/Alembic/.worktrees/evidence-fase1
```

**Branch:** `evidence/fase1-ledger` (già creato, già pushato, già allineato). Lavora SOLO lì dentro.

⚠️ **La directory principale del repo è usata in questo momento da un altro agente su un altro branch.** Non toccarla, non fare `git checkout` lì, non fare `cd` fuori dal tuo worktree per operazioni git.

**Il piano che devi eseguire:** `docs/superpowers/plans/2026-08-01-fase1-ledger-evidenze.md` (già presente nel tuo worktree). Contiene 8 task; **a te ne toccano 4**.

---

## Cosa devi fare: Task 1, 2, 3, 5 (solo la parte alpha-miss)

| task | cosa | file |
|---|---|---|
| **1** | Carta di osservazione | crea `docs/evidence/OBSERVATION_CHARTER.md` |
| **2** | Inizializza i due ledger | crea `docs/evidence/findings.json` e `docs/evidence/market_daily.jsonl` |
| **3** | Protocollo ledger nel cron alpha-miss | modifica `scripts/daily_alpha_miss_analysis.sh` |
| **5** | Verifica sostituzione placeholder | solo **Step 1** (alpha-miss). Lo Step 2 è di un altro agente |

Il piano contiene il **contenuto integrale** di ogni file e il **testo esatto** da inserire nei prompt. Copialo alla lettera: non riscriverlo con parole tue, non riformattarlo, non "migliorarlo". Quei testi finiscono dentro prompt di sessioni automatiche e ogni parola è stata scelta.

## Cosa NON devi fare

- **NON** toccare `scripts/daily_analysis.sh` (Task 4) né `scripts/deadline_reminders.conf` (Task 7): sono di un altro agente che lavora in parallelo. Se li tocchi, creiamo un conflitto.
- **NON** eseguire la Task 6 (prova end-to-end). La esegue il revisore: richiede `.env`, che è gitignored e quindi assente dal tuo worktree.
- **NON** eseguire la Task 8.
- **NON** fare merge su `main`, **NON** fare push forzati, **NON** riavviare container, **NON** toccare il sistema di trading, il DB o Redis.
- **NON** modificare nulla sotto `src/`, `config/` o `tests/`. Questa fase non ha codice.

---

## Protocollo di sessione

1. **Un commit per task**, con il messaggio già scritto nel piano. Non accorpare.
2. **Esegui ogni comando di verifica del piano** e mostra l'output reale. Se un atteso non torna, fermati e riporta: non aggirare il problema.
3. **Le due verifiche della Task 3 sono le più importanti dell'intero lavoro** e non vanno saltate:
   - `bash -n scripts/daily_alpha_miss_analysis.sh` deve stampare `SINTASSI OK`
   - il controllo `awk` deve stampare `OK: entrambe dentro il heredoc`

   Motivo: il testo che inserisci va dentro un heredoc bash. Se finisce **dopo** la riga di chiusura `PROMPT`, bash lo interpreta come comandi da eseguire invece che come testo del prompt. Questo script parte da cron **lunedì alle 10:00** e il suo modo tipico di fallire è il silenzio.
4. Al termine: `git push origin evidence/fase1-ledger` e fermati. **Niente PR, niente merge.**

## Punto di attenzione specifico sulla Task 3

Devi inserire due blocchi di testo dentro il heredoc del prompt (`_PROMPT_TEMPLATE=$(cat <<'PROMPT'` ... `PROMPT`):

- il blocco `FASE 0` va **subito prima** della riga `FASE 1 — RENDIMENTI DEL __DATE_TARGET__`
- il blocco `FASE FINALE` va **dopo** il blocco `OUTPUT FINALE` (dopo il punto 7) e **prima** di `REGOLE IMPORTANTI`

Il heredoc usa il delimitatore fra apici singoli (`<<'PROMPT'`), quindi **nessuna espansione shell avviene al suo interno**: le stringhe `__DATE_TARGET__` devono restare letterali nel sorgente. Vengono sostituite a runtime più in basso nello script. Non tentare di risolverle tu.

Devi anche cambiare la riga degli `allowedTools` (è **fuori** dal heredoc, verso la fine del file):

```bash
# da
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Write" -p "$_CLAUDE_PROMPT" 2>&1)
# a
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Read,Write,Edit" -p "$_CLAUDE_PROMPT" 2>&1)
```

Serve perché il protocollo richiede di leggere e riscrivere `findings.json`.

## Se qualcosa non torna

Fermati e riporta cosa hai trovato. Non inventare una soluzione alternativa: questo lavoro ha una scadenza reale (lunedì mattina) e un errore silenzioso costa più di un ritardo dichiarato.

## Restituzione

Quando hai finito, riporta:

1. I 4 commit prodotti (hash + messaggio)
2. L'output reale delle verifiche: `bash -n`, il controllo `awk` del heredoc, la validazione JSON di `findings.json`, e la Task 5 Step 1
3. Qualunque cosa ti abbia sorpreso o su cui hai dovuto decidere da solo
