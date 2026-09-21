# Neural Log, as one image.
#
# Two stages, and the split is the point. The frontend needs Node and 200 MB of
# node_modules to produce about 600 KB of static files; the runtime needs Python
# and none of that. Building them in one stage would ship the toolchain to
# production - a ~1.2 GB image where 180 MB does the same job, on a box with
# 1 GB of RAM.
#
# It also means the instance never builds anything. CI builds the image, the
# instance pulls it, and a redeploy is a download rather than a compile. That
# matters more than it sounds: `npm run build` on a 512 MB instance is a coin
# flip against the OOM killer, and losing that flip takes the site down.

# --- stage 1: the SPA --------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build

# package files first, so `npm ci` is only re-run when dependencies actually
# change rather than on every source edit.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# --- stage 2: the app --------------------------------------------------------
FROM python:3.13-slim AS runtime

# The commit this image was built from, baked in at build time.
#
# The VERSION file says which release the code belongs to, which only changes
# when somebody cuts one. This says exactly which build is running, which is the
# question you actually have when production is behaving oddly - and it is what
# lets the deploy assert that the thing it just pushed is the thing now serving.
ARG GIT_SHA=unknown

# PYTHONUNBUFFERED so logs appear as they happen rather than when a buffer
# fills - the difference between watching a deploy and guessing at one.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NEURAL_LOG_ENV=production \
    NEURAL_LOG_COMMIT=$GIT_SHA

# sqlite3 for the backup script's `.backup` command, which is the only safe way
# to copy a database that is being written to. curl for the health check.
RUN apt-get update \
    && apt-get install -y --no-install-recommends sqlite3 curl \
    && rm -rf /var/lib/apt/lists/*

# A user that is not root. If something does get through, it should land as
# somebody who cannot write to the application code.
RUN useradd --create-home --uid 10001 neurallog

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=neurallog:neurallog . .
COPY --from=frontend --chown=neurallog:neurallog /build/dist ./frontend/dist

# The database lives on a mounted volume, never in the image. /data is where the
# compose file mounts the host directory; DATABASE points at it.
ENV DATABASE=/data/neural_log.db
RUN mkdir -p /data && chown neurallog:neurallog /data
VOLUME ["/data"]

USER neurallog
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:app"]
