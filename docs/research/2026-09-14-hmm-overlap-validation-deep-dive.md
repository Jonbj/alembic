# Deep dive: K=5 overlap, HMM persistence e validation gate

**Data:** 2026-09-14  
**Origine:** approfondimento del triage su “I Built a Trading Bot That Refuses to Trade Until It Can Prove It Has an Edge”.  
**Scopo:** misurare quanta “persistenza di regime” nasce meccanicamente dal rolling return K=5 e definire un gate causale per Alembic [#580](https://github.com/Jonbj/alembic/issues/580). Non è una replica dell'EA né un'autorizzazione all'implementazione.

## Risultato in breve

Con rendimenti base perfettamente IID, un return cumulativo rolling K=5 ha autocorrelazione teorica lag-1 pari a `4/5 = 0,8`. Nella replica a seed fisso è `0,7998`; una semplice segmentazione in tercili resta nello stesso pseudo-stato il `64,80%` delle volte, contro circa `33,5%` per K=1 e K=5 non-overlap. Un HMM può quindi interpretare come durata di regime una dipendenza creata dalla feature.

Il validation gate “mean edge > 0” non corregge il problema. Su 100.000 campioni null con 84 osservazioni K=5, passa nel `50,086%` dei casi prima dei costi. Con costo 5 bp passa ancora nel `41,950%`; una lower confidence bound calcolata erroneamente come IID passa nel `17,920%`, mentre usando `N_eff=N/5` scende al `3,883%`. È un controllo di incertezza, non una prova definitiva: dipendenza HMM/trade, molteplici retrain e scelta delle varianti richiedono block bootstrap, trial ledger e holdout forward untouched.

## 1. Derivazione dell'overlap

Siano i rendimenti base `r_t` IID con media zero e varianza `sigma²`. Definiamo il K-period return rolling:

`X_t = r_t + r_(t-1) + ... + r_(t-K+1)`.

Allora:

- `Var(X_t) = K sigma²`;
- `X_t` e `X_(t-1)` condividono esattamente `K-1` shock;
- `Cov(X_t, X_(t-1)) = (K-1) sigma²`;
- quindi `Corr(X_t, X_(t-1)) = (K-1)/K`.

Più in generale, per `0 < h < K`, `rho_h=(K-h)/K`; per `h>=K`, `rho_h=0`. La integrated autocorrelation time asintotica per la media è:

`IAT = 1 + 2 sum(rho_h, h=1..K-1) = K`,

da cui `N_eff ≈ N/K`. Il rolling produce quasi K volte più righe del non-overlap, ma non K volte più informazione. L'econometria degli overlapping returns tratta precisamente la correlazione seriale indotta da finestre condivise ([Hansen e Hodrick, 1980](https://doi.org/10.1086/260910)).

Questa derivazione presuppone IID e somma di log-return. Con autocorrelazione, eteroschedasticità e range/volume reali la formula `0,8` non è più esatta; non c'è però ragione per aspettarsi che il problema sparisca.

## 2. Replica sintetica

Ambiente locale: Python/NumPy, seed `20260914`, `N=200000`, rendimenti `Normal(0,1)`. `hmmlearn`, `scikit-learn` e `statsmodels` non sono installati: per non aggiungere dipendenze al repository, la replica usa ACF/ESS e una segmentazione tercile dichiarata, non finge un fit HMM.

| Feature | N righe | ACF(1) | P(stesso tercile adiacente) | ESS stimato |
|---|---:|---:|---:|---:|
| K=1 | 200.000 | -0,0001 | 0,3346 | 199.691 |
| K=5 rolling | 199.996 | 0,7998 | 0,6480 | 39.989 |
| K=5 non-overlap | 40.000 | 0,0032 | 0,3376 | 39.286 |

L'ESS è calcolato da `N/(1+2 sum(max(ACF_h,0), h=1..4))`; il valore teorico K=5 è 40.000. La segmentazione in tercili non è un HMM: serve solo a mostrare che anche uno state assignment privo di memoria appare persistente quando l'input ha overlap.

Su 100.000 boundary IID indipendenti:

- ultimo K=5 train vs primo K=5 validation senza purge: correlazione `0,7990`;
- ultimo K=5 train vs primo validation dopo quattro endpoint scartati: `-0,0056`, compatibile con zero.

La replica isola quindi due fenomeni distinti: dipendenza **interna** a tutta la serie rolling e contaminazione **attraverso** il confine train/validation.

## 3. Purge minimo e causalità HMM

Per la sola feature backward-looking K=5, il minimo embargo al confine è `K-1=4` barre/endpoints: il primo feature vector validation conservato non deve condividere alcun `r_t` con l'ultimo feature vector train.

Questo non basta quando esistono target o trade forward-looking:

- eliminare dal train ogni osservazione la cui label/holding interval attraversa il confine;
- aggiungere le quattro barre richieste dalla feature backward alla partenza della validation;
- in modo equivalente, se si conserva l'ultimo target train di orizzonte `H`, la separazione raw deve arrivare a `H+K-1`;
- usare gli intervalli reali entry-exit quando la durata è variabile, non una costante media HMM.

Passare alla validation la probabilità **filtrata** terminale del train è causale, se parametri e scaler restano congelati. Usare posteriori smoothed, che incorporano osservazioni future, non lo è. Durante validation non si rifittano emissioni, transizioni, soglie o mapping dei label.

Il purge rimuove la condivisione al confine; non rende IID le osservazioni validation K=5. Inferenza e bootstrap devono ancora rispettarne la dipendenza.

## 4. Positive-mean gate contro lower confidence bound

### Esperimento null

Sono stati simulati 100.000 validation set, ciascuno con 84 osservazioni rolling K=5 e volatilità marginale 1%. Il true gross edge è zero; il costo round-trip illustrativo è 5 bp.

| Gate | Frazione di campioni null promossi |
|---|---:|
| gross sample mean `>0` | 50,086% |
| net sample mean, dopo 5 bp, `>0` | 41,950% |
| one-sided 95% LCB net, assumendo falsamente N=84 IID | 17,920% |
| one-sided 95% LCB net, usando `N_eff=84/5=16,8` | 3,883% |

La LCB approssimata è `mean_net - 1.645*s/sqrt(N_eff)`. `N_eff=16,8` è corretto solo sotto il null MA(4) sintetico; in Alembic va stimata la dipendenza e affiancato un bootstrap a blocchi.

In un singolo campione riproducibile della stessa replica:

- mean gross `+3,335 bp`: il gate positivo passa;
- mean net `-1,665 bp`;
- LCB IID `-17,516 bp`;
- LCB effective-N `-37,109 bp`;
- moving-block bootstrap circolare, block length 5 e 20.000 resample: LCB 5% `-28,109 bp`, intervallo percentile 90% `[-28,109; +24,319] bp`.

Il block length 5 è il minimo illustrativo coerente con la feature sintetica. Su trade/regimi reali va preregistrato e stressato; 84 osservazioni lasciano poca precisione. Il moving-block bootstrap nasce per osservazioni stazionarie dipendenti ([Künsch, 1989](https://doi.org/10.1214/aos/1176347265)).

### Il conteggio 46/84 non dimostra direzione

Nel validation example, `46/84 = 54,762%`. Sotto una moneta equa e indipendente:

- test binomiale esatto one-sided `P(X>=46)=0,2226`;
- intervallo binomiale esatto Clopper-Pearson 95% `[43,52%; 65,66%]`.

Include quindi 50%; con dipendenza e selezione ripetuta l'evidenza è ancora più debole. È inoltre un test di hit-rate, non di P&L netto o utilità. L'intervallo esatto inverte il test binomiale secondo il metodo originale di [Clopper e Pearson, 1934](https://doi.org/10.1093/biomet/26.4.404).

Se un gate “mean>0” viene rieseguito su `m` finestre null indipendenti e basta un singolo pass, il riferimento illustrativo è `P(any pass)=1-0.5^m`: per `m=5`, `0,96875`. Le finestre rolling reali non sono indipendenti, quindi questo non è una stima del sistema dell'articolo né un bound universale; mostra soltanto perché repeated gating e scelta post-hoc richiedono un ledger e controllo della molteplicità ([White, 2000](https://doi.org/10.1111/1468-0262.00152)).

## 5. Incertezza della expected state duration

Per un HMM standard la durata attesa nello stato `i` è `D_i=1/(1-A_ii)` ([Rabiner, 1989](https://www.cs.cornell.edu/courses/cs481/2004fa/rabiner.pdf)). La trasformazione esplode vicino a `A_ii=1`.

Esempio favorevole che tratta la sequenza di stato come **nota** e osserva 80 transizioni in uscita dallo stato:

| self transitions / 80 | `A_ii` | durata point estimate | 95% CI trasformato da Wilson |
|---:|---:|---:|---:|
| 64 | 0,80 | 5,0 barre | [3,33; 7,87] |
| 72 | 0,90 | 10,0 barre | [5,40; 19,40] |
| 76 | 0,95 | 20,0 barre | [8,22; 50,99] |

In un HMM vero gli stati sono latenti e le transizioni sono fractional posterior counts; emissioni, `A` e label mapping sono stimati insieme da EM, che può convergere a massimi locali. La tabella sottostima quindi l'incertezza completa. Un retrain da 250 barre e tre stati deve pubblicare occupancy/effective transitions, seed dispersion e intervallo/bootstrap di `D_i`; stati sotto una soglia preregistrata non possono pilotare holding o stop.

## 6. Script minimale riproducibile

```python
import numpy as np

rng = np.random.default_rng(20260914)
N, K = 200_000, 5
r = rng.standard_normal(N)
xs = {
    "K1": r,
    "K5 rolling": np.convolve(r, np.ones(K), mode="valid"),
    "K5 nonoverlap": r[: N // K * K].reshape(-1, K).sum(1),
}
for name, x in xs.items():
    acf = [np.corrcoef(x[:-h], x[h:])[0, 1] for h in range(1, K)]
    q = np.quantile(x, [1 / 3, 2 / 3])
    state = np.digitize(x, q)
    iat = 1 + 2 * sum(max(v, 0) for v in acf)
    print(name, np.corrcoef(x[:-1], x[1:])[0, 1],
          np.mean(state[:-1] == state[1:]), len(x) / iat)

# Boundary Monte Carlo: shared 4/5 shocks, then disjoint after purge=4.
z = rng.standard_normal((100_000, 2 * K))
train = z[:, :K].sum(1)
val0 = z[:, 1:K + 1].sum(1)
val_purged = z[:, K:2 * K].sum(1)
print(np.corrcoef(train, val0)[0, 1],
      np.corrcoef(train, val_purged)[0, 1])
```

Gate Monte Carlo e block-bootstrap:

```python
M, n, cost = 100_000, 84, 0.0005
rng = np.random.default_rng(20260914)
e = rng.normal(0, 0.01, (M, n + K - 1))
cs = np.pad(np.cumsum(e, axis=1), ((0, 0), (1, 0)))
x = (cs[:, K:] - cs[:, :-K]) / np.sqrt(K)
mu, s = x.mean(1), x.std(1, ddof=1)
print(np.mean(mu > 0), np.mean(mu - cost > 0))
print(np.mean(mu - cost - 1.645 * s / np.sqrt(n) > 0))
print(np.mean(mu - cost - 1.645 * s / np.sqrt(n / K) > 0))

# Singolo campione: seed fisso, dopo lo stesso prefisso N della replica principale.
rng = np.random.default_rng(20260914)
rng.standard_normal(N)
e = rng.normal(0, 0.01, n + K - 1)
x = np.convolve(e, np.ones(K), mode="valid") / np.sqrt(K)
B = 20_000
starts = rng.integers(0, n, size=(B, int(np.ceil(n / K))))
idx = (starts[:, :, None] + np.arange(K)) % n
boot_net = x[idx].reshape(B, -1)[:, :n].mean(1) - cost
print(x.mean(), x.mean() - cost, np.quantile(boot_net, [0.05, 0.95]))
```

Per un artifact operativo questi calcoli vanno versionati come test del runner #580, non copiati dal report.

## 7. Protocollo Alembic dentro #580

1. **Status:** HMM resta challenger opzionale; baseline persistence, EWMA/STD e GARCH vengono prima.
2. **Feature ablation congelata:** K=1, K=5 rolling e K=5 non-overlap; range estimator e tick-volume on/off; scaler fit solo sul train.
3. **Fit HMM:** probabilità filtrate, almeno più seed, floor sulle varianze, minimum state occupancy/effective transitions e mapping deterministico dei label fra refit.
4. **Split:** walk-forward PIT; purge degli event interval e almeno K-1 barre di embargo feature; nessun smoothing futuro.
5. **Target/metriche:** realized variance agli orizzonti predefiniti; QLIKE e MSE/calibrazione, più turnover, exposure, costi, drawdown e tail loss.
6. **Gate:** non `mean>0`. Richiedere contemporaneamente improvement OOS preregistrato sulla baseline e one-sided cost-adjusted block-bootstrap LCB `>0`, senza degrado di coda.
7. **Informazione minima:** soglia su `N_eff`, non numero righe/trade; pubblicare ACF, block length/sensitivity, state occupancy e intervalli sulla durata.
8. **Molteplicità:** trial ledger completo per seed, K, feature, N states, covariance e soglie; DSR/Reality Check secondo il contratto già previsto.
9. **Holdout:** un ultimo blocco untouched aperto una volta; repeated post-retrain gates fanno parte della policy da testare, non sono validatori indipendenti.
10. **Artifact:** code/data/config hash, decision timestamp, train/validation endpoints, purge, seeds, mapping stati e risultati di ogni baseline/challenger.

Relazioni: [#31](https://github.com/Jonbj/alembic/issues/31) resta il gate separato per stop `vol_scaled`; [#84](https://github.com/Jonbj/alembic/issues/84) fornisce preregistrazione/holdout/trial-accounting; [#171](https://github.com/Jonbj/alembic/issues/171) impedisce modifiche operative durante il freeze.

## Decisione

**Nessuna nuova issue e nessuna campagna autonoma.** Allegare questo approfondimento al contesto di #580. Il primo test utile non è “HMM sì/no”, ma se l'HMM conserva valore incrementale dopo aver rimosso la persistenza meccanica K=5, rispettato un confine purged e sostituito il positive-mean gate con una decisione netta dei costi e corretta per incertezza/molteplicità.
