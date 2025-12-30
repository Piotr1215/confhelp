#!/usr/bin/env bash
set -eo pipefail

# Example: Alacritty popup for confhelp
# Shows bindings in a centered popup window
# Enter = jump to line in nvim

DOTFILES="$HOME/dev/dotfiles"
TEMP_FILE=$(mktemp)

FZF_COLORS='fg:#f8f8f2,bg:#282a36,hl:#bd93f9,fg+:#f8f8f2,bg+:#44475a,hl+:#bd93f9,info:#ffb86c,prompt:#50fa7b,pointer:#ff79c6,marker:#ff79c6,spinner:#ffb86c,header:#6272a4'

main_loop() {
    local selection
    selection=$(confhelp -b "$DOTFILES" | column -t -s'|' | fzf \
        --header='Enter=jump to file' \
        --height=100% \
        --layout=reverse \
        --info=inline \
        --border=sharp \
        --prompt='bindings: ' \
        --color="$FZF_COLORS" \
        || true)

    if [[ -n "$selection" ]]; then
        local file_line=$(echo "$selection" | awk '{print $NF}')
        local file=$(echo "$file_line" | cut -d: -f1)
        local line=$(echo "$file_line" | cut -d: -f2)
        echo "FILE:${DOTFILES}/${file}:${line}" > "$TEMP_FILE"
    fi
}

export -f main_loop
export DOTFILES TEMP_FILE FZF_COLORS

# Calculate center position (requires xdpyinfo)
read screen_w screen_h < <(xdpyinfo | awk '/dimensions:/{print $2}' | tr 'x' ' ')
cols=220
lines=50
win_w=$((cols * 9))
win_h=$((lines * 20))
pos_x=$(( (screen_w - win_w) / 2 ))
pos_y=$(( (screen_h - win_h) / 2 ))

alacritty --class config-bindings-popup \
    --config-file /dev/null \
    -o window.dimensions.columns=$cols \
    -o window.dimensions.lines=$lines \
    -o window.position.x=$pos_x \
    -o window.position.y=$pos_y \
    -e bash -c "main_loop"

# Handle result
if [[ -f "$TEMP_FILE" ]]; then
    result=$(cat "$TEMP_FILE")
    rm -f "$TEMP_FILE"

    case "$result" in
        FILE:*)
            target="${result#FILE:}"
            file=$(echo "$target" | cut -d: -f1)
            line=$(echo "$target" | cut -d: -f2)
            nohup alacritty -e nvim "+$line" "$file" >/dev/null 2>&1 &
            ;;
    esac
fi
