# Stage 4 — Cloudflare private data boundary

This stage adds a deployable Cloudflare Worker + private R2 architecture.

No production GitHub workflow is activated yet.

## Security boundary

Public GitHub contains code only. Private state and daily outputs are stored in R2, and documents are forwarded from Worker to Telegram. Telegram credentials live only in Cloudflare Worker secrets.

## Required Cloudflare resources

1. Worker: `job-market-monitor-private-gateway`
2. Private R2 bucket: `job-market-monitor-private`
3. Worker secrets:
   - `INGEST_TOKEN`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`

The R2 bucket must not have public access enabled.

## Next stage

After the Worker is deployed and its `/health` endpoint works, Stage 5 will connect the GitHub Actions production workflow to this gateway and remove every GitHub-side persistence path.
