from __future__ import annotations

import unittest

from jobs_v6_4_recall_guard import (
    canonical_url_identity,
    classify_title,
    deduplicate,
    evaluate_full_jd,
    is_explicit_remote_spain,
    seen_keys,
)


class RecallGuardTitleTests(unittest.TestCase):
    def test_data_scientist_is_reviewable(self) -> None:
        self.assertEqual(classify_title("Data Scientist")[0], "REVIEW")

    def test_data_product_owner_is_reviewable(self) -> None:
        self.assertEqual(classify_title("Senior Data Product Owner")[0], "REVIEW")

    def test_intern_data_analyst_is_not_auto_skip(self) -> None:
        self.assertNotEqual(classify_title("Data Analyst Internship")[0], "AUTO_SKIP_TITLE")

    def test_apprentice_data_scientist_is_not_auto_skip(self) -> None:
        self.assertNotEqual(classify_title("Apprentice Data Scientist Finance")[0], "AUTO_SKIP_TITLE")

    def test_internship_jd_is_not_hard_blocker(self) -> None:
        job = {
            "title": "Data Analyst Internship",
            "full_detail": (
                "This is an internship position. You will analyze business data, build dashboards, "
                "write SQL queries, use Power BI, validate data quality, and support KPI reporting. "
                "Candidates should have analytical skills and interest in data analysis."
            ),
            "location": "Barcelona, Catalonia, Spain",
        }
        bucket, _fit, blockers, _low = evaluate_full_jd(job)
        self.assertNotEqual(bucket, "AUTO_SKIP_JD")
        self.assertFalse(any("Internship" in x for x in blockers))

    def test_spanish_real_estate_consultant_is_auto_skip(self) -> None:
        self.assertEqual(classify_title("Consultor Inmobiliario")[0], "AUTO_SKIP_TITLE")
        self.assertEqual(classify_title("Asesor inmobiliario")[0], "AUTO_SKIP_TITLE")

    def test_english_real_estate_consultant_is_auto_skip(self) -> None:
        self.assertEqual(classify_title("Real Estate Consultant")[0], "AUTO_SKIP_TITLE")

    def test_software_engineer_with_data_scope_is_reviewable(self) -> None:
        bucket, _reason = classify_title("Software Engineer - Data")
        self.assertEqual(bucket, "REVIEW")

    def test_generic_software_engineer_remains_auto_skip(self) -> None:
        bucket, _reason = classify_title("Software Engineer")
        self.assertEqual(bucket, "AUTO_SKIP_TITLE")

    def test_analytics_engineer_full_stack_is_reviewable(self) -> None:
        bucket, reason = classify_title("Analytics Engineer II, Full Stack (Revenue Analytics)")
        self.assertEqual(bucket, "REVIEW")
        self.assertIn("Analytics Engineer", reason)

    def test_generic_full_stack_developer_remains_auto_skip(self) -> None:
        bucket, _reason = classify_title("Full Stack Developer")
        self.assertEqual(bucket, "AUTO_SKIP_TITLE")

    def test_data_analyst_trainer_is_auto_skip(self) -> None:
        bucket, reason = classify_title("Formador/a Data Analyst")
        self.assertEqual(bucket, "AUTO_SKIP_TITLE")
        self.assertIn("Teaching", reason)

    def test_plain_data_analyst_remains_high(self) -> None:
        bucket, _reason = classify_title("Data Analyst")
        self.assertEqual(bucket, "HIGH")

    def test_data_architect_with_five_years_is_low_not_auto_skip(self) -> None:
        job = {
            "title": "Data Architect",
            "full_detail": (
                "We require 5+ years of experience in data architecture and database design. "
                "Strong SQL and NoSQL skills, cloud platforms, data governance, data quality, "
                "enterprise data models and end-to-end data solutions are required."
            ),
            "location": "Barcelona, Catalonia, Spain",
        }
        bucket, _fit, blockers, low = evaluate_full_jd(job)
        self.assertEqual(bucket, "LOW_PRIORITY")
        self.assertFalse(any("Data architecture role" in x for x in blockers))
        self.assertTrue(any("Data Architect role requiring at least 5 years" in x for x in low))

    def test_junior_data_architect_remains_reviewable(self) -> None:
        job = {
            "title": "Data Architect",
            "full_detail": (
                "You will design data models, work with SQL databases, support data governance "
                "and data quality, and collaborate with analysts and data engineers. "
                "One year of relevant experience is preferred."
            ),
            "location": "Barcelona, Catalonia, Spain",
        }
        bucket, _fit, blockers, _low = evaluate_full_jd(job)
        self.assertEqual(bucket, "REVIEW")
        self.assertFalse(blockers)

    def test_work_from_anywhere_in_spain_is_remote_spain(self) -> None:
        self.assertTrue(is_explicit_remote_spain("Work from Anywhere in Spain"))

    def test_same_canonical_url_deduplicates_title_company_variations(self) -> None:
        jobs = [
            {
                "source": "LinkedIn",
                "id": "a",
                "url": "https://example.com/jobs/123?utm_source=linkedin",
                "company": "Opera",
                "title": "Data Analyst",
                "location": "Barcelona",
                "query_found_by": "data analyst",
            },
            {
                "source": "LinkedIn",
                "id": "b",
                "url": "https://example.com/jobs/123?utm_medium=jobs",
                "company": "Opera Software",
                "title": "Data Analyst - BI",
                "location": "Barcelona",
                "query_found_by": "business intelligence",
            },
        ]
        unique, duplicates = deduplicate(jobs)
        self.assertEqual(len(unique), 1)
        self.assertEqual(duplicates, 1)

    def test_canonical_url_strips_tracking_and_fragment(self) -> None:
        raw = "https://Example.com/jobs/123/?utm_source=x&foo=1#section"
        self.assertEqual(canonical_url_identity(raw), "https://example.com/jobs/123?foo=1")

    def test_seen_keys_include_stable_url_identity(self) -> None:
        job = {
            "source": "LinkedIn",
            "id": "new-id",
            "url": "https://example.com/jobs/123?utm_campaign=test",
            "company": "Changed Company",
            "title": "Changed Title",
            "location": "Barcelona",
        }
        keys = seen_keys(job)
        self.assertIn("url::https://example.com/jobs/123", keys)
        self.assertEqual(len(keys), 2)


if __name__ == "__main__":
    unittest.main()
