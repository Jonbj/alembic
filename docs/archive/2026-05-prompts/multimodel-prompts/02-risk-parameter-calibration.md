# Prompt 2 — Calibrazione Parametri di Rischio

## Contesto del sistema

Sistema di trading algoritmico multi-asset basato su segnali LLM. Caratteristiche operative:

- **Mercati:** equity USA/EU, ETF, crypto, futures, forex (tramite QuantConnect Lean)
- **Strategie attive:**
  - *Intraday 1h*: momentum + sentiment score. Entry quando `sentiment_score > 0.3` e momentum confermato
  - *Swing 4h–1D*: regime-aware positioning. Size = `base_size × regime_multiplier`
- **Regime multiplier:** risk_on=1.0, trending=0.8, ranging=0.6, high_vol=0.5, risk_off=0.3, uncertain=0.3
- **Segnali:** sentiment score `[-1.0, +1.0]` aggiornato ogni 15 minuti, regime aggiornato ogni ora
- **Broker target Fase 1-2:** Interactive Brokers o Alpaca (equity + ETF), Binance (crypto)
- **Portafoglio target:** dimensione non specificata (sistema deve funzionare da $10k a $500k)

## Parametri di rischio attuali nella spec

```
Stop-loss intraday (1h):     2% per trade
Stop-loss swing (4h–1D):     5% per trade
Daily drawdown → pausa:      5%
Daily drawdown → stop:       10%
Max posizione singola:       10% del portafoglio
Max ordini/minuto:           10
Sentiment entry threshold:   score > 0.3
Score estremo |score|>0.8:   approvazione manuale (semi-auto) / size ×0.5 (full-auto)
```

---

## Il tuo compito

Sei un quant risk manager con esperienza in sistemi di trading automatici multi-asset. Valuta i parametri sopra e rispondi alle seguenti domande:

### Parte A — Validazione parametri attuali

Per ogni parametro:
1. Il valore è ragionevole per il contesto descritto?
2. Quali sono i rischi di avere questo valore **troppo stretto** (es. stop-loss 2% troppo vicino)?
3. Quali sono i rischi di avere questo valore **troppo largo**?
4. Hai un suggerimento di valore alternativo o range consigliato basato su letteratura o pratica?

Rispondi in forma tabellare:

| Parametro | Valore attuale | Valutazione | Range consigliato | Motivazione |
|---|---|---|---|---|

### Parte B — Parametri mancanti

Identifica i parametri di rischio assenti dalla spec che consideri **essenziali** per un sistema in produzione. Per ognuno:
- Nome del parametro
- Valore iniziale consigliato
- Impatto operativo se assente

Considera almeno:
- Gross exposure limit (esposizione totale long + short)
- Correlation limit (max N posizioni correlate nello stesso settore)
- Maximum single-day loss assoluto (in $, non solo %)
- Overnight exposure limit (posizioni swing aperte over-weekend)
- Volatility-adjusted position sizing (es. targeting volatilità costante)
- Slippage model appropriato per equity 1h e swing

### Parte C — Interazione tra parametri

Analizza le seguenti interazioni critiche:

1. Con regime `high_vol` (multiplier=0.5) e stop-loss fisso al 2%: il sistema si comporta correttamente in alta volatilità? Un ATR-based stop sarebbe più appropriato?

2. Con 10 posizioni al 10% ciascuna (gross 100%): se tutte sono long su tech stocks correlate, cosa succede durante un sell-off settoriale? Come si protegge il portafoglio?

3. Il daily drawdown al 10% + max posizione al 10%: teoricamente il sistema potrebbe aprire 10 posizioni che scendono tutte del 10% → perdita del 10% del portafoglio in un giorno. È questo il comportamento desiderato?

### Parte D — Parametri per Fase 1 (backtest) vs Fase 3 (live)

Proponi due set di parametri:
- **Conservativo** (Fase 1-2, backtest + paper trading): ottimizzato per preservare capitale e raccogliere dati
- **Operativo** (Fase 3+, semi-auto live): bilanciato tra protezione e cattura di alpha

---

## Formato risposta atteso

1. Tabella validazione parametri attuali (Parte A)
2. Lista parametri mancanti con valori iniziali (Parte B)
3. Analisi interazioni (Parte C) — max 300 parole per punto
4. Due set di parametri (Parte D) in formato configurazione YAML
5. **Top 3 rischi** che i parametri attuali non coprono adeguatamente
