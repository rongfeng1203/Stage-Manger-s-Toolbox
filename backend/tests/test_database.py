from datetime import date, time

from sqlmodel import select

from backend.app.database import (
    build_sqlite_url,
    create_db_and_tables,
    create_sqlite_engine,
    get_session,
)
from backend.app.models import Actor, Character, Production, Scene


def test_build_sqlite_url_supports_memory_database() -> None:
    assert build_sqlite_url(":memory:") == "sqlite://"


def test_build_sqlite_url_supports_file_database() -> None:
    assert build_sqlite_url("stage_scheduler.db") == "sqlite:///stage_scheduler.db"


def test_create_sqlite_database_and_tables() -> None:
    engine = create_sqlite_engine(":memory:")

    create_db_and_tables(engine)

    with engine.connect() as connection:
        table_names = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).all()

    assert ("production",) in table_names
    assert ("scene",) in table_names
    assert ("actor",) in table_names
    assert ("character",) in table_names


def test_production_scene_actor_and_character_can_be_created() -> None:
    engine = create_sqlite_engine(":memory:")
    create_db_and_tables(engine)

    with next(get_session(engine)) as session:
        production = Production(
            name="Hamlet",
            rehearsal_start_date=date(2026, 7, 1),
            rehearsal_end_date=date(2026, 7, 14),
            daily_start_time=time(18, 0),
            daily_end_time=time(22, 0),
        )
        session.add(production)
        session.commit()
        session.refresh(production)

        actor = Actor(name="Rina Feng", email="rina@example.com")
        session.add(actor)
        character = Character(production_id=production.id or 0, name="Hamlet")
        session.add(character)
        scene = Scene(
            production_id=production.id or 0,
            scene_code="A1S1",
            title="Battlements",
            page_start=1,
            page_end=6,
            priority=3,
            target_rehearsal_minutes=120,
        )
        session.add(scene)
        session.commit()

        assert session.exec(select(Production)).one().name == "Hamlet"
        assert session.exec(select(Actor)).one().calendar_connected is False
        assert session.exec(select(Character)).one().name == "Hamlet"
        assert session.exec(select(Scene)).one().scene_code == "A1S1"
