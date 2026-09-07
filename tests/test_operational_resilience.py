from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jobs_v6_4_recall_guard as jobs


class OperationalResilienceTests(unittest.TestCase):
    def test_default_detail_limit_covers_recent_peak(self) -> None:
        self.assertGreaterEqual(jobs.DEFAULT_DETAIL_LIMIT, 120)

    def test_json_parser_tolerates_control_characters(self) -> None:
        proc = SimpleNamespace(
            returncode=0,
            stdout='{"results":[{"description":"line one\nline two"}]}',
            stderr="",
        )
        with patch.object(jobs, "run_command", return_value=proc):
            payload = jobs.run_json_command(Path("."), ["dummy"])
        self.assertEqual(payload["results"][0]["description"], "line one\nline two")

    def test_json_parser_extracts_payload_around_diagnostic_noise(self) -> None:
        proc = SimpleNamespace(
            returncode=0,
            stdout='diagnostic before\n{"results":[{"id":"abc"}]}\ndiagnostic after',
            stderr="",
        )
        with patch.object(jobs, "run_command", return_value=proc):
            payload = jobs.run_json_command(Path("."), ["dummy"])
        self.assertEqual(payload["results"][0]["id"], "abc")

    def test_freehire_retries_smaller_page_after_first_failure(self) -> None:
        successful = {
            "results": [
                {
                    "id": "1",
                    "title": "Data Analyst",
                    "company": "Example",
                    "location": "Spain",
                    "description": "SQL, Power BI, dashboards, requirements and 2 years of experience.",
                }
            ]
        }
        with patch.object(jobs, "SUPPLEMENTARY_QUERIES", ["business intelligence"]), patch.object(
            jobs, "run_json_command", side_effect=[RuntimeError("bad json"), successful]
        ) as mocked:
            rows = jobs.collect_freehire(False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(mocked.call_count, 2)
        retry_args = mocked.call_args_list[1].args[1]
        limit_idx = retry_args.index("--limit") + 1
        self.assertLess(int(retry_args[limit_idx]), jobs.LIMIT_PER_SEARCH)


if __name__ == "__main__":
    unittest.main()
