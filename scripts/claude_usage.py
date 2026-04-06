#!/usr/bin/env python3
"""Claude Code token usage monitor for tmux status bar.

Reads Claude Code JSONL session logs and calculates token usage
within the current 5-hour window against plan limits.

No external dependencies — uses Python standard library only.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone, timedelta


# Plan token limits (matches claude-monitor definitions)
PLAN_LIMITS = {
    "pro": {"tokens": 19_000, "label": "Pro"},
    "max5": {"tokens": 88_000, "label": "Max5"},
    "max20": {"tokens": 220_000, "label": "Max20"},
}

WINDOW_HOURS = 5
CLAUDE_DIR = os.path.expanduser("~/.claude/projects")


def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp string to datetime."""
    # Handle both 'Z' suffix and '+00:00' formats
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def collect_tokens(hours_back=WINDOW_HOURS):
    """Read all JSONL files and sum tokens from the last N hours."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    total_tokens = 0
    jsonl_pattern = os.path.join(CLAUDE_DIR, "*", "*.jsonl")
    files = glob.glob(jsonl_pattern)

    for filepath in files:
        # Skip files not modified recently (optimization)
        try:
            mtime = os.path.getmtime(filepath)
            if datetime.fromtimestamp(mtime, tz=timezone.utc) < cutoff:
                continue
        except OSError:
            continue

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Only count assistant messages with usage data
                    if entry.get("type") != "assistant":
                        continue

                    usage = entry.get("message", {}).get("usage")
                    if not usage:
                        continue

                    # Check timestamp is within window
                    ts = parse_timestamp(entry.get("timestamp", ""))
                    if ts is None or ts < cutoff:
                        continue

                    # Sum input + output tokens only.
                    # Cache tokens (cache_creation, cache_read) are excluded
                    # because plan limits (Pro=19K, Max5=88K, Max20=220K)
                    # correspond to input+output tokens only.
                    tokens = (
                        usage.get("input_tokens", 0)
                        + usage.get("output_tokens", 0)
                    )
                    total_tokens += tokens
        except (OSError, IOError):
            continue

    return total_tokens


def format_tokens_short(tokens):
    """Format token count in human-readable short form."""
    if tokens >= 1_000_000:
        return f"{tokens / 1_000_000:.1f}M"
    if tokens >= 1_000:
        return f"{tokens / 1_000:.1f}K"
    return str(tokens)


def build_progress_bar(pct, width=8):
    """Build a Unicode progress bar."""
    filled = int(pct / (100 / width))
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled)


def format_output(plan_label, pct, remaining_min, fmt="full", use_color=True):
    """Format the tmux status string."""
    pct_int = int(min(pct, 100))

    # Color based on usage level
    if use_color:
        if pct >= 85:
            cs, ce = "#[fg=red]", "#[fg=default]"
        elif pct >= 60:
            cs, ce = "#[fg=yellow]", "#[fg=default]"
        else:
            cs, ce = "#[fg=green]", "#[fg=default]"
    else:
        cs, ce = "", ""

    if fmt == "minimal":
        return f"{cs}{pct_int}%{ce}"

    # Time remaining string
    if remaining_min > 0:
        hours = remaining_min // 60
        mins = remaining_min % 60
        time_str = f" {hours}h{mins:02d}m" if hours > 0 else f" {mins}m"
    else:
        time_str = ""

    if fmt == "short":
        return f"{cs}{plan_label} {pct_int}%{time_str}{ce}"

    # full format
    bar = build_progress_bar(pct)
    return f"{cs}{plan_label} {pct_int}% {bar}{time_str}{ce}"


def main():
    parser = argparse.ArgumentParser(description="Claude Code usage for tmux")
    parser.add_argument(
        "--plan",
        choices=["pro", "max5", "max20", "custom"],
        default="pro",
        help="Subscription plan (default: pro)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Custom token limit (only used with --plan custom)",
    )
    parser.add_argument(
        "--format",
        choices=["full", "short", "minimal"],
        default="full",
        dest="fmt",
        help="Output format (default: full)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable tmux color codes",
    )
    args = parser.parse_args()

    # Determine token limit
    if args.plan == "custom":
        if args.limit is None:
            token_limit = 44_000  # default custom limit
        else:
            token_limit = args.limit
        plan_label = "Custom"
    else:
        plan_info = PLAN_LIMITS[args.plan]
        token_limit = plan_info["tokens"]
        plan_label = plan_info["label"]

    # Collect tokens
    total_tokens = collect_tokens()

    # Calculate percentage
    if token_limit > 0:
        pct = (total_tokens / token_limit) * 100
    else:
        pct = 0

    # Calculate remaining time in the 5-hour window
    # The window resets every 5 hours from an epoch-aligned boundary
    now = datetime.now(timezone.utc)
    # Approximate: time remaining = 5h - (minutes since last 5h boundary)
    epoch_minutes = int(now.timestamp() / 60)
    minutes_into_window = epoch_minutes % (WINDOW_HOURS * 60)
    remaining_min = (WINDOW_HOURS * 60) - minutes_into_window

    output = format_output(
        plan_label, pct, remaining_min, fmt=args.fmt, use_color=not args.no_color
    )
    print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
