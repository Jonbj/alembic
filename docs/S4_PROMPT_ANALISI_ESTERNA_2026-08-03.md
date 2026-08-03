# Prompt per analisi esterna della strategia S4

> Da consegnare a un LLM esterno insieme ai documenti elencati in fondo.
> Scritto il 2026-08-03.

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
   Domain-Knowledge Chain-of-Thought: ruolo di analista buy-side, ragionamento su cash flow /
   concorrenza / redditività, esempi few-shot analogici, output JSON strutturato, analisi bull/bear
   esplicita prima del verdetto.
4. **Formula del punteggio**: `score = polarity × confidence`, con polarity ∈ [−1, +1] e
   confidence ∈ [0, 1].
5. **Selezione**: un ranker prende i **top 5** ticker per punteggio, con prefiltri `min_score = 0.10`
   e `min_confidence = 0.30`, e una **soglia d'ordine separata a 0.30**. I segnali più vecchi di
   **4 ore** sono scartati. È **long-only**: le SELL servono solo a chiudere posizioni.
6. **Esecuzione**: ciclo di portafoglio ogni 15 minuti, 14:07-19:52 UTC. Nessuna chiamata LLM nel
   percorso di esecuzione: i segnali sono pre-calcolati e letti da Postgres/Redis.

**Regola #108**: un segnale prodotto dal solo fallback (senza ensemble) non può generare un BUY.

## 2. I numeri misurati, non stimati

**Information Coefficient.** Ho appena misurato se il punteggio predica i rendimenti futuri, su
2.002 osservazioni simbolo-giorno in 34 giorni di borsa. Metodo: una osservazione per simbolo-giorno
(l'ultimo segnale del giorno, che è quello che il ranker usa), Spearman cross-sectional giornaliero,
t calcolato sui giorni.

| sottoinsieme | 1 giorno | 3 giorni | 5 giorni |
|---|---:|---:|---:|
| tutti | −0,018 (t −0,76) | −0,010 (t −0,42) | −0,026 (t −1,09) |
| solo ensemble | −0,006 (t −0,15) | +0,015 (t +0,39) | +0,017 (t +0,49) |
| solo fallback | −0,020 (t −0,45) | −0,061 (t −1,24) | −0,063 (t −1,42) |
| \|score\| ≥ 0,30 | +0,027 (t +0,51) | +0,030 (t +0,48) | +0,064 (t +1,03) |

**Nessuno è significativo.** Ma con 34 giorni e una deviazione standard giornaliera dell'IC di 0,14,
rileviamo solo |IC| > 0,072, mentre l'IC tipico di un segnale azionario in letteratura è 0,02-0,05.
**Quindi l'esito è «non rilevabile», non «assente».**

**Copertura.** Su 96 simboli in watchlist, ogni giorno **solo 46-60 hanno almeno un articolo**. Nei
report giornalieri `NO_NEWS` è la causa di miss dominante da cinque giorni consecutivi (48-55%).

**Affidabilità dell'ensemble.** Il **46% dei segnali** è prodotto dal fallback perché i due modelli
non convergono. Un'analisi precedente ha stabilito che la "divergenza" è per il 99,3% disaccordo a
bassa confidenza, non disaccordo direzionale.

**Qualità della cattura.** In un giorno documentato, MSFT è stato comprato a sentiment +0,765 e
rivenduto 2h45 dopo perché il punteggio era sceso a +0,270 — 0,03 sotto la soglia d'*ingresso*. Il
titolo quel giorno ha fatto **+15,5%**; il trade ha realizzato **+13,03 $**.

**Churn del segnale intraday.** Un ticker può produrre 20-31 segnali in 6 ore con punteggi che
oscillano fra −0,20 e +0,57. Il ranker usa **l'ultimo**, quindi il valore che decide dipende da quale
articolo è arrivato per ultimo, non dal peso complessivo della notizia.

**P&L.** Da metà giugno: 287 trade chiusi, 35,9% vincenti, **−559 $ netti**, di cui **172 $ di costi**
(cioè i costi sono il 31% della perdita). Il conto è ~110.000 $.

## 3. Vincoli non negoziabili

- **Long-only.** Non possiamo shortare. Ogni risultato di letteratura basato su portafogli
  long-short va scomposto per gamba prima di essere applicabile.
- **Universo fisso di 96 large-cap US** più alcuni ETF settoriali. Non small-cap.
- **Solo barre giornaliere** per la validazione. Niente fondamentali point-in-time, niente short
  interest, niente dati intraday.
- Nessuna chiamata LLM sincrona nel percorso di esecuzione.
- Capitale ~110.000 $, paper trading. I costi contano in proporzione al turnover.
- L'ensemble gira su **Ollama Cloud** a pagamento: ri-scorare grandi archivi ha un costo reale.

## 4. Cosa è già stato valutato e scartato, con il motivo

Non ripropormi queste senza un argomento nuovo:

- **Aggiungere un terzo modello all'ensemble** — considerato, non escluso, ma non risolve il problema
  a monte (la copertura).
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
plausibilità.

**(b) La formula.** `score = polarity × confidence` è una scelta di progetto mai validata. Ha
proprietà indesiderabili? Esistono alternative documentate in letteratura, e come le testeresti
distinguendole dal rumore con il campione che abbiamo?

**(c) Il churn intraday.** Con 20-31 segnali al giorno per ticker e varianza altissima, quale regola
di aggregazione useresti al posto di «l'ultimo vince»? Massimo, media pesata per confidenza, decay
temporale, o altro? Come si sceglie fra queste senza fare data mining su 34 giorni?

**(d) Efficacia dei modelli.** Come valuteresti se `glm-5.2` + `gpt-oss` siano la coppia giusta, dato
che il 46% delle volte non convergono? E come misureresti il contributo marginale di un terzo modello
prima di pagarlo?

**(e) Ingresso e uscita.** L'uscita usa la stessa soglia dell'ingresso, senza banda morta. Quale
struttura proporresti, e quale evidenza servirebbe per giustificarla?

**(f) Il problema della copertura.** Metà della watchlist non ha notizie in un giorno tipico. Quali
sorgenti aggiungeresti, e — più importante — come stabiliresti *prima* di integrarle se
aumenterebbero davvero il segnale invece del solo volume?

**(g) La domanda scomoda.** Sulla base di quanto sopra: c'è una ragione teorica per aspettarsi alpha
da sentiment su news editoriale riguardo a 96 large-cap USA, i titoli più coperti e più arbitraggiati
del mondo? Se la risposta è no, dillo. Preferisco una risposta negativa argomentata a una lista di
migliorie su una premessa sbagliata.

## 6. Come voglio la risposta

- **Ogni proposta con un test associato**: cosa misureresti, su quale campione, e quale risultato la
  falsificherebbe. Una proposta non falsificabile non mi serve.
- **Confrontati con il vincolo di potenza.** Con 34 giorni rileviamo solo |IC| > 0,072. Se una tua
  proposta richiede più campione di quello che abbiamo, dimmi quanto ne serve.
- **Ordina per rapporto (valore atteso)/(costo del test)**, non per interesse intellettuale.
- **Dichiara le tue incertezze.** Se citi un risultato di letteratura, indica su quale universo e
  periodo è stato stabilito, e se è sopravvissuto a repliche recenti. Molti effetti documentati prima
  del 2010 sono decaduti.
- Se pensi che qualcuno dei nostri vincoli sia sbagliato o auto-inflitto, dillo.

---

## Avvertenza sulla documentazione

Questo repo ha una storia documentata di **divergenza fra documentazione e codice**. Verificando gli
allegati il 2026-08-03 ho trovato che la tabella dei parametri di S4 in `docs/strategies.md`
elencava quattro campi di cui **nessuno esisteva nel codice**, e uno dichiarava una scadenza segnale
di 30 minuti contro le 4 ore reali. È stata corretta, ma la lezione vale in generale:

**Dove documentazione e codice si contraddicono, il codice ha ragione.** Se noti un'incoerenza,
segnalala: è essa stessa un finding utile.

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
9. `docs/strategies.md` §S4 — parametri verificati contro il codice il 2026-08-03
7. `src/strategies/s4/` e `src/workers/sentiment.py` — il codice della strategia e dello scoring.
   **Autorevole in caso di conflitto con la documentazione.**
8. `config/trading.yaml` — watchlist, soglie, parametri di rischio
