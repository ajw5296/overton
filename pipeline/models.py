"""TypedDict definitions for the unified researcher record."""

from typing import TypedDict, Optional


class TopicInfo(TypedDict):
    topic: str
    subfield: Optional[str]
    field: Optional[str]
    domain: Optional[str]


class AffiliationInfo(TypedDict):
    institution: str
    years: list[int]
    is_current: bool


class OpenAlexData(TypedDict):
    works_count: int
    cited_by_count: int
    h_index: int
    i10_index: int
    two_yr_mean_citedness: float
    affiliations: list[AffiliationInfo]
    topics: list[TopicInfo]
    last_fetched: str


class RMDProfile(TypedDict, total=False):
    title: Optional[str]
    organization_name: Optional[str]
    email: Optional[str]
    total_scopus_citations: Optional[int]
    scopus_h_index: Optional[int]
    bio: Optional[str]
    pure_profile_url: Optional[str]


class RMDGrant(TypedDict, total=False):
    id: str
    title: Optional[str]
    agency: Optional[str]
    amount_in_dollars: Optional[float]
    start_date: Optional[str]
    end_date: Optional[str]


class RMDOrgMembership(TypedDict, total=False):
    organization_name: Optional[str]
    organization_type: Optional[str]
    position_title: Optional[str]


class RMDData(TypedDict, total=False):
    webaccess_id: str
    profile: RMDProfile
    grants: list[RMDGrant]
    presentations_count: int
    etds_count: int
    org_memberships: list[RMDOrgMembership]
    last_fetched: str


class PolicyDocSource(TypedDict, total=False):
    title: Optional[str]
    country: Optional[str]
    type: Optional[str]
    organisation_type: Optional[str]


class PolicyDocument(TypedDict, total=False):
    policy_document_id: str
    title: Optional[str]
    source: PolicyDocSource
    published_on: Optional[str]
    topics: list[str]
    sdgcategories: list[str]
    overton_url: Optional[str]


class OvertonData(TypedDict, total=False):
    policy_documents_total: int
    policy_documents: list[PolicyDocument]
    last_fetched: str


class Researcher(TypedDict, total=False):
    orcid: str
    openalex_id: str
    display_name: str
    openalex: OpenAlexData
    rmd: Optional[RMDData]
    overton: Optional[OvertonData]


# === Overton Articles API types ===


class ArticleCitedBySource(TypedDict, total=False):
    """A policy document that cites a scholarly article (from Articles API)."""
    policy_document_id: str
    policy_source_id: str
    source_title: str
    document_title: str
    published_on: Optional[str]
    type: Optional[str]
    country: Optional[str]
    topics: list[str]
    classifications: list[str]


class ArticleRecord(TypedDict, total=False):
    """A scholarly article record from the Overton Articles API."""
    title: str
    doi: str
    document_url: Optional[str]
    container: Optional[str]
    journal: Optional[str]
    publisher: Optional[str]
    type: Optional[str]
    published_on: Optional[str]
    authors: list[str]
    orcids: list[str]
    language: Optional[str]
    abstract: Optional[str]
    oa_status: Optional[str]
    funders: list[str]
    grant_ids: list[str]
    citations: int
    cited_by_documents: list[ArticleCitedBySource]
    last_fetched: str


# === Overton Documents API types ===


class PolicyDocSourceFull(TypedDict, total=False):
    """Full source metadata from the Overton Documents API."""
    source_id: str
    title: Optional[str]
    country: Optional[str]
    state: Optional[str]
    type: Optional[str]
    subtype: Optional[str]
    sector: Optional[str]
    organisation_type: Optional[str]
    function: list[str]
    region: list[str]


class PolicyDocCitedWork(TypedDict, total=False):
    """A scholarly work cited by a policy document."""
    doi: str
    title: Optional[str]
    journal: Optional[str]
    publisher: Optional[str]


class PolicyDocumentFull(TypedDict, total=False):
    """Full policy document record from the Overton Documents API."""
    policy_document_id: str
    pdf_document_id: Optional[str]
    title: str
    translated_title: Optional[str]
    source: PolicyDocSourceFull
    published_on: Optional[str]
    added_on: Optional[str]
    document_url: Optional[str]
    pdf_url: Optional[str]
    thumbnail: Optional[str]
    topics: list[str]
    classifications: list[str]
    sdgcategories: list[str]
    cofog_divisions: list[str]
    llm_document_theme: Optional[str]
    llm_document_description: Optional[str]
    citation_count: int
    authors: list[str]
    languages: list[str]
    dont_show_pdf: bool
    cites_scholarly_dois: list[str]
    overton_url: Optional[str]
    s3_pdf_key: Optional[str]
    download_status: Optional[str]
    last_fetched: str


# === Article ↔ Policy Document junction ===


class ArticleCitation(TypedDict, total=False):
    """Junction record linking a scholarly article to a citing policy document."""
    doi: str
    policy_document_id: str
    source_title: Optional[str]
    document_title: Optional[str]
    published_on: Optional[str]
    type: Optional[str]
    country: Optional[str]
    cited_on_pages: list[int]


# === Pipeline metadata ===


class PipelineRunMetadata(TypedDict, total=False):
    """Metadata for a single pipeline stage execution."""
    run_id: str
    stage: str
    status: str
    started_at: str
    completed_at: Optional[str]
    records_processed: int
    records_inserted: int
    records_updated: int
    errors: int
