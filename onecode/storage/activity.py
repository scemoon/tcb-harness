from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, String, Text, DateTime, JSON, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from onecode.config import CLOUD_DEV_HARNESS_DIR

Base = declarative_base()


class ActivityRecord(Base):
    __tablename__ = "activities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(50), nullable=False)
    project = Column(String(255), default="")
    session = Column(String(36), default="")
    details = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ActivityRecorder:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = CLOUD_DEV_HARNESS_DIR / "sessions" / "cdh.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def record(self, event_type: str, project: str = "", session: str = "", details: Optional[dict] = None) -> str:
        with self.Session() as s:
            record = ActivityRecord(
                event_type=event_type,
                project=project,
                session=session,
                details=details or {},
            )
            s.add(record)
            s.commit()
            s.refresh(record)
            return record.id

    def list_activities(self, project: str = "", limit: int = 50) -> list[ActivityRecord]:
        with self.Session() as s:
            q = s.query(ActivityRecord).order_by(ActivityRecord.created_at.desc())
            if project:
                q = q.filter_by(project=project)
            return q.limit(limit).all()

    def list_by_session(self, session_id: str) -> list[ActivityRecord]:
        with self.Session() as s:
            return (
                s.query(ActivityRecord)
                .filter_by(session=session_id)
                .order_by(ActivityRecord.created_at.desc())
                .all()
            )
