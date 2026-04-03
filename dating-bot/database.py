"""
База данных
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL

# Для SQLite нужен connect_args
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_async_engine(DATABASE_URL, echo=False, connect_args=connect_args)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    """Инициализация БД - создание таблиц"""
    async with engine.begin() as conn:
        from models import Base
        await conn.run_sync(Base.metadata.create_all)
