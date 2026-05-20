# tempo-cli

> ⚠️ **AI-generated** — The majority of this repository was written by an LLM coding agent (Claude). Read the code before pointing it at production data. Provided **as-is** under the [MIT license](LICENSE) — no warranty, no responsibility.

A JSON-first CLI over the [Tempo](https://www.tempo.io/) (Jira) REST API.

Primary consumer: **LLM agents**. Secondary: humans. Output defaults to JSON on stdout for trivial parsing; pass `--table` for a human-readable view.

## What it does

- Read worklogs (by issue, by user, by project, by saved JQL filter, by date range)
- Log time on behalf of a user (create / update / delete worklogs, including custom work attributes)
- Aggregate time per user on a given issue (manager view)
- Aggregate own time per issue / per day / per period (developer view)
- Required-vs-logged reports for the current week / month / Tempo period (with approval status)
- CRUD for Tempo plans, plus a plan-vs-actual report
- List work attributes (custom worklog fields configured in Tempo)
- Browse Tempo teams and user schedules

## Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv)
- [`acli`](https://developer.atlassian.com/cloud/acli/) authenticated against your Jira site (used for `issueKey` ↔ `issueId` resolution and `@me` lookup — no global Atlassian token required)
- A Tempo API token (Tempo → Settings → API Integration → New token)

## Install

Install the latest release directly from GitHub:

```bash
uv tool install git+https://github.com/mlutonsky/tempo-cli.git
# or with pipx
pipx install git+https://github.com/mlutonsky/tempo-cli.git
```

To pin to a specific tag:

```bash
uv tool install git+https://github.com/mlutonsky/tempo-cli.git@v0.1.0
```

### Local / editable install

If you've cloned the repo and want local edits to be picked up immediately:

```bash
uv tool install -e ~/bin/tempo-cli
```

If you bump dependencies in `pyproject.toml`, reinstall:

```bash
uv tool install --reinstall -e ~/bin/tempo-cli
```

## Configuration

Set the Tempo API token in your shell:

```bash
export TEMPO_API_TOKEN="…"
```

For convenience, add it to your shell profile (or a secrets manager you source).

## Usage examples

```bash
# Who am I?
tempo-cli user me

# All worklogs on an issue
tempo-cli issue worklogs STAN-23298

# Manager view: who worked how much on this issue
tempo-cli report by-user --issue STAN-23298

# My time this week
tempo-cli report week

# Tempo period view with approval status
tempo-cli report period

# My time in May 2026, grouped by issue
tempo-cli report by-issue --from 2026-05-01 --to 2026-05-31

# Project-wide rollup with by-user and by-issue breakdowns
tempo-cli report by-project --project STAN --top-users 5

# Saved JQL filter rollup (numeric id or exact filter name)
tempo-cli report by-filter --filter "Kanban filter"

# Plan-vs-actual
tempo-cli report plan-vs-actual

# List my plans
tempo-cli plan list

# Log time
tempo-cli worklog add --issue STAN-23298 --duration 1h30m --date today --description "review"

# Log time with a Tempo work attribute
tempo-cli worklog add --issue STAN-23298 --duration 1h --date today --attribute _Activity_=Development

# List configured work attributes
tempo-cli attribute list

# Human view
tempo-cli issue worklogs STAN-23298 --table
```

Dates accept literal `YYYY-MM-DD` or shortcuts: `today`, `yesterday`, `this-week`, `last-week`, `this-month`, `last-month`.

`--user` accepts `@me` (default) or a Jira accountId.

## For LLM agents

Read [CLAUDE.md](CLAUDE.md) (or run `tempo-cli agent-guide`) for the structured cheat sheet of subcommands, JSON output shapes, and conventions.

## License

MIT. See [LICENSE](LICENSE).
