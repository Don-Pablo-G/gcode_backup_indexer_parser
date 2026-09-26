"""Path-specific folder tree map (machine + multi-tags + exclude).

Sidecar next to the database: ``folder_tree_map.yaml``.

Unlike name-wide ``folder_colour_aliases`` / ``machine_folders.yaml``, rules here
are **full paths** (absolute, or ``root`` + ``rel``). The **longest matching
path prefix** wins over shorter tree rules and over name-based role aliases.

Schema::

    version: 1
    rules:
      - path: "D:/Backup/15.09.2026/VF2S/Pawel"   # absolute preferred
        machine_id: haas-vf-2                      # optional
        tags: [wip, fixture]                       # multi-tag; empty = clear roles
        exclude: false
      - root: "D:/Extra"
        rel: "scrap"
        exclude: true

Reindex reloads this file and reapplies assignments without reopening the tree UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Optional, Sequence

import yaml

from gcode_index.models import COLOUR_EXCLUDE

TREE_MAP_FILENAME = "folder_tree_map.yaml"


def tree_map_path_for_target(target: Path | str) -> Path:
    return Path(target) / TREE_MAP_FILENAME


def normalize_roles_list(raw: Any) -> list[str]:
    """Normalize tags from list / CSV / single string → sorted unique ids."""
    if raw is None:
        return []
    items: list[str] = []
    if isinstance(raw, str):
        items = [p.strip() for p in raw.replace(";", ",").split(",")]
    elif isinstance(raw, (list, tuple, set)):
        for x in raw:
            if x is None:
                continue
            s = str(x).strip()
            if "," in s or ";" in s:
                items.extend(normalize_roles_list(s))
            elif s:
                items.append(s)
    else:
        s = str(raw).strip()
        if s:
            items.append(s)
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.casefold().replace(" ", "_").replace("-", "_")
        if not key or key == COLOUR_EXCLUDE or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return sorted(out)


def roles_to_db(roles: Sequence[str] | None) -> Optional[str]:
    cleaned = normalize_roles_list(list(roles or []))
    return ",".join(cleaned) if cleaned else None


def roles_from_db(raw: Optional[str]) -> list[str]:
    return normalize_roles_list(raw)


def _norm_abs(path: Path | str) -> str:
    """Stable absolute path key (posix-ish, casefold for compare)."""
    try:
        p = Path(path).expanduser().resolve()
    except OSError:
        p = Path(path).expanduser()
    # Keep Windows drive letters; use as_posix for separators in storage
    return str(p).replace("\\", "/")


def _norm_key(path: Path | str) -> str:
    return _norm_abs(path).casefold()


@dataclass
class FolderTreeRule:
    """One path-prefix rule from the tree map."""

    path: str  # absolute (normalized /)
    machine_id: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    exclude: bool = False

    def __post_init__(self) -> None:
        self.path = _norm_abs(self.path)
        mid = (self.machine_id or "").strip()
        self.machine_id = mid or None
        self.tags = normalize_roles_list(self.tags)
        self.exclude = bool(self.exclude)

    @property
    def key(self) -> str:
        return self.path.casefold()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"path": self.path}
        if self.machine_id:
            d["machine_id"] = self.machine_id
        if self.tags:
            d["tags"] = list(self.tags)
        if self.exclude:
            d["exclude"] = True
        return d


@dataclass
class FolderTreeMap:
    """Path-prefix rules; longest match wins."""

    rules: list[FolderTreeRule] = field(default_factory=list)

    def __post_init__(self) -> None:
        by_key: dict[str, FolderTreeRule] = {}
        for rule in self.rules:
            if not rule.path:
                continue
            by_key[rule.key] = rule
        # Longest paths first for linear scan convenience
        self.rules = sorted(by_key.values(), key=lambda r: len(r.key), reverse=True)

    def __len__(self) -> int:
        return len(self.rules)

    def set_rule(
        self,
        path: Path | str,
        *,
        machine_id: Optional[str] = None,
        tags: Optional[Sequence[str]] = None,
        exclude: bool = False,
        clear: bool = False,
    ) -> None:
        """Upsert or clear a rule for ``path``."""
        key = _norm_key(path)
        others = [r for r in self.rules if r.key != key]
        if clear:
            self.rules = sorted(others, key=lambda r: len(r.key), reverse=True)
            return
        rule = FolderTreeRule(
            path=_norm_abs(path),
            machine_id=machine_id,
            tags=list(tags or []),
            exclude=exclude,
        )
        # Drop empty no-op rules
        if not rule.machine_id and not rule.tags and not rule.exclude:
            self.rules = sorted(others, key=lambda r: len(r.key), reverse=True)
            return
        others.append(rule)
        self.rules = sorted(others, key=lambda r: len(r.key), reverse=True)

    def get_exact(self, path: Path | str) -> Optional[FolderTreeRule]:
        key = _norm_key(path)
        for r in self.rules:
            if r.key == key:
                return r
        return None

    def resolve(self, path: Path | str) -> Optional[FolderTreeRule]:
        """Longest path-prefix rule that contains ``path`` (or equals it)."""
        key = _norm_key(path)
        best: Optional[FolderTreeRule] = None
        best_len = -1
        for r in self.rules:
            rk = r.key
            if key == rk or key.startswith(rk.rstrip("/") + "/"):
                if len(rk) > best_len:
                    best = r
                    best_len = len(rk)
        return best

    def resolve_for_source(
        self,
        *,
        scan_root: Path | str | None,
        source_path: str,
    ) -> Optional[FolderTreeRule]:
        """Resolve using absolute source file path under ``scan_root``."""
        if not source_path:
            return None
        raw = str(source_path)
        is_win_abs = len(raw) >= 2 and raw[1] == ":"
        if Path(raw).is_absolute() or is_win_abs:
            return self.resolve(raw)
        if not scan_root:
            return None
        return self.resolve(Path(scan_root) / raw)

    def inherited_from(
        self, path: Path | str
    ) -> tuple[Optional[FolderTreeRule], Optional[FolderTreeRule]]:
        """Return ``(exact_rule, inherited_rule)`` for UI (inherited = parent prefix)."""
        exact = self.get_exact(path)
        key = _norm_key(path)
        parent = str(Path(_norm_abs(path)).parent).replace("\\", "/")
        inherited = self.resolve(parent) if parent and parent.casefold() != key else None
        if inherited is not None and exact is not None and inherited.key == exact.key:
            inherited = None
        return exact, inherited


def load_folder_tree_map(path: Path | str) -> FolderTreeMap:
    p = Path(path)
    if not p.is_file():
        return FolderTreeMap()
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return FolderTreeMap()
    raw_rules: list[Any] = []
    if isinstance(data, list):
        raw_rules = data
    elif isinstance(data, dict):
        raw_rules = list(data.get("rules") or [])
    rules: list[FolderTreeRule] = []
    for item in raw_rules:
        rule = _parse_rule(item)
        if rule is not None:
            rules.append(rule)
    return FolderTreeMap(rules=rules)


def save_folder_tree_map(path: Path | str, tree_map: FolderTreeMap) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "_comment": (
            "Folder tree map (path-specific). Longest path prefix wins over "
            "name-wide role aliases. tags may list multiple roles (e.g. fixture+wip). "
            "exclude skips the branch. machine_id optional. Reindex reapplies these rules."
        ),
        "version": 1,
        "rules": [r.to_dict() for r in sorted(tree_map.rules, key=lambda r: r.path.casefold())],
    }
    p.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return p


def _parse_rule(item: Any) -> Optional[FolderTreeRule]:
    if isinstance(item, FolderTreeRule):
        return item if item.path else None
    if not isinstance(item, dict):
        return None
    path_raw = item.get("path")
    if not path_raw:
        root = item.get("root") or item.get("scan_root")
        rel = item.get("rel") or item.get("relative") or item.get("folder")
        if root and rel:
            path_raw = str(Path(str(root)) / str(rel))
        elif root:
            path_raw = str(root)
        else:
            return None
    tags = item.get("tags")
    if tags is None:
        # legacy single role fields
        tags = item.get("tag") or item.get("role") or item.get("colour") or item.get("color")
    return FolderTreeRule(
        path=str(path_raw),
        machine_id=(
            str(item["machine_id"]).strip()
            if item.get("machine_id")
            else (str(item["machine"]).strip() if item.get("machine") else None)
        ),
        tags=normalize_roles_list(tags),
        exclude=bool(item.get("exclude") or item.get("skip")),
    )


def list_child_dirs(path: Path | str) -> list[Path]:
    """Immediate subdirectories (lazy tree). Sorted by name."""
    p = Path(path)
    if not p.is_dir():
        return []
    try:
        kids = [c for c in p.iterdir() if c.is_dir()]
    except OSError:
        return []
    return sorted(kids, key=lambda c: c.name.casefold())
