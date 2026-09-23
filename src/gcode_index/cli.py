from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from gcode_index import __version__
from gcode_index.aliases import AliasMap, default_aliases_path
from gcode_index.db import open_db, search_instances, write_scan_result
from gcode_index.excel_export import export_excel
from gcode_index.scanner import scan_backup_tree

app = typer.Typer(
    name="gcode-index",
    help="Index CNC backup trees into a portable SQLite catalog of program instances.",
    no_args_is_help=True,
)

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", help="Show version and exit.", is_eager=True
    ),
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command("scan")
def scan_cmd(
    backup_root: Path = typer.Argument(
        ..., exists=True, file_okay=False, dir_okay=True, readable=True,
        help="Root of the CNC backup folder tree.",
    ),
    db: Path = typer.Option(
        ...,
        "--db",
        help="Output SQLite path (e.g. gcode_index.sqlite).",
    ),
    excel: Optional[Path] = typer.Option(
        None,
        "--excel",
        help="Optional Excel (.xlsx) export path.",
    ),
    aliases: Optional[Path] = typer.Option(
        None,
        "--aliases",
        exists=True,
        dir_okay=False,
        help="YAML alias map (default: bundled aliases.yaml).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Scan a backup tree and write program_instances into SQLite (+ optional Excel)."""
    _setup_logging(verbose)
    aliases_path = aliases or default_aliases_path()
    alias_map = AliasMap.load(aliases_path)
    typer.echo(f"Scanning {backup_root} …")
    result = scan_backup_tree(backup_root, alias_map)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = open_db(db)
    run_id = write_scan_result(
        conn,
        backup_root=str(Path(backup_root).resolve()),
        aliases_path=str(aliases_path),
        result=result,
    )
    conn.close()
    typer.echo(
        f"Wrote {len(result.instances)} instances, "
        f"{len(result.files_seen)} files_seen, "
        f"{len(result.unknowns)} unknowns → {db} (run_id={run_id})"
    )
    if excel is not None:
        export_excel(excel, result.instances)
        typer.echo(f"Excel export → {excel}")


@app.command("search")
def search_cmd(
    db: Path = typer.Argument(..., exists=True, dir_okay=False),
    query: str = typer.Argument(..., help="Must contain ≥4 digits."),
    limit: int = typer.Option(50, "--limit", "-n"),
) -> None:
    """Search program_number / part_number (substring). Requires ≥4 digits in query."""
    digit_count = sum(1 for ch in query if ch.isdigit())
    if digit_count < 4:
        typer.echo("Error: query must contain at least 4 digits.", err=True)
        raise typer.Exit(code=2)
    conn = open_db(db)
    try:
        rows = search_instances(conn, query, limit=limit)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    finally:
        conn.close()
    if not rows:
        typer.echo("No matches.")
        return
    typer.echo(
        f"{'program':<12} {'part':<28} {'machine':<18} {'date':<28} type"
    )
    for r in rows:
        part = (r["part_number"] or "")[:28]
        typer.echo(
            f"{r['program_number']:<12} {part:<28} {r['machine_id']:<18} "
            f"{str(r['backup_date'])[:28]:<28} {r['source_type']}"
        )


@app.command("extract")
def extract_cmd(
    db: Path = typer.Argument(..., exists=True, dir_okay=False),
    instance_id: str = typer.Argument(..., help="instance_id from the index"),
    backup_root: Path = typer.Option(
        ...,
        "--backup-root",
        exists=True,
        file_okay=False,
        help="Backup root used when paths in the DB are relative.",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", "-o", help="Write extracted text to this file (default: stdout)."
    ),
) -> None:
    """Thin extract helper: slice glued span or copy whole-file .nc for external parsers."""
    import sqlite3

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT source_path, line_start, line_end, byte_start, byte_end, source_type
        FROM program_instances WHERE instance_id = ?
        """,
        (instance_id,),
    ).fetchone()
    conn.close()
    if row is None:
        typer.echo(f"instance_id not found: {instance_id}", err=True)
        raise typer.Exit(code=1)

    src = Path(row["source_path"])
    if not src.is_absolute():
        src = Path(backup_root) / src
    if not src.is_file():
        typer.echo(f"source file missing: {src}", err=True)
        raise typer.Exit(code=1)

    glued = row["source_type"] in (
        "haas_pgm_glued",
        "fanuc_all_fldr",
        "fanuc_all_prog",
    )
    if glued and row["byte_start"] is not None and row["byte_end"] is not None:
        with open(src, "rb") as f:
            f.seek(int(row["byte_start"]))
            data = f.read(int(row["byte_end"]) - int(row["byte_start"]))
        text = data.decode("ascii", errors="replace")
    elif glued and row["line_start"] is not None and row["line_end"] is not None:
        lines = src.read_bytes().splitlines(keepends=True)
        chunk = lines[int(row["line_start"]) - 1 : int(row["line_end"])]
        text = b"".join(chunk).decode("ascii", errors="replace")
    else:
        text = src.read_text(encoding="ascii", errors="replace")

    if out is not None:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"Wrote {out}")
    else:
        typer.echo(text, nl=False)


if __name__ == "__main__":
    app()
