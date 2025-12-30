#!/usr/bin/env bash
set -eo pipefail

# Example: rofi popup for confhelp
# Global hotkey friendly - works from any app

DOTFILES="$HOME/dev/dotfiles"

selection=$(confhelp -b "$DOTFILES" | column -t -s'|' | rofi -dmenu -i -p "bindings" -theme-str 'window {width: 80%;} listview {lines: 20;}')

if [[ -n "$selection" ]]; then
    file_line=$(echo "$selection" | awk '{print $NF}')
    file=$(echo "$file_line" | cut -d: -f1)
    line=$(echo "$file_line" | cut -d: -f2)

    # Open in terminal with nvim
    alacritty -e nvim "+$line" "${DOTFILES}/${file}" &
fi
