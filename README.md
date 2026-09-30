# QuickDrop

Temporary private file sharing on Cloudflare.

Uploaders sign in. Downloaders use a link. Files expire automatically or after their first download. The R2 bucket stays private.

## Stack

- Frontend: React + Vite + TypeScript
- Backend: Python 3.13 + FastAPI on Cloudflare Python Workers
- Database: Cloudflare D1
- Storage: Cloudflare R2
- Cleanup: Cloudflare Cron (`0 * * * *`)
- Auth: Google OIDC, plus a local dev login
- Tools: `uv` + `pywrangler`

The Worker entrypoint is:

```python
Default = asgi.entrypoint(app)
```

Bindings are read from `request.scope["env"]`.

## Limits

- 500 MiB active storage per user
- 500 MiB max per file
- Expiry: 1h, 6h, 24h, 3d, 7d (default 24h)

## Local development

Install:

```bash
# Python toolchain
uv sync

# Frontend
npm --prefix frontend install
```

Copy secrets:

```bash
cp .dev.vars.example .dev.vars
```

Apply D1 migrations and start the Worker:

```bash
uv run pywrangler d1 migrations apply DB --local --env development
npm --prefix frontend run build
uv run pywrangler dev --env development
```

The Worker serves `/api/*` and the built frontend on `http://localhost:8787`.

Optional frontend-only Vite server with API proxy:

```bash
uv run pywrangler dev --env development
npm --prefix frontend run dev
```

### Local auth

If `GOOGLE_CLIENT_ID` is empty, `/api/auth/google` redirects to `/api/dev/login` in development. That creates a `dev` identity (`provider=dev`, `provider_subject=local-dev-user`) and sets an HttpOnly session cookie.

### Local R2

Wrangler simulates R2 locally. `/api/uploads/init` returns `/api/dev/uploads/{id}` so the browser can PUT the file through the Worker. This path is development-only and capped at 10 MiB.

Production uses short-lived signed PUT URLs so the browser uploads directly to R2.

### Local Google OAuth

Set in `.dev.vars`:

```bash
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
APP_ORIGIN=http://localhost:8787
```

Authorized redirect URI:

```text
http://localhost:8787/api/auth/google/callback
```

## Production upload flow

1. Browser `POST /api/uploads/init`
2. Worker checks auth and quota, creates a `PENDING` row, reserves quota
3. Worker returns a signed R2 PUT URL
4. Browser uploads directly to R2
5. Browser `POST /api/uploads/{id}/complete`
6. Worker HEADs the R2 object, validates its actual size and current quota, then marks it `ACTIVE` and moves reserved quota to used quota atomically

Share links store SHA-256 hashes of cryptographically random tokens. Downloads validate the token, file status, and expiry, then redirect to a short-lived signed GET URL. For one-time links, the token is consumed atomically when the first download starts and the object is reclaimed by Cron after the signed URL expires.

## Cron

Hourly the Worker:

- deletes expired R2 objects
- marks files `EXPIRED`
- reclaims used quota
- fails stale `PENDING` uploads
- releases abandoned reservations
- deletes expired sessions

Test it locally after the Worker starts:

```bash
curl "http://localhost:8787/cdn-cgi/local/scheduled?format=json"
```

## Deploy

Create D1 and R2 resources, then replace the placeholder D1 IDs in both the top-level and `env.production` bindings in `wrangler.jsonc`.

```bash
npx wrangler d1 create quickdrop
npx wrangler r2 bucket create quickdrop-files
uv run pywrangler d1 migrations apply DB --remote --env production
npm --prefix frontend run build
# Fill the git-ignored .env.production.local file, then upload it once:
npx wrangler secret bulk .env.production.local --env production
uv run pywrangler deploy --env production
```

`APP_ORIGIN`, `R2_ACCOUNT_ID`, and `R2_BUCKET_NAME` are non-secret production
variables configured in `wrangler.jsonc`.

Use an R2 API token only for signing. Do not make the bucket public. The R2 Worker binding is named `FILES`.

Copy `r2-cors.example.json`, replace `https://your-domain.example` with the exact production origin (no path or wildcard), then apply and verify it:

```bash
cp r2-cors.example.json r2-cors.json
npx wrangler r2 bucket cors set quickdrop-files --file r2-cors.json
npx wrangler r2 bucket cors list quickdrop-files
```

The policy permits only browser `PUT` uploads with `Content-Type`; signed downloads are normal top-level navigations and do not need permissive bucket CORS.

## Tests

```bash
uv run pytest
```

## Schema

Provider-neutral auth:

- `users`
- `auth_identities` (`user_id`, `provider`, `provider_subject`, `provider_email`)
- `sessions`
- `files`

Google OIDC `sub` is stored as `provider_subject`. There is no `google_id` column on `users`.
