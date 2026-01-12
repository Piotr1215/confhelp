"""Tests for the config-driven parser."""

import tempfile
from pathlib import Path

import pytest

from bindings_help.parser import parse_file, parse_all, load_config, Binding, find_conflicts, MissedLine


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


class TestParseFile:
    def test_parse_tmux_bindings(self, temp_dir):
        config = {
            "type": "tmux",
            "match_line": "^bind",
            "regex": r"bind(?:-key)?\s+(?:-n\s+)?(\S+)(.*)",
            "key_group": 1,
            "desc_group": 2,
            "truncate": 50,
        }
        tmux_conf = temp_dir / ".tmux.conf"
        tmux_conf.write_text("""
bind r source-file ~/.tmux.conf
bind-key -n C-h select-pane -L
bind v split-window -h
# comment line
set -g status on
""")
        results, _ = parse_file(tmux_conf, config)

        assert len(results) == 3
        assert results[0].key == "r"
        assert "source-file" in results[0].desc
        assert results[1].key == "C-h"
        assert results[2].key == "v"

    def test_parse_aliases(self, temp_dir):
        config = {
            "type": "alias",
            "regex": r"alias\s+(?:-[gs]\s+)?([^=]+)=(.*)",
            "key_group": 1,
            "desc_group": 2,
            "strip_quotes": True,
            "truncate": 50,
        }
        aliases = temp_dir / ".zsh_aliases"
        aliases.write_text("""
alias ls='exa --color=always'
alias -g G='| grep -i'
alias vim=nvim
# comment
""")
        results, _ = parse_file(aliases, config)

        assert len(results) == 3
        assert results[0].key == "ls"
        assert "exa" in results[0].desc
        assert results[1].key == "G"

    def test_parse_with_skip_comment(self, temp_dir):
        config = {
            "type": "func",
            "regex": r"(\w+)\s*\(\)",
            "key_group": 1,
            "skip_comment": True,
            "desc_literal": "(function)",
        }
        funcs = temp_dir / ".zsh_functions"
        funcs.write_text("""
# helper() - not a real function
myfunc() {
    echo "hello"
}
""")
        results, _ = parse_file(funcs, config)

        assert len(results) == 1
        assert results[0].key == "myfunc"
        assert results[0].desc == "(function)"

    def test_parse_abbrev_regex(self, temp_dir):
        config = {
            "type": "abbr",
            "match_line": '".*"',
            "regex": r'"([^"]+)"\s+\'([^\']+)\'',
            "key_group": 1,
            "desc_group": 2,
        }
        abbrevs = temp_dir / ".zsh_abbreviations"
        abbrevs.write_text("""
typeset -Ag abbrevs
abbrevs=(
    "gst"  'git status'
    "gco"  'git checkout'
)
""")
        results, _ = parse_file(abbrevs, config)

        assert len(results) == 2
        assert results[0].key == "gst"
        assert results[0].desc == "git status"

    def test_parse_nonexistent_file(self, temp_dir):
        config = {"type": "test", "regex": ".*"}
        results, missed = parse_file(temp_dir / "nonexistent", config)
        assert results == []
        assert missed == []

    def test_truncate(self, temp_dir):
        config = {
            "type": "alias",
            "regex": r"alias\s+([^=]+)=(.*)",
            "key_group": 1,
            "desc_group": 2,
            "truncate": 10,
        }
        aliases = temp_dir / ".aliases"
        aliases.write_text("alias foo='this is a very long description that should be truncated'")

        results, _ = parse_file(aliases, config)
        assert len(results[0].desc) == 10


class TestParseAll:
    def test_parse_multiple_files(self, temp_dir):
        config_toml = temp_dir / "config.toml"
        config_toml.write_text("""
[tmux]
paths = [".tmux.conf"]
match_line = "^bind"
regex = 'bind\\s+(\\S+)'
key_group = 1
type = "tmux"

[alias]
paths = [".aliases"]
regex = 'alias\\s+([^=]+)='
key_group = 1
type = "alias"
""")
        (temp_dir / ".tmux.conf").write_text("bind r reload")
        (temp_dir / ".aliases").write_text("alias ls='exa'")

        results, _ = parse_all(config_toml, temp_dir)

        assert len(results) == 2
        types = {r.type for r in results}
        assert types == {"tmux", "alias"}


class TestBinding:
    def test_to_line(self):
        b = Binding("tmux", "r", "reload config", ".tmux.conf", 42)
        assert b.to_line() == "[tmux]|r|reload config|.tmux.conf:42"

    def test_to_line_empty_desc(self):
        b = Binding("func", "myfunc", "", ".funcs", 1)
        assert b.to_line() == "[func]|myfunc||.funcs:1"


class TestEdgeCases:
    def test_match_line_filter(self, temp_dir):
        """Only lines matching match_line are processed."""
        config = {
            "type": "tmux",
            "match_line": "^bind",
            "regex": r"(\S+)",
            "key_group": 1,
        }
        f = temp_dir / "conf"
        f.write_text("set -g status on\nbind r reload\nunbind x")

        results, _ = parse_file(f, config)
        assert len(results) == 1
        assert results[0].key == "bind"

    def test_empty_file(self, temp_dir):
        config = {"type": "test", "regex": r"(\w+)"}
        f = temp_dir / "empty"
        f.write_text("")

        results, _ = parse_file(f, config)
        assert results == []

    def test_no_matches(self, temp_dir):
        config = {"type": "test", "regex": r"NOMATCH(\d+)"}
        f = temp_dir / "conf"
        f.write_text("line one\nline two\nline three")

        results, _ = parse_file(f, config)
        assert results == []

    def test_desc_from_comment(self, temp_dir):
        config = {
            "type": "bind",
            "regex": r"bindkey\s+'([^']+)'",
            "key_group": 1,
            "desc_from_comment": True,
        }
        f = temp_dir / ".zshrc"
        f.write_text("bindkey '^R' fzf-history  # search history\nbindkey '^T' fzf-file")

        results, _ = parse_file(f, config)
        assert len(results) == 2
        assert results[0].desc == "search history"
        assert "fzf-file" in results[1].desc or results[1].desc == ""

    def test_multiple_paths_in_config(self, temp_dir):
        config_toml = temp_dir / "config.toml"
        config_toml.write_text("""
[alias]
paths = [".aliases1", ".aliases2"]
regex = 'alias\\s+(\\w+)='
key_group = 1
type = "alias"
""")
        (temp_dir / ".aliases1").write_text("alias foo=bar")
        (temp_dir / ".aliases2").write_text("alias baz=qux")

        results, _ = parse_all(config_toml, temp_dir)
        keys = {r.key for r in results}
        assert keys == {"foo", "baz"}

    def test_line_numbers_correct(self, temp_dir):
        config = {"type": "test", "regex": r"test(\d+)"}
        f = temp_dir / "conf"
        f.write_text("# comment\ntest1\n# another\ntest2\ntest3")

        results, _ = parse_file(f, config)
        assert results[0].line == 2
        assert results[1].line == 4
        assert results[2].line == 5

    def test_strip_quotes_various(self, temp_dir):
        config = {
            "type": "alias",
            "regex": r"alias\s+\w+=(.*)",
            "desc_group": 1,
            "strip_quotes": True,
        }
        f = temp_dir / ".aliases"
        f.write_text("alias a='single'\nalias b=\"double\"\nalias c=none")

        results, _ = parse_file(f, config)
        assert results[0].desc == "single"
        assert results[1].desc == "double"
        assert results[2].desc == "none"


class TestMissedLines:
    def test_collect_missed_lines(self, temp_dir):
        """Lines matching match_line but failing regex are collected."""
        config = {
            "type": "tmux",
            "match_line": "^bind",
            "regex": r"bind\s+(\w)\s+",  # Only matches single-char keys
        }
        f = temp_dir / ".tmux.conf"
        f.write_text("bind r reload\nbind C-h select-pane\nbind v split")

        results, missed = parse_file(f, config, collect_missed=True, parser_name="tmux")

        assert len(results) == 2  # r and v match
        assert len(missed) == 1  # C-h doesn't match (not single char)
        assert missed[0].parser_name == "tmux"
        assert "C-h" in missed[0].content

    def test_no_missed_without_flag(self, temp_dir):
        """Missed lines are not collected unless collect_missed=True."""
        config = {
            "type": "tmux",
            "match_line": "^bind",
            "regex": r"bind\s+(\w)\s+",
        }
        f = temp_dir / ".tmux.conf"
        f.write_text("bind C-h select-pane")

        results, missed = parse_file(f, config, collect_missed=False)

        assert results == []
        assert missed == []


class TestDefaultValues:
    """Tests to verify default parameter behavior (mutation testing)."""

    def test_collect_missed_false_by_default(self, temp_dir):
        """MUTATION FIX: collect_missed defaults to False, not True."""
        config = {
            "type": "test",
            "match_line": "^bind",
            "regex": r"bind\s+(\w)\s+",  # Only matches single-char keys
        }
        f = temp_dir / ".conf"
        f.write_text("bind C-h select-pane")  # Won't match (C-h is multi-char)

        # Default collect_missed=False should return empty missed list
        results, missed = parse_file(f, config)
        assert missed == [], "collect_missed should default to False"

    def test_skip_comment_false_by_default(self, temp_dir):
        """MUTATION FIX: skip_comment defaults to False - comments are parsed."""
        config = {
            "type": "test",
            "regex": r"#\s*(\w+)",
            "key_group": 1,
            # skip_comment NOT set - should default to False
        }
        f = temp_dir / "conf"
        f.write_text("# hello")

        results, _ = parse_file(f, config)
        # If skip_comment defaulted to True, this would be empty
        assert len(results) == 1, "skip_comment should default to False"
        assert results[0].key == "hello"

    def test_strip_quotes_false_by_default(self, temp_dir):
        """MUTATION FIX: strip_quotes defaults to False - quotes preserved."""
        config = {
            "type": "alias",
            "regex": r"alias\s+\w+=(.*)",
            "desc_group": 1,
            # strip_quotes NOT set - should default to False
        }
        f = temp_dir / ".aliases"
        f.write_text("alias a='quoted'")

        results, _ = parse_file(f, config)
        # If strip_quotes defaulted to True, quotes would be stripped
        assert results[0].desc == "'quoted'", "strip_quotes should default to False"

    def test_desc_from_comment_function_fallback(self, temp_dir):
        """MUTATION FIX: desc_from_comment extracts function name when no # comment."""
        config = {
            "type": "bind",
            "regex": r"bindkey\s+'([^']+)'",
            "key_group": 1,
            "desc_from_comment": True,
        }
        f = temp_dir / ".zshrc"
        # No # comment - should extract function name via regex fallback
        f.write_text("bindkey '^T' 'fzf-file-widget'")

        results, _ = parse_file(f, config)
        assert len(results) == 1
        # Should extract fzf-file-widget from the pattern
        assert "fzf-file-widget" in results[0].desc

    def test_truncate_exact_boundary(self, temp_dir):
        """MUTATION FIX: truncate with > not >= (len == truncate should not truncate)."""
        config = {
            "type": "alias",
            "regex": r"alias\s+([^=]+)=(.*)",
            "key_group": 1,
            "desc_group": 2,
            "truncate": 5,
        }
        f = temp_dir / ".aliases"
        f.write_text("alias a=exact")  # "exact" is exactly 5 chars

        results, _ = parse_file(f, config)
        # Should NOT truncate when len == truncate
        assert results[0].desc == "exact"
        assert len(results[0].desc) == 5

    def test_empty_desc_when_no_desc_options(self, temp_dir):
        """MUTATION FIX: desc defaults to empty string when no desc options set."""
        config = {
            "type": "test",
            "regex": r"test\s+(\w+)",
            "key_group": 1,
            # No desc_group, desc_literal, or desc_from_comment
        }
        f = temp_dir / "conf"
        f.write_text("test hello")

        results, _ = parse_file(f, config)
        assert len(results) == 1
        assert results[0].desc == ""  # Must be empty string, not None or "XXXX"

    def test_parse_all_collect_missed_false_by_default(self, temp_dir):
        """MUTATION FIX: parse_all collect_missed defaults to False."""
        config_toml = temp_dir / "config.toml"
        config_toml.write_text("""
[tmux]
paths = [".tmux.conf"]
match_line = "^bind"
regex = 'bind\\s+(\\w)\\s+'
key_group = 1
type = "tmux"
""")
        # This line matches match_line but fails regex (C-h is multi-char)
        (temp_dir / ".tmux.conf").write_text("bind C-h select-pane")

        # Default collect_missed=False should return empty missed list
        results, missed = parse_all(config_toml, temp_dir)
        assert missed == [], "parse_all collect_missed should default to False"


class TestFindConflicts:
    def test_find_duplicate_keys(self):
        bindings = [
            Binding("tmux", "r", "reload", ".tmux.conf", 1),
            Binding("tmux", "r", "restart", ".tmux.conf", 5),
            Binding("tmux", "v", "split", ".tmux.conf", 10),
        ]

        conflicts = find_conflicts(bindings)

        assert len(conflicts) == 1
        assert ("tmux", "r") in conflicts
        assert len(conflicts[("tmux", "r")]) == 2

    def test_no_conflicts(self):
        bindings = [
            Binding("tmux", "r", "reload", ".tmux.conf", 1),
            Binding("tmux", "v", "split", ".tmux.conf", 5),
            Binding("alias", "r", "reset", ".aliases", 1),  # Different type
        ]

        conflicts = find_conflicts(bindings)
        assert conflicts == {}

    def test_conflicts_across_files(self):
        bindings = [
            Binding("alias", "gs", "git status", ".zsh_aliases", 1),
            Binding("alias", "gs", "gst alias", ".bash_aliases", 5),
        ]

        conflicts = find_conflicts(bindings)

        assert len(conflicts) == 1
        assert ("alias", "gs") in conflicts


class TestStructuredParser:
    """Tests for structured file parsing (TOML, YAML, JSON)."""

    def test_parse_toml_bindings(self, temp_dir):
        """Parse bindings from a TOML config file."""
        config = {
            "type": "rio",
            "parser": "toml",
            "binding_path": "bindings.keys",
            "key": "key",
            "desc": "action",
        }
        toml_file = temp_dir / "config.toml"
        toml_file.write_text("""
[bindings]
keys = [
    { key = "v", mods = "Control", action = "Paste" },
    { key = "c", mods = "Control", action = "Copy" },
    { key = "n", mods = "Control | Shift", action = "WindowCreateNew" },
]
""")
        results, _ = parse_file(toml_file, config)

        assert len(results) == 3
        assert results[0].key == "v"
        assert results[0].desc == "Paste"
        assert results[0].type == "rio"
        assert results[1].key == "c"
        assert results[1].desc == "Copy"
        assert results[2].key == "n"
        assert results[2].desc == "WindowCreateNew"

    def test_parse_yaml_bindings(self, temp_dir):
        """Parse bindings from a YAML config file."""
        config = {
            "type": "app",
            "parser": "yaml",
            "binding_path": "keybindings",
            "key": "key",
            "desc": "command",
        }
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("""
keybindings:
  - key: Ctrl+S
    command: save
  - key: Ctrl+O
    command: open
  - key: Ctrl+Q
    command: quit
""")
        results, _ = parse_file(yaml_file, config)

        assert len(results) == 3
        assert results[0].key == "Ctrl+S"
        assert results[0].desc == "save"
        assert results[1].key == "Ctrl+O"
        assert results[1].desc == "open"
        assert results[2].key == "Ctrl+Q"
        assert results[2].desc == "quit"

    def test_parse_json_bindings(self, temp_dir):
        """Parse bindings from a JSON config file."""
        config = {
            "type": "vscode",
            "parser": "json",
            "binding_path": "",  # Top-level array
            "key": "key",
            "desc": "command",
        }
        json_file = temp_dir / "keybindings.json"
        json_file.write_text("""
[
    { "key": "ctrl+shift+p", "command": "workbench.action.showCommands" },
    { "key": "ctrl+p", "command": "workbench.action.quickOpen" },
    { "key": "ctrl+`", "command": "workbench.action.terminal.toggleTerminal" }
]
""")
        results, _ = parse_file(json_file, config)

        assert len(results) == 3
        assert results[0].key == "ctrl+shift+p"
        assert results[0].desc == "workbench.action.showCommands"
        assert results[1].key == "ctrl+p"
        assert results[2].key == "ctrl+`"

    def test_parse_nested_binding_path(self, temp_dir):
        """Navigate deeply nested structures with dot notation."""
        config = {
            "type": "app",
            "parser": "yaml",
            "binding_path": "settings.keyboard.shortcuts",
            "key": "binding",
            "desc": "action",
        }
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("""
settings:
  theme: dark
  keyboard:
    shortcuts:
      - binding: Ctrl+A
        action: select_all
      - binding: Ctrl+Z
        action: undo
""")
        results, _ = parse_file(yaml_file, config)

        assert len(results) == 2
        assert results[0].key == "Ctrl+A"
        assert results[0].desc == "select_all"

    def test_combined_fields_with_plus(self, temp_dir):
        """Support combining multiple fields using + syntax."""
        config = {
            "type": "rio",
            "parser": "toml",
            "binding_path": "bindings",
            "key": "mods+key",  # Combine mods and key
            "desc": "action",
        }
        toml_file = temp_dir / "config.toml"
        toml_file.write_text("""
[[bindings]]
key = "v"
mods = "Control"
action = "Paste"

[[bindings]]
key = "c"
mods = "Control"
action = "Copy"
""")
        results, _ = parse_file(toml_file, config)

        assert len(results) == 2
        assert results[0].key == "Control+v"
        assert results[0].desc == "Paste"
        assert results[1].key == "Control+c"

    def test_truncate_structured_desc(self, temp_dir):
        """Truncate long descriptions in structured files."""
        config = {
            "type": "app",
            "parser": "json",
            "binding_path": "bindings",
            "key": "key",
            "desc": "description",
            "truncate": 10,
        }
        json_file = temp_dir / "config.json"
        json_file.write_text("""
{
    "bindings": [
        { "key": "a", "description": "This is a very long description that should be truncated" }
    ]
}
""")
        results, _ = parse_file(json_file, config)

        assert len(results) == 1
        assert len(results[0].desc) == 10

    def test_line_numbers_toml(self, temp_dir):
        """Verify line numbers are approximated correctly for TOML."""
        config = {
            "type": "rio",
            "parser": "toml",
            "binding_path": "bindings.keys",
            "key": "key",
            "desc": "action",
        }
        toml_file = temp_dir / "config.toml"
        toml_file.write_text("""# Rio config
[bindings]
keys = [
    { key = "v", action = "Paste" },
    { key = "c", action = "Copy" },
]
""")
        results, _ = parse_file(toml_file, config)

        assert len(results) == 2
        # Line numbers should point to lines containing the keys
        assert results[0].line >= 4  # "v" appears on line 4
        assert results[1].line >= 5  # "c" appears on line 5

    def test_line_numbers_yaml(self, temp_dir):
        """Verify line numbers are approximated correctly for YAML."""
        config = {
            "type": "app",
            "parser": "yaml",
            "binding_path": "bindings",
            "key": "key",
            "desc": "cmd",
        }
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("""# Comment
bindings:
  - key: Ctrl+A
    cmd: select
  - key: Ctrl+B
    cmd: bold
""")
        results, _ = parse_file(yaml_file, config)

        assert len(results) == 2
        assert results[0].line == 3  # Ctrl+A on line 3
        assert results[1].line == 5  # Ctrl+B on line 5

    def test_empty_binding_path(self, temp_dir):
        """Handle top-level arrays with empty binding_path."""
        config = {
            "type": "vscode",
            "parser": "json",
            "binding_path": "",
            "key": "key",
            "desc": "command",
        }
        json_file = temp_dir / "keybindings.json"
        json_file.write_text('[{"key": "ctrl+a", "command": "selectAll"}]')

        results, _ = parse_file(json_file, config)

        assert len(results) == 1
        assert results[0].key == "ctrl+a"

    def test_missing_binding_path(self, temp_dir):
        """Return empty results if binding_path doesn't exist."""
        config = {
            "type": "app",
            "parser": "yaml",
            "binding_path": "nonexistent.path",
            "key": "key",
            "desc": "cmd",
        }
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("other: value\n")

        results, _ = parse_file(yaml_file, config)

        assert results == []

    def test_invalid_file_content(self, temp_dir):
        """Return empty results for invalid file content."""
        config = {
            "type": "app",
            "parser": "json",
            "binding_path": "bindings",
            "key": "key",
            "desc": "cmd",
        }
        json_file = temp_dir / "config.json"
        json_file.write_text("not valid json {{{")

        results, _ = parse_file(json_file, config)

        assert results == []

    def test_skip_entries_without_key(self, temp_dir):
        """Skip binding entries that don't have the key field."""
        config = {
            "type": "app",
            "parser": "yaml",
            "binding_path": "bindings",
            "key": "shortcut",
            "desc": "action",
        }
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("""
bindings:
  - shortcut: Ctrl+S
    action: save
  - action: orphan  # No shortcut field
  - shortcut: Ctrl+Q
    action: quit
""")
        results, _ = parse_file(yaml_file, config)

        assert len(results) == 2
        assert results[0].key == "Ctrl+S"
        assert results[1].key == "Ctrl+Q"

    def test_parse_all_with_structured_parser(self, temp_dir):
        """Verify structured parsers work through parse_all."""
        config_toml = temp_dir / "confhelp.toml"
        config_toml.write_text("""
[rio]
parser = "toml"
paths = ["rio.toml"]
binding_path = "keys"
key = "key"
desc = "action"
type = "rio"
""")
        rio_config = temp_dir / "rio.toml"
        rio_config.write_text("""
[[keys]]
key = "v"
action = "Paste"

[[keys]]
key = "c"
action = "Copy"
""")
        results, _ = parse_all(config_toml, temp_dir)

        assert len(results) == 2
        assert results[0].type == "rio"
        assert results[0].key == "v"
        assert results[1].key == "c"

    def test_default_type_from_parser(self, temp_dir):
        """Use parser type as default binding type if type not specified."""
        config = {
            "parser": "yaml",
            "binding_path": "bindings",
            "key": "key",
            "desc": "cmd",
            # No "type" specified
        }
        yaml_file = temp_dir / "config.yaml"
        yaml_file.write_text("bindings:\n  - key: a\n    cmd: test\n")

        results, _ = parse_file(yaml_file, config)

        assert len(results) == 1
        assert results[0].type == "yaml"  # Defaults to parser type

    def test_parse_zledit_actions(self, temp_dir):
        """Parse zledit actions config (top-level [[actions]] array)."""
        config = {
            "type": "zledit",
            "parser": "toml",
            "binding_path": "actions",
            "key": "binding",
            "desc": "description",
        }
        toml_file = temp_dir / "config.toml"
        toml_file.write_text("""
[[actions]]
binding = 'ctrl-u'
description = 'upper'
script = '~/.config/zledit/scripts/uppercase.sh'

[[actions]]
binding = 'ctrl-l'
description = 'lower'
script = '~/.config/zledit/scripts/lowercase.sh'
""")
        results, _ = parse_file(toml_file, config)

        assert len(results) == 2
        assert results[0].key == "ctrl-u"
        assert results[0].desc == "upper"
        assert results[0].type == "zledit"
        assert results[1].key == "ctrl-l"
        assert results[1].desc == "lower"

    def test_parse_zledit_previewers(self, temp_dir):
        """Parse zledit previewers config (top-level [[previewers]] array)."""
        config = {
            "type": "zledit-preview",
            "parser": "toml",
            "binding_path": "previewers",
            "key": "pattern",
            "desc": "description",
        }
        toml_file = temp_dir / "config.toml"
        toml_file.write_text("""
[[previewers]]
pattern = '^https?://'
description = 'URL preview'
script = '~/.config/zledit/scripts/url-preview.sh'

[[previewers]]
pattern = '\\.(json|yaml|yml)$'
description = 'Structured data'
script = '/usr/bin/cat'
""")
        results, _ = parse_file(toml_file, config)

        assert len(results) == 2
        assert results[0].key == "^https?://"
        assert results[0].desc == "URL preview"
        assert results[0].type == "zledit-preview"
        assert results[1].key == r"\.(json|yaml|yml)$"
        assert results[1].desc == "Structured data"


class TestNavigatePath:
    """Tests for the _navigate_path helper function."""

    def test_simple_path(self):
        from bindings_help.parser import _navigate_path

        data = {"a": {"b": {"c": 123}}}
        assert _navigate_path(data, "a.b.c") == 123

    def test_empty_path_returns_data(self):
        from bindings_help.parser import _navigate_path

        data = [1, 2, 3]
        assert _navigate_path(data, "") == [1, 2, 3]

    def test_list_index_navigation(self):
        from bindings_help.parser import _navigate_path

        data = {"items": [{"name": "first"}, {"name": "second"}]}
        assert _navigate_path(data, "items.0.name") == "first"
        assert _navigate_path(data, "items.1.name") == "second"

    def test_missing_key_returns_none(self):
        from bindings_help.parser import _navigate_path

        data = {"a": {"b": 1}}
        assert _navigate_path(data, "a.c") is None
        assert _navigate_path(data, "x.y.z") is None

    def test_invalid_list_index(self):
        from bindings_help.parser import _navigate_path

        data = {"items": [1, 2, 3]}
        assert _navigate_path(data, "items.10") is None
        assert _navigate_path(data, "items.notanumber") is None


class TestFindLineForValue:
    """Tests for the _find_line_for_value helper function."""

    def test_find_quoted_value(self):
        from bindings_help.parser import _find_line_for_value

        content = 'line1\nkey = "myvalue"\nline3'
        assert _find_line_for_value(content, "myvalue") == 2

    def test_find_bare_value(self):
        from bindings_help.parser import _find_line_for_value

        content = "line1\nkey: myvalue\nline3"
        assert _find_line_for_value(content, "myvalue") == 2

    def test_start_line_parameter(self):
        from bindings_help.parser import _find_line_for_value

        content = "a: val\nb: val\nc: val"
        # First occurrence is line 1, but start_line=2 should find line 2
        assert _find_line_for_value(content, "val", start_line=2) == 2
        assert _find_line_for_value(content, "val", start_line=3) == 3

    def test_value_not_found_returns_start_line(self):
        from bindings_help.parser import _find_line_for_value

        content = "a: x\nb: y\nc: z"
        assert _find_line_for_value(content, "notfound") == 1
        assert _find_line_for_value(content, "notfound", start_line=5) == 5

    def test_special_regex_chars_escaped(self):
        from bindings_help.parser import _find_line_for_value

        content = 'key = "ctrl+shift+p"\nother'
        assert _find_line_for_value(content, "ctrl+shift+p") == 1
