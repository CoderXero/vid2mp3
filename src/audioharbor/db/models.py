from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.types import JSON


def now() -> datetime: return datetime.now(UTC)
def uid() -> str: return str(uuid4())


class Base(DeclarativeBase): pass


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    input_url_redacted: Mapped[str] = mapped_column(Text)
    canonical_source: Mapped[str | None] = mapped_column(Text)
    service: Mapped[str] = mapped_column(String(40), default="youtube")
    state: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    options_json: Mapped[dict] = mapped_column(JSON, default=dict)
    discovery_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    limit_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    entries: Mapped[list["JobEntry"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Collection(Base):
    __tablename__ = "collections"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    service: Mapped[str] = mapped_column(String(40))
    collection_key: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("collections.id"))
    index_path: Mapped[list] = mapped_column(JSON, default=list)
    title: Mapped[str] = mapped_column(String(500), default="Playlist")
    discovery_cursor: Mapped[str | None] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(32), default="discovering")
    __table_args__ = (UniqueConstraint("job_id", "collection_key", name="uq_collection_job_key"),)


class MediaTask(Base):
    __tablename__ = "media_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service: Mapped[str] = mapped_column(String(40))
    media_id: Mapped[str] = mapped_column(String(255))
    profile_hash: Mapped[str] = mapped_column(String(64))
    generation: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[str] = mapped_column(String(32), default="discovered", index=True)
    auth_session_id: Mapped[str | None] = mapped_column(String(36))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(100), index=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    progress_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_id: Mapped[str | None] = mapped_column(String(36))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint("service", "media_id", "profile_hash", "generation", name="uq_task_identity"),)


class JobEntry(Base):
    __tablename__ = "job_entries"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    collection_id: Mapped[str | None] = mapped_column(ForeignKey("collections.id"))
    index_path: Mapped[list] = mapped_column(JSON, default=list)
    source_id: Mapped[str | None] = mapped_column(String(255))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("media_tasks.id"))
    display_title: Mapped[str] = mapped_column(String(500), default="Unavailable item")
    occurrence_status: Mapped[str] = mapped_column(String(32), default="discovered")
    selected: Mapped[bool] = mapped_column(Boolean, default=True)
    job: Mapped[Job] = relationship(back_populates="entries")
    task: Mapped[MediaTask | None] = relationship()
    __table_args__ = (UniqueConstraint("job_id", "index_path", name="uq_entry_path"),)


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    task_id: Mapped[str] = mapped_column(ForeignKey("media_tasks.id", ondelete="CASCADE"), index=True)
    phase: Mapped[str] = mapped_column(String(32)); number: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64)); provider_http_status: Mapped[int | None] = mapped_column(Integer)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False); sanitized_message: Mapped[str | None] = mapped_column(Text)
    diagnostic_ref: Mapped[str | None] = mapped_column(String(255))


class Output(Base):
    __tablename__ = "outputs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service: Mapped[str] = mapped_column(String(40)); media_id: Mapped[str] = mapped_column(String(255))
    profile_hash: Mapped[str] = mapped_column(String(64)); generation: Mapped[int] = mapped_column(Integer)
    relative_path: Mapped[str] = mapped_column(Text, unique=True); sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer); duration_seconds: Mapped[float]
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(64)); payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    scope_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    next_allowed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    throttle_count: Mapped[int] = mapped_column(Integer, default=0); reason: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    service: Mapped[str] = mapped_column(String(40)); opaque_secret_ref: Mapped[str | None] = mapped_column(String(255))
    credential_version: Mapped[int] = mapped_column(Integer, default=1); method: Mapped[str] = mapped_column(String(32))
    persistence: Mapped[str] = mapped_column(String(16), default="ephemeral"); expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(32), default="active")


def make_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False, "timeout": 30})
    @event.listens_for(engine, "connect")
    def _sqlite(dbapi_connection, _):
        cur = dbapi_connection.cursor(); cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA foreign_keys=ON"); cur.execute("PRAGMA busy_timeout=30000"); cur.close()
    return engine


engine = make_engine(Path.home() / ".local/state/audioharbor/audioharbor.sqlite3")
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

