FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE requirements-tested.txt ./
COPY src ./src
ARG PHISHGUARD_EXTRAS=api
RUN pip install --no-cache-dir -c requirements-tested.txt ".[${PHISHGUARD_EXTRAS}]" && useradd --uid 10001 --create-home phishguard
USER 10001
EXPOSE 8000
# Mount trusted model read-only and writable data dir if opting into event storage.
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "phishguard.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
