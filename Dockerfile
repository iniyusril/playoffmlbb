# ── Stage 1: base image dengan Playwright Chromium ──────────────────────────
FROM mcr.microsoft.com/playwright/python:v1.59.0-jammy AS base

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Playwright browsers sudah tersedia di base image Microsoft
# (chromium sudah preinstalled di /ms-playwright)

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM base AS runtime

WORKDIR /app

COPY . .

# Non-root user untuk keamanan
RUN useradd --no-create-home --shell /bin/false appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 9009

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9009"]
