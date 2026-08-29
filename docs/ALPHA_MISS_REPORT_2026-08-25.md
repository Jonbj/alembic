# Alpha Miss Report — 2026-08-25

Fonte numerica primaria: `docs/evidence/dossier/2026-08-25.json` (deterministico, Alpaca SIP
`adjustment=all`). Query dirette via `docker exec alembic-postgres-1 psql` per `trades`,
`sentiment_signals`, `execution_decisions`, `news_log`. Equity da Alpaca Trading API
(`/v2/account/portfolio/history`). Nessun ricalcolo dei numeri già presenti nel dossier.

> **Nota di provenienza — il dossier non si è generato da solo.**
> `uv run python scripts/alpha_miner_dossier.py 2026-08-25` è fallito con
> `ERROR: column reference "decision_at" is ambiguous` e ha stampato
> `2026-08-25 saltato ... dossier scritti: 0`. La causa è in `_s4_entry_intents`
> (`scripts/alpha_miner_dossier.py:835-836`): la `WHERE`/`ORDER BY` usa `decision_at` non
> qualificato mentre il join espone quella colonna sia in `s4_candidate_population` sia in
> `s4_intent_events`. Il dossier di oggi è stato prodotto da una **copia usa-e-getta in `/tmp`**
> con le sole due referenze qualificate (`intent.decision_at`), quindi lo stesso codice per ogni
> altro numero. Il repo **non è stato modificato**. Vedi §7 [F-044].

## 1. Executive summary

11 dei 96 simboli watchlist si sono mossi ≥3% (soglia `soglia_mover=0.03` del dossier), **9 al
rialzo contro 2 al ribasso**, dispersione σ=1.90% su un mercato moderatamente risk-on (SPY +0.32%,
QQQ +0.62%). **7 mover su 11 erano già a libro** (AMD, MRVL, DELL, NOK, MRK, PANW via S1;
WDC via S4 dal 07-21): il book ha incassato il rialzo su sei di essi e il ribasso su PANW −3.13%. **4 miss**:
HOOD +8.17% (THIN_NEUTRAL — 5 articoli, ma l'unico issuer-specific, *«Why Is Robinhood Stock
Surging on Tuesday?»*, viene scorato **−0.0098**), RDDT +6.39% e NVO +3.71% (NO_NEWS puri — zero
righe in `news_log`; NVO aveva pure un evento di calendario **OBSERVED**), NKE −3.12%
(OUT_OF_STRATEGY_SCOPE — segnale del segno corretto a −0.246, ma book long-only e titolo non
detenuto). **Copertura news al minimo della serie: 55/96 simboli a zero righe** (40→41→43→51→55 dal
08-19), effective-timely 17/96 = 17.7%. Il fatto più utile della giornata non è un miss ma una
**misura di orizzonte**: sui tre mover bloccati dal guard/gate l'opportunità lorda close-to-close
vale $308 ma quella **realmente accessibile dal primo ciclo eleggibile vale −$30** (AMD +$11.03,
DELL +$1.32, MRVL **−$42.81**) — il guard anti-pyramiding oggi ha **fatto risparmiare** denaro.
24 cicli portfolio, nessun gap oltre 15 minuti, primo ciclo 14:07 UTC. Book: NAV **109.959,77**
(+98,39 sulla giornata), realizzato **+91,80** (un'unica uscita: XLE), MTM del book aperto +282,43.

## 2. Tabella rendimenti completa (96 simboli)

Fonte: dossier, Alpaca SIP `adjustment=all`, close vs close precedente. Nessun simbolo senza barre
(`simboli_senza_dati: []`).

| Simbolo | Return % | Catturato |
|---|---:|---|
| HOOD | +8.17% | No — miss (THIN_NEUTRAL) |
| RDDT | +6.39% | No — miss (NO_NEWS) |
| AMD | +4.91% | **Sì** — a libro (S1) |
| MRVL | +4.84% | **Sì** — a libro (S1) |
| DELL | +4.23% | **Sì** — a libro (S1) |
| NOK | +3.92% | **Sì** — a libro (S1) |
| MRK | +3.84% | **Sì** — a libro (S1) |
| NVO | +3.71% | No — miss (NO_NEWS) |
| WDC | +3.53% | **Sì** — a libro (S4, dal 07-21) |
| NFLX | +2.77% | — sotto soglia |
| MU | +2.48% | — a libro, sotto soglia |
| GE | +2.25% | — a libro, sotto soglia |
| NVDA | +2.19% | — **tradato oggi** (ingresso S4 19:07), sotto soglia |
| SPCX | +2.19% | — sotto soglia |
| GS | +2.18% | — a libro, sotto soglia |
| ERIC | +2.17% | — sotto soglia |
| PFE | +2.15% | — sotto soglia |
| META | +1.97% | — **tradato oggi** (ingresso S4 19:52), sotto soglia |
| VALE | +1.93% | — a libro, sotto soglia |
| RIO | +1.92% | — a libro, sotto soglia |
| TSM | +1.78% | — a libro, sotto soglia |
| INFY | +1.78% | — sotto soglia |
| AZN | +1.77% | — sotto soglia |
| ORCL | +1.62% | — sotto soglia |
| DB | +1.61% | — sotto soglia |
| SOXX | +1.56% | — a libro, sotto soglia |
| IBM | +1.36% | — sotto soglia |
| BIDU | +1.36% | — sotto soglia |
| QCOM | +1.28% | — sotto soglia |
| MS | +1.26% | — a libro, sotto soglia |
| ARM | +1.16% | — a libro, sotto soglia |
| C | +1.16% | — a libro, sotto soglia |
| ROKU | +1.00% | — a libro, sotto soglia |
| UBS | +0.97% | — a libro, sotto soglia |
| XLK | +0.94% | — a libro, sotto soglia |
| MSFT | +0.90% | — sotto soglia |
| BABA | +0.82% | — sotto soglia |
| CSCO | +0.80% | — **tradato oggi** (ingresso S4 19:07), sotto soglia |
| QQQ | +0.62% | — a libro, sotto soglia |
| DIS | +0.58% | — sotto soglia |
| JD | +0.55% | — sotto soglia |
| JNJ | +0.53% | — a libro, sotto soglia |
| ABBV | +0.48% | — a libro, sotto soglia |
| V | +0.45% | — sotto soglia |
| TXN | +0.43% | — a libro, sotto soglia |
| IWM | +0.42% | — a libro, sotto soglia |
| TSLA | +0.37% | — sotto soglia |
| XLV | +0.34% | — a libro, sotto soglia |
| SPY | +0.32% | — a libro, sotto soglia |
| T | +0.31% | — sotto soglia |
| CMCSA | +0.30% | — sotto soglia |
| BA | +0.29% | — sotto soglia |
| INTC | +0.25% | — sotto soglia |
| ASML | +0.23% | — a libro, sotto soglia |
| MMM | +0.20% | — a libro, sotto soglia |
| VZ | +0.20% | — sotto soglia |
| BAC | +0.16% | — a libro, sotto soglia |
| XLF | +0.15% | — a libro, sotto soglia |
| F | +0.14% | — sotto soglia |
| HD | +0.13% | — sotto soglia |
| JPM | +0.08% | — a libro, sotto soglia |
| WFC | +0.08% | — sotto soglia |
| CAT | +0.03% | — a libro, sotto soglia |
| BRK.B | +0.00% | — sotto soglia |
| MA | −0.08% | — sotto soglia |
| AAPL | −0.14% | — a libro, sotto soglia |
| GOOGL | −0.32% | — a libro, sotto soglia |
| AMZN | −0.39% | — sotto soglia |
| AXP | −0.41% | — sotto soglia |
| TM | −0.44% | — sotto soglia |
| UNH | −0.54% | — a libro, sotto soglia |
| TMUS | −0.55% | — sotto soglia |
| AVGO | −0.56% | — sotto soglia |
| SAP | −0.79% | — sotto soglia |
| PG | −0.82% | — sotto soglia |
| NOW | −0.82% | — sotto soglia |
| SHEL | −0.84% | — a libro, sotto soglia |
| ADBE | −0.85% | — sotto soglia |
| AMAT | −0.86% | — a libro, sotto soglia |
| SONY | −0.87% | — sotto soglia |
| WMT | −1.04% | — sotto soglia |
| LLY | −1.06% | — a libro, sotto soglia |
| COST | −1.17% | — sotto soglia |
| GM | −1.35% | — a libro, sotto soglia |
| CVX | −1.58% | — a libro, sotto soglia |
| SBUX | −1.61% | — a libro, sotto soglia |
| CRM | −1.61% | — sotto soglia |
| MCD | −1.63% | — sotto soglia |
| XLE | −1.66% | — **uscito oggi** alle 18:07, sotto soglia |
| PBR | −1.71% | — a libro, sotto soglia |
| SNOW | −1.78% | — a libro, sotto soglia |
| PLTR | −1.80% | — sotto soglia |
| BP | −2.01% | — sotto soglia |
| XOM | −2.08% | — a libro, sotto soglia |
| NKE | −3.12% | No — miss (OUT_OF_STRATEGY_SCOPE) |
| PANW | −3.13% | **Sì** — a libro (S1); il book ha incassato il ribasso |

Soglia mover: |return| ≥ 3%, il valore `soglia_mover` del dossier. Non la scelgo io: è fissata dallo
strumento deterministico ed è la stessa in tutta la serie, che è l'unico modo perché i conteggi di
`market_daily.jsonl` siano confrontabili giorno su giorno.

## 3. Miss classificati

| Simbolo | Return | Categoria | Evidenza |
|---|---:|---|---|
| HOOD | +8.17% | THIN_NEUTRAL | 5 articoli, `extraction_method=source_metadata`. Segnali del giorno: 14:15 **+0.174** (art. *«Bitcoin's Rebound May Be Running On ETF Flows, Not Leverage»*, `relevance=UNKNOWN`), 15:30 0.000 (fallback), **16:45 −0.0098** — e questo è l'unico articolo `ISSUER_SPECIFIC` della giornata, titolo *«Why Is Robinhood Stock Surging on Tuesday?»*, 17:30 +0.125 e +0.040 (entrambi fallback single-model). `max_score_own −0.0098`, `max_score_fanout +0.040`, gate 0.30. 24 intent S4, tutti scartati: 12 `SKIP_ENTRY_GATE`, 12 `SKIP_ENTRY_FRESHNESS`. Nota: al primo ciclo (14:07) l'intent portava score **+0.3524** — sopra gate — ma il segnale (id 8708) era del **2026-08-21 18:45**, quattro giorni prima: `SKIP_ENTRY_FRESHNESS` è la decisione corretta. Opportunità: lorda $179,83, accessibile $76,78. |
| RDDT | +6.39% | NO_NEWS | **Zero righe in `news_log`** il 2026-08-25, zero segnali, zero intent S4. `catalyst.type=UNKNOWN`, `corporate_calendar=NOT_OBSERVED`, `residual_vs_spy +6.07%`. Opportunità: lorda $140,47, accessibile $86,42. |
| NVO | +3.71% | NO_NEWS | **Zero righe in `news_log`**, zero segnali. 22 intent S4, tutti `SKIP_ENTRY_FRESHNESS` su un segnale stantio. Il dossier registra però `corporate_calendar.status=OBSERVED` — `cash_dividends` del 2026-08-25 da Alpaca Corporate Actions: l'evento c'era e la pipeline news non lo ha visto. Opportunità: lorda $81,59, accessibile $36,31. |
| NKE | −3.12% | OUT_OF_STRATEGY_SCOPE | Il segnale c'era ed era **del segno giusto**: 16:15 −0.127 e 18:30 **−0.246**, ensemble non-fallback, su due articoli issuer-specific (*«Dick's Sporting Goods Stock Plunges 25%…»*, *«Nike Stock Slides After Dick's Disappointing Q2 Results»*). Ma il book è long-only e NKE non era detenuto: nulla su cui agire. `accessible_opportunity_usd = 0.0` conferma che sull'orizzonte azionabile non c'era nulla da prendere. |

Conteggi: NO_NEWS 2 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 0 · OUT_OF_STRATEGY_SCOPE 1.

### 3b. I mover a libro bloccati da guard/gate — e quanto sarebbero valsi davvero

Non sono miss (i titoli erano detenuti), ma sono la misura più informativa della giornata perché
mettono a confronto l'opportunità **lorda** e quella **accessibile**:

| Simbolo | Return | Reason code | Score | Lordo (2200×ret) | Accessibile (ingresso al 1° ciclo eleggibile → close) |
|---|---:|---|---:|---:|---:|
| AMD | +4.91% | `SKIP_ENTRY_GATE` ×22 | +0.2666 (segno giusto, sotto gate 0.30) | $108,06 | **+$11,03** (ingresso 14:40 @476,79 → close 479,18) |
| MRVL | +4.84% | `SKIP_PYRAMIDING` ×5, poi `SKIP_ENTRY_GATE` ×19 | +0.3683 (**sopra gate**) | $106,48 | **−$42,81** (ingresso 14:10 @245,15 → close 240,38) |
| DELL | +4.23% | `SKIP_PYRAMIDING` ×15 | +0.5813 (**sopra gate**) | $93,06 | **+$1,32** (ingresso 16:25 @451,23 → close 451,50) |

Somma: lordo **$307,60**, accessibile **−$30,46**. Su AMD il gate ha fermato l'unico segnale del
segno corretto su un mover forte, ma l'incremento sarebbe stato ~zero perché il titolo era già
detenuto da S1 e a valle sarebbe scattato `SKIP_PYRAMIDING` come su DELL e MRVL. Su MRVL e DELL il
guard anti-pyramiding **ha fatto risparmiare** $41,49 netti: entrambi i titoli avevano già fatto (e
MRVL più che esaurito) il proprio movimento quando il segnale è diventato azionabile.

## 4. Titoli catturati — esito

**Uscite del giorno (1).**

| Simbolo | Sleeve | Uscita | Prezzo | Qty | Net P&L | exit_reason | Tenuta | Drift post-uscita |
|---|---|---|---:|---:|---:|---|---:|---:|
| XLE | «S1» (in realtà legacy, `stop_strategy` NULL, ingresso 07-10 14:07) | 18:07 | 62,50 | 12,372 | **+91,80** | `sentiment_reversal` | 1108,0 h | **−5,44** |

Il drift negativo dice che uscire è stato corretto: dopo l'uscita XLE ha continuato a scendere. Il
segnale che ha innescato l'uscita è XLE −0.357 delle 18:00 (ensemble non-fallback), l'unico segnale
ribassista sopra gate della giornata, coerente con il crollo dell'energia (*«Oil Sinks As Navy
Clears Hormuz Mines»*).

**Ingressi del giorno (3), tutti S4, tutti ancora aperti a fine giornata.**

| Simbolo | Ora UTC | Prezzo | Qty | Nozionale | Percentile d'ingresso | MTM EoD | Effetto timing vs ingresso all'apertura |
|---|---|---:|---:|---:|---:|---:|---:|
| CSCO | 19:07 | 111,06 | 17,136 | $1.903,09 | 0,240 | +$0,86 | **+$20,05** |
| NVDA | 19:07 | 212,74 | 8,946 | $1.903,09 | 0,569 | +$2,77 | **−$15,34** |
| META | 19:52 | 569,43 | 3,341 | $1.902,44 | 0,854 | +$2,07 | **−$18,54** |

Percentile mediano 0,569 contro mediana mobile a 20 giorni 0,616: dentro banda. Somma degli effetti
timing **−$13,83**. Tutti e tre gli ingressi arrivano dopo che l'84-104% del movimento di giornata
era già avvenuto (`quota_movimento_precedente_al_segnale` 1,045 / 0,847 / 0,900).

**Mover detenuti che il book ha subito o incassato passivamente.** AMD +4,91%, MRVL +4,84%,
DELL +4,23%, NOK +3,92%, MRK +3,84%, WDC +3,53% al rialzo; PANW −3,13% al ribasso. Su NOK e WDC il
sistema non ha avuto nessun segnale di giornata (zero righe `news_log`, 24 intent ciascuno tutti
`SKIP_STALE` su segnali del 08-24). Su PANW 21 intent `SKIP_FALLBACK` su uno score stantio **+0,08**
— segno opposto al −3,13% effettivo, ma il fallback lo ha fermato prima che contasse.

Pannello decision-quality del giorno: `passive_pnl −$6,46`, `selection_pnl +$5,70`,
`exit_effect +$10,89`, `active_decision_pnl +$16,59` contro un `actual_intraday_pnl +$10,13`;
`market_beta_1 −$10,51`.

## 5. Pattern osservato

**Rotazione intra-tech da software a hardware, finanziata dall'energia — e un secondo fronte
crypto-beta.** Il lato forte è compatto: AI hardware / memoria (AMD +4,91%, MRVL +4,84%,
DELL +4,23%, WDC +3,53%, MU +2,48%, NVDA +2,19%, TSM +1,78%, SOXX +1,56%, XLK +0,94%), mentre il
software cede in blocco nello stesso giorno (PANW −3,13%, PLTR −1,80%, SNOW −1,78%, CRM −1,61%,
ADBE −0,85%, NOW −0,82%): è una rotazione dentro la tecnologia, non un movimento di settore.
Il lato debole vero è l'energia, sull'unico catalizzatore macro leggibile della giornata (*«Bitcoin
Tops $80,000, Oil Sinks As Navy Clears Hormuz Mines»*): XOM −2,08%, BP −2,01%, XLE −1,66%,
PBR −1,71%, CVX −1,58%, SHEL −0,84% — tutti e sei negativi, nessuna eccezione. Terzo blocco,
consumer/retail: NKE −3,12% su un catalizzatore idiosincratico (i conti di Dick's Sporting Goods),
con MCD −1,63%, SBUX −1,61%, COST −1,17%, WMT −1,04% a contorno. I due mover più violenti — HOOD
+8,17% e RDDT +6,39% — non appartengono a nessuno di questi gruppi: sono i due nomi ad alta beta
sui flussi retail, e lo stesso pezzo sul Bitcoin sopra $80.000 li tocca entrambi. Farmaceutico
positivo ma disperso (MRK +3,84%, NVO +3,71%, PFE +2,15%, AZN +1,77%). Indice ampio moderatamente
positivo (SPY +0,32%, QQQ +0,62%), quindi la dispersione σ=1,90% è quasi tutta trasversale.

## 6. Confronto con i giorni precedenti

- **Speculare al 08-24.** Ieri il dossier registrava «rotazione netta fuori da semiconduttori/memoria
  … dentro pagamenti e difensivi», con MU −5,83%, WDC −5,24%, AMD −3,49%, MRVL −3,27%. Oggi gli
  stessi quattro nomi sono +2,48%, +3,53%, +4,91%, +4,84%. Il 08-21 era già stata osservata
  un'inversione speculare rispetto al 08-20. Tre inversioni in quattro sedute sullo stesso gruppo di
  titoli: **il segnale di giornata sui semiconduttori non ha persistenza**, e questo è esattamente
  il regime in cui l'ingresso tardivo (F-030) costa di più. Non lo estendo oltre: quattro sedute non
  sono una serie.
- **Copertura news in peggioramento monotono.** 40 (08-19) → 41 (08-20) → 43 (08-21) → 51 (08-24) →
  **55** (08-25) simboli a zero righe. Cinque sedute consecutive di peggioramento, mai un
  miglioramento. È il valore peggiore della serie recente.
- **Latenza di ingestione in netto miglioramento.** Mediana `published_to_scored` **40,3 min** su
  n=98 (max 111,2 min) contro le mediane 72-76 min registrate su F-019 il 08-20. Non lo registro come
  occorrenza perché il difetto oggi *non* ricorre; lo annoto perché la serie di F-019 lo veda.
- **Il conteggio cumulato delle cause** dopo oggi: NO_NEWS 38, THIN_NEUTRAL 42, WRONG_SIGN 7,
  FILTERED 7, OUT_OF_STRATEGY_SCOPE 4. THIN_NEUTRAL e NO_NEWS restano le due cause dominanti a
  distanza da tutte le altre.

## 7. Segnalazioni

Nessun fix proposto: siamo dentro il periodo di sola osservazione (`OBSERVATION_CHARTER.md`, minimo
40 sedute dal 2026-08-03). Dove una causa mi sembra un difetto e non un limite noto lo dico e mi
fermo lì; la decisione se aprire una issue è dell'operatore.

**[F-044] Sembra un difetto — `scripts/alpha_miner_dossier.py` non genera più il dossier: la query
degli intent S4 fallisce con `column reference "decision_at" is ambiguous`.** ID nuovo giustificato:
nessun finding esistente copre la generazione del dossier — F-026 riguarda il ciclo *forense* che non
aggiorna `findings.json`, F-027 i log dei container. Qui salta il precalcolo deterministico stesso.
`_s4_entry_intents` (righe 835-836) usa `decision_at` non qualificato in `WHERE` e `ORDER BY`, ma il
join espone quella colonna sia in `s4_candidate_population` sia in `s4_intent_events`: è un errore di
**parsing**, quindi deterministico e indipendente dai dati — non fallisce «a volte». L'errore è
catturato per-giorno e degrada in `INFO 2026-08-25 saltato … dossier scritti: 0`, cioè **exit code 0
e nessun allarme**: il cron di ieri ha potuto scrivere `dossier scritti: 0` senza che nulla se ne
accorgesse. La deroga del 2026-08-01 che autorizza questo script lo motiva con «la sessione rischia
il timeout silenzioso che farebbe fallire l'osservazione stessa»: questa è la stessa classe di
guasto, con la differenza che colpisce lo strumento invece della sessione. I dossier 08-21 e 08-24,
rigenerati stamattina, non contengono la chiave `intenti_ingresso_s4` — quindi il blocco intent non
è mai stato prodotto in produzione da quando è stato innestato.
*Costo: null — è strumentazione, non P&L. Il danno è la perdita della giornata di osservazione, che
si conta per ricorrenza.*

**[F-001] Copertura news al minimo della serie: 55 dei 96 simboli watchlist senza una sola riga in
`news_log`.** Quinta seduta consecutiva di peggioramento monotono (40 → 41 → 43 → 51 → 55).
Copertura effective-timely 17/96 = **17,7%** (21 articoli issuer-specific tempestivi su 55 articoli
unici, 98 righe). Due dei quattro miss del giorno sono NO_NEWS puri: **RDDT +6,39%** e
**NVO +3,71%**, entrambi con zero righe e zero segnali. Su NVO il buco è particolarmente netto
perché il dossier registra `corporate_calendar.status=OBSERVED` (`cash_dividends` del 2026-08-25,
Alpaca Corporate Actions API): l'evento societario era osservabile da un'altra fonte già integrata,
la pipeline news non lo ha visto. Zero copertura anche su NOK e WDC, entrambi mover ≥3,5%.
*Costo: $222,13 lordo (RDDT $140,47 + NVO $81,59, size S4 2% NAV = $2.200); sull'orizzonte
realmente accessibile $122,73.*

**[F-009] Il gate d'ingresso S4 (0.30) scarta il segnale del segno corretto su HOOD, il mover più
forte della giornata.** HOOD +8,17%, non detenuto, quindi pienamente azionabile. Il primo segnale
del giorno vale **+0,174** — segno giusto, magnitudine insufficiente — e i 12 `SKIP_ENTRY_GATE`
registrati negli intent lo confermano. Stesso schema del 08-24 su MA e V. Sul secondo caso della
giornata, **AMD +4,91% con score +0,2666** fermato da 22 `SKIP_ENTRY_GATE`, il costo incrementale è
invece **zero e non non-stimato**: AMD era già detenuto da S1 e a valle sarebbe scattato
`SKIP_PYRAMIDING` esattamente come su DELL e MRVL, quindi il gate non ha tolto nulla che il guard
non avrebbe tolto comunque.
*Costo: $179,83 lordo su HOOD (close-to-close × $2.200); sull'orizzonte accessibile (ingresso 14:22
@108,31 → close 112,09) **$76,78**. AMD: $0,00 per la ragione sopra.*

**[F-012] Metà delle righe scorate nasce ancora da articoli fan-out multi-ticker.** 43 mapping
fan-out extra su 98 righe di `news_log` (44%), 55 articoli unici, `mapping_rilevanza` con **77
UNKNOWN contro 21 ISSUER_SPECIFIC**. Due casi puliti oggi: (a) l'articolo *«What's Going On With
Dell Technologies Stock Tuesday?»*, che è per costruzione un pezzo su DELL, è mappato anche su
**AMD** e concorre a formarne il punteggio; (b) *«Bitcoin Tops $80.000, Oil Sinks As Navy Clears
Hormuz Mines: Stock Market Today»*, **10 ticker**, produce il `max_score_fanout +0,040` di HOOD — che
è più alto del suo `max_score_own` di **−0,0098**. Cioè: sul titolo che ha fatto +8,17% il segnale
proveniente da terzi batte quello proveniente dall'articolo dedicato.
*Costo: null — la quota fan-out è una proprietà della pipeline, il danno che produce è già contato
sotto F-009 e F-023 quando si materializza in una decisione.*

**[F-030] La notizia arriva quando il movimento è già avvenuto, e oggi la misura è pulita su
entrambe le facce.** (a) **Lato ingresso**: i tre ingressi S4 hanno
`quota_movimento_precedente_al_segnale` **1,045 (CSCO), 0,847 (NVDA), 0,900 (META)** — su CSCO il
movimento era già più che completo. Gli effetti timing del pannello decision-quality contro il
baseline «stesso ticker, stessa qty, ingresso all'apertura» sommano **−$13,83** (CSCO +$20,05,
NVDA −$15,34, META −$18,54). (b) **Lato miss**: sui quattro candidati il divario fra opportunità
lorda e accessibile vale $271,05 su $470,55 lordi, cioè **il 58% del movimento non era raggiungibile**
al primo ciclo eleggibile. (c) La prova più diretta è testuale: l'unico articolo issuer-specific su
HOOD si intitola *«Why Is Robinhood Stock Surging on Tuesday?»* — un pezzo che **descrive** un rialzo
già avvenuto, pubblicato alle 16:45 UTC, e scorato −0,0098.
*Costo: $13,83 (attribuita, lato ingresso: somma degli effetti timing sui tre ingressi del giorno).
Il divario di $271,05 sul lato miss NON è sommato qui per non contarlo due volte con F-001 e F-009.*

**[F-031] Il guard anti-pyramiding blocca due segnali sopra gate su mover forti — e oggi fa
risparmiare denaro.** DELL score **+0,5813** (il più alto della giornata) bloccato per 15 cicli
consecutivi, MRVL **+0,3683** bloccato per 5, entrambi su titoli già detenuti da S1 con posizioni
minuscole (DELL 0,930 azioni ≈ $420, MRVL 1,552 ≈ $373 contro uno slot S4 da $2.200). L'opportunità
lorda dei due vale $199,54, ma sull'orizzonte accessibile vale **−$41,49** (DELL +$1,32,
MRVL −$42,81): MRVL alle 14:10 quotava 245,15 e ha chiuso a 240,38, cioè aveva già fatto e superato
tutto il proprio movimento prima che l'intento fosse valutabile. Stessa conclusione del 08-24, con
numeri opposti nel segno del movimento.
*Costo: **$0,00 — costo zero, non non-stimato**: il guard ha impedito due ingressi che
sull'orizzonte realmente accessibile avrebbero perso $41,49 netti.*

**[F-033] `sentiment_reversal` chiude di nuovo una posizione che S4 non ha aperto, e il P&L finisce
in un'altra sleeve.** L'unica uscita del giorno è XLE: posizione entrata il **2026-07-10 14:07** con
`stop_strategy` NULL e `signal_id` NULL (coorte legacy, F-002), chiusa alle 18:07 dall'overlay
sentiment di S4 sul segnale XLE −0,357. Il dossier la attribuisce a **S1** per la convenzione
`COALESCE(stop_strategy, CASE WHEN signal_id IS NOT NULL THEN 'S4' ELSE 'S1' END)`, quindi i
**+$91,80** — l'intero realizzato della giornata — entrano nella serie di S1 mentre la decisione è di
S4. Questa è la classe esatta coperta dalla deroga **#182(a) pre-registrata proprio il 2026-08-25**;
il deploy non è ancora avvenuto, quindi la seduta di oggi è ancora nel regime vecchio. Differenza
rispetto alle occorrenze precedenti: qui la decisione era **giusta** (drift post-uscita −5,44, XLE ha
continuato a scendere), quindi la sleeve S1 incassa un guadagno che non ha prodotto.
*Costo: null — è un difetto di attribuzione, non di P&L. Oggi il segno è pure favorevole (+$91,80),
il che rende il difetto di misura più insidioso e non meno.*

**[F-043] CONTRO-ESEMPIO — oggi il gate ha selezionato anche la direzione, non solo la magnitudine.**
Registro questa occorrenza *contro* il finding, non a suo favore, perché una serie che raccoglie solo
conferme non è evidenza. Il 08-24 tutti e 9 i segnali sopra gate erano rialzisti e i titoli chiudevano
in media −2,02%. Oggi i segnali sopra |0,30| sono **9 su 8 ticker distinti**: NVDA +0,330/+0,420/
+0,378/+0,3575, DELL +0,5813, MS +0,680, CSCO +0,3199, META +0,3855 e — per la prima volta nella
serie recente — **uno ribassista, XLE −0,357**. Alla chiusura: DELL +4,23%, NVDA +2,19%,
META +1,97%, MS +1,26%, CSCO +0,80%, XLE −1,66%. **Sei su sei col segno corretto**, media dei
rialzisti +2,09%. Il segnale ribassista ha pure prodotto l'azione giusta (l'uscita da XLE, +$91,80).
Una seduta non ribalta dieci occorrenze contrarie, ma va messa a verbale che il pattern del 08-24
non ha retto ventiquattr'ore.
*Costo: null — è un contro-esempio, non una perdita.*
