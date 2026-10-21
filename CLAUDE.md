# tempo-cli — Agent Guide

`tempo-cli` is a **JSON-first** CLI over the Tempo (Jira) REST API. It is designed for you, an LLM agent, to call when the user wants information from Tempo (worked time, reports) or to log/modify worklogs on their behalf.

## Contract

- **Stdout = valid JSON on success.** Pipe it straight into `jq`.
- **Errors → stderr** as `{"error": {"code": "...", "message": "...", "details": ...}}`. `details` is optional. A `tempo_api_error` also carries the HTTP `status`.
- **Exit codes:** 2 when the arguments do not parse (missing or unknown option, unknown command), 1 for every other error.
- Pass `--table` to get a human view (Rich-formatted) — but for your own parsing, leave the default.
- Every subcommand has `--help`; use it when unsure of arg shape.

## Setup the user must have done

- `TEMPO_API_TOKEN` env var set
- `acli jira` authenticated (`acli jira auth status` should succeed)

If a call fails with an auth-shaped error, check those two and tell the user.

## Argument conventions

| Convention | Examples |
|---|---|
| Issue identifier | `STAN-23298` (key) — resolved to numeric ID internally via `acli` |
| User identifier | `@me` (default) or a Jira accountId like `557058:abc…` |
| Single date (`worklog --date`, `plan --start`/`--end`) | `today`, `yesterday`, or `YYYY-MM-DD` |
| Range (`--from`/`--to`) | a single date, or a period: `this-week`, `last-week`, `this-month`, `last-month` |
| Durations | `30m`, `1h`, `1h30m`, `1.5h`, `1d` (1d = 8h) |

Range defaults:
- `--from` and `--to` both omitted: `this-month`. `schedule` uses `this-week`. `issue worklogs` and `report by-user` read the whole history of the issue.
- One of them omitted: it defaults to `today`.
- A period in either slot sets the whole range and overrides the other slot.

## Command map

### Identity
- `tempo-cli user me` → `{"accountId": "...", "source": "acli|seeded"}`
- `tempo-cli user me --account-id <id>` stores the accountId in the cache. Use it when `acli` cannot infer `@me` because no issue is assigned to the user.

### Worklog CRUD
All write commands accept `--dry-run`, which emits `{"dryRun": true, "command": "...", "would": {"method": "...", "path": "...", "body": ...}}` and exits without calling Tempo. Every real write is also recorded in `$XDG_CACHE_HOME/tempo-cli/audit.log` (one JSON-line per write).

- `tempo-cli worklog list [--issue KEY] [--user @me] [--from DATE] [--to DATE] [--limit N]`
- `tempo-cli worklog get <id>` → single worklog object
- `tempo-cli worklog add --issue KEY --duration 1h30m --date today [--description "…"] [--start HH:MM] [--user @me] [--billable-seconds N] [--attribute KEY=VALUE] [--dry-run]` → created worklog. `--billable-seconds` defaults to the duration; `--attribute` is repeatable.
- `tempo-cli worklog update <id> [--duration ...] [--description ...] [--date ...] [--start HH:MM] [--billable-seconds N] [--attribute KEY=VALUE] [--dry-run]` — if you change `--duration` without `--billable-seconds`, tempo-cli sets billable time to the new duration. Tempo PUT is replace, not patch; tempo-cli copies the existing worklog's attributes into the body by default so they survive single-field updates. `--attribute` (if passed) replaces the whole attribute set.
- `tempo-cli worklog delete <id> [--dry-run]` → `{"deleted": true, "id": ...}`

### Issue-centric (manager view)
- `tempo-cli issue worklogs KEY [--from --to]` →
  ```json
  {
    "issue": "STAN-23298",
    "issueId": 103012,
    "from": null, "to": null,
    "totalSeconds": 13800,
    "count": 12,
    "byUser": [{"accountId": "...", "displayName": "...", "seconds": 12600}, ...],
    "worklogs": [{"id": ..., "issueId": ..., "issue": "STAN-23298", "accountId": "...", "date": "...", "start": "HH:MM:SS", "seconds": ..., "billableSeconds": ..., "description": "..."}, ...]
  }
  ```
- `tempo-cli report by-user --issue KEY [--from --to]` → just the `byUser` rollup, sorted desc

### User-centric (developer view)
- `tempo-cli user worklogs [--user @me] [--from --to]` →
  ```json
  {
    "user": {"accountId": "..."},
    "from": "...", "to": "...",
    "count": 165,
    "totalSeconds": 252660,
    "byIssue": [{"issueId": 102930, "seconds": 52500}, ...],
    "byDay":   [{"date": "2026-05-19", "seconds": 23220}, ...],
    "worklogs": [...]
  }
  ```
  Note: `byIssue` here uses `issueId` only (no key resolution) for performance — a wide window can contain hundreds of distinct issues. Use `report by-issue` if you also need the keys.
- `tempo-cli report by-issue [--user @me] [--from --to] [--top N]` → top issues with `issueId` AND resolved `issue` key; also emits `totalSeconds` (full window) and `displayedSeconds` (sum of returned slice).

### Periodic reports
- `tempo-cli report week [--user @me]` →
  ```json
  {
    "period": "this-week",
    "from": "2026-05-18", "to": "2026-05-24",
    "user": {"accountId": "..."},
    "requiredSeconds": 115200,
    "loggedSeconds": 46260,
    "balanceSeconds": -68940,
    "byDay": [{"date": "...", "required": ..., "logged": ..., "type": "WORKING_DAY|NON_WORKING_DAY"}, ...]
  }
  ```
- `tempo-cli report month [--user @me]` → same shape, monthly window
- `tempo-cli report period [--user @me] [--from --to | --period this-month|last-month|this-week|last-week]` — uses Tempo's official period accounting:
  ```json
  {"from": "...", "to": "...", "requiredSeconds": N, "loggedSeconds": N,
   "balanceSeconds": N, "status": "OPEN|READY_TO_SUBMIT|WAITING_FOR_APPROVAL|APPROVED|REJECTED",
   "availableActions": ["submit", ...]}
  ```

### Project / filter rollups
- `tempo-cli report by-project --project KEY [--from --to] [--top-users N] [--top-issues N]` — all logs in a Jira project. Returns `totalSeconds` (full window) + `byUser`, `byIssue` (sliced if `--top-*` set) + `displayedUserSeconds`, `displayedIssueSeconds` (sum of slices) so an agent can detect truncation.
- `tempo-cli report by-filter --filter <id-or-name> [--from --to] [--top-users N] [--top-issues N]` — same shape, scoped to a saved Jira filter (own/favourite filters can be referenced by name).
- `tempo-cli report plan-vs-actual [--user @me] [--from --to]` → `{plannedSeconds, loggedSeconds, balanceSeconds, planCount, worklogCount}`. `plannedSeconds = sum(secondsPerDay × days-in-window)` per plan.

### Plans (capacity)
- `tempo-cli plan list [--user @me | --team N] [--from --to]`
- `tempo-cli plan get <id>`
- `tempo-cli plan add --start DATE --end DATE --per-day 4h (--issue KEY | --project KEY) [--user @me | --team N] [--description "..."] [--dry-run]`
- `tempo-cli plan update <id> [--start ...] [--end ...] [--per-day ...] [--description ...] [--dry-run]` — preserves the plan's existing TEAM vs USER assignee shape when other fields are updated.
- `tempo-cli plan delete <id> [--dry-run]`

### Work attributes (custom worklog fields)
- `tempo-cli attribute list` → `[{key, name, type, required, staticListValues}, ...]`

### Reference data
- `tempo-cli team list` → `[{"id": ..., "name": "...", "leadAccountId": "..."}, ...]`
- `tempo-cli team members <teamId>` → list of members
- `tempo-cli schedule [--user @me] [--from --to]` →
  ```json
  {
    "user": {"accountId": "..."},
    "from": "...", "to": "...",
    "totalRequiredSeconds": 115200,
    "days": [{"date": "...", "requiredSeconds": ..., "type": "WORKING_DAY|NON_WORKING_DAY"}, ...]
  }
  ```

### Self-documentation
- `tempo-cli agent-guide` → `{"path": "...", "content": "<this markdown>"}`. Useful if you don't know the path.

## Common patterns

**"How much have I worked this week?"**
```
tempo-cli report week
```

**"Who worked on STAN-23298 and how much?"**
```
tempo-cli report by-user --issue STAN-23298
```

**"Log 30 minutes to STAN-23298 with a note":**
```
tempo-cli worklog add --issue STAN-23298 --duration 30m --date today --description "code review"
```

**"What did I work on in May?"**
```
tempo-cli report by-issue --from 2026-05-01 --to 2026-05-31
```

## Failure modes you should handle

- **Missing `TEMPO_API_TOKEN`** — tell the user to export it.
- **`acli` not authenticated / not installed** — surface to the user; we cannot proceed without it for key/`@me` resolution.
- **Unknown issue key** — `acli` returns no id; the error message will say so. Confirm the key with the user.
- **Stale identity or names** — the `@me` accountId, issue key ↔ id, project key → id and accountId → displayName lookups are cached without expiry in `$XDG_CACHE_HOME/tempo-cli/cache.json` (default `~/.cache`). A user without a visible issue is also cached as having no displayName. Delete the file to reset.
- **HTTP 401/403 from Tempo** — token is invalid or lacks scope; tell the user to regenerate it in Tempo Settings.
- **HTTP 429 / 5xx** — the client retries with exponential backoff up to 3 attempts total (honouring `Retry-After` when present, capped at 60s). If it still fails, report the error to the user. Note: writes (POST/PUT/DELETE) are NOT retried on transient network errors to avoid duplicate worklogs/plans; only the server's own 429/5xx triggers a retry.

## Things this tool does NOT do (v1)

- Tempo accounts / cost centres (CRUD)
- Timesheet approval workflow (submit / approve / reject)
- Self-hosted Tempo Server (Cloud-only)
