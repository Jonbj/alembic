# Pre-registrazione — il gap fuori orario è incassabile in pre-market?

Scritta il **2026-09-16**, *prima* di guardare qualunque numero di liquidità, spread o
quota di gap consumata. Issue: **#608**. Alimenta la decisione del 28/09 (#607).

Questo documento esiste perché la Definition of Done di #608 chiede una **raccomandazione
binaria con la soglia dichiarata prima**. La soglia è il §5. Tutto ciò che sta sopra serve
a renderla non negoziabile dopo aver visto l'esito.

## 1. La domanda, in una riga

Il sentiment sulle news fuori orario predice il gap di apertura — **+0,560% in eccesso su
SPY, t 2,35 su 49 giornate** (pilota esplorativo; il test confermativo è #606 e il suo
esito non si guarda prima di ≈80 giornate). Entrando **all'apertura** quel gap è già
avvenuto: resta la gamba intraday, +0,078% con t 0,49, cioè niente.

> Con la nostra size e il nostro universo, un ordine in pre-market è eseguibile a un
> prezzo che lascia sul tavolo meno di quanto il segnale vale?

## 2. Cosa questa misura NON fa

1. **Non invia ordini**, nemmeno in paper. Sola lettura su barre e quote storiche.
2. **Non rimisura H1.** Il +0,560% è preso come dato d'ingresso, con la sua incertezza.
   Se #606 lo falsifica a novembre, questa misura decade insieme a lui.
3. **Non decide l'execution.** Passare a `LimitOrderRequest` + `extended_hours=True` è
   taratura e appartiene al 28/09 (#607). Qui si stabilisce solo se quella decisione ha
   una base o è già persa in partenza.
4. **Non stima l'impatto oltre il primo livello.** Le quote Alpaca sono NBBO (L1): la
   profondità oltre il tocco non è osservabile con i dati che abbiamo, e il rapporto deve
   dirlo invece di modellarla.

## 3. Campione — identico a #606 per costruzione

- **Popolazione:** righe `sentiment_signals` con `news_log.source = 'alpaca_benzinga'`,
  `published_at` non nullo e **fuori** dalla finestra 09:30–16:00 America/New_York nei
  giorni feriali; `abs(score) >= 0.10`.
- **Riduzione:** una osservazione per `(simbolo, seduta di reazione)` con
  `scelta_produzione()` di `scripts/measure_169_dedup_rules.py` **importata, non
  riscritta** (regola #169/#467).
- **Seduta di reazione:** la prima seduta di borsa che apre dopo `published_at`, dal
  calendario Alpaca (attenzione #372: le date del calendario **non** sono UTC).
- **Finestra dati:** barre al minuto e quote Alpaca **feed SIP**, troncate a
  `now − 3 giorni`. Un fetch fallito **aborta la misura**; non riduce il campione.
  È il difetto del pilota (§1 di `PREREGISTRAZIONE_GAP_OFFHOURS_2026-09-16.md`): Alpaca
  rifiuta l'**intera** richiesta sull'embargo del dato recente, quindi cadono esattamente
  i simboli più liquidi e il campione si auto-seleziona al contrario.

**Descrizione della popolazione già guardata prima di scrivere questo file** (è
descrizione, non esito, e va detto lo stesso): 380 segnali, 69 simboli, 2026-07-03 →
2026-09-15; per ora di pubblicazione ET: 02:00 → 3, 07:00 → 16, 08:00 → 102, 09:00 → 248,
16:00 → 10, 17:00 → 1. Il 92% nasce fra le 08:00 e le 09:30 ET.

## 4. Le quattro misure (DoD di #608)

### 4.1 Liquidità pre-market
Barre al minuto SIP fra 04:00 e 09:30 ET sulla seduta di reazione, per le quattro fasce
**04:00–07:00 · 07:00–08:00 · 08:00–09:00 · 09:00–09:30**. Per fascia: volume, numero di
trade, controvalore, e quota di `(simbolo, seduta)` con **zero** scambi nella fascia —
quest'ultima è la misura che conta davvero, perché un ordine in una fascia senza scambi
non è eseguibile a nessun prezzo.

### 4.2 Quota di gap già consumata
**Non** come rapporto `(p_t − close_prec)/(open − close_prec)`: un rapporto con
denominatore vicino a zero non ha mediana interpretabile. La forma primaria è quella che
risponde direttamente alla domanda, **nelle stesse unità del segnale**:

```
residuo(t) = sign(score) × [ (open_succ − p_t)/p_t − (open_SPY − p_SPY,t)/p_SPY,t ]
```

cioè *quanto resta da incassare entrando a `t` invece che al close precedente*. Per
`t = close_prec` questo è per costruzione il gap in eccesso del pilota; per `t = open` è
zero. Si misura a **07:00, 08:00, 09:00, 09:29 ET**, con `p_t` = ultimo prezzo scambiato
a `t` o prima nella stessa seduta pre-market (mai il giorno prima).
Il rapporto `(p_t − close_prec)/(open − close_prec)` è pubblicato **come diagnostico**,
solo sul sottoinsieme `|gap| ≥ 0,20%`, dichiarato qui e non rivedibile.

**Statistica, identica a #606:** unità di inferenza = **la giornata**, non l'evento; media
delle medie giornaliere; `t` sugli errori standard fra giornate; barra **|t| ≥ 3**
(`config/s4_kill_criterion.yaml`); `effetto_rilevabile_a_t3` pubblicato con l'esito.

**Azionabilità — la condizione che rende la misura non-look-ahead.** Il residuo alle
`07:00` calcolato su una notizia pubblicata alle `09:00` è un rendimento che nessuno
poteva prendere. Si pubblicano quindi tre insiemi per ogni ora `t`:

| insieme | condizione | a cosa serve |
|---|---|---|
| `tutti` | nessuna | **solo** descrizione della forma della curva — mai la raccomandazione |
| `pubblicati` | `published_at ≤ t` | limite superiore: cosa sarebbe azionabile con latenza di scoring **zero** |
| `scorati` | `generated_at ≤ t` | cosa il sistema di **oggi** sa davvero a quell'ora |

**La raccomandazione del §5 si legge su `scorati`**, con `pubblicati` come limite superiore
che dice quanto varrebbe al massimo anticipare lo scoring (la leva di #607). Va pubblicato
anche il **conteggio** delle osservazioni azionabili per ora e insieme: se a un'ora
l'insieme è quasi vuoto, la media a quell'ora non regge una decisione, qualunque sia.

### 4.3 Costo di attraversamento
Quote NBBO SIP, campionate in quattro finestre di 5 minuti che chiudono sulle fasce sopra
(06:55–07:00, 07:55–08:00, 08:55–09:00, 09:25–09:30), più **09:30–09:35 come riferimento
in orario**. Per fascia e per `(simbolo, seduta)`: spread relativo mediano
`(ask − bid) / mid`, e profondità al tocco in dollari `min(bid_size, ask_size) × mid`.

Costo modellato per un ingresso *aggressivo* (prendere il lato offerto):
`costo(bp) = mezzo spread relativo mediano` se il controvalore dell'ordine è ≤ profondità
al tocco; altrimenti il rapporto fra i due è pubblicato come **eccesso sul tocco** e il
costo oltre il primo livello è dichiarato **non osservabile** (§2.4) invece che stimato.
Il costo dell'uscita in orario è aggiunto allo stesso modo sulla fascia 09:30–09:35.

**Size:** empirica, non da `config/trading.yaml`. Dalla tabella `trades` sugli ultimi 60
giorni, percentili del controvalore d'ingresso; la size di riferimento è la **mediana**, e
la rottura si cerca facendo salire la size finché il costo supera la soglia del §5.

### 4.4 Vincoli del broker
Contratto reale di `alpaca-py` installato (sorgente, non documentazione riassunta) +
documentazione ufficiale Alpaca: quali `*OrderRequest` accettano `extended_hours`, quali
`TimeInForce` sono ammessi, se bracket e frazionari sopravvivono, e cosa implica per
`src/workers/portfolio_scheduler.py`, che oggi costruisce `MarketOrderRequest`.
Descrittivo: **nessuna modifica di codice** sotto questa issue.

## 5. La soglia — dichiarata ora

Lordo di riferimento: **56,0 bp** (il +0,560% clusterizzato del pilota).

> **Raccoglibile** se, a una delle ore di esecuzione esaminate, il **netto alla size
> mediana** — cioè `residuo(t) − costo di attraversamento all-in` — è **≥ 18,7 bp**, un
> terzo del lordo.
> **Non raccoglibile** altrimenti.

Perché un terzo, e perché è una soglia severa e non di comodo: la potenza di #606 è
calcolata *sul lordo*. Con dispersione giornaliera 1,67%, per `|t| ≥ 3` servono ≈80
giornate **su 56 bp**; su un effetto netto `x` ne servono `80 × (56/x)²`. A 18,7 bp sono
**≈720 giornate**, cioè oltre dieci anni al ritmo osservato. La soglia non dice quindi
«questo è profittevole»: dice **«sotto questo livello la domanda non è nemmeno più
decidibile»**, e proporre di raccoglierlo lo stesso sarebbe chiedere di eseguire su un
numero che non sapremo mai leggere. Il rapporto deve pubblicare `giornate_necessarie` al
netto osservato, accanto alla raccomandazione.

**Esito subordinato:** se il residuo lordo alla migliore ora fattibile è sotto il proprio
`effetto_rilevabile_a_t3`, l'esito è **`INSUFFICIENT_N`**, che batte
raccoglibile/non-raccoglibile per costruzione (stessa gerarchia di
`config/s4_kill_criterion.yaml`). Una raccomandazione non si estrae da un campione che non
la sostiene.

**Nessuna revisione a posteriori.** Se il netto cade appena sotto 18,7 bp, l'esito è «non
raccoglibile»: spostare la soglia dopo aver visto il numero è la mossa che questo
documento esiste per impedire.

## 5-bis. Cosa è stato guardato prima di chiudere questo documento

La trasparenza vale più della finzione di un ordine cronologico perfetto: **un run di
smoke test su 3 sedute** è stato eseguito per validare l'impianto, prima che il file
raggiungesse questa forma. Non è l'esito e i suoi numeri non compaiono nel rapporto. Ha
però trovato **due difetti che avrebbero invalidato la misura**, entrambi corretti prima
del run completo, ed è il motivo per cui il §4.3 e il §4.2 sopra dicono quello che dicono:

1. **Unità delle size di quote.** `bid_size`/`ask_size` di Alpaca sono in **azioni**, non
   in lotti da 100 — verificato sui dati (NVDA 100/200/300, F 2500/7700 a 13$). La prima
   stesura moltiplicava per 100 e gonfiava la profondità al tocco di due ordini di
   grandezza, cioè rendeva la size non vincolante per costruzione.
2. **Look-ahead nel residuo.** La prima stesura calcolava il residuo alle `07:00` su tutte
   le osservazioni della seduta, comprese quelle pubblicate alle `09:00`. È il difetto che
   ha prodotto la regola di azionabilità del §4.2: **la raccomandazione si legge su
   `scorati`**, non su `tutti`.

La **soglia del §5 non è stata toccata** dopo lo smoke test, e non lo sarà dopo l'esito.

## 6. Vincolo di freeze

Sola lettura: `sentiment_signals`, `news_log`, `trades`, barre e quote storiche Alpaca,
sorgente di `alpaca-py` e documentazione pubblica. Nessuna scrittura su `news_log`,
`sentiment_signals` o Redis; nessuna soglia, peso, flag o cooldown toccato; **nessun
ordine inviato, nemmeno in paper**. Registrata in `docs/evidence/OBSERVATION_CHARTER.md`
alla data del 2026-09-16.
