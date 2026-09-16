# Il gap fuori orario non è incassabile — e la liquidità non c'entra

**2026-09-16 · issue #608 · sola lettura, nessun ordine inviato.**
Pre-registrazione: `docs/evidence/PREREGISTRAZIONE_ESEGUIBILITA_PREMARKET_2026-09-16.md`
(campione, outcome, statistica e **soglia** fissati prima dell'esecuzione).
Misura: `scripts/measure_608_premarket_feasibility.py` · artefatto:
`docs/evidence/premarket_feasibility_608.json`.
Alimenta la decisione del 28/09 (#607).

## Raccomandazione

> **NON RACCOGLIBILE**, con esito formale **`INSUFFICIENT_N`** — che per costruzione batte
> raccoglibile/non-raccoglibile (§5 della pre-registrazione).

E la ragione **non è quella che l'issue si aspettava**. Non è la liquidità: il pre-market
sul nostro universo è profondo e continuo. Non è lo spread: 7-11 bp mediani, cioè 3-6 bp di
mezzo spread. Non è la size: il nostro ordine mediano vale **$1.243**, il **5,9%** della
profondità al tocco.

Il motivo è che **quando la notizia esce, il gap è già avvenuto**.

| | |
|---|---|
| gap in eccesso su SPY, entrando al close precedente | **+62,4 bp** (t 2,54, 49 giornate, 282 oss) |
| residuo entrando alle **07:00 ET** | **+10,1 bp** (t 0,64) — l'84% è già andato |
| residuo entrando alle **08:00 ET** | +9,1 bp (t 0,52) |
| residuo entrando alle **09:00 ET** | −7,1 bp (t −1,29) |
| residuo entrando alle **09:29 ET** | −0,6 bp (t −0,73) |

E il 92% dei nostri segnali fuori orario nasce **fra le 08:00 e le 09:30 ET**, cioè dentro
la finestra in cui il residuo è già zero o negativo.

**A quale size si rompe: a size zero.** Al miglior orario azionabile il residuo lordo vale
**16,8 bp**, sotto la soglia dichiarata di **18,7 bp** *prima di pagare qualunque costo*.
Un'esecuzione gratuita, istantanea e infinitamente liquida fallirebbe comunque il criterio.
La size non è la variabile vincolante: non esiste una size a cui la cosa funzioni.

---

## 1. Liquidità pre-market — non è il problema

282 osservazioni `(simbolo, seduta di reazione)`, 68 simboli, 49 sedute, 2026-07-03 →
2026-09-15. Barre al minuto Alpaca **SIP**, finestra troncata a `now − 3 giorni`, **fetch
fallito = misura abortita** (il difetto che nel pilota aveva portato n da 330 a 68
eliminando i simboli più liquidi). Nessuna osservazione persa per dati mancanti: `con_barre`
282, `senza_barre` 0, `senza_giornaliere` 0.

| fascia ET | volume mediano | trade mediani | controvalore mediano | controvalore p10 | quota senza scambi |
|---|---|---|---|---|---|
| 04:00-07:00 | 201.065 | 6.601 | $66,4 M | $2,24 M | **0,35%** |
| 07:00-08:00 | 129.739 | 2.837 | $41,2 M | $1,71 M | **0,71%** |
| 08:00-09:00 | 198.916 | 4.140 | $60,6 M | $2,81 M | **0,00%** |
| 09:00-09:30 | 171.597 | 3.303 | $50,2 M | $2,47 M | **0,71%** |

La riga che decide è l'ultima: **la quota di `(simbolo, seduta)` senza nemmeno uno scambio
nella fascia è sotto l'1% ovunque**. Un ordine in pre-market sul nostro universo trova un
mercato. Anche al decimo percentile il controvalore scambiato nell'ora è sopra $1,7 M, cioè
oltre mille volte il nostro ordine mediano.

Questo è un effetto del nostro universo, non del pre-market in generale: 69 simboli, quasi
tutti mega-cap USA, con NVDA, MU, SPY, QQQ, AAPL e AMD a fare il grosso dei segnali.

## 2. Quanto del gap è già consumato

La forma primaria è **quanto resta da incassare entrando a `t` invece che al close
precedente**, nelle stesse unità del segnale e depurata dal mercato:

```
residuo(t) = sign(score) × [ (open − p_t)/p_t − (open_SPY − p_SPY,t)/p_SPY,t ]
```

Inferenza clusterizzata **per giornata** come #606, barra |t| ≥ 3.

| ingresso a | n giornate | n eventi | residuo | t | rilevabile a t3 | giornate positive |
|---|---|---|---|---|---|---|
| close precedente | 49 | 282 | **+62,42 bp** | 2,54 | 73,87 bp | 29/49 |
| 07:00 ET | 49 | 281 | +10,14 bp | 0,64 | 47,63 bp | 26/49 |
| 08:00 ET | 49 | 282 | +9,07 bp | 0,52 | 51,82 bp | 28/49 |
| 09:00 ET | 49 | 282 | −7,06 bp | −1,29 | 16,45 bp | 20/49 |
| 09:29 ET | 49 | 282 | −0,63 bp | −0,73 | 2,62 bp | 21/49 |
| apertura | 49 | 282 | 0 per costruzione | — | — | — |

Il gap in eccesso riprodotto qui è **+62,4 bp con t 2,54**, contro i +56,0 bp / t 2,35 del
pilota: stessa grandezza, scarto dovuto alla riduzione a una osservazione per
`(simbolo, seduta)` con `scelta_produzione()` e al troncamento dell'embargo (50 osservazioni
cadute oltre `now − 3 giorni`). **Il suo `effetto_rilevabile_a_t3` è 73,87 bp: il gap lordo
stesso è sotto la soglia di rilevabilità** — coerente con #606, che non si legge prima di
≈80 giornate.

Il diagnostico per rapporto, sul sottoinsieme `|gap| ≥ 0,20%` dichiarato in anticipo
(n=250), racconta la stessa cosa in forma indipendente:

| ora ET | quota del gap già avvenuta (mediana) | p25 | p75 |
|---|---|---|---|
| 07:00 | **69,0%** | 44,0% | 98,7% |
| 08:00 | **80,4%** | 54,2% | 102,6% |
| 09:00 | **93,0%** | 71,0% | 116,2% |
| 09:29 | **100,4%** | 97,8% | 103,0% |

Alle 09:29 il gap è, mediano, **interamente** avvenuto: l'asta di apertura non aggiunge
nulla che non sia già nel prezzo pre-market.

## 3. Azionabilità — il fatto che chiude la questione

Un residuo alle 07:00 calcolato su una notizia pubblicata alle 09:00 è look-ahead: è un
rendimento che nessuno poteva prendere. La pre-registrazione (§4.2) impone quindi di
contare, per ogni ora, **quante osservazioni erano davvero disponibili**.

| ora ET | osservazioni totali | già **pubblicate** | già **scorate** dal sistema |
|---|---|---|---|
| 07:00 | 282 | 14 (5,0%) | **14 (5,0%)** |
| 08:00 | 282 | 28 (9,9%) | **14 (5,0%)** |
| 09:00 | 282 | 93 (33,0%) | **14 (5,0%)** |
| 09:29 | 282 | 277 (98,2%) | **14 (5,0%)** |

La colonna «scorate» è **costante a 14**. Non è un errore: sono le uniche notizie fuori
orario che il sistema riesce a scorare prima dell'apertura, e sono esattamente le 11
pubblicate subito **dopo la chiusura precedente** (16:00-17:00 ET) più le 3 delle 02:00 ET.
Le altre **268 su 282 — il 95% — non sono scorate prima delle 09:29**, perché nascono fra
le 08:00 e le 09:30 e il worker di sentiment è a sua volta gated sulla sessione regolare.

Sui soli 14 eventi azionabili (6 giornate distinte):

| ingresso a | residuo lordo | t | rilevabile a t3 |
|---|---|---|---|
| 07:00 | **+16,78 bp** | 0,78 | **64,61 bp** |
| 08:00 | −3,80 bp | −0,16 | 69,92 bp |
| 09:00 | −0,86 bp | −0,04 | 63,05 bp |
| 09:29 | −5,25 bp | −1,75 | 9,00 bp |

Sei giornate non decidono niente, ed è il motivo per cui l'esito formale è `INSUFFICIENT_N`
e non «non raccoglibile» e basta.

**E il limite superiore?** La colonna «pubblicate» dice quanto varrebbe **anticipare lo
scoring a latenza zero**, cioè la leva che #607 mette sul tavolo: 07:00 → +16,8 bp (14 ev),
08:00 → +7,2 bp (28 ev), 09:00 → **−4,3 bp** (93 ev), 09:29 → **−0,6 bp** (277 ev). Nel
punto in cui il campione diventa numeroso, il residuo è **negativo**. Anticipare lo scoring
non recupera il gap: **la pubblicazione stessa arriva tardi**, e uno scoring istantaneo su
una notizia tardiva resta tardivo. È il risultato più utile di questa misura per il 28/09.

## 4. Costo di attraversamento

Quote NBBO SIP, finestre di 5 minuti che chiudono sulle fasce, più 09:30-09:31 come
riferimento in orario. Profondità al tocco = `min(bid_size, ask_size) × mid`, con le size
in **azioni** (verificato sui dati: NVDA 100/200/300, F 2500/7700 a 13$).

| finestra ET | spread mediano | p75 | p90 | tocco mediano | tocco p10 | n |
|---|---|---|---|---|---|---|
| 06:55-07:00 | 10,34 bp | 19,43 | 31,27 | $21.162 | $10.926 | 268 |
| 07:55-08:00 | 8,30 bp | 15,13 | 25,84 | $20.579 | $10.661 | 275 |
| 08:55-09:00 | 7,08 bp | 14,53 | 24,17 | $20.715 | $10.398 | 275 |
| 09:25-09:30 | 11,18 bp | 20,64 | 45,02 | $20.209 | $10.145 | 282 |
| **09:30-09:31 (in orario)** | **6,97 bp** | 12,99 | 27,09 | $20.467 | $10.567 | 282 |

Il pre-market del nostro universo costa **da 0,1 a 1,6 bp in più** che i primi 60 secondi di
seduta regolare. È un sovrapprezzo trascurabile, non una barriera.

**Size, empirica e non da config** (tabella `trades`, 167 ordini negli ultimi 60 giorni):

| p50 | p75 | p90 | max |
|---|---|---|---|
| **$1.243** | $1.437 | $1.838 | $6.234 |

Il nostro ordine mediano è il **5,9%** della profondità al tocco mediana e il **11,4%** di
quella al decimo percentile. `size_oltre_il_tocco` è **falso a ogni ora**: il costo si
esaurisce nel mezzo spread, senza attraversare il primo livello. Anche l'ordine massimo mai
inviato ($6.234) resta sotto il tocco al p10.

Costo all-in modellato (mezzo spread all'ingresso + mezzo spread all'uscita in orario):

| ora | costo ingresso | costo uscita | **all-in** | residuo lordo | **netto** | giornate per t≥3 |
|---|---|---|---|---|---|---|
| 07:00 | 5,17 bp | 3,48 bp | **8,65 bp** | +16,78 bp | **+8,12 bp** | **≈3.800** |
| 08:00 | 4,15 bp | 3,48 bp | 7,63 bp | −3,80 bp | −11,44 bp | — |
| 09:00 | 3,54 bp | 3,48 bp | 7,02 bp | −0,86 bp | −7,89 bp | — |
| 09:29 | 5,59 bp | 3,48 bp | 9,08 bp | −5,25 bp | −14,32 bp | — |

Il costo **oltre il primo livello non è stimato**: le quote Alpaca sono L1 e la profondità
oltre il tocco non è osservabile con i dati che abbiamo. Alla nostra size la questione non
si pone; a size dieci volte superiore si porrebbe, e non sarebbe rispondibile da qui.

## 5. Vincoli del broker

Verificato sul **sorgente di `alpaca-py` 0.43.5 installato** e sulla documentazione
ufficiale, non assunto.

**SDK.** `extended_hours: Optional[bool]` è definito **una sola volta**, su
`OrderRequest` (`alpaca/trading/requests.py:313`), ed è ereditato da tutte e sei le
sottoclassi — market, limit, stop, stop-limit, trailing. **Nessun validatore client-side lo
tocca**: qualunque combinazione illegale passa l'SDK e viene rifiutata solo dal server.
Quando il campo non è valorizzato, `NonEmptyRequest` lo elimina dal payload — oggi non viene
proprio inviato.

**Contratto server** (docs.alpaca.markets/docs/orders-at-alpaca):

- sessioni: pre-market **04:00-09:30 ET**, after-hours 16:00-20:00 ET, overnight 20:00-04:00;
- **solo ordini `limit`**, con `time_in_force` **`day` o `gtc`**. «*All other order types and
  TIF values will be rejected with an error*»;
- **bracket / OTO vietati**: «*Extended hours are not supported. `extended_hours` must be
  "false" or omitted*»;
- **stop e stop-limit non eleggibili** su nessuna TIF;
- frazionari e notional ammessi, ma solo `limit` + `day` (il `gtc` frazionario richiede
  abilitazione esplicita dal CSM).

**Cosa fa oggi `src/workers/portfolio_scheduler.py`** — `engine: portfolio` è il motore
attivo, quindi è l'unico percorso che invia ordini:

| voce | dove | compatibile con `extended_hours=True`? |
|---|---|---|
| BUY frazionabile: `MarketOrderRequest(notional=…, tif="day")` | `:5034-5041` | **no** — deve essere `limit` |
| BUY non frazionabile: `MarketOrderRequest(qty=…, tif="gtc")` | `:5042-5066` | **no** — idem |
| `order_class=BRACKET` + `take_profit` + `stop_loss` | `:5070-5088` | **no** — bracket vietato |
| SELL ribilanciamento / reversal: `MarketOrderRequest` | `:5148`, `:5267` | **no** |
| stop sintetico: `MarketOrderRequest` | `:92-107` | **no** |
| stop protettivo `StopOrderRequest` GTC | `src/portfolio/fractional_stop_orders.py:192-203` | inviato senza `extended_hours`, ma **inerte** in sessione estesa — una posizione aperta in pre-market resta scoperta fino alle 09:30 |
| gate `clock.is_open` | `:2464-2476` | **chiude ogni ciclo fuori RTH** |
| beat Celery `crontab(hour="14-21")` UTC | `src/workers/celery_app.py:263-266` | il ciclo **non gira** in pre-market |

I due ostacoli veri vengono **prima** della forma dell'ordine: il gate `clock.is_open` e il
crontab impediscono fisicamente al ciclo di girare fuori dalla sessione regolare. Nel
codebase `extended_hours` come parametro d'ordine ha **zero occorrenze**.

*(Descrittivo. Nessuna modifica di codice è stata fatta né va fatta sotto #608: cambiare
l'execution è taratura e appartiene al 28/09.)*

## 6. Conseguenze per il 28/09 (#607)

1. **La leva «anticipare lo scoring» vale molto meno di quanto sembrava.** Alla latenza zero
   ipotetica, nel punto in cui il campione è numeroso (09:29, 277 osservazioni su 282), il
   residuo è **−0,6 bp**. Il collo di bottiglia non è il nostro ritardo di scoring: è che la
   notizia esce quando il prezzo si è già mosso. Coerente con l'event study intraday, dove
   lo stream Benzinga non produce **nessun** picco di volatilità al `published_at`.
2. **La leva «separare le popolazioni» resta in piedi, ma non come strategia d'ingresso.**
   Il +62 bp di gap in eccesso è una proprietà vera e misurata del mondo; non è un
   rendimento disponibile. Serve a dire *quali news sono informative*, non *quando comprare*.
3. **Costruire execution in extended hours non è giustificato da questa evidenza.**
   Richiederebbe limit order, un prezzo limite che oggi non esiste, l'abbandono del bracket,
   una riscrittura del gate orario e del beat — per raccogliere, nella migliore delle ipotesi
   e prima di ogni costo, 16,8 bp misurati su 6 giornate.
4. **Se si volesse comunque provare**, la condizione necessaria è che #606 chiuda **PASS** a
   ≈80 giornate. Finché quell'esito non c'è, questa misura non ha nemmeno un lordo da cui
   sottrarre.

## 7. Limiti dichiarati

- Il lordo di riferimento (56 bp) **non è confermato**: viene dal pilota, e #606 non si legge
  prima di ≈80 giornate. Se #606 falsifica H1, questo rapporto decade con lui.
- Il campione azionabile è **6 giornate**. È il motivo dell'`INSUFFICIENT_N`. Non va letto
  come «l'effetto è assente»: va letto come «con questo campione non è distinguibile da zero,
  e nemmeno da 18,7 bp».
- **Profondità oltre il primo livello non osservabile** (quote L1). Irrilevante alla nostra
  size, vincolante a size ~10×.
- Non misurate le fasce 04:00-07:00 come ore d'ingresso: la griglia oraria decisionale è
  quella dichiarata in anticipo (07:00 / 08:00 / 09:00 / 09:29) e **non è stata riletta su
  ore aggiunte dopo**. Che il grosso del gap si formi prima delle 07:00 si legge comunque dal
  residuo: 62,4 → 10,1 bp, l'84% è già andato.
- La griglia oraria è **una lista chiusa di quattro celle** dichiarata prima. La
  raccomandazione si legge sulla cella migliore, non sulla migliore di una griglia allargata
  a posteriori.
