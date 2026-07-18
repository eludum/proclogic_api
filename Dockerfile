# syntax=docker/dockerfile:1

# ── Builder: full toolchain, resolves/compiles deps into an isolated venv ──
# build-essential lives ONLY in this throwaway stage, so gcc/cc1 and the rest of
# the build toolchain never reach the shipped image. (Nearly all our deps ship
# manylinux wheels, but keep the compiler here so a wheel-less package still builds.)
# Unpinned base + unpinned requirements → every rebuild pulls the latest of everything.
FROM python:slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir --upgrade -r /tmp/requirements.txt

# ── Runtime: slim base + the prebuilt venv only (no compiler, no build tools) ──
FROM python:slim AS runtime

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY ./alembic.ini /code/alembic.ini
COPY ./alembic /code/alembic
COPY ./app /code/app

EXPOSE 80

CMD ["uvicorn", "app.main:proclogic", "--host", "0.0.0.0", "--port", "80"]

# # If running behind a proxy like Nginx or Traefik add --proxy-headers
# CMD ["fastapi", "run", "app/main.py", "--port", "80", "--proxy-headers"]
