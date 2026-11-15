"""Key notation translation: every source's spelling becomes one canonical form,
short M/C/S notation first and the spelled-out words in brackets, so a search
for m-s-g or alt+shift+g finds a key whatever file defined it."""

import pytest

from bindings_help.keys import normalize_key


@pytest.mark.parametrize("raw, expected", [
    ("^[G", "M-S-g (alt+shift+g)"),
    ("^[q", "M-q (alt+q)"),
    ("^[^O", "M-C-o (ctrl+alt+o)"),
    ("^[^G", "M-C-g (ctrl+alt+g)"),
    ("^X^P", "C-x C-p (ctrl+x ctrl+p)"),
    ("^x^g", "C-x C-g (ctrl+x ctrl+g)"),
    ("^Xw", "C-x w (ctrl+x w)"),
    ("^XY", "C-x S-y (ctrl+x shift+y)"),
    ("^s", "C-s (ctrl+s)"),
    ("^@", "C-Space (ctrl+space)"),
    ("^M", "Enter"),
    ("^[^M", "M-Enter (alt+enter)"),
    ("^[[1;5C", "C-Right (ctrl+right)"),
    ("^[[1;4A", "M-S-Up (alt+shift+up)"),
    ("^[[3~", "Delete"),
    ("^[[Z", "S-Tab (shift+tab)"),
    ("\\eg", "M-g (alt+g)"),
])
def test_zsh(raw, expected):
    assert normalize_key(raw, "zsh") == expected


@pytest.mark.parametrize("raw, expected", [
    ("M-f", "M-f (alt+f)"),
    ("'M-m'", "M-m (alt+m)"),
    ("M-Y", "M-S-y (alt+shift+y)"),
    ("C-M-r", "M-C-r (ctrl+alt+r)"),
    ("M-S-Left", "M-S-Left (alt+shift+left)"),
    ("C-PageDown", "C-PageDown (ctrl+pagedown)"),
    ("M-\\;", "M-; (alt+;)"),
    ("'C-\\'", "C-\\ (ctrl+\\)"),
    ("S", "S-s (shift+s)"),
    ("F2", "F2"),
    ("v", "v"),
    ("'*'", "*"),
    ("MouseDragEnd1Pane", "MouseDragEnd1Pane"),
])
def test_tmux(raw, expected):
    assert normalize_key(raw, "tmux") == expected


@pytest.mark.parametrize("raw, expected", [
    ("<C-P>", "C-p (ctrl+p)"),
    ("<M-h>", "M-h (alt+h)"),
    ("<M-H>", "M-S-h (alt+shift+h)"),
    ("<A-x>", "M-x (alt+x)"),
    ("<C-Up>", "C-Up (ctrl+up)"),
    ("<S-PageUp>", "S-PageUp (shift+pageup)"),
    ("<leader><C-S>", "<leader> C-s (<leader> ctrl+s)"),
    ("<leader>dt", "<leader>dt"),
    ("<Esc>", "Escape"),
    ("<C-w>v", "C-w v (ctrl+w v)"),
])
def test_vim(raw, expected):
    assert normalize_key(raw, "vim") == expected


@pytest.mark.parametrize("raw, expected", [
    ("ctrl+shift+b", "C-S-b (ctrl+shift+b)"),
    ("meta+p", "M-p (alt+p)"),
    ("ctrl+shift+-", "C-S-- (ctrl+shift+-)"),
    ("ctrl+x ctrl+k", "C-x C-k (ctrl+x ctrl+k)"),
    ("shift+tab", "S-Tab (shift+tab)"),
    ("escape", "Escape"),
    ("k", "k"),
    ("ctrl-o", "C-o (ctrl+o)"),
    ("Control+I", "C-i (ctrl+i)"),
    ("Shift|Control+Space", "C-S-Space (ctrl+shift+space)"),
    ("Command+P", "Super-p (super+p)"),
    ("Y", "y"),
    ("Shift+Return", "S-Enter (shift+enter)"),
    ("M-x ctrl-l", "M-x C-l (alt+x ctrl+l)"),
    ("__gh_cli ctrl-y", "__gh_cli C-y (__gh_cli ctrl+y)"),
    ("ctrl+alt+h", "M-C-h (ctrl+alt+h)"),
    ("alt+f10", "M-F10 (alt+f10)"),
    ("ctrl+alt+h (M-C-h)", "M-C-h (ctrl+alt+h)"),
    ("alt+k (M-k)", "M-k (alt+k)"),
])
def test_plus(raw, expected):
    assert normalize_key(raw, "plus") == expected


def test_unknown_or_missing_notation_leaves_the_key_alone():
    assert normalize_key("^[G", None) == "^[G"
    assert normalize_key("^[G", "klingon") == "^[G"


def test_an_unparseable_key_is_returned_unchanged():
    assert normalize_key("^[[99;5x", "zsh") == "^[[99;5x"
