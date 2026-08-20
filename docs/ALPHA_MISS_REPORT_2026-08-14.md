# Alpha Miss Report — 2026-08-14

Fonte numerica: `docs/evidence/dossier/2026-08-14.json` (Alpaca SIP, `adjustment=all`), letto e non ricalcolato.
Perimetro: i 96 simboli di `config/trading.yaml → symbols.watchlist`. Nessun simbolo senza barre
(`simboli_senza_dati: []`).
Periodo di sola osservazione (`docs/evidence/OBSERVATION_CHARTER.md`): nessuna proposta di taratura.
Nota sul perimetro dell'emendamento 2026-08-15: la domanda 1 (S4) ha un nuovo `t=0` non ancora fissato
(batch atomico non deployato al 14/08); questa giornata resta nel segmento pre-batch, leggibile per
failure analysis ma non concatenabile al forward della domanda 1. La domanda 2 (S1) non è toccata.

---

## 1. Executive summary

Giornata di dispersione elevata (σ 2,18%) su indici sostanzialmente fermi (SPY −0,20%, QQQ −0,14%):
**8 mover** oltre |3%|, 4 al rialzo e 4 al ribasso. Alembic ne ha in mano **3 su 8** (AMD, WDC, AMAT,
tutte posizioni vecchie di 2-4 settimane, nessuna decisione presa oggi), **5 mancati**: RDDT +12,63%
(il mover più forte della finestra), F +3,46%, AVGO −5,94%, HOOD −3,83%, ORCL −3,65%.

Causa dominante: **THIN_NEUTRAL/BELOW_GATE (4 su 5)** — segnale generato, spesso di segno corretto, ma
sotto il gate 0,30; **NO_NEWS 1 su 5** (F). Zero WRONG_SIGN, zero FILTERED, zero OUT_OF_STRATEGY_SCOPE.
45/96 simboli (47%) hanno zero righe in `news_log` oggi.

Caso di rilievo: **AVGO** ha un articolo genuinamente dedicato ("Broadcom Plunges 5% as Its AI Boom
Faces a $370 Billion Financing Question"), segno corretto, punteggio −0,282 — a un soffio dal gate
0,30 — poi ulteriormente attenuato a −0,226 dal moltiplicatore di signal-velocity prima del log. È la
prima occorrenza pulita di F-009 (il gate scarta segnali col segno corretto) dopo il ripristino del gate
di design a 0,30 (deroga #191, 07-08): le occorrenze precedenti di F-009 erano tutte generate sotto un
gate temporaneamente salito a 0,45. Costo comunque **verificato zero**: AVGO è un mover al ribasso su
libro long-only, non tradabile in ogni caso.

Nessuna chiusura oggi, nessun trade con P&L realizzato. Due ingressi S4 (JD, BA), nessuno dei due un
mover. Equity di fine giornata $110.440,21, variazione NAV del giorno −$23,60. 24 cicli portfolio, nessun
gap oltre 16 minuti.

## 2. Rendimenti completi della watchlist (2026-08-14)

`SI (in book)` = posizione aperta a fine giornata (aperta oggi o ereditata). In grassetto i mover
|return| ≥ 3%.

| simbolo | return | catturato |
|---|---:|---|
| **RDDT** | +12.63% | no |
| **AMD** | +6.50% | SI (in book) |
| **WDC** | +4.41% | SI (in book) |
| **F** | +3.46% | no |
| SONY | +2.88% | no |
| ROKU | +2.34% | SI (in book) |
| MU | +2.30% | SI (in book) |
| TXN | +2.25% | SI (in book) |
| GE | +2.15% | SI (in book) |
| DIS | +1.96% | no |
| NOK | +1.89% | SI (in book) |
| SHEL | +1.49% | SI (in book) |
| XLE | +1.39% | SI (in book) |
| BABA | +1.35% | no |
| TM | +1.27% | no |
| T | +1.26% | no |
| CVX | +1.16% | SI (in book) |
| XOM | +0.94% | SI (in book) |
| WFC | +0.81% | no |
| TSLA | +0.68% | no |
| UNH | +0.67% | SI (in book) |
| BAC | +0.62% | SI (in book) |
| QCOM | +0.61% | no |
| BA | +0.58% | SI (in book) |
| VZ | +0.54% | no |
| IWM | +0.52% | SI (in book) |
| BP | +0.50% | no |
| DB | +0.47% | no |
| GM | +0.44% | SI (in book) |
| C | +0.43% | SI (in book) |
| MA | +0.40% | no |
| ARM | +0.28% | SI (in book) |
| CAT | +0.23% | SI (in book) |
| AAPL | +0.22% | SI (in book) |
| MRK | +0.21% | SI (in book) |
| MCD | +0.21% | no |
| PG | +0.20% | no |
| CMCSA | +0.00% | no |
| MMM | +0.00% | SI (in book) |
| ERIC | +0.00% | no |
| PFE | -0.04% | no |
| PBR | -0.06% | SI (in book) |
| SOXX | -0.06% | SI (in book) |
| NVDA | -0.06% | no |
| MRVL | -0.07% | SI (in book) |
| JPM | -0.07% | SI (in book) |
| COST | -0.08% | no |
| NFLX | -0.10% | no |
| GOOGL | -0.13% | SI (in book) |
| QQQ | -0.14% | SI (in book) |
| XLF | -0.17% | SI (in book) |
| UBS | -0.19% | SI (in book) |
| SPY | -0.20% | SI (in book) |
| ASML | -0.21% | SI (in book) |
| SBUX | -0.22% | SI (in book) |
| MSFT | -0.30% | no |
| GS | -0.31% | SI (in book) |
| AXP | -0.34% | no |
| V | -0.36% | no |
| WMT | -0.39% | no |
| XLK | -0.40% | SI (in book) |
| TMUS | -0.42% | no |
| RIO | -0.45% | SI (in book) |
| MS | -0.47% | SI (in book) |
| AZN | -0.50% | no |
| ABBV | -0.54% | SI (in book) |
| BRK.B | -0.57% | no |
| XLV | -0.60% | SI (in book) |
| SAP | -0.63% | no |
| JNJ | -0.66% | SI (in book) |
| DELL | -0.75% | SI (in book) |
| JD | -0.82% | SI (in book) |
| HD | -0.83% | no |
| META | -0.86% | no |
| SPCX | -0.91% | no |
| AMZN | -0.94% | no |
| TSM | -0.96% | SI (in book) |
| BIDU | -0.96% | no |
| IBM | -1.19% | no |
| NKE | -1.21% | no |
| VALE | -1.23% | SI (in book) |
| CSCO | -1.58% | no |
| NVO | -1.79% | no |
| INTC | -1.97% | SI (in book) |
| LLY | -2.25% | SI (in book) |
| ADBE | -2.39% | no |
| SNOW | -2.51% | SI (in book) |
| NOW | -2.55% | no |
| CRM | -2.56% | no |
| INFY | -2.58% | no |
| PLTR | -2.78% | no |
| PANW | -2.96% | SI (in book) |
| **ORCL** | -3.65% | no |
| **HOOD** | -3.83% | no |
| **AMAT** | -5.12% | SI (in book) |
| **AVGO** | -5.94% | no |

Soglia mover: |return| ≥ 3% (`soglia_mover` del dossier), su una dispersione cross-sectional di 2,18% —
circa 1,38σ — coerente con le soglie usate nelle sedute precedenti della finestra. 8 nomi su 96 (8%),
in linea con la banda 8-13 osservata dal 08-03.

## 3. Miss classificati

| simbolo | return | categoria | evidenza |
|---|---:|---|---|
| RDDT | +12,63% | THIN_NEUTRAL | Il mover più forte dell'intera finestra e **zero copertura dedicata**: 2 righe in `news_log`, entrambe rassegne fan-out Benzinga — "Heartflow, Eton Pharmaceuticals, Nu Holdings And Other Big Stocks Moving Higher On Friday" (13:55) e "Russell 2000 Extends Records, SanDisk Rallies 7%: Stock Market Today" (17:22) — nessuna delle due parla di Reddit. Segnali 14:15 **0,000** (ensemble, conf 0,15) e 18:00 **+0,04** (single-model fallback, conf 0,40). 7 righe `SKIP_THRESHOLD` fra le 14:22 e le 15:52, tutte a punteggio zero. |
| AVGO | −5,94% | THIN_NEUTRAL (BELOW_GATE) | **Unico caso del giorno con un articolo genuinamente dedicato**: "Broadcom Plunges 5% as Its AI Boom Faces a $370 Billion Financing Question" (17:08). Segnale 17:30 **−0,282** (ensemble non-fallback, conf 0,60) — segno corretto, magnitudine a **6 centesimi dal gate 0,300**. Prima del confronto col gate il punteggio viene ulteriormente attenuato dal moltiplicatore di signal-velocity (`portfolio_scheduler.py:4271-4298`, velocità negativa → ×0,80) a **−0,226**, loggato alle 17:37 come "score 0.226 < feedback threshold 0.300" — il segno si perde nel testo (`abs(sig_score)`, stesso meccanismo di F-006). L'attenuazione non cambia l'esito: −0,282 era già sotto gate. Mover al ribasso, libro long-only, posizione non detenuta: **costo verificato zero**. Vedi F-009 e F-006 in §7. |
| HOOD | −3,83% | THIN_NEUTRAL | 2 righe in `news_log`: una rassegna generica (15:02, "Micron and 15 Other Stocks...") e una **HOOD-specifica ma tonalmente disallineata al movimento** — "Robinhood Exec Says AI Boom Could Keep Stocks Ripping Higher..." (16:30), un commento ottimista di un dirigente mentre il titolo perde il 3,8%. Segnali **entrambi single-model fallback**: 15:45 −0,04, 17:01 +0,072 — segno instabile, magnitudine irrilevante in entrambi i casi. **Zero righe in `execution_decisions`**: nessun segnale non-fallback nella finestra di 4h della strategia, ma HOOD ha un vecchio segnale ensemble dell'08-13 (+0,013) che rientra nel lookback di 96h e sopprime il log SKIP_FALLBACK — stesso meccanismo isolato l'08-11 su AVGO (F-006, ticket TK-F). Mover al ribasso, long-only: costo verificato zero. |
| ORCL | −3,65% | THIN_NEUTRAL (BELOW_GATE) | Un articolo genuinamente dedicato — "Michael Burry Doubles Down on Oracle, Micron Nebius Shorts After Saying It's Like 'Shooting Fish in a Barrel'" (14:02) — segno corretto ma segnale **−0,112** (ensemble, conf 0,40), sotto gate di oltre un terzo. Un secondo segnale delle 15:45, −0,039, diluito dalla stessa rassegna fan-out che tocca AVGO e RDDT. 7 righe `SKIP_THRESHOLD` fra le 15:22 e le 16:52. Mover al ribasso, long-only: costo verificato zero. Corroborazione secondaria per F-009 (segno corretto, gate design 0,30). |
| F | +3,46% | NO_NEWS | **Zero righe in `news_log`, zero segnali, zero righe in `execution_decisions`**: nessuna catena decisionale esiste. Mover al **rialzo** — la direzione era accessibile a un motore long-only. |

Conteggi del giorno: **NO_NEWS 1 · THIN_NEUTRAL 4 (di cui 3 taggate `BELOW_GATE` dal dossier) · WRONG_SIGN 0 ·
FILTERED 0 · OUT_OF_STRATEGY_SCOPE 0**.

Nota sui costi: solo due dei cinque miss hanno un costo congetturale positivo — RDDT (+12,63% × size S4
tipica $2.200 = **$277,85**) e F (+3,46% × $2.200 = **$76,03**). I tre mover al ribasso (AVGO, HOOD, ORCL)
sono **verificati a costo zero**: il libro è long-only e nessuno dei tre era detenuto, quindi nessun
controfattuale di uscita esisteva.

## 4. Titoli catturati — esito

### 4.1 Mover tenuti passivamente (3)

Nessuna decisione presa oggi su questi tre nomi: sono posizioni aperte da 3-4 settimane.

| simbolo | strategia | dall'apertura | return oggi | MTM oggi (stimato da qty × Δclose) |
|---|---|---|---:|---:|
| AMD | S1 | 2026-07-14 | +6,50% | **+$25,53** |
| WDC | S4 | 2026-07-21 | +4,41% | **+$64,13** |
| AMAT | S1 | 2026-07-14 | −5,12% | **−$23,45** |

AMAT è l'unico dei tre con una causa esplicita e idiosincratica: "Applied Materials Stock Tanks Despite
Q3 Beat, Semiconductor Strength" (16:36) e "Applied Materials shares drop despite earnings beat, bullish
outlook" (16:00) — un caso di guidance percepita come debole nonostante il beat sul trimestre. La
posizione resta aperta (nessuna vendita oggi); la decisione di tenerla è S1, fuori perimetro di questa
analisi e comunque congelata dalla carta di osservazione.

WDC ha **zero righe proprie** in `news_log` nonostante il +4,41%: l'unico indizio testuale nei dati
raccolti è indiretto, dentro il titolo "Russell 2000 Extends Records, SanDisk Rallies 7%" (SanDisk è lo
spin-off storage di WDC) — un fan-out che non tagga WDC stesso.

### 4.2 Ingressi della giornata (2, entrambi S4, nessuno un mover)

| simbolo | ora UTC | prezzo | percentile d'ingresso | mtm EOD | vs apertura |
|---|---|---:|---:|---:|---:|
| JD | 14:37 | 29,02 | 0,784 | +2,49 | +33,02 |
| BA | 16:52 | 230,98 | 0,310 | +5,39 | +0,31 |

Mediana mobile a 20 giorni del percentile d'ingresso: 0,530. JD è entrato all'estremo alto del range
di giornata (78° percentile); BA vicino alla mediana (31°). Nessuno dei due chiude ±3%: JD −0,82%,
BA +0,58%. Non pertinenti alla classificazione dei miss di oggi.

### 4.3 Chiusure

Nessuna (`chiusure: []` nel dossier). Realizzato del giorno: $0,00.

## 5. Pattern osservato

**Dispersione idiosincratica, non rotazione settoriale.** Il tema dominante di sedute recenti (memoria/
storage e semiconduttori AI-adiacenti, si veda il report del 08-12) oggi **si spacca in due direzioni
opposte all'interno dello stesso comparto**: AMD +6,50% e WDC +4,41% salgono, AVGO −5,94% e AMAT −5,12%
scendono, con SOXX (indice del settore) sostanzialmente fermo (−0,06%) — non è un movimento di comparto,
sono quattro storie single-name che per coincidenza cadono nello stesso settore. Le cause individuate nei
dati: AMAT su guidance percepita debole nonostante il beat, AVGO su un pezzo dedicato al costo di
finanziamento del capex AI, ORCL sulla tesi short pubblica di Michael Burry. RDDT, il mover più forte
della giornata, resta senza alcuna spiegazione nei dati raccolti (nessun articolo dedicato). Indici quasi
fermi (SPY −0,20%, QQQ −0,14%) confermano che il movimento è confinato alla coda, non di mercato.

## 6. Confronto con le sedute precedenti della finestra

- **Il gate S4 (0,30, valore di design dalla deroga #191 del 07-08) continua a scartare segnali col
  segno corretto** (F-009): la seduta del 12/08 (ORCL, META, HD) e quella di oggi (AVGO, ORCL) mostrano
  lo stesso schema — articolo dedicato, segno giusto, magnitudine insufficiente. Il collo di bottiglia
  resta il dato (magnitudine debole), non la soglia, come già osservato l'08-10.
- **La copertura fan-out multi-ticker resta stabile in banda 46-66%**: oggi 77/169 righe (45,6%)
  derivano da 24 articoli multi-ticker su 116 (20,7%), in linea con la serie 51/66/53/55/51,5/48,8/46,5%
  delle sedute precedenti (F-012). Il caso RDDT di oggi è il più costoso della serie in termini di alpha
  congetturale attribuito a questo meccanismo ($277,85 su un mover del +12,63%).
- **Meccanismo di soppressione del log SKIP_FALLBACK** (F-006, isolato l'08-11 su AVGO): si ripete
  identico oggi su HOOD — un vecchio segnale ensemble di 24-48h prima, sotto soglia e mai loggato lui
  stesso, basta a rendere invisibile nel Decision Log un simbolo il cui unico segnale della giornata era
  fallback-only.
- **Nota fuori scope, non indagata a fondo**: `docs/evidence/dossier/2026-08-13.json` esiste ma non
  risultano né un `ALPHA_MISS_REPORT_2026-08-13.md` né una riga per il 2026-08-13 in
  `docs/evidence/market_daily.jsonl` — il 13/08 è un giorno di borsa feriale (giovedì). Segnalato per
  completezza di lettura dei giorni precedenti; non indagato oltre perché fuori dallo scope di questo
  report (una sola domanda, il 14/08).

## 7. Segnalazioni

[F-001] NO_NEWS su F (+3,46%), zero righe in `news_log`/`sentiment_signals`/`execution_decisions`:
nessuna catena decisionale esiste, catena nulla in una giornata con 45/96 simboli (47%) senza copertura
— dentro la banda 42-57% osservata dal 07-31. Costo congetturale $76,03 con size S4 tipica $2.200.

[F-009] Prima occorrenza pulita dopo il ripristino del gate di design a 0,30 (deroga #191, 07-08):
AVGO ha un articolo dedicato, segno corretto (−0,282, poi attenuato a −0,226 dal moltiplicatore di
signal-velocity), magnitudine a 6 centesimi dal gate. ORCL corrobora lo stesso giorno con un secondo
caso (−0,112, articolo Burry-specifico, segno corretto). Le occorrenze precedenti di F-009 (08-03→08-06)
erano generate sotto un gate temporaneamente salito a 0,45 e restano compromesse per confronto (vedi
"Discontinuità nella serie osservata" nella carta); questa è la prima al valore di design. Costo
verificato zero su entrambi: mover al ribasso, libro long-only, nessuna posizione detenuta.

[F-006] Nuova occorrenza dello stesso meccanismo isolato l'08-11 (AVGO, ticket TK-F): HOOD ha 2 segnali
fallback-only il 14/08 (−0,04, +0,072) e **zero righe in `execution_decisions`**. La causa non è il gate
ma `_record_fallback_drops(non_fallback_signals=signals)`: un segnale ensemble dell'08-13 (+0,013),
esso stesso sotto soglia e mai loggato, rientra nella finestra di lookback di 96h e basta a marcare HOOD
come "valutato davvero", sopprimendo il log SKIP_FALLBACK che altrimenti lo renderebbe distinguibile da
NO_NEWS. Costo non stimabile (osservabilità, non P&L; il mover è comunque al ribasso su libro long-only).

[F-012] Ricorrenza quantificata: 77/169 righe scorate (45,6%) da 24 articoli multi-ticker su 116 (20,7%),
in linea con la banda 46,5-66% della serie. Caso del giorno: RDDT, mover più forte della finestra
(+12,63%), ha **due** righe di copertura e **nessuna** parla di Reddit — entrambe rassegne "movers of the
day" che lo taggano insieme ad altri titoli. A differenza dei casi precedenti di questo finding (SPCX,
NVDA — tutti a costo verificato zero perché al ribasso su libro long-only), oggi il fan-out ha un costo
congetturale positivo: **$277,85**, perché RDDT è un mover al rialzo e la direzione era accessibile.
