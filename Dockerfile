# Backend Titisanku — FastAPI (Helipod/GHCR build)
FROM python:3.12-slim

WORKDIR /app

# Copy backend (bukan frontend, biar image kecil)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/

EXPOSE 8000

# Healthcheck sederhana (FastAPI /health)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]