# Build from the project root, not from this folder:
#     docker build -f docker/Dockerfile -t labpilot .
#     docker run --rm -p 8000:8000 --env-file .env labpilot
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copied alone so the layer is cached until the pinned versions change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY labpilot/ ./labpilot/
COPY web/ ./web/

# Never bake .env into the image. Keys come from the platform at run time, and
# load_dotenv does not override what the environment already supplies.
RUN useradd --create-home --uid 1000 labpilot
USER labpilot

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health')"

# One worker on purpose: the free tier is 512MB and every worker is a full copy
# of the interpreter. The route is a plain def, so uvicorn's thread pool already
# serves concurrent requests without a second process.
CMD ["uvicorn", "labpilot.api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
