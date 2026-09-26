FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt || pip install --no-cache-dir .
COPY . .
ARG C33_BUILD_SHA=unknown
ENV PYTHONPATH=/app C33_BUILD_SHA=$C33_BUILD_SHA
EXPOSE 8080
CMD ["sh", "-c", "uvicorn src.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
