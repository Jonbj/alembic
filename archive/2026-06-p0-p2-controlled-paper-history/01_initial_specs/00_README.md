# Alembic — Sistema quant multi-strategia

**Versione documento**: 2.0 (riscrittura completa)
**Data**: 22 maggio 2026
**Audience**: developer agent + sviluppatore singolo
**Cosa sostituisce**: i documenti v1 (focus wealth manager / SaaS)

---

## TL;DR

Alembic viene riposizionato da "robo-advisor LLM-driven" a **sistema quant multi-strategia personale**, costruito sul codice esistente, con questi obiettivi:

- **Edge reale e difendibile**: combinazione di 3 strategie nel portfolio live (S1+S2+S4) + 1 R&D sleeve (S3, gate run completato ma demoted), ognuna con base accademica solida e implementazione rigorosa
- **Riuso massivo del codice esistente** (LLM ensemble, regime classifier, drift detection, risk monitor, Celery infra)
- **Capacity adeguata a capitale singolo**: nessun vincolo di scala, funziona da 10k a 5M
- **Sharpe target combinato OOS**: 1.0-1.5 (vs 0.5-0.6 di un 60/40 buy-and-hold)
- **Drawdown atteso**: 12-18%
- **Effort totale**: ~10 mesi part-time (15-20 ore/settimana)

---

## Il principio centrale

> **Nessuna strategia singola è l'edge. L'edge è la combinazione disciplinata di strategie note, replicate correttamente da letteratura, con risk management rigoroso.**

I retail quant falliscono per due ragioni principali:
1. Cercano "un'idea segreta" invece di implementare bene idee pubbliche
2. Concentrano su una singola strategia che decade

Alembic v2 prende l'approccio dei CTA professionali (AQR, Man AHL, Winton): **portfolio of low-correlation strategies**, ciascuna con Sharpe modesto, combinate per Sharpe alto.

---

## Le 4 strategie

| ID | Nome | Edge atteso (Sharpe OOS) | Allocazione target | Maturità accademica |
|----|------|--------------------------|--------------------| ---------------------|
| S1 | Time-series momentum multi-asset | 0.6-0.8 | 40% | Altissima |
| S2 | Volatility risk premium harvesting | 0.8-1.2 | 30% | Altissima |
| S3 | Cross-sectional momentum equity | 0.5-0.7 | **0% live (R&D)** ⚠️ R&D sleeve — gate 3&5 FAIL, OOS Sharpe 0.15, esclusa dal live | Altissima |
| S4 | News-driven tactical (refactor) | 0.0-0.5 | 10% | Bassa (R&D) |

Dettagli in `01_strategy_design.md`.

---

## Mappa documenti

| File | Contenuto | Quando leggerlo |
|------|-----------|-----------------|
| `00_README.md` | Questo file | Sempre per primo |
| `01_strategy_design.md` | Le 4 strategie, letteratura, parametri, expected edge | Prima di implementare ogni strategia |
| `02_architecture.md` | Architettura multi-strategia, riuso del codice esistente, contratti | All'inizio + quando aggiungi strategie |
| `03_backtest_framework.md` | Backtest engine specifications, cost model, portfolio combiner | Prima di costruire il backtest |
| `04_roadmap.md` | Task atomici con priorità, effort, dipendenze | Per la pianificazione |
| `05_validation_and_gates.md` | Walk-forward, decay monitoring, go-live criteria | Quando ogni strategia è pronta |

---

## Cosa cambia rispetto ai doc v1

I documenti v1 erano scritti per un framing **wealth manager / SaaS** che è stato accantonato. Buona parte di quel contenuto resta utile come reference futuro, ma **non è il piano operativo attuale**.

Cosa **muore** dei doc v1:
- Asset allocation strategica con CMA engine
- Black-Litterman per integrare views macro
- Tax engine italiano completo (rimanda)
- Client profile management
- Reporting LLM per cliente
- Tutto il framing "sostituisci consulente Fineco"

Cosa **sopravvive** in forma rivista:
- Rigore statistico (multiple testing, walk-forward, DSR)
- Architettura modulare a contratti
- Anti-look-ahead enforcement
- Decay study come pratica continuativa
- Risk monitor always-on
- Observability e monitoring

Cosa è **nuovo**:
- Strategy-per-modulo architecture
- Portfolio combiner cross-strategy
- Options integration (per Strategia 2)
- Multi-asset universe (15+ ETF cross-asset)
- Cost model serio inclusi opzioni

---

## Stack tecnico

Resta quello che hai, con aggiunte:

**Già presente**:
- Python 3.11+
- PostgreSQL + Redis
- Celery
- Alpaca SDK (mantenuto per equity US paper)
- LLM ensemble (GLM, Qwen, Kimi, DeepSeek)
- Statistical framework (PSI, CUSUM, Newey-West HAC)

**Da aggiungere**:
- **IBKR API** (`ib_insync` o `ibapi`): per opzioni in Strategia 2, niente Alpaca per opzioni
- **vectorbt** o **NautilusTrader**: backtest engine event-driven serio
- **PyPortfolioOpt** o **riskfolio-lib**: per portfolio combiner
- **yfinance** + **FRED API** (gratis): data storica per backtest lungo
- **arch**: per modelli vol (GARCH, EWMA) usati in Strategia 2

**Da considerare in seguito**:
- **MLflow**: experiment tracking serio quando avrai 10+ strategy variants
- **Optuna**: hyperparameter tuning (con cautela, vedere docs su overfit)

---

## Filosofia operativa

Sei un developer singolo. Questo ha implicazioni:

1. **Niente over-engineering**. YAGNI rigoroso. Multi-tenancy, microservices, eventi distribuiti: non servono.
2. **Test pesanti su business logic, leggeri su glue code**. Una strategia di trading sbagliata costa soldi. Un endpoint API mal testato no.
3. **Backtest correctness > speed**. Meglio backtest che gira in 1 ora correttamente che 1 minuto con look-ahead.
4. **Config over code**. Strategy parameters in YAML versionati, mai magic numbers.
5. **Paper before live, walk-forward before paper**. Nessuna eccezione.
6. **Una strategia alla volta**. Validi S1, poi S2, poi S4, poi combiner. S3 ha completato il gate run come R&D sleeve (Fase C). Non parallelizzare.

---

## Cosa significa "fatto" per questo progetto

Il progetto è "fatto" quando:

- [ ] S1, S2, S4 implementate e validate OOS individualmente; S3 completata come R&D sleeve con gate run documentato (gate 3&5 FAIL)
- [ ] Portfolio combiner aggrega S1+S2+S4 con risk parity overlay (S3 esclusa come R&D sleeve)
- [ ] Walk-forward sull'intero sistema su 10+ anni storici mostra Sharpe ≥ 1.0 OOS netto costi
- [ ] 90+ giorni paper trading consecutivi senza crash di sistema, con performance entro l'1σ del backtest
- [ ] Decay monitoring attivo su ciascuna strategia
- [ ] Dashboard di monitoring funzionante
- [ ] Documentazione completa per ogni strategia (cosa fa, perché, come monitorarla, quando spegnerla)

Quando questi sono tutti veri, **decidi** se passare a capitale reale (su scala piccola, es. 5-10k iniziali) o se mantenere paper. Quella decisione viene dopo, e non è un obiettivo della roadmap attuale.
