-- 043_mobile_fcm_delivery.sql
-- MOB-04 (#94): recovery hysteresis and retry-safe outbox leases.
SET lock_timeout = '2s';

ALTER TABLE mobile_events
    ADD COLUMN IF NOT EXISTS clear_observation_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE mobile_notification_deliveries
    ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ;

ALTER TABLE mobile_notification_deliveries
    ADD COLUMN IF NOT EXISTS claim_id UUID;

CREATE INDEX IF NOT EXISTS idx_mobile_notification_deliveries_due
    ON mobile_notification_deliveries (next_attempt_at, created_at)
    WHERE sent_at IS NULL AND failed_at IS NULL;
