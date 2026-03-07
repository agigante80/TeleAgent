# Proactive Alerts

> Status: **Planned** | Priority: Low

Let the bot notify the chat proactively when something happens in the repo or container.

## Usage (env vars)

```env
WATCH_FILES=docker-compose.yml,requirements.txt   # alert on file changes
ALERT_KEYWORDS=ERROR,FATAL                        # alert on log keywords
ALERT_CHANNEL=C0123456789                         # Slack channel (optional override)
```

## Design

### File watcher
- Uses `watchfiles` library — async, efficient, cross-platform
- Monitors `REPO_DIR` for changes to files listed in `WATCH_FILES`
- Posts `📝 File changed: <path>` to chat

### Log keyword monitor
- Tails `/data/history.db` WAL or a configurable log path
- Scans each new line for keywords in `ALERT_KEYWORDS`
- Posts `⚠️ Alert: matched '<keyword>' in <source>`

## Dependencies to Add

```
watchfiles>=0.21
```

## Files to Create/Change

- `src/watcher.py` — file and log watchers, async tasks
- `src/main.py` — start watcher tasks alongside the bot event loop
- `src/config.py` — add `BotConfig.watch_files`, `alert_keywords`
- `requirements.txt` — add `watchfiles`
