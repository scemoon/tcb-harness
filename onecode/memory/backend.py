from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, String, Text, DateTime, JSON, create_engine, Index
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from onecode.config import ONECODE_DIR


Base = declarative_base()


class MemoryRecord(Base):
    __tablename__ = "memory_entries"

    id = Column(String(16), primary_key=True)
    layer = Column(String(20), nullable=False, index=True)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    metadata_json = Column(JSON, default=dict)
    parent_id = Column(String(16), nullable=True, index=True)
    result_ref = Column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_layer_timestamp", "layer", "timestamp"),
        Index("idx_parent_id", "parent_id"),
    )


class MemoryBackend:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = ONECODE_DIR / "memory" / "memory.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False)
        with self.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    @contextmanager
    def session(self) -> Session:
        s = self.Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def add_entry(
        self,
        entry_id: str,
        layer: str,
        content: str,
        metadata: Optional[dict] = None,
        parent_id: Optional[str] = None,
        result_ref: Optional[str] = None,
    ) -> bool:
        with self.session() as s:
            record = MemoryRecord(
                id=entry_id,
                layer=layer,
                content=content,
                timestamp=datetime.now(timezone.utc),
                metadata_json=metadata or {},
                parent_id=parent_id,
                result_ref=result_ref,
            )
            s.merge(record)
            return True

    def get_entry(self, entry_id: str) -> Optional[dict]:
        with self.session() as s:
            record = s.query(MemoryRecord).filter_by(id=entry_id).first()
            if record:
                return {
                    "id": record.id,
                    "layer": record.layer,
                    "content": record.content,
                    "timestamp": record.timestamp.isoformat() if record.timestamp else "",
                    "metadata_json": record.metadata_json,
                    "parent_id": record.parent_id,
                    "result_ref": record.result_ref,
                }
            return None

    def get_entries_by_layer(self, layer: str, limit: int = 100) -> list[MemoryRecord]:
        with self.session() as s:
            records = (
                s.query(MemoryRecord)
                .filter_by(layer=layer)
                .order_by(MemoryRecord.timestamp.desc())
                .limit(limit)
                .all()
            )
            return records

    def get_entries_by_parent(self, parent_id: str) -> list[MemoryRecord]:
        with self.session() as s:
            return (
                s.query(MemoryRecord)
                .filter_by(parent_id=parent_id)
                .order_by(MemoryRecord.timestamp)
                .all()
            )

    def get_all_entries(self, layer: Optional[str] = None) -> list[dict]:
        with self.session() as s:
            query = s.query(MemoryRecord).order_by(MemoryRecord.timestamp.desc())
            if layer:
                query = query.filter_by(layer=layer)
            return [
                {
                    "id": r.id,
                    "layer": r.layer,
                    "content": r.content,
                    "timestamp": r.timestamp.isoformat() if r.timestamp else "",
                    "metadata_json": r.metadata_json or {},
                    "parent_id": r.parent_id,
                    "result_ref": r.result_ref,
                }
                for r in query.all()
            ]

    def get_recent_entries(self, layer: Optional[str] = None, limit: int = 20) -> list[MemoryRecord]:
        with self.session() as s:
            query = s.query(MemoryRecord).order_by(MemoryRecord.timestamp.desc())
            if layer:
                query = query.filter_by(layer=layer)
            return query.limit(limit).all()

    def search_content(self, query: str, layer: Optional[str] = None, limit: int = 10) -> list[MemoryRecord]:
        with self.session() as s:
            q = s.query(MemoryRecord)
            if layer:
                q = q.filter_by(layer=layer)
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            q = q.filter(MemoryRecord.content.like(pattern, escape="\\"))
            records = q.order_by(MemoryRecord.timestamp.desc()).limit(limit).all()
            return records

    def delete_entry(self, entry_id: str) -> bool:
        with self.session() as s:
            record = s.query(MemoryRecord).filter_by(id=entry_id).first()
            if record:
                s.delete(record)
                return True
            return False

    def count_by_layer(self) -> dict[str, int]:
        with self.session() as s:
            from sqlalchemy import func
            results = s.query(MemoryRecord.layer, func.count(MemoryRecord.id)).group_by(MemoryRecord.layer).all()
            return {layer: count for layer, count in results}

    def clear_old_entries(self, layer: str, keep_last: int = 100) -> tuple[int, list[str]]:
        removed_ids = []
        with self.session() as s:
            count = s.query(MemoryRecord).filter_by(layer=layer).count()
            if count > keep_last:
                old_entries = (
                    s.query(MemoryRecord)
                    .filter_by(layer=layer)
                    .order_by(MemoryRecord.timestamp.asc())
                    .limit(count - keep_last)
                    .all()
                )
                for entry in old_entries:
                    removed_ids.append(entry.id)
                    s.delete(entry)
        return len(removed_ids), removed_ids