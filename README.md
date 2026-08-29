<div align="center">

<img src="https://raw.githubusercontent.com/eludum/proclogic_api/main/assets/proclogic.svg" alt="ProcLogic Logo" width="120" height="120">


</div>

# ProcLogic API

**The first fully open-source public tender platform - Backend API**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)

</div>

---

ProcLogic API is the backend service powering the ProcLogic platform. It provides a comprehensive REST API for managing public procurement tenders, user authentication, subscriptions, AI-powered chat, and more.

## Features

- **Publication Management**: Fetch, search, and manage public tender publications, with a public (unauthenticated) free tier alongside the full authenticated API
- **AI-Powered Chat**: Conversation API backed by OpenAI, scoped to a publication and its documents
- **Smart Scraping**: Background worker that polls the BOSA e-Procurement API and gathers notifications
- **Contract Awards**: Award/contract tracking with automated winner emails and open-tracking
- **Kanban Pipeline**: Per-company boards to track publications through custom statuses
- **Notifications**: In-app notifications plus email delivery over Mailtrap SMTP
- **Company Profiles**: Company/VAT records, team invites, and website scraping (httpx + BeautifulSoup, summarised by OpenAI) used to pre-fill onboarding and build recommendations
- **User Authentication**: Secure JWT-based auth via Clerk (JWKS validated, cache pre-warmed at startup)
- **Subscription Management**: Stripe webhooks for payment and subscription state
- **Document Handling**: Streamed download and extraction of tender document archives
- **Caching**: Redis-based caching for search results and document sets
- **Database**: PostgreSQL with SQLAlchemy ORM; Alembic migrations run automatically at startup
- **Error Tracking**: Structured stdout logging plus a global exception handler, ready for any log-shipping/alerting stack

## Prerequisites

- Python 3.11 or higher
- PostgreSQL 14+ database
- Redis server
- Clerk account (for authentication)
- OpenAI API key (for AI features)
- Stripe account (for payments)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/eludum/proclogic_api.git
cd proclogic_api
```

### 2. Set up Python virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
playwright install chromium  # Only needed to run scripts/backfill_contracts
```

### 4. Obtain BOSA public procurement API Credentials

Before setting up environment variables, you need to obtain API credentials from the Belgian public procurement system (BOSA):

**⚠️ Important**: You must contact BOSA to get your `PUBPROC_CLIENT_ID` and `PUBPROC_CLIENT_SECRET`.

**Steps to obtain credentials:**

1. Visit the [BOSA e-Procurement Helpdesk](https://bosa.belgium.be/nl/services/helpdesk-e-procurement)
2. Navigate to **Partners and Media**
3. Go to **Onboarding for the API**
4. Follow the onboarding process to request your API credentials
5. BOSA will provide you with:
   - Client ID (`PUBPROC_CLIENT_ID`)
   - Client Secret (`PUBPROC_CLIENT_SECRET`)

**Note**: The API credentials are required to access Belgian public procurement data. Without these, the application will not be able to fetch tender publications.

### 5. Set up environment variables

Create a `.env` file in the root directory (see `env_example`):

```bash
# Database
POSTGRES_CON_URL=postgresql://user:password@localhost:5432/proclogic

# Authentication
CLERK_SECRET_KEY=sk_test_...
CLERK_JWKS_URL=https://your-clerk-instance/.well-known/jwks.json

# AI Services
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-mini  # optional, this is the default

# PubProc Integration (Belgian public procurement system)
# ⚠️ Obtain these credentials from BOSA (see step 4 above)
PUBPROC_SERVER=https://enot.publicprocurement.be
PUBPROC_TOKEN_URL=https://.../oauth2/token
PUBPROC_CLIENT_ID=your-client-id-from-bosa
PUBPROC_CLIENT_SECRET=your-client-secret-from-bosa

# Stripe Payments
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Redis Cache
REDIS_HOST=localhost
REDIS_PORT=6379

# Email
MAILTRAP_TOKEN=your-mailtrap-token
MAIL_FROM=info@yourdomain.com

# Optional
DEBUG_MODE=true  # Enable debug logging and expose /docs
```

**Important**: Never commit `.env` to version control. It's already in `.gitignore`.

### 6. Set up PostgreSQL and Redis

#### Option A: Using Docker Compose (recommended)

`compose.yml` starts PostgreSQL, Redis (redis-stack) and pgAdmin, so this covers both datastores.

Create `.env.postgres` file (see `env_postgres_example`):

```bash
POSTGRES_USER=proclogic
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=proclogic
PGADMIN_DEFAULT_EMAIL=admin@yourdomain.com
PGADMIN_DEFAULT_PASSWORD=your-admin-password
```

Start the stack:

```bash
docker compose up -d
```

Services:
- **PostgreSQL**: localhost:5432 (container `postgres_proc`)
- **Redis**: localhost:6379, RedisInsight on http://localhost:8001 (container `redis_proc`)
- **pgAdmin**: http://localhost:8002 (container `pgadmin_proc`)

To get the PostgreSQL container IP for pgAdmin:
```bash
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' postgres_proc
```

#### Option B: Local PostgreSQL installation

```bash
# Install PostgreSQL (platform-specific)
# Then create database and user:
createdb proclogic
psql -c "CREATE USER proclogic WITH PASSWORD 'your-password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE proclogic TO proclogic;"
```

You will also need a Redis server reachable at `REDIS_HOST`/`REDIS_PORT`.

### 7. Run database migrations

The app runs `alembic upgrade head` itself on startup (see `app/util/alembic_runner.py`), so this is only needed if you want to migrate ahead of time:

```bash
alembic upgrade head
```

### 8. Start the development server

```bash
fastapi dev app/main.py
```

The API will be available at:
- **API**: http://localhost:8000
- **Interactive docs**: http://localhost:8000/docs
- **Alternative docs**: http://localhost:8000/redoc

**Note**: the docs are only mounted when `DEBUG_MODE=true`. In production `docs_url` is `None`, so `/docs` returns 404 by design.

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `POSTGRES_CON_URL` | PostgreSQL connection string | Yes | - |
| `CLERK_SECRET_KEY` | Clerk authentication secret | Yes | - |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint for JWT validation | No | `https://clerk.proclogic.be/.well-known/jwks.json` |
| `OPENAI_API_KEY` | OpenAI API key for AI features | Yes | - |
| `OPENAI_MODEL` | Model used for chat, summaries and recommendations | No | `gpt-5-mini` |
| `PUBPROC_SERVER` | Public procurement API server | Yes | - |
| `PUBPROC_TOKEN_URL` | OAuth2 token endpoint for the procurement API | Yes | - |
| `PUBPROC_CLIENT_ID` | OAuth client ID for procurement system (obtain from BOSA) | Yes | - |
| `PUBPROC_CLIENT_SECRET` | OAuth client secret (obtain from BOSA) | Yes | - |
| `STRIPE_SECRET_KEY` | Stripe secret key for payments | Yes | - |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature secret | Yes | - |
| `REDIS_HOST` | Redis server hostname | No | `proclogic-redis` |
| `REDIS_PORT` | Redis server port | No | `6379` |
| `REDIS_DB` | Redis database index | No | `0` |
| `MAILTRAP_TOKEN` | Mailtrap API token, used as the SMTP password against `live.smtp.mailtrap.io` | No | - |
| `MAIL_FROM` | Sender email address | No | `info@proclogic.be` |
| `DEBUG_MODE` | Enable debug logging and expose `/docs` | No | `false` |
| `SCRAPER_MODE` | Run as background scraper worker | No | `false` |
| `MCP_ENABLED` | Mount the MCP server at `/mcp` and give Procy its database tools | No | `true` |
| `MCP_TRANSPORT` | `inprocess` (dispatch directly) or `http` (drive a real MCP client against `/mcp`) | No | `inprocess` |
| `MCP_SERVICE_TOKEN` | Bearer token used only when `MCP_TRANSPORT=http` | No | - |
| `MCP_SQL_TOOL_ENABLED` | Offer the read-only SQL tool (also needs `POSTGRES_RO_CON_URL`) | No | `true` |
| `POSTGRES_RO_CON_URL` | Connection string for a **read-only** role. Without it the SQL tool is not registered at all | No | - |
| `FRONTEND_BASE_URL` | Used to build the links Procy cites | No | `https://app.proclogic.be` |

Settings are declared in `app/config/settings.py` (pydantic-settings). Anything without a default is required at import time — the process fails fast on a missing value rather than erroring at first use.

## Monitoring & Error Alerting

The API ships no hosted error tracker and no APM agent. Error reporting is
log-based, so it plugs into whatever log pipeline you already run:

- The app logs to **stdout** (`logging.StreamHandler`), unbuffered in the
  container, so any log shipper can collect it. The level is `ERROR` by default
  and `INFO` when `DEBUG_MODE=true`.
- A global FastAPI exception handler (in `app/main.py`) logs every unhandled
  request exception at `ERROR` level with a full traceback, and returns a
  generic 500 so internals are never leaked to the client.
- `/health` returns 200 and is filtered out of the uvicorn access log, so it is
  cheap to poll from a liveness probe or an external uptime check.

To get alerting, point your stack at those two signals: match
error/exception/traceback lines in the container logs, and probe `/health` for
uptime. No application configuration is required — just don't route logging
away from stdout.

## Performance & Resource Safeguards

Tender document sets are large (multi-GB archives are not unusual), so several
paths are deliberately streaming-first. Keep these invariants in mind when
touching them:

- **Document downloads stream to disk** (`app/util/pubproc.py`), never into
  memory — an unbounded read previously OOM-killed the scraper pod.
- **ZIP extraction is bounded** (`app/util/zip.py`): members spill to disk, and
  the archive is refused up-front unless it fits within the free-disk budget
  (capped at 6 GiB uncompressed) with headroom left on the node.
- **Redis never caches oversized payloads** (`app/util/redis_cache.py`): entries
  above `MAX_CACHE_ENTRY_BYTES` (25 MiB) are skipped and re-fetched on demand,
  and document sets are sized by seek rather than by reading them into RAM.
- **Search eager-loads collections** (`selectinload`) to avoid the N+1 that made
  search take ~12s and time out behind the ingress.
- **Two OpenAI clients** (`app/ai/openai.py`): an `AsyncOpenAI` for interactive
  request paths (chat, website scraping) and a blocking `OpenAI` for long batch
  work, which must only be called via `asyncio.to_thread` so it never stalls the
  event loop.

## API Documentation

With `DEBUG_MODE=true` and the server running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Main API Endpoints

All endpoints require a Clerk bearer token except `/health`, the Stripe webhook, and the `free` publication endpoints.

**Health**
- `GET /health` - Health check endpoint (also used by the k8s probes and Blackbox)

**Publications**
- `GET /publications/` - Paginated list/search with filters (`search_term`, `region`, `sector`, `cpv_code`, `date_from`, `date_to`, `recommended`, `saved`, `viewed`, `sort_by`, `sort_order`)
- `GET /publications/free/search/` - Public, unauthenticated search (reduced fields)
- `GET /publications/publication/{workspace_id}/` - Publication details
- `GET /publications/free/publication/{workspace_id}/` - Public publication details
- `POST /publications/publication/{workspace_id}/save` | `/unsave` | `/viewed` - Track user interaction
- `GET /publications/publication/{workspace_id}/related` - Comparable awarded contracts, found by searching the award database (see **AI database access** below). `?refresh=true` recomputes.
- `GET /publications/publication/{workspace_id}/document/{filename}` - Download a tender document

**Conversations (AI chat)**
- `GET /conversations/` - List the user's conversations
- `GET /conversations/{conversation_id}` - Conversation with messages
- `POST /conversations/chat` - Ask a question about a publication
- `DELETE /conversations/{conversation_id}` - Delete a conversation
- `GET /publications/{workspace_id}/conversation` - Conversation for a publication

**Contracts (award analytics)**
- `GET /contracts` - Paginated awarded contracts
- `GET /contracts/summary` - Award totals and aggregates
- `GET /contracts/by-sector` | `/by-region` | `/by-winner` | `/by-supplier` | `/by-buyer` - Grouped counts and values
- `GET /contracts/timeseries?granularity=month|quarter|year` - Awards over time

  All of these share one filter set: `search`, `year`, `quarter`, `month`, `sector_code`, `cpv_code`, `region`, `winner`, `supplier`, `buyer`, `min_value`, `max_value`.
- `GET /email/contract/{contract_id}` - Winner-email tracking records

**Kanban**
- `GET /kanban/board` - Full board for the user's company
- `GET|POST|PUT|DELETE /kanban/statuses[/{status_id}]` - Manage columns
- `POST|GET|PUT|DELETE /kanban/publications[/{workspace_id}]` - Manage cards
- `POST /kanban/move` - Move a publication between statuses
- `POST /kanban/initialize` - Seed the default statuses

**Notifications**
- `GET /notifications/` | `/combined` | `/counts` | `/unread` | `/by-type/{type}` - Read notifications
- `POST /notifications/` | `/{id}/read` | `/mark-read` | `/delete` - Create and manage

**Company & Users**
- `GET|POST|PATCH /company/` , `GET /company/{vat_number}` - Company profile
- `POST /company/scrape-website` - Fetch a company site over HTTP and have OpenAI extract name, VAT, sectors and regions (onboarding pre-fill)
- `GET /users/company-users` | `/company-emails`, `POST /users/invite`, `DELETE /users/remove/{email}`

**Billing**
- `POST /stripe/webhook` - Stripe subscription/payment webhook

## AI database access (MCP)

Procy used to be blind to the database. Its prompt carried one publication and
the company profile, there was no tool-calling anywhere in the codebase, and any
question about comparable gunningen, market values or who tends to win was
answered from the model's own memory — which is to say, invented.

`/publications/.../related` had the opposite problem: it was real data, ranked by
a hand-tuned `CASE` sum (same buyer +50, shared keyword +35, CPV +25) that never
compared the *text* of two tenders, and whose point total was rendered to users
as a "% match".

Both are now served by one tool layer.

### The registry

Every tool is defined once in `app/mcp/registry.py` — name, JSON schema, handler
— and three callers dispatch against it, so they cannot drift apart:

| Caller | Path |
|---|---|
| External MCP clients | `app/mcp/server.py`, mounted at `/mcp` (Streamable HTTP) |
| Procy's chat loop | `app/util/conversations_helper.py` |
| The retrieval agent | `app/ai/retrieval_agent.py` |

`MCP_TRANSPORT` selects how internal callers reach a tool. The default,
`inprocess`, dispatches straight to the handler; `http` drives a real MCP client
session against `/mcp`, which is useful for verifying the server but makes the
API issue an authenticated HTTP request to itself once per tool call.

### Tools

**Gunningen** — `search_awards`, `get_award`, `award_market_stats`,
`awards_by_sector`, `awards_by_region`, `awards_by_winner`, `awards_by_supplier`,
`awards_by_buyer`, `awards_timeseries`, `find_similar_awards`

**Tenders** — `search_publications`, `get_publication`,
`find_similar_publications`, `publications_with_upcoming_deadlines`

**Entities** — `search_organisations`, `get_organisation_profile`, `lookup_cpv`,
`lookup_nuts`

**Caller-scoped** — `get_my_company_profile`, `my_publications`

**Escape hatch** — `describe_schema`, `run_sql_readonly`

Every tool that returns a tender or an award includes a `url`, so Procy cites
pages the user can open rather than describing results vaguely.

### How "vergelijkbare gunningen" is produced

`app/ai/retrieval_agent.py`:

1. A deterministic query builds a broad candidate pool (Dutch full-text over the
   award text, plus CPV proximity). Recall only.
2. The model reads that pool and issues **its own** searches against the same
   database, reformulating in Dutch, widening the CPV or dropping the value band
   until it has enough. Capped at `RETRIEVAL_AGENT_MAX_ROUNDS` rounds and
   `RETRIEVAL_AGENT_MAX_CANDIDATES` candidates.
3. It ranks what it found and explains each choice.
4. The response is rebuilt from the database rows.

The model selects and explains; it never supplies data. Any workspace id it
returns that did not come out of a tool result is dropped before assembly, so a
gunning that does not exist cannot reach the frontend. `similarity_score` is now
a real 0–100 relevance rather than an open-ended point total.

Results are cached in Redis per publication for `SIMILAR_AWARDS_CACHE_TTL`
seconds and invalidated with the rest of a publication's cache. On timeout or
model failure the endpoint falls back to the old deterministic scorer, so the
section degrades to its previous behaviour rather than to an empty state.

### Security

`/mcp` is on the public internet and reads a database, so:

- Every request must carry the same Clerk bearer token the REST API requires.
  The verified identity becomes the `ToolContext` that tenant-scoped tools filter
  on — it is never taken from anything the model produced.
- `run_sql_readonly` runs **only** against `POSTGRES_RO_CON_URL`. Grant that role
  `SELECT` on the procurement tables and nothing else; it must have no access to
  `companies`, `conversations`, `messages`, `kanban_*`, `notifications` or
  `company_publication_matches`. **If the URL is unset the tool is not registered
  at all** — it never falls back to the read-write engine.
- The statement parser in `app/mcp/tools/sql.py` (single `SELECT`, no DDL/DML, no
  file functions, forced row cap) is defence in depth, not the boundary. Do not
  weaken the grants on the strength of it.

Creating the read-only role:

```sql
CREATE USER proclogic_ro WITH PASSWORD '...';
GRANT CONNECT ON DATABASE proclogic TO proclogic_ro;
GRANT USAGE ON SCHEMA public TO proclogic_ro;
GRANT SELECT ON publications, contracts, contract_organizations,
    contract_addresses, contract_contact_persons, descriptions, dossiers, lots,
    cpv_codes, organisations, organisation_names, enterprise_categories,
    publication_cpv_additional_codes, publication_lots
    TO proclogic_ro;
```

### Full-text search

Migration `c4d5e6f7a8b9` adds `publications.searchable_content` — dossier and lot
titles and descriptions, organisation names, keywords, AI summaries, and the
winner — with a GIN index on `to_tsvector('dutch', ...)` and a trigram index for
substring fallback. It is written at ingest by `get_or_create_publication`.

It is deliberately not a generated column: Postgres generated columns may only
reference the same row, and this aggregates across `descriptions` and
`organisation_names`.

Rows that predate the migration have a NULL, which is invisible to full-text
search. Backfill once:

```bash
python -m scripts.backfill_searchable_content.backfill_searchable_content
```

Safe to re-run and to interrupt; `--all` rebuilds every row rather than only the
missing ones.

## Project Structure

```
proclogic_api/
├── app/
│   ├── ai/                  # OpenAI clients, recommendations, document AI
│   │   ├── openai.py        # Sync + async client factories (see safeguards above)
│   │   ├── recommend.py
│   │   └── scraper.py
│   ├── config/              # Configuration and connections
│   │   ├── postgres.py      # Engine / session factory
│   │   ├── redis_manager.py # Redis connection management
│   │   └── settings.py      # Pydantic settings
│   ├── crud/                # Database CRUD operations
│   │   ├── company.py
│   │   ├── publication.py
│   │   └── ...
│   ├── models/              # SQLAlchemy database models
│   │   ├── company_models.py
│   │   ├── publication_models.py
│   │   └── ...
│   ├── schemas/             # Pydantic request/response schemas
│   ├── routers/             # API route handlers
│   │   ├── conversations.py
│   │   ├── publications.py
│   │   ├── kanban.py
│   │   ├── stripe.py
│   │   └── ...
│   ├── services/            # Cross-cutting services
│   │   └── contract_email.py
│   ├── util/                # Utility functions
│   │   ├── alembic_runner.py     # Runs migrations at startup
│   │   ├── clerk.py              # Auth helpers + JWKS cache
│   │   ├── pubproc.py            # Procurement integration & scraper loops
│   │   ├── publication_utils/    # CPV/NUTS codes, converters, contracts
│   │   ├── redis_cache.py        # Caching decorator (with size caps)
│   │   ├── web_scraper.py        # Playwright scrape of the procurement portal,
│   │   │                         #   used only by scripts/backfill_contracts
│   │   ├── zip.py                # Disk-bounded archive extraction
│   │   └── email/                # Email templates and service
│   └── main.py              # FastAPI app, lifespan, scraper tasks, error handler
├── alembic/                 # Database migrations
│   ├── versions/            # Migration files
│   └── env.py               # Alembic configuration
├── scripts/                 # Utility scripts (run from a checkout, not the image)
│   └── backfill_contracts/  # Historic award backfill; needs Playwright
├── assets/                  # Logos
├── .env                     # Environment variables (not in git)
├── .env.postgres            # PostgreSQL env vars (not in git)
├── env_example              # Example .env template
├── env_postgres_example     # Example .env.postgres template
├── alembic.ini              # Alembic configuration
├── compose.yml              # Postgres + Redis + pgAdmin for local dev
├── Dockerfile               # Multi-stage production image
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Database Migrations

Migrations are applied automatically when the app starts; a failure is logged and startup continues. The commands below are for authoring and manual control.

### How migrations run at startup

`run_migration()` (`app/util/alembic_runner.py`) holds a Postgres advisory lock
for the duration, so only one replica migrates at a time. The API runs 3–7 pods
and every one of them calls it on start; without the lock they race, and the
indexes below are built with `CREATE INDEX CONCURRENTLY`, where losing that race
can leave an index marked **invalid** and permanently unused. A pod that cannot
get the lock within `MIGRATION_LOCK_TIMEOUT` logs and skips — whoever holds it
is the one that will finish. The lock is session-scoped, so a crashed pod
releases it automatically and cannot wedge a rollout.

Index builds are concurrent: a plain `CREATE INDEX` on `publications` holds a
lock that blocks writes for the whole build, which would stall the scraper. The
`ALTER TABLE` statements run under `SET LOCAL lock_timeout` so they cannot queue
for an exclusive lock while every later query queues behind them. Both index
migrations first drop any same-named index left **invalid** by an interrupted
build — `CREATE INDEX CONCURRENTLY IF NOT EXISTS` sees the name, skips, and the
index would otherwise stay dead forever.

### Provisioning a new environment

`run_migration()` takes one of two paths:

- **Existing database** — the normal `alembic upgrade head`.
- **Empty database** — the schema is created from the models and stamped at head.

The second path exists because the initial revision `8a03694dc199` is an empty
`pass` and nothing else ever created the tables, so `alembic upgrade head`
against a fresh database ran every later revision against tables that did not
exist and failed on the first `ALTER TABLE`. Provisioning a new environment was
impossible; the schema had only ever been created out of band. Production is not
empty, so it is unaffected and takes the upgrade path exactly as before.

### Backfills

Two one-off scripts, both safe to re-run:

```bash
# Fill publications.searchable_content for rows predating migration c4d5e6f7a8b9.
# Without this, historical tenders are invisible to full-text search.
python -m scripts.backfill_searchable_content.backfill_searchable_content

# Classify legacy `descriptions` rows as titles or descriptions (migration
# d5e6f7a8b9c0). Dry-run by default -- read the sample before committing.
python -m scripts.backfill_description_kind.backfill_description_kind
python -m scripts.backfill_description_kind.backfill_description_kind --commit
```

### Titles vs. descriptions

`Dossier.titles`/`Dossier.descriptions` (and the same pair on `Lot`) used to be
two relationships over one foreign key with no discriminator, so both returned
*every* row for the parent and `get_publication_title` returned whichever came
last — often the description. Migration `d5e6f7a8b9c0` adds `descriptions.kind`.

Rows created before it carry `kind='unknown'` and belong to both collections,
which reproduces the old behaviour exactly, so applying the migration changes
nothing for existing data. Newly ingested rows are precise; run the backfill
above to classify the historical ones.

Related: `create_descriptions` no longer reuses an existing row with matching
text. It used to, and because a description row carries a single
`dossier_reference_number` and `lot_id`, "reusing" one actually *moved* it —
silently stripping the text from whichever parent had it before. Since
`update_publication` rebuilds a publication's lots on every notice update, and
phrases like "Onderhoud groenzones" repeat across tenders, republished notices
quietly emptied each other's lots.

### Create a new migration

```bash
alembic revision --autogenerate -m "Description of changes"
```

### Apply migrations

```bash
alembic upgrade head
```

### Rollback migration

```bash
alembic downgrade -1
```

### View migration history

```bash
alembic history
```

## Running the Scraper Worker

With `SCRAPER_MODE=true` the same image starts three background loops instead of serving traffic only:

- `fetch_pubproc_data()` — pulls new publications, hourly
- `update_pubproc_data()` — refreshes existing publications, hourly
- `gather_notifications()` — builds user notifications, every 6 hours

```bash
SCRAPER_MODE=true fastapi run app/main.py
```

Or via environment variable in `.env`:
```
SCRAPER_MODE=true
```

Run a single scraper replica — the loops are not coordinated across pods.

## Building for Production

### Build Docker image

```bash
docker build -t proclogic-api .
```

The image is a two-stage build: `build-essential` and pip live in a throwaway
builder stage that produces `/opt/venv`, and the runtime stage copies only that
venv onto `python:slim`, so no compiler or build toolchain ships in the final
image. It serves with `uvicorn app.main:proclogic` on port 80.

The image ships no browser: nothing the API or the scraper worker serves uses
Playwright. `app/util/web_scraper.py` is imported only by
`scripts/backfill_contracts`, which runs from a checkout with its own venv, so
install the Chromium binary there rather than in the image (it costs ~1.4 GB).

### Run production container

```bash
docker run -p 8000:80 \
  --env-file .env \
  proclogic-api
```

### Kubernetes Deployment

Example Kubernetes deployment configuration:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: proclogic-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: proclogic-api
  template:
    metadata:
      labels:
        app: proclogic-api
    spec:
      containers:
      - name: proclogic-api
        image: your-registry/proclogic-api:latest
        ports:
        - containerPort: 80
        env:
        - name: DEBUG_MODE
          value: "false"
        - name: REDIS_HOST
          value: "redis-service"
        envFrom:
        - secretRef:
            name: proclogic-secrets
        livenessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 60
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 80
          initialDelaySeconds: 30
          periodSeconds: 5
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: proclogic-api
spec:
  selector:
    app: proclogic-api
  ports:
  - port: 80
    targetPort: 80
  type: ClusterIP
```

For the scraper worker, deploy separately:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: proclogic-scraper
spec:
  replicas: 1  # Single scraper instance
  selector:
    matchLabels:
      app: proclogic-scraper
  template:
    metadata:
      labels:
        app: proclogic-scraper
    spec:
      containers:
      - name: proclogic-scraper
        image: your-registry/proclogic-api:latest  # Same image
        env:
        - name: SCRAPER_MODE
          value: "true"
        - name: REDIS_HOST
          value: "redis-service"
        envFrom:
        - secretRef:
            name: proclogic-secrets
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 1000m
            memory: 4Gi
```

The scraper needs enough ephemeral storage for archive extraction — `app/util/zip.py`
refuses archives that would not fit in the free disk budget, so a small
`emptyDir`/node disk shows up as skipped documents rather than a crash.

## Development

### Code Quality

The project follows FastAPI best practices:
- Type hints for all function parameters
- Pydantic models for request/response validation
- Async/await for I/O operations
- Dependency injection for auth and database sessions

### Testing & Linting

There is no automated test suite or linter configuration in the repository yet —
contributions that add one are very welcome. If you want to lint locally:

```bash
pip install ruff black
ruff check .
black .
```

## CPV Code Reference

The Common Procurement Vocabulary (CPV) is used to classify tender categories:

- **Explorer**: https://europadecentraal.nl/cpv-code-zoekmachine/#cpv-explorer-form
- Used for publication categorization and search filtering

## Contributing

We welcome contributions! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure code passes linting
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## Security

### Reporting Vulnerabilities

Please report security vulnerabilities to security@proclogic.be

### Best Practices

- Never commit `.env` files
- Rotate API keys regularly
- Use environment variables for all secrets
- Enable HTTPS in production
- Keep dependencies updated

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Related Projects

- [proclogic_app](https://github.com/eludum/proclogic_app) - Frontend application

## Support

- Issues: [GitHub Issues](https://github.com/eludum/proclogic_api/issues)
- Email: info@proclogic.be

---

<div align="center">

<a href="https://koselogic.be" target="_blank">
  <img src="https://raw.githubusercontent.com/eludum/proclogic_api/main/assets/koselogic.svg" alt="KoseLogic" width="200">
</a>




**[koselogic.be](https://koselogic.be)**

ProcLogic is developed by KoseLogic

</div>
