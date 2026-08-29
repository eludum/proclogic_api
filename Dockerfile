# syntax=docker/dockerfile:1

# ── Builder: full toolchain, resolves/compiles deps into an isolated venv ──
# build-essential lives ONLY in this throwaway stage, so gcc/cc1 and the rest of
# the build toolchain never reach the shipped image. (Nearly all our deps ship
# manylinux wheels, but keep the compiler here so a wheel-less package still builds.)
# Base pinned to a minor version: `python:slim` floats across majors, so a
# rebuild could have moved the interpreter under the app without anything in the
# repo changing. 3.14-slim still receives patch and OS security updates, which a
# digest pin would freeze out.
FROM python:3.14-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install the lock, not requirements.txt: the lock pins the full transitive
# closure, so the built image is the same on every rebuild. No --upgrade, which
# would defeat the pins.
COPY requirements.lock.txt /tmp/requirements.lock.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r /tmp/requirements.lock.txt

# ── Runtime: slim base + the prebuilt venv only (no compiler, no build tools) ──
FROM python:3.14-slim AS runtime

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

# No `playwright install` here on purpose: nothing the API or the scraper worker
# serves drives a browser. The one Playwright caller, app/util/web_scraper.py,
# is imported only by scripts/backfill_contracts, which is run from a checkout
# with its own venv — installing Chromium here would add ~1.4 GB for code this
# image never executes.

WORKDIR /code

COPY ./alembic.ini /code/alembic.ini
COPY ./alembic /code/alembic
COPY ./app /code/app
# The one-off maintenance jobs (backfill_searchable_content, backfill_description_kind)
# have to be runnable against production, and the only place with the right
# database credentials and network path is a pod. Without these in the image
# there is no way to run them short of a laptop with a tunnel to the cluster.
# backfill_contracts is the exception -- it drives Playwright, which this image
# deliberately does not ship (see above) -- so it stays a checkout-only script.
COPY ./scripts /code/scripts

EXPOSE 80

CMD ["uvicorn", "app.main:proclogic", "--host", "0.0.0.0", "--port", "80"]

# # If running behind a proxy like Nginx or Traefik add --proxy-headers
# CMD ["fastapi", "run", "app/main.py", "--port", "80", "--proxy-headers"]
