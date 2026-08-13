# S4 — decisione sull'orizzonte economico: prompt per analisi esterna

**Data:** 2026-08-13 · **Issue di riferimento:** [#242](https://github.com/Jonbj/alembic/issues/242)
· **Precedente:** `docs/S4_PROMPT_ANALISI_ESTERNA_2026-08-03.md` (analisi diversa, stesso metodo)

Questo documento è **autosufficiente**: contiene tutto il necessario per rispondere senza accesso al
repo o al database. È scritto per essere sottoposto a più modelli in parallelo, indipendentemente,
e poi confrontato.

> **Istruzione ai modelli che lo ricevono.** Non rispondere per consenso col documento. Se pensi che
> la domanda sia mal posta, dillo e riformulala. Se pensi che i dati non bastino a rispondere, dillo
> e indica cosa servirebbe. Una risposta «non decidibile con questi dati, ecco perché» è un esito
> legittimo e preferibile a una scelta forzata. La sezione 6 elenca apposta i punti deboli
> dell'evidenza: usali.

---

## 1. La domanda, in una riga

**Che orizzonte economico deve avere S4** — intraday, 1–3 giorni, o nessuno (shadow) — dato che oggi
non ne ha nessuno *dichiarato* e quello *effettivo* è un sottoprodotto della cadenza di
pubblicazione delle fonti di notizie?

Non è una domanda di taratura. Le tre opzioni sono tre strategie diverse, con tre infrastrutture
dati diverse e tre metriche di validazione diverse.

---

## 2. Il sistema, in breve

**Alembic** è un sistema di trading algoritmico su azioni USA che segue il paradigma *Alpha Miner*:
gli LLM non sono mai nel percorso di esecuzione. Girano offline, producono segnali di sentiment che
vengono scritti su PostgreSQL/Redis, e il motore di esecuzione legge i segnali già calcolati.

- Esecuzione: **Alpaca**, paper trading, ~110.000 $ di NAV
- Universo: watchlist fissa di **96 simboli** large-cap USA
- Ciclo di portafoglio: ogni **15 minuti**, solo in RTH (14:00–21:00 UTC circa), 24 cicli/giorno
- **Long-only.** Non si shorta. Un segnale ribassista può solo chiudere una posizione, mai aprirne una
- Due sleeve attive: **S1** (momentum cross-sectional, 50% del portafoglio) e **S4** (news-driven, 10%)

### S4 nel dettaglio

Overlay tattico che compra i titoli su cui l'ensemble di LLM produce il sentiment più forte.

**Pipeline:** articoli di news (principalmente Benzinga via Alpaca, più altre fonti) → estrazione
ticker → ensemble di 2 LLM (`glm52` + `gptoss`, via Ollama Cloud) → punteggio
`score = polarity × confidence` con `polarity ∈ [−1,+1]` e `confidence ∈ [0,1]` → tabella
`sentiment_signals` → il ciclo di portafoglio ogni 15 min legge, filtra, ordina e alloca.

**Parametri effettivi** (`src/strategies/s4/config.py`):

| parametro | valore | ruolo |
|---|---|---|
| `bucket_pct` | 0.10 | quota di portafoglio della sleeve |
| `n_top` | 5 | quanti titoli tenere per ciclo |
| `fixed_slot_sizing` | `true` | ogni titolo scelto pesa 1/5 del bucket = **2% del portafoglio**; gli slot vuoti restano non impiegati |
| `max_signal_age_hours` | **4** | oltre le 4 ore il segnale è scartato — **misurate in ore solari, non di mercato** |
| `signals_lookback_hours` | 96 | finestra di lettura dal DB |
| `min_score` / `min_confidence` | 0.10 / 0.30 | prefiltri del ranker, **non** la soglia d'ordine |
| soglia d'ordine | **0.30** | `feedback:entry_threshold` in Redis, in **valore assoluto** |
| `rebalance_frequency` | `DAILY` | **dichiarata ma non applicata**: S4 è escluso dal clock, quindi ribilancia di fatto ogni 15 minuti |

**Come nasce un'uscita.** Non esiste una regola d'uscita esplicita. La posizione viene chiusa quando
il peso target del simbolo scende a zero nel combiner, il che accade in quattro modi:

1. `below_entry_gate` — il punteggio è sceso sotto 0,30, **restando positivo**
2. `expired` — il segnale ha superato le 4 ore di orologio da parete
3. `unknown` (difetto QS-07/FIX-D) — un filtro di freschezza dentro la strategia riscarta segnali che
   lo scheduler aveva deliberatamente preservato per mantenere aperta la posizione
4. `whipsaw` — il segnale c'è ma non guida una posizione

**In nessuno dei quattro casi il modello ha detto «vendi».**

---

## 3. I numeri misurati

Tutti verificati per query diretta su PostgreSQL. Nessuno stimato salvo dove indicato.

### 3.1 La finestra analizzata: 5 sedute, 2026-08-06 → 2026-08-12

| sleeve | chiusure | in perdita | netto | costi | tenuta mediana |
|---|---:|---:|---:|---:|---:|
| S4 | 9 | **8** | **−89,12 $** | 11,00 | 1h45 |
| S1 | 7 | 4 | −4,38 $ | 2,75 | ~5 giorni |

Le nove uscite S4, integrali:

| data | sym | ingresso | uscita | tenuta | netto | meccanismo |
|---|---|---|---|---:|---:|---|
| 08-06 | MSFT | 14:22 | 16:07 | 1h45 | −7,79 | whipsaw |
| 08-06 | SPCX | 14:37 | 18:52 | 4h15 | −34,98 | expired |
| 08-10 | NVDA | 17:22 | 19:07 | 1h45 | +1,29 | below_entry_gate |
| 08-10 | META | 17:37 | 19:22 | 1h45 | −3,57 | below_entry_gate |
| 08-10 | MSFT | 17:52 | 19:37 | 1h45 | −2,37 | below_entry_gate |
| 08-11 | SONY | 08-10 16:07 | 14:22 | 22h15 | −5,47 | QS-07/FIX-D |
| 08-11 | HOOD | 14:07 | 18:22 | 4h15 | −8,82 | QS-07/FIX-D |
| 08-12 | IBM | 08-11 19:07 | 14:22 | 19h15 | −26,47 | QS-07/FIX-D |
| 08-12 | NVDA | 17:22 | 19:07 | 1h45 | −0,93 | below_entry_gate |

Sei uscite su nove cadono a **1h45 o 4h15 esatte** dall'ingresso: 7 o 17 cicli da 15 minuti.

Il NAV complessivo nella stessa finestra è **+221 $**: la sleeve passiva S1 ha compensato in
mark-to-market quello che S4 ha perso in realizzato.

### 3.2 ⚠️ Il contesto storico, che ribalta la lettura di cui sopra

**Questa è la sezione più importante del documento e va letta prima di concludere qualsiasi cosa.**

Sulla vita intera di S4 (dal 2026-07-13, quando l'attribuzione di sleeve è affidabile):

| sleeve | chiusure | vincenti | netto | costi | tenuta mediana |
|---|---:|---:|---:|---:|---:|
| **S4** | **81** | **43 (53%)** | **+209,11 $** | 99,02 | **4h15** |
| S1 | 54 | 7 (13%) | −768,60 $ | 40,40 | 24h |

Per settimana:

| settimana | n | vincenti | netto |
|---|---:|---:|---:|
| 2026-07-13 | 21 | 12 | +173,49 |
| 2026-07-20 | 14 | 7 | −97,55 |
| 2026-07-27 | 20 | 12 | +110,41 |
| 2026-08-03 | 17 | 10 | +116,32 |
| **2026-08-10** | **9** | **2** | **−93,55** |

**La finestra di 5 giorni analizzata è la settimana peggiore nella storia di S4, con n=9.** Sul
realizzato di lungo periodo S4 è in utile e vince il 53% delle volte, mentre S1 — la sleeve
«sana» — perde 769 $ e vince il 13% (P&L realizzato avversamente selezionato: S1 chiude solo ciò
che è sceso e tiene aperto ciò che è salito, quindi il suo realizzato non è confrontabile).

Chi legge questo documento **non deve** trattare i 9 trade come rappresentativi. Il difetto
*meccanico* descritto alla §2 è reale e permanente; la sua *dimensione economica* misurata su 5
giorni non lo è.

### 3.3 Il momento dell'ingresso

`entry_percentile` = posizione del prezzo d'ingresso nel range low-high della giornata.

Undici ingressi S4 nella finestra: mediana **64,3°** percentile, media **57,4°**, **5 su 11 sopra
il 70°**. MTM a fine giornata: **−10,26 $**. Gli stessi undici nomi, stessa size, comprati
all'apertura della loro seduta: **+186,42 $**. Delta **+196,68 $**.

Controllo su S1, stessa finestra, 5 ingressi: mediana 22,6° percentile, e l'apertura sarebbe stata
**peggiore** di 25,05 $. L'effetto è specifico della sleeve che entra su notizia.

> ⚠️ «Comprare all'apertura» **non è una strategia alternativa**: alle 09:30 ET non si sa quali nomi
> il segnale delle 17:22 sceglierà. Usa informazione futura. È una decomposizione che isola quanto
> del P&L dipende dall'ora d'ingresso condizionatamente ai titoli poi scelti — non una proposta.

### 3.4 Quando arriva la notizia

Frazione del movimento **intraday** già avvenuta al momento del primo punteggio utile sul titolo,
mediana per seduta: **08-07: 82% · 08-10: 70% · 08-11: 84%**. Su ORCL (110,8%) e NOK (121,1%) supera
il 100%: al primo segnale il prezzo aveva già oltrepassato il proprio livello di chiusura.

Misura **diversa e non confrontabile con le precedenti**, usata solo il 08-12 perché quel giorno la
metrica sopra aveva denominatori quasi nulli: la quota del movimento contenuta nel **gap di
apertura** era del **99% mediano** sui 9 mover al rialzo, con la gamba intraday piatta o negativa su
7 su 9.

Non è latenza tecnica. Il 08-07 la latenza di ingestione era la migliore mai misurata (mediana
39,6 min contro ~100 dei giorni precedenti) **e la frazione era comunque 82%**. L'articolo viene
scritto *perché* il movimento è avvenuto.

### 3.5 L'Information Coefficient

`docs/evidence/s4_ic.json`, Spearman cross-sectional giornaliero, una osservazione per
simbolo-giorno, n=38 giorni, 2.197 osservazioni:

| sottoinsieme | IC 1g | IC 3g | IC 5g |
|---|---:|---:|---:|
| tutti i segnali | −0,0147 | −0,0121 | −0,0329 |
| **solo ensemble** | **−0,0029** | **+0,0126** | **+0,0136** |
| solo fallback (FinBERT) | −0,0306 | −0,0767 | −0,0832 |
| alta convinzione (≥0,30) | +0,0434 | +0,0465 | +0,0624 |

Nessuno è significativo a t=3. L'IC minimo rilevabile a t=3 su questo campione è **0,10–0,12**, cioè
**un ordine di grandezza sopra qualunque valore osservato**: con questo `n` il test non può
distinguere un IC di 0,05 da zero.

**Il criterio di kill è già pre-registrato** (2026-08-06, prima del dato): a n ≥ 73 giorni si calcola
la media degli IC solo-ensemble ai tre orizzonti; se **≤ 0**, S4 passa a shadow. Oggi quella media
vale **+0,0078** — S4 sopravviverebbe, per un margine che è rumore puro.

**Il problema che motiva questo documento:** l'IC è misurato a 1, 3 e 5 giorni, ma i trade durano in
mediana **4h15**. Il criterio che deciderà la sorte di S4 misura un orizzonte che la strategia non
ha mai avuto.

### 3.6 La qualità del dato a monte

Difetti misurati sulle stesse 5 sedute, tutti già tracciati come issue separate e in corso di
correzione (non sono oggetto di questa decisione, ma ne condizionano l'interpretazione):

- **51 simboli su 96** senza una sola riga di news in giornata
- **405 righe scorate su 816 (49,6%)** nascono da articoli taggati a 2+ ticker: liste, rassegne, 13F
- Il resolver attribuisce a **MS 122 righe di cui solo 4** citano Morgan Stanley (97% di falsi
  positivi); a **GS 65 di cui 2**. MS e GS sono i due ticker più coperti dell'intera watchlist
- Un articolo su Lumentum ha chiuso una posizione su Nvidia (l'ultimo segnale per ticker vince, e
  quello era un quasi-zero proveniente da un pezzo su una società terza)

**Implicazione da tenere presente:** una parte non quantificata dell'IC ≈ 0 potrebbe essere
attribuibile a questo rumore a monte piuttosto che all'assenza di alpha nella news. Le correzioni
sono in corso ma **non ancora deployate**, quindi l'IC attuale è misurato sul dato sporco.

---

## 4. Le tre opzioni

### Opzione A — S4 diventa esplicitamente **intraday**

Orizzonte dichiarato 1–4 ore, coerente con la tenuta mediana attuale di 4h15.

Conseguenze: l'IC va rimisurato a 1h/4h/close, non a 1/3/5 giorni — il criterio di #179 va
riscritto. Servono fonti a bassa latenza o event-driven (filing, earnings, revisioni di analisti)
al posto della news editoriale, che per la §3.4 arriva a movimento avvenuto. La sensibilità ai costi
di transazione cresce: oggi 99 $ di costi su 209 $ di utile lordo, cioè il **32% dell'alpha lordo se
ne va in costi**, e un orizzonte più corto peggiora quel rapporto.

### Opzione B — S4 diventa **1–3 giorni**

Orizzonte multi-day, coerente con l'orizzonte su cui l'IC è già misurato.

Conseguenze: `max_signal_age` non può più governare l'uscita — non si può liquidare una posizione
perché Benzinga ha smesso di pubblicare dopo quattro ore. Servono una regola d'uscita esplicita
(contro-segnale, stop, o scadenza dichiarata) e le correzioni #236/#242. Il turnover crolla, i costi
scendono. Ma il capitale resta impegnato più a lungo su una sleeve il cui IC a 3 giorni è +0,013,
cioè indistinguibile da zero, e aumenta la sovrapposizione con S1 (vedi §5).

### Opzione C — S4 passa a **shadow**

Continua a produrre segnali e a misurarsi, smette di eseguire. È l'opzione (a) già pre-registrata
su #179 come conseguenza di un IC ≤ 0.

Conseguenze: azzera turnover, costi e interferenza con S1; conserva la serie storica per misure
future; libera il 10% del portafoglio. Ma rinuncia all'unica sleeve con P&L realizzato positivo
(+209 $ contro −769 $ di S1) e chiude la questione senza aver mai misurato S4 su dati puliti né su
un orizzonte scelto.

---

## 5. Vincoli non negoziabili

1. **Long-only.** Nessuna gamba short. Un segnale negativo può solo chiudere.
2. **Nessun LLM nel percorso di esecuzione.** L'inferenza è offline; il motore legge segnali
   pre-calcolati. Non proporre chiamate sincrone a modelli dentro il ciclo.
3. **Solo RTH.** Nessuna infrastruttura per pre-market o after-hours: il campo `extended_hours` non
   è mai stato usato. Qualunque proposta che richieda di operare sul gap richiede lavoro
   infrastrutturale che va dichiarato, non assunto.
4. **S4 è capped al 10% del portafoglio**, con validazione allo startup.
5. **Periodo di sola osservazione** fino al 2026-09-28 (40 sedute di borsa), con una deroga
   d'ambito concessa il 2026-08-13 per questo specifico lavoro. Ogni cambiamento di comportamento
   crea una **discontinuità** nella serie osservata e va deployato come un unico cambiamento datato,
   non spalmato su più giorni.
6. **La collisione con S1.** Il guard anti-pyramiding impedisce a S4 di comprare nomi già in
   portafoglio per S1. Misura su 2 giorni (unica finestra osservabile): **21 intenti S4 su 30 erano
   diretti a titoli già detenuti da S1** — AMD, CSCO, MU, NOK, RIO, SHEL, SOXX, SPY, TSM, XLE, cioè
   il cuore del book S1. `n=30` su 2 giorni: **non è conclusivo**, ma l'ipotesi «S4 duplica S1
   invece di diversificarlo» non è smentita.

---

## 6. Dove l'evidenza è debole — usa questi punti, non farti guidare dai numeri sopra

Elencati apposta perché una risposta che non li affronta non ci serve.

1. **n=9 sulla finestra.** È la settimana peggiore di S4 su cinque. Il difetto meccanico è reale;
   la sua dimensione economica non è misurata su quel campione.
2. **n=38 sull'IC**, contro un minimo rilevabile 10× superiore ai valori osservati. Non sappiamo se
   S4 abbia alpha: sappiamo che non lo abbiamo misurato.
3. **L'IC è calcolato su dati sporchi** (§3.6). Le correzioni non sono ancora deployate.
4. **Il controfattuale «all'apertura» usa informazione futura** e non è realizzabile.
5. **La misura di sovrapposizione con S1 ha n=30 su 2 giorni.**
6. **Il P&L realizzato di S1 è avversamente selezionato** e non è confrontabile con quello di S4:
   S1 chiude solo i perdenti. Il confronto +209 $ contro −769 $ **non dimostra** che S4 sia migliore.
7. **Una t di −4,96 sull'ora d'ingresso 14 UTC circola nei nostri aggregati: non è un test valido.**
   129 osservazioni ma 87 sono una coorte legacy senza attribuzione e 33 vengono da un solo giorno.
   Non usarla.

---

## 7. Cosa chiediamo

1. **Quale delle tre opzioni**, con la motivazione. Se pensi che nessuna sia giusta, dillo e proponi
   la quarta, spiegando perché non è una delle tre travestita.
2. **Cosa falsificherebbe la tua scelta.** Un criterio osservabile, con soglia e `n`, scritto prima
   del dato. Se la tua raccomandazione non è falsificabile, dichiaralo.
3. **Come va rimisurato l'IC** perché il criterio di #179 sia coerente con l'orizzonte scelto —
   orizzonte, metodo, `n` minimo.
4. **Se l'evidenza basta.** Se pensi che non basti, dillo esplicitamente e indica quale misura
   mancante cambierebbe la risposta, e quanto tempo servirebbe a raccoglierla.
5. **La sequenza.** Data la §5.5, in che ordine i cambiamenti vanno deployati per lasciare almeno
   un segmento di serie confrontabile prima del 28/09.

### Formato della risposta

```
SCELTA:            A | B | C | altro (una riga di motivazione)
CONFIDENZA:        alta | media | bassa — e perché
CRITERIO DI FALSIFICAZIONE:  soglia, orizzonte, n, misurabile su dati che già abbiamo?
RIMISURA DELL'IC:  orizzonte, metodo, n minimo
L'EVIDENZA BASTA?  sì | no — se no, quale misura manca e in quanto tempo si ottiene
SEQUENZA DI DEPLOY:  ordine e motivo
COSA HO IGNORATO:  quali numeri del documento non hai usato e perché
DISSENSO:          su quali affermazioni del documento non sei d'accordo
```

L'ultima riga è obbligatoria. Una risposta che non dissente da nulla è un segnale che il documento
ha guidato invece di informare, e va trattata come tale in fase di confronto.

---

## 8. Materiale di riferimento (facoltativo, il documento è autosufficiente)

- `docs/evidence/OBSERVATION_CHARTER.md` — carta di osservazione, domande di uscita pre-registrate,
  registro delle deroghe, soglie in dollari
- `docs/evidence/s4_ic.json` — serie IC completa
- `docs/ALPHA_MISS_REPORT_2026-08-{06,07,10,11,12}.md` — i cinque report giornalieri
- `docs/evidence/findings.json` — ledger dei findings, F-024 / F-025 / F-030 / F-035 in particolare
- `docs/issues/186/FINDING.md` — meccanismo QS-07/FIX-D
- `docs/strategies.md` §S4 — specifica
- Issue: [#242](https://github.com/Jonbj/alembic/issues/242) (questa decisione),
  [#179](https://github.com/Jonbj/alembic/issues/179) (kill criterion),
  [#236](https://github.com/Jonbj/alembic/issues/236),
  [#246](https://github.com/Jonbj/alembic/issues/246),
  [#181](https://github.com/Jonbj/alembic/issues/181) (overlap S1∩S4)
