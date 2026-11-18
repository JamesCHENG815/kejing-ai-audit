from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DATABASE_PATH = DATA_DIR / "kejing_audit.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


class Base(DeclarativeBase):
    pass


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Importing models registers every table on Base.metadata.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    # create_all does not add columns to an existing SQLite database. Keep this
    # small migration here until the project introduces a dedicated migration tool.
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info(human_reviews)")
        }
        if "confirmed" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE human_reviews "
                "ADD COLUMN confirmed BOOLEAN NOT NULL DEFAULT 0"
            )
        _backfill_review_events(connection)


def _backfill_review_events(connection) -> None:
    """Record pre-upgrade review rows as ``legacy`` events.

    ``review_events`` was introduced after the first production data existed, so
    those tasks would otherwise show an empty audit panel. The rows are real
    (reviewer / value / reason / timestamp all come from ``human_reviews``); only
    the intermediate history before the upgrade is genuinely unknown, and the
    event type makes that explicit instead of implying it was observed.

    Idempotent: a task that already has any event is skipped.
    """
    connection.exec_driver_sql(
        """
        INSERT INTO review_events
            (task_id, event_type, field_name, value_before, value_after,
             reason, reviewer, created_at)
        SELECT hr.task_id, 'legacy', hr.field_name, NULL, hr.final_value,
               hr.change_reason, hr.reviewer, hr.updated_at
        FROM human_reviews hr
        WHERE NOT EXISTS (
            SELECT 1 FROM review_events ev WHERE ev.task_id = hr.task_id
        )
        """
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
