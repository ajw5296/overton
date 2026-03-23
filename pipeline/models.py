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
