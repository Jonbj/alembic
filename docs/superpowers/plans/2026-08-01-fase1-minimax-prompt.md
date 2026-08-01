# Fase 1 ledger evidenze — Prompt di esecuzione per Minimax

> **Per l'agente esecutore:** non hai contesto pregresso su questo repo. Leggi questo documento una volta, poi esegui esattamente ciò che dice. NON improvvisare oltre la spec. Un revisore umano controlla prima del merge: il tuo compito è eseguire e restituire, non mergiare né deployare.

**Repo:** `/home/stefano/Documents/Projects/Alembic` — sistema di trading algoritmico LLM in **paper trading**.

**Il tuo worktree (NON la directory principale):**

```
/home/stefano/Documents/Projects/Alembic/.worktrees/evidence-forensic
```

**Branch:** `evidence/fase1-forensic-deadlines` (già creato, già pushato, già allineato). Lavora SOLO lì dentro.

⚠️ **La directory principale del repo è usata in questo momento da altri agenti su altri branch.** Non toccarla, non fare `git checkout` lì, non fare `cd` fuori dal tuo worktree per operazioni git.

**Il piano che devi eseguire:** `docs/superpowers/plans/2026-08-01-fase1-ledger-evidenze.md` (già presente nel tuo worktree). Contiene 8 task; **a te ne toccano 3**.

---

## Cosa devi fare: Task 4, 5 (solo la parte forensic), 7

| task | cosa | file |
|---|---|---|
| **4** | Protocollo di match dei findings nel cron forensic | modifica `scripts/daily_analysis.sh` |
| **5** | Verifica sostituzione placeholder | solo **Step 2** (forensic). Lo Step 1 è di un altro agente |
| **7** | Due promemoria di scadenza | modifica `scripts/deadline_reminders.conf` (append di 2 righe) |

Il piano contiene il **testo esatto** da inserire. Copialo alla lettera: non riscriverlo con parole tue, non riformattarlo, non "migliorarlo". Quei testi finiscono dentro prompt di sessioni automatiche e ogni parola è stata scelta.

## Cosa NON devi fare

- **NON** toccare `scripts/daily_alpha_miss_analysis.sh` (Task 3), né creare `docs/evidence/OBSERVATION_CHARTER.md`, `docs/evidence/findings.json`, `docs/evidence/market_daily.jsonl` (Task 1 e 2): sono di un altro agente che lavora in parallelo. Se li tocchi, creiamo un conflitto.
- **NON** eseguire le Task 1, 2, 3, 6, 8.
- **NON** fare merge su `main`, **NON** fare push forzati, **NON** riavviare container, **NON** toccare il sistema di trading, il DB o Redis.
- **NON** modificare nulla sotto `src/`, `config/` o `tests/`. Questa fase non ha codice.

---

## Protocollo di sessione

1. **Un commit per task**, con il messaggio già scritto nel piano. Non accorpare.
2. **Esegui ogni comando di verifica del piano** e mostra l'output reale. Se un atteso non torna, fermati e riporta: non aggirare il problema.
3. **Le due verifiche della Task 4 non vanno saltate:**
   - `bash -n scripts/daily_analysis.sh` deve stampare `SINTASSI OK`
   - il controllo `awk` deve stampare `OK: dentro il heredoc`

   Motivo: il testo che inserisci va dentro un heredoc bash. Se finisce **dopo** la riga di chiusura `PROMPT`, bash lo interpreta come comandi da eseguire invece che come testo del prompt. Questo script parte da cron ogni giorno feriale alle 14:30.
4. Al termine: `git push origin evidence/fase1-forensic-deadlines` e fermati. **Niente PR, niente merge.**

## Punto di attenzione sulla Task 4

Il blocco `LEDGER DELLE EVIDENZE` va inserito dentro il heredoc (`_PROMPT_TEMPLATE=$(cat <<'PROMPT'` ... `PROMPT`), **subito prima** della riga `REGOLE IMPORTANTI`.

Il heredoc usa il delimitatore fra apici singoli, quindi **nessuna espansione shell avviene al suo interno**: le stringhe `__DATE_TARGET__` devono restare letterali nel sorgente. Vengono sostituite a runtime più in basso. Non tentare di risolverle tu.

Devi anche cambiare la riga degli `allowedTools` (è **fuori** dal heredoc, verso la fine del file):

```bash
# da
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Write" -p "$_CLAUDE_PROMPT" 2>&1)
# a
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Read,Write,Edit" -p "$_CLAUDE_PROMPT" 2>&1)
```

Nota: il cron forensic aggiorna **solo** `findings.json`. Non deve scrivere `market_daily.jsonl`, che è di competenza esclusiva del cron alpha-miss (gira alle 10:00, prima del forensic delle 14:30).

## Deviazione obbligatoria dal piano, Task 7 Step 3

Il piano dice di eseguire `./scripts/deadline_reminder.sh` per verificare. **Non farlo dal tuo worktree.**

Motivo: quello script ha il percorso del progetto **cablato**:

```bash
PROJECT_DIR="/home/stefano/Documents/Projects/Alembic"
```

Eseguito dal tuo worktree leggerebbe comunque il file di configurazione della directory **principale**, non il tuo — quindi non verificherebbe la tua modifica, e potrebbe mandare messaggi Telegram basati su una configurazione che non è la tua.

Fai invece solo queste due verifiche:

```bash
cd /home/stefano/Documents/Projects/Alembic/.worktrees/evidence-forensic
bash -n scripts/deadline_reminder.sh && echo "SINTASSI OK"
awk -F'|' '/^OSS_/{print NF-1" campi-1 | id="$1" | data="$2}' scripts/deadline_reminders.conf
```

Atteso: `SINTASSI OK`, poi due righe con `2 campi-1`, `OSS_MIDPOINT` con data `2026-08-28` e `OSS_SCADENZA` con data `2026-09-28`.

L'esecuzione vera la fa il revisore dalla directory principale, dopo il merge.

## Se qualcosa non torna

Fermati e riporta cosa hai trovato. Non inventare una soluzione alternativa: questo lavoro ha una scadenza reale (lunedì mattina) e un errore silenzioso costa più di un ritardo dichiarato.

## Restituzione

Quando hai finito, riporta:

1. I 3 commit prodotti (hash + messaggio)
2. L'output reale delle verifiche: `bash -n`, il controllo `awk` del heredoc, il controllo del formato delle scadenze, e la Task 5 Step 2
3. Qualunque cosa ti abbia sorpreso o su cui hai dovuto decidere da solo
