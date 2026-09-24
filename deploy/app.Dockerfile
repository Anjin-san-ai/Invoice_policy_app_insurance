# Single image for all three Python services (neuro-san server, nsflow, invoice backend).
# Each Azure Container App runs this same image with a different start command.
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

# Dependency layer (cached until requirements change)
COPY requirements.txt requirements-build.txt ./
RUN pip install -r requirements.txt -r requirements-build.txt \
    fastapi "uvicorn[standard]" pydantic httpx

# Application
COPY . .
RUN pip install -e .

# Point the Neuro-SAN server at this repo's registries/coded_tools (not the packaged examples).
ENV AGENT_MANIFEST_FILE="/app/registries/manifest.hocon" \
    AGENT_TOOL_PATH="/app/coded_tools" \
    AGENT_TOOLBOX_INFO_FILE="/app/neuro_san_studio/toolbox/toolbox_info.hocon"

# One image, three services. Each Container App sets SERVICE=neuro-san|nsflow|invoice-api
# and the entrypoint dispatches — avoids per-app command overrides.
RUN chmod +x deploy/service-entrypoint.sh
ENTRYPOINT ["bash", "deploy/service-entrypoint.sh"]
