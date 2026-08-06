# S4 — 04 Alpha Assessment

**Strategia:** S4 `NewsDrivenTactical` (news-driven tactical sentiment overlay)
**Data:** 2026-08-04
**Verdetto (implementazione):** `NEGATIVE` (sul criterio IC — il segnale non
predice, anzi predice al contrario)
**Verdetto (fenomeno):** `DECAYED` (PEAD ~zero post-2017; edge LLM in erosion)

---

## 1. L'evidenza interna del progetto (decisiva)

Il progetto ha il proprio strumento di misurazione dell'alpha:
`scripts/compute_s4_ic.py` → `docs/evidence/s4_ic.json` (generato 2026-08-03).
Calcola l'**Information Coefficient** Spearman cross-sectionale giornaliero (una
osservazione per simbolo-giorno, ultimo segnale come il ranker), forward returns
da Alpaca storica. Questo è il criterio **IC>placebo** citato in P0-13.

### Risultati (`s4_ic.json`, n=2002 simbolo-giorno, 34 giorni):

| Sottoinsieme | IC 1g | t-stat | IC 3g | t-stat | IC 5g | t-stat |
|---|---|---|---|---|---|---|
| **Tutti** | **−0.018** | −0.76 | **−0.010** | −0.42 | **−0.026** | −1.09 |
| **Ensemble** | −0.006 | −0.15 | +0.015 | +0.39 | +0.017 | +0.49 |
| **Fallback** | −0.020 | −0.45 | **−0.061** | −1.24 | **−0.063** | −1.42 |

**Nessun IC è significativo** a t>3 (soglia del progetto). Peggio: l'IC **totale
è negativo** su tutti gli orizzonti (il segnale predice nella direzione **opposta**
— peggiore di un placebo casuale, IC=0). I segnali **fallback** (FinBERT/singolo
modello, 70-86% del volume per la memoria collo #1) hanno IC ancora più negativo
(−0.063 a 5g, t=−1.42). Solo l'ensemble (segnali concordi) mostra IC
leggermente positivo (+0.015-0.017) ma del tutto non significativo (t<0.5).

**Conclusione IC**: il progetto **non ha confermato IC>placebo** — in realtà
l'IC è **sotto placebo** (negativo) per il segnale aggregato e per il fallback.
Questo è esattamente il blocco P0-13: `promotion_blocked=true` perché IC>placebo
non confermato. L'evidenza interna dice di più: **il segnale è non-predittivo o
contro-predittivo** nel campione disponibile.

### P&L live paper (DB read-only 2026-08-04):

```
trades.stop_strategy='S4': 64 trade, 62 closed
  net_pnl  = +$329.10   avg +$5.31/trade   37 wins (60% win rate)
  gross_pnl= +$408.97   costs ~$80
```

Il P&L live è **marginally positivo** (+$329 su 7 settimane, 64 trade). Come
riconciliare con IC negativo?

1. **Small sample**: 64 trade in 7 settimane paper è rumore; +$329 su uno sleeve
   al 10% è ben dentro la varianza di campionamento.
2. **Market beta**: S4 è long-only → in un mercato rialzista (gi lug-ago 2026)
   guadagna beta di mercato positivo che non c'entra col sentiment IC. Il P&L
   non è risk-adjusted; l'IC sì (forward return cross-sectionale).
3. **Selection mechanism**: l'entry gate `feedback:entry_threshold` + la
   conferma S1 possono filtrare un sottoinsieme che sopravvive per ragioni non
   legate al sentiment (es. momentum S1 overlap).
4. **Costi**: net_pnl include ~$80 di costi ma non slippage reale/spread di
   mercati illiquidi; paper sottostima i costi.

⇒ Il P&L positivo è **non in conflitto** con IC negativo: long-only in mercato
rialzista + small sample = beta + rumore; l'IC cross-sectionale (che isola il
contenuto informativo del segnale) è la misura di alpha ed è negativa.

## 2. Sintesi con la letteratura (fase 03)

La letteratura è **sfavorevole** per l'implementazione S4 specifica su ogni
dimensione rilevante:

| Dimensione | Letteratura | S4 |
|---|---|---|
| Fenomeno parente | PEAD ~zero post-2017 (Kettell 2022) | generalizza a news generiche |
| Costi | consumano 70-100% edge PEAD (Chordia 2009) | universo liquido (peggio), backtest no costi |
| Stock liquidity | PEAD 0.04%/mese liquido vs 2.43% illiquido | large-cap S1 universe (lato 0.04%) |
| Orizzonte | news giornaliera → 1-2 giorni predict (Heston-Sinha) | tattico giornaliero (lato 1-2g, rumor) |
| Gamba | long leg 9 bps vs short leg 29 bps (Lopez-Lira-Tang) | long-only positivo (gamba debole) |
| Modello fallback | FinBERT Sharpe −0.43 (Lopez-Lira-Tang) | FinBERT è il fallback S4 |
| LLM edge decay | Sharpe 6.54→2.33 (2021-2023) | regime di eroding edge |

Ogni scelta d'implementazione cade sul lato **debole o noto-non-predittivo**. La
letteratura non offre supporto per "large-cap, long-only positivo, tattico
giornaliero, con fallback FinBERT generi alpha netto post-cost".

## 3. Decomposizione alternative-beta

- **Market beta**: long-only → beta positivo; il P&L +$329 è in gran parte questo
  (non risk-adjusted).
- **Momentum beta (S1)**: S4 è **overlay di conferma a S1** (orchestrator combina
  sleeve). Sentiment+ è correlato momentum+ → S4 può duplicare esposizione S1, non
  essere incrementale. Cruciale per `cross_review` (signal_id coupling, overlap).
- **News/event beta**: partly prezzabile (Lopez-Lira-Tang: ChatGPT subsume
  RavenPack sentiment → LLM-sentiment è partly news-beta, non alpha puro).
- **Size beta**: large-cap tilt.

La domanda alpha è: **S4 aggiunge contenuto informativo incrementale oltre S1
(momentum) e oltre beta di mercato?** L'IC cross-sectionale (che netta il beta
di mercato per costruzione, Spearman su residui di ranking) è negativo → no.

## 4. Decay

- **PEAD decaduto** a ~zero post-2017 (Kettell-McInnis-Zhao 2022).
- **LLM edge in erosion attiva**: Sharpe ChatGPT 6.54→2.33 (2021-2023); l'adozione
  degli LLM riduce l'underreaction che alimenta l'edge.
- **Textual sentiment features show OOS alpha decay** (Chung-Tanaka-Ishii 2023);
  contextual/embedding features sono quelle che sopravvivono, non polarity pura.

S4 usa polarity testuale (il tipo di feature che decade OOS) senza contextual
embeddings → esposto al decay. A differenza di S3 (residual momentum NON
decaduto), S4 opera su un fenomeno in active decay.

## 5. Costi, capacità, regime

- **Costi**: la letteratura è inequivoca — i costi consumano 70-100% dell'edge
  PEAD, specialmente su stock liquidi (S4). Il backtest S4 non modella costi; il
  paper live sottostima. Post-cost, l'edge (già ~zero pre-cost su liquidi) è
  negativo.
- **Capacità**: le news materiali sono poche → capacity limitata, MA su
  large-cap liquido la capacità è alta e l'edge è basso (paradosso: dove S4 può
  scalare, non c'è edge; dove c'è edge, è illiquido).
- **Regime**: edge 3× più forte in recessione (García 2013) e per news negative
  (Lopez-Lira-Tang). S4 long-only positivo in espansione → lato debole entrambe.

## 6. Verdetto

### Implementazione S4: `NEGATIVE` (criterio IC)

L'evidenza interna del progetto (`s4_ic.json`) mostra IC **negativo** su tutti
gli orizzonti per il segnale aggregato (−0.018/−0.010/−0.026 a 1/3/5g) e per il
fallback (−0.020/−0.061/−0.063), nessuno significativo. Il criterio di promozione
P0-13 (IC>placebo) **non è soddisfatto** — è peggiore di placebo. Il P&L live
paper +$329 è small-sample + market beta (long-only in mercato rialzista), non
sentiment alpha; l'IC cross-sectionale (che isola il contenuto informativo) è
la misura pertinente ed è negativa.

**Non `UNPROVEN`** perché il progetto ha una misura diretta (IC) che va nella
direzione sbagliata, non solo "non abbastanza dati." **Non `DECAYED`** a livello
di implementazione perché l'IC negativo non è decay (il segnale non prediceva
meglio in passato nel campione disponibile). È `NEGATIVE` sul criterio di
predizione.

### Fenomeno (news sentiment drift): `DECAYED`

L'anomalia parente (PEAD) è decaduta a ~zero post-2017; l'edge LLM-sentiment è in
erosione attiva (Sharpe 6.54→2.33); le feature testuali polarity mostrano OOS
decay. Il fenomeno non è morto (esistono sub-segmenti: news negative, small-cap,
contesto/embedding), ma la **forma generalizzata long-only positiva su large-cap
che S4 implementa** è sul lato decaduto/debole.

### Rango rispetto alle strategie auditate

| Strategia | Verdetto implementazione | Verdetto fenomeno |
|---|---|---|
| S1 | `DECAYED` | `DECAYED` |
| S2 | `NEGATIVE` + `DECAYED` | `DECAYED` |
| S3 | `UNPROVEN` (non fedele) | `UNPROVEN` (non decaduto) |
| **S4** | **`NEGATIVE` (IC<0)** | **`DECAYED`** |

S4 è la strategia **live attiva** ma con la base di evidenza **più debole**:
l'IC interno è negativo, la letteratura è sfavorevole su ogni dimensione, il
fenomeno è decaduto. È significativo che l'unica strategia realmente eseguita a
rilevanza (con S1) sia proprio quella il cui alpha è internamente misurato come
negativo e la cui promozione è bloccata sul criterio che essa fallisce.

## 7. Rischi chiave e caveat

1. **IC sample piccolo** (34 giorni): l'IC negativo non è significativo, ma la
   **direzione** è coerente (negativa su 5/6 celle aggregate/fallback). Un
   campione più lungo potrebbe cambiare il punto, ma non invertire la direzione
   in modo credibile vista la letteratura concorde.
2. **IC ≠ P&L**: l'IC misura predizione cross-sectionale; la strategia
   long-only con entry gate può avere P&L positivo via beta anche con IC≤0.
   Questo è il rischio "S4 sembra guadagnare ma è solo beta" — da monitorare
   con P&L risk-adjusted (vs benchmark) nella fase runtime.
3. **Ensemble vs fallback**: l'IC ensemble è ~0 (leggermente positivo), il
   fallback è negativo. Se l'ensemble divergence order drought (70-86% fallback)
   non fosse presente, l'IC aggregato sarebbe ~0 non −0.02. L'implementazione
   del pair swap/3° modello (collo #1) potrebbe spostare l'IC verso 0, MA non
   verso positivo significativo.
4. **Incrementale a S1**: l'IC non netta S1; S4 potrebbe aggiungere valore solo
   come conferma timing a S1, non come alpha standalone. La `cross_review`
   deve stabilire se l'incremento è reale.

**Convergenza**: l'evidenza interna (IC<0, promotion blocked P0-13) e la
letteratura (decay, costi, gamba debole, FinBERT non-predittivo) convergono: S4
**non dimostra alpha netto**; il suo segnale è non-predittivo nel campione
misurato e il fenomeno è decaduto. Il fatto che sia la strategia live attiva è
il rischio principale del sistema.

---
**Stato fase:** 04_alpha_assessment = **done**. Prossimo cursore: `S4:05_code_mapping`.