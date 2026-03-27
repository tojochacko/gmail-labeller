"""Async SQLAlchemy engine and session factory."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def make_engine(database_url: str):
    """Create an async SQLAlchemy engine from a connection URL."""
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_async_engine(database_url, connect_args=connect_args)


def make_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to *engine*."""
    return async_sessionmaker(engine, expire_on_commit=False)
