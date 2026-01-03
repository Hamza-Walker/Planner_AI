# Dockerfile - Eco profile (energy-efficient, smaller models)
# Default profile optimized for sustainability

FROM python:3.11-slim

# Build argument for profile identification
ARG DEPLOYMENT_PROFILE=eco
ENV DEPLOYMENT_PROFILE=${DEPLOYMENT_PROFILE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

# Eco profile: Use smaller, more efficient models
ENV LLM_MODEL_LARGE=gpt-3.5-turbo
ENV LLM_MODEL_SMALL=gpt-3.5-turbo
ENV ENERGY_PRICE_THRESHOLD_EUR=0.50

WORKDIR /app

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY src/ ./src/

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Labels for identification
LABEL org.opencontainers.image.title="Planner_AI (Eco Profile)"
LABEL org.opencontainers.image.description="Energy-efficient profile for high carbon-intensity periods"
LABEL sustainability.profile="eco"
LABEL sustainability.model-tier="small"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
