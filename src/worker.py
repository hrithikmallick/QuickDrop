from app import app
from workers import asgi

Default = asgi.entrypoint(app)


async def scheduled(self, controller, env, ctx):
    from cleanup import run_cleanup

    await run_cleanup(env)


Default.scheduled = scheduled
