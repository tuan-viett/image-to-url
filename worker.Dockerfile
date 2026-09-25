FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /worker

# System deps for cryptography wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    libssl-dev \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install the SAME dependencies as the API. The worker is just a separate
# entrypoint (app.tasks.cleanup_runner) that reuses the api/ package.
COPY api/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && pip install -r /tmp/requirements.txt

# Copy the api source so `app.*` imports resolve.
COPY api /api

ENV PYTHONPATH=/worker:/api

CMD ["python", "-m", "app.tasks.cleanup_runner"]