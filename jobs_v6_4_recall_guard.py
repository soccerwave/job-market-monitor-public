from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from scoring_v1 import SCORING_VERSION as SCORING_VERSION_V1, apply_scoring_v1
from scoring_v2 import SCORING_VERSION as SCORING_VERSION_V2, apply_scoring_v2
from typing import Any

HOME = Path.home()
SCRIPT_DIR = Path(__file__).resolve().parent
MADRID_TZ = ZoneInfo("Europe/Madrid")
IS_GITHUB_ACTIONS = os.getenv("GITHUB_ACTIONS", "").lower() == "true"

# Local Windows mode keeps the existing folder layout.
# GitHub Actions mode uses repo-relative archive/state paths supplied by the workflow.
if IS_GITHUB_ACTIONS:
    MADS_REPO = Path(os.getenv("JOB_SEARCH_MADS_REPO", SCRIPT_DIR / ".vendor" / "mads"))
    SPAIN_REPO = Path(os.getenv("JOB_SEARCH_SPAIN_REPO", SCRIPT_DIR / ".vendor" / "spain"))
    OUTPUT_DIR = Path(os.getenv("JOB_SEARCH_OUTPUT_DIR", SCRIPT_DIR / "archive"))
    STATE_DIR = Path(os.getenv("JOB_SEARCH_STATE_DIR", SCRIPT_DIR / "_state"))
else:
    MADS_REPO = Path(os.getenv("JOB_SEARCH_MADS_REPO", HOME / "Documents" / "ai-job-search-private"))
    SPAIN_REPO = Path(os.getenv("JOB_SEARCH_SPAIN_REPO", HOME / "Documents" / "ai-job-search-spain-test"))
    OUTPUT_DIR = Path(os.getenv("JOB_SEARCH_OUTPUT_DIR", HOME / "Documents" / "job-search-output"))
    STATE_DIR = Path(os.getenv("JOB_SEARCH_STATE_DIR", OUTPUT_DIR / "_state"))

STATE_FILE = STATE_DIR / "seen_jobs.json"


def local_today() -> date:
    """Calendar date in Europe/Madrid, both locally and on cloud runners."""
    return datetime.now(MADRID_TZ).date()

# ============================================================
# SEARCH CONFIG
# ============================================================

QUERIES = [
    "data analyst",
    "power bi",
    "business intelligence",
    "analytics engineer",
    "data quality",
    "marketing data analyst",
]

# Targeted recall expansion. Generic "data scientist" is intentionally
# NOT used because it would add a large amount of ML-heavy noise.
LINKEDIN_EXTRA_QUERIES = [
    "data scientist marketing",
]

# Compact query set for the new tech-focused supplementary portals.
SUPPLEMENTARY_QUERIES = [
    "data analyst",
    "business intelligence",
    "analytics engineer",
    "power bi",
    "product analyst",
    "data scientist marketing",
]

LIMIT_PER_SEARCH = 10
SUPPLEMENTARY_LIMIT = 25

# Normal daily mode.
LINKEDIN_DAILY_MINUTES = 36 * 60
OTHER_DAILY_DAYS = 1

# Catch-up mode.
CATCHUP_DAYS = 7

LINKEDIN_SCOPES = [
    {"label": "Catalunya", "location": "Catalonia, Spain", "remote": None},
    {"label": "Remote Spain", "location": "Spain", "remote": "remote"},
]

# Tecnoempleo filters by province, so cover all four Catalan provinces.
TECNO_LOCATIONS = ["Barcelona", "Girona", "Tarragona", "Lleida"]

LINKEDIN_CLI = Path(".agents/skills/linkedin-search/cli/src/cli.ts")
INFOJOBS_CLI = Path(".agents/skills/infojobs-search/cli/src/cli.ts")
TECNO_CLI = Path(".agents/skills/tecnoempleo-search/cli/src/cli.ts")
GETMANFRED_CLI = Path(".agents/skills/getmanfred-search/cli/src/cli.ts")
JOPPY_CLI = Path(".agents/skills/joppy-search/cli/src/cli.ts")
FREEHIRE_CLI = Path(".agents/skills/freehire-search/cli/src/cli.ts")

SEEN_RETENTION_DAYS = 45
DEFAULT_DETAIL_LIMIT = int(os.getenv("JOB_SEARCH_DETAIL_LIMIT", "140"))

# ============================================================
# TITLE TRIAGE
# ============================================================

AUTO_SKIP_TITLE_PATTERNS = [
    (r"\bsoftware engineer\b", "Software engineering role"),
    (r"\bplatform engineer\b", "Platform engineering role"),
    (r"\bazure devops engineer\b|\bdevops\b", "DevOps role"),
    (r"\bbim\b", "BIM role"),
    (r"\brpa developer\b", "RPA developer role"),
    (r"\bphp developer\b|\bjavascript developer\b", "Software developer role"),
    (r"\bproduct owner\b", "Product Owner role"),
    (r"\bhead waiter\b", "Hospitality role"),
    (r"\bconsultor(?:/a)? inmobiliari[oa]\b|\basesor(?:/a)? inmobiliari[oa]\b|\bagente inmobiliari[oa]\b|\breal estate (?:agent|consultant|advisor|sales)\b|\bproperty consultant\b", "Real-estate sales/consulting role"),
    (r"\bquality assurance rater\b", "QA rater, not data-quality analytics"),
    (r"\bservice desk analyst\b", "IT support/service desk role"),
    (r"\bservice manager\b", "Service management / IT operations role"),
    (r"\bciberseguridad\b|\bcybersecurity\b", "Cybersecurity role"),
    (r"\bdynamics 365\b", "Dynamics 365 specialist role"),
    (r"\bdocente\b", "Teaching role"),
    (r"\bprogramador\b", "Programming/developer role"),
    (r"\bbig data developer\b", "Big-data developer role"),
    (r"\bstrategic purchaser\b|\bprocurement\b.*\bpurchas", "Procurement/purchasing role"),
    (r"\btechnical architect\b|\bmdm technical architect\b", "Technical architecture role"),
    (r"\bbackend engineer\b", "Backend engineering role"),
    (r"\bjava backend developer\b|\bjava developer\b", "Java/backend development role"),
    (r"\bhelpdesk\b|\bhelp desk\b", "Helpdesk / IT support role"),
    (r"\bhead of\b", "Head-level role outside target seniority"),
    (r"\blead test data specialist\b", "Lead test-data role outside target family/level"),
    (r"\bquality affairs specialist\b", "Regulatory/quality-affairs role, not data quality"),
    (r"\bsupply planner\b", "Supply planning role rather than target analytics family"),
    (r"\bfull[- ]stack\b", "Full-stack software development role"),
    (r"\bfrontend (?:developer|engineer)\b", "Frontend software development role"),
    (r"\baccount manager\b", "Account management / sales role"),
    (r"\bbusiness development (?:representative|executive)\b", "Business development / sales role"),
    (r"\bcustomer experience specialist\b", "Customer experience / account-management role"),
    (r"\boffice manager\b|\bexecutive assistant\b", "Office management / executive-assistant role"),
    (r"\bcloud engineer\b", "Cloud infrastructure role"),
    (r"\bsap support specialist\b", "SAP support role"),
    (r"\bodoo\b.*\bdeveloper\b", "Odoo software-development role"),
    (r"\bthird[- ]party cyber risk\b|\bcyber risk management\b", "Cyber-risk role"),
    (r"\bsupply chain business process architect\b", "Supply-chain solution consulting role"),
]

HIGH_TITLE_PATTERNS = [
    (r"\bbi analyst\b", "BI Analyst target family"),
    (r"\bbusiness intelligence analyst\b", "Business Intelligence Analyst target family"),
    (r"\bbusiness data analyst\b", "Business Data Analyst target family"),
    (r"\bpower bi analyst\b", "Power BI Analyst target family"),
    (r"\breporting analyst\b", "Reporting Analyst target family"),
    (r"\bproduct data analyst\b", "Product Data Analyst target family"),
    (r"\bmarketing data analyst\b", "Marketing Data Analyst target family"),
    (r"\bdigital data analyst\b", "Digital Data Analyst target family"),
    (r"\bweb analyst\b", "Web Analyst target family"),
    (r"\bfinance data analyst\b", "Data Analyst target family"),
    (r"\bdata analyst\b", "Data Analyst target family"),
    (r"\banalista de datos\b|\banalista de dades\b", "Data Analyst target family"),
    (r"\bdata steward\b", "Data Steward / Data Quality target-adjacent"),
    (r"\binsights analyst\b", "Insights Analyst target-adjacent"),
    (r"\bpeople analytics\b", "People Analytics target-adjacent"),
    (r"\bsales performance analyst\b", "Performance Analytics target-adjacent"),
    (r"\btechnical data steward\b", "Technical Data Steward target-adjacent"),
    (r"\bcontent quality analyst\b", "Content Quality target using journalism/research background"),
    (r"\bjunior data & analytics product specialist\b", "Junior Data & Analytics target"),
]

REVIEW_TITLE_PATTERNS = [
    (r"\bdata scientist\b", "Data Scientist title; full JD required because some roles strongly overlap with marketing/product analytics"),
    (r"\banalytics engineer\b", "Analytics Engineer target family"),
    (r"\bbi engineer\b|\bbusiness intelligence engineer\b", "BI Engineer target-adjacent"),
    (r"\bpower bi engineer\b", "Power BI target-adjacent"),
    (r"\bbi consultant\b|\bconsultor/a bi\b", "BI consulting target-adjacent"),
    (r"\bdata quality\b", "Data Quality target family"),
    (r"\bdata governance\b", "Data Governance target-adjacent"),
    (r"\bmaster data\b", "Master Data / Data Quality target-adjacent"),
    (r"\bdata visualization\b", "BI / visualization target-adjacent"),
    (r"\bdata specialist\b", "Data specialist, needs JD review"),
    (r"\bbusiness analyst\b", "Business Analyst, needs JD review"),
    (r"\bmarketing analyst\b", "Marketing analytics target-adjacent"),
    (r"\bdata engineer\b", "Data engineering overlap, needs JD review"),
    (r"\bcatalogue and master data\b", "Master Data target-adjacent"),
    (r"\bperformance analyst\b", "Performance analytics target-adjacent"),
    (r"\bpricing analyst\b", "Pricing analytics target-adjacent"),
    (r"\bsales operations analyst\b", "Sales/RevOps analytics target-adjacent"),
    (r"\btechnical analyst\b", "Technical analyst, needs JD review"),
]

# ============================================================
# FULL-JD SIGNALS
# ============================================================

HEAVY_ENGINEERING_SIGNALS = {
    "spark": r"\bspark\b|\bpyspark\b",
    "kafka": r"\bkafka\b",
    "hadoop": r"\bhadoop\b",
    "scala": r"\bscala\b",
    "hdfs": r"\bhdfs\b",
    "flink": r"\bflink\b",
    "kubernetes": r"\bkubernetes\b",
    "terraform": r"\bterraform\b",
    "emr": r"\baws emr\b|\bemr\b",
    "glue": r"\baws glue\b|\bglue\b",
    "microservices": r"\bmicroservices?\b",
    "distributed_systems": r"\bdistributed systems?\b",
}

TARGET_TECH_SIGNALS = {
    "sql": r"\bsql\b",
    "python": r"\bpython\b",
    "power_bi": r"\bpower bi\b",
    "tableau": r"\btableau\b",
    "looker": r"\blooker\b|\blooker studio\b",
    "dbt": r"\bdbt\b",
    "bigquery": r"\bbigquery\b|\bbig query\b",
    "snowflake": r"\bsnowflake\b",
    "data_modeling": r"\bdata model(?:ing|ling)\b|\bdimensional model(?:ing|ling)\b|\bsemantic model",
    "dashboard": r"\bdashboards?\b",
    "reporting": r"\breporting\b|\breports?\b",
    "data_quality": r"\bdata quality\b|\breconciliation\b|\bdata validation\b",
    "ga4": r"\bga4\b|\bgoogle analytics 4\b",
}

CONTENT_SIGNALS = {
    "research": r"\bresearch\b|\bdue diligence\b",
    "writing_editing": r"\bwriting\b|\bediting\b|\beditorial\b",
    "quality_control": r"\bquality control\b|\bcontent quality\b",
    "farsi": r"\bfarsi\b|\bpersian\b",
}

ML_ENGINEERING_SIGNALS = [
    r"\bmlops\b",
    r"\bmlflow\b",
    r"\bkubeflow\b",
    r"\bmodel serving\b",
    r"\bmodel deployment\b",
    r"\bdeploy(?:ing)? machine learning models?\b",
    r"\bproduction machine learning\b",
    r"\bcomputer vision\b",
    r"\bnatural language processing\b|\bnlp\b",
    r"\bpytorch\b",
    r"\btensorflow\b",
]

MANAGERIAL_LEADERSHIP_SIGNALS = [
    r"\blead and develop (?:the )?(?:team|function)\b",
    r"\blead, coach, and develop\b",
    r"\bpeople leadership\b",
    r"\bmanage(?:ment|s|d)? (?:of )?(?:a )?team\b",
    r"\bdirect reports?\b",
    r"\bcoordinate teams? and (?:external )?providers?\b",
    r"\blider(?:ar|ando|azgo)\b.{0,80}\bequip",
    r"\bgestionar\b.{0,60}\bequip",
    r"\bgesti[oó]n de equipos\b",
    r"\bcoordinaci[oó]n de equipos\b",
    r"\bliderando o gestionando entornos\b",
    r"\bleading data analytics teams?\b",
    r"\bleading analytics teams?\b",
]

PROCUREMENT_DOMAIN_SIGNALS = [
    r"\bprocurement\b",
    r"\bcoupa\b",
    r"\bprocure to pay\b|\bp2p\b",
    r"\bvendor management\b",
    r"\bsupplier management\b",
]

SENIOR_EXPECTATION_SIGNALS = [
    r"\bexpert[- ]level\b",
    r"\bproduction[- ]level\b",
    r"\bsenior and hands[- ]on\b",
    r"\bsenior, strategic\b",
    r"\bsignificant experience\b",
    r"\bdeeply comfortable with\b",
]

PHARMA_SPECIALIST_PATTERNS = [
    r"\b(?:minimum of )?\d+\+?\s+years?.{0,120}\bpharmaceutical\b",
    r"\b(?:minimum of )?\d+\+?\s+years?.{0,120}\bbiotech\b",
    r"\bpharma r&d\b.{0,120}\bexperience\b",
]

CONTROLLING_DOMAIN_SIGNALS = [
    r"\bcontrolling\b",
    r"\bfp&a\b",
    r"\bdigital finance\b",
    r"\bfinancial planning\b",
]

SECURITY_ANALYTICS_SPECIALIST_SIGNALS = [
    r"\bsecurity analytics\b",
    r"\bciso\b",
    r"\bsecops\b",
    r"\bgrc\b",
    r"\bvulnerability remediation\b",
    r"\bvendor risk\b",
]

GRAPH_ENGINEERING_SIGNALS = [
    r"\bneo4j\b",
    r"\bcypher\b",
    r"\bgraph data science\b",
    r"\bgnn\b",
    r"\bgraph ml\b",
]

ML_LIFECYCLE_SIGNALS = [
    r"\bmodel deployment\b",
    r"\bdeployment and monitoring\b",
    r"\bdeploy(?:ing|ment)?\b",
    r"\bmodels? deployed\b",
    r"\btensorflow\b",
    r"\bpytorch\b",
    r"\bdatabricks\b",
    r"\bmlflow\b",
]

NON_TARGET_REQUIRED_TOOL_SIGNALS = [
    r"\bselligent\b.{0,80}\b(?:required|mandatory|imprescindible)\b",
    r"\b(?:required|mandatory|imprescindible)\b.{0,80}\bselligent\b",
]

NON_TARGET_LANGUAGE_HARD_PATTERNS = [
    r"\bfrench\b.{0,80}\bmandatory\b",
    r"\bfrench\b.{0,80}\brequired\b",
    r"\bfrancais\b.{0,80}\bobligatoire\b",
    r"\bfrances\b.{0,80}\bimprescindible\b",
]

US_WORK_AUTH_PATTERNS = [
    r"legal authorization to work permanently in the united states",
    r"authorized to work (?:permanently )?in the united states",
    r"work authorization (?:for|in) the united states",
    r"u\.?s\.? work authorization",
    r"eligible to work in the united states",
]

CATALAN_HARD_PATTERNS = [
    r"(?:native|bilingual|c2).{0,30}catalan",
    r"catalan.{0,30}(?:native|bilingual|c2)",
    r"(?:catal[aà]|catalan).{0,35}(?:imprescindible|required|mandatory)",
]


CLINICAL_HARD_SIGNALS = [
    r"\bclinical data management\b",
    r"\bclinical study\b",
    r"\bclinical trials?\b",
    r"\bcdisc\b",
    r"\bsdtm\b",
    r"\badam\b",
    r"\bmedidata rave\b",
    r"\bich[- ]gcp\b",
]

SANCTIONS_SPECIALIST_SIGNALS = [
    r"\bsanctions data\b",
    r"\bsanctions lists?\b",
    r"\beu sanctions\b",
    r"\bun sanctions\b",
]

# Known specialist stacks outside the current core profile.
SAP_REQUIRED = [
    r"\bsap bw\b",
    r"\bsap hana\b",
    r"\bsap analytics cloud\b",
]

WORKDAY_REQUIRED = [
    r"\bworkday architecture\b",
    r"\bworkday configuration",
    r"\bworkday hcm\b",
]

ORACLE_BI_REQUIRED = [
    r"\boracle bi\b",
    r"\bpowercenter\b",
    r"\binformatica powercenter\b",
]

# ============================================================
# HELPERS
# ============================================================

def fail(message: str) -> None:
    print(f"\nERROR: {message}", file=sys.stderr)
    sys.exit(1)


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def normalize(value: Any) -> str:
    text = clean_text(value).lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"\b(s\.?l\.?|s\.?a\.?|ltd\.?|limited|inc\.?|gmbh)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_location(value: Any) -> str:
    text = normalize(value)
    if not text:
        return "unknown"
    if "barcelona" in text:
        return "barcelona"
    if any(x in text for x in ["madrid", "alcobendas", "pozuelo", "san fernando de henares"]):
        return "madrid"
    if text == "spain" or any(x in text for x in ["work from home", "remoto", "remote"]):
        return "spain_remote_or_unspecified"
    if "malaga" in text:
        return "malaga"
    if "seville" in text or "sevilla" in text:
        return "seville"
    if "tenerife" in text or "canary islands" in text:
        return "canary_islands"
    if "valencia" in text or "paterna" in text:
        return "valencia"
    return text

# Broad Catalunya coverage for location scoring.
# This is intentionally permissive: the user is willing to consider
# roles throughout Catalunya, including locations roughly 1-2 hours
# from Barcelona.
CATALONIA_LOCATION_TERMS = [
    # Region / provinces
    "catalonia", "catalunya", "barcelona", "girona", "gerona",
    "tarragona", "lleida", "lerida",

    # Barcelona metro / Baix Llobregat
    "hospitalet", "l hospitalet", "badalona", "santa coloma",
    "sant adria", "el prat", "prat de llobregat", "cornella",
    "sant boi", "viladecans", "gava", "castelldefels",
    "sant feliu de llobregat", "sant joan despi", "sant just desvern",
    "esplugues", "molins de rei", "martorell", "abrera",

    # Vallès / major commuting & industrial hubs
    "sant cugat", "rubi", "terrassa", "sabadell", "cerdanyola",
    "barbera del valles", "sant quirze", "granollers", "mollet",
    "montcada", "ripollet", "parets del valles", "les franqueses",
    "montmelo", "la roca del valles",

    # Maresme / north coast
    "mataro", "premia de mar", "vilassar", "el masnou", "masnou",
    "arenys", "calella", "pineda de mar", "malgrat de mar", "tordera",

    # Penedès / Garraf / Anoia / Bages / Osona
    "vilanova i la geltru", "sitges", "vilafranca del penedes",
    "igualada", "manresa", "vic", "berga",

    # Girona province / Costa Brava
    "figueres", "blanes", "lloret de mar", "salt", "olot",
    "banyoles", "palamos", "palafrugell", "sant feliu de guixols",

    # Tarragona province
    "reus", "salou", "cambrils", "valls", "el vendrell",
    "tortosa", "amposta",

    # Lleida province
    "tarrega", "balaguer", "mollerussa", "cervera", "la seu d urgell",
]


def is_catalonia_target_location(value: Any) -> bool:
    text = normalize(value)
    if not text:
        return False
    return any(term in text for term in CATALONIA_LOCATION_TERMS)


def check_setup() -> None:
    checks = [
        (MADS_REPO, "Mads repo"),
        (SPAIN_REPO, "Spain repo"),
        (MADS_REPO / LINKEDIN_CLI, "LinkedIn CLI"),
        (SPAIN_REPO / INFOJOBS_CLI, "InfoJobs CLI"),
        (SPAIN_REPO / TECNO_CLI, "Tecnoempleo CLI"),
        (SPAIN_REPO / GETMANFRED_CLI, "GetManfred CLI"),
        (SPAIN_REPO / JOPPY_CLI, "Joppy CLI"),
        (SPAIN_REPO / FREEHIRE_CLI, "FreeHire CLI"),
    ]
    for path, label in checks:
        if not path.exists():
            fail(f"{label} not found: {path}")

    try:
        subprocess.run(
            ["bun", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        fail("Bun is not available in PATH. Run: bun --version")


def run_command(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bun", "run", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_json_command(cwd: Path, args: list[str]) -> dict[str, Any]:
    proc = run_command(cwd, args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "Unknown CLI error")

    raw = proc.stdout.strip()
    if not raw:
        return {"results": []}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as first_exc:
        # Some supplementary CLIs occasionally emit unescaped control
        # characters or a diagnostic line around an otherwise valid JSON
        # payload. Retry conservatively before declaring the source failed.
        payload = None
        candidates = [raw]
        for opening, closing in [("{", "}"), ("[", "]")]:
            start = raw.find(opening)
            end = raw.rfind(closing)
            if start >= 0 and end > start:
                candidate = raw[start : end + 1]
                if candidate not in candidates:
                    candidates.append(candidate)
        for candidate in candidates:
            try:
                payload = json.loads(candidate, strict=False)
                break
            except json.JSONDecodeError:
                continue
        if payload is None:
            raise RuntimeError(f"Invalid JSON from CLI: {raw[:400]}") from first_exc

    if isinstance(payload, list):
        return {"results": payload}
    if isinstance(payload, dict):
        return payload
    raise RuntimeError("Unexpected JSON structure.")


def run_plain_command(cwd: Path, args: list[str]) -> str:
    proc = run_command(cwd, args)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "Unknown CLI error")
    return proc.stdout.strip()


def make_job(source: str, scope: str, query: str, item: dict[str, Any]) -> dict[str, str]:
    salary = clean_text(item.get("salary"))
    salary_min = clean_text(item.get("salaryMin") or item.get("salary_min"))
    salary_max = clean_text(item.get("salaryMax") or item.get("salary_max"))

    return {
        "source": source,
        "search_scope": scope,
        "query_found_by": query,
        "id": clean_text(item.get("id")),
        "title": clean_text(item.get("title")),
        "company": clean_text(item.get("company")),
        "location": clean_text(item.get("location")),
        "modality": clean_text(item.get("modality") or item.get("work_mode")),
        "date": clean_text(item.get("date")),
        "url": clean_text(item.get("url")),
        "salary": salary,
        "salary_min": salary_min,
        "salary_max": salary_max,
        # FreeHire search results already contain the complete JD. Other portals
        # simply leave this blank and use their detail endpoint later.
        "preloaded_detail": clean_text(item.get("description")),
    }


def merge_values(existing: str, new: str) -> str:
    values = [v.strip() for v in (existing or "").split(";") if v.strip()]
    for value in [v.strip() for v in (new or "").split(";") if v.strip()]:
        if value not in values:
            values.append(value)
    return "; ".join(values)


def portal_identity(job: dict[str, str]) -> str:
    identity = job.get("id") or job.get("url")
    if identity:
        return f"{job.get('source', '')}::{identity}"
    return (
        f"{job.get('source', '')}::{normalize(job.get('company', ''))}::"
        f"{normalize(job.get('title', ''))}::{canonical_location(job.get('location', ''))}"
    )


def cross_portal_key(job: dict[str, str]) -> str:
    company = normalize(job.get("company", ""))
    title = normalize(job.get("title", ""))
    loc = canonical_location(job.get("location", ""))
    if company and title:
        return f"{company}::{title}::{loc}"
    return portal_identity(job)


def stable_fingerprint(job: dict[str, str]) -> str:
    return hashlib.sha1(cross_portal_key(job).encode("utf-8")).hexdigest()


def matched_named_signals(text: str, signals: dict[str, str]) -> list[str]:
    return [name for name, pattern in signals.items() if re.search(pattern, text, flags=re.I)]


def count_patterns(text: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, text, flags=re.I))


def extract_min_required_years(text: str) -> float | None:
    """Extract explicit candidate experience requirements while avoiding company
    history statements. Handles raw punctuation and normalized text.
    """
    patterns = [
        # English
        r"\bat least\s+(\d+(?:\.\d+)?)\+?\s+years?\b",
        r"\bminimum(?: of)?\s+(\d+(?:\.\d+)?)\+?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s+years?\b",
        r"\b(\d+(?:\.\d+)?)\+?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s+years?\s+of\s+(?:relevant\s+|professional\s+|work\s+|hands[- ]on\s+)?experience\b",
        r"\b(\d+(?:\.\d+)?)\+?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s+years?\s+of\s+.{0,80}?\bexperience\b",
        r"\b(\d+(?:\.\d+)?)\+?\s+years?\s+(?:relevant\s+|professional\s+)?experience\b",

        # Spanish
        r"\bal menos\s+(\d+(?:\.\d+)?)\+?\s+años\b",
        r"\bm[ií]nim[oa]\s+(?:de\s+)?(\d+(?:\.\d+)?)\+?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s+años\b",
        r"\bexperiencia previa.{0,120}?m[ií]nim[oa]\s+(?:de\s+)?(\d+(?:\.\d+)?)\+?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s+años\b",
        r"\b(\d+(?:\.\d+)?)\+?(?:\s*[-–]\s*\d+(?:\.\d+)?)?\s+años\s+de\s+experiencia\b",
        r"\bcon\s+(\d+(?:\.\d+)?)\+?\s+años\s+de\s+experiencia\b",
    ]

    vals: list[float] = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.I):
            try:
                val = float(m.group(1))
            except Exception:
                continue
            if 0 < val <= 15:
                vals.append(val)

    return max(vals) if vals else None


def is_explicit_remote_spain(text: str) -> bool:
    lower = normalize(text)
    patterns = [
        r"\bfully remote\b",
        r"\b100 remote\b",
        r"\b100 remoto\b",
        r"\bremoto 100\b",
        r"\bremote spain\b",
        r"\bremote in spain\b",
        r"\bremoto desde espana\b",
        r"\bremoto desde cualquier punto de espana\b",
        r"\bwork remotely from anywhere in spain\b",
        r"\bwork from anywhere in spain\b",
        r"\bwork anywhere\b",
        r"\bentorno 100 remoto\b",
        r"\btrabajo 100 remoto\b",
        r"\bmodalidad 100 remota\b",
    ]
    return any(re.search(p, lower, re.I) for p in patterns)


def explicit_outside_target_onsite(detail: str) -> str:
    """Return a concise mismatch reason when the JD explicitly contradicts
    portal metadata and requires onsite/hybrid work outside Catalunya.
    """
    lower = normalize(detail)

    # Explicit fully-onsite city requirements.
    outside_onsite = [
        (r"\bfully onsite\b.{0,100}\blisbon\b|\bfully on site\b.{0,100}\blisbon\b", "Fully onsite in Lisbon"),
        (r"\bfully onsite\b.{0,100}\bmadrid\b|\bfully on site\b.{0,100}\bmadrid\b", "Fully onsite in Madrid"),
        (r"\bpresencial\b.{0,100}\bmadrid\b", "On-site in Madrid"),
        (r"\bpresencial\b.{0,100}\blisboa\b|\bpresencial\b.{0,100}\blisbon\b", "On-site in Lisbon"),
    ]
    for pattern, reason in outside_onsite:
        if re.search(pattern, lower, re.I):
            return reason

    return ""


def outside_target_location_penalty(job: dict[str, str], detail: str) -> bool:
    raw_location = job.get("location", "")
    loc = canonical_location(raw_location)
    title_lower = normalize(job.get("title", ""))

    # A job explicitly labelled Remote/Remoto in its title should not be
    # demoted merely because the portal also attaches a city/office location.
    if re.search(r"\bremote\b|\bremot[oa]\b", title_lower, re.I):
        return False

    # Any location in Catalunya is acceptable without penalty.
    if is_catalonia_target_location(raw_location):
        return False

    if loc in {"spain_remote_or_unspecified", "unknown"}:
        return False

    if is_explicit_remote_spain(detail):
        return False

    lower = normalize(detail)

    # If the JD explicitly offers Barcelona/Catalunya as one of several
    # possible office locations, do not penalize it.
    accepted_location_signals = [
        "madrid or barcelona",
        "madrid o barcelona",
        "barcelona or madrid",
        "barcelona o madrid",
        "barcelona spain",
        "catalonia spain",
        "catalunya",
    ]
    if any(signal in lower for signal in accepted_location_signals):
        return False

    return True

# ============================================================
# COLLECTION
# ============================================================

def collect_linkedin(catchup: bool) -> list[dict[str, str]]:
    jobs = []
    for query in [*QUERIES, *LINKEDIN_EXTRA_QUERIES]:
        for scope in LINKEDIN_SCOPES:
            print(f"LinkedIn      | {scope['label']:<12} | {query}")
            args = [
                str(LINKEDIN_CLI), "search",
                "-q", query,
                "-l", scope["location"],
                "--limit", str(LIMIT_PER_SEARCH),
                "--format", "json",
            ]
            if catchup:
                args += ["--jobage", str(CATCHUP_DAYS)]
            else:
                args += ["--jobage-minutes", str(LINKEDIN_DAILY_MINUTES)]
            if scope["remote"]:
                args += ["--remote", scope["remote"]]

            try:
                payload = run_json_command(MADS_REPO, args)
                for item in payload.get("results", []):
                    if isinstance(item, dict):
                        jobs.append(make_job("LinkedIn", scope["label"], query, item))
            except Exception as exc:
                print(f"  WARNING: LinkedIn failed for '{query}' / {scope['label']}: {exc}")
    return jobs


def collect_infojobs(catchup: bool) -> list[dict[str, str]]:
    jobs = []
    jobage = CATCHUP_DAYS if catchup else OTHER_DAILY_DAYS
    for query in QUERIES:
        print(f"InfoJobs      | Spain        | {query}")
        args = [
            str(INFOJOBS_CLI), "search",
            "-q", query,
            "--jobage", str(jobage),
            "--limit", str(LIMIT_PER_SEARCH),
            "--format", "json",
        ]
        try:
            payload = run_json_command(SPAIN_REPO, args)
            for item in payload.get("results", []):
                if isinstance(item, dict):
                    jobs.append(make_job("InfoJobs", "Spain", query, item))
        except Exception as exc:
            print(f"  WARNING: InfoJobs failed for '{query}': {exc}")
    return jobs


def collect_tecnoempleo(catchup: bool) -> list[dict[str, str]]:
    jobs = []
    jobage = CATCHUP_DAYS if catchup else OTHER_DAILY_DAYS
    for query in QUERIES:
        for province in TECNO_LOCATIONS:
            print(f"Tecnoempleo   | {province:<12} | {query}")
            args = [
                str(TECNO_CLI), "search",
                "-q", query,
                "-l", province,
                "--jobage", str(jobage),
                "--limit", str(LIMIT_PER_SEARCH),
                "--format", "json",
            ]
            try:
                payload = run_json_command(SPAIN_REPO, args)
                for item in payload.get("results", []):
                    if isinstance(item, dict):
                        jobs.append(make_job("Tecnoempleo", province, query, item))
            except Exception as exc:
                print(f"  WARNING: Tecnoempleo failed for '{query}' / {province}: {exc}")
    return jobs

def collect_getmanfred(catchup: bool) -> list[dict[str, str]]:
    """Curated Spain/remote-Europe tech jobs with salary transparency."""
    jobs = []
    jobage = CATCHUP_DAYS if catchup else OTHER_DAILY_DAYS

    # GetManfred's list API returns the whole active catalogue for non-tech queries,
    # so keep this deliberately compact.
    queries = ["data", "business intelligence", "power bi"]

    for query in queries:
        print(f"GetManfred    | Spain/EU     | {query}")
        args = [
            str(GETMANFRED_CLI), "search",
            "-q", query,
            "--jobage", str(jobage),
            "--limit", str(SUPPLEMENTARY_LIMIT),
            "--format", "json",
        ]
        try:
            payload = run_json_command(SPAIN_REPO, args)
            for item in payload.get("results", []):
                if isinstance(item, dict):
                    jobs.append(make_job("GetManfred", "Spain/Remote EU", query, item))
        except Exception as exc:
            print(f"  WARNING: GetManfred failed for '{query}': {exc}")
    return jobs


def collect_joppy(catchup: bool) -> list[dict[str, str]]:
    """Small, high-signal Spanish tech/startup corpus."""
    jobs = []
    jobage = CATCHUP_DAYS if catchup else OTHER_DAILY_DAYS

    for query in SUPPLEMENTARY_QUERIES:
        print(f"Joppy         | Spain        | {query}")
        args = [
            str(JOPPY_CLI), "search",
            "-q", query,
            "--jobage", str(jobage),
            "--limit", str(SUPPLEMENTARY_LIMIT),
            "--format", "json",
        ]
        try:
            payload = run_json_command(SPAIN_REPO, args)
            for item in payload.get("results", []):
                if isinstance(item, dict):
                    jobs.append(make_job("Joppy", "Spain", query, item))
        except Exception as exc:
            print(f"  WARNING: Joppy failed for '{query}': {exc}")
    return jobs


def collect_freehire(catchup: bool) -> list[dict[str, str]]:
    """Tech-focused aggregator over many ATS platforms; full JD is inline."""
    jobs = []
    jobage = CATCHUP_DAYS if catchup else OTHER_DAILY_DAYS

    for query in SUPPLEMENTARY_QUERIES:
        print(f"FreeHire      | Spain        | {query}")
        args = [
            str(FREEHIRE_CLI), "search",
            "-q", query,
            "--country", "ES",
            "--jobage", str(jobage),
            "--limit", str(LIMIT_PER_SEARCH),
            "--description-format", "text",
            "--format", "json",
        ]
        try:
            payload = run_json_command(SPAIN_REPO, args)
        except Exception as exc:
            # FreeHire has occasionally returned malformed large JSON payloads.
            # Retry once with a smaller page rather than silently losing the
            # whole query. The source remains best-effort if the retry also fails.
            retry_args = list(args)
            try:
                limit_index = retry_args.index("--limit") + 1
                retry_args[limit_index] = str(max(3, LIMIT_PER_SEARCH // 2))
            except ValueError:
                pass
            print(f"  WARNING: FreeHire first attempt failed for '{query}': {exc}; retrying smaller page")
            try:
                payload = run_json_command(SPAIN_REPO, retry_args)
                print(f"  FreeHire retry succeeded for '{query}'")
            except Exception as retry_exc:
                print(f"  WARNING: FreeHire failed for '{query}' after retry: {retry_exc}")
                continue

        for item in payload.get("results", []):
            if isinstance(item, dict):
                jobs.append(make_job("FreeHire", "Spain", query, item))
    return jobs


def deduplicate(jobs: list[dict[str, str]]) -> tuple[list[dict[str, str]], int, set[str]]:
    stage1 = {}
    for job in jobs:
        key = portal_identity(job)
        if key not in stage1:
            row = dict(job)
            row["sources_seen"] = job["source"]
            row["queries_seen"] = job["query_found_by"]
            row["urls_seen"] = job["url"]
            stage1[key] = row
        else:
            stage1[key]["queries_seen"] = merge_values(stage1[key]["queries_seen"], job["query_found_by"])
            stage1[key]["urls_seen"] = merge_values(stage1[key]["urls_seen"], job["url"])

    cross = {}
    for job in stage1.values():
        key = cross_portal_key(job)
        if key not in cross:
            cross[key] = dict(job)
        else:
            cross[key]["sources_seen"] = merge_values(cross[key]["sources_seen"], job["source"])
            cross[key]["queries_seen"] = merge_values(cross[key]["queries_seen"], job["queries_seen"])
            cross[key]["urls_seen"] = merge_values(cross[key]["urls_seen"], job["urls_seen"])

    unique = list(cross.values())
    return unique, len(jobs) - len(unique)

# ============================================================
# FIRST-PASS TITLE TRIAGE
# ============================================================

def classify_title(title: str) -> tuple[str, str]:
    t = normalize(title)

    # Recall-safe exceptions: these titles are adjacent enough to Data/BI that
    # generic "platform engineer" / "product owner" rules must not discard them
    # before the JD is read.
    recall_safe_title_patterns = [
        (
            r"\bdata platform engineer\b",
            "Data Platform Engineer is target-adjacent; full JD required",
        ),
        (
            r"\bdata product owner\b",
            "Data Product Owner is target-adjacent; full JD required",
        ),
        (
            r"\bproduct owner\b.*\banalytics\b|\banalytics\b.*\bproduct owner\b",
            "Analytics Product Owner is target-adjacent; full JD required",
        ),
        (
            r"\bsoftware engineer\b.*\bdata\b|\bdata\b.*\bsoftware engineer\b",
            "Software Engineer with explicit Data scope is target-adjacent; full JD required",
        ),
    ]
    for pattern, reason in recall_safe_title_patterns:
        if re.search(pattern, t):
            return "REVIEW", reason

    for pattern, reason in AUTO_SKIP_TITLE_PATTERNS:
        if re.search(pattern, t):
            return "AUTO_SKIP_TITLE", reason

    for pattern, reason in HIGH_TITLE_PATTERNS:
        if re.search(pattern, t):
            return "HIGH", reason

    for pattern, reason in REVIEW_TITLE_PATTERNS:
        if re.search(pattern, t):
            return "REVIEW", reason

    return "REVIEW", "Not an obvious mismatch; needs full-JD review"


def add_title_triage(jobs: list[dict[str, str]]) -> None:
    for job in jobs:
        bucket, reason = classify_title(job["title"])
        job["title_bucket"] = bucket
        job["title_reason"] = reason
        job["canonical_location"] = canonical_location(job["location"])

# ============================================================
# DETAIL CACHE / FETCH
# ============================================================

def detail_cache_key(job: dict[str, str]) -> str:
    source = clean_text(job.get("source"))
    identifier = clean_text(job.get("id")) or clean_text(job.get("url"))
    if identifier:
        return f"{source}::{identifier}"
    return f"fp::{stable_fingerprint(job)}"


def load_detail_cache() -> dict[str, str]:
    cache = {}
    paths = set()

    for pattern in [
        "*shortlist_full_*.csv",
        "*final_shortlist_full_*.csv",
        "*primary_shortlist_full_*.csv",
        "*primary_shortlist_full.csv",
    ]:
        paths.update(OUTPUT_DIR.rglob(pattern))

    for path in sorted(paths):
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    detail = clean_text(row.get("full_detail"))
                    status = clean_text(row.get("detail_status"))
                    if not detail or status not in {"OK", "CACHE", "INLINE"}:
                        continue

                    job = {
                        "source": clean_text(row.get("source")),
                        "id": clean_text(row.get("id")),
                        "url": clean_text(row.get("url")),
                        "company": clean_text(row.get("company")),
                        "title": clean_text(row.get("title")),
                        "location": clean_text(row.get("location")),
                    }
                    cache[detail_cache_key(job)] = detail
                    cache[f"fp::{stable_fingerprint(job)}"] = detail
        except Exception as exc:
            print(f"  WARNING: cache read failed for {path.name}: {exc}")

    return cache


def fetch_full_detail(job: dict[str, str]) -> tuple[str, str]:
    source = job["source"]
    identifier = job.get("id") or job.get("url")
    if not identifier:
        return "", "No job ID or URL available."

    if source == "LinkedIn":
        cwd = MADS_REPO
        args = [str(LINKEDIN_CLI), "detail", identifier, "--format", "plain"]
    elif source == "InfoJobs":
        cwd = SPAIN_REPO
        args = [str(INFOJOBS_CLI), "detail", identifier, "--format", "plain"]
    elif source == "Tecnoempleo":
        cwd = SPAIN_REPO
        args = [str(TECNO_CLI), "detail", identifier, "--format", "plain"]
    elif source == "GetManfred":
        cwd = SPAIN_REPO
        args = [str(GETMANFRED_CLI), "detail", identifier, "--format", "plain"]
    elif source == "Joppy":
        cwd = SPAIN_REPO
        args = [str(JOPPY_CLI), "detail", identifier, "--format", "plain"]
    elif source == "FreeHire":
        cwd = SPAIN_REPO
        args = [str(FREEHIRE_CLI), "detail", identifier, "--format", "plain"]
    else:
        return "", f"Unsupported source: {source}"

    try:
        return run_plain_command(cwd, args), ""
    except Exception as exc:
        return "", str(exc)


def attach_details(
    jobs: list[dict[str, str]],
    cache: dict[str, str],
    detail_limit: int,
) -> tuple[int, int, int, int]:
    cache_hits = inline_hits = fetched = failed = fresh_requests = 0

    for job in jobs:
        key = detail_cache_key(job)
        fp = f"fp::{stable_fingerprint(job)}"

        inline = clean_text(job.get("preloaded_detail"))

        def _freehire_summary_only(value: str) -> bool:
            if job.get("source") != "FreeHire" or not value:
                return False
            if len(value) >= 550:
                return False
            lower_value = normalize(value)
            return count_patterns(
                lower_value,
                [
                    r"\brequires?\b|\brequired\b|\brequirements?\b",
                    r"\brequisitos?\b|\bimprescindible\b",
                    r"\bexperience\b|\bexperiencia\b",
                    r"\bideal candidate\b|\bwhat you.ll need\b|\bwhat we.re looking for\b",
                ],
            ) == 0

        if inline and not _freehire_summary_only(inline):
            job["full_detail"] = inline
            job["detail_status"] = "INLINE"
            cache[key] = inline
            cache[fp] = inline
            inline_hits += 1
            continue

        cached_detail = cache.get(key) or cache.get(fp) or ""
        if cached_detail and not _freehire_summary_only(cached_detail):
            job["full_detail"] = cached_detail
            job["detail_status"] = "CACHE"
            cache_hits += 1
            continue

        if fresh_requests >= detail_limit:
            job["full_detail"] = ""
            job["detail_status"] = "NOT_FETCHED_LIMIT"
            continue

        print(f"Detail         | {job['source']:<12} | {job['company']} — {job['title']}")
        detail, error = fetch_full_detail(job)
        fresh_requests += 1

        if detail:
            job["full_detail"] = detail
            job["detail_status"] = "OK"
            cache[key] = detail
            cache[fp] = detail
            fetched += 1
        else:
            job["full_detail"] = ""
            job["detail_status"] = "FAILED"
            job["detail_error"] = error
            failed += 1

    return cache_hits, inline_hits, fetched, failed


def _detail_similarity_text(value: str) -> str:
    value = normalize(value)
    # URLs/contact boilerplate differ frequently between duplicate portal copies.
    value = re.sub(r"https?://\\S+", " ", value)
    value = re.sub(r"\\bjob id\\s*[:#]?\\s*[a-z0-9-]+", " ", value)
    return re.sub(r"\\s+", " ", value).strip()


def deduplicate_near_identical_details(
    jobs: list[dict[str, str]],
) -> tuple[list[dict[str, str]], int, set[str]]:
    """Merge same-company/same-title copies when their fetched JDs are effectively identical.

    This catches reposted LinkedIn IDs and cross-portal copies without collapsing
    genuinely different openings that merely share a title.
    """
    from difflib import SequenceMatcher

    kept: list[dict[str, str]] = []
    removed = 0
    dropped_fingerprints: set[str] = set()

    for job in jobs:
        company = normalize(job.get("company", ""))
        title = normalize(job.get("title", ""))
        detail = _detail_similarity_text(job.get("full_detail", ""))

        merged = False
        if company and title and len(detail) >= 300:
            for existing in kept:
                if normalize(existing.get("company", "")) != company:
                    continue
                if normalize(existing.get("title", "")) != title:
                    continue

                other = _detail_similarity_text(existing.get("full_detail", ""))
                if len(other) < 300:
                    continue

                # Compare a bounded prefix for predictable runtime.
                ratio = SequenceMatcher(None, detail[:16000], other[:16000]).ratio()
                if ratio >= 0.93:
                    existing["sources_seen"] = merge_values(
                        existing.get("sources_seen", existing.get("source", "")),
                        job.get("sources_seen", job.get("source", "")),
                    )
                    existing["queries_seen"] = merge_values(
                        existing.get("queries_seen", ""),
                        job.get("queries_seen", job.get("query_found_by", "")),
                    )
                    existing["urls_seen"] = merge_values(
                        existing.get("urls_seen", existing.get("url", "")),
                        job.get("urls_seen", job.get("url", "")),
                    )
                    dropped_fingerprints.add(stable_fingerprint(job))
                    removed += 1
                    merged = True
                    break

        if not merged:
            kept.append(job)

    return kept, removed, dropped_fingerprints


# ============================================================
# SECOND-PASS JD CLASSIFICATION
# ============================================================

def has_actionable_detail(job: dict[str, str]) -> bool:
    """Reject metadata-only/boilerplate bodies from normal classification."""
    detail = clean_text(job.get("full_detail"))
    if not detail:
        return False

    lower = normalize(detail)
    tech = matched_named_signals(lower, TARGET_TECH_SIGNALS)

    # Short FreeHire bodies are often portal summaries rather than full JDs.
    # They may be useful for discovery, but should not be treated as complete
    # enough for final Primary classification when candidate requirements are absent.
    if job.get("source") == "FreeHire" and len(detail) < 550:
        requirement_signal = count_patterns(
            lower,
            [
                r"\brequires?\b|\brequired\b|\brequirements?\b",
                r"\brequisitos?\b|\bimprescindible\b",
                r"\bexperience\b|\bexperiencia\b",
                r"\bideal candidate\b|\bwhat you.ll need\b|\bwhat we.re looking for\b",
            ],
        )
        if requirement_signal == 0:
            return False

    if len(detail) < 450 and not tech:
        concrete = count_patterns(
            lower,
            [
                r"\brequirements?\b|\brequisitos?\b",
                r"\bresponsibilit(?:y|ies)\b|\bfunciones\b",
                r"\bwhat we.re looking for\b|\bwhat you.ll need\b",
                r"\bexperience\b|\bexperiencia\b",
            ],
        )
        if concrete == 0:
            return False

    # LinkedIn sometimes returns only the job header/status with no posting body.
    if (
        len(detail) < 650
        and "status: active" in lower
        and not tech
        and count_patterns(lower, [r"\brequirements?\b", r"\bresponsibilit", r"\bexperience\b"]) == 0
    ):
        return False

    return True



def evaluate_full_jd(job: dict[str, str]) -> tuple[str, list[str], list[str], list[str]]:
    title = normalize(job.get("title", ""))
    detail = clean_text(job.get("full_detail"))
    text = f"{job.get('title', '')}\n{detail}"
    lower = text.lower()

    fit = []
    blockers = []
    low_reasons = []

    if not detail:
        return "REVIEW", ["Full JD unavailable"], [], ["Needs manual review"]

    min_years = extract_min_required_years(lower)
    tech = matched_named_signals(lower, TARGET_TECH_SIGNALS)
    heavy = matched_named_signals(lower, HEAVY_ENGINEERING_SIGNALS)
    content = matched_named_signals(lower, CONTENT_SIGNALS)

    if tech:
        fit.append("Target tech: " + ", ".join(tech[:10]))
    if content and re.search(r"\bcontent\b|\blists analyst\b", title):
        fit.append("Content/research signals: " + ", ".join(content))

    # ---------- HARD BLOCKERS ----------
    # Internship/apprenticeship is intentionally NOT a hard blocker.
    # Human calibration treats it as a moderate employment-fit penalty only;
    # keep these roles reviewable so Scoring V1 can rank them later.

    if any(re.search(p, lower, re.I) for p in US_WORK_AUTH_PATTERNS):
        blockers.append("Requires US work authorization")

    if any(re.search(p, lower, re.I) for p in CATALAN_HARD_PATTERNS):
        blockers.append("Mandatory native/bilingual/C2 Catalan")

    if any(re.search(p, lower, re.I) for p in NON_TARGET_LANGUAGE_HARD_PATTERNS):
        blockers.append("Mandatory non-target language requirement")

    if any(re.search(p, lower, re.I) for p in NON_TARGET_REQUIRED_TOOL_SIGNALS):
        blockers.append("Requires specialist CRM platform experience outside target profile")

    explicit_onsite_mismatch = explicit_outside_target_onsite(detail)
    location_conflict = bool(explicit_onsite_mismatch)

    clinical_count = count_patterns(lower, CLINICAL_HARD_SIGNALS)
    if re.search(r"\bclinical\b", title) and clinical_count >= 2:
        blockers.append("Clinical-data specialization required")

    is_data_architect = bool(
        re.search(r"\bdata architect\b|\benterprise data architect\b|\bbig data architect\b", title)
    )

    is_data_engineer = bool(re.search(r"\bdata engineer\b|\bingeniero\b.*\bdatos\b", title))
    # 5+ years specifically in sanctions data is a hard domain mismatch.
    if count_patterns(lower, SANCTIONS_SPECIALIST_SIGNALS) >= 1 and min_years is not None and min_years >= 5:
        blockers.append("Requires 5+ years sanctions-data experience")

    # Workday-specialized + 5+ years is too specific.
    if count_patterns(lower, WORKDAY_REQUIRED) >= 1 and min_years is not None and min_years >= 5:
        blockers.append("Requires senior Workday/data-governance specialization")

    if blockers:
        return "AUTO_SKIP_JD", fit, blockers, low_reasons

    # ---------- LOW PRIORITY, NOT DELETED ----------
    seniorish = bool(re.search(r"\bsenior\b|\bsr\b|\bprincipal\b|\blead\b|\bhead\b|\bexpert\b|\bmanager\b|\bgerente\b|\bdirector\b", title))

    if re.search(r"\bprincipal\b", title):
        low_reasons.append("Principal-level role")

    if re.search(r"\bdirector\b|\bhead of\b", title):
        low_reasons.append("Director/head-level role outside target seniority")

    if re.search(r"\bmanager\b|\bgerente\b", title):
        leadership_count = count_patterns(lower, MANAGERIAL_LEADERSHIP_SIGNALS)
        if (min_years is not None and min_years >= 4) or leadership_count >= 1:
            low_reasons.append("Managerial/service-leadership role rather than hands-on analyst role")

    if re.search(r"\blead\b", title):
        low_reasons.append("Lead-level role outside target seniority")

    if seniorish and min_years is not None and min_years >= 4:
        low_reasons.append(f"Senior/expert-level role requiring at least {min_years:g} years")

    # Data Architect is target-adjacent, not a hard mismatch. Keep junior/unclear
    # cases reviewable, but demote clearly senior architecture requirements.
    if is_data_architect and min_years is not None and min_years >= 4:
        low_reasons.append(f"Data Architect role requiring at least {min_years:g} years")

    # Procurement roles occasionally contain "data quality" or "reporting" and
    # otherwise look analytical by keyword. Keep them visible but out of Primary
    # unless they have a real analytical core.
    analytics_core = [
        name for name in tech
        if name in {"sql", "python", "power_bi", "tableau", "looker", "dbt", "bigquery", "snowflake", "data_modeling", "dashboard"}
    ]
    if (
        re.search(r"\bprocurement\b|\bpurchasing\b", title)
        and count_patterns(lower, PROCUREMENT_DOMAIN_SIGNALS) >= 2
        and len(analytics_core) <= 1
    ):
        low_reasons.append("Procurement-domain role with limited hands-on analytics core")

    # Data Scientist titles are no longer auto-skipped. Only genuinely senior or
    # ML-engineering-heavy DS roles are demoted after reading the JD.
    if re.search(r"\bdata scientist\b", title):
        ml_eng_count = count_patterns(lower, ML_ENGINEERING_SIGNALS)
        if min_years is not None and min_years >= 4:
            low_reasons.append(f"Data Scientist role requiring at least {min_years:g} years")

    if (
        re.search(r"\bdata steward\b", title)
        and min_years is not None
        and min_years >= 5
        and re.search(r"\binformatica\b|\bidmc\b|\bdatabricks\b", lower)
    ):
        low_reasons.append("Senior specialist Data Steward stack (5+ years / Informatica-IDMC/Databricks)")

    # Data Engineer is not a blanket penalty anymore. Light/junior DE roles with
    # strong BI/analytics overlap remain Review; senior/pure engineering roles fall.
    if is_data_engineer and not re.search(r"\banalytics engineer\b", title):
        bi_overlap = [
            name for name in tech
            if name in {"power_bi", "tableau", "looker", "dashboard", "reporting", "data_quality", "data_modeling"}
        ]
        if min_years is not None and min_years >= 4:
            low_reasons.append(f"Data Engineer role requiring at least {min_years:g} years")
        elif not bi_overlap and len(heavy) >= 3:
            low_reasons.append("Data Engineer role with strongly engineering-heavy stack")

    # Explicit ML Engineer / production-model roles are outside the intended DS
    # expansion. Marketing/product-facing Data Scientist roles remain eligible.
    if re.search(r"\bml engineer\b|\bmachine learning engineer\b", title):
        low_reasons.append("ML Engineer / production-model role rather than target analytics")

    if (
        re.search(r"\bdata science\b.*\bmachine learning\b", title)
        and count_patterns(lower, [r"\bdeployment\b|\bdespliegue\b", r"\bdatabricks\b", r"\bpyspark\b"]) >= 2
    ):
        low_reasons.append("Production ML / advanced Data Science specialization")

    if (
        re.search(r"\bdata scientist\b", title)
        and (
            (
                count_patterns(lower, ML_LIFECYCLE_SIGNALS) >= 4
                and count_patterns(lower, [r"\bdeployment\b|\bdeploy\b|\bpuesta en producci[oó]n\b|\bproducci[oó]n de modelos\b"]) >= 1
            )
            or (
                count_patterns(lower, [r"\btensorflow\b|\bpytorch\b"]) >= 1
                and count_patterns(lower, [r"\bdatabricks\b"]) >= 1
                and count_patterns(lower, [r"\bdespliegue\b|\bpuesta en producci[oó]n\b|\bmodelos desplegados\b"]) >= 1
            )
        )
    ):
        low_reasons.append("Data Scientist role centered on production ML lifecycle")

    if (
        re.search(r"\bgraph data engineer\b", title)
        and count_patterns(lower, GRAPH_ENGINEERING_SIGNALS) >= 2
    ):
        low_reasons.append("Specialized graph-data engineering role")

    if (
        count_patterns(lower, SECURITY_ANALYTICS_SPECIALIST_SIGNALS) >= 3
        and count_patterns(lower, MANAGERIAL_LEADERSHIP_SIGNALS) >= 1
    ):
        low_reasons.append("Security-analytics leadership specialization")

    if (
        re.search(r"\bmarket risk\b", title)
        and count_patterns(lower, [r"\bvar\b", r"\bvalue at risk\b", r"\bsensitivities\b|\bsensibilidades\b"]) >= 1
    ):
        low_reasons.append("Specialized market-risk data role")

    # BA/consulting roles with explicit multi-year pharma/biotech specialization
    # are domain-mismatched even if they contain generic data keywords.
    if (
        re.search(r"\bbusiness analyst\b|\bconsultant\b", title)
        and count_patterns(lower, PHARMA_SPECIALIST_PATTERNS) >= 1
    ):
        low_reasons.append("Requires specialized pharma/biotech experience")

    # Controlling/finance-transformation roles can contain BI keywords but are not
    # core Data/BI jobs for this search.
    if (
        re.search(r"\bcontrolling\b", title)
        and count_patterns(lower, CONTROLLING_DOMAIN_SIGNALS) >= 2
    ):
        low_reasons.append("Controlling/finance-domain role rather than core Data/BI")

    # FreeHire crawls whole career sites. If a title did not match any target
    # family at title stage and the JD has only weak analytics overlap, keep it
    # out of the daily Primary shortlist.
    if (
        job.get("source") == "FreeHire"
        and job.get("title_reason") == "Not an obvious mismatch; needs full-JD review"
        and len(analytics_core) < 2
    ):
        low_reasons.append("Supplementary-source role with weak analytics alignment")

    if count_patterns(lower, SAP_REQUIRED) >= 2:
        low_reasons.append("Requires SAP BW/HANA/Analytics Cloud specialization")

    if count_patterns(lower, ORACLE_BI_REQUIRED) >= 2:
        low_reasons.append("Requires Oracle BI / PowerCenter specialization")

    remote_context = f"{job.get('title', '')}\n{detail}"
    if outside_target_location_penalty(job, remote_context) and not location_conflict:
        low_reasons.append("On-site/hybrid location outside Catalunya without clear Spain-remote option")

    # Senior consulting leadership.
    if re.search(r"\bsenior data consultant\b", title) and (
        re.search(r"\bmentor", lower) or re.search(r"\blead(?:ing)? small (?:team|squad)", lower)
    ):
        low_reasons.append("Senior consulting role with team leadership")

    if low_reasons:
        return "LOW_PRIORITY", fit or ["Some relevant overlap"], [], low_reasons

    if location_conflict:
        return "REVIEW", (fit or ["Relevant role"]) + [f"Location conflict to verify: {explicit_onsite_mismatch}"], [], []

    # Senior target-family roles without a stronger mismatch are retained for
    # human review rather than promoted to HIGH or demoted solely for seniority.
    if re.search(r"\bsenior\b|\bsr\b", title):
        return "REVIEW", fit or ["Senior target role; human review required"], [], []

    # ---------- HIGH ----------
    if re.search(r"\bcontent quality analyst\b", title):
        return "HIGH", fit or ["Content Quality target family"], [], []

    if re.search(r"\bglobal business intelligence senior analyst\b", title):
        if min_years is None or min_years <= 3:
            return "HIGH", fit or ["Strong BI target role"], [], []

    if job.get("title_bucket") == "HIGH" and len(tech) >= 1:
        return "HIGH", fit, [], []

    if re.search(r"\btechnical analyst\b", title) and len(tech) >= 4 and (min_years is None or min_years <= 3):
        return "HIGH", fit, [], []

    if re.search(r"\bdata consultant\b", title) and not seniorish and len(tech) >= 3:
        return "HIGH", fit, [], []

    if re.search(r"\brevops\b|\brevenue operations\b", title) and len(tech) >= 2:
        return "HIGH", fit, [], []

    if re.search(r"\bbusiness analyst\b", title) and len(tech) >= 2 and (min_years is None or min_years <= 3):
        return "HIGH", fit, [], []

    if re.search(r"\bpricing analyst\b", title) and len(tech) >= 1 and (min_years is None or min_years <= 3):
        return "HIGH", fit, [], []

    if re.search(r"\bjunior data & analytics product specialist\b", title):
        return "HIGH", fit, [], []

    # ---------- REVIEW ----------
    return "REVIEW", fit or ["No hard blocker detected"], [], []


def apply_full_jd_rules(jobs: list[dict[str, str]]) -> None:
    for job in jobs:
        bucket, fit, blockers, low_reasons = evaluate_full_jd(job)
        job["final_bucket"] = bucket
        job["jd_fit_signals"] = "; ".join(fit)
        job["jd_blockers"] = "; ".join(blockers)
        job["low_priority_reasons"] = "; ".join(low_reasons)

# ============================================================
# SEEN STATE
# ============================================================

def load_seen() -> dict[str, str]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(payload, dict) and isinstance(payload.get("items"), dict):
        return {str(k): str(v) for k, v in payload["items"].items()}
    return {}


def save_seen(seen: dict[str, str]) -> None:
    payload = {
        "updated": local_today().isoformat(),
        "retention_days": SEEN_RETENTION_DAYS,
        "items": seen,
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def prune_seen(seen: dict[str, str]) -> dict[str, str]:
    cutoff = local_today() - timedelta(days=SEEN_RETENTION_DAYS)
    kept = {}
    for fp, last_seen in seen.items():
        try:
            d = date.fromisoformat(last_seen)
        except ValueError:
            continue
        if d >= cutoff:
            kept[fp] = last_seen
    return kept


def seed_from_previous_outputs() -> int:
    if STATE_FILE.exists():
        return 0

    seen = {}
    paths = set()
    for pattern in [
        "daily_jobs_*.csv",
        "all_current_*.csv",
        "new_jobs_*.csv",
        "daily_all_current_*.csv",
        "daily_new_jobs_*.csv",
        "*reprocess_all_current_*.csv",
        "all_current.csv",
        "catchup_all_current.csv",
        "reprocess_all_current.csv",
    ]:
        paths.update(OUTPUT_DIR.rglob(pattern))

    for path in sorted(paths):
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as f:
                for row in csv.DictReader(f):
                    job = {
                        "source": clean_text(row.get("source")),
                        "id": clean_text(row.get("id")),
                        "url": clean_text(row.get("url")),
                        "company": clean_text(row.get("company")),
                        "title": clean_text(row.get("title")),
                        "location": clean_text(row.get("location")),
                    }
                    seen[stable_fingerprint(job)] = local_today().isoformat()
        except Exception as exc:
            print(f"  WARNING: could not seed from {path.name}: {exc}")

    if seen:
        save_seen(seen)
    return len(seen)

# ============================================================
# OUTPUT
# ============================================================

def sort_key(job: dict[str, str]) -> tuple[int, int, str, str]:
    order = {
        "HIGH": 0,
        "REVIEW": 1,
        "LOW_PRIORITY": 2,
        "NEEDS_DETAIL": 3,
        "AUTO_SKIP_JD": 4,
        "AUTO_SKIP_TITLE": 5,
    }
    try:
        score = int(float(job.get("score_v2") or -1))
    except Exception:
        score = -1
    return (
        order.get(job.get("final_bucket") or job.get("title_bucket") or "", 99),
        -score,
        normalize(job.get("title", "")),
        normalize(job.get("company", "")),
    )


def primary_score_sort_key(job: dict[str, str]) -> tuple[int, int, str, str]:
    """Rank the recall-safe Primary set by Scoring V2 without changing buckets.

    V2 is the active ranking key; V6.4 bucket is only a tie-breaker.
    V1 is retained in the output for week-over-week comparison.
    """
    try:
        score = int(float(job.get("score_v2") or -1))
    except Exception:
        score = -1
    bucket_tie = 0 if job.get("final_bucket") == "HIGH" else 1
    return (-score, bucket_tie, normalize(job.get("title", "")), normalize(job.get("company", "")))


def write_csv(path: Path, rows: list[dict[str, str]], include_detail: bool = False) -> None:
    fieldnames = [
        "final_bucket",
        "score_v2",
        "score_band_v2",
        "scoring_version_v2",
        "score_v2_role_family",
        "score_v2_geography_fit",
        "score_v2_years_required",
        "score_v2_skill_count",
        "score_v2_skill_signals",
        "score_v2_role_points",
        "score_v2_skill_points",
        "score_v2_experience_points",
        "score_v2_geography_points",
        "score_v2_domain_points",
        "score_v2_seniority_points",
        "score_v2_employment_points",
        "score_v2_evidence_points",
        "score_v2_penalty",
        "score_v2_penalty_reasons",
        "score_v1",
        "score_band_v1",
        "scoring_version",
        "score_role_family",
        "score_geography_fit",
        "score_years_required",
        "score_skill_count",
        "score_skill_signals",
        "score_role_points",
        "score_skill_points",
        "score_experience_points",
        "score_geography_points",
        "score_domain_points",
        "score_seniority_points",
        "score_employment_points",
        "score_evidence_points",
        "score_penalty",
        "score_penalty_reasons",
        "jd_fit_signals",
        "jd_blockers",
        "low_priority_reasons",
        "title_bucket",
        "title_reason",
        "source",
        "sources_seen",
        "search_scope",
        "title",
        "company",
        "location",
        "canonical_location",
        "modality",
        "salary",
        "salary_min",
        "salary_max",
        "date",
        "id",
        "url",
        "queries_seen",
        "urls_seen",
        "detail_status",
    ]
    if include_detail:
        fieldnames.append("full_detail")

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, jobs: list[dict[str, str]], title: str) -> None:
    parts = [f"# {title} — {local_today().isoformat()}", ""]
    for job in jobs:
        parts.extend([
            "---", "",
            f"## {job['title']} — {job['company']}", "",
            f"- Bucket: {job['final_bucket']}",
            f"- Score V2: {job.get('score_v2', 'N/A')} ({job.get('score_band_v2', 'N/A')})",
            f"- V2 penalties: {job.get('score_v2_penalty_reasons') or 'None'}",
            f"- Legacy Score V1: {job.get('score_v1', 'N/A')} ({job.get('score_band_v1', 'N/A')})",
            f"- Source: {job['source']}",
            f"- Location: {job['location']}",
            f"- Modality: {job['modality']}",
            f"- Salary: {job.get('salary') or (str(job.get('salary_min', '')) + '–' + str(job.get('salary_max', ''))).strip('–') or 'Not stated'}",
            f"- Posted: {job['date']}",
            f"- Fit signals: {job['jd_fit_signals'] or 'None'}",
            f"- Blockers: {job['jd_blockers'] or 'None'}",
            f"- Low-priority reasons: {job['low_priority_reasons'] or 'None'}",
            f"- URL: {job['url']}", "",
            "### Full posting", "",
            job.get("full_detail") or "[Full detail unavailable]", "",
        ])
    path.write_text("\n".join(parts), encoding="utf-8")

# ============================================================
# MAIN
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="V6.4 job discovery: expanded sources -> dedupe -> full JD -> HIGH/REVIEW/LOW/AUTO-SKIP."
    )
    parser.add_argument("--catchup", action="store_true")
    parser.add_argument(
        "--reprocess-current",
        action="store_true",
        help="Test current search window again; does not update seen-state.",
    )
    parser.add_argument("--show-all", action="store_true")
    parser.add_argument("--detail-limit", type=int, default=DEFAULT_DETAIL_LIMIT)
    args = parser.parse_args()

    if args.detail_limit < 0:
        fail("--detail-limit must be >= 0")

    check_setup()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    seeded = seed_from_previous_outputs()
    seen = prune_seen(load_seen())
    cache = load_detail_cache()

    print("\n=== JOB DISCOVERY V6.4 ===")
    print("Mode:", "CATCHUP" if args.catchup else "DAILY",
          "+ REPROCESS CURRENT" if args.reprocess_current else "")
    print(f"Queries: {len(QUERIES)}")
    print(f"Detail cache entries: {len(cache)}")
    if seeded:
        print(f"Seeded seen-state: {seeded}")
    print(f"Active seen fingerprints: {len(seen)}")
    print()

    all_jobs = []
    all_jobs.extend(collect_linkedin(args.catchup))
    all_jobs.extend(collect_infojobs(args.catchup))
    all_jobs.extend(collect_tecnoempleo(args.catchup))
    all_jobs.extend(collect_getmanfred(args.catchup))
    all_jobs.extend(collect_joppy(args.catchup))
    all_jobs.extend(collect_freehire(args.catchup))

    unique_jobs, duplicate_count = deduplicate(all_jobs)
    add_title_triage(unique_jobs)

    if args.reprocess_current:
        working = list(unique_jobs)
    else:
        working = [j for j in unique_jobs if stable_fingerprint(j) not in seen]

    title_skipped = [j for j in working if j["title_bucket"] == "AUTO_SKIP_TITLE"]
    detail_candidates = [j for j in working if j["title_bucket"] != "AUTO_SKIP_TITLE"]

    # Fetch likely target titles first so a noisy REVIEW tail cannot consume the
    # whole detail budget.
    detail_candidates.sort(
        key=lambda j: (
            0 if j.get("title_bucket") == "HIGH" else 1,
            normalize(j.get("title", "")),
            normalize(j.get("company", "")),
        )
    )

    cache_hits, inline_hits, fetched, failed = attach_details(detail_candidates, cache, args.detail_limit)

    # A second, JD-aware dedup catches reposts with different portal IDs.
    detail_candidates, near_detail_duplicates, near_dropped_fps = deduplicate_near_identical_details(detail_candidates)

    # Keep the master "all_current" grain aligned with the post-JD canonical set.
    canonical_unique_jobs = [
        j for j in unique_jobs
        if stable_fingerprint(j) not in near_dropped_fps
    ]

    apply_full_jd_rules(detail_candidates)

    # A job without a fetched/cached JD must NOT pollute the Primary shortlist.
    # Keep it in a separate file for manual/detail retry review.
    needs_detail = [
        j for j in detail_candidates
        if not has_actionable_detail(j)
    ]
    classified = [
        j for j in detail_candidates
        if has_actionable_detail(j)
    ]

    for j in needs_detail:
        if clean_text(j.get("full_detail")):
            j["detail_status"] = "INSUFFICIENT_DETAIL"
        j["final_bucket"] = "NEEDS_DETAIL"
        j["jd_fit_signals"] = j.get("jd_fit_signals", "")
        j["jd_blockers"] = j.get("jd_blockers", "")
        j["low_priority_reasons"] = "Insufficient actionable JD for automated classification"

    # Fill fields for title-skipped rows before scoring so every canonical row
    # receives a transparent score, even though scores never change V6.4 buckets.
    for j in title_skipped:
        j["final_bucket"] = "AUTO_SKIP_TITLE"
        j["jd_fit_signals"] = ""
        j["jd_blockers"] = ""
        j["low_priority_reasons"] = ""
        j["detail_status"] = ""

    # Both scorers are ranking-only layers. V6.4 remains authoritative and
    # neither scorer may promote/demote buckets or create AUTO_SKIP.
    # V1 is retained as the legacy comparator; V2 is the active ranker.
    scored_rows = classified + needs_detail + title_skipped
    apply_scoring_v1(scored_rows)
    apply_scoring_v2(scored_rows)

    high = [j for j in classified if j["final_bucket"] == "HIGH"]
    review = [j for j in classified if j["final_bucket"] == "REVIEW"]
    low = [j for j in classified if j["final_bucket"] == "LOW_PRIORITY"]
    jd_skipped = [j for j in classified if j["final_bucket"] == "AUTO_SKIP_JD"]

    primary = high + review
    primary.sort(key=primary_score_sort_key)
    low.sort(key=sort_key)
    jd_skipped.sort(key=sort_key)
    needs_detail.sort(key=sort_key)
    title_skipped.sort(key=sort_key)

    if not args.reprocess_current:
        today = local_today().isoformat()
        for j in canonical_unique_jobs:
            seen[stable_fingerprint(j)] = today
        save_seen(seen)

    stamp = local_today().isoformat()

    # Store each day's outputs in its own dated folder.
    day_dir = OUTPUT_DIR / stamp
    day_dir.mkdir(parents=True, exist_ok=True)

    # Normal daily runs use clean filenames.
    # Catch-up and reprocess runs get a prefix so they do not overwrite daily files.
    if args.reprocess_current:
        file_prefix = "reprocess_"
    elif args.catchup:
        file_prefix = "catchup_"
    else:
        file_prefix = ""

    primary_csv = day_dir / f"{file_prefix}primary_shortlist.csv"
    primary_full_csv = day_dir / f"{file_prefix}primary_shortlist_full.csv"
    primary_md = day_dir / f"{file_prefix}primary_shortlist_full.md"
    low_csv = day_dir / f"{file_prefix}low_priority.csv"
    skip_csv = day_dir / f"{file_prefix}auto_skipped.csv"
    needs_detail_csv = day_dir / f"{file_prefix}needs_detail_review.csv"

    write_csv(primary_csv, primary)
    write_csv(primary_full_csv, primary, include_detail=True)
    write_markdown(primary_md, primary, "Primary Job Shortlist")
    write_csv(low_csv, low, include_detail=True)
    write_csv(skip_csv, jd_skipped + title_skipped, include_detail=True)
    write_csv(needs_detail_csv, needs_detail, include_detail=False)

    all_path = None
    if args.show_all:
        for j in canonical_unique_jobs:
            j.setdefault("final_bucket", j.get("title_bucket", ""))
            j.setdefault("jd_fit_signals", "")
            j.setdefault("jd_blockers", "")
            j.setdefault("low_priority_reasons", "")
            j.setdefault("detail_status", "")
        missing_v1_scores = [j for j in canonical_unique_jobs if not clean_text(j.get("score_v1"))]
        if missing_v1_scores:
            apply_scoring_v1(missing_v1_scores)
        missing_v2_scores = [j for j in canonical_unique_jobs if not clean_text(j.get("score_v2"))]
        if missing_v2_scores:
            apply_scoring_v2(missing_v2_scores)
        all_path = day_dir / f"{file_prefix}all_current.csv"
        write_csv(all_path, canonical_unique_jobs)

    counts = Counter(j["source"] for j in all_jobs)

    print("\n=== SUMMARY ===")
    print(f"Raw results:          {len(all_jobs)}")
    print(f"  LinkedIn:           {counts.get('LinkedIn', 0)}")
    print(f"  InfoJobs:           {counts.get('InfoJobs', 0)}")
    print(f"  Tecnoempleo:        {counts.get('Tecnoempleo', 0)}")
    print(f"  GetManfred:         {counts.get('GetManfred', 0)}")
    print(f"  Joppy:              {counts.get('Joppy', 0)}")
    print(f"  FreeHire:           {counts.get('FreeHire', 0)}")
    print(f"Duplicates removed:   {duplicate_count}")
    print(f"Near-JD duplicates:   {near_detail_duplicates}")
    print(f"Unique pre-JD:        {len(unique_jobs)}")
    print(f"Canonical current:    {len(canonical_unique_jobs)}")
    print(f"Working jobs:         {len(working)}")
    print(f"Title auto-skip:      {len(title_skipped)}")
    print(f"Detail candidates:    {len(detail_candidates)}")
    print(f"Detail cache hits:    {cache_hits}")
    print(f"Inline full JDs:      {inline_hits}")
    print(f"Fresh details:        {fetched}")
    print(f"Detail failures:      {failed}")
    print(f"Needs detail review:  {len(needs_detail)}")
    print(f"JD auto-skip:         {len(jd_skipped)}")
    print(f"LOW PRIORITY:         {len(low)}")
    print(f"HIGH:                 {len(high)}")
    print(f"REVIEW:               {len(review)}")
    print(f"PRIMARY SHORTLIST:    {len(primary)}")
    primary_v2_bands = Counter(j.get("score_band_v2", "") for j in primary)
    primary_v1_bands = Counter(j.get("score_band_v1", "") for j in primary)
    print(f"Scoring layer:        {SCORING_VERSION_V2} (active ranking only; V6.4 buckets unchanged)")
    print(f"Legacy comparator:    {SCORING_VERSION_V1}")
    print(
        "Primary V2 bands:     "
        f"HIGH={primary_v2_bands.get('HIGH', 0)} "
        f"REVIEW={primary_v2_bands.get('REVIEW', 0)} "
        f"LOW_SCORE={primary_v2_bands.get('LOW_SCORE', 0)} "
        f"VERY_LOW_SCORE={primary_v2_bands.get('VERY_LOW_SCORE', 0)}"
    )
    print(
        "Primary V1 bands:     "
        f"HIGH={primary_v1_bands.get('HIGH', 0)} "
        f"REVIEW={primary_v1_bands.get('REVIEW', 0)} "
        f"LOW_SCORE={primary_v1_bands.get('LOW_SCORE', 0)} "
        f"VERY_LOW_SCORE={primary_v1_bands.get('VERY_LOW_SCORE', 0)}"
    )

    print("\nFiles:")
    print(f"  Output folder:      {day_dir}")
    print(f"  Primary shortlist:  {primary_csv}")
    print(f"  Primary full CSV:   {primary_full_csv}")
    print(f"  Primary full MD:    {primary_md}")
    print(f"  Low priority:       {low_csv}")
    print(f"  Auto-skipped:       {skip_csv}")
    print(f"  Needs detail:       {needs_detail_csv}")
    if all_path:
        print(f"  All current:        {all_path}")

    if args.reprocess_current:
        print("\nTEST MODE: seen-state was not updated.")
    else:
        print("\nNormal daily use:")
        print("  python jobs_v6_4_recall_guard.py")
        print("Catch-up:")
        print("  python jobs_v6_4_recall_guard.py --catchup")

    print("\nUpload primary_shortlist_full_*.md to ChatGPT for final Apply/Skip evaluation.")


if __name__ == "__main__":
    main()
