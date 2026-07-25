# Alembic Android Monitor — Operator Runbook

**Date:** 2026-07-21  
**Device:** Google Pixel 9, stock Android, portrait  
**Network:** LAN-only MVP  
**GitHub issue:** `#99` (MOB-09)

## 1. What this document covers

This runbook describes how a trusted operator installs, configures, and runs the Alembic Android monitor on a private device. It is not a public distribution guide: the app is distributed as a signed APK from a private GitHub release.

## 2. Prerequisites

- A server running the Alembic backend with `/api/mobile/v1` enabled.
- A separately provisioned `monitor_users` account (use `scripts/manage_monitor_users.py` once it exists; until then create the row server-side with a bcrypt hash).
- A local LAN hostname resolving to the Alembic host, e.g. `alembic.lan`.
- An internal CA certificate installed on the Pixel 9.
- For push notifications (optional): a Firebase project and `google-services.json` mounted at build time.
- For release APK: a Java signing keystore stored offline.

## 3. Build the release APK

```bash
cd mobile/android
export ALEMBIC_RELEASE_STORE_FILE=/secure/path/to/alembic-monitor.keystore
export ALEMBIC_RELEASE_STORE_PASSWORD=<keystore-password>
export ALEMBIC_RELEASE_KEY_PASSWORD=<key-password>
./gradlew assembleRelease
```

The release build:
- requires HTTPS;
- trusts only the configured LAN CA (`alembic.lan`);
- disables debug logging and leak/canary telemetry;
- embeds no Firebase credentials unless `google-services.json` is present.

Upload the resulting `app/build/outputs/apk/release/app-release.apk` to a private GitHub release.

## 4. Install on Pixel 9

1. Enable **Install unknown apps** for the file manager/browser used to download the APK.
2. Download the signed APK from the private release.
3. Install and launch the app.
4. Enter the monitor username, password, and the LAN base URL, e.g. `https://alembic.lan/api/mobile/v1`.
5. Complete biometric enrollment when prompted.

## 5. Trust anchor

- Replace `mobile/android/app/src/main/res/raw/lan_ca.pem` with the real operator CA.
- Verify the CA is installed under **Settings → Security → Encryption & credentials → Install a certificate → CA certificate**.
- The app’s `network_security_config.xml` trusts user CAs only for `alembic.lan`; it does **not** trust arbitrary user CAs globally.

## 6. Verify read-only boundary

From the app:
- Confirm there are no buttons to change strategy, risk, mode, or kill-switch.
- Confirm all four tabs load data from the server.
- Pull-to-refresh updates the timestamp and data age.
- Enable airplane mode and reopen the app: cached data appears with an offline indicator and age.

From the server:
- A monitor access token must receive `403` on every admin/config/strategy/weight/labeling/order mutation. This is enforced by the existing authorization matrix tests.

## 7. Push notifications (optional)

1. Place `google-services.json` in `mobile/android/app/` before building.
2. Mount the Firebase service account JSON at runtime on the server as `FIREBASE_SERVICE_ACCOUNT_PATH`.
3. Ensure each device registers its Firebase Installation ID through the
   authenticated device endpoint; the backend requires Firebase Admin SDK 7.5+
   for direct FID targeting.
4. Generic lock-screen copy and opaque `event_id` are sent; no NAV, ticker, or token is included.

## 8. Operational checks

| Check | Expected |
| --- | --- |
| Server reachable, market open | Stato shows **OPERATIVO** and NAV |
| Killswitch active | Stato shows **BLOCCATO**, event detail opens, push sent |
| Portfolio cycle late | Warning incident, escalates to critical after configured duration |
| LAN unreachable | Cached data with offline banner, no crash |
| App version below minimum | Server returns `426 Upgrade Required` |

## 9. Revocation

- To revoke a device: delete the `monitor_devices` row or set `revoked_at`.
- The app purges its vault and cache on next launch when the refresh fails.
- To revoke a session: set `monitor_sessions.revoked_at`.

## 10. Known external-only gates

- Real LAN reverse proxy / TLS termination and operator CA.
- Firebase project and `google-services.json` for real FCM.
- Release signing keystore and secure storage.
- Server-side monitor user provisioning script (planned follow-up).
- End-to-end Pixel 9 instrumentation on physical hardware (CI uses compile/unit tests only).
