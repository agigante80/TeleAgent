# Web Dashboard

> Status: **Planned** | Priority: Low (optional)

A lightweight read-only HTTP endpoint served inside the container for monitoring.

## Features

- Current uptime, active backend, last 10 conversation exchanges
- `/health` endpoint for external monitoring (alternative to file-based HEALTHCHECK)
- Protected by `DASHBOARD_TOKEN` env var (Bearer token)
- Single-file FastAPI implementation

## Configuration

```env
DASHBOARD_ENABLED=true
DASHBOARD_PORT=8080
DASHBOARD_TOKEN=secret-token
```

## Design

- `src/dashboard.py` — FastAPI app, started as a background `asyncio.Task` alongside the bot
- Reads from the same `ConversationHistory` instance (thread-safe read)
- Exposes `/`, `/health`, `/api/status`

## Dependencies to Add

```
fastapi>=0.110
uvicorn>=0.29
```

## Notes

Expose the port in `docker-compose.yml`:
```yaml
ports:
  - "8080:8080"
```
