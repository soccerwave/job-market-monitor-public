# Cloudflare private gateway

This Worker is the private data boundary for the public GitHub repository.

## What it stores

Private R2 bucket `job-market-monitor-private`:

- `state/seen_jobs.json`
- `state/last_successful_run.json`
- `archive/YYYY-MM-DD/<file>`

The bucket must NOT be public.

## Secrets

Set these as Worker secrets, never in Git:

- `INGEST_TOKEN` — random bearer token shared only with the GitHub Actions secret of the same purpose.
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

## Endpoints

All `/v1/*` endpoints require `Authorization: Bearer <INGEST_TOKEN>`.

- `GET /health` — public, contains no private data.
- `GET /v1/state/seen_jobs.json`
- `PUT /v1/state/seen_jobs.json`
- `GET /v1/state/last_successful_run.json`
- `PUT /v1/state/last_successful_run.json`
- `PUT /v1/archive/YYYY-MM-DD/<filename>` — raw body is stored in R2.
- `POST /v1/telegram/document` — raw file body, with `X-Filename` and optional `X-Caption` headers; Worker forwards it to Telegram using multipart/form-data.

## Deployment

From this directory:

```bash
npm install
npx wrangler login
npx wrangler r2 bucket create job-market-monitor-private
npx wrangler secret put INGEST_TOKEN
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npx wrangler deploy
```

Generate `INGEST_TOKEN` locally with a cryptographically random generator, for example:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Do not put the generated value in a file committed to Git.

## Quick health check

After deployment:

```bash
curl https://<worker-subdomain>/health
```

Expected response:

```json
{"ok":true,"service":"job-market-monitor-private-gateway"}
```

Authenticated state check (404 is normal before the first run):

```bash
curl -i \
  -H "Authorization: Bearer $INGEST_TOKEN" \
  https://<worker-subdomain>/v1/state/seen_jobs.json
```
