-- 041_mobile_monitoring.sql
-- MOB-01 (#91): persistence foundation for the read-only mobile monitor.
-- Adds monitor identities, rotating sessions, registered devices, coherent
-- portfolio snapshots, operator events with history, and the notification
-- outbox. No existing runtime behavior is changed.
--
-- UUIDs are generated server-side. Refresh tokens are stored only as hashes.
-- Financial columns keep NULL for unavailable broker data and are never coerced
-- to zero. One open/escalated incident is allowed per stable fingerprint, and
-- one delivery is allowed per (event, device, transition).
SET lock_timeout = '2s';

-- Monitor users: separate, non-admin identities with case-normalized usernames.
CREATE TABLE IF NOT EXISTS monitor_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(50) NOT NULL,
    password_hash   TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT monitor_username_lowercase CHECK (username = LOWER(username)),
    CONSTRAINT monitor_username_unique UNIQUE (username)
);

CREATE INDEX IF NOT EXISTS idx_monitor_users_enabled
    ON monitor_users (enabled);

-- Registered devices per monitor user. installation_id is scoped to the user;
-- the Firebase installation id is optional until push registration succeeds.
CREATE TABLE IF NOT EXISTS monitor_devices (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES monitor_users (id) ON DELETE CASCADE,
    installation_id         VARCHAR(64) NOT NULL,
    firebase_installation_id VARCHAR(128),
    name                    VARCHAR(100),
    app_version             VARCHAR(20),
    push_enabled            BOOLEAN NOT NULL DEFAULT FALSE,
    last_seen_at            TIMESTAMPTZ,
    revoked_at              TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT monitor_device_installation_unique UNIQUE (user_id, installation_id)
);

CREATE INDEX IF NOT EXISTS idx_monitor_devices_user
    ON monitor_devices (user_id, revoked_at, created_at DESC);

-- Rotating refresh sessions. Family reuse detection: a rotated token that is
-- presented again revokes the whole family. Hashed tokens are stored; raw tokens
-- never appear in the database.
CREATE TABLE IF NOT EXISTS monitor_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES monitor_users (id) ON DELETE CASCADE,
    device_id           UUID REFERENCES monitor_devices (id) ON DELETE SET NULL,
    refresh_token_hash  TEXT NOT NULL,
    family_id           UUID NOT NULL,
    expires_at          TIMESTAMPTZ NOT NULL,
    last_used_at        TIMESTAMPTZ,
    rotated_at          TIMESTAMPTZ,
    revoked_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_monitor_sessions_active
    ON monitor_sessions (user_id, device_id, revoked_at, expires_at)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_monitor_sessions_family
    ON monitor_sessions (family_id, created_at);

-- Immutable, versioned monitoring snapshots assembled server-side. Stored
-- every five minutes during expected windows and on material state transitions.
CREATE TABLE IF NOT EXISTS portfolio_monitor_snapshots (
    id                      BIGSERIAL PRIMARY KEY,
    snapshot_id             UUID NOT NULL UNIQUE,
    as_of                   TIMESTAMPTZ NOT NULL,
    broker_environment      VARCHAR(20),
    mode                    VARCHAR(30),
    nav                     NUMERIC(18, 2),
    previous_close_equity   NUMERIC(18, 2),
    nav_change_today        NUMERIC(18, 2),
    cash                    NUMERIC(18, 2),
    gross_exposure          NUMERIC(10, 6),
    gross_exposure_limit    NUMERIC(10, 6),
    unrealized_pnl          NUMERIC(18, 2),
    current_drawdown        NUMERIC(10, 6),
    drawdown_limit          NUMERIC(10, 6),
    open_positions          INTEGER,
    source                  VARCHAR(50),
    pipeline_health         JSONB,
    degradations            JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_portfolio_monitor_snapshots_as_of
    ON portfolio_monitor_snapshots (as_of DESC);

-- Mobile operator events / alert incidents. A stable fingerprint groups
-- repeated observations and their recovery into one timeline item.
CREATE TABLE IF NOT EXISTS mobile_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    fingerprint         VARCHAR(255) NOT NULL,
    kind                VARCHAR(50) NOT NULL,
    category            VARCHAR(50) NOT NULL,
    severity            VARCHAR(20) NOT NULL,
    status              VARCHAR(20) NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL,
    first_observed_at   TIMESTAMPTZ NOT NULL,
    last_observed_at    TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ,
    title               TEXT NOT NULL,
    summary             TEXT,
    entity_type         VARCHAR(50),
    entity_id           VARCHAR(255),
    details             JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT mobile_events_severity_check
        CHECK (severity IN ('critical', 'warning', 'info')),
    CONSTRAINT mobile_events_status_check
        CHECK (status IN ('open', 'escalated', 'recovered', 'closed'))
);

-- One open/escalated incident per fingerprint.
CREATE UNIQUE INDEX IF NOT EXISTS idx_mobile_events_active_fingerprint
    ON mobile_events (fingerprint)
    WHERE status IN ('open', 'escalated');

-- Cursor ordering for event feed: (occurred_at DESC, id DESC).
CREATE INDEX IF NOT EXISTS idx_mobile_events_cursor
    ON mobile_events (occurred_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_mobile_events_status_category
    ON mobile_events (status, category, occurred_at DESC);

-- History of incident transitions (open -> escalate -> recover -> close).
CREATE TABLE IF NOT EXISTS mobile_event_history (
    id              BIGSERIAL PRIMARY KEY,
    event_id        UUID NOT NULL REFERENCES mobile_events (id) ON DELETE CASCADE,
    state           VARCHAR(30) NOT NULL,
    severity        VARCHAR(20),
    details         JSONB,
    occurred_at     TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_mobile_event_history_event
    ON mobile_event_history (event_id, occurred_at DESC);

-- Notification outbox: one delivery row per event transition and device.
-- Retry bookkeeping, provider message id, and redacted error codes are stored
-- server-side; no financial/ticker/token detail lives here.
CREATE TABLE IF NOT EXISTS mobile_notification_deliveries (
    id                  BIGSERIAL PRIMARY KEY,
    event_id            UUID NOT NULL REFERENCES mobile_events (id) ON DELETE CASCADE,
    device_id           UUID NOT NULL REFERENCES monitor_devices (id) ON DELETE CASCADE,
    transition          VARCHAR(30) NOT NULL,
    attempt_count       INTEGER NOT NULL DEFAULT 0,
    next_attempt_at     TIMESTAMPTZ,
    provider_message_id VARCHAR(255),
    sent_at             TIMESTAMPTZ,
    failed_at           TIMESTAMPTZ,
    error_code          VARCHAR(50),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT mobile_deliveries_unique UNIQUE (event_id, device_id, transition)
);

CREATE INDEX IF NOT EXISTS idx_mobile_deliveries_due
    ON mobile_notification_deliveries (next_attempt_at, sent_at, failed_at)
    WHERE sent_at IS NULL AND failed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_mobile_deliveries_event
    ON mobile_notification_deliveries (event_id, transition, created_at DESC);
