# Job Market Monitor — Cloud Setup

This repository runs the personal job-discovery pipeline automatically on GitHub Actions.


## Current canonical checkpoint (2026-08-30)

* Rule engine: `jobs_v6_4_recall_guard.py` (V6.4 recall-safe baseline).
* `jobs_v5.py` is kept only as a backward-compatible wrapper.
* Human evaluation and Scoring V1 assets live under `evaluation/`.
* Clean DEV labels: 60.
* Scoring V1 is integrated as a **ranking-only** layer and reproduces the 60-row DEV calibration fixture exactly.
* Clean HOLDOUT reserved for one-time validation: 71 rows; it has not been used for tuning.
* See `PROJECT_STATUS.md` and `evaluation/README.md` before changing filtering/scoring behavior.

Two structural policy fixes are included in this checkpoint: internship/apprenticeship is no longer a hard auto-skip, and obvious real-estate sales/consultant titles are handled as structural non-target noise.

## What it does

Every day at **16:17 Europe/Madrid** (DST-safe GitHub schedule):  

1. Downloads the configured source CLIs (LinkedIn, InfoJobs, Tecnoempleo, FreeHire, Joppy, and GetManfred).
2. Searches the configured job queries.
3. Deduplicates and applies the frozen V6.4 recall-safe filter.
4. Fetches full job descriptions for shortlisted candidates.
5. Applies Scoring V1 for ranking only; scores never change V6.4 buckets or create Auto-Skip.
6. Writes a dated archive under `archive/YYYY-MM-DD/`.
7. Updates `\_state/seen\_jobs.json` so previously seen jobs are not reprocessed.
8. Copies the latest standardized files to `latest/`.
9. Commits the archive and state back to this **private** repository.
10. Uploads `latest/` as a GitHub Actions artifact for 14 days.

If a day was missed, the next automatic run switches to a 7-day catch-up.

## Files you will normally use

For daily ChatGPT evaluation:

* `latest/primary\_shortlist\_full.csv`
* or `latest/primary\_shortlist\_full.md`

For weekly pipeline QC:

* `archive/YYYY-MM-DD/primary\_shortlist\_full.csv`
* `archive/YYYY-MM-DD/low\_priority.csv`
* `archive/YYYY-MM-DD/auto\_skipped.csv`
* `archive/YYYY-MM-DD/needs\_detail\_review.csv`
* `archive/YYYY-MM-DD/all\_current.csv`

For evaluation/scoring work:

* `evaluation/gold_dev_labeled.csv`
* `evaluation/gold_set_review.xlsx`
* `evaluation/scoring_v1_spec.json`
* `evaluation/dev_scoring_calibration.csv`
* `scoring_v1.py` — frozen Scoring V1 implementation used by production ranking.
* `evaluation/SCORING_V1_FREEZE.json` — hash manifest protecting the frozen scorer/calibration and clean HOLDOUT.

Production CSV/Markdown outputs now include `score_v1`, `score_band_v1`, component points and penalty reasons. Primary rows are ordered by score, while their V6.4 bucket remains unchanged.

Do not use `evaluation/gold_holdout_clean.csv` for tuning. It is reserved for one-time validation after Scoring V1 implementation is frozen.

## First setup

### Option A — GitHub website

1. Create a new **Private** repository, for example `job-market-monitor`.
2. Copy all files from this bundle into the repository.
3. Commit them to the default branch (`main` is recommended).
4. Open **Actions** and run `Daily Job Search` manually once using mode `auto`.
5. Inspect the run logs and `latest/`.

### Option B — GitHub CLI

From the folder containing these files:

```powershell
git init
git add .
git commit -m "Initial cloud job monitor"
git branch -M main
gh repo create job-market-monitor --private --source . --remote origin --push
```

## Optional: migrate the current local seen-state

To avoid re-surfacing jobs already seen on your laptop, copy:

```text
C:\\Users\\<YOUR\_USER>\\Documents\\job-search-output\\\_state\\seen\_jobs.json
```

into:

```text
\_state\\seen\_jobs.json
```

before the first cloud run.

If you do not migrate it, the first cloud run simply establishes a fresh baseline from the normal daily window.

## Workflow permissions

The workflow needs permission to commit the new archive/state.

Normally `permissions: contents: write` in the workflow is enough. If the final `git push` is rejected:

Repository → **Settings → Actions → General → Workflow permissions**

Select **Read and write permissions**, save, then re-run the workflow.

## Manual run modes

Actions → `Daily Job Search` → `Run workflow`

* `auto`: normal daily behavior; catches up automatically if a day was missed.
* `normal`: force the normal 24/36-hour search window.
* `catchup`: force the 7-day catch-up window.
* `reprocess`: re-check the current window without updating seen-state; outputs go under `reprocess\_...`.

## Important first validation

Cloud runners use datacenter IP addresses. Some job portals may behave differently than they do from a home connection.

After the first manual GitHub Actions run, verify:

* LinkedIn returned results.
* InfoJobs returned results.
* Tecnoempleo returned results.
* Full-detail fetches succeeded.
* `latest/summary.json` contains plausible counts.

If a portal blocks GitHub-hosted runners, keep the rest of this cloud architecture and move only the collector execution to another runner/server.

## Current geography

* Catalunya-wide
* Barcelona and surrounding commuting locations
* Remote Spain
* InfoJobs Spain discovery
* Tecnoempleo across Barcelona, Girona, Tarragona, and Lleida provinces

Spanish language requirements are **not** an automatic blocker.

