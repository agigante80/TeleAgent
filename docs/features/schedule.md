# Scheduled Commands (`/gate schedule`)

> Status: **Planned** | Priority: Medium

Allow recurring shell commands or AI prompts triggered on a schedule.

## Usage

```
/gate schedule "git pull && pytest" every 6h
/gate schedule "check if any service is down" every 30m
/gate schedule list
/gate schedule cancel <id>
```

## Design

- **Scheduler**: `APScheduler` (async, cron + interval triggers)
- **Storage**: schedules persisted to `/data/schedules.db` (SQLite) — survive restarts
- **Auth**: only allowed from authorized chat/user (same `@_requires_auth` guard)
- **Output**: results posted to the originating chat when the job fires

## Dependencies to Add

```
apscheduler>=3.10
```

## Files to Create/Change

- `src/scheduler.py` — job store, CRUD, runner
- `src/bot.py` / `src/platform/slack.py` — add `cmd_schedule` handler
- `requirements.txt` — add `apscheduler`
