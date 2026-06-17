# Prompt 6 — Review Schema PostgreSQL: Signals + Audit Log

## Contesto del sistema

Sistema di trading algoritmico. PostgreSQL è il **cold storage / audit trail** del sistema. Redis è la hot cache con TTL (4h per sentiment, 2h per regime). Ogni segnale generato dai worker LLM viene scritto sia su Redis che su PostgreSQL.

**Query workload atteso:**
- **Backtest:** query su range di date per simbolo specifico — alta frequenza, lettura massiva
- **Debug post-mortem:** join tra segnali e ordini per ricostruire le decisioni del sistema
- **Monitoring:** aggregazioni periodiche (es. media confidence per worker, conteggio fallback FinBERT)
- **A/B test analysis:** confronto performance tra periodi con/senza sentiment
- **Audit compliance:** tutte le azioni del sistema con chi le ha approvate

**Schema corrente nella spec:**

```sql
-- Tabella segnali
CREATE TABLE signals (
    id                  UUID PRIMARY KEY,
    symbol              VARCHAR(20),
    timestamp           TIMESTAMPTZ NOT NULL,
    sentiment_score     FLOAT,
    confidence          FLOAT,
    regime_label        VARCHAR(20),
    position_multiplier FLOAT,
    source_ids          TEXT[],
    reasoning           TEXT,
    worker_version      VARCHAR(20),
    model_id            VARCHAR(50)
);
-- Nota spec: "Indici su (symbol, timestamp) per query backtest"

-- Tabella audit
CREATE TABLE audit_log (
    id            UUID PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL,
    action        VARCHAR(50),     -- 'order_placed', 'order_rejected', 'mode_changed',
                                   -- 'killswitch', 'extreme_score_approval', ecc.
    symbol        VARCHAR(20),
    quantity      FLOAT,
    price         FLOAT,
    signal_score  FLOAT,
    signal_id     UUID REFERENCES signals(id),
    guardrail     VARCHAR(50),     -- quale regola ha scattato
    approved_by   VARCHAR(50),     -- 'auto' | 'telegram:user_id'
    reason        TEXT
);
```

**Volumi attesi:**
- Sentiment Worker: ogni 15 min × ~50 simboli attivi = ~200 segnali/ora → ~4.800 segnali/giorno
- Regime: 1 record/ora = 24 record/giorno
- Audit log: dipende dall'attività di trading, stimato 100-500 record/giorno in operatività
- Retention: minimo 5 anni di dati storici per backtest (operativo, non archivio)

**Caratteristiche operazionali:**
- Scritture: bulk insert ogni 15 min (batch di ~50 segnali simultanei dal SentimentWorker)
- Letture backtest: range query su anni di dati, lette sequenzialmente in QC
- Deployment target: PostgreSQL 15+ su singolo server (no cluster in Fase 1-2)

---

## Il tuo compito

Sei un database architect con esperienza in sistemi time-series su PostgreSQL e in sistemi finanziari. Analizza lo schema corrente e rispondi.

### Parte A — Valutazione schema corrente

1. **Problemi strutturali nella tabella `signals`:**
   - Il campo `signals` mescola dati di sentiment (`sentiment_score`, `confidence`) e di regime (`regime_label`, `position_multiplier`). È corretto? Oppure questi dovrebbero essere in tabelle separate?
   - `source_ids TEXT[]` — è il tipo giusto per un array di UUID/string? Quali sono i pro/contro rispetto a una tabella relazionale separata `signal_sources`?
   - `reasoning TEXT` — potenzialmente molto grande. Impatto su storage e query performance?
   - Mancano campi? (es. `polarity` e `confidence` separati oltre allo `score`? `worker_type`? `fallback_used`?)

2. **Problemi strutturali nella tabella `audit_log`:**
   - `signal_id UUID REFERENCES signals(id)` — cosa succede se un audit event non è associato a un segnale? (es. kill-switch manuale, mode change). La FK deve essere nullable?
   - `action VARCHAR(50)` — è meglio un VARCHAR libero o un tipo ENUM/dominio PostgreSQL?
   - Mancano campi critici per il debug post-mortem?

3. **Tipo di dati per `symbol`:** `VARCHAR(20)` copre tutti i casi? (es. `BTC-USD`, `EUR/USD`, `ES=F` per futures, tickers europei come `ENEL.MI`)

### Parte B — Strategia di indicizzazione

Lo schema attuale ha solo il commento "Indici su (symbol, timestamp)". Progetta la strategia completa:

1. **Per `signals`:**
   - Quali indici creare? (btree, hash, BRIN per time-series, GIN per TEXT[]?)
   - Ordine delle colonne negli indici compositi (es. `(symbol, timestamp)` vs `(timestamp, symbol)`)
   - Index su `model_id` e `worker_version` per query di debug — necessari o eccessivi?
   - Partial index su `confidence < 0.4` (segnali scartati) — ha senso?

2. **Per `audit_log`:**
   - Query tipica: "tutti gli ordini per simbolo X nel giorno Y con il segnale associato" — quale indice serve?
   - Query tipica: "tutti i kill-switch delle ultime 24h" — quale indice?

3. **Considera TimescaleDB:** vale la pena usarlo al posto di PostgreSQL nativo per una tabella `signals` che è essenzialmente una time-series? Pro/contro nel contesto di questo sistema.

### Parte C — Schema migliorato

Proponi lo schema SQL completo migliorato. Includi:

1. Definizione completa delle tabelle con tutti i campi che aggiungeresti/modificheresti
2. Tutti i vincoli (`NOT NULL`, `CHECK`, valori permessi per `regime_label` e `action`)
3. Tutti gli indici con commento sul workload che servono
4. Se decidi di separare sentiment e regime in tabelle distinte, mostra lo schema relazionale completo
5. Eventuali `TRIGGER` o funzioni PostgreSQL che hanno senso (es. auto-calcolo `score = polarity × confidence`, validazione range)

### Parte D — Query patterns critici

Scrivi le query SQL per questi casi d'uso, ottimizzate per lo schema che hai proposto:

1. **Backtest query:** recupera tutti i segnali per simbolo `AAPL` tra `2022-01-01` e `2024-12-31`, ordinati per timestamp, con solo le colonne necessarie a QuantConnect (`score`, `confidence`, `regime_multiplier`, `generated_at`)

2. **Debug post-mortem:** per ogni ordine piazzato nella settimana `2024-03-01 → 2024-03-07`, mostra: simbolo, prezzo, quantità, score del segnale associato, reasoning LLM, chi ha approvato (Telegram user o auto)

3. **Performance monitoring:** per ogni `model_id`, calcola: numero segnali generati nell'ultimo mese, media confidence, percentuale segnali con `confidence < 0.4` (fallback), media score per simbolo

4. **Staleness analysis:** quanti segnali negli ultimi 7 giorni erano "stale" al momento in cui QC li avrebbe letti? (definizione stale: `now - generated_at > 30 minuti` al momento dell'ordine associato)

### Parte E — Migration e operatività

1. **Alembic migration:** proponi la struttura della migration Alembic per creare le tabelle, inclusi i metadati di versione

2. **Bulk insert pattern:** il SentimentWorker deve inserire ~50 segnali ogni 15 minuti in modo atomico (o tutti o nessuno). Qual è il pattern ottimale in SQLAlchemy async? (`execute(insert().values([...]))` vs `add_all()` vs `execute_many()`?)

3. **Retention policy:** con 4.800 segnali/giorno × 5 anni = ~8.7M righe nella tabella `signals`. Come gestiresti l'archiviation dei dati più vecchi senza impattare le query di backtest?

4. **Idempotency:** se il SentimentWorker crasha a metà di un batch e viene riavviato (retry Celery), come eviti duplicati nella tabella `signals`? (L'UUID è generato dal worker prima dell'insert — è sufficiente con `ON CONFLICT DO NOTHING`?)

---

## Formato risposta atteso

1. Analisi problemi schema corrente, tabella per tabella (Parte A) — bullet points concisi
2. Strategia indicizzazione completa con motivazione per ogni indice (Parte B)
3. Schema SQL completo migliorato, pronto da usare come migration (Parte C)
4. Le 4 query SQL ottimizzate con note sulle performance (Parte D)
5. Pattern operativi: migration Alembic skeleton + bulk insert + retention + idempotency (Parte E)
6. **Stima storage:** con i volumi indicati e lo schema proposto, quanti GB occuperà PostgreSQL dopo 1 anno? Dopo 5 anni?
