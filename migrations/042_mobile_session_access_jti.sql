-- Bind each mobile access token to its issuing refresh session.
--
-- Migration 041 was already deployed before MOB-02 remediation. Keep that
-- migration immutable and add the revocation binding through this forward-only
-- upgrade so existing databases receive the new column and lookup index.

ALTER TABLE monitor_sessions
    ADD COLUMN IF NOT EXISTS access_jti UUID;

CREATE UNIQUE INDEX IF NOT EXISTS idx_monitor_sessions_access_jti
    ON monitor_sessions (access_jti)
    WHERE access_jti IS NOT NULL;
