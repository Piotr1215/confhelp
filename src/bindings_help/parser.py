"""Config-driven parser for extracting bindings from config files."""

import re
import sys
from dataclasses import dataclass

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pathlib import Path
from typing import Optional


@dataclass
class Binding:
    """A parsed binding entry."""
    type: str
    key: str
    desc: str
    file: str
    line: int

    def to_line(self) -> str:
        return f"[{self.type}]|{self.key}|{self.desc}|{self.file}:{self.line}"


@dataclass
class MissedLine:
    """A line that matched match_line but failed regex."""
    file: str
    line: int
    content: str
    parser_name: str


def load_config(config_path: Path) -> dict:
    """Load parser configuration from TOML file."""
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def parse_file(
    path: Path,
    cfg: dict,
    rel_path: Optional[str] = None,
    collect_missed: bool = False,
    parser_name: str = "",
) -> tuple[list[Binding], list[MissedLine]]:
    """Parse a single file according to config.

    Returns (bindings, missed_lines). missed_lines is empty unless collect_missed=True.
    """
    if not path.exists():
        return [], []

    results = []
    missed = []
    content = path.read_text()
    lines = content.splitlines()
    fname = rel_path if rel_path else path.name

    regex = re.compile(cfg["regex"])
    match_line = cfg.get("match_line")
    skip_comment = cfg.get("skip_comment", False)
    truncate = cfg.get("truncate", 0)
    strip_quotes = cfg.get("strip_quotes", False)
    desc_from_comment = cfg.get("desc_from_comment", False)
    desc_literal = cfg.get("desc_literal")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        if skip_comment and stripped.startswith("#"):
            continue

        if match_line and not re.search(match_line, stripped):
            continue

        m = regex.search(stripped)
        if not m:
            if collect_missed:
                missed.append(MissedLine(fname, i, stripped, parser_name))
            continue

        key = m.group(cfg.get("key_group", 1))

        # Determine description
        if desc_literal:
            desc = desc_literal
        elif desc_from_comment:
            if "#" in line:
                desc = line.split("#", 1)[1].strip()
            else:
                func_match = re.search(r"['\"][^'\"]+['\"]\s+(\S+)", stripped)
                desc = func_match.group(1) if func_match else stripped[:40]
        elif cfg.get("desc_group"):
            desc = m.group(cfg["desc_group"]).strip()
        else:
            desc = ""

        if strip_quotes:
            desc = desc.strip("'\"")
        if truncate and len(desc) > truncate:
            desc = desc[:truncate]

        results.append(Binding(cfg["type"], key, desc, fname, i))

    return results, missed


def parse_all(
    config_path: Path, base_dir: Path, collect_missed: bool = False
) -> tuple[list[Binding], list[MissedLine]]:
    """Parse all configs and return bindings.

    Returns (bindings, missed_lines). missed_lines is empty unless collect_missed=True.
    """
    config = load_config(config_path)
    all_results = []
    all_missed = []

    for name, cfg in config.items():
        # Skip non-parser entries (e.g., base_dirs)
        if not isinstance(cfg, dict):
            continue
        for rel_path in cfg.get("paths", []):
            # Support glob patterns
            if "*" in rel_path:
                for path in base_dir.glob(rel_path):
                    if path.is_file():
                        file_rel = str(path.relative_to(base_dir))
                        results, missed = parse_file(
                            path, cfg, file_rel, collect_missed, name
                        )
                        all_results.extend(results)
                        all_missed.extend(missed)
            else:
                path = base_dir / rel_path
                results, missed = parse_file(path, cfg, rel_path, collect_missed, name)
                all_results.extend(results)
                all_missed.extend(missed)

    return all_results, all_missed


def find_conflicts(bindings: list[Binding]) -> dict[tuple[str, str], list[Binding]]:
    """Find keys that are defined more than once.

    Returns dict mapping (type, key) to list of bindings with that key.
    Only includes entries with 2+ bindings.
    """
    from collections import defaultdict

    by_key: dict[tuple[str, str], list[Binding]] = defaultdict(list)
    for b in bindings:
        by_key[(b.type, b.key)].append(b)

    return {k: v for k, v in by_key.items() if len(v) > 1}
