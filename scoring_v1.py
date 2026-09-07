from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Any

SCORING_VERSION = "SCORING_V1_CALIBRATED"
RETENTION_THRESHOLD = 75

SCORE_BANDS = {
    "HIGH": (85, 100),
    "REVIEW": (75, 84),
    "LOW_SCORE": (55, 74),
    "VERY_LOW_SCORE": (0, 54),
}


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )
    return re.sub(r"[^a-z0-9+#./ -]+", " ", text)


def count_patterns(text: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, text, flags=re.I))


def extract_min_required_years(text: str) -> float | None:
    text = clean_text(text).lower()
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    # A range such as "3-5 years" means the minimum qualifying threshold is 3,
    # not 5. Capture ranges first so the upper bound is not later mistaken for
    # a standalone requirement.
    range_patterns = [
        r"\b(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s+years?\b",
        r"\b(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s+anos\b",
    ]
    vals: list[float] = []
    occupied: list[tuple[int, int]] = []
    for pattern in range_patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            val = float(match.group(1))
            if 0 < val <= 15:
                vals.append(val)
                occupied.append(match.span())

    patterns = [
        r"\bat least\s+(\d+(?:\.\d+)?)\+?\s+years?\b",
        r"\bminimum(?: of)?\s+(\d+(?:\.\d+)?)\+?\s+years?\b",
        r"\b(\d+(?:\.\d+)?)\+?\s+years?\s+of\s+(?:relevant\s+|professional\s+|work\s+|hands[- ]on\s+)?experience\b",
        r"\b(\d+(?:\.\d+)?)\+?\s+years?\s+of\s+.{0,80}?\bexperience\b",
        r"\b(\d+(?:\.\d+)?)\+?\s+years?\s+(?:relevant\s+|professional\s+)?experience\b",
        r"\b(\d+(?:\.\d+)?)\+?\s+years?\s+as\s+(?:an?\s+)?[a-z]",
        r"\bal menos\s+(\d+(?:\.\d+)?)\+?\s+anos\b",
        r"\bminim[oa]\s+(?:de\s+)?(\d+(?:\.\d+)?)\+?\s+anos\b",
        r"\bexperiencia previa.{0,120}?minim[oa]\s+(?:de\s+)?(\d+(?:\.\d+)?)\+?\s+anos\b",
        r"\b(\d+(?:\.\d+)?)\+?\s+anos\s+de\s+experiencia\b",
        r"\bcon\s+(\d+(?:\.\d+)?)\+?\s+anos\s+de\s+experiencia\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.I):
            if any(match.start() >= a and match.start() < b for a, b in occupied):
                continue
            try:
                val = float(match.group(1))
            except Exception:
                continue
            if 0 < val <= 15:
                vals.append(val)
    return max(vals) if vals else None


SKILL_SIGNALS = {
    "SQL": r"\bsql\b",
    "Python": r"\bpython\b",
    "Power BI": r"\bpower\s*bi\b",
    "Tableau": r"\btableau\b",
    "Looker": r"\blooker(?:\s+studio)?\b",
    "BigQuery": r"\bbig\s*query\b|\bbigquery\b",
    "dbt": r"\bdbt\b",
    "Snowflake": r"\bsnowflake\b",
    "Excel": r"\bexcel\b",
    "Fabric": r"\bmicrosoft\s+fabric\b|\bfabric\b",
    "DAX": r"\bdax\b",
    "Power Query": r"\bpower\s+query\b",
    "Data Quality": r"\bdata quality\b|\bdata validation\b|\breconciliation\b|\bdeduplicat(?:e|ion)\b|\bdata governance\b",
    "Airflow": r"\bairflow\b",
    "Cloud": r"\baws\b|\bazure\b|\bgcp\b|\bgoogle cloud\b|\bcloud platform\b",
}

PRODUCT_DS_SIGNALS = [
    r"\bproduct analytics\b", r"\bexperimentation\b", r"\ba/?b test", r"\bfunnel",
    r"\bcommerce analytics\b", r"\bmarketing analytics\b", r"\bpricing\b",
    r"\bpromotion", r"\bcustomer analytics\b", r"\bbusiness insights?\b",
    r"\bfinance analytics\b", r"\bmetrics\b",
]

ML_SPECIALIST_SIGNALS = [
    r"\bmlops\b", r"\bmlflow\b", r"\bkubeflow\b", r"\bmodel serving\b",
    r"\bmodel deployment\b", r"\bdeploy(?:ing|ed)? (?:machine learning|ml) models?\b",
    r"\bproduction machine learning\b", r"\bcomputer vision\b", r"\bnlp\b",
    r"\bnatural language processing\b", r"\bpytorch\b", r"\btensorflow\b",
    r"\bdeep learning\b", r"\bllm\b", r"\bgenai\b|\bgenerative ai\b",
]

HEAVY_ENGINEERING_SIGNALS = [
    r"\bspark\b|\bpyspark\b", r"\bkafka\b", r"\bhadoop\b", r"\bscala\b",
    r"\bhdfs\b", r"\bflink\b", r"\bkubernetes\b", r"\bterraform\b",
    r"\baws emr\b|\bemr\b", r"\baws glue\b", r"\bhive\b",
]

SPECIALIZED_DOMAIN_GROUPS = {
    "market risk": [r"\bmarket risk\b", r"\bvalue at risk\b|\bvar\b", r"\bsensitivit|\bsensibilidad|\bsensibilidades"],
    "medicaid": [r"\bmedicaid\b", r"\bt-msis\b", r"\bhealthcare fraud\b|\bfraud waste abuse\b"],
    "pharma clinical": [r"\bpharma\b|\bbiotech\b", r"\bclinical trials?\b|\bdrug development\b|\bcmc\b"],
    "crop regulatory": [r"\bcrop science\b|\bplant protection\b|\bbiological assessment\b", r"\bregulatory dossier\b|\bregulatory\b"],
    "sap specialist": [r"\bsap\b", r"\bbpc\b|\bsap bw\b|\bsap hana\b|\bsap integration\b"],
    "security analytics": [r"\bsiem\b|\bedr\b|\biam\b|\bdlp\b", r"\bsecurity analytics\b|\bvulnerability management\b"],
    "cyberark": [r"\bcyberark\b", r"\bpam\b|\bidentity access management\b|\biam\b"],
    "agrochemical": [r"\bbiostimulant\b|\bfertilizer\b|\bagrochemical\b", r"\bagronom"],
    "clinical programming": [r"\brshiny\b|\br shiny\b", r"\bcro\b|\bclinical data\b|\bgxp\b"],
}

NON_TARGET_CORE_PATTERNS = [
    r"\bfull[- ]?stack\b|\bfrontend\b|\bback[- ]?end\b|\bsoftware developer\b",
    r"\bconsultor(?:/a)? inmobiliario\b|\breal estate (?:sales|consultant|agent)\b",
    r"\bsales specialist\b|\baccount executive\b",
    r"\bquality affairs\b|\bregulatory affairs\b|\bit quality manager\b",
    r"\bcontroller financiero\b|\bfinancial controller\b|\bproduct and marketing manager\b",
    r"\bcontact[- ]center\b|\bresponsable servicio atc\b",
    r"\biam\b.*\bpam\b|\bcyberark\b",
    r"\berror manager\b|\bhmi\b",
    r"\br programmer\b|\bshiny developer\b",
]

MANDATORY_NON_TARGET_LANGUAGE_PATTERNS = [
    # Keep the proficiency marker grammatically attached to the language so
    # "Fluent English; German is a plus" is NOT misread as mandatory German.
    r"\b(?:fluent(?:\s+in)?|native|bilingual|c1|c2|working fluency(?:\s+in)?|professional proficiency(?:\s+in)?)\s+(?:french|italian|portuguese|polish|german|dutch)\b",
    r"\bworking fluency in at least one of.{0,40}\b(?:french|italian|portuguese|polish|german|dutch)\b",
    r"\b(?:french|italian|portuguese|polish|german|dutch)\b.{0,35}\b(?:required|mandatory|must have|c1|c2|native|bilingual)\b",
]

INTERNSHIP_PATTERNS = [
    r"\bintern(?:ship)?\b", r"\bapprentice(?:ship)?\b", r"\btrainee\b",
    r"\bcontrato de practicas\b", r"\ben practicas\b", r"\bbeca(?:rio|ria)?\b",
]


@dataclass
class ScoreResult:
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
            "score_v1": str(self.score),
            "score_band_v1": self.band,
            "scoring_version": self.version,
            "score_role_family": self.role_family,
            "score_geography_fit": self.geography_fit,
            "score_years_required": "" if self.years_required is None else f"{self.years_required:g}",
            "score_skill_count": str(self.skill_count),
            "score_skill_signals": " | ".join(self.skill_signals),
            "score_role_points": str(self.role_points),
            "score_skill_points": str(self.skill_points),
            "score_experience_points": str(self.experience_points),
            "score_geography_points": str(self.geography_points),
            "score_domain_points": str(self.domain_points),
            "score_seniority_points": str(self.seniority_points),
            "score_employment_points": str(self.employment_points),
            "score_evidence_points": str(self.evidence_points),
            "score_penalty": str(self.penalty),
            "score_penalty_reasons": "; ".join(self.penalty_reasons),
        }


def _has_actionable_detail(job: dict[str, Any]) -> bool:
    detail = clean_text(job.get("full_detail"))
    status = normalize(job.get("detail_status"))
    if not detail:
        return False
    if status in {"failed", "insufficient_detail"}:
        return False
    return len(detail) >= 250 or count_patterns(normalize(detail), [r"\brequirements?\b", r"\bexperience\b", r"\bresponsibilit", r"\brequisitos?\b"]) >= 1


def _role_family_and_points(title: str, text: str) -> tuple[str, int]:
    t = normalize(title)
    lower = normalize(text)
    if re.search(r"\banalytics engineer\b|\bdata analytics engineer\b", t):
        return "Analytics Engineer", 24
    if re.search(r"\bbi analyst\b.*\bdata engineer\b|\bdata engineer\b.*\bbi analyst\b", t):
        return "Data Engineer", 20
    if re.search(r"\bdata analyst\b|\bbi analyst\b|\bbusiness intelligence (?:developer|analyst|manager)\b|\bdata operations and business intelligence manager\b|\breporting analyst\b|\bpower bi analyst\b", t):
        return "BI / Reporting", 25
    if re.search(r"\bbusiness analyst\b", t):
        return "Business Analyst", 22
    if re.search(r"\bdata scientist\b", t):
        productish = (
            count_patterns(lower, PRODUCT_DS_SIGNALS) >= 2
            or bool(re.search(r"\bproduct data scientist\b|\bdata scientist finance\b|\bcommerce analytics\b", t))
        )
        # Finance/product/commerce DS is target-adjacent; ML-engineering DS is lower.
        return "Data Scientist", 22 if productish else 18
    if re.search(r"\bdata science\b", t):
        return "Other", 6
    if re.search(r"\bdata engineer\b|\bingeniero.{0,20}\bdatos\b", t):
        return "Data Engineer", 20

    adjacent = [
        r"\bdata product owner\b", r"\bdata annotation\b", r"\bdata specialist\b",
        r"\bbusiness controller\b", r"\bdata & ai engineer\b|\bdata and ai engineer\b",
        r"\bconsultor.{0,20}\bdatos\b", r"\bdata solutions specialist\b",
        r"\banalisis de datos\b|\banalysis of data\b", r"\bbi\b",
    ]
    if any(re.search(p, t, re.I) for p in adjacent):
        return "Other", 15

    weak_adjacent = [r"\bdata lead\b", r"\bdata science\b", r"\bteam manager\b", r"\bdirector\b.*\bdata lead\b"]
    if any(re.search(p, t, re.I) for p in weak_adjacent):
        return "Other", 6

    if any(re.search(p, t, re.I) for p in NON_TARGET_CORE_PATTERNS):
        return "Other", 1

    # Unknown title with substantive analytical content gets modest credit.
    analytical = count_patterns(lower, [r"\bsql\b", r"\bpower bi\b", r"\bdashboard", r"\bdata quality\b", r"\betl\b", r"\banalytics\b"])
    if analytical >= 2:
        return "Other", 15
    return "Other", 6


def _skill_signals(text: str, title: str = "") -> list[str]:
    lower = normalize(text)
    signals = [name for name, pattern in SKILL_SIGNALS.items() if re.search(pattern, lower, flags=re.I)]
    t = normalize(title)
    if (
        "Data Quality" not in signals
        and re.search(r"\bgovernance\b", lower)
        and re.search(r"\bbusiness intelligence\b|\banalytics engineer\b|\bdata analyst\b", t)
    ):
        signals.append("Data Quality")
    return signals


def _skill_points(skill_count: int, evidence: bool, role_points: int) -> int:
    if not evidence:
        return 10
    if skill_count >= 7:
        return 20
    if skill_count >= 5:
        return 18
    if skill_count >= 3:
        return 15
    if skill_count == 2:
        return 12
    if skill_count == 1:
        return 8
    return 6


def _experience_points(years: float | None) -> int:
    if years is None:
        return 11
    if years <= 1:
        return 15
    if years <= 2:
        return 14
    if years <= 3:
        return 11
    if years <= 4:
        return 7
    if years <= 5:
        return 3
    return 0


def _is_remote_spain(text: str) -> bool:
    lower = normalize(text)
    patterns = [
        r"\bfully remote\b", r"\b100 remote\b", r"\b100 remoto\b", r"\bremote spain\b",
        r"\bremote in spain\b", r"\bwork from anywhere in spain\b", r"\bwork remotely from anywhere in spain\b",
        r"\bremoto desde cualquier punto de espana\b", r"\bteletrabajo 100\b", r"\bremotespain\b", r"\bwork anywhere company\b",
    ]
    return any(re.search(p, lower) for p in patterns)


def _is_catalunya(location: str) -> bool:
    loc = normalize(location)
    return any(x in loc for x in ["barcelona", "catalonia", "catalunya", "girona", "tarragona", "lleida", "sant cugat", "badalona", "terrassa", "sabadell"])


def _geography(job: dict[str, Any], text: str) -> tuple[str, int, bool]:
    location = clean_text(job.get("location"))
    t = normalize(job.get("title"))
    full = normalize(text)
    if re.search(r"\bremote\b|\bremot[oa]\b|\bteletrabajo\b", t) or _is_remote_spain(full):
        return "Remote fit", 15, False
    if _is_catalunya(location) or count_patterns(full, [r"\bbarcelona\b", r"\bcatalunya\b|\bcatalonia\b"]) >= 1:
        return "Catalunya fit", 15, False
    if not location or normalize(location) in {"unknown", ""}:
        return "Unknown", 10, False
    if normalize(location) in {"spain", "espana"}:
        return "Outside target / unclear", 9, False

    loc_norm = normalize(location)
    clearly_outside_city = any(city in loc_norm for city in ["madrid", "seville", "sevilla", "sagunto", "alcobendas"])
    explicit_outside = clearly_outside_city or count_patterns(full, [
        r"\b(?:hybrid|hibrid[oa])\b.{0,80}\b(?:madrid|sevilla|seville|sagunto|valencia|pamplona|alcobendas)\b",
        r"\b(?:madrid|sevilla|seville|sagunto|valencia|pamplona|alcobendas)\b.{0,80}\b(?:hybrid|hibrid[oa])\b",
        r"\bpresencial\b.{0,80}\b(?:madrid|sevilla|sagunto|valencia|pamplona|alcobendas)\b",
        r"\bonsite\b.{0,80}\b(?:madrid|sevilla|seville|sagunto|valencia|pamplona|alcobendas|lisbon|lisboa)\b",
    ]) >= 1
    if explicit_outside:
        return "Outside target / unclear", 3, True
    return "Outside target / unclear", 9, False


def _specialized_domain(text: str) -> tuple[bool, str]:
    lower = normalize(text)
    for name, patterns in SPECIALIZED_DOMAIN_GROUPS.items():
        if all(re.search(p, lower, re.I) for p in patterns):
            return True, name
    return False, ""


def _domain_points(role_family: str, role_points: int, text: str, specialized: bool) -> int:
    lower = normalize(text)
    if role_points <= 1:
        return 0
    if specialized:
        return 3
    if role_family in {"Analytics Engineer", "BI / Reporting", "Data Analyst", "Business Analyst"}:
        return 10
    if role_family == "Data Engineer":
        return 9
    if role_family == "Data Scientist":
        if count_patterns(lower, ML_SPECIALIST_SIGNALS) >= 2:
            return 6
        return 9 if role_points >= 22 or count_patterns(lower, PRODUCT_DS_SIGNALS) >= 1 else 6
    if role_points == 15:
        return 8
    if role_points == 6:
        return 4
    return 0


def _seniority_points(title: str) -> int:
    t = normalize(title)
    if re.search(r"\bdirector\b|\bhead\b|\bmanager\b|\bgerente\b|\bresponsable\b|\blead\b", t):
        return 0
    if re.search(r"\bsenior\b|\bsr\b|\bprincipal\b|\bexpert\b", t):
        return 3
    return 5


def _penalties(job: dict[str, Any], role_family: str, role_points: int, years: float | None, explicit_outside: bool, text: str) -> tuple[int, list[str]]:
    title = normalize(job.get("title"))
    lower = normalize(text)
    penalty = 0
    reasons: list[str] = []

    if years is not None:
        if years >= 6:
            penalty -= 10
            reasons.append(f"{years:g}+ years" if years > 6 else "6+ years")
        elif years >= 5:
            penalty -= 8
            reasons.append("5+ years")
        elif years >= 4:
            penalty -= 3
            reasons.append("4 years")

    if re.search(r"\bdirector\b|\bhead\b|\bmanager\b|\bgerente\b|\bresponsable\b", title):
        penalty -= 15
        reasons.append("manager/director")
    elif re.search(r"\blead\b", title):
        penalty -= 8
        reasons.append("lead")

    heavy_count = count_patterns(lower, HEAVY_ENGINEERING_SIGNALS)
    ml_count = count_patterns(lower, ML_SPECIALIST_SIGNALS)
    explicit_ml_engineer = bool(re.search(r"\bml engineer\b|\bmachine learning engineer\b", title))
    heavy_specialist = heavy_count >= 4 or (role_family == "Data Scientist" and ml_count >= 3) or explicit_ml_engineer
    production_ml = (
        explicit_ml_engineer
        or (
            role_family == "Data Scientist"
            and ml_count >= 2
            and count_patterns(lower, [r"\bproduction\b|\bproduccion\b", r"\bdeploy|\bdesplieg", r"\bserving\b|\bmodelos? productivos?\b"]) >= 1
        )
    )
    if heavy_specialist:
        penalty -= 12
        reasons.append("heavy specialist stack")
    if production_ml:
        penalty -= 12
        reasons.append("production ML")

    specialized, _ = _specialized_domain(lower)
    if re.search(r"\br programmer\b|\bshiny developer\b", title):
        specialized = True
    if re.search(r"\bbiostimulants?\b|\bfertilizers?\b|\bagrochemicals?\b", title):
        specialized = True
    if specialized:
        penalty -= 10
        reasons.append("specialized domain")

    if explicit_outside:
        penalty -= 8
        reasons.append("outside geography")

    # Spanish is intentionally excluded. Only explicit other-language requirements count.
    if any(re.search(p, lower, re.I) for p in MANDATORY_NON_TARGET_LANGUAGE_PATTERNS):
        penalty -= 18
        reasons.append("mandatory non-target language")

    # Senior production-intensity penalty is reserved for genuinely demanding
    # senior analytics-engineering ownership when no explicit 5+ year penalty exists.
    if (
        role_family == "Analytics Engineer"
        and re.search(r"\bsenior\b|\bsr\b", title)
        and years is None
        and count_patterns(lower, [r"\bproduction\b", r"\bexpert sql\b", r"\bownership\b|\bown\b", r"\blarge[- ]scale\b|\bcomplex datasets?\b"]) >= 3
    ):
        penalty -= 8
        reasons.append("senior production intensity")

    # General non-target core penalty. Data/BI managers are handled by seniority
    # rather than this penalty so the two concepts do not get conflated.
    non_target_core = any(re.search(p, title, re.I) for p in NON_TARGET_CORE_PATTERNS)
    target_manager = role_family in {"BI / Reporting", "Data Analyst", "Data Engineer", "Analytics Engineer", "Data Scientist", "Business Analyst"}
    if non_target_core and not target_manager and role_points <= 1:
        penalty -= 18
        reasons.append("non-target core role")

    return penalty, reasons


def score_band(score: int) -> str:
    for name in ("HIGH", "REVIEW", "LOW_SCORE", "VERY_LOW_SCORE"):
        lo, hi = SCORE_BANDS[name]
        if lo <= score <= hi:
            return name
    return "VERY_LOW_SCORE" if score < 0 else "HIGH"


def score_job_v1(job: dict[str, Any]) -> ScoreResult:
    title = clean_text(job.get("title"))
    detail = clean_text(job.get("full_detail"))
    text = f"{title}\n{detail}"
    evidence = _has_actionable_detail(job)

    role_family, role_points = _role_family_and_points(title, text)
    skills = _skill_signals(text, title) if evidence else []
    skill_points = _skill_points(len(skills), evidence, role_points)
    years = extract_min_required_years(text) if evidence else None
    experience_points = _experience_points(years)
    geography_fit, geography_points, explicit_outside = _geography(job, text)
    specialized, _domain_name = _specialized_domain(text)
    domain_points = _domain_points(role_family, role_points, text, specialized)
    seniority_points = _seniority_points(title)
    employment_points = 2 if any(re.search(p, normalize(text), re.I) for p in INTERNSHIP_PATTERNS) else 5
    evidence_points = 5 if evidence else 4
    penalty, penalty_reasons = _penalties(job, role_family, role_points, years, explicit_outside, text)

    raw = (
        role_points + skill_points + experience_points + geography_points + domain_points
        + seniority_points + employment_points + evidence_points + penalty
    )
    score = max(0, min(100, int(round(raw))))
    return ScoreResult(
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
        seniority_points=seniority_points,
        employment_points=employment_points,
        evidence_points=evidence_points,
        penalty=penalty,
        penalty_reasons=penalty_reasons,
    )


def apply_scoring_v1(jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        result = score_job_v1(job)
        job.update(result.as_job_fields())
