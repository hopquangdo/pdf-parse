# syntax=docker/dockerfile:1

# ---- 1. build the React UI ----
FROM node:22-alpine AS web
WORKDIR /web
COPY app/frontend/package.json app/frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY app/frontend/ ./
RUN npm run build

# ---- 2. runtime: FastAPI serves the API and the built UI from one process ----
FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 DATA_DIR=/data
WORKDIR /srv

COPY requirements.txt requirements-ocr.txt ./
RUN pip install -r requirements.txt

# Optional local OCR engine (VietOCR on CPU): docker build --build-arg LOCAL_OCR=1 ... then run with OCR_ENGINE=local.
# The weights are fetched at build time so the read-only container never downloads anything.
ARG LOCAL_OCR=0
ENV VIETOCR_WEIGHTS=/opt/vietocr/vgg_transformer.pth HOME=/tmp
RUN if [ "$LOCAL_OCR" = "1" ]; then \
      pip install -r requirements-ocr.txt && pip install --no-deps vietocr==0.3.13 \
      && mkdir -p /opt/vietocr \
      && python -c "import urllib.request; urllib.request.urlretrieve('https://vocr.vn/data/vietocr/vgg_transformer.pth', '/opt/vietocr/vgg_transformer.pth')"; \
    fi

COPY src ./src
COPY app ./app
COPY templates ./templates
COPY assets ./assets
COPY --from=web /web/dist ./app/frontend/dist

# Run as an unprivileged user; /data is the only writable place (uploads, run logs, exports).
RUN useradd --system --uid 10001 --no-create-home appuser && mkdir -p /data && chown appuser /data
USER appuser
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

# One worker on purpose: background extraction jobs and caches live in this process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
