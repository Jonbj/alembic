# Forensic Daily Report — 2026-08-07 (venerdì)

Generato il 2026-08-10. Analisi read-only. Periodo di **sola osservazione** (carta del 2026-08-01,
giorno 5 di 40): nessuna proposta di taratura, solo difetti di correttezza.

---

## 1. Executive summary

Giornata **funzionalmente pulita ma quasi inerte**. Il libro ha fatto +$128,55 di NAV
(110.051,33 → 110.179,88, +0,12%) contro SPY +0,61%, con il 71% in cassa. Sono stati inviati al
broker **due soli ordini**, entrambi S1: BUY SBUX (14:07 UTC) e SELL BRK.B (14:22 UTC, −$2,77
realizzati). **S4 non ha inviato nulla.**

Il 2026-08-07 è il **primo giorno con la correzione #185 in produzione**: `orders_count` per ciclo
crolla da ~48 (media 03–06/08) a 2,8, e la chiave Redis `strategy:rebalance_state:S1` è stata
scritta alle 14:07. La serie S1 è quindi discontinua a partire da oggi, come previsto dalla carta.
Lo stopgap sulla soglia S4 ha tenuto: tutte le 584 righe `SKIP_THRESHOLD` citano 0,300, non 0,45.

La pipeline news→LLM ha funzionato senza degradazioni: Ollama up per tutte le 6 ore di sessione,
**zero fallback FinBERT**, budget $0,148 su 139 articoli, nessun timeout. Il collo di bottiglia è
a valle: dei 139 segnali, 60 valgono esattamente 0, 90 stanno sotto |0,05|, **5 superano il gate
0,30 e solo 2 sono anche non-fallback** (AMD 0,384; ROKU 0,300). Entrambi questi 2 sono stati
bloccati dal guard anti-pyramiding P0-05 perché S1/legacy detiene già quei simboli: **il tasso di
conversione segnale→ordine di S4 è stato 0/139**, e la causa non è il gate ma un guard che non
lascia traccia in `execution_decisions`.

L'unica posizione S4 aperta (WDC, entrata 21/07, tenuta 17 giorni contro un `max_signal_age` di 4h)
ha prodotto **−$51,33 di MTM**, la peggior riga del libro in una giornata in cui S1 faceva +$129,53.

## 2. Verdict finale

**OK CON WARNING.**

Nessun ordine sbagliato, nessun duplicato, nessun trade fuori orario, nessuna violazione di
idempotenza, riconciliazione ordini↔trade↔posizioni coerente. I warning sono tutti su
**osservabilità e funnel**, non su money-path: (a) S4 ha convertito 0 segnali su 139 e il motivo
del blocco non è persistito da nessuna parte; (b) il report di rischio ha emesso un ALERT
"drawdown 14,2% > 10%" in una giornata chiusa a +0,12% con drawdown reale 0,40%; (c) i log dei
container del 07/08 non esistono più.

---

## 3. Timeline del 2026-08-07 (tutti gli orari UTC)

Timezone: **UTC**, confermato in `src/workers/celery_app.py:51` (`timezone="UTC"`) e
`SHOW timezone` su Postgres. Il 07/08 gli USA erano in EDT → apertura 13:30 UTC, chiusura 20:00 UTC.

| ora UTC | componente | evento | evidenza |
|---|---|---|---|
| 08:35–13:2x | monitor | 86 snapshot `portfolio_monitor_snapshots`, NAV fermo a 110.307,36 (pre-market, prezzi stale) | `portfolio_monitor_snapshots` |
| 09:02:07 | — | riga `ingestion_stats_daily` source=`reuters`, fetched=16 — **nessun connettore RSS nel beat, 0 righe in `news_log`** | [DAY-011] |
| 13:30 | mercato | apertura EDT. **Nessun ciclo portfolio**: il beat parte da `hour="14-21"` | [DAY-008] |
| 14:01:24 | ingest+LLM | primo articolo scorato della giornata (AMZN, benzinga, pubblicato 13:19) | `news_log` id 6849 |
| 14:01:42 | LLM | MSFT score **+0,360** (`single:glm-5.2`, fallback_used=t) → scartato dal filtro #108 | `sentiment_signals` 6852 |
| 14:01:52 | LLM | AMD score **+0,384** (ensemble, fallback=f) — il segnale più forte "tradabile" del giorno | `sentiment_signals` 6854 |
| 14:07:00 | portfolio | **ciclo 838**: S1 esegue il ribilanciamento mensile (prima esecuzione con #185 live). 48 ordini target, **1 inviato** | `portfolio_cycles` 838 |
| 14:07:00 | ordini | **BUY SBUX** 6,5817 az. @ 105,39 — S1 momentum, peso 1,2% | `trades` 692, `execution_decisions` |
| 14:07:13 | S4 | 2 righe `SKIP_STALE`: GOOGL (−0,229, 18,6h) e QQQ (−0,215, 19,1h) — segnali di ieri sera | [DAY-009] |
| 14:22:00 | ordini | **SELL BRK.B** 1,3089 az. @ 520,52, `portfolio_sell`, net **−$2,77** (tenuta 21,0h) | `trades` 670 |
| 14:22 / 14:37 / 14:52 | S4 | ordine target BUY AMD (3,50 az.) generato 3 volte, **mai inviato** (guard P0-05) | [DAY-001] |
| 15:45:09 | LLM | ROKU score **+0,300** (ensemble, fallback=f) | `sentiment_signals` 6892 |
| 15:52 → 19:37 | S4 | ordine target BUY ROKU (11,04 az.) generato in **14 cicli consecutivi**, mai inviato | [DAY-001], [DAY-004] |
| 16:15:21 | LLM | MU score **+0,420** (`single:glm-5.2`) — punteggio massimo del giorno, scartato dal filtro #108 | [DAY-002] |
| 19:30:50 | LLM | AMAT +0,358 (`single:gpt-oss`), scartato dal filtro #108 | `sentiment_signals` 6976 |
| 19:45:42 | ingest | ultimo articolo scorato; `ingestion_stats_daily` chiuso (benzinga 588/382, gdelt 1897/96) | `ingestion_stats_daily` |
| 19:52:10 | portfolio | ultimo ciclo (24° e ultimo), 0 ordini | `portfolio_cycles` 861 |
| 20:00:00 | monitor | snapshot di chiusura: NAV 110.179,88, cash 78.379,87, gross exp. 28,86%, 48 posizioni | `portfolio_monitor_snapshots` |
| 22:30:00 | risk | unico `risk_reports` del giorno: dd combinato 1,24%, ma ALERT "portfolio drawdown 14,2% > 10%" | [DAY-005] |

Fasce: nessun ordine in pre-market né in post-market. Tutti e 2 gli ordini sono in market hours.
I cicli portfolio coprono 14:07–19:52 (24 cicli × 15 min): **mancano i 37 minuti 13:30–14:07**.

---

## 4. Tabella news ingest

### Per fonte (articoli effettivamente scorati, `news_log`)

| fonte | scorati | ticker distinti | content_hash distinti | primo | ultimo | latenza media | latenza mediana | pubblicati nel futuro | campi mancanti |
|---|---|---|---|---|---|---|---|---|---|
| alpaca_benzinga | 76 | 32 | 25 | 14:01:24 | 19:45:42 | 57,8 min | 43,6 min | 0 | 0 |
| gdelt_gkg | 63 | 17 | 59 | 14:30:30 | 19:30:53 | 37,9 min | 30,6 min | 0 | 0 |
| **totale** | **139** | **45** | **84** | | | | | **0** | **0** |

### Funnel dichiarato (`ingestion_stats_daily`, contatori additivi del giorno)

| fonte | fetched | queued | duplicates | scartati no-ticker | stale | parse_fail |
|---|---|---|---|---|---|---|
| alpaca_benzinga | 588 | 382 | **3120** | 0 | 0 | 0 |
| gdelt_gkg | 1897 | 96 | 11 | 1801 | 0 | 0 |
| reuters | 16 | 16 | 0 | 4 | 0 | 0 |

`duplicates` (3120) supera `fetched` (588) di 5,3× → [DAY-010]. Le righe `reuters` non hanno alcun
corrispettivo in `news_log` (0 righe con `source='reuters'` in tutta la storia della tabella) e non
esiste un task RSS nel beat → [DAY-011].

### Scarti per età

`news_queue_drops`: **138 articoli** scartati perché più vecchi della finestra di entry-freshness
(2,0h). benzinga 118 (età media 7,2h, minima **2,04h**), gdelt 20 (età media 18,8h, minima 18,3h).
La minima a 2,04h dice che la finestra taglia esattamente al bordo: con una latenza mediana di
ingestione di 43,6 min (benzinga), l'articolo entra già ad oltre un terzo della finestra consumato
→ [DAY-013].

### Per ticker (top 12, articoli scorati)

| ticker | articoli | metodo estrazione | note |
|---|---|---|---|
| MS | 19 | org_lookup (19) | **tutti falsi positivi** — Morgan Stanley come casa di analisi nel boilerplate |
| MU | 10 | org_lookup 9 / source_metadata 1 | |
| MSFT | 8 | source_metadata | |
| SPCX | 6 | source_metadata | mover +15,83%, nessun segnale sopra 0,12 |
| GOOGL | 6 | source_metadata | |
| META | 5 | source_metadata | |
| DB | 5 | org_lookup | falsi positivi (Deutsche Bank come analista) |
| NVDA | 5 | source_metadata | |
| TSM | 5 | misto | |
| GS | 4 | org_lookup | falsi positivi |
| SHEL | 4 | misto | |
| AMD | 4 | source_metadata | |

### Duplicazione / fan-out multi-ticker

76 righe su 139 (**55%**) condividono il `content_hash` con almeno un'altra riga: un solo articolo
viene scorato N volte, una per ticker. Casi peggiori:

| content_hash (prefisso) | copie | ticker | titolo |
|---|---|---|---|
| 138f3a60… | 10 | AAPL, AMZN, GOOGL, META, MSFT, MU, NVDA, QQQ, SPCX, SPY | "Chinese Buying Lifts Gold And Silver From Technical Support" |
| 9a50a814… | 7 | AMD, AVGO, MSFT, NVDA, ORCL, PLTR, TSM | "Trump Says AI Could Be Bigger Than Oil…" |
| 7232c5d2… | 6 | IWM, QQQ, WDC, XLE, XLF, XLK | "S&P 500 Hits Record As Jobs Shock Sinks Rate-Hike Bets" |
| 3825cc70… | 5 | AMD, INTC, NVDA, SPCX, WDC | "Chip Stocks Find Buyers After Earnings Shock…" |

Un articolo su oro e argento produce un punteggio "specifico" su AAPL e su SPY. Vedi [DAY-012].

### Risoluzione ticker (`news_resolved_entities`, shadow)

259 righe, **100% NO_TRADE**: 139 `NO_TRADE_LOW_RESOLUTION_CONFIDENCE` (confidenza media 0,451),
120 `NO_TRADE_NOT_TRADABLE` (0 tradable). Il resolver è in sola osservazione (QX-01) e non gate-a
nulla; se fosse acceso oggi, **azzererebbe l'intera pipeline**. Osservazione, non anomalia.

### Sanitizzazione

`extraction_method` è popolato su 139/139 righe (76 `source_metadata`, 63 `org_lookup`) — QT-03 è
attivo. Nessuna riga con `published_at` nel futuro, nessun campo obbligatorio nullo, nessun retry
visibile. Buchi temporali: nessuno in market hours; l'unico buco è **13:30–14:01** (pre-primo-ciclo).

---

## 5. Tabella performance modelli LLM

Coppia attiva: `glm52,gptoss` (Redis `config:sentiment_llm_models`), pesi ensemble
glm-5.2 **0,601** / gpt-oss **0,399** (`ensemble:weights:current`, source `auto_apply`).

| modello | richieste | risposte | errori/timeout | parse fail | polarity media | confidence media | conf < 0,35 | `eligible=true` |
|---|---|---|---|---|---|---|---|---|
| glm-5.2:cloud | 139 | 139 (100%) | 0 | 0 | +0,0590 | 0,2421 | **109 (78%)** | 17 (12%) |
| gpt-oss:20b-cloud | 139 | 139 (100%) | 0 | 0 | +0,0428 | 0,3729 | 67 (48%) | 17 (12%) |

**Latenza: non misurabile.** `llm_responses` non ha colonna latenza; `llm_shadow_responses`
(che ce l'ha) ha 0 righe il 07/08.

### Aggregazione

| model_id risultante | segnali | fallback_used |
|---|---|---|
| `ensemble:glm-5.2:cloud+gpt-oss:20b-cloud` | 85 (61%) | 0 |
| `single:gpt-oss:20b-cloud` | 47 (34%) | 47 |
| `single:glm-5.2:cloud` | 7 (5%) | 7 |
| `finbert` | **0** | 0 |

**Zero fallback FinBERT**: Ollama Cloud up per l'intera sessione, `fallback_counters.consecutive_fallback = 0`,
budget $0,1478 (76.887 tok in / 9.209 out), `budget_exhausted = false`.

### Disaccordo e distribuzione

- Divergenza media |polarity_glm − polarity_oss| = **0,082**; massima 0,500.
- Segno opposto (entrambi ≠ 0): **3 casi su 139** (2,2%).
- Entrambi a 0: 55 (40%). Uno solo a 0: 34 (24%).
- `ensemble_std` medio 0,0259 — varianza bassissima, nessun caso di scarto per divergenza.

Distribuzione di `score = polarity × confidence` (n=139): media +0,0264, min −0,220, max +0,420;
**60 righe esattamente 0 (43%)**, 90 sotto |0,05| (65%), **5 sopra 0,30 (3,6%)**.

### Segnali estremi

| segnale | ora | simbolo | score | conf | modello | fallback | ammesso al ranking? |
|---|---|---|---|---|---|---|---|
| 6912 | 16:15 | MU | **+0,420** | 0,600 | single:glm-5.2 | sì | **no** (filtro #108) |
| 6854 | 14:01 | AMD | **+0,384** | 0,600 | ensemble | no | sì → bloccato da P0-05 |
| 6852 | 14:01 | MSFT | **+0,360** | 0,600 | single:glm-5.2 | sì | **no** (filtro #108) |
| 6976 | 19:30 | AMAT | **+0,358** | 0,650 | single:gpt-oss | sì | **no** (filtro #108) |
| 6892 | 15:45 | ROKU | **+0,300** | 0,500 | ensemble | no | sì → bloccato da P0-05 |
| 6900 | 16:00 | F | +0,286 | 0,625 | ensemble | no | no (sotto gate 0,300) |
| 6974 | 19:30 | TSM | −0,220 | 0,550 | single:gpt-oss | sì | no |

### Verifica funzionale

| domanda | risposta | evidenza |
|---|---|---|
| l'output LLM è validato prima del signal store? | **sì** — parsing strutturato, `eligible` per risposta, aggregazione con floor di confidenza, tag `single:`/`finbert` | `src/workers/sentiment.py:215-236` |
| l'ensemble gestisce varianza alta? | **sì** — divergenza → fallback FinBERT (0 casi oggi) | `sentiment.py:314` |
| le news duplicate pesano più volte? | **sì, per costruzione** — 55% delle righe da articoli fan-out multi-ticker | [DAY-012] |
| la stessa news può generare segnali multipli? | sì, uno per ticker estratto (fino a 10) | [DAY-012] |
| confidence bassa riduce il peso? | **sì** — `score = polarity × confidence`, e sotto floor il modello esce dall'ensemble | verificato su 139 righe |
| chiamate LLM nel trading loop? | **no** — worker Celery `inference`, il ciclo portfolio legge da DB | `celery_app.py` |
| hallucination può entrare in decisione? | **rischio residuo** — nessun supervisor agent; la difesa reale è il gate 0,30 + filtro fallback | vedi §11 |

Osservazione da segnalare: glm-5.2 riceve il **peso maggiore** (0,601) pur essendo il modello con
confidenza sistematicamente più bassa (0,242 contro 0,373) e quindi il più spesso escluso
dall'ensemble. Non è un difetto in sé — LOO-ICIR pesa la qualità, non la loquacità — ma i due
segnali si contraddicono e vale la pena registrarlo.

---

## 6. Tabella segnali finali per ticker

45 simboli scorati. Solo i 5 sopra soglia sono candidati a ordine; l'ultima colonna è il verdetto
effettivo del funnel.

| simbolo | n segnali | max \|score\| | sopra gate 0,30 | non-fallback | esito |
|---|---|---|---|---|---|
| MU | 10 | 0,420 | sì | **no** | scartato da filtro fallback #108 |
| AMD | 4 | 0,384 | sì | sì | **ordine target generato → bloccato P0-05** |
| MSFT | 8 | 0,360 | sì | **no** | scartato da filtro fallback #108 |
| AMAT | 1 | 0,358 | sì | **no** | scartato da filtro fallback #108 |
| ROKU | 1 | 0,300 | sì | sì | **ordine target generato → bloccato P0-05** |
| F | 1 | 0,286 | no | sì | SKIP_THRESHOLD ×5 |
| TSM | 5 | 0,263 | no | — | SKIP_THRESHOLD ×9 |
| CAT | 3 | 0,217 | no | — | SKIP_THRESHOLD ×3 |
| GOOGL | 6 | 0,180 | no | — | SKIP_STALE ×1 + SKIP_THRESHOLD |
| WDC | 2 | 0,180 | no | no | mai arrivato al gate (filtro fallback) |
| SPCX | 6 | 0,120 | no | — | mai valutato (sotto soglia) — **mover +15,83%** |
| PLTR | 2 | 0,120 | no | — | SKIP_THRESHOLD — **mover +10,32%** |
| RDDT / NOW | 1 / 1 | 0,000 | no | — | punteggio nullo — **mover +7,18% / +6,42%** |
| altri 31 | 1–5 | < 0,18 | no | — | SKIP_THRESHOLD o mai valutati |

584 righe `SKIP_THRESHOLD` (tutte con soglia **0,300**, mai 0,45 → lo stopgap del 07/08 ha tenuto
per l'intera sessione) + 2 righe `SKIP_STALE`. `signal_id` è **NULL su tutte e 588** → [DAY-006].

Copertura: 52 simboli della watchlist senza alcun articolo in giornata (`market_daily.jsonl`).

---

## 7. Tabella ordini generati/eseguiti

### Ordini effettivamente inviati al broker (2)

| ts decisione | strategia | ticker | azione | qty | prezzo fill | stato | broker | rationale | segnale causante | risk check | anomalie |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 14:07:00,630 | S1 | SBUX | BUY | 6,581744 | 105,39 | **filled** | Alpaca **paper** | "S1 momentum: time-series momentum signal, portfolio weight 1,2%" | nessuno (momentum, non news) | gate P0-05 (non detenuto), esposizione 28,9% < 50%, halted=∅ | nessuna |
| 14:22:00,629 | S1 | BRK.B | SELL (close) | 1,308921 | 520,52 | **filled** | Alpaca **paper** | "[s1_weight_drop] S1 target weight dropped to 0% — position closed (not an S4 exit)" | nessuno | — | nessuna |

Modalità confermata **paper** su tutti i fronti: `.env → ALPACA_BASE_URL=https://paper-api.alpaca.markets`,
`portfolio_monitor_snapshots.broker_environment='paper'`, `mode='paper'`, `source='alpaca_paper'`.

### Ordini target generati e MAI inviati

| cicli | ticker | azione | qty target | motivo del blocco | tracciato in `execution_decisions`? |
|---|---|---|---|---|---|
| 838 (14:07) | 47 simboli (AAPL, ABBV, AMAT, …) | BUY (top-up) | varie | P0-05 anti-pyramiding (già detenuti) | **no** |
| 839, 840, 841 | AMD | BUY | 3,5048 az. (2,36%) | P0-05 anti-pyramiding | **no** |
| 845–860 (14 cicli) | ROKU | BUY | 11,0367 az. (2,64%) | P0-05 anti-pyramiding | **no** |

`portfolio_cycles.orders_count` per la giornata: 68 in totale (48 nel solo ciclo 838). Ordini
realmente inviati: **2**. Rapporto 34:1 → [DAY-004].

### Controllo cicli

24 cicli portfolio, uno ogni 15 minuti da 14:07:00 a 19:52:00, nessun ciclo saltato, nessun
`constraints_fired`. Media `orders_count` 2,8 (contro 48,7 / 48,7 / 48,9 / 48,1 nei quattro giorni
precedenti): **conferma che #185 è in produzione dal ciclo delle 14:07 del 07/08**, con
`strategy:rebalance_state:S1` scritta a `2026-08-07T14:07:00.630195+00:00`.

---

## 8. Tabella PnL/rendimento

Fonte prezzi: **Alpaca SIP, `adjustment="all"`** (barre giornaliere 06/08 e 07/08). Coerente con
la correzione #192.

### Sintesi

| voce | valore |
|---|---|
| NAV 06/08 (chiusura) | 110.051,33 |
| NAV 07/08 (snapshot 20:00 UTC) | **110.179,88** |
| Variazione NAV | **+128,55 (+0,117%)** |
| SPY del giorno | +0,61% · QQQ +1,17% |
| PnL **realizzato** | **−$2,77** (1 sola chiusura: BRK.B) |
| PnL **non realizzato** (mark-to-market close-to-close, 47 posizioni portate) | **+$101,74** |
| MTM posizione aperta oggi (SBUX 105,39 → 105,58) | +$1,25 |
| Totale close-to-close | **+$99,17** |
| Cash a fine giornata | 78.379,87 (71,1% del NAV) |
| Gross exposure | 28,86% (limite 50%) |
| Unrealized PnL cumulato del libro | +1.022,53 |
| Posizioni aperte | 48 |
| Commissioni | 0 (Alpaca paper, equity) |
| Costo transazione stimato | $0,37 su BRK.B (`cost_usd`) |
| Slippage | **non misurato** — `slippage_est` è una copia di `cost_usd` → [DAY-007] |

Riconciliazione: +128,55 (NAV snapshot) vs +99,17 (close-to-close calcolato). La differenza
(~$29) viene dal fatto che lo snapshot delle 20:00 UTC usa gli ultimi prezzi visti dal poller,
non i close ufficiali consolidati, e da `previous_close_equity` del broker. Non è un'anomalia:
è la stessa grandezza misurata con due orologi. Il ledger `market_daily.jsonl` riporta
`mtm: 133.36` con una terza metodologia (P&L economico da prezzo d'ingresso).

### PnL per strategia (MTM close-to-close, posizioni portate)

| strategia | posizioni | MTM 07/08 | realizzato 07/08 |
|---|---|---|---|
| **S1** | 36 | **+129,53** | −2,77 |
| legacy (senza attribuzione) | 11 | +23,55 | 0,00 |
| **S4** | 1 (WDC) | **−51,33** | 0,00 |
| SBUX (aperta oggi) | 1 | +1,25 | — |

### PnL per ticker — code

| top 6 | MTM | bottom 6 | MTM |
|---|---|---|---|
| SNOW | +21,58 | **WDC (S4)** | **−51,33** |
| TXN | +20,67 | PBR | −22,18 |
| DELL | +14,98 | CAT | −13,54 |
| ROKU | +14,07 | CVX | −11,36 |
| ASML | +13,83 | GE | −10,30 |
| MRVL | +12,69 | SHEL | −10,11 |

Nota: **ROKU ha fatto +14,07 sulla posizione legacy esistente** mentre l'ordine S4 di rinforzo
veniva bloccato 14 volte. Vedi [DAY-001] per il controfattuale.

### PnL da posizioni aperte prima / durante il 07/08

- Aperte prima: 47 posizioni, +$101,74 MTM, −$2,77 realizzato.
- Aperte il 07/08: 1 (SBUX), +$1,25 MTM, 0 realizzato.

---

## 9. Analisi correttezza buy/sell

| controllo | esito | evidenza |
|---|---|---|
| BUY generati solo quando consentito | **OK** | unico BUY inviato = SBUX, simbolo non detenuto, dentro il target S1, halted=∅, esposizione sotto limite |
| SELL/exit generati correttamente | **OK** | BRK.B chiusa perché uscita dal target S1 (peso → 0%), `exit_reason='portfolio_sell'`, motivo esplicito |
| Stop-loss rispettati | **N/A** | nessuno stop scattato; `stop_shadow_log` 1.153 righe il 07/08 (shadow attivo). `stop_decisions` fermo al 14/07 (tabella del ramo vol_scaled, non in uso) |
| Signal flip rispettato | **N/A** | nessun flip: S4 non ha posizioni con controsegnale eseguibile |
| Max holding days rispettato | **VIOLATO in senso lato** | WDC (S4) aperta da 17 giorni contro `max_signal_age_hours=4`; la tiene in vita `preserve-stale` (FIX-D) → [DAY-003] |
| Rebalance band rispettata | **OK** | delta-ordering idempotente; nessun ordine con delta < 1e-4 |
| Ordini duplicati | **nessuno** | 2 ordini, simboli distinti, minuti distinti |
| Ordini contrari ravvicinati | **nessuno** | nessun BUY+SELL sullo stesso simbolo |
| Ticker non consentiti | **nessuno** | SBUX e BRK.B entrambi in watchlist |
| Ordini fuori orario | **nessuno** | 14:07 e 14:22 UTC, dentro 13:30–20:00 |
| Trade su dati stale | **no** | SKIP_STALE correttamente emesso su GOOGL/QQQ, nessun ordine derivato |
| Trade su output LLM non valido | **no** | 0 parse failure, 0 fallback FinBERT |
| Circuit breaker | **non attivo** | `system:halted_by_operator` vuoto; nessun kill-switch |
| Strategia disabilitata | **N/A** | S1 e S4 entrambe attive (`strategies_run: ["S1","S4"]` su 24/24 cicli) |
| Paper/live coerente | **OK, paper** | tre fonti indipendenti concordi |
| Idempotenza retry Celery | **OK** | `_idempotency_skip` per signal_id; nessuna riga duplicata in `trades` o `execution_decisions` per lo stesso ordine |
| Riconciliazione ordini↔fill↔posizioni | **OK** | 2 ordini → 2 righe `trades` (1 apertura, 1 chiusura) → 48 posizioni aperte in DB = 48 in `portfolio_monitor_snapshots.open_positions` |

### Pattern operativi specifici richiesti

| pattern | esito |
|---|---|
| Roundtrip < 30 min | **nessuno** |
| BUY ripetuto > 3 volte senza SELL (pyramiding) | **nessuno inviato**; ma 14 BUY ROKU e 3 BUY AMD *generati* e bloccati dal guard — vedi [DAY-001] |
| SELL con sentiment positivo (bug A5) | **nessuno** |
| `fallback_used=True` su tutti i simboli (Ollama giù) | **no** — 54/139 (38,8%), e nessuno è FinBERT: Ollama up tutto il giorno |
| NO-ORDER (decisione creata, ordine assente) | **nessuno**: entrambe le decisioni BUY/SELL hanno `order_id` popolato |
| Score < 0,05 che hanno generato ordini | **nessuno** |
| Ordini identici nello stesso minuto (race scheduler) | **nessuno** |

### Avvertenza obbligatoria su `exit_mechanism` (#184)

Il campo `exit_mechanism` è **NULL su tutte le righe** di `execution_decisions` del 07/08 e sulla
sola chiusura del giorno (BRK.B, `exit_reason='portfolio_sell'`). Questo report **non conta né
interpreta** `exit_mechanism`: la chiusura di BRK.B è attribuita a S1 dal testo esplicito del
motivo ("S1 target weight dropped to 0% — not an S4 exit"), non dall'etichetta.

---

## 10. Anomalie trovate

### [DAY-001] Il guard anti-pyramiding blocca il 100% degli ingressi S4 sopra soglia, senza lasciare traccia

* Tipo: Anomalia (strutturale)
* Area: Orders / Signal
* Evidenza:
  * file/log/tabella: `src/workers/portfolio_scheduler.py:2675-2678`; `portfolio_cycles` 839-841, 845-860; `execution_decisions` (assenza di righe); `trades` (posizioni aperte AMD dal 14/07, ROKU dal 10/07)
  * timestamp: 2026-08-07 14:22:00 → 19:37:00 UTC
  * snippet/query:
    ```sql
    -- i due soli segnali del giorno sopra gate 0,30 e non-fallback
    SELECT symbol, score, model_id, fallback_used FROM sentiment_signals
    WHERE created_at::date='2026-08-07' AND abs(score)>=0.30 AND NOT fallback_used;
    --  AMD 0.3839 ensemble f | ROKU 0.3000 ensemble f
    -- entrambi già detenuti:
    SELECT symbol, stop_strategy, entry_time FROM trades
    WHERE exit_time IS NULL AND symbol IN ('AMD','ROKU');
    --  AMD S1 2026-07-14 | ROKU legacy 2026-07-10
    -- nessuna riga di decisione per i BUY bloccati:
    SELECT count(*) FROM execution_decisions
    WHERE created_at::date='2026-08-07' AND symbol IN ('AMD','ROKU') AND decision IN ('BUY','SELL');  -- 0
    ```
* Descrizione: il guard P0-05 (`if order.side == BUY and order.symbol in open_db_symbols: continue`)
  scarta l'ordine **prima** che venga scritta qualunque riga in `execution_decisions`. Il 07/08 i
  due soli segnali S4 abilitati a produrre un ingresso riguardavano simboli che S1 (AMD) e il
  libro legacy (ROKU) già detenevano, quindi la conversione segnale→ordine di S4 è stata **0/139**.
  L'ordine ROKU è stato rigenerato e riscartato in **14 cicli consecutivi** senza produrre un solo
  record. Il guard in sé è corretto per design (niente pyramiding); il difetto è duplice: (a) non
  è osservabile, un giorno in cui S4 è stata bloccata è indistinguibile da un giorno in cui S4
  non aveva nulla da dire; (b) implica che **S4 non può esprimere alcun segnale news su nessuno
  dei 48 simboli che S1/legacy già detiene**, cioè sulla parte più liquida della watchlist.
* Impatto: economicamente nullo oggi (controfattuale: ROKU comprata alle 15:52 a 152,43 e chiusa
  a 152,50 → **+$0,77** su 11,04 azioni; AMD comprata alle 14:22 a ~482,86 e chiusa a 482,80 →
  **−$0,21** su 3,50 azioni; netto **+$0,56** mancato). Strutturalmente è il vincolo che rende
  S4 non misurabile: la domanda di uscita n.1 della carta ("esiste alpha nella news editoriale?")
  non è rispondibile se la strategia non può entrare sui nomi che il resto del libro detiene.
* Severità: **High** (per l'osservabilità e per la validità della finestra di osservazione; Low
  come costo del singolo giorno)
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — persistere una riga `execution_decisions` con
  `decision='SKIP_PYRAMIDING'` per ogni BUY scartato dal guard. È strumentazione pura, non tocca
  cosa si compra né con che size, quindi passa il test di esenzione della carta. La domanda "S4
  deve poter incrementare posizioni detenute da S1" è **taratura** e resta al 28/09.
* Test/monitor consigliato: contatore giornaliero `s4_entries_blocked_by_pyramiding` e assert nel
  report forense che `count(SKIP_PYRAMIDING) + count(BUY) == numero di BUY target S4`.

### [DAY-002] Il filtro #108 scarta il 39% dei segnali, inclusi i tre più forti del giorno, trattando un LLM cloud come se fosse FinBERT

* Tipo: Bug (di etichettatura, con effetto sul funnel)
* Area: LLM / Signal
* Evidenza:
  * file/log/tabella: `src/workers/sentiment.py:215-236` (`_label_from_model_count`), `src/workers/portfolio_scheduler.py:3428-3439` (`_filter_fallback_signals`), `sentiment_signals`, `llm_responses`
  * timestamp: 2026-08-07 14:01:42, 16:15:21, 19:30:50 UTC
  * snippet/query:
    ```sql
    SELECT model_id, count(*), count(*) FILTER (WHERE fallback_used)
    FROM sentiment_signals WHERE created_at::date='2026-08-07' GROUP BY 1;
    -- ensemble:… 85 / 0 ; single:gpt-oss 47 / 47 ; single:glm-5.2 7 / 7 ; finbert 0
    SELECT model_id, count(*) FILTER (WHERE eligible) FROM llm_responses
    WHERE generated_at::date='2026-08-07' GROUP BY 1;  -- 17 e 17, su 139 risposte ciascuno
    ```
* Descrizione: un aggregato a un solo modello viene etichettato `single:<model>` con
  `fallback_used=True` "so it is gated everywhere a FinBERT fallback is gated" (commento nel
  codice). A valle, il filtro introdotto con #108 — pensato per non far comprare S4 sul modello
  locale debole — scarta dal ranking BUY **tutte** queste righe. Il 07/08 sono 54 su 139 (38,8%),
  e includono i tre punteggi più alti della giornata: MU +0,420, MSFT +0,360, AMAT +0,358.
  Nessuna di queste è una lettura FinBERT: sono output completi di un LLM cloud, scartati perché
  l'*altro* modello è finito sotto il floor di confidenza. Il difetto a monte è
  `llm_responses.eligible`, marcato `true` su sole 17 risposte per modello mentre 85 segnali sono
  ensemble a due modelli (≥85 contributori reali per modello).
* Impatto: **oggi favorevole**. Dei tre scartati solo MSFT era acquistabile (MU e AMAT sono già
  detenuti, e ricadrebbero comunque in [DAY-001]); MSFT dalle 14:01 (≈504,10) alla chiusura
  (499,60) fa **−0,89%**, cioè su una size tipica S4 di ~$2.204 il filtro ha **evitato −$19,6**.
  Il costo non è quantificabile su un giorno: il problema è che il criterio di scarto non ha
  relazione con la qualità del segnale.
* Severità: **Medium**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — separare `fallback_used` (FinBERT, modello locale)
  da `degraded_ensemble` (un solo LLM cloud), e correggere `eligible` perché rifletta i
  contributori reali. Senza questa separazione la LOO-ICIR pesa i modelli su un insieme di 17
  risposte su 139. **Non** cambiare oggi il comportamento del filtro: quello è taratura.
* Test/monitor consigliato: invariante `count(llm_responses.eligible) >= 2 × count(segnali ensemble)`;
  metrica giornaliera "segnali scartati dal filtro fallback / segnali sopra gate".

### [DAY-003] L'unica posizione S4 è tenuta da 17 giorni da preserve-stale e produce la peggior riga del libro

* Tipo: Bug
* Area: Orders / PnL
* Evidenza:
  * file/log/tabella: `trades` id 373; `src/workers/portfolio_scheduler.py:3475-3495` (`_preserve_stale_signals_for_open_positions`, FIX-D); `execution_decisions` (WDC, ultima riga 2026-08-06 19:22 `SKIP_STALE`)
  * timestamp: ingresso 2026-07-21 16:37:01 UTC; giornata analizzata 2026-08-07
  * snippet/query:
    ```sql
    SELECT id,symbol,entry_time,entry_price,qty,stop_strategy FROM trades WHERE id=373;
    -- 373 | WDC | 2026-07-21 16:37 | 549.24 | 2.981 | S4
    -- WDC close 06/08 = 451.52 → 07/08 = 434.30  ⇒ MTM −51.33
    ```
* Descrizione: `max_signal_age_hours` di S4 è **4 ore**, ma WDC è aperta dal 21 luglio. La tiene
  viva FIX-D (`preserve-stale`), che ri-ammette i segnali scaduti positivi sulle posizioni aperte
  prive di controsegnale. Il 06/08 WDC aveva un segnale **−0,313**, scartato dal gate (allora
  0,400) e poi scaduto per età; il 07/08 il suo unico segnale (+0,180, fallback) non è mai
  arrivato al gate perché filtrato da [DAY-002]. Risultato: una posizione senza orizzonte di
  uscita, che nessuno dei tre meccanismi (scadenza, controsegnale, stop) può chiudere.
* Impatto: **−$51,33 di MTM il 07/08**, la peggiore riga singola del libro in una giornata
  chiusa in positivo, e l'intero contributo negativo di S4. Dall'ingresso: 549,24 → 434,30 =
  **−20,9%** su 2,981 azioni ≈ **−$342,7** non realizzati.
* Severità: **High**
* Confidenza: **High**
* Azione consigliata: ticket di correttezza — `preserve-stale` deve avere un tetto assoluto
  (es. la posizione esce se nessun segnale fresco la conferma entro N giorni di borsa). Senza,
  ogni posizione S4 che smette di far notizia diventa permanente e il P&L economico di S4 sulla
  finestra misura una posizione che il design non prevede.
* Test/monitor consigliato: alert quando una posizione S4 supera `max_signal_age_hours × K` senza
  un segnale fresco; riga nel report forense con l'età di ogni posizione S4.

### [DAY-004] `portfolio_cycles.orders_count` conta gli ordini target, non quelli inviati: 68 contro 2

* Tipo: Bug (osservabilità)
* Area: Ops
* Evidenza:
  * file/log/tabella: `portfolio_cycles` id 838-861; `trades`; `execution_decisions`
  * timestamp: 2026-08-07 14:07:00 → 19:52:00 UTC
  * snippet/query:
    ```sql
    SELECT sum(orders_count) FROM portfolio_cycles WHERE timestamp::date='2026-08-07';  -- 68
    SELECT count(*) FROM execution_decisions
    WHERE created_at::date='2026-08-07' AND decision IN ('BUY','SELL');                 -- 2
    ```
* Descrizione: il ciclo 838 registra `orders_count=48` mentre ha inviato un solo ordine (SBUX);
  i cicli 845-860 registrano 1 ciascuno (ROKU) e non hanno inviato nulla. `final_orders` contiene
  gli ordini *target*, cioè il risultato del delta-ordering prima dei guard di submission.
* Impatto: non economico. Ma qualunque lettura automatica dell'attività ("quanto ha tradato oggi
  il sistema") sbaglia di un fattore 34, e nel periodo di osservazione questa è la serie che
  documenta l'attività di trading.
* Severità: Medium
* Confidenza: High
* Azione consigliata: ticket di correttezza — aggiungere `orders_submitted` accanto a
  `orders_count`, senza modificare il campo esistente (append-only sulla serie storica).
* Test/monitor consigliato: assert `orders_submitted == count(execution_decisions in BUY/SELL)`
  per ciclo.

### [DAY-005] Il report di rischio emette un ALERT "drawdown 14,2%" in una giornata chiusa a +0,12%

* Tipo: Bug
* Area: Risk
* Evidenza:
  * file/log/tabella: `risk_reports` (unica riga del giorno), `config/trading.yaml` (`risk.portfolio_drawdown: 0.05`), `portfolio_monitor_snapshots`
  * timestamp: 2026-08-07 22:30:00 UTC
  * snippet/query:
    ```
    combined_drawdown = 0.012429
    per_strategy_metrics.portfolio.drawdown = 0.14197  → ALERT "exceeds 10%"
    per_strategy_metrics.portfolio.daily_pnl = -446.52
    portfolio_monitor_snapshots(20:00).current_drawdown = 0.004010
    portfolio_monitor_snapshots(20:00).nav_change_today  = +130.59
    ```
* Descrizione: tre grandezze che dovrebbero coincidere ne danno tre diverse (0,40% / 1,24% /
  14,2%), e la quarta (`daily_pnl −446,52`) contraddice il segno del giorno (+128,55 misurati sul
  NAV, +99,17 close-to-close). In più il testo dell'alert cita una soglia del **10%** mentre
  `config/trading.yaml` dichiara `risk.portfolio_drawdown: 0.05`.
* Impatto: non ci sono state conseguenze operative (nessun kill-switch, `system:halted_by_operator`
  vuoto). Ma è un alert che grida al lupo ogni giorno: quando il drawdown sarà vero, nessuno lo
  distinguerà dal rumore. Ricorre dal 31/07.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato — ticket di correttezza per riconciliare le tre serie di
  drawdown su una sola definizione e allineare la soglia dell'alert al file di configurazione.
* Test/monitor consigliato: test che, dato un NAV in salita, nessuna metrica di drawdown del
  giorno superi il drawdown effettivo calcolato su `peak_equity`.

### [DAY-006] `execution_decisions.signal_id` NULL su 588/588 righe

* Tipo: Bug
* Area: Data
* Evidenza:
  * file/log/tabella: `execution_decisions`; `src/workers/portfolio_scheduler.py:3260-3275` (`_record_gate_drops` scrive `signal_id=None`)
  * timestamp: intera giornata 2026-08-07
  * snippet/query:
    ```sql
    SELECT count(*) FILTER (WHERE signal_id IS NULL), count(*) FROM execution_decisions
    WHERE created_at::date='2026-08-07';  -- 588 | 588
    ```
* Descrizione: la catena segnale → decisione → trade non è ricostruibile per chiave esterna.
  `signal_score` è presente e permette una ricostruzione per valore, ma è ambigua quando due
  segnali sullo stesso simbolo hanno lo stesso punteggio (oggi accade: MU ha 4 righe a 0,000).
* Impatto: nessuno oggi sul money-path; alto sull'auditabilità della finestra di osservazione.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato. Popolare `signal_id` anche sulle righe di scarto.
* Test/monitor consigliato: invariante "nessuna riga di `execution_decisions` con `signal_score`
  non nullo e `signal_id` nullo".

### [DAY-007] `trades.slippage_est` è una copia di `cost_usd`

* Tipo: Bug
* Area: PnL
* Evidenza:
  * file/log/tabella: `trades` id 670 (BRK.B)
  * timestamp: 2026-08-07 14:22:00 UTC
  * snippet/query:
    ```sql
    SELECT symbol, slippage_est, cost_usd FROM trades WHERE exit_time::date='2026-08-07';
    -- BRK.B | 0.3702988971795879 | 0.3702988971795879
    ```
* Descrizione: i due campi sono bit-identici. La qualità di esecuzione (differenza fra prezzo
  atteso al momento della decisione e prezzo di fill) non è misurata da nessuna parte.
* Impatto: non quantificabile — è esattamente la grandezza che servirebbe per quantificarlo.
* Severità: Low
* Confidenza: High
* Azione consigliata: già tracciato. Registrare il prezzo di riferimento al momento della
  decisione e calcolare lo slippage come differenza.
* Test/monitor consigliato: assert che `slippage_est != cost_usd` su almeno una riga di test con
  prezzi divergenti.

### [DAY-008] Le finestre beat sono in ora UTC fissa: i primi 37 minuti di sessione non sono coperti

* Tipo: Bug
* Area: Ops
* Evidenza:
  * file/log/tabella: `src/workers/celery_app.py` righe 78, 93, 142, 153, 175, 201, 219 (`hour="14-21"`)
  * timestamp: 2026-08-07 13:30–14:07 UTC
  * snippet/query: primo `portfolio_cycles` del giorno = `2026-08-07 14:07:00.630195+00`; apertura EDT = 13:30 UTC
* Descrizione: tutte le schedule intraday sono ancorate a `hour="14-21"` UTC, corrispondente a
  09:00–16:00 EST. In EDT (marzo–novembre) la sessione apre alle 13:30 UTC, quindi i primi 37
  minuti — che nelle giornate news-driven concentrano la maggior parte del movimento — non hanno
  né ingest, né scoring, né ciclo portfolio.
* Impatto: il 07/08 il movimento è stato quasi tutto intraday (SPCX: gap +0,04%, intraday +15,78%),
  quindi la finestra persa è la più densa. Non quantificabile su un giorno con 0 ordini S4.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato. Ancorare le schedule al calendario Alpaca invece che a un'ora
  UTC fissa.
* Test/monitor consigliato: test che, dato un giorno EDT, il primo ciclo cada entro 10 minuti
  dall'apertura ufficiale.

### [DAY-009] `max_signal_age` è misurato in tempo di parete: due segnali di ieri sera scadono al primo ciclo del giorno

* Tipo: Bug
* Area: Signal
* Evidenza:
  * file/log/tabella: `execution_decisions` (2 righe `SKIP_STALE`), `audit_log` (478 righe `SIGNAL_STALE_SKIP`)
  * timestamp: 2026-08-07 14:07:13 UTC
  * snippet/query:
    ```
    GOOGL  SKIP_STALE  signal 18.6h old > max_age 4h (score -0.229)
    QQQ    SKIP_STALE  signal 19.1h old > max_age 4h (score -0.215)
    ```
* Descrizione: i due segnali sono nati verso la chiusura del 06/08 e sono stati contati come
  vecchi di 18-19 ore perché la finestra di 4h scorre anche a mercato chiuso. In tempo di mercato
  avevano meno di un'ora di vita.
* Impatto: controfattuale corto del giorno, **favorevole al difetto**: onorare i due segnali
  negativi avrebbe chiuso GOOGL (che ha fatto −0,96%, risparmiando $6,63) e QQQ (che ha fatto
  +1,17%, perdendo $9,04) → netto **−$2,41**, cioè oggi il difetto ha fatto guadagnare. Il
  problema resta strutturale: la regola non fa ciò che dichiara.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato. Misurare l'età in minuti di mercato (calendario Alpaca).
* Test/monitor consigliato: test con un segnale generato alle 19:55 UTC del venerdì e valutato al
  primo ciclo del lunedì.

### [DAY-010] `ingestion_stats_daily.duplicates` supera `fetched` di 5,3×

* Tipo: Anomalia
* Area: News / Data
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily`, riga `2026-08-07 / alpaca_benzinga`
  * timestamp: aggiornata 2026-08-07 19:45:01 UTC
  * snippet/query: `fetched=588, queued=382, duplicates=3120`
* Descrizione: il contatore dei duplicati è additivo attraverso le run e conta i confronti, non
  gli articoli; il rapporto è salito da 3,99× (05/08) a 4,0× (06/08) a **5,3×** (07/08). Non è
  verificabile indipendentemente: `news_log` mostra 84 `content_hash` distinti su 139 righe, cioè
  la deduplicazione **per URL/hash funziona** (i 55 "duplicati" in `news_log` sono fan-out
  multi-ticker dello stesso articolo, non fallimenti di dedup).
* Impatto: non economico; il contatore non è utilizzabile come metrica di qualità dell'ingest.
* Severità: Low
* Confidenza: Medium
* Azione consigliata: già tracciato. Chiarire la semantica del contatore o resettarlo per run.
* Test/monitor consigliato: invariante `duplicates <= fetched` per (giorno, fonte).

### [DAY-011] La suite di test scrive nel database di produzione (righe `source='reuters'`)

* Tipo: Bug
* Area: Data / Ops
* Evidenza:
  * file/log/tabella: `ingestion_stats_daily` riga `2026-08-07 / reuters`; `tests/workers/test_rss_ingestion.py:14`, `tests/connectors/test_rss.py:29`
  * timestamp: `updated_at = 2026-08-07 09:02:07.249131+00`
  * snippet/query:
    ```sql
    SELECT * FROM ingestion_stats_daily WHERE day='2026-08-07' AND source='reuters';
    -- fetched=16 queued=16 discarded_no_ticker=4
    SELECT count(*) FROM news_log WHERE source='reuters';  -- 0 (in tutta la storia)
    ```
    Nessun task RSS/reuters è registrato nel beat (`grep -n "rss\|reuters" src/workers/celery_app.py` → vuoto).
* Descrizione: 16 fetch da una fonte che il sistema live non interroga, alle 09:02 UTC (fuori da
  qualunque finestra operativa), senza una sola riga corrispondente in `news_log`. Il valore 16 è
  4× il valore osservato il 05/08 e il 06/08 (4 ciascuno), coerente con più esecuzioni della suite.
* Impatto: contamina i contatori di ingest usati come evidenza nella finestra di osservazione.
  Nessun impatto sul money-path (non produce segnali né ordini).
* Severità: **High** (contamina l'evidenza, che è esattamente ciò che la carta chiede di
  proteggere)
* Confidenza: High
* Azione consigliata: ticket di correttezza — la suite deve puntare a un database separato o
  fallire se `DATABASE_URL` è quello di produzione. Passa il test di esenzione della carta:
  senza la correzione, i contatori raccolti nelle prossime settimane sono sbagliati.
* Test/monitor consigliato: fixture che rifiuta di connettersi a un DSN contenente l'host di
  produzione; alert su righe `ingestion_stats_daily` con `source` fuori dalla lista dei connettori
  attivi.

### [DAY-012] Il 55% delle righe scorate proviene da articoli fan-out multi-ticker

* Tipo: Bug
* Area: News / LLM
* Evidenza:
  * file/log/tabella: `news_log` (07/08), raggruppamento per `content_hash`
  * timestamp: intera giornata
  * snippet/query:
    ```sql
    SELECT content_hash, count(*), string_agg(DISTINCT ticker,',')
    FROM news_log WHERE created_at::date='2026-08-07' GROUP BY 1 HAVING count(*)>1 ORDER BY 2 DESC;
    -- 138f3a60… ×10  AAPL,AMZN,GOOGL,META,MSFT,MU,NVDA,QQQ,SPCX,SPY
    --   "Chinese Buying Lifts Gold And Silver From Technical Support"
    ```
* Descrizione: 76 righe su 139 sono copie dello stesso articolo assegnate a ticker diversi. Un
  pezzo su oro e argento genera un "sentiment specifico" su AAPL, su SPY e su altri otto nomi;
  un pezzo sulle dichiarazioni di Trump sui data center ne genera sette. Il costo LLM viene
  moltiplicato e il segnale per ticker è, in questi casi, un segnale macro travestito.
* Impatto: 76 chiamate su 139 (55% del budget del giorno, ≈$0,081) spese su attribuzioni deboli.
  Nessun ordine ne è derivato oggi (tutti sotto gate), quindi il costo diretto è la spesa LLM.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato. Distinguere articoli *ticker-specifici* da *menzioni in lista*
  (il campo `directness` di `news_resolved_entities` esiste già) e non scorare i secondi come
  segnali per-ticker.
* Test/monitor consigliato: metrica giornaliera "quota di righe scorate con `content_hash`
  condiviso da >3 ticker".

### [DAY-013] La latenza di ingestione consuma un terzo della finestra di freschezza

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log` (07/08), `news_queue_drops`, `src/config.py:287` (`MAX_NEWS_AGE_HOURS=2`)
  * timestamp: intera giornata
  * snippet/query:
    ```
    latenza published_at → created_at:  benzinga  mediana 43,6 min / media 57,8 min
                                        gdelt_gkg mediana 30,6 min / media 37,9 min
    news_queue_drops: 138 articoli, età minima 2,04h
    ```
* Descrizione: la finestra di entry-freshness è 2,0h; l'articolo entra nel sistema già vecchio di
  43,6 minuti in mediana (36% della finestra) e fino a 106 minuti nei casi peggiori (AMAT id 6976,
  scorato alle 19:30 su un articolo delle 17:45). L'età minima degli articoli scartati è 2,04h,
  cioè il taglio è netto al bordo.
* Impatto: non quantificabile isolatamente oggi (0 ordini S4). Si somma a [DAY-008] e a F-030
  ("al primo punteggio utile è già passato l'82% del movimento").
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato. Ridurre il ritardo fra fetch e scoring (oggi ingest e
  sentiment sono su due cadenze sfasate: minuti 12/27/42/57 e 7/22/37/52).
* Test/monitor consigliato: percentile 90 della latenza `published_at → created_at` nel report
  giornaliero, con soglia di allarme.

### [DAY-014] I log dei container del 2026-08-07 non esistono più

* Tipo: Bug (osservabilità)
* Area: Ops
* Evidenza:
  * file/log/tabella: `docker compose ps` — `alembic-worker-1`, `alembic-worker-inference-1`,
    `alembic-api-1`, `alembic-beat-1` ricreati **26 ore fa** (≈2026-08-09 12:30 CEST)
  * timestamp: analisi eseguita il 2026-08-10
  * snippet/query: `docker compose logs worker --since 96h` non contiene alcuna riga anteriore al
    riavvio; 6.555 righe totali, tutte post-redeploy
* Descrizione: il redeploy sostituisce i container e con essi il file di log JSON. Ogni analisi
  forense eseguita più di un ciclo di deploy dopo la giornata target perde gli errori a runtime,
  i warning di rete, i tempi di risposta Ollama e i restart. Questo report ha ricostruito tutto
  dal database, che copre il money-path ma non i fallimenti silenziosi.
* Impatto: non economico. Rende non verificabili le categorie "eccezioni silenziose", "errori non
  propagati ad alert" e "worker restart events" per il 07/08.
* Severità: Medium
* Confidenza: High
* Azione consigliata: già tracciato. Driver di logging persistente (o spedizione a file su volume)
  prima che il periodo di osservazione arrivi alla sintesi del giorno 40.
* Test/monitor consigliato: check giornaliero che i log coprano almeno le ultime 72h.

### [DAY-015] `org_lookup` attribuisce 30 articoli ai ticker bancari perché la banca compare come casa di analisi

* Tipo: Bug
* Area: News
* Evidenza:
  * file/log/tabella: `news_log` (07/08), `extraction_method='org_lookup'`
  * timestamp: intera giornata
  * snippet/query:
    ```
    MS ×19  "Halozyme Therapeutics Upgraded to Outperform at Leerink Partners"
            "Resideo Technologies Now Covered by JPMorgan Chase & Co."
            "Somnigroup International Price Target Cut by Truist Financial"
    DB ×5   "Piper Sandler Reiterates Neutral Rating for Collegium Pharmaceutical"
    GS ×4   "Atlassian Soars 34%, Twilio Leaps 27%…"
    C  ×2
    ```
* Descrizione: 30 righe su 139 (22%) sono attribuite a MS/DB/GS/C perché il nome della banca
  compare nel boilerplate come emittente del rating, non come soggetto della notizia.
* Impatto: **mitigato oggi**: tutti i 19 articoli MS hanno ricevuto score **0,000** dall'LLM, che
  ha correttamente riconosciuto l'irrilevanza (media |score| su MS = 0,000; DB 0,042; GS 0,009).
  Il costo è la spesa LLM sprecata (~22% del budget, ≈$0,033) e il rumore nel golden set QX-01.
* Severità: Low (oggi) / Medium (strutturale)
* Confidenza: High
* Azione consigliata: già tracciato. Il resolver deterministico ha già il concetto di
  `directness`; usarlo per scartare le menzioni da boilerplate prima dello scoring.
* Test/monitor consigliato: caso di regressione con un titolo "X Upgraded to Outperform at
  Morgan Stanley" che non deve produrre una riga ticker=MS.

### [DAY-016] 11 posizioni su 48 non hanno attribuzione di strategia

* Tipo: Anomalia (debito storico)
* Area: Data
* Evidenza:
  * file/log/tabella: `trades` (posizioni aperte)
  * timestamp: fotografia al 2026-08-07
  * snippet/query:
    ```sql
    SELECT count(*) FILTER (WHERE stop_strategy IS NULL), count(*)
    FROM trades WHERE exit_time IS NULL;  -- 11 | 48
    ```
* Descrizione: 11 posizioni (BAC, GOOGL, GS, MS, PBR, RIO, ROKU, SPY, UBS, UNH, XLE — tutte
  aperte il 2026-07-10) precedono la patch `stop_strategy` e non hanno né strategia né
  `stop_mode`. Portano $23,55 di MTM il 07/08.
* Impatto: il P&L per strategia della finestra di osservazione ha un 23% del libro non
  attribuibile. Non è correggibile retroattivamente senza inventare dati.
* Severità: Low
* Confidenza: High
* Azione consigliata: già tracciato. Trattare esplicitamente il blocco "legacy" come una terza
  colonna nella sintesi del giorno 40, non fonderlo in S1.
* Test/monitor consigliato: invariante "ogni nuova riga `trades` ha `stop_strategy` non nullo".

---

## 11. False positive e aree risultate corrette

| area | verifica | esito |
|---|---|---|
| **Churn intraday / SELL→BUY→SELL** (F-013) | 2 ordini su simboli distinti | **nessun churn** — con #185 live il pattern è scomparso |
| **Ordini duplicati / race scheduler** | nessun ordine identico nello stesso minuto | corretto |
| **Loop reversal S1↔S4** | nessuna posizione contesa fra le due strategie oggi | corretto |
| **Ollama giù / fallback FinBERT di massa** | 0 righe `model_id='finbert'`, `consecutive_fallback=0` | **Ollama up 100%** |
| **Budget LLM** | $0,1478, `budget_exhausted=false` | corretto |
| **Deduplicazione content-hash** | 84 hash distinti su 139 righe; i "duplicati" sono fan-out per ticker, non fallimenti di dedup | corretto |
| **Sanitizzazione input** | `extraction_method` popolato 139/139; nessun campo nullo; nessun timestamp futuro | corretto |
| **Idempotenza** | `_idempotency_skip` per signal_id, nessun doppio inserimento | corretto |
| **Anti-pyramiding** | funziona (è il *log* a mancare, non il guard) — vedi [DAY-001] | comportamento corretto |
| **Stopgap soglia S4 0,45→0,30** | 584/584 righe `SKIP_THRESHOLD` citano 0,300 | **deroga applicata correttamente per l'intera sessione** |
| **Deploy #185** | `orders_count` medio da 48,7 a 2,8; `strategy:rebalance_state:S1` scritta alle 14:07 | **verificato in produzione dal 07/08** |
| **Kill-switch / halt** | `system:halted_by_operator` vuoto, nessun blocco | corretto |
| **Paper mode** | tre fonti concordi | corretto |
| **Ordini fuori orario** | nessuno | corretto |
| **Riconciliazione DB↔snapshot** | 48 posizioni in `trades` = 48 in `portfolio_monitor_snapshots` | corretto |
| **Shadow stop** | 1.153 righe in `stop_shadow_log` il 07/08 | attivo |

Nota su `stop_decisions`: la tabella è ferma al 2026-07-14. **Non è un'anomalia**: è la tabella del
ramo `vol_scaled`, non in uso; il percorso attivo è `stop_shadow_log` (shadow) più gli stop GTC
lato broker (`trades.exit_order_ids`, popolato su WDC).

---

## 12. Dati mancanti o non accessibili

| dato | stato | query/passo che servirebbe |
|---|---|---|
| Log container del 07/08 | **perso** (redeploy del 09/08) | vedi [DAY-014] |
| API REST locale | **non accessibile** — il bearer token fornito restituisce `{"detail":"Invalid or expired JWT token"}` su tutti gli endpoint | rigenerare il token; l'analisi è stata condotta interamente su Postgres/Redis, che sono la fonte primaria |
| Latenza per chiamata LLM | **non registrata** | aggiungere `latency_ms` a `llm_responses` (esiste già in `llm_shadow_responses`, che però ha 0 righe) |
| Slippage reale | **non registrato** | vedi [DAY-007] |
| Prezzo atteso al momento della decisione | **non registrato** | necessario per slippage e per il controfattuale degli ordini bloccati |
| Motivo di scarto degli ordini target | **non registrato** | vedi [DAY-001] |
| `exit_mechanism` | NULL su tutte le righe del giorno | non usato in questo report (vedi §9) |
| Restart dei worker il 07/08 | **non verificabile** | conseguenza di [DAY-014] |
| PSI / drift / composite IC | `performance_metrics` vuota per 05–08/08 | verificare che il task giornaliero di performance stia girando |
| Attribuzione strategia su 11 posizioni | **irrecuperabile** | vedi [DAY-016] |

---

## 13. Raccomandazioni immediate

Tutte dentro il perimetro consentito dalla carta di osservazione (correttezza e strumentazione, mai
taratura):

1. **Persistere il motivo di scarto degli ordini target** ([DAY-001], [DAY-004]). Oggi un giorno in
   cui S4 è stata bloccata 17 volte è indistinguibile da un giorno senza segnali. È la singola
   correzione che vale di più per la validità dei 40 giorni.
2. **Isolare il database di test da quello di produzione** ([DAY-011]). Passa esplicitamente il
   test di esenzione: senza, i contatori di ingest della finestra sono sporchi.
3. **Dare a `preserve-stale` un tetto assoluto** ([DAY-003]). WDC da sola vale −$342,7 non
   realizzati e sporca il P&L economico di S4, che è la grandezza della domanda di uscita n.1.
4. **Separare `fallback_used` (FinBERT) da `degraded_ensemble` (un solo LLM cloud)** e correggere
   `eligible` ([DAY-002]). Senza, la LOO-ICIR pesa i modelli su 17 risposte su 139.
5. **Logging persistente prima del giorno 40** ([DAY-014]).
6. **Non toccare nulla di tarabile**: soglia 0,30, filtro #108, `max_signal_age`, guard P0-05,
   cooldown. Restano congelati fino al 28/09.

## 14. Test o monitor da aggiungere

| # | test/monitor | difetto coperto |
|---|---|---|
| T1 | assert per ciclo: `orders_target = orders_submitted + Σ(scarti loggati)` | [DAY-001], [DAY-004] |
| T2 | contatore giornaliero `s4_entries_blocked_by_pyramiding` nel report forense | [DAY-001] |
| T3 | invariante `count(llm_responses.eligible) ≥ 2 × count(segnali ensemble)` | [DAY-002] |
| T4 | alert su posizione S4 più vecchia di `max_signal_age_hours × K` senza segnale fresco | [DAY-003] |
| T5 | test: NAV in salita ⇒ nessuna metrica di drawdown del giorno > drawdown effettivo | [DAY-005] |
| T6 | invariante: `signal_score` non nullo ⇒ `signal_id` non nullo | [DAY-006] |
| T7 | test del primo ciclo in EDT: deve cadere entro 10 min dall'apertura | [DAY-008] |
| T8 | test: segnale delle 19:55 UTC venerdì, valutato lunedì, non è "stale" in minuti di mercato | [DAY-009] |
| T9 | invariante `duplicates ≤ fetched` per (giorno, fonte) | [DAY-010] |
| T10 | fixture che rifiuta un DSN di produzione; alert su `source` fuori dai connettori attivi | [DAY-011] |
| T11 | metrica giornaliera "quota righe scorate con `content_hash` su >3 ticker" | [DAY-012] |
| T12 | P90 della latenza `published_at → created_at` nel report giornaliero | [DAY-013] |
| T13 | check che i log dei container coprano ≥72h | [DAY-014] |
| T14 | regressione: "X Upgraded at Morgan Stanley" non genera ticker=MS | [DAY-015] |
| T15 | invariante: ogni nuova riga `trades` ha `stop_strategy` non nullo | [DAY-016] |

## 15. Ticket tecnici suggeriti

Solo difetti di **correttezza**, come impone la carta. Nessuna taratura.

| id proposto | titolo | difetto | priorità |
|---|---|---|---|
| TK-A | `SKIP_PYRAMIDING`: persistere in `execution_decisions` ogni BUY scartato dal guard P0-05 | [DAY-001] | **P0** |
| TK-B | La suite di test non deve poter scrivere sul DB di produzione | [DAY-011] | **P0** |
| TK-C | Tetto assoluto a `preserve-stale` per le posizioni S4 | [DAY-003] | **P1** |
| TK-D | Separare `degraded_ensemble` da `fallback_used`; correggere `llm_responses.eligible` | [DAY-002] | **P1** |
| TK-E | `portfolio_cycles.orders_submitted` accanto a `orders_count` | [DAY-004] | P1 |
| TK-F | Riconciliare le tre definizioni di drawdown e allineare la soglia dell'alert al config | [DAY-005] | P1 |
| TK-G | Popolare `execution_decisions.signal_id` anche sulle righe di scarto | [DAY-006] | P2 |
| TK-H | Logging persistente dei container (driver o volume) | [DAY-014] | P2 |
| TK-I | Ancorare le schedule beat al calendario Alpaca invece che a `hour="14-21"` UTC | [DAY-008] | P2 |
| TK-J | `max_signal_age` in minuti di mercato | [DAY-009] | P2 |
| TK-K | Registrare prezzo di riferimento della decisione e calcolare lo slippage reale | [DAY-007] | P2 |
| TK-L | Usare `directness` per non scorare le menzioni da boilerplate e i fan-out macro | [DAY-012], [DAY-015] | P2 |

## 16. Stato sistema

| voce | valore |
|---|---|
| **Ollama** | **UP** per l'intera sessione (14:01–19:45 UTC). Downtime: **0 ore**. 278/278 risposte ricevute, 0 timeout, 0 parse failure |
| **FinBERT fallback rate** | **0,0%** (0 segnali su 139 con `model_id='finbert'`; `fallback_counters.consecutive_fallback = 0`, ultimo incremento 05/08 17:15) |
| **Ensemble degradato a un solo modello** | 54/139 = **38,8%** (47 `single:gpt-oss`, 7 `single:glm-5.2`) — **non** è un fallback FinBERT, vedi [DAY-002] |
| **Budget LLM** | $0,1478 / giorno · 76.887 token in · 9.209 out · `budget_exhausted = false` |
| **Coppia modelli attiva** | `glm52,gptoss` (corretta) · pesi glm 0,601 / gpt-oss 0,399 |
| **Soglia ingresso S4** | 0,30 per l'intera sessione (stopgap del 07/08 tenuto; TTL Redis ancora attivo al momento dell'analisi) |
| **Worker restart events** | **non verificabile** — log persi con il redeploy del 09/08 ([DAY-014]) |
| **Cicli portfolio** | 24/24 eseguiti, nessuno saltato, nessun `constraints_fired` |
| **Kill-switch / halt operatore** | non attivi |
| **Health container** | api healthy, postgres healthy, redis healthy, worker/worker-inference/beat up |
| **Modalità broker** | **paper** (`https://paper-api.alpaca.markets`) |

---

*Report generato in sola lettura. Nessun file di codice o configurazione è stato modificato,
nessun worker avviato, nessun ordine inviato.*
