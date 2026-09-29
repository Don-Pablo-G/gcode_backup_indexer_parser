from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from gcode_index.models import MachineInfo

_PUNCT_RE = re.compile(r"[^a-z0-9]+")
# GUI display suffix for catalog rows; also stripped from user-typed spellings.
_BUNDLED_TAG_RE = re.compile(r"\[\s*bundled\s*\]", re.IGNORECASE)

LOCAL_ALIASES_FILENAME = "aliases.local.yaml"
# Appended in the Machines & aliases list for read-only catalog spellings.
BUNDLED_ALIAS_DISPLAY_SUFFIX = "  [bundled]"


def sanitize_local_alias_spelling(raw: str) -> str:
    """Strip user-entered ``[bundled]`` markers from a shop-local folder spelling.

    The Machines & aliases UI marks catalog rows with
    :data:`BUNDLED_ALIAS_DISPLAY_SUFFIX`. If that text is typed into an alias
    field, it must not become part of the stored key
    (``normalize_folder_name("vf2s [bundled]")`` → ``vf2sbundled``) and must
    not block delete via a naive ``" [bundled]" in display`` check.
    """
    s = _BUNDLED_TAG_RE.sub(" ", str(raw or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def remove_alias_list_selection(
    local_aliases: list[str],
    bundled_aliases: list[str],
    index: int,
) -> tuple[Optional[list[str]], str]:
    """Classify / apply a Listbox selection for Machines & aliases.

    List order matches the GUI: local rows first, then bundled. Returns
    ``(new_local_aliases, status)`` where status is:

    - ``"removed"`` — local row deleted (``new_local_aliases`` is the new list)
    - ``"bundled"`` — true catalog row; do not delete (``new_local_aliases`` is None)
    - ``"invalid"`` — out of range (``new_local_aliases`` is None)

    Classification is by **index**, never by whether the display label contains
    ``[bundled]`` — a shop-local spelling that includes that text stays deletable.
    """
    locals_ = list(local_aliases)
    bundled = list(bundled_aliases)
    if 0 <= index < len(locals_):
        del locals_[index]
        return locals_, "removed"
    if len(locals_) <= index < len(locals_) + len(bundled):
        return None, "bundled"
    return None, "invalid"


def normalize_folder_name(raw: str) -> str:
    """Lowercase, strip spaces/-/_, then strip remaining punctuation.

    Used for **exact** full-string equality and as the stored alias key.
    Fuzzy matching no longer runs against this concatenated form — see
    ``folder_name_tokens`` / ``match_tier_in_raw``.
    """
    s = raw.strip().lower()
    s = s.replace(" ", "").replace("-", "").replace("_", "")
    s = _PUNCT_RE.sub("", s)
    return s


def folder_name_tokens(raw: str) -> list[str]:
    """Split a folder name or O-line ``(…)`` body into match tokens.

    Separators: space, ``_``, ``-``, and any other non ``[a-z0-9]`` punctuation.
    Each token is lowercased alphanumerics only (empty pieces dropped).
    """
    s = (raw or "").strip().lower()
    if not s:
        return []
    return [p for p in _PUNCT_RE.split(s) if p]


def default_aliases_path() -> Path:
    """Bundled aliases.yaml next to package, PyInstaller bundle, or repo root."""
    pkg = Path(__file__).resolve().parent
    candidates = [
        pkg / "data" / "aliases.yaml",
        pkg.parent.parent / "aliases.yaml",
        Path.cwd() / "aliases.yaml",
    ]
    # PyInstaller onedir/onefile: data files land under sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates = [
            meipass / "gcode_index" / "data" / "aliases.yaml",
            meipass / "aliases.yaml",
            *candidates,
        ]
    for c in candidates:
        if c.is_file():
            return c
    return pkg / "data" / "aliases.yaml"


def local_aliases_path_for_target(target: Path | str) -> Path:
    """Shop-local alias overlay stored next to the index database."""
    return Path(target) / LOCAL_ALIASES_FILENAME


# Substring / prefix fallbacks (avoid tiny keys like "sl" matching both SL-10 and SL-20).
# Shared by machines, roles, recipients, and O-line header matchers.
# Fuzzy runs **within a single token** only (not the fully stripped mash).
MIN_SUBSTRING_ALIAS_LEN = 4
MIN_PREFIX_ALIAS_LEN = 3
# Prefix within a token only when the leftover suffix is short (VF2→VF2S = +1;
# blocks pat→pattyn = +3). Substring ≥4 is unchanged.
MAX_PREFIX_RESIDUAL = 2
# Back-compat private aliases used inside this module historically.
_MIN_SUBSTRING_ALIAS_LEN = MIN_SUBSTRING_ALIAS_LEN
_MIN_PREFIX_ALIAS_LEN = MIN_PREFIX_ALIAS_LEN

# Score tiers for exact-then-fuzzy (higher wins; then longer needle).
FUZZY_TIER_EXACT = 2
FUZZY_TIER_SUBSTRING = 1
FUZZY_TIER_PREFIX = 0


def fuzzy_match_tier(needle: str, haystack: str) -> Optional[int]:
    """Within-token fuzzy: exact → substring (≥4) → prefix (≥3, residual ≤2).

    ``needle`` and ``haystack`` are single already-normalized tokens (or a
    single-token haystack). Prefer ``match_tier_in_raw`` for folder / O-line
    bodies so multi-token names are split first. Returns a tier, or ``None``.
    """
    if not needle or not haystack:
        return None
    if needle == haystack:
        return FUZZY_TIER_EXACT
    if len(needle) >= MIN_SUBSTRING_ALIAS_LEN and needle in haystack:
        return FUZZY_TIER_SUBSTRING
    if (
        len(needle) >= MIN_PREFIX_ALIAS_LEN
        and haystack.startswith(needle)
        and 0 < (len(haystack) - len(needle)) <= MAX_PREFIX_RESIDUAL
    ):
        return FUZZY_TIER_PREFIX
    return None


def match_tier_in_raw(needle: str, raw: str) -> Optional[int]:
    """Best tier for ``needle`` against a folder name or O-line ``(…)`` body.

    1. Exact full ``normalize_folder_name`` equality (space/_/- equivalent).
    2. Exact single token, or consecutive tokens whose concat equals needle.
    3. Fuzzy **only within one token** (substring ≥4 / prefix ≥3 residual ≤2).

    Never runs fuzzy against the fully concatenated stripped string.
    """
    if not needle:
        return None
    hay = normalize_folder_name(raw)
    if hay and needle == hay:
        return FUZZY_TIER_EXACT
    tokens = folder_name_tokens(raw)
    if not tokens:
        return None
    # Exact token or consecutive-token span (multi-word aliases like Acme Sp).
    for i in range(len(tokens)):
        acc = ""
        for j in range(i, len(tokens)):
            acc += tokens[j]
            if acc == needle:
                return FUZZY_TIER_EXACT
            if len(acc) > len(needle):
                break
    best: Optional[int] = None
    for tok in tokens:
        tier = fuzzy_match_tier(needle, tok)
        if tier is None or tier == FUZZY_TIER_EXACT:
            # Exact already handled above; skip None.
            continue
        if best is None or tier > best:
            best = tier
    return best


def best_fuzzy_key(raw_haystack: str, keys: Iterable[str]) -> Optional[str]:
    """Best normalized alias key for a raw folder / comment body.

    Exact full-normalize dict lookup is the caller's job when a key map
    exists. Here: exact token / consecutive-token span, then within-token
    substring (≥4), then within-token prefix (≥3, residual ≤2). Longest
    needle wins within the best tier. ``keys`` are already-normalized.
    """
    if not (raw_haystack or "").strip():
        return None
    key_list = [k for k in keys if k]
    if not key_list:
        return None
    best_key = ""
    best_tier = -1
    for ak in key_list:
        tier = match_tier_in_raw(ak, raw_haystack)
        if tier is None:
            continue
        # Skip full-normalize exact — caller already tried dict lookup; still
        # allow token/sequence exact (same tier value) and fuzzy tiers.
        if tier > best_tier or (tier == best_tier and len(ak) > len(best_key)):
            best_tier = tier
            best_key = ak
    return best_key or None


def _machines_from_yaml_data(data: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(data, dict):
        return {}
    machines = data.get("machines") or {}
    if not isinstance(machines, dict):
        raise ValueError("aliases file must have a 'machines' mapping")
    return {str(k): dict(v) if isinstance(v, dict) else {"machine_id": str(v)} for k, v in machines.items()}


def _sanitize_local_machines(
    local_raw: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Rewrite local alias keys, dropping empty results after strip."""
    cleaned: dict[str, dict[str, Any]] = {}
    for raw_key, entry in local_raw.items():
        key = sanitize_local_alias_spelling(str(raw_key))
        if not key:
            continue
        cleaned[key] = dict(entry) if isinstance(entry, dict) else {"machine_id": str(entry)}
    return cleaned


class AliasMap:
    def __init__(
        self,
        machines: dict[str, dict[str, Any]],
        *,
        local_keys: Optional[set[str]] = None,
        local_raw: Optional[dict[str, dict[str, Any]]] = None,
        bundled_machines: Optional[dict[str, dict[str, Any]]] = None,
    ):
        # Normalized key → entry (merged view used for resolve)
        self._machines = {normalize_folder_name(k): v for k, v in machines.items()}
        # Keys that came from the local overlay (normalized)
        self._local_keys: set[str] = set(local_keys or ())
        # Raw spelling → entry for local file round-trip (preserve folder spelling as key)
        self._local_raw: dict[str, dict[str, Any]] = dict(local_raw or {})
        # Bundled-only snapshot (normalized) so local removals can restore defaults
        if bundled_machines is not None:
            self._bundled = {
                normalize_folder_name(k): dict(v) for k, v in bundled_machines.items()
            }
        else:
            # Pure bundled load: current machines are the bundled set
            self._bundled = {
                k: dict(v) for k, v in self._machines.items() if k not in self._local_keys
            }
    @classmethod
    def load(cls, path: Optional[Path | str] = None) -> "AliasMap":
        p = Path(path) if path else default_aliases_path()
        with p.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        machines = _machines_from_yaml_data(data)
        return cls(machines)

    @classmethod
    def load_merged(
        cls,
        bundled: Optional[Path | str] = None,
        local: Optional[Path | str] = None,
    ) -> "AliasMap":
        """Load bundled aliases, then overlay shop-local aliases (local wins)."""
        base = cls.load(bundled)
        local_path = Path(local) if local else None
        if local_path is None or not local_path.is_file():
            return base
        with local_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        local_raw = _sanitize_local_machines(_machines_from_yaml_data(data))
        if not local_raw:
            return base
        merged = dict(base._machines)
        local_keys: set[str] = set()
        for raw_key, entry in local_raw.items():
            nk = normalize_folder_name(raw_key)
            merged[nk] = entry
            local_keys.add(nk)
        return cls(
            merged,
            local_keys=local_keys,
            local_raw=local_raw,
            bundled_machines=dict(base._machines),
        )

    def with_local_file(self, local: Optional[Path | str]) -> "AliasMap":
        """Return a new map with ``local`` aliases overlaid (no-op if missing)."""
        if local is None:
            return self
        local_path = Path(local)
        if not local_path.is_file():
            return self
        with local_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        local_raw = _sanitize_local_machines(_machines_from_yaml_data(data))
        if not local_raw:
            return self
        merged = dict(self._machines)
        local_keys = set(self._local_keys)
        combined_raw = dict(self._local_raw)
        for raw_key, entry in local_raw.items():
            nk = normalize_folder_name(raw_key)
            merged[nk] = entry
            local_keys.add(nk)
            combined_raw[raw_key] = entry
        return AliasMap(
            merged,
            local_keys=local_keys,
            local_raw=combined_raw,
            bundled_machines=dict(self._bundled),
        )

    def _info_from_entry(self, entry: dict[str, Any], machine_folder_raw: str) -> MachineInfo:
        return MachineInfo(
            machine_id=str(entry["machine_id"]),
            label=entry.get("label"),
            control_family=entry.get("control_family"),
            layout=entry.get("layout"),
            machine_folder_raw=machine_folder_raw,
            mapped=True,
        )

    def _lookup_fuzzy(self, machine_folder_raw: str) -> Optional[dict[str, Any]]:
        """Token-boundary fuzzy: exact token/span, else within-token substring/prefix."""
        best_key = best_fuzzy_key(machine_folder_raw, self._machines)
        if best_key:
            return self._machines[best_key]
        return None

    def resolve(self, machine_folder_raw: str) -> MachineInfo:
        key = normalize_folder_name(machine_folder_raw)
        entry = self._machines.get(key)
        if entry is None:
            entry = self._lookup_fuzzy(machine_folder_raw)
        if entry is None:
            return MachineInfo(
                machine_id=f"unmapped:{machine_folder_raw}",
                machine_folder_raw=machine_folder_raw,
                mapped=False,
            )
        return self._info_from_entry(entry, machine_folder_raw)

    def known_machine_displays(self) -> list[str]:
        """Unique ``Label (machine_id)`` strings for GUI filters (alias catalog)."""
        seen: set[str] = set()
        out: list[str] = []
        rows: list[tuple[str, str]] = []
        for entry in self._machines.values():
            mid = str(entry.get("machine_id") or "").strip()
            if not mid or mid in seen:
                continue
            seen.add(mid)
            label = str(entry.get("label") or "").strip()
            rows.append((label or mid, mid))
        rows.sort(key=lambda t: t[0].casefold())
        for label, mid in rows:
            display = f"{label} ({mid})" if label and label != mid else mid
            out.append(display)
        return out

    def info_for_machine_id(
        self,
        machine_id: str,
        machine_folder_raw: str,
    ) -> Optional[MachineInfo]:
        """Look up catalog fields (label/control/layout) by ``machine_id``."""
        mid = str(machine_id or "").strip()
        if not mid:
            return None
        for entry in self._machines.values():
            if str(entry.get("machine_id") or "").strip() == mid:
                return self._info_from_entry(entry, machine_folder_raw)
        return None

    def add_local_alias(
        self,
        folder_raw: str,
        machine_id: str,
        *,
        label: Optional[str] = None,
        control_family: Optional[str] = None,
        layout: Optional[str] = None,
    ) -> None:
        """Add/update a shop-local alias keyed by the folder name spelling."""
        raw = sanitize_local_alias_spelling(folder_raw)
        mid = str(machine_id).strip()
        if not raw or not mid or mid == "unknown" or mid.startswith("unmapped:"):
            return
        # Prefer catalog metadata when available
        catalog = self.info_for_machine_id(mid, raw)
        entry: dict[str, Any] = {"machine_id": mid}
        lab = (label or (catalog.label if catalog else None) or "").strip()
        if lab:
            entry["label"] = lab
        cf = control_family or (catalog.control_family if catalog else None)
        if cf:
            entry["control_family"] = cf
        lay = layout or (catalog.layout if catalog else None)
        if lay:
            entry["layout"] = lay
        nk = normalize_folder_name(raw)
        self._machines[nk] = entry
        self._local_keys.add(nk)
        # Drop prior local raw keys that normalize to the same spelling
        for old in list(self._local_raw):
            if normalize_folder_name(old) == nk:
                del self._local_raw[old]
        self._local_raw[raw] = entry

    def remove_local_alias(self, folder_raw: str) -> bool:
        """Remove a shop-local alias by folder spelling (or normalized match)."""
        raw = str(folder_raw).strip()
        if not raw:
            return False
        nk = normalize_folder_name(raw)
        removed = False
        for key in list(self._local_raw):
            if key == raw or normalize_folder_name(key) == nk:
                del self._local_raw[key]
                removed = True
        if nk in self._local_keys:
            self._local_keys.discard(nk)
            removed = True
        if not removed:
            return False
        # Restore bundled meaning if this key existed in the catalog
        if nk in self._bundled:
            self._machines[nk] = dict(self._bundled[nk])
        elif nk in self._machines:
            del self._machines[nk]
        return True

    def rename_local_alias(self, old_raw: str, new_raw: str) -> bool:
        """Rename the folder key of a local alias (keeps machine entry)."""
        old = str(old_raw).strip()
        new = str(new_raw).strip()
        if not old or not new:
            return False
        entry = None
        for key, ent in list(self._local_raw.items()):
            if key == old or normalize_folder_name(key) == normalize_folder_name(old):
                entry = dict(ent)
                break
        if entry is None:
            return False
        self.remove_local_alias(old)
        mid = str(entry.get("machine_id") or "").strip()
        if not mid:
            return False
        self.add_local_alias(
            new,
            mid,
            label=entry.get("label"),
            control_family=entry.get("control_family"),
            layout=entry.get("layout"),
        )
        return True

    def list_local_aliases(self) -> list[tuple[str, dict[str, Any]]]:
        """``(folder_raw, entry)`` for shop-local aliases, sorted by name."""
        rows = list(self._local_raw.items())
        rows.sort(key=lambda kv: kv[0].casefold())
        return [(k, dict(v)) for k, v in rows]

    def list_bundled_alias_keys(self) -> list[tuple[str, dict[str, Any]]]:
        """Bundled aliases (normalized keys) for read-only browsing in the GUI."""
        rows: list[tuple[str, dict[str, Any]]] = []
        for nk, entry in self._bundled.items():
            rows.append((nk, dict(entry)))
        rows.sort(key=lambda kv: kv[0].casefold())
        return rows

    def catalog_machines(self) -> list[dict[str, Any]]:
        """Unique machines from the catalog for picker UIs."""
        by_id: dict[str, dict[str, Any]] = {}
        for entry in self._machines.values():
            mid = str(entry.get("machine_id") or "").strip()
            if not mid or mid in by_id:
                continue
            by_id[mid] = {
                "machine_id": mid,
                "label": entry.get("label"),
                "control_family": entry.get("control_family"),
                "layout": entry.get("layout"),
            }
        return sorted(by_id.values(), key=lambda e: str(e.get("label") or e["machine_id"]).casefold())

    def machines_overview(self) -> list[dict[str, Any]]:
        """Machines with their folder-alias spellings (bundled + local).

        Each row::
            machine_id, label, control_family, layout,
            local_aliases: list[str],   # shop-local folder spellings
            bundled_aliases: list[str], # bundled keys not overridden locally
            aliases: list[str],         # local first, then bundled (display order)
            local_only: bool            # True when no bundled aliases remain
        """
        by_id: dict[str, dict[str, Any]] = {}

        def _ensure(mid: str, entry: dict[str, Any]) -> dict[str, Any]:
            row = by_id.get(mid)
            if row is None:
                row = {
                    "machine_id": mid,
                    "label": entry.get("label"),
                    "control_family": entry.get("control_family"),
                    "layout": entry.get("layout"),
                    "local_aliases": [],
                    "bundled_aliases": [],
                }
                by_id[mid] = row
            else:
                if not row.get("label") and entry.get("label"):
                    row["label"] = entry.get("label")
                if not row.get("control_family") and entry.get("control_family"):
                    row["control_family"] = entry.get("control_family")
                if not row.get("layout") and entry.get("layout"):
                    row["layout"] = entry.get("layout")
            return row

        local_norm: set[str] = set()
        for raw, entry in self._local_raw.items():
            mid = str(entry.get("machine_id") or "").strip()
            if not mid:
                continue
            row = _ensure(mid, entry)
            if raw not in row["local_aliases"]:
                row["local_aliases"].append(raw)
            local_norm.add(normalize_folder_name(raw))

        for nk, entry in self._bundled.items():
            mid = str(entry.get("machine_id") or "").strip()
            if not mid:
                continue
            row = _ensure(mid, entry)
            if nk in local_norm:
                continue  # local override hides bundled key in the editable list
            if nk not in row["bundled_aliases"]:
                row["bundled_aliases"].append(nk)

        out: list[dict[str, Any]] = []
        for row in by_id.values():
            row["local_aliases"] = sorted(row["local_aliases"], key=str.casefold)
            row["bundled_aliases"] = sorted(row["bundled_aliases"], key=str.casefold)
            row["aliases"] = list(row["local_aliases"]) + list(row["bundled_aliases"])
            # No remaining bundled spellings → shop-local machine (or empty draft)
            row["local_only"] = not bool(row["bundled_aliases"])
            out.append(row)
        out.sort(key=lambda e: str(e.get("label") or e["machine_id"]).casefold())
        return out

    def remove_local_aliases_for_machine(self, machine_id: str) -> int:
        """Remove every shop-local alias pointing at ``machine_id``. Returns count."""
        mid = str(machine_id or "").strip()
        if not mid:
            return 0
        to_drop = [
            raw
            for raw, entry in list(self._local_raw.items())
            if str(entry.get("machine_id") or "").strip() == mid
        ]
        for raw in to_drop:
            self.remove_local_alias(raw)
        return len(to_drop)

    def set_local_aliases_for_machine(
        self,
        machine_id: str,
        aliases: list[str],
        *,
        label: Optional[str] = None,
        control_family: Optional[str] = None,
        layout: Optional[str] = None,
    ) -> None:
        """Replace shop-local folder aliases for one machine with ``aliases``."""
        mid = str(machine_id or "").strip()
        if not mid or mid == "unknown" or mid.startswith("unmapped:"):
            return
        # Keep prior meta if caller omitted fields
        prior = self.info_for_machine_id(mid, mid)
        lab = label if label is not None else (prior.label if prior else None)
        cf = (
            control_family
            if control_family is not None
            else (prior.control_family if prior else None)
        )
        lay = layout if layout is not None else (prior.layout if prior else None)
        self.remove_local_aliases_for_machine(mid)
        seen: set[str] = set()
        for raw in aliases:
            name = sanitize_local_alias_spelling(raw)
            if not name:
                continue
            nk = normalize_folder_name(name)
            if not nk or nk in seen:
                continue
            seen.add(nk)
            self.add_local_alias(
                name,
                mid,
                label=lab,
                control_family=cf,
                layout=lay,
            )

    def save_local(self, path: Path | str) -> Path:
        """Write only shop-local aliases (does not touch bundled aliases.yaml)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        machines: dict[str, Any] = {}
        for raw, entry in sorted(self._local_raw.items(), key=lambda kv: kv[0].casefold()):
            machines[raw] = dict(entry)
        payload = {
            "machines": machines,
            "_comment": "Shop-local aliases for this index target. Overlay on bundled aliases.yaml.",
        }
        with p.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                payload,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        return p

    @property
    def local_alias_count(self) -> int:
        return len(self._local_raw)
