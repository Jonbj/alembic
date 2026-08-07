# Android Monitor remediation brief — 2026-07-22

This document records the corrective implementation requirements found by the independent review of `83ed7a2...4d9fc67`. It is a design and acceptance artifact, not a progress tracker. Live state remains GitHub issue `#21` and its native children/dependencies.

## Authority and delivery model

The approved product scope remains defined by:

- `docs/superpowers/specs/2026-07-21-android-monitoring-app-design.md`
- `docs/superpowers/plans/2026-07-21-android-monitoring-app-implementation.md`
- `docs/adr/0001-native-android-monitoring-client.md`
- `docs/adr/0002-mobile-read-only-security-boundary.md`
- `docs/adr/0003-server-owned-alert-incidents-with-fcm-delivery.md`

For this remediation, live issue bodies and reopening comments refine the acceptance evidence required to close `#92`, `#93`, `#95`, `#98`, and `#99`.

The authoring development session must claim and implement one ready issue at a time, open a PR, and stop. It must not merge its own PR or manually close the issue. A separate review must approve both repository standards and specification compliance after all required checks are green.

## Canonical dependency order

Query the native graph before every ticket. The intended order is:

1. `#92` MOB-02 and `#93` MOB-03 are independently ready after `#91`.
2. `#95` MOB-05 is blocked by both `#92` and `#93`.
3. `#96` MOB-06 is blocked by `#93` and `#95`.
4. `#97` MOB-07 is blocked by `#94` and `#95`.
5. `#98` MOB-08 is blocked by `#96` and `#97`.
6. `#99` MOB-09 is blocked by `#98`.

## MOB-02 authentication remediation (`#92`)

### Required behavior

- Refresh rotation is one atomic database transaction. The old token row is selected and locked, validated, revoked/rotated, and the successor inserted before commit.
- Concurrent use of the same active refresh token produces exactly one successor. A losing concurrent request cannot create another active child.
- Reuse of any already rotated refresh token revokes every still-active session in its family before returning the authentication failure.
- The replay response must not claim revocation unless the revocation transaction succeeded.
- Monitor access JWTs retain the approved audience, token type, subject, device ID, JTI, expiry, and explicit scopes.
- A monitor access token remains unusable on every trading, order, admin, configuration, strategy, labeling, and weight mutation before side effects.
- The operator CLI supports creation, disabling and re-enabling a monitor user, revoking a specific session, revoking all user sessions, and revoking a device. It never prints password hashes, refresh tokens, access tokens, or other secrets.
- Existing administrator authentication remains behaviorally unchanged.

### Mandatory tests

- Successful login and normal refresh rotation.
- The old refresh token is rejected after rotation.
- After replay of the old token, the previously valid child refresh token is also rejected because the family was revoked.
- Two refresh attempts racing on the same token yield one success and one deterministic authentication failure, with one active successor at most.
- Failure between old-token update and successor insert rolls back the entire rotation.
- Expired, disabled-user, revoked-device, malformed and unknown refresh cases.
- Full route-matrix parameterization across all mutation router families, with side-effect spies or state assertions proving no mutation occurred.
- CLI tests for create, disable/enable, session revocation and device revocation, including redacted output.
- Existing admin-auth regression tests.

### Implementation constraints

- Do not solve races with a process-local lock; the guarantee must hold across API processes.
- Prefer an explicit store transaction API that owns connection acquisition and row locking instead of exposing transaction details to the route.
- Add or adjust database constraints/indexes only when they strengthen an invariant and are covered by forward migration tests.
- Do not change the Android client in the `#92` PR except shared contract fixtures strictly required by the backend tests.

## MOB-03 read-contract remediation (`#93`)

### Canonical public paths

The approved public read paths are:

- `GET /api/mobile/v1/snapshot`
- `GET /api/mobile/v1/performance`
- `GET /api/mobile/v1/positions`
- `GET /api/mobile/v1/events`

Authentication remains under `/api/mobile/v1/auth/*` and device operations under `/api/mobile/v1/devices/*`. Remove the accidental public `/read` segment rather than teaching the client a second contract.

### Required behavior and evidence

- The app-version gate must allow supported or absent versions according to the approved compatibility policy and must return a real 426 envelope for an older valid semantic version. It must not catch its own `HTTPException`.
- Malformed version values follow a deliberate, tested policy and never bypass an explicitly mandatory upgrade by accident.
- Events default to seven days and reject values above thirty days.
- Pagination uses an opaque authenticated/signed cursor. Tampering, expiry or query-filter mismatch is rejected deterministically. `next_cursor` is returned when more results exist.
- Snapshot headline values share the same snapshot ID and `as_of`; routes read the coherent server-owned snapshot/read model rather than independently fanning out to broker/Redis for each field.
- Performance calculations honor every approved period, broker NAV truth, nullable benchmark/alpha, nullable unavailable financial values and drawdown semantics.
- Error envelopes do not expose raw dependency exception messages.
- Contract tests exercise the exact public URLs used by Android.

## MOB-05 Android foundation remediation (`#95`)

- Android calls the canonical read paths and sends the required app-version header consistently.
- Access-token refresh is a real single-flight operation: callers that waited for an in-flight refresh observe the new token generation and retry without rotating again.
- Logout and confirmed server revocation purge both the session vault and every encrypted cache entry.
- Authentication failures use the backend's actual status/error envelope; no incorrect 409-only assumption remains.
- Cached age increases with wall-clock time since `as_of` and is rendered as stale/offline according to policy.
- 426 maps to a non-retryable mandatory-update state, not a generic cached-success fallback.
- Release logging never emits headers, tokens, credentials or response bodies containing sensitive monitoring data.
- Android compilation, unit tests and relevant instrumentation/Compose tests run in CI before closure.

## MOB-06 product screens (`#96`)

- Stato includes every approved health, freshness, NAV, day change, drawdown, exposure, cash, position, pipeline and compact strategy lifecycle field.
- Andamento implements 1S, 1M, 3M, 6M, 1A and Tutto, with NAV series, optional benchmark, drawdown and an accessible textual summary.
- Portafoglio implements summary, position rows and details, ordered from worst return to best.
- Refresh is lifecycle-aware, follows server expected-window state, supports pull-to-refresh and never presents cached data without age/offline disclosure.
- Compose tests cover operational, degraded, blocked, paused, offline, empty and mandatory-update states, including large font and accessibility semantics.

## MOB-07 events and push (`#97`)

- Implement a real `FirebaseMessagingService`; a generic Android `Service` stub is not acceptance.
- Request notification permission contextually after login; denial leaves monitoring functional.
- Register, rotate and revoke Firebase installation/token identity through authenticated device endpoints.
- Create generic local notifications containing no financial or identity data and deduplicate repeated deliveries.
- Cold, warm and process-dead notification taps route only opaque identifiers through biometric/device-credential unlock, then fetch authenticated event detail.
- Events implement approved categories, seven-day default, thirty-day maximum, cursor loading and grouped incident recovery.

## MOB-08 release and LAN security (`#98`)

- Do not start until both `#96` and `#97` are closed.
- Release builds never use the debug signing key.
- Durable signing material is supplied only through authorized secret storage; no key or password enters Git, logs or APK resources.
- The Android workflow triggers for its own definition and Android source/config changes, and runs lint, unit tests, required UI/instrumented tests, debug build and release build.
- An approved signed artifact includes SHA-256 plus successful `apksigner verify` evidence.
- No placeholder/test CA is trusted by release. LAN HTTPS rejects plaintext, wrong hostname and invalid/untrusted certificates.
- An upgrade signed with the same key installs over the prior release and preserves supported local data migrations.

## MOB-09 Pixel acceptance (`#99`)

- Do not start until `#98` is closed.
- A runbook is necessary but is not proof of acceptance.
- Execute the approved matrix on the stock Pixel 9: install, signed upgrade, biometric startup/background lock, reboot, online/offline/stale cache, partial outage, holiday/early-close state, 426, revocation, notification cold/warm/process-dead flow and recovery.
- Record build/version identifiers, artifact SHA-256, device/OS version, timestamps and pass/fail evidence without exposing financial screenshots or secrets.
- Keep the issue open if physical hardware, durable signing, LAN trust or real FCM remains unavailable.

## Cross-cutting merge gates

For every remediation PR:

- the issue is claimed before code changes;
- tests fail for the reported defect before the fix and pass after it;
- ticket-specific tests and lint are green;
- the repo-wide suite introduces no new failures, and any baseline failures are identified by exact test name and linked tracker item rather than described generically;
- secrets and sensitive payloads are absent from diff, logs and test artifacts;
- `code-review` reports no unresolved high/critical Standards or Spec finding;
- the PR references the issue but the authoring session does not merge it or close the issue manually.
