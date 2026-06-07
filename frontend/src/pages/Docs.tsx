import { HelpButton } from '@/components/shared/HelpButton'

export default function Docs() {
  const h2: React.CSSProperties = {
    fontSize: 17, fontWeight: 700, margin: '0 0 14px',
    paddingBottom: 10, borderBottom: '1px solid var(--border)',
    display: 'flex', alignItems: 'center', gap: 8,
  }
  const h3: React.CSSProperties = { fontSize: 13, fontWeight: 600, margin: '16px 0 6px', color: 'var(--blue)' }
  const card: React.CSSProperties = {
    background: 'var(--card)', border: '1px solid var(--border)',
    borderRadius: 8, padding: '20px 24px', marginBottom: 20,
  }
  const inner: React.CSSProperties = {
    background: 'var(--bg)', border: '1px solid var(--border)',
    borderRadius: 6, padding: '12px 14px', marginBottom: 10,
  }
  const p: React.CSSProperties = { margin: '0 0 10px', lineHeight: 1.7, color: 'var(--text-muted)', fontSize: 13 }
  const ul: React.CSSProperties = { margin: '0 0 10px', paddingLeft: 20, lineHeight: 2, color: 'var(--text-muted)', fontSize: 13 }
  const mono: React.CSSProperties = {
    background: 'var(--bg)', border: '1px solid var(--border)', borderRadius: 6,
    padding: '14px 18px', fontFamily: 'monospace', fontSize: 12,
    color: 'var(--text-muted)', lineHeight: 2, overflowX: 'auto', whiteSpace: 'pre',
    marginBottom: 10,
  }
  const badge = (color: string, bg: string): React.CSSProperties => ({
    display: 'inline-block', marginLeft: 8, padding: '1px 8px',
    borderRadius: 99, fontSize: 11, fontWeight: 600, color, background: bg, border: `1px solid ${color}`,
  })
  const stag: React.CSSProperties = {
    background: 'var(--blue)', color: 'white', borderRadius: 6,
    padding: '3px 9px', fontWeight: 700, fontSize: 12, flexShrink: 0, marginTop: 1,
  }
  const rowFlex: React.CSSProperties = { display: 'flex', gap: 8, alignItems: 'flex-start', marginBottom: 8 }
  const tableRow: React.CSSProperties = { borderBottom: '1px solid #1e293b' }
  const td: React.CSSProperties = { padding: '6px 10px', color: '#94a3b8', fontSize: 13 }
  const th: React.CSSProperties = { textAlign: 'left' as const, padding: '6px 10px', color: '#64748b', fontWeight: 600, fontSize: 12 }

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '0 0 40px' }}>
      <HelpButton title="Guida Alembic" sections={[
        {
          heading: "Cos'è Alembic",
          content: "Alembic è un sistema di trading algoritmico guidato da LLM. L'intelligenza artificiale lavora offline come motore di ricerca: produce segnali di sentiment che vengono letti dal motore di esecuzione in modo asincrono. Nessun LLM viene chiamato in tempo reale durante un ordine.",
        },
        {
          heading: "Le strategie in breve",
          content: "**S1 (50%)**: momentum multi-lookback su ETF/azionario — usa solo prezzi storici, nessun LLM.\n\n**S4 (10%)**: news sentiment via LLM ensemble — legge segnali pre-calcolati da Redis, filtra con EMA e regime.\n\n**S2**: DISABILITATA (OOS Sharpe −0.55, tutti i gate falliti).\n\n**S3**: R&D sleeve, non in produzione.",
        },
        {
          heading: "Dove guardare",
          content: "• **Overview** — P&L live, segnali recenti, IC\n• **Signals** — segnali LLM per ticker\n• **Trades → Analytics** — P&L per regime/simbolo/durata\n• **Performance → Weekly Report** — costi, cash drag, infrastruttura\n• **Strategies** — gate di validazione OOS\n• **Auto-Improve** — feedback loop e counterfactual\n• **LLM** — pesi ensemble e ICIR per modello",
        },
      ]} />

      <h1 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Guida Alembic</h1>

      {/* 1. COS'È ALEMBIC */}
      <div style={card}>
        <h2 style={h2}>🧭 Cos'è Alembic e come funziona</h2>
        <p style={p}>
          Alembic è un sistema di trading algoritmico che usa LLM (Large Language Models) come motore di ricerca e generazione di segnali, mai come esecutore in tempo reale. Il principio architetturale fondamentale è: <strong>gli LLM lavorano offline, l'execution engine legge segnali pre-calcolati</strong>.
        </p>
        <div style={mono}>{`[News: GDELT / MarketAux / Alpaca]
         ↓  ogni 15 min (ore di mercato)
[LLM Ensemble Worker] ──→ Redis: signal:{symbol}:sentiment
         ↑ offline, asincrono

[Portfolio Scheduler] ──→ legge segnali da Redis (ogni ora)
         ↓
[Risk Constraints] ──→ [Alpaca Paper/Live API]`}</div>
        <p style={p}>
          Questo design garantisce che un eventuale timeout o rallentamento del modello LLM non blocchi mai l'esecuzione di un ordine. Il motore di esecuzione ha sempre un segnale già pronto in Redis.
        </p>
      </div>

      {/* 2. STRATEGIE */}
      <div style={card}>
        <h2 style={h2}>📊 Le Strategie</h2>
        <p style={{ ...p, marginBottom: 16 }}>
          Alembic usa un portfolio multi-strategia con allocazioni fisse configurate in <code>config/strategies.yaml</code>. Le strategie producono <em>pesi sleeve-local</em> (frazioni del proprio capitale), poi l'orchestratore li scala per l'allocazione percentuale.
        </p>

        {/* S1 */}
        <div style={inner}>
          <div style={rowFlex}>
            <div style={stag}>S1</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                Multi-Lookback Relative Momentum
                <span style={badge('#15803d', '#dcfce7')}>LIVE — 50% portafoglio</span>
              </div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Teoria</h3>
              <p style={p}>
                Il momentum è una delle anomalie di mercato più documentate (Jegadeesh &amp; Titman, 1993; Moskowitz et al., 2012). Le attività che hanno performato bene negli ultimi mesi tendono a continuare nel breve termine, per ragioni comportamentali (under-reaction, herding) e strutturali (trend-following istituzionale).
              </p>
              <p style={p}>
                S1 usa <strong>quattro finestre di lookback</strong> (1M=21d, 3M=63d, 6M=126d, 12M=252d). Il ritorno grezzo viene normalizzato per la volatilità. Il <strong>z-score cross-sezionale</strong> classifica ogni asset rispetto ai peer — il segnale è il ranking relativo, non il livello assoluto.
              </p>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come genera il segnale</h3>
              <div style={mono}>{`Dati input: prezzi OHLCV storici (~15 ETF + azionario)

Per ogni lookback lb ∈ {21, 63, 126, 252} giorni:
    raw_lb  = price / price.shift(lb) - 1        # ritorno grezzo
    norm_lb = raw_lb / rolling_vol(63d)           # normalizzato per vol

signal_raw = weighted_sum(norm_lb, [1×, e×, e²×, e³×] norm.)
signal     = z_score(signal_raw, cross-sectional)  # ranking vs peer

raw_weight ∝ signal × (target_vol=15% / realised_vol)
sleeve_weight = normalise(raw_weight, long-only, sum≤1)`}</div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come interviene sul portafoglio</h3>
              <p style={p}>
                L'orchestratore moltiplica i pesi sleeve S1 per 0.50. Un asset con peso sleeve 0.40 occupa il 20% del portafoglio totale. S1 è <strong>puro price-momentum</strong>: nessun filtro LLM, nessun regime multiplier.
              </p>
            </div>
          </div>
        </div>

        {/* S4 */}
        <div style={inner}>
          <div style={rowFlex}>
            <div style={stag}>S4</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                News-Driven Tactical (LLM Sentiment)
                <span style={badge('#1d4ed8', '#dbeafe')}>PAPER — 10% portafoglio</span>
              </div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Teoria</h3>
              <p style={p}>
                Le notizie aziendali generano price discovery: il mercato reagisce con ritardo agli eventi positivi/negativi (Tetlock, 2007; Loughran &amp; McDonald, 2011). L'uso di LLM permette di estrarre sentiment più preciso rispetto a dizionari tradizionali, catturando contesto e sfumature.
              </p>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come genera il segnale</h3>
              <div style={mono}>{`Fonti news (ogni 15 min, 14:00-21:00 UTC Lun-Ven):
  ├── GDELT GKG    — eventi geopolitici globali
  ├── MarketAux    — news finanziarie con ticker
  └── Alpaca News  — news real-time

LLM Ensemble (4 modelli in parallelo via Ollama cloud):
  kimi-k2.6   → { polarity ∈ [-1,+1], confidence ∈ [0,1] }
  qwen3.5     → { polarity, confidence }
  deepseek    → { polarity, confidence }
  glm-5.1     → { polarity, confidence }

  score_i = polarity_i × confidence_i

Aggregazione:
  if std(score_i) > 0.30 → FinBERT locale (fallback)
  else: score = Σ(weight_i × score_i)

Redis: SET signal:{symbol}:sentiment = { score, ts, model_id }`}</div>
              <h3 style={{ ...h3, margin: '8px 0 4px' }}>Come S4 interviene sul segnale</h3>
              <div style={mono}>{`Ogni ciclo portfolio (ogni ora):
  S4.compute_target_weights(signals):

  [1] Filtro score:     score < 0.30  → SKIP
  [2] Filtro EMA20:     price < EMA20 → SKIP (downtrend)
  [3] Filtro staleness: age > 30 min  → SKIP (news obsoleta)

  Se PASS:
    sleeve_weight = base_size (0.02) × regime_multiplier

  regime_multiplier:
    bull      → ×1.0  |  sideways → ×0.7
    bear      → ×0.4  |  high_vol → ×0.2

Portfolio orchestratore:
  merged[sym] += S4_weight[sym] × 0.10`}</div>
              <p style={p}>
                Il <strong>regime multiplier</strong> è il meccanismo più importante: in bear market, anche un segnale fortemente positivo genera solo il 40% della posizione normale. Questo protegge dal bias di conferma dell'LLM in mercati avversi.
              </p>
            </div>
          </div>
        </div>

        {/* S2 */}
        <div style={{ ...inner, opacity: 0.6 }}>
          <div style={rowFlex}>
            <div style={{ ...stag, background: '#475569' }}>S2</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                Volatility Risk Premium (VRP)
                <span style={badge('#991b1b', '#fee2e2')}>DISABILITATA — 0% portafoglio</span>
              </div>
              <p style={p}>
                <strong>Teoria:</strong> La volatilità implicita (VIX) eccede sistematicamente la volatilità realizzata di 3–4 punti annualizzati. Vendere questa "assicurazione" cattura un premio strutturale. L'implementazione attuale è un proxy semplificato (long SPY overnight quando VIX/realised_vol_20d {'>'} 0.20) — non usa opzioni reali.
              </p>
              <p style={{ ...p, color: '#ef4444', marginBottom: 0 }}>
                Stato: OOS Sharpe −0.55, tutti i gate (1–4) falliti. Non attiva. Per riattivarla serve superare tutti i gate.
              </p>
            </div>
          </div>
        </div>

        {/* S3 */}
        <div style={{ ...inner, opacity: 0.6 }}>
          <div style={rowFlex}>
            <div style={{ ...stag, background: '#92400e' }}>S3</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                Cross-Sectional Momentum
                <span style={badge('#a16207', '#fef9c3')}>R&D — 0% portafoglio</span>
              </div>
              <p style={p}>
                <strong>Teoria:</strong> Momentum residuale su azionario US: top quintile per rendimento 12-1 mesi, rebalancing mensile su S&P 500.
              </p>
              <p style={{ ...p, color: '#f59e0b', marginBottom: 0 }}>
                Stato: Gate 3 (IC OOS) e Gate 5 (drag da costi) falliti. Possibile lookahead nel sizing. Non attiva.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 3. FLUSSO COMPLETO SEGNALE */}
      <div style={card}>
        <h2 style={h2}>🔄 Flusso Completo di un Segnale (S4)</h2>
        <div style={mono}>{`STEP 1 — INGESTION (ogni 15 min, 14:00-21:00 UTC, Lun-Ven)
  GDELTConnector / MarketAuxConnector / AlpacaNewsConnector
  → INSERT INTO news_log(ticker, headline, source, fetched_at)
  → PUSH news_id in Redis queue

STEP 2 — LLM ENSEMBLE
  Prompt DK-CoT: "Act as buy-side analyst. Reason over cash flows,
  competition, profitability. Output JSON: {polarity, confidence, reasoning}"

  4 modelli in parallelo → [score_1, score_2, score_3, score_4]

  if std(scores) > 0.30:
    → FinBERT locale: confidence = 1 - H(softmax) / log(3)
  else:
    → score = Σ(weight_i × polarity_i × confidence_i)

  → UPDATE sentiment_signals SET score=...
  → SET Redis: signal:{ticker}:sentiment = {score, ts, model_id}

STEP 3 — PORTFOLIO CYCLE (ogni ora)
  S1.compute_target_weights(prices):
    → {AAPL: 0.35, NVDA: 0.22, ...}  # sleeve-local, no LLM

  S4.compute_target_weights(signals):
    Per ticker: score < 0.30 → skip | price < EMA20 → skip | age > 30min → skip
    → {MSFT: 0.02, TSLA: 0.015, ...}  # sleeve-local, scaled by regime

STEP 4 — MERGE + RISK CONSTRAINTS
  merged[sym] += S1_weight[sym] × 0.50
  merged[sym] += S4_weight[sym] × 0.10

  Constraints (iterative, 10 pass max):
    max per-asset 10% NAV | max total 95% | max sector 25% | HHI check
  Vol overlay: qty × (target_vol=10% / estimated_portfolio_vol) clamped [0.5×, 2×]

STEP 5 — ORDINI
  delta_qty = target - current
  → BUY / SELL → Alpaca Paper API → INSERT INTO trades`}</div>
      </div>

      {/* 4. COME LE STRATEGIE INTERVENGONO */}
      <div style={card}>
        <h2 style={h2}>⚙️ Come le Strategie Intervengono sul Segnale</h2>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border)' }}>
                <th style={th}>Filtro / Intervento</th>
                <th style={th}>S1</th>
                <th style={th}>S4</th>
                <th style={th}>Dove</th>
              </tr>
            </thead>
            <tbody>
              {[
                ['Score threshold (≥0.30)', '—', '✓ blocca entry', 'S4.compute_target_weights()'],
                ['EMA20 trend filter', '—', '✓ blocca entry in downtrend', 'S4.compute_target_weights()'],
                ['Signal staleness (≤30 min)', '—', '✓ scarta segnali vecchi', 'S4.compute_target_weights()'],
                ['Regime multiplier (×0.2–1.0)', '—', '✓ scala la size', 'S4 + RegimeDetector'],
                ['Vol-normalisation per lookback', '✓', '—', 'S1 signal compute'],
                ['Cross-sectional z-score', '✓', '—', 'S1 signal compute'],
                ['Inverse-vol sizing (target 15%)', '✓', '—', 'S1 sizing.py'],
                ['Allocazione sleeve (50% / 10%)', '✓', '✓', 'PortfolioOrchestrator'],
                ['Max per-asset 10% NAV', '✓', '✓', 'PortfolioConstraints'],
                ['Max exposure 95% NAV', '✓', '✓', 'PortfolioConstraints'],
                ['Max sector 25% NAV', '✓', '✓', 'PortfolioConstraints'],
                ['Vol overlay (target 10% ptf)', '✓', '✓', 'PortfolioVolTargeter'],
                ['Kill-switch (blocca tutto)', '✓', '✓', 'ExecutionWorker pre-check'],
                ['Drawdown cap portafoglio (10%)', '✓', '✓', 'ExecutionWorker pre-check'],
                ['Feedback: threshold adattivo', '—', '✓ alza soglia score', 'LossFeedbackWorker'],
              ].map(([filtro, s1, s4, dove]) => (
                <tr key={filtro as string} style={tableRow}>
                  <td style={td}>{filtro}</td>
                  <td style={{ ...td, color: s1 === '—' ? '#334155' : '#22c55e' }}>{s1}</td>
                  <td style={{ ...td, color: s4 === '—' ? '#334155' : '#60a5fa' }}>{s4}</td>
                  <td style={{ ...td, color: '#64748b', fontSize: 11 }}>{dove}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h3 style={h3}>Regime multiplier: effetto pratico su S4</h3>
        <div style={mono}>{`Regime   Mult   Esempio: MSFT score=0.45 su portafoglio $10k
────────────────────────────────────────────────────────
bull     ×1.0   sleeve=2.0% → ptf_weight=0.20% → ordine ~$20
sideways ×0.7   sleeve=1.4% → ordine ~$14
bear     ×0.4   sleeve=0.8% → ordine ~$8
high_vol ×0.2   sleeve=0.4% → ordine ~$4`}</div>
      </div>

      {/* 5. PARAMETRI DI RISCHIO */}
      <div style={card}>
        <h2 style={h2}>⚠️ Parametri di Rischio</h2>
        <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th style={th}>Parametro</th>
              <th style={th}>Default</th>
              <th style={th}>Descrizione</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['ENTRY_THRESHOLD (S4)', '0.30', 'Score minimo LLM per BUY. Alzato dal feedback loop in caso di perdite.'],
              ['Stop-loss S4', '5% (tier A/B: 2%)', 'Chiude se prezzo scende a entry × (1 − stop_loss_pct).'],
              ['Max posizione per asset', '10% NAV', 'Nessun ticker può superare il 10% del portafoglio.'],
              ['Max esposizione totale', '95% NAV', 'Il 5% rimane liquido come buffer.'],
              ['Max esposizione settoriale', '25% NAV', 'Evita concentrazione su singolo settore.'],
              ['Drawdown cap portafoglio', '10%', 'Se portafoglio scende del 10% dal picco → kill-switch automatico.'],
              ['Regime multiplier min', '×0.2 (high_vol)', 'In alta volatilità le posizioni S4 si riducono dell\'80%.'],
              ['Vol target portafoglio', '10% annualizzato', 'Il vol overlay scala le qty per puntare a questo livello.'],
              ['Max signal age S4', '30 min', 'Segnali più vecchi di 30 min vengono ignorati.'],
              ['Allocazione S1', '50% NAV', 'Unica strategia con gate completi superati.'],
              ['Allocazione S4', '10% NAV', 'Cappato al 10% fino a gate dedicati passati.'],
            ].map(([param, def_, desc]) => (
              <tr key={param as string} style={tableRow}>
                <td style={{ ...td, fontFamily: 'monospace', fontSize: 11 }}>{param}</td>
                <td style={{ ...td, color: 'white', fontWeight: 600, whiteSpace: 'nowrap' as const }}>{def_}</td>
                <td style={{ ...td, color: '#64748b' }}>{desc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* 6. GATE DI VALIDAZIONE */}
      <div style={card}>
        <h2 style={h2}>✅ Gate di Validazione Strategie</h2>
        <p style={p}>
          Ogni strategia deve superare 5 gate prima di entrare nel portfolio live. Il fallimento demote la strategia al sleeve R&D.
        </p>
        {[
          { gate: 'Gate 1', name: 'Significance', desc: 'OOS Sharpe > 0.5. La strategia batte il caso?' },
          { gate: 'Gate 2', name: 'Walk-Forward OOS', desc: 'OOS Sharpe > 0.8 × IS Sharpe. Il rendimento regge out-of-sample?' },
          { gate: 'Gate 3', name: 'Robustness', desc: 'IC OOS > 0.05 su ≥3 finestre walk-forward. Segnale generalizzabile?' },
          { gate: 'Gate 4', name: 'Sensitivity', desc: 'Sharpe stabile con ±20% variazione parametri (CV < 0.5). Nessun overfitting.' },
          { gate: 'Gate 5', name: 'Stress Test', desc: 'Non collassa in 2008, COVID 2020, 2022 rate shock. Cost drag < gross P&L.' },
        ].map(({ gate, name, desc }) => (
          <div key={gate} style={{ ...inner, display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 6 }}>
            <div style={{ background: '#1d4ed8', color: 'white', borderRadius: 6, padding: '2px 8px', fontSize: 11, fontWeight: 700, flexShrink: 0 }}>{gate}</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13 }}>{name}</div>
              <div style={{ color: '#64748b', fontSize: 12, marginTop: 2 }}>{desc}</div>
            </div>
          </div>
        ))}
      </div>

      {/* 7. METRICHE CHIAVE */}
      <div style={card}>
        <h2 style={h2}>📈 Metriche Chiave</h2>
        {[
          { name: 'IC (Information Coefficient)', desc: 'Correlazione di Spearman tra predizione LLM e rendimento reale. > 0.05 = segnale utile, < 0 = anti-predittivo.' },
          { name: 'ICIR (IC Information Ratio)', desc: 'IC / Std(IC). > 0.3 = segnale consistente nel tempo. Il LOO-ICIR misura il contributo marginale di ogni modello.' },
          { name: 'Polarity', desc: 'Direzione del segnale LLM: +1 = fortemente bullish, −1 = fortemente bearish.' },
          { name: 'Confidence', desc: 'Certezza del modello. Per FinBERT: confidence = 1 − H(softmax) / log(3).' },
          { name: 'Score finale S4', desc: 'polarity × confidence. Alta polarità + bassa confidenza → score piccolo. Penalizza l\'incertezza.' },
          { name: 'OOS Sharpe', desc: 'Sharpe ratio out-of-sample. > 0.5 = Gate 1 superato. > 1.0 = eccellente.' },
          { name: 'Cost drag', desc: 'Frazione di P&L lordo consumata da spread + market impact. Annualizzato = cost_drag_pct × 252.' },
          { name: 'Cash drag', desc: 'Costo opportunità del capitale non deployato: cash_pct × 4.5% (T-bill proxy) per anno.' },
          { name: 'Regime multiplier', desc: 'Coefficiente (0.2–1.0) che scala le posizioni S4 in base al regime rilevato da RegimeDetector.' },
          { name: 'HHI', desc: 'Herfindahl-Hirschman Index: concentrazione del portafoglio. Alto HHI = pochi asset dominanti.' },
        ].map(({ name, desc }) => (
          <div key={name} style={{ ...inner, marginBottom: 6 }}>
            <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 3 }}>{name}</div>
            <div style={{ color: '#64748b', fontSize: 12 }}>{desc}</div>
          </div>
        ))}
      </div>

      {/* 8. AUTO-IMPROVE */}
      <div style={card}>
        <h2 style={h2}>🔧 Auto-Improve (Phase A / B / C)</h2>
        <h3 style={h3}>Phase A — Trade Analytics (pagina Trades → tab Analytics)</h3>
        <ul style={ul}>
          <li><strong>P&L per simbolo</strong> — quali ticker generano alpha, quali distruggono valore</li>
          <li><strong>P&L per regime</strong> — la strategia funziona meglio in bull o sideways?</li>
          <li><strong>P&L per score bucket</strong> — segnali con score alto → P&L alto? Se no, il segnale LLM non ha edge</li>
          <li><strong>P&L per durata holding</strong> — finestra ottimale di holding</li>
        </ul>
        <h3 style={h3}>Phase B — Loss Feedback Loop (pagina Auto-Improve)</h3>
        <p style={p}>
          N perdite consecutive o P&L rolling negativo → <code>LossFeedbackWorker</code> alza <code>ENTRY_THRESHOLD</code> e riduce <code>regime_scale</code>. Visibile nel tab Weekly Report della pagina Performance.
        </p>
        <h3 style={h3}>Phase C — Counterfactual Analysis (pagina Auto-Improve)</h3>
        <p style={p}>
          Per ogni trade saltato (<code>SKIP_EMA</code>, <code>SKIP_CAP</code>, <code>SKIP_POSITION</code>), calcola il rendimento che avrebbe generato. Permette di calibrare i filtri.
        </p>
      </div>

      {/* 9. MODALITÀ OPERATIVE */}
      <div style={card}>
        <h2 style={h2}>⚙️ Modalità Operative</h2>
        {[
          { mode: 'Backtest', color: '#475569', bg: '#f1f5f9', desc: 'Simulazione su dati storici. Nessun ordine reale o simulato. Pagina Backtest.' },
          { mode: 'Paper', color: '#1d4ed8', bg: '#dbeafe', desc: 'Ordini simulati su Alpaca paper account. Denaro fittizio. Stato attuale.' },
          { mode: 'Live', color: '#15803d', bg: '#dcfce7', desc: 'Ordini reali su Alpaca live. Solo dopo 90 giorni di paper trading validati + go-live checklist.' },
        ].map(({ mode, color, bg, desc }) => (
          <div key={mode} style={{ ...inner, display: 'flex', gap: 12, alignItems: 'flex-start', marginBottom: 6 }}>
            <div style={badge(color, bg)}>{mode}</div>
            <div style={{ color: '#94a3b8', fontSize: 13 }}>{desc}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
