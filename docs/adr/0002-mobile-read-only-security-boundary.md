# Enforce mobile read-only access at a dedicated API boundary

The Android client will use versioned endpoints under `/api/mobile/v1` and device-bound monitor identities whose access tokens cannot satisfy the existing admin dependency. Mobile access is read-only for the trading domain; the only non-read operations are authentication and registering/revoking that user's notification device. Reusing the current admin JWT was rejected because hiding write controls in the UI would not prevent a stolen or manually replayed token from mutating Alembic.

## Consequences

The backend needs separate monitor users, rotating refresh sessions, explicit JWT audience/scopes, device revocation, and authorization tests proving that monitor credentials receive `403` on every operational mutation. The Android application never receives broker, database, Redis, admin API, Firebase service-account, or signing-key secrets.
