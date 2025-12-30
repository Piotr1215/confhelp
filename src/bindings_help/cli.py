"""CLI - parse and optionally select bindings with fzf."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from iterfzf import iterfzf

from .parser import parse_all

def get_default_config_paths() -> list[Path]:
    paths = []
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        paths.append(Path(xdg_config) / "confhelp/config.toml")
    paths.append(Path.home() / ".config/confhelp/config.toml")
    paths.append(Path.home() / ".confhelp.toml")
    return paths


def find_config() -> Path | None:
    for p in get_default_config_paths():
        if p.exists():
            return p
    return None


def main():
    default_config = find_config()
    parser = argparse.ArgumentParser(
        description="Parse keybindings from config files",
        epilog="Example: confhelp -b ~/dotfiles"
    )
    parser.add_argument("--config", "-c", type=Path, default=default_config,
                       help="Parser config TOML file (default: ~/.config/confhelp/config.toml)")
    parser.add_argument("--base-dir", "-b", type=Path, required=True,
                       help="Base directory for config files")
    parser.add_argument("--format", "-f", choices=["pipe", "tsv", "json"], default="pipe",
                       help="Output format (default: pipe-separated)")
    parser.add_argument("--select", "-s", action="store_true",
                       help="Interactive selection with fzf")
    parser.add_argument("--edit", "-e", action="store_true",
                       help="Open selected binding in $EDITOR (implies --select)")
    args = parser.parse_args()

    if not args.config:
        paths = get_default_config_paths()
        print(f"Error: No config file found. Looked in:", file=sys.stderr)
        for p in paths:
            print(f"  - {p}", file=sys.stderr)
        print("Use -c to specify a config file.", file=sys.stderr)
        sys.exit(1)

    bindings = parse_all(args.config, args.base_dir)

    # Interactive mode
    if args.select or args.edit:
        lines = [b.to_line() for b in bindings]
        # Format with column for alignment
        proc = subprocess.run(["column", "-t", "-s|"], input="\n".join(lines),
                             capture_output=True, text=True)
        formatted = proc.stdout.strip().split("\n")

        selection = iterfzf(formatted, exact=True)
        if not selection:
            sys.exit(1)

        # Extract file:line from last column
        file_line = selection.split()[-1]
        fname, line = file_line.rsplit(":", 1)
        path = args.base_dir / fname

        if args.edit:
            editor = os.environ.get("EDITOR", "vim")
            subprocess.run([editor, f"+{line}", str(path)])
        else:
            print(f"{path}:{line}")
        return

    # Output mode
    if args.format == "json":
        import json
        data = [{"type": b.type, "key": b.key, "desc": b.desc,
                 "file": b.file, "line": b.line} for b in bindings]
        print(json.dumps(data, indent=2))
    elif args.format == "tsv":
        for b in bindings:
            print(f"{b.type}\t{b.key}\t{b.desc}\t{b.file}:{b.line}")
    else:
        for b in bindings:
            print(b.to_line())


if __name__ == "__main__":
    main()
