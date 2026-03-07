# File Upload & Download (`/gate file`)

> Status: **Planned** | Priority: Medium

Send files from `/repo` to chat, or receive files and write them into `/repo`.

## Usage

```
/gate file get <path>       # send /repo/<path> as a document
/gate file put <filename>   # accept next uploaded document, write to /repo/<filename>
```

## Design

### Download
- Resolve `<path>` relative to `REPO_DIR`
- Reject paths outside `REPO_DIR` (path traversal guard)
- Send as Telegram document / Slack file upload
- Cap at 50 MB (Telegram limit); warn if larger

### Upload
- User sends a document message after `/gate file put <filename>`
- Bot saves the file bytes to `REPO_DIR / filename`
- Confirm with checksum

## Platform Notes

| Platform | Download API | Upload API |
|----------|-------------|------------|
| Telegram | `bot.send_document()` | `message.document.get_file()` |
| Slack | `client.files_upload_v2()` | `files_info()` + auth download |

## Files to Change

- `src/bot.py` — add `cmd_file` handler, pending-upload state
- `src/platform/slack.py` — matching handler
