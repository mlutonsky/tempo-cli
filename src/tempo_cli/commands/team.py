from __future__ import annotations

import typer

from ..client import TempoClient
from ..models import normalise_team
from ..output import emit, emit_error

app = typer.Typer(help="Tempo teams.", no_args_is_help=True)


@app.command("list")
def list_():
    """List Tempo teams visible to the token."""
    try:
        with TempoClient() as client:
            results = list(client.paginate("/teams"))
        emit([normalise_team(t) for t in results])
    except Exception as e:
        emit_error(e)


@app.command("members")
def members(team_id: int):
    """List members of a team."""
    try:
        with TempoClient() as client:
            results = list(client.paginate(f"/teams/{team_id}/members"))
        emit(results)
    except Exception as e:
        emit_error(e)
