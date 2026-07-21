# Alembic Android Read-Only Monitor — Implementation Plan and Agent Handoff

**Date:** 2026-07-21  
**Design authority:** `docs/superpowers/specs/2026-07-21-android-monitoring-app-design.md`  
**Status authority:** GitHub issue `#21` and its native child issues; this document is a design/implementation guide, not a tracker  
**Tracker children:** `#91`–`#99` (aliases `MOB-01`–`MOB-09`)  
**Implementation status:** intentionally not recorded here

## 1. Goal and guardrails

Deliver a privately distributed, native Android monitor that shows Alembic operational state, portfolio performance, positions, and significant events. It must receive privacy-safe push notifications and retain an encrypted offline cache, while being technically unable to change trading-domain state.

Non-negotiable invariants:

1. A monitor credential cannot authorize any existing admin, configuration, strategy, labeling, weight, order, or kill-switch mutation.
2. The Android app never connects to Alpaca, Postgres, Redis, Telegram, or Firebase Admin directly.
3. Headline portfolio performance means broker NAV mark-to-market, not closed-trade P&L.
4. Mobile status is market-calendar aware; scheduled inactivity is `paused`, not false degradation.
5. A monitoring snapshot is assembled once server-side and read atomically by the API/client.
6. Missing broker data is `null` plus degradation, never a zero placeholder.
7. FCM is a delivery channel for persisted incidents; FCM payloads contain no financial detail.
8. Release traffic is HTTPS-only and the release build contains no permissive trust bypass.
9. Markdown plan files never become progress trackers. Work is done only when the corresponding child issue is closed, preferably through a merged PR with `closes #N`.

## 2. Required reading for an implementing agent

Read in this order before editing:

1. `AGENTS.md`
2. `docs/agents/wayfinder-roadmap-method.md`
3. Run `gh issue list --state open`
4. Fetch the assigned child issue and all native `blocked_by` edges
5. `CONTEXT.md`, especially Mobile monitoring
6. The design authority above, completely
7. `docs/adr/0001-native-android-monitoring-client.md`
8. `docs/adr/0002-mobile-read-only-security-boundary.md`
9. `docs/adr/0003-server-owned-alert-incidents-with-fcm-delivery.md`
10. Relevant current code/tests named in the selected work package

Do not start from a package described here unless its actual child issue is open, unassigned, `ready-for-agent`, and has no open blockers. Claim it with `gh issue edit <n> --add-assignee @me` before implementation.

## 3. Delivery map

The work is intentionally split into independently reviewable tracer bullets. Identifiers `MOB-*` are planning aliases, not status markers or GitHub numbers.

```text
MOB-01 Contract + schema
   ├──> MOB-02 Scoped monitor authentication
   └──> MOB-03 Snapshot/read-model API

MOB-02 ──> MOB-04 Incident/outbox + FCM
   └─────> MOB-05 Android secure shell <── MOB-03

MOB-03 + MOB-05 ──> MOB-06 Android status/performance/portfolio
MOB-04 + MOB-05 ──> MOB-07 Android events/push

MOB-06 + MOB-07
   └──> MOB-08 LAN TLS + release pipeline
           └──> MOB-09 end-to-end acceptance and operator handoff
```

`MOB-03` may begin after the shared contract/schema portion of `MOB-01`. `MOB-04` depends on scoped device identity from `MOB-02`; incident evaluation can still be developed with fake devices inside that child before production delivery is wired.

## 4. Published tracker tickets

The approved tracer bullets were published on 2026-07-22 as native children of `#21`, with `wayfinder:task`, `ready-for-agent`, no assignee, and the native `blocked_by` edges below. Always query GitHub again; this table is an identity/dependency map, not a status report.

| Alias | Issue | Title | Native blockers at publication |
| --- | --- | --- | --- |
| MOB-01 | `#91` | Mobile monitor: v1 contract, persistence schema, and domain fixtures | None |
| MOB-02 | `#92` | Mobile monitor: scoped users, rotating device sessions, and authorization boundary | `#91` |
| MOB-03 | `#93` | Mobile monitor: coherent snapshot, performance, positions, and events read API | `#91` |
| MOB-04 | `#94` | Mobile monitor: alert incidents, notification outbox, and FCM delivery | `#92` |
| MOB-05 | `#95` | Android monitor: Compose scaffold, secure onboarding, session vault, and offline store | `#92`, `#93` |
| MOB-06 | `#96` | Android monitor: Status, Performance, and Portfolio vertical slice | `#93`, `#95` |
| MOB-07 | `#97` | Android monitor: Events feed, FCM receiver, privacy-safe notifications, and deep links | `#94`, `#95` |
| MOB-08 | `#98` | Android monitor: LAN HTTPS, signing, CI, and private APK releases | `#96`, `#97` |
| MOB-09 | `#99` | Android monitor: Pixel 9 end-to-end acceptance and operator runbook | `#98` |

Avoid a single giant “build mobile app” issue: backend/auth/push/release failures should be independently reviewable and have explicit blocking edges.

## 5. MOB-01 — Contract, migration, and fixtures

### Objective

Freeze the v1 transport/domain contract and add persistence required by monitor identities, snapshots, events, and deliveries without changing existing runtime behavior.

### Likely files

- Create `src/mobile_monitoring/__init__.py`
- Create `src/mobile_monitoring/models.py`
- Create `src/api/mobile_models.py`
- Create next migration, currently expected `migrations/041_mobile_monitoring.sql`
- Create `tests/mobile_monitoring/test_models.py`
- Create `tests/migrations/test_mobile_monitoring_migration.py` or extend the repository's migration smoke coverage
- Create `tests/fixtures/mobile_monitoring.py`
- Update `docs/API.md` only after routes exist; do not duplicate the full design contract prematurely

### Schema requirements

Implement the tables specified in design section 9.2 with these hard constraints:

- UUID identifiers generated server-side.
- Case-normalized unique monitor usernames.
- Bcrypt password hashes only.
- Refresh tokens stored as hashes with session family, rotation, expiry, revocation, and reuse audit fields.
- Device uniqueness scoped to user/installation; Firebase identifier nullable until permission/registration succeeds.
- Snapshot numeric columns retain precision and never coerce unavailable broker state to zero.
- One open alert incident per stable fingerprint.
- One delivery per event transition/device.
- Foreign keys use explicit delete behavior; revoking a user/session/device should preserve security audit/event history where appropriate.
- Index event cursor `(occurred_at DESC, id DESC)`, active fingerprint, due delivery, active session, snapshot time.
- Add bounded detail JSON schemas at the Python boundary; JSONB is not a license to store raw logs/broker objects.

### Contract models

Define Pydantic v2 response/request models for auth, snapshot, performance, positions, events, devices, and standard errors. Enums and nullability must match the design verbatim. Generate an OpenAPI snapshot fixture for `/api/mobile/v1` once routes land.

### Tests

- Migration applies to a fresh database after migrations 001–040.
- Unique active incident and delivery constraints reject duplicates.
- Decimal/nullable financial fields round-trip without zero substitution.
- Every example payload in the design validates against the Pydantic model.
- Unexpected enum/value/unsafe overlong copy is rejected.
- Models serialize UTC timestamps and fractions consistently.

### Exit criteria

Fresh CI database migrates successfully; contract examples validate; no route or worker behavior has changed; rollback/backup note is attached to the child issue.

## 6. MOB-02 — Monitor authentication and authorization boundary

### Objective

Add separately provisioned monitor identities, short mobile access tokens, rotating device-bound refresh sessions, and an exhaustive proof that these credentials cannot mutate Alembic.

### Likely files

- Create `src/mobile_monitoring/auth.py`
- Create `src/api/routes/mobile_auth.py`
- Modify `src/api/jwt_utils.py` to issue/decode typed claims without weakening legacy validation
- Modify `src/api/auth.py` to expose explicit admin and monitor dependencies
- Modify `src/api/main.py` to include the mobile auth router
- Create `scripts/manage_monitor_users.py`
- Create `tests/api/test_mobile_auth.py`
- Create `tests/api/test_mobile_authorization_matrix.py`
- Extend config for mobile access/refresh lifetimes and token pepper if used

### Design

- Access token: JWT, 15 minutes, `aud=alembic-mobile`, `type=access`, explicit scopes, user/device/jti.
- Refresh token: opaque ≥256 bits entropy, 30-day absolute expiry, hash at rest, rotate every use.
- Refresh serialization: one valid child token per use. Reuse of an already rotated token revokes the session family.
- Login is rate-limited by username and source address without revealing whether the user exists.
- Disabled user or revoked device/session fails closed.
- Provisioning occurs only through a server-side command with interactive password input or safe hash input; secrets never appear in shell history/log output.
- Admin legacy tokens remain valid only for current admin endpoints; they do not silently become monitor-user sessions.

### Authorization matrix test

Discover FastAPI routes programmatically. For every non-safe method outside the four explicitly allowed mobile technical writes (login, refresh, logout, device registration/revocation):

1. send a structurally valid monitor JWT;
2. assert `403` before handler side effects;
3. assert mocks/stores/broker clients received no mutation call.

Include all current POST/PUT/PATCH/DELETE routes under admin, config, strategies, weights, labeling, and future routes discovered by the test. The test should fail when a new mutation is added without an explicit authorization classification.

### Tests

- Correct/wrong/disabled-user login.
- Audience, type, scope, expiry, signature, device mismatch.
- Refresh rotation, expiry, revocation, replay/reuse family revocation, concurrent refresh.
- Logout revokes server session and device best effort.
- Rate-limit behavior and uniform auth errors.
- Admin regression tests remain green.
- Authorization matrix described above.

### Exit criteria

A monitor user can obtain and rotate a session, but cannot reach any trading-domain mutation. The provisioning command and revocation procedure are documented and demonstrated against a test database.

## 7. MOB-03 — Monitoring read model and mobile API

### Objective

Produce one coherent monitoring snapshot on the server and expose the read endpoints for snapshot, performance, positions, and events.

### Likely files

- Create `src/mobile_monitoring/snapshot.py`
- Create `src/mobile_monitoring/state.py`
- Create `src/mobile_monitoring/performance.py`
- Create `src/mobile_monitoring/events.py`
- Create `src/mobile_monitoring/store.py` or focused methods in `src/store/pg_store.py` if they remain cohesive
- Create `src/api/routes/mobile.py`
- Create `src/workers/mobile_monitor_task.py`
- Modify `src/workers/celery_app.py`
- Modify `src/api/main.py`
- Create `tests/mobile_monitoring/test_state.py`
- Create `tests/mobile_monitoring/test_snapshot.py`
- Create `tests/mobile_monitoring/test_performance.py`
- Create `tests/api/test_mobile_routes.py`
- Create `tests/workers/test_mobile_monitor_task.py`

### Snapshot builder

Run once per minute. It gathers account/positions from the configured Alpaca paper/live client, DB/Redis health, kill switch, latest signal/cycle, strategy lifecycle, active incident count, and authoritative market clock/calendar context. It computes the design formulas and writes one versioned immutable JSON document to Redis using an atomic replace. Store a unique snapshot ID and one `as_of`.

Every five minutes during an expected window, and on material state transition, persist a monitoring point for history/risk. Do not insert a fake row if broker account state is unavailable.

The builder owns degradation mapping. Route handlers do not recompute operational state or call Alpaca. If the cache is absent/stale beyond the safe ceiling, the route returns `503` with the standard error contract.

### Performance service

- Reuse `compute_period_benchmark` where its semantics match the approved design.
- Use the anchor immediately before the requested period.
- Join/derive exposure history from monitoring snapshots; if missing, benchmark fields are all null with degradation.
- Append the current coherent snapshot as the final point when newer than broker history.
- Compute drawdown from ordered NAV points.
- Downsample deterministically to ≤500 points while retaining endpoints and extrema.
- Cache expensive broker/SPY histories with bounded TTL and expose the source age.

### Market-aware state

Use the broker calendar/clock or a single authoritative market-calendar adapter. Tests cover weekends, full holidays, early close, premarket, after-hours, expected pipeline windows, daylight-saving transitions, and critical faults outside hours.

### Events projection

Map persisted mobile incidents and significant execution/order lifecycle rows into the safe `Operator event` contract. Do not return raw unbounded `reason`, LLM reasoning, or log text. Cursor is signed/opaque and stable under concurrent inserts.

### Tests

- State precedence table and per-component freshness table from the design.
- Consistent snapshot `as_of` under changing fakes.
- Broker/DB/Redis partial failures and null-not-zero behavior.
- Financial formulas and period anchors.
- Event inclusion/exclusion rules, cursor stability, 30-day cap.
- ETag/304 and version/426 behavior.
- Snapshot route performs no broker call.
- API p95 benchmark in a local integration test with warm read model.

### Exit criteria

All four GET endpoints return design-valid payloads from a coherent read model, survive partial dependencies safely, and have contract tests/OpenAPI coverage.

## 8. MOB-04 — Incidents, outbox, and FCM

### Objective

Turn important system/risk/order observations into persisted, deduplicated incidents and privacy-safe per-device FCM deliveries, including recovery.

### Likely files

- Create `src/mobile_monitoring/incidents.py`
- Create `src/mobile_monitoring/notification_outbox.py`
- Create `src/notifications/fcm.py`
- Create `src/workers/mobile_alert_task.py`
- Modify `src/workers/celery_app.py`
- Integrate event-driven order failure/kill-switch observations at the narrow existing notification seams
- Extend `src/config.py` and `.env.example` with non-secret project/config paths only
- Create `tests/mobile_monitoring/test_incidents.py`
- Create `tests/mobile_monitoring/test_notification_outbox.py`
- Create `tests/notifications/test_fcm.py`
- Create `tests/workers/test_mobile_alert_task.py`

### Incident engine

Implement the initial rule table from design section 9.3. Each evaluation produces `open`, `escalate`, `observe`, or `recover` against a stable fingerprint. Use explicit hysteresis/consecutive-observation rules. A terminal order rejection/cancel event is historical and does not fabricate recovery.

Persist transition and outbox entries in the same database transaction. A worker that crashes after commit can retry; a crash before commit produces neither partial incident nor delivery.

### Delivery adapter

- Initialize Firebase Admin from mounted application-default/service-account credentials; never commit credential JSON.
- Hide Firebase identifiers and SDK details behind `FcmDeliveryPort`.
- Build the minimal payload from the design; unit tests assert forbidden financial/ticker/token keys are absent.
- Record provider acceptance ID and redacted error code.
- Retry transient failures with bounded backoff; disable invalid/unregistered destinations on terminal errors.
- Do not require or initialize Firebase Analytics.
- A fake adapter is the default in tests/development when credentials are absent.

### Limitations

Document that in-process detection cannot guarantee host-down notification. Do not claim that DB/Redis/API total failure is externally monitored. Add that to the cloud follow-up rather than hiding it.

### Tests

- Each incident opens once, observes without duplicate, escalates once, and recovers once.
- Market-window suppression affects only schedule staleness.
- Transactional outbox and duplicate constraints.
- Retry/terminal provider errors and device disablement.
- Generic notification content and minimal data payload.
- Measured event-to-provider acceptance meets fake-clock SLO logic.
- Existing Telegram notifications remain unchanged.

### Exit criteria

Synthetic kill switch, pipeline lag, drawdown, exposure, and order failure scenarios produce the correct incident history and exactly one delivery per transition/device through a fake FCM transport; staging FCM smoke test succeeds without sensitive payload.

## 9. MOB-05 — Android secure shell and offline data foundation

### Objective

Create the native app, secure onboarding/session lifecycle, typed API client, protected cache, biometric gate, and shared live/offline state before building feature screens.

### Likely files

- Create `mobile/android/settings.gradle.kts`
- Create `mobile/android/build.gradle.kts`
- Create `mobile/android/gradle/libs.versions.toml`
- Create `mobile/android/app/build.gradle.kts`
- Create manifest/resources and package tree from design section 11
- Create debug/LAN/cloud network-security resources
- Add Android unit/instrumentation/Compose test source sets
- Add `mobile/android/README.md` for local build only; operator deployment belongs to MOB-08/MOB-09

### Build baseline

- Application ID recommendation: `com.jonbj.alembic.monitor`; confirm it is stable/available before first signed build.
- Select stable Kotlin/AGP/Compose BOM/AndroidX/Firebase versions at implementation time; record them in the version catalog.
- Avoid alpha dependencies unless required and justified in a new ADR.
- One `app` module; package boundaries from the design.
- Material 3, single activity, Navigation 3, coroutines/Flow, lifecycle ViewModels.
- Hilt or a similarly testable DI mechanism; no global service locator.

### Session vault

- First-run form: server HTTPS URL, username, password, device name.
- Reject HTTP in release. Normalize URL without accepting embedded user info.
- Store raw refresh token encrypted with AES-GCM using a non-exportable Android Keystore key; access token may remain memory-first and encrypted when persistence is necessary.
- One refresh mutex prevents concurrent token rotation/reuse false positives.
- Biometric/device credential gate at startup and after five minutes background.
- Protect task-switcher snapshot; no sensitive notification preview.
- Logout always wipes tokens/cache locally, then reports whether server revocation succeeded.

### Offline store

Use Room for indexes/metadata. Encrypt sensitive payloads/columns using authenticated encryption backed by Android Keystore; do not start new work on deprecated `androidx.security.crypto` APIs. Cache retention matches the design and is wiped on logout/revocation. Inject a clock for deterministic age tests.

### Repository state machine

Expose immutable UI state that distinguishes:

- initial/loading;
- live/fresh;
- live/degraded/blocked/paused;
- cached/offline with age;
- unauthenticated/session expired;
- incompatible/mandatory update;
- no prior data/unavailable.

### Tests

- URL/TLS validation and release cleartext rejection.
- Login/refresh/replay flow with MockWebServer and concurrent requests.
- Keystore wrapper round-trip/failure/key invalidation.
- Biometric gate timeout and process recreation.
- Room migrations, encrypted data not present as plaintext in DB file fixture, retention and purge.
- Repository live→offline→recovery state.
- Debug logs redact headers/body/secrets; release logging interceptor absent.

### Exit criteria

On emulator and Pixel test device, a signed/debug build can securely log into fake/staging v1, cache a snapshot, reopen behind biometric auth offline, refresh a session once, and purge on logout. No feature screen beyond diagnostic shell is required yet.

## 10. MOB-06 — Status, Performance, and Portfolio vertical slice

### Objective

Implement the first three product destinations end-to-end using real v1 contract repositories and all specified states/accessibility requirements.

### Likely packages

- `feature/status/`
- `feature/performance/`
- `feature/portfolio/`
- shared formatting/theme/components under `core/ui/` only when reused
- corresponding unit and Compose UI test packages

### Stato

Implement the wireframe hierarchy from the design. Highest-severity reason is prominent and links to event detail only when an event ID exists. Mode badge is always visible. `unknown` mode renders critical. Pipeline ages use server classifications, not Android schedule math.

### Andamento

- Ranges `1S`, `1M`, `3M`, `6M`, `1A`, `Tutto`; default `1M`.
- NAV chart with optional benchmark/drawdown overlays.
- Portfolio return, absolute NAV change, max drawdown, benchmark, alpha, and separated realized P&L.
- Accessible non-chart summary/table.
- Keep selected period across rotation/process recreation.
- Do not invent values for null benchmark or partial curve.

Choose a maintained stable Compose chart dependency only after a bounded comparison against a small custom Canvas implementation. Acceptance is accessibility, correct scaling/negative values, testability, and dependency health—not visual novelty. Record the chosen library in the issue/PR, not an ADR unless it becomes a meaningful lock-in.

### Portafoglio

Implement summary and rows sorted by worst return first. Detail contains agreed fields only. Number formatting handles fractional shares, negative cash, large values, null entry time, and no positions.

### Refresh

Foreground 60s when pipeline expected, five minutes otherwise, plus pull-to-refresh. All requests use shared repositories/cache. Refresh cancellation follows lifecycle; no parallel polling per screen.

### Tests

- Golden/screenshot or semantic Compose tests for all states and dark/light-system theme.
- TalkBack content descriptions and heading/order semantics.
- Font scale 200%, narrow Pixel 9 portrait, landscape functional smoke.
- Positive/negative/zero/null money and percent formatting.
- Portfolio sort and detail.
- Chart data/period/overlay and accessible fallback.
- Shared `as_of` displayed; offline age banner cannot be hidden by navigation.

### Exit criteria

The three screens meet the design on Pixel 9 against staging v1, including one forced partial dependency failure and offline mode, with no mobile domain writes.

## 11. MOB-07 — Events, push, and deep links

### Objective

Implement event browsing, FCM registration/rotation, generic notifications, biometric-gated deep links, and local push-disabled status.

### Likely packages/files

- `feature/events/`
- `push/AlembicMessagingService.kt`
- notification channel/deep-link helpers
- device registration repository
- manifest notification permission/service declarations
- unit, Compose, and instrumented tests

### Behavior

- Ask Android notification permission with contextual copy after successful login, not on first cold launch before trust is established.
- Register current Firebase Installation ID and refresh it when provider callback says it changed.
- If permission is denied or Play Services/FCM registration fails, the app remains fully usable and shows “Notifiche disattivate/non disponibili” in status/settings.
- Generic lock-screen message only. Tapping opens the app, requires biometric/device credential, then fetches event detail by opaque ID.
- Never render FCM data before authenticated fetch.
- Event feed defaults seven days and uses cursor pagination up to thirty; filters and incident/recovery grouping match design.
- Device revocation/logout removes local identifier and calls server revocation best effort.

### Tests

- FCM identifier initial registration/rotation/revocation.
- Notification permission grant/deny/don't-ask-again flows.
- Generic title/body and no sensitive extras.
- Cold/warm/dead-process deep link; no detail before biometric success.
- Missing/expired/deleted event gives safe state.
- Cursor paging, filters, incident history/recovery rendering.
- Duplicate FCM delivery does not duplicate local notification for same transition.

### Exit criteria

A staging incident produces one generic Pixel notification, opens the correct authenticated event after unlock, and produces one recovery notification. Permission denial degrades visibly without breaking monitoring.

## 12. MOB-08 — LAN TLS, signing, CI, and private release

### Objective

Make the complete stack safely installable on the LAN and produce reproducible signed APK releases without leaking secrets.

### Likely files

- Add reverse-proxy service/config for stable LAN HTTPS (technology selected in issue with a small operational comparison)
- Modify `docker-compose.yml` without exposing new plaintext Internet surfaces
- Add LAN CA creation/rotation script or documented operator command using a reviewed tool
- Add Android `network_security_config` for exact LAN hostname/build flavor
- Extend `.github/workflows/ci.yml` or create a focused Android workflow
- Create release workflow and checksum/signature verification step
- Update `.gitignore`, gitleaks allow/deny patterns, `.env.example`
- Create preliminary `docs/mobile/android-release.md`

### TLS

- Stable LAN hostname with SAN-matching internal certificate.
- Pixel installs the CA; Android release config trusts it only for the intended LAN domain.
- Release refuses cleartext and invalid hostname/certificate.
- Debug cleartext exception is restricted to explicit local emulator/development hosts.
- Future cloud flavor trusts public system CAs and removes LAN trust configuration.

### Signing and CI

- Generate one long-lived release signing key; store encrypted/offline backup.
- Inject keystore and passwords through protected CI secrets; never echo them.
- Build/lint/unit/Compose tests on PR.
- Release on an explicit version tag/manual approval: signed APK, SHA-256, signature verification, version JSON, release notes.
- Verify an update signed with the same key installs over the previous release and preserves intended data/session migration.
- Secret scanning must cover `google-services.json`, Firebase server credentials, keystores, passwords, and generated CA private keys.
- Plan package/signing-key registration through Android Developer Console before wider/global enforcement; personal limited-distribution is acceptable for the agreed small device count.

### Tests

- Pixel connects through LAN HTTPS and rejects plaintext/bad certificate/wrong hostname.
- Release artifact signature verifies and checksum matches.
- Debug/release resources do not leak into each other.
- CI forks/untrusted PRs cannot access signing/Firebase secrets.
- APK inspection finds no server service-account, broker/admin key, private CA/signing key, or plaintext password.

### Exit criteria

A reproducible signed APK installs/updates on Pixel 9, connects only through the reviewed LAN HTTPS route, and is published privately with verified checksum/signature and no secret findings.

## 13. MOB-09 — End-to-end acceptance and operator handoff

### Objective

Exercise the complete agreed product on the reference device, document operation/recovery, and close the implementation only with evidence.

### Deliverables

- Create `docs/mobile/android-operator-runbook.md`
- Finalize `docs/mobile/android-release.md`
- Update `docs/API.md` with canonical `/api/mobile/v1` summary and link to OpenAPI/design
- Update `docs/deployment.md` and `docs/operations.md` for mobile workers, FCM, TLS, backup/restore, and monitor-user/device revocation
- Add a decision/context pointer to `#21` only when resolving the last child, per roadmap rules
- Attach acceptance evidence to the issue/PR without committing secrets or financial screenshots unless redacted

### Runbook content

- create/disable monitor user;
- install/rotate LAN CA;
- configure Firebase and mount credential;
- install/update/rollback signed APK;
- grant/revoke notification permission;
- list/revoke sessions/devices;
- inspect snapshot age, incidents, outbox, FCM failures;
- recover from lost phone, lost signing key, compromised refresh session, expired CA, Firebase outage;
- explain in-process host-down alert limitation and future cloud external monitoring.

### Acceptance execution

Run all nine design scenarios plus:

- holiday/early close fixture;
- Pixel reboot and app process death;
- CA expiry/wrong hostname;
- token family reuse/revocation;
- FCM provider identifier rotation;
- DB or Redis partial outage;
- broker unavailable with cached portfolio;
- old app receives 426;
- upgrade previous signed APK to release candidate.

Record timestamps for notification SLOs from server observation to FCM acceptance and to Pixel display. Distinguish provider acceptance from guaranteed device presentation.

### Exit criteria

The Pixel 9 acceptance matrix passes, full backend and Android CI is green, runbooks are executable by another operator, all child issues are closed through their merged PRs, and `#21` contains the final context pointer. A future-cloud ticket captures remote ingress/external uptime work rather than smuggling it into MVP completion.

## 14. Review gates

Each PR should be small enough to review independently and must include:

- the child issue reference and `closes #N` only when it fully resolves that child;
- explicit statement of which design invariants it touches;
- tests that fail before the change and prove the security/semantic boundary;
- migration/deploy/rollback notes where relevant;
- no unrelated cleanup of the existing dirty worktree;
- no app screenshots containing real portfolio values unless redacted.

Mandatory human gates before destructive/external operations:

- applying production DB migrations;
- creating Firebase project/service account or uploading credentials;
- generating/rotating signing or CA private keys;
- changing Docker exposure/firewall/DNS;
- publishing a signed release;
- revoking real user sessions/devices.

## 15. Definition of done

The initiative is complete only when all of the following are true in the authoritative tracker and merged code:

- every published MOB child is closed;
- monitor authorization is proven read-only against all mutation routes;
- coherent v1 snapshot/performance/positions/events APIs are documented and tested;
- alert incidents and FCM delivery/recovery satisfy the agreed behavior;
- the native app implements all four destinations and protected offline mode;
- LAN HTTPS, signing, private release, and Pixel update are verified;
- operator runbooks and security recovery procedures exist;
- the final decision/context pointer is appended to `#21`.

Do not mark this document with completion checkboxes. GitHub child issue state is the only progress source.
