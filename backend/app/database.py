from collections.abc import Iterator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine


def build_sqlite_url(database_path: str) -> str:
    if database_path == ":memory:":
        return "sqlite://"
    return f"sqlite:///{database_path}"


def create_sqlite_engine(database_path: str, *, echo: bool = False) -> Engine:
    connect_args = {"check_same_thread": False}
    return create_engine(build_sqlite_url(database_path), echo=echo, connect_args=connect_args)


def create_db_and_tables(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)


def get_session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
