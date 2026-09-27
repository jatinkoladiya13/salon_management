# Salon Management — AWS Production Deployment Guide

Everything needed to take this Django project from an empty AWS account to a running
production deployment with automatic deploys from GitHub.

**Contents**

1. [Architecture](#1-architecture)
2. [AWS infrastructure setup](#2-aws-infrastructure-setup)
3. [The `.env` file](#3-the-env-file)
4. [Docker — every service explained](#4-docker--every-service-explained)
5. [WebSockets — the full path](#5-websockets--the-full-path)
6. [GitHub Actions self-hosted runner](#6-github-actions-self-hosted-runner)
7. [`deploy.yml` walkthrough](#7-deployyml-walkthrough)
8. [Day-2 operations](#8-day-2-operations)
9. [Scaling for live traffic — and why a load balancer](#9-scaling-for-live-traffic--and-why-a-load-balancer)
10. [Troubleshooting](#10-troubleshooting)
11. [Known gaps before going live](#11-known-gaps-before-going-live)

---

## 1. Architecture

### What actually runs today

```
                          Internet
                             │
                    HTTP :80  /  WS
                             │
                             ▼
┌────────────────────────── EC2 ──────────────────────────┐
│                                                          │
│   nginx container  :80 ──────┐                           │
│      ├── /static/  → static_data volume                  │
│      ├── /media/   → media_data volume                   │
│      └── /         → proxy_pass http://web:8000          │
│                              │                           │
│   web container (Daphne, ASGI)                           │
│      ├── HTTP  → Django / DRF                            │
│      └── WS    → Django Channels                         │
│                                                          │
│   worker container   → Celery worker (runs the tasks)    │
│   beat container     → Celery beat (schedules the tasks) │
│   setup container    → migrations only, on demand        │
│                                                          │
└───────┬──────────────────────┬───────────────────┬───────┘
        │                      │                   │
        ▼                      ▼                   ▼
  RDS PostgreSQL        ElastiCache Redis      S3 (optional)
  (tenant schemas)      db 0  = Celery broker  media files
                        db N  = channel layer
```

### Deploy flow

```
git push origin main
        │
        ▼
GitHub Actions workflow  (.github/workflows/deploy.yml)
        │
        ▼
self-hosted runner  — runs ON the EC2 box itself
        │
        ├── writes .env from GitHub Secrets
        ├── docker compose up -d --build   (image built locally on EC2)
        └── health check + logs
```

> **Note on the architecture diagram with ECR in it:** that diagram shows a registry-based
> flow (build image in CI → push to ECR → pull on EC2). This project does **not** use ECR
> today. The self-hosted runner lives on the EC2 instance and builds the image in place, so
> there is no registry hop. That is simpler and cheaper for one box. Moving to ECR only
> becomes worth it when you run more than one EC2 instance, or want the build to happen off
> the production machine. See [§9](#9-scaling-for-live-traffic--and-why-a-load-balancer).

### The process model, in one line each

| Process | What it is | Why it exists |
|---|---|---|
| **Daphne** | ASGI server | Serves HTTP **and** WebSocket in one process. Replaces Gunicorn here. |
| **Celery worker** | Task executor | Actually runs background jobs. Without it, queued tasks just sit in Redis forever. |
| **Celery beat** | Scheduler | Fires jobs on a clock (cron-like). Queues them; never runs them itself. |
| **nginx** | Reverse proxy | TLS, static/media, upload limits, and one public port in front of everything. |
| **Redis** | Broker + channel layer | Task queue for Celery, and the pub/sub bus for Channels. |
| **PostgreSQL** | Database | Multi-tenant (`django_tenants`), one schema per tenant. |

---

## 2. AWS infrastructure setup

Region used in this guide: **ap-south-1 (Mumbai)**. Keep every resource in the same region
and the same VPC — cross-region traffic costs money and adds latency.

### 2.1 Security groups — create these first

Security groups are the firewall. Make three, and have them reference each other rather
than raw IPs. That way the database is reachable *only* from the app server, whatever its
IP happens to be.

| Group | Inbound rule | Source | Purpose |
|---|---|---|---|
| `salon-ec2-sg` | 22 (SSH) | **your office/home IP /32** | admin access — never `0.0.0.0/0` |
| | 80 (HTTP) | `0.0.0.0/0` | public web |
| | 443 (HTTPS) | `0.0.0.0/0` | public web (after TLS) |
| `salon-rds-sg` | 5432 | **`salon-ec2-sg`** | Postgres, app server only |
| `salon-redis-sg` | 6379 | **`salon-ec2-sg`** | Redis, app server only |

Outbound: leave the default "all traffic allowed" on all three.

> Port `8001` (the `web` container's published port) is deliberately **not** open. Traffic
> must arrive through nginx. See [§4.7](#47-the-8001-port-publish).

### 2.2 EC2 instance

* **AMI:** Ubuntu Server 22.04 LTS or 24.04 LTS (x86_64)
* **Type:** `t3.medium` minimum. `t3.small` (2 GB) will OOM — you are running Daphne +
  worker + beat + nginx + a Docker *build* on the same box.
* **Storage:** 30 GB gp3. Docker images, build layers, and logs fill a 8 GB root disk fast.
* **Key pair:** create and download `salon-management-key.pem`. There is no second chance
  to download it.
* **Security group:** `salon-ec2-sg`
* **Elastic IP:** allocate one and associate it. Without it the public IP changes on every
  stop/start, breaking `ALLOWED_HOSTS`, DNS, and your SSH habits.
* **IAM instance profile:** attach `salon-ec2-role` (see [§2.5](#25-s3-bucket--iam-role)).

Connect (Windows PowerShell, from the folder holding the `.pem`):

```powershell
icacls ".\salon-management-key.pem" /inheritance:r /grant:r "$($env:USERNAME):R"
ssh -i ".\salon-management-key.pem" ubuntu@3.108.219.102
```

`icacls` is required once — OpenSSH on Windows refuses a key file that other users can read.

### 2.3 Install Docker on EC2

Do **not** install Python, Django, Postgres, or Redis on the host. Everything the app needs
lives in the image. The host only needs Docker and the GitHub runner.

```bash
sudo apt-get update && sudo apt-get upgrade -y

# Docker's official repo (Ubuntu's own docker.io package is usually too old for compose v2)
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker ubuntu     # log out and back in for this to take effect
docker compose version             # must print v2.x
```

Cap the log files, or JSON logs will eat the disk over a few months:

```bash
sudo tee /etc/docker/daemon.json > /dev/null << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
sudo systemctl restart docker
```

### 2.4 RDS PostgreSQL

**Amazon RDS** is managed PostgreSQL — AWS handles backups, patching, failover and disk
growth. You get a hostname and a password; you never touch the server.

Create with:

* Engine **PostgreSQL 15** or 16
* Template **Production** (or Dev/Test to save money while building)
* Instance `db.t3.micro` to start, `db.t3.small` once real tenants are on it
* Storage 20 GB gp3, **storage autoscaling on**
* **Public access: No** — it must only be reachable from inside the VPC
* Security group `salon-rds-sg`
* Automated backups: 7 days, deletion protection **on**

This project uses `django_tenants`, so the app creates and migrates **one Postgres schema
per tenant** inside a single database. You only ever create the one database by hand; the
app does the rest via `migrate_schemas`.

Verify connectivity from EC2 before deploying anything:

```bash
docker run --rm postgres:16-alpine \
  psql "postgresql://USER:PASSWORD@salon-db.xxxx.ap-south-1.rds.amazonaws.com:5432/salondb" -c "select version();"
```

If that hangs, it is the security group, not Django, 95% of the time.

### 2.5 ElastiCache Redis

Redis does **two separate jobs** here, and the code keeps them on different databases:

| Use | Setting | Redis DB |
|---|---|---|
| Celery broker (task queue) | `CELERY_BROKER_URL` | `0` — hardcoded in settings |
| Channels layer (WebSocket fan-out) | `CHANNEL_LAYERS` | `REDIS_CHANNEL` from `.env` |

So `REDIS_CHANNEL` must be a **database number** (e.g. `1`), not a channel name. Setting
it to `0` would make Celery messages and WebSocket messages share one keyspace — it mostly
works, but it makes `FLUSHDB` during debugging destructive in surprising ways. Use `1`.

Create the cluster:

* ElastiCache → Redis OSS → **Cluster mode disabled**
* Node `cache.t4g.micro`, 1 replica if you want failover
* Security group `salon-redis-sg`, same VPC/subnets as EC2
* Encryption in transit → if you enable it, you must also set `REDIS_USE_TLS=True`, which
  flips the URL scheme to `rediss://` ([settings.py:337](salon_management/settings.py#L337))
* Note the **primary endpoint** → that is `REDIS_HOST`

#### "What if I don't use ElastiCache?"

Three options, in order of preference:

**A. ElastiCache (recommended for production).** Managed, backed up, survives an EC2
rebuild. `REDIS_HOST=my-cache.xxxx.cache.amazonaws.com`.

**B. Redis as a container on the same EC2 box.** Cheapest. Add to `docker-compose.yml`:

```yaml
  redis:
    image: redis:7-alpine
    command: ["redis-server", "--appendonly", "yes", "--requirepass", "${REDIS_PASSWORD}"]
    volumes:
      - redis_data:/data
    restart: unless-stopped
```

…add `redis_data:` under `volumes:`, and set `REDIS_HOST=redis` (the service name — Docker's
internal DNS resolves it). Trade-off: if the instance dies, queued tasks die with it, and
Redis competes with Django for the same RAM.

**C. Redis installed on the host (local dev habit).** Set `REDIS_HOST=host.docker.internal`
— the compose file already maps that name to the host gateway via `extra_hosts`. Fine on a
laptop, not for production.

Whichever you choose, **nothing in the application code changes.** Only `REDIS_HOST`,
`REDIS_PORT`, `REDIS_PASSWORD` and `REDIS_USE_TLS` move. That is the whole point of keeping
them in `.env`.

### 2.6 S3 bucket + IAM role

`settings.py` switches storage backends automatically
([settings.py:248](salon_management/settings.py#L248)):

* **Both** `AWS_STORAGE_BUCKET_NAME` **and** `AWS_S3_REGION_NAME` set → uploads go to S3.
* Either one missing → uploads go to the local `media/` volume, served by nginx at `/media/`.

Bucket setup:

```
Name:              salon-management-media
Region:            ap-south-1
Block public access: ON  (all four boxes — files are served via signed URLs)
Versioning:        Enabled
Encryption:        SSE-S3
```

**Do not put AWS access keys in `.env`.** Attach an IAM role to the instance instead —
`boto3` picks up credentials from the instance metadata service automatically, and the
credentials rotate themselves.

Create role `salon-ec2-role` (trusted entity: EC2) with this inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::salon-management-media/*"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::salon-management-media"
    }
  ]
}
```

Then EC2 → Actions → Security → Modify IAM role → `salon-ec2-role`.

> ⚠️ **Before enabling S3:** `django-storages` and `boto3` are **not in
> [requirements.txt](requirements.txt)**. Setting both S3 variables today makes Django fail at
> import with `ModuleNotFoundError: storages`. Add `django-storages==1.14.4` and
> `boto3==1.35.*` to requirements first, then set the variables. Until then, leave both
> unset and serve media from the volume.

### 2.7 Email

`settings.py` uses plain SMTP ([settings.py:325-330](salon_management/settings.py#L325-L330)).
Two options:

* **Gmail app password** — fine for low volume. `EMAIL_HOST=smtp.gmail.com`, port `587`,
  `EMAIL_USE_TLS=True`, and a 16-character app password (not the account password).
* **Amazon SES** — the production answer. Verify your domain, request production access
  (the sandbox only mails verified addresses), then create SMTP credentials:
  `EMAIL_HOST=email-smtp.ap-south-1.amazonaws.com`, port `587`, TLS on.

Mail is sent from Celery tasks, so a slow SMTP server never blocks an API response.

### 2.8 Domain and HTTPS

Right now [nginx.conf](nginx.conf) listens on port **80 only** — there is no TLS. Pick one
of these before real traffic:

**Option A — Certbot on the instance (cheapest).**

```bash
sudo apt-get install -y certbot
sudo docker compose stop nginx
sudo certbot certonly --standalone -d api.example.com
sudo docker compose start nginx
```

Then mount the certs into the nginx container and add a TLS server block:

```yaml
  nginx:
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - /etc/letsencrypt:/etc/letsencrypt:ro
      - static_data:/app/staticfiles:ro
      - media_data:/app/media:ro
    ports:
      - "80:80"
      - "443:443"
```

```nginx
server {
    listen 443 ssl;
    http2 on;
    server_name api.example.com;

    ssl_certificate     /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;

    # ... same location blocks as the :80 server ...
}

server {
    listen 80;
    server_name api.example.com;
    return 301 https://$host$request_uri;
}
```

Renewal: `0 3 * * * certbot renew --quiet --deploy-hook "docker compose -f /path/docker-compose.yml restart nginx"`

**Option B — Application Load Balancer + ACM (the AWS way).** Free auto-renewing
certificate, TLS terminated at the ALB, health checks on `/health/`, and a path to running
more than one instance later. Costs about $18/month. The ALB must have **stickiness on**
and an **idle timeout ≥ 300s** or WebSocket connections will be cut every 60 seconds.

With either option, add to `.env`:

```
ALLOWED_HOSTS=api.example.com,3.108.219.102,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=https://api.example.com
CHANNELS_ALLOWED_ORIGINS=api.example.com
```

### 2.9 Lambda (optional)

Lambda is not part of the deployment — it is for small independent jobs that shouldn't
occupy the app server. Two realistic uses here:

```
S3 (image uploaded)  →  Lambda  →  validate / generate thumbnail / write back to S3

EventBridge (cron)   →  Lambda  →  call an internal Django endpoint
```

For this project, Celery beat already covers scheduled work, so Lambda's honest use case is
**S3 event processing** — thumbnails, virus scan, EXIF stripping — where you don't want a
5 MB upload pinned in Django's memory.

### 2.10 Monitoring and backups

* **RDS automated backups** — 7 days minimum, verify a restore once.
* **CloudWatch agent** on EC2 for disk and memory (the default EC2 metrics include neither).
* **CloudWatch alarm** on `StatusCheckFailed`, CPU > 80% for 10 min, and RDS free storage.
* **Container logs** — capped by `daemon.json` above; ship to CloudWatch Logs if you want
  retention beyond the instance's life.
* **Media** — versioning on the S3 bucket. If you're on the local volume instead, back it
  up: `docker run --rm -v salon_management_media_data:/m -v $PWD:/b alpine tar czf /b/media-$(date +%F).tgz -C /m .`

---

## 3. The `.env` file

### How it reaches the container

There are **three** copies of this configuration. Keep them straight:

| Where | Who writes it | Used by |
|---|---|---|
| Your laptop's `.env` | You, by hand | local `docker compose up` |
| **GitHub Secrets** | You, once, in repo settings | the deploy workflow |
| EC2 `.env` | **the workflow, on every deploy** | the running containers |

The EC2 `.env` is **generated, not edited.** Anything you type into it by hand is
overwritten on the next push to `main`. To change a production value, change the GitHub
Secret and re-run the workflow.

`.env` is in both [.gitignore](.gitignore) and [.dockerignore](.dockerignore) — it is never
committed and never baked into the image. It is read at container start via compose's
`env_file:`.

### Creating it on EC2 by hand (first boot, before CI exists)

```bash
cd ~/salon_management
nano .env          # paste the variables below
ls -la | grep .env
cat .env
```

### Every variable

| Variable | Example | Notes |
|---|---|---|
| `SECRET_KEY` | `django-insecure-…` | 50+ random chars. Regenerate for production — never reuse the dev one. |
| `DEBUG` | `False` | **Must** be `False` in production. |
| `ALLOWED_HOSTS` | `api.example.com,3.108.219.102,localhost,127.0.0.1` | Host header allow-list. A missing entry = 400 on every request. |
| `CHANNELS_ALLOWED_ORIGINS` | `api.example.com` | Gates the WebSocket **Origin** header. Empty → falls back to `ALLOWED_HOSTS`. |
| `CHANNELS_ALLOW_MISSING_ORIGIN` | `True` | Lets mobile apps/Postman connect (they send no Origin). Safe here because WS auth uses a JWT, not a cookie. |
| `CSRF_TRUSTED_ORIGINS` | `https://api.example.com` | Needs the scheme. Required for the admin behind a proxy. |
| `DEFAULT_DB_NAME` | `salondb` | |
| `DEFAULT_DB_USER` | `salonadmin` | |
| `DEFAULT_DB_PASSWORD` | | No `#` and no line breaks — see the gotcha below. |
| `DEFAULT_DB_HOST` | `salon-db.xxxx.rds.amazonaws.com` | RDS endpoint, no port. |
| `DEFAULT_DB_PORT` | `5432` | |
| `REDIS_HOST` | `salon-cache.xxxx.cache.amazonaws.com` | Or `redis` / `host.docker.internal`. |
| `REDIS_PORT` | `6379` | |
| `REDIS_PASSWORD` | | Empty is allowed — settings omits auth when blank. |
| `REDIS_CHANNEL` | `1` | A **DB number**, not a name. |
| `REDIS_USE_TLS` | `False` | `True` → `rediss://`. Must match ElastiCache's encryption setting. |
| `ACCESS_TOKEN_EXPIRE_TIME_IN_MIN` | `60` | |
| `REFRESH_TOKEN_EXPIRE_TIME_IN_MIN` | `1440` | |
| `HOST_URI` | `https://api.example.com` | Used to build absolute links in emails. |
| `HTTP_PROXY` | | Leave blank unless you really use a proxy. |
| `SUPERUSER_USERNAME` / `_EMAIL` / `_PASSWORD` | | Consumed by `setup_project` on first boot. |
| `STRIPE_LIVE_MODE` | `True` | |
| `STRIPE_PUBLIC_KEY` / `STRIPE_SECRET_KEY` | | Live keys, not test keys. |
| `DJSTRIPE_WEBHOOK_SECRET` | `whsec_…` | Must match the webhook endpoint in the Stripe dashboard. |
| `EMAIL_HOST` … `DEFAULT_FROM_EMAIL` | | See [§2.7](#27-email). |
| `ELASTIC_CLOUD_ID` / `ELASTIC_API_KEY` / `ELASTIC_USERNAME` / `ELASTIC_PASSWORD` | | Only if Elasticsearch is in use — see [elasticsearch.md](elasticsearch.md). |
| `AWS_STORAGE_BUCKET_NAME` / `AWS_S3_REGION_NAME` | | Set **both** to switch to S3 — and read the warning in [§2.6](#26-s3-bucket--iam-role) first. |

### Two `.env` gotchas that cost real hours

1. **No line breaks inside a value.** `.env` is parsed line by line. A multi-line value
   silently keeps only the first line and drops the rest — the variable decodes to garbage
   with no error anywhere. This is exactly why the workflow flattens the base64 bridge key
   with `tr -d '[:space:]'` before writing it.
2. **`#` starts a comment.** A password containing `#` gets truncated at that character.
   Regenerate the password rather than fighting the quoting.

---

## 4. Docker — every service explained

One image, five services. [Dockerfile](Dockerfile) builds
`salon-management:latest` once; `web` has the `build:` block, and `worker`, `beat` and
`setup` just reference the same `image:` tag. So `docker compose up -d --build` rebuilds
once and all four processes get identical code. **Never give worker or beat their own
`build:` block** — that's how you end up with a worker running last week's tasks.

### 4.1 `web` — Django + DRF + WebSockets

```yaml
command: … daphne -b 0.0.0.0 -p 8000 salon_management.asgi:application
```

Runs **Daphne**, not Gunicorn. That is deliberate: this app serves WebSockets
([asgi.py](salon_management/asgi.py) routes `http` → Django and `websocket` → Channels), and
Gunicorn's sync workers cannot hold a long-lived connection open. One ASGI server handles
both protocols.

Its startup script does four things before Daphne starts:

1. `nc -z $DEFAULT_DB_HOST $DEFAULT_DB_PORT` in a loop — blocks until RDS answers. Without
   this the container crash-loops on boot while RDS is still waking up.
2. `migrate_schemas --shared` then `--tenant` — `django_tenants` needs both: shared apps
   live in the `public` schema, tenant apps are migrated into every tenant schema.
3. `setup_project` — the project's own bootstrap command (superuser, base data).
4. `collectstatic --noinput` — writes into the `static_data` volume that nginx reads from.

`exec daphne …` matters: `exec` replaces the shell so Daphne becomes PID 1 and receives
`SIGTERM` directly. Without it, `docker compose down` waits the full 10-second timeout and
then kills it, dropping in-flight connections.

### 4.2 `worker` — Celery worker

```yaml
command: ["celery", "-A", "salon_management", "worker", "-l", "info"]
```

**This is the piece people miss.** Calling `some_task.delay(...)` in Django does not run
anything — it serializes the call and pushes it into Redis, then returns instantly. The
message sits in the queue until a worker process picks it up. No worker container means:

* `.delay()` keeps succeeding — no error, no exception, nothing in the logs
* Redis list `celery` grows forever
* Emails are never sent, reminders never go out, and every debugging hour goes into Django

The worker is a **separate container from `web` on purpose**:

* A task that pins the CPU for 30s cannot slow down an API request
* You can restart the worker (new task code) without dropping WebSocket connections
* You can scale them independently: `docker compose up -d --scale worker=3`

Tasks live in [appointment/tasks.py](appointment/tasks.py) and
[appointment/email.py](appointment/email.py). Because this is a multi-tenant project,
[celery.py](salon_management/celery.py) uses `tenant_schemas_celery`'s `CeleryApp` and
`TenantTask` — the schema name travels with the message, so the worker switches to the
right tenant schema before running the task. A plain `celery.Celery` app here would run
every task against the `public` schema and quietly write data into the wrong tenant.

Useful flags once load grows:

```yaml
command: ["celery", "-A", "salon_management", "worker",
          "-l", "info",
          "--concurrency", "4",        # worker processes; default = CPU count
          "--max-tasks-per-child", "100"]  # recycle workers, caps slow memory leaks
```

### 4.3 `beat` — Celery beat

```yaml
command: ["celery", "-A", "salon_management", "beat", "-l", "info"]
```

Beat is the **clock**. It reads `CELERY_BEAT_SCHEDULE`
([settings.py:349](salon_management/settings.py#L349)) and, when a schedule fires, pushes a
message into the same Redis queue. It never executes a task itself — beat without a worker
produces a growing queue and zero work.

Current schedule:

| Job | Task | When |
|---|---|---|
| `create-timeslots-every-day` | `appointment.tasks.create_recurring_timeslots` | `crontab(hour=0, minute=0)` — daily at midnight UTC |
| `appointment-reminders` | `appointment.tasks.send_appointment_reminders` | `crontab(minute="*/15")` — every 15 minutes |

`CELERY_ENABLE_UTC = True`, so those times are **UTC**. Midnight UTC is 05:30 IST — if
"end of day" should mean end of the Indian business day, that job is running mid-morning.

> 🚨 **Run exactly one beat container.** Two beat processes = every scheduled job fires
> twice = duplicate reminder emails to real customers. This is the one service you must
> never `--scale`.

A comment in settings records a bug worth remembering: the schedule dict was once assigned
to `CELERY_BEAT_SCHEDULER` (which names the scheduler *class*) instead of
`CELERY_BEAT_SCHEDULE`. Beat started fine, logged nothing unusual, and never registered a
single job.

### 4.4 `setup` — migrations on demand

```yaml
profiles: [setup]
```

The `profiles` key means this service is **skipped** by a normal `docker compose up`. It
only runs when you ask for it:

```bash
docker compose --profile setup run --rm setup
```

It is the same migrate/setup/collectstatic block as `web`'s startup. Use it when you want to
run migrations *without* restarting the API — or, better, move migrations out of `web`'s
command entirely and make this the only place they run. Today they are in both, so every
`web` restart re-runs `migrate_schemas` across every tenant schema; that is idempotent but
gets slow as tenants multiply, and it delays the health check on each restart.

### 4.5 `nginx` — why it's in compose at all

The honest question: Daphne already speaks HTTP on 8000. Why put another server in front?

Because Daphne is an application server, not a web server. nginx handles the things an app
server shouldn't:

| Job | Why nginx and not Daphne |
|---|---|
| **TLS / HTTPS** | Certificates, ciphers, HTTP→HTTPS redirect. Django should receive plain HTTP on a private network and read `X-Forwarded-Proto`. |
| **Static files** | `/static/` is served straight off disk with `expires 7d` and `Cache-Control: immutable`. Those bytes never enter a Python process. |
| **Media files** | Same for `/media/`, when not on S3. |
| **Reverse proxy** | One public port 80/443 in front of everything, with real client IP forwarded as `X-Real-IP` / `X-Forwarded-For`. |
| **WebSocket forwarding** | Upgrades `/ws/` connections to Daphne and holds them open. |
| **Upload limits** | `client_max_body_size 25m` — an oversized upload is rejected at the edge, before Django allocates memory. |
| **Domain routing** | `server_name` blocks: add a second app or an admin subdomain later without touching Django. |
| **Slow clients** | nginx buffers a slow connection so it doesn't hold a Daphne worker hostage. |

Why **inside** compose rather than on the host:

* `proxy_pass http://web:8000` uses Docker's internal DNS — no host ports, no IP hunting
* `depends_on: web: condition: service_healthy` — nginx doesn't start until `/health/` passes
* The static and media volumes mount read-only into nginx (`:ro`); host-nginx would need
  those volumes bind-mounted and permission-matched
* One `docker compose up -d` brings the whole stack up, identically on every machine
* Version-pinned (`nginx:1.27-alpine`) and configured by a file in the repo, so the proxy
  config is reviewed and deployed like code

### 4.6 Volumes

```yaml
volumes:
  media_data:     # user uploads       — web writes, nginx reads (:ro)
  static_data:    # collectstatic out  — web+setup write, nginx reads (:ro)
```

Named volumes, so they survive `docker compose down` and image rebuilds. They are destroyed
by `docker compose down -v` — that flag deletes **all customer uploads**. This is also why
[deploy.yml:25](.github/workflows/deploy.yml#L25) sets `clean: false` on checkout: a git
clean in the workspace would take `media/` with it.

### 4.7 The `8001` port publish

```yaml
ports:
  - "8001:8000"
```

This exposes Daphne directly on the host, bypassing nginx. It was useful for debugging
before nginx existed. Now it is a way to reach the app without TLS, without rate limits and
without the upload cap. Keep port 8001 closed in `salon-ec2-sg` (it is), and consider
deleting these two lines — nginx reaches `web:8000` over the internal network and does not
need a published port.

### 4.8 Health check

```yaml
test: ["CMD", "curl", "-f", "-H", "Host:3.108.219.102", "http://127.0.0.1:8000/health/"]
```

The explicit `Host` header exists because Django validates it against `ALLOWED_HOSTS`, and
`127.0.0.1` inside the container isn't necessarily in the list. But the IP is **hardcoded**
— move the instance, get a new Elastic IP, and the health check fails, nginx never starts
(it waits for `service_healthy`), and the whole deploy stalls with a confusing error. Use a
name that is always in `ALLOWED_HOSTS` instead:

```yaml
test: ["CMD", "curl", "-f", "-H", "Host:localhost", "http://127.0.0.1:8000/health/"]
```

…with `localhost` present in `ALLOWED_HOSTS`. The endpoint itself
([urls.py:22](salon_management/urls.py#L22)) returns `{"status": "ok"}` and prints the
effective `ALLOWED_HOSTS` / `CHANNELS_ALLOWED_ORIGINS` values, which makes
`docker compose logs web` the fastest way to see what the container actually loaded.

### 4.9 Commands you'll use constantly

```bash
# bring the stack up (builds the image)
docker compose up -d --build

# what's running, and is it healthy?
docker compose ps

# logs
docker compose logs -f web
docker compose logs -f worker
docker compose logs -f beat
docker compose logs --tail=100

# Django shell / management commands
docker compose exec web python manage.py shell
docker compose exec web python manage.py migrate_schemas --shared
docker compose exec web python manage.py createsuperuser

# migrations without touching the API
docker compose --profile setup run --rm setup

# restart just the worker after a task-code change
docker compose restart worker

# is the queue actually draining?
docker compose exec worker celery -A salon_management inspect active
docker compose exec worker celery -A salon_management inspect registered

# reclaim disk
docker image prune -f
docker system df
```

---

## 5. WebSockets — the full path

```
Browser:  new WebSocket("wss://api.example.com/ws/notifications/?token=<JWT>")
   │
   │  HTTP GET with  Upgrade: websocket  +  Origin: https://api.example.com
   ▼
nginx        :443 → TLS terminated
   │           proxy_http_version 1.1
   │           proxy_set_header Upgrade $http_upgrade
   │           proxy_set_header Connection "upgrade"
   ▼
Daphne       :8000  — ASGI, holds the socket open
   │
   ▼
ProtocolTypeRouter          asgi.py — "websocket" branch
   │
   ├── SettingsOriginValidator   checks Origin against CHANNELS_ALLOWED_ORIGINS
   ├── AuthMiddlewareStack       resolves the user
   └── URLRouter                 routing.py
   │
   ▼
NotificationConsumer        appointment/consumers.py
   │
   ▼
Channel layer → Redis (db = REDIS_CHANNEL)
   │
   └── group_send from anywhere — a DRF view, or a Celery worker — reaches every
       connected socket in the group, even across containers
```

The route is
`^(?:(?P<tenant_schema>[\w-]+)/)?ws/notifications/$`
([routing.py](salon_management/routing.py)), so both of these connect:

```
wss://api.example.com/ws/notifications/
wss://api.example.com/salon-abc/ws/notifications/     ← tenant-scoped
```

**Redis is what makes this work with more than one process.** A Celery worker in one
container can push a notification to a browser held open by the `web` container, because
both talk to the same channel layer. With the in-memory layer, that message would vanish.

Two headers decide whether a connection lives or dies, and they are easy to confuse:

| Header | Checked against | Failure looks like |
|---|---|---|
| `Host` | `ALLOWED_HOSTS` | HTTP 400 on every request |
| `Origin` | `CHANNELS_ALLOWED_ORIGINS` | WebSocket closes immediately, HTTP works fine |

Non-browser clients (mobile, Postman, `wscat`) send **no** `Origin` header —
`CHANNELS_ALLOW_MISSING_ORIGIN=True` is what lets them in. Auth is a JWT in the query
string, not a cookie, so a hostile page can't forge a connection on a victim's behalf.

> ⚠️ **nginx bug to fix.** [nginx.conf:25](nginx.conf#L25) sets `Connection "upgrade"` on
> **every** request in `location /`, not just WebSocket ones. Normal API requests then carry
> a bogus upgrade header, which breaks keep-alive and confuses some clients and load
> balancers. The correct pattern is a `map` at `http` level:
>
> ```nginx
> map $http_upgrade $connection_upgrade {
>     default upgrade;
>     ''      close;
> }
> ```
> …then `proxy_set_header Connection $connection_upgrade;`. Also add
> `proxy_read_timeout 3600s;` — nginx's default 60s closes idle WebSockets after a minute.

Test from the EC2 box:

```bash
curl -i -H "Host: api.example.com" http://127.0.0.1/health/
docker compose exec web python -c "import websockets"   # or use wscat from your laptop
```

---

## 6. GitHub Actions self-hosted runner

### Why self-hosted instead of `ubuntu-latest`

`runs-on: self-hosted` means the job executes **on the EC2 instance itself**. That buys:

* **No SSH keys in GitHub.** A GitHub-hosted runner would need a private key and an open
  port 22 to deploy. The self-hosted runner already *is* the server.
* **RDS and ElastiCache stay private.** They are only reachable from inside the VPC; a
  hosted runner can't reach them at all.
* **Docker layer cache persists** between runs, so rebuilds take a minute instead of ten.
* **Free.** No Actions minutes are billed for self-hosted runners.

The cost: the runner has full access to your production box, and it builds there — so CPU
and disk are shared with the live app. **Never enable a self-hosted runner on a public
repository** — anyone's pull request would execute code on your server.

### Install

Get the registration token first: **repo → Settings → Actions → Runners → New self-hosted
runner → Linux x64**. The token shown there expires in about an hour.

```bash
ssh -i salon-management-key.pem ubuntu@3.108.219.102

mkdir -p ~/actions-runner && cd ~/actions-runner

# use the version GitHub's page shows you — this is an example
curl -o actions-runner-linux-x64.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.328.0/actions-runner-linux-x64-2.328.0.tar.gz
tar xzf ./actions-runner-linux-x64.tar.gz

./config.sh \
  --url https://github.com/<your-org>/salon_management \
  --token <REGISTRATION_TOKEN> \
  --name salon-prod-ec2 \
  --labels self-hosted,linux,x64,production \
  --work _work \
  --unattended
```

Install it as a service so it survives reboots and SSH disconnects:

```bash
sudo ./svc.sh install ubuntu     # run AS the ubuntu user, not root
sudo ./svc.sh start
sudo ./svc.sh status
```

Confirm it shows **Idle** in Settings → Actions → Runners.

### Give the runner Docker access

The workflow calls `sudo docker compose`, so the runner user needs passwordless sudo for
docker:

```bash
echo 'ubuntu ALL=(ALL) NOPASSWD: /usr/bin/docker' | sudo tee /etc/sudoers.d/runner-docker
sudo chmod 440 /etc/sudoers.d/runner-docker
sudo visudo -c        # validate — a broken sudoers file locks you out
```

Cleaner alternative: add `ubuntu` to the `docker` group (done in [§2.3](#23-install-docker-on-ec2)),
then drop `sudo` from every command in the workflow. Both work; pick one and be consistent,
because containers started with `sudo` and containers started without it belong to the same
daemon but the *files* the runner writes will differ in ownership — which is exactly why
[deploy.yml:17-19](.github/workflows/deploy.yml#L17-L19) has a "Reclaim workspace ownership"
step. That step exists because an earlier root-owned build left files `actions/checkout`
couldn't overwrite.

### Where the code lands

```
~/actions-runner/_work/salon_management/salon_management/
```

That is the workspace, and it is **not** `~/salon_management`. Everything the workflow runs
happens there, so that directory is the live deployment.

Docker Compose names a project after its directory, so both paths happen to produce the
project name `salon_management` and therefore share the same containers and volumes. Don't
rely on that coincidence — **pick the runner workspace as the one true path** and run manual
commands there:

```bash
cd ~/actions-runner/_work/salon_management/salon_management
docker compose ps
```

To be explicit and immune to directory names, set a fixed project name:

```bash
echo "COMPOSE_PROJECT_NAME=salon" >> ~/.bashrc
# and add  name: salon  at the top of docker-compose.yml
```

### Required GitHub Secrets

Settings → Secrets and variables → Actions → New repository secret. The workflow writes one
`.env` line per secret, so a missing secret becomes an empty value, not an error.

```
SECRET_KEY                          DEFAULT_DB_NAME
ALLOWED_HOSTS                       DEFAULT_DB_USER
CHANNELS_ALLOWED_ORIGINS            DEFAULT_DB_PASSWORD
CHANNELS_ALLOW_MISSING_ORIGIN       DEFAULT_DB_HOST
DEBUG                               DEFAULT_DB_PORT

REDIS_HOST                          ACCESS_TOKEN_EXPIRE_TIME_IN_MIN
REDIS_PORT                          REFRESH_TOKEN_EXPIRE_TIME_IN_MIN
REDIS_PASSWORD                      HTTP_PROXY
REDIS_CHANNEL                       HOST_URI

SUPERUSER_USERNAME                  STRIPE_LIVE_MODE
SUPERUSER_EMAIL                     STRIPE_PUBLIC_KEY
SUPERUSER_PASSWORD                  STRIPE_SECRET_KEY
                                    DJSTRIPE_WEBHOOK_SECRET
ELASTIC_CLOUD_ID
ELASTIC_API_KEY                     EMAIL_HOST
ELASTIC_USERNAME                    EMAIL_HOST_USER
ELASTIC_PASSWORD                    EMAIL_HOST_PASSWORD
                                    EMAIL_PORT
AWS_STORAGE_BUCKET_NAME             EMAIL_USE_TLS
AWS_S3_REGION_NAME                  DEFAULT_FROM_EMAIL

BRIDGE_SIGNING_PRIVATE_KEY_B64
```

Faster with the `gh` CLI:

```bash
gh secret set SECRET_KEY --body "…"
gh secret set DEFAULT_DB_PASSWORD --body "…"
# bulk, from a local file of KEY=VALUE lines:
gh secret set -f .env.production
```

---

## 7. `deploy.yml` walkthrough

Triggers: push to `main`, or manual run via **workflow_dispatch**. Pushes to `dev` do
nothing — merge to `main` to deploy.

| Step | What it does | Why it's there |
|---|---|---|
| **Reclaim workspace ownership** | `chown -R $(id -u):$(id -g) $GITHUB_WORKSPACE` | Root-owned leftovers from `sudo docker` would make checkout fail. `\|\| true` so a clean workspace doesn't fail the job. |
| **Checkout** | `actions/checkout@v3`, `clean: false`, `fetch-depth: 0` | `clean: false` protects `media/`. Full history for tags/version info. |
| **Create environment file** | heredoc → `.env`, then the bridge key, then a sanity check | See below. |
| **Build and start services** | `docker compose up -d --build` | Builds the image on the box and recreates changed containers. Unchanged ones keep running. |
| **Wait for services** | `sleep 15`, `compose ps`, `logs web --tail=50` | Gives migrations + collectstatic time before the status check. |
| **Run database migrations** | prints a message, sleeps 10 | Migrations actually run inside `web`'s startup command — this step is just a pause. |
| **Check service status** | `compose ps`, `logs --tail=100`, `image prune -f` | Final state in the run log, then reclaims disk from the old image layers. |

### About the `.env` step

Two mechanisms, deliberately different:

```bash
cat > .env << 'EOF'
SECRET_KEY=${{ secrets.SECRET_KEY }}
…
EOF
```

The quotes in `<< 'EOF'` stop **bash** from expanding anything. That is safe because
`${{ secrets.X }}` is substituted by **GitHub Actions before bash ever sees the script** —
so a secret containing `$HOME` or a backtick can't be executed. YAML strips the block's
common indentation, so each `KEY=VALUE` lands at column 0.

The bridge key is handled separately because `base64` wraps output at 76 columns, so the
secret itself may be multi-line — and a multi-line value in `.env` loses everything after
the first line, silently. `tr -d '[:space:]'` collapses it back to one line before it is
appended.

Then:

```bash
if [ ! -f ".env" ] || [ ! -s ".env" ]; then exit 1; fi
echo "Environment variables count: $(grep -c "=" .env)"
```

That count is worth reading in the run log. If it drops after you add a secret, a heredoc
line is malformed.

### Manual deploy, if CI is down

```bash
cd ~/actions-runner/_work/salon_management/salon_management
git pull origin main
docker compose up -d --build
docker compose ps
docker compose logs -f web
```

`.env` is already on disk from the last successful workflow run.

---

## 8. Day-2 operations

### Deploying

Merge to `main`. Watch the run in the Actions tab. Expect 2–5 minutes; the first build after
a `requirements.txt` change is slower because the pip layer is invalidated.

There is a **short downtime window** on every deploy — `docker compose up` stops the old
`web` container before the new one is healthy. For zero-downtime you need two web replicas
behind nginx with `--scale web=2` and a rolling restart, or an ALB with two instances.

### Rolling back

```bash
cd ~/actions-runner/_work/salon_management/salon_management
git log --oneline -10
git checkout <last-good-sha>
docker compose up -d --build
```

Then fix forward on `main`. **A rollback does not undo a migration** — if the bad deploy
migrated the database, restore from the RDS snapshot or write a reverse migration.

### Adding a tenant

```bash
docker compose exec web python manage.py shell
```

Create the `Client`/`Domain` rows; `django_tenants` creates and migrates the new schema. Then
make sure the tenant's domain is in `ALLOWED_HOSTS` (or use a wildcard like `.example.com`)
and in `CHANNELS_ALLOWED_ORIGINS`, or that tenant's WebSockets will fail while its HTTP works.

### Checking Celery is alive

```bash
docker compose logs beat | tail -20        # should show "Scheduler: Sending due task …"
docker compose logs worker | tail -20      # should show "Task … succeeded"
docker compose exec worker celery -A salon_management inspect active
```

If beat logs "Sending due task" and worker logs nothing, the two are pointed at different
Redis databases — compare `REDIS_HOST`/`REDIS_PORT` in both containers with
`docker compose exec worker env | grep REDIS`.

### Disk

```bash
df -h
docker system df
docker image prune -f          # the workflow already does this
docker builder prune -f        # build cache — this is usually the real hog
```

---

## 9. Scaling for live traffic — and why a load balancer

Today everything runs on **one EC2 instance**: nginx, Daphne, the worker, beat, *and* the
Docker build. That is the right choice for launch — it is cheap, simple, and one `docker
compose up` deploys the whole thing. It is also a single point of failure, and it stops
being enough at a fairly predictable point.

### 9.1 When one box stops being enough

Watch for these, in roughly this order:

| Signal | What it means |
|---|---|
| CPU > 70% sustained, or CPU spikes during every deploy | The Docker build is competing with live requests for the same cores |
| API p95 latency climbing while CPU is fine | Blocked on the database or on slow external calls (Stripe, SMTP) |
| Memory pressure / OOM-killed containers | Daphne + N worker processes + a build don't fit in 4 GB |
| Celery queue depth growing and never draining | Not enough worker concurrency |
| RDS connections near the cap | Too many processes, each holding connections |
| "The site was down for 4 minutes during the deploy" | The inherent restart gap of a single instance |
| Any unplanned reboot = total outage | The real reason to move, regardless of load |

Some quick capacity math for this stack. Daphne is async, so **concurrent WebSocket
connections are cheap** — a `t3.medium` holds several thousand idle sockets. What actually
runs out first is **CPU on request handling** and **database connections**: every Daphne
process and every Celery worker process holds its own Postgres connection, and a
`db.t3.micro` caps out around 112 total. Four workers plus Daphne plus a migration run is
already a meaningful slice of that.

### 9.2 Scale up before you scale out

Do the cheap things first — they buy a lot and cost nothing in complexity:

1. **Bigger instance.** `t3.medium` → `t3.large` is one stop/start and a two-minute outage.
2. **Move the build off the box.** Build the image in GitHub-hosted CI, push to **ECR**, and
   have the instance only `docker compose pull && up -d`. Production CPU stops being spent
   on `pip install`, and deploys get faster. (This is the point where the ECR box in your
   architecture diagram starts to be real.)
3. **Indexes and query fixes.** One missing index usually beats one extra server.
4. **Move media to S3.** Also a prerequisite for step 9.4 — see below.
5. **Scale workers in place:** `docker compose up -d --scale worker=3`. Background work is
   the easiest thing to scale, and it doesn't need a load balancer at all.

### 9.3 Why a load balancer

A load balancer is not only about spreading traffic. For this stack it does six jobs:

| Job | What you get |
|---|---|
| **TLS termination** | A free, auto-renewing **ACM** certificate. No certbot cron, no cert files on disk, no 3 a.m. expiry outage. |
| **Health checks** | The ALB polls `/health/` on every instance and stops sending traffic to a sick one **within seconds**, automatically. Today a broken container serves errors until someone notices. |
| **Zero-downtime deploys** | Deploy to instance A while B serves, then swap. The ALB drains connections instead of cutting them. Right now every deploy has a real downtime gap. |
| **Horizontal scale** | Add a third instance and it starts receiving traffic. Without an LB, the only way to add capacity is a bigger box — and there is a ceiling. |
| **High availability across AZs** | Instances in `ap-south-1a` and `ap-south-1b`. An entire availability zone can fail and the site stays up. A single EC2 cannot survive its own AZ. |
| **A stable front door** | One DNS name forever. Instances come and go, get replaced, get resized — clients never see it. Also the attach point for **WAF**, Shield, and access logs. |

And two smaller ones: the ALB absorbs slow/malicious clients so they never occupy a Daphne
connection, and its access logs give you per-request latency without adding anything to
Django.

**Which one:** an **Application Load Balancer (ALB)**. It is layer 7, so it understands HTTP
paths, hostnames (useful with tenant subdomains), and — importantly here — it supports
**WebSocket upgrades natively**. A Network Load Balancer is layer 4: faster and it gives you
a static IP, but it can't route by path or host and can't terminate at the HTTP level. The
Classic LB is deprecated. **Use the ALB.**

Cost: roughly **$18–25/month** plus a small per-request charge. That is about the price of
the `t3.small` you'd otherwise add — and you get TLS management and health checks for free.

### 9.4 What must be true before you can run two instances

This is the part that bites people. A load balancer sends request 1 to instance A and
request 2 to instance B, so **anything stored on one instance's disk effectively disappears
half the time.** Go through this list before adding the second box:

| Requirement | Status in this project |
|---|---|
| **Media on shared storage** | ❌ **Blocker.** Uploads go to the `media_data` Docker volume on one instance. With two, an image uploaded via A returns 404 when the next request lands on B. Must move to **S3** ([§2.6](#26-s3-bucket--iam-role)) — and that needs `django-storages` + `boto3` added first. |
| **Sessions not in local memory** | ✅ API auth is JWT (stateless); admin sessions are database-backed. |
| **Channel layer shared** | ✅ Already Redis. This is the big one and it's already right — a WebSocket held open by instance A still receives a `group_send` fired from instance B or from a Celery worker. An in-memory channel layer would have made multi-instance impossible. |
| **Celery broker shared** | ✅ Already Redis. Any worker on any instance picks up any task. |
| **Static files** | ⚠️ Each instance runs its own `collectstatic`, which works. Cleaner: push static to S3 + CloudFront and let the CDN serve it. |
| **Exactly one beat** | ❌ **Blocker.** Beat is in `docker-compose.yml`, so two instances = two schedulers = every reminder email sent twice. Split into a separate compose file (or a separate small instance) that runs on one node only. |
| **Migrations run once** | ❌ **Blocker.** They're in `web`'s startup command, so two instances migrate the same database concurrently on every deploy. Move them to the `setup` profile and run that as its own deploy step ([§4.4](#44-setup--migrations-on-demand)). |
| **Config not hand-placed on a box** | ⚠️ `.env` is written by the workflow onto one instance. With N instances, move to **SSM Parameter Store** or **Secrets Manager** and have each instance fetch at boot. |
| **Image built once, not per-box** | ⚠️ Each instance would build its own. Move to **ECR** and pull. |

Items 1, 2 and 3 are genuine blockers. Everything else is cleanup.

### 9.5 The target architecture

```
                            Route 53
                               │
                          ACM certificate
                               ▼
                   ┌───────────────────────┐
                   │  Application LB :443  │  health check → /health/
                   └───────┬───────┬───────┘
                           │       │
              ap-south-1a  │       │  ap-south-1b
                  ┌────────▼──┐ ┌──▼────────┐
                  │   EC2 #1  │ │   EC2 #2  │   ← Auto Scaling Group
                  │  web      │ │  web      │
                  │  worker   │ │  worker   │
                  └────┬──────┘ └──────┬────┘
                       │               │
                  ┌────▼───────────────▼────┐
                  │  EC2 #0  (no LB traffic)│
                  │  beat ×1  + migrations  │  ← the singleton box
                  └────┬───────────────┬────┘
                       │               │
        ┌──────────────▼──┐        ┌───▼─────────────┐        ┌──────────┐
        │ RDS (Multi-AZ)  │        │ ElastiCache     │        │   S3     │
        │ + read replica  │        │ Redis + replica │        │  media   │
        └─────────────────┘        └─────────────────┘        └──────────┘
```

Note what moved: **nginx's job shrinks.** The ALB handles TLS and health checks, S3 +
CloudFront handle static and media. You can keep nginx per-instance for request buffering
and upload limits, or drop it and point the ALB target group straight at Daphne on 8000.
Keeping it is the smaller change.

### 9.6 ALB setup, with the settings that matter

Target group:

```
Protocol/port:        HTTP : 80   (or 8000 if you drop nginx)
Health check path:    /health/
Healthy threshold:    2      Unhealthy: 3
Interval: 15s          Timeout: 5s
Deregistration delay: 300s        ← give open WebSockets time to drain
Stickiness:           enabled, 1 day (lb_cookie)
```

Listeners:

```
:80   → redirect 301 to HTTPS
:443  → ACM certificate → forward to the target group
        Idle timeout: 3600s        ← THE WebSocket setting
```

Three settings decide whether WebSockets survive behind an ALB:

1. **Idle timeout 3600s.** The default is 60 seconds, and it closes any connection with no
   bytes flowing — which is exactly what an idle notification socket looks like. Combine it
   with an application-level ping every ~30s so the connection is never truly idle.
2. **Deregistration delay 300s.** On deploy, this lets existing sockets finish instead of
   being cut mid-message.
3. **Stickiness.** Irrelevant *once* a WebSocket is established (it's one long-lived
   connection to one target), but it keeps a client's HTTP requests on one instance, which
   makes the admin and any session-backed flows behave predictably.

Then update `.env`: `ALLOWED_HOSTS` must include the domain, and because TLS now terminates
at the ALB, Django sees plain HTTP. Add to `settings.py` so it trusts the proxy header that
nginx and the ALB already send:

```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
```

Without that, `request.is_secure()` is `False`, absolute URLs come out as `http://`, and
`SECURE_SSL_REDIRECT` (if you enable it) causes an infinite redirect loop.

### 9.7 Scaling each tier

**Web.** Add instances behind the ALB. With an Auto Scaling Group, scale on
`ALBRequestCountPerTarget` (a better signal than CPU for this workload) or on CPU > 60%.
Set a generous cooldown — instances take a couple of minutes to boot, pull, and pass health
checks. Min 2, so you always survive losing one.

**Celery workers.** The easiest tier. They take no inbound traffic, so no load balancer is
involved — just run more processes. Scale on **queue depth**, not CPU:

```bash
docker compose exec worker celery -A salon_management inspect active
docker compose up -d --scale worker=4
```

Give slow jobs their own queue (`-Q emails`) so a backlog of reminder emails can't delay
time-sensitive work.

**Celery beat.** Never scales. Exactly one, forever. If you want it highly available,
that's what `RedBeat` (a Redis-lock-based scheduler) is for — it lets two beats run with
only one holding the lock.

**Database.** Vertical first (`db.t3.micro` → `small` → `medium`), then:
- **Multi-AZ** — a standby in another AZ, automatic failover. Doubles cost, and it is the
  first thing to buy once you have paying tenants.
- **Read replica** — for reports and analytics, via a Django database router.
- **RDS Proxy** — pools connections. Worth it once N instances × M processes exceeds the
  connection cap; cheaper than upgrading the instance just for connection headroom.

**Redis.** One `cache.t4g.micro` handles both the broker and the channel layer for a long
time. Add a replica for failover before you add size. If the channel layer ever gets noisy,
split it onto its own cluster — the DB-number separation is already in place, so it is a
config change only.

### 9.8 A staged path

| Stage | Traffic | Setup | ~Cost/mo |
|---|---|---|---|
| **0 — now** | Launch, first tenants | 1× `t3.medium`, RDS micro, ElastiCache micro, media on volume | ~$70 |
| **1** | Real users, downtime hurts | Move media → S3, build → ECR, `t3.large`, RDS Multi-AZ. Still one box. | ~$150 |
| **2** | Can't afford an outage | **ALB + ACM**, 2 instances in 2 AZs, beat split onto its own node, migrations as a deploy step | ~$250 |
| **3** | Growing and spiky | Auto Scaling Group (min 2), read replica, CloudFront for static/media, RDS Proxy | ~$400+ |

Most projects stay at stage 1 far longer than expected. The honest trigger for stage 2 is
usually not load — it's **"we can no longer take a four-minute outage to deploy."** That is
what the load balancer is really buying.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `: No such file or directory` in the env step | An undefined variable used as a redirect target — bash writes to `""`. Caused by a leftover `$ENV_TMP`; now writes to `.env`. | Every redirect target in that step must be a literal path or a variable defined in the same step. |
| HTTP 400 on every request | Host not in `ALLOWED_HOSTS` | Add the domain/IP to the secret, re-run the workflow. |
| HTTP works, WebSocket closes instantly | Origin not in `CHANNELS_ALLOWED_ORIGINS` | Bare hostname, no scheme. `docker compose logs web` prints the loaded value. |
| WebSocket drops after exactly 60s | nginx `proxy_read_timeout` default | Set `proxy_read_timeout 3600s;` (and ALB idle timeout, if used). |
| `nginx` container never starts | It waits for `web` to be `service_healthy`; the health check has a hardcoded Host IP | [§4.8](#48-health-check) |
| Container restart loop, "could not connect to server" | Security group, or wrong `DEFAULT_DB_HOST` | Test with the `psql` one-liner in [§2.4](#24-rds-postgresql). |
| Tasks queue but never run | No worker container, or worker on a different Redis | [§4.2](#42-worker--celery-worker) |
| Scheduled jobs never fire | Beat not running, or wrong settings key | [§4.3](#43-beat--celery-beat) |
| Duplicate reminder emails | Two beat containers | Exactly one, always. |
| `ModuleNotFoundError: storages` | S3 vars set, `django-storages` not installed | [§2.6](#26-s3-bucket--iam-role) |
| Static files 404 | `collectstatic` didn't run, or nginx lost the volume | `docker compose --profile setup run --rm setup` |
| Uploads vanish after deploy | Someone ran `docker compose down -v` | Restore from backup. Never use `-v` here. |
| Checkout fails, "permission denied" | Root-owned files from `sudo docker` | The chown step handles it; make sure it ran. |
| Runner shows Offline | Service stopped, or instance rebooted | `cd ~/actions-runner && sudo ./svc.sh status && sudo ./svc.sh start` |
| Deploy succeeds, old code still served | Stale image or a second compose project | `docker compose ps` and check `CREATED`; confirm you're in the runner workspace. |

Useful one-liners:

```bash
# what did the container actually load?
docker compose exec web env | grep -E "ALLOWED|REDIS|DB_HOST|DEBUG"

# is Redis reachable from inside?
docker compose exec web python -c "import redis, os; \
  print(redis.Redis(host=os.environ['REDIS_HOST'], port=int(os.environ['REDIS_PORT']), \
  password=os.environ.get('REDIS_PASSWORD') or None).ping())"

# Django's own check
docker compose exec web python manage.py check --deploy
```

---

## 11. Known gaps before going live

Findings from reading the current configuration. Ordered by how much they'd hurt.

| # | Issue | Where | Fix |
|---|---|---|---|
| 1 | **No HTTPS.** Everything, including JWTs, travels in clear text. | [nginx.conf:2](nginx.conf#L2) | [§2.8](#28-domain-and-https) |
| 2 | **`Connection: upgrade` on every request**, not just WebSocket ones. Breaks keep-alive. | [nginx.conf:25](nginx.conf#L25) | `map $http_upgrade $connection_upgrade` |
| 3 | **`proxy_read_timeout` unset** — idle WebSockets die after 60s. | [nginx.conf](nginx.conf) | `proxy_read_timeout 3600s;` |
| 4 | **`django-storages` / `boto3` missing** while the workflow ships S3 secrets — setting both crashes Django at import. | [requirements.txt](requirements.txt) | Add both, or leave the S3 vars unset. |
| 5 | **Hardcoded IP in the health check.** New Elastic IP → deploy stalls. | [docker-compose.yml:71](docker-compose.yml#L71) | Use `Host:localhost`. |
| 6 | **Port 8001 published**, bypassing nginx. | [docker-compose.yml:55-56](docker-compose.yml#L55-L56) | Delete the `ports:` block on `web`. |
| 7 | **Migrations run on every `web` start**, not just on deploy. Slows restarts as tenants grow; two `web` replicas would migrate concurrently. | [docker-compose.yml:37-44](docker-compose.yml#L37-L44) | Move to the `setup` profile, run it as its own workflow step. |
| 8 | **`worker`/`beat` don't wait for the database** — they crash-loop until RDS answers. Noisy, but self-healing via `restart: unless-stopped`. | [docker-compose.yml:101](docker-compose.yml#L101) | Add the same `nc -z` wait, or `depends_on: web: service_healthy`. |
| 9 | **`actions/checkout@v3`** runs on Node 16, which GitHub has retired. | [deploy.yml:22](.github/workflows/deploy.yml#L22) | Bump to `@v4`. |
| 10 | **No tests in the pipeline.** A syntax error reaches production and is caught by the health check, not by CI. | [deploy.yml](.github/workflows/deploy.yml) | Add a `pytest` step before the deploy job. |
| 11 | **Deploy has a downtime gap** — old container stops before the new one is healthy. | — | Two replicas + rolling restart, or an ALB — [§9.3](#93-why-a-load-balancer). |
| 12 | **Single point of failure.** One EC2; if it dies, everything is down and the runner with it. | — | ALB + two instances across AZs — [§9](#9-scaling-for-live-traffic--and-why-a-load-balancer). |
| 13 | **`requirements.txt` is UTF-16 encoded.** pip handles the BOM, but many editors and `grep` do not. | [requirements.txt](requirements.txt) | Re-save as UTF-8. |
| 14 | **Beat schedule is UTC** — the "daily at midnight" job runs at 05:30 IST. | [settings.py:352](salon_management/settings.py#L352) | Intentional? If not, offset the crontab. |

### Pre-launch checklist

- [ ] `DEBUG=False`
- [ ] Fresh `SECRET_KEY`, different from every dev environment
- [ ] `ALLOWED_HOSTS` covers the real domain and every tenant domain
- [ ] HTTPS live, HTTP redirects to it
- [ ] `python manage.py check --deploy` clean
- [ ] RDS: public access **off**, backups on, deletion protection on
- [ ] Security groups: no `0.0.0.0/0` except 80/443
- [ ] SSH restricted to known IPs
- [ ] Stripe live keys, webhook endpoint registered and verified
- [ ] A test email actually arrives
- [ ] WebSocket connects from the real frontend over `wss://`
- [ ] Beat fired at least one scheduled job and the worker ran it
- [ ] Media survives a `docker compose down && up`
- [ ] Tested a restore from an RDS snapshot
- [ ] CloudWatch alarms on CPU, disk, and RDS storage
- [ ] Runner shows **Idle**, service enabled, survives a reboot
