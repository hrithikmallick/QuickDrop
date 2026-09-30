from constants import EXPIRY_SECONDS, DEFAULT_EXPIRY
from util import hash_token, random_token, sanitize_filename


def test_hash_token_is_sha256_hex():
    digest = hash_token("secret")
    assert len(digest) == 64
    assert digest == hash_token("secret")
    assert digest != hash_token("other")


def test_random_tokens_are_unique():
    tokens = {random_token() for _ in range(50)}
    assert len(tokens) == 50


def test_default_expiry_is_24h():
    assert DEFAULT_EXPIRY == "24h"
    assert set(EXPIRY_SECONDS) == {"1h", "6h", "24h", "3d", "7d"}
    assert EXPIRY_SECONDS["24h"] == 86400


def test_sanitize_filename_strips_path_parts():
    assert "/" not in sanitize_filename("../../etc/passwd")
    assert "\\" not in sanitize_filename("win\\path")
    assert sanitize_filename("") == "download"


def test_sanitize_filename_strips_control_characters():
    assert "\r" not in sanitize_filename("bad\r\nname.txt")
    assert "\n" not in sanitize_filename("bad\r\nname.txt")
