# Stage 5 — Public GitHub Actions + private Cloudflare runtime

This stage connects the public GitHub repository to the already-deployed private Cloudflare Worker/R2 gateway.

## Security boundary

Public GitHub contains only code, synthetic tests and workflow definitions. Runtime job data is written only under `$RUNNER_TEMP`, then sent through the authenticated Cloudflare Worker to the private R2 bucket and Telegram.

The production workflow:

1. validates the public repository and private gateway health;
2. restores `seen_jobs.json` and `last_successful_run.json` from private R2;
3. checks out the public external collector repositories;
4. runs collection/scoring with all runtime paths under `$RUNNER_TEMP`;
5. suppresses collector stdout/stderr from public Actions logs and stores the full run log only in the private runtime directory;
6. uploads dated outputs/logs/summary to private R2;
7. sends `primary_shortlist_full.csv` to Telegram through the Worker;
8. persists state to R2 only after archive + Telegram delivery succeed;
9. deletes runtime files from the runner.

There is no `git push`, runtime-data commit, or private artifact upload.

## Required GitHub repository secrets

Create exactly these repository Actions secrets:

- `CF_GATEWAY_URL` — e.g. `https://job-market-monitor-private-gateway.<subdomain>.workers.dev`
- `CF_INGEST_TOKEN` — the current long random Worker `INGEST_TOKEN`

Do NOT add Telegram credentials to GitHub. They remain Cloudflare Worker secrets.

## Required repository variable

The workflow contains a daily schedule but scheduled production is disabled by default.

Do not create `PRODUCTION_ENABLED=true` until the real historical state has been migrated into R2 and a manual smoke test has passed.

After validation, create repository Actions variable:

- `PRODUCTION_ENABLED` = `true`

## IMPORTANT: migrate real state before first production run

The earlier manual R2 test wrote a synthetic `state/seen_jobs.json`. It must not be used for production because that would make the first run behave as though the historical seen set were empty.

Before enabling the schedule, upload the real current private-repository files through the Worker:

- `_state/seen_jobs.json` -> `/v1/state/seen_jobs.json`
- `_state/last_successful_run.json` -> `/v1/state/last_successful_run.json`

Then GET both endpoints back and verify them.

## First run protocol

1. Keep `PRODUCTION_ENABLED` absent/false.
2. Add the two GitHub secrets.
3. Run `Public CI` and confirm green.
4. Manually dispatch `Daily Job Search` in `reprocess` mode first. Reprocess does not persist seen-state.
5. Confirm the file arrives in Telegram and private R2 receives the reprocess archive.
6. Inspect the public Actions log and verify no job titles/companies/URLs are exposed.
7. Manually dispatch `auto` only after the real state migration is verified.
8. Finally set `PRODUCTION_ENABLED=true` for daily scheduling.

## Expected daily schedule

The workflow triggers at both possible UTC equivalents of 16:17 Europe/Madrid and uses a Madrid-time guard, preserving DST-safe behavior.
