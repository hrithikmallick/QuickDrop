import asyncio

from app import claim_one_time_download
from constants import STATUS_ACTIVE, STATUS_CONSUMED
from tests.fakes import FakeEnv


def run(coro):
    return asyncio.run(coro)


def test_one_time_download_can_only_be_claimed_once():
    env = FakeEnv()
    row = {
        "id": "f1",
        "status": STATUS_ACTIVE,
        "share_token_hash": "token-hash",
        "delete_after_download": 1,
        "expires_at": 10_000,
        "updated_at": 0,
    }
    env.DB.files[row["id"]] = row

    assert run(claim_one_time_download(env, row, "token-hash", 100, 60)) is True
    assert row["status"] == STATUS_CONSUMED
    assert row["share_token_hash"] is None
    assert row["expires_at"] == 160
    assert run(claim_one_time_download(env, row, "token-hash", 101, 60)) is False
