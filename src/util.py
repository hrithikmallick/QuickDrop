import hashlib
import hmac
import secrets
import time
from urllib.parse import quote
def now_ts() -> int:
    return int(time.time())


def new_id() -> str:
    return secrets.token_hex(16)


def random_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def row_get(row, key, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        pass
    return getattr(row, key, default)


def row_dict(row) -> dict | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    keys = None
    for attr in ("keys", "_keys"):
        maybe = getattr(row, attr, None)
        if callable(maybe):
            try:
                keys = list(maybe())
                break
            except Exception:
                pass
        elif maybe is not None:
            keys = list(maybe)
            break
    if keys:
        return {k: row_get(row, k) for k in keys}
    try:
        return dict(row)
    except Exception:
        result = {}
        for name in dir(row):
            if name.startswith("_"):
                continue
            value = getattr(row, name, None)
            if callable(value):
                continue
            result[name] = value
        return result


def env_str(env, name: str, default: str = "") -> str:
    value = getattr(env, name, None)
    if value is None:
        return default
    return str(value)


def is_development(env) -> bool:
    return env_str(env, "ENVIRONMENT") == "development"


def cookie_secure(env, request) -> bool:
    if is_development(env):
        return False
    scheme = request.url.scheme if hasattr(request, "url") else "https"
    return scheme == "https"


def get_cookie(request, name: str) -> str | None:
    cookies = getattr(request, "cookies", None)
    if cookies:
        value = cookies.get(name)
        if value:
            return value
    header = request.headers.get("cookie") or request.headers.get("Cookie")
    if not header:
        return None
    for part in header.split(";"):
        part = part.strip()
        if not part:
            continue
        if part.startswith(name + "="):
            return part[len(name) + 1 :]
    return None


def sanitize_filename(name: str) -> str:
    cleaned = "".join(
        ch if ch >= " " and ch not in '<>:"/\\|?*' else "_" for ch in (name or "")
    )
    cleaned = cleaned.strip().strip(".")
    if not cleaned:
        return "download"
    return cleaned[:255]


def content_disposition(filename: str) -> str:
    safe = sanitize_filename(filename)
    encoded = quote(safe)
    return f"attachment; filename=\"{safe}\"; filename*=UTF-8''{encoded}"


def hmac_sha256(key: bytes, msg: str | bytes) -> bytes:
    data = msg.encode("utf-8") if isinstance(msg, str) else msg
    return hmac.new(key, data, hashlib.sha256).digest()


def sha256_hex(data: str | bytes) -> str:
    payload = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(payload).hexdigest()
