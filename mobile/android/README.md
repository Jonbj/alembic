# Alembic Android Monitor

Native Kotlin / Jetpack Compose read-only monitoring application for Alembic.

## Scope

- Read-only monitor: Stato, Andamento, Portafoglio, Eventi.
- No trading, admin, strategy, configuration, or kill-switch mutations.
- Biometric / device-credential gate on cold start and after 5 minutes in background.
- Encrypted session vault backed by Android Keystore.
- Encrypted offline cache (Room + AES-GCM column encryption via Keystore).
- Status, performance, and portfolio product destinations backed by the real v1
  repositories, with explicit live/offline/stale/update-required presentation.
- Lifecycle-aware foreground polling (60 seconds while the server says the
  pipeline is expected; 5 minutes otherwise) plus pull-to-refresh.
- LAN TLS with a domain-scoped user CA.
- Backend incidents and FCM delivery are integrated with the Android receiver,
  privacy-safe notifications, authenticated event deep links, and local deduplication.

## Project structure

```text
mobile/android/
├── app/src/main/java/com/jonbj/alembic/monitor/
│   ├── app/              # MainActivity, navigation, DI
│   ├── core/model/       # Domain models and load state
│   ├── core/network/     # Retrofit API, DTOs, auth interceptor
│   ├── core/database/    # Room cache + encrypted store
│   ├── core/security/    # Keystore cipher, session vault, biometric gate, app lock
│   ├── data/repository/  # Auth + status/performance/portfolio/events repositories
│   ├── feature/          # Login, status, performance, portfolio, events, biometric lock
│   ├── push/             # Firebase gateway, receiver, registration, deep links, deduplication
│   └── worker/           # Opportunistic cache refresh worker
├── app/src/main/res/xml/network_security_config.xml
└── app/src/debug/res/raw/lan_ca.pem  # debug-only fake CA; absent from release
```

## Build

Requirements:

- JDK 17
- Android SDK API 34 (compileSdk=34)
- A LAN hostname and reverse proxy terminating TLS with a private CA

```bash
cd mobile/android
./gradlew assembleDebug
```

Release signing and the private release pipeline are intentionally owned by MOB-08.
This project never falls back to the Android debug key for a release artifact.

Never commit `google-services.json`, release keystores, or backend secrets.

## LAN setup

1. Choose a stable LAN hostname (e.g. `alembic.lan`) and point it at the Alembic host.
2. Run a reverse proxy with TLS using your internal CA.
3. Install the CA certificate on the Pixel device as a user CA.
4. Enter the trusted HTTPS server origin in the first-run login screen.

`network_security_config.xml` trusts the system store plus the operator-installed
user CA only for `alembic.lan`. The test CA is packaged only in debug. Cleartext is
disabled in release builds; debug builds allow it only for explicit emulator and
loopback hosts.

## Security notes

- Session JWTs and refresh tokens are encrypted at rest; the encryption key lives in Android Keystore and is non-exportable.
- Cached financial data is encrypted before being written to Room.
- `FLAG_SECURE` hides window content from the task switcher / screenshots.
- Logout clears local tokens and cache even if server revocation fails, and reports
  that revocation failure to the caller.
- The bundled debug `lan_ca.pem` is a self-signed test certificate and is never
  packaged in release.

## Tests

Unit tests (JVM + Robolectric):

```bash
./gradlew test
```

Instrumentation tests (require an Android device or emulator):

```bash
./gradlew connectedAndroidTest
```

Key test areas:

- `EncryptedSessionVaultTest`: Keystore-backed encryption round-trip.
- `TimeoutAppLockTest`: biometric timeout gating logic with a fake clock.
- `RepositoryCacheFallbackTest`: repository returns cached data when the network returns 503.
- `MonitoringPresentationTest`: safety-state precedence, refresh cadence, numeric
  formatting, and worst-return-first position ordering.
- `RepositoryRefreshSerializationTest`: foreground/manual refreshes never overlap
  inside one repository.
- `MonitoringScreensTest`: Compose semantics for operational/degraded/blocked/
  paused/offline/empty/update-required states and 200% font scale.
- `MobileDtoContractTest`: Android DTOs decode the real v1 server contract.
- `ApiCallerConcurrencyTest`: concurrent 401 responses trigger one refresh rotation.
- `ServerUrlPolicyTest`: release HTTPS onboarding and debug loopback policy.
- `KeystoreSessionVaultInstrumentedTest`: real Keystore cipher on a device.

The NAV visualization uses a small custom Compose `Canvas` rather than another
chart dependency. Every series has a textual summary and an expandable data
table, so the chart is never the only accessible representation.

## External prerequisites

The following are intentionally not bundled and must be supplied by the operator:

- Real LAN CA certificate and hostname.
- Firebase project and `google-services.json` for the MOB-07 Android FCM integration.
- Release signing keystore.
- Monitor user provisioned on the Alembic server.

## License

Private project; do not distribute the APK or signing material publicly.
