# syntax=docker/dockerfile:1

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# FFmpeg and FFprobe render the approved local edit plan at runtime.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

FROM base AS test

COPY tests ./tests
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]

FROM base AS runtime

# Mount source videos and transcripts into /work when running the container.
WORKDIR /work
ENTRYPOINT ["youtube-video-editor"]
