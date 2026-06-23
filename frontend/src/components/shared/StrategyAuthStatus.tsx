/**
 * Pure presentational component for strategy authorization state (F0-1).
 *
 * Shows the real authorization state returned by the strategy API:
 * mode, promotion_blocked, live_authorized, promotion_authorized, data_quality_warning.
 *
 * Fail-safe: if no auth fields are present, shows an explicit "unavailable" warning
 * rather than assuming any authorization.
 *
 * IMPORTANT: never renders "validated", "live-ready", or "authorized for live"
 * unless live_authorized=true is explicitly set by the API.
 */

interface Props {
  mode?: string
  promotion_blocked?: boolean
  live_authorized?: boolean
  promotion_authorized?: boolean
  data_quality_warning?: string
}

const MODE_LABEL: Record<string, string> = {
  supervised_paper: 'supervised_paper',
  paper: 'paper',
  research: 'R&D',
  disabled: 'disabled',
  live: 'live',
}

const MODE_BG: Record<string, string> = {
  supervised_paper: '#6d28d9',
  paper: '#1d4ed8',
  research: '#374151',
  disabled: '#6b7280',
  live: '#dc2626',
}

export function StrategyAuthStatus({
  mode,
  promotion_blocked,
  live_authorized,
  promotion_authorized,
  data_quality_warning,
}: Props) {
  const hasAuthField =
    mode !== undefined ||
    promotion_blocked !== undefined ||
    live_authorized !== undefined ||
    promotion_authorized !== undefined

  if (!hasAuthField) {
    return (
      <div
        role="alert"
        data-testid="auth-unavailable"
        style={{
          padding: '8px 12px',
          background: '#1e293b',
          border: '1px solid #475569',
          borderRadius: 6,
          color: '#94a3b8',
          fontSize: 12,
        }}
      >
        Authorization status unavailable — do not treat as approved.
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {/* Badge row */}
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {mode && (
          <span
            data-testid="mode-badge"
            style={{
              display: 'inline-block',
              padding: '2px 10px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
              background: MODE_BG[mode] ?? '#374151',
              color: 'white',
              letterSpacing: '0.04em',
              textTransform: 'lowercase',
            }}
          >
            {MODE_LABEL[mode] ?? mode}
          </span>
        )}

        {promotion_blocked === true && (
          <span
            data-testid="promotion-blocked-badge"
            style={{
              display: 'inline-block',
              padding: '2px 10px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
              background: '#92400e',
              color: '#fef3c7',
              letterSpacing: '0.04em',
            }}
          >
            promotion_blocked
          </span>
        )}

        {live_authorized === false && (
          <span
            data-testid="not-live-authorized"
            style={{
              display: 'inline-block',
              padding: '2px 10px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
              background: '#7f1d1d',
              color: '#fca5a5',
              letterSpacing: '0.04em',
            }}
          >
            live_authorized: false
          </span>
        )}

        {promotion_authorized === false && (
          <span
            data-testid="not-promotion-authorized"
            style={{
              display: 'inline-block',
              padding: '2px 10px',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
              background: '#7f1d1d',
              color: '#fca5a5',
              letterSpacing: '0.04em',
            }}
          >
            promotion_authorized: false
          </span>
        )}
      </div>

      {/* Promotion blocked warning */}
      {promotion_blocked === true && (
        <div
          role="alert"
          data-testid="promotion-blocked-warning"
          style={{
            padding: '8px 12px',
            background: '#451a03',
            border: '1px solid #92400e',
            borderRadius: 6,
            color: '#fef3c7',
            fontSize: 12,
          }}
        >
          ⚠ Promotion blocked. This strategy is not authorized for live promotion.
        </div>
      )}

      {/* Data quality / stale snapshot warning */}
      {data_quality_warning && (
        <div
          role="alert"
          data-testid="data-quality-warning"
          style={{
            padding: '8px 12px',
            background: '#422006',
            border: '1px solid #d97706',
            borderRadius: 6,
            color: '#fde68a',
            fontSize: 12,
          }}
        >
          {data_quality_warning}
        </div>
      )}
    </div>
  )
}
