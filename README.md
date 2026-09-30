<div align="center">

# QuickDrop

Private, temporary file sharing built entirely on Cloudflare.

Upload directly to R2, share an expiring link, and optionally make it disappear after the first download starts.

**[Open QuickDrop](https://quickdrop-production.hrithikmallick-work.workers.dev/login)** · [Technical documentation](docs/TECHNICAL_DOCUMENTATION.md)

</div>

## Features

- Google sign-in for uploaders
- Public downloads without an account
- Drag-and-drop or file-picker uploads
- Direct browser-to-R2 production uploads with progress
- Private R2 bucket and server-generated object keys
- Expiry choices: 1 hour, 6 hours, 24 hours, 3 days, or 7 days
- Optional one-time share links
- 500 MiB per-user quota and 500 MiB single-file limit
- Automatic R2 cleanup and quota reclamation through Cron
- Responsive login, dashboard, and public download pages

## Architecture

```text
React + Vite + TypeScript
            │
            ▼
FastAPI on a Cloudflare Python Worker
       │                    │
       ▼                    ▼
 D1 metadata          Private R2 files
       │
       ▼
 Hourly cleanup Cron
```

| Component | Technology |
| --- | --- |
| Frontend | React 19, Vite 6, TypeScript |
| Backend | Python 3.13, FastAPI, Cloudflare Workers |
| Metadata | Cloudflare D1 |
| File storage | Cloudflare R2 |
| Authentication | Google OAuth/OIDC |
| Cleanup | Cloudflare Cron Trigger |

The Worker entrypoint is intentionally small:

```python
from app import app
from workers import asgi

Default = asgi.entrypoint(app)
```

Cloudflare bindings are available to FastAPI through `request.scope["env"]`.

## How uploads work

1. The browser calls `POST /api/uploads/init`.
2. The Worker authenticates the user and reserves quota in D1.
3. A `PENDING` file record is created with a server-generated R2 key.
4. The Worker returns a 15-minute signed R2 PUT URL.
5. The browser uploads the file directly to R2.
6. The browser calls `POST /api/uploads/{id}/complete`.
7. The Worker checks the real R2 object size with `HEAD` and marks the file `ACTIVE`.

The production Worker never proxies the 500 MiB upload body.

## One-time downloads

Selecting **Expire after first download** makes the public share token single-use. The metadata page does not consume it; the token is consumed atomically when the recipient starts the download.

The first request receives an R2 URL valid for at most 60 seconds. Later share-link requests are rejected, and Cron removes the object and reclaims quota after the grace period becomes eligible for cleanup.

## Project structure

```text
frontend/                 React application
  src/pages/              Login, dashboard, and download pages
  src/components/         Shared UI components
  src/api.ts              Typed API client and upload progress
migrations/               Ordered D1 migrations
src/app.py                FastAPI routes and application logic
src/cleanup.py            Expiration and stale-upload cleanup
src/constants.py          Limits, TTLs, and file states
src/db.py                 D1 helpers
src/r2util.py             R2 operations and signed URLs
src/worker.py             Worker and scheduled-event entrypoint
tests/                    Backend unit tests and Cloudflare fakes
wrangler.jsonc            Worker resources and environments
```

See [Technical Documentation](docs/TECHNICAL_DOCUMENTATION.md) for the full schema, API reference, state machine, security model, and operations guide.

## Local development

### Prerequisites

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- Node.js and npm
- A Cloudflare/Wrangler-compatible environment

### Install dependencies

```bash
uv sync
npm --prefix frontend install
```

### Create local variables

Bash:

```bash
cp .dev.vars.example .dev.vars
```

PowerShell:

```powershell
Copy-Item .dev.vars.example .dev.vars
```

For the built-in local development identity, leave the Google fields empty. The development login creates a provider-neutral `dev` identity and an HttpOnly session.

### Apply migrations, build, and run

```bash
uv run pywrangler d1 migrations apply DB --local --env development
npm --prefix frontend run build
uv run pywrangler dev --env development
```

Open `http://localhost:8787`.

On Unix-like systems, the convenience script performs those steps:

```bash
./start.sh
```

### Optional Vite development server

Run the Worker and frontend in separate terminals:

```bash
uv run pywrangler dev --env development
npm run dev:web
```

Vite runs on `http://localhost:5173` and proxies `/api` to the Worker on port 8787.

### Local Google OAuth

Add credentials to `.dev.vars`:

```dotenv
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
APP_ORIGIN=http://localhost:8787
```

Configure this Google authorized redirect URI:

```text
http://localhost:8787/api/auth/google/callback
```

### Local R2 behavior

When R2 signing credentials are blank in development, uploads use `/api/dev/uploads/{id}` and the local R2 binding. This fallback is capped at 10 MiB. Production requires signed direct uploads.

## Configuration

### Worker bindings

| Binding | Resource |
| --- | --- |
| `DB` | D1 database named `quickdrop` |
| `FILES` | Private R2 bucket named `quickdrop-files` |
| `ASSETS` | Compiled files from `frontend/dist` |

### Required production values

Non-secret variables in `wrangler.jsonc`:

- `ENVIRONMENT`
- `APP_ORIGIN`
- `R2_ACCOUNT_ID`
- `R2_BUCKET_NAME`

Worker secrets:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

Never commit `.dev.vars`, `.env.production.local`, or R2 credentials.

## R2 CORS

Copy `r2-cors.example.json` to the ignored `r2-cors.json`, replace the placeholder with the exact application origin, then apply it:

```bash
npx wrangler r2 bucket cors set quickdrop-files --file r2-cors.json
npx wrangler r2 bucket cors list quickdrop-files
```

The policy permits only browser PUT uploads with `Content-Type`. Keep the bucket private.

## Tests

```bash
# Backend tests
npm test

# TypeScript check and production frontend build
npm run build:web

# Production Worker packaging check
npx wrangler deploy --env production --dry-run
```

The backend suite covers quota boundaries, token generation and hashing, filename sanitization, signed R2 URLs, cleanup, stale uploads, and atomic one-time download claims.

## Deployment

After creating the D1 database and R2 bucket and configuring `wrangler.jsonc`:

```bash
# Apply schema first
npx wrangler d1 migrations apply DB --remote --env production

# Build the React application
npm run build:web

# Upload secrets from the Git-ignored local file
npx wrangler secret bulk .env.production.local --env production

# Validate and deploy
npx wrangler deploy --env production --dry-run
npx wrangler deploy --env production
```

Verify the release:

```bash
curl https://quickdrop-production.hrithikmallick-work.workers.dev/api/health
npx wrangler secret list --env production
npx wrangler d1 migrations list DB --remote --env production
```

Detailed resource setup, Windows Python packaging, secret rotation, post-deployment checks, and troubleshooting are documented in the [deployment and operations guide](docs/TECHNICAL_DOCUMENTATION.md#18-production-deployment).

## Security notes

- Session and share-token plaintext values are never stored in D1.
- Owner-only operations include the authenticated user ID in their database query.
- SQL uses bound parameters.
- Filenames are sanitized and never become R2 object paths.
- The Worker verifies the actual uploaded object size instead of trusting the browser.
- Signed URLs are short-lived and R2 credentials never reach frontend code.

Review the documented [known limitations and future hardening](docs/TECHNICAL_DOCUMENTATION.md#21-known-limitations-and-future-hardening) before expanding beyond the current deployment.

## Documentation

- [Full technical documentation](docs/TECHNICAL_DOCUMENTATION.md)
- [Live application](https://quickdrop-production.hrithikmallick-work.workers.dev/login)
- [Health endpoint](https://quickdrop-production.hrithikmallick-work.workers.dev/api/health)

