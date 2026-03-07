# npm Globals Not Covered by Dependabot

> Status: **Open** | Priority: Low

## Problem

`@github/copilot-cli` and `@openai/codex` are pinned in the Dockerfile but Dependabot does not update npm globals installed via `RUN npm install -g`.

## Impact

Security patches and new features in Copilot CLI or Codex CLI are not automatically picked up. Manual update required when new versions ship.

## Resolution Options

1. **Manual**: monitor release pages and update Dockerfile pins on each release
2. **Dependabot workaround**: add a minimal `package.json` that lists these as devDependencies and commit it — Dependabot can then track it
3. **Automated check**: add a GitHub Actions step that calls `npm outdated -g` and comments on PRs when stale

Preferred: option 2 — minimal friction, no new tooling.
