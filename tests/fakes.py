from types import SimpleNamespace


class FakePrepared:
    def __init__(self, db, sql, params=()):
        self.db = db
        self.sql = " ".join(sql.split())
        self.params = params

    def bind(self, *params):
        return FakePrepared(self.db, self.sql, params)

    async def all(self):
        rows = self.db.execute(self.sql, self.params)
        return SimpleNamespace(results=rows)

    async def first(self):
        rows = self.db.execute(self.sql, self.params)
        return rows[0] if rows else None

    async def run(self):
        rows = self.db.execute(self.sql, self.params)
        return SimpleNamespace(meta=SimpleNamespace(changes=len(rows)))


class FakeD1:
    def __init__(self):
        self.users = {}
        self.files = {}
        self.sessions = {}
        self.identities = {}

    def prepare(self, sql: str):
        return FakePrepared(self, sql)

    async def batch(self, statements):
        return [await statement.run() for statement in statements]

    def execute(self, sql: str, params):
        sql_u = sql.upper()
        if sql_u.startswith("UPDATE FILES") and "SET EXPIRES_AT = ?" in sql_u:
            expires_at, now, file_id, expected, token_hash, cutoff = params
            row = self.files.get(file_id)
            if (
                row
                and row["status"] == expected
                and row.get("share_token_hash") == token_hash
                and (row.get("expires_at") is None or row["expires_at"] > cutoff)
            ):
                row["expires_at"] = expires_at
                row["share_token_hash"] = None
                row["updated_at"] = now
                return [row]
            return []
        if sql_u.startswith("SELECT ID, USER_ID, SIZE_BYTES, R2_KEY"):
            if "STATUS = ?" in sql_u and "EXPIRES_AT" in sql_u:
                status, cutoff = params
                return [
                    row
                    for row in self.files.values()
                    if row["status"] == status
                    and row.get("expires_at") is not None
                    and row["expires_at"] <= cutoff
                ]
            if "STATUS = ?" in sql_u and "CREATED_AT" in sql_u:
                status, cutoff = params
                return [
                    row
                    for row in self.files.values()
                    if row["status"] == status and row["created_at"] <= cutoff
                ]
        if "STATUS IN" in sql_u and "R2_KEY" in sql_u:
            statuses = set(params)
            return [
                {"id": row["id"], "r2_key": row["r2_key"]}
                for row in self.files.values()
                if row["status"] in statuses
            ]
        if sql_u.startswith("UPDATE USERS") and "STORAGE_USED_BYTES" in sql_u and "EXISTS" in sql_u:
            delta, now, user_id, file_id, file_user_id, expected, cutoff = params
            row = self.files.get(file_id)
            if row and row["user_id"] == file_user_id and row["status"] == expected and row["expires_at"] <= cutoff:
                user = self.users[user_id]
                user["storage_used_bytes"] = max(0, user["storage_used_bytes"] - delta)
                user["updated_at"] = now
                return [user]
            return []
        if sql_u.startswith("UPDATE USERS") and "STORAGE_RESERVED_BYTES" in sql_u and "EXISTS" in sql_u:
            delta, now, user_id, file_id, file_user_id, expected, cutoff = params
            row = self.files.get(file_id)
            if row and row["user_id"] == file_user_id and row["status"] == expected and row["created_at"] <= cutoff:
                user = self.users[user_id]
                user["storage_reserved_bytes"] = max(0, user["storage_reserved_bytes"] - delta)
                user["updated_at"] = now
                return [user]
            return []
        if sql_u.startswith("UPDATE FILES") and "STATUS = ?" in sql_u and "SHARE_TOKEN_HASH = NULL" in sql_u:
            status, now, file_id, expected, cutoff = params
            row = self.files.get(file_id)
            if row and row["status"] == expected and row["expires_at"] <= cutoff:
                row["status"] = status
                row["share_token_hash"] = None
                row["updated_at"] = now
                return [row]
            return []
        if sql_u.startswith("UPDATE FILES") and "STATUS = ?" in sql_u:
            status, now, file_id, expected, cutoff = params
            row = self.files.get(file_id)
            if row and row["status"] == expected and row["created_at"] <= cutoff:
                row["status"] = status
                row["updated_at"] = now
                return [row]
            return []
        if sql_u.startswith("UPDATE USERS") and "STORAGE_USED_BYTES" in sql_u:
            delta, now, user_id = params
            user = self.users[user_id]
            user["storage_used_bytes"] = max(0, user["storage_used_bytes"] - delta)
            user["updated_at"] = now
            return [user]
        if sql_u.startswith("UPDATE USERS") and "STORAGE_RESERVED_BYTES" in sql_u:
            delta, now, user_id = params
            user = self.users[user_id]
            user["storage_reserved_bytes"] = max(0, user["storage_reserved_bytes"] - delta)
            user["updated_at"] = now
            return [user]
        if sql_u.startswith("DELETE FROM SESSIONS"):
            cutoff = params[0]
            removed = [s for s in self.sessions.values() if s["expires_at"] <= cutoff]
            for row in removed:
                self.sessions.pop(row["id"], None)
            return removed
        return []


class FakeR2:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    async def put(self, key, body, **kwargs):
        self.objects[key] = body
        return SimpleNamespace(size=len(body) if hasattr(body, "__len__") else 0)

    async def head(self, key):
        body = self.objects.get(key)
        if body is None:
            return None
        return SimpleNamespace(size=len(body))

    async def get(self, key):
        body = self.objects.get(key)
        if body is None:
            return None

        class Obj:
            async def arrayBuffer(self_inner):
                return body

        return Obj()

    async def delete(self, key):
        self.deleted.append(key)
        self.objects.pop(key, None)


class FakeEnv:
    def __init__(self):
        self.DB = FakeD1()
        self.FILES = FakeR2()
        self.ENVIRONMENT = "development"
