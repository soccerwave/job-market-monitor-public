from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PublicRuntimeSafetyTests(unittest.TestCase):
    def test_latest_dir_can_be_moved_outside_repository(self) -> None:
        env = dict(os.environ)
        env["JOB_SEARCH_LATEST_DIR"] = "/tmp/private-latest"
        code = "import run_cloud_daily; print(run_cloud_daily.LATEST_DIR)"
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(proc.stdout.strip(), "/tmp/private-latest")

    def test_active_workflows_have_no_private_artifact_or_git_commit_path(self) -> None:
        for workflow_path in (ROOT / ".github" / "workflows").glob("*.y*ml"):
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertNotIn("actions/upload-artifact", workflow)
            self.assertNotIn("git add archive", workflow)
            self.assertNotIn("git add latest", workflow)
            self.assertNotIn("git add _state", workflow)
            self.assertNotIn("TELEGRAM_BOT_TOKEN", workflow)
            self.assertNotIn("TELEGRAM_CHAT_ID", workflow)

    def test_production_workflow_uses_private_runtime_and_cloudflare_only(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "daily-job-search.yml").read_text(encoding="utf-8")
        self.assertIn("JOB_SEARCH_PUBLIC_RUNNER", workflow)
        self.assertIn("CF_GATEWAY_URL", workflow)
        self.assertIn("CF_INGEST_TOKEN", workflow)
        self.assertIn("scripts/cloudflare_runtime.py restore-state", workflow)
        self.assertIn("scripts/cloudflare_runtime.py upload-archive", workflow)
        self.assertIn("scripts/cloudflare_runtime.py send-primary", workflow)
        self.assertIn("scripts/cloudflare_runtime.py push-state", workflow)
        self.assertIn("PRODUCTION_ENABLED", workflow)

    def test_public_runner_redacts_collector_output(self) -> None:
        code = (ROOT / "run_cloud_daily.py").read_text(encoding="utf-8")
        self.assertIn("JOB_SEARCH_PUBLIC_RUNNER", code)
        self.assertIn("Collector output captured privately", code)


if __name__ == "__main__":
    unittest.main()
