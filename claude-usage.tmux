#!/usr/bin/env bash
# tmux-claude-usage: TPM plugin entry point
# Shows Claude Code token usage in the tmux status bar.

CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Store plugin directory for scripts to reference
tmux set-option -g @claude_usage_plugin_dir "$CURRENT_DIR"

# Set default options if not already configured
set_default() {
    local option="$1"
    local default="$2"
    local current
    current="$(tmux show-option -gqv "$option" 2>/dev/null)"
    if [ -z "$current" ]; then
        tmux set-option -g "$option" "$default"
    fi
}

set_default "@claude_usage_plan" "pro"
set_default "@claude_usage_format" "full"
set_default "@claude_usage_colors" "on"
set_default "@claude_usage_cache_ttl" "30"

# Check Python availability
if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
    tmux display-message "tmux-claude-usage: python3 not found"
fi

# Register #{claude_usage} interpolation
# Replace #{claude_usage} in status-right and status-left with #(script call)
SCRIPT="$CURRENT_DIR/scripts/claude_usage.sh"
chmod +x "$SCRIPT"

do_interpolation() {
    local option="$1"
    local value
    value="$(tmux show-option -gqv "$option" 2>/dev/null)"
    if [ -n "$value" ]; then
        local updated="${value//\#\{claude_usage\}/#($SCRIPT)}"
        if [ "$updated" != "$value" ]; then
            tmux set-option -g "$option" "$updated"
        fi
    fi
}

do_interpolation "status-right"
do_interpolation "status-left"
