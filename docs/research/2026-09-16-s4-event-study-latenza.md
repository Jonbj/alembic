# S4 — event study attorno al timestamp delle news: dove si perde il segnale

**2026-09-16 · esplorativo, post-hoc, NON pre-registrato.** I numeri qui dentro sono
ipotesi, non risultati. Il test confermativo è pre-registrato in
`docs/evidence/PREREGISTRAZIONE_GAP_OFFHOURS_2026-09-16.md` (#606).

## Da cosa nasce

Un'analisi esterna sosteneva che il sentiment funzionasse **al contrario** ("buy the
rumor, sell the news"): news positive seguite da −0,78% a 5 giorni. Riprodotta esatta
sull'aritmetica, **falsa nell'inferenza**: `forward_return*` è un close-to-close grezzo,
non depurato dal fattore giornata. Demediando per seduta i positivi passano da −0,78% a
**+0,06%**, e 5 giornate su 64 portavano tutto l'effetto. Il claim più forte — negativi
forti al 64,6% di hit rate — scende a 54,0% (IC95 44,8–63,2) con t −0,31 sui 31 giorni.

Restava però un fatto vero: l'IC di S4 è **persistentemente negativo**, non zero.
−0,036 con t −2,09 su 64 giorni, stesso segno su tre orizzonti, due fonti, due motori.
Un IC zero è rumore; un IC negativo costante è un **meccanismo**. Questo documento lo
cerca.

## Scomposizione dell'IC (post-hoc)

| taglio | segmento | oss | IC 1g | t |
|---|---|---|---|---|
| latenza pub→scoring | < 15 min | 289 | **+0,101** | +1,14 |
| | 15-60 min | 1.168 | +0,021 | +0,51 |
| | 1-3 h | 1.973 | −0,028 | −1,13 |
| fonte | alpaca_benzinga | 2.608 | −0,022 | −1,05 |
| | gdelt_gkg | 1.006 | **−0,099** | −2,65 |
| motore | ensemble | 2.720 | −0,039 | −1,68 |
| | FinBERT fallback | 1.925 | −0,038 | −1,50 |

Tre letture, tutte da pre-registrare prima di essere usate:

1. **Gradiente di latenza.** Il segno è positivo solo sotto i 15 minuti, su tutti e tre
   gli orizzonti (+0,10 / +0,10 / +0,28), e degrada monotonicamente. Nessuna banda è
   significativa da sola e la banda fresca è quasi vuota (4-8 giornate).
2. **GDELT.** Il 28% delle osservazioni porta gran parte del segno negativo, e tiene
   segmentando per periodo.
3. **L'ensemble non batte FinBERT.** Due modelli cloud con prompt DK-CoT pareggiano un
   classificatore locale a 3 classi. È un'indicazione sulla premessa dell'intero
   paradigma, non su S4.

## L'event study: la news muove il prezzo?

749 news Benzinga **in orario**, |score| ≥ 0,10, 25 sedute, 76 simboli, barre al minuto
SIP. Segno allineato al sentiment, rendimento rispetto al prezzo all'istante della news.

| T−60 | T−15 | T−1 | T+1 | T+15 | T+60 |
|---|---|---|---|---|---|
| −0,013% | +0,000% | −0,004% | +0,000% | +0,022% | +0,010% |

Piatta, ogni IC contiene lo zero. Poteva essere disallineamento dei timestamp, quindi il
controllo che lo distingue — la **volatilità al minuto**, che su un evento vero fa 2-5×
anche quando la direzione media è zero:

| T−10 | T−1 | T+0 | T+1 | T+5 | T+30 |
|---|---|---|---|---|---|
| 0,84× | 0,92× | **0,89×** | 0,89× | 0,78× | 0,75× |

**Nessun picco.** E il rapporto è sotto 1 ovunque: la finestra di riferimento (T−30 →
T−6) è più agitata dell'evento. Sui soli |score| ≥ 0,5 (n=35) è 0,58× a T+0.

Quote di movimento: al `published_at` è già avvenuto il **61,3%** mediano del movimento
[−60,+60]; quando noi scoriamo, l'**82,9%**. Il nostro ritardo mediano su questo
sottoinsieme è 21,7 minuti.

**Lettura: due terzi del ritardo sono della fonte, un terzo è nostro.** Lo stream
Benzinga intraday è in larga parte cronaca del prezzo — l'articolo segue il movimento.
Una fonte più veloce dello *stesso* contenuto non aiuta: non si anticipa uno specchio.

## Il ribaltamento: le news fuori orario

Stessa misura sulle news pubblicate a mercato chiuso. 380 eventi, 330 utilizzabili.

| | media allineata | t |
|---|---|---|
| gap di apertura, grezzo | +0,678% | +3,86 |
| gap in eccesso su SPY | +0,637% | +3,81 |
| **gap in eccesso, clusterizzato per giornata (49 gg)** | **+0,560%** | **+2,35** |
| intraday dopo l'apertura | +0,078% | +0,49 |

Giornate con media positiva: 29 su 49. Segnali scoriati **dopo** l'apertura della seduta
di reazione: **279 su 330 (85%)**.

Il sentiment funziona — sugli eventi veri, con il segno giusto, e sopravvive
all'aggiustamento di mercato quasi intatto (0,678 → 0,637). Ma con il clustering per
giornata la t scende a 2,35, **sotto la barra |t| ≥ 3 della casa**. È un candidato
forte, non un risultato.

### Trappola trovata e corretta, da non ripetere

La prima passata dava +0,936% con n=68. L'attrito 380→68 non era casuale: Alpaca rifiuta
l'**intera** richiesta con `subscription does not permit querying recent SIP data` quando
la finestra tocca l'embargo sul dato recente, quindi cadevano i simboli con news recenti
— cioè i più liquidi (AAPL, MSFT, GOOGL, META, NVDA…). Con la finestra troncata a
`now − 3 giorni`: n=330 e l'effetto **scende** a +0,678%. Un fetch fallito deve abortire
la misura, mai ridurre il campione in silenzio.

## Conseguenza

L'IC aggregato di S4 è ≈0-negativo perché mescola due popolazioni opposte:

- **intraday** (~80% del flusso): non-eventi, nessuna reazione, IC negativo — diluiscono;
- **fuori orario** (~20%): eventi veri, segnale corretto, **non raccolto** perché l'85%
  viene scoriato dopo l'apertura.

Il sistema sa già distinguerle: `src/analysis/dossier/article_coverage.py` classifica
`ANTICIPATORY` / `CONCURRENT` / `RETROSPECTIVE` e marca i template content-mill come
`CONTENT_EMPTY`. Ma quel codice vive **solo nel livello dossier**. Nessun path di segnale
lo legge: ogni articolo retrospettivo diventa comunque un segnale tradabile.

E il turno di notte esiste: `src/workers/sentiment_shadow.py` (#432 Opzione C) consuma la
coda off-session, ma scrive in una tabella ombra che nessuno legge.

**L'ostacolo vero:** il gap non è incassabile entrando all'apertura — lì è già avvenuto,
e resta la gamba intraday che vale +0,078% con t 0,49. Il +0,560% è la *prova che il
segnale è informativo*, non un rendimento disponibile. Incassarlo richiede esecuzione in
extended hours, che è un cambiamento di execution, non un flag (#608).

## Seguiti

- **#606** — test confermativo pre-registrato su H1 (≈31 giornate mancanti, soglia verso
  metà novembre 2026).
- **#607** — decisione del 28/09: separare le due popolazioni nel path dei segnali e
  anticipare lo scoring prima dell'apertura. Entrambe **taratura**, congelate fino ad allora.
- **#608** — raccoglibilità: si può eseguire in extended hours con la nostra size?
