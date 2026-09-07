from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scoring_v2 import SCORING_VERSION, score_job_v2  # noqa: E402

FIXTURE = HERE / "synthetic_policy_cases.json"


def main() -> int:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if payload.get("scoring_version") != SCORING_VERSION:
        print(f"Synthetic fixture version mismatch: {payload.get('scoring_version')} != {SCORING_VERSION}")
        return 1

    cases = payload.get("cases", [])
    failures: list[str] = []
    for case in cases:
        result = score_job_v2(
            {
                "title": case["title"],
                "location": case["location"],
                "full_detail": case["full_detail"],
            }
        )
        expected = case["expected"]
        checks = {
            "score": result.score,
            "band": result.band,
            "role_family": result.role_family,
            "geography_fit": result.geography_fit,
            "years_required": result.years_required,
            "penalty_reasons": result.penalty_reasons,
        }
        for field, expected_value in expected.items():
            if checks[field] != expected_value:
                failures.append(
                    f"{case['id']} {field}: expected={expected_value!r} actual={checks[field]!r}"
                )

    if failures:
        print("Public synthetic regression FAILED")
        print("\n".join(failures))
        return 1

    print(f"Public synthetic regression PASS: {len(cases)}/{len(cases)} cases")
    print(f"Scoring version: {SCORING_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
