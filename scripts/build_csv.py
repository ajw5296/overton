"""
Build CSV from Overton child welfare JSON export.

Reads the 44K-document JSON, computes local fields (regulatory action, state,
citation counts), queries the Overton API for each URE boolean type, and writes
a combined CSV.

URE API queries use checkpoint/cache files so interrupted runs can resume.
"""

import csv
import json
import math
import os
import re
import time

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("OVERTON_API_KEY", "7cb1b1-daf77f-94ed27")
DOCUMENTS_URL = "https://app.overton.io/documents.php"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "overton_exports")
INPUT_FILE = os.path.join(DATA_DIR, "us_gov_child_welfare_2023_2025.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "us_gov_child_welfare_2023_2025.csv")
URE_CACHE_DIR = os.path.join(DATA_DIR, "ure_cache")

RATE_LIMIT_DELAY = 0.3
RATE_LIMIT_BACKOFF = 10
MAX_RETRIES = 5

YEAR_SLICES = [
    ("2023-01-01", "2023-12-31"),
    ("2024-01-01", "2024-12-31"),
    ("2025-01-01", "2025-12-31"),
]

# ---------------------------------------------------------------------------
# Child welfare boolean (same as overton_policy_pull.py)
# ---------------------------------------------------------------------------
CHILD_WELFARE_BOOLEAN = (
    '(  "child abuse"~5 OR "abuse child"~5 OR '
    '  "child abused"~5 OR "abused child"~5 OR '
    '  "child abusing"~5 OR "abusing child"~5 OR '
    '  "child abusive"~5 OR "abusive child"~5 OR '
    '   "child\'s abuse"~5 OR "abuse child\'s"~5 OR '
    '  "child\'s abused"~5 OR "abused child\'s"~5 OR '
    '  "child\'s abusing"~5 OR "abusing child\'s"~5 OR '
    '  "child\'s abusive"~5 OR "abusive child\'s"~5 OR '
    '   "children abuse"~5 OR "abuse children"~5 OR '
    '  "children abused"~5 OR "abused children"~5 OR '
    '  "children abusing"~5 OR "abusing children"~5 OR '
    '  "children abusive"~5 OR "abusive children"~5 OR '
    '   "child neglect"~5 OR "neglect child"~5 OR '
    '  "child neglected"~5 OR "neglected child"~5 OR '
    '  "child neglecting"~5 OR "neglecting child"~5 OR '
    '  "child negligent"~5 OR "negligent child"~5 OR '
    '   "child\'s neglect"~5 OR "neglect child\'s"~5 OR '
    '  "child\'s neglected"~5 OR "neglected child\'s"~5 OR '
    '  "child\'s neglecting"~5 OR "neglecting child\'s"~5 OR '
    '  "child\'s negligent"~5 OR "negligent child\'s"~5 OR '
    '   "children neglect"~5 OR "neglect children"~5 OR '
    '  "children neglected"~5 OR "neglected children"~5 OR '
    '  "children neglecting"~5 OR "neglecting children"~5 OR '
    '  "children negligent"~5 OR "negligent children"~5 OR '
    ' "Best interests of the child" OR "best interest of the child" OR '
    ' "Reasonable efforts to prevent removal" OR '
    ' ("imminent danger child"~5 OR "child imminent danger"~5 OR '
    '  "imminent danger children"~5 OR "children imminent danger"~5) OR '
    ' "termination of parental rights" OR '
    ' ("relinquish parental rights"~5 OR "parental rights relinquish"~5 OR '
    '  "relinquished parental rights"~5 OR "parental rights relinquished"~5) OR '
    ' "Permanency hearing" OR "Legal guardianship" OR '
    ' "court-appointed special advocate" OR "guardian ad litem" OR '
    ' "out-of-home care" OR '
    ' ("foster care child"~20 OR "child foster care"~20 OR '
    '  "foster care children"~20 OR "children foster care"~20) OR '
    ' ("foster home child"~20 OR "child foster home"~20 OR '
    '  "foster home children"~20 OR "children foster home"~20) OR '
    ' ("foster parent child"~20 OR "child foster parent"~20 OR '
    '  "foster parent children"~20 OR "children foster parent"~20) OR '
    ' ("temporary placement child"~10 OR "child temporary placement"~10 OR '
    '  "temporary placement children"~10 OR "children temporary placement"~10) OR '
    ' "Kinship foster care" OR "kinship care" OR '
    ' "Permanency goal" OR "family reunification" OR "adoption assistance" OR '
    ' "parenting program" OR "Wraparound services" OR '
    ' "family preservation" OR "early childhood intervention" OR '
    ' "child care assistance" OR '
    ' ("mandated reporter child"~5 OR "child mandated reporter"~5 OR '
    '  "mandated reporter children"~5 OR "children mandated reporter"~5) OR '
    ' ("failure to report child"~5 OR "child failure to report"~5 OR '
    '  "failure to report children"~5 OR "children failure to report"~5) OR '
    ' "shaken baby syndrome" OR "abusive head trauma" OR '
    ' "parental substance use" )'
)

# ---------------------------------------------------------------------------
# URE boolean queries
# ---------------------------------------------------------------------------
URE_BOOLEANS = {
    "URE_ProbDef": (
        '('
        '  ('
        '    ('
        '      "data indicate" OR "data indicates" OR "data indicated" OR'
        '      "data demonstrate" OR "data demonstrates" OR "data demonstrated" OR'
        '      "data found" OR "data finds" OR'
        '      "data illustrates" OR "data illustrated" OR "data illustrate" OR'
        '      "data reveals" OR "data revealed" OR "data reveal" OR'
        '      "data shows" OR "data showed" OR "data show" OR'
        '      "data suggests" OR "data suggested" OR "data suggest" OR'
        '      "data suggesting"'
        '    )'
        '  )'
        '  OR'
        '  ('
        '    evidence AND NOT ('
        '      "evidence crime"~10 OR "evidence offense"~10 OR "evidence preponderance"~10 OR'
        '      "evidence defendant"~10 OR "evidence plaintiff"~10 OR "evidence victim"~10 OR'
        '      "evidence legal"~10 OR "evidence proceedings"~10 OR "evidence charges"~10 OR'
        '      "evidence clear and convincing"~10 OR "evidence compliance"~10 OR "evidence court"~10'
        '    )'
        '    AND'
        '    ('
        '      "evidence indicate" OR "evidence indicates" OR "evidence indicated" OR'
        '      "evidence demonstrates" OR "evidence demonstrated" OR'
        '      "evidence demonstrating" OR "evidence found" OR "evidence finds" OR'
        '      "evidence recommends" OR "evidence recommended" OR "evidence reveals" OR'
        '      "evidence revealed" OR "evidence shows" OR "evidence showed" OR'
        '      "evidence suggests" OR "existing evidence" OR "overwhelming evidence" OR'
        '      "empirical evidence" OR "recent evidence" OR "scientific evidence"'
        '    )'
        '  )'
        ')'
    ),
    "URE_ProbSol": (
        '('
        '  "research informed" OR "informed by research" OR "evidence based" OR'
        '  "science based" OR "empirically based" OR "research based" OR'
        '  "based on research" OR "scientifically based" OR "scientifically accurate" OR'
        '  "evidence informed" OR "data driven" OR "data informed" OR "data to inform" OR'
        '  "data that informs" OR "supporting data" OR "supported by data" OR'
        '  "data supports" OR "data supporting" OR'
        '  "prioritize research" OR "implement science" OR "implement research"'
        ')'
    ),
    "URE_Account": (
        '('
        '  "results of the research" OR'
        '  "results of the study" OR'
        '  "findings of the study" OR'
        '  "quality improvement" OR'
        '  "continuous quality improvement" OR'
        '  "assessment measures" OR'
        '  "measurable objectives" OR'
        '  (measures outcomes OR outcomes measures) OR'
        '  "program evaluation" OR'
        '  ("evaluation results"~2 OR "evaluation findings"~2 OR'
        '   "evaluation evidence"~2 OR "evaluation research"~2) OR'
        '  ("impact analyze"~2 OR "impact analysis"~2 OR'
        '   "impact analyses"~2 OR "impact study"~2 OR'
        '   "impact studies"~2 OR "impact evidence"~2) OR'
        '  ('
        '    "study conducted" OR "studies conducted" OR'
        '    "research conducted" OR "conducted research"'
        '  )'
        '  AND'
        '  ("pursuant" OR "report" OR "shall" OR'
        '   "section" OR "subsection" OR "paragraph") OR'
        '  (study assess OR assess study)'
        ')'
    ),
    "URE_KnowGen": (
        '('
        '  ("best practices disseminate"~2 OR "best practices identify"~2 OR'
        '   "best practices develop"~2 OR "best practices implement"~2 OR'
        '   "best practices share"~2) OR'
        '  "conduct studies" OR'
        '  "conduct a study" OR'
        '  (conducts research OR research conducts) OR'
        '  "engage in research" OR'
        '  ("technical assistance" AND "best practices") OR'
        '  "utilize data" OR "utilize findings" OR "utilize research" OR'
        '  "support studies" OR "support research" OR'
        '  "develop studies" OR "develop research" OR'
        '  "propose studies" OR "propose research" OR'
        '  "research driven" OR "research-driven" OR'
        '  ("innovative research" AND NOT "innovative research small business"~2) OR'
        '  ("disseminate results"~3 OR "disseminate findings"~3 OR'
        '   "disseminate evidence"~3 OR "disseminate research"~3 OR'
        '   "disseminate best practices"~3) OR'
        '  "fund research" OR "fund studies"'
        ')'
    ),
    "URE_Method": (
        '('
        '  "research design" OR "research designs" OR'
        '  "study design" OR "study designs" OR'
        '  "research methodology" OR "research method" OR'
        '  "research methods" OR "scientific methods" OR'
        '  "scientific methodology" OR'
        '  "random sample" OR'
        '  "representative sample" OR "representative samples" OR'
        '  "representative sampling" OR'
        '  "sample size" OR "sample sizes" OR'
        '  "hypothesis" OR "hypotheses" OR'
        '  "research question" OR "research questions" OR'
        '  "randomized trial" OR "randomized control trial" OR'
        '  "randomized controlled trial" OR "randomized control study" OR'
        '  "control group" OR "control groups" OR'
        '  "qualitative" OR'
        '  ("quantitative" AND NOT "non-quantitative") OR'
        '  "causal relationship" OR "cause and effect relationship" OR'
        '  "causal effect" OR'
        '  "generalizability" OR "external validity"'
        ')'
    ),
    "URE_TypeStudy": (
        '('
        '  "observational study" OR "observational studies" OR'
        '  "pilot study" OR "pilot studies" OR'
        '  "population study" OR "population studies" OR'
        '  "longitudinal study" OR "longitudinal studies" OR'
        '  "experimental study" OR "experimental studies" OR'
        '  "empirical study" OR "empirical studies" OR'
        '  "case study" OR "case studies" OR'
        '  "quasi-experimental" OR'
        '  (("independent study" OR "independent studies")'
        '   AND NOT ("independent study coursework"~4 OR'
        '            "independent study credit"~4 OR'
        '            "independent study student"~4 OR'
        '            "independent studies school"~4)) OR'
        '  "cooperative research" OR "ecological research" OR'
        '  "empirical research" OR "clinical research" OR'
        '  "experimental research" OR "clinical trial" OR'
        '  "root cause analysis"'
        ')'
    ),
    "URE_Data": (
        '('
        '  "statistical analysis" OR "statistical test" OR "statistical tests" OR'
        '  "analysis of data" OR'
        '  "comparative analysis" OR "comparative analyses" OR'
        '  "data analysis" OR "data analyses" OR'
        '  "data for analysis" OR "analysis of databases" OR'
        '  "systematically analyze" OR "systematically test" OR'
        '  "data set" OR "data sets" OR "dataset" OR "datasets" OR'
        '  "data system" OR "data systems" OR'
        '  "preliminary data" OR "administrative data" OR'
        '  "aggregate data" OR'
        '  (data available OR available data) OR'
        '  "census data" OR "empirical data" OR'
        '  "observational data" OR "observation data" OR'
        '  "statistical data" OR "significant data" OR'
        '  "regression analysis" OR "gap analysis" OR'
        '  "overlap analysis" OR "comparison analysis" OR'
        '  "meta analysis" OR "meta analyses" OR'
        '  "statistically validate" OR "scientifically valid" OR'
        '  "descriptive statistics" OR "confidence interval" OR'
        '  "standard deviation" OR "standard deviations" OR'
        '  (correlate data OR data correlate) OR'
        '  "significantly correlated" OR'
        '  "significantly more likely" OR'
        '  "significantly less likely" OR'
        '  "theoretical framework" OR "empirically supported theory" OR'
        '  "data monitoring" OR'
        '  (data collect OR collect data) OR'
        '  "data methods" OR'
        '  "data quality" OR "quality of data"'
        ')'
    ),
    "URE_Conceptual": (
        '('
        '  "trauma informed" OR'
        '  "protective factor" OR "protective factors" OR'
        '  "developmental harm" OR'
        '  "disparity" OR "disparities" OR'
        '  "inequity" OR "inequities" OR'
        '  "disrupted access" OR "reduced access" OR'
        '  (disproportionate AND NOT "disproportionate share hospital") OR'
        '  "marginalized" OR'
        '  ("vulnerable groups"~5 OR "vulnerable populations"~5 OR'
        '   "vulnerable communities"~5 OR "vulnerable people"~5) OR'
        '  "long term outcomes" OR'
        '  "social determinants" OR'
        '  ("stressors daily"~5 OR "stressors social"~5 OR'
        '   "stressors compounded"~5 OR "stressors affecting"~5 OR'
        '   "stressors vulnerable"~5 OR "stressors health"~5 OR'
        '   "stressors socioeconomic"~5) OR'
        '  "risk factor" OR "risk factors" OR'
        '  ("root cause" AND NOT "root cause analysis") OR'
        '  ("barriers" AND NOT ("barriers jurisdictional"~3 OR'
        '                         "barriers financial"~3 OR'
        '                         "barriers geographic"~3)) OR'
        '  ("sustainability" AND NOT "sustainability institute") OR'
        '  "burnout" OR'
        '  ("prevention health"~3 OR "prevention efforts"~3 OR'
        '   "prevention programs"~3 OR "prevention education"~3 OR'
        '   "prevention violence"~3 OR "prevention services"~3)'
        ')'
    ),
    "URE_Overt": (
        '('
        '  ("evidence" OR "research" OR "study" OR "studies" OR'
        '   "scientific" OR "scientifically" OR "data" OR'
        '   "empirical" OR "empirically" OR "evaluation" OR'
        '   "RCT" OR "randomized controlled trial" OR'
        '   "QED" OR "quasi-experimental research design" OR'
        '   "control" OR "comparison" OR "impacts" OR'
        '   "expert" OR "researcher")'
        '  AND'
        '  ("informed" OR "based" OR "based on" OR "driven" OR'
        '   "experimental" OR "peer-reviewed" OR "rigorous" OR'
        '   "randomized" OR "effective" OR "ineffective" OR'
        '   "promising" OR "statistically significant")'
        '  AND'
        '  ("demonstrate" OR "suggest" OR "found" OR "show" OR'
        '   "illustrate" OR "replicate")'
        ')'
    ),
}

URE_NAMES = list(URE_BOOLEANS.keys())

# ---------------------------------------------------------------------------
# Regulatory action detection
# ---------------------------------------------------------------------------

REGULATORY_TERMS = [
    "final rule", "proposed rule", "interim rule", "interim final rule",
    "direct final rule", "emergency rule", "adopted rule", "repealed rule",
    "rule adoption", "rule amendment", "rulemaking", "final rulemaking",
    "notice of rulemaking", "notice of proposed rulemaking", "NPRM",
    "statement of basis and purpose", "regulatory amendment",
    "executive order", "secretarial order", "commissioner order",
    "department order", "administrative order", "agency order",
    "policy directive", "administrative directive", "directive",
    "emergency order", "emergency directive", "public health order",
    "temporary order", "emergency declaration",
    "regulatory determination", "final determination",
    "determination of applicability", "regulatory finding", "finding of fact",
    "order and determination", "final agency action",
    "enforcement action", "administrative enforcement",
    "notice of violation", "notice of noncompliance",
    "penalty assessment", "civil penalty", "administrative penalty",
    "compliance order", "consent order", "settlement agreement",
    "cease and desist",
    "permit approval", "permit denial", "permit issuance",
    "permit decision", "permit modification", "permit revocation",
    "licensing decision", "license approval", "license denial",
    "license revocation", "certification", "authorization",
    "regulatory decision",
]

# Build a single compiled regex for the term-based pattern (case-insensitive)
_reg_terms_pattern = re.compile(
    "|".join(re.escape(t) for t in REGULATORY_TERMS),
    re.IGNORECASE,
)

# US state names for the second pattern
US_STATE_NAMES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
]

_state_pattern = re.compile(
    "|".join(re.escape(s) for s in US_STATE_NAMES) + r"|state|commonwealth",
    re.IGNORECASE,
)
_agency_pattern = re.compile(
    r"department|agency|board|commission|office",
    re.IGNORECASE,
)
_action_pattern = re.compile(
    r"rule|order|regulation|directive|enforcement|permit",
    re.IGNORECASE,
)


def is_regulatory_action(title: str) -> int:
    """Return 1 if the title matches regulatory action criteria, else 0."""
    if not title:
        return 0
    # Pattern 1: any regulatory term
    if _reg_terms_pattern.search(title):
        return 1
    # Pattern 2: state/commonwealth + agency word + action word
    if (_state_pattern.search(title)
            and _agency_pattern.search(title)
            and _action_pattern.search(title)):
        return 1
    return 0


# ---------------------------------------------------------------------------
# State extraction from source.title
# ---------------------------------------------------------------------------

def extract_state(source_title: str) -> str:
    """Extract state name from source title like 'State of Delaware'."""
    if not source_title:
        return ""
    m = re.match(r"(?:State|Commonwealth)\s+of\s+(.+)", source_title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return source_title


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def fetch_page(params, page):
    """Fetch a single page of results with retry logic."""
    req_params = {**params, "page": page}
    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(DOCUMENTS_URL, params=req_params, timeout=60)
            if response.status_code == 429:
                wait = RATE_LIMIT_BACKOFF * (2 ** attempt)
                print(f"      Rate limited. Waiting {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError:
            if attempt < MAX_RETRIES - 1:
                wait = RATE_LIMIT_BACKOFF * (2 ** attempt)
                print(f"      HTTP error. Retrying in {wait}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(wait)
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < MAX_RETRIES - 1:
                wait = 5 * (attempt + 1)
                print(f"      Request error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                raise
    return None


def fetch_ids_for_query(query, label="", extra_params=None):
    """Fetch all policy_document_ids matching a query, split by year."""
    all_ids = set()
    for pub_after, pub_before in YEAR_SLICES:
        year = pub_after[:4]
        params = {
            "api_key": API_KEY,
            "format": "json",
            "query": query,
            "sector": "public_sector",
            "source_type": "government",
            "country": "USA",
            "published_after": pub_after,
            "published_before": pub_before,
            "sort": "published_on",
            "per_page": 50,
        }
        if extra_params:
            params.update(extra_params)

        # First page
        time.sleep(RATE_LIMIT_DELAY)
        data = fetch_page(params, 1)
        if data is None:
            print(f"    {label} {year}: failed to fetch page 1, skipping")
            continue

        query_info = data.get("query", {})
        total_results = query_info.get("total_results", 0)
        total_pages = math.ceil(total_results / 50) if total_results > 0 else 0

        if total_results == 0:
            print(f"    {label} {year}: 0 results")
            continue

        # Extract IDs from first page
        results = data.get("results", [])
        if isinstance(results, dict):
            results = list(results.values())
        year_ids = set()
        for doc in results:
            doc_id = doc.get("policy_document_id", "")
            if doc_id:
                year_ids.add(doc_id)

        print(f"    {label} {year}: {total_results:,} results, {total_pages} pages")

        # Remaining pages
        for page in range(2, total_pages + 1):
            time.sleep(RATE_LIMIT_DELAY)
            try:
                data = fetch_page(params, page)
                if data is None:
                    print(f"      {label} {year}: failed page {page}, stopping year")
                    break
                results = data.get("results", [])
                if isinstance(results, dict):
                    results = list(results.values())
                for doc in results:
                    doc_id = doc.get("policy_document_id", "")
                    if doc_id:
                        year_ids.add(doc_id)

                if page % 50 == 0 or page == total_pages:
                    print(f"      {label} {year} page {page}/{total_pages}: {len(year_ids):,} IDs")
            except Exception as e:
                print(f"      {label} {year} error on page {page}: {e}")
                break

        all_ids.update(year_ids)
        print(f"    {label} {year}: {len(year_ids):,} IDs collected (running total: {len(all_ids):,})")

    return all_ids


def get_cached_ids(name, query, extra_params=None):
    """Get document IDs for a named query, using cache if available."""
    cache_file = os.path.join(URE_CACHE_DIR, f"{name}.json")

    # Check cache first
    if os.path.exists(cache_file):
        with open(cache_file, "r", encoding="utf-8") as f:
            cached_ids = json.load(f)
        print(f"  {name}: loaded {len(cached_ids):,} IDs from cache")
        return set(cached_ids)

    print(f"  {name}: querying API...")
    ids = fetch_ids_for_query(query, label=name, extra_params=extra_params)

    # Save to cache
    os.makedirs(URE_CACHE_DIR, exist_ok=True)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False)
    print(f"  {name}: {len(ids):,} IDs saved to cache")

    return ids


def get_ure_ids(ure_name, ure_boolean):
    """Get document IDs for a URE type, using cache if available."""
    combined_query = f"({CHILD_WELFARE_BOOLEAN}) AND ({ure_boolean})"
    return get_cached_ids(ure_name, combined_query)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Build CSV — US State Child Welfare Documents + URE Flags")
    print("=" * 60)

    # Step 1: Load documents
    print(f"\nLoading documents from {INPUT_FILE}...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    documents = data.get("results", [])
    print(f"  Loaded {len(documents):,} documents")

    # Step 2: Compute local fields
    print("\nComputing local fields (regulatory action, state, citations)...")
    rows = []
    for doc in documents:
        doc_id = doc.get("policy_document_id", "")
        title = doc.get("title", "")
        source = doc.get("source", {}) or {}
        source_title = source.get("title", "")
        published_on = doc.get("published_on", "")

        cites = doc.get("cites", {}) or {}
        scholarly = cites.get("scholarly", []) or []
        policy = cites.get("policy", []) or []
        news = cites.get("news", []) or []

        rows.append({
            "overton_id": doc_id,
            "title": title,
            "is_regulatory_action": is_regulatory_action(title),
            "state": extract_state(source_title),
            "published_on": published_on,
            "cites_scholarly_count": len(scholarly),
            "cites_policy_count": len(policy),
            "cites_news_count": len(news),
            "cites_all_count": len(scholarly) + len(policy) + len(news),
        })

    # Quick stats on regulatory actions
    reg_count = sum(r["is_regulatory_action"] for r in rows)
    print(f"  Regulatory actions: {reg_count:,} / {len(rows):,}")

    # Step 3: Fetch has_references and has_citations IDs
    print("\nFetching has_references / has_citations document IDs...")
    has_references_ids = get_cached_ids(
        "has_references", CHILD_WELFARE_BOOLEAN,
        extra_params={"has_references": "1"},
    )
    has_citations_ids = get_cached_ids(
        "has_citations", CHILD_WELFARE_BOOLEAN,
        extra_params={"has_citations": "1"},
    )

    # Step 4: Fetch URE IDs
    print("\nFetching URE document IDs...")
    ure_id_sets = {}
    for ure_name in URE_NAMES:
        ure_id_sets[ure_name] = get_ure_ids(ure_name, URE_BOOLEANS[ure_name])

    # Step 5: Build CSV
    print(f"\nWriting CSV to {OUTPUT_FILE}...")
    fieldnames = [
        "overton_id", "title", "is_regulatory_action", "state", "published_on",
        "cites_scholarly_count", "cites_policy_count", "cites_news_count",
        "cites_all_count", "has_references", "has_citations",
    ] + URE_NAMES

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            doc_id = row["overton_id"]
            row["has_references"] = 1 if doc_id in has_references_ids else 0
            row["has_citations"] = 1 if doc_id in has_citations_ids else 0
            for ure_name in URE_NAMES:
                row[ure_name] = 1 if doc_id in ure_id_sets[ure_name] else 0
            writer.writerow(row)

    print(f"  Wrote {len(rows):,} rows")

    # Step 6: Summary statistics
    print("\n" + "=" * 60)
    print("Summary Statistics")
    print("=" * 60)
    print(f"Total documents:        {len(rows):,}")
    print(f"Regulatory actions:     {reg_count:,} ({100*reg_count/len(rows):.1f}%)")

    states = {}
    for r in rows:
        s = r["state"]
        states[s] = states.get(s, 0) + 1
    print(f"Unique states:          {len(states)}")

    scholarly_nonzero = sum(1 for r in rows if r["cites_scholarly_count"] > 0)
    policy_nonzero = sum(1 for r in rows if r["cites_policy_count"] > 0)
    news_nonzero = sum(1 for r in rows if r["cites_news_count"] > 0)
    any_nonzero = sum(1 for r in rows if r["cites_all_count"] > 0)
    print(f"Cites scholarly: {scholarly_nonzero:,} ({100*scholarly_nonzero/len(rows):.1f}%) — total refs: {sum(r['cites_scholarly_count'] for r in rows):,}")
    print(f"Cites policy:    {policy_nonzero:,} ({100*policy_nonzero/len(rows):.1f}%) — total refs: {sum(r['cites_policy_count'] for r in rows):,}")
    print(f"Cites news:      {news_nonzero:,} ({100*news_nonzero/len(rows):.1f}%) — total refs: {sum(r['cites_news_count'] for r in rows):,}")
    print(f"Cites any:       {any_nonzero:,} ({100*any_nonzero/len(rows):.1f}%)")

    ref_count = sum(1 for r in rows if r["overton_id"] in has_references_ids)
    cit_count = sum(1 for r in rows if r["overton_id"] in has_citations_ids)
    print(f"has_references (cites others):  {ref_count:,} ({100*ref_count/len(rows):.1f}%)")
    print(f"has_citations (cited by others): {cit_count:,} ({100*cit_count/len(rows):.1f}%)")

    print(f"\nURE type counts:")
    for ure_name in URE_NAMES:
        count = sum(1 for r in rows if r["overton_id"] in ure_id_sets[ure_name])
        print(f"  {ure_name:20s}: {count:,} ({100*count/len(rows):.1f}%)")

    print(f"\nDone! CSV written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
