from __future__ import annotations

from importlib import resources
from pathlib import Path

import click
import typer

from . import __version__
from .commands import attribute, issue, plan, report, team, user, worklog
from .commands.schedule import schedule as _schedule_cmd
from .errors import InputError
from .output import emit, emit_error

app = typer.Typer(
    name="tempo-cli",
    help=(
        "JSON-first CLI over the Tempo (Jira) REST API. Designed for LLM agents and humans. "
        "Set TEMPO_API_TOKEN in your env. Issue key / @me resolution uses local `acli`."
    ),
    no_args_is_help=True,
)


def _version_cb(value: bool) -> None:
    if value:
        emit({"name": "tempo-cli", "version": __version__})
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    table: bool = typer.Option(False, "--table", help="Render output as a human-readable table instead of JSON."),
    version: bool = typer.Option(
        False, "--version", help="Print version and exit.", is_eager=True, callback=_version_cb
    ),
):
    ctx.ensure_object(dict)
    ctx.obj["table"] = table


@app.command("agent-guide")
def agent_guide():
    """Return the agent-facing CLAUDE.md so LLMs can fetch it from anywhere.

    Output JSON shape: {"path": "<absolute path or package resource>", "content": "<markdown>"}.
    """
    # Prefer the in-package copy (bundled in the wheel via hatch force-include);
    # fall back to the repo root for an editable install during development.
    try:
        bundled = resources.files("tempo_cli").joinpath("CLAUDE.md")
        if bundled.is_file():
            emit({"path": str(bundled), "content": bundled.read_text(encoding="utf-8")})
            return
    except (FileNotFoundError, ModuleNotFoundError):
        pass
    repo_path = Path(__file__).resolve().parent.parent.parent / "CLAUDE.md"
    if repo_path.exists():
        emit({"path": str(repo_path), "content": repo_path.read_text(encoding="utf-8")})
        return
    emit_error(
        InputError(
            "CLAUDE.md not found next to the install; see the README in the source repo.",
            details={"searched": [str(repo_path)]},
        )
    )


app.add_typer(worklog.app, name="worklog")
app.add_typer(issue.app, name="issue")
app.add_typer(user.app, name="user")
app.add_typer(report.app, name="report")
app.add_typer(team.app, name="team")
app.add_typer(plan.app, name="plan")
app.add_typer(attribute.app, name="attribute")
app.command("schedule")(_schedule_cmd)


def main() -> None:
    """Console-script entry point.

    Wraps `app()` so that Click/Typer arg-parsing errors (missing options, bad
    parameter types, unknown commands) are emitted as the documented JSON
    error envelope on stderr instead of Click's default "Usage:\\nError: ..."
    plain-text output.
    """
    try:
        app(standalone_mode=False)
    except click.exceptions.Exit as e:  # raised by typer.Exit() — propagate cleanly
        raise SystemExit(e.exit_code) from e
    except click.exceptions.Abort as e:
        raise SystemExit(130) from e
    except click.UsageError as e:
        details: dict = {}
        if e.ctx is not None and e.ctx.command_path:
            details["command"] = e.ctx.command_path
        emit_error(InputError(e.format_message(), details=details or None), exit_code=2)
    except click.ClickException as e:
        emit_error(InputError(e.format_message()), exit_code=e.exit_code or 1)


if __name__ == "__main__":
    main()
