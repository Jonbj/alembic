# Pre-registrazione — momentum shadow su `NO_NEWS` / `THIN_NEUTRAL`

Data di registrazione: 2026-09-05. Issue: #451. Questa definizione e' fissata
prima di eseguire il calcolo sul campione e non verra' modificata dopo averne
osservato i risultati.

## Domanda e campione

La misura e' descrittiva: tra i candidati alpha-miss gia' classificati
`NO_NEWS` o `THIN_NEUTRAL`, quanta opportunita' accessibile positiva sarebbe
stata associata a un semplice segnale di prezzo noto prima della seduta del
mover?

Il campione e' costituito dalle 38 righe classificate `NO_NEWS` o
`THIN_NEUTRAL` nei report di Week 34 (2026-08-17..20) e Week 35
(2026-08-24..27), materializzate nel manifest
`docs/evidence/SHADOW_MOMENTUM_451_SAMPLE.json`. Nessun ticker o giorno viene
selezionato in base al risultato. Le righe senza storia completa restano nel
conteggio del campione ma sono dichiarate non valutabili dal segnale.

**Errata di estrazione registrata prima del run definitivo.** Il primo dry-run
ha mostrato che il filtro letterale descritto nel commit iniziale `acec644` era
impossibile: il dossier usa una tassonomia nativa diversa (`BELOW_GATE`,
`OFF_TOPIC_NON_DECIDIBILE`, ecc.), mentre i report settimanali da cui nasce
#451 pubblicano `THIN_NEUTRAL`; inoltre Week 34 si chiude il 20 agosto, non il
21. Il manifest copia le classificazioni gia' pubblicate nei report e conserva
anche la causa nativa del dossier nell'output. Questa correzione cambia soltanto
l'estrazione della popolazione da 22 righe solo `NO_NEWS` alle 38 richieste
dall'issue: lookback, regola del segnale, outcome e bootstrap restano invariati.

## Segnale fissato

Per ogni `(data, symbol)` si prendono i rendimenti close-to-close pubblicati in
`mercato.rendimenti[symbol]` nei cinque dossier di sedute precedenti. La seduta
del mover non entra mai nel segnale.

```text
momentum_5d = product(1 + rendimento_giornaliero) - 1
intent_shadow = LONG se momentum_5d > 0; altrimenti ABSTAIN
```

Servono esattamente cinque osservazioni finite e maggiori di -100%. Una storia
incompleta non viene imputata. Cinque sedute e soglia zero sono una sola
specifica, non l'inizio di una ricerca su griglie di lookback o soglie.

## Outcome e stima

L'outcome economico viene letto senza ricalcolo da
`opportunity_v2.accessible_opportunity_usd`, che usa l'entry al primo ciclo
eleggibile e l'exit EOD. Per evitare di chiamare profitto una grandezza che non
lo e', la misura primaria e' la **quota di opportunita' accessibile positiva
catturabile**:

```text
opportunita_positiva_i = max(accessible_opportunity_usd_i, 0)
quota_catturabile = sum(opportunita_positiva_i per LONG)
                    / sum(opportunita_positiva_i per tutto il campione valutabile)
```

`accessible_opportunity_usd = null` resta missing e non diventa zero. Vengono
pubblicati separatamente: N totale, N con segnale calcolabile, N LONG, N outcome
accessibili, dollari accessibili positivi totali e associati ai LONG, quota
catturabile, e direzione della seduta fra i LONG.

Questa non e' una stima di P&L della strategia: per i mover negativi il
contratto long-only di `opportunity_v2` registra correttamente opportunita' zero
e non conserva un prezzo d'ingresso controfattuale. I falsi positivi sono
quindi contati per direzione ma non monetizzati.

## Intervallo di confidenza e interpretazione

L'incertezza viene stimata con bootstrap percentile bilaterale 95%, 10.000
repliche, seed 451, ricampionando con replacement i **giorni evento** e tenendo
insieme tutte le righe dello stesso giorno. Vengono dichiarati gli intervalli
per la quota catturabile e per i dollari catturabili medi per riga del campione.
Le repliche con denominatore nullo non contribuiscono all'intervallo della
quota; se non ne resta nessuna, l'intervallo e' `null`.

Il risultato e' esplorativo e condizionato a una popolazione scelta ex post
(mover poi classificati alpha-miss). Non autorizza un gate, una soglia, un peso,
un flag o qualunque altro cambiamento live durante il freeze #171. Qualunque
decisione di taratura resta fuori da #451 e appartiene al lavoro post-freeze
#289.
