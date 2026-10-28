# Optional: a clean, pinned environment for `make reproduce` (no API key needed). Build: docker build -t policy-agent .
# Run:   docker run --rm policy-agent            (downloads the public datasets once, then rebuilds, tests and regenerates the report)
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends make && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_LINK_MODE=copy

# dependencies first, so the layer is cached until pyproject.toml or uv.lock change
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen

COPY . .
RUN uv sync --frozen
CMD ["make", "reproduce"]
