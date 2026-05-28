#!/usr/bin/env python3
"""Claude Code usage monitor for tmux status bar.

Uses ccusage CLI (https://ccusage.com/) to read the current 5-hour
billing window and displays cost-based usage against plan spend limits.

Requires: ccusage (npm/bun — e.g. `bunx ccusage`)
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone


# Estimated spend budget per 5-hour window (USD).
PLAN_LIMITS = {
    "pro":   {"budget": 10.00,  "label": "Pro"},
    "max5":  {"budget": 50.00,  "label": "Max5"},
    "max20": {"budget": 200.00, "label": "Max20"},
}


def _find_ccusage_runner():
    """Return a command prefix list for running ccusage."""
    for cmd in ["bunx", "npx"]:
        if _which(cmd):
            return [cmd, "ccusage"]
    # Try ccusage directly (global install)
    if _which("ccusage"):
        return ["ccusage"]
    return None


def _which(cmd):
    """Check if a command is available on PATH."""
    from shutil import which
    return which(cmd) is not None


def get_active_block(runner):
    """Run ccusage claude blocks --json and return the active block dict."""
    cmd = runner + ["claude", "blocks", "--json"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    blocks = data.get("blocks", [])
    for block in blocks:
        if block.get("isActive"):
            return block

    return None


def build_progress_bar(pct, width=8):
    """Build a Unicode progress bar."""
    filled = int(pct / (100 / width))
    filled = max(0, min(filled, width))
    return "\u2588" * filled + "\u2591" * (width - filled)


def format_output(plan_label, pct, remaining_min,
                  fmt="full", use_color=True):
    """Format the tmux status string."""
    pct_capped = min(pct, 999)
    pct_int = int(min(pct_capped, 100))

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

    if fmt == "pie":
        return f"{cs}{plan_label} {{p:{pct_int}}} {pct_int}%{time_str}{ce}"

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
        "--budget",
        type=float,
        default=None,
        help="Custom spend budget in USD (only used with --plan custom)",
    )
    parser.add_argument(
        "--format",
        choices=["full", "short", "minimal", "pie"],
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

    # Determine spend budget
    if args.plan == "custom":
        budget = args.budget if args.budget is not None else 10.0
        plan_label = "Custom"
    else:
        plan_info = PLAN_LIMITS[args.plan]
        budget = plan_info["budget"]
        plan_label = plan_info["label"]

    # Find ccusage runner
    runner = _find_ccusage_runner()
    if runner is None:
        print("[ccusage?]", end="")
        return 1

    # Get current billing window from ccusage
    block = get_active_block(runner)
    if block is None:
        # No active block — usage is 0
        total_cost = 0.0
        remaining_min = 0
    else:
        total_cost = block.get("costUSD", 0.0)
        projection = block.get("projection") or {}
        remaining_min = int(projection.get("remainingMinutes", 0))

    # Calculate percentage
    if budget > 0:
        pct = (total_cost / budget) * 100
    else:
        pct = 0

    output = format_output(
        plan_label, pct, remaining_min,
        fmt=args.fmt, use_color=not args.no_color,
    )
    print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
