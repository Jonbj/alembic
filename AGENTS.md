# Alembic Agent Instructions

## Roadmap Management (Mandatory)

Before selecting or implementing roadmap work, read
`docs/agents/wayfinder-roadmap-method.md` and run:

```bash
gh issue list --state open
```

GitHub issue `#21`, "Alembic Roadmap (Wayfinder map)", is the sole source of
truth for roadmap state. Its child issues are the units of open work.

- Do not track progress by adding or changing checkboxes in Markdown plan docs.
- Treat `docs/superpowers/plans/` as design specifications, not status trackers.
- Treat work as done only when its child issue is closed, preferably by a merged
  PR containing `closes #N`.
- Respect native `blocked_by` dependencies. Work only on an open, unassigned,
  `ready-for-agent` child whose blockers are all closed.
- Claim a child before working on it with
  `gh issue edit <n> --add-assignee @me`.
- Do not implement `ready-for-human` issues. Prepare decision context and stop.
- When resolving a child, record the result on the issue and append a context
  pointer to the Decisions-so-far section of `#21`.

Never infer the current frontier from a static document or a remembered issue
graph. Query GitHub at session start. `docs/OPEN_WORK_AUDIT_2026-07-15.md` is an
historical snapshot only.

Tracker conventions live in `docs/agents/issue-tracker.md`; label conventions
live in `docs/agents/triage-labels.md`.
