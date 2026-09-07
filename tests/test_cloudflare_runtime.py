from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cloudflare_runtime as cfr


class CloudflareRuntimeTests(unittest.TestCase):
    def test_restore_state_writes_valid_private_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            target = Path(td)

            def fake_call(method, path, **kwargs):
                if path.endswith("seen_jobs.json"):
                    return 200, b'{"items":{"abc":"2026-09-06"}}'
                return 404, b'{"found":false}'

            with patch.object(cfr, "call_gateway", side_effect=fake_call):
                cfr.restore_state(target)

            self.assertTrue((target / "seen_jobs.json").exists())
            self.assertFalse((target / "last_successful_run.json").exists())
            self.assertEqual(json.loads((target / "seen_jobs.json").read_text())["items"]["abc"], "2026-09-06")

    def test_push_state_skips_reprocess(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / "state"
            latest = root / "latest" / "reprocess"
            state.mkdir(parents=True)
            latest.mkdir(parents=True)
            (latest / "summary.json").write_text('{"date":"2026-09-07","mode":"reprocess"}')
            with patch.object(cfr, "call_gateway") as call:
                cfr.push_state(state, root / "latest")
            call.assert_not_called()

    def test_noop_skips_private_delivery_operations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            latest = root / "latest"
            latest.mkdir()
            (latest / "summary.json").write_text('{"date":"2026-09-07","mode":"noop"}')
            with patch.object(cfr, "call_gateway") as call:
                cfr.upload_archive(root / "archive", latest)
                cfr.send_primary(latest)
                cfr.push_state(root / "state", latest)
            call.assert_not_called()

    def test_send_primary_prefers_full_csv(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            latest = Path(td)
            (latest / "summary.json").write_text('{"date":"2026-09-07","mode":"normal"}')
            (latest / "primary_shortlist_full.csv").write_text("title,company\nAnalyst,Example\n")
            (latest / "primary_shortlist.csv").write_text("title\nOther\n")
            with patch.object(cfr, "call_gateway", return_value=(200, b'{"ok":true,"telegram_message_id":1}')) as call:
                cfr.send_primary(latest)
            kwargs = call.call_args.kwargs
            self.assertEqual(kwargs["extra_headers"]["X-Filename"], "primary_shortlist_full.csv")


if __name__ == "__main__":
    unittest.main()
