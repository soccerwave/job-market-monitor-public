from __future__ import annotations

import argparse
import io
import json
import mimetypes
import time
import zipfile
from datetime import timedelta
from pathlib import Path

from scripts.cloudflare_runtime import call_gateway
from run_cloud_daily import now_madrid

# Production outputs used for the weekly scoring / recall review.
# Reprocess outputs are intentionally excluded so the weekly batch reflects
# the actual production stream only.
ARCHIVE_NAMES = (
    "summary.json",
    "run.log",
    "primary_shortlist.csv",
    "primary_shortlist_full.csv",
    "primary_shortlist_full.md",
    "low_priority.csv",
    "auto_skipped.csv",
    "needs_detail_review.csv",
    "all_current.csv",
)

PREFIXES = ("", "catchup_")


def fetch_archive_object(day: str, name: str) -> bytes | None:
    status, payload = call_gateway(
        "GET",
        f"/v1/archive/{day}/{name}",
        allow_404=True,
    )
    if status == 404:
        return None
    return payload


def wait_for_today(day: str, wait_minutes: int) -> None:
    if wait_minutes <= 0:
        return
    deadline = time.monotonic() + wait_minutes * 60
    while True:
        if fetch_archive_object(day, "summary.json") is not None:
            return
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"today's production archive is still missing after {wait_minutes} minutes: {day}"
            )
        print(f"Waiting for daily production archive to finish: {day}")
        time.sleep(60)


def build_weekly_zip(days: int = 7, wait_for_today_minutes: int = 0) -> tuple[str, bytes, dict]:
    if days < 1:
        raise ValueError("days must be >= 1")

    end = now_madrid().date()
    start = end - timedelta(days=days - 1)
    wait_for_today(end.isoformat(), wait_for_today_minutes)

    buffer = io.BytesIO()
    manifest: dict[str, object] = {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days_requested": days,
        "days": {},
    }

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for offset in range(days):
            day = (start + timedelta(days=offset)).isoformat()
            found: list[str] = []
            missing: list[str] = []

            # summary.json and run.log are never prefixed. The collector outputs
            # use catchup_ only on catch-up production days.
            for name in ("summary.json", "run.log"):
                payload = fetch_archive_object(day, name)
                if payload is None:
                    missing.append(name)
                    continue
                zf.writestr(f"{day}/{name}", payload)
                found.append(name)

            for base_name in ARCHIVE_NAMES[2:]:
                selected_name = None
                selected_payload = None
                for prefix in PREFIXES:
                    candidate = f"{prefix}{base_name}"
                    payload = fetch_archive_object(day, candidate)
                    if payload is not None:
                        selected_name = candidate
                        selected_payload = payload
                        break
                if selected_payload is None:
                    missing.append(base_name)
                    continue
                zf.writestr(f"{day}/{selected_name}", selected_payload)
                found.append(selected_name)

            manifest["days"][day] = {
                "found": found,
                "missing": missing,
            }

        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        zf.writestr("manifest.json", manifest_bytes)

    filename = f"weekly_review_{start.isoformat()}_to_{end.isoformat()}.zip"
    return filename, buffer.getvalue(), manifest


def send_weekly_zip(filename: str, payload: bytes, manifest: dict) -> None:
    caption = (
        f"Weekly Job Market Review | {manifest['from']} to {manifest['to']} | "
        f"{manifest['days_requested']} days"
    )
    status, response_payload = call_gateway(
        "POST",
        "/v1/telegram/document",
        body=payload,
        content_type=mimetypes.guess_type(filename)[0] or "application/zip",
        extra_headers={"X-Filename": filename, "X-Caption": caption},
    )
    response = json.loads(response_payload.decode("utf-8")) if response_payload else {}
    if status != 200 or not response.get("ok"):
        raise RuntimeError("Telegram gateway did not confirm weekly ZIP delivery")
    print(f"Delivered weekly review ZIP to Telegram: {filename}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and privately deliver the weekly review archive")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--wait-for-today-minutes", type=int, default=0)
    args = parser.parse_args()

    filename, payload, manifest = build_weekly_zip(
        days=args.days,
        wait_for_today_minutes=args.wait_for_today_minutes,
    )
    send_weekly_zip(filename, payload, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
