#!/usr/bin/env python3
"""Claude Code usage monitor for tmux status bar.

Reads Claude Code JSONL session logs and estimates cost-based usage
within the current 5-hour window against plan spend limits.

No external dependencies — uses Python standard library only.
"""

import argparse
import glob
import json
import os
import sys
from datetime import datetime, timezone, timedelta


# API pricing per 1M tokens (USD) — https://www.anthropic.com/pricing
MODEL_PRICING = {
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_creation": 18.75,
        "cache_read": 1.50,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_creation": 3.75,
        "cache_read": 0.30,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.0,
        "cache_creation": 1.0,
        "cache_read": 0.08,
    },
}

# Fallback pricing when model is unrecognized — use Opus (most expensive)
# to avoid under-counting.
_FALLBACK_PRICING = MODEL_PRICING["claude-opus-4-6"]

# Estimated spend budget per 5-hour window (USD).
# Anthropic does not publish exact numbers.  These are community-derived
# estimates calibrated against observed rate-limit behaviour.
# Ref: GitHub issues #24147, #49302, #54750; Portkey/TrueFoundry analyses.
# Updated 2026-05 after Anthropic doubled all plan limits.
#
# Calibration: a Max5 subscriber used ~$40 in a 5h window without hitting
# rate limits, so the budget must be well above $40.  Estimates below
# assume roughly $50 for Max5 (= 5× Pro $10).
PLAN_LIMITS = {
    "pro":   {"budget": 10.00,  "label": "Pro"},
    "max5":  {"budget": 50.00,  "label": "Max5"},
    "max20": {"budget": 200.00, "label": "Max20"},
}

WINDOW_HOURS = 5
CLAUDE_DIR = os.path.expanduser("~/.claude/projects")


def parse_timestamp(ts_str):
    """Parse ISO 8601 timestamp string to datetime."""
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None


def _resolve_pricing(model_str):
    """Return pricing dict for a model string, with prefix matching."""
    if model_str in MODEL_PRICING:
        return MODEL_PRICING[model_str]
    # Prefix match (e.g. "claude-opus-4-6-20260101" → opus pricing)
    for key, pricing in MODEL_PRICING.items():
        if model_str.startswith(key.rsplit("-", 1)[0]):
            return pricing
    return _FALLBACK_PRICING


def collect_usage(hours_back=WINDOW_HOURS):
    """Read all JSONL files and compute estimated cost in the last N hours.

    Deduplicates by message ID (streaming writes the same message multiple
    times; we keep only the last entry per ID).

    Returns (total_cost_usd, total_messages).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    # {message_id: (model, input, output, cache_creation, cache_read)}
    seen = {}
    jsonl_pattern = os.path.join(CLAUDE_DIR, "*", "*.jsonl")
    subagent_pattern = os.path.join(CLAUDE_DIR, "*", "*", "subagents", "*.jsonl")
    files = glob.glob(jsonl_pattern) + glob.glob(subagent_pattern)

    for filepath in files:
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

                    if entry.get("type") != "assistant":
                        continue

                    msg = entry.get("message", {})
                    usage = msg.get("usage")
                    if not usage:
                        continue

                    ts = parse_timestamp(entry.get("timestamp", ""))
                    if ts is None or ts < cutoff:
                        continue

                    msg_id = msg.get("id")
                    seen[msg_id] = (
                        msg.get("model", ""),
                        usage.get("input_tokens", 0),
                        usage.get("output_tokens", 0),
                        usage.get("cache_creation_input_tokens", 0),
                        usage.get("cache_read_input_tokens", 0),
                    )
        except (OSError, IOError):
            continue

    total_cost = 0.0
    for _id, (model, inp, out, cc, cr) in seen.items():
        p = _resolve_pricing(model)
        total_cost += (
            inp * p["input"]
            + out * p["output"]
            + cc * p["cache_creation"]
            + cr * p["cache_read"]
        ) / 1_000_000

    return total_cost, len(seen)


def build_progress_bar(pct, width=8):
    """Build a Unicode progress bar."""
    filled = int(pct / (100 / width))
    filled = max(0, min(filled, width))
    return "█" * filled + "░" * (width - filled)


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

    # Collect cost-based usage
    total_cost, _ = collect_usage()

    # Calculate percentage
    if budget > 0:
        pct = (total_cost / budget) * 100
    else:
        pct = 0

    # Calculate remaining time in the 5-hour window
    now = datetime.now(timezone.utc)
    epoch_minutes = int(now.timestamp() / 60)
    minutes_into_window = epoch_minutes % (WINDOW_HOURS * 60)
    remaining_min = (WINDOW_HOURS * 60) - minutes_into_window

    output = format_output(
        plan_label, pct, remaining_min,
        fmt=args.fmt, use_color=not args.no_color,
    )
    print(output, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
