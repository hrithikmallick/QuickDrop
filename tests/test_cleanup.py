import asyncio

from cleanup import run_cleanup
from constants import STATUS_ACTIVE, STATUS_CONSUMED, STATUS_EXPIRED, STATUS_FAILED, STATUS_PENDING
from tests.fakes import FakeEnv


def run(coro):
    return asyncio.run(coro)


def test_cleanup_expires_files_and_reclaims_quota():
    env = FakeEnv()
    env.DB.users["u1"] = {
        "id": "u1",
        "storage_used_bytes": 100,
        "storage_reserved_bytes": 50,
        "updated_at": 0,
    }
    env.DB.files["f1"] = {
        "id": "f1",
        "user_id": "u1",
        "size_bytes": 100,
        "r2_key": "k1",
        "status": STATUS_ACTIVE,
        "expires_at": 1,
        "created_at": 1,
        "share_token_hash": "abc",
    }
    env.FILES.objects["k1"] = b"hello"
    result = run(run_cleanup(env))
    assert result["expired_files"] == 1
    assert env.DB.files["f1"]["status"] == STATUS_EXPIRED
    assert env.DB.users["u1"]["storage_used_bytes"] == 0
    assert "k1" in env.FILES.deleted
    assert run(run_cleanup(env))["expired_files"] == 0
    assert env.DB.users["u1"]["storage_used_bytes"] == 0


def test_cleanup_fails_stale_pending_and_releases_reservation():
    env = FakeEnv()
    env.DB.users["u1"] = {
        "id": "u1",
        "storage_used_bytes": 0,
        "storage_reserved_bytes": 40,
        "updated_at": 0,
    }
    env.DB.files["f2"] = {
        "id": "f2",
        "user_id": "u1",
        "size_bytes": 40,
        "r2_key": "k2",
        "status": STATUS_PENDING,
        "expires_at": 9_999_999_999,
        "created_at": 1,
        "share_token_hash": None,
    }
    env.FILES.objects["k2"] = b"pending"
    result = run(run_cleanup(env))
    assert result["stale_pending"] == 1
    assert env.DB.files["f2"]["status"] == STATUS_FAILED
    assert env.DB.users["u1"]["storage_reserved_bytes"] == 0


def test_cleanup_reclaims_consumed_one_time_file():
    env = FakeEnv()
    env.DB.users["u1"] = {
        "id": "u1",
        "storage_used_bytes": 80,
        "storage_reserved_bytes": 0,
        "updated_at": 0,
    }
    env.DB.files["f3"] = {
        "id": "f3",
        "user_id": "u1",
        "size_bytes": 80,
        "r2_key": "k3",
        "status": STATUS_CONSUMED,
        "expires_at": 1,
        "created_at": 1,
        "share_token_hash": None,
    }
    env.FILES.objects["k3"] = b"one-time"

    result = run(run_cleanup(env))

    assert result["expired_files"] == 1
    assert env.DB.files["f3"]["status"] == STATUS_EXPIRED
    assert env.DB.users["u1"]["storage_used_bytes"] == 0
    assert "k3" in env.FILES.deleted
    assert run(run_cleanup(env))["stale_pending"] == 0
    assert env.DB.users["u1"]["storage_reserved_bytes"] == 0
