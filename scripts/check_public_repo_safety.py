from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_DIRS = {"archive", "latest", "_state", "runtime", "output", ".vendor"}
FORBIDDEN_SUFFIXES = {".xlsx", ".xls", ".csv", ".log", ".zip", ".pem", ".key"}
ALLOW_FILES = set()

# High-confidence credential formats only. Variable names such as
# TELEGRAM_BOT_TOKEN are not secrets and are intentionally not flagged.
SECRET_PATTERNS = [
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("OpenAI key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]


def tracked_candidate_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if ".git" in rel.parts or "__pycache__" in rel.parts:
            continue
        files.append(path)
    return files


def main() -> int:
    failures: list[str] = []
    files = tracked_candidate_files()

    for path in files:
        rel = path.relative_to(ROOT)
        if any(part in FORBIDDEN_DIRS for part in rel.parts):
            failures.append(f"forbidden runtime/private directory: {rel}")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES and rel.as_posix() not in ALLOW_FILES:
            failures.append(f"forbidden public file type: {rel}")

        if path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                failures.append(f"possible {label}: {rel}")

    run_cloud = ROOT / "run_cloud_daily.py"
    if run_cloud.exists():
        run_text = run_cloud.read_text(encoding="utf-8")
        if "JOB_SEARCH_PUBLIC_RUNNER" not in run_text:
            failures.append("public runner log-redaction guard missing from run_cloud_daily.py")

    workflow_dir = ROOT / ".github" / "workflows"
    if workflow_dir.exists():
        for wf in workflow_dir.glob("*.y*ml"):
            text = wf.read_text(encoding="utf-8")
            forbidden_workflow_snippets = [
                "git add archive",
                "git add latest",
                "git add _state",
                "actions/upload-artifact",
                "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_CHAT_ID",
            ]
            for snippet in forbidden_workflow_snippets:
                if snippet in text:
                    failures.append(f"unsafe workflow behavior '{snippet}': {wf.relative_to(ROOT)}")

    if failures:
        print("PUBLIC SAFETY CHECK FAILED")
        for item in failures:
            print(f"- {item}")
        return 1

    print(f"PUBLIC SAFETY CHECK PASS: {len(files)} repository files scanned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
