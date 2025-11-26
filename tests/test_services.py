import asyncio

import telegram.bot.services as services


class DummyAdminService:
    _pool = None
    configured_with = None
    init_called = False

    def __init__(self):
        self.created = True

    @classmethod
    def configure(cls, pool):
        cls._pool = pool
        cls.configured_with = pool

    @classmethod
    async def init_storage(cls):
        cls.init_called = True


class DummyCuratorService:
    _pool = None
    configured_with = None
    init_called = False

    def __init__(self, bot):
        self.bot = bot

    @classmethod
    def configure(cls, pool):
        cls._pool = pool
        cls.configured_with = pool

    @classmethod
    async def init_storage(cls):
        cls.init_called = True


async def _run_setup(monkeypatch):
    monkeypatch.setattr(services, "AdminService", DummyAdminService)
    monkeypatch.setattr(services, "CuratorService", DummyCuratorService)

    bot = object()
    pool = object()

    container = await services.setup_services(bot, pool)

    assert isinstance(container.admin, DummyAdminService)
    assert isinstance(container.curator, DummyCuratorService)
    assert container.curator.bot is bot
    assert container.pool is pool
    assert DummyAdminService.configured_with is pool
    assert DummyAdminService.init_called is True
    assert DummyCuratorService.configured_with is pool
    assert DummyCuratorService.init_called is True


def test_setup_services_builds_service_container(monkeypatch):
    asyncio.run(_run_setup(monkeypatch))
