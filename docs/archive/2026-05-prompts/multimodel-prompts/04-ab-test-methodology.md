# Prompt 4 — Metodologia A/B Test: Sentiment LLM vs No-Sentiment

## Contesto del sistema

Sistema di trading algoritmico che usa segnali di sentiment LLM come feature aggiuntiva su strategie su QuantConnect Lean. Prima di passare dalla Fase 1 (backtest) alla Fase 2 (paper trading con tutti e 3 i worker LLM), dobbiamo dimostrare che il sentiment LLM aggiunge **alpha misurabile** rispetto alla stessa strategia senza sentiment.

**Strategia base (intraday 1h):**
- Entry: momentum confermato + `sentiment_score > 0.3`
- Exit: stop-loss 2% o target momentum
- Universo: multi-asset (equity USA, ETF, alcuni crypto)

**Strategia controllo (A/B baseline):**
- Identica alla base ma **senza** la condizione `sentiment_score > 0.3`
- Entry: solo momentum confermato

**Segnale LLM:**
- `score = polarity × confidence` ∈ [-1.0, +1.0]
- Aggiornato ogni 15 minuti
- Derivato da notizie finanziarie via DK-CoT prompt

**Dati disponibili per backtest:**
- Dati OHLCV storici su QuantConnect (equity USA 2018–2024, crypto 2020–2024)
- Segnali LLM pre-computati su dati storici (generati offline applicando il Sentiment Worker a news archive)

---

## Il tuo compito

Sei un quantitative researcher con esperienza in financial machine learning e test statistici su serie temporali finanziarie. Progetta un A/B test rigoroso per questo contesto.

### Parte A — Sfide specifiche dei dati finanziari

Prima di progettare il test, analizza le seguenti sfide e come andrebbero gestite:

1. **Autocorrelazione temporale:** i rendimenti giornalieri/orari sono autocorrelati. Come impatta questo sulla stima della dimensione campionaria e sul test statistico?
2. **Non-stazionarietà:** il mercato cambia regime (bull/bear/sideways). Come evitare che il test misuri solo la performance in un regime favorevole?
3. **Data snooping bias:** se usiamo gli stessi dati per ottimizzare il prompt LLM e per fare il backtest, i risultati sono validi?
4. **Overfitting del segnale LLM:** il Sentiment Worker è stato calibrato (soglia 0.3) su dati storici — questo introduce look-ahead bias nel test?

### Parte B — Design del test

Proponi il design completo dell'A/B test:

1. **Periodo dati:** quale split train/validation/test usi? Perché?
2. **Universo asset:** quali asset includere per massimizzare generalizzabilità?
3. **Metrica primaria:** quale metrica usi come primary outcome? (Sharpe Ratio? Alpha vs benchmark? Information Ratio? Calmar?)
4. **Metriche secondarie:** quali metriche aggiuntive osservi?
5. **Test statistico:** quale test usi per valutare la significatività? (t-test? Bootstrap? Permutation test?) Perché quello e non altri?
6. **Livello di significatività:** α = 0.05? 0.01? Motivazione nel contesto finanziario
7. **Dimensione campionaria:** quanti trade o quanti giorni di backtest sono necessari per avere potere statistico sufficiente?

### Parte C — Walk-forward validation

Descrivi come struttureresti una walk-forward analysis:

1. Lunghezza della finestra di training (in-sample)
2. Lunghezza della finestra di test (out-of-sample)
3. Passo di avanzamento (rolling vs expanding window)
4. Come aggregare i risultati delle multiple finestre in un unico giudizio

### Parte D — Soglia di decisione

Definisci la soglia quantitativa per decidere "il sentiment LLM aggiunge valore":

1. Qual è il delta Sharpe minimo statisticamente significativo E economicamente rilevante?
2. Come consideri i costi del sistema LLM ($200-600/mese) nel calcolo del net alpha?
3. Cosa succede se il test è inconclusivo (delta Sharpe positivo ma non significativo)?
4. Disegna la matrice decisionale: (significativo/non, positivo/negativo) → azione

### Parte E — Validazione del segnale stesso

Oltre al backtest integrato, come valuteresti il segnale LLM come predittore in isolamento?

1. Come misureresti l'Information Coefficient (IC) del sentiment score?
2. Come costruiresti un portfolio "pure sentiment" per isolare il contributo del segnale?
3. Quali baseline alternative al sentiment LLM testeresti? (es. FinBERT, bag-of-words, headline count)

---

## Formato risposta atteso

1. Analisi sfide dati finanziari con soluzioni concrete (Parte A)
2. Design test completo con motivazioni (Parte B) — includi pseudo-codice per il test statistico
3. Schema walk-forward con parametri consigliati (Parte C)
4. Soglia decisionale e matrice 2×2 (Parte D)
5. Framework valutazione segnale isolato (Parte E)
6. **Stima realistica:** con un backtest di 2 anni (2022-2024), quanti trade genererebbe la strategia 1h multi-asset? È sufficiente per conclusioni statisticamente valide?
