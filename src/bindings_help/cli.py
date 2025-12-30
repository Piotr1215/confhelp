"""CLI - parse and optionally select bindings with fzf."""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

# Handle broken pipe (e.g., confhelp | head) gracefully
signal.signal(signal.SIGPIPE, signal.SIG_DFL)

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


SAMPLE_CONFIG = '''\
# confhelp config - define regex patterns for each config file type

[tmux]
paths = [".tmux.conf"]
match_line = "^bind"
regex = 'bind(?:-key)?\\s+(?:-n\\s+)?(\\S+)(.*)'
key_group = 1
desc_group = 2
type = "tmux"
truncate = 80

[alias]
paths = [".zsh_aliases", ".bash_aliases"]
regex = 'alias\\s+([^=]+)=(.*)'
key_group = 1
desc_group = 2
type = "alias"
strip_quotes = true

[bindkey]
paths = [".zshrc"]
match_line = "bindkey"
regex = "bindkey\\s+['\"]([^'\"]+)['\"]\\s+(\\S+)"
key_group = 1
desc_group = 2
type = "bind"
desc_from_comment = true
'''


def init_config() -> None:
    config_dir = Path.home() / ".config/confhelp"
    config_file = config_dir / "config.toml"

    if config_file.exists():
        print(f"Config already exists: {config_file}")
        return

    config_dir.mkdir(parents=True, exist_ok=True)
    config_file.write_text(SAMPLE_CONFIG)
    print(f"Created: {config_file}")


def main():
    default_config = find_config()
    parser = argparse.ArgumentParser(
        description="Parse keybindings from config files",
        epilog="Example: confhelp -b ~/dotfiles"
    )
    parser.add_argument("--init", action="store_true",
                       help="Create sample config at ~/.config/confhelp/config.toml")
    parser.add_argument("--config", "-c", type=Path, default=default_config,
                       help="Parser config TOML file (default: ~/.config/confhelp/config.toml)")
    parser.add_argument("--base-dir", "-b", type=Path,
                       help="Base directory for config files")
    parser.add_argument("--format", "-f", choices=["pipe", "tsv", "json"], default="pipe",
                       help="Output format (default: pipe-separated)")
    parser.add_argument("--select", "-s", action="store_true",
                       help="Interactive selection with fzf")
    parser.add_argument("--edit", "-e", action="store_true",
                       help="Open selected binding in $EDITOR (implies --select)")
    args = parser.parse_args()

    if args.init:
        init_config()
        return

    if not args.base_dir:
        parser.error("--base-dir/-b is required")

    if not args.config:
        paths = get_default_config_paths()
        print("Error: No config file found. Looked in:", file=sys.stderr)
        for p in paths:
            print(f"  - {p}", file=sys.stderr)
        print("Run 'confhelp --init' to create a sample config.", file=sys.stderr)
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
