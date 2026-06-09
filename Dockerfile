# Aethvion Project Mapper — Docker image
# -----------------------------------------
# Multi-stage build: keep the final image lean (~180 MB).
#
# Build:   docker build -t aethvion-pm .
# Run:     docker run -p 7474:7474 -v /my/projects:/projects aethvion-pm
# MCP:     docker run --rm -i aethvion-pm python -m project_mapper.mcp_server \
#              --db my_project --project-root /projects/my_project

# ---- Stage 1: build wheels ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml .
COPY project_mapper/ project_mapper/
COPY server.py .

RUN pip install --upgrade pip \
 && pip wheel --no-deps --wheel-dir /wheels .

# ---- Stage 2: runtime ----
FROM python:3.12-slim

LABEL org.opencontainers.image.title="Aethvion Project Mapper" \
      org.opencontainers.image.description="Static code analysis + knowledge-graph for AI agents" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

# Non-root user for security
RUN useradd -m -u 1000 pm
USER pm
WORKDIR /app

COPY --from=builder /wheels /wheels

# Install runtime deps + our package
RUN pip install --no-index --find-links=/wheels /wheels/*.whl \
 && pip install fastapi "uvicorn[standard]" pydantic \
 && rm -rf /wheels

# Copy source
COPY --chown=pm:pm project_mapper/ project_mapper/
COPY --chown=pm:pm server.py .

# Data directory (databases live here)
RUN mkdir -p /home/pm/.aethvion_pm/data
ENV PM_DATA_DIR=/home/pm/.aethvion_pm/data
ENV PM_LOG_LEVEL=INFO

EXPOSE 7474

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7474/health')"

CMD ["sh", "-c", "pm-server --host 0.0.0.0 --port ${PORT:-7474}"]
