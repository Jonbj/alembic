# Preregistrazione #468 — drift del SELL S1 differito

Data di registrazione: 2026-09-10, prima dell'esecuzione dello script
`scripts/measure_s1_rebalance_atomicity.py` e della scrittura dell'artefatto.

## Domanda

Quanto cambia il prezzo dei simboli che S1 porta a peso zero fra il ciclo in
cui il nuovo target viene deciso e il ciclo successivo in cui l'isteresi di
uscita lascia passare il SELL?

## Campione congelato

Tutti i `execution_decisions` eseguiti (`order_id IS NOT NULL`) con
`exit_mechanism = 's1_weight_drop'` dal 2026-08-07T14:07:00Z, primo ciclo del
regime col clock mensile #185, fino all'istante di esecuzione. Non si selezionano
simboli o sedute in base al risultato.

Le righe storiche precedono la telemetria #468. Per ciascun SELL, il ciclo di
decisione è quindi il `portfolio_cycles` immediatamente precedente al ciclo del
SELL, ammesso soltanto quando la distanza è compresa fra 10 e 20 minuti. Questa
è la materializzazione storica della regola di produzione
`execution.exit_persistence_cycles = 2`, letta dallo script tramite
`_get_exit_persistence_cycles()`: il primo candidato è soppresso e il secondo è
eseguito. Lo script rifiuta di produrre il report se il helper restituisce un
valore diverso. Gap più lunghi e run manuali ravvicinati sono esclusi.

## Prezzo e calcolo congelati

Fonte prezzi: barre Alpaca IEX `TimeFrame.Minute`, `Adjustment.ALL`. A ogni
timestamp si prende il close dell'ultima barra minuto **completa**, con timestamp
strettamente precedente al minuto del ciclo e staleness massima di cinque
minuti. Non si usa la barra ancora aperta, per evitare look-ahead.

Per ogni simbolo:

```text
drift_pct = prezzo_pre_SELL / prezzo_pre_decisione - 1
drift_usd = quantita_venduta * (prezzo_pre_SELL - prezzo_pre_decisione)
```

Il segno è dal punto di vista del venditore: positivo significa che il rinvio ha
ottenuto un prezzo di riferimento più alto, negativo che è costato. Si riportano
ogni simbolo, il totale firmato, i mancanti e la sintesi per ribilanciamento.

## Esito ammesso

La misura è descrittiva: non ha una soglia di promozione e non autorizza alcun
cambio di `exit_persistence_cycles`, ordine SELL/BUY, frequenza, peso o altra
taratura durante il freeze #171. Il valore può essere favorevole, sfavorevole o
incompleto; i prezzi mancanti restano `missing_price` e non vengono imputati.
