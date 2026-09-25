# Alpha Miss Report — 2026-09-18

Contratto: `alpha_miss_prompt_v2`, dossier `schema_version` 3.1. Fonte numerica unica: `docs/evidence/dossier/2026-09-18.json` (generato 2026-09-25T08:00:36Z, `fonte_prezzi`: Alpaca SIP adjustment=all). Soglia mover pre-registrata `soglia_mover`=0,03; gate `soglia_gate_usata`=0,30. Report scritto a posteriori (2026-09-25): il dossier è stato rigenerato il 25/09 e nessun report forense della seduta esiste (`docs/FORENSIC_DAILY_REPORT_2026-09-18.md` assente), quindi nessuna occorrenza del 18/09 è già nel ledger.

## 1. Decision card

1. **Il mover più forte della watchlist (HOOD +9,12%) aveva un segnale sopra gate che S4 non ha mai valutato**: +0,338 ISSUER_SPECIFIC alle 13:51 ("Robinhood's 24/7 Stock Dream Just Got A Boost From The SEC"), sovrascritto 8 minuti dopo da +0,073 su un articolo CFTC non confermato, prima del primo ciclo delle 14:07 — `opportunity_v2.net_opportunity_usd`=**72,99 $**.
2. **Su 110 intenti S4 eseguibili ne è stato sottomesso 1** (AVGO); 96 (87,3%) finiscono `SKIP_PYRAMIDING`, fra cui AMAT (+6,51%, secondo mover della giornata) bloccato alle 19:22 perché già detenuto da S1.
3. **L'unico ingresso del giorno è uscito su un articolo fan-out**: AVGO comprato 15:52 su +0,368 issuer-specific, venduto 19:37 `below_entry_gate` perché un pezzo sugli ETF semis a 7 ticker ha scorato +0,115; realizzato −3,03 $, `drift_post_uscita` +5,94 $. Realizzato di seduta **−17,78 $**, tutto S4.

## 2. Stato carta

Da `docs/evidence/economic_pnl.json`, **as_of 2026-09-17** (i cumulati arrivano al giorno osservato precedente al 18/09; questa seduta non è ancora nel ledger).

- Giorno **30/40** della finestra di osservazione (inizio 2026-08-03, `minimo_giorni`=40).
- Quota NO_NEWS dominante: **13/30 = 43,3%**, sotto la soglia carta 0,60 (`superata_soglia`=false).
- S4 economico cumulato: **−696,33 $** vs banda ±200 $ (`within`=false — fuori banda; il 16/09 era −979,55 $, il rientro parziale è del solo 17/09).
- Book cumulato: **−66,22 $**. S1 cumulato +664,95 $ contro un benchmark SPY di +943,98 $ sulla stessa base di capitale (`delta_vs_spy` = **−279,03 $**).
- `docs/evidence/longitudinal_panels.json` **non esiste**: i denominatori del §8 sono contati dalle occorrenze di `findings.json` e dichiarati come tali.

## 3. Miss del giorno

7 candidati in `candidati_miss`, tutti mover non detenuti. `funnel_v2.conteggi_pipeline`={"NO_RELEVANT_NEWS":2,"BELOW_GATE":1,"RANKED_OUT":1}; 3 righe `non_actionable_long_only`.

| Simbolo | Return% | Categoria | Campo del dossier che decide |
|---|---:|---|---|
| HOOD | +9,12% | **FILTERED** | `funnel_v2.righe[HOOD].pipeline`="RANKED_OUT" (stadio oltre il gate), `evidence.reason_codes`=["SKIP_ENTRY_GATE","SKIP_ENTRY_FRESHNESS"]; `causa_legacy`="NON_CLASSIFICATO". Il meccanismo che scarta è la **selezione del segnale**, non il gate: `max_score_own`=0,338 (signal 11568, 13:51, ISSUER_SPECIFIC) non compare in nessuno dei 24 intenti HOOD di `intenti_ingresso_s4`; il primo intento (14:07) valuta il signal 11578 (+0,073, 13:59, `relevance`=TAG_UNCONFIRMED, `attribution`=UNKNOWN). Lettura degli articoli: il 13:51 è un pezzo issuer-specifico sul percorso SEC per le azioni tokenizzate (catalizzatore diretto per Robinhood); il 13:59 parla di mercati predittivi CFTC per app terze senza nominare Robinhood nel testo letto. Poi +0,006 (14:30, template "How Much You Would Have Made", content-mill) e +0,26 (16:45, "Robinhood Stock Rises with Bitcoin…", retrospettivo, sotto gate). Vedi §8, F-023. |
| BABA | +4,33% | **THIN_NEUTRAL** | `funnel_v2.righe[BABA].pipeline`="BELOW_GATE", `evidence.score_firmato`=+0,169 < `soglia_gate` 0,30, segno corretto. Unica riga: GDELT 14:45 "Alibaba Climbs 3%, PDD and JD.com Tick Up…" — retrospettiva, constata il rialzo. `net_opportunity_usd`=**−2,59 $**: entrando al primo ciclo utile (14:52 @113,31) si chiudeva a 113,24, quindi il gate qui non è costato nulla. |
| ARM | +4,04% | **NO_NEWS** | `news_count`=0, `funnel_v2.righe[ARM].pipeline`="NO_RELEVANT_NEWS", `evidence.rilevanza` tutto a 0. `net_opportunity_usd`=66,75 $. |
| TXN | +3,29% | **NO_NEWS** | `news_count`=0, `funnel_v2.righe[TXN].pipeline`="NO_RELEVANT_NEWS". `net_opportunity_usd`=30,50 $. Zero righe da 4 sedute (`blind_set.per_ticker[TXN].sedute_consecutive_zero_articoli`=4). |
| QCOM | −5,82% | **OUT_OF_STRATEGY_SCOPE** | `funnel_v2.righe[QCOM].actionability`="NON_ACTIONABLE", `pipeline_escluso_motivo`="non_actionable_long_only". Campo grezzo `causa`="OFF_TOPIC_NON_DECIDIBILE": 3 righe, tutte fan-out (`quota_righe_fanout`=1,0) — due flash Reuters sulla cena di Stato per Xi Jinping e il roundup macro delle 16:55. Nessuna riga su Qualcomm; residuo vs SOXX −8,51%. |
| NFLX | −4,67% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE" (ribasso non detenuto, long-only). Qui il segnale **c'era ed era giusto**: `max_score_own`=−0,538, tre righe ISSUER_SPECIFIC tra −0,52 e −0,54 sul downgrade Wells Fargo (Equal-Weight→Underweight, PT 80→57), di cui due ANTICIPATORY (pubblicate 12:53, scorate 13:43, prima dell'open). Non azionabile per perimetro — vedi §9b, F-040. |
| IBM | −3,45% | **OUT_OF_STRATEGY_SCOPE** | `actionability`="NON_ACTIONABLE". Campo grezzo `causa`="BELOW_GATE": unica riga −0,12 `fallback`=true dal roundup macro "Bitcoin Tops $80,000, S&P 500 Slips…" (fan-out, 18 ticker). Nessuna notizia su IBM. |

**Conteggi**: NO_NEWS 2 · THIN_NEUTRAL 1 · WRONG_SIGN 0 · FILTERED 1 · OUT_OF_STRATEGY_SCOPE 3. (`aggregati.cause_del_giorno` invariato per vincolo #288: {"NO_NEWS":2,"BELOW_GATE":2,"OFF_TOPIC_NON_DECIDIBILE":1,"NON_CLASSIFICATO":2}, `dominante`=null.)

**Nota di metodo**: come nei report precedenti, dove i due divergono prevale l'asse `actionability`/`pipeline` di `funnel_v2` sul campo grezzo `causa`; il valore legacy è riportato per riga. HOOD è FILTERED perché il dossier lo porta a `RANKED_OUT`; la lettura degli intenti precisa che lo scarto avviene nella scelta di quale segnale valutare, a monte del ranking.

### Titoli catturati

Nessun mover tradato in giornata. I 7 mover detenuti all'apertura (`funnel_v2.kpi.held_at_open`: 4 PASSIVE_EXPOSURE, 3 EXIT_RISK) — marcature di seduta ≈ `notional_usd × r/(1+r)` da `copertura_uscita`:

| Simbolo | Return% | Come | Esito |
|---|---:|---|---|
| AMAT | +6,51% | detenuto (S1), nozionale 381 $ | `PASSIVE_EXPOSURE`, ≈ +23,3 $; `ritorno_da_ingresso` resta −25,13%. Intento S4 bloccato da `SKIP_PYRAMIDING` (§8, F-031). |
| MU | +3,92% | detenuto (S4), 1.487 $ | `PASSIVE_EXPOSURE`, ≈ +56,1 $ — l'ingresso tardivo del 17/09 recupera: `ritorno_da_ingresso` +3,78%. |
| ASML | +3,08% | detenuto (S1), 634 $ | `PASSIVE_EXPOSURE`, ≈ +19,0 $. |
| WDC | +4,13% | detenuto (S4), 148 $ | `PASSIVE_EXPOSURE`, ≈ +5,9 $; nozionale residuo al 6,7% di uno slot (caso F-075). |
| GM | −5,10% | detenuto (S1), 833 $ | `EXIT_RISK`, `pipeline_uscita`="EXIT_WRONG_SIGN" (`score_firmato`=+0,174), ≈ −44,8 $. |
| PANW | −3,06% | detenuto (S4), 1.409 $ | `EXIT_RISK`, "EXIT_WRONG_SIGN" (`score_firmato`=0,0), ≈ −44,5 $. |
| DELL | −3,46% | detenuto (S1), 528 $ | `EXIT_RISK`, "STALE_EXIT_SIGNAL" (signal 11235 del 16/09, score 0,0), ≈ −18,9 $; zero righe `news_log`. |

Somma delle marcature ≈ −4 $: il libro ereditato ha incassato i semis e restituito tutto su GM/PANW/DELL. `exit_signal_recall`=0/3; `profitable_capture_rate`=0/4.

## 4. Attività del book

<!-- alpha-miss-book:start -->
<!-- alpha-miss-book-manifest: {"schema":1,"ingressi":["AVGO"],"chiusure":["BA","NVO","AVGO"]} -->

Dati deterministici dal dossier; la prosa seguente li annota e non li sostituisce.

| Tipo | Simbolo | Strategia | Ora UTC | Prezzo | Quantità | P&L netto | Motivo / qualità |
|---|---|---|---|---:|---:|---:|---|
| IN | AVGO | S4 | 15:52 | $356.0500 | 4.0660 | — | percentile 44.93%; denominatore intraday valido |
| OUT | BA | S4 | — | $196.3900 | 7.1955 | −$21.22 | portfolio_sell |
| OUT | NVO | S4 | — | $43.3281 | 33.2014 | +$6.47 | portfolio_sell |
| OUT | AVGO | S4 | — | $355.5000 | 4.0660 | −$3.03 | portfolio_sell |
<!-- alpha-miss-book:end -->

Una giornata quasi ferma: 1 ingresso (AVGO, S4, 15:52) e 3 chiusure S4, tutte `portfolio_sell`. Le tre chiusure hanno cause diverse lette dal log decisionale: BA alle 14:22 per `fallback_filtered` (segnale +0,359 del 17/09 escluso dal ranking perché fallback FinBERT, #108), NVO e AVGO alle 19:37 per `below_entry_gate` su segnali delle 19:16-19:17 (NVO −0,210 sul generico di Ozempic in Canada; AVGO +0,115 da un fan-out). Realizzato −17,78 $ (BA −21,22, NVO +6,47, AVGO −3,03). Due delle tre uscite hanno `drift_post_uscita` positivo (BA +13,02 $, AVGO +5,94 $). L'ingresso AVGO ha `entry_percentile` 0,449 ma `quota_movimento_precedente_al_segnale` 0,835: segnale arrivato a movimento largamente fatto. Il collo di bottiglia della giornata è a monte degli ordini: 110 intenti tradabili su 2.050, di cui 96 `SKIP_PYRAMIDING`, 13 `SKIP_IDEMPOTENCY`, 1 `SUBMITTED`. Le 3 righe SELL di `execution_decisions` sono senza `signal_id` (`decision_signal_id_coverage.regressions`=["SELL","SKIP_PYRAMIDING"]).

## 5. Cecita' lato uscita

Da `copertura_uscita`: 45 posizioni, `n_indeterminati`=**0** — nessuna riga con `cieco_lato_uscita: null`. Una posizione cieca, ancora aperta:

| Ticker | Strategia | `ritorno_da_ingresso` | `sedute_consecutive_senza_righe` | `fonti_osservate_finestra` | Nozionale |
|---|---|---:|---:|---|---:|
| SBUX | S1 | **−9,07%** | 7 | `alpaca_benzinga` | 630,73 $ |

La streak di SBUX cresce (6 il 17/09 → 7). `ritorno_da_ingresso` è la perdita dall'ingresso al close (nessuna uscita in seduta); `ritorno_seduta` del solo 18/09 è −0,87%, sotto soglia mover. `fonti_osservate_finestra` non è vuota: il connettore Benzinga interroga il ticker e non ha reso nulla in 7 sedute, cioè zero resa e non fonte non configurata. PFE, cieca il 17/09, esce dalla lista perché ha una riga oggi (`sedute_consecutive_senza_righe`=0), pur restando a −3,59% dall'ingresso. Aggregato: 13 posizioni a copertura grezza nulla, 21 a copertura effective-timely nulla, 8 in perdita marcata, nozionale cieco **630,73 $**.

## 6. Backstop NO_NEWS

Popolazione `no_news_backstop.population`: 34 simboli a zero righe `news_log` (3 mover, 31 non-mover, `return_missing`=0).

### 6a. Marker calendario

| Simbolo | Return% | `observed_catalysts` | Calendario |
|---|---:|---|---|
| ARM | +4,04% | `[]` | `NOT_OBSERVED` (FMP earnings-calendar e Alpaca Corporate Actions entrambe risposte) |
| TXN | +3,29% | `[]` | `NOT_OBSERVED`, stesse due fonti |
| DELL | −3,46% | `[]` | `NOT_OBSERVED`, stesse due fonti (detenuto: non è fra i candidati miss) |

Nessun marker `CALENDAR` sui mover a zero notizie: `mover_observed`=0/3, contro 1/31 (3,2%) fra i non-mover (settore energy). `calendario_earnings.status`="OBSERVED", `simboli_flaggati`=[]. Il marker, quando c'è, indica un evento a calendario, non un segnale né un ordine.

### 6b. Volume — `POST_HOC_EOD`, non point-in-time

`temporal_validity`="POST_HOC_EOD", `valid_for_signal_evaluation`=false: il volume di seduta è noto solo alla chiusura, quindi nulla qui era disponibile prima del movimento. Nessuna soglia, nessun false-positive rate (valutazione ex-ante in #451).

- Mediana della sorpresa di volume, mover a zero news (n=3): **+79,9%**; non-mover (n=31): **+51,0%**.
- TXN: volume 19.060.944 vs ADV20 5.229.016, sorpresa **+264,5%** — il caso più marcato, con zero righe `news_log` e calendario vuoto.
- ARM: +79,9%. DELL: +19,6%.

### 6c. Copertura raw di `news_log` per settore (tutti i settori)

Copertura **raw**, distinta dalla quota effective-timely di `copertura_articoli.per_settore`.

| Settore | ticker_with_news / ticker_universe | `raw_news_coverage_rate` | mover a zero news |
|---|---:|---:|---:|
| etf_broad | 4/4 | 100,0% | 0 |
| healthcare | 8/9 | 88,9% | 0 |
| semis | 12/15 | 80,0% | 3 (ARM, TXN, DELL) |
| financials | 9/14 | 64,3% | 0 |
| consumer | 7/11 | 63,6% | 0 |
| media | 3/5 | 60,0% | 0 |
| tech | 12/21 | 57,1% | 0 |
| energy | 3/6 | 50,0% | 0 |
| industrials | 2/4 | 50,0% | 0 |
| telecom | 2/5 | 40,0% | 0 |
| materials | 0/2 | **0,0%** | 0 |

Totale: 62/96 con almeno una riga (`watchlist_zero_news`=34). Tutti e tre i mover a zero notizie stanno nel settore con la terza copertura raw più alta: il buco non è settoriale ma per ticker. `materials` (RIO, VALE) resta a zero per la terza seduta osservata consecutiva.

### 6d. Attribuzione fonti per ticker (#511 passo 2)

Ticker con `articoli_unici`=0 (per tutti `fonti_osservate`={} e `effective_timely_articles_giorno`=0, da `blind_set.per_ticker`); tra parentesi `sedute_consecutive_zero_articoli`:

ABBV (2), ADBE (4), ARM (1), BAC (1), BIDU (2), BP (2), CAT (2), CMCSA (2), COST (1), CSCO (5), CVX (1), DB (1), DELL (2), ERIC (10, troncato da `finestra`), HD (5), INFY (6), JD (1), MMM (3), NOW (3), PLTR (1), RIO (5), ROKU (7), SAP (3), SBUX (7), SHEL (3), SNOW (5), T (8), TXN (4), UBS (3), V (1), VALE (2), VZ (4), WFC (1), WMT (1). `ticker_allerta_zero_articoli` (≥5): CSCO, ERIC, HD, INFY, RIO, ROKU, SBUX, SNOW, T.

Fonte presente ma non utile (articoli > 0, effective-timely 0) — per tutti la fonte è solo `alpaca_benzinga`: AMD 2, AMZN 8, AXP 1, AZN 2, C 1, IBM 1, IWM 2, JNJ 1, MA 1, META 6, MSFT 6, PFE 1, PG 1, QCOM 3, QQQ 3, SOXX 3, XLE 3, XLV 1 righe, nessuna effective-timely. Per `per_fonte`: `alpaca_benzinga` 95 articoli unici, 52 effective-timely (54,7%); `gdelt_gkg` 39/39. La scelta dei connettori resta all'operatore (#454/#455/#458/#459).

## 7. Pattern osservato

**Seconda seduta di forza sui semis, con dispersione interna.** 6 degli 8 mover rialzisti sono `semis` (AMAT +6,51%, WDC +4,13%, ARM +4,04%, MU +3,92%, TXN +3,29%, ASML +3,08%), con AVGO +2,97% e AMD +2,70% appena sotto soglia e SOXX +2,69% contro SPY +0,13% e QQQ +0,63%. Il 17/09 il tema era lo stesso (8 semis su 12 mover rialzisti): è la continuazione, non una rotazione nuova. Il comparto però non si muove compatto: QCOM −5,82% (residuo vs SOXX −8,51%, `catalyst`="IDIOSYNCRATIC") e DELL −3,46% vanno nel verso opposto.

Gli altri due rialzisti sono idiosincratici: HOOD (crypto/regolamentazione, Bitcoin sopra 80.000 $, residuo vs XLF +9,15%) e BABA (Cina tech). I 6 ribassisti non hanno un tema comune evidente: GM (auto), NFLX (downgrade analista), IBM, DELL e QCOM (hardware/IT), PANW (security). Pattern lato ribasso: **non chiaro**. Regime osservato SIDEWAYS (`regime_mult` 0,7, VIX 14,81), dispersione cross-sectional 2,18%.

## 8. Segnalazioni

Tre finding esposti oggi con una conseguenza in dollari. Denominatori contati dalle occorrenze di `findings.json` (`longitudinal_panels.json` assente).

### [F-023] S4 non ha mai valutato il segnale issuer-specifico sopra gate sul mover più forte della watchlist, sovrascritto dopo 8 minuti da un segnale debole

- **Meccanismo e fonte**: §3, riga HOOD; `candidati_miss[HOOD].segnali`, `intenti_ingresso_s4`, `funnel_v2.righe[HOOD]`. Signal 11568 (13:51:13, +0,338, ISSUER_SPECIFIC, articolo SEC/tokenized stocks) → signal 11578 (13:59:53, +0,073, TAG_UNCONFIRMED/UNKNOWN, articolo CFTC sui mercati predittivi). Il primo ciclo della seduta (14:07) legge solo l'ultimo: `SKIP_ENTRY_GATE`. Nessuno dei 24 intenti HOOD della giornata porta `signal_id`=11568.
- **Esposizione oggi**: 1 mover `ENTRY_OPPORTUNITY` su 4 ha avuto un segnale sopra gate col segno giusto (`active_signal_recall`=1/2 dei mover con notizia tempestiva: il numeratore è proprio HOOD); quel segnale non è mai arrivato al ranking. Il finding conta 16 occorrenze in `findings.json` prima di oggi, l'ultima il 17/09 (NVDA +0,496 → +0,013 in 76 s).
- **Evidenza contraria**: se il finding fosse falso, il primo intento HOOD delle 14:07 porterebbe il signal 11568 o un punteggio ≥0,30, oppure il 13:59 sarebbe un aggiornamento dello stesso articolo. Invece porta 11578, con `canonical_article_id` diverso e punteggio 0,073.
- **Non-occorrenza**: su AVGO il segnale issuer-specifico +0,368 (15:41) **è** rimasto l'ultimo fino al ciclo delle 15:52 ed è stato eseguito (`SUBMITTED`, trade 1017): quando nessun articolo successivo arriva prima del ciclo, il meccanismo non morde. Su BABA (un solo segnale) il fenomeno non può presentarsi.
- **Next evidence (read-only)**: su `sentiment_signals` della finestra 08-03→09-18, per ogni coppia (ticker, ciclo) contare i casi in cui il massimo |score| ISSUER_SPECIFIC generato nelle 2h precedenti è ≥0,30 mentre l'ultimo segnale prima del ciclo è <0,30, e affiancare il rendimento ciclo→close. Separare le sovrascritture da articolo TAG_UNCONFIRMED/FANOUT da quelle issuer-specifiche, perché solo le prime sono il difetto.
- **Costo**: **72,99 $** (congetturale). Formula: `opportunity_v2.net_opportunity_usd` = (2.200 / 115,91) × (119,82 − 115,91) − 1,23 = 74,21 − 1,23. Ingresso all'open della prima barra eleggibile (14:07, 115,91), uscita al close (119,82), costi da `cost_model.yaml`. Scartato il lordo `gross_opportunity_usd`=200,55 $ (close-to-close): alle 14:07 il 5,1% del movimento era già avvenuto (`ritorno_sessione_al_segnale`=0,0508), quindi non era accessibile.

### [F-031] Il guard anti-pyramiding è il destino dell'87,3% degli intenti eseguibili e blocca il secondo mover della giornata perché detenuto da S1

- **Meccanismo e fonte**: §4; `intenti_ingresso_s4` (`final_reason_code`) e `guard_decisions`. 110 intenti `is_tradable`: 96 `SKIP_PYRAMIDING`, 13 `SKIP_IDEMPOTENCY` (AVGO dopo l'acquisto), 1 `SUBMITTED`. I 96 blocchi: SHEL 24, PBR 24, NVO 21, MS 8, MRK 8, LLY 8, AMAT 3. SHEL, PBR, MS, MRK, LLY e AMAT sono detenuti da **S1** (75 blocchi, 78%); NVO da S4 stessa (21, il guard come progettato). AMAT: signal 11781 (+0,274 grezzo, eseguibile dopo moltiplicatore di velocità — F-073) bloccato alle 19:22, 19:37, 19:52.
- **Esposizione oggi**: 96 intenti esposti; 1 mover colpito (AMAT +6,51%). Tracciabilità: `guard_decisions` ha **7** righe `SKIP_PYRAMIDING` contro 96 intenti (7,3%; era 20% il 17/09), e 2 di queste 7 senza `signal_id`.
- **Evidenza contraria**: se il blocco fosse soprattutto il guard legittimo sulle posizioni aperte da S4, NVO sarebbe la maggioranza; è 21/96.
- **Non-occorrenza**: nessuno dei 7 candidati miss del §3 è stato toccato dal guard (zero intenti `SKIP_PYRAMIDING` per HOOD, BABA, ARM, TXN, QCOM, NFLX, IBM). Il guard spiega solo i blocchi sui titoli già a libro.
- **Next evidence (read-only)**: sulla finestra 08-03→09-18, quota degli intenti `is_tradable` in `SKIP_PYRAMIDING` separata per sleeve detentrice (S1/legacy, S4 aperta in giorni precedenti, S4 aperta nella stessa seduta), con il `counterfactual_return_1h` di `guard_decisions` dove esiste. Se la quota S1 è stabilmente >50% con mediana controfattuale positiva, il costo è strutturale.
- **Costo**: **37,89 $** (congetturale). Formula: `guard_decisions[35044].intended_notional_usd × counterfactual_return_1h` = 2.185,65 × 0,017337. Limite inferiore: orizzonte di 1 ora e solo il mover AMAT; gli altri 93 blocchi sono su non-mover senza un controfattuale in `guard_decisions`.

### [F-008] Un articolo sugli ETF semis a 7 ticker sostituisce il segnale issuer-specifico di AVGO e ne forza l'uscita 3h45 dopo l'ingresso

- **Meccanismo e fonte**: §4; blocchi `ingressi` e `chiusure` e `copertura_articoli.segnali` del dossier; `execution_decisions` 35164. AVGO comprato alle 15:52 @356,05 sul signal 11644 (+0,368, ISSUER_SPECIFIC, "What Is Going on With Broadcom Stock on Friday?"). Alle 19:16 l'articolo "$3.2T Chip Boom: Which Semiconductor ETFs Get The Biggest Slice?" (Benzinga) produce segnali FANOUT/TAG_UNCONFIRMED su 7 ticker (AMAT 0,274, MU 0,23, SOXX 0,212, TSM 0,15, AVGO **0,115**, AMD 0,10, NVDA 0,068). Ciclo 19:37: SELL `below_entry_gate` ("score=+0.115"), exit 355,50, `pnl_net` −3,03 $.
- **Esposizione oggi**: 3 chiusure S4, di cui 2 `below_entry_gate` alle 19:37 (AVGO, NVO); solo AVGO nasce da un fan-out. Il segno qui non si inverte (+0,368 → +0,115): conta il livello, sceso sotto gate. Il finding conta 14 occorrenze prima di oggi, l'ultima il 22/09 (ARM).
- **Evidenza contraria**: se il finding fosse falso, l'uscita AVGO avrebbe una ragione issuer-specifica (notizia negativa su Broadcom) o il titolo sarebbe sceso dopo l'uscita. Il segnale d'uscita viene da un pezzo di rassegna ETF e il titolo chiude a 356,96 (`drift_post_uscita` +5,94 $).
- **Non-occorrenza**: NVO esce nello stesso ciclo su un −0,210 **issuer-specifico** (generico di Ozempic in Canada): è un'uscita su notizia propria e ha `drift_post_uscita` −2,93 $, quindi ha evitato una perdita. Il fenomeno riguarda solo le uscite decise da righe fan-out.
- **Next evidence (read-only)**: per tutte le SELL `below_entry_gate`/`sentiment_reversal` S4 della finestra, classificare il segnale che le ha causate per `attribution` (FANOUT vs ISSUER_SPECIFIC) e confrontare la mediana di `drift_post_uscita` fra i due gruppi. Se il gruppo FANOUT ha drift sistematicamente positivo e quello ISSUER_SPECIFIC no, l'uscita su fan-out è un costo misurabile.
- **Costo**: **5,94 $** (attribuita). Formula: `drift_post_uscita` = qty × (close − exit) = 4,066 × (356,96 − 355,50); il close 356,96 viene da `ingressi[AVGO].mtm_eod` (3,70 $ = 4,066 × (356,96 − 356,05)). Scartato come alternativa il P&L realizzato −3,03 $: quello misura l'ingresso tardivo (quota 0,835, F-030), non l'uscita.

## 9. Appendice

### (a) Rendimenti completi della watchlist — `mercato.rendimenti`, 96 simboli

`M` = mover ≥ |3%|. "Art." = `copertura_articoli.per_ticker[*].articoli_unici`. "Det." = sleeve della posizione in `copertura_uscita.posizioni` (detenuta all'open RTH).

| Simbolo | Return% | Settore | Art. | Det. | Mover |
|---|---:|---|---:|---|---|
| HOOD | +9,12% | financials | 6 | no | **M** |
| AMAT | +6,51% | semis | 4 | S1 | **M** |
| BABA | +4,33% | tech | 1 | no | **M** |
| WDC | +4,13% | semis | 1 | S4 | **M** |
| ARM | +4,04% | semis | 0 | no | **M** |
| MU | +3,92% | semis | 8 | S4 | **M** |
| TXN | +3,29% | semis | 0 | no | **M** |
| ASML | +3,08% | semis | 1 | S1 | **M** |
| AVGO | +2,97% | semis | 3 | no |  |
| AMD | +2,70% | semis | 2 | S1 |  |
| SOXX | +2,69% | semis | 3 | S1 |  |
| MRVL | +1,45% | semis | 3 | S4 |  |
| NVDA | +1,34% | semis | 13 | no |  |
| CAT | +1,30% | industrials | 0 | S1 |  |
| JD | +1,05% | tech | 0 | no |  |
| TMUS | +1,04% | telecom | 1 | no |  |
| TSM | +1,02% | semis | 3 | S1 |  |
| AMZN | +1,00% | tech | 8 | no |  |
| XLK | +0,82% | tech | 2 | S1 |  |
| PLTR | +0,79% | tech | 0 | no |  |
| NOK | +0,75% | telecom | 1 | S1 |  |
| MMM | +0,72% | industrials | 0 | no |  |
| GOOGL | +0,64% | tech | 11 | S1 |  |
| QQQ | +0,63% | etf_broad | 3 | S4 |  |
| BA | +0,61% | industrials | 2 | S4 |  |
| UNH | +0,45% | healthcare | 2 | S1 |  |
| GE | +0,26% | industrials | 1 | no |  |
| XOM | +0,17% | energy | 1 | S1 |  |
| COST | +0,15% | consumer | 0 | no |  |
| UBS | +0,14% | financials | 0 | S1 |  |
| SPY | +0,13% | etf_broad | 26 | S1 |  |
| AXP | +0,13% | financials | 1 | no |  |
| NVO | +0,12% | healthcare | 1 | S4 |  |
| BRK.B | +0,11% | financials | 20 | no |  |
| JPM | +0,10% | financials | 4 | S1 |  |
| PFE | +0,07% | healthcare | 1 | S1 |  |
| LLY | +0,04% | healthcare | 4 | S1 |  |
| T | +0,04% | telecom | 0 | no |  |
| ABBV | −0,02% | healthcare | 0 | S1 |  |
| XLF | −0,04% | financials | 2 | S1 |  |
| AZN | −0,04% | healthcare | 2 | no |  |
| WMT | −0,06% | consumer | 0 | no |  |
| JNJ | −0,09% | healthcare | 1 | S1 |  |
| MA | −0,09% | financials | 1 | no |  |
| MCD | −0,10% | consumer | 2 | no |  |
| BIDU | −0,11% | tech | 0 | no |  |
| INTC | −0,18% | semis | 5 | S4 |  |
| MRK | −0,19% | healthcare | 1 | S1 |  |
| XLV | −0,25% | healthcare | 1 | S1 |  |
| AAPL | −0,26% | tech | 7 | S1 |  |
| XLE | −0,27% | energy | 3 | S4 |  |
| ROKU | −0,29% | media | 0 | S1 |  |
| V | −0,44% | financials | 0 | no |  |
| MS | −0,46% | financials | 8 | S1 |  |
| IWM | −0,47% | etf_broad | 2 | no |  |
| VZ | −0,50% | telecom | 0 | no |  |
| TSLA | −0,53% | consumer | 5 | no |  |
| CSCO | −0,66% | tech | 0 | S4 |  |
| PBR | −0,67% | energy | 2 | S1 |  |
| RIO | −0,68% | materials | 0 | S1 |  |
| C | −0,70% | financials | 1 | S1 |  |
| CMCSA | −0,74% | media | 0 | no |  |
| BAC | −0,77% | financials | 0 | no |  |
| PG | −0,79% | consumer | 1 | no |  |
| MSFT | −0,80% | tech | 6 | no |  |
| HD | −0,84% | consumer | 0 | no |  |
| SBUX | −0,87% | consumer | 0 | S1 |  |
| WFC | −0,89% | financials | 0 | no |  |
| CVX | −0,97% | energy | 0 | S1 |  |
| GS | −1,00% | financials | 7 | no |  |
| ERIC | −1,17% | telecom | 0 | no |  |
| TM | −1,23% | consumer | 2 | no |  |
| RDDT | −1,30% | media | 1 | no |  |
| SHEL | −1,34% | energy | 0 | S1 |  |
| SPCX | −1,36% | etf_broad | 4 | no |  |
| ADBE | −1,48% | tech | 0 | no |  |
| SONY | −1,55% | tech | 1 | no |  |
| SNOW | −1,76% | tech | 0 | S1 |  |
| VALE | −1,80% | materials | 0 | S1 |  |
| BP | −1,85% | energy | 0 | S1 |  |
| SAP | −1,97% | tech | 0 | no |  |
| ORCL | −1,98% | tech | 4 | no |  |
| CRM | −2,03% | tech | 3 | no |  |
| NOW | −2,17% | tech | 0 | no |  |
| INFY | −2,26% | tech | 0 | no |  |
| NKE | −2,34% | consumer | 1 | no |  |
| META | −2,43% | tech | 6 | no |  |
| DIS | −2,54% | media | 3 | no |  |
| DB | −2,74% | financials | 0 | no |  |
| F | −2,94% | consumer | 3 | no |  |
| PANW | −3,06% | tech | 4 | S4 | **M** |
| IBM | −3,45% | tech | 1 | no | **M** |
| DELL | −3,46% | semis | 0 | S1 | **M** |
| NFLX | −4,67% | media | 5 | no | **M** |
| GM | −5,10% | consumer | 4 | S1 | **M** |
| QCOM | −5,82% | semis | 3 | no | **M** |

### (b) Altri finding aperti toccati dalla giornata

- [F-001] supported — `watchlist_zero_news`=34/96; effective-timely 44/96 (45,8%).
- [F-009] contradicted — l'unico caso sotto gate col segno giusto (BABA +0,169) aveva `net_opportunity_usd`=−2,59 $: il gate non è costato nulla oggi.
- [F-011] supported — 3/3 SELL in `execution_decisions` senza `signal_id`; `regressions`=["SELL","SKIP_PYRAMIDING"].
- [F-012] supported — 242 righe da 134 articoli, `mapping_fanout_extra`=105, TAG_UNCONFIRMED 137/242; QCOM e IBM hanno solo righe fan-out.
- [F-013] supported — AVGO BUY 15:52 → SELL 19:37 sullo stesso simbolo in 3h45 senza banda fra gate e uscita.
- [F-030] supported — AVGO `quota_movimento_precedente_al_segnale`=0,835; ogni riga HOOD issuer-specifica dopo le 14:30 è retrospettiva.
- [F-040] supported — NFLX −4,67% con tre segnali issuer-specifici tra −0,52 e −0,54 (due ANTICIPATORY), non azionabili per il vincolo long-only.
- [F-056] not_exposed — BA uscita per `fallback_filtered` è il filtro #108, non la preferenza non-fallback di `fetch_signals_for_cycle`.
- [F-073] supported — AMAT eseguibile con `signal_score` grezzo 0,274 < 0,30 (blocco `SKIP_PYRAMIDING`, non gate).
- [F-075] supported — WDC conta come mover PASSIVE_EXPOSURE con 147,72 $ di nozionale (6,7% di uno slot).
- [F-076] supported — testi a `&#39;`/`&amp;` nei titoli scorati (es. "S&amp;P 500", "CFTC&#39;s"): la seduta precede il deploy del 21/09.
- [F-082] not_exposed — `guardia_contraddizione.giorno.n_soppressi`=0 su 110 valutabili.

### (c) Casi di successo

Nessun mover catturato con P&L positivo in giornata. L'unica chiusura in utile è NVO (+6,47 $, non mover), uscita alle 19:37 su notizia issuer-specifica negativa prima di un `drift_post_uscita` di −2,93 $.
