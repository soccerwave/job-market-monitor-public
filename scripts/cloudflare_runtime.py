from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from pathlib import Path
from urllib import error, request

STATE_NAMES = ("seen_jobs.json", "last_successful_run.json")


def gateway_config() -> tuple[str, str]:
    base = (os.getenv("CF_GATEWAY_URL") or "").strip().rstrip("/")
    token = os.getenv("CF_INGEST_TOKEN") or ""
    if not base.startswith("https://"):
        raise RuntimeError("CF_GATEWAY_URL must be an https:// URL")
    if not token:
        raise RuntimeError("CF_INGEST_TOKEN is missing")
    return base, token


def call_gateway(
    method: str,
    path: str,
    *,
    body: bytes | None = None,
    content_type: str | None = None,
    extra_headers: dict[str, str] | None = None,
    allow_404: bool = False,
) -> tuple[int, bytes]:
    base, token = gateway_config()
    headers = {"Authorization": f"Bearer {token}"}
    if content_type:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(base + path, data=body, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except error.HTTPError as exc:
        payload = exc.read()
        if allow_404 and exc.code == 404:
            return exc.code, payload
        safe_detail = payload.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"gateway request failed: HTTP {exc.code}: {safe_detail}") from exc


def restore_state(state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    for name in STATE_NAMES:
        status, payload = call_gateway("GET", f"/v1/state/{name}", allow_404=True)
        target = state_dir / name
        if status == 404:
            if target.exists():
                target.unlink()
            print(f"Private state not present yet: {name}")
            continue
        # Validate JSON before allowing it to influence the collector.
        try:
            json.loads(payload.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"private state is not valid JSON: {name}") from exc
        target.write_bytes(payload)
        print(f"Restored private state: {name}")


def push_state(state_dir: Path, latest_dir: Path) -> None:
    summary = read_summary(latest_dir)
    if summary.get("mode") in {"reprocess", "noop"}:
        print(f"{summary.get('mode')} run: private state upload intentionally skipped")
        return
    for name in STATE_NAMES:
        path = state_dir / name
        if not path.exists():
            raise RuntimeError(f"expected state file missing after successful run: {name}")
        payload = path.read_bytes()
        json.loads(payload.decode("utf-8"))
        call_gateway("PUT", f"/v1/state/{name}", body=payload, content_type="application/json")
        print(f"Persisted private state: {name}")


def summary_path(latest_dir: Path) -> Path:
    reprocess = latest_dir / "reprocess" / "summary.json"
    normal = latest_dir / "summary.json"
    if reprocess.exists():
        return reprocess
    if normal.exists():
        return normal
    raise RuntimeError("run summary not found")


def read_summary(latest_dir: Path) -> dict:
    path = summary_path(latest_dir)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("date"):
        raise RuntimeError("invalid run summary")
    return payload


def upload_archive(output_dir: Path, latest_dir: Path) -> None:
    summary = read_summary(latest_dir)
    if summary.get("mode") == "noop":
        print("No-op run: private archive upload skipped")
        return
    day = str(summary["date"])
    day_dir = output_dir / day
    if not day_dir.exists():
        raise RuntimeError(f"dated output directory missing: {day_dir}")

    files = sorted(path for path in day_dir.iterdir() if path.is_file())
    if not files:
        raise RuntimeError("no private run outputs found to archive")

    for path in files:
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        call_gateway(
            "PUT",
            f"/v1/archive/{day}/{path.name}",
            body=path.read_bytes(),
            content_type=ctype,
        )
        print(f"Archived privately: {path.name}")

    spath = summary_path(latest_dir)
    summary_name = "reprocess_summary.json" if summary.get("mode") == "reprocess" else "summary.json"
    call_gateway(
        "PUT",
        f"/v1/archive/{day}/{summary_name}",
        body=spath.read_bytes(),
        content_type="application/json",
    )
    print(f"Archived privately: {summary_name}")


def send_primary(latest_dir: Path) -> None:
    summary = read_summary(latest_dir)
    if summary.get("mode") == "noop":
        print("No-op run: Telegram delivery skipped")
        return
    base = latest_dir / "reprocess" if summary.get("mode") == "reprocess" else latest_dir
    candidates = [
        base / "primary_shortlist_full.csv",
        base / "primary_shortlist.csv",
        base / "primary_shortlist_full.md",
    ]
    selected = next((path for path in candidates if path.exists()), None)
    if selected is None:
        raise RuntimeError("no primary result document found for Telegram delivery")

    ctype = mimetypes.guess_type(selected.name)[0] or "application/octet-stream"
    caption = f"Job Market Monitor | {summary.get('date')} | {summary.get('mode')}"
    status, payload = call_gateway(
        "POST",
        "/v1/telegram/document",
        body=selected.read_bytes(),
        content_type=ctype,
        extra_headers={"X-Filename": selected.name, "X-Caption": caption},
    )
    response = json.loads(payload.decode("utf-8")) if payload else {}
    if status != 200 or not response.get("ok"):
        raise RuntimeError("Telegram gateway did not confirm delivery")
    print(f"Delivered privately to Telegram: {selected.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Private Cloudflare runtime bridge for public GitHub Actions")
    sub = parser.add_subparsers(dest="command", required=True)

    restore = sub.add_parser("restore-state")
    restore.add_argument("--state-dir", required=True, type=Path)

    persist = sub.add_parser("push-state")
    persist.add_argument("--state-dir", required=True, type=Path)
    persist.add_argument("--latest-dir", required=True, type=Path)

    archive = sub.add_parser("upload-archive")
    archive.add_argument("--output-dir", required=True, type=Path)
    archive.add_argument("--latest-dir", required=True, type=Path)

    telegram = sub.add_parser("send-primary")
    telegram.add_argument("--latest-dir", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "restore-state":
        restore_state(args.state_dir)
    elif args.command == "push-state":
        push_state(args.state_dir, args.latest_dir)
    elif args.command == "upload-archive":
        upload_archive(args.output_dir, args.latest_dir)
    elif args.command == "send-primary":
        send_primary(args.latest_dir)
    else:
        raise AssertionError(args.command)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Private runtime bridge failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
