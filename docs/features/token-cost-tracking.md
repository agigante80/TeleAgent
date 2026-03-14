Feature: Token / Cost Tracking
Status: Proposed
Owners: @GateCode (implementation), @GateSec (security review)

Summary

Capture usage/`usage` payloads returned by OpenAI (via DirectAPIBackend) and accumulate per-session and per-day spend counters. Surface spend and token usage via `/gate status` and expose lightweight metrics for consumption.

Motivation

- Make AI costs visible to operators and end users.
- Enable budget alerts and per-session accountability.
- Provide data for cost-optimizations (prompt trimming, model selection).

Files to Change

- src/ai/direct.py — collect and forward `usage` from provider responses.
- src/config.py — add pricing overrides and feature flags (see Env vars).
- src/history.py or a new src/billing.py — persist aggregated usage (per-day, per-session).
- src/bot.py — extend `/gate status` handler to show today's spend and session totals.
- tests/ — unit/contract tests for aggregation and reporting.

Design

1. Capture: DirectAPIBackend inspects provider responses for a `usage` block (e.g., OpenAI: prompt_tokens, completion_tokens, total_tokens). Convert tokens -> cost using model-specific pricing coefficients.

2. Storage: add a new SQLite table `usage_records`:
   - id, date (YYYY-MM-DD), session_id, backend, model, prompt_tokens, completion_tokens, total_tokens, cost_usd, created_at

   Aggregate queries calculate per-session and per-day totals. Prefer storing raw token counts + computed cost (avoid storing provider billing IDs).

3. Pricing config: add optional per-model pricing overrides to `AIConfig` (e.g., `pricing_overrides: {"gpt-4": {"prompt": 0.03, "completion": 0.06}}`). If unset, fall back to default in-code coefficients (documented and testable).

4. Surface: `/gate status` returns concise spend summary for current session and today (e.g., "Today: $1.23 — Session: $0.11"). Additionally, expose metrics (see metrics feature) and a `/gate billing --since=2026-03-01` admin command.

5. Backpressure & batching: buffer usage writes in-memory and flush periodically to avoid DB I/O bursts. On shutdown, flush buffer.

Env Vars

- TOKEN_TRACKING_ENABLED=true|false (default: false)
- TOKEN_PRICING_OVERRIDES — JSON string or path to file (optional)

Security Considerations

- Usage records do not store prompts or model responses; only token counts and computed cost. Avoid persisting any unredacted text.
- Access to usage data is still sensitive (billing info). Enforce same access controls as history DB and audit access events.
- Validate that redaction logic is not accidentally bypassed — token counting should occur from the provider response metadata, not by re-parsing user content.

Testing

- Unit tests: token->cost conversion, per-model pricing override, DB insertion, aggregation queries.
- Integration tests: simulate DirectAPIBackend responses with `usage` payload and assert `/gate status` shows expected sums.
- Regression: ensure no raw text fields are written to usage tables.

Rollout Plan

- Feature-flagged rollout (TOKEN_TRACKING_ENABLED=false by default).
- Deploy to staging, validate metrics and `/gate status` output for sample loads, then enable in prod.

Open Questions

- Who pays costs per-session (user vs tenant)? Add tenant_id to storage if multi-tenant.
- Should historical per-day costs be exportable (CSV)?
- Rate-limits around DB writes under high traffic.

Notes

This doc focuses on OpenAI-style `usage` payloads. For other backends (Anthropic, Gemini), normalize their usage metadata to the same schema.
