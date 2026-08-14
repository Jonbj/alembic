# Pre-registrazione — orizzonte economico di S4 e criterio di riattivazione

**Scritta il 2026-08-14.** Sostituisce il criterio registrato il 2026-08-06 nei commenti di
[#179](https://github.com/Jonbj/alembic/issues/179), che viene **formalmente ritirato** (§1).

Decisione a monte: [#242](https://github.com/Jonbj/alembic/issues/242) — S4 passa a **shadow
reversibile**, con la configurazione B a 2 sedute eseguita virtualmente end-to-end. Base
documentale: `docs/s4-orizzonte-review-2026-08-13/` (quattro analisi indipendenti + consolidamento).

Soglie: quelle del consolidamento §6, riportate qui senza modifiche. Dove il consolidamento non
specificava un parametro che *deve* essere fissato ex ante, il valore è scelto qui ed è marcato
**[aggiunto]** con la motivazione.

> **Scopo di questo documento.** Togliere a noi stessi la possibilità di scegliere le regole dopo
> aver visto i risultati. Vale la stessa disciplina di `OBSERVATION_CHARTER.md`: quello che è scritto
> qui vincola, quello che non è scritto qui non è un criterio.

---

## 1. Ritiro del criterio precedente, con la motivazione ex ante

Il criterio del 2026-08-06 diceva: *«a n ≥ 73 giorni, media degli IC **solo-ensemble** ai tre
orizzonti 1g/3g/5g; se ≤ 0, S4 passa a shadow»*. Viene ritirato per **tre errori di specificazione
documentati**, non perché il risultato non piaccia — al momento del ritiro il criterio, se valutato
come dichiarato, sarebbe **favorevole a S4** (media +0,0078 > 0).

### E1 — Il criterio non era eseguibile

`scripts/compute_s4_ic.py:40` legge `config/s4_kill_criterion.yaml`. **Quel file non è mai esistito.**
Ogni run dal 2026-08-06 ha restituito `NO_CRITERION` in silenzio. La pre-registrazione viveva
soltanto come commento su una issue.

### E2 — La popolazione dichiarata non era quella misurata

Il criterio dice «solo-ensemble». La riga di `s4_ic.json` su cui tutte le analisi hanno ragionato —
`alta_convinzione_0.30` — **mescola ensemble e FinBERT-fallback**. Scomposizione
(`scripts/compute_s4_ic_2x2.py` → `docs/evidence/s4_ic_2x2.json`):

| cella | IC 1g | IC 3g | IC 5g | oss. | gg |
|---|---:|---:|---:|---:|---:|
| ensemble ∩ \|score\|≥0,30 | **+0,1372** | +0,0609 | +0,0742 | 303 | 23 |
| ensemble ∩ \|score\|<0,30 | +0,0004 | −0,0080 | −0,0038 | 1094 | 42 |
| fallback ∩ \|score\|≥0,30 | **−0,0995** | −0,0866 | +0,0524 | 51 | 5 |
| fallback ∩ \|score\|<0,30 | −0,0269 | −0,0132 | −0,0774 | 856 | 39 |
| *mista* (= la riga letta) | +0,0852 | +0,0485 | +0,1006 | 411 | 31 |

Il fallback ad alta convinzione è negativo a 1g e 3g e positivo a 5g: è lui che produceva la
monotonia crescente `+0,0434 → +0,0465 → +0,0624` letta come «l'alpha cresce con l'orizzonte».

> **Nota sulle cifre citate.** `+0,0434 / +0,0465 / +0,0624` è lo snapshot di `s4_ic.json` del
> 2026-08-07 (38 giorni), cioè quello che le quattro analisi hanno effettivamente letto.
> `compute_s4_ic.py` ricalcola e riscrive il file a ogni run, e al 2026-08-14 (42 giorni) la stessa
> riga vale `+0,0905 / +0,0510 / +0,0800`: **la monotonia si è già dissolta con quattro giorni di
> dati in più**, indipendentemente dalla decontaminazione. Due letture della stessa riga a quattro
> giorni di distanza danno forme opposte — è la stessa instabilità di E4, vista sull'asse del tempo
> invece che su quello del parametro. Nulla di cui i modelli avrebbero potuto accorgersi: la loro
> lettura era corretta al momento in cui l'hanno fatta.
>
> La media dell'ensemble puro ai tre orizzonti — la metrica che il criterio ritirato dichiarava —
> vale oggi **+0,0149** (era +0,0078). Resta favorevole a S4 e resta non significativa.

### E3 — Anche con lo YAML, lo script valuterebbe un'altra cosa

`_esito()` in `compute_s4_ic.py:178-196` legge `sintesi["tutti"]["1g"]`: popolazione **tutti** e
**solo 1 giorno**, non «solo-ensemble, media dei tre orizzonti». Il criterio e il suo valutatore non
coincidono. **Allineare `_esito()` a questo documento è lavoro di codice ed è parte del deploy (§8),
non un dettaglio di configurazione.**

### E4 — E la metrica non era comunque decidibile

Facendo variare `MIN_SIMBOLI_GIORNO`, l'unico parametro arbitrario del calcolo, la **forma** della
struttura a termine si capovolge:

| min simboli/gg | IC 1g | IC 3g | IC 5g | giorni |
|---:|---:|---:|---:|---:|
| 3 | **+0,1819** (t 2,13) | +0,1229 | +0,1190 | 30 |
| **5** (convenzione attuale) | **+0,1372** (t 1,75) | +0,0609 | +0,0742 | 23 |
| 8 | +0,0322 | **+0,1416** (t 4,22) | +0,1282 | 12 |
| 10 | +0,0322 | **+0,1416** (t 4,22) | +0,1282 | 12 |
| 15 | +0,0717 | +0,1417 | **+0,1545** (t 4,23) | 9 |

Con 9–30 giorni i dati rispondono quello che gli si chiede. Nessun valore è significativo; tutti sono
su dati pre-fix. **È il motivo per cui §3 fissa `min_simboli` ex ante.**

---

## 2. Configurazione sotto misura — unica e congelata

Una sola configurazione. Non si misurano varianti: misurare due cose con questo `n` non produce due
risultati, produce zero.

| elemento | valore | nota |
|---|---|---|
| orizzonte dichiarato | **2 sedute**, uscita alla chiusura di D+2 | §3 |
| regola d'uscita | time-stop **primario**; contro-segnale ≤ −0,30 e stop di rischio come **uniche** eccezioni | il silenzio delle fonti non è più un'uscita |
| `max_signal_age_hours` | 4, come filtro di **ingresso** | cessa di essere driver d'uscita |
| `rebalance_frequency` | DAILY, **applicata** (S4 entra in `_REBALANCE_CLOCK_STRATEGIES`) | oggi dichiarata e non applicata |
| ingresso | primo prezzo RTH eseguibile dopo il decision timestamp | §4 |
| popolazione ordinabile | solo-ensemble, \|score\| ≥ 0,30 | §3 |
| `bucket_pct` / `n_top` / `fixed_slot_sizing` | 0,10 / 5 / `true` | **congelati** |
| soglia d'ordine | 0,30 | **congelata** |
| coppia LLM | `glm52` + `gptoss` | **congelata** |
| esecuzione | **shadow**: nessun ordine al broker | #242 |

**Il lato ingresso è congelato per disciplina sperimentale, non perché sia validato.** Va scritto
adesso: l'ingresso ha un difetto documentato (64,3° percentile mediano del range della giornata, con
il 70–84% del movimento già avvenuto al primo segnale) e la misura che sembrerebbe assolverlo è
quella di E4, che non è stabile. Se fra sette settimane l'esito è positivo, **non sarà attribuibile
all'ingresso**: l'unica variabile cambiata è l'uscita.

### Shadow end-to-end, non shadow del solo IC

Requisito, non preferenza. Lo shadow deve girare **lo stesso codice dell'esecuzione** fino al confine
broker: selezione, ranking, guard anti-pyramiding e collisione S1, fill virtuale, cost model, aging,
regola d'uscita, `reason` code. Uno shadow ridotto al calcolo dell'IC produrrebbe un backtest elegante
e non deployabile, e lascerebbe valida l'obiezione di Opus (§3 del consolidamento): i difetti più
importanti — guard anti-pyramiding, uscite `unknown`, percentile d'ingresso — sono emersi dal ciclo
ordini reale, non dal logging dei segnali.

---

## 3. Misura dell'IC

### Popolazione

- **Primaria:** le osservazioni che S4 avrebbe **realmente potuto tradare** — solo-ensemble,
  \|score\| ≥ 0,30, ticker validato, dato disponibile al decision timestamp, dopo i gate di
  universo, liquidità, capacità e dopo la collisione con S1.
- **Secondarie, diagnostiche e mai sostitutive del test primario:** tutti i segnali ensemble;
  ensemble sotto soglia; fallback FinBERT; articoli single-ticker contro multi-ticker; per fonte.
- Ogni giorno vanno riportati numero di simboli effettivi, copertura e motivo di esclusione.
  **Aumentare `n` con osservazioni non tradabili produce falsa potenza.**

### Parametri fissati ex ante

| parametro | valore | perché |
|---|---|---|
| una osservazione per simbolo-giorno | **ultimo** segnale del giorno | è quello che il ranker usa in produzione |
| `MIN_SIMBOLI_GIORNO` | **5** **[aggiunto]** | è la convenzione già in `compute_s4_ic.py:45` e l'unico valore non scelto dopo aver visto i risultati. Il consolidamento non lo specificava: E4 mostra che senza fissarlo il protocollo non vincola nulla |
| orizzonte primario | **2 sedute** | coerente con la B candidata; nessuna media ex post fra orizzonti |
| robustezza predefinita | 1 e 3 sedute | il segno non deve essere contraddetto |
| diagnostico | close, 5 sedute | 5g ha forte sovrapposizione dei forward return: `n` effettivo molto minore del nominale |

**Un eventuale picco intraday non autorizza l'opzione A** con la pipeline attuale: aprirebbe un
progetto separato su fonti event-driven, con una nuova pre-registrazione.

### Stimatore

- Spearman cross-sectional per giorno; inferenza sulla **serie temporale** degli IC giornalieri.
- Errori standard **Newey–West/HAC**, lag coerente con l'orizzonte (forward return sovrapposti).
- Cluster bootstrap per giorno come **robustezza**, non come scorciatoia per trasformare migliaia di
  symbol-day correlati in altrettante osservazioni indipendenti.
- Da riportare sempre: IC medio, mediana, intervallo di confidenza, `t`, giorni, numero mediano di
  nomi/giorno, `n` effettivo.

### Prezzi

- **Iniziale:** fill shadow al primo prezzo RTH realisticamente eseguibile dopo il decision
  timestamp; in assenza, chiusura della barra 15 minuti successiva.
- **Finale:** close di D+2, total return, corporate action trattate correttamente
  (`adjustment="all"` — vedi #192).
- **Da riportare separatamente:** IC da prezzo-segnale e IC da prezzo eseguibile. La differenza
  misura slippage e ritardo strutturale e **non va nascosta nei costi espliciti**.
- Nessun controfattuale con informazione futura. Nessun cambio ad hoc di timestamp, universo o
  winsorization dopo aver visto i risultati.

---

## 4. Numerosità minima

| soglia | valore | statuto |
|---|---:|---|
| diagnostica di pipeline | 40 / 73 sedute | **non decisionale** |
| indicativa a t ≈ 2 | ~120 sedute | non sufficiente per riattivare |
| **confirmatoria** | **~213 sedute pulite** | `(3 × 0,243 / 0,05)²` sulla dev. std. giornaliera ensemble osservata |

La power analysis **va rifatta sulla varianza post-fix** e sul numero effettivo di nomi/giorno prima
di congelare il conteggio. Può solo **aumentare** se la varianza peggiora: rivederla al ribasso dopo
aver visto i dati è la mossa che questo documento esiste per impedire.

### Il 28/09 non è una data di verdetto

Da un deploy immediato si arriva a ~30 sedute pulite. La review del 28/09 classifica l'esito come
**tecnico e diagnostico**: pipeline, integrità, direzione. **Non riattiva B e non killa S4 per
insufficienza di significatività.** Ridurre `n` per rispettare una scadenza amministrativa sposta il
rischio dalla pazienza al falso positivo.

Per `n = 213` servono circa dieci mesi di borsa dal deploy. Se si volesse decidere prima, la sola
mossa legittima è **pre-registrare un effetto minimo più grande** accettando che edge più piccoli
restino non decidibili — e va fatto adesso, non a settembre.

---

## 5. Criterio di riattivazione di B — congiuntivo

B può essere riattivata **solo se tutte e quattro** le condizioni sono soddisfatte su un segmento
pulito, congelato e post-fix.

### R1 — Integrità operativa

- ≥ **95%** dei lifecycle shadow ricostruibile end-to-end
- uscite `expired` + `unknown` < **5%**
- nessuna divergenza materiale fra configurazione dichiarata e applicata

### R2 — Alpha

Sulla popolazione **tradabile** (§3), all'orizzonte primario di **2 sedute**:

- IC medio ≥ **+0,05**
- `t` Newey–West ≥ **3**
- segno **non contraddetto** a 1 e 3 sedute

### R3 — Economia

Il portafoglio shadow, dopo fill eseguibili, costi e slippage conservativi, batte il benchmark
**equal-weight della watchlist**, con **limite inferiore unilaterale al 95% dell'excess return > 0**.

### R4 — Indipendenza da S1

Overlap degli intenti con S1 ≤ **50%** (#181, #182). Oltre quella soglia, S4 deve dimostrare **valore
incrementale** rispetto a S1, non P&L standalone.

**Perché congiuntivo.** IC positivo senza monetizzazione non basta. P&L positivo senza relazione
segnale-rendimento può essere fortuna o artefatto della regola d'uscita. Le due cose insieme sono
l'unica evidenza che regge.

### Esito negativo

Il mancato superamento a `n = 73` **non falsifica B e non giustifica un kill**. Al raggiungimento del
campione minimo, IC economicamente nullo o performance netta non positiva implicano **kill o
redesign**, non shadow indefinito. Lo shadow non è un parcheggio: ha una deadline statistica (§4) e
una regola di riattivazione (§5).

---

## 6. Cosa NON conta come evidenza

Pre-registrato per non poterlo invocare in seguito:

- Le **9 chiusure** della settimana 2026-08-06 → 08-12 — campione selezionato, ed è la settimana
  peggiore su cinque contro +209,11 $ sulla vita intera
- Il **controfattuale «compra all'apertura»** (+196,68 $) — usa informazione futura
- La **t = −4,96** sull'ora d'ingresso 14 UTC — 87 osservazioni su 129 sono coorte legacy senza
  attribuzione, 33 da un solo giorno
- Il confronto **realizzato S4 (+209 $) contro S1 (−769 $)** — P&L non omogenei: S1 chiude solo i
  perdenti ed è avversamente selezionato (#210)
- I **30 intenti di overlap** su 2 giorni — troppo corto; è un allarme da misurare, non una prova
- Il **P&L settimanale**, in qualunque direzione

---

## 7. Rischi dichiarati

- **Cambio di popolazione.** I fix a monte (#243, #244) possono migliorare l'IC semplicemente
  selezionando un'altra popolazione. È corretto per costruire la strategia futura, e **vieta di
  concatenare il segmento pre-fix con quello post-fix**.
- **Multiple testing.** La curva completa degli orizzonti serve solo all'esplorazione una tantum
  (§8.1). Il test ha **un solo** orizzonte primario.
- **Dipendenza temporale.** Forward return a 3 e 5 giorni si sovrappongono: errori standard ingenui
  e conteggi nominali sovrastimano la potenza.
- **Simulazione ottimistica.** Fill, slippage e impatto devono essere conservativi. L'ingresso
  tardivo suggerisce che lo slippage strutturale possa superare i costi espliciti contabilizzati.
- **Qualità non osservabile.** «Post-fix» non significa «corretto»: serve verifica su campione
  etichettato (QX-01, #30/#54).
- **Regime shift.** Accumulare giorni non garantisce stazionarietà. Riportare stabilità per
  sottoperiodo **senza** usare gli split per ottimizzare ex post.
- **Confusione fra test tecnico ed economico.** Tenuta mediana, mix delle uscite e turnover dicono se
  B è *implementata*; IC e P&L netto dicono se l'alpha è *monetizzabile*. Nessuno dei due sostituisce
  l'altro.

---

## 8. Sequenza

1. **Snapshot e audit, senza cambiare comportamento.** Congelare configurazione, timestamp, universo
   e segmento pre-deploy. Term structure retrospettiva completa `{1h, 4h, close, 1g, 2g, 3g, 5g}` su
   popolazione pulibile e prezzi eseguibili. **Informa il protocollo, non conta come out-of-sample.**
2. **Questa pre-registrazione, prima di guardare il segmento post-fix.** Include:
   `config/s4_kill_criterion.yaml` **e** l'allineamento di `_esito()` alla popolazione e
   all'orizzonte dichiarati (E3).
3. **Un solo deploy datato:** fix di correttezza del dato (#243, #244) + shadow end-to-end di B
   insieme. Se i fix non sono tutti pronti: shadow subito per sicurezza, ma `n = 0` parte col batch
   atomico successivo.
4. **Validazione tecnica:** lifecycle, fill virtuali, collisioni S1, `reason` code, clock DAILY,
   time-stop. Qualunque errore di implementazione **azzera e riavvia** il campione confirmatorio se
   può averne alterato le osservazioni.
5. **Freeze.** Nessun cambio a fonte, resolver, gate, ranking, soglia, universo, sizing, slot, cost
   model o orizzonte durante la raccolta. Report settimanale separato per integrità, IC diagnostico,
   economia shadow e overlap. **Nessuna decisione su P&L settimanale.**
6. **Review del 28/09:** esito tecnico/diagnostico (§4).
7. **Decisione confirmatoria:** riattivare B solo al superamento congiunto di R1–R4.
8. **Canary:** dopo il gate, riattivazione paper breve a capitale minimo per verificare che fill,
   stato ordini e uscite reali replichino lo shadow. Scala solo dopo riconciliazione.

---

## Registro delle modifiche a questo documento

Ogni modifica va annotata qui con data e motivo. Una modifica non annotata invalida la
pre-registrazione.

| data | modifica | motivo |
|---|---|---|
| 2026-08-14 | versione iniziale | ritiro di #179 (E1–E4) e registrazione del criterio del consolidamento |
