# Available Data Sources Reference

This document catalogs all data fields available from the three data sources used in the Overton Research Impact pipeline: **OpenAlex**, **PSU RMD (Research Metadata Database)**, and **Overton**. It is intended to help identify potential uses and cross-linkages across sources.

---

## 1. OpenAlex

**What it is:** An open catalog of the global research system — authors, works, institutions, funders, journals, and topics. Free to use.

**API base:** `https://api.openalex.org`

**How we query it:** Filter by PSU's ROR ID (`https://ror.org/04p491231`) and `has_orcid:true` to get all PSU-affiliated researchers with an ORCID.

### 1a. Author Record

The core entity. One record per researcher.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | OpenAlex author ID | `https://openalex.org/A5025227099` |
| `orcid` | string | ORCID identifier (URL format) | `https://orcid.org/0000-0003-3838-0523` |
| `display_name` | string | Preferred name | `Donna H. Korzick` |
| `display_name_alternatives` | string[] | All known name variants | `["D H. Korzick", "D. Korzick", ...]` |
| `works_count` | int | Total number of scholarly works | `85` |
| `cited_by_count` | int | Total times cited across all works | `1356` |
| `summary_stats.h_index` | int | h-index | `24` |
| `summary_stats.i10_index` | int | Number of works with 10+ citations | `37` |
| `summary_stats.2yr_mean_citedness` | float | Average citations in last 2 years | `0.0` |
| `ids.openalex` | string | OpenAlex ID | |
| `ids.orcid` | string | ORCID | |
| `last_known_institutions` | object[] | Current institutional affiliation(s) | PSU |
| `works_api_url` | string | URL to fetch all works by this author | |
| `updated_date` | datetime | When OpenAlex last updated this record | `2026-03-03T12:20:50` |
| `created_date` | datetime | When record was first created | `2016-06-24` |

### 1b. Author Affiliations

Historical list of all institutions an author has published from.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `institution.id` | string | OpenAlex institution ID | `https://openalex.org/I130769515` |
| `institution.ror` | string | ROR identifier | `https://ror.org/04p491231` |
| `institution.display_name` | string | Institution name | `Pennsylvania State University` |
| `institution.country_code` | string | ISO country code | `US` |
| `institution.type` | string | Institution type | `education`, `healthcare`, `nonprofit`, `facility` |
| `institution.lineage` | string[] | Parent institution IDs | |
| `years` | int[] | Publication years at this institution | `[2025, 2022, 2018, ...]` |

### 1c. Author Topics

Top research topics (ranked by work count) with a 4-level hierarchy.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | OpenAlex topic ID | `https://openalex.org/T11457` |
| `display_name` | string | Topic name | `Adipose Tissue and Metabolism` |
| `count` | int | Number of works in this topic | `16` |
| `subfield.display_name` | string | Subfield (level 2) | `Physiology` |
| `field.display_name` | string | Field (level 3) | `Medicine` |
| `domain.display_name` | string | Domain (level 4, broadest) | `Health Sciences` |

### 1d. Author Topic Share

Same hierarchy as topics, but ranked by the author's relative contribution to the global topic (how much of that topic's output this author represents).

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Topic ID | |
| `display_name` | string | Topic name | `Cardiac Ischemia and Reperfusion` |
| `value` | float | Author's share of total topic output | `0.0001189` |
| `subfield` / `field` / `domain` | object | Same hierarchy as above | |

### 1e. Author Counts by Year

Year-over-year publication and citation metrics.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `year` | int | Calendar year | `2025` |
| `works_count` | int | Works published that year | `2` |
| `oa_works_count` | int | Open-access works that year | `0` |
| `cited_by_count` | int | Citations received that year | `0` |

### 1f. Author Concepts (x_concepts, legacy)

Broad concept tagging with relevance scores (0-1). Being replaced by topics but still available.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Concept ID | `71924100` |
| `wikidata` | string | Wikidata link | |
| `display_name` | string | Concept name | `Medicine` |
| `score` | float | Relevance score (0-1) | `0.9410` |

### 1g. Works (Individual Publications)

Available via `works_api_url` on each author. One record per publication.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | OpenAlex work ID | `https://openalex.org/W2414696471` |
| `doi` | string | DOI (if available) | `null` or DOI URL |
| `title` | string | Publication title | |
| `display_name` | string | Same as title | |
| `publication_year` | int | Year published | `1991` |
| `publication_date` | string | Full date | `1991-01-01` |
| `ids.openalex` | string | OpenAlex ID | |
| `ids.pmid` | string | PubMed ID (if indexed) | `https://pubmed.ncbi.nlm.nih.gov/1794940` |
| `ids.mag` | string | Microsoft Academic Graph ID (legacy) | |
| `language` | string | ISO language code | `en` |
| `type` | string | Work type | `article`, `book-chapter`, `review`, etc. |
| `indexed_in` | string[] | Where indexed | `["pubmed"]` |
| **Primary Location** | | | |
| `primary_location.is_oa` | bool | Is it open access? | `false` |
| `primary_location.landing_page_url` | string | URL to access | |
| `primary_location.pdf_url` | string | Direct PDF link (if OA) | |
| `primary_location.source.display_name` | string | Journal/repo name | `PubMed` |
| `primary_location.source.type` | string | Source type | `journal`, `repository` |
| `primary_location.source.is_oa` | bool | Is the source open access? | |
| `primary_location.source.host_organization_name` | string | Publisher/host org | `National Institutes of Health` |
| `primary_location.version` | string | Version available | `publishedVersion`, `acceptedVersion` |
| **Open Access** | | | |
| `open_access.is_oa` | bool | Is work OA? | |
| `open_access.oa_status` | string | OA type | `gold`, `green`, `hybrid`, `bronze`, `closed` |
| `open_access.oa_url` | string | Best OA URL | |
| **Authorships** | | | |
| `authorships[].author_position` | string | Position in author list | `first`, `middle`, `last` |
| `authorships[].author.id` | string | Author's OpenAlex ID | |
| `authorships[].author.display_name` | string | Author name | |
| `authorships[].author.orcid` | string | Author's ORCID (if known) | |
| `authorships[].institutions` | object[] | Author's affiliated institutions for this work | |
| `authorships[].countries` | string[] | Author's countries | `["US", "JP"]` |
| `authorships[].is_corresponding` | bool | Is corresponding author? | |

### 1h. Funder Records

Available as a separate entity type. Tracks grant-making organizations.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | OpenAlex funder ID | `https://openalex.org/F4320337376` |
| `display_name` | string | Funder name | `NIH Clinical Center` |
| `alternate_titles` | string[] | Other names | |
| `country_code` | string | Country | `US` |
| `description` | string | Description | |
| `homepage_url` | string | Website | |
| `awards_count` | int | Number of awards made | `2237` |
| `works_count` | int | Works funded | `16347` |
| `cited_by_count` | int | Total citations to funded works | `1,097,913` |
| `summary_stats` | object | h-index, i10_index, 2yr_mean_citedness | |
| `counts_by_year` | object[] | Year-over-year stats | |
| `roles` | object[] | Dual roles (funder + institution) | |
| `ids.ror` | string | ROR ID | |
| `ids.crossref` | string | Crossref funder ID | |
| `ids.doi` | string | Funder DOI | |

### 1i. Topic Records

Detailed info for any topic in the OpenAlex taxonomy (~65,000 topics).

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Topic ID | `https://openalex.org/T10924` |
| `display_name` | string | Topic name | `Cardiovascular Health and Disease Prevention` |
| `description` | string | Multi-sentence description of the topic cluster | (long text) |
| `keywords` | string[] | Associated keywords | `["Arterial Stiffness", "Endothelial Dysfunction", ...]` |
| `subfield` | object | Parent subfield | `Cardiology and Cardiovascular Medicine` |
| `field` | object | Parent field | `Medicine` |
| `domain` | object | Parent domain | `Health Sciences` |
| `siblings` | object[] | Other topics in the same subfield | (list of topic IDs and names) |
| `works_count` | int | Total works globally | `69,821` |
| `cited_by_count` | int | Total citations globally | `1,260,445` |

### 1j. Additional OpenAlex Entities (available but not currently used)

- **Institutions** — Full profiles with geo coordinates, associated funders, Wikipedia links
- **Sources (Journals)** — ISSN, publisher, APC info, h-index, DOAJ/OA status, subject areas
- **Concepts** (legacy) — Wikidata-linked concept hierarchy

---

## 2. PSU RMD (Research Metadata Database)

**What it is:** Penn State's internal research activity database. Contains institutional data about researchers: grants, publications, presentations, advising, organizational memberships, and news coverage. Currently we have read access to HHD (College of Health and Human Development); full university access is pending.

**API base:** `https://metadata.libraries.psu.edu/v1`

**Authentication:** API key required (`X-API-Key` header) for most endpoints.

### 2a. User Profile

Comprehensive researcher profile with institutional details.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal RMD user ID | `787` |
| `attributes.name` | string | Full name | `Donna Hope Korzick` |
| `attributes.organization_name` | string | Department | `Kinesiology` |
| `attributes.title` | string | Academic title | `Professor` |
| `attributes.office_location` | string | Office address | `106 Noll Lab` |
| `attributes.office_phone_number` | string | Phone | `(814) 865-5679` |
| `attributes.personal_website` | string | Personal website URL | |
| `attributes.email` | string | Email | `dhk102@psu.edu` |
| `attributes.total_scopus_citations` | int | Citation count from Scopus | `1225` |
| `attributes.scopus_h_index` | int | h-index from Scopus | `23` |
| `attributes.pure_profile_url` | string | Link to Pure profile | `https://pure.psu.edu/en/persons/...` |
| `attributes.orcid_identifier` | string | ORCID (if set) | |
| `attributes.bio` | string | Free-text biography | (long text about research focus) |
| `attributes.teaching_interests` | string | Teaching areas | `Advanced Cellular and Integrative Cardiovascular Physiology, Exercise Physiology` |
| `attributes.research_interests` | string | Research description | (detailed text) |
| `attributes.education_history` | array | Education records | |
| `attributes.publications` | string[] | HTML-formatted publication list | (with DOI links and journal names) |
| `attributes.other_publications` | object | Categorized non-primary pubs | `{"Others": [...]}` |
| `attributes.presentations` | string[] | Formatted presentation list | |
| `attributes.performances` | array | Creative performances (arts faculty) | |
| `attributes.master_advising_roles` | string[] | Master's thesis advising | (HTML with student name, thesis title, ETDA link, year) |
| `attributes.phd_advising_roles` | string[] | PhD dissertation advising | (HTML with student name, title, ETDA link, year) |
| `attributes.news_stories` | string[] | Press coverage | (HTML with title, URL, date) |
| `attributes.grants` | array | Grants (in profile view) | |

### 2b. User Grants

Detailed grant/funding records per researcher.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal grant ID | |
| `type` | string | Always `"grant"` | |
| `attributes.title` | string | Grant title | |
| `attributes.agency` | string | Funding agency | `NIH`, `NSF`, etc. |
| `attributes.amount_in_dollars` | float | Award amount | |
| `attributes.start_date` | string | Award start date | |
| `attributes.end_date` | string | Award end date | |

*Note: The grants endpoint returned empty for our sample researcher. Full data availability may vary.*

### 2c. User Presentations

Conference talks, posters, panels, and other scholarly presentations.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal presentation ID | `57137` |
| `type` | string | Always `"presentation"` | |
| `attributes.title` | string | Presentation title | `Inhibition of Programmed Necrosis...` |
| `attributes.activity_insight_identifier` | string | Activity Insight ID | |
| `attributes.name` | string | Event/conference name | `Women's Health Research Conference` |
| `attributes.organization` | string | Host organization | `Penn State University` |
| `attributes.location` | string | Location | `University Park PA` |
| `attributes.started_on` | string | Start date | |
| `attributes.ended_on` | string | End date | |
| `attributes.presentation_type` | string | Format | `Posters`, `Panels`, `Invited Talks` |
| `attributes.classification` | string | Classification | |
| `attributes.meet_type` | string | Meeting type | `Academic` |
| `attributes.attendance` | string | Attendance count | |
| `attributes.refereed` | string | Peer reviewed? | `Yes`, `No` |
| `attributes.abstract` | string | Abstract text | |
| `attributes.comment` | string | Additional context | |
| `attributes.scope` | string | Geographic scope | `Local`, `National`, `International` |
| `attributes.profile_preferences` | object[] | Visibility settings per user | |

### 2d. User Organization Memberships

Professional and institutional affiliations.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal ID | `3198` |
| `type` | string | Always `"organization_membership"` | |
| `attributes.organization_name` | string | Organization | `Kinesiology` |
| `attributes.organization_type` | string | Org type | `Department` |
| `attributes.position_title` | string | Role held | `Professor` |
| `attributes.position_started_on` | string | Start date | `2000-01-03` |
| `attributes.position_ended_on` | string | End date (null if current) | `null` |

### 2e. User ETDs (Electronic Theses and Dissertations)

Theses/dissertations the researcher supervised.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal ETD ID | `4565` |
| `type` | string | Always `"etd"` | |
| `attributes.title` | string | Thesis/dissertation title | `ROLE OF HEMODYNAMIC FORCES...` |
| `attributes.year` | int | Completion year | `2005` |
| `attributes.author_last_name` | string | Student last name | `Kim` |
| `attributes.author_first_name` | string | Student first name | `Min-ho` |
| `attributes.author_middle_name` | string | Student middle name | |

### 2f. Publications (Individual)

Detailed publication records from the RMD perspective.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal publication ID | `4` |
| `attributes.title` | string | Publication title | `Rapid estrogen receptor-α activation...` |
| `attributes.secondary_title` | string | Subtitle | |
| `attributes.publication_type` | string | Type | `Academic Journal Article` |
| `attributes.status` | string | Status | `Published` |
| `attributes.volume` | string | Journal volume | `150` |
| `attributes.issue` | string | Journal issue | `2` |
| `attributes.page_range` | string | Pages | `889-896` |
| `attributes.abstract` | string | Full abstract text | (long text) |
| `attributes.doi` | string | DOI | `https://doi.org/10.1210/en.2008-0708` |
| `attributes.preferred_open_access_url` | string | OA link | |
| `attributes.publisher` | string | Publisher name | `Endocrine Society` |
| `attributes.journal_title` | string | Journal name | `Endocrinology (United States)` |
| `attributes.published_on` | string | Publication date | `2009-02-01` |
| `attributes.citation_count` | int | Citation count | `51` |
| `attributes.contributors` | object[] | Author list with PSU user IDs | `[{first_name, middle_name, last_name, psu_user_id}]` |
| `attributes.tags` | object[] | Ranked keyword tags | `[{name: "Estrogen Receptor", rank: 4.0}, ...]` |
| `attributes.pure_ids` | string[] | Pure system identifiers | |
| `attributes.activity_insight_ids` | string[] | Activity Insight IDs | |
| `attributes.profile_preferences` | object[] | User visibility settings | |

### 2g. Publication Grants

Grant-to-publication linkage (which grants funded which publications).

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| *(endpoint returns grant objects linked to a specific publication)* | | | |

*Note: Returned empty in our sample — may be sparsely populated.*

### 2h. User News Feed Items

Press coverage and news mentions.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal ID | `3473` |
| `type` | string | Always `"news_feed_item"` | |
| `attributes.title` | string | Article headline | `$2.6M NIH grant to fund new microbiome sciences training program` |
| `attributes.url` | string | Article URL | `https://www.psu.edu/news/...` |
| `attributes.description` | string | Article summary (HTML) | |
| `attributes.published_on` | string | Date published | `2025-07-22` |

### 2i. Organizations

PSU organizational units (departments, centers, colleges).

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `id` | string | Internal org ID | `10` |
| `type` | string | Always `"organization"` | |
| `attributes.name` | string | Organization name | `College of Health and Human Development` |

*Current access shows HHD orgs: the College, Center For Healthy Aging, Methodology Center, Edna Bennett Pierce Prevention Research Center, Biobehavioral Health, Communication Sciences and Disorders, Human Development and Family Studies, Kinesiology, Nutritional Sciences, Recreation Park and Tourism Management.*

### 2j. Organization Publications

Paginated list of all publications from an organization unit — used to build the ORCID-to-WebAccess ID mapping.

| Field | Type | Description |
|-------|------|-------------|
| *(Same structure as individual publication, returned in paginated lists)* | | |

---

## 3. Overton

**What it is:** A database tracking how scholarly research is cited in policy documents worldwide — government reports, think tank publications, IGO documents, NGO reports, and more.

**API base:** `https://app.overton.io`

**Endpoints used:**
- `/articles.php` — scholarly articles indexed by Overton (the subset cited by ≥1 policy doc)
- `/documents.php` — policy documents
- `/generate_id_set.php` — POST endpoint that batches DOIs into a set ID (required for >1 DOI per query)

**Pipeline query strategy:** the pipeline's Stage 3 uses **DOI-set** (`articles.php?dois=<set_id>`), not the simpler `query=<ORCID>` free-text approach. For Jonathan Foulds (mapped researcher with 205 DOIs from OpenAlex) this returned 3× more policy documents than ORCID-text-search because Overton doesn't always tag every co-authored or older article with the researcher's ORCID. See section 3d for the full filter catalog.

### 3a. Articles Endpoint (`/articles.php`)

Returns scholarly articles that have been cited by policy documents. Queried by ORCID.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `title` | string | Article title | `Tax Increment Financing` |
| `doi` | string | DOI | `10.1111/1540-5850.00809` |
| `document_url` | string | URL to article | `https://doi.org/...` |
| `container` | string | Container (journal) | `Public Budgeting & Finance` |
| `journal` | string | Journal name | `Public Budgeting & Finance` |
| `publisher` | string | Publisher | `Wiley` |
| `type` | string | Work type | `journal-article` |
| `published_on` | string | Publication date | `1989-01-01T00:00:00+00:00` |
| `authors` | string[] | Author names | `["Don E. Davis"]` |
| `orcids` | string[] | Author ORCIDs | `["0000-0003-3169-6576"]` |
| `isbns` | string[] | ISBNs (for books) | |
| `open_institution_authors` | string[] | Institutional affiliations (delimited) | `["Antioch University __OVSEP__ Don E Davis"]` |
| `language` | string | Language code | `en` |
| `abstract` | string | Article abstract | |
| `abstract_short` | string | Shortened abstract | |
| `funders` | string[] | Funding organizations | |
| `grant_ids` | string[] | Grant identifiers | |
| `citations` | int | Number of policy doc citations | `1` |
| `affiliations` | string[] | Author affiliations | |
| `oa_status` | string | Open access status | `closed`, `gold`, `green`, etc. |
| `last_cited` | string | Date of most recent policy citation | `2024-03-13` |
| `with_journal_subject` | string[] | Journal subject areas | `["Finance", "Economics and Econometrics"]` |
| `medline_mesh` | string[] | MeSH terms (biomedical articles) | |
| `citing_classifications` | string[] | IPTC classifications of citing documents | `["politics", "economy, business and finance>economy"]` |
| **cited_by_documents** (nested) | | **Policy documents that cite this article** | |

### 3b. Policy Documents Citing an Article (nested in Articles)

Each article contains an array of policy documents that cite it.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `policy_document_id` | string | Overton document ID | `kdi-b07b9be02393ac3841e94908465aadf0` |
| `policy_source_id` | string | Source organization ID | `kdi` |
| `source_title` | string | Publishing organization | `Korea Development Institute` |
| `document_title` | string | Policy document title | `2014/15 Knowledge Sharing Program with Vietnam I` |
| `published_on` | string | Publication date | `2015-09-30` |
| `overton_document_series` | string | Document series/type | `Publication` |
| `document_url` | string | URL to document | |
| `type` | string | Organization type | `think tank`, `government`, `igo` |
| `subtype` | string | Organization subtype | |
| `country` | string | Country of origin | `South Korea` |
| `source_primary_classification` | string | Primary class | `Third Sector` |
| `source_secondary_classification` | string | Secondary class | `Think Tank` |
| `source_tertiary_classification` | string[] | Tertiary classes | `["Research Centre", "Policy Centre"]` |
| `topics` | string[] | Policy topics | `["City", "Economic growth", "Infrastructure"]` |
| `classifications` | string[] | IPTC content classifications | `["economy, business and finance>economy", ...]` |
| `cited_by_child_pdfs` | object | PDF-level citation details | (PDF URLs and page numbers) |
| `url` | string | Overton document page | `https://app.overton.io/document.php?...` |

### 3c. Documents Endpoint (`/documents.php`)

Returns policy documents directly. Simpler structure than the articles endpoint.

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `policy_document_id` | string | Unique document ID | `cdc-c87cda9d4cc56f9c1f4021d7726b9ac4` |
| `title` | string | Document title | `Inhalation of Silver Silicate Nanoparticles...` |
| `source.title` | string | Source organization | `Centers for Disease Control and Prevention (CDC)` |
| `source.country` | string | Country | `USA` |
| `source.type` | string | Source type | `government` |
| `source.organisation_type` | string | Organization classification | `Government` |
| `published_on` | string | Publication date | `2022-01-01` |
| `topics` | string[] | Topic keywords | `["Microglia", "Nanotoxicology", ...]` |
| `sdgcategories` | string[] | UN Sustainable Development Goal categories | |
| `overton_url` | string | Overton page for this document | |

### 3d. Filter Parameters & DOI-Set Workflow

Filters validated against the live API (Swagger docs are incomplete). All recognized — we tested them by checking that Overton's response `description` field changes from "All articles" / "All documents" when the filter is parsed correctly.

**`/articles.php` filters:**

| Parameter | What it filters | Notes |
|---|---|---|
| `query` | Free-text search across title/abstract/authors/etc. | Used to be the pipeline's primary path (jam ORCID into this). Lossy. |
| `r_open_institution_authors` | Author-at-institution by canonical ID | Format: `{ROR}__OVSEP__{Display Name}__OVSEP__{lowercase_name}` — e.g. `https://ror.org/04p491231 __OVSEP__ Jonathan Foulds __OVSEP__ jonathan foulds`. Must match Overton's internal indexed name exactly (Crossref-derived). |
| `dois` | Single DOI or set ID | For >1 DOI, create a set first via `/generate_id_set.php` (see below). |
| `journal` | Articles in a named journal | e.g. `The Lancet` |
| `publisher` | Articles from a publisher | e.g. `Wiley` |
| `year` | Publication year | e.g. `2020` |

**`/documents.php` filters:**

| Parameter | What it filters | Notes |
|---|---|---|
| `query` | Free-text search across document text | |
| `r_open_cited_institution_authors` | Policy docs citing a person at an institution | Same `{ROR}__OVSEP__{Name}__OVSEP__{lower}` format as above |
| `plain_dois_cited` | Policy docs citing a specific DOI or set | Single DOI or set ID |
| `year` | Policy docs published in a year | |

**Plus the documented UI/facets**: people cited, source country, region, topics, SDG categories, journals cited, publishers cited, funders cited, document type, subject area.

**`POST /generate_id_set.php` — batching DOIs**

Because URL parameters can't carry hundreds of DOIs, batching uses this POST workflow:

```
POST https://app.overton.io/generate_id_set.php?format=json&api_key=<KEY>
Content-Type: application/x-www-form-urlencoded   ← REQUIRED, else body is silently mis-parsed

dois=10.1016/j.jadohealth.2015.09.004
10.1093/ntr/ntu071
10.1080/22221751.2024.2321993
```

Response:
```json
{"set": "set:25040:9406ebe5293849540ad765bc954f1118"}
```

Then use the set ID as the value of `dois=` (articles) or `plain_dois_cited=` (documents):
- `GET /articles.php?dois=set:25040:9406ebe5293849540ad765bc954f1118`
- `GET /documents.php?plain_dois_cited=set:25040:9406ebe5293849540ad765bc954f1118`

Tested ceiling: at least 10,000 DOIs per set (we never hit a limit). One POST per researcher is plenty.

**Rate limiting**: `/generate_id_set.php` has a sustained-burst limit per API key. We hit a 429 wall around researcher 80 in our first run with no pacing. Mitigation in `pipeline/overton_articles_stage.py`:
- 5/10/20/40s exponential backoff on 429
- `OVERTON_DELAY` (~0.2s) sleep between researchers in the run loop

The `api_request` helper in `pipeline/utils.py` already handles 429 retries for GETs but doesn't support POSTs — `_create_doi_set` has its own retry block.

**Discovering the canonical author identifier**: the `r_open_institution_authors` filter requires Overton's internal name spelling. The most reliable way to discover it is to query an article we know is by the researcher (via DOI lookup) and read the `r_open_institution_authors` field on the response. Don't try to construct the value from RMD or OpenAlex names — Crossref-derived spellings differ in subtle ways (unicode hyphens, accent marks).

---

## 4. Cross-Source Linkages

These are the key identifiers that allow joining data across sources:

| Link | Source A | Source B | Identifier |
|------|----------|----------|------------|
| Researcher identity | OpenAlex | RMD | **ORCID** (primary) or **DOI matching** (fallback via org publications) |
| Researcher identity | OpenAlex | Overton | **ORCID** |
| Researcher to PSU | OpenAlex | RMD | RMD WebAccess ID ← built from ORCID-to-WebAccess mapping |
| Publication matching | OpenAlex | RMD | **DOI** |
| Publication to policy | OpenAlex Works | Overton Articles | **DOI** |
| Funder matching | OpenAlex Funders | RMD Grants | Agency name (fuzzy) or Crossref Funder ID |
| Topic alignment | OpenAlex Topics | Overton Topics | No direct link; text matching possible |
| SDG alignment | N/A | Overton SDG Categories | Overton-specific |
| Journal context | OpenAlex Sources | Overton Journal Subjects | Journal name or ISSN |

---

## 5. What We Currently Capture vs. What's Available

### Currently captured in pipeline

| Source | What we pull | What we skip |
|--------|-------------|--------------|
| **OpenAlex** | Author: name, ORCID, works_count, cited_by_count, h_index, i10_index, 2yr_citedness, top 5 topics, affiliations | display_name_alternatives, topic_share, x_concepts, counts_by_year, Works (individual publications), Funders, Sources, Institutions |
| **RMD** | Profile: name, title, org, email, scopus_h_index, scopus_citations, bio, pure_url. Grants, presentations (count), ETDs (count), org memberships | Full presentation details, publication records, publication tags/keywords, advising roles, news feed items, performances, office info, teaching/research interests, education history, publication-grant linkages |
| **Overton** | Documents endpoint: policy_document_id, title, source (title/country/type/org_type), published_on, topics, sdgcategories, overton_url | Articles endpoint entirely (article-level citations, DOI-to-policy links, funders, grant_ids, journal subjects, MeSH terms, OA status, IPTC classifications, PDF-level citation locations, citing_classifications) |

### High-value fields not yet captured

1. **OpenAlex Works** — Individual publication records with DOIs, co-authors, OA status, and journal details. Enables publication-level analysis rather than just author-level counts.

2. **OpenAlex Counts by Year** — Year-over-year citation trends per author. Enables trajectory analysis (rising stars, declining impact, etc.).

3. **Overton Articles endpoint** — The richest Overton data. Links specific scholarly articles to specific policy documents. Includes which page of the PDF cites the article, IPTC classifications, MeSH terms, funder info, and journal subject areas.

4. **RMD Publication Tags** — Ranked keyword tags on each publication. Enables content analysis beyond OpenAlex topic classification.

5. **RMD Advising Roles** — Master's and PhD advising history with student names, thesis titles, and years. Enables mentorship network analysis.

6. **RMD Teaching & Research Interests** — Free-text descriptions of research focus and teaching areas. Useful for NLP/topic modeling.

7. **RMD News Feed Items** — Press coverage with URLs and dates. Measures public engagement beyond academic/policy impact.

8. **Overton SDG Categories** — UN Sustainable Development Goal alignment. Enables SDG-focused reporting on research impact.

9. **Overton IPTC Classifications** — Standardized news/content taxonomy on both citing and cited documents. Enables media-style topic analysis.

10. **OpenAlex Funder data** — Detailed funder profiles with works_count, cited_by_count, and cross-linkages. Could enrich the RMD grant data with funder-level impact metrics.

---

## 6. Data Volume Estimates (Full University Scale)

When full RMD access is enabled (all colleges, not just HHD):

| Metric | HHD Only (current) | Full University (projected) |
|--------|--------------------|-----------------------------|
| Researchers (OpenAlex, PSU + ORCID) | ~8,000 | ~8,000 (same — OpenAlex already covers all PSU) |
| RMD-matchable researchers | ~200-400 (HHD orgs) | ~3,000-5,000 (all colleges) |
| RMD organizations | ~10 | ~200+ |
| Grant records | Limited | ~20,000-50,000 |
| Presentation records | Limited | ~100,000+ |
| Publication records (RMD) | Limited | ~200,000+ |
| Policy documents (Overton) | ~1.3M references | ~1.3M (same — Overton coverage doesn't change) |
| Estimated total data size | ~3 GB | ~5-10 GB |
