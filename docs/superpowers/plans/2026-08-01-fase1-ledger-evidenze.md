# Fase 1 — Ledger delle evidenze (solo prompt + file) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendere contabili le segnalazioni dei due report giornalieri, in tempo per l'inizio dell'osservazione di lunedì 2026-08-03.

**Architecture:** Nessun codice. Un documento di carta pre-registrato, due file-ledger versionati, e i prompt dei due cron esistenti estesi con un protocollo di lettura/match/append. I due cron girano alle 10:00 e alle 14:30, quindi scrivono in sequenza e non serve alcun lock.

**Tech Stack:** Markdown, JSON, JSON Lines, heredoc bash. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-08-01-osservazione-evidenze-roadmap-pesata-design.md`

**Scadenza reale:** il cron `daily_alpha_miss_analysis.sh` gira lunedì 2026-08-03 alle 10:00. Se il prompt è rotto, l'osservazione comincia con un cron morto — e il suo modo tipico di fallire è il silenzio. La Task 6 è quindi obbligatoria, non opzionale.

---

## Struttura dei file

| file | responsabilità |
|---|---|
| `docs/evidence/OBSERVATION_CHARTER.md` | criteri pre-registrati: durata, esenzioni, soglie, domande di uscita. Sola lettura dopo la creazione, tranne il registro delle deroghe |
| `docs/evidence/findings.json` | ledger delle evidenze con ID stabili. Letto e appeso da entrambi i cron |
| `docs/evidence/market_daily.jsonl` | una riga per giorno di borsa. Scritto solo dal cron alpha-miss |
| `scripts/daily_alpha_miss_analysis.sh` | prompt esteso: fase 0 di lettura, fase finale di append su entrambi i ledger |
| `scripts/daily_analysis.sh` | prompt esteso: solo match dei findings, non scrive il ledger di mercato |

**Scostamento dalla spec, deliberato:** la spec descrive `findings.json` come array di record. Il piano usa un oggetto contenitore con `schema_version`, `prossimo_id` e `findings`. Motivo: il contatore rende l'assegnazione degli ID deterministica invece di richiedere a ogni sessione di scandire l'array per trovare il massimo — che è il tipo di operazione su cui un LLM sbaglia in silenzio, generando ID duplicati.

---

### Task 1: Creare la carta di osservazione

**Files:**
- Create: `docs/evidence/OBSERVATION_CHARTER.md`

- [ ] **Step 1: Creare la directory**

```bash
mkdir -p /home/stefano/Documents/Projects/Alembic/docs/evidence
```

- [ ] **Step 2: Scrivere la carta**

Contenuto integrale di `docs/evidence/OBSERVATION_CHARTER.md`:

```markdown
# Carta di osservazione — periodo di sola osservazione

Scritta il 2026-08-01, **prima** che l'osservazione cominci. Scopo unico: togliere a noi stessi la
possibilità di razionalizzare a posteriori.

Design di riferimento: `docs/superpowers/specs/2026-08-01-osservazione-evidenze-roadmap-pesata-design.md`

## Durata

- **Inizio:** lunedì 2026-08-03
- **Minimo:** 40 giorni di borsa
- **Scadenza attesa:** 2026-09-28 (contando il Labor Day del 2026-09-07). Da confermare con la
  `GetCalendarRequest` di Alpaca che `scripts/daily_alpha_miss_analysis.sh` già usa.
- **Controllo di metà periodo:** ~2026-08-28 (giorno 20). Non decide nulla: verifica solo che il
  ledger sia vivo.

Motivo dei 40 giorni: sotto quella soglia la finestra non contiene abbastanza giornate ad alta
dispersione per distinguere un difetto ricorrente da una coincidenza. Riscontro empirico: la
finestra 17-31 luglio 2026, 10 giorni di borsa, ha prodotto ±$100 su $110K — rumore.

## Cosa è congelato

Tutta la **taratura**: soglie, pesi, flag, cooldown, parametri di strategia.

## Cosa è esente

Solo i **difetti di correttezza**, con questo test da applicare a ogni candidato:

> Se non lo correggo, l'evidenza che raccolgo nelle prossime settimane è sbagliata?

Esempio che passa il test: il gate S4 disarmato (#163, corretto il 2026-07-30) — con il gate spento
il sistema comprava a soglie diverse da quelle di design, quindi ogni giorno osservato sarebbe stato
inutilizzabile. Esempio che non lo passa: un cooldown da tarare.

## Registro delle deroghe

Ogni eccezione applicata va annotata qui con data, motivo e commit.

| data | deroga | motivo | commit |
|---|---|---|---|
| 2026-08-01 | Script deterministico di precalcolo per il report alpha-miner (`scripts/alpha_miner_dossier.py`, fase 2) | Senza precalcolo i numeri della roadmap pesata sono ri-derivati ogni mattina da un LLM diverso, e la sessione rischia il timeout silenzioso che farebbe fallire l'osservazione stessa. È strumentazione, non un difetto di correttezza: quindi deroga. | nessuno: deroga registrata in anticipo, fase 2 non ancora rilasciata |
| 2026-08-01 | Riscrittura retroattiva di `market_daily.jsonl` all'innesto della fase 2 | Le righe scritte prima dell'innesto sono calcolate dalla sessione, quelle successive dallo script: lo script le ricalcola tutte perché la serie abbia una sola provenienza. Unica eccezione ammessa al "solo append"; **non si applica mai a `findings.json`**. | nessuno: deroga registrata in anticipo, fase 2 non ancora rilasciata |

## Soglie: cosa guadagna diritto a lavoro alla scadenza

| confidenza | definizione | soglia |
|---|---|---|
| **misurata** | perdita reale tracciabile a righe di DB | ≥ $100 cumulativi, ricorrenza irrilevante |
| **attribuita** | il trade esiste, il controfattuale è corto | ≥ $250 cumulativi **e** ≥ 5 giorni distinti |
| **congetturale** | alpha mancato, nessun trade avvenuto | ≥ $1.000 cumulativi **e** ≥ 10 giorni distinti |

L'asimmetria è voluta: un controfattuale deve valere dieci volte un bug misurato per pesare uguale.
Sugli alpha mancati non sappiamo se saremmo entrati, con che size, né quando saremmo usciti. Il
report del 2026-07-30 lo dimostra: MSFT catturato su un giorno a +15,5% ha prodotto $13,03
realizzati, perché l'uscita è scattata 2h45 dopo l'ingresso.

## Definizione: P&L economico

Termine usato nei criteri di uscita, da non confondere con il P&L realizzato. Per ogni posizione, il
movimento di prezzo attribuibile alla finestra: si marca dal close del primo giorno della finestra
(o dal prezzo di ingresso, se successivo) al prezzo corrente (o al prezzo di uscita, se anteriore),
moltiplicato per la quantità. Somma su tutte le posizioni, aperte e chiuse.

Serve perché il P&L realizzato di S1 è strutturalmente distorto: la sua regola d'uscita chiude solo
le posizioni che hanno perso rango momentum, cioè quelle scese, mentre le vincenti restano aperte
(#134). Sulla finestra 17-31 luglio la differenza era −$564 realizzati contro −$2,81 economici.

## Domande di uscita, pre-registrate

**1. Esiste alpha nella news editoriale su questa watchlist?**

Falsificazione: se alla scadenza `NO_NEWS` resta la causa di miss dominante in **≥60% dei giorni**
**e** il P&L economico di S4 sulla finestra resta dentro **±$200**, la risposta è no.

Conseguenza pre-registrata: S4 cambia fonte dati (vettori strutturati Tier A in
`docs/RESEARCH_SYNTHESIS_ALPHA_AND_TOOLING_2026-07-26.md`) oppure esce. Nessuna ulteriore taratura.
Precedente: `docs/S7_LIFECYCLE_HISTORY_2026-07-15.md`.

**2. S1 ha un edge una volta corretta la misura?**

Criterio: P&L **economico** di S1 sulla finestra confrontato con SPY, con la serie **realizzata
esplicitamente ignorata**.

**Esito legittimo previsto:** se alla scadenza nessun criterio è soddisfatto, la conclusione corretta
è **estendere la finestra**, non agire comunque.
```

- [ ] **Step 3: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add docs/evidence/OBSERVATION_CHARTER.md
git commit -m "docs(evidence): carta di osservazione pre-registrata

Criteri fissati prima dell'inizio: 40 giorni di borsa minimi, soglie per
livello di confidenza, due domande di uscita falsificabili con conseguenza
pre-registrata."
```

---

### Task 2: Inizializzare i due ledger

**Files:**
- Create: `docs/evidence/findings.json`
- Create: `docs/evidence/market_daily.jsonl`

- [ ] **Step 1: Creare findings.json**

Contenuto integrale:

```json
{
  "schema_version": 1,
  "prossimo_id": 1,
  "findings": []
}
```

- [ ] **Step 2: Creare market_daily.jsonl vuoto**

```bash
cd /home/stefano/Documents/Projects/Alembic
touch docs/evidence/market_daily.jsonl
```

- [ ] **Step 3: Verificare che il JSON sia valido**

```bash
cd /home/stefano/Documents/Projects/Alembic
python3 -c "import json; d=json.load(open('docs/evidence/findings.json')); print('ok', d['prossimo_id'], len(d['findings']))"
```

Atteso: `ok 1 0`

- [ ] **Step 4: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add docs/evidence/findings.json docs/evidence/market_daily.jsonl
git commit -m "docs(evidence): inizializza i due ledger

findings.json usa un contenitore con prossimo_id invece di un array nudo:
l'assegnazione degli ID resta deterministica senza chiedere a ogni sessione
di scandire l'array per trovare il massimo."
```

---

### Task 3: Estendere il prompt del cron alpha-miss

**Files:**
- Modify: `scripts/daily_alpha_miss_analysis.sh` (prompt heredoc che termina alla riga 181; riga `--allowedTools` alla 187)

- [ ] **Step 1: Ampliare allowedTools**

Il protocollo richiede di leggere e riscrivere `findings.json`. Oggi la sessione ha solo `Bash,Write`.

Sostituire nella riga 187:

```bash
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Write" -p "$_CLAUDE_PROMPT" 2>&1)
```

con:

```bash
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Read,Write,Edit" -p "$_CLAUDE_PROMPT" 2>&1)
```

- [ ] **Step 2: Inserire la fase 0 nel prompt**

Nel heredoc, subito **prima** della riga `FASE 1 — RENDIMENTI DEL __DATE_TARGET__`, inserire:

```
FASE 0 — LEGGI IL LEDGER PRIMA DI ANALIZZARE
Leggi docs/evidence/findings.json. Contiene le evidenze già note, ciascuna con un id stabile
(F-001, F-002, ...), un titolo e le occorrenze già registrate. Tienile presenti per tutta
l'analisi: alla fine ogni segnalazione che produrrai andrà agganciata a una di queste o
registrata come nuova.
Leggi anche docs/evidence/OBSERVATION_CHARTER.md: sei dentro un periodo di sola osservazione,
quindi NON proporre tarature né fix, solo evidenza.
```

- [ ] **Step 3: Inserire la fase finale nel prompt**

Nel heredoc, subito **dopo** il blocco `OUTPUT FINALE` (dopo il punto 7 che vieta di proporre fix) e
**prima** di `REGOLE IMPORTANTI`, inserire:

```
FASE FINALE — AGGIORNA I DUE LEDGER

A) Appendi UNA riga a docs/evidence/market_daily.jsonl (JSON Lines: una riga sola, niente
   indentazione, newline finale). Schema esatto:

   {"data":"__DATE_TARGET__","spy":0.0,"qqq":0.0,"dispersione_sigma":0.0,
    "mover_3pct":0,"up":0,"down":0,"watchlist_zero_news":0,"tema":"",
    "miss":{"NO_NEWS":0,"THIN_NEUTRAL":0,"WRONG_SIGN":0,"FILTERED":0,"OUT_OF_STRATEGY_SCOPE":0},
    "catturati":0,
    "book":{"equity":0.0,"realizzato":0.0,"mtm":null,"s1_realizzato":0.0,"s4_realizzato":0.0}}

   Definizioni:
   - spy / qqq: rendimento giornaliero (close vs close precedente), come frazione non percentuale.
   - dispersione_sigma: deviazione standard cross-sectional dei rendimenti dei 96 simboli.
   - mover_3pct / up / down: quanti simboli con |return| >= 3%, e la ripartizione.
   - watchlist_zero_news: quanti dei 96 simboli hanno ZERO righe in news_log quel giorno.
   - tema: una riga di testo, la stessa lettura della tua sezione "Pattern osservato".
     Ammesso "non chiaro".
   - miss: i conteggi della tua tabella dei miss classificati.
   - catturati: quanti mover erano in portafoglio o sono stati tradati.
   - book: equity di fine giornata da Alpaca; realizzato = somma net_pnl dei trade chiusi quel
     giorno; s1_realizzato / s4_realizzato = stessa somma per strategia; mtm = variazione
     mark-to-market del book aperto se la calcoli, altrimenti null.
   Se un valore non lo puoi calcolare, scrivi null. NON inventarlo e NON omettere la chiave.
   Se esiste già una riga con la stessa "data", NON aggiungerne una seconda: significa che il
   report è stato rigenerato. In quel caso lascia il file com'è e segnalalo a stdout.

B) Aggiorna docs/evidence/findings.json per OGNI voce della tua sezione di segnalazioni.
   Per ciascuna, decidi se è già nel ledger:
   - SE corrisponde a un finding esistente: aggiungi UNA voce al suo array "occorrenze" e
     ricalcola "costo_cumulato_usd" come somma di occorrenze[].costo_usd.
   - SE è genuinamente nuova: crea un record con id "F-NNN" dove NNN è il valore corrente di
     "prossimo_id" formattato a 3 cifre, poi incrementa "prossimo_id" di 1.

   Schema di un record:
   {"id":"F-001","titolo":"","tipo":"difetto|alpha_miss|osservazione",
    "confidenza":"misurata|attribuita|congetturale","primo_avvistamento":"__DATE_TARGET__",
    "occorrenze":[{"data":"__DATE_TARGET__","costo_usd":0.0,"nota":"","fonte":""}],
    "costo_cumulato_usd":0.0,"stato":"aperto","issue":null}

   Livelli di confidenza:
   - misurata: perdita reale tracciabile a righe di DB.
   - attribuita: il trade esiste, il controfattuale è corto.
   - congetturale: alpha mancato, nessun trade avvenuto. TUTTI i miss sono congetturali.
   Il campo "fonte" deve puntare al report e alla sezione che giustifica l'occorrenza, es.
   "ALPHA_MISS_REPORT___DATE_TARGET__.md §7".

   DUE REGOLE VINCOLANTI:
   1. SOLO APPEND. Non modificare né cancellare occorrenze già presenti, né cambiare il titolo o
      l'id di un finding esistente. Puoi solo aggiungere occorrenze, creare record nuovi, e
      ricalcolare costo_cumulato_usd.
   2. NEL DUBBIO, AGGANCIA. Creare un id nuovo va giustificato nella nota. Due record duplicati si
      fondono a fine periodo; un'evidenza spezzata in cinque id diversi ha ricorrenza 1 ciascuno e
      sparisce sotto tutte le soglie — errore silenzioso e non recuperabile.

   Le CAUSE di miss (NO_NEWS, THIN_NEUTRAL, ...) NON diventano findings: sono già contate in
   market_daily.jsonl. Diventa un finding solo un'affermazione strutturale, es. "39 simboli su 96
   non hanno copertura news in un giorno tipico".

C) Committa i due file:
   git add docs/evidence/findings.json docs/evidence/market_daily.jsonl
   git commit -m "evidence: ledger __DATE_TARGET__"
   Se non c'è nulla da committare, non forzare il commit.

D) Nella sezione di segnalazioni del report, ogni voce deve riportare il suo id fra parentesi
   quadre a inizio riga, es. "[F-004] Sembra un difetto — ...".
```

- [ ] **Step 4: Verificare la sintassi bash**

```bash
cd /home/stefano/Documents/Projects/Alembic
bash -n scripts/daily_alpha_miss_analysis.sh && echo "SINTASSI OK"
```

Atteso: `SINTASSI OK`

- [ ] **Step 5: Verificare che il testo nuovo sia dentro il heredoc**

Il rischio è di averlo inserito dopo la riga di chiusura `PROMPT`, dove sarebbe interpretato come
comandi bash. Il numero di riga di `FASE 0` e `FASE FINALE` deve essere **minore** di quello della
riga che chiude il heredoc.

```bash
cd /home/stefano/Documents/Projects/Alembic
awk '/^FASE 0 —/{f0=NR} /^FASE FINALE —/{ff=NR} /^PROMPT$/{p=NR} END{print "FASE0="f0" FASEFINALE="ff" chiusura="p; if(f0<p && ff<p) print "OK: entrambe dentro il heredoc"; else print "ERRORE: fuori dal heredoc"}' scripts/daily_alpha_miss_analysis.sh
```

Atteso: l'ultima riga stampata è `OK: entrambe dentro il heredoc`

- [ ] **Step 6: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add scripts/daily_alpha_miss_analysis.sh
git commit -m "feat(evidence): protocollo ledger nel cron alpha-miss

Fase 0 di lettura del ledger, fase finale di append su market_daily.jsonl e
findings.json con match degli id. Aggiunti Read ed Edit agli allowedTools:
findings.json richiede read-modify-write."
```

---

### Task 4: Estendere il prompt del cron forensic

**Files:**
- Modify: `scripts/daily_analysis.sh` (prompt heredoc che termina alla riga 353; riga `--allowedTools` alla 361)

Il forensic fa **solo** il match dei findings: non scrive `market_daily.jsonl`, che è di competenza
esclusiva del cron alpha-miss.

- [ ] **Step 1: Ampliare allowedTools**

Sostituire nella riga 361:

```bash
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Write" -p "$_CLAUDE_PROMPT" 2>&1)
```

con:

```bash
ANALYSIS_OUTPUT=$(claude --allowedTools "Bash,Read,Write,Edit" -p "$_CLAUDE_PROMPT" 2>&1)
```

- [ ] **Step 2: Inserire il protocollo nel prompt**

Nel heredoc, subito **prima** della riga `REGOLE IMPORTANTI`, inserire:

```
LEDGER DELLE EVIDENZE

Prima di iniziare l'analisi leggi docs/evidence/findings.json e
docs/evidence/OBSERVATION_CHARTER.md. Sei dentro un periodo di sola osservazione: NON proporre
tarature. I remediation ticket che la sezione precedente ti chiede restano ammessi solo per
difetti di CORRETTEZZA, cioè quelli che, se non corretti, rendono sbagliata l'evidenza raccolta
nelle settimane successive.

Al termine, per OGNI anomalia che hai riportato, aggiorna docs/evidence/findings.json:
- SE corrisponde a un finding già presente: aggiungi UNA voce al suo array "occorrenze" e
  ricalcola "costo_cumulato_usd" come somma di occorrenze[].costo_usd.
- SE è genuinamente nuova: crea un record con id "F-NNN" dove NNN è il valore corrente di
  "prossimo_id" formattato a 3 cifre, poi incrementa "prossimo_id" di 1.

Schema di un record:
{"id":"F-001","titolo":"","tipo":"difetto|alpha_miss|osservazione",
 "confidenza":"misurata|attribuita|congetturale","primo_avvistamento":"__DATE_TARGET__",
 "occorrenze":[{"data":"__DATE_TARGET__","costo_usd":0.0,"nota":"","fonte":""}],
 "costo_cumulato_usd":0.0,"stato":"aperto","issue":null}

Livelli di confidenza: misurata = perdita reale tracciabile a righe di DB; attribuita = il trade
esiste e il controfattuale è corto; congetturale = nessun trade avvenuto.
Il campo "fonte" punta al report e alla sezione, es. "FORENSIC_DAILY_REPORT___DATE_TARGET__.md".

DUE REGOLE VINCOLANTI:
1. SOLO APPEND. Non modificare né cancellare occorrenze già presenti, né cambiare titolo o id di
   un finding esistente.
2. NEL DUBBIO, AGGANCIA. Creare un id nuovo va giustificato nella nota. Un'evidenza spezzata in
   più id ha ricorrenza 1 ciascuno e sparisce sotto tutte le soglie.

Poi committa:
   git add docs/evidence/findings.json
   git commit -m "evidence: forensic __DATE_TARGET__"
Se non c'è nulla da committare, non forzare il commit.

Nel report, ogni anomalia riportata deve avere il suo id fra parentesi quadre a inizio riga.
```

- [ ] **Step 3: Verificare la sintassi bash**

```bash
cd /home/stefano/Documents/Projects/Alembic
bash -n scripts/daily_analysis.sh && echo "SINTASSI OK"
```

Atteso: `SINTASSI OK`

- [ ] **Step 4: Verificare che il testo nuovo sia dentro il heredoc**

```bash
cd /home/stefano/Documents/Projects/Alembic
awk '/^LEDGER DELLE EVIDENZE$/{l=NR} /^PROMPT$/{p=NR} END{print "LEDGER="l" chiusura="p; if(l<p) print "OK: dentro il heredoc"; else print "ERRORE: fuori dal heredoc"}' scripts/daily_analysis.sh
```

Atteso: l'ultima riga stampata è `OK: dentro il heredoc`

- [ ] **Step 5: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add scripts/daily_analysis.sh
git commit -m "feat(evidence): protocollo di match dei findings nel cron forensic

Solo findings.json: market_daily.jsonl resta di competenza esclusiva del
cron alpha-miss, che gira per primo."
```

---

### Task 5: Verificare la sostituzione dei placeholder

Il protocollo che ho inserito usa `__DATE_TARGET__` dentro il testo. Va verificato che la
sostituzione runtime lo raggiunga anche nelle parti nuove: se restasse letterale, la sessione
scriverebbe `__DATE_TARGET__` dentro il ledger.

**Files:** nessuna modifica, solo verifica.

- [ ] **Step 1: Simulare la sostituzione sull'alpha-miss**

```bash
cd /home/stefano/Documents/Projects/Alembic
_T=$(sed -n "/^_PROMPT_TEMPLATE=\$(cat <<'PROMPT'\$/,/^PROMPT\$/p" scripts/daily_alpha_miss_analysis.sh)
echo "${_T//__DATE_TARGET__/2026-07-31}" | grep -c "__DATE_TARGET__"
```

Atteso: `0`

- [ ] **Step 2: Simulare la sostituzione sul forensic**

```bash
cd /home/stefano/Documents/Projects/Alembic
_T=$(sed -n "/^_PROMPT_TEMPLATE=\$(cat <<'PROMPT'\$/,/^PROMPT\$/p" scripts/daily_analysis.sh)
echo "${_T//__DATE_TARGET__/2026-07-31}" | grep -c "__DATE_TARGET__"
```

Atteso: `0`

Se uno dei due stampa un numero maggiore di zero, un `__DATE_TARGET__` è rimasto: individua la riga
con `grep -n "__DATE_TARGET__"` sull'output e correggi.

---

### Task 6: Prova end-to-end reale (obbligatoria)

Oggi è sabato 2026-08-01, quindi lo script punta all'ultimo giorno di borsa: **venerdì 2026-07-31**,
il cui report non esiste ancora. Eseguirlo a mano è insieme il test end-to-end e la produzione di un
report mancante.

Questa task **non è opzionale**: lunedì alle 10:00 il cron gira da solo, e se il prompt è rotto
fallisce in silenzio.

**Files:** nessuna modifica. Produce `docs/ALPHA_MISS_REPORT_2026-07-31.md` e popola i due ledger.

- [ ] **Step 1: Eseguire lo script**

```bash
cd /home/stefano/Documents/Projects/Alembic
./scripts/daily_alpha_miss_analysis.sh
```

Richiede diversi minuti e invia due messaggi Telegram (comportamento normale).

- [ ] **Step 2: Verificare che il report esista**

```bash
cd /home/stefano/Documents/Projects/Alembic
test -f docs/ALPHA_MISS_REPORT_2026-07-31.md && wc -c docs/ALPHA_MISS_REPORT_2026-07-31.md
```

Atteso: il file esiste e supera i 5000 byte.

- [ ] **Step 3: Verificare la riga di mercato**

```bash
cd /home/stefano/Documents/Projects/Alembic
python3 -c "
import json
righe=[json.loads(l) for l in open('docs/evidence/market_daily.jsonl') if l.strip()]
print('righe:', len(righe))
r=righe[-1]
attese={'data','spy','qqq','dispersione_sigma','mover_3pct','up','down','watchlist_zero_news','tema','miss','catturati','book'}
mancanti=attese-set(r)
print('data:', r['data'])
print('chiavi mancanti:', mancanti or 'nessuna')
print('placeholder non sostituiti:', [k for k,v in r.items() if isinstance(v,str) and '__' in v] or 'nessuno')
"
```

Atteso: `righe: 1`, `data: 2026-07-31`, `chiavi mancanti: nessuna`, `placeholder non sostituiti: nessuno`

- [ ] **Step 4: Verificare il ledger dei findings**

```bash
cd /home/stefano/Documents/Projects/Alembic
python3 -c "
import json
d=json.load(open('docs/evidence/findings.json'))
print('prossimo_id:', d['prossimo_id'], '| findings:', len(d['findings']))
for f in d['findings']:
    print(' ', f['id'], '|', f['confidenza'], '| occorrenze:', len(f['occorrenze']), '|', f['titolo'][:60])
    assert f['id'].startswith('F-'), 'id malformato'
    assert f['confidenza'] in ('misurata','attribuita','congetturale'), 'confidenza non valida'
    assert abs(f['costo_cumulato_usd'] - sum(o['costo_usd'] for o in f['occorrenze'])) < 0.01, 'costo_cumulato non torna'
print('coerenza OK')
"
```

Atteso: `prossimo_id` maggiore di 1, almeno un finding, e `coerenza OK`.

Se `findings` è vuoto: verifica se il report del 31 contiene davvero segnalazioni. Se ne contiene e
il ledger è vuoto, il protocollo non è stato eseguito — rileggi la Task 3 Step 3.

- [ ] **Step 5: Verificare che gli id compaiano nel report**

```bash
cd /home/stefano/Documents/Projects/Alembic
grep -c "\[F-[0-9]\{3\}\]" docs/ALPHA_MISS_REPORT_2026-07-31.md
```

Atteso: un numero pari al numero di segnalazioni del report (almeno 1).

- [ ] **Step 6: Commit di quanto prodotto**

La sessione dovrebbe aver già committato i ledger. Verificare e completare:

```bash
cd /home/stefano/Documents/Projects/Alembic
git status --short docs/evidence docs/ALPHA_MISS_REPORT_2026-07-31.md
git add docs/evidence docs/ALPHA_MISS_REPORT_2026-07-31.md
git commit -m "evidence: prova end-to-end del protocollo ledger sul 2026-07-31" || echo "niente da committare"
```

---

### Task 7: Programmare i due promemoria di scadenza

La spec prevede un controllo di metà periodo (§3.5) e una sintesi finale (§3.6), entrambi a
settimane di distanza. Senza un promemoria si dimenticano, e il controllo di metà periodo esiste
proprio per intercettare un ledger morto: se salta, salta la sua ragione d'essere.

Il repo ha già il meccanismo adatto: `scripts/deadline_reminders.conf`, letto da
`scripts/deadline_reminder.sh`, che rimanda ogni giorno alle 09:11 e a ogni boot finché l'operatore
non fa l'ack. Formato: `id|due_date(YYYY-MM-DD)|message`, una riga per scadenza.

**Files:**
- Modify: `scripts/deadline_reminders.conf` (append di due righe in fondo)

- [ ] **Step 1: Appendere le due righe**

Aggiungere in fondo al file, una per riga, senza spezzarle su più righe:

```
OSS_MIDPOINT|2026-08-28|Osservazione giorno 20 — controllo di SALUTE del ledger, NON decide nulla. Verifica: (a) docs/evidence/market_daily.jsonl ha una riga per ogni giorno di borsa dal 2026-08-03; (b) docs/evidence/findings.json e' stato toccato di recente. Se il ledger e' fermo, il cron sta fallendo in silenzio e va sistemato subito: scoprirlo al giorno 40 costerebbe l'intera finestra. Carta: docs/evidence/OBSERVATION_CHARTER.md. Ack: bash /home/stefano/Documents/Projects/Alembic/scripts/ack_deadline.sh OSS_MIDPOINT
OSS_SCADENZA|2026-09-28|Osservazione giorno 40 — SCADENZA. Produrre docs/evidence/WEIGHTED_ROADMAP_2026-09-28.md applicando MECCANICAMENTE le soglie della carta (misurata >=$100; attribuita >=$250 e >=5 giorni; congetturale >=$1000 e >=10 giorni), rispondere alle due domande di uscita pre-registrate, ed elencare esplicitamente cio' che NON e' passato e viene lasciato cadere. Se nessun criterio e' soddisfatto l'esito legittimo e' ESTENDERE, non agire comunque. Carta: docs/evidence/OBSERVATION_CHARTER.md. Ack: bash /home/stefano/Documents/Projects/Alembic/scripts/ack_deadline.sh OSS_SCADENZA
```

- [ ] **Step 2: Verificare il formato**

Ogni riga deve avere esattamente due separatori `|` e una data valida.

```bash
cd /home/stefano/Documents/Projects/Alembic
awk -F'|' '/^OSS_/{print NF-1" campi-1 | id="$1" | data="$2}' scripts/deadline_reminders.conf
```

Atteso: due righe, entrambe con `2 campi-1`, id `OSS_MIDPOINT` con data `2026-08-28` e
`OSS_SCADENZA` con data `2026-09-28`.

- [ ] **Step 3: Verificare che lo script non si rompa**

```bash
cd /home/stefano/Documents/Projects/Alembic
bash -n scripts/deadline_reminder.sh && ./scripts/deadline_reminder.sh && echo "ESECUZIONE OK"
```

Atteso: `ESECUZIONE OK`. Nessuna delle due nuove scadenze è ancora dovuta (2026-08-28 e 2026-09-28
sono future), quindi non deve partire alcun messaggio per `OSS_*`.

- [ ] **Step 4: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add scripts/deadline_reminders.conf
git commit -m "chore(evidence): promemoria per il controllo di meta periodo e la scadenza

Il controllo del giorno 20 esiste per intercettare un ledger morto: senza
promemoria si dimentica, e scoprire al giorno 40 che il cron era fermo dal
giorno 3 costerebbe l'intera finestra."
```

---

### Task 8: Annotare l'esito nella carta

**Files:**
- Modify: `docs/evidence/OBSERVATION_CHARTER.md`

- [ ] **Step 1: Aggiungere la sezione di stato in fondo alla carta**

```markdown
## Stato

| data | evento |
|---|---|
| 2026-08-01 | Carta scritta e committata. Ledger inizializzati. Protocollo attivo su entrambi i cron. Prova end-to-end eseguita sul 2026-07-31. Promemoria OSS_MIDPOINT e OSS_SCADENZA programmati. |
| 2026-08-03 | Inizio del periodo di osservazione. |
```

- [ ] **Step 2: Commit**

```bash
cd /home/stefano/Documents/Projects/Alembic
git add docs/evidence/OBSERVATION_CHARTER.md
git commit -m "docs(evidence): registra lo stato di attivazione nella carta"
```

---

## Cosa NON è in questa fase

- Lo script `scripts/alpha_miner_dossier.py` e le sezioni analitiche nuove del report (falsi
  positivi, qualità di cattura, aggregazioni). Sono la fase 2, con il loro piano.
- Il recupero retroattivo dei ~20 report esistenti: la spec lo esclude, il ledger parte vuoto.
- Qualunque modifica al sistema di trading.

## Verifica finale della fase

- [ ] `bash -n` passa su entrambi gli script
- [ ] `findings.json` è JSON valido e contiene almeno un record dopo la prova end-to-end
- [ ] `market_daily.jsonl` contiene una riga per il 2026-07-31 con tutte le chiavi
- [ ] Il report del 2026-07-31 esiste e le sue segnalazioni portano gli id
- [ ] La carta è committata e non modificata dopo l'inizio dell'osservazione, tranne il registro
      delle deroghe e la sezione di stato
