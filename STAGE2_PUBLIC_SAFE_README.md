# Stage 2 — Public-safe synthetic evaluation

This snapshot extends Stage 1 with a public-safe evaluation layer.

## Added in Stage 2

- `evaluation/synthetic_policy_cases.json` — 24 completely synthetic regression cases.
- `evaluation/validate_public_synthetic.py` — exact policy/scoring regression validator.
- `evaluation/PUBLIC_FREEZE.json` — public-safe freeze manifest.
- `evaluation/check_public_freeze.py` — line-ending-independent freeze checker.
- `evaluation/README.md` — explains the public evaluation boundary.

## Explicitly NOT included

- Production job listings or URLs
- `archive/`, `latest/`, `_state/`
- Historical logs
- Excel workbooks
- The original 131-job calibration datasets
- Human Apply/Skip labels or other private evaluation data
- Git history
- GitHub Actions workflow (will be rebuilt in a later stage)

## Verification

```bash
python -m unittest discover -s tests -v
python evaluation/validate_public_synthetic.py
python evaluation/check_public_freeze.py
```

Expected:

- 37 unit tests: OK
- Synthetic regression: 24/24 PASS
- Public freeze: PASS

Do not publish yet. The runtime/workflow and Cloudflare private-data path still need to be rebuilt before this becomes the final public repository.
