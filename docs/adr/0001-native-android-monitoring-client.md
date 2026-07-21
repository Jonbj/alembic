# Native Android monitoring client in the Alembic monorepo

Alembic will implement its private, read-only mobile monitor as a native Kotlin and Jetpack Compose application under `mobile/android/`. This deliberately rejects a responsive wrapper around the React cockpit and a cross-platform runtime: the Android-only scope benefits from first-class biometric, Keystore, FCM, offline, and lifecycle behavior, while keeping the mobile API and client changes atomic in one repository.

## Considered options

- Responsive web/PWA: cheapest reuse, but the existing cockpit is intentionally dense, currently unsuitable on mobile, and would retain the admin-shaped authentication boundary.
- React Native: shares TypeScript familiarity, but adds a bridge/runtime without a second target platform in scope.
- Native Kotlin/Compose: a separate UI implementation, but the smallest platform-aligned solution for the agreed security and background-delivery requirements.

## Consequences

The mobile client does not reuse React components. It does reuse Alembic domain terms and a versioned backend contract. Android build/test/release jobs remain separate from Python and web jobs.
