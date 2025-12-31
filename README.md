# confhelp

[![PyPI](https://img.shields.io/pypi/v/confhelp)](https://pypi.org/project/confhelp/)
[![Python](https://img.shields.io/pypi/pyversions/confhelp.svg)](https://pypi.org/project/confhelp/)
[![CI](https://github.com/Piotr1215/confhelp/actions/workflows/publish.yml/badge.svg)](https://github.com/Piotr1215/confhelp/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Find and edit your keybindings instantly.

![demo](media/demo.png)

## The Problem

Over time you accumulate tmux bindings, zsh aliases, vim mappings, custom functions - scattered across dozens of files. You *know* you set something up, but where?

**Two pain points:**

1. **Finding bindings** - "What key did I bind for git status?" "Do I have an alias for docker compose?"
2. **Editing bindings** - You remember it exists, now you need to change it. Which file? What line? grep → open → scroll → find → edit. Every. Single. Time.

## The Solution

```bash
confhelp -b ~/dotfiles --edit
```

Fuzzy search all your bindings → select one → opens `$EDITOR` at exact file:line.

## Install

```bash
pip install confhelp
```

## Usage

```bash
# Output all bindings (uses base_dirs from config)
confhelp

# Interactive fzf selection
confhelp --select

# Select and open in $EDITOR at line
confhelp --edit

# JSON output
confhelp -f json

# Override base directory
confhelp -b ~/other-dotfiles

# Show keys defined more than once
confhelp --conflicts

# Report lines that look like bindings but failed to parse
confhelp --check
```

Example output:

```
[tmux]   prefix+g   display-popup -w 80%...   .tmux.conf:42
[alias]  gs         git status                .zsh_aliases:15
[bind]   ^[e        edit-command-line         .zshrc:89
```

The `--edit` flag drops you directly into the file at the exact line. Change the binding, save, done.

## Config Format

Define parsers in TOML. Each section describes how to extract bindings from a set of files:

```toml
# Default directories to search (no -b needed)
base_dirs = ["~/dotfiles", "~/work-dotfiles"]

[tmux]
paths = [".tmux.conf"]
match_line = "^bind"
regex = 'bind(?:-key)?\s+(?:-n\s+)?(\S+)(.*)'
key_group = 1
desc_group = 2
type = "tmux"
truncate = 100

[alias]
paths = [".zsh_aliases", ".zsh_claude"]
regex = "alias\\s+(?:-[gs]\\s+)?([^=]+)=(.*)"
key_group = 1
desc_group = 2
type = "alias"
strip_quotes = true

[abbrev]
paths = [".zsh_abbreviations"]
match_line = '".*"'
regex = '''"([^"]+)"\s+'([^']+)''''
key_group = 1
desc_group = 2
type = "abbrev"

[nvim]
paths = [".config/nvim/lua/**/*.lua"]  # glob pattern
match_line = "vim.keymap.set"
regex = 'vim\.keymap\.set\([^,]+,\s*"([^"]+)".*desc\s*=\s*"([^"]+)"'
key_group = 1
desc_group = 2
type = "nvim"
```

### Config Options

| Option | Description |
|--------|-------------|
| `paths` | List of files or glob patterns (e.g., `**/*.lua`) |
| `regex` | Pattern with capture groups for key/desc |
| `key_group` | Capture group number for the key |
| `desc_group` | Capture group number for description |
| `match_line` | Only process lines matching this pattern |
| `skip_comment` | Skip lines starting with `#` |
| `truncate` | Max length for description |
| `strip_quotes` | Remove surrounding quotes from desc |
| `desc_literal` | Use fixed string as description |
| `desc_from_comment` | Extract desc from trailing `# comment` |

## Output Formats

- `pipe` (default): pipe-delimited `[type]|key|desc|file:line`
- `tsv`: Tab-separated
- `json`: JSON array

The pipe format works well with `column -t -s'|'` for aligned display.

## Integration Examples

`confhelp` outputs text. How you display it is up to you.

### Alacritty Popup

Spawn a centered popup window showing bindings. Enter jumps to the file:

```bash
selection=$(confhelp -b ~/dotfiles | column -t -s'|' | fzf)
# parse selection, open in editor
```

See `examples/alacritty-popup.sh` for a complete implementation.

### tmux Popup

```bash
tmux display-popup -w 80% -h 80% -E 'confhelp -b ~/dotfiles --select'
```

See `examples/tmux-popup.sh` for a complete implementation.

### Rofi/dmenu

```bash
confhelp -b ~/dotfiles | rofi -dmenu
```

## Acknowledgments

Inspired by [Extracto](https://github.com/sarthakbhatkar1/Extracto).

## License

MIT
