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
- **Company Profiles**: Company/VAT records, team invites, and Playwright-based website scraping used to build recommendations
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
playwright install chromium  # Browser binary for company website scraping
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
- `GET /publications/publication/{workspace_id}/related` - Related publications and content
- `GET /publications/publication/{workspace_id}/document/{filename}` - Download a tender document

**Conversations (AI chat)**
- `GET /conversations/` - List the user's conversations
- `GET /conversations/{conversation_id}` - Conversation with messages
- `POST /conversations/chat` - Ask a question about a publication
- `DELETE /conversations/{conversation_id}` - Delete a conversation
- `GET /publications/{workspace_id}/conversation` - Conversation for a publication

**Contracts**
- `GET /contracts` - Paginated awarded contracts
- `GET /contracts/summary` - Award totals and aggregates
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
- `POST /company/scrape-website` - Playwright scrape used to enrich recommendations
- `GET /users/company-users` | `/company-emails`, `POST /users/invite`, `DELETE /users/remove/{email}`

**Billing**
- `POST /stripe/webhook` - Stripe subscription/payment webhook

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
│   │   ├── web_scraper.py        # Playwright website scraping
│   │   ├── zip.py                # Disk-bounded archive extraction
│   │   └── email/                # Email templates and service
│   └── main.py              # FastAPI app, lifespan, scraper tasks, error handler
├── alembic/                 # Database migrations
│   ├── versions/            # Migration files
│   └── env.py               # Alembic configuration
├── scripts/                 # Utility scripts
│   └── backfill_contracts/  # Historic award backfill
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

The runtime stage also installs Chromium plus its shared libraries
(`playwright install --with-deps chromium`) into `/opt/playwright`, which is
what `POST /company/scrape-website` launches. That layer costs ~1.4 GB — by far
the largest part of the image — so drop the `RUN playwright install` line if you
do not need that endpoint.

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
