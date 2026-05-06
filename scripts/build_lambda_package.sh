#!/bin/bash
# Build Lambda deployment package for the Overton pipeline.
# Installs dependencies and bundles pipeline code into a zip file,
# then uploads to S3.
#
# Usage: bash scripts/build_lambda_package.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/lambda"
OUTPUT_ZIP="$PROJECT_ROOT/build/pipeline-lambda.zip"
S3_BUCKET="overton-datalake-700032885189"
S3_KEY="lambda-packages/pipeline-lambda.zip"

echo "=== Building Lambda deployment package ==="

# Clean previous build
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Install dependencies into the build directory
# Use manylinux wheels compatible with Lambda (Amazon Linux 2023 / x86_64)
echo "Installing dependencies..."
pip install \
    --target "$BUILD_DIR" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    requests \
    tqdm \
    python-dotenv \
    psycopg2-binary \
    sqlalchemy \
    boto3 \
    2>&1 | tail -5

# Copy pipeline code
echo "Copying pipeline code..."
cp -r "$PROJECT_ROOT/pipeline" "$BUILD_DIR/pipeline"

# Remove unnecessary files from the package
find "$BUILD_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$BUILD_DIR/pipeline/Dockerfile"
rm -rf "$BUILD_DIR/boto3" "$BUILD_DIR/botocore" "$BUILD_DIR/s3transfer" "$BUILD_DIR/jmespath"  # Already in Lambda runtime

# Create zip
echo "Creating zip..."
cd "$BUILD_DIR"
rm -f "$OUTPUT_ZIP"
zip -r -q "$OUTPUT_ZIP" .

ZIP_SIZE=$(du -h "$OUTPUT_ZIP" | cut -f1)
echo "Package size: $ZIP_SIZE"

# Upload to S3
echo "Uploading to s3://$S3_BUCKET/$S3_KEY ..."
aws s3 cp "$OUTPUT_ZIP" "s3://$S3_BUCKET/$S3_KEY"

echo "=== Done ==="
echo "S3 location: s3://$S3_BUCKET/$S3_KEY"
