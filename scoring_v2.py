from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import scoring_v1 as v1

SCORING_VERSION = "SCORING_V2_WEEK2_CANDIDATE"
RETENTION_THRESHOLD = 75

SCORE_BANDS = {
    "HIGH": (85, 100),
    "REVIEW": (75, 84),
    "LOW_SCORE": (55, 74),
    "VERY_LOW_SCORE": (0, 54),
}

# V2 is deliberately small. It fixes observed structural ranking errors while
# leaving V6.4 as the authoritative recall-safe filter.
ANALYTICS_TASK_SIGNALS = [
    r"\bdata analys(?:is|e|es|ing)\b|\banalisis de datos\b",
    r"\binsights?\b|\brecommendations?\b|\brecomendaciones\b",
    r"\bkpis?\b|\bmetrics?\b|\bmetricas\b|\bindicadores\b",
    r"\bdashboards?\b|\breporting\b|\breports?\b|\binformes\b",
    r"\bforecast(?:ing|s)?\b|\bprevision\b|\bplanificacion\b",
    r"\ba/?b test(?:ing)?\b|\bexperimentation\b|\bexperimentos?\b",
    r"\bsegmentation\b|\bsegmentacion\b|\bcohort\b",
    r"\bdata quality\b|\bcalidad del dato\b|\bdata validation\b|\breconciliation\b",
    r"\broot[- ]cause\b|\bcausa raiz\b|\bdiagnostic\b",
    r"\bmarket intelligence\b|\bmarket analysis\b|\banalisis de mercado\b|\bcompetitive analysis\b",
    r"\bpricing\b|\bpromotions?\b|\brevenue analytics\b|\bgrowth analytics\b",
    r"\bproduct analytics\b|\bproduct usage\b|\buser (?:and )?product data\b|\buser behavior\b|\bplayer behavio",
    r"\bgrowth\b|\bmonetization\b|\bexperiment results?\b|\bhigh-performing campaigns?\b",
    r"\bcrm analytics\b|\bcampaign performance\b|\bmarketing analytics\b",
    r"\bbusiness intelligence\b|\bdecision[- ]support\b|\btoma de decisiones\b",
    r"\bstatistics?\b|\bestadistic\b|\bcausal inference\b",
]

ROLE_TITLE_PATTERNS = [
    (
        "Product / Growth Analytics",
        24,
        [
            r"\bproduct analyst\b",
            r"\bproduct analytics\b",
            r"\bgrowth analyst\b",
            r"\bgrowth analytics\b",
            r"\bmarketing data analyst\b",
            r"\bmarketing analyst\b",
            r"\bcrm (?:data )?analyst\b",
            r"\bpricing.*\banalyst\b",
            r"\binsights analyst\b",
            r"\bproduct performance.*\banalytics\b",
            r"\brevenue analytics\b",
            r"\bgrowth manager\b",
        ],
    ),
    (
        "Data Quality / Governance",
        22,
        [r"\bdata steward\b", r"\bdata quality\b", r"\bdata governance\b", r"\bgobierno del dato\b"],
    ),
    (
        "Business / Operations Analytics",
        22,
        [
            r"\bmarket intelligence\b",
            r"\bcapacity planner\b",
            r"\bbusiness information analyst\b",
            r"\bbusiness operations analyst\b",
            r"\boperations analyst\b",
            r"\banalista funcional sql\b",
            r"\bdata consultant\b",
            r"\badvanced analytics scientist\b",
            r"\bbusiness performance analyst\b",
            r"\breport analyst\b",
            r"\bcustomer (?:strategy|experience) analyst\b",
            r"\banalista experiencia cliente\b",
            r"^\s*data analytics\s*$|\bdata analytics (?:analyst|specialist|consultant)\b",
        ],
    ),
]


def norm(value: Any) -> str:
    return v1.normalize(value)


def count(text: str, patterns: list[str]) -> int:
    return v1.count_patterns(text, patterns)


def role_family_and_points(title: str, text: str) -> tuple[str, int]:
    family, points = v1._role_family_and_points(title, text)
    t = norm(title)
    lower = norm(text)
    if family != "Other" or points >= 20:
        return family, points

    for family2, points2, patterns in ROLE_TITLE_PATTERNS:
        if any(re.search(pattern, t, re.I) for pattern in patterns):
            return family2, points2

    task_count = count(lower, ANALYTICS_TASK_SIGNALS)

    # Week-1 observation showed that the generic analytics fallback could
    # over-promote adjacent-but-different roles (software engineering,
    # architecture, FP&A/controlling and generic process roles). Explicit
    # target-adjacent title families above are still rescued at full strength.
    generic_boost_blocked = any(
        re.search(pattern, t, re.I)
        for pattern in [
            r"\bsoftware engineer\b|\bfull[- ]stack\b|\bbackend\b|\bfrontend\b",
            r"\bdeveloper\b|\bdesarrollador(?:/a)?\b",
            r"\barchitect\b|\barquitect[oa]\b",
            r"\bfp&a\b|\bfinancial planning\b|\bcontroller\b|\bcontrolling\b",
            r"\bcloud marketplace\b|\bprocess analyst\b",
        ]
    )
    if not generic_boost_blocked and re.search(
        r"\banalyst\b|\banalista\b|\banalytics\b|\bintelligence\b|\binsights?\b|\bdata specialist\b",
        t,
    ):
        if task_count >= 4:
            return "Other Analytics", 18
        if task_count >= 2:
            return "Other Analytics", 16
    if not generic_boost_blocked and task_count >= 6:
        return "Other Analytics", 14
    return family, points


def _explicit_remote_from_structured(job: dict[str, Any], detail: str) -> bool:
    title = norm(job.get("title"))
    loc = norm(job.get("location"))
    prefix = norm(detail[:1800])
    if re.search(r"\bremote\b|\bremot[oa]\b|\bteletrabajo\b", title):
        return True
    if re.search(
        r"\bremote\s*-?\s*spain\b|\bremote within spain\b|\b100\s*%?\s*(?:remote|remoto|teletrabajo)\b|"
        r"\bwork from anywhere in spain\b|\bfully remote\b",
        prefix,
    ):
        return True
    return loc in {"remote - spain", "remote spain"}


def geography(job: dict[str, Any], detail: str) -> tuple[str, int, bool]:
    location = v1.clean_text(job.get("location"))
    loc = norm(location)
    prefix = norm(detail[:2000])
    structured_catalunya = v1._is_catalunya(location)
    remote = _explicit_remote_from_structured(job, detail)

    outside_places = [
        "madrid", "lisbon", "lisboa", "valencia", "malaga", "a coruna", "bergondo",
        "inca", "mallorca", "pais vasco", "tres cantos", "alcobendas", "pozuel", "alfafar",
        "california",
    ]
    outside_location = any(place in loc for place in outside_places) and not structured_catalunya
    explicit_onsite_outside = any(
        re.search(pattern, prefix)
        for pattern in [
            r"\b(?:fully )?onsite\b.{0,100}\b(?:madrid|lisbon|lisboa|valencia|malaga|california)\b",
            r"\b(?:madrid|lisbon|lisboa|valencia|malaga|california)\b.{0,100}\b(?:fully )?onsite\b",
            r"\b(?:hybrid|hibrid[oa]|presencial)\b.{0,120}\b(?:madrid|lisbon|lisboa|valencia|malaga|tres cantos|alcobendas|pozuel|alfafar|inca|mallorca|pais vasco)\b",
            r"\b(?:madrid|lisbon|lisboa|valencia|malaga|tres cantos|alcobendas|pozuel|alfafar|inca|mallorca|pais vasco)\b.{0,120}\b(?:hybrid|hibrid[oa]|presencial)\b",
        ]
    )

    # Contradictory structured location and JD workplace evidence is not a
    # blocker. Keep the job reviewable and surface the conflict explicitly.
    if structured_catalunya and explicit_onsite_outside:
        return "Location conflict / manual review", 10, False
    if remote:
        return "Remote fit", 15, False
    if structured_catalunya:
        return "Catalunya fit", 15, False
    if not location or loc in {"unknown", ""}:
        return "Unknown", 10, False
    if loc in {"spain", "espana"}:
        return "Spain / modality unclear", 10, False

    outside_country = "california" in loc or bool(re.search(r"\bcalifornia\b|\bunited states\b|\busa\b", prefix))
    if outside_country:
        return "Outside country", 0, True
    if outside_location or explicit_onsite_outside:
        return "Outside target / review", 7, True
    return "Outside target / unclear", 9, False


def has_people_management(title: str, detail: str) -> bool:
    t = norm(title)
    d = norm(detail)
    if re.search(r"\bdirector\b|\bhead\b|\bgerente\b", t):
        return True
    patterns = [
        r"\bmanage(?:s|d|ment|ing)? (?:a |the )?team\b",
        r"\blead(?:ing)? (?:a |the )?team\b",
        r"\bteam leadership\b",
        r"\bpeople management\b",
        r"\bdirect reports?\b",
        r"\bpersonas a cargo\b",
        r"\bliderar(?:as)? (?:un |el )?equipo\b",
        r"\bgestionar(?:as)? (?:un |el )?equipo\b",
        r"\bteam of \d+\b",
    ]
    return any(re.search(pattern, d, re.I) for pattern in patterns)


def architect_penalty(title: str, detail: str, years: float | None) -> tuple[int, str | None]:
    t = norm(title)
    d = norm(detail)
    if not re.search(r"\barchitect\b|\barquitect[oa]\b", t):
        return 0, None
    architecture_count = count(
        d,
        [
            r"\benterprise architecture\b",
            r"\bdata architecture\b",
            r"\barchitectural leadership\b",
            r"\bmicroservices\b",
            r"\bhybrid cloud\b",
            r"\barchitecture standards\b",
            r"\btechnology roadmap\b",
            r"\bmiddleware\b",
            r"\binformatica powercenter\b",
        ],
    )
    senior = bool(re.search(r"\bsenior\b|\blead\b|\bprincipal\b|\benterprise\b", t)) or (
        years is not None and years >= 5
    ) or architecture_count >= 4
    if senior:
        return -15, "senior architecture specialization"
    return -5, "architecture specialization"


def penalties(
    job: dict[str, Any],
    role_family: str,
    role_points: int,
    years: float | None,
    explicit_outside: bool,
    text: str,
) -> tuple[int, list[str]]:
    title = norm(job.get("title"))
    lower = norm(text)
    penalty = 0
    reasons: list[str] = []

    if years is not None:
        if years >= 6:
            penalty -= 10
            reasons.append(f"{years:g}+ years" if years > 6 else "6+ years")
        elif years >= 5:
            penalty -= 8
            reasons.append("5+ years")
        # Four years is already represented by lower experience points. V2
        # avoids charging it a second time.

    if re.search(r"\bdirector\b|\bhead\b|\bgerente\b", title):
        penalty -= 15
        reasons.append("manager/director")
    elif re.search(r"\bmanager\b|\bresponsable\b", title):
        growth_ic = bool(re.search(r"\bgrowth manager\b", title)) and count(lower, ANALYTICS_TASK_SIGNALS) >= 3
        if not growth_ic:
            penalty -= 15
            reasons.append("people-management role" if has_people_management(title, text) else "manager seniority")
    elif re.search(r"\blead\b", title):
        penalty -= 8
        reasons.append("lead")

    heavy_count = count(lower, v1.HEAVY_ENGINEERING_SIGNALS)
    ml_count = count(lower, v1.ML_SPECIALIST_SIGNALS)
    explicit_ml_engineer = bool(re.search(r"\bml engineer\b|\bmachine learning engineer\b", title))
    heavy_specialist = heavy_count >= 4 or (role_family == "Data Scientist" and ml_count >= 3) or explicit_ml_engineer
    production_ml = explicit_ml_engineer or (
        role_family == "Data Scientist"
        and ml_count >= 2
        and count(lower, [r"\bproduction\b|\bproduccion\b", r"\bdeploy|\bdesplieg", r"\bserving\b|\bmodelos? productivos?\b"]) >= 1
    )
    if heavy_specialist:
        penalty -= 16
        reasons.append("heavy specialist stack")
    if production_ml:
        penalty -= 12
        reasons.append("production ML")

    specialized, _ = v1._specialized_domain(lower)
    if re.search(r"\br programmer\b|\bshiny developer\b", title):
        specialized = True
    if re.search(r"\bbiostimulants?\b|\bfertilizers?\b|\bagrochemicals?\b", title):
        specialized = True
    if specialized:
        penalty -= 15
        reasons.append("specialized domain")

    geography_label = geography(job, v1.clean_text(job.get("full_detail")))[0]
    if geography_label == "Outside country":
        penalty -= 15
        reasons.append("outside country")
    elif explicit_outside:
        penalty -= 4
        reasons.append("outside geography")

    if any(re.search(pattern, lower, re.I) for pattern in v1.MANDATORY_NON_TARGET_LANGUAGE_PATTERNS):
        penalty -= 18
        reasons.append("mandatory non-target language")

    architecture_penalty, architecture_reason = architect_penalty(title, text, years)
    if architecture_penalty:
        penalty += architecture_penalty
        reasons.append(architecture_reason or "architecture specialization")

    non_target_core = any(re.search(pattern, title, re.I) for pattern in v1.NON_TARGET_CORE_PATTERNS)
    targetish = role_points >= 19 or role_family in {
        "BI / Reporting",
        "Data Analyst",
        "Data Engineer",
        "Analytics Engineer",
        "Data Scientist",
        "Business Analyst",
        "Product / Growth Analytics",
        "Data Quality / Governance",
        "Business / Operations Analytics",
        "Other Analytics",
    }
    if non_target_core and not targetish:
        penalty -= 18
        reasons.append("non-target core role")

    return penalty, reasons


def seniority_points(title: str, detail: str) -> int:
    t = norm(title)
    if re.search(r"\bdirector\b|\bhead\b|\bgerente\b", t):
        return 0
    if re.search(r"\bmanager\b|\bresponsable\b|\blead\b", t):
        return 1 if has_people_management(title, detail) else 4
    if re.search(r"\bsenior\b|\bsr\b|\bprincipal\b|\bexpert\b", t):
        return 3
    return 5


@dataclass
class ScoreResultV2:
    version: str
    score: int
    band: str
    role_family: str
    geography_fit: str
    years_required: float | None
    skill_count: int
    skill_signals: list[str]
    role_points: int
    skill_points: int
    experience_points: int
    geography_points: int
    domain_points: int
    seniority_points: int
    employment_points: int
    evidence_points: int
    penalty: int
    penalty_reasons: list[str]

    def as_job_fields(self) -> dict[str, str]:
        return {
            "score_v2": str(self.score),
            "score_band_v2": self.band,
            "scoring_version_v2": self.version,
            "score_v2_role_family": self.role_family,
            "score_v2_geography_fit": self.geography_fit,
            "score_v2_years_required": "" if self.years_required is None else f"{self.years_required:g}",
            "score_v2_skill_count": str(self.skill_count),
            "score_v2_skill_signals": " | ".join(self.skill_signals),
            "score_v2_role_points": str(self.role_points),
            "score_v2_skill_points": str(self.skill_points),
            "score_v2_experience_points": str(self.experience_points),
            "score_v2_geography_points": str(self.geography_points),
            "score_v2_domain_points": str(self.domain_points),
            "score_v2_seniority_points": str(self.seniority_points),
            "score_v2_employment_points": str(self.employment_points),
            "score_v2_evidence_points": str(self.evidence_points),
            "score_v2_penalty": str(self.penalty),
            "score_v2_penalty_reasons": "; ".join(self.penalty_reasons),
        }


def score_band(score: int) -> str:
    if score >= 85:
        return "HIGH"
    if score >= 75:
        return "REVIEW"
    if score >= 55:
        return "LOW_SCORE"
    return "VERY_LOW_SCORE"


def score_job_v2(job: dict[str, Any]) -> ScoreResultV2:
    title = v1.clean_text(job.get("title"))
    detail = v1.clean_text(job.get("full_detail"))
    text = f"{title}\n{detail}"
    evidence = v1._has_actionable_detail(job)

    role_family, role_points = role_family_and_points(title, text)
    skills = v1._skill_signals(text, title) if evidence else []
    skill_points = v1._skill_points(len(skills), evidence, role_points)
    years = v1.extract_min_required_years(text) if evidence else None
    experience_points = v1._experience_points(years)
    geography_fit, geography_points, explicit_outside = geography(job, detail)
    specialized, _ = v1._specialized_domain(text)
    base_domain_family = role_family if role_family in {
        "Analytics Engineer", "BI / Reporting", "Data Analyst", "Business Analyst", "Data Engineer", "Data Scientist"
    } else "Other"
    domain_points = v1._domain_points(base_domain_family, role_points, text, specialized)
    if role_family in {"Product / Growth Analytics", "Data Quality / Governance", "Business / Operations Analytics", "Other Analytics"}:
        domain_points = max(domain_points, 10 if not specialized else 3)
    seniority = seniority_points(title, detail)
    employment_points = 2 if any(re.search(pattern, norm(text), re.I) for pattern in v1.INTERNSHIP_PATTERNS) else 5
    evidence_points = 5 if evidence else 4
    penalty, reasons = penalties(job, role_family, role_points, years, explicit_outside, text)

    raw = (
        role_points
        + skill_points
        + experience_points
        + geography_points
        + domain_points
        + seniority
        + employment_points
        + evidence_points
        + penalty
    )
    score = max(0, min(100, int(round(raw))))
    return ScoreResultV2(
        version=SCORING_VERSION,
        score=score,
        band=score_band(score),
        role_family=role_family,
        geography_fit=geography_fit,
        years_required=years,
        skill_count=len(skills),
        skill_signals=skills,
        role_points=role_points,
        skill_points=skill_points,
        experience_points=experience_points,
        geography_points=geography_points,
        domain_points=domain_points,
        seniority_points=seniority,
        employment_points=employment_points,
        evidence_points=evidence_points,
        penalty=penalty,
        penalty_reasons=reasons,
    )


def apply_scoring_v2(jobs: list[dict[str, Any]]) -> None:
    """Attach V2 ranking fields without changing V6.4 buckets."""
    for job in jobs:
        bucket_before = job.get("final_bucket")
        result = score_job_v2(job)
        job.update(result.as_job_fields())
        if job.get("final_bucket") != bucket_before:
            raise AssertionError("Scoring V2 must never change V6.4 final_bucket")
