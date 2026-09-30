from constants import QUOTA_BYTES, quota_allows


def test_quota_allows_exact_limit():
    assert quota_allows(0, 0, QUOTA_BYTES) is True


def test_quota_rejects_over_limit():
    assert quota_allows(QUOTA_BYTES, 0, 1) is False


def test_quota_includes_reserved():
    used = 100
    reserved = QUOTA_BYTES - 100
    assert quota_allows(used, reserved, 1) is False
    assert quota_allows(used, reserved, 0) is True


def test_quota_used_reserved_and_new_file():
    used = 200 * 1024 * 1024
    reserved = 200 * 1024 * 1024
    new_file = 100 * 1024 * 1024
    assert quota_allows(used, reserved, new_file) is True
    assert quota_allows(used, reserved, new_file + 1) is False
