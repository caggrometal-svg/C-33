FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src:/app

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src

RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install .

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
