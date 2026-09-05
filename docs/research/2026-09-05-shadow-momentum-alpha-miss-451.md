# #451 — momentum shadow su `NO_NEWS` / `THIN_NEUTRAL`

## Esito

Sul campione pre-registrato di 38 miss (Week 34 e Week 35), il momentum
close-to-close delle cinque sedute precedenti avrebbe generato 20 intent LONG.
Quegli intent sono associati a **196,45 $ dei 569,21 $ di opportunita'
accessibile positiva**, cioe' **34,51%**. L'intervallo bootstrap 95% a cluster
per data e' ampio: **8,11%–70,83%**.

La media catturabile e' 5,17 $ per riga con outcome disponibile (IC 95%
0,76–12,85 $). Delle 20 accensioni, 12 hanno poi avuto una seduta positiva e 8
una negativa. Fra i 17 eventi con opportunita' accessibile positiva, il segnale
ne intercetta 8.

Questo risponde alla domanda stretta della issue: sul campione esiste una quota
misurabile associata al segnale, ma la precisione e' bassa e l'incertezza fra
giorni e' grande. **Non e' un P&L di strategia e non sostiene una modifica
live.**

## Metodo e provenienza

La specifica e' stata fissata in
[`PREREGISTRAZIONE_SHADOW_MOMENTUM_451.md`](../evidence/PREREGISTRAZIONE_SHADOW_MOMENTUM_451.md):

- campione: le 38 righe pubblicate come `NO_NEWS` o `THIN_NEUTRAL` nei report
  17–20 e 24–27 agosto, materializzate nel
  [`SHADOW_MOMENTUM_451_SAMPLE.json`](../evidence/SHADOW_MOMENTUM_451_SAMPLE.json);
- segnale: `product(1 + return)` sulle cinque sedute complete precedenti;
- intent: LONG se il momentum e' strettamente positivo, altrimenti ABSTAIN;
- outcome: `opportunity_v2.accessible_opportunity_usd`, senza ricalcolarne entry
  o exit;
- IC: bootstrap percentile bilaterale 95%, 10.000 repliche, seed 451,
  ricampionamento a cluster degli otto giorni evento.

Tutte le 38 righe hanno cinque rendimenti precedenti e un outcome disponibile;
nessuna osservazione e' stata imputata. La causa pubblicata dal report e la
causa nativa del dossier restano entrambe nell'output del comando. Questa
distinzione e' necessaria: `THIN_NEUTRAL` e' il vocabolario dei report, mentre i
dossier usano anche `BELOW_GATE`, `OFF_TOPIC_NON_DECIDIBILE` e altre categorie.

## Scomposizione

| causa report | N | LONG | LONG up/down | opportunita' positiva | associata ai LONG | quota |
|---|---:|---:|---:|---:|---:|---:|
| `NO_NEWS` | 20 | 11 | 6 / 5 | 391,85 $ | 86,59 $ | 22,10% |
| `THIN_NEUTRAL` | 18 | 9 | 6 / 3 | 177,36 $ | 109,87 $ | 61,95% |
| **Totale** | **38** | **20** | **12 / 8** | **569,21 $** | **196,45 $** | **34,51%** |

| data | N | LONG | opportunita' positiva | associata ai LONG |
|---|---:|---:|---:|---:|
| 2026-08-17 | 7 | 3 | 0,00 $ | 0,00 $ |
| 2026-08-18 | 3 | 1 | 0,00 $ | 0,00 $ |
| 2026-08-19 | 8 | 3 | 164,61 $ | 3,12 $ |
| 2026-08-20 | 3 | 1 | 3,42 $ | 3,42 $ |
| 2026-08-24 | 3 | 3 | 29,97 $ | 29,97 $ |
| 2026-08-25 | 3 | 2 | 199,50 $ | 113,09 $ |
| 2026-08-26 | 4 | 4 | 0,00 $ | 0,00 $ |
| 2026-08-27 | 7 | 3 | 171,71 $ | 46,86 $ |

La concentrazione per giorno spiega l'ampiezza dell'intervallo: il 25 agosto da
solo porta 113,09 $ dei 196,45 $ associati al segnale.

## Limiti che impediscono una decisione live

La popolazione e' condizionata ex post: per sapere che una riga e'
`NO_NEWS`/`THIN_NEUTRAL` bisogna prima osservare il mover e il report. Questo
studio misura il potere discriminante dentro quella popolazione, non costruisce
un universe selector eseguibile all'open.

Inoltre `opportunity_v2` tratta correttamente un ribasso non detenuto come
opportunita' zero per il book long-only e non conserva l'entry controfattuale.
Gli otto LONG finiti su sedute negative sono quindi contati, ma la loro perdita
non e' monetizzabile dai dati versionati. Chiamare 196,45 $ "P&L" ignorerebbe i
falsi positivi e sarebbe scorretto.

Durante il freeze #171 restano deliberatamente fuori: ricerca su altri
lookback, scelta di una soglia, sizing, ranking, gate live e qualunque flag di
attivazione. Sono taratura e appartengono, se mai giustificati dopo nuova
evidenza, al lavoro post-freeze #289.

## Riproduzione

Dal root del repository:

```bash
python scripts/analyze_shadow_momentum.py | jq '.summary'
```

L'output atteso dichiara `population: 38`, `momentum_evaluable: 38`,
`long_intents: 20`, `outcome_available: 38`, `capture_ratio:
0.34513479201916125` e l'IC 95% `[0.08107930153525138,
0.7082883140623857]`.
