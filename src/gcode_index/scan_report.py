"""Post-scan quality report (#14) and duplicate grouping helpers (#13)."""

from __future__ import annotations

from gcode_index.i18n import DEFAULT_LANG, t as i18n_t

import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from gcode_index.models import ScanResult
from gcode_index.scanner import UNKNOWN_MACHINE_ID, UNKNOWN_MACHINE_LABEL

# Source types that are Haas NGC / loose ``*.nc.copy`` siblings
_COPY_SUFFIX = "_copy"

# Near-duplicate: sizes within this relative difference count as similar
DEFAULT_NEAR_SIZE_RATIO = 0.05
# Also accept absolute slack for tiny files
DEFAULT_NEAR_SIZE_ABS = 64


@dataclass
class ScanReport:
    """Summary of one index run for the scan report panel."""

    run_id: Optional[str] = None
    instance_count: int = 0
    file_count: int = 0
    unknown_folder_count: int = 0
    per_machine: list[tuple[str, int]] = field(default_factory=list)
    copy_count: int = 0
    copy_by_type: list[tuple[str, int]] = field(default_factory=list)
    unknown_program_count: int = 0
    unknown_sample_paths: list[str] = field(default_factory=list)
    unknown_folders: list[tuple[str, str]] = field(default_factory=list)
    # (date_folder, machine_folder)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # path, note
    errors: list[tuple[str, str]] = field(default_factory=list)
    provenance_counts: dict[str, int] = field(default_factory=dict)
    source_type_counts: list[tuple[str, int]] = field(default_factory=list)


@dataclass
class DuplicateGroup:
    """One cluster of exact or near-duplicate program instances."""

    kind: str  # "exact" | "near"
    label: str
    members: list  # sqlite3.Row or mapping


def _machine_display(machine_id: Optional[str], machine_label: Optional[str]) -> str:
    mid = (machine_id or "").strip() or "?"
    label = (machine_label or "").strip()
    if label and label != mid:
        return f"{label} ({mid})"
    return mid


def _is_copy_type(source_type: Optional[str]) -> bool:
    st = (source_type or "").strip()
    return st.endswith(_COPY_SUFFIX)


def scan_report_from_result(
    result: ScanResult,
    *,
    run_id: Optional[str] = None,
    unknown_sample_limit: int = 40,
) -> ScanReport:
    """Build a report directly from an in-memory ``ScanResult`` (post-scan)."""
    machine_counts: Counter[str] = Counter()
    copy_types: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    prov: Counter[str] = Counter()
    unknown_paths: list[str] = []
    copy_count = 0
    unknown_prog = 0

    for inst in result.instances:
        display = _machine_display(inst.machine_id, inst.machine_label)
        machine_counts[display] += 1
        type_counts[inst.source_type or "?"] += 1
        prov[inst.provenance or "backup"] += 1
        if _is_copy_type(inst.source_type):
            copy_count += 1
            copy_types[inst.source_type or "?"] += 1
        if (inst.machine_id or "").casefold() == UNKNOWN_MACHINE_ID:
            unknown_prog += 1
            if len(unknown_paths) < unknown_sample_limit:
                unknown_paths.append(inst.source_path)

    skipped = [
        (fs.source_path, fs.note or "")
        for fs in result.files_seen
        if fs.status == "skipped"
    ]
    errors = [
        (fs.source_path, fs.note or "")
        for fs in result.files_seen
        if fs.status == "error"
    ]
    folders = [
        (u.date_folder_raw, u.machine_folder_raw) for u in result.unknowns
    ]

    return ScanReport(
        run_id=run_id,
        instance_count=len(result.instances),
        file_count=len(result.files_seen),
        unknown_folder_count=len(result.unknowns),
        per_machine=sorted(machine_counts.items(), key=lambda kv: (-kv[1], kv[0].casefold())),
        copy_count=copy_count,
        copy_by_type=sorted(copy_types.items(), key=lambda kv: (-kv[1], kv[0])),
        unknown_program_count=unknown_prog,
        unknown_sample_paths=unknown_paths,
        unknown_folders=folders,
        skipped=skipped,
        errors=errors,
        provenance_counts=dict(prov),
        source_type_counts=sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0])),
    )


def load_scan_report(
    conn: sqlite3.Connection,
    *,
    run_id: Optional[str] = None,
    unknown_sample_limit: int = 40,
) -> Optional[ScanReport]:
    """Rebuild a report from ``index_runs`` + related tables (latest run by default)."""
    conn.row_factory = sqlite3.Row
    if run_id:
        run = conn.execute(
            "SELECT * FROM index_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
    else:
        run = conn.execute(
            "SELECT * FROM index_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    if run is None:
        return None
    rid = run["run_id"]

    machine_counts: Counter[str] = Counter()
    copy_types: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    prov: Counter[str] = Counter()
    unknown_paths: list[str] = []
    copy_count = 0
    unknown_prog = 0
    instance_count = 0

    for row in conn.execute(
        """
        SELECT machine_id, machine_label, source_type, provenance, source_path
        FROM program_instances WHERE run_id = ?
        """,
        (rid,),
    ):
        instance_count += 1
        display = _machine_display(row["machine_id"], row["machine_label"])
        machine_counts[display] += 1
        st = row["source_type"] or "?"
        type_counts[st] += 1
        prov[row["provenance"] or "backup"] += 1
        if _is_copy_type(st):
            copy_count += 1
            copy_types[st] += 1
        if (row["machine_id"] or "").casefold() == UNKNOWN_MACHINE_ID:
            unknown_prog += 1
            if len(unknown_paths) < unknown_sample_limit:
                unknown_paths.append(row["source_path"] or "")

    skipped = [
        (r["source_path"] or "", r["note"] or "")
        for r in conn.execute(
            "SELECT source_path, note FROM files_seen WHERE run_id = ? AND status = 'skipped'",
            (rid,),
        )
    ]
    errors = [
        (r["source_path"] or "", r["note"] or "")
        for r in conn.execute(
            "SELECT source_path, note FROM files_seen WHERE run_id = ? AND status = 'error'",
            (rid,),
        )
    ]
    folders = [
        (r["date_folder_raw"] or "", r["machine_folder_raw"] or "")
        for r in conn.execute(
            "SELECT date_folder_raw, machine_folder_raw FROM unknowns WHERE run_id = ?",
            (rid,),
        )
    ]

    return ScanReport(
        run_id=rid,
        instance_count=instance_count,
        file_count=int(run["file_count"] or len(skipped) + len(errors)),
        unknown_folder_count=int(run["unknown_count"] or len(folders)),
        per_machine=sorted(machine_counts.items(), key=lambda kv: (-kv[1], kv[0].casefold())),
        copy_count=copy_count,
        copy_by_type=sorted(copy_types.items(), key=lambda kv: (-kv[1], kv[0])),
        unknown_program_count=unknown_prog,
        unknown_sample_paths=unknown_paths,
        unknown_folders=folders,
        skipped=skipped,
        errors=errors,
        provenance_counts=dict(prov),
        source_type_counts=sorted(type_counts.items(), key=lambda kv: (-kv[1], kv[0])),
    )


def format_scan_report(report: ScanReport, *, lang: str | None = None) -> str:
    """Plain-text body for the scan report panel / CLI."""
    code = lang or DEFAULT_LANG
    lines: list[str] = []
    rid = (report.run_id or "")[:8]
    run_sfx = i18n_t(code, "report_run_suffix", id=rid) if rid else ""
    lines.append(i18n_t(code, "report_title", run=run_sfx))
    lines.append("=" * 48)
    lines.append(
        i18n_t(
            code,
            "report_summary",
            instances=report.instance_count,
            files=report.file_count,
            unknown=report.unknown_folder_count,
        )
    )
    if report.provenance_counts:
        bits = ", ".join(f"{k}={v}" for k, v in sorted(report.provenance_counts.items()))
        lines.append(i18n_t(code, "report_flags", bits=bits))
    lines.append("")
    lines.append(i18n_t(code, "report_per_machine"))
    lines.append("-" * 48)
    if report.per_machine:
        for name, n in report.per_machine:
            lines.append(f"  {n:5d}  {name}")
    else:
        lines.append(i18n_t(code, "report_none"))

    lines.append("")
    lines.append(i18n_t(code, "report_source_types"))
    lines.append("-" * 48)
    for name, n in report.source_type_counts:
        lines.append(f"  {n:5d}  {name}")

    lines.append("")
    lines.append(i18n_t(code, "report_copies", n=report.copy_count))
    for name, n in report.copy_by_type:
        lines.append(f"  {n:5d}  {name}")

    lines.append("")
    lines.append(
        i18n_t(
            code,
            "report_unknown_programs",
            label=UNKNOWN_MACHINE_LABEL,
            n=report.unknown_program_count,
        )
    )
    for path in report.unknown_sample_paths:
        lines.append(f"  · {path}")
    if report.unknown_program_count > len(report.unknown_sample_paths):
        extra = report.unknown_program_count - len(report.unknown_sample_paths)
        lines.append(i18n_t(code, "report_more", n=extra))

    lines.append("")
    lines.append(i18n_t(code, "report_unmapped", n=len(report.unknown_folders)))
    for date_f, mach_f in report.unknown_folders:
        lines.append(f"  · {date_f} / {mach_f}")

    lines.append("")
    lines.append(i18n_t(code, "report_skipped", n=len(report.skipped)))
    for path, note in report.skipped:
        suffix = f" — {note}" if note else ""
        lines.append(f"  · {path}{suffix}")

    lines.append("")
    lines.append(i18n_t(code, "report_errors", n=len(report.errors)))
    for path, note in report.errors:
        suffix = f" — {note}" if note else ""
        lines.append(f"  · {path}{suffix}")

    return "\n".join(lines) + "\n"


def _size_similar(
    a: Optional[int],
    b: Optional[int],
    *,
    ratio: float = DEFAULT_NEAR_SIZE_RATIO,
    abs_slack: int = DEFAULT_NEAR_SIZE_ABS,
) -> bool:
    if a is None or b is None:
        return False
    if a < 0 or b < 0:
        return False
    if a == b:
        return True
    diff = abs(a - b)
    if diff <= abs_slack:
        return True
    denom = max(a, b, 1)
    return (diff / denom) <= ratio


def find_exact_duplicate_groups(
    conn: sqlite3.Connection,
    *,
    limit_groups: int = 200,
) -> list[DuplicateGroup]:
    """Groups sharing the same non-empty ``program_sha256`` (2+ members).

    Falls back to ``content_sha256`` only when ``program_sha256`` is absent
    (pre-reindex DBs) — that fallback is whole-file and will not cross glued↔.nc.
    """
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(program_instances)")}
    sha_col = "program_sha256" if "program_sha256" in cols else "content_sha256"
    sha_rows = conn.execute(
        f"""
        SELECT {sha_col} AS body_sha, COUNT(*) AS n
        FROM program_instances
        WHERE {sha_col} IS NOT NULL AND {sha_col} != ''
        GROUP BY {sha_col}
        HAVING n >= 2
        ORDER BY n DESC
        LIMIT ?
        """,
        (limit_groups,),
    ).fetchall()

    groups: list[DuplicateGroup] = []
    for hit in sha_rows:
        sha = hit["body_sha"]
        members = list(
            conn.execute(
                f"""
                SELECT instance_id, program_number, part_number, machine_id, machine_label,
                       machine_folder_raw, date_folder_raw, backup_date, source_path,
                       line_start, line_end, byte_start, byte_end, source_type,
                       folder_path, control_family, source_size, content_sha256,
                       program_sha256,
                       provenance, scan_root, programmer
                FROM program_instances
                WHERE {sha_col} = ?
                ORDER BY backup_date DESC, machine_id, program_number
                """,
                (sha,),
            )
        )
        if len(members) < 2:
            continue
        # Build label
        machines = sorted(
            {
                _machine_display(m["machine_id"], m["machine_label"])
                for m in members
            }
        )
        types = sorted({str(m["source_type"] or "") for m in members})
        mach_note = ", ".join(machines[:4])
        if len(machines) > 4:
            mach_note += f", +{len(machines) - 4}"
        type_note = "/".join(t for t in types if t)[:40]
        label = (
            f"Exact body · {len(members)} · {sha[:12]}… · {mach_note}"
            + (f" · {type_note}" if type_note else "")
        )
        groups.append(DuplicateGroup(kind="exact", label=label, members=members))
    return groups


def find_near_duplicate_groups(
    conn: sqlite3.Connection,
    *,
    size_ratio: float = DEFAULT_NEAR_SIZE_RATIO,
    size_abs: int = DEFAULT_NEAR_SIZE_ABS,
    limit_groups: int = 200,
) -> list[DuplicateGroup]:
    """Same program #, different program-body hash, similar ``source_size``.

    Catches copies/drift across machines or dates that are not byte-identical.
    """
    conn.row_factory = sqlite3.Row
    cols = {row[1] for row in conn.execute("PRAGMA table_info(program_instances)")}
    has_prog = "program_sha256" in cols
    # Pull candidates grouped by casefold program number
    by_prog: dict[str, list] = defaultdict(list)
    sel = """
        SELECT instance_id, program_number, part_number, machine_id, machine_label,
               machine_folder_raw, date_folder_raw, backup_date, source_path,
               line_start, line_end, byte_start, byte_end, source_type,
               folder_path, control_family, source_size, content_sha256,
               provenance, scan_root, programmer
    """
    if has_prog:
        sel = sel.replace(
            "content_sha256,",
            "content_sha256, program_sha256,",
        )
    for row in conn.execute(
        sel
        + """
        FROM program_instances
        WHERE program_number IS NOT NULL AND program_number != ''
        ORDER BY program_number, backup_date DESC
        """
    ):
        key = str(row["program_number"]).casefold()
        by_prog[key].append(row)

    def _body_sha(row) -> str:
        keys = row.keys()
        if "program_sha256" in keys and row["program_sha256"]:
            return str(row["program_sha256"]).strip()
        return str(row["content_sha256"] or "").strip()

    groups: list[DuplicateGroup] = []
    for prog_key, rows in by_prog.items():
        if len(rows) < 2:
            continue
        # Cluster by similar size; require at least two distinct body SHA (or missing)
        used: set[int] = set()
        for i, a in enumerate(rows):
            if i in used:
                continue
            cluster = [a]
            used.add(i)
            sha_a = _body_sha(a)
            size_a = a["source_size"]
            for j in range(i + 1, len(rows)):
                if j in used:
                    continue
                b = rows[j]
                if not _size_similar(
                    size_a, b["source_size"], ratio=size_ratio, abs_slack=size_abs
                ):
                    continue
                sha_b = _body_sha(b)
                # Skip if both have same non-empty SHA (those belong in exact)
                if sha_a and sha_b and sha_a == sha_b:
                    continue
                cluster.append(b)
                used.add(j)
            if len(cluster) < 2:
                continue
            shas = {_body_sha(m) for m in cluster}
            # Need genuine near-dup signal: not all identical SHA
            non_empty = {s for s in shas if s}
            if len(non_empty) <= 1 and "" not in shas:
                continue
            machines = sorted(
                {
                    _machine_display(m["machine_id"], m["machine_label"])
                    for m in cluster
                }
            )
            display_prog = str(cluster[0]["program_number"] or prog_key)
            mach_note = ", ".join(machines[:4])
            if len(machines) > 4:
                mach_note += f", +{len(machines) - 4}"
            label = (
                f"Near {display_prog} · {len(cluster)} instances · "
                f"similar size · {mach_note}"
            )
            groups.append(DuplicateGroup(kind="near", label=label, members=cluster))
            if len(groups) >= limit_groups:
                return groups
    return groups


def find_duplicate_groups(
    conn: sqlite3.Connection,
    *,
    include_near: bool = True,
    size_ratio: float = DEFAULT_NEAR_SIZE_RATIO,
    size_abs: int = DEFAULT_NEAR_SIZE_ABS,
    limit_groups: int = 200,
) -> list[DuplicateGroup]:
    """Exact SHA groups first, then near-duplicates."""
    out = find_exact_duplicate_groups(conn, limit_groups=limit_groups)
    if include_near:
        remaining = max(0, limit_groups - len(out))
        if remaining:
            out.extend(
                find_near_duplicate_groups(
                    conn,
                    size_ratio=size_ratio,
                    size_abs=size_abs,
                    limit_groups=remaining,
                )
            )
    return out
