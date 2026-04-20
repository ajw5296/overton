# CLAUDE.md

## Project Overview

PSU Research Impact Dashboard — combines data from OpenAlex, Penn State RMD (Researcher Metadata Database), and Overton to track how Penn State research is cited in policy documents. Streamlit dashboard deployed on ECS Fargate, backed by a 6-stage data pipeline orchestrated by Step Functions with Lambda fan-out, writing to RDS PostgreSQL + S3.

## Architecture

- **Database**: RDS PostgreSQL (db.t3.micro) with JSONB columns — `overton-postgres.c86jss96xcpx.us-east-1.rds.amazonaws.com`
- **Storage**: S3 bucket `overton-datalake-700032885189` for raw API response archival, PDF documents, and Lambda deployment packages
- **Dashboard**: Streamlit on ECS Fargate (existing `overton-dashboard` stack)
- **Pipeline**: 6-stage ETL via Lambda functions, with fan-out parallelism for stages 3-5
- **Orchestration**: Step Functions with Map states for fan-out + EventBridge for weekly scheduling
- **Region**: us-east-1
- **VPC**: vpc-b653f0cb (default VPC)
  - Public subnets: EC2 dev instance, NAT Gateway, ECS tasks
  - Private subnets: `subnet-05e2b3532a74fd147` (us-east-1a), `subnet-024916f3b1d8b27a7` (us-east-1b) — Lambda functions route through NAT Gateway for internet access while maintaining VPC access to RDS

## Pipeline Stages

```
Stage 1: OpenAlex Fetch        → researchers table           (single Lambda)
Stage 2: RMD Enrichment        → researchers table (update)  (single Lambda)
Stage 3: Overton Articles      → articles + article_citations (fan-out via Map)
Stage 4: Overton Documents     → policy_documents table      (fan-out via Map)
Stage 5: Document PDF Download → S3                          (fan-out via Map)
Stage 6: Export (optional)     → flat JSON files for backward compat
```

Fan-out pattern for stages 3-5:
1. Chunker Lambda splits work into chunks (e.g., 50 ORCIDs, 200 doc IDs)
2. Step Functions Map state invokes up to 10 parallel Lambda workers
3. Each worker processes its chunk and writes to RDS (idempotent upserts)

Run locally:
```bash
export AWS_DEFAULT_REGION=us-east-1
export DATABASE_SECRET_ARN="arn:aws:secretsmanager:us-east-1:700032885189:secret:overton/rds-credentials-M85fjC"
export S3_BUCKET_NAME="overton-datalake-700032885189"
export OPENALEX_EMAIL="overton-pipeline@psu.edu"
export OVERTON_API_KEY="<from secretsmanager: overton/api-keys/overton>"
export PSU_RESEARCH_API_KEY="<from secretsmanager: overton/api-keys/rmd>"

python -m pipeline.run --all --incremental           # Full incremental run
python -m pipeline.run --stage openalex --max-researchers 50  # Test with 50
python -m pipeline.run --all --skip-export            # Skip flat file export
```

## Database Tables

- `researchers` — PK: orcid, JSONB data column with full OpenAlex+RMD+Overton profile
- `articles` — PK: doi, from Overton Articles API
- `policy_documents` — PK: policy_document_id, from Overton Documents API
- `article_citations` — junction table (doi, policy_document_id), FK to both
- `pipeline_metadata` — run tracking (run_id, stage, status, stats)

## CloudFormation Stacks

| Stack | Template | Status |
|-------|----------|--------|
| `overton-ecr` | ecr-only.yaml | Deployed |
| `overton-dashboard` | ecs-fargate.yaml | Deployed |
| `overton-vpc-endpoints` | vpc-endpoints.yaml | Deployed |
| `overton-s3-datalake` | s3-datalake.yaml | Deployed |
| `overton-rds` | rds-postgres.yaml | Deployed |
| `overton-pipeline-iam` | pipeline-iam.yaml | Deployed |
| `overton-nat-gateway` | nat-gateway.yaml | Deployed |
| `overton-lambda-functions` | lambda-functions.yaml | Deployed |
| `overton-step-functions` | step-functions.yaml | Deployed |

## Lambda Functions

| Function | Handler | Purpose |
|----------|---------|---------|
| `overton-openalex` | `openalex_handler` | Stage 1: Fetch PSU researchers from OpenAlex |
| `overton-rmd` | `rmd_handler` | Stage 2: Enrich researchers with RMD data |
| `overton-chunker` | `chunker_handler` | Split work into chunks for Map state fan-out |
| `overton-articles` | `overton_articles_handler` | Stage 3: Fetch Overton articles (chunk worker) |
| `overton-documents` | `overton_documents_handler` | Stage 4: Fetch policy document metadata (chunk worker) |
| `overton-document-download` | `document_download_handler` | Stage 5: Download PDFs to S3 (chunk worker) |

Lambda deployment package: `s3://overton-datalake-700032885189/lambda-packages/pipeline-lambda.zip`
Build script: `scripts/build_lambda_package.sh`

To rebuild and update Lambda code:
```bash
bash scripts/build_lambda_package.sh
for fn in overton-openalex overton-rmd overton-chunker overton-articles overton-documents overton-document-download; do
  aws lambda update-function-code --function-name "$fn" --s3-bucket overton-datalake-700032885189 --s3-key lambda-packages/pipeline-lambda.zip
done
```

## Key Security Groups

- `sg-098cc4d9e34afd357` — overton-dashboard-task-sg (ECS tasks + Lambda functions)
- `sg-0a14c4c496906c471` — overton-dashboard-alb-sg (ALB)
- `sg-003335a00482554ab` — overton-rds-sg (RDS, allows 5432 from task SG)
- `sg-09b766244cf6996ea` — alex-dev-sg (dev instance, has temp RDS access via sgr-058461653ed7a8a36)

## Secrets Manager

- `overton/rds-credentials` — DB username/password/host/port (auto-generated)
- `overton/api-keys/overton` — Overton API key
- `overton/api-keys/rmd` — PSU RMD API key

## Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `DATABASE_SECRET_ARN` | RDS credentials secret ARN | Yes (or DATABASE_URL) |
| `DATABASE_URL` | Direct PostgreSQL connection string (local dev) | Alternative to above |
| `S3_BUCKET_NAME` | S3 data lake bucket | Yes for S3 archival |
| `AWS_DEFAULT_REGION` | AWS region (local only, reserved in Lambda) | Yes for local runs |
| `OPENALEX_EMAIL` | Contact email for OpenAlex API | Yes |
| `OVERTON_API_KEY` | Overton API key | Yes for stages 3-4 |
| `PSU_RESEARCH_API_KEY` | RMD API key | Yes for stage 2 |

## Project Structure

```
pipeline/               — 6-stage ETL pipeline
  lambda_handlers/      — Lambda entry points for each stage + chunker
  db/                   — PostgreSQL + S3 data layer (connection, schema, operations, s3_client)
  run.py                — CLI orchestrator (local runs)
  config.py             — All configuration (auto-detects Lambda via IS_LAMBDA)
  models.py             — TypedDict schemas
dashboard/              — Streamlit app
  utils/                — data_loader.py (DB with flat file fallback), db_connection.py
  pages/                — 4 dashboard pages
infrastructure/         — CloudFormation templates
scripts/                — Build scripts (build_lambda_package.sh)
data/                   — Local data files (gitignored)
docs/                   — Data source docs, API sample JSONs (docs/api_samples/)
archive/                — Old standalone scripts, notebooks, and pre-migration plan
```

## Conventions

- All pipeline writes use upsert (INSERT ... ON CONFLICT DO UPDATE) — idempotent and safe for incremental runs and parallel fan-out workers
- Dashboard tries PostgreSQL first, falls back to flat JSON files if DB unavailable
- Raw API responses archived to `s3://bucket/raw-api-responses/{stage}/{date}/{id}.json`
- PDFs stored at `s3://bucket/policy-documents/{policy_document_id}.pdf`
- Lambda deployment package at `s3://bucket/lambda-packages/pipeline-lambda.zip`
- All infrastructure tagged with `Project: overton`
- Deploy stacks with `--tags "Project=overton"`
- Lambda functions use `/tmp` for any file writes (detected via `IS_LAMBDA` in config.py)

## Networking Note

Lambda functions run in private subnets with a NAT Gateway for outbound internet access. This is required because VPC-attached Lambdas don't get public IPs, but they need both VPC access (for RDS) and internet access (for external APIs like OpenAlex, Overton, RMD). The NAT Gateway costs ~$32/month.

## IAM Note

The dev instance role `alex-dev-instance-role` currently has `AdministratorAccess` attached for deployment. This should be scoped down to specific policies needed for day-to-day use.
