# Prompt per consultazione esterna — redesign dello stop-loss

> Documento da incollare in ChatGPT / altro modello. Autosufficiente.
> Generato 2026-07-11. Contenuto: prompt integrato (dubbi originali + fatti emersi da esplorazione del codice).
> Risposte di ChatGPT hanno informato `docs/superpowers/plans/2026-07-11-stop-loss-redesign.md`.

Sei un quant developer senior. Analizza i dubbi di progettazione qui sotto per un cambiamento
a una regola di stop-loss in un sistema di trading algoritmico live, e dammi risposte
ragionate con raccomandazioni esplicite. Segnala anche quello che non ho chiesto ma dovrei.

# Contesto di sistema
- "Alpha Miner ATS": LLM offline produce segnali di sentiment; il motore di esecuzione
  legge segnali pre-calcolati da Redis/PostgreSQL, mai LLM nel hot path. Broker: Alpaca
  (paper/live via alpaca-py). Stack: FastAPI + Celery + Redis + PostgreSQL.
- Path attivo: execution.engine=portfolio. Un Celery beat lancia run_portfolio_cycle
  ogni 15 min durante le market hours. Strategie multiple (S1 momentum, S4 news-sentiment,
  S2 VRP, S7 PEAD...) producono target weights; un orchestrator fa merge dei pesi,
  applica un vol-targeter e un constraint enforcer, poi il ciclo sottomette ordini.
- Regime multiplier (×0.2–1.0) scala il notionale finale. Stop-loss, drawdown cap,
  kill-switch, feedback ratchet sono i guardrail.

# Il problema concreto (caso reale del 2026-07-10)
- Strategia S1 Time-Series Momentum ha comprato PANW @ $337.52 (notional ~$650,
  regime_mult 0.7). S1 usa momentum vol-normalizzato su lookback 21/63/126/252 giorni
  con pesi esponenziali che favoriscono il 252g. PANW al 10/07: 5d -6.3%, 21d +25.0%,
  63d +95.1%, 126d +68.0%, 252d +58.1%. Quindi S1 ha comprato "forza" correttamente;
  il -6% su 5 giorni è rumore contro un uptrend annuale.
- 30 minuti dopo il prezzo è a $328.01: lo stop-loss al 2% è scattato (soglia
  337.52×0.98=330.77; exit a 328.01 sotto soglia). Perdita net -$19.64 su un notional
  di $650. PANW chiuso la giornata a 325.82 (swing intraday -3.5%, normale per un titolo
  con +95% in 63 giorni).
- Causa diretta: stop-loss 2% fisso, uguale per tutto l'universo, non calibrato sulla
  volatilità del titolo. Per PANW (~2.5-3% vol daily) il 2% è ~0.7σ → scatta su rumore
  fisiologico. Per un titolo a bassa vol lo stesso 2% sarebbe larghissimo.

# Implementazione attuale dello stop (path portfolio) — dettaglio verificato nel codice
- _stop_loss_breached_symbols (portfolio_scheduler.py:536-579): confronto fisso
  `price <= entry * (1 - stop_loss_pct)`, stop_loss_pct=0.02 da config/trading.yaml
  (risk.stop_loss), UNICO per tutto l'universo.
- È uno stop SINTETICO per-ciclo: Alpaca rifiuta le gambe bracket sugli ordini
  notional/fractional (errore 42210000), quindi non c'è stop lato broker sui
  fractionable; ogni ciclo (15 min) si controlla e si forza-close chi è sotto soglia.
- ESISTONO GIÀ DUE PARAMETRI DI STOP INCONGRUENTI:
  (1) risk.stop_loss = 0.02 (trading.yaml) → drive il check sintetico per-ciclo (path portfolio).
  (2) ALPACA_STOP_LOSS_PCT = 0.03 (config.py, env-overridable) → gambo bracket lato broker,
      attivo SOLO sul path whole-share (`not is_fractionable`, portfolio_scheduler.py:2270);
      i fractionable non hanno stop lato broker, solo il check sintetico.
  Quindi oggi 2% (sintetico) e 3% (broker whole-share) coesistono senza allineamento.
- Cooldown: stop_loss_today:{symbol} con TTL fino a mezzanotte UTC blocca il re-BUY
  dello stesso titolo nello stesso giorno. È INTENZIONALE anti-churn, va mantenuto.
- Entry price = avg_entry_price reale blended di Alpaca (fill reale, non prezzo a segnale).
- PATH LEGACY (execution.py, dormant perché engine=portfolio): lo stop è PER-SIMBOLO ma
  per LIQUIDITY TIER, non per vol (cost_model.yaml: tier_a 2% mega-cap, tier_b 3.5%
  large, tier_c 4% mid, tier_d 5% small/illiquid). risk.stop_loss è MORTO nel path legacy
  (legacy usa solo la tier table). C'è quindi già un precedente di "stop per-simbolo",
  ma per tier.

# Loop sistemico in cui si inserisce (importante per le risposte)
Il sistema è bloccato a ~5% deployment (vs ~50% design) da un loop auto-rinforzato:
stop 2% troppo stretto → stop-out frequenti su rumore → perdite registrate →
loss-feedback ratchet alza feedback:entry_threshold (hard gate su ingressi S4) →
meno ingressi → underdeployment. Lo stop è una delle cause. Nota: il ratchet può
solo BLOCCARE nuovi ingressi, non ridurre il rischio di posizioni esistenti.

# Fatti emersi dall'esplorazione del codice (rilevanti per le risposte)
- La vol per-simbolo è calcolabile in una riga da `bars_df` già in scope al call site
  dello stop (300 close daily/simbolo, pct_change() già calcolato): nessuna fetch
  aggiuntiva. Caveat: simboli held non nell'universo delle strategie attive non sono in
  bars_df → serve un fallback.
- Non esiste alcuno script di stop-out analytics. I dati sono in trades.exit_reason
  (via pg_store.fetch_trades), MA il path sintetico NON chiama pg_store.close_trade
  con exit_reason="stop_loss" → è reconcile_trade_fills (performance.py) che assegna
  exit_reason a posteriori. Quindi misurare lo stop-out rate richiede prima di verificare
  come la riconciliazione tagga gli exit sintetici.  [NOTA: verificato FALSO in audit —
  vedi docs/superpowers/plans/2026-07-11-stop-loss-redesign.md §5: exit_reason è scritto
  al submit-time dallo scheduler, non dalla riconciliazione.]
- Test che si rompono cambiando la formula: test_day1_fixes.py:123-183 (8 test pinnavano
  lo scalare 0.02 + la formula entry*(1-0.02)). Nuove chiavi di config passano
  _RISK_BOUNDS (config_routes.py:18-22) senza validazione se non le aggiungo; il cap
  0.10 su stop_loss può confliggere con stop vol-scaled su titoli ad alta vol.

# I miei dubbi (rispondi a ciascuno con raccomandazione + trade-off)

D1. Approccio. Opzioni: (a) stop scalato su vol per-simbolo
    stop_pct(sym)=clamp(k * vol_daily(sym), floor, cap); (b) alzare il % fisso;
    (c) ATR-based stop = entry - k*ATR(14); (d) trailing stop. Io propendo per (a)
    perché reusa le bar già scaricate e risolve il mismatch per-simbolo. Tu cosa
    raccomandi e perché?

D2. Orizzonte dello stop vs orizzonte della strategia. S1 è MONTHLY rebalance
    (posizioni pensate per ~1 mese); S4 è event-driven (orizzonte giorni). Uno stop
    basato sulla vol daily è troppo stretto per una strategia mensile: un movimento
    su 1 mese è ~sqrt(21)*vol_daily. Lo stop dovrebbe scalare con l'orizzonte di
    holding atteso della strategia, non solo col simbolo? Es.
    stop_pct = k * vol_daily(sym) * sqrt(target_holding_days_per_strategia)?
    O è un errore mescolare holding-horizon nel stop? Come si calibra uno stop
    per una strategia momentum mensile vs una event-driven a breve orizzonte?

D3. Per-strategia vs per-simbolo. Il dubbio D2 suggerisce che lo stop debba
    dipendere anche dalla strategia (orizzonte), non solo dal simbolo (vol).
    Come strutturare uno stop che è funzione di (simbolo, strategia) senza
    esplodere la complessità del config? Un default per-strategia con override
    per-simbolo?

D4. Semantica: stop fisso dall'entry vs trailing. Una strategia momentum mensile
    che va +20% e poi torna all'entry non è "fermata" da uno stop fisso dall'entry,
    ma dà back tutto il guadagno. Uno stop trailing lock-i-gains si addice meglio
    al momentum? O il trailing è un cambiamento di semantica troppo grande per ora?
    Si può fare vol-scaled + trailing in due fasi?

D5. Calibrazione numerica (se vol-scaled): finestra di vol (20d vs 63d?),
    annualizzazione (la soglia è un drawdown cumulato dall'entry, non un move
    a 1 giorno: come questo cambia la scelta di k e dell'annualizzazione?),
    valore di k (2σ? 3σ?), floor/cap sane ([2%,15%]? [1%,20%]?). Dammi numeri
    motivati e la formula precisa. Considera che c'è già un cap 0.10 su
    risk.stop_loss e un valore broker-side di 0.03: come si conciliano?

D6. "Measure before enforce". Il progetto ha una disciplina forte: non abilitare
    cambiamenti di scoring/rischio senza misurare prima. Per uno stop-loss questo
    significa implementare dietro flag, misurare su trade storici (ho tabelle
    trades + execution_decisions con entry/exit/pnl) e poi abilitare? Quali metriche
    definiscono "stop ben calibrato": stop-out rate, frazione di stop che sarebbero
    stati profittevoli se non fermati, P&L delta vs stop attuale, drawdown massimo
    per trade? Quale gate di passaggio da 2% a vol-scaled?
    PASSO ZERO OBBLIGATORIO: il path sintetico NON scrive exit_reason="stop_loss"
    nella tabella trades (è reconcile_trade_fills in performance.py a farlo a posteriori)
    → prima di misurare qualunque stop-out rate devo verificare come la
    riconciliazione tagga gli exit sintetici, altrimenti misuro rumore. Serve uno
    script nuovo (pattern read-only/idempotent). Aggiungi questo alla raccomandazione.
    [NOTA: questo passo-zero è risultato già soddisfatto — vedi §5 del plan.]

D7. Effetto sul ratchet e sul loop. Uno stop più largo = meno stop-out ma perdite
    più grandi ad ogni stop. L'effetto netto sul loss-feedback ratchet (che conta
    le perdite) è ambiguo: meglio poche perdite grandi o tante piccole? Come si
    comporta il ratchet con i due regimi? Questo cambia la raccomandazione?

D8. Scope e allineamento dei due parametri. Oggi coesistono risk.stop_loss=0.02
    (check sintetico, fractionable) e ALPACA_STOP_LOSS_PCT=0.03 (gambo broker,
    whole-share solo). Il fix deve allinearli sotto la stessa formula vol-scaled, o
    mantenerli separati con semantiche diverse (es. sintetico = drawdown, broker =
    hard limit)? Cosa comporta l'inconsistenza 2% vs 3% già presente? Inoltre: il
    path legacy ha già uno stop per-tier (2/3.5/4/5%) — il vol-scaled lo sostituisce,
    o la tier table diventa fallback per simboli senza vol sufficiente? Il path
    legacy è dormant: conviene toccarlo ora (per evitare drift futuro) o lasciarlo
    e fissare solo il path portfolio attivo?

D9. Rischio di regressione e rollout. Come si fa il rollout sicuro in paper trading:
    shadow-mode (calcola il nuovo stop senza eseguire, logga cosa avrebbe fermato),
    poi attivo su paper, poi live? Quanto tempo di paper è sufficiente data la
    frequenza 15-min e il basso numero di trade?

# Cosa voglio da te
1. Risposta ragionata + raccomandazione esplicita per D1-D9.
2. Una formula di stop finale proposta (funzione di simbolo e, se raccomandi, strategia)
   con i parametri numerici motivati.
3. Un piano di misura (quali metriche, su quale storico, quale gate) coerente con
   la disciplina "measure before enforce", incluso il passo zero di verifica del
   tagging di exit_reason in reconcile_trade_fills.
4. Flagga qualsiasi cosa io non abbia chiesto e dovrei (es. gap risk, slippage
   nello stop sintetico per-ciclo, interazione con sentiment-reversal exit,
   survivorship bias nella misurazione, survivorship dei titoli ad alta vol
   nell'universo, ecc.).
Sii critico: se una mia opzione preferita ha un buco, dillo apertamente.