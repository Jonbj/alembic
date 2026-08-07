# Pre-registrazione del programma di backtest S1

Scritta il 2026-08-01, **prima** di eseguire qualunque backtest. Scopo: fissare cosa testiamo, con
quale soglia e con quale interpretazione, così che i risultati non possano essere razionalizzati a
posteriori.

Fonti che vincolano questo documento:
- `docs/research/2026-08-01-momentum-literature-hypotheses.md` — catalogo da letteratura primaria
- `docs/superpowers/specs/2026-08-01-osservazione-evidenze-roadmap-pesata-design.md` — carta di osservazione
- Analisi di sessione 2026-07-30/31 (finding interni)

---

## 1. La scoperta che riorganizza il programma

Il momentum long-short è morto; **la gamba long no**. Dai calcoli su dati Kenneth French fino a
maggio 2026:

| periodo | WML | t | winner − mercato | t | loser − mercato | t |
|---|---:|---:|---:|---:|---:|---:|
| 1927-1993 | 1,352% | 5,09 | 0,657% | 5,55 | −0,696% | −3,56 |
| 1994-2026 | 0,731% | 1,66 | 0,373% | 1,91 | −0,358% | −1,03 |
| 2009-2026 | 0,277% | **0,46** | 0,296% | 1,15 | **+0,019%** | 0,04 |

Il long-short è a zero perché dal 2009 il decile perdente **non sottoperforma più il mercato**. La
gamba lunga ha perso circa il 55% del suo edge ma resta positiva in ogni finestra.

**Conseguenza operativa:** quasi tutta la letteratura "il momentum è morto" descrive una gamba che
non tradiamo. Ma la conseguenza inversa è altrettanto vincolante — tutti i numeri di beneficio
citati per vol-scaling, hedging e regime timing sono anch'essi della gamba short, e **non ci
riguardano**. Ogni ipotesi di questo programma va valutata sulla scomposizione per gamba, non sul
risultato long-short.

## 2. Il vincolo di potenza, e cosa ci impedisce di fare

Con l'effetto atteso stimato per la gamba long (≈0,3%/mese su volatilità mensile ~3,5%) servono
**oltre 100 mesi** per raggiungere |t| = 3, anche se l'effetto fosse reale e perfettamente stabile.

**Un backtest su 5-15 anni non può né confermare né falsificare l'esistenza dell'alpha di momentum
sul nostro universo.** Questo è scritto prima di iniziare, non dopo aver visto risultati deludenti.

Ne discende la struttura del programma. I test si dividono in tre categorie che **non si confondono
mai**:

| categoria | cosa produce | consuma budget di test multipli? |
|---|---|---|
| **Calibrazione** | una stima dell'effetto e il suo intervallo di confidenza | no — non c'è ipotesi nulla da rifiutare |
| **Confermativa** | rifiuto o non-rifiuto di un'ipotesi pre-registrata | **sì** |
| **Diagnostica** | una scomposizione descrittiva del comportamento attuale | no |

Perché la distinzione conta: una calibrazione che restituisce «l'effetto è 0,25%/mese ± 0,4» è un
risultato utile e onesto. Trattarla come test e dire «non significativo, quindi non c'è effetto»
sarebbe un errore logico.

**Un'asimmetria di potenza da sfruttare.** Testare «la variante B batte la variante A» su rendimenti
appaiati ha potenza molto maggiore che testare «A ha alpha», perché la componente comune di mercato
si cancella nella differenza. Le ipotesi confermative di questo programma sono quindi formulate
**tutte come confronti fra varianti**, mai come test di alpha assoluto. È l'unico modo di ottenere
qualcosa di decidibile dai dati che abbiamo.

## 3. Soglia di significatività

**|t| ≥ 3,0** per ogni risultato confermativo, con correzione Holm al 5% sull'insieme dei test
confermativi pre-registrati qui sotto.

La soglia viene da Harvey-Liu-Zhu (2016), che mostrano come con le decine di anomalie testate in
letteratura la soglia convenzionale |t| = 1,96 produca in maggioranza falsi positivi. Con 5 test
confermativi la soglia Holm più stringente è |t| ≈ 2,9; adottiamo 3,0 per tutti, che è più
conservativo e più semplice da comunicare.

**Ogni ipotesi aggiunta a questo elenco alza la soglia per tutte le altre.** È il motivo per cui la
lista confermativa è corta e per cui la sezione 7 esiste.

---

## 4. Calibrazioni — da eseguire per prime

Non sono test. Fissano l'ordine di grandezza e vanno completate **prima** di eseguire qualunque
confermativa, perché determinano se le confermative abbiano senso.

### C1 — Ordine di grandezza dell'effetto sulla gamba long
Replicare il segnale 12-2 long-only sull'universo Alembic (96 titoli) 2010-2026 e stimare
l'extra-rendimento sul mercato con intervallo di confidenza.
**Atteso:** 0,2-0,4%/mese, |t| ≈ 1,2 — cioè **non dimostrabile**. L'esito utile è l'intervallo, non
il verdetto. (Corrisponde a L8 del catalogo.)

### C2 — Diluizione da universo ristretto
Confrontare lo spread top-decile-meno-mercato sui 96 nomi contro il benchmark CRSP value-weighted
sullo stesso periodo.
**Atteso:** inferiore di ≥25% per compressione cross-sezionale; con decili di ~10 nomi la varianza
campionaria è molto più alta. Nessuna fonte in letteratura lavora su universi fissi di ~100 titoli:
questa calibrazione parte senza ancoraggio e serve proprio a crearlo. (L9.)

### C3 — Costi di transazione
Stimare il costo per rotazione dell'universo con spread e commissioni Alpaca reali.
**Perché è una calibrazione e non un dettaglio:** l'holding attuale di ~14 giorni implica ~18
rotazioni l'anno contro le 2 di una strategia 6/6. Nessun numero della letteratura è al netto dei
costi, e Moskowitz-Grinblatt avvertono che a orizzonte mensile il turnover «sembra precludere i
profitti dopo i costi». Senza C3 i risultati di F2 e F4 non sono interpretabili.

---

## 5. Ipotesi confermative — cinque, non di più

Tutte formulate come confronto fra varianti su rendimenti appaiati. Soglia |t| ≥ 3,0 con Holm.

### F1 — Residual momentum su residui FF3
> Rankare i 96 titoli sui residui cumulati (t−252…t−21) di una regressione rolling a 36 mesi sui tre
> fattori Fama-French, standardizzati per la σ residua, produce **volatilità di strategia inferiore
> di ≥30%** rispetto al ranking su rendimenti totali, a parità o con minore media.

Prior **forte**: replicato da autori indipendenti, sopravvive in Hou-Xue-Zhang fino al 2016 con
t 2,88-3,82, verificato esplicitamente su large-cap (Sharpe 0,36 → 0,60). Non richiede fondamentali:
bastano i nostri prezzi e le serie FF3, scaricabili gratuitamente.

**Rischio noto e dichiarato:** nessuna fonte scompone il residual momentum per gamba long/short. Il
test dovrà misurarlo da sé. È l'ipotesi che raccomando di più *e* quella con il buco documentale più
serio: le due cose vanno tenute insieme.

### F2 — Holding period
> Allungare l'holding minimo di S1 da ~14 giorni a ≥60 giorni di trading, con gate anti-riacquisto,
> aumenta l'IC per unità di turnover.

Prior **forte** che l'holding attuale sia fuori finestra: JT93, Novy-Marx, HXZ, Barroso-Santa-Clara
misurano tutti holding da 1 a 12 **mesi**; nessuno stabilisce alcunché a 2-3 settimane, e JT93 mostra
il mese 1 in event-time **negativo** (−0,25%). Miglior rapporto valore/costo del catalogo.
**Dipende da C3:** senza contabilità dei costi il test è vuoto.

### F3 — Momentum settoriale long-only
> Un tilt long-only verso i settori vincitori a 6 mesi (senza skip) dentro l'universo Alembic batte
> l'equal-weight dell'universo di ≥0,2%/mese, e la variante con skip-month **non** lo migliora.

Prior **medio-forte**. È **l'unica area in cui una fonte primaria dice esplicitamente che il profitto
sta sul lato long**: Moskowitz-Grinblatt riportano 0,36 su 0,43%/mese sulla gamba lunga. L'universo
contiene già XLF/XLK/SOXX e una `sector_map` esiste nel repo.
**Freno dichiarato:** Grundy-Martin contraddicono la versione forte della tesi; testare come segnale
additivo o vincolo di allocazione, non come sostituto di S1.

### F4 — Componente a 21 giorni
> Rimuovere la componente a 21 giorni dal segnale multi-lookback di S1 non peggiora l'IC.

Prior **medio-forte** che non aggiunga nulla. La reversal a un mese, che sarebbe la sua
giustificazione, sui large-cap value-weighted **è sparita dal 1994** (t = 0,02). Test a costo quasi
nullo su un pezzo di segnale attualmente attivo in produzione.

### F5 — Vol-scaling long-only
> Scalare l'esposizione per la volatilità realizzata a 126 giorni della serie di rendimenti della
> strategia, con peso ≤ 1, riduce kurtosi e peggior mese di ≥40% **lasciando il rendimento medio
> invariato entro ±10%**.

Prior **forte** su entrambe le metà, inclusa la seconda. L'enunciato dice esplicitamente che *non*
aumenta il rendimento perché il «raddoppio dello Sharpe» della letteratura è un fenomeno della gamba
short: misurato long-only con cap, il guadagno di Sharpe scende a +0,09 con rendimento medio
invariato. Il beneficio reale è sulle code.

---

## 6. Diagnostiche — nessun budget statistico consumato

### D1 — Quanto di S1 è momentum settoriale mascherato
Neutralizzare il segnale per settore (z-score dentro ciascun gruppo) e misurare la caduta di IC.
Le fonti sono **in aperto conflitto** (MG99 prevede un crollo quasi totale, Grundy-Martin e HXZ una
riduzione modesta) e la riportiamo come tale. Valore diagnostico alto, valore di alpha basso: se D1
mostra che il segnale è in gran parte un bet settoriale, allora la concentrazione settoriale del book
**non è un effetto collaterale, è il segnale** — e questo cambia come si legge il cap settoriale
(#29) e l'episodio semiconduttori.

### D2 — Comportamento nei crash di momentum
Misurare la perdita relativa al mercato del book long-only negli eventi datati (2009-03…05,
2020-03…06, 2022) contro la corrispondente long-short.
Nota: il decile winner ha skew mensile −0,82, **più negativa** di quella dei loser (+0,09). Il
long-only non è privo di code: le ha diverse e più piccole.

---

## 7. Cosa NON testiamo, e perché

Dal catalogo (X1-X10) e per decisione nostra. Ogni voce esclusa è una soglia più bassa per le altre.

| escluso | motivo |
|---|---|
| Reversal a lungo termine (De Bondt-Thaler) | è un'anomalia della gamba short; e sui large-cap è sparita e ha cambiato segno (t = 0,29 dal 1994) |
| Reversal settimanale (Lehmann) | anomalia da market maker, quantificata al netto di spread del 1986 |
| Hedging con beta time-varying (Grundy-Martin) | già falsificato da Barroso-Santa-Clara: la componente di mercato è il 23% del rischio |
| 52-week high (George-Hwang) | fallisce la replica in HXZ: t = 0,38 |
| **Griglia esaustiva di lookback** | con 15 varianti la soglia Holm supera |t| = 3,4 e nessuna la raggiungerebbe mai |
| Pesi esponenziali fra lookback | nessun mandato in letteratura: ottimizzare un iperparametro non ancorato è overfitting puro |
| Time-series momentum | costruito su futures multi-asset con leva e short |
| Stagionalità di calendario | su 96 nomi dal 2010 sono ~15 osservazioni per mese: potenza zero |
| Dynamic momentum (Daniel-Moskowitz) | metà del guadagno viene dalla gamba che non abbiamo, l'altra metà è già in F5 |
| Residual momentum con FF5/q-factor | richiede fondamentali point-in-time che non abbiamo |
| **Gate di regime bear × volatilità** (L7) | il canale causale di DM sono i loser che diventano opzioni con beta esplosiva — non abbiamo la gamba loser. Alembic ha già `regime_mult` e F8 con storia di problemi: una seconda leva non ancorata brucerebbe budget |
| **Echo / intermediate horizon** (L4) | fonte primaria non verificabile in tabella (paywall) più contraddizione pubblicata su 37 mercati. Prior debole: non merita di alzare la soglia per F1-F5 |
| **Skip-month** (L2) | vedi sotto |

**Sullo skip-month, in dettaglio.** Era la nostra ipotesi H1 originale, ed è già implementata sul
branch `s1-refinements-2026-07-12`. La ricerca la ridimensiona: il paper che tutti citano usa un gap
di **una settimana**, non un mese; il beneficio documentato è +0,15 pp/mese su campioni
equal-weighted degli anni '60-'80; e l'effetto che dovrebbe giustificarla è sparito dai large-cap dal
1994. **Non entra fra le confermative** — non vale un incremento di soglia per tutte le altre. Viene
misurata come variante secondaria dentro F3 (dove MG99 dice esplicitamente che non serve) e
riportata in modo descrittivo, senza test di significatività.

---

## 8. Ipotesi interne: perché non sono qui

Dall'analisi di sessione del 2026-07-30/31 erano emerse due ipotesi nostre: la concentrazione delle
perdite nell'ora 14:00 UTC, e il fatto che la regola d'uscita di S1 realizzi solo perdenti.

**Non entrano nel programma confermativo.** Sono state trovate **guardando i nostri stessi dati**:
testarle sugli stessi dati che le hanno generate è data snooping, e un |t| ottenuto così non è
interpretabile. Il finding sull'ora 14:00 dava t = −2,11 su otto bucket orari — che non sopravvive a
nessuna correzione.

Restano trattate così:
- **L'ora d'ingresso** diventa una colonna fissa del dossier (fase 2 del report) e viene osservata
  in avanti. Se il pattern persiste su dati nuovi, allora sarà un'ipotesi con evidenza indipendente.
- **La regola d'uscita** è un cambio strutturale, non un parametro. Va simulata come book
  alternativo, come diagnostica, senza test di significatività.

Questa è la differenza fra l'evidenza della letteratura e la nostra: la prima è indipendente dai
nostri dati, la seconda no.

---

## 9. Regole procedurali

1. **Ordine obbligato:** C1, C2, C3 prima di qualunque confermativa. Le calibrazioni determinano se
   le confermative siano interpretabili.
2. **Nessuna modifica in produzione prima del giorno 40** dell'osservazione (2026-09-28), coerente
   con la carta. I risultati arrivano alla sintesi finale come seconda fonte di evidenza accanto al
   ledger. Dove backtest e ledger si contraddicono, **vince il ledger**: è misura diretta, non
   simulazione.
3. **Walk-forward IS/OOS** e i cinque gate già presenti in `src/backtest/` si applicano a tutte le
   confermative.
4. **Dati:** Alpaca, non yfinance — stessa fonte dell'esecuzione live, così backtest e produzione
   vedono gli stessi prezzi. Il bias di sopravvivenza va **misurato** (quanti dei 96 esistevano 5 e
   10 anni fa, e come cambia C1 restringendo l'universo), non assunto.
5. **Se un'ipotesi confermativa non raggiunge |t| = 3,0**, l'esito registrato è «non dimostrata su
   questo campione», non «falsa». Con la potenza disponibile le due cose sono diverse, e la sezione 2
   spiega perché.
6. **Questo documento non si modifica dopo l'inizio dell'esecuzione**, salvo il registro degli
   scostamenti in coda, con data e motivo.

## 10. Registro degli scostamenti

| data | scostamento | motivo |
|---|---|---|
| 2026-08-03 | **C1 non e' interpretabile come stima dell'effetto; le confermative F1-F5 restano eseguibili solo in forma comparativa** | Prima esecuzione delle calibrazioni. Due vincoli emersi, entrambi dirimenti. **(a) Dati:** Alpaca IEX non ha il 2019, ha 1 barra nel 2018 e 111 nel 2020 — storia utilizzabile solo dal 2021, cioe' **53 mesi**, contro i 100+ che servono per t=3. **(b) Universo scelto col senno di poi:** il primo commit del repo e' del 2026-05-04, quindi i 96 simboli sono stati scelti a maggio 2026 conoscendo il periodo 2021-2026 che il backtest misura. Il paniere contiene NVDA, AVGO, AMD, MU, META, TSLA, ARM, PLTR e il suo equipesato rende **+22,9%/anno**. C1 misura +2,29%/mese (t=2,53) contro i 0,2-0,4%/mese attesi dalla letteratura: il fattore ~6 e' la firma della selezione, non un edge. **Conseguenza:** la scelta di formulare F1-F5 come confronti fra varianti (§2) passa da prudente a **indispensabile** — un confronto A vs B sullo stesso universo distorto cancella gran parte della distorsione, un livello assoluto no. E la domanda sui dati a pagamento non e' piu' teorica: il gratuito da' 4,5 anni e un universo con hindsight. |
