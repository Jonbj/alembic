-- Migration 024: Add SIGNAL_STALE_SKIP and SIGNAL_DUPLICATE_SKIP to audit_action_enum
-- P1-S4-FRESHNESS-IDEMPOTENCY: freshness gate and idempotency key for S4 signals.
-- These values are written to audit_log when a signal is dropped for being stale or
-- when a signal_id has already fired an order in the current session date.
ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'SIGNAL_STALE_SKIP';
ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS 'SIGNAL_DUPLICATE_SKIP';
