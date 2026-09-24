from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer

from gcode_index import __version__
from gcode_index.aliases import AliasMap, default_aliases_path, local_aliases_path_for_target
from gcode_index.db import open_db, write_scan_result
from gcode_index.excel_export import export_excel
from gcode_index.extract import ExtractError, extract_instance_to_path, extract_text, fetch_instance
from gcode_index.folder_map import FolderMachineMap
from gcode_index.scanner import scan_backup_tree, scan_with_extra_roots

app = typer.Typer(
    name="gcode-index",
    help="Index CNC backup trees into a portable SQLite catalog of program instances.",
    no_args_is_help=True,
    invoke_without_command=True,
)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    return


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
    local_aliases: Optional[Path] = typer.Option(
        None,
        "--local-aliases",
        dir_okay=False,
        help="Shop-local aliases overlay (default: aliases.local.yaml next to --db).",
    ),
    folder_map: Optional[Path] = typer.Option(
        None,
        "--folder-map",
        exists=True,
        dir_okay=False,
        help="Optional machine_folders.yaml (folder→machine; wins over aliases).",
    ),
    extra_root: Optional[list[Path]] = typer.Option(
        None,
        "--extra-root",
        exists=True,
        file_okay=False,
        dir_okay=True,
        readable=True,
        help="Additional folder to scan (yellow flag). Repeatable.",
    ),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        help="Reuse unchanged source files from an existing --db (skip re-parse).",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Scan a backup tree and write program_instances into SQLite (+ optional Excel)."""
    _setup_logging(verbose)
    aliases_path = aliases or default_aliases_path()
    local_path = local_aliases
    if local_path is None:
        candidate = local_aliases_path_for_target(db.parent)
        if candidate.is_file():
            local_path = candidate
    alias_map = AliasMap.load_merged(aliases_path, local_path)
    fmap = FolderMachineMap.load(folder_map) if folder_map else None
    extras = list(extra_root or [])
    cache = None
    if incremental and db.is_file():
        from gcode_index.scan_cache import load_scan_cache

        prior = open_db(db)
        try:
            cache = load_scan_cache(prior)
        finally:
            prior.close()
        typer.echo(f"Incremental: loaded cache for {len(cache.by_key)} source file(s)")
    if extras:
        typer.echo(f"Scanning {backup_root} + {len(extras)} extra root(s) …")
        result = scan_with_extra_roots(
            backup_root,
            alias_map,
            extra_roots=extras,
            folder_map=fmap if fmap and fmap.assignments else None,
            cache=cache,
        )
    else:
        typer.echo(f"Scanning {backup_root} …")
        result = scan_backup_tree(
            backup_root,
            alias_map,
            folder_map=fmap if fmap and fmap.assignments else None,
            cache=cache,
        )
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.is_file():
        db.unlink()
    conn = open_db(db)
    run_id = write_scan_result(
        conn,
        backup_root=str(Path(backup_root).resolve()),
        aliases_path=str(aliases_path),
        result=result,
    )
    conn.close()
    n_cached = sum(1 for fs in result.files_seen if fs.status == "cached")
    typer.echo(
        f"Wrote {len(result.instances)} instances, "
        f"{len(result.files_seen)} files_seen"
        f"{f' ({n_cached} cached)' if n_cached else ''}, "
        f"{len(result.unknowns)} unknowns → {db} (run_id={run_id})"
    )
    if excel is not None:
        export_excel(excel, result.instances)
        typer.echo(f"Excel export → {excel}")


@app.command("search")
def search_cmd(
    db: Path = typer.Argument(..., exists=True, dir_okay=False),
    query: str = typer.Argument(
        ...,
        help="Free text (letters/digits/symbols) — program #, part #, path, machine.",
    ),
    limit: int = typer.Option(50, "--limit", "-n"),
    machine: Optional[str] = typer.Option(
        None, "--machine", "-m", help="Filter by machine id or label."
    ),
    date_from: Optional[str] = typer.Option(
        None, "--from", help="Inclusive start date (DD.MM.YYYY or YYYY-MM-DD)."
    ),
    date_to: Optional[str] = typer.Option(
        None, "--to", help="Inclusive end date (DD.MM.YYYY or YYYY-MM-DD)."
    ),
    source_type: Optional[str] = typer.Option(
        None, "--type", help="Filter source_type (e.g. loose_nc, haas_pgm_glued)."
    ),
) -> None:
    """Search / filter the index (free text + optional machine / date / type)."""
    from gcode_index.db import query_instances

    conn = open_db(db)
    try:
        rows = query_instances(
            conn,
            text=query,
            machine=machine,
            date_from=date_from,
            date_to=date_to,
            source_type=source_type,
            limit=limit,
        )
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
    """Slice glued span or copy whole-file .nc for an external parser."""
    import sqlite3

    conn = sqlite3.connect(str(db))
    try:
        if out is not None:
            path = extract_instance_to_path(
                conn, instance_id, out, backup_root=backup_root
            )
            typer.echo(f"Wrote {path}")
        else:
            row = fetch_instance(conn, instance_id)
            text = extract_text(row, backup_root=backup_root)
            typer.echo(text, nl=False)
    except ExtractError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    finally:
        conn.close()


if __name__ == "__main__":
    app()
