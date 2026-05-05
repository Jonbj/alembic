-- Migration 003: extend weight_update_log.source to include auto_apply and freeze
-- Safe to run on existing data — only changes the constraint definition.

ALTER TABLE weight_update_log
  DROP CONSTRAINT weight_update_log_source_check;

ALTER TABLE weight_update_log
  ADD CONSTRAINT weight_update_log_source_check
  CHECK (source IN ('suggestion', 'override', 'expired', 'auto_apply', 'freeze'));
