import { HelpButton } from '@/components/shared/HelpButton'

export default function Docs() {
  const h2Style: React.CSSProperties = {
    fontSize: 17,
    fontWeight: 700,
    margin: '0 0 14px',
    paddingBottom: 10,
    borderBottom: '1px solid var(--border)',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  }

  const h3Style: React.CSSProperties = {
    fontSize: 13,
    fontWeight: 600,
    margin: '16px 0 6px',
    color: 'var(--blue)',
  }

  const pStyle: React.CSSProperties = {
    margin: '0 0 10px',
    lineHeight: 1.7,
    color: 'var(--text-muted)',
    fontSize: 13,
  }

  const cardStyle: React.CSSProperties = {
    background: 'var(--card)',
    border: '1px solid var(--border)',
    borderRadius: 8,
    padding: '20px 24px',
    marginBottom: 20,
  }

  const listStyle: React.CSSProperties = {
    margin: '0 0 10px',
    paddingLeft: 20,
    lineHeight: 2,
    color: 'var(--text-muted)',
    fontSize: 13,
  }

  const metricCardStyle: React.CSSProperties = {
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '12px 14px',
  }

  const pipelineBoxStyle: React.CSSProperties = {
    background: 'var(--bg)',
    border: '1px solid var(--border)',
    borderRadius: 6,
    padding: '14px 18px',
    fontFamily: 'monospace',
    fontSize: 12,
    color: 'var(--text-muted)',
    lineHeight: 2,
    overflowX: 'auto',
    whiteSpace: 'pre',
  }

  const badgeStyle = (color: string, bg: string): React.CSSProperties => ({
    display: 'inline-flex',
    alignItems: 'center',
    padding: '2px 8px',
    borderRadius: 9999,
    fontSize: 11,
    fontWeight: 600,
    color,
    background: bg,
    marginLeft: 8,
  })

  return (
    <div style={{ position: 'relative' }}>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Guida Alembic</h2>
      <HelpButton title="Guida Alembic" sections={[
        {
          heading: "Cos'è questa pagina",
          content: "Documentazione completa del sistema Alembic: architettura, strategie, pipeline, parametri di rischio e modalità operative.",
        },
        {
          heading: "Come usarla",
          content: "Ogni sezione copre un aspetto del sistema. Usa questa pagina come riferimento quando hai dubbi su metriche, parametri o comportamenti del sistema.",
        },
      ]} />

      {/* 1 — FLUSSO DI UTILIZZO */}
      <div style={cardStyle}>
        <h2 style={h2Style}>🗺️ Il Flusso di Utilizzo</h2>
        <p style={pStyle}>Ordine consigliato per la revisione quotidiana del sistema:</p>
        <ol style={listStyle}>
          <li><strong>Overview</strong> — Quadro generale: P&L mensile, posizioni aperte, segnali recenti</li>
          <li><strong>Signals</strong> — Segnali LLM per ticker: score, direzione, confidence, modelli</li>
          <li><strong>Trading</strong> — Posizioni aperte, storico ordini, P&L non realizzato</li>
          <li><strong>Trades</strong> — Storico trade chiusi, cumulative P&L, analisi multidimensionale (tab Analytics)</li>
          <li><strong>Auto-Improve</strong> — Stato feedback loop (Phase B) e opportunità mancate (Phase C)</li>
          <li><strong>Strategies</strong> — Stato di validazione delle strategie (gates, sensitivity, equity curve)</li>
          <li><strong>Backtest</strong> — Risultati storici: IC, ICIR, bucket analysis, drawdown</li>
          <li><strong>Performance</strong> — Rendimento cumulativo e mensile del portfolio</li>
          <li><strong>News</strong> — Notizie che alimentano il sistema di sentiment (GDELT, MarketAux, Alpaca)</li>
          <li><strong>LLM</strong> — Pesi dei modelli, feedback per segnale, costo inference</li>
          <li><strong>Config</strong> — Watchlist e parametri di rischio personalizzabili</li>
          <li><strong>Admin</strong> — Kill switch, cambio modalità operativa, log di sistema</li>
        </ol>
      </div>

      {/* 2 — ARCHITETTURA */}
      <div style={cardStyle}>
        <h2 style={h2Style}>🏗️ Architettura del Sistema</h2>
        <p style={pStyle}>
          Il sistema segue il paradigma <strong>Alpha Miner</strong>: i modelli LLM operano <em>offline</em> come motori di ricerca e generazione segnali, mai nel hot path di esecuzione.
        </p>
        <div style={pipelineBoxStyle}>
{`[Frontend React :3000]
        │
        ▼
[FastAPI :8001] ────────── [PostgreSQL]
        │                       │
        ▼                       ▼
[Redis Queue] ◄──── [Celery Workers] ──── [Beat Scheduler]
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
   [News Ingestion] [LLM Ensemble] [Portfolio Scheduler]
   GDELT/MarketAux   kimi/qwen/      S1+S2+S4 merge
   Alpaca News       deepseek/glm    → Risk Check
                                     → Alpaca Paper API

[Grafana :3001] ── Overview / Risk / Decay dashboards`}
        </div>

        <h3 style={h3Style}>Componenti Chiave (Fase G)</h3>
        <ul style={listStyle}>
          <li><strong>Strategy Registry</strong> — Registro centrale per S1, S2, S4 con interfaccia standard</li>
          <li><strong>Portfolio Orchestrator</strong> — Unisce i segnali delle strategie attive, applica pesi di allocazione</li>
          <li><strong>Risk Monitor</strong> — Esposizione totale, concentrazione HHI, peso massimo per asset, killswitch</li>
          <li><strong>Decay Monitor</strong> — Walk-forward: confronta metriche recenti vs baseline; alert giallo/rosso</li>
          <li><strong>Portfolio Scheduler</strong> — Task Celery oraria: fetch segnali → orchestrate → risk check → ordini</li>
        </ul>
      </div>

      {/* 3 — STRATEGIE */}
      <div style={cardStyle}>
        <h2 style={h2Style}>📊 Strategie Validate</h2>

        {[
          {
            tag: 'S1',
            name: 'Time-Series Momentum Multi-Asset',
            alloc: '50%',
            status: 'ATTIVA',
            statusColor: '#15803d',
            statusBg: '#dcfce7',
            details: [
              'Momentum cross-asset su 15 ETF azionari/obbligazionari/commodity',
              'Segnale: momentum 12-1 mesi, pesatura inversa-volatilità',
              'OOS Sharpe: 0.51 — tutti i 5 gate superati',
            ],
          },
          {
            tag: 'S2',
            name: 'Volatility Risk Premium',
            alloc: '20%',
            status: 'ATTIVA',
            statusColor: '#15803d',
            statusBg: '#dcfce7',
            details: [
              'Short put su SPY/QQQ nei regimi a bassa volatilità implicita',
              'Filtro LLM per eventi macro ad alto rischio',
              'Gate 3 & 4 parzialmente superati — in portfolio',
            ],
          },
          {
            tag: 'S4',
            name: 'News-Driven Tactical',
            alloc: '30%',
            status: 'ATTIVA',
            statusColor: '#15803d',
            statusBg: '#dcfce7',
            details: [
              'Ranking cross-sezionale di ticker per sentiment LLM ensemble',
              '4 modelli: kimi-k2.6, qwen3.5, deepseek-v4-pro, glm-5.1',
              'Segnale = media pesata (polarity × confidence) per ogni modello',
            ],
          },
          {
            tag: 'S3',
            name: 'Cross-Sectional Momentum',
            alloc: '—',
            status: 'R&D',
            statusColor: '#a16207',
            statusBg: '#fef9c3',
            details: [
              'Momentum residuale su azionario USA',
              'Gate 3 (IC OOS) e Gate 5 (drag da costi) FALLITI',
              'Non nel portfolio — demoted a sleeve di ricerca',
            ],
          },
        ].map((s) => (
          <div key={s.tag} style={{
            ...metricCardStyle,
            marginBottom: 10,
            display: 'flex',
            gap: 14,
            alignItems: 'flex-start',
          }}>
            <div style={{
              background: 'var(--blue)',
              color: 'white',
              borderRadius: 6,
              padding: '4px 10px',
              fontWeight: 700,
              fontSize: 13,
              flexShrink: 0,
            }}>{s.tag}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>
                {s.name}
                <span style={badgeStyle(s.statusColor, s.statusBg)}>{s.status}</span>
                {s.alloc !== '—' && (
                  <span style={badgeStyle('#1d4ed8', '#dbeafe')}>{s.alloc}</span>
                )}
              </div>
              <ul style={{ ...listStyle, lineHeight: 1.8, marginBottom: 0 }}>
                {s.details.map((d, i) => <li key={i}>{d}</li>)}
              </ul>
            </div>
          </div>
        ))}
      </div>

      {/* 4 — PIPELINE DATI */}
      <div style={cardStyle}>
        <h2 style={h2Style}>🔄 Pipeline Dati</h2>
        <div style={pipelineBoxStyle}>
{`Sorgenti News (ogni 15 min, ore di mercato)
  ├── GDELT GKG        — eventi globali, segnali geopolitici
  ├── MarketAux        — sentiment pre-calcolato, notizie finanziarie
  └── Alpaca News      — notizie di mercato in tempo reale
          │
          ▼
  Redis Queue  ──►  LLM Ensemble Worker
                      ├── kimi-k2.6:cloud    (polarity, confidence)
                      ├── qwen3.5:397b       (polarity, confidence)
                      ├── deepseek-v4-pro    (polarity, confidence)
                      └── glm-5.1:cloud      (polarity, confidence)
          │
          ▼
  Score = Σ(weight_i × polarity_i × confidence_i)
  Score ∈ [-1, +1] — positivo = bullish, negativo = bearish
          │
          ▼
  Signal Aggregation (per strategia)
  Portfolio Orchestrator  ──►  Risk Check  ──►  Alpaca API`}
        </div>

        <h3 style={h3Style}>Task Celery Pianificati</h3>
        <ul style={listStyle}>
          <li><strong>news-ingestion</strong> — ogni 15 min (Lun-Ven, 14:00-21:00 UTC): ingestione GDELT/MarketAux/Alpaca</li>
          <li><strong>sentiment-worker</strong> — elaborazione continua coda Redis, LLM inference</li>
          <li><strong>portfolio-cycle</strong> — ogni ora (Lun-Ven, 14:00-21:00 UTC): ciclo completo di orchestrazione</li>
          <li><strong>loss-feedback-check</strong> — ogni 30 min (Lun-Ven, 14:00-21:00 UTC): Phase B — aggiusta threshold/scale se perdite recenti</li>
          <li><strong>counterfactual-worker</strong> — ogni notte alle 22:45 UTC: Phase C — calcola ritorni a 1h per i trade saltati</li>
          <li><strong>risk-monitor</strong> — giornaliero alle 22:30 UTC: monitoraggio esposizione e HHI</li>
          <li><strong>decay-monitor</strong> — mensile (1° del mese, 23:00 UTC): walk-forward decay detection</li>
        </ul>
      </div>

      {/* 5 — MODELLI LLM */}
      <div style={cardStyle}>
        <h2 style={h2Style}>🤖 Ensemble LLM</h2>
        <p style={pStyle}>
          Ogni notizia viene elaborata da 4 modelli in parallelo. Ogni modello produce una <strong>polarity</strong> (direzione, da -1 a +1) e una <strong>confidence</strong> (certezza, da 0 a 1).
          Il segnale finale è la media pesata dei prodotti <em>polarity × confidence</em>.
        </p>

        {[
          { model: 'kimi-k2.6:cloud', role: 'Modello primario', desc: 'Forte nel ragionamento finanziario e nell\'analisi di report trimestrali e notizie macro.' },
          { model: 'qwen3.5:397b', role: 'Ragionamento cross-domain', desc: 'Eccellente su analisi cross-settoriale e comprensione di eventi geopolitici complessi.' },
          { model: 'deepseek-v4-pro:cloud', role: 'Analisi strutturata', desc: 'Ottimo per output strutturato (JSON) e analisi passo-passo di documenti finanziari.' },
          { model: 'glm-5.1:cloud', role: 'Fallback low-cost', desc: 'Costo inference ridotto. Usato quando i modelli primari sono indisponibili o lenti.' },
        ].map((m) => (
          <div key={m.model} style={{ ...metricCardStyle, marginBottom: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>{m.model}</span>
              <span style={{ fontSize: 11, color: 'var(--text-muted)', fontStyle: 'italic' }}>{m.role}</span>
            </div>
            <p style={{ ...pStyle, margin: 0, fontSize: 12 }}>{m.desc}</p>
          </div>
        ))}

        <h3 style={h3Style}>Prompt Engineering (DK-CoT)</h3>
        <p style={pStyle}>
          Tutti i prompt usano <strong>Domain Knowledge Chain-of-Thought</strong>: il modello interpreta il ruolo di un analista buy-side, ragiona su flussi di cassa e competitività prima di emettere il verdetto, e produce output JSON deterministico.
        </p>
      </div>

      {/* 6 — MONITORAGGIO */}
      <div style={cardStyle}>
        <h2 style={h2Style}>📡 Monitoraggio</h2>

        <h3 style={h3Style}>Risk Monitor</h3>
        <p style={pStyle}>
          Controlla continuamente l'esposizione del portfolio. Interrompe l'esecuzione (killswitch) se vengono violati i limiti. Metriche monitorate:
        </p>
        <ul style={listStyle}>
          <li><strong>Esposizione totale</strong> — somma dei pesi assoluti nel portfolio (max 50%)</li>
          <li><strong>HHI</strong> — Herfindahl-Hirschman Index, misura la concentrazione (evita over-weighting su un singolo asset)</li>
          <li><strong>Peso massimo per asset</strong> — nessun singolo asset può superare il 10% del portfolio</li>
          <li><strong>Freshness segnali</strong> — segnali più vecchi di 30 min vengono scartati</li>
          <li><strong>Killswitch</strong> — arresto di emergenza: blocca tutti gli ordini immediatamente</li>
        </ul>

        <h3 style={h3Style}>Decay Monitor</h3>
        <p style={pStyle}>
          Confronta mensile le metriche recenti (ultimi 3 mesi) con il baseline OOS di ogni strategia. Se la degradazione supera le soglie, emette un alert.
        </p>
        <ul style={listStyle}>
          <li><strong>Metriche monitorate</strong> — IC, Sharpe, hit-rate, max drawdown per strategia</li>
          <li><strong>Alert giallo</strong> — score ≥ 0.3: degradazione rilevabile, monitorare attentamente</li>
          <li><strong>Alert rosso</strong> — score ≥ 0.5: degradazione significativa, valutare sospensione strategia</li>
        </ul>

        <h3 style={h3Style}>Dashboard Grafana (porta 3001)</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10, marginTop: 8 }}>
          {[
            { name: 'Overview', items: 'P&L, posizioni, IC, segnali, spesa LLM, volume news' },
            { name: 'Risk Monitor', items: 'Esposizione totale, pesi strategie, pesi modelli, confidence, alert' },
            { name: 'Decay Monitor', items: 'IC/Sharpe/hit-rate/drawdown decay per strategia, livelli di alert' },
          ].map((d) => (
            <div key={d.name} style={metricCardStyle}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>📊 {d.name}</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.5 }}>{d.items}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 7 — PARAMETRI DI RISCHIO */}
      <div style={cardStyle}>
        <h2 style={h2Style}>⚠️ Parametri di Rischio</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 10 }}>
          {[
            { param: 'Stop-loss per posizione', value: '2%', desc: 'Chiusura automatica se la posizione perde il 2%' },
            { param: 'Max drawdown portfolio', value: '10%', desc: 'Killswitch automatico se il portfolio scende del 10% dal picco' },
            { param: 'Max esposizione totale', value: '50%', desc: 'Il portfolio non può essere investito per più del 50% del capitale' },
            { param: 'Max peso per asset', value: '10%', desc: 'Nessun singolo ticker può superare il 10% del NAV' },
            { param: 'Signal freshness', value: '30 min', desc: 'Segnali più vecchi di 30 minuti vengono ignorati' },
            { param: 'Allocazione S1', value: '50%', desc: 'Time-Series Momentum Multi-Asset' },
            { param: 'Allocazione S2', value: '20%', desc: 'Volatility Risk Premium' },
            { param: 'Allocazione S4', value: '30%', desc: 'News-Driven Tactical' },
          ].map((r) => (
            <div key={r.param} style={metricCardStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 4 }}>
                <span style={{ fontWeight: 600, fontSize: 12 }}>{r.param}</span>
                <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--blue)' }}>{r.value}</span>
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: 11, lineHeight: 1.5 }}>{r.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 8 — GATES DI VALIDAZIONE */}
      <div style={cardStyle}>
        <h2 style={h2Style}>✅ Gates di Validazione</h2>
        <p style={pStyle}>
          Ogni strategia deve superare 5 gate prima di entrare nel portfolio. Il mancato superamento di un gate demote la strategia al sleeve R&D.
        </p>
        {[
          { gate: 'Gate 1', name: 'Qualità del Codice', desc: 'Documentazione, riproducibilità dei risultati, revisione del codice. Verifica che il backtest sia deterministic e privo di look-ahead bias.' },
          { gate: 'Gate 2', name: 'Expectation Positiva', desc: 'Backtest single-asset con aspettativa positiva statistica (p-value < 0.05). Esclude strategie con edge casuale.' },
          { gate: 'Gate 3', name: 'Walk-Forward OOS', desc: 'IC out-of-sample > 0.05 su almeno 3 finestre walk-forward. Verifica che il segnale sia generalizzabile, non overfitted.' },
          { gate: 'Gate 4', name: 'Sensitivity Analysis', desc: 'Parametri robusti: l\'edge deve persistere con variazioni ±20% dei parametri chiave. Evita strategie eccessivamente ottimizzate.' },
          { gate: 'Gate 5', name: 'Costi di Transazione', desc: 'Drag da costi (spread + slippage + commissioni) < 50% dell\'alpha lordo. Garantisce che l\'edge sopravviva all\'execution reale.' },
        ].map((g, i) => (
          <div key={g.gate} style={{
            display: 'flex',
            gap: 14,
            padding: '12px 0',
            borderBottom: i < 4 ? '1px solid var(--border)' : 'none',
          }}>
            <div style={{
              background: 'var(--blue)',
              color: 'white',
              borderRadius: 6,
              padding: '4px 10px',
              fontWeight: 700,
              fontSize: 12,
              flexShrink: 0,
              alignSelf: 'flex-start',
            }}>{g.gate}</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{g.name}</div>
              <p style={{ ...pStyle, margin: 0, fontSize: 12 }}>{g.desc}</p>
            </div>
          </div>
        ))}
      </div>

      {/* 9 — METRICHE CHIAVE */}
      <div style={cardStyle}>
        <h2 style={h2Style}>📈 Metriche Chiave</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {[
            { name: 'OOS Sharpe', desc: 'Rendimento risk-adjusted out-of-sample. > 0.5 = buona, > 1.0 = eccellente' },
            { name: 'IC', desc: 'Information Coefficient — correlazione di Spearman tra predizione e rendimento. > 0.05 = segnale utile' },
            { name: 'ICIR', desc: 'IC Information Ratio: IC / Std(IC). > 0.3 = segnale consistente nel tempo' },
            { name: 'Max Drawdown', desc: 'Massima perdita dal picco equity. < 20% accettabile, > 30% preoccupante' },
            { name: 'Confidence', desc: 'Concordanza tra modelli LLM sul segnale. > 0.7 = alta affidabilità del segnale' },
            { name: 'Hit Rate', desc: 'Percentuale di predizioni corrette (direzione). > 52% indica edge statistico' },
            { name: 'Polarity', desc: 'Direzione del segnale LLM: +1 = fortemente bullish, -1 = fortemente bearish, 0 = neutro' },
            { name: 'Score finale', desc: 'polarity × confidence — scala il segnale direzionale per la certezza del modello' },
          ].map((m) => (
            <div key={m.name} style={metricCardStyle}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{m.name}</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.5 }}>{m.desc}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 10 — MODALITÀ OPERATIVE */}
      <div style={cardStyle}>
        <h2 style={h2Style}>⚙️ Modalità Operative</h2>
        <p style={pStyle}>La modalità operativa corrente è visibile e modificabile nella pagina <strong>Admin</strong>.</p>
        {[
          { mode: 'Backtest', badge: '#475569', badgeBg: '#f1f5f9', desc: 'Simulazione storica. Nessun ordine reale o simulato inviato. Usato per testare strategie su dati passati.' },
          { mode: 'Paper', badge: '#1d4ed8', badgeBg: '#dbeafe', desc: 'Modalità corrente. Ordini simulati via Alpaca Paper API. Comportamento identico al live, senza rischio capitale reale.' },
          { mode: 'Semi-auto', badge: '#a16207', badgeBg: '#fef9c3', desc: 'Ogni ordine richiede approvazione manuale via Telegram prima dell\'esecuzione. Utile nella transizione verso il live.' },
          { mode: 'Full-auto', badge: '#15803d', badgeBg: '#dcfce7', desc: 'Esecuzione completamente automatica senza intervento umano. Richiede piena fiducia nel sistema e nei parametri di rischio.' },
          { mode: 'Halted', badge: '#b91c1c', badgeBg: '#fee2e2', desc: 'Tutti gli ordini bloccati. Il sistema continua a raccogliere segnali e monitorare, ma non esegue. Attivabile tramite killswitch.' },
        ].map((m) => (
          <div key={m.mode} style={{
            display: 'flex',
            gap: 14,
            padding: '12px 0',
            borderBottom: '1px solid var(--border)',
          }}>
            <div style={{
              ...badgeStyle(m.badge, m.badgeBg),
              marginLeft: 0,
              flexShrink: 0,
              alignSelf: 'flex-start',
              fontSize: 12,
              padding: '4px 12px',
            }}>{m.mode}</div>
            <p style={{ ...pStyle, margin: 0, fontSize: 13 }}>{m.desc}</p>
          </div>
        ))}
      </div>

      {/* 11 — PERFORMANCE & AUTO-IMPROVE */}
      <div style={cardStyle}>
        <h2 style={h2Style}>📉 Performance & Auto-Improve</h2>
        <p style={pStyle}>
          Il sistema valuta la propria performance in tre fasi distinte e usa i risultati per auto-correggersi continuamente.
        </p>

        <h3 style={h3Style}>Phase A — Trade Analytics (pagina Trades → tab Analytics)</h3>
        <p style={pStyle}>
          Analisi retrospettiva multidimensionale dei trade chiusi. Risponde alla domanda: <em>dove guadagna e perde il sistema?</em>
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10, marginBottom: 16 }}>
          {[
            { dim: 'Per Simbolo', use: 'Identifica ticker con edge positivo e ticker che drenano. Un simbolo sistematicamente negativo va rimosso dalla watchlist.' },
            { dim: 'Per Regime', use: 'Verifica che il sistema guadagni nei regimi attesi (bullish). Se guadagna anche in regime basso, valuta di abbassare la soglia minima di regime.' },
            { dim: 'Per Ora', use: 'Individua le fasce orarie redditizie. Le prime 30 minuti di mercato (9:30–10:00 EST) spesso hanno spread alti — se negativi, aggiungi un filtro orario.' },
            { dim: 'Per Score LLM', use: 'Verifica che bucket di score alto → P&L alto. Se la correlazione è assente, il segnale LLM non ha edge — rivaluta i pesi dei modelli.' },
            { dim: 'Per Durata', use: 'Trova la finestra di holding ottimale. Trade <15 min soffrono di spread; trade >2h rischiano staleness del segnale.' },
          ].map((r) => (
            <div key={r.dim} style={metricCardStyle}>
              <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 4 }}>{r.dim}</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.5 }}>{r.use}</div>
            </div>
          ))}
        </div>

        <h3 style={h3Style}>Phase B — Loss Feedback Loop (pagina Auto-Improve)</h3>
        <p style={pStyle}>
          Aggiustamento automatico delle soglie in risposta a perdite recenti. Opera <strong>ogni 30 minuti</strong> durante gli orari di mercato.
        </p>
        <ul style={listStyle}>
          <li><strong>Trigger OR</strong>: 3 perdite consecutive oppure P&L rolling negativo sugli ultimi 10 trade</li>
          <li><strong>Effetto Entry Threshold</strong>: alzata da 0.30 fino a 0.60 (step +0.05 per aggiustamento) — sistema più selettivo</li>
          <li><strong>Effetto Regime Scale</strong>: ridotta a 0.80× — position sizing ridotto del 20%</li>
          <li><strong>Cooldown</strong>: 4 ore tra aggiustamenti; <strong>Recovery</strong>: 5 vincite consecutive per tornare al baseline</li>
          <li><strong>TTL</strong>: ogni aggiustamento scade automaticamente dopo 48 ore</li>
        </ul>
        <div style={{ ...metricCardStyle, marginBottom: 0 }}>
          <div style={{ fontWeight: 600, fontSize: 12, marginBottom: 6 }}>Come interpretare lo stato</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: 'Entry Threshold = 0.30, Scale = 1.0×', meaning: 'Baseline — sistema normale, nessuna perdita recente' },
              { label: 'Entry Threshold > 0.30', meaning: 'Feedback attivo — filtra i segnali deboli dopo perdite' },
              { label: 'Scale < 1.0×', meaning: 'Sizing ridotto — il sistema si protegge in un contesto difficile' },
              { label: 'Attivo da >24h senza recovery', meaning: 'Mercato avverso — analizza Signals e considera Halted' },
            ].map((s) => (
              <div key={s.label} style={{ background: 'var(--bg)', borderRadius: 6, padding: '8px 10px' }}>
                <div style={{ fontFamily: 'monospace', fontSize: 11, color: 'var(--blue)', marginBottom: 2 }}>{s.label}</div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{s.meaning}</div>
              </div>
            ))}
          </div>
        </div>

        <h3 style={h3Style}>Phase C — Counterfactual Analysis (pagina Auto-Improve)</h3>
        <p style={pStyle}>
          Valutazione retrospettiva delle opportunità filtrate. Il sistema registra ogni trade saltato (<strong>SKIP_EMA</strong>, <strong>SKIP_CAP</strong>) e il giorno dopo calcola cosa sarebbe successo se fosse stato eseguito (ritorno a 1h tramite dati Alpaca 1-minuto).
        </p>
        <ul style={listStyle}>
          <li><strong>SKIP_EMA</strong>: prezzo sotto la EMA20 al momento del segnale — filtro trend-following</li>
          <li><strong>SKIP_CAP</strong>: limite di allocazione per ciclo raggiunto — filtro di concentrazione</li>
          <li><strong>SKIP_POSITION</strong>: ticker già in portafoglio — escluso dall'analisi (no pyramiding by design)</li>
        </ul>
        <p style={pStyle}>
          <strong>Regola decisionale</strong>: agisci su un filtro solo se <em>avg_return &gt; +0.5%</em> e <em>% profitable &gt; 55%</em> su almeno 30 osservazioni. Sotto questa soglia i dati sono statisticamente rumorosi. Aggiornamento: nightly alle 22:45 UTC.
        </p>
      </div>

      {/* 12 — AIUTO CONTESTUALE */}
      <div style={cardStyle}>
        <h2 style={h2Style}>❓ Aiuto Contestuale</h2>
        <p style={pStyle}>
          Ogni pagina ha un pulsante <strong style={{ background: '#3b82f6', color: 'white', borderRadius: '50%', padding: '1px 6px', fontSize: 12 }}>?</strong> in alto a destra. Cliccalo per aprire un pannello laterale con la documentazione specifica di quella pagina: metriche, interpretazione dei dati, e flusso consigliato.
        </p>
        <p style={{ ...pStyle, marginBottom: 0 }}>
          Per domande sul sistema, consultare prima questa pagina. Per problemi tecnici o configurazione avanzata, verificare i log in <strong>Admin</strong> e i task Celery tramite Grafana.
        </p>
      </div>
    </div>
  )
}
