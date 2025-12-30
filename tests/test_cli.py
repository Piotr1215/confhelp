"""Tests for CLI functionality."""

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_config():
    """Create a temporary config and dotfiles for testing."""
    with tempfile.TemporaryDirectory() as d:
        base = Path(d)

        # Create config
        config = base / "config.toml"
        config.write_text("""
[tmux]
paths = [".tmux.conf"]
match_line = "^bind"
regex = 'bind\\s+(\\S+)(.*)'
key_group = 1
desc_group = 2
type = "tmux"
""")

        # Create dotfile with many bindings
        tmux_conf = base / ".tmux.conf"
        lines = [f"bind {chr(97+i)} action{i}" for i in range(26)]
        tmux_conf.write_text("\n".join(lines))

        yield base, config


class TestCLI:
    def test_broken_pipe_handled(self, temp_config):
        """Piping to head should not raise BrokenPipeError."""
        base, config = temp_config

        # Run confhelp piped to head -5
        result = subprocess.run(
            f"confhelp -c {config} -b {base} | head -5",
            shell=True,
            capture_output=True,
            text=True,
        )

        # Should have output and no Python traceback
        assert result.stdout.count("\n") == 5
        assert "BrokenPipeError" not in result.stderr
        assert "Traceback" not in result.stderr

    def test_output_format_pipe(self, temp_config):
        """Default pipe format outputs correctly."""
        base, config = temp_config

        result = subprocess.run(
            ["confhelp", "-c", str(config), "-b", str(base)],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.strip().split("\n")
        assert len(lines) == 26
        assert lines[0].startswith("[tmux]|")
        assert "|.tmux.conf:" in lines[0]

    def test_output_format_json(self, temp_config):
        """JSON format outputs valid JSON."""
        import json
        base, config = temp_config

        result = subprocess.run(
            ["confhelp", "-c", str(config), "-b", str(base), "-f", "json"],
            capture_output=True,
            text=True,
        )

        data = json.loads(result.stdout)
        assert len(data) == 26
        assert data[0]["type"] == "tmux"
        assert "key" in data[0]

    def test_output_format_tsv(self, temp_config):
        """TSV format uses tabs."""
        base, config = temp_config

        result = subprocess.run(
            ["confhelp", "-c", str(config), "-b", str(base), "-f", "tsv"],
            capture_output=True,
            text=True,
        )

        lines = result.stdout.strip().split("\n")
        assert "\t" in lines[0]
        assert lines[0].count("\t") == 3  # type, key, desc, file:line

    def test_missing_base_dir_error(self, temp_config):
        """Error when base-dir not provided."""
        _, config = temp_config

        result = subprocess.run(
            ["confhelp", "-c", str(config)],
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "base-dir" in result.stderr.lower() or "required" in result.stderr.lower()

    def test_init_creates_config(self):
        """--init creates sample config."""
        with tempfile.TemporaryDirectory() as d:
            # Set HOME to temp dir
            import os
            old_home = os.environ.get("HOME")
            os.environ["HOME"] = d

            try:
                result = subprocess.run(
                    ["confhelp", "--init"],
                    capture_output=True,
                    text=True,
                )

                config_path = Path(d) / ".config/confhelp/config.toml"
                assert config_path.exists()
                assert "Created:" in result.stdout
            finally:
                if old_home:
                    os.environ["HOME"] = old_home

    def test_base_dirs_from_config(self):
        """base_dirs can be set in config file."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)

            # Create config with base_dirs
            config = base / "config.toml"
            dotfiles = base / "dotfiles"
            dotfiles.mkdir()

            config.write_text(f'''
base_dirs = ["{dotfiles}"]

[tmux]
paths = [".tmux.conf"]
match_line = "^bind"
regex = 'bind\\s+(\\S+)(.*)'
key_group = 1
desc_group = 2
type = "tmux"
''')

            # Create dotfile
            (dotfiles / ".tmux.conf").write_text("bind r reload")

            # Run without -b flag
            result = subprocess.run(
                ["confhelp", "-c", str(config)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "[tmux]|r|" in result.stdout

    def test_multiple_base_dirs(self):
        """Multiple base_dirs are all parsed."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)

            # Create two dotfile directories
            dotfiles1 = base / "dotfiles1"
            dotfiles2 = base / "dotfiles2"
            dotfiles1.mkdir()
            dotfiles2.mkdir()

            config = base / "config.toml"
            config.write_text(f'''
base_dirs = ["{dotfiles1}", "{dotfiles2}"]

[tmux]
paths = [".tmux.conf"]
regex = 'bind\\s+(\\S+)'
key_group = 1
type = "tmux"
''')

            (dotfiles1 / ".tmux.conf").write_text("bind a action1")
            (dotfiles2 / ".tmux.conf").write_text("bind b action2")

            result = subprocess.run(
                ["confhelp", "-c", str(config)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "[tmux]|a|" in result.stdout
            assert "[tmux]|b|" in result.stdout

    def test_glob_pattern_single_star(self):
        """Glob pattern *.lua matches files in directory."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            lua_dir = base / "lua"
            lua_dir.mkdir()

            config = base / "config.toml"
            config.write_text('''
[nvim]
paths = ["lua/*.lua"]
match_line = "keymap"
regex = 'keymap\\("([^"]+)".*desc\\s*=\\s*"([^"]+)"'
key_group = 1
desc_group = 2
type = "nvim"
''')

            (lua_dir / "a.lua").write_text('keymap("<leader>a", cmd, { desc = "action a" })')
            (lua_dir / "b.lua").write_text('keymap("<leader>b", cmd, { desc = "action b" })')
            (lua_dir / "not_lua.txt").write_text('keymap("<leader>x", cmd, { desc = "ignored" })')

            result = subprocess.run(
                ["confhelp", "-c", str(config), "-b", str(base)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "[nvim]|<leader>a|action a|" in result.stdout
            assert "[nvim]|<leader>b|action b|" in result.stdout
            assert "ignored" not in result.stdout  # .txt not matched

    def test_glob_pattern_double_star(self):
        """Glob pattern **/*.lua matches nested directories."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)

            # Create nested structure
            (base / "lua").mkdir()
            (base / "lua/config").mkdir()
            (base / "lua/plugins").mkdir()

            config = base / "config.toml"
            config.write_text('''
[nvim]
paths = ["lua/**/*.lua"]
match_line = "map"
regex = 'map\\("([^"]+)".*desc\\s*=\\s*"([^"]+)"'
key_group = 1
desc_group = 2
type = "nvim"
''')

            (base / "lua/mappings.lua").write_text('map("<leader>m", x, { desc = "root" })')
            (base / "lua/config/keys.lua").write_text('map("<leader>c", x, { desc = "config" })')
            (base / "lua/plugins/lsp.lua").write_text('map("<leader>l", x, { desc = "lsp" })')

            result = subprocess.run(
                ["confhelp", "-c", str(config), "-b", str(base)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "root" in result.stdout
            assert "config" in result.stdout
            assert "lsp" in result.stdout

    def test_glob_no_matches(self):
        """Glob pattern with no matches produces no output."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)

            config = base / "config.toml"
            config.write_text('''
[nvim]
paths = ["nonexistent/**/*.lua"]
regex = 'map\\("([^"]+)"'
key_group = 1
type = "nvim"
''')

            result = subprocess.run(
                ["confhelp", "-c", str(config), "-b", str(base)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert result.stdout.strip() == ""

    def test_glob_mixed_with_explicit_paths(self):
        """Config can mix glob patterns and explicit paths."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "lua").mkdir()

            config = base / "config.toml"
            config.write_text('''
[tmux]
paths = [".tmux.conf"]
regex = 'bind\\s+(\\S+)'
key_group = 1
type = "tmux"

[nvim]
paths = ["lua/*.lua"]
regex = 'map\\("([^"]+)"'
key_group = 1
type = "nvim"
''')

            (base / ".tmux.conf").write_text("bind r reload")
            (base / "lua/keys.lua").write_text('map("<leader>k")')

            result = subprocess.run(
                ["confhelp", "-c", str(config), "-b", str(base)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "[tmux]|r|" in result.stdout
            assert "[nvim]|<leader>k|" in result.stdout

    def test_glob_relative_path_in_output(self):
        """Glob matches show correct relative path in output."""
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "config/nvim/lua").mkdir(parents=True)

            config = base / "config.toml"
            config.write_text('''
[nvim]
paths = ["config/nvim/lua/**/*.lua"]
regex = 'map\\("([^"]+)"'
key_group = 1
type = "nvim"
''')

            (base / "config/nvim/lua/init.lua").write_text('map("<leader>i")')

            result = subprocess.run(
                ["confhelp", "-c", str(config), "-b", str(base)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            # Output should show full relative path
            assert "config/nvim/lua/init.lua:" in result.stdout
