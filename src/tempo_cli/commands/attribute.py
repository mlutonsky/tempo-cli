from __future__ import annotations

import typer

from ..client import TempoClient
from ..models import normalise_attribute
from ..output import emit, emit_error

app = typer.Typer(help="Tempo work attributes (custom worklog fields).", no_args_is_help=True)


@app.command("list")
def list_():
    """List configured work attributes (custom fields on worklogs)."""
    try:
        with TempoClient() as client:
            results = list(client.paginate("/work-attributes"))
        emit([normalise_attribute(a) for a in results])
    except Exception as e:
        emit_error(e)
