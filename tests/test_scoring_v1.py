from __future__ import annotations

import unittest

from scoring_v1 import apply_scoring_v1, score_job_v1


class ScoringV1PolicyTests(unittest.TestCase):
    def test_scoring_does_not_change_existing_bucket(self) -> None:
        job = {
            "title": "Data Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "SQL Power BI Python. Two years of relevant experience.",
            "final_bucket": "REVIEW",
        }
        apply_scoring_v1([job])
        self.assertEqual(job["final_bucket"], "REVIEW")
        self.assertIn("score_v1", job)
        self.assertIn("score_band_v1", job)

    def test_three_to_five_year_range_uses_minimum_three(self) -> None:
        job = {
            "title": "Analytics Engineer",
            "location": "Barcelona, Spain",
            "full_detail": "We are looking for approximately 3–5 years of experience with SQL and dbt.",
        }
        result = score_job_v1(job)
        self.assertEqual(result.years_required, 3)
        self.assertEqual(result.experience_points, 11)
        self.assertNotIn("5+ years", result.penalty_reasons)

    def test_spanish_requirement_is_not_penalized(self) -> None:
        job = {
            "title": "Data Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "SQL, Power BI and Python. Spanish C2/native required.",
        }
        result = score_job_v1(job)
        self.assertNotIn("mandatory non-target language", result.penalty_reasons)

    def test_non_target_language_can_be_penalized(self) -> None:
        job = {
            "title": "Data Annotation Specialist",
            "location": "Barcelona, Spain",
            "full_detail": "Python and data QA. Working fluency in Italian is required.",
        }
        result = score_job_v1(job)
        self.assertIn("mandatory non-target language", result.penalty_reasons)

    def test_desirable_or_plus_language_is_not_penalized(self) -> None:
        job = {
            "title": "Senior Product Owner - Analytics",
            "location": "Barcelona, Spain",
            "full_detail": (
                "Fluent English in a business environment; German and Spanish is a plus. "
                "Portuguese is desirable. SQL and analytics experience."
            ),
        }
        result = score_job_v1(job)
        self.assertNotIn("mandatory non-target language", result.penalty_reasons)

    def test_apprenticeship_is_moderate_not_skip_logic(self) -> None:
        job = {
            "title": "Apprentice Data Scientist Finance",
            "location": "Barcelona, Spain",
            "full_detail": "Finance analytics using Python, SQL and dashboards.",
            "final_bucket": "REVIEW",
        }
        result = score_job_v1(job)
        self.assertEqual(result.employment_points, 2)
        self.assertGreaterEqual(result.score, 55)
        self.assertNotIn("non-target core role", result.penalty_reasons)

    def test_five_years_is_serious_penalty(self) -> None:
        job = {
            "title": "Senior Data Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "5+ years of relevant experience. SQL, Python, data quality and dashboards.",
        }
        result = score_job_v1(job)
        self.assertEqual(result.experience_points, 3)
        self.assertIn("5+ years", result.penalty_reasons)
        self.assertEqual(result.penalty, -8)


if __name__ == "__main__":
    unittest.main()
