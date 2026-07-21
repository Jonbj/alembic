# Alembic Android Read-Only Monitor — Product and Technical Design

**Date:** 2026-07-21  
**Status:** Approved design; implementation not started  
**Roadmap:** native child issues `#91`–`#99` of GitHub issue `#21`; live issue state and native blockers are authoritative  
**Target:** private installation on a Google Pixel 9 with stock Android, portrait-first, LAN-only for the MVP

## 1. Outcome

Build a small Android application that answers four questions without exposing any trading control:

1. Is Alembic healthy and expected to be running now?
2. Is the portfolio gaining or losing value, over the selected period?
3. Which open positions currently drive exposure and P&L?
4. Has anything occurred that requires the operator's attention?

The app is a monitor, not a mobile version of the full web cockpit. It must remain useful in under thirty seconds, tolerate temporary network loss, and be incapable of changing strategies, risk configuration, operating mode, orders, positions, or kill-switch state.

## 2. Decisions approved by the product owner

| Area | Decision |
| --- | --- |
| Audience | Private use by the owner and a small number of separately provisioned trusted operators |
| Distribution | Signed APK from a private repository release; no public Play Store release in the MVP |
| Platform | Native Kotlin and Jetpack Compose in `mobile/android/` |
| Navigation | Four destinations: Stato, Andamento, Portafoglio, Eventi |
| Primary performance truth | Broker NAV mark-to-market; realized and unrealized P&L are secondary breakdowns |
| Strategy data | Show lifecycle/mode/allocation only; no strategy-level P&L in the MVP |
| Interaction | No domain mutation or emergency action, including kill switch |
| Authentication | Separate monitor users, short access JWT, rotating device-bound refresh session |
| Push | Server-generated critical/warning/recovery notifications through FCM |
| Network | LAN-only MVP, HTTPS release traffic via a local CA; configurable base URL for future cloud migration |
| Offline | Protected local cache; visible age and offline status; purge on logout/revocation |
| Privacy | Biometric/device credential gate; generic lock-screen notifications; no analytics or Crashlytics |
| Language | Italian UI; technical identifiers in English; USD values; device-local time with ET context where useful |
| Reference device | Pixel 9, stock Android, portrait |

## 3. Repository analysis and data gaps

The web dashboard already proves that the required data exists, but its endpoints are not a safe or coherent mobile contract.

| Existing source | Useful data | Gap to close for mobile |
| --- | --- | --- |
| `GET /api/system/readiness` | Redis/DB health, kill switch, signal/cycle age | No market calendar; raw stale flags are misleading outside expected windows; no stable enum or `as_of` |
| `GET /api/performance/pnl` | Alpaca daily equity and daily/monthly P&L | Direct broker request per call; no unified current snapshot, drawdown, exposure, freshness, or explicit source metadata |
| `GET /api/performance/daily` | Realized trade P&L, daily NAV enrichment, beta-scaled SPY benchmark | Combines different sources; NAV snapshots currently depend on the daily 22:30 risk job |
| `GET /api/performance/weekly` | Live account enrichment, capital efficiency, regime | Cache semantics and breadth are designed for the web report, not a fast mobile summary |
| `GET /api/positions` | Live positions and unrealized P&L | No portfolio weight or coherent snapshot timestamp; broker request per call |
| `GET /api/orders`, `/api/decisions` | Broker lifecycle and decision audit | Too noisy; no stable operator-event model, cursor, incident status, or recovery |
| `GET /api/strategies` | Lifecycle, allocation, authorization | Must be reduced to read-only display fields and captured with the same snapshot timestamp |
| Current JWT login | Username/password, 24-hour admin bearer token | One admin identity, no audience/scope, no refresh rotation, and the same credential can call writes |
| Docker ports 3000/8001 | LAN access | Plain HTTP and no mobile-specific TLS endpoint |
| Telegram notifier | Existing alert transport abstraction | No persisted incident/outbox, per-device delivery, recovery notification, or privacy-safe mobile payload |

Additional constraints discovered in code:

- The active order path is the portfolio orchestrator; the app must never contact Alpaca directly.
- `risk_reports` is daily, so it cannot by itself meet five-minute risk alerting or current-state requirements.
- `portfolio_daily_state` is aggregate and strategy attribution is not consistently historical; strategy P&L remains out of scope.
- A process inside the Alembic host cannot guarantee notification when that entire host or its network is down. True host-down alerting requires an external uptime monitor in the future cloud deployment.

## 4. Information selection

### 4.1 Information that belongs in the app

| Information | Why it is primary | Presentation |
| --- | --- | --- |
| Operational state | First safety question | Large status banner with reason and `as_of` |
| Operating mode | Prevent confusion between paper and future live money | Persistent badge; unknown is critical |
| Current NAV | Authoritative portfolio value | Large USD figure |
| Today's NAV change | Best short-horizon outcome including open positions | USD and percent, with source label |
| Current drawdown | Direct loss/risk context | Percent plus configured limit |
| Gross exposure and cash | Shows how much capital is actually deployed | Percent/amount with limit where defined |
| Last signal and cycle age | Pipeline liveness | Human duration, interpreted using schedule |
| Open-position count and unrealized P&L | Current portfolio pressure | Summary plus position list |
| Period portfolio performance | Answers “come sta andando?” | NAV curve and period metrics |
| Exposure-adjusted benchmark and alpha | Avoids unfair comparison with fully invested SPY | Optional overlay and period summary |
| Significant events | Explains state changes without raw logs | Deduplicated event feed |
| Active strategies, mode, allocation | Governance context | Compact read-only summary |

### 4.2 Information deliberately excluded

- Raw news, LLM responses, model weights, prompts, confidence distributions, quality labeling, backtests, validation internals, configuration, and logs.
- Every generated signal and every normal `SKIP` decision.
- Strategy-level performance until attribution is reliable and explicitly specified.
- Any action that changes Alembic, including kill switch, mode, approvals, order cancellation, watchlist, or alert thresholds.
- Broker credentials, admin API keys, service-account credentials, signing keys, and database/Redis details.

## 5. Canonical financial semantics

Every monetary/percentage metric includes `source`, `as_of`, and where applicable `period_start`/`period_end`. Missing data is `null` with a machine-readable reason; the server must never substitute zero for unavailable broker data.

| Metric | Definition |
| --- | --- |
| `nav` | Current broker account equity. This is the headline portfolio value. |
| `nav_change_today` | Broker-supplied mark-to-market day profit/loss where available; otherwise unavailable, not reconstructed from closed trades. |
| `portfolio_return` | `(nav_end / nav_start) - 1` over the selected period, using an anchor immediately before the period. |
| `realized_pnl` | Sum of local closed-trade `net_pnl` for the stated period. Supporting breakdown only. |
| `unrealized_pnl` | Sum of current broker position `unrealized_pl`. Supporting breakdown only. |
| `gross_exposure` | `sum(abs(position.market_value)) / nav`; nullable when NAV is unavailable/non-positive. |
| `cash_pct` | Broker cash divided by NAV, not `1 - gross_exposure` because short/leverage states can violate that identity. |
| `current_drawdown` | Non-negative loss magnitude from the all-time/high-water NAV relevant to the configured risk rule. `0.054` renders as `5.4%`. |
| `max_drawdown` | Maximum peak-to-trough loss magnitude within the selected NAV series, including the pre-period anchor. |
| `benchmark_return` | SPY return multiplied by average portfolio exposure over the period, using the existing benchmark domain rule. |
| `alpha` | `portfolio_return - benchmark_return`; descriptive monitoring, not proof of statistical alpha. |
| `position_weight` | `abs(market_value) / nav`; nullable when NAV is unavailable/non-positive. |

The UI must label NAV performance and realized trade P&L separately. It must never add realized P&L to unrealized P&L and present that sum as NAV performance.

## 6. Operational-state model

### 6.1 States and precedence

Precedence is highest severity first:

| API enum | Italian label | Trigger |
| --- | --- | --- |
| `blocked` | BLOCCATO | Kill switch active, unknown operating mode, DB unavailable, Redis unavailable, or snapshot cannot establish safety state |
| `degraded` | DEGRADATO | Redis not writable, expected signal/cycle late, broker data stale, order rejection, or another non-blocking active incident |
| `paused` | IN PAUSA | Market/pipeline window closed or holiday while infrastructure and safety state are healthy |
| `operational` | OPERATIVO | Infrastructure healthy and expected pipeline activity within its freshness budget |

A critical fault remains `blocked` outside market hours. `paused` suppresses only schedule-dependent staleness, never infrastructure, safety, or unknown-state failures.

### 6.2 Schedule context

The backend, not each client, returns:

- `market_phase`: `open`, `pre_market`, `after_hours`, `closed`, or `holiday`;
- `pipeline_expected`: boolean;
- `next_expected_activity_at`;
- `timezone`: `America/New_York` for market semantics;
- per-component `freshness`: `fresh`, `aging`, `stale`, `not_expected`, or `unknown`.

Use an authoritative market calendar/clock already available through the broker. Static Monday-Friday logic is insufficient because of holidays and early closes.

### 6.3 Freshness budgets

| Data | During expected window | Outside expected window |
| --- | --- | --- |
| Monitoring snapshot | fresh ≤90s; aging ≤5m; stale >5m | fresh ≤10m; aging ≤30m; stale >30m |
| Portfolio cycle | compare with configured schedule plus 8m grace | `not_expected` |
| Signal batch | compare with configured schedule plus 8m grace | `not_expected` |
| Positions/account | fresh ≤90s; stale >5m | fresh ≤10m; stale >30m |
| Historical curve | fresh ≤15m when market open; ≤24h when closed | same |

Budgets are server configuration returned as metadata, not duplicated constants in Android.

## 7. UX and information architecture

### 7.1 Global behavior

- Single activity, four bottom-navigation destinations.
- Portrait-first on Pixel 9; landscape/tablet must remain functional without bespoke optimization.
- Italian copy, USD formatting from API currency, timestamps in device timezone; event detail may also show ET.
- Dark by default with “follow system” option.
- Color is never the only signal: icon, label, sign, and accessible content description are mandatory.
- Every screen has three explicit modes: live, cached/offline, and unavailable/empty.
- `Aggiornato …` is always visible. Cached content is never silently presented as current.
- Pull-to-refresh is the only refresh action; there are no domain mutation controls.

### 7.2 Stato

```text
┌─────────────────────────────────┐
│ Alembic                 PAPER   │
│ ● OPERATIVO                      │
│ Aggiornato 15:42 · mercato aperto│
├─────────────────────────────────┤
│ NAV             $110,307.36     │
│ Oggi          -$115.60  -0.10%  │
│ Drawdown           1.45% / 5.0% │
│ Esposizione      30.2% / 50.0%  │
├─────────────────────────────────┤
│ 7 posizioni   Unreal. -$97.14   │
│ Cash $76,998                   > │
├─────────────────────────────────┤
│ Pipeline                        │
│ Segnale 8m · Ciclo 5m · DB/Redis OK│
├─────────────────────────────────┤
│ Strategie                       │
│ S1 supervised_paper  90%        │
│ S4 paper             10%        │
└─────────────────────────────────┘
```

If state is degraded/blocked, the status banner expands to the highest-severity reason and links to the matching event detail. It never suggests a write action.

### 7.3 Andamento

Controls: `1S`, `1M` (default), `3M`, `6M`, `1A`, `Tutto`.

Header metrics:

- portfolio return and absolute NAV change;
- max drawdown;
- exposure-adjusted benchmark return;
- alpha;
- realized P&L as a clearly separated supporting value.

Chart defaults to NAV. Benchmark and drawdown are optional overlays. Each point is reachable through accessibility semantics or a summary table; the chart cannot be the only representation.

### 7.4 Portafoglio

Rows are sorted by worst P&L percentage first, then absolute market value. Summary shows position count, gross exposure, and total unrealized P&L.

Immediate row fields: ticker, portfolio weight, market value, unrealized P&L USD/percent. Detail fields: quantity, average entry price, current price, entry time, and data age. No strategy attribution, LLM reasoning, or news in the MVP.

### 7.5 Eventi

Default window: seven days; cursor pagination may load up to thirty days. Feed includes:

- alert incident opened/escalated/recovered;
- order submitted/filled/rejected/canceled;
- position opened/closed;
- `BUY`, `SELL`, and `HALT` decisions.

Normal `SKIP*`, successful empty cycles, raw logs, and signal chatter are excluded. Filters: `Tutti`, `Critici`, `Trading`, `Sistema`. An incident and its recovery are one timeline item with state history, not two unrelated rows.

## 8. Mobile API contract

### 8.1 General rules

- Base path `/api/mobile/v1`.
- JSON field names and enum values are English `snake_case`; copy keys may be localized by Android.
- UTC ISO-8601 timestamps with `Z`.
- Money is a JSON number plus response-level `currency`; percentages are fractions (`0.0545`, not `5.45`).
- All successful read responses include `contract_version`, `as_of`, `data_age_seconds`, and source/degradation metadata.
- Additive fields are backward compatible. Removing/renaming/changing semantics requires `/v2`.
- Responses include `min_supported_app_version` and `latest_app_version`.
- Support `ETag`/`If-None-Match` on snapshot, performance, positions, and events.
- The API is a projection over Alembic; it does not leak raw broker objects or DB rows.

### 8.2 Authentication

`POST /api/mobile/v1/auth/login`

```json
{
  "username": "monitor-stefano",
  "password": "<secret>",
  "device": {
    "installation_id": "uuid-generated-on-device",
    "name": "Pixel 9",
    "app_version": "1.0.0"
  }
}
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "expires_in": 900,
  "refresh_token": "<opaque-random-token>",
  "refresh_expires_at": "2026-08-20T12:00:00Z",
  "user": {"id": "uuid", "username": "monitor-stefano"},
  "device_id": "uuid"
}
```

`POST /api/mobile/v1/auth/refresh` rotates the opaque refresh token. Reuse of a rotated token revokes that session family and requires login. `POST /api/mobile/v1/auth/logout` revokes the current device session and its push registration.

Access JWT requirements:

```json
{
  "sub": "monitor-user-uuid",
  "aud": "alembic-mobile",
  "type": "access",
  "scope": ["monitor:read", "monitor:device"],
  "device_id": "uuid",
  "jti": "uuid",
  "exp": 1787228100
}
```

The existing admin dependency must reject this audience. Mobile dependencies must reject admin API keys and legacy admin JWTs unless a future explicit policy says otherwise.

### 8.3 Snapshot

`GET /api/mobile/v1/snapshot`

```json
{
  "contract_version": 1,
  "as_of": "2026-07-21T13:42:15Z",
  "data_age_seconds": 32,
  "currency": "USD",
  "min_supported_app_version": "1.0.0",
  "latest_app_version": "1.0.0",
  "operational": {
    "state": "operational",
    "primary_reason": null,
    "mode": "paper",
    "market_phase": "open",
    "pipeline_expected": true,
    "next_expected_activity_at": "2026-07-21T13:52:00Z",
    "active_incident_count": 0
  },
  "portfolio": {
    "nav": 110307.36,
    "nav_change_today": -115.60,
    "nav_return_today": -0.001047,
    "realized_pnl_today": -18.46,
    "unrealized_pnl": -97.14,
    "cash": 76998.12,
    "cash_pct": 0.69799,
    "gross_exposure": 0.30201,
    "gross_exposure_limit": 0.50,
    "current_drawdown": 0.0145,
    "drawdown_limit": 0.05,
    "open_positions": 7,
    "source": "alpaca_paper"
  },
  "pipeline": {
    "database": {"status": "fresh", "age_seconds": 0},
    "redis": {"status": "fresh", "age_seconds": 0, "writeable": true},
    "signal": {"status": "fresh", "age_seconds": 480},
    "portfolio_cycle": {"status": "fresh", "age_seconds": 300},
    "broker": {"status": "fresh", "age_seconds": 32}
  },
  "strategies": [
    {"id": "S1", "mode": "supervised_paper", "allocation_pct": 0.90, "approved": true},
    {"id": "S4", "mode": "paper", "allocation_pct": 0.10, "approved": true}
  ],
  "degradations": []
}
```

The snapshot is produced server-side on a cadence and read atomically from a cache/read model. The HTTP request must not fan out to Alpaca, Redis, and multiple DB queries independently.

### 8.4 Performance

`GET /api/mobile/v1/performance?period=1w|1m|3m|6m|1y|all`

```json
{
  "contract_version": 1,
  "as_of": "2026-07-21T13:42:15Z",
  "data_age_seconds": 32,
  "currency": "USD",
  "period": "1m",
  "period_start": "2026-06-20T00:00:00Z",
  "period_end": "2026-07-21T13:42:15Z",
  "summary": {
    "nav_start": 109850.00,
    "nav_end": 110307.36,
    "nav_change": 457.36,
    "portfolio_return": 0.004164,
    "realized_pnl": 132.40,
    "max_drawdown": 0.0182,
    "avg_gross_exposure": 0.287,
    "spy_return": 0.021,
    "benchmark_return": 0.006027,
    "alpha": -0.001863
  },
  "points": [
    {"at": "2026-06-20T20:00:00Z", "nav": 109850.00, "drawdown": 0.0, "benchmark_nav": 109850.00}
  ],
  "degradations": []
}
```

The server downsamples longer periods to a maximum of 500 ordered points while retaining first/last and extrema. Benchmark fields are nullable as a group if SPY or exposure history is unavailable.

### 8.5 Positions

`GET /api/mobile/v1/positions`

```json
{
  "contract_version": 1,
  "as_of": "2026-07-21T13:42:15Z",
  "data_age_seconds": 32,
  "currency": "USD",
  "summary": {"count": 1, "market_value": 6234.10, "unrealized_pnl": -77.88, "gross_exposure": 0.0565},
  "items": [
    {
      "symbol": "MSFT",
      "qty": 12.3456,
      "avg_entry_price": 511.22,
      "current_price": 505.00,
      "market_value": 6234.10,
      "position_weight": 0.0565,
      "unrealized_pnl": -77.88,
      "unrealized_return": -0.01234,
      "entry_time": "2026-07-20T15:22:00Z"
    }
  ],
  "degradations": []
}
```

### 8.6 Events

`GET /api/mobile/v1/events?category=all|critical|trading|system&days=7&cursor=<opaque>&limit=50`

```json
{
  "contract_version": 1,
  "as_of": "2026-07-21T13:42:15Z",
  "items": [
    {
      "id": "uuid",
      "kind": "alert_incident",
      "category": "system",
      "severity": "critical",
      "status": "open",
      "occurred_at": "2026-07-21T13:40:00Z",
      "updated_at": "2026-07-21T13:42:00Z",
      "resolved_at": null,
      "title": "Ciclo di portafoglio in ritardo",
      "summary": "Nessun ciclo completato da 18 minuti durante la finestra operativa.",
      "entity": {"type": "portfolio_cycle", "id": null},
      "measure": {"value": 1080, "unit": "seconds", "threshold": 900},
      "history": [{"state": "opened", "at": "2026-07-21T13:40:00Z"}]
    }
  ],
  "next_cursor": null
}
```

Cursor order is `(occurred_at DESC, id DESC)`. Cursors are opaque and signed. Event title/summary are safe, concise operator copy, not unbounded raw `reason`/log strings.

### 8.7 Device registration

`POST /api/mobile/v1/devices` is idempotent by `installation_id` for the authenticated user/device session.

```json
{
  "installation_id": "uuid",
  "firebase_installation_id": "opaque-fid",
  "name": "Pixel 9",
  "app_version": "1.0.0",
  "push_enabled": true
}
```

`DELETE /api/mobile/v1/devices/{device_id}` revokes only that user's device. These endpoints require `monitor:device`; no other mobile endpoint may mutate server state.

### 8.8 Errors

```json
{
  "error": {
    "code": "snapshot_unavailable",
    "message": "Monitoring snapshot is temporarily unavailable.",
    "request_id": "uuid",
    "retryable": true,
    "details": {}
  }
}
```

Required status behavior:

- `400` invalid request;
- `401` absent/expired/invalid access token;
- `403` valid identity without required audience/scope;
- `409` refresh-token reuse/session conflict;
- `426` app below minimum supported version;
- `429` rate limited;
- `503` no safe snapshot available, with cached client data left intact.

## 9. Backend design

### 9.1 Components

```text
Alpaca / DB / Redis / registry / market clock
                     │
             Snapshot builder (60s)
                     │
        Redis atomic Monitoring snapshot
          │                    │
 Mobile API reads       5m historical sample
          │                    │
 Android cache      portfolio_monitor_snapshots

Worker/order/risk/health observations
                     │
             Incident evaluator
                     │
       mobile_events + notification outbox
                     │
              FCM dispatcher ───> devices
```

The mobile API should be a deep read-model boundary: clients ask for monitoring concepts, not the internals required to assemble them.

### 9.2 Persistence

Allocate the next migration number at implementation time (currently `041`). Proposed tables:

- `monitor_users`: UUID, username unique, bcrypt password hash, enabled, timestamps.
- `monitor_sessions`: UUID, user/device, refresh token hash, family ID, expiry, last use, rotated/revoked timestamps. Never store raw refresh tokens.
- `monitor_devices`: UUID, user, installation ID, Firebase Installation ID, device/app metadata, push state, last seen, revoked timestamp.
- `portfolio_monitor_snapshots`: timestamp, broker environment, NAV, previous-close equity/day P&L, cash, gross exposure, unrealized P&L, drawdown, mode, source health. Persist every five minutes during the expected window and at material state transitions; define retention/downsampling.
- `mobile_events`: UUID, stable fingerprint, kind/category/severity/status, first/last observation, resolution, safe structured details, optional source entity reference.
- `mobile_event_history`: event ID, state transition, severity, timestamp, safe details.
- `mobile_notification_deliveries`: event/device, transition, attempt count, next attempt, provider message ID, sent/failed timestamps and redacted error code.

Unique constraints enforce one active incident per fingerprint and one delivery per `(event_id, device_id, transition)`.

### 9.3 Alert incident rules

Initial notification set:

| Incident | Severity | Detection target | Resolution |
| --- | --- | --- | --- |
| Kill switch active | critical | event-driven, ≤1m | both kill-switch keys absent and explicit state observation |
| Unknown operating mode | critical | snapshot, ≤1m | recognized mode observed |
| DB/Redis unavailable | critical | health cadence, ≤5m, best effort | healthy for two consecutive observations |
| Portfolio cycle late | warning, escalate critical after configured duration | ≤5m during expected window | new successful cycle |
| Broker snapshot stale/unavailable | warning/critical by age | ≤5m | fresh broker snapshot |
| Drawdown limit breached | critical | ≤5m | below configured recovery threshold, not merely below trigger by rounding |
| Gross exposure limit breached | critical | ≤5m | below limit for two observations |
| Order rejected/error | critical | event-driven, ≤1m | terminal event remains historical; no synthetic recovery |
| Order canceled | warning unless expected | event-driven, ≤1m | terminal historical event |

Fingerprint examples: `system:killswitch`, `pipeline:portfolio_cycle_late`, `risk:drawdown:<environment>`, `order:<broker_order_id>:rejected`.

Opening, escalation, and recovery can each notify once. Repeated observations update `last_observed_at`. Recovery is attached to the same incident. Notification retries use bounded exponential backoff and do not duplicate a successfully acknowledged transition.

### 9.4 FCM privacy and behavior

- Use Firebase Admin SDK only on the trusted Alembic server.
- Prefer Firebase Installation IDs if supported by the selected stable SDK; isolate provider identifiers behind a delivery adapter.
- FCM data payload: opaque `event_id`, `transition`, `severity`, and contract/deep-link version only.
- Lock-screen title/body are generic: “Alembic richiede attenzione” or “Alembic è tornato operativo”.
- The app fetches authenticated event detail after unlock; no NAV, P&L, ticker, reason, username, URL, or token in FCM.
- Firebase Analytics, delivery export, Crashlytics, and marketing/topic messaging are disabled/not integrated.
- Revoked/unregistered provider identifiers are disabled after terminal provider errors.

## 10. Security and threat model

### 10.1 Trust boundaries

| Asset | Location | Rule |
| --- | --- | --- |
| Alpaca credentials | Alembic server only | Never returned or embedded |
| Firebase service account | Alembic server secret only | Never in repo/APK |
| APK signing key | CI secret/secure offline backup | Never in repo or runtime container |
| Monitor password hash | Postgres | Bcrypt; no plaintext |
| Refresh token | Raw only on device; hash on server | Rotating, family reuse detection |
| Access token | Device memory/protected store | 15-minute expiry, mobile audience |
| Local encryption key | Android Keystore | Non-exportable; user-auth policy where practical |
| Cached financial data | App-private Room store | Encrypt sensitive payloads/columns with AES-GCM keys from Keystore; purge on logout/revocation |

Do not use deprecated `androidx.security.crypto` APIs for new code. Use Android Keystore directly for key material and standard authenticated encryption. Never implement a permissive hostname verifier, `trust-all` trust manager, or log interceptor that records authorization headers/bodies in release builds.

### 10.2 Local authentication

- Initial server login uses username/password over trusted HTTPS.
- Subsequent app entry and return after five minutes in background require `BiometricPrompt` with device credential fallback.
- Device lock, key invalidation, or biometric enrollment change must fail closed and require login as appropriate.
- Recent-app previews use `FLAG_SECURE` or a protected placeholder so financial data is not captured in the task switcher/screenshots.
- Logout revokes session/device best effort, clears tokens and encrypted cache locally even if server revocation cannot be reached; server-side expiry/revocation completes protection.

### 10.3 Authorization invariants

Automated tests must enumerate every non-GET admin/config/strategy/weight/labeling endpoint and prove a monitor access token receives `403`. Authentication, refresh, logout, and device registration are the only allowed mobile writes. The API must not infer authorization from route naming or the absence of UI controls.

### 10.4 LAN TLS

- Release flavor: HTTPS only; cleartext disabled.
- Debug flavor: cleartext may be allowed only for explicit emulator/development hosts.
- Provide a stable LAN hostname and internal CA certificate. Configure a domain-scoped Android Network Security Configuration to trust the intended local CA/user trust anchor; do not trust arbitrary user CAs for every host.
- Install the CA on the Pixel as an operator step and verify hostname/SAN matching.
- Future cloud flavor uses a public CA and removes the LAN trust anchor without changing API paths.

## 11. Android architecture

Use one Gradle application module initially; organize by clear packages/features rather than premature multi-module overhead.

```text
mobile/android/app/src/main/java/com/jonbj/alembic/monitor/
├── app/                 # Application, activity, navigation, DI
├── core/model/          # app/domain models and enums
├── core/network/        # DTOs, auth interceptor, refresh serialization
├── core/database/       # Room entities/DAO and encrypted value adapters
├── core/security/       # Keystore, biometric gate, session vault
├── data/                # repositories; network + cache source of truth
├── feature/status/
├── feature/performance/
├── feature/portfolio/
├── feature/events/
├── feature/login/
└── push/                # FirebaseMessagingService and deep links
```

Technical baseline:

- Kotlin, Jetpack Compose, Material 3, single activity, Navigation 3 (latest stable at implementation).
- Unidirectional data flow: ViewModel `StateFlow` → immutable UI state; UI events upward.
- Repository per monitoring area; composables never call network/Room/Firebase directly.
- Coroutines/Flow; lifecycle-aware collection.
- Room for offline cache; DataStore only for non-sensitive preferences.
- Android Keystore + `BiometricPrompt` for protected session/cache access.
- Retrofit/OkHttp or an equivalently testable typed HTTP client with Kotlin serialization; one shared refresh mutex prevents token-refresh storms.
- Hilt is acceptable for dependency injection; keep boundaries replaceable with fakes.
- WorkManager performs opportunistic cache refresh/version check, not exact alert delivery. FCM handles push.
- No third-party behavioral analytics SDK.

The exact minimum/target SDK and dependency versions are selected from stable releases when implementation starts. Pixel 9 is the acceptance device; avoid alpha dependencies unless a separate decision records the reason.

### 11.1 Refresh and cache policy

- Foreground and pipeline expected: refresh snapshot/positions every 60 seconds.
- Foreground and pipeline not expected: every five minutes.
- Pull-to-refresh always available when authenticated.
- Background periodic work is opportunistic and battery-aware; it is not used to claim notification SLOs.
- Cache latest snapshot, latest selected performance curves, latest positions, and 30 days of events.
- On 401: attempt one serialized refresh, replay once, then enter re-login state.
- On network/5xx: keep cache and surface offline/stale banner.
- On 426: show mandatory update screen; cached data may be shown only if its contract is still declared readable.

## 12. Non-functional requirements

| Requirement | Acceptance target |
| --- | --- |
| Read-only safety | Zero mobile credentials can invoke a trading/config/admin mutation |
| Snapshot consistency | All headline values share one snapshot ID/`as_of`; no client-side multi-endpoint join |
| Snapshot API latency | p95 ≤500ms on LAN when read model exists |
| Foreground freshness | Display snapshot no more than 90s old in normal operation |
| Notification latency | Kill switch/order failure ≤1m; pipeline/risk ≤5m, measured server observation→FCM acceptance |
| Notification noise | One notification per incident transition/device; no repeat for unchanged observation |
| Offline startup | Cached status visible after local auth within 2s on Pixel 9 |
| Accessibility | TalkBack labels, scalable text, 48dp targets, non-color semantics, chart summary alternative |
| Privacy | No financial detail on lock screen/task switcher/logs/FCM payload |
| Reliability | Process death, rotation, token expiry, FCM token/FID rotation, and network switching do not corrupt session/cache |
| Compatibility | Server can require update via explicit version metadata; additive v1 fields tolerated |

## 13. Testing strategy

### Backend

- Unit: metric formulas, state precedence, calendar-aware freshness, incident fingerprints/transitions, safe copy, downsampling, refresh rotation/reuse detection.
- Authorization matrix: monitor/admin/invalid/expired/revoked credentials across every route class.
- API contract: Pydantic response schemas, OpenAPI snapshot, nullable/degraded cases, ETag, cursor stability, 426 behavior.
- Store integration: migration, unique incident/delivery constraints, token hashes, event pagination, snapshot retention.
- Worker: fake Alpaca/Redis/DB, cadence, broker failure returns null/degradation rather than zero, incident recovery and outbox retries.
- FCM adapter: fake provider; never call external FCM in CI; assert privacy-safe payload and terminal-token handling.

### Android

- Unit: DTO mapping, money/percent formatting, operational state rendering, token refresh mutex, cache age, sort order, version compatibility.
- Repository tests with fake network/Room/clock covering live→offline→recovered and logout purge.
- Compose UI: all four screens in loading/live/degraded/blocked/paused/offline/empty/426 states; large font and TalkBack semantics.
- Navigation/deep link: generic push opens biometric gate then the matching event, never displays detail before unlock.
- Instrumented security: release rejects HTTP/bad hostname; secrets absent from logs; biometric timeout; task-switcher protection.
- FCM: provider identifier rotation and notification permission denial; app remains usable without push and exposes the disabled state.
- Device acceptance on Pixel 9: install signed APK, local CA, login, background delivery, offline cache, update with same signing key.

### End-to-end acceptance scenarios

1. Healthy market-open system shows `OPERATIVO` and coherent NAV/positions with matching `as_of`.
2. Weekend shows `IN PAUSA`, not false stale warnings.
3. Kill switch fixture opens one critical incident and sends one generic push; unchanged state sends none; recovery sends one recovery push.
4. Monitor token calling every known mutation receives `403` and produces no side effect.
5. Broker unavailable returns nullable portfolio values with `blocked/degraded` reason, never `$0` NAV.
6. Network disconnected after a successful sync shows encrypted cached data with age and `OFFLINE` after biometric auth.
7. Expired access token rotates refresh once under concurrent requests; reused old refresh token revokes the family.
8. Logout clears local data and disables/revokes the device registration.
9. App below `min_supported_app_version` cannot interpret live payload and opens the private update path.

## 14. Deployment and operations

MVP prerequisites owned by the operator:

- stable LAN hostname and internal CA/reverse proxy;
- Firebase project with Cloud Messaging enabled, Android app registered, `google-services.json` supplied outside public artifacts, and server credential mounted as a secret;
- stable application ID, recommended `com.jonbj.alembic.monitor`, confirmed before first signed release;
- release signing key generated once, backed up securely, injected into CI secrets, and never regenerated casually;
- monitor user provisioned by a server-side command;
- Pixel notification permission granted and local CA installed.

CI produces tests, lint, debug artifact, signed release APK, SHA-256 checksum, version metadata, and release notes. A release job must verify the APK signature. Do not publish signing material or Firebase server credentials as artifacts.

Android developer verification is changing during 2026–2027. Direct sideloading remains viable for the MVP, but package/signing-key registration through Android Developer Console (including the limited-distribution path for small personal deployments) should be completed before broader/global enforcement.

## 15. Observability without analytics

Server metrics:

- snapshot build success/age/duration;
- active incidents by severity;
- outbox pending/oldest age;
- FCM accepted/failure counts by redacted code;
- registered/active/revoked devices;
- mobile API latency/status counts without financial payload logging;
- auth failure, refresh reuse, device revocation security counters.

The app keeps a bounded, redacted diagnostic log that the user can export manually. It excludes URL credentials, headers/tokens, response bodies, NAV/P&L/tickers, FCM identifiers, and password fields.

## 16. Explicit limitations and future work

Not part of the MVP:

- remote Internet access, public Play Store, self-service onboarding, password recovery, or public multi-tenant service;
- admin/emergency actions;
- widgets, Wear OS, tablets/landscape-specific layouts;
- non-Google push transports;
- strategy attribution/performance;
- external host/API-down monitoring.

Cloud deployment later must add public TLS, ingress/rate limiting, secret management, backup/restore, external uptime monitoring, and a deliberate remote-access threat review. The configurable base URL and versioned contract make that a deployment change rather than a mobile rewrite.

## 17. Primary references

- Android Developers, [Recommendations for Android architecture](https://developer.android.com/topic/architecture/recommendations)
- Android Developers, [Guide to app architecture](https://developer.android.com/topic/architecture)
- Android Developers, [Room persistence library](https://developer.android.com/training/data-storage/room/)
- Android Developers, [Android Keystore system](https://developer.android.com/privacy-and-security/keystore)
- Android Developers, [Network security configuration](https://developer.android.com/privacy-and-security/security-config)
- Android Developers, [Biometric authentication](https://developer.android.com/identity/sign-in/biometric-auth)
- Android Developers, [WorkManager](https://developer.android.com/reference/androidx/work/WorkManager)
- Firebase, [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- Firebase, [FCM for Android](https://firebase.google.com/docs/cloud-messaging/android/get-started)
- Firebase, [Send with the Admin SDK](https://firebase.google.com/docs/cloud-messaging/send/admin-sdk)
- Android Developers, [Sign your app](https://developer.android.com/studio/publish/app-signing)
- Android Developers, [Developer verification guidance](https://developer.android.com/developer-verification/guides)
