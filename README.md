# ImageURL SaaS — MVP

> A developer-friendly image infrastructure SaaS that converts Base64 or uploaded images into reliable public URLs.

Built according to [`PLAN.md`](./PLAN.md). The MVP covers **Phase 0 + Phase 1**: anonymous upload, Base64 → URL, email/password auth, dashboard, API + API keys, plans, mock payments, and an hourly cleanup job.

---

## Stack

| Layer | Tech |
|---|---|
| Database | MySQL 8 (Docker) |
| Backend | Python 3.12 + FastAPI + SQLAlchemy + Alembic |
| Auth | JWT (python-jose) + bcrypt |
| Image processing | Pillow (magic bytes + EXIF strip + pixel-bomb guard) |
| Rate limiting | slowapi (in-memory) |
| Storage | Local filesystem (`/data/uploads`, sharded by key prefix) |
| Worker | APScheduler inside a Python container |
| Reverse proxy + static | nginx:alpine |
| Frontend | Static HTML + Tailwind Play CDN + Vanilla JS |
| Dev DB UI | Adminer (port 8080) |

The architecture, security and abuse rules in `PLAN.md` §5, §8 and §9 are implemented as far as the MVP requires.

---

## Project layout

```
imageurl-demo/
├── PLAN.md                       # The product plan this MVP implements
├── README.md                     # You are here
├── docker-compose.yml            # mysql + api + worker + web (nginx) + adminer
├── .env.example                  # All env vars; copy to .env
├── Makefile                      # make up / down / logs / migrate / seed / e2e / reset
├── scripts/
│   └── smoke_test.sh             # E2E happy-path through nginx
├── api/                          # FastAPI service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/                  # migration env + 0001_initial.py
│   ├── scripts/                  # entrypoint.sh + wait-for-mysql.sh
│   └── app/
│       ├── main.py               # FastAPI app, routers, exception handlers
│       ├── config.py             # Pydantic Settings
│       ├── database.py
│       ├── security.py           # bcrypt + JWT
│       ├── deps.py
│       ├── errors.py
│       ├── rate_limit.py
│       ├── models/               # 7 SQLAlchemy models (Baokim conventions)
│       ├── schemas/              # Pydantic request/response
│       ├── routers/              # auth, images, anonymous, api_keys, usage, payments, public_serve
│       ├── services/             # storage, image_processor, base64_decode, key_generator, credit, plan, api_key, upload
│       └── seed.py               # idempotent: 3 plans + demo user
├── worker.Dockerfile             # Build from root context so it can import api/*
├── worker/
│   ├── requirements.txt
│   └── app/tasks/cleanup_runner.py   # APScheduler, batch delete expired images
└── web/                          # Static frontend (nginx-served)
    ├── Dockerfile
    ├── nginx.conf                # serves /i/* from shared volume, proxies /api/*
    ├── index.html                # Landing page (anonymous upload)
    ├── login.html
    ├── register.html
    ├── dashboard.html            # Sidebar + 6 tabs (Upload/Overview/Images/Keys/Usage/Docs)
    └── assets/
        ├── css/site.css
        └── js/{api,auth,upload,dashboard,index,docs}.js
```

---

## Quickstart

### 0. Prerequisites

- Docker + Docker Compose v2
- (Optional) `make` — the Makefile wraps common commands
- A terminal with `python3` available for the smoke test

### 1. Configure

```bash
cp .env.example .env
# Edit .env: set MYSQL_ROOT_PASSWORD and JWT_SECRET (e.g. `openssl rand -hex 32`).
```

The compose file mounts `.env` into the API and worker containers. Make sure `PUBLIC_IMAGE_BASE_URL=http://localhost/i` (default) matches your access host.

### 2. Start everything

```bash
make up         # docker compose up -d --build
```

The `api` container's entrypoint will:
- Wait until MySQL is reachable (`wait-for-mysql.sh`)
- Run `alembic upgrade head`
- Run `python -m app.seed` (idempotent: 3 plans + demo user)
- Start `uvicorn`

Tail logs:
```bash
make logs       # docker compose logs -f --tail=200
```

### 3. Sanity check

```bash
curl -s http://localhost/healthz
# {"status":"ok"}
```

### 4. Run the E2E smoke test

```bash
make e2e
```

This registers a fresh user, uploads a 1×1 PNG anonymously, registers, logs in, uploads with JWT, creates an API key, uploads via API key, lists plans and usage. See [`scripts/smoke_test.sh`](./scripts/smoke_test.sh).

### 5. Open the UI

| URL | Purpose |
|---|---|
| http://localhost/ | Landing page — anonymous upload (no auth) |
| http://localhost/login.html | Login form |
| http://localhost/register.html | Sign-up form |
| http://localhost/dashboard.html | Authenticated dashboard (6 tabs) |
| http://localhost:8080 | Adminer (database inspection, user = `imageurl`, pwd = `imageurl_pwd`, server = `mysql`) |
| http://localhost/api/v1/docs | Auto-generated OpenAPI / Swagger UI |

**Demo account:** `demo@example.com` / `Demo123!` (Free plan, 20 credits).

---

## API

All endpoints are under `/api/v1`. Request/response envelope:

```json
// Success
{ "success": true, "data": { ... } }

// Failure
{
  "success": false,
  "error": {
    "code": "FILE_TOO_LARGE",
    "message": "Image exceeds the 5 MB limit for this upload.",
    "details": { "max_bytes": 5242880 }
  }
}
```

| Method | Path | Auth | Notes |
|---|---|---|---|
| `POST` | `/auth/register` | – | Free plan, returns `{user, access_token}` |
| `POST` | `/auth/login` | – | Returns `{user, access_token}` |
| `GET` | `/auth/me` | JWT | Current user with plan info |
| `POST` | `/images` | JWT or API key | `multipart` (`file`) **or** form-data (`image` = base64 / data URI) |
| `GET` | `/images` | JWT or API key | Paginated, excludes soft-deleted |
| `GET` | `/images/{id}` | JWT or API key | One image metadata |
| `DELETE` | `/images/{id}` | JWT | Soft delete + `usage_event` audit |
| `POST` | `/anonymous/images` | – | IP rate-limited (default 10/day) |
| `POST` | `/api-keys` | JWT | Returns `secret` once — save immediately |
| `GET` | `/api-keys` | JWT | List without secrets |
| `DELETE` | `/api-keys/{id}` | JWT | Revoke |
| `GET` | `/usage` | JWT | Aggregated counters by event type |
| `GET` | `/plans` | – | Public pricing table |
| `POST` | `/payments/upgrade` | JWT | Mock — marks payment completed, sets new plan + grants credits |
| `POST` | `/payments/topup` | JWT | Mock — body `{amount_credits, amount_vnd}` |
| `GET` | `/payments` | JWT | List user payments |
| `GET` | `/i/{s1}/{s2}/{key}.{ext}` | – | **Public** image serving (nginx-first, API-fallback) |

### Examples

Upload by curl with JWT:

```bash
curl -X POST http://localhost/api/v1/images \
  -H "Authorization: Bearer sk_live_..." \
  -F "file=@image.png"
```

Upload via Base64:

```bash
curl -X POST http://localhost/api/v1/images \
  -H "Authorization: Bearer sk_live_..." \
  -F "image=data:image/png;base64,iVBOR..."
```

---

## Database

7 tables created in [`api/alembic/versions/0001_initial.py`](./api/alembic/versions/0001_initial.py). MySQL schema follows Baokim conventions:

- `snake_case`, plural table names ≤ 24 chars
- `DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP` for `created`/`modified`
- `BIGINT UNSIGNED` for money columns with explicit comment "đơn vị xu"
- `utf8mb4_unicode_ci` on string columns
- Index names: `idx_<cols>`, `uk_<cols>`, `fk_<tbl>_<cols>`
- Vietnamese comments on every column; `tinyint` columns include a list of allowed values

Tables: `plans`, `users`, `upload_credit_transactions`, `payments`, `api_keys`, `images`, `usage_events`.

Migration commands:

```bash
make migrate    # alembic upgrade head
make seed       # python -m app.seed (idempotent)
```

---

## Storage layout

Files live under the volume-mounted directory (default `/data/uploads`) in a 2-level sharded layout to keep any single directory from accumulating millions of files:

```
/data/uploads/ab/cd/abcdef123...xyz.png
                └─┬─┘└┬┘└────────┬────────┘
                  │   │       storage_key (secrets.token_urlsafe(16))
                  │   └── shard2 (key[2:4])
                  └── shard1 (key[:2])
```

The public URL mirrors the disk path so nginx can serve the file directly without any application hop:

```
http://localhost/i/ab/cd/abcdef123...xyz.png
```

`/i/*` is served by nginx from the same shared volume (`storage_data`). The FastAPI `routers/public_serve.py` is a fallback for running the API standalone.

---

## Cleanup worker

The `worker` container runs [`cleanup_runner.py`](./worker/app/tasks/cleanup_runner.py) on an APScheduler trigger (default every 60 minutes). Each pass:

1. Selects up to `WORKER_BATCH_SIZE` (default 100) image rows where `expires_at <= NOW()` and `deleted_at IS NULL`.
2. Soft-deletes them in bulk (`deleted_at = NOW()`).
3. Inserts a `usage_events` row per image (event_type `IMAGE_EXPIRED`).
4. Deletes the corresponding files from disk.

Test it:

```bash
# Mark every image of demo user as already past expiry
docker compose exec mysql mysql -uimageurl -p$MYSQL_PASSWORD imageurl \
  -e "UPDATE images SET expires_at = NOW() - INTERVAL 1 DAY WHERE deleted_at IS NULL;"

# Tail the worker logs
docker compose logs -f worker
```

---

## Security notes

Implemented in the MVP:

- `storage_key` is `secrets.token_urlsafe(16)`; the `/i/...` route validates the regex `^[A-Za-z0-9_-]{16,32}$` plus the shard prefix matches the key itself.
- Original filename is **never** used to build disk paths; the extension in the URL comes from magic bytes, not the client.
- Pillow validates `Image.verify()` and re-loads. Pixel-bomb check (`width × height ≤ MAX_PIXELS`, default 50M) happens before decoding the pixel buffer.
- EXIF/GPS metadata stripped on save (RGB conversion + re-encode).
- API secrets are stored only as `bcrypt(secret)`; the plaintext is returned to the client **once** at creation.
- Credit consumption uses `SELECT … FOR UPDATE` to avoid race conditions in concurrent uploads.
- Anonymous uploads are IP rate-limited (slowapi in-memory, default 10/day/IP).
- Login failures, file-too-large, validation errors and quota-exceeded return the consistent envelope.
- Public image responses carry `X-Content-Type-Options: nosniff` and `Cache-Control: public, max-age=31536000, immutable`.
- Application logs do not log Base64 payloads, passwords, or full API keys.

Deferred (per `PLAN.md`):

- Virus / malware scanning (interface placeholder only).
- Image transformation (`?w=800&format=webp`) — Phase 3.
- Real payment integration — Phase 2 (currently a mock provider).
- Admin dashboard — Phase 2.

---

## Useful commands

```bash
make help               # list all targets
make up                 # docker compose up -d --build
make down               # docker compose down
make logs               # tail all logs
make shell-api          # bash inside api
make exec-api CMD="..." # run arbitrary command in api container
make migrate            # alembic upgrade head
make seed               # run idempotent seed
make e2e                # end-to-end smoke test
make reset              # nuke volumes and rebuild from scratch
```

---

## Out of scope (this MVP)

Following `PLAN.md` §28, the MVP deliberately does **not** include:

- Social features, image editor, AI generation
- Video hosting, mobile app
- Real Stripe integration (we ship a mock provider)
- Image transformations (resize/crop/WebP/AVIF)
- Admin dashboard UI
- OAuth login
- Refresh tokens

These are tracked as Phase 2/3/4 in the plan.