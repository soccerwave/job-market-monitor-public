from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
TZ = ZoneInfo("Europe/Madrid")
OUTPUT_DIR = Path(os.getenv("JOB_SEARCH_OUTPUT_DIR", ROOT / "archive"))
STATE_DIR = Path(os.getenv("JOB_SEARCH_STATE_DIR", ROOT / "_state"))
LAST_SUCCESS = STATE_DIR / "last_successful_run.json"
SEEN_FILE = STATE_DIR / "seen_jobs.json"
LATEST_DIR = Path(os.getenv("JOB_SEARCH_LATEST_DIR", ROOT / "latest"))


def now_madrid() -> datetime:
    return datetime.now(TZ)


def read_last_success() -> date | None:
    if not LAST_SUCCESS.exists():
        return None
    try:
        payload = json.loads(LAST_SUCCESS.read_text(encoding="utf-8"))
        return date.fromisoformat(payload["date"])
    except Exception:
        return None


def restore_file(path: Path, old_bytes: bytes | None) -> None:
    if old_bytes is None:
        if path.exists():
            path.unlink()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(old_bytes)


def count_csv(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def score_band_counts(path: Path, field: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not path.exists():
        return counts
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            band = (row.get(field) or "").strip()
            if band:
                counts[band] += 1
    return counts


def copy_latest(day_dir: Path, prefix: str, target: Path) -> dict[str, int]:
    target.mkdir(parents=True, exist_ok=True)
    names = [
        "primary_shortlist.csv",
        "primary_shortlist_full.csv",
        "primary_shortlist_full.md",
        "low_priority.csv",
        "auto_skipped.csv",
        "needs_detail_review.csv",
        "all_current.csv",
    ]
    for name in names:
        src = day_dir / f"{prefix}{name}"
        if src.exists():
            shutil.copy2(src, target / name)

    primary_v2_bands = score_band_counts(target / "primary_shortlist.csv", "score_band_v2")
    primary_v1_bands = score_band_counts(target / "primary_shortlist.csv", "score_band_v1")
    counts = {
        "primary": count_csv(target / "primary_shortlist.csv"),
        "low_priority": count_csv(target / "low_priority.csv"),
        "auto_skipped": count_csv(target / "auto_skipped.csv"),
        "needs_detail_review": count_csv(target / "needs_detail_review.csv"),
        "all_current": count_csv(target / "all_current.csv"),
        # V2 is the active ranker. Keep V1 counters for the one-week comparison.
        "primary_score_high": primary_v2_bands.get("HIGH", 0),
        "primary_score_review": primary_v2_bands.get("REVIEW", 0),
        "primary_score_low": primary_v2_bands.get("LOW_SCORE", 0),
        "primary_score_very_low": primary_v2_bands.get("VERY_LOW_SCORE", 0),
        "primary_score_v2_high": primary_v2_bands.get("HIGH", 0),
        "primary_score_v2_review": primary_v2_bands.get("REVIEW", 0),
        "primary_score_v2_low": primary_v2_bands.get("LOW_SCORE", 0),
        "primary_score_v2_very_low": primary_v2_bands.get("VERY_LOW_SCORE", 0),
        "primary_score_v1_high": primary_v1_bands.get("HIGH", 0),
        "primary_score_v1_review": primary_v1_bands.get("REVIEW", 0),
        "primary_score_v1_low": primary_v1_bands.get("LOW_SCORE", 0),
        "primary_score_v1_very_low": primary_v1_bands.get("VERY_LOW_SCORE", 0),
    }
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["auto", "normal", "catchup", "reprocess"],
        default="auto",
        help="auto = daily unless a missed day requires catch-up",
    )
    args = parser.parse_args()

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LATEST_DIR.mkdir(parents=True, exist_ok=True)

    today = now_madrid().date()
    last = read_last_success()

    if args.mode == "auto":
        # Auto mode must still perform a real collection even if another manual
        # run already succeeded earlier on the same calendar day. seen_jobs.json
        # handles de-duplication, so same-day runs remain safe while the scheduled
        # 17:17 run can still discover jobs posted since the earlier run.
        if last is not None and last < today - timedelta(days=1):
            actual = "catchup"
        else:
            actual = "normal"
    else:
        actual = args.mode

    cmd = [sys.executable, str(ROOT / "jobs_v6_4_recall_guard.py"), "--show-all"]
    prefix = ""
    if actual == "catchup":
        cmd.append("--catchup")
        prefix = "catchup_"
    elif actual == "reprocess":
        cmd.append("--reprocess-current")
        prefix = "reprocess_"

    print(f"Cloud runner mode: requested={args.mode}, actual={actual}")
    if last:
        print(f"Last successful collection: {last}")
    else:
        print("No previous cloud success marker found.")

    # Transactional safety for state files.
    old_seen = SEEN_FILE.read_bytes() if SEEN_FILE.exists() else None
    old_success = LAST_SUCCESS.read_bytes() if LAST_SUCCESS.exists() else None

    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )

    day_dir = OUTPUT_DIR / today.isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    log_name = "reprocess_run.log" if actual == "reprocess" else "run.log"
    log_path = day_dir / log_name
    log_path.write_text(
        f"$ {' '.join(cmd)}\n\nSTDOUT\n{proc.stdout}\n\nSTDERR\n{proc.stderr}\n",
        encoding="utf-8",
    )

    public_runner = os.getenv("JOB_SEARCH_PUBLIC_RUNNER", "").lower() in {"1", "true", "yes"}
    if public_runner:
        # The public repository's Actions logs are visible to everyone. Collector
        # stdout/stderr can contain job titles, companies and URLs, so keep the
        # complete log only in the private runtime directory for R2 upload.
        print("Collector output captured privately; public log redaction enabled.")
    else:
        print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)

    if proc.returncode != 0:
        restore_file(SEEN_FILE, old_seen)
        restore_file(LAST_SUCCESS, old_success)
        print("Collection failed; state was rolled back.", file=sys.stderr)
        return proc.returncode

    if actual == "reprocess":
        target = LATEST_DIR / "reprocess"
        counts = copy_latest(day_dir, prefix, target)
        summary_target = target / "summary.json"
    else:
        target = LATEST_DIR
        counts = copy_latest(day_dir, prefix, target)
        summary_target = LATEST_DIR / "summary.json"

        LAST_SUCCESS.write_text(
            json.dumps(
                {
                    "date": today.isoformat(),
                    "completed_at": now_madrid().isoformat(),
                    "mode": actual,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    summary = {
        "date": today.isoformat(),
        "mode": actual,
        **counts,
    }
    summary_target.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("\nCloud summary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
