"""Integration tests create and remove only their own uniquely named databases."""

from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from alembic.config import Config
from sqlalchemy import create_engine, text

from alembic import command
from app.core.config import get_settings


@contextmanager
def isolated_database():
    url = get_settings().database_url
    name = "finsight_test_" + uuid4().hex
    admin = create_engine(url, isolation_level="AUTOCOMMIT", connect_args={"connect_timeout": 5})
    engine = None
    created = False
    try:
        with admin.connect() as connection:
            # name is exclusively a generated prefix + UUID, never user-supplied SQL.
            connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
        created = True
        engine = create_engine(
            url.set(database=name),
            connect_args={"connect_timeout": 5, "options": "-c timezone=UTC"},
        )
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            assert name.startswith("finsight_test_") and len(name) == 46
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}"'))
        admin.dispose()


def run_migration(engine, operation, target=None):
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        if target is None:
            getattr(command, operation)(config)
        else:
            getattr(command, operation)(config, target)
