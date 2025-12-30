#!/usr/bin/env bash
set -eo pipefail

# Example: tmux popup for confhelp
# Shows bindings in a tmux popup, opens selection in $EDITOR

DOTFILES="$HOME/dotfiles"

selection=$(confhelp -b "$DOTFILES" | column -t -s'|' | fzf \
    --header='Enter=jump to file' \
    --height=100% \
    --layout=reverse \
    --border=sharp \
    --prompt='bindings: ')

if [[ -n "$selection" ]]; then
    file_line=$(echo "$selection" | awk '{print $NF}')
    file=$(echo "$file_line" | cut -d: -f1)
    line=$(echo "$file_line" | cut -d: -f2)
    ${EDITOR:-nvim} "+$line" "${DOTFILES}/${file}"
fi
