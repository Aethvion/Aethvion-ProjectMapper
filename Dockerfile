# Aethvion Project Mapper — Docker image
# -----------------------------------------
# Build:   docker build -t aethvion-pm .
# Run:     docker run -p 7474:7474 aethvion-pm
# MCP:     docker run --rm -i aethvion-pm python -m project_mapper.mcp.server \
#              --db my_project --project-root /projects/my_project

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Aethvion Project Mapper" \
      org.opencontainers.image.description="Static code analysis + knowledge-graph for AI agents" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

WORKDIR /app

# Copy package source and install (pulls deps from PyPI)
COPY pyproject.toml .
COPY project_mapper/ project_mapper/

RUN pip install --no-cache-dir .[languages]

# Non-root user for security
RUN useradd -m -u 1000 pm \
 && mkdir -p /home/pm/.aethvion_pm/data \
 && chown -R pm:pm /home/pm/.aethvion_pm

USER pm

ENV PM_DATA_DIR=/home/pm/.aethvion_pm/data
ENV PM_LOG_LEVEL=INFO

EXPOSE 7474

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7474/health')"

CMD ["sh", "-c", "pm-server --host 0.0.0.0 --port ${PORT:-7474}"]
