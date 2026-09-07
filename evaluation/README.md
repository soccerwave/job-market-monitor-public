# Public-safe evaluation

This directory intentionally contains **synthetic regression evidence only**.

It does not contain production job listings, historical archives, user decisions, private labels, URLs, state files, Excel workbooks, or the original 131-job calibration data.

## Checks

```bash
python evaluation/validate_public_synthetic.py
python evaluation/check_public_freeze.py
```

`synthetic_policy_cases.json` covers critical policy behavior such as target Data/BI roles, product/growth analytics, governance, internships, experience penalties, people management, non-target languages, heavy engineering/ML, geography conflicts, and Week-2 overboost regressions.

The freeze checker uses canonical text hashing, normalizing CRLF/LF before hashing, so checkout line endings cannot create false freeze failures.
