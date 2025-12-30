"""Tests for the config-driven parser."""

import tempfile
from pathlib import Path

import pytest

from bindings_help.parser import parse_file, parse_all, load_config, Binding


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
        results = parse_file(tmux_conf, config)

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
        results = parse_file(aliases, config)

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
        results = parse_file(funcs, config)

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
        results = parse_file(abbrevs, config)

        assert len(results) == 2
        assert results[0].key == "gst"
        assert results[0].desc == "git status"

    def test_parse_nonexistent_file(self, temp_dir):
        config = {"type": "test", "regex": ".*"}
        results = parse_file(temp_dir / "nonexistent", config)
        assert results == []

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

        results = parse_file(aliases, config)
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

        results = parse_all(config_toml, temp_dir)

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

        results = parse_file(f, config)
        assert len(results) == 1
        assert results[0].key == "bind"

    def test_empty_file(self, temp_dir):
        config = {"type": "test", "regex": r"(\w+)"}
        f = temp_dir / "empty"
        f.write_text("")

        results = parse_file(f, config)
        assert results == []

    def test_no_matches(self, temp_dir):
        config = {"type": "test", "regex": r"NOMATCH(\d+)"}
        f = temp_dir / "conf"
        f.write_text("line one\nline two\nline three")

        results = parse_file(f, config)
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

        results = parse_file(f, config)
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

        results = parse_all(config_toml, temp_dir)
        keys = {r.key for r in results}
        assert keys == {"foo", "baz"}

    def test_line_numbers_correct(self, temp_dir):
        config = {"type": "test", "regex": r"test(\d+)"}
        f = temp_dir / "conf"
        f.write_text("# comment\ntest1\n# another\ntest2\ntest3")

        results = parse_file(f, config)
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

        results = parse_file(f, config)
        assert results[0].desc == "single"
        assert results[1].desc == "double"
        assert results[2].desc == "none"
