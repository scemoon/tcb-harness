from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    JSON,
    create_engine,
)
from sqlalchemy.orm import declarative_base, Session as SASession, sessionmaker

from cdh.config import CLOUD_DEV_HARNESS_DIR

Base = declarative_base()


class SessionRecord(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), default="Untitled")
    mode = Column(String(50), default="agent")
    project = Column(String(255), default="")
    model = Column(String(255), default="")
    provider = Column(String(255), default="")
    messages = Column(JSON, default=list)
    lifecycle_state = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class SessionStore:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = CLOUD_DEV_HARNESS_DIR / "sessions" / "cdh.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def create(self, name: str = "Untitled", mode: str = "agent") -> SessionRecord:
        with self.Session() as session:
            record = SessionRecord(name=name, mode=mode)
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_all(self) -> list[SessionRecord]:
        with self.Session() as session:
            return session.query(SessionRecord).order_by(SessionRecord.updated_at.desc()).all()

    def load(self, session_id: str) -> Optional[SessionRecord]:
        with self.Session() as session:
            return session.query(SessionRecord).filter_by(id=session_id).first()

    def update(self, record: SessionRecord):
        with self.Session() as s:
            s.merge(record)
            s.commit()

    def delete(self, session_id: str):
        with self.Session() as s:
            record = s.query(SessionRecord).filter_by(id=session_id).first()
            if record:
                s.delete(record)
                s.commit()

    def rename(self, session_id: str, new_name: str):
        with self.Session() as s:
            record = s.query(SessionRecord).filter_by(id=session_id).first()
            if record:
                record.name = new_name
                s.commit()

    def export_json(self, session_id: str) -> Optional[str]:
        record = self.load(session_id)
        if not record:
            return None
        return json.dumps(
            {
                "id": record.id,
                "name": record.name,
                "mode": record.mode,
                "project": record.project,
                "model": record.model,
                "messages": record.messages,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            },
            indent=2,
            ensure_ascii=False,
        )
