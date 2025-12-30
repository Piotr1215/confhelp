# confhelp

[![PyPI](https://img.shields.io/pypi/v/confhelp)](https://pypi.org/project/confhelp/)
[![Python](https://img.shields.io/pypi/pyversions/confhelp.svg)](https://pypi.org/project/confhelp/)
[![CI](https://github.com/Piotr1215/confhelp/actions/workflows/publish.yml/badge.svg)](https://github.com/Piotr1215/confhelp/actions/workflows/publish.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Config-driven parser for extracting keybindings from dotfiles.

![demo](media/demo.png)

**What**: Extracts keybindings from config files (tmux, zsh, vim, etc.) using regex patterns defined in TOML.

**How**: Point `confhelp` at your dotfiles with a config defining patterns per file type. It outputs `[type]|key|desc|file:line` - pipe to fzf, rofi, or scripts.

**Why**: Static cheatsheets drift out of sync. `tldr`/`cheat.sh` show generic examples, not your bindings. Grepping configs works but no structure. `confhelp` gives you searchable, structured output from your actual configs with jump-to-definition.

## Install

```bash
pip install confhelp
```

## Usage

```bash
# Output all bindings (uses ~/.config/confhelp/config.toml)
confhelp -b ~/dotfiles

# Interactive fzf selection
confhelp -b ~/dotfiles --select

# Select and open in $EDITOR at line
confhelp -b ~/dotfiles --edit

# JSON output
confhelp -b ~/dotfiles -f json

# Custom config
confhelp -c /path/to/config.toml -b ~/dotfiles
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
mode = "abbrev_block"
type = "abbrev"
```

### Config Options

| Option | Description |
|--------|-------------|
| `paths` | List of files to parse (relative to base-dir) |
| `regex` | Pattern with capture groups for key/desc |
| `key_group` | Capture group number for the key |
| `desc_group` | Capture group number for description |
| `match_line` | Only process lines matching this pattern |
| `skip_comment` | Skip lines starting with `#` |
| `truncate` | Max length for description |
| `strip_quotes` | Remove surrounding quotes from desc |
| `desc_literal` | Use fixed string as description |
| `desc_from_comment` | Extract desc from trailing `# comment` |
| `mode` | Special modes: `abbrev_block` for zsh abbreviations |

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
