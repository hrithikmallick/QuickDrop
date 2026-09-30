from constants import (
    PENDING_TTL_SECONDS,
    STATUS_ACTIVE,
    STATUS_CONSUMED,
    STATUS_DELETED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_PENDING,
)
from db import batch, changes, execute, query_all
from r2util import r2_delete
from util import now_ts


async def _safe_delete_r2(env, key: str) -> None:
    try:
        await r2_delete(env, key)
    except Exception:
        pass


async def expire_due_files(env, now: int) -> int:
    rows = await query_all(
        env,
        """
        SELECT id, user_id, size_bytes, r2_key, status
        FROM files
        WHERE status IN (?, ?) AND expires_at IS NOT NULL AND expires_at <= ?
        """,
        STATUS_ACTIVE,
        STATUS_CONSUMED,
        now,
    )
    count = 0
    for row in rows:
        expected_status = row["status"]
        await _safe_delete_r2(env, row["r2_key"])
        results = await batch(
            env,
            [
                (
                    """
                    UPDATE users
                    SET storage_used_bytes = MAX(0, storage_used_bytes - ?), updated_at = ?
                    WHERE id = ? AND EXISTS (
                        SELECT 1 FROM files
                        WHERE id = ? AND user_id = ? AND status = ?
                          AND expires_at IS NOT NULL AND expires_at <= ?
                    )
                    """,
                    (
                        int(row["size_bytes"] or 0), now, row["user_id"], row["id"],
                        row["user_id"], expected_status, now,
                    ),
                ),
                (
                    """
                    UPDATE files SET status = ?, share_token_hash = NULL, updated_at = ?
                    WHERE id = ? AND status = ? AND expires_at IS NOT NULL AND expires_at <= ?
                      AND changes() = 1
                    """,
                    (STATUS_EXPIRED, now, row["id"], expected_status, now),
                ),
            ],
        )
        if changes(results[1]) == 1:
            count += 1
    return count


async def fail_stale_pending(env, now: int) -> int:
    cutoff = now - PENDING_TTL_SECONDS
    rows = await query_all(
        env,
        """
        SELECT id, user_id, size_bytes, r2_key
        FROM files
        WHERE status = ? AND created_at <= ?
        """,
        STATUS_PENDING,
        cutoff,
    )
    count = 0
    for row in rows:
        await _safe_delete_r2(env, row["r2_key"])
        results = await batch(
            env,
            [
                (
                    """
                    UPDATE users
                    SET storage_reserved_bytes = MAX(0, storage_reserved_bytes - ?), updated_at = ?
                    WHERE id = ? AND EXISTS (
                        SELECT 1 FROM files
                        WHERE id = ? AND user_id = ? AND status = ? AND created_at <= ?
                    )
                    """,
                    (int(row["size_bytes"] or 0), now, row["user_id"], row["id"], row["user_id"], STATUS_PENDING, cutoff),
                ),
                (
                    """
                    UPDATE files SET status = ?, updated_at = ?
                    WHERE id = ? AND status = ? AND created_at <= ? AND changes() = 1
                    """,
                    (STATUS_FAILED, now, row["id"], STATUS_PENDING, cutoff),
                ),
            ],
        )
        if changes(results[1]) == 1:
            count += 1
    return count


async def purge_deleted_objects(env) -> int:
    rows = await query_all(
        env,
        """
        SELECT id, r2_key
        FROM files
        WHERE status IN (?, ?, ?) AND r2_key IS NOT NULL
        """,
        STATUS_EXPIRED,
        STATUS_DELETED,
        STATUS_FAILED,
    )
    count = 0
    for row in rows:
        await _safe_delete_r2(env, row["r2_key"])
        count += 1
    return count


async def run_cleanup(env) -> dict:
    now = now_ts()
    expired = await expire_due_files(env, now)
    stale = await fail_stale_pending(env, now)
    purged = await purge_deleted_objects(env)
    await execute(env, "DELETE FROM sessions WHERE expires_at <= ?", now)
    return {
        "expired_files": expired,
        "stale_pending": stale,
        "purged_objects": purged,
        "ran_at": now,
    }
