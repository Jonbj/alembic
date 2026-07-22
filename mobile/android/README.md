# Alembic Android Monitor

Native Kotlin / Jetpack Compose read-only monitoring application for Alembic.

## Scope

- Read-only monitor: Stato, Andamento, Portafoglio, Eventi.
- No trading, admin, strategy, configuration, or kill-switch mutations.
- Biometric / device-credential gate on cold start and after 5 minutes in background.
- Encrypted session vault backed by Android Keystore.
- Encrypted offline cache (Room + AES-GCM column encryption via Keystore).
- Repository skeletons with network-first and cache fallback, exposed as StateFlow.
- LAN TLS with a domain-scoped user CA.
- Push delivery is intentionally external-only in the MVP; the backend owns incidents and FCM is a future delivery channel.

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
│   ├── push/             # Push delivery port and stub service
│   └── worker/           # Opportunistic cache refresh worker
├── app/src/main/res/xml/network_security_config.xml
└── app/src/main/res/raw/lan_ca.pem  # test-only fake CA; replace with your real LAN CA
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

Release builds require an injected signing keystore:

```bash
./gradlew assembleRelease \
  -Pandroid.injected.signing.store.file=$KEYSTORE_PATH \
  -Pandroid.injected.signing.store.password=$STORE_PASSWORD \
  -Pandroid.injected.signing.key.alias=$KEY_ALIAS \
  -Pandroid.injected.signing.key.password=$KEY_PASSWORD
```

Never commit `google-services.json`, release keystores, or backend secrets.

## LAN setup

1. Choose a stable LAN hostname (e.g. `alembic.lan`) and point it at the Alembic host.
2. Run a reverse proxy with TLS using your internal CA.
3. Install the CA certificate on the Pixel device as a user CA.
4. Replace `app/src/main/res/raw/lan_ca.pem` with your real CA certificate.
5. Configure the mobile base URL at build time via `BASE_URL` in `app/build.gradle.kts` or through managed configuration.

`network_security_config.xml` trusts the system store plus the user CA and the bundled anchor only for `alembic.lan`. Cleartext is disabled in release builds; debug builds allow cleartext only for `10.0.2.2` / `10.0.3.2` (emulator hosts).

## Security notes

- Session JWTs and refresh tokens are encrypted at rest; the encryption key lives in Android Keystore and is non-exportable.
- Cached financial data is encrypted before being written to Room.
- `FLAG_SECURE` hides window content from the task switcher / screenshots.
- Logout clears local tokens and cache even if the server call fails.
- The bundled `lan_ca.pem` is a self-signed test certificate and must be replaced before any real deployment.

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
- `KeystoreSessionVaultInstrumentedTest`: real Keystore cipher on a device.

## External prerequisites

The following are intentionally not bundled and must be supplied by the operator:

- Real LAN CA certificate and hostname.
- Firebase project and `google-services.json` if enabling FCM in a future build.
- Release signing keystore.
- Monitor user provisioned on the Alembic server.

## License

Private project; do not distribute the APK or signing material publicly.
