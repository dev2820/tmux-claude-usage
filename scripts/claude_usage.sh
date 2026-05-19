#!/usr/bin/env bash
# Shell wrapper for claude_usage.py with file-based caching.
# Called by tmux via #() — must be fast.

CACHE_FILE="/tmp/tmux-claude-usage.cache"
CACHE_TTL="${CLAUDE_USAGE_CACHE_TTL:-30}"

PLUGIN_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$PLUGIN_DIR/scripts/claude_usage.py"

# Read tmux options (with defaults)
get_tmux_option() {
    local option="$1"
    local default="$2"
    local value
    value="$(tmux show-option -gqv "$option" 2>/dev/null)"
    if [ -n "$value" ]; then
        echo "$value"
    else
        echo "$default"
    fi
}

# Check cache freshness
if [ -f "$CACHE_FILE" ]; then
    if [ "$(uname)" = "Darwin" ]; then
        cache_mtime=$(stat -f %m "$CACHE_FILE" 2>/dev/null)
    else
        cache_mtime=$(stat -c %Y "$CACHE_FILE" 2>/dev/null)
    fi
    now=$(date +%s)
    cache_age=$((now - cache_mtime))
    if [ "$cache_age" -lt "$CACHE_TTL" ]; then
        cat "$CACHE_FILE"
        exit 0
    fi
fi

# Check Python availability
PYTHON=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
fi

if [ -z "$PYTHON" ]; then
    printf "[py?]"
    exit 0
fi

# Build arguments from tmux options
PLAN=$(get_tmux_option "@claude_usage_plan" "pro")
FORMAT=$(get_tmux_option "@claude_usage_format" "full")
COLORS=$(get_tmux_option "@claude_usage_colors" "on")
CUSTOM_BUDGET=$(get_tmux_option "@claude_usage_custom_budget" "")
CACHE_TTL_OPT=$(get_tmux_option "@claude_usage_cache_ttl" "")

# Override cache TTL if set via tmux option
if [ -n "$CACHE_TTL_OPT" ]; then
    CACHE_TTL="$CACHE_TTL_OPT"
fi

ARGS="--plan $PLAN --format $FORMAT"

if [ "$COLORS" = "off" ]; then
    ARGS="$ARGS --no-color"
fi

if [ -n "$CUSTOM_BUDGET" ] && [ "$PLAN" = "custom" ]; then
    ARGS="$ARGS --budget $CUSTOM_BUDGET"
fi

# Run Python script and cache result
# shellcheck disable=SC2086
result=$($PYTHON "$SCRIPT" $ARGS 2>/dev/null)

if [ -n "$result" ]; then
    printf '%s' "$result" > "$CACHE_FILE"
    printf '%s' "$result"
else
    printf '[err]'
fi
