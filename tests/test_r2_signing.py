from r2util import has_r2_signing_credentials, presign_r2


class Env:
    def __init__(self, **values):
        for key, value in values.items():
            setattr(self, key, value)


def test_missing_credentials():
    env = Env()
    assert has_r2_signing_credentials(env) is False


def test_presign_contains_required_query_params():
    env = Env(
        R2_ACCOUNT_ID="abc123",
        R2_ACCESS_KEY_ID="AKIAEXAMPLE",
        R2_SECRET_ACCESS_KEY="secretsecretsecretsecret",
        R2_BUCKET_NAME="quickdrop-files",
    )
    url = presign_r2(env, "PUT", "uploads/user/file/key", 900, {"content-type": "text/plain"})
    assert url.startswith("https://abc123.r2.cloudflarestorage.com/quickdrop-files/uploads/user/file/key?")
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in url
    assert "X-Amz-Signature=" in url
    assert "X-Amz-Expires=900" in url
    assert "secretsecret" not in url
