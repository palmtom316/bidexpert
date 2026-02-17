FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       libreoffice \
       tesseract-ocr \
       tesseract-ocr-chi-sim \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY alembic.ini ./
COPY docs ./docs
COPY app ./app
COPY migrations ./migrations
COPY sql ./sql

RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
