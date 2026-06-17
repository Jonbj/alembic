# Prompt per Review con Claude Code — GKG Historical Backtest

Copia questo testo intero in una nuova sessione Claude Code per eseguire la review completa.

---

```
Esegui una review completa del commit `8fb2932` su `main` per la feature
"GKG Historical Backtest Pipeline". Segui esattamente le istruzioni
qui sotto.

## 1. SKILL DA INVOCARE — in questo ordine

1. `superpowers:verification-before-completion` — per verificare che tutti i
   test passino e non ci siano regressioni prima di qualsiasi giudizio.
2. `superpowers:requesting-code-review` — per strutturare la review secondo
   gli standard del progetto.

## 2. FILE DA LEGGERE PRIMA DI INIZIARE

Leggi nell'ordine:
1. `CLAUDE.md` — vincoli architetturali NON negoziabili
2. `docs/superpowers/specs/2026-05-13-gkg-backtest-design.md`
3. `docs/superpowers/plans/2026-05-13-gkg-backtest.md`
4. `docs/superpowers/reviews/2026-05-13-gkg-backtest-review-instructions.md`
   — istruzioni dettagliate con checklist per ogni file

## 3. COMANDI DA ESEGUIRE

```bash
# Verifica suite completa
pytest --tb=short -q
# Atteso: 489 passed

# Verifica componenti specifici
pytest tests/connectors/test_gdelt_gkg.py -v
pytest tests/workers/test_sentiment_worker.py -v
pytest tests/backtest/test_forward_returns.py -v
pytest tests/backtest/test_backtest_report.py -v
pytest tests/backtest/test_backtest_runner.py -v

# Verifica DB migration
python -c "
import psycopg2, os
os.environ['DATABASE_URL'] = 'postgresql://trading:trading@localhost:5432/trading'
c = psycopg2.connect(os.environ['DATABASE_URL'])
cur = c.cursor()
cur.execute(\"SELECT column_name FROM information_schema.columns WHERE table_name = 'backtest_signals' ORDER BY ordinal_position\")
print('Columns:', [r[0] for r in cur.fetchall()])
c.close()
"
```

## 4. FILE DA CONTROLLARE — checklist

### Nuovi file
- `migrations/005_add_backtest_signals.sql` — DDL tabella
- `src/backtest/__init__.py` — package scaffold
- `src/backtest/forward_returns.py` — ForwardReturnCalculator
- `src/backtest/report.py` — BacktestReportBuilder
- `scripts/run_backtest.py` — CLI 4-phase runner
- `tests/backtest/__init__.py` — package scaffold
- `tests/backtest/test_forward_returns.py` — 8 test
- `tests/backtest/test_backtest_report.py` — 5 test
- `tests/backtest/test_backtest_runner.py` — 4 test

### Modificati
- `src/connectors/gdelt_gkg.py` — aggiunto `fetch_historical()`
- `src/workers/sentiment.py` — estratto `run_inference()`
- `tests/connectors/test_gdelt_gkg.py` — 4 test fetch_historical
- `tests/workers/test_sentiment_worker.py` — 4 test run_inference

## 5. VINCOLI ARCHITETTURALI DA VERIFICARE

- [ ] Zero chiamate LLM sincrone nel loop di trading
- [ ] Nessuna chiamata bloccante in next() di Backtrader o confirm_trade_entry() di Freqtrade
- [ ] SQL parametrizzato: zero f-string o concatenazione nelle query
- [ ] run_inference NON tocca Redis/PostgreSQL (side-effect-free)
- [ ] process_news_item delega a run_inference + store writes (wrapper sottile)
- [ ] Nessuna interpolazione prezzi: None su barra mancante
- [ ] Checkpoint/resume: phase2_infer salta score IS NOT NULL
- [ ] GDELTConnector esistente non rotto (test passano)

## 6. OUTPUT RICHIESTO

Scrivi un report in questo formato esatto:

```markdown
# Review Report — GKG Historical Backtest Pipeline

**Reviewer:** <nome modello>
**Data:** <data>
**Commit:** 8fb2932

## Verdict
- [ ] APPROVED
- [ ] APPROVED with minor notes
- [ ] CHANGES REQUESTED

## Checklist risultati
- [ ] Tutti i test passano (489/489)
- [ ] Nessuna violazione dei vincoli architetturali
- [ ] Nessun problema di sicurezza rilevato
- [ ] Codice leggibile e ben commentato

## Test eseguiti
<Sommario dei test run e risultati>

## File-by-file notes
<Per ogni file controllato, una riga con stato: OK / NOTE / ISSUE>

## Issue dettagliate (se presenti)
<File:line_number — descrizione del problema — severità>
```

NON approvare se:
- Un qualsiasi test fallisce
- Un vincolo architetturale è violato
- Trovi SQL injection, XSS, o altre vulnerabilità OWASP top 10
- run_inference scrive direttamente su store
- Ci sono import circolari o dipendenze mancanti

Se trovi un problema, descrivilo con precisione (file:line_number) e
richiedi CHANGES REQUESTED. Non correggere autonomamente.
```

---

**Come usarlo:**
1. Apri una nuova sessione Claude Code nel repository.
2. Incolla l'intero blocco qui sopra (dalle triple-backtick in poi).
3. Attendi che Claude invochi le skill e completi la review.
