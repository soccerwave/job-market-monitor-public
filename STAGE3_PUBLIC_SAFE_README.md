# Stage 3 — Public-safe GitHub workflow boundary

Stage 3 adds only a safe public CI workflow and prepares, but does not activate,
the production Cloudflare runtime workflow.

## Active GitHub workflow

`.github/workflows/public-ci.yml` runs only public-safe verification:

- repository safety scan
- unit tests
- synthetic policy regression
- public freeze check

It has `contents: read` permission and does not upload private artifacts or commit
runtime data.

## Production workflow status

Production scheduling is intentionally **not active yet**.

`deployment/daily-job-search.cloud-runtime.template.yml` is a non-active template.
It demonstrates the required boundary:

- runtime archive -> `$RUNNER_TEMP`
- state -> `$RUNNER_TEMP`
- latest results -> `$RUNNER_TEMP`
- no `git add/commit/push` for outputs
- no GitHub artifact upload of private results
- no Telegram bot token/chat ID in GitHub

Stage 4 will configure the authenticated Cloudflare Worker/R2 endpoints, state
round-trip, private archive storage, and Telegram delivery. Only then will the
daily workflow be activated and scheduled.

## Runtime code change

`run_cloud_daily.py` now supports `JOB_SEARCH_LATEST_DIR`, matching the existing
environment-driven output and state directories. This allows all private runtime
files to live outside the checked-out public repository.

## Verification

```bash
python scripts/check_public_repo_safety.py
python -m unittest discover -s tests -v
python evaluation/validate_public_synthetic.py
python evaluation/check_public_freeze.py
```
