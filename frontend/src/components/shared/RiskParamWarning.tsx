/**
 * Pure presentational component for risk parameter safety warnings (F0-3).
 *
 * Shows explicit warnings when stop-loss or max-drawdown exceed the 10% safety threshold.
 * Intended for use in Config.tsx alongside risk sliders.
 *
 * Thresholds:
 *   stop-loss  > 10% (0.10 as decimal)  → high-risk warning
 *   drawdown   > 10% (as integer %)     → high-risk warning
 */

interface Props {
  stopLoss: number   // decimal, e.g. 0.15 = 15%
  drawdown: number   // percent integer, e.g. 15 = 15%
}

export function RiskParamWarning({ stopLoss, drawdown }: Props) {
  const stopLossHigh = stopLoss > 0.10
  const drawdownHigh = drawdown > 10

  if (!stopLossHigh && !drawdownHigh) return null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {stopLossHigh && (
        <div
          role="alert"
          data-testid="stop-loss-warning"
          style={{
            padding: '8px 12px',
            background: '#7f1d1d',
            border: '1px solid #dc2626',
            borderRadius: 6,
            color: '#fca5a5',
            fontSize: 12,
          }}
        >
          ⚠ High-risk value: stop-loss of {(stopLoss * 100).toFixed(0)}% exceeds the 10% safety threshold.
          Paper and preflight use only — does not authorize live trading.
        </div>
      )}
      {drawdownHigh && (
        <div
          role="alert"
          data-testid="drawdown-warning"
          style={{
            padding: '8px 12px',
            background: '#7f1d1d',
            border: '1px solid #dc2626',
            borderRadius: 6,
            color: '#fca5a5',
            fontSize: 12,
          }}
        >
          ⚠ High-risk value: max drawdown of {drawdown.toFixed(0)}% exceeds the 10% safety threshold.
          Paper and preflight use only — does not authorize live trading.
        </div>
      )}
    </div>
  )
}
