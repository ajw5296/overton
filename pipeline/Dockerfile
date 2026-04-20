FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline package
COPY pipeline/ ./pipeline/

# Default: run all stages incrementally
ENTRYPOINT ["python", "-m", "pipeline.run"]
CMD ["--all", "--incremental"]
