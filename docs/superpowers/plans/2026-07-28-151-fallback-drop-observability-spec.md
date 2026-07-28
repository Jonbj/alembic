# Spec — #151: rendere visibile lo scarto dei segnali solo-fallback

Part of #21 · Issue: #151 · Branch: `fix/151-fallback-drop-observability`

## Contesto

`_filter_fallback_signals` (`src/workers/portfolio_scheduler.py:761`) esclude i segnali
single-model-fallback dal ranking BUY (#108, lezione SPCX). **La policy è corretta e non si
tocca.** Il problema è che lo scarto fa solo `log.info`, mentre i due meccanismi gemelli nella
stessa funzione scrivono una riga in `execution_decisions`.

Conseguenza: per un simbolo il cui **unico** segnale del giorno è fallback, non esiste riga in
nessuna tabella che dica "notizia vista, segnale calcolato, scartato per bassa affidabilità" —
è indistinguibile da NO_NEWS. Casi reali: ERIC e AMAT il 2026-07-27
(`docs/ALPHA_MISS_REPORT_2026-07-27.md` §7).

### Correzione al report — leggila prima di ragionare sul meccanismo

Il §7 ipotizza che il fallback venga trattato diversamente *"quando il calcolo ensemble non
produce affatto un risultato per un simbolo"*. **È falso.** `_filter_fallback_signals` scarta
**ogni** segnale fallback, sempre, senza guardare cos'altro esista per quel simbolo.

AMD risultava visibile non perché il suo fallback sia stato trattato diversamente, ma perché le
sue letture *ensemble* raggiungevano il log come `SKIP_THRESHOLD`. ERIC e AMAT non ne avevano
nessuna. **L'invisibilità dipende dal simbolo non avere nient'altro, non dal trattamento del
fallback.** È il motivo per cui lo scope qui sotto è ristretto ai soli simboli senza segnale
valido: non è una scelta di volume, è la definizione esatta del buco.

## Decisioni già prese — non riaprirle

Sono l'esito di una sessione di grilling sui dati misurati, non preferenze.

| Decisione | Esito | Motivo |
|---|---|---|
| **Volume** | dedup su `symbol + generated_at` | senza dedup, con il portfolio-cycle ogni 15 min, si arriva a ~980 righe/giorno nei giorni di fallback alto — cinque volte l'attuale tipo dominante, su un evento che non genera trade |
| **Scope** | solo simboli **senza** alcun segnale non-fallback nel batch del ciclo | è il buco reale (vedi correzione sopra). Sul 07-27: 10 simboli su 46, non 30 |
| **Stringa** | riusa **`SKIP_FALLBACK`** | la UI è già cablata: `DECISION_LABELS` in `frontend/src/pages/News.tsx`, contatore in `Overview.tsx`, testo di aiuto che già lo promette all'operatore. Zero modifiche frontend |
| **Redis giù** | fail-open (logga comunque) | stesso ragionamento di `_record_stale_drops`: una riga duplicata è meno grave di un buco invisibile |
| **Chiave dedup** | **separata** da `s4:logged_stale_signals` | semantiche diverse; condividere il set farebbe sopprimere a vicenda i due meccanismi |

Nota su `SKIP_FALLBACK`: esiste già in `src/workers/execution.py:648`, ma è il path **legacy**
(`execution.engine=legacy_sentiment`, non attivo) e in DB non c'è mai stata una riga. Non c'è
collisione pratica.

## Dati misurati (per calibrare, non da ri-misurare)

```
execution_decisions, ultimi 14 giorni:
  SKIP_THRESHOLD  1447 righe  (206.7/giorno)  <- nessun dedup, una riga per ciclo
  BUY              115        (11.5/giorno)
  SELL              77         (7.7/giorno)
  SKIP_STALE         0                        <- dedup + filtro materialità; inattivo, non rotto

tasso fallback (7 giorni): bimodale — 0%, 0.5%, 0.5%, 36.1%, 48.3%
simboli con SOLO fallback: 10 su 46 (07-27), 15 su 54 (07-21)
```

## Implementazione

Al call site (`portfolio_scheduler.py:3106`), dopo il filtro, l'informazione è già disponibile —
nessuna query aggiuntiva:

```python
signals, _fb_dropped = _filter_fallback_signals(signals)
kept = {s.symbol for s in signals}
only_fallback = [s for s in _fb_dropped if s.symbol not in kept]
```

Aggiungi `_record_fallback_drops(only_fallback)` modellata su `_record_stale_drops`
(`portfolio_scheduler.py:2936` e dintorni): stessa struttura, stesso stile di fail-safe, stessa
meccanica di set Redis con TTL rinfrescato a ogni scrittura (`sadd` + `expire`).

Requisiti della riga scritta:
- `decision="SKIP_FALLBACK"`
- `reason` deve contenere `model_id`, score e confidence del segnale scartato, **e** il fatto che
  per quel simbolo non esisteva alcun segnale ensemble nel ciclo. È l'informazione la cui assenza
  ha reso necessaria l'archeologia manuale su ERIC/AMAT.
- `signal_score` valorizzato come negli altri due meccanismi.

## Fuori scope

- Non toccare `_filter_fallback_signals` né la policy di esclusione dal ranking (#108).
- Nessuna modifica al frontend: la stringa scelta è quella che la UI già gestisce. Se scopri che
  non è vero, **fermati e segnalalo** invece di modificare il frontend.
- Nessuna migration: `decision` è `varchar(20)`, `SKIP_FALLBACK` sono 13 caratteri.
- Non toccare `_record_stale_drops` né `_record_gate_drops`.

## Cerca i consumatori anche in `docs/`

**Lezione da #138.** Se il tuo intervento cambia una risposta API, un formato serializzato, uno
schema o un contratto osservabile dall'esterno, la ricerca dei consumatori deve includere `docs/`
(in particolare `API.md`, `ARCHITECTURE.md`, `operations.md`), `README.md`, `CONTEXT.md` e le
pagine di testo del frontend. Se trovi una descrizione diventata falsa, correggila nello stesso
branch. Se non cambi nulla di osservabile, scrivi una riga nella PR che lo dichiara — serve a far
vedere che il controllo è stato fatto, non saltato.

Qui è probabile che vada aggiornata la documentazione del Decision Log dove elenca i tipi di
decision: verificalo.

## Metodo

TDD. Test richiesti, prima dell'implementazione:

1. **Il caso ERIC/AMAT**: un simbolo il cui unico segnale è fallback → viene scritta una riga
   `SKIP_FALLBACK`.
2. **Il caso AMD**: un simbolo con un segnale fallback **e** uno ensemble → **nessuna** riga
   (il segnale valido è già tracciato altrove). Questo test è il cuore dello scope: deve fallire
   se qualcuno allarga il filtro a tutti i drop.
3. **Idempotenza**: due cicli consecutivi sullo stesso segnale → **una sola** riga. Deve fallire
   se il dedup viene rimosso.
4. **Fail-open**: con Redis irraggiungibile la riga viene scritta comunque e il ciclo non si
   rompe.
5. **Chiave separata**: una registrazione fallback non deve sopprimere una registrazione stale
   per lo stesso `symbol+generated_at`, né viceversa.

## Criteri di accettazione

- I cinque test verdi.
- Suite completa senza regressioni. Nota i due rossi **pre-esistenti e non tuoi**:
  `test_get_s1_backtest_returns_equity_curve` (#152, dipende da `reports/` gitignorato) e i test
  in `tests/store/test_pg_store_stop_methods.py` se non hai un `DATABASE_URL` raggiungibile.
- Nessuna modifica al frontend nel diff.

## Nota di metodo

Se un test pre-esistente diventa rosso, la prima domanda è *"la mia modifica è sbagliata?"*, non
*"il test è troppo stretto?"*. Se concludi che il test va cambiato, difendine il merito nel
report prima di toccarlo.

## Consegna

Branch `fix/151-fallback-drop-observability`, un commit, PR con `closes #151`.
**Non mergiare e non deployare**: review e merge li faccio io.
