-- Widen model_id from varchar(50) to text.
-- Ensemble model IDs like "ensemble:kimi-k2.6:cloud+qwen3.5:397b+deepseek-v4-pro:cloud+glm-5.1:cloud"
-- exceed 50 characters and caused write failures in the sentiment worker.
ALTER TABLE sentiment_signals ALTER COLUMN model_id TYPE text;
