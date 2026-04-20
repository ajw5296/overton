"""S3 operations for raw API response archival and PDF document storage."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_s3_client = None


def get_s3_client():
    """Return a singleton boto3 S3 client."""
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def _get_bucket() -> str:
    bucket = os.getenv("S3_BUCKET_NAME")
    if not bucket:
        raise RuntimeError("S3_BUCKET_NAME environment variable is not set.")
    return bucket


def upload_raw_response(
    stage: str, identifier: str, data: dict, bucket: str | None = None
) -> str:
    """Upload a raw API response JSON to S3 for archival.

    Stored at: raw-api-responses/{stage}/{YYYY-MM-DD}/{identifier}.json

    Returns the S3 key.
    """
    bucket = bucket or _get_bucket()
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prefix = os.getenv("S3_RAW_PREFIX", "raw-api-responses")
    key = f"{prefix}/{stage}/{date_prefix}/{identifier}.json"

    get_s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    logger.debug("Uploaded raw response to s3://%s/%s", bucket, key)
    return key


def upload_pdf(
    policy_document_id: str,
    pdf_bytes: bytes,
    bucket: str | None = None,
    content_type: str = "application/pdf",
) -> str:
    """Upload a policy document PDF to S3.

    Stored at: policy-documents/{policy_document_id}.pdf

    Returns the S3 key.
    """
    bucket = bucket or _get_bucket()
    prefix = os.getenv("S3_PDF_PREFIX", "policy-documents")
    key = f"{prefix}/{policy_document_id}.pdf"

    get_s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=pdf_bytes,
        ContentType=content_type,
        ContentDisposition="inline",
    )
    logger.info("Uploaded PDF to s3://%s/%s", bucket, key)
    return key


def generate_presigned_url(
    key: str, expires_in: int = 3600, bucket: str | None = None
) -> str:
    """Generate a presigned URL for an S3 object.

    Args:
        key: S3 object key.
        expires_in: URL expiration time in seconds (default 1 hour).
        bucket: S3 bucket name (defaults to S3_BUCKET_NAME env var).

    Returns:
        Presigned URL string.
    """
    bucket = bucket or _get_bucket()
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


def load_json_from_s3(key: str, bucket: str | None = None) -> dict | list | None:
    """Load a JSON file from S3. Returns None if not found."""
    bucket = bucket or _get_bucket()
    try:
        response = get_s3_client().get_object(Bucket=bucket, Key=key)
        return json.loads(response["Body"].read().decode("utf-8"))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        raise


def save_json_to_s3(key: str, data: dict | list, bucket: str | None = None) -> str:
    """Save a JSON object to S3. Returns the S3 key."""
    bucket = bucket or _get_bucket()
    get_s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(data, default=str).encode("utf-8"),
        ContentType="application/json",
    )
    logger.info("Saved JSON to s3://%s/%s", bucket, key)
    return key


def pdf_exists(
    policy_document_id: str, bucket: str | None = None
) -> bool:
    """Check whether a PDF already exists in S3 for a given policy document."""
    bucket = bucket or _get_bucket()
    prefix = os.getenv("S3_PDF_PREFIX", "policy-documents")
    key = f"{prefix}/{policy_document_id}.pdf"

    try:
        get_s3_client().head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == "404":
            return False
        raise
