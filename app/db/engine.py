from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.core.config import settings

# command_timeout (asyncpg) — серверный statement timeout: зависший запрос
# не будет держать коннект до бесконечности (важно при пуле 10+20).
# pool_recycle — переустановка коннектов раз в час (защита от RST из-за
# простоев и от закрытия idle-коннектов фаерволами).
engine = create_async_engine(
    settings.database_url,
    echo=settings.log_level == "DEBUG",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={
        "command_timeout": 30,
        "timeout": 10,  # connect timeout
    },
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
