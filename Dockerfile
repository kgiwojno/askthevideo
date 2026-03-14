FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY api/ api/
COPY config/ config/
COPY frontend/ frontend/
COPY .git/ .git/
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    git rev-parse --short HEAD > /app/.git_sha && \
    rm -rf .git && \
    apt-get purge -y git && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
EXPOSE 8000
HEALTHCHECK CMD curl --fail http://localhost:8000/health || exit 1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
