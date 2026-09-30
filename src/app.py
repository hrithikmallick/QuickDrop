import base64
import json
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

from constants import (
    DEFAULT_EXPIRY,
    EXPIRY_SECONDS,
    LOCAL_UPLOAD_MAX_BYTES,
    MAX_FILE_BYTES,
    OAUTH_STATE_COOKIE,
    ONE_TIME_GET_TTL_SECONDS,
    QUOTA_BYTES,
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    SIGNED_GET_TTL_SECONDS,
    SIGNED_PUT_TTL_SECONDS,
    STATUS_ACTIVE,
    STATUS_DELETED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
)
from db import batch, changes, execute, query_all, query_first
from r2util import (
    has_r2_signing_credentials,
    object_size,
    r2_delete,
    r2_head,
    r2_put,
    signed_get_url,
    signed_put_url,
)
from util import (
    content_disposition,
    env_str,
    get_cookie,
    hash_token,
    is_development,
    new_id,
    now_ts,
    random_token,
    sanitize_filename,
)

app = FastAPI(title="QuickDrop")


class UploadInitBody(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str | None = None
    size_bytes: int = Field(gt=0)
    expiry: str = DEFAULT_EXPIRY
    delete_after_download: bool = False


class ShareBody(BaseModel):
    expiry: str | None = None


def get_env(request: Request):
    return request.scope["env"]


def public_origin(request: Request, env) -> str:
    configured = env_str(env, "APP_ORIGIN")
    if configured:
        return configured.rstrip("/")
    return str(request.base_url).rstrip("/")


def set_auth_cookie(response: Response, name: str, value: str, env, request, max_age: int) -> None:
    from util import cookie_secure

    secure = cookie_secure(env, request)
    if max_age <= 0:
        response.delete_cookie(key=name, path="/", httponly=True, secure=secure, samesite="lax")
        return
    response.set_cookie(
        key=name,
        value=value,
        max_age=max_age,
        path="/",
        httponly=True,
        secure=secure,
        samesite="lax",
    )


async def load_session_user(env, token: str | None):
    if not token:
        return None
    row = await query_first(
        env,
        """
        SELECT u.id, u.email, u.display_name, u.storage_used_bytes, u.storage_reserved_bytes,
               s.expires_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = ?
        """,
        hash_token(token),
    )
    if not row:
        return None
    if int(row["expires_at"]) <= now_ts():
        return None
    return row


async def require_user(request: Request):
    env = get_env(request)
    token = get_cookie(request, SESSION_COOKIE)
    user = await load_session_user(env, token)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def expiry_seconds(value: str | None) -> int:
    key = value or DEFAULT_EXPIRY
    if key not in EXPIRY_SECONDS:
        raise HTTPException(status_code=400, detail="Invalid expiry option")
    return EXPIRY_SECONDS[key]


def file_public(row: dict, include_share: bool = False) -> dict:
    payload = {
        "id": row["id"],
        "filename": row["original_filename"],
        "content_type": row.get("content_type"),
        "size_bytes": int(row["size_bytes"] or 0),
        "status": row["status"],
        "expires_at": row.get("expires_at"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "has_share": bool(row.get("share_token_hash")),
        "delete_after_download": bool(row.get("delete_after_download")),
    }
    if include_share:
        payload["share_url"] = None
    return payload


async def fail_pending_upload(env, file_id: str, user_id: str, size_bytes: int, now: int) -> bool:
    results = await batch(
        env,
        [
            (
                "UPDATE files SET status = ?, updated_at = ? "
                "WHERE id = ? AND user_id = ? AND status = ?",
                (STATUS_FAILED, now, file_id, user_id, STATUS_PENDING),
            ),
            (
                "UPDATE users SET storage_reserved_bytes = MAX(0, storage_reserved_bytes - ?), "
                "updated_at = ? WHERE id = ? AND changes() = 1",
                (size_bytes, now, user_id),
            ),
        ],
    )
    return changes(results[0]) == 1


async def claim_one_time_download(env, row: dict, token_hash: str, now: int, ttl: int) -> bool:
    if not row.get("delete_after_download"):
        return True
    result = await execute(
        env,
        """
        UPDATE files
        SET expires_at = ?, share_token_hash = NULL, updated_at = ?
        WHERE id = ? AND status = ? AND share_token_hash = ?
          AND (expires_at IS NULL OR expires_at > ?)
        """,
        now + ttl,
        now,
        row["id"],
        STATUS_ACTIVE,
        token_hash,
        now,
    )
    return changes(result) == 1


async def create_session(env, user_id: str) -> str:
    token = random_token(32)
    now = now_ts()
    await execute(
        env,
        """
        INSERT INTO sessions (id, user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        new_id(),
        user_id,
        hash_token(token),
        now + SESSION_TTL_SECONDS,
        now,
    )
    return token


async def upsert_identity(env, provider: str, subject: str, email: str | None, name: str | None):
    now = now_ts()
    identity = await query_first(
        env,
        """
        SELECT id, user_id FROM auth_identities
        WHERE provider = ? AND provider_subject = ?
        """,
        provider,
        subject,
    )
    if identity:
        await execute(
            env,
            """
            UPDATE auth_identities SET provider_email = ? WHERE id = ?
            """,
            email,
            identity["id"],
        )
        if email or name:
            await execute(
                env,
                """
                UPDATE users
                SET email = COALESCE(?, email),
                    display_name = COALESCE(?, display_name),
                    updated_at = ?
                WHERE id = ?
                """,
                email,
                name,
                now,
                identity["user_id"],
            )
        return identity["user_id"]

    user_id = new_id()
    await batch(
        env,
        [
            (
                """
                INSERT INTO users (id, email, display_name, storage_used_bytes, storage_reserved_bytes, created_at, updated_at)
                VALUES (?, ?, ?, 0, 0, ?, ?)
                """,
                (user_id, email, name, now, now),
            ),
            (
                """
                INSERT INTO auth_identities (id, user_id, provider, provider_subject, provider_email, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, provider_subject) DO NOTHING
                """,
                (new_id(), user_id, provider, subject, email, now),
            ),
            (
                "DELETE FROM users WHERE id = ? AND changes() = 0",
                (user_id,),
            ),
        ],
    )
    identity = await query_first(
        env,
        "SELECT user_id FROM auth_identities WHERE provider = ? AND provider_subject = ?",
        provider,
        subject,
    )
    return identity["user_id"]


@app.get("/api/health")
async def health(request: Request):
    env = get_env(request)
    return {
        "ok": True,
        "service": "quickdrop",
        "environment": env_str(env, "ENVIRONMENT", "development"),
    }


@app.get("/api/auth/google")
async def auth_google(request: Request):
    env = get_env(request)
    client_id = env_str(env, "GOOGLE_CLIENT_ID")
    if not client_id:
        if is_development(env):
            return RedirectResponse(url="/api/dev/login", status_code=302)
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    state = random_token(24)
    redirect_uri = f"{public_origin(request, env)}/api/auth/google/callback"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    response = RedirectResponse(url=url, status_code=302)
    set_auth_cookie(response, OAUTH_STATE_COOKIE, state, env, request, 600)
    return response


@app.get("/api/auth/google/callback")
async def auth_google_callback(request: Request, code: str | None = None, state: str | None = None):
    env = get_env(request)
    client_id = env_str(env, "GOOGLE_CLIENT_ID")
    client_secret = env_str(env, "GOOGLE_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured")
    expected = get_cookie(request, OAUTH_STATE_COOKIE)
    if not code or not state or not expected or state != expected:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    redirect_uri = f"{public_origin(request, env)}/api/auth/google/callback"
    token_resp = await fetch_json(
        "https://oauth2.googleapis.com/token",
        method="POST",
        headers={"content-type": "application/x-www-form-urlencoded"},
        body=urlencode(
            {
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        ),
    )
    id_token = token_resp.get("id_token")
    if not id_token:
        raise HTTPException(status_code=400, detail="Missing id_token")
    claims = id_token_claims(id_token)
    try:
        token_expires_at = int(claims.get("exp", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid identity token")
    if (
        claims.get("aud") != client_id
        or claims.get("iss") not in ("https://accounts.google.com", "accounts.google.com")
        or not claims.get("sub")
        or token_expires_at <= now_ts()
    ):
        raise HTTPException(status_code=400, detail="Invalid identity token")
    user_id = await upsert_identity(
        env,
        "google",
        claims["sub"],
        claims.get("email"),
        claims.get("name"),
    )
    session_token = await create_session(env, user_id)
    response = RedirectResponse(url="/", status_code=302)
    set_auth_cookie(response, SESSION_COOKIE, session_token, env, request, SESSION_TTL_SECONDS)
    set_auth_cookie(response, OAUTH_STATE_COOKIE, "", env, request, 0)
    return response


@app.get("/api/dev/login")
async def dev_login(request: Request):
    env = get_env(request)
    if not is_development(env):
        raise HTTPException(status_code=404, detail="Not found")
    user_id = await upsert_identity(
        env,
        "dev",
        "local-dev-user",
        "dev@localhost",
        "Local Dev",
    )
    session_token = await create_session(env, user_id)
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        response = JSONResponse({"ok": True, "user_id": user_id})
    else:
        response = RedirectResponse(url="/", status_code=302)
    set_auth_cookie(response, SESSION_COOKIE, session_token, env, request, SESSION_TTL_SECONDS)
    return response


@app.post("/api/auth/logout")
async def logout(request: Request):
    env = get_env(request)
    token = get_cookie(request, SESSION_COOKIE)
    if token:
        await execute(env, "DELETE FROM sessions WHERE token_hash = ?", hash_token(token))
    response = JSONResponse({"ok": True})
    set_auth_cookie(response, SESSION_COOKIE, "", env, request, 0)
    return response


@app.get("/api/me")
async def me(request: Request):
    user = await require_user(request)
    used = int(user["storage_used_bytes"] or 0)
    reserved = int(user["storage_reserved_bytes"] or 0)
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "storage_used_bytes": used,
        "storage_reserved_bytes": reserved,
        "storage_limit_bytes": QUOTA_BYTES,
        "storage_available_bytes": max(0, QUOTA_BYTES - used - reserved),
    }


@app.get("/api/files")
async def list_files(request: Request):
    env = get_env(request)
    user = await require_user(request)
    rows = await query_all(
        env,
        """
        SELECT id, original_filename, content_type, size_bytes, status, expires_at,
               share_token_hash, delete_after_download, created_at, updated_at
        FROM files
        WHERE user_id = ? AND status IN (?, ?)
        ORDER BY created_at DESC
        """,
        user["id"],
        STATUS_ACTIVE,
        STATUS_PENDING,
    )
    return {"files": [file_public(row) for row in rows]}


@app.delete("/api/files/{file_id}")
async def delete_file(file_id: str, request: Request):
    env = get_env(request)
    user = await require_user(request)
    row = await query_first(
        env,
        "SELECT * FROM files WHERE id = ? AND user_id = ?",
        file_id,
        user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if row["status"] in (STATUS_DELETED, STATUS_EXPIRED, STATUS_FAILED):
        return {"ok": True}
    now = now_ts()
    results = await batch(
        env,
        [
            (
                """
                UPDATE users
                SET storage_used_bytes = MAX(0, storage_used_bytes - COALESCE((
                        SELECT size_bytes FROM files WHERE id = ? AND user_id = ? AND status = ?
                    ), 0)),
                    storage_reserved_bytes = MAX(0, storage_reserved_bytes - COALESCE((
                        SELECT size_bytes FROM files WHERE id = ? AND user_id = ? AND status = ?
                    ), 0)),
                    updated_at = ?
                WHERE id = ? AND EXISTS (
                    SELECT 1 FROM files WHERE id = ? AND user_id = ? AND status IN (?, ?)
                )
                """,
                (
                    file_id, user["id"], STATUS_ACTIVE,
                    file_id, user["id"], STATUS_PENDING,
                    now, user["id"], file_id, user["id"], STATUS_ACTIVE, STATUS_PENDING,
                ),
            ),
            (
                """
                UPDATE files SET status = ?, share_token_hash = NULL, updated_at = ?
                WHERE id = ? AND user_id = ? AND status IN (?, ?) AND changes() = 1
                """,
                (STATUS_DELETED, now, file_id, user["id"], STATUS_ACTIVE, STATUS_PENDING),
            ),
        ],
    )
    if changes(results[1]) == 1:
        try:
            await r2_delete(env, row["r2_key"])
        except Exception:
            pass
    return {"ok": True}


@app.post("/api/uploads/init")
async def uploads_init(body: UploadInitBody, request: Request):
    env = get_env(request)
    user = await require_user(request)
    if body.size_bytes > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 500 MiB limit")
    ttl = expiry_seconds(body.expiry)
    now = now_ts()
    file_id = new_id()
    r2_key = f"uploads/{user['id']}/{file_id}/{random_token(12)}"
    results = await batch(
        env,
        [
            (
                """
                UPDATE users SET storage_reserved_bytes = storage_reserved_bytes + ?, updated_at = ?
                WHERE id = ? AND storage_used_bytes + storage_reserved_bytes + ? <= ?
                """,
                (body.size_bytes, now, user["id"], body.size_bytes, QUOTA_BYTES),
            ),
            (
                """
                INSERT INTO files (
                    id, user_id, original_filename, content_type, size_bytes, r2_key,
                    status, expires_at, share_token_hash, created_at, updated_at, completed_at,
                    delete_after_download
                ) SELECT ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, ? WHERE changes() = 1
                """,
                (
                    file_id, user["id"], sanitize_filename(body.filename), body.content_type,
                    body.size_bytes, r2_key, STATUS_PENDING, now + ttl, now, now,
                    int(body.delete_after_download),
                ),
            ),
        ],
    )
    if changes(results[0]) != 1:
        raise HTTPException(status_code=403, detail="Storage quota exceeded")
    upload_mode = "signed"
    upload_url = None
    required_headers = {}
    if has_r2_signing_credentials(env):
        try:
            upload_url = signed_put_url(env, r2_key, body.content_type)
        except Exception:
            await fail_pending_upload(env, file_id, user["id"], body.size_bytes, now)
            raise HTTPException(status_code=503, detail="Signed uploads are not configured")
        if body.content_type:
            required_headers["Content-Type"] = body.content_type
    elif is_development(env):
        upload_mode = "local"
        upload_url = f"/api/dev/uploads/{file_id}"
    else:
        await fail_pending_upload(env, file_id, user["id"], body.size_bytes, now)
        raise HTTPException(status_code=503, detail="Signed uploads are not configured")
    return {
        "id": file_id,
        "upload_url": upload_url,
        "upload_mode": upload_mode,
        "headers": required_headers,
        "expires_in": SIGNED_PUT_TTL_SECONDS,
        "r2_key": None,
    }


@app.put("/api/dev/uploads/{file_id}")
async def dev_upload(file_id: str, request: Request):
    env = get_env(request)
    if not is_development(env):
        raise HTTPException(status_code=404, detail="Not found")
    user = await require_user(request)
    row = await query_first(
        env,
        "SELECT * FROM files WHERE id = ? AND user_id = ?",
        file_id,
        user["id"],
    )
    if not row or row["status"] != STATUS_PENDING:
        raise HTTPException(status_code=404, detail="Upload not found")
    body = await request.body()
    if len(body) > LOCAL_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="Local upload exceeds 10 MiB test limit")
    await r2_put(env, row["r2_key"], body, row.get("content_type"))
    return {"ok": True, "size_bytes": len(body)}


@app.post("/api/uploads/{file_id}/complete")
async def uploads_complete(file_id: str, request: Request):
    env = get_env(request)
    user = await require_user(request)
    row = await query_first(
        env,
        "SELECT * FROM files WHERE id = ? AND user_id = ?",
        file_id,
        user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if row["status"] == STATUS_ACTIVE:
        return file_public(row)
    if row["status"] != STATUS_PENDING:
        raise HTTPException(status_code=409, detail="Upload is not pending")
    obj = await r2_head(env, row["r2_key"])
    actual = object_size(obj)
    now = now_ts()
    declared = int(row["size_bytes"] or 0)
    if actual is None:
        await fail_pending_upload(env, file_id, user["id"], declared, now)
        raise HTTPException(status_code=400, detail="Uploaded object was not found")
    if actual > MAX_FILE_BYTES:
        if await fail_pending_upload(env, file_id, user["id"], declared, now):
            await r2_delete(env, row["r2_key"])
        raise HTTPException(status_code=400, detail="Uploaded object exceeds size limit")
    results = await batch(
        env,
        [
            (
                """
                UPDATE files
                SET status = ?, size_bytes = ?, updated_at = ?, completed_at = ?
                WHERE id = ? AND user_id = ? AND status = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                  AND EXISTS (
                    SELECT 1 FROM users
                    WHERE id = ? AND storage_used_bytes + storage_reserved_bytes - ? + ? <= ?
                  )
                """,
                (
                    STATUS_ACTIVE, actual, now, now, file_id, user["id"], STATUS_PENDING,
                    now, user["id"], declared, actual, QUOTA_BYTES,
                ),
            ),
            (
                """
                UPDATE users
                SET storage_reserved_bytes = MAX(0, storage_reserved_bytes - ?),
                    storage_used_bytes = storage_used_bytes + ?, updated_at = ?
                WHERE id = ? AND changes() = 1
                """,
                (declared, actual, now, user["id"]),
            ),
        ],
    )
    if changes(results[0]) == 1:
        updated = await query_first(env, "SELECT * FROM files WHERE id = ?", file_id)
        return file_public(updated)

    current = await query_first(
        env, "SELECT * FROM files WHERE id = ? AND user_id = ?", file_id, user["id"]
    )
    if current and current["status"] == STATUS_ACTIVE:
        return file_public(current)
    if current and current["status"] == STATUS_PENDING:
        expired = current.get("expires_at") and int(current["expires_at"]) <= now
        if await fail_pending_upload(env, file_id, user["id"], declared, now):
            await r2_delete(env, row["r2_key"])
        if expired:
            raise HTTPException(status_code=410, detail="Upload has expired")
        raise HTTPException(status_code=403, detail="Storage quota exceeded")
    raise HTTPException(status_code=409, detail="Upload is not pending")


@app.post("/api/files/{file_id}/share")
async def share_file(file_id: str, request: Request, body: ShareBody | None = None):
    env = get_env(request)
    user = await require_user(request)
    row = await query_first(
        env,
        "SELECT * FROM files WHERE id = ? AND user_id = ?",
        file_id,
        user["id"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
    if row["status"] != STATUS_ACTIVE:
        raise HTTPException(status_code=409, detail="File is not available to share")
    now = now_ts()
    expires_at = row.get("expires_at")
    if expires_at and int(expires_at) <= now:
        raise HTTPException(status_code=410, detail="File has expired")
    payload = body or ShareBody()
    if payload.expiry:
        ttl = expiry_seconds(payload.expiry)
        expires_at = now + ttl
        await execute(
            env,
            "UPDATE files SET expires_at = ?, updated_at = ? WHERE id = ?",
            expires_at,
            now,
            file_id,
        )
    token = random_token(32)
    await execute(
        env,
        "UPDATE files SET share_token_hash = ?, updated_at = ? WHERE id = ?",
        hash_token(token),
        now,
        file_id,
    )
    origin = public_origin(request, env)
    return {
        "share_url": f"{origin}/d/{token}",
        "expires_at": expires_at,
    }


@app.get("/api/d/{share_token}")
async def public_download_meta(share_token: str, request: Request):
    env = get_env(request)
    row = await query_first(
        env,
        "SELECT * FROM files WHERE share_token_hash = ?",
        hash_token(share_token),
    )
    if not row or row["status"] != STATUS_ACTIVE:
        raise HTTPException(status_code=404, detail="Link not found")
    expires_at = row.get("expires_at")
    if expires_at and int(expires_at) <= now_ts():
        raise HTTPException(status_code=410, detail="This file has expired")
    one_time = bool(row.get("delete_after_download"))
    return {
        "filename": row["original_filename"],
        "content_type": row.get("content_type"),
        "size_bytes": int(row["size_bytes"] or 0),
        "expires_at": expires_at,
        "download_url": f"/api/d/{share_token}/download",
        "download_mode": "one-time" if one_time else "signed",
        "expires_in": ONE_TIME_GET_TTL_SECONDS if one_time else SIGNED_GET_TTL_SECONDS,
        "delete_after_download": one_time,
    }


@app.get("/api/d/{share_token}/download")
@app.get("/api/d/{share_token}/content")
async def public_download_content(share_token: str, request: Request):
    env = get_env(request)
    token_hash = hash_token(share_token)
    row = await query_first(
        env,
        "SELECT * FROM files WHERE share_token_hash = ?",
        token_hash,
    )
    if not row or row["status"] != STATUS_ACTIVE:
        raise HTTPException(status_code=404, detail="Link not found")
    now = now_ts()
    expires_at = row.get("expires_at")
    if expires_at and int(expires_at) <= now:
        raise HTTPException(status_code=410, detail="This file has expired")
    ttl = ONE_TIME_GET_TTL_SECONDS if row.get("delete_after_download") else SIGNED_GET_TTL_SECONDS
    if expires_at:
        ttl = min(ttl, max(1, int(expires_at) - now))
    if has_r2_signing_credentials(env):
        download_url = signed_get_url(env, row["r2_key"], row["original_filename"], ttl)
        if not await claim_one_time_download(env, row, token_hash, now, ttl):
            raise HTTPException(status_code=410, detail="This one-time link has already been used")
        return RedirectResponse(
            url=download_url,
            status_code=302,
            headers={"cache-control": "no-store"},
        )
    obj = await env.FILES.get(row["r2_key"])
    if obj is None:
        raise HTTPException(status_code=404, detail="Object not found")
    if not await claim_one_time_download(env, row, token_hash, now, ttl):
        raise HTTPException(status_code=410, detail="This one-time link has already been used")
    if hasattr(obj, "arrayBuffer"):
        raw = await obj.arrayBuffer()
        body = bytes(raw)
    elif hasattr(obj, "bytes"):
        body = await obj.bytes()
    else:
        body = obj.body
    headers = {
        "content-disposition": content_disposition(row["original_filename"]),
    }
    content_type = row.get("content_type") or "application/octet-stream"
    return Response(content=body, media_type=content_type, headers=headers)


@app.get("/d/{share_token}")
async def download_page(share_token: str, request: Request):
    env = get_env(request)
    assets = getattr(env, "ASSETS", None)
    if assets is not None:
        resp = await assets.fetch("https://assets.local/index.html")
        body = await resp.bytes()
        return Response(content=body, media_type="text/html")
    return RedirectResponse(url=f"/?download={share_token}", status_code=302)


async def fetch_json(url: str, method: str = "GET", headers=None, body=None) -> dict:
    from workers import fetch

    init = {"method": method}
    if headers:
        init["headers"] = headers
    if body is not None:
        init["body"] = body
    resp = await fetch(url, **init)
    text = await resp.text()
    status = int(getattr(resp, "status", 200))
    if status >= 400:
        raise HTTPException(status_code=400, detail="Identity provider request failed")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def id_token_claims(id_token: str) -> dict:
    try:
        payload = id_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        if not isinstance(claims, dict):
            raise ValueError("ID token claims must be an object")
        return claims
    except (IndexError, ValueError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid identity token")


@app.get("/{path:path}")
async def frontend(path: str, request: Request):
    env = get_env(request)
    assets = getattr(env, "ASSETS", None)
    if assets is None:
        raise HTTPException(status_code=404, detail="Not found")
    asset_path = path if path else "index.html"
    resp = await assets.fetch(f"https://assets.local/{asset_path}")
    body = await resp.bytes()
    content_type = resp.headers.get("content-type") if hasattr(resp.headers, "get") else None
    return Response(content=body, status_code=resp.status, media_type=content_type)
