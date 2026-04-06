# tmux-claude-usage

Claude Code token usage monitor for the tmux status bar.

Shows your current plan, usage percentage, progress bar, and time remaining in the 5-hour window — all at a glance.

```
Pro 98% ████████ 2h03m    # red - approaching limit
Max5 52% ████░░░░ 3h21m   # yellow - moderate usage
Max20 8% ░░░░░░░░ 4h50m   # green - plenty of room
```

## Features

- Real-time token usage tracking from Claude Code session logs
- Color-coded status (green/yellow/red) based on usage level
- File-based caching (30s TTL) for minimal overhead
- Three display formats: `full`, `short`, `minimal`
- Supports Pro, Max5, Max20, and custom plans
- Zero external dependencies — Python standard library only

## Requirements

- tmux (with or without TPM)
- Python 3.6+

## Installation

### With TPM (recommended)

Add to your `.tmux.conf`:

```bash
set -g @plugin 'dev2820/tmux-claude-usage'
```

Then press `prefix + I` to install.

### Manual

```bash
git clone https://github.com/dev2820/tmux-claude-usage ~/.tmux/plugins/tmux-claude-usage
```

Add to your `.tmux.conf`:

```bash
run-shell ~/.tmux/plugins/tmux-claude-usage/claude-usage.tmux
```

## Usage

Add `#{claude_usage}` to your status bar:

```bash
set -g status-right '#{claude_usage} | %R | %d %b'
```

For Oh My Tmux users, edit `~/.tmux/.tmux.conf.local`:

```bash
tmux_conf_theme_status_right=" #{claude_usage} | %R | %d %b "
```

## Configuration

All options are set via tmux options:

| Option                       | Default | Values                           | Description                 |
| ---------------------------- | ------- | -------------------------------- | --------------------------- |
| `@claude_usage_plan`         | `pro`   | `pro`, `max5`, `max20`, `custom` | Subscription plan           |
| `@claude_usage_format`       | `full`  | `full`, `short`, `minimal`       | Display format              |
| `@claude_usage_colors`       | `on`    | `on`, `off`                      | Color output                |
| `@claude_usage_cache_ttl`    | `30`    | seconds                          | Cache duration              |
| `@claude_usage_custom_limit` | —       | integer                          | Token limit for custom plan |

Example:

```bash
set -g @claude_usage_plan 'max5'
set -g @claude_usage_format 'short'
```

### Display Formats

- **full**: `Pro 52% ████░░░░ 2h31m`
- **short**: `Pro 52% 2h31m`
- **minimal**: `52%`

### Color Thresholds

| Usage  | Color  | Meaning           |
| ------ | ------ | ----------------- |
| < 60%  | Green  | Plenty of room    |
| 60-84% | Yellow | Moderate usage    |
| >= 85% | Red    | Approaching limit |

### Plan Limits

| Plan   | Token Limit  |
| ------ | ------------ |
| Pro    | 19,000       |
| Max5   | 88,000       |
| Max20  | 220,000      |
| Custom | configurable |

## How It Works

1. Reads Claude Code session logs (`~/.claude/projects/*/*.jsonl`)
2. Sums `input_tokens + output_tokens` from the last 5 hours
3. Calculates percentage against your plan's token limit
4. Outputs a formatted string with tmux color codes

Cache file is stored at `/tmp/tmux-claude-usage.cache` and refreshed every 30 seconds (configurable).

## License

MIT
