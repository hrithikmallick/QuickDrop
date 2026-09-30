from datetime import datetime, timezone
from urllib.parse import quote

from constants import SIGNED_GET_TTL_SECONDS, SIGNED_PUT_TTL_SECONDS
from util import env_str, hmac_sha256, sha256_hex


def r2_credentials(env) -> tuple[str, str, str, str]:
    account_id = env_str(env, "R2_ACCOUNT_ID")
    access_key = env_str(env, "R2_ACCESS_KEY_ID")
    secret_key = env_str(env, "R2_SECRET_ACCESS_KEY")
    bucket = env_str(env, "R2_BUCKET_NAME", "quickdrop-files")
    return account_id, access_key, secret_key, bucket


def has_r2_signing_credentials(env) -> bool:
    account_id, access_key, secret_key, _ = r2_credentials(env)
    return bool(account_id and access_key and secret_key)


def _uri_encode(value: str, is_path: bool = False) -> str:
    safe = "/" if is_path else ""
    return quote(value, safe=safe)


def aws_v4_signing_key(secret_key: str, datestamp: str, region: str, service: str) -> bytes:
    k_date = hmac_sha256(("AWS4" + secret_key).encode("utf-8"), datestamp)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    return hmac_sha256(k_service, "aws4_request")


def presign_r2(
    env,
    method: str,
    object_key: str,
    expires: int,
    headers: dict[str, str] | None = None,
    extra_query: dict[str, str] | None = None,
) -> str:
    account_id, access_key, secret_key, bucket = r2_credentials(env)
    if not (account_id and access_key and secret_key):
        raise RuntimeError("R2 signing credentials are not configured")

    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    region = "auto"
    service = "s3"
    host = f"{account_id}.r2.cloudflarestorage.com"
    canonical_uri = "/" + _uri_encode(f"{bucket}/{object_key}", is_path=True).replace("%2F", "/")
    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    signed_headers_map = {"host": host}
    extra = headers or {}
    for name, value in extra.items():
        signed_headers_map[name.lower()] = value.strip()
    signed_header_names = ";".join(sorted(signed_headers_map))
    canonical_headers = "".join(
        f"{k}:{signed_headers_map[k]}\n" for k in sorted(signed_headers_map)
    )
    query = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access_key}/{credential_scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": signed_header_names,
        "X-Amz-Content-Sha256": "UNSIGNED-PAYLOAD",
    }
    if extra_query:
        query.update(extra_query)
    canonical_query = "&".join(
        f"{_uri_encode(k)}={_uri_encode(v)}" for k, v in sorted(query.items())
    )
    canonical_request = "\n".join(
        [
            method.upper(),
            canonical_uri,
            canonical_query,
            canonical_headers,
            signed_header_names,
            "UNSIGNED-PAYLOAD",
        ]
    )
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            credential_scope,
            sha256_hex(canonical_request),
        ]
    )
    signing_key = aws_v4_signing_key(secret_key, datestamp, region, service)
    signature = hmac_sha256(signing_key, string_to_sign).hex()
    return f"https://{host}{canonical_uri}?{canonical_query}&X-Amz-Signature={signature}"


def signed_put_url(env, object_key: str, content_type: str | None) -> str:
    headers = {}
    if content_type:
        headers["content-type"] = content_type
    return presign_r2(env, "PUT", object_key, SIGNED_PUT_TTL_SECONDS, headers)


def signed_get_url(
    env,
    object_key: str,
    filename: str | None = None,
    expires: int = SIGNED_GET_TTL_SECONDS,
) -> str:
    extra = None
    if filename:
        safe = filename.replace('"', "")
        extra = {"response-content-disposition": f'attachment; filename="{safe}"'}
    return presign_r2(env, "GET", object_key, expires, extra_query=extra)


async def r2_head(env, key: str):
    return await env.FILES.head(key)


async def r2_put(env, key: str, body, content_type: str | None = None):
    options = {}
    if content_type:
        options["httpMetadata"] = {"contentType": content_type}
    if options:
        return await env.FILES.put(key, body, **options)
    return await env.FILES.put(key, body)


async def r2_delete(env, key: str):
    await env.FILES.delete(key)


def object_size(obj) -> int | None:
    if obj is None:
        return None
    size = getattr(obj, "size", None)
    if size is None and isinstance(obj, dict):
        size = obj.get("size")
    if size is None:
        return None
    return int(size)
