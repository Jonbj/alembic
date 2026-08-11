# Alembic — Trading System

An LLM-based algorithmic trading system ("Alpha Miner" paradigm): LLMs run offline in background workers producing sentiment signals; the execution engine reads pre-computed signals from Redis/PostgreSQL and never calls an LLM in the hot path. The active order path is the weight-then-order portfolio orchestrator (`execution.engine=portfolio`).

## Language

### Capital allocation

**Sleeve** (capital sleeve):
The fraction of portfolio capital assigned to a single strategy. Strategies express target weights as fractions of *their own* sleeve, not of the whole portfolio.
_Avoid:_ allocation, bucket, pot.

**Allocation_pct**:
The governance lever that assigns a fraction of the total portfolio to a strategy's sleeve. It is the sole lever for *capital allocation between strategies*; it is not the sole lever for actual deployed capital (see regime multiplier, vol-targeter).
_Avoid:_ weight, size.

**Regime multiplier**:
A macro risk throttle (×0.2–1.0) that scales deployed notional, orthogonal to allocation governance. Derived from a daily LLM regime label; falls back to a VIX mapping, then to 0.2 when absent.
_Avoid:_ regime scale (that name is taken by the loss-feedback lever), sizing factor.

### Signal & gating

**Signal freshness**:
How recently a sentiment signal was *generated* (≤4h to be usable). A property of the signal itself.
_Avoid:_ news age, staleness (conflates with event-time).

**Event-time gate**:
How recently the *underlying news* a signal is based on was published (≤2h for S4 entry). Distinct from signal freshness: a freshly-generated signal can rest on stale news and be blocked at entry while still usable for exit-protection.
_Avoid:_ freshness (that name is taken by signal freshness), published_at (that's the column, not the concept).

**Feedback entry threshold**:
A hard binary gate that excludes a symbol from entry when `abs(score) < threshold`. Raised by the loss-feedback ratchet. Unlike a sizing signal, it does not reduce a position's weight — it drops the symbol entirely.
_Avoid:_ entry score, cutoff.

**Fired-signal idempotency**:
A per-session dedup so a discrete signal (S4) is not acted on twice across cycles. Distinct from the pyramiding guard (which keys on open positions, not signal identity).
_Avoid:_ dedup (too generic; also used for news content deduplication).

### Risk feedback

**Loss-feedback ratchet**:
The mechanism that raises the feedback entry threshold and lowers the regime scale after losing streaks or an EWMA of trade R-multiples at or below −0.50, decaying back toward baseline on wins or on quiet time. Its adjustments carry a 96h TTL (raised from 48h on 2026-07-21: the check runs Mon–Fri only, so a 48h key expired over the weekend and the de-risk disarmed itself every Monday).
_Avoid:_ feedback loop (too generic), throttle.

**Regime scale** (feedback):
~~A per-strategy lever (`feedback:regime_scale:<strategy>`) that scaled a sleeve's sizing down after that sleeve's own losses — ×0.80 per trigger, floored at 0.20. It was wired into the portfolio path (per-strategy, before the weighted-sum merge), gated by `loss_feedback.apply_regime_scale` (`false`/`true`/list of strategy ids). **Retired 2026-08-10** (#134, lifecycle: `docs/F8_LIFECYCLE_HISTORY_2026-08-10.md`): premise falsified on the per-DAY unit (S1 +0.065, S4 +0.017 — no detectable dependence), mechanism independently broken (trigger reset the same clock the decay branch read). Code recovered from git; the surviving lever is the entry threshold above, governed by #191.~~
_Avoid:_ regime multiplier (that is the macro throttle; this name is free now — use only when describing the historical F8).

**Teaching trade**:
A closed trade the loss-feedback ratchet learns from — exits tagged `stop_loss` or `portfolio_sell` only. Other exits (`sentiment_reversal`, `LEGACY_FLATTEN`) are invisible to the ratchet, so a sleeve's teaching subset is not the same population as its P&L.
_Avoid:_ closed trade (broader), losing trade (a teaching trade can be a win).

### Exits

**Stop-loss cooldown**:
A same-day re-entry lockout: a symbol stopped out today cannot be re-bought until midnight UTC. Anti-churn.
_Avoid:_ lockout (ambiguous), stop-out window.

**Sentiment reversal exit**:
A forced exit of a held position when its current LLM score drops below −0.20, regardless of news age.
_Avoid:_ reversal sell, score exit.

**Pyramiding guard**:
Prevents a second entry on a symbol already held (no pyramiding). Keys on open trades; fail-closed on DB failure.
_Avoid:_ position check, double-entry.

**Vol-targeter**:
Scales buy orders toward a target portfolio volatility (`scale = target_vol / estimated_vol`, clamped [0.5, 2.0]); leaves sells unchanged. Operates before the constraint enforcer.
_Avoid:_ vol scaling, leverage overlay.