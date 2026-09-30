from util import row_dict, row_get


def db(env):
    return env.DB


async def query_all(env, sql: str, *params):
    stmt = env.DB.prepare(sql)
    if params:
        stmt = stmt.bind(*params)
    result = await stmt.all()
    rows = getattr(result, "results", None)
    if rows is None:
        rows = result
    return [row_dict(r) or {} for r in rows]


async def query_first(env, sql: str, *params):
    stmt = env.DB.prepare(sql)
    if params:
        stmt = stmt.bind(*params)
    row = await stmt.first()
    return row_dict(row)


async def execute(env, sql: str, *params):
    stmt = env.DB.prepare(sql)
    if params:
        stmt = stmt.bind(*params)
    return await stmt.run()


async def batch(env, statements: list[tuple[str, tuple]]) -> list:
    prepared = []
    for sql, params in statements:
        stmt = env.DB.prepare(sql)
        if params:
            stmt = stmt.bind(*params)
        prepared.append(stmt)
    return await env.DB.batch(prepared)


def changes(result) -> int:
    meta = getattr(result, "meta", None)
    if meta is None and isinstance(result, dict):
        meta = result.get("meta")
    if meta is None:
        return 0
    value = row_get(meta, "changes", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
