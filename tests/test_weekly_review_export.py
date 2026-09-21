from __future__ import annotations

import io
import json
import unittest
import zipfile
from datetime import date, datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import weekly_review_export as weekly


class WeeklyReviewExportTests(unittest.TestCase):
    def test_build_weekly_zip_uses_production_archive_and_excludes_reprocess(self) -> None:
        objects = {
            "/v1/archive/2026-09-07/summary.json": b'{"date":"2026-09-07","mode":"normal"}',
            "/v1/archive/2026-09-07/primary_shortlist_full.csv": b"title\nAnalyst\n",
            "/v1/archive/2026-09-08/summary.json": b'{"date":"2026-09-08","mode":"catchup"}',
            "/v1/archive/2026-09-08/catchup_primary_shortlist_full.csv": b"title\nBI Analyst\n",
            "/v1/archive/2026-09-08/reprocess_primary_shortlist_full.csv": b"title\nSHOULD_NOT_APPEAR\n",
        }

        def fake_call(method, path, **kwargs):
            payload = objects.get(path)
            if payload is None:
                return 404, b'{"found":false}'
            return 200, payload

        madrid = ZoneInfo("Europe/Madrid")
        with (
            patch.object(weekly, "call_gateway", side_effect=fake_call),
            patch.object(weekly, "now_madrid", return_value=datetime(2026, 9, 8, 18, 0, tzinfo=madrid)),
        ):
            filename, payload, manifest = weekly.build_weekly_zip(days=2)

        self.assertEqual(filename, "weekly_review_2026-09-07_to_2026-09-08.zip")
        self.assertEqual(manifest["from"], "2026-09-07")
        self.assertEqual(manifest["to"], "2026-09-08")

        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("2026-09-07/primary_shortlist_full.csv", names)
            self.assertIn("2026-09-08/catchup_primary_shortlist_full.csv", names)
            self.assertNotIn("2026-09-08/reprocess_primary_shortlist_full.csv", names)
            manifest_payload = json.loads(zf.read("manifest.json"))
            self.assertEqual(manifest_payload["days_requested"], 2)

    def test_manual_run_after_midnight_uses_latest_completed_archive(self) -> None:
        objects = {
            "/v1/archive/2026-09-20/summary.json": b'{"date":"2026-09-20","mode":"normal"}',
            "/v1/archive/2026-09-20/primary_shortlist_full.csv": b"title\nAnalyst\n",
        }

        def fake_call(method, path, **kwargs):
            payload = objects.get(path)
            if payload is None:
                return 404, b'{"found":false}'
            return 200, payload

        madrid = ZoneInfo("Europe/Madrid")
        with (
            patch.object(weekly, "call_gateway", side_effect=fake_call),
            patch.object(weekly, "now_madrid", return_value=datetime(2026, 9, 21, 2, 13, tzinfo=madrid)),
            patch.object(weekly.time, "sleep") as sleep,
        ):
            filename, _, manifest = weekly.build_weekly_zip(days=7)

        self.assertEqual(filename, "weekly_review_2026-09-14_to_2026-09-20.zip")
        self.assertEqual(manifest["to"], "2026-09-20")
        sleep.assert_not_called()

    def test_explicit_end_date_is_required_after_wait(self) -> None:
        objects = {
            "/v1/archive/2026-09-20/summary.json": b'{"date":"2026-09-20","mode":"normal"}',
        }

        def fake_call(method, path, **kwargs):
            payload = objects.get(path)
            if payload is None:
                return 404, b'{"found":false}'
            return 200, payload

        with (
            patch.object(weekly, "call_gateway", side_effect=fake_call),
            patch.object(weekly, "wait_for_archive") as wait,
        ):
            filename, _, manifest = weekly.build_weekly_zip(
                days=7,
                wait_for_end_date_minutes=60,
                end_date=date(2026, 9, 20),
            )

        wait.assert_called_once_with("2026-09-20", 60)
        self.assertEqual(filename, "weekly_review_2026-09-14_to_2026-09-20.zip")
        self.assertEqual(manifest["to"], "2026-09-20")

    def test_send_weekly_zip_uses_private_telegram_gateway(self) -> None:
        manifest = {"from": "2026-09-07", "to": "2026-09-13", "days_requested": 7}
        with patch.object(
            weekly,
            "call_gateway",
            return_value=(200, b'{"ok":true,"telegram_message_id":42}'),
        ) as call:
            weekly.send_weekly_zip("weekly_review.zip", b"zip-bytes", manifest)

        args = call.call_args
        self.assertEqual(args.args[0], "POST")
        self.assertEqual(args.args[1], "/v1/telegram/document")
        self.assertEqual(args.kwargs["extra_headers"]["X-Filename"], "weekly_review.zip")


if __name__ == "__main__":
    unittest.main()
