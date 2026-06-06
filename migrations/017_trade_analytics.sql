-- Phase A: Trade Analytics Engine
ALTER TABLE trades ADD COLUMN IF NOT EXISTS postmortem_diagnosis TEXT;
