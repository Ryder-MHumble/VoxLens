# VoxLens Local Ops Runbook

VoxLens alpha mode uses local browser automation and crawler-style collection. This runbook turns the legal risk notice into operational rules for maintainers.

## Safe Operating Defaults

- Use low-frequency local runs; avoid parallel manual retries against the same platform.
- Prefer test or low-risk accounts where platform terms and local law allow it.
- Use explicit cookie environment variables only for accounts you control.
- Do not bypass platform controls, captchas, login challenges, paywalls or rate limits.
- Treat all outputs as research assistance that needs human review.

## Cookie and Login Handling

Cookie env vars are listed in `/api/capabilities` under `auth.cookieEnvVars` and come from the shared platform catalog.

- Store cookies in `.env` or shell-local environment only; never commit them.
- Rotate cookies after suspicious login prompts, unexpected redirects, or account-security warnings.
- Remove cookies immediately if a run triggers verification, account warnings or unusual platform behavior.
- Prefer `authMode=auto` for local experiments; use `authMode=cookie` only when you want the run to fail closed if cookies are absent.

## Runtime Data Locations

- Research runs: `runtime/runs/research/{runId}/`
- Crawler outputs: `runtime/runs/crawler/`
- Markdown CLI reports: `reports/`

Cleanup policy for local alpha:

```bash
rm -rf runtime/runs/research/* runtime/runs/crawler/*
```

Only delete local runtime output after confirming no active run is using it.

## Stop Conditions

Stop running collection for a platform immediately when any of these occur:

- The platform displays verification, abnormal-login or account-risk prompts.
- The account receives warnings, temporary restrictions or ban signals.
- Requests begin returning repeated anti-automation pages, empty pages, or login loops.
- A run unexpectedly increases request volume beyond the configured limits.
- The requested use case involves regulated, illegal, harassing or privacy-invasive collection.

After a stop condition, clear cookies, archive the run logs for diagnosis, and do not retry until a maintainer reviews the cause.

## Incident Response

1. Stop the active process or close the browser automation session.
2. Preserve `record.json`, `events.jsonl`, provider stderr and relevant crawler JSONL for debugging.
3. Remove cookies from `.env` and shell history if needed.
4. Note the platform, query, request limits, auth mode and timestamp in the issue or PR.
5. Lower limits or disable the affected platform before re-running.

## Capacity Assumptions

The current queue is in-process and single-node. Keep alpha usage within these bounds:

- One local API process.
- Low single-digit concurrent runs.
- Conservative per-platform limits.
- No unattended recurring crawler jobs.

Move to an external queue and stronger run storage only when alpha exit criteria show this local model is the bottleneck.
