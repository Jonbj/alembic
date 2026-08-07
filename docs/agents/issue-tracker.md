# Issue tracker: GitHub

Issues and PRDs for this repo live as GitHub issues. Use the `gh` CLI for all operations.

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`, filtering comments by `jq` and also fetching labels.
- **List issues**: `gh issue list --state open --json number,title,body,labels,comments --jq '[.[] | {number, title, body, labels: [.labels[].name], comments: [.comments[].body]}]'` with appropriate `--label` and `--state` filters.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

Infer the repo from `git remote -v` — `gh` does this automatically when run inside a clone.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external PRs as feature requests; `/triage` reads this flag.)_

When set to `yes`, PRs run through the same labels and states as issues, using the `gh pr` equivalents:

- **Read a PR**: `gh pr view <number> --comments` and `gh pr diff <number>` for the diff.
- **List external PRs for triage**: `gh pr list --state open --json number,title,body,labels,author,authorAssociation,comments` then keep only `authorAssociation` of `CONTRIBUTOR`, `FIRST_TIME_CONTRIBUTOR`, or `NONE` (drop `OWNER`/`MEMBER`/`COLLABORATOR`).
- **Comment / label / close**: `gh pr comment`, `gh pr edit --add-label`/`--remove-label`, `gh pr close`.

GitHub shares one number space across issues and PRs, so a bare `#42` may be either — resolve with `gh pr view 42` and fall back to `gh issue view 42`.

## When a skill says "publish to the issue tracker"

Create a GitHub issue.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body. `gh issue create --label wayfinder:map`.
- **Child ticket**: an issue linked to the map as a GitHub sub-issue (`gh api` on the sub-issues endpoint). Where sub-issues aren't enabled, add the child to a task list in the map body and put `Part of #<map>` at the top of the child body. Labels: `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`). Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: GitHub's **native issue dependencies** — the canonical, UI-visible representation. Add an edge with `gh api --method POST repos/<owner>/<repo>/issues/<child>/dependencies/blocked_by -F issue_id=<blocker-db-id>`, where `<blocker-db-id>` is the blocker's numeric **database id** (`gh api repos/<owner>/<repo>/issues/<n> --jq .id`, _not_ the `#number` or `node_id`). GitHub reports `issue_dependencies_summary.blocked_by` (open blockers only — the live gate). Where dependencies aren't available, fall back to a `Blocked by: #<n>, #<n>` line at the top of the child body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: list the map's open children (`gh issue list --state open`, scoped to the map's sub-issues / task list), drop any with an open blocker (`issue_dependencies_summary.blocked_by > 0`, or an open issue in the `Blocked by` line) or an assignee; first in map order wins.
- **Claim**: `gh issue edit <n> --add-assignee @me` — the session's first write.
- **Resolve**: `gh issue comment <n> --body "<answer>"`, then `gh issue close <n>`, then append a context pointer (gist + link) to the map's Decisions-so-far.

## Autonomous roadmap loop (active 2026-08-06 → 2026-09-28)

`scripts/roadmap_agent_loop.sh` runs four times a day (cron: 07/12/17/21) and works **one**
issue per run in an isolated worktree, then reviews the PR and merges it if two gates both pass.

The work is delegated to models **other than** the one that designed this machinery — the
`MOTORI` array (`codex`, `glm52`, `minimax`), rotated one per run. `glm52` and `minimax` run
Claude Code with a different model underneath (`ollama launch claude --model glm-5.2:cloud` /
`minimax-m3:cloud`): same tool, different head. Two reasons, the second
mattering more: whoever wrote the queue and the criteria is not the right observer to judge
whether the output respects them; and different models fail differently, so a single model
across twenty issues repeats one blind spot twenty times with nobody noticing. If no engine
in the list is installed the run is **cancelled** — there is deliberately no fallback, since
a silent one would put the work back exactly where it must not be. It never merges: the CI
`test` job in this repo is chronically red for environmental reasons, so an automatic merge
would be gating on a signal that isn't there.

During the observation freeze (#171) the agent does **not** decide its own scope. Two
independent locks do, and an issue is worked only if it clears both:

1. **`scripts/roadmap_queue.txt`** — the order, top-down.
2. **the `freeze-ok` label** — the permission: correctness, instrumentation, measurement.
   Never tuning.

Neither the queue file nor the labels may be modified by the agent, and the prompt forbids it
along with `docs/evidence/{OBSERVATION_CHARTER.md,findings.json,market_daily.jsonl}`. Changing
what the loop is allowed to touch is an operator action.

Operator commands:

```bash
scripts/roadmap_agent_loop.sh --dry-run       # which issue is next, no session consumed
scripts/roadmap_agent_loop.sh --motori        # engine status, incl. who is rate-limited
scripts/roadmap_agent_loop.sh --prova glm52   # smoke-test one engine (60s)
scripts/roadmap_agent_loop.sh --sblocca glm52 # early return from the bench (rarely needed)
gh issue list --label freeze-ok --state open
cat logs/roadmap_agent_state.tsv              # issue <TAB> failed attempts (2 = out of rotation)
```

**Review and merge (decided 2026-08-07).** After the PR is opened, two gates decide:

1. **Mechanical** — the set of tests failing in the PR minus the set failing on `main`, for the
   *same commit SHA*. This repo's CI is chronically red for environmental reasons, so its pass/fail
   says nothing; the **difference** says everything. Zero new failures is the bar.
2. **Human-shaped** — a model **other than the implementer** reviews the diff against the issue,
   the operator's scoping comments, and the freeze charter, then emits `VERDETTO: APPROVA` or
   `VERDETTO: RESPINGI`. It runs with write tools removed: a written instruction not to edit and a
   denied permission are not the same thing. Its review is posted to the PR either way.

Both gates green → the loop merges. Anything else — reject, CI that never finished, no second
engine available — leaves the PR open with a Telegram. **A merge is not a deploy:** images are
baked, so `main` moves ahead of production until someone rebuilds.

**Rate limits.** An exhausted engine is not a broken engine. Its output is matched against a
deliberately broad set of signatures; on a hit it is benched for 3h and the run **fails over to
the next available engine instead of burning the slot**. Critically, a rate-limited run is *not*
charged to the issue — otherwise two quota exhaustions would drop an issue out of rotation
without anyone having actually looked at it. Benched engines return **on their own** at expiry;
`--sblocca` only exists for when quota comes back early. If every engine is benched the run is
postponed, not failed.

An issue that yields no PR twice drops out of rotation rather than burning sessions. A run
that concludes an issue isn't workable is expected to comment on it and open nothing — an
honest no-op beats a filler PR.
