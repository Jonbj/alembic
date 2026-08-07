# S3 — 04 Alpha Assessment

**Strategia:** S3 `CrossSectionalMomentum` (Residual Momentum)
**Data:** 2026-08-04
**Verdetto (implementazione):** `UNPROVEN`
**Verdetto (fenomeno):** `UNPROVEN` con prior positivo (non decaduto)

---

## 1. Quadro della valutazione

La fase 02 ha mostrato che il codice S3 **non testa fedelmente** il residual
momentum canonico (Blitz-Huij-Martens 2011): 12-0 vs 12-1, long-short vs
long-only, sizing non normalizzato, 50 sopravvissuti, pannello bilanciato. La
fase 03 ha mostrato che il fenomeno **residual momentum** ha prior accademico
forte e, crucialmente, **NON decade** significativamente post-pubblicazione
(Huij-Lansdorp 2017; Blitz-Hanauer-Vidojevic 2020). Questo rende S3 diverso da
S1 (momentum lordo decaduto) e S2 (VRP decaduto): per S3 l'argomento "anomalia
decaduta" è debole.

Il verdetto deve quindi separare due domande:

1. **L'implementazione S3 genera alpha netto?** → No, ma il backtest è
   invalidato, quindi non è nemmeno una falsificazione pulita → `UNPROVEN`.
2. **Il fenomeno (residual momentum 12-1) genera alpha netto, se testato
   fedelmente?** → La letteratura dice sì con prior forte e non decaduto, ma il
   progetto **non l'ha ancora testato** → `UNPROVEN` con prior positivo.

## 2. L'evidenza di backtest del progetto

Da `reports/s3_backtest/summary.json` (fase 01 §8):

- **OOS Sharpe = 0.148** — praticamente zero, ma **non una falsificazione pulita**
  perché:
  - **Survivorship**: universo = 50 sopravvissuti liquidi OGGI, riusati su
    2000-today (DV-6) → i sopravvissuti hanno rendimenti sistematicamente
    superiori; un momentum long su sopravvissuti è meccanicamente inflato. Che
    il risultato sia comunque ~0 suggerisce che il segnale 12-0 contaminato è
    debole anche con tailwind di survivorship — indicatore **negativo** per la
    variante di codice, ma non per il fenomeno.
  - **Pannello bilanciato con look-ahead** (DV-7): le date sono droppate se un
    ticker future-listed ha NaN → l'universo di date è determinato dai
    future-listed, come S1 BUG-2. Look-ahead nella selezione delle date.
  - **Soglie banali**: gate 1/2 PASS con `min_sharpe=0.0` (qualunque Sharpe ≥ 0
    passa); gate 3/5 FAIL. Il "PASS" dei gate 1/2 è privo di valore informativo.
- **WF**: 21 finestre, mean Sharpe 0.011, median 0.0, std 0.798, positive
  fraction 0.333 → distribuzione centrata su zero, **nessuna evidenza di alpha**
  anche ignorando i bias.
- **Non riproducibile**: file datati 2026-06-01, ignorati da Git, nessun manifest
  dati/versione (review §2.2) → il numero non è verificabile.

**Conclusione sul backtest**: 0.148 misura una **variante confusa** (12-0
long-short non normalizzato su 50 sopravvissuti con pannello bilanciato), non il
residual momentum canonico. Non falsifica il fenomeno; non conferma la variante
di codice. È numericamente ~0, ma in un backtest invalidato → `UNPROVEN`, non
`NEGATIVE`.

## 3. Decomposizione alternative-beta

Anche se il backtest fosse valido, il rendimento va decomposto prima di
chiamarlo alpha:

- **Momentum beta**: il residual momentum è correlato ~0.5 al momentum lordo
  (BHM 2011) → parte del rendimento è momentum-beta, non alpha. Gutman 2023
  mostra però incremental alpha oltre il momentum lordo → non è puro beta.
- **Market beta**: ridotta per costruzione (sottrazione `beta·market_mom`), ma
  il long-short dollar-neutral retain exposure via differenziali di beta tra le
  gambe.
- **Low-vol beta**: sizing inverse-vol 252d tilta low-vol → esposizione al
  fattore low-vol (Schneider 2020: compensazione coskewness, non alpha).
- **Size beta**: universo 50 large-cap → tilt large.
- **Factor momentum residuo**: S3 sottrae solo beta×market (1-factor), non FF3
  → può contenere factor momentum su size/value/quality (Ehsani-Linn 2023).
  La variante FF3-residual (Gutman) è più pulita; S3 è sotto-pulita.

**Sintesi beta**: anche un rendimento positivo non sarebbe alpha pulito —
sarebbe una combinazione di momentum-beta, low-vol-beta, size-beta e factor
momentum residuo. Il residual momentum letteratura-documenato ha incremental
alpha, ma la variante 1-factor di S3 non lo isola completamente.

## 4. Costi, capacità, regime

- **Costi**: a favore di S3 — il residual momentum ha ~metà turnover del momentum
  lordo (BHM 2011) → costi di transazione inferiori. MA il long-short (non
  long-only del design) aggiunge costi di borrow e short-squeeze risk non
  modellati. Patton-Weller 2020: costi momentum 7.2-7.6%/anno per fondi tipici
  — applicabili alla famiglia; il residual è minore ma non nullo. Il backtest
  S3 **non modella costi** esplicitamente (review §2.2) → il 0.148 è pre-cost.
- **Capacità**: universe large/mid US liquido → capacità elevata per la gamba
  long; la gamba short su 50 large-cap è borrowable ma concentra il rischio di
  short-squeeze. Non è un limite pratico per la scala Alembic.
- **Regime**: a favore di S3 — il residual momentum ha crash meno severi del
  momentum lordo (BHM 2011: +4.7% vs −8.5% nel 2000-2009) perché la componente
  beta è sottratta. MA l'implementazione long-short + sizing non normalizzato
  reintroduce rischio che il design long-only evitava; l'assenza di vol-scaling
  aggregato (BSC 2015) riduce il vantaggio.

## 5. Decay (differenza chiave vs S1/S2)

| Strategia | Fenomeno | Decay post-pubblicazione |
|---|---|---|
| S1 | Momentum lordo TS | **Decaduto** (Ben-David 2021: 0.92→0.16%/mese) |
| S2 | VRP short-put | **Decaduto** (Chicago Fed 2025: alpha≈0 ultimi 15y) |
| S3 | Residual momentum | **Non decaduto** (Huij-Lansdorp 2017: poco decay OOS) |

Per S3 l'argomento "anomalia sfruttata via via via dal crowding" è debole: la
letteratura documenta **repliche OOS post-pubblicazione robuste**. Questo non
garantisce alpha futuro, ma sposta il prior: a differenza di S1/S2, non c'è
evidenza accademica che il fenomeno sia sparito. Il rischio principale per S3
non è il decay ma l'**implementazione non fedele** e i **bias di backtest**.

## 6. Verdetto

### Implementazione S3 (codice corrente): `UNPROVEN`

Il codice testa una variante economicamente diversa dal residual momentum
canonico (12-0 long-short non normalizzato su 50 sopravvissuti). Il backtest
0.148 è (a) numericamente ~0, (b) invalidato da survivorship + pannello
bilanciato + soglie banali, (c) non riproducibile. Non è una falsificazione
pulita del fenomeno, né una conferma della variante. La variante di codice non
ha dimostrato alpha netto, ma non è stata nemmeno testata in modo conclusivo.

**Non `NEGATIVE`** perché il backtest è invalidato (i bias dovrebbero inflare,
non sgonfiare, e il risultato è ~0 — ma in un test non pulito non si converte in
falsificazione). **Non `GENUINE_NET_ALPHA`** perché 0.148 ~ 0 e i gate 3/5 FAIL.

### Fenomeno (residual momentum 12-1 long-only): `UNPROVEN` con prior positivo

La letteratura sostiene il residual momentum come anomalia genuina, non
subsumed, con Sharpe ~doppio del momentum lordo, crash meno severi, turnover
minore, e **non decaduto** post-pubblicazione. Il progetto **non l'ha testato
fedelmente**: la review interna (2026-07-20) raccomanda un POC A/B della
variante originale, e issue #55 (design-alignment) è ancora aperta. Fino a quel
POC, il fenomeno resta `UNPROVEN` per Alembic — ma con un prior accademico
nettamente più favorevole di S1/S2.

### Rango rispetto alle altre strategie auditate

| Strategia | Verdetto implementazione | Verdetto fenomeno |
|---|---|---|
| S1 | `DECAYED` (momentum lordo decaduto) | `DECAYED` |
| S2 | `NEGATIVE` (sostituzione non-VRP) + `DECAYED` (VRP) | `DECAYED` |
| S3 | `UNPROVEN` (variante non fedele, backtest invalido) | `UNPROVEN` con prior positivo (non decaduto) |

S3 è, a priori, la strategia **meno screditata** dalla letteratura tra le tre
momentum-family auditate, ma l'implementazione corrente non la testa e il
backtest non decide. Il percorso corretto (review 2026-07-20) è un POC A/B
offline della **variante originale** 12-1 long-only normalizzata, PIT, prima di
qualsiasi paper trading o broker wiring.

## 7. Rischi chiave per la valutazione

1. **Non-test fedele**: la domanda "il residual momentum funziona per Alembic?"
   resta aperta; il 0.148 non risponde.
2. **Bias di backtest**: survivorship + pannello bilanciato + soglie banali →
   anche un POC pulito potrebbe dare risultato diverso da 0.148.
3. **Decay futuro non escluso**: la letteratura dice "poco decay" finora, ma il
   crowding su momentum-family nel complesso potrebbe erodere anche il residual.
4. **Beta non isolato**: la variante 1-factor di S3 non pulisce size/value/
   quality → un eventuale alpha apparente potrebbe essere factor momentum
   residuo.
5. **Long-short vs long-only**: il codice inverte il design long-only; il
   profilo di rischio (short-squeeze, borrow) è diverso e non modellato.

---
**Stato fase:** 04_alpha_assessment = **done**. Prossimo cursore: `S3:05_code_mapping`.