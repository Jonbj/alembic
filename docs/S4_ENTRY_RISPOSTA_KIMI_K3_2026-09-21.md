# S4 — architettura di ingresso: risposta di Kimi K3 al prompt del 2026-09-21

**Prompt:** `docs/S4_ENTRY_PROMPT_KIMI_K3_2026-09-21.md` · **Data:** 2026-09-21

Convenzioni: ogni numero è (a) **misurato** sui nostri dati con artefatto citato,
(b) **supportato** dalla letteratura raccolta (`review.verdict == "SUPPORTED"`), oppure
(c) **congetturale** (detto esplicitamente). Ogni taglio sulla finestra già ispezionata
2026-08-03 → 2026-09-04 è **discovery** e non un risultato. Long-only ovunque.
Nessuna raccomandazione è motivata dalla sola letteratura (regola 6 del prompt).

---

## D1 — Specifica ricostruita e matrice dell'evidenza

### Catena funzionale ricostruita (verificata sul codice, non sulla documentazione)

```
fonte (Benzinga REST/WS, GDELT GKG)
  → sanitizzazione (src/text/sanitizer.py)                    [fail-open: nessun entità HTML decode, F-076]
  → dedup TTL 4h su (hash, asset_tags[0])                     [difetto pre-registrato: TTL = 2× MAX_NEWS_AGE_HOURS]
  → risoluzione ticker deterministica                         [fail-closed: NO_TRADE_*; F-057: mai RESOLVED]
  → scoring async (ensemble Ollama Cloud / FinBERT fallback)  [fuori dal path di esecuzione — vincolo primario rispettato]
  → fetch ranker: ultimo segnale per simbolo, lookback 96h
  → prefiltri: min_confidence 0.30, |score| ≥ 0.10, score > 0 [ranking.py:217-236; drop fallback, _filter_fallback_signals]
  → gate freschezza published_at ≤ 2h (solo simboli non detenuti) [portfolio_scheduler.py:1344-1380; FIX-D riammette per detenuti]
  → gate staleness generated_at ≤ 4h                          [portfolio_scheduler.py:1383-1400; fail-open sul logging]
  → gate ordine: feedback:entry_threshold ≥ 0.30              [fail-closed al floor su Redis down; si applica sullo score × velocity_multiplier, non sullo score grezzo — #550]
  → ranking cross-sezionale: sort per effective_strength, n_top = 5
  → sizing: peso fisso 1/n_top per slot, non ridistribuito
  → guardie ciclo: SKIP_IDEMPOTENCY [fail-closed], SKIP_PYRAMIDING [fail-closed, elenco trade non disponibile → tutti i BUY saltati], SKIP_STOP_COOLDOWN
  → anti-churn: hold 90 min [fail-open al default], exit_persistence 2 [fail-open su errore Redis]
  → ordine Alpaca
```

**Punto di rottura strutturale:** tutto ciò che decide *cosa* comprare (prefiltri, gate, ranking)
opera su **score e età**, ovvero su *quanto* è forte un segnale e *quando* è stato generato —
mai su *che cosa è* la notizia (rilevante per l'emittente? anticipatoria o cronaca? contenuto
duro o content-mill?). Quell'informazione esiste già (`article_coverage.py`: classificazione
ANTICIPATORY/CONCURRENT/RETROSPECTIVE, CONTENT_EMPTY, ISSUER_SPECIFIC/fan-out) ma è letta
solo dal dossier ex-post e mai dal path di trading.

### Matrice scelta · registro · artefatto · H0x · verdetto

| # | Scelta | Registro | Artefatto / riferimento | H0x | Verdetto |
|---|--------|----------|--------------------------|-----|----------|
| M1 | Score = `polarity × confidence` | congetturale (mai misurato contro alternative) | `src/workers/sentiment.py:501,489` | — | nessuna evidenza a sostegno né contro |
| M2 | Gate assoluto `feedback:entry_threshold` 0.30 | misurato (separa debolmente: 54.9% vs 48.7% hit rate, n=257/1.268; IC same-session +0.031, t 0.77) | `ENTRY_FUNNEL_FINDINGS_2026-09-08.md` | H06 | insufficentemente giustificato: separa magnitudine, non direzione (F-043) |
| M3 | Gate sullo score **boostato** da velocity_multiplier | misurato come difetto di misura | `portfolio_scheduler.py:4646-4659`, #550 | — | errore di confrontabilità: gate drops contengono score boostati, la serie pubblicata no |
| M4 | Ultimo segnale per simbolo, non il più forte | misurato (F-023, 14 occ., $31.59; F-051, $220.87) | `ranking.py:203-206`, `findings.json` | — | difetto: un segnale forte è sovrascritto da uno debole pochi secondi dopo |
| M5 | `n_top = 5`, sizing fisso `1/n_top` | congetturale (mai variato, mai misurato) | `src/strategies/s4/config.py:12,157` | — | nessuna evidenza |
| M6 | `MAX_NEWS_AGE_HOURS = 2` | misurato come vincolo non rispettato dalla filiera (latenza pub→score mediana 46.0 min, p90 92.8) | `ENTRY_FUNNEL_FINDINGS_2026-09-08.md` | H21 | la soglia è un dato, la filiera non la onora: è la latenza che decide, non il parametro |
| M7 | Dedup TTL 4h = 2× MAX_NEWS_AGE_HOURS | misurato, correzione già pre-registrata | `src/connectors/deduplicator.py:22` (docstring stale 2h) | — | difetto noto, allineare |
| M8 | `min_confidence 0.30`, `min_score 0.10` | congetturale | `src/strategies/s4/config.py:18-19` | — | nessuna evidenza |
| M9 | Scoring off-session in tabella shadow non letta | misurato | `src/workers/sentiment_shadow.py` (#432-C) | H10 | informazione calcolata e sprecata; il vero gap è *raccoglibile* solo misurando il drift — vedi D2 |
| M10 | Classificazione ANTICIPATORY/CONCURRENT/RETROSPECTIVE + CONTENT_EMPTY solo nel dossier | misurato (lo stream intraday è in gran parte cronaca: volatilità a T+0 = 0.89× il fondo, nessun picco; 82.9% del movimento già fatto allo score) | `src/analysis/dossier/article_coverage.py`; `docs/research/2026-09-16-s4-event-study-latenza.md` | H05, H06 | **difetto di architettura**: il discriminante decisivo (evento reale vs copertura di prezzo) è computato e non vincola nulla |
| M11 | Fan-out articoli multi-ticker equiparati a issuer-specific | misurato (55.6% delle timeline multi-ticker; caso ORCL: `max_score_fanout` 0.22 vs `max_score_own` 0.021; costo evitato TMUS $122.44, RDDT $66.59) | F-012, #629, dossier 2026-09-17 | H08 | difetto di attribuzione: il segnale più vicino al gate spesso non riguarda l'emittente |
| M12 | GDELT GKG come fonte equiparata a Benzinga | misurato (IC 1g −0.099, t −2.65, n=1.006, regge per periodo — registro discovery) | `docs/research/2026-09-16-s4-event-study-latenza.md` | H21 | candidato a rimozione dal path di gating; da confermare su replica forward (H12/H13) |
| M13 | SKIP_PYRAMIDING globale per simbolo (indifferente alla sleeve) | misurato (73.5% degli intenti tradabili muore lì; 57.3% dei blocchi su titoli detenuti da S1/legacy; #628) | `portfolio_scheduler.py:4766-4786` | — | guard **corretto**: non raddoppiare l'esposizione. Il problema è a monte: il ranking continua a generare intenti su nomi già detenuti |
| M14 | Ensemble glm52+gptoss preferito a FinBERT | misurato (IC ensemble −0.039 vs FinBERT −0.038, t ≈ −1.6/−1.5; attenzione: fallback concentrato nei giorni degradati, confronto confundato) | `s4_ic.json` | H19 | l'ensemble non batte FinBERT sui nostri dati: evidenza sulla premessa del paradigma, non solo su S4 |
| M15 | `ensemble_std` persistito ma mai gate; F-054: guardia di divergenza aggirata (`ensemble_std` = 0.000 esatto quando i modelli divergono al massimo) | misurato | `src/store/pg_store.py:151-163`, F-037/F-054 | H15 | telemetria sbagliata: fix di calcolo esente dal freeze; farne un gate è taratura |
| M16 | `stop_loss = 0.0` per S4 | decisione esplicita 2026-07-15 | `config/trading.yaml:182-183` | — | fuori scope ingresso; si nota |
| M17 | F-076: entità HTML non decodificate, 61.6% delle righe arriva al modello corrotto | misurato | `src/text/sanitizer.py` (nessun `html.unescape` nel codice, verificato 2026-09-21) | — | **difetto di correttezza**: passa il test del charter (input corrotto → evidenza sui punteggi sbagliata) |
| M18 | F-046: solo body nel prompt | misurato, mitigato dalla Variante A live (#399/#408, `.env:28`) — resta dipendente dalla env, non dal default | F-046, `src/workers/sentiment.py:327-328` | H06 | chiuso di fatto il 2026-09-01; registrare che il default legacy resta pericoloso |

**Scelte prive di qualsiasi evidenza:** `n_top = 5`, sizing `1/n_top`, `min_confidence 0.30`,
`min_score 0.10`, la formula `polarity × confidence`, la coppia d'ensemble attuale contro
alternative con pari prompt, il gate assoluto 0.30 come forma (al di là del valore). Questo è
il vero risultato di D1: la metà delle manopole dell'ingresso non ha mai avuto una misura a
sostegno.

---

## D2 — L'architettura di ingresso proposta

Principio guida: **il problema non è la soglia, è cosa il sistema considera un "segnale"**.
L'evidenza misurata dice che tre popolazioni con proprietà opposte sono oggi fuse in un unico
flusso: (1) cronaca intraday retrospettiva (~80% del flusso, IC ≈ 0 o negativo, misurato), (2)
eventi fuori orario informativi ma non raccoglibili all'apertura (+0.560% gap in eccesso,
t 2.35 clusterizzato — candidato; +0.078% dopo l'apertura, t 0.49 — non raccoglibile,
misurato; −0.6 bp anticipando solo lo scoring alla 09:29, misurato #608), (3) una minoranza di
eventi anticipatori issuer-specific il cui segnale è annegato nel mix. Spostare il gate 0.30 in
su o in giù non separa le popolazioni (M2, F-043).

### Unità decisionale

**L'evento informativo, non l'articolo** (H05 ha claim SUPPORTED: IND001-C18.1-01, categorie
evento come unità di inferenza). Concretezza: la chiave dell'unità è
`(simbolo, seduta, cluster canonico)` dove il cluster riusa l'identità canonica già testata in
`article_coverage.py` (content_hash → title-hash → URL → news_log_id). Per event si
aggregano: `n_articoli`, `max_score_own`, `max_score_fanout`, `primo_published_at`,
classificazione dominante di copertura e rilevanza, tipo evento se disponibile. Il ranker
ordina **eventi**, non righe: così F-023 (il più recente sovrascrive il più forte) e F-051
(slot top-N a segnali vecchi) spariscono per costruzione.

La riduzione articolo→evento deve riusare gli helper di produzione importati
(`compute_dedup_hash`, `scelta_produzione()` per la coerenza con la misura #169/#467), non
riscriverli nella pipeline.

### Le due lane e la separazione evento/copertura

```
pubblicazione
 ├─ fuori orario → scoring notturno (oggi shadow) → evento off-hours
 │    → ammissibile SOLO per la tesi multi-day, congelata fino al verdetto #606 (~metà 11-2026)
 │    → NIENTE ingresso intraday post-open da questa lane (misurato: +0.078%, t 0.49)
 └─ in orario → classificazione persistita allo scoring:
      evento ammissibile sse:
        rilevanza ISSUER_SPECIFIC (non fan-out ignudo)          — misurato M11
        NON CONTENT_EMPTY                                        — misurato, F-066
        ANTICIPATORY oppure CONCURRENT-con-novità                — il discriminante di
                                                                   copertura di prezzo (M10)
```

Domanda del prompt: *fails open o closed?* **Fail-closed al layer di ammissibilità:** se la
classificazione manca o la rilevanza è TAG_UNCONFIRMED, l'evento non entra (oggi F-057 dice
che il resolver non ha mai prodotto RESOLVED e day-level TAG_UNCONFIRMED era 61.4% il
09-17 — con un requisito stretto il flusso si svuota; va quindi accompagnato dal fix
osservazionale QX-01, altrimenti si misura solo l'assenza di dati). Il CONCURRENT puro è il
caso difficile: misurato che la volatilità a T+0 è 0.89× (nessun evento reale nel flusso
mediano), quindi un CONCURRENT senza novità è cronaca → escluso. La "novità" non esiste come
campo: la proxy minimale già computabile è *primo articolo del cluster per
(simbolo, seduta)* — un articolo che apre un cluster nuovo ha una chance di precedere il
movimento; uno che si accoda a un cluster esistente, o che arriva con
`quota_movimento_precedente_al_segnale` già alta su dati **pre-articolo**, è cronaca.

**Dichiarazione di scoperta:** la separazione CONCURRENT=ignaro / CONCURRENT=copertura è
congetturale; l'unica misura pulita possibile è la D4-M1.

### Fan-out

`max_score_fanout` non può creare un evento ammissibile da solo. Gli articoli macro/sector
restano **contesto** (utili per l'uscita e per il post-mortem, non per l'ingresso), coerente
con H08 (issuer/sector/macro = unità distinte, claim SUPPORTED IND001-C21-03).
**Fail-closed:** un evento esistente solo per fan-out non entra. Caso-test di regressione:
ORCL 2026-09-17 (fan-out 0.22 vs own 0.021 — deve NON entrare).

### La popolazione fuori orario

Risposta onesta al prompt: *non c'è nulla da raccogliere oggi*. Misurato sui nostri dati:
all'apertura resta +0.078% (t 0.49); alle 07:00 resta +10.1 bp lordi (t 0.64); l'esecuzione
extended-hours non è giustificata (INSUFFICIENT_N formale in #608: anche gratis, i 14 eventi
azionabili danno +16.78 bp < soglia 18.7 bp). Il segnale è probabilmente informativo
(gap +0.560%, t 2.35, sotto la barra) ma informatività ≠ raccoglibilità. L'unico uso
architettonico legittimo è una **posizione multi-giorno sulla tesi di drift** (letteratura:
H02/H04, news momentum persiste 63–252 gg, claim SUPPORTED ACA011-C10-02 — ma sui nostri dati
il drift 1–5 gg della popolazione mista è negativo, misurato: IC −0.065/−0.066/−0.070, e non
corretto per molteplicità). Quindi: **lane off-hours → astensione di default**, con la
decisione agganciata a #606 (confermativo, ~metà novembre 2026) e a una misura D4-M3 sul
drift della sola popolazione off-hours. Assunzione non coperta dichiarata: H16 è INSUFFICIENT
(zero claim) — se la prima perdita del funnel fosse altrove, l'astensione non la cura.

### Ammissibilità oltre lo score

Oltre alla classificazione: (1) novità del cluster (primo articolo vs accodato), (2) rilevanza
diretta (ISSUER_SPECIFIC; H06 ha 34 claim SUPPORTED: hard news > soft news), (3) qualità di
fonte — GDELT messo in quarantena dal path di gating (misurato M12, da confermare su replica
forward: la letteratura non autorizza il cambio, H21-H22 servono solo a formulare l'ipotesi),
(4) `ensemble_std` come gate: **no, non ora**. Il calcolo è sbagliato (F-054: std = 0.000
esatto a divergenza massima) e non esiste golden set (H15, QX-01: enforcement gated su
`news_labels`). Prima si corregge la telemetria (esente), poi si misura l'accordo modello
contro esito sui label, poi — solo a quel punto — un gate ha senso.

### Gate vs ranking

Il gate assoluto 0.30 su una quantità non stazionaria è una scelta, non un dato (M2: la
separazione 54.9%/48.7% non è significativa; F-043: il gate seleziona magnitudine, non
direzione). Struttura proposta: **l'ammissibilità diventa categoriale** (classificazione +
novità + rilevanza), lo **score resta solo ordinatore** nel ranking cross-sezionale per
seduta (`max_score_own` dell'evento, con decay temporale sul cluster anziché ultimo-vince).
Un pavimento assoluto minimo resta come guardia anti-rumore, ma il suo valore è taratura da
decidere su replica forward, non su questa finestra.

### Conflitto con le altre sleeve

`SKIP_PYRAMIDING` è un guard **corretto** (mai raddoppiare l'esposizione sullo stesso nome —
73.5% degli intenti tradabili e 57.3% dei blocchi su nomi S1/legacy, #628). Il problema è a
monte: il ranking continua a riproporre come candidati simboli detenuti, consumando cicli e
slot logici (F-051). Fix architettonico: **esclusione a monte nel ranking** dei nomi già
detenuti (qualunque sleeve) — il guard d'ordine resta come ultima riga, fail-closed. Questo
è un cambio di posizione di un controllo esistente: cambia il comportamento osservato →
TARATURA. L'osservabilità mancante (chi ha bloccato chi, attribuzione per sleeve, F-031) è
strumentazione esente dal freeze, profilo #161/#324/#512.

### Aggregazione temporale

Keep-strongest-per-cluster con mezza-vita esplicita, invece di ultimo-per-simbolo
(F-023/F-051, misurati). Segnali su eventi con cluster morto (nessun articolo nuovo da X ore)
non rientrano nel ranking se non per governare uscite su posizioni détenute (branca FIX-D,
invariata). Valori di decay: taratura.

### Astensione

È legittimo — e l'evidenza lo suggerisce — che la struttura dica spesso **no**: con le lane
sopra, il flusso ammissibile atteso è **congetturale, qualche evento a seduta, e sedute
intere a zero** (ordine di grandezza 0–3, contro i ~102 intenti tradabili del 09-17).
Contesto misurato: S4 è a −$979.55 cumulati il 09-16 (peggiore di finestra, banda ±$200;
−$696.33 il 09-17, `economic_pnl.json`), è `promotion_blocked` e il criterio di riattivazione
non è valutabile prima di metà 2027 (INSUFFICIENT_N, `n_corrente` 7/213, `s4_ic.json` post-#601).
Una struttura che compra raramente e non peggiora la serie è superiore a una che compra
cronaca: il costo dell'astensione è misurabile (D4-M4), il costo dell'ingresso-su-cronaca è
già nel P&L.

### Comportamento su dato mancante (sintesi)

| Dato mancante | Comportamento |
|---|---|
| classificazione copertura/rilevanza | evento non ammissibile (fail-closed) |
| `published_at` | escluso (non classificabile per lane) — è già la regola #606 |
| Redis gate / idempotency / trade list | come oggi: fail-closed (confermato nel codice) |
| ensemble giù | fallback FinBERT ammesso solo se il trattamento-fallback è omogeneo; oggi SKIP_FALLBACK li droppa tutti — decidere è taratura |
| barre prezzi per la proxy di quota pre-mossa | fail-closed, mai proseguire su fetch parziale (lezione SIP dell'embargo, §6.8 del prompt) |

---

## D3 — Schede dei cambiamenti (8), in ordine evidenza/costo

**C1 — Classificazione copertura/rilevanza persistita allo scoring e vincolante per l'ammissibilità.**
- Meccanismo: la misura mostra che lo stream intraday è cronaca (vol T+0 0.89×, 82.9% del
  movimento già fatto allo score); filtrare RETROSPECTIVE/CONTENT_EMPTY/fan-out ignudo toglie
  la popolazione diluita prima del gate.
- Charter: **TARATURA** (cambia cosa entra; il fix del *path di persistenza* senza gate è
  strumentazione esente, profilo #432-C).
- Ipotesi falsificabile: H1 "il forward IC dei soli eventi ammissibili è > 0 e > quello della
  popolazione completa"; H0 "IC filtrato ≤ IC non filtrato (o ≤ 0)".
- Dove: `article_coverage.py` (classificatori già testati, da richiamare — non riscrivere —
  nel sink di scoring `sentiment.py`/`pg_store.py`), poi filtro in `ranking.py`.
- Effetto atteso: segno positivo sul sotto-campione; **congetturale** +0.03/+0.08 di IC
  (ordine di grandezza, non misura).
- Costo se sbagliato: il flusso si svuota (61.4% TAG_UNCONFIRMED il 09-17) → visibile nel
  funnel_v2 entro pochi giorni.
- Interazione: prerequisito di C2 e C5; collide con C1-bis "novità" se i due filtri si
  applicano entrambi senza distinguere le lane.

**C2 — Ranking su `max_score_own`; il fan-out non crea eventi.**
- Meccanismo: il segnale che supera il gate deve riguardare l'emittente dell'ordine, non un
  roundup macro (misurato: ORCL fan-out 0.22 vs own 0.021; costo evitato TMUS $122.44 /
  RDDT $66.59, #629).
- Charter: **TARATURA**.
- H1: IC/P&L degli ingressi migliora escludendo eventi only-fan-out; H0: nessuna differenza.
- Dove: aggregazione evento in `ranking.py` + campi `max_score_own/fanout` già materializzati
  nel dossier, da portare upstream.
- Costo se sbagliato: si perdono i (pochi) casi in cui il macro anticipa davvero il nome
  (controesempio documentato: AAPL 09-17 own 0.42 già batte fan-out — l'own-score li conserva).
- Interazione: con C1 condividono la classificazione di rilevanza: fare C1 prima, C2 viene
  per ride.

**C3 — Unità decisionale evento + keep-strongest-con-decay al posto di ultimo-per-simbolo.**
- Meccanismo: oggi un segnale debole sovrascrive uno forte su timestamp (F-023 misurato) e
  segnali di giorni fa occupano top-N (F-051, $220.87 misurato).
- Charter: **TARATURA**.
- H1: P&L realizzato degli ingressi migliora con keep-strongest; H0: nessuna differenza.
- Dove: riduzione per `(simbolo, cluster)` in `ranking.py:203-206` usando l'identità canonica
  di `article_coverage.py` importata.
- Costo se sbagliato: un evento davvero nuovo sullo stesso nome resta nascosto sotto il
  cluster vecchio (mitigazione: il decay + nuovo-cluster-reset).
- Interazione: C3 è la cornice entro cui vivono C1/C2.

**C4 — Quarantena GDELT GKG dal path di gating (persistere comunque i suoi score).**
- Meccanismo: 28% delle osservazioni porta la maggior parte del segno IC negativo
  (−0.099, t −2.65; registro **discovery** sulla finestra ispezionata).
- Charter: **TARATURA**, con replica forward dichiarata prima del deploy (H12/H13: il backfill
  non è conferma).
- H1: IC della popolazione Benzinga-sola > IC mista; H0: nessuna differenza dopo clustering
  per giorno.
- Dove: flag di fonte nel filtro di ammissibilità (stessi punti di C1).
- Costo se sbagliato: si perde il flusso GDELT sui nomi in cui soltanto GDELT copre — e
  F-001 ($5.068 cumulati) ricorda che la copertura già manca: visibile come riduzione del
  volume, non del P&L peggiorato.
- Interazione: indipendente.

**C5 — Criterio di astensione esplicito (default: non entrare quando nessun evento è ammissibile).**
- Meccanismo: con la popolazione intraday a IC ≈ 0 (misurato) e la popolazione off-hours non
  raccoglibile (misurato), entrare "perché qualcosa ha passato il gate" è il difetto.
- Charter: **TARATURA** (è una regola di comportamento, non strumentazione).
- H1: il P&L cumulato della sleeve sotto astensione non è significativamente peggiore dello
  status quo e ne riduce la varianza verso la banda; H0: astensione = status quo sul P&L **ma
  con meno operatività** (a parità di rischio è già meglio, dichiarato come criterio secondario).
- Dove: nessun flag nuovo — è la conseguenza di C1+C2: il ranking vuoto produce zero ordini.
- Costo se sbagliato: alpha reale non raccolto; visibile nei candidati_miss (la tassonomia
  esiste già: `candidati_miss`, funnel_v2).
- Interazione: conseguenza derivata, non un cambio separato — elencata perché va dichiarata
  nel charter come intento, non scoperta nella serie a posteriori.

**C6 — Fix F-076: `sanitize_text` decodifica le entità HTML prima del prompt.**
- Meccanismo: il 61.6% delle righe raggiunge il modello con `&amp;`/`&#39;` → input corrotto,
  punteggi sporchi (misurato, codice verificato: nessun `html.unescape` in `src/text/sanitizer.py`).
- Charter: **DIFETTO_DI_CORRETTEZZA** (passa il test: senza il fix, l'evidenza sui punteggi
  è sbagliata — stesso profilo #163). Nota di perimetro: il fix cambia la distribuzione degli
  score di più di un puro refactor → **discontinuità dichiarata** in `s4_ic.json`/dossier e
  nel registro delle rotture, come fatto per #399 il 02-09.
- H0: la quota di righe con entità residue nel prompt dopo il fix ≠ 0.
- Dove: `src/text/sanitizer.py` + test di regressione; nessun consumatore di serie cambia
  definizione se non annotata.
- Effetto atteso: riduzione del rumore di segno sui teaser Benzinga (congetturale).
- Interazione: con F-046/Variante A (già live) forma la coppia "input pulito + titolo".

**C7 — Fix F-054: calcolo corretto di `ensemble_std` + attribuzione per sleeve dei blocchi anti-pyramiding.**
- Meccanismo: telemetria sbagliata (std = 0.000 esatto a divergenza massima) inficia ogni
  futura misura di accordo modello; i blocchi `SKIP_PYRAMIDING` senza attributo di sleeve
  impediscono la misura di C-upstream.
- Charter: **DIFETTO_DI_CORRETTEZZA** per il calcolo (evidenza raccolta sbagliata → test
  superato); **strumentazione** per l'attributo sleeve (non cambia cosa compriamo).
  **Non** include farne un gate: quella è taratura gated su golden set (QX-01, H15).
- H0: `ensemble_std` ricomputato sui casi divergenti resta 0.000.
- Dove: aggregazione in `sentiment.py:524`/`pg_store.py`; campo `owner_sleeve` su
  `s4_intent_events`/`execution_decisions` per i blocchi.
- Interazione: prerequisito di una futura ipotesi "varianza come gate" (oggi vietata per
  mancanza di golden set).

**C8 — Lane off-hours: promozione dello scoring pre-open su tabella reale + astensione intraday post-open da segnali off-hours.**
- Meccanismo: misurato che post-open resta +0.078% (t 0.49) e che anticipare lo scoring alla
  09:29 vale −0.6 bp (#608): la lane non può produrre ingressi intraday, ma i suoi segnali
  servono alla tesi di drift da testare su #606.
- Charter: la scrittura su `sentiment_signals` **è una deroga-da-registrare** (cambia il
  denominatore di copertura #508/#511 a metà finestra — esattamente ciò che #432-C evitava);
  raccomando di **non farla prima del 28/09** e tenere lo shadow com'è, annotando la decisione.
  L'astensione intraday dalla lane è taratura.
- H1/H0: delegati a #606 (pre-registrato) e D4-M3.
- Costo se sbagliato: scrivere su `sentiment_signals` contamina la serie del criterio —
  irrecuperabile dentro la finestra di osservazione.
- Interazione: dipende dall'esito #606 (~metà novembre); **richiede un dato che non abbiamo** —
  va in fondo all'ordine (D6).

---

## D4 — Misure aggiuntive su dati esistenti (5)

Premessa di metodo: H12 è SUPPORTS sulla letteratura raccolta ("live trading è l'unico vero
test out-of-sample", MET007-C5-02) e coerente col nostro caso: **nessun taglio sulla finestra
2026-08-03 → 2026-09-17 è confermativo** — è tutta discovery che serve solo a scegliere cosa
pre-registrare al 28/09. Le misure decisive già esistenti (`s4_kill_criterion.yaml`, #606)
richiedono tempo forward, non backfill. Detto questo:

**M1 — Forward IC della popolazione ammissibile proposta (C1+C2).**
- Q: filtrando i 3.748 segnali con la classificazione di produzione (`article_coverage.py`
  importato, non reimplementato) + `max_score_own`, l'IC a 1g/3g/5g è > 0 e > della popolazione
  completa? H0: entrambe le disuguaglianze false.
- Unità: (simbolo, seduta) ridotto con `scelta_produzione()` importata. Popolazione: snapshot
  segnali 2026-08-03 → 09-05 (outcome 1g al 96.7%). **Discovery**, finestra ispezionata.
- Famiglia: 3 orizzonti × 2 confronti = 6 celle; correzione FWER (Holm) dichiarata; power:
  sd giornaliera IC ~0.243 (da `s4_kill_criterion.yaml`) → su n≈25–30 giorni l'IC rilevabile a
  t=3 è ~0.15 — **probabilmente INSUFFICIENT_N, dichiarato in anticipo**: il valore di M1 è
  escludere i fallimenti grossolani, non promuovere.
- Produzione da chiamare: `scelta_produzione()` (`scripts/measure_169_dedup_rules.py:300`),
  classificatori di `article_coverage.py`, `compute_s4_ic.py`.
- Falsificante: IC filtrato ≤ 0.

**M2 — Fan-out single vs multi-ticker, A/B su forward return.**
- Q: a parità di score e giorno, i segnali da articoli issuer-specific battono quelli da
  multi-ticker? H0: differenza di media = 0 (cluster per giorno).
- Unità: (articolo canonical, simbolo, seduta); popolazione: `news_log` + snapshot segnali
  (55.6% multi — n ampio su entrambi i bracci). Discovery. Famiglia condivisa con M1: totale
  celle aggregate dichiarate = 12, Holm sul pacchetto.
- Produzione: identità canonica di `article_coverage.py`; stessi forward returns di M1.
- Falsificante: differenza ≤ 0 o segno opposto al campione 09-17.

**M3 — Drift multi-giorno della sola popolazione off-hours.**
- Q: sui segnali con `published_at` fuori orario (regola di classificazione identica a
  `PREREGISTRAZIONE_GAP_OFFHOURS_2026-09-16.md` §3, importata), il rendimento open→+1g/+3g/+5g
  in eccesso su SPY è > 0? Deciso che il gap non è raccoglibile (#608), questa misura testa
  l'unica lane residua: il drift. H0: media dell'eccesso = 0, cluster per giorno.
- Unità: (simbolo, seduta di reazione) ridotta con `scelta_produzione()`. Barre giornaliere
  Alpaca SIP troncate a now−3gg; **fetch fallito → abort** (lezione embargo). Discovery
  (popolazione parzialmente già ispezionata) — e resta subordinata a #606 per la
  promozione a tesi.
- Power: n congetturale ~150–300 osservazioni su ~70–90 giorni: l'effetto rilevabile a t=3
  andrà riportato come `ic_rilevabile_a_t3` prima di guardare l'esito; atteso vicino al
  limite → esito probabile INSUFFICIENT_N.
- Falsificante: eccesso ≤ 0 a +3g.

**M4 — Controfattuale di astensione su quota pre-mossa computabile live.**
- Q: qual è il P&L cumulato S4 se fossero esclusi gli ingressi con metrica di pre-mossa
  **disponibile al momento della decisione** (non `quota_movimento_precedente_al_segnale`, che
  usa il close ex-post — §6.2 del prompt)? Candidata: `entry_percentile` (mediana mobile 20g,
  calcolabile in tempo reale) e/o quota calcolata su prezzi fino al `published_at`.
- Dati: `LATE_ENTRY_OBSERVATION_DECISIONS` in `execution_decisions` (lettore con filtro
  obbligatorio, deroga #512) + `trades.net_pnl`; benchmark: la joint distribution esistente
  (≥1.0: −$192.71 su 22 ingressi, dossier aggregato). H0: esclusione → P&L cumulato uguale o
  peggiore.
- Discovery, n ingressi ~65–100 → esito atteso descrittivo, non decisionale. Dichiarare che
  qualunque soglia scelta da M4 è taratura pre-registrandola ex-novo.
- Falsificante: il P&L del controfattuale non migliora su nessun cut monotone della metrica.

**M5 — Calibrazione score vs label umani (QX-01 feeding).**
- Q: sui label ciechi accumulati (`news_labels`), l'ordine degli score ensemble rispetta
  l'ordine dei forward return? Chiama `scripts/compute_label_forward_returns.py` (già testato).
- H0: IC label-vs-return = 0. **INSUFFICIENT_N atteso** (golden set piccolo) — il risultato
  di valore è il **tasso di copertura dei label** e l'accordo ensemble/FinBERT sui label,
  che alimenta la decisione futura su ensemble_std come gate (C7) e su H15/H19.
- Discovery; nessuna promozione conseguente.

---

## D5 — Trappole e anti-raccomandazioni

1. **La banda < 15 min di latenza** (IC +0.101, n=289, 4–8 giornate) è il punto più facile in
   cui autoingannarsi: costruirci una "fast lane" è selezione del rumore — il precedente è
   letterale: `issuer_first` sembrava la regola migliore e con 0/42 celle al bar era rumore,
   mentre il difetto vero era un gate anti-selettivo altrove (#169, INSUFFICIENT_N).
2. **Ritarare 0.30** in su o in giù dai tagli hit-rate (54.9% vs 48.7%): differenza non
   significativa, e F-043 dice che il gate seleziona magnitudine, non direzione. Qualunque
   ottimo post-hoc della soglia su questa finestra è rumore.
3. **Esecuzione extended-hours per cogliere il gap**: misurato non raccoglibile (#608:
   INSUFFICIENT_N formale; anche gratis, +16.78 bp < 18.7 bp di soglia; le notizie escono a
   gap già avvenuto). Comprare l'infrastruttura sarebbe inseguire +0.560% che il +0.078%
   post-open dichiara non disponibile.
4. **`quota_movimento_precedente_al_segnale` come regola live**: usa il close noto ex-post.
   Ogni regola anti-late-entry deve usare solo informazioni disponibili al ciclo (M4 esiste
   apposta).
5. **Sostituire l'ensemble con FinBERT** guardando IC −0.039 vs −0.038: il confronto è
   confondato (il fallback si concentra nei giorni degradati, es. outage 09-09) e i due
   valori sono indistinguibili. La domanda vera (ensemble ≠ value-add) va al golden set, M5.
6. **Rimuovere GDELT e dichiarare vittoria sulla stessa finestra** che ha generato
   l'ipotesi: H12/H13 — niente replica forward, niente risultato. La quarantena (C4) si
   pre-registra e si guarda solo su dati nuovi.
7. **Validare il filtro cronaca su `costo_usd` dei dossier** o sui candidati_miss: sono
   valutazioni con esito noto (il mover si identifica dal movimento). Vale solo M1/M2 con
   forward returns ridotte simbolo-seduta via produzione.
8. **Trattare un claim `SUPPORTED` come autorità per parametri**: l'audit 09-15 dice che
   SUPPORTED = "citazione verificata, non sovrastimata", non verità trasferibile (e 2 claim
   SUPPORTED hanno provenance fallita). La letteratura genera ipotesi, non patch (regola 6).
9. **"Sistemare" SKIP_PYRAMIDING togliendo il guard**: il guard è corretto; toglierlo
   raddoppierebbe l'esposizione sui nomi in tema condivisi con S1 (43/75 blocchi = proprio
   la sovrapposizione voluta). Il fix è a monte nel ranking, con osservabilità (C7).
10. **Aprire la serie del criterio a ritocchi**: i forward IC della tabella di M2-gate
    (−0.065/−0.066/−0.070) sono già vicini al bar senza correzione di molteplicità; resistere
    alla tentazione di pubblicarli come "risultato" o di ricalcolare `min_giorni` a ribasso
    (il file stesso lo vieta, #601).

---

## D6 — Ordine dei lavori

**Fase 0 — esenti dal freeze, subito** (nessuna dipende dalle misure D4):
1. C6: fix F-076 (`html.unescape` nel sanitizer + test), con annotazione di discontinuità
   registrata in anticipo. — *Correttezza dell'input: senza, ogni settimana di evidenza ulteriore sui punteggi è sporca.*
2. C7: fix calcolo `ensemble_std` (F-054) in sola telemetria/persistenza; attributo
   `owner_sleeve` sui blocchi pyramiding (strumentazione, profilo #512 con filtro-lettori
   dichiarato se si scrive su `execution_decisions`).
3. Allineamento TTL dedup già pre-registrato (4h → coerente con MAX_NEWS_AGE_HOURS) +
   docstring stale (`deduplicator.py:51-56,69` dice "2h", il codice 4h — la docstring mente).
4. Registrare nel charter la decisione C8-a: lo shadow off-session **non** è promosso su
   tabella reale prima del 28/09 (motivo: denominatori di copertura della finestra).
5. Nessuna lettura intermedia di #606 (esito a ~metà novembre 2026).

**Fase 1 — misure D4 in parallelo** (discovery, nessun deploy; dipendono solo da Fase 0-C6 se
si vuole coerenza di scoring futuro, ma girano su dati già persistiti): M1, M2, M3, M4, M5.
Ognuna con pre-registrazione interna breve (popolazione, celle, Holm, `ic_rilevabile_a_t3`
dichiarato prima dell'esito) nel formato dei PREREGISTRAZIONE_* esistenti. Output atteso:
quali cambi di Fase 2 pre-registrare e quali archiviare.

**Fase 2 — dal 2026-09-28, solo con pre-registrazione chiusa a Fase 1** (ordine: C1 → C2+C3 →
C4 → C5 dichiarata nel charter):
1. Persistenza della classificazione allo scoring (strumentazione già esente per il solo
   scrivere; attenzione: scrivere cambia `news_log`? No — tabella/colonne proprie, non
   toccherebbe `sentiment_signals`: perimetro da fissare nella pre-registrazione, stesso
   stile #432-C).
2. Gate categoriale di ammissibilità + fan-out excluded (C1+C2), ranking su eventi con
   keep-strongest-decay (C3): un solo deploy logico, una sola discontinuità annotata.
3. Quarantena GDELT dal gating (C4) con replica forward: il verdetto di C4 si legge solo sui
   giorni **successivi** al deploy.
4. Esclusione a monte dei detenuti dal ranking (conguard pyramiding invariato a valle).

**Fase 3 — richiede dati che non abbiamo, va per ultima**:
1. Tesi drift off-hours (C8-b): dipende dall'esito #606 (~metà novembre 2026) e da M3.
   Dato mancante: il verdetto confermativo stesso. Se #606 esce INSUFFICIENT_N o FAIL,
   l'architettura resta con la lane off-hours in astensione permanente.
2. `ensemble_std` come gate: richiede golden set `news_labels` di dimensione adeguata
   (QX-01) **più** esito M5. Dato mancante: label sufficienti.
3. Qualunque ipotesi di esecuzione extended-hours: oggi esclusa dalla misura (#608); riaprirla
   richiederebbe un cambio di fonte (news più veloci) **e** di regime di esecuzione — altro
   ordine di grandezza di lavoro, fuori mandato fino a prova contraria.
