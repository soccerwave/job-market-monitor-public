from __future__ import annotations

import unittest

from scoring_v2 import apply_scoring_v2, score_job_v2


class ScoringV2PolicyTests(unittest.TestCase):
    def test_scoring_does_not_change_existing_bucket(self) -> None:
        job = {
            "title": "Market Intelligence Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "Analyze market trends, KPIs, dashboards and business insights using Excel and Power BI.",
            "final_bucket": "REVIEW",
        }
        apply_scoring_v2([job])
        self.assertEqual(job["final_bucket"], "REVIEW")
        self.assertIn("score_v2", job)
        self.assertIn("score_band_v2", job)

    def test_market_intelligence_is_target_adjacent(self) -> None:
        job = {
            "title": "Market Intelligence",
            "location": "Barcelona, Spain",
            "full_detail": "Market analysis, competitive analysis, KPIs, dashboards, reporting and recommendations for business decisions.",
        }
        result = score_job_v2(job)
        self.assertEqual(result.role_family, "Business / Operations Analytics")
        self.assertGreaterEqual(result.role_points, 22)

    def test_madrid_is_not_catalunya_because_jd_mentions_barcelona(self) -> None:
        job = {
            "title": "Data Analyst",
            "location": "Madrid, Community of Madrid, Spain",
            "full_detail": "Hybrid role in Madrid. We partner with teams and clients including FC Barcelona. SQL, Power BI and dashboards.",
        }
        result = score_job_v2(job)
        self.assertNotEqual(result.geography_fit, "Catalunya fit")
        self.assertIn("outside geography", result.penalty_reasons)

    def test_location_conflict_is_manual_review_not_hard_outside(self) -> None:
        job = {
            "title": "Product Analyst",
            "location": "Barcelona, Catalonia, Spain",
            "full_detail": "This role is fully onsite in Lisbon. Product analytics, SQL, Python, A/B testing and dashboards.",
        }
        result = score_job_v2(job)
        self.assertEqual(result.geography_fit, "Location conflict / manual review")
        self.assertNotIn("outside geography", result.penalty_reasons)

    def test_growth_manager_is_not_overpromoted_as_product_analytics(self) -> None:
        job = {
            "title": "Graduate Growth Manager",
            "location": "Barcelona, Spain",
            "full_detail": "Run experiments, analyze growth metrics, build dashboards, segment users and make data-driven recommendations.",
        }
        result = score_job_v2(job)
        self.assertNotEqual(result.role_family, "Product / Growth Analytics")
        self.assertLess(result.role_points, 19)
        self.assertNotIn("people-management role", result.penalty_reasons)

    def test_real_people_manager_is_penalized(self) -> None:
        job = {
            "title": "Business Intelligence Manager",
            "location": "Barcelona, Spain",
            "full_detail": "Manage a team of 7 analysts, own hiring and performance reviews. SQL and Power BI reporting.",
        }
        result = score_job_v2(job)
        self.assertTrue(any(reason in result.penalty_reasons for reason in ["people-management role", "manager seniority"]))

    def test_senior_architect_gets_specialization_penalty(self) -> None:
        job = {
            "title": "Senior Data & Informatica Architect",
            "location": "Barcelona, Spain",
            "full_detail": "Enterprise architecture, data architecture, hybrid cloud, microservices, middleware, architecture standards and Informatica PowerCenter.",
        }
        result = score_job_v2(job)
        self.assertIn("senior architecture specialization", result.penalty_reasons)

    def test_five_year_requirement_remains_serious(self) -> None:
        job = {
            "title": "Senior Insights Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "5+ years of experience in product analytics. SQL, Tableau, experimentation and segmentation.",
        }
        result = score_job_v2(job)
        self.assertIn("5+ years", result.penalty_reasons)
        self.assertEqual(result.experience_points, 3)

    def test_spanish_requirement_is_not_penalized(self) -> None:
        job = {
            "title": "Data Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "Spanish C2/native required. SQL, Power BI and Python.",
        }
        result = score_job_v2(job)
        self.assertNotIn("mandatory non-target language", result.penalty_reasons)



class ScoringV2Week2RegressionTests(unittest.TestCase):
    def test_product_performance_analytics_stays_target_adjacent(self) -> None:
        job = {
            "title": "Product Performance & Analytics Specialist",
            "location": "Barcelona, Spain",
            "full_detail": "Analyze product performance, KPIs, dashboards, cohorts and business recommendations.",
        }
        result = score_job_v2(job)
        self.assertEqual(result.role_family, "Product / Growth Analytics")
        self.assertGreaterEqual(result.role_points, 22)

    def test_business_performance_analyst_stays_target_adjacent(self) -> None:
        job = {
            "title": "Business Performance Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "Analyze KPIs, reporting, forecasts and business performance using SQL and Power BI.",
        }
        result = score_job_v2(job)
        self.assertEqual(result.role_family, "Business / Operations Analytics")
        self.assertGreaterEqual(result.role_points, 22)

    def test_software_engineer_data_analytics_is_not_generic_analytics_boosted(self) -> None:
        job = {
            "title": "Golang Software Engineer - Data Analytics",
            "location": "Spain",
            "full_detail": "Build services for analytics, metrics, dashboards, reporting, data analysis and recommendations.",
        }
        result = score_job_v2(job)
        self.assertNotEqual(result.role_family, "Other Analytics")
        self.assertLess(result.role_points, 19)

    def test_fpa_supply_chain_is_not_generic_analytics_boosted(self) -> None:
        job = {
            "title": "FP&A Supply Chain",
            "location": "Barcelona, Spain",
            "full_detail": "Forecasting, KPIs, reporting, dashboards, planning and business recommendations using Excel and Power BI.",
        }
        result = score_job_v2(job)
        self.assertNotEqual(result.role_family, "Other Analytics")
        self.assertLess(result.role_points, 19)

    def test_ai_engineer_is_not_generic_analytics_boosted(self) -> None:
        job = {
            "title": "Artificial Intelligence Engineer",
            "location": "Barcelona, Spain",
            "full_detail": "Build LLM and RAG solutions, analyze metrics, reporting, dashboards and recommendations using Python and Azure.",
        }
        result = score_job_v2(job)
        self.assertNotEqual(result.role_family, "Other Analytics")
        self.assertLess(result.role_points, 19)

    def test_outside_structured_location_with_barcelona_jd_is_manual_review(self) -> None:
        job = {
            "title": "Business Analyst",
            "location": "Madrid, Community of Madrid, Spain",
            "full_detail": "Hybrid locations: Barcelona, Spain. Analyze campaign performance, KPIs, dashboards and reporting.",
        }
        result = score_job_v2(job)
        self.assertEqual(result.geography_fit, "Location conflict / manual review")
        self.assertNotIn("outside geography", result.penalty_reasons)

    def test_direct_data_analyst_sap_specialization_keeps_reviewability(self) -> None:
        job = {
            "title": "Data Analyst",
            "location": "Barcelona, Spain",
            "full_detail": "Responsibilities: Power BI, SAP BW, SAP BusinessObjects, SQL, DAX, Excel, dashboards, data models and reconciliation for business reporting.",
        }
        result = score_job_v2(job)
        self.assertIn("specialized domain", result.penalty_reasons)
        self.assertEqual(result.penalty, -10)
        self.assertGreaterEqual(result.score, 75)

    def test_reporting_automation_analyst_is_target_adjacent(self) -> None:
        job = {
            "title": "Junior IT Reporting & Automation Analyst",
            "location": "Pozuelo de Alarcón, Community of Madrid, Spain",
            "full_detail": "Location: Madrid or Barcelona, hybrid. Build Excel reports, Power BI dashboards and Power Automate workflows.",
        }
        result = score_job_v2(job)
        self.assertEqual(result.role_family, "Business / Operations Analytics")
        self.assertGreaterEqual(result.role_points, 22)

    def test_analytics_architect_does_not_use_generic_other_analytics_boost(self) -> None:
        job = {
            "title": "AWS BI & Data Analytics Architect",
            "location": "Barcelona, Spain",
            "full_detail": "Architecture standards, analytics, dashboards, KPIs, reporting, data architecture and technology roadmap.",
        }
        result = score_job_v2(job)
        self.assertNotEqual(result.role_family, "Other Analytics")
        self.assertIn("architecture specialization", result.penalty_reasons)

if __name__ == "__main__":
    unittest.main()
