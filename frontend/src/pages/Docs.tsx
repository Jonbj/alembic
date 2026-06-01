export default function Docs() {
  const h2Style: React.CSSProperties = {
    fontSize: 18,
    fontWeight: 700,
    margin: '0 0 12px',
    paddingBottom: 8,
    borderBottom: '1px solid var(--border)',
  }

  const h3Style: React.CSSProperties = {
    fontSize: 14,
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

  return (
    <div>
      <h2 style={{ margin: '0 0 20px', fontSize: 20, fontWeight: 700 }}>Guida Alembic</h2>

      <div style={cardStyle}>
        <h2 style={h2Style}>Il Flusso di Utilizzo</h2>
        <ol style={{ margin: 0, paddingLeft: 20, lineHeight: 2, color: 'var(--text-muted)', fontSize: 13 }}>
          <li><strong>Overview</strong> → Quadro generale del sistema: P&L, posizioni, segnali</li>
          <li><strong>Signals</strong> → Analizza i segnali LLM per ogni ticker</li>
          <li><strong>Trading</strong> → Verifica posizioni aperte e storico ordini</li>
          <li><strong>Strategies</strong> → Controlla lo stato di validazione delle strategie (gates, sensitivity, equity curve)</li>
          <li><strong>Backtest</strong> → Esamina i risultati dei test storici (IC, ICIR, bucket analysis)</li>
          <li><strong>Performance</strong> → Monitora il rendimento cumulativo e mensile</li>
          <li><strong>News</strong> → Le notizie che alimentano il sistema di sentiment</li>
          <li><strong>LLM</strong> → I pesi dei modelli e il feedback per segnale</li>
          <li><strong>Config</strong> → Personalizza watchlist e parametri di rischio</li>
          <li><strong>Admin</strong> → Kill switch e modalità operativa</li>
        </ol>
      </div>

      <div style={cardStyle}>
        <h2 style={h2Style}>Come Funziona il Sistema</h2>
        <h3 style={h3Style}>Pipeline</h3>
        <p style={pStyle}>
          Notizie (GDELT/RSS) → LLM Ensemble (kimi, qwen, deepseek, glm) → Sentiment Score → Signal Aggregation → Risk Check → Execution (Alpaca paper)
        </p>
        <h3 style={h3Style}>Strategie validate</h3>
        <ul style={{ margin: '0 0 10px', paddingLeft: 20, lineHeight: 2, color: 'var(--text-muted)', fontSize: 13 }}>
          <li><strong>S1 (Momentum, 40%)</strong> — Time-series cross-asset, OOS Sharpe 0.51</li>
          <li><strong>S2 (VRP, 30%)</strong> — In sviluppo (Fase D)</li>
          <li><strong>S4 (News, 10%)</strong> — In sviluppo (Fase E)</li>
          <li><strong>S3 (XSM)</strong> — R&D sleeve, gate 3&5 FALLITI, non nel portfolio</li>
        </ul>
        <h3 style={h3Style}>Parametri di rischio</h3>
        <p style={pStyle}>
          Stop-loss 2%, max drawdown 10%, max esposizione 50%, signal freshness 30 min
        </p>
        <h3 style={h3Style}>Frequenza</h3>
        <p style={pStyle}>
          Segnali ogni 15 minuti, performance ogni giorno alle 22:00 UTC
        </p>
      </div>

      <div style={cardStyle}>
        <h2 style={h2Style}>Metriche Chiave</h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
          {[
            { name: 'OOS Sharpe', desc: 'Rendimento risk-adjusted out-of-sample. > 0.5 = buona, > 1.0 = eccellente' },
            { name: 'IC', desc: 'Information Coefficient, correlazione predizione-rendimento. > 0.05 = utile' },
            { name: 'ICIR', desc: 'IC normalizzato per deviazione standard. > 0.3 = consistente' },
            { name: 'Max Drawdown', desc: 'Massima perdita dal picco. < 20% = accettabile' },
            { name: 'Confidence', desc: 'Concordanza tra modelli LLM. > 0.7 = alta affidabilità' },
          ].map((m) => (
            <div key={m.name} style={{
              background: 'var(--bg)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              padding: '12px 14px',
            }}>
              <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4 }}>{m.name}</div>
              <div style={{ color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.5 }}>{m.desc}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={cardStyle}>
        <h2 style={h2Style}>Aiuto Contestuale</h2>
        <p style={pStyle}>
          Ogni pagina ha un pulsante <strong style={{ background: '#3b82f6', color: 'white', borderRadius: '50%', padding: '1px 6px', fontSize: 12 }}>?</strong> in alto a destra. Cliccalo per aprire un pannello con la documentazione specifica di quella pagina.
        </p>
      </div>
    </div>
  )
}
