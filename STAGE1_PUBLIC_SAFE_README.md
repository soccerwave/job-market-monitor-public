# Job Market Monitor — Public-safe Stage 1 snapshot

This is a clean-room source snapshot prepared for migration to a new public repository.

## Included
- Core Python source files
- Non-sensitive unit/regression tests
- Git text configuration
- Original README retained as `README_ORIGINAL.md` for later rewriting

## Deliberately excluded
- `.git/` and all previous Git history
- `.github/workflows/`
- `archive/`
- `latest/`
- `_state/`
- all `evaluation/` calibration datasets and reports
- all Excel/CSV/log runtime or historical data
- patch notes / migration artifacts

## Important
Do **not** treat this Stage 1 snapshot as the final production repository yet.
The next migration stages must add:
1. public-safe synthetic evaluation/freeze checks;
2. a redesigned workflow that never commits private runtime data;
3. Cloudflare/R2 state and result transport;
4. Telegram delivery through Cloudflare rather than GitHub-held Telegram credentials.
