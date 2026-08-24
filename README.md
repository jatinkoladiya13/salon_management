# Salon Management Platform

A multi-tenant salon management backend built with Django and Django REST Framework. Each salon runs in its own PostgreSQL schema, with role-based access, appointment scheduling, inventory, payments, subscriptions, notifications, and search.

## Highlights

- Multi-tenant architecture with schema isolation
- JWT authentication bound to the tenant workspace
- Role-based access for platform admins, salon admins, staff, and customers
- Salon details, services, staff assignments, appointments, and time slots
- Product catalog, inventory receiving, stock adjustments, cart, and invoices
- Stripe subscriptions, checkout, payment webhooks, and subscription lifecycle handling
- Optional Razorpay payment support
- Celery workers and scheduled tasks for reminders and recurring time slots
- Redis-backed task queue and WebSocket channel layer
- Elasticsearch-powered user and product search
- Password reset and two-factor authentication support
- Paginated, filterable, and searchable REST API responses

## Technology

| Area | Technology |
| --- | --- |
| Framework | Django 5.2, Django REST Framework |
| Database | PostgreSQL with `django-tenants` |
| Authentication | JWT with Simple JWT |
| Async processing | Celery, Redis, Celery Beat |
| Real-time updates | Django Channels, Daphne, Redis |
| Payments | Stripe, dj-stripe, Razorpay |
| Search | Elasticsearch 8 |
| Image handling | Pillow |
| Python | Python 3.14 recommended for the current environment |

## Architecture

The platform uses a shared public schema for platform-wide records such as subscription plans and tenant metadata. Every salon has a separate tenant schema containing its operational data.

```text
Client
  |
  v
Django REST API ---- PostgreSQL public schema
  |                  |
  |                  +-- Tenant registry and subscription plans
  |
  +---------------- PostgreSQL tenant schemas
  |                  +-- Users and roles
  |                  +-- Salon data
  |                  +-- Appointments
  |                  +-- Products and stock
  |
  +-- Redis -------- Celery workers and WebSocket channel layer
  +-- Stripe/Razorpay payment providers
  +-- Elasticsearch search index
```

## Roles

| Role | Scope | Responsibility |
| --- | --- | --- |
| `SuperAdmin` | Platform | Manages platform-level operations in the public schema |
| `TenantAdmin` | One salon | Manages the salon workspace, staff, settings, and permissions |
| `Staff` | One salon | Performs the operational work granted by the tenant admin |
| `User` | One salon | Books appointments and accesses customer features |

JWTs include the tenant schema and are checked against the request host. Tenant-admin actions operate only inside the tenant selected by the request host.

## Project Structure

```text
salon_management/
├── account/             Authentication, users, roles, password reset, 2FA
├── appointment/         Services, appointments, time slots, notifications
├── checkout/            Stripe checkout and credit purchase flows
├── company_logo/        Company logo support
├── core/                Shared permissions, constants, and administration
├── payments/            Payment configuration and provider services
├── product_sales/      Products, carts, invoices, and sales
├── salonDetails/       Salon workspace details
├── stock_management/   Stock purchases and inventory changes
├── subscription/       Plans, subscriptions, invoices, and Stripe helpers
├── tenant/             Tenant and domain models
├── utils/               Authentication, permissions, pagination, and helpers
├── webhook_handler/    Stripe and Razorpay webhook processing
├── salon_management/   Django settings, ASGI, WSGI, and Celery configuration
├── manage.py
└── requirements.txt
```

## Local Requirements

- Python 3.12+
- PostgreSQL
- Redis
- Elasticsearch 8.x for search features
- Stripe account for payment and subscription flows
- Node.js is not required because this repository is a backend API

## Installation

### Windows PowerShell

```powershell
git clone <your-repository-url>
cd salon_management

py -3.14 -m venv env
.\env\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Environment Variables

Create a local `.env` file in the project root. Never commit it.

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1,test.localhost
CSRF_TRUSTED_ORIGINS=http://localhost:8000
CORS_ALLOWED_ORIGINS=http://localhost:3000

DEFAULT_DB_NAME=salon_management
DEFAULT_DB_USER=postgres
DEFAULT_DB_PASSWORD=replace-me
DEFAULT_DB_HOST=127.0.0.1
DEFAULT_DB_PORT=5432

ACCESS_TOKEN_EXPIRE_TIME_IN_MIN=60
REFRESH_TOKEN_EXPIRE_TIME_IN_MIN=1440

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_CHANNEL=1

ELASTICSEARCH_HOST=http://127.0.0.1:9200

STRIPE_LIVE_MODE=False
STRIPE_PUBLIC_KEY=pk_test_replace-me
STRIPE_SECRET_KEY=sk_test_replace-me
DJSTRIPE_WEBHOOK_SECRET=whsec_replace-me

EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
EMAIL_PORT=587
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=no-reply@example.com
```

The settings module requires database, Redis, and JWT expiry values. Configure real credentials for any service used by the environment.

## Database Setup

Run Django migrations for the shared schema and tenant schemas:

```powershell
python manage.py migrate_schemas --shared
python manage.py migrate_schemas --tenant
```

The project includes management commands for creating the public tenant, template schema, tenant roles, and permissions. Review the commands in `core/management/commands/` before running them in a shared environment.

A typical development sequence is:

```powershell
python manage.py create_public_tenant
python manage.py create_template_schema
python manage.py setup_project
```

Create a superuser when required by the deployment:

```powershell
python manage.py create_superuser
```

## Docker deployment

The Compose file supports both local development and EC2 deployment. Local PostgreSQL and Redis are enabled with the `local` profile:

```powershell
docker compose --profile local up --build -d
docker compose --profile local --profile setup run --rm setup
```

For EC2, create `.env` from values stored in AWS Systems Manager Parameter Store or Secrets Manager. Do not copy production secrets into the repository or image. The file must contain the settings required by `salon_management/settings.py`, including `SECRET_KEY`, database credentials, `REDIS_PASSWORD`, JWT expiry values, payment credentials, and email settings. Set `DEBUG=False`, an explicit `ALLOWED_HOSTS`, and production `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`. Set `DEFAULT_DB_HOST` to the RDS endpoint and `REDIS_HOST` to the ElastiCache endpoint; set `REDIS_USE_TLS=True` when ElastiCache in-transit encryption is enabled.

Deploy the AWS stack with the same Compose file. Do not enable the `local` profile; the application will connect to the managed AWS services from `.env`:

```bash
docker compose build
docker compose --profile setup run --rm setup
docker compose up -d
```

Nginx runs on port 80 and proxies API and WebSocket traffic to Daphne. Configure an HTTPS Application Load Balancer with an ACM certificate in front of this port, restrict the EC2 security group to the ALB security group, and forward the ALB health check to `/health/`. Nginx serves the static and media volumes populated by the setup command.

## Running the Services

### Docker Compose

After creating `.env` and configuring its database, JWT, Redis, and service
credentials, start the local API, PostgreSQL, Redis, Celery worker, and scheduler:

```powershell
docker compose --profile local up --build -d
```

The API is available on host port `8001`. If that port is already in use,
choose another host port without changing the container:

```powershell
$env:WEB_PORT = "8001"
docker compose up --build -d
```

Run the one-time project initializer after the application image is built:

```powershell
docker compose --profile local --profile setup run --rm setup
```

This creates the public tenant, platform superuser, template schema, and
default tenant roles and permissions. It is intentionally a one-shot command
and is not part of the normal web restart cycle.

Apply migrations from the web container before first use:

```powershell
docker compose exec web python manage.py migrate_schemas --shared
docker compose exec web python manage.py migrate_schemas --tenant
```

View service logs or stop the stack:

```powershell
docker compose logs -f web
docker compose down
```

The Compose stack does not include Elasticsearch because the current client is
configured for Elastic Cloud. Set `ELASTIC_CLOUD_ID` and `ELASTIC_API_KEY` in
`.env` when search features are enabled.

### Django development server

```powershell
python manage.py runserver
```

### ASGI server

Daphne serves both HTTP and WebSocket traffic:

```powershell
daphne -b 0.0.0.0 -p 8000 salon_management.asgi:application
```

### Celery worker

```powershell
celery -A salon_management worker -l info --pool=solo
```

### Celery Beat

Run the scheduler in a separate process:

```powershell
celery -A salon_management beat -l info
```

Scheduled tasks include recurring time-slot creation and appointment reminders.

## API Documentation

All API responses use a common envelope with `error`, `data`, and `message` fields.

- [Account API](account/API.md)
- [Appointment API](appointment/API.md)
- [Checkout API](checkout/API.md)
- [Core API](core/API.md)
- [Payments API](payments/API.md)
- [Product Sales API](product_sales/API.md)
- [Salon Details API](salonDetails/API.md)
- [Stock Management API](stock_management/API.md)
- [Subscription API](subscription/API.md)
- [Tenant API](tenant/API.md)
- [Webhook API](webhook_handler/API.md)

Base routes are grouped under `/api/`:

```text
/api/account/
/api/appointment/
/api/checkout/
/api/core/
/api/payments/
/api/product-sales/
/api/salon/
/api/stock-management/
/api/subscription/
/api/tenant/
/api/webhook-handler/
```

## Authentication

Protected HTTP endpoints use a bearer access token:

```http
Authorization: Bearer <access_token>
```

Login is tenant-aware. The request host identifies the workspace, and the issued token is bound to that workspace. Anonymous endpoints are limited to login, registration, token refresh, password reset, and signed payment webhooks.

## WebSocket Notifications

Authenticated clients can connect to:

```text
ws://<tenant-domain>/ws/notifications/?token=<access_token>
```

The connection validates the JWT, resolves the registered tenant domain, checks the tenant subscription, and loads an active user from that tenant schema. Appointment reminders are delivered through the notification group for that user.

For production, serve this endpoint over `wss://` and ensure proxy and WebSocket timeout settings are configured correctly.

## Payments and Webhooks

Stripe configuration is required for checkout and subscription workflows. Configure webhook endpoints in the Stripe dashboard and set `DJSTRIPE_WEBHOOK_SECRET` to the signing secret.

Local Stripe webhook forwarding can be performed with the Stripe CLI:

```powershell
stripe listen --forward-to localhost:8000/api/webhook-handler/stripe/
```

See [stripe.md](stripe.md) for the integration notes and [elasticsearch.md](elasticsearch.md) for search setup.

## Search Setup

Start Elasticsearch locally with Docker:

```powershell
docker run -d --name elasticsearch -p 9200:9200 `
  -e "discovery.type=single-node" `
  -e "xpack.security.enabled=false" `
  docker.elastic.co/elasticsearch/elasticsearch:8.12.0
```

Production Elasticsearch must use authentication, TLS, restricted network access, and an appropriate index lifecycle policy.

## Testing

Run the full test suite with the project virtual environment:

```powershell
.\env\Scripts\Activate.ps1
python manage.py test --keepdb
```

Run an individual application suite:

```powershell
python manage.py test account
python manage.py test appointment
python manage.py test stock_management
python manage.py test subscription
```

Useful checks before opening a pull request:

```powershell
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
```

## Production Checklist

Before deployment:

- Set `DEBUG=False`.
- Set an explicit `ALLOWED_HOSTS` list.
- Use a long, randomly generated `SECRET_KEY` and rotate any exposed credentials.
- Enforce HTTPS and configure secure session and CSRF cookies.
- Configure trusted CSRF and CORS origins explicitly.
- Use authenticated Redis connections and private network access.
- Configure PostgreSQL backups, restore testing, connection limits, and monitoring.
- Run migrations for shared and tenant schemas through the deployment process.
- Run Celery worker and Beat as supervised services.
- Configure an ASGI-capable reverse proxy for HTTP and WebSocket traffic.
- Require valid Stripe and Razorpay webhook signatures.
- Protect `/admin/` and operational endpoints with network and account controls.
- Store payment credentials in a secrets manager where possible.
- Configure centralized logs, error monitoring, health checks, and alerts.
- Complete the full test suite against a clean test database.

Run the deployment check and resolve every warning before release:

```powershell
python manage.py check --deploy
```

## License

No license has been declared yet. Add a license before publishing this repository for external reuse.
