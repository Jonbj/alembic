-- Add human-readable reason field to execution_decisions
ALTER TABLE execution_decisions ADD COLUMN IF NOT EXISTS reason TEXT;
