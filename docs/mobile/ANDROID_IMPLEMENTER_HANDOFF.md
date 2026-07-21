# Android Monitor — Start Here for the Implementing Model

This is the entry point, not the specification itself.

## Mission

Implement the approved private Android read-only monitor for Alembic. The product has four screens (`Stato`, `Andamento`, `Portafoglio`, `Eventi`), uses broker NAV mark-to-market as its primary performance truth, receives server-owned alert incidents through FCM, and cannot mutate trading-domain state.

## Read before acting

1. `AGENTS.md`
2. `docs/agents/wayfinder-roadmap-method.md`
3. Run `gh issue list --state open`
4. Read and claim only the assigned, unblocked, `ready-for-agent` child of roadmap `#21`
5. `CONTEXT.md`
6. `docs/superpowers/specs/2026-07-21-android-monitoring-app-design.md`
7. `docs/superpowers/plans/2026-07-21-android-monitoring-app-implementation.md`
8. `docs/adr/0001-native-android-monitoring-client.md`
9. `docs/adr/0002-mobile-read-only-security-boundary.md`
10. `docs/adr/0003-server-owned-alert-incidents-with-fcm-delivery.md`

Do not infer progress from the plan. GitHub child issue state and native blockers are authoritative.

## First implementation move

The implementation tickets are native roadmap children `#91`–`#99`. Query their live state and native dependencies; at publication only `#91` had no mobile blocker. Fetch and claim only an open, unassigned, `ready-for-agent` child whose current blockers are all closed, then implement only that bounded tracer bullet.

## Fixed product decisions

- Kotlin/Jetpack Compose, monorepo at `mobile/android/`.
- Pixel 9 stock Android, portrait-first.
- Private signed APK, LAN-only MVP, HTTPS release traffic.
- Separate monitor users and device-bound rotating sessions.
- Mobile trading-domain access is GET-only; auth/device registration are the only technical writes.
- Dedicated `/api/mobile/v1` contract and server-side coherent snapshot.
- FCM with generic lock-screen content; authenticated detail after biometric unlock.
- Protected offline cache, 30-day event retention, purge on logout/revocation.
- No admin controls, Alpaca credentials, strategy P&L, LLM/news/backtest detail, analytics, or Crashlytics.

## Safety checks before claiming completion

- Programmatic authorization test proves monitor JWTs get `403` on every mutation route.
- Missing broker data is null/degraded, never zero.
- Weekend/holiday is `paused`, not false stale.
- FCM payload contains no financial/ticker/user/server detail.
- Release APK rejects HTTP and invalid TLS.
- The signing key, Firebase server credential, CA private key, broker/admin secrets, and passwords are absent from Git/artifacts/logs.
- Completion is recorded by closing the child issue through a merged PR containing `closes #N`, then following the `#21` context-pointer rule.

## Operator-supplied prerequisites

Implementation will eventually require operator approval/input for Firebase project credentials, LAN hostname/CA, monitor-user provisioning, APK signing material, private release publication, and Pixel 9 acceptance. Code and tests must use fakes until those explicit external steps are authorized.
