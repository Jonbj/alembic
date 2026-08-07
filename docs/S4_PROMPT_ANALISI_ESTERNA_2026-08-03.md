# Prompt per analisi esterna della strategia S4

> Da consegnare a un LLM esterno insieme ai documenti elencati in fondo.
> Scritto il 2026-08-03. Rifinito il 2026-08-03 contro il codice (`src/strategies/s4`,
> `src/workers/sentiment.py`, `config/trading.yaml`): corretta la composizione dell'universo, lo
> stack di uscita, la soglia dinamica di ingresso, la tassonomia del fallback; aggiunti i caveat
> metodologici (orizzonte vs tesi intraday, istanza del segnale IC↔P&L, potenza per sottogruppo).

---

Sei un quant researcher senior specializzato in segnali alternativi e NLP finanziario. Ti chiedo una
revisione critica di una strategia di trading basata su sentiment da news, chiamata **S4**, e
soprattutto **proposte concrete per migliorarne l'accuratezza**.

Non voglio una rassegna generica di buone pratiche. Voglio una critica ancorata ai numeri e ai
vincoli qui sotto, con proposte che io possa mettere in coda a un programma di test già pre-registrato.

## 1. Che cos'è S4, concretamente

Pipeline offline, in **paper trading** da metà giugno 2026:

1. **Ingestione news** da due sorgenti attive: Alpaca/Benzinga e un worker generico (GDELT GKG).
   ~160-215 articoli al giorno.
2. **Risoluzione ticker deterministica**, separata dal sentiment: alias interni, `company_tickers`
   SEC, OpenFIGI. Emette `NO_TRADE_*` quando l'evidenza è debole. Un ticker sbagliato è considerato
   l'errore peggiore possibile, quindi non è mai deciso dall'LLM.
3. **Scoring del sentiment**: ensemble di **due modelli via Ollama Cloud** (attualmente
   `glm-5.2:cloud` + `gpt-oss:20b-cloud`), più **FinBERT locale int8 come fallback**. Prompt in stile
   Domain-Knowledge Chain-of-Thought: ruolo di analista buy-side, ragionamento step-by-step su
   cash flow / concorrenza / materialità, analisi bull/bear esplicita, output JSON strutturato. **Il
   design spec prevede anche esempi few-shot analogici, ma il prompt live non li contiene** (drift
   doc/code — può incidere sulla qualità; vedi Avvertenza in fondo). Tre limiti hard del segnale: il
   corpo della news è **troncato a 600 caratteri** (`SENTIMENT_LLM_BODY_CHARS`), gli articoli MarketAux con `|sentiment| < 0,20` sono
   **scartati prima dell'LLM** (pre-filter, −60-80% token), e una news più vecchia di **2 ore non
   viene proprio scorerata** all'ingestione (`MAX_NEWS_AGE_HOURS`): la tesi implicita è intraday —
   "la news editoriale oltre le 2 ore è già priced in".
   **Tassonomia del fallback** (46% dei segnali, vedi §2): (i) lettura **single-model** (un modello
   risponde, l'altro va in timeout — `model_id = single:<m>`, `fallback_used = True`); (ii) fallback
   **FinBERT su divergenza** persistente (`ensemble_std > 0,40` dopo un retry senza floor di
   confidenza, fix #90); (iii) fallback FinBERT su timeout/budget di tutti i modelli. #90 fa sì che
   l'accordo a bassa confidenza NON conti come divergenza: viene usato direttamente.
4. **Formula del punteggio**: `score = polarity × confidence`, con polarity ∈ [−1, +1] e
   confidence ∈ [0, 1]. Applicata una sola volta: il ranker ordina per `score` e **non** moltiplica
   di nuovo per confidenza (sarebbe confidence²).
5. **Selezione**: il ranker prende i **top 5** ticker per `score`, con prefiltri `min_score = 0,10`
   e `min_confidence = 0,30`. Sopra questi c'è una **soglia d'ordine live separata,
   `feedback:entry_threshold` (baseline 0,30)** che **ratchetta dinamicamente 0,30 → 0,60** dopo 3
   loss consecutive e decade in 24 h: non è una soglia fissa. Sizing: bucket S4 = 10% del NAV, 5 slot
   **fissi da 2%** (gli slot non usati non vengono ridistribuiti ai sopravvissuti). I segnali più
   vecchi di **4 ore** (`max_signal_age_hours`) sono scartati. È **long-only**: le SELL servono
   solo a chiudere posizioni.
6. **Esecuzione**: ciclo di portafoglio ogni 15 minuti, 14:07-19:52 UTC. Nessuna chiamata LLM nel
   percorso di esecuzione: i segnali sono pre-calcolati e letti da Postgres/Redis. **L'uscita non è
   soglia-triggered ma rank-triggered**: una posizione viene venduta quando il suo ticker esce dal
   target top-5, e serve restarne fuori per **2 cicli consecutivi** (`exit_persistence_cycles = 2`,
   ~30 min) più un **min-hold di 90 min** dall'ingresso (`hold_minimum_minutes`). **Lo stop
   protettivo è DISABILITATO** (`stop_loss = 0,0`): un replay OOS interno ha mostrato che lo stop al
   2% distruggeva ~7,5× l'alpha che proteggeva (stop-out su rumore 0,26-0,53σ che poi recuperava).
   L'anti-whipsaw aggiuntivo (#61) è OFF. Quindi l'unica uscita è il sentiment che crolla sotto la
   soglia + la persistenza, senza nessun floor di protezione.

**Regola #108**: un segnale con `fallback_used = True` non può generare un BUY. Copre sia il
fallback FinBERT (divergenza/timeout/budget) sia la lettura **single-model** (un solo modello ha
risposto). Il sizing breaker, invece, scatta solo su outage completa dell'ensemble (FinBERT), non
su single-model (#128).

## 2. I numeri misurati, non stimati

**Information Coefficient.** Ho misurato se il punteggio predica i rendimenti futuri, su 2.002
osservazioni simbolo-giorno in 34 giorni di borsa. Metodo: una osservazione per simbolo-giorno
(l'**ultimo** segnale del giorno), Spearman cross-sectional giornaliero, t calcolato sui giorni.
Due caveat metodologici che incidono sull'interpretazione:

- **Orizzonte vs tesi.** `forward_return` è a 1/3/5 giorni di borsa (close-to-close, barre Alpaca),
  ma il sistema scorerà solo news più recenti di 2 h (tesi intraday). Se l'alpha fosse intraday,
  l'IC a 5 giorni lo sottostima; se la tesi intraday è sbagliata, l'IC a 5 giorni è la metrica
  giusta. È una tensione di design, non un dettaglio.
- **Istanza del segnale.** L'IC usa l'ultimo segnale del giorno; ma i trade partono intraday sui
  segnali attivi a ogni ciclo (ogni 15 min). Il segnale che ha guidato l'entry di MSFT (+0,765) non
  è quello che l'IC gli attribuirebbe a fine giorno (+0,270). IC e P&L misurano istanze di segnale
  diverse: l'IC dice se il segnale di fine giorno predice, non se i segnali che hanno generato trade
  predicevano.

| sottoinsieme | 1 giorno | 3 giorni | 5 giorni |
|---|---:|---:|---:|
| tutti | −0,018 (t −0,76) | −0,010 (t −0,42) | −0,026 (t −1,09) |
| solo ensemble | −0,006 (t −0,15) | +0,015 (t +0,39) | +0,017 (t +0,49) |
| solo fallback | −0,020 (t −0,45) | −0,061 (t −1,24) | −0,063 (t −1,42) |
| \|score\| ≥ 0,30 | +0,027 (t +0,51) | +0,030 (t +0,48) | +0,064 (t +1,03) |

**Nessuno è significativo.** Ma con 34 giorni e una deviazione standard giornaliera dell'IC di 0,14
sul campione completo, rileviamo solo |IC| > 0,072, mentre l'IC tipico di un segnale azionario in
letteratura è 0,02-0,05. **Quindi l'esito è «non rilevabile», non «assente».** Caveat importante: la dev.std dei
sottoinsiemi è molto più alta del campione completo (ensemble ~0,19-0,25, fallback ~0,23-0,27,
|score|≥0,30 ~0,27-0,31), quindi l'IC minimo rilevabile lì (3·dev/√34) è ~0,10-0,16, non 0,072. Il
sottogruppo più promettente (+0,064 a 5 giorni, |score|≥0,30) è anche il peggio in potenza: la sua
MDE a 5 giorni è ~0,16, e il t massimo stimato (1,03) resta largamente sotto.

**Copertura.** Su 96 simboli in watchlist, ogni giorno **solo 46-60 hanno almeno un articolo**. Nei
report giornalieri `NO_NEWS` è la causa di miss dominante da cinque giorni consecutivi (48-55%).

**Affidabilità dell'ensemble.** Il **46% dei segnali** è `fallback_used = True` (single-model +
FinBERT). Nota: la caratterizzazione "99,3% disaccordo a bassa confidenza, non direzionale" è
precedente al fix #90 (che ora usa l'accordo a bassa confidenza invece di mandarlo in fallback —
vedi §1), quindi il 46% odierno è composto diversamente (divergenza direzionale persistente,
timeout, budget, single-model). Confermare la composizione attuale prima di agire su (d).

**Qualità della cattura.** In un giorno documentato, MSFT è stato comprato a sentiment +0,765 e
rivenduto 2h45 dopo perché il punteggio era sceso a +0,270 — 0,03 sotto la soglia d'*ingresso*. Il
titolo quel giorno ha fatto **+15,5%**; il trade ha realizzato **+13,03 $**.

**Churn del segnale intraday.** Un ticker può produrre 20-31 segnali in 6 ore con punteggi che
oscillano fra −0,20 e +0,57. Il ranker usa **l'ultimo**, quindi il valore che decide dipende da quale
articolo è arrivato per ultimo, non dal peso complessivo della notizia.

**P&L.** Da metà giugno: 287 trade chiusi, 35,9% vincenti, **−559 $ netti**, di cui **172 $ di costi**.
Il lordo è ~−387 $: la strategia **perde anche prima dei costi**, non è solo un problema di turnover.
Conto ~110.000 $; sleeve S4 ~10% (~11 k$, 5 slot da ~2,2 k$). [La cifra è cumulativa; assumerla
S4-only è conservativo — se includesse anche S1, il turnover relativo allo sleeve S4 sarebbe
minore e la win-rate non sarebbe confrontabile.]

## 3. Vincoli non negoziabili

- **Long-only.** Non possiamo shortare. Ogni risultato di letteratura basato su portafogli
  long-short va scomposto per gamba prima di essere applicabile.
- **Universo fisso di 96 nomi**, non "96 large-cap US": ~66 US large/mega-cap + 17 ADR
  internazionali (SAP, SHEL, BP, AZN, UBS, DB, ERIC, NOK, BABA, BIDU, JD, TM, SONY, INFY, RIO, VALE,
  PBR) + 8 ETF (SPY/QQQ/IWM + XLF/XLK/XLE/XLV/SOXX) + 5 nomi aggiunti 2026-06-30 (ROKU, RDDT, HOOD,
  WDC, SPCX — di cui RDDT/HOOD IPO recenti, SPCX è una SPAC). La premessa "titoli più coperti e più
  arbitraggiati del mondo" vale per i mega-cap US, **non** per ADR, ETF, IPO recenti e SPAC — vedi (g).
- **Solo barre giornaliere** per la validazione. Niente fondamentali point-in-time, niente short
  interest, niente dati intraday.
- Nessuna chiamata LLM sincrona nel percorso di esecuzione.
- Capitale ~110.000 $, paper trading; sleeve S4 ~10%. Il deployment è ulteriormente modulato da
  vol-targeting (target 12%) e regime-mult. I costi contano in proporzione al turnover.
- L'ensemble gira su **Ollama Cloud** a pagamento: ri-scorare grandi archivi ha un costo reale.

## 4. Cosa è già stato valutato e scartato, con il motivo

Non ripropormi queste senza un argomento nuovo:

- **Aggiungere un terzo modello all'ensemble** — considerato, non escluso, ma non risolve il problema
  a monte (la copertura). Nota: esiste già un'infrastruttura di **shadow scoring**
  (`llm_shadow_responses`) che ri-scora offline ogni item con i modelli candidati non in coppia,
  quindi il contributo marginale di un terzo modello è misurabile a costo marginale quasi zero (non
  pagandolo in produzione) — vedi (d).
- **Reinforcement learning e bot a indicatori** — una rassegna della letteratura ha concluso che non
  producono alpha nel nostro contesto.
- **Sostituire l'ensemble con FinGPT** — accuracy di movimento riportata 45-53%, cioè testa o croce.
- **Comprare dati storici senza bias di sopravvivenza** (Norgate, ~630 $/anno) — risolve i titoli
  delistati, non la selezione della watchlist, che è la distorsione dominante.
- **Costruire un archivio news storico per backtestare S4** — il costo dominante è il ri-scoring di
  anni di articoli con l'ensemble. E il sistema genera ~59 osservazioni al giorno da solo: in un anno
  raggiunge la stessa potenza statistica a costo zero. L'archivio comprerebbe solo l'anticipo.

## 5. Cosa ti chiedo

Rispondi a queste domande, in quest'ordine, e **distingui sempre ciò che è misurabile con i nostri
dati da ciò che è congettura**.

**(a) Diagnosi.** Guardando i numeri della sezione 2, dove sta il problema principale? Copertura
dati, qualità del modello, formula del punteggio, meccanica di ingresso/uscita, o la premessa stessa
che la news editoriale contenga alpha su large-cap liquidi? Argomenta con i numeri, non per
plausibilità. Distingui ciò che indebolisce l'IC (segnale) da ciò che indebolisce il P&L ma non l'IC
(meccanica, sizing, costi).

**(b) La formula.** `score = polarity × confidence` è una scelta di progetto mai validata. Ha
proprietà indesiderabili? Esistono alternative documentate in letteratura, e come le testeresti
distinguendole dal rumore con il campione che abbiamo? Nota: i dati mostrano già un pattern — IC
negativo sui segnali a bassa convinzione, positivo (debole) su |score|≥0,30 — che suggerisce che
moltiplicare per confidenza potrebbe star facendo la cosa sbagliata O quella giusta; l'IC da solo
non distingue. Come lo disambigueresti?

**(c) Il churn intraday.** Con 20-31 segnali al giorno per ticker e varianza altissima, quale regola
di aggregazione useresti al posto di «l'ultimo vince» (max, media pesata per confidenza, decay
temporale, o altro)? Come si sceglie fra queste senza fare data mining su 34 giorni? **Attenzione a
non proporre ciò che già esiste**: l'uscita ha già un'isteresi (2 cicli fuori target + min-hold 90
min); la domanda è sull'aggregazione del *valore* del segnale che entra nel ranker, non sull'uscita.

**(d) Efficacia dei modelli.** Come valuteresti se `glm-5.2` + `gpt-oss` siano la coppia giusta, dato
che il 46% delle volte è `fallback_used`? Prima di ipotizzare un problema di modello, considera che
l'input è troncato a 600 caratteri, le news più vecchie di 2 h non sono scorerate, e il prompt live
non ha few-shot (vedi Avvertenza) — quanto del "non-convergere" è un problema di modello vs un
problema di input (testo troncato / vecchio / generico)? Per il contributo marginale di un terzo
modello: esiste già lo shadow scoring (`llm_shadow_responses`) — come useresti i suoi output per
decidere prima di pagare?

**(e) Ingresso e uscita.** Correzione di premessa: l'uscita non è "soglia d'ingresso senza banda
morta" — è **rank-triggered** (vendo quando il ticker esce dal top-5 per 2 cicli consecutivi, con
min-hold 90 min), con stop protettivo disabilitato (evidenza: stop al 2% distruggeva ~7,5× l'alpha)
e nessun floor di protezione. La soglia d'ingresso inoltre ratchetta 0,30→0,60 sulle loss. Su questa
base reale: quale struttura di ingresso/uscita proposeresti, e quale evidenza servirebbe? Valuta
esplicitamente se reintrodurre un floor di protezione (diverso dallo stop al 2% già scartato) o se
l'assenza di floor è corretta per la tesi intraday.

**(f) Il problema della copertura.** Metà della watchlist non ha notizie in un giorno tipico. Separa
due questioni: (1) **esistenza** della news (`NO_NEWS` = nessun articolo per quel ticker) e (2)
**raggiungimento del modello** (dopo il pre-filter MarketAux `|sent|<0,20` e il cutoff 2 h). Le due
hanno cause e fix diversi. Quali sorgenti aggiungeresti per (1), e — più importante — come
stabiliresti *prima* di integrarle se aumenterebbero davvero il segnale (IC cross-sectionale ≠ 0 su
un campione) invece del solo volume?

**(g) La domanda scomoda.** Sulla base di quanto sopra: c'è una ragione teorica per aspettarsi alpha
da sentiment su news editoriale riguardo a un universo **misto** (mega-cap US molto coperti + ADR +
ETF + IPO recenti/SPAC)? La premessa "più coperti e più arbitraggiati del mondo" vale solo per una
parte della watchlist: valuta l'alpha per sottogruppo, non in aggregato. Un test concreto e a costo
zero: calcolare l'IC per settore/gruppo (la mappa settoriale è in `config/trading.yaml`) e vedere se
si concentra nei nomi meno coperti. Se l'alpha fosse assente anche lì, dillo: preferisco una
risposta negativa argomentata a una lista di migliorie su una premessa sbagliata.

## 6. Come voglio la risposta

- **Ogni proposta con un test associato**: cosa misureresti, su quale campione, e quale risultato la
  falsificherebbe. Una proposta non falsificabile non mi serve.
- **Confrontati con il vincolo di potenza.** Con 34 giorni rileviamo solo |IC| > 0,072 sul campione
  completo (e ~0,10-0,16 sui sottogruppi; ~0,14-0,16 per il solo |score|≥0,30). Se una tua proposta
  richiede più campione di quello che abbiamo, dimmi quanto ne serve.
- **Ordina per rapporto (valore atteso)/(costo del test)**, non per interesse intellettuale.
- **Dichiara le tue incertezze.** Se citi un risultato di letteratura, indica su quale universo e
  periodo è stato stabilito, e se è sopravvissuto a repliche recenti. Molti effetti documentati prima
  del 2010 sono decaduti.
- Se pensi che qualcuno dei nostri vincoli sia sbagliato o auto-inflitto, dillo. (Es: la tesi intraday
  con cutoff 2 h vs validazione a barre giornaliere è una tensione interna — vale la pena
  problematizzarla.)
- **Non riempire una domanda con proposte se la risposta onesta è «non c'è alpha» o «non lo so».**
  Per (g) in particolare, una risposta negativa argomentata è il risultato più utile che puoi darmi.

---

## Avvertenza sulla documentazione

Questo repo ha una storia documentata di **divergenza fra documentazione e codice**. Verificando gli
allegati il 2026-08-03 ho trovato che la tabella dei parametri di S4 in `docs/strategies.md`
elencava quattro campi di cui **nessuno esisteva nel codice**, e uno dichiarava una scadenza segnale
di 30 minuti contro le 4 ore reali. È stata corretta, ma la lezione vale in generale:

**Dove documentazione e codice si contraddicono, il codice ha ragione.** Se noti un'incoerenza,
segnalala: è essa stessa un finding utile.

Un secondo esempio, rilevante per la domanda (d): il design spec (CLAUDE.md) richiede che il prompt
DK-CoT includa **esempi few-shot analogici**, ma il prompt live in `src/workers/sentiment.py`
**non li contiene**. È un drift aperto che può incidere sulla qualità del segnale.

I numeri della sezione 2 di questo documento sono invece misurati direttamente sul database di
produzione, non presi dalla documentazione.

## Documenti da allegare

1. `docs/evidence/S4_IC_ANALISI_2026-08-03.md` — la misura dell'IC e il vincolo di potenza
2. `docs/evidence/s4_ic.json` — la serie giornaliera degli IC
3. `docs/ALPHA_MISS_REPORT_2026-07-{27,28,29,30,31}.md` — cinque giorni di analisi «cosa abbiamo
   mancato e perché», con la classificazione delle cause
4. `docs/research/2026-08-01-momentum-literature-hypotheses.md` — l'analisi di letteratura su S1, utile
   come esempio del livello di rigore atteso e del metodo di pre-registrazione
5. `docs/evidence/PREREGISTRAZIONE_BACKTEST_S1.md` — il protocollo statistico in uso (soglia |t| ≥ 3,
   correzione per test multipli, distinzione calibrazione/confermativa/diagnostica)
6. `docs/RESEARCH_SYNTHESIS_ALPHA_AND_TOOLING_2026-07-26.md` — la rassegna che ha portato a scartare
   RL, bot a indicatori e FinGPT
7. `docs/strategies.md` §S4 — parametri verificati contro il codice il 2026-08-03
8. `src/strategies/s4/` e `src/workers/sentiment.py` — il codice della strategia e dello scoring.
   **Autorevole in caso di conflitto con la documentazione.**
9. `config/trading.yaml` — watchlist, soglie, parametri di rischio