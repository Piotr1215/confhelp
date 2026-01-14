"""Config-driven parser for extracting bindings from config files."""

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass

import yaml

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib
from pathlib import Path
from typing import Any, Optional


@dataclass
class Binding:
    """A parsed binding entry."""
    type: str
    key: str
    desc: str
    file: str
    line: int

    def to_line(self) -> str:
        return f"[{self.type}]|{self.key}|{self.desc.replace('|', '¦')}|{self.file}:{self.line}"


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


def _navigate_path(data: Any, path: str) -> Any:
    """Navigate to a nested value using dot notation.

    Args:
        data: The parsed data structure (dict/list)
        path: Dot-separated path like "bindings.keys" or "keyboard.shortcuts"

    Returns:
        The value at the specified path, or None if not found.
    """
    if not path:
        return data

    parts = path.split(".")
    current = data

    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
        elif isinstance(current, list):
            try:
                idx = int(part)
                current = current[idx]
            except (ValueError, IndexError):
                return None
        else:
            return None

    return current


def _find_line_for_value(content: str, key_value: str, start_line: int = 1) -> int:
    """Find the line number where a key value appears in content.

    For structured files, we search for the key value to approximate line numbers.
    This handles the fact that parsed data loses line information.

    Args:
        content: Raw file content
        key_value: The key/binding value to search for
        start_line: Minimum line number to start searching from

    Returns:
        The 1-based line number where the value was found, or start_line if not found.
    """
    lines = content.splitlines()
    # Escape special regex chars in key_value for literal matching
    escaped = re.escape(str(key_value))

    for i, line in enumerate(lines, 1):
        if i < start_line:
            continue
        # Look for the key value in the line (as string literal in quotes or bare)
        if re.search(rf'["\']?{escaped}["\']?', line):
            return i

    return start_line


def _parse_file_structured(
    path: Path,
    cfg: dict,
    rel_path: Optional[str] = None,
) -> list[Binding]:
    """Parse structured config files (TOML, YAML, JSON).

    Config options:
        parser: "toml", "yaml", or "json" - the format to parse
        binding_path: dot notation path to the bindings array (e.g., "bindings.keys")
        fields: list of fields to extract from each binding (optional, for validation)
        key: which field is the primary key/binding
        desc: which field is the description
        type: the binding type for output
        truncate: max description length (optional)

    Example config:
        [rio]
        parser = "toml"
        paths = [".config/rio/config.toml"]
        binding_path = "bindings.keys"
        fields = ["key", "mods", "action"]
        key = "key"
        desc = "action"
        type = "rio"
    """
    content = path.read_text()
    fname = rel_path if rel_path else path.name

    # Parse the file based on format
    parser_type = cfg.get("parser", "").lower()
    try:
        if parser_type == "toml":
            data = tomllib.loads(content)
        elif parser_type == "yaml":
            data = yaml.safe_load(content)
        elif parser_type == "json":
            data = json.loads(content)
        else:
            return []
    except Exception:
        return []

    # Navigate to bindings location
    binding_path = cfg.get("binding_path", "")
    bindings_data = _navigate_path(data, binding_path)

    if not isinstance(bindings_data, list):
        return []

    # Extract field names for key and description
    key_field = cfg.get("key", "key")
    desc_field = cfg.get("desc", "desc")
    binding_type = cfg.get("type", parser_type)
    truncate = cfg.get("truncate", 0)

    # Optional: combine multiple fields for key or desc
    # If key/desc contains "+" it means combine fields: "mods+key"
    def extract_field(entry: dict, field_spec: str) -> str:
        if "+" in field_spec:
            parts = field_spec.split("+")
            values = []
            for p in parts:
                val = entry.get(p.strip(), "")
                if val:
                    values.append(str(val))
            return "+".join(values) if values else ""
        return str(entry.get(field_spec, ""))

    results = []
    last_line = 1

    for entry in bindings_data:
        if not isinstance(entry, dict):
            continue

        key = extract_field(entry, key_field)
        desc = extract_field(entry, desc_field)

        if not key:
            continue

        if truncate and len(desc) > truncate:
            desc = desc[:truncate]

        # Find approximate line number by searching for the key value
        line_num = _find_line_for_value(content, key, last_line)
        last_line = line_num + 1  # Next search starts after this line

        results.append(Binding(binding_type, key, desc, fname, line_num))

    return results


def query_tmuxinator_sessions(cfg: dict, base_dir: Optional[Path] = None) -> list[Binding]:
    """Query tmuxinator session files."""
    tmuxinator_dir = Path.home() / ".config/tmuxinator"
    if not tmuxinator_dir.exists():
        return []

    bindings = []
    for yml_file in sorted(tmuxinator_dir.glob("*.yml")):
        try:
            content = yml_file.read_text()
            data = yaml.safe_load(content)
            if not isinstance(data, dict):
                continue

            # Get session name (from 'name' field or filename)
            name = data.get("name", yml_file.stem)
            # Handle ERB templates like "<%= @args[0] %>"
            if "<%=" in str(name):
                name = yml_file.stem

            # Get root directory as description
            root = data.get("root", "~")

            # Find line number of 'name:' field
            line_num = 1
            for i, line in enumerate(content.splitlines(), 1):
                if line.strip().startswith("name:"):
                    line_num = i
                    break

            bindings.append(Binding(
                "mux",
                name,
                root,
                yml_file.name,
                line_num
            ))
        except (OSError, yaml.YAMLError):
            continue

    return bindings


def query_nvim_keymaps(cfg: dict, base_dir: Optional[Path] = None) -> list[Binding]:
    """Query nvim for keymaps via headless execution."""
    if not shutil.which("nvim"):
        return []

    import tempfile
    lua_script = r'''
local leader = vim.g.mapleader or "\\"
for _, mode in ipairs({"n", "v", "i", "x"}) do
  for _, m in ipairs(vim.api.nvim_get_keymap(mode)) do
    if m.desc then
      local lhs = m.lhs
      if lhs:sub(1, #leader) == leader then
        lhs = "<leader>" .. lhs:sub(#leader + 1)
      end
      print(string.format("%s|%s", lhs, m.desc))
    end
  end
end
'''
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".lua", delete=False) as f:
            f.write(lua_script)
            lua_file = f.name
        result = subprocess.run(
            ["nvim", "--headless", "-c", f"luafile {lua_file}", "-c", "q"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        Path(lua_file).unlink(missing_ok=True)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    # Build desc->location index by grepping nvim config files
    desc_locations: dict[str, tuple[str, int]] = {}
    if base_dir:
        nvim_dir = base_dir / ".config/nvim"
        if nvim_dir.exists():
            for lua_path in nvim_dir.rglob("*.lua"):
                try:
                    for i, line in enumerate(lua_path.read_text().splitlines(), 1):
                        # Look for desc = "..." or desc = '...' patterns
                        # Match quote type separately to handle apostrophes in strings
                        match = re.search(r'desc\s*=\s*"([^"]+)"', line)
                        if not match:
                            match = re.search(r"desc\s*=\s*'([^']+)'", line)
                        if match:
                            desc_locations[match.group(1)] = (
                                str(lua_path.relative_to(base_dir)),
                                i,
                            )
                except (OSError, UnicodeDecodeError):
                    continue

    bindings = []
    truncate = cfg.get("truncate", 60)
    output = result.stderr or result.stdout
    for line in output.strip().split("\n"):
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) >= 2:
            key, desc = parts[0], parts[1]
            # Find source location from desc - skip plugin bindings without source
            if desc not in desc_locations:
                continue
            src, line_num = desc_locations[desc]
            if truncate and len(desc) > truncate:
                desc = desc[:truncate]
            bindings.append(Binding("nvim", key, desc, src, line_num))
    return bindings


def _get_line_number(content: str, pos: int) -> int:
    """Get 1-based line number for position in content."""
    return content[:pos].count("\n") + 1


def _parse_file_multiline(
    path: Path,
    cfg: dict,
    rel_path: Optional[str] = None,
) -> list[Binding]:
    """Parse file using multi-line regex matching."""
    content = path.read_text()
    fname = rel_path if rel_path else path.name

    # Compile with DOTALL so . matches newlines
    regex = re.compile(cfg["regex"], re.DOTALL)
    truncate = cfg.get("truncate", 0)
    strip_quotes = cfg.get("strip_quotes", False)

    results = []
    for m in regex.finditer(content):
        key = m.group(cfg.get("key_group", 1))

        if cfg.get("desc_group"):
            desc = m.group(cfg["desc_group"]).strip()
        else:
            desc = ""

        if strip_quotes:
            desc = desc.strip("'\"")
        if truncate and len(desc) > truncate:
            desc = desc[:truncate]

        # Use source_group to override file if present
        file_out = fname
        if cfg.get("source_group"):
            src = m.group(cfg["source_group"]).strip()
            if src:
                file_out = src

        line_num = _get_line_number(content, m.start())
        results.append(Binding(cfg["type"], key, desc, file_out, line_num))

    return results


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

    fname = rel_path if rel_path else path.name

    # Structured parser mode: parse TOML/YAML/JSON files
    parser_type = cfg.get("parser", "").lower()
    if parser_type in ("toml", "yaml", "json"):
        return _parse_file_structured(path, cfg, rel_path), []

    # Multi-line mode: match across lines
    if cfg.get("multiline", False):
        return _parse_file_multiline(path, cfg, rel_path), []

    results = []
    missed = []
    content = path.read_text()
    lines = content.splitlines()

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

    # Handle query engines (top-level setting)
    query_engines = config.get("query_engines", [])
    engine_configs = config.get("engine", {})
    for engine in query_engines:
        if engine == "nvim":
            nvim_cfg = engine_configs.get("nvim", {})
            all_results.extend(query_nvim_keymaps(nvim_cfg, base_dir))
        elif engine == "tmuxinator":
            tmux_cfg = engine_configs.get("tmuxinator", {})
            all_results.extend(query_tmuxinator_sessions(tmux_cfg, base_dir))

    for name, cfg in config.items():
        # Skip non-parser entries
        if not isinstance(cfg, dict):
            continue
        # Skip engine config namespace
        if name == "engine":
            continue
        for rel_path in cfg.get("paths", []):
            # Expand ~ to home directory
            if rel_path.startswith("~"):
                expanded = Path(rel_path).expanduser()
                if "*" in rel_path:
                    for path in expanded.parent.glob(expanded.name):
                        if path.is_file():
                            results, missed = parse_file(
                                path, cfg, str(path), collect_missed, name
                            )
                            all_results.extend(results)
                            all_missed.extend(missed)
                elif expanded.exists():
                    results, missed = parse_file(
                        expanded, cfg, str(expanded), collect_missed, name
                    )
                    all_results.extend(results)
                    all_missed.extend(missed)
            # Support glob patterns
            elif "*" in rel_path:
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
