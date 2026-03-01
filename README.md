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

- **Publication Management**: Fetch, search, and manage public tender publications
- **AI-Powered Chat**: Interactive assistant using OpenAI for tender insights
- **Smart Scraping**: Automated background workers for data collection
- **User Authentication**: Secure JWT-based auth via Clerk
- **Subscription Management**: Stripe integration for payment processing
- **Document Handling**: Download and serve tender documents
- **Notifications**: Email notifications via Mailtrap/SMTP
- **Caching**: Redis-based caching for performance
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Error Tracking**: Sentry integration for monitoring

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
playwright install  # Install browser binaries for web scraping
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

# PubProc Integration (Belgian public procurement system)
# ⚠️ Obtain these credentials from BOSA (see step 4 above)
PUBPROC_SERVER=https://enot.publicprocurement.be
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
SENTRY_DSN=https://...  # For error tracking
DEBUG_MODE=true  # Enable debug mode for development
```

**Important**: Never commit `.env` to version control. It's already in `.gitignore`.

### 6. Set up PostgreSQL database

#### Option A: Using Docker Compose (recommended)

Create `.env.postgres` file (see `env_postgres_example`):

```bash
POSTGRES_USER=proclogic
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=proclogic
PGADMIN_DEFAULT_EMAIL=admin@yourdomain.com
PGADMIN_DEFAULT_PASSWORD=your-admin-password
```

Start PostgreSQL and pgAdmin:

```bash
docker compose up -d
```

Access pgAdmin at http://localhost:5050

To get the PostgreSQL container IP for pgAdmin:
```bash
docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' proclogic_api-postgres-1
```

#### Option B: Local PostgreSQL installation

```bash
# Install PostgreSQL (platform-specific)
# Then create database and user:
createdb proclogic
psql -c "CREATE USER proclogic WITH PASSWORD 'your-password';"
psql -c "GRANT ALL PRIVILEGES ON DATABASE proclogic TO proclogic;"
```

### 7. Run database migrations

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

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `POSTGRES_CON_URL` | PostgreSQL connection string | Yes | - |
| `CLERK_SECRET_KEY` | Clerk authentication secret | Yes | - |
| `CLERK_JWKS_URL` | Clerk JWKS endpoint for JWT validation | No | Auto-generated |
| `OPENAI_API_KEY` | OpenAI API key for AI features | Yes | - |
| `PUBPROC_SERVER` | Public procurement API server | No | Belgian endpoint |
| `PUBPROC_CLIENT_ID` | OAuth client ID for procurement system (obtain from BOSA) | Yes | - |
| `PUBPROC_CLIENT_SECRET` | OAuth client secret (obtain from BOSA) | Yes | - |
| `STRIPE_SECRET_KEY` | Stripe secret key for payments | Yes | - |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature secret | Yes | - |
| `REDIS_HOST` | Redis server hostname | No | `localhost` |
| `REDIS_PORT` | Redis server port | No | `6379` |
| `MAILTRAP_TOKEN` | Email service API token | No | - |
| `MAIL_FROM` | Sender email address | No | `info@proclogic.be` |
| `SENTRY_DSN` | Sentry error tracking DSN | No | - |
| `DEBUG_MODE` | Enable debug logging | No | `false` |
| `SCRAPER_MODE` | Run as background scraper worker | No | `false` |

## API Documentation

Once the server is running, visit:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

### Main API Endpoints

- `GET /health` - Health check endpoint
- `GET /publications` - List all publications
- `POST /publications/search` - Search publications with filters
- `GET /publications/{id}` - Get publication details
- `GET /publications/publication/{workspace_id}/document/{filename}` - Download documents
- `POST /chat` - AI-powered chat about publications
- `GET /user/saved-publications` - Get user's saved publications
- `POST /stripe/*` - Payment and subscription endpoints
- `GET /company/*` - Company management endpoints

## Project Structure

```
proclogic_api/
├── app/
│   ├── config/              # Configuration and settings
│   │   ├── redis_manager.py # Redis connection management
│   │   └── settings.py      # Pydantic settings
│   ├── crud/                # Database CRUD operations
│   │   ├── crud_company.py
│   │   ├── crud_publication.py
│   │   └── ...
│   ├── models/              # SQLAlchemy database models
│   │   ├── company.py
│   │   ├── publication.py
│   │   └── ...
│   ├── routers/             # API route handlers
│   │   ├── chat.py
│   │   ├── publications.py
│   │   ├── stripe.py
│   │   └── ...
│   ├── util/                # Utility functions
│   │   ├── auth.py          # Authentication helpers
│   │   ├── pubproc.py       # Public procurement integration
│   │   ├── redis_cache.py   # Caching decorator
│   │   ├── zip.py           # File handling
│   │   └── email/           # Email templates and service
│   ├── main.py              # FastAPI application entry point
│   └── scraper.py           # Background scraper worker
├── alembic/                 # Database migrations
│   ├── versions/            # Migration files
│   └── env.py               # Alembic configuration
├── scripts/                 # Utility scripts
│   └── backfill_contracts/  # Data backfill scripts
├── .env                     # Environment variables (not in git)
├── .env.postgres            # PostgreSQL env vars (not in git)
├── env_example              # Example .env template
├── env_postgres_example     # Example .env.postgres template
├── alembic.ini              # Alembic configuration
├── compose.yml              # Docker Compose for local dev
├── Dockerfile               # Production Docker image
├── requirements.txt         # Python dependencies
└── README.md                # This file
```

## Database Migrations

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

The scraper mode runs background tasks for data collection:

```bash
SCRAPER_MODE=true fastapi run app/main.py
```

Or via environment variable in `.env`:
```
SCRAPER_MODE=true
```

## Building for Production

### Build Docker image

```bash
docker build -t proclogic-api .
```

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


## Development

### Code Quality

The project follows FastAPI best practices:
- Type hints for all function parameters
- Pydantic models for request/response validation
- Async/await for I/O operations
- Dependency injection for auth and database sessions

### Testing

```bash
pytest
```

### Linting

```bash
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

<div align="center">

## Part of KoseLogic

<a href="https://koselogic.be" target="_blank">
  <img src="https://raw.githubusercontent.com/eludum/proclogic_api/main/assets/koselogic.svg" alt="KoseLogic" width="200">
</a>

<br>

**[koselogic.be](https://koselogic.be)**

ProcLogic is developed by KoseLogic

</div>
