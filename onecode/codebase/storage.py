from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from sqlalchemy import Column, String, Text, Integer, Float, create_engine, Index
from sqlalchemy.orm import declarative_base, sessionmaker, Session

from onecode.codebase.chunker import CodeChunk

Base = declarative_base()


class ChunkRecord(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_path = Column(String(1024), nullable=False, index=True)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    language = Column(String(64), default="")
    file_mtime = Column(Float, default=0.0)

    __table_args__ = (
        Index("idx_file_path", "file_path"),
        Index("idx_language", "language"),
    )


class CodebaseStorage:
    def __init__(self, project_dir: Path):
        db_dir = project_dir / ".cdh" / "codebase"
        db_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_dir / "index.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def save_chunks(self, chunks: list[CodeChunk], mtime: float = 0.0) -> None:
        if not chunks:
            return
        file_path = chunks[0].file_path
        with self.Session() as s:
            s.query(ChunkRecord).filter_by(file_path=file_path).delete()
            for c in chunks:
                s.add(ChunkRecord(
                    file_path=c.file_path,
                    start_line=c.start_line,
                    end_line=c.end_line,
                    content=c.content,
                    language=c.language,
                    file_mtime=mtime,
                ))
            s.commit()

    def remove_file(self, file_path: str) -> None:
        with self.Session() as s:
            s.query(ChunkRecord).filter_by(file_path=file_path).delete()
            s.commit()

    def remove_directory(self, dir_path: str) -> None:
        prefix = dir_path.rstrip("/") + "/"
        with self.Session() as s:
            s.query(ChunkRecord).filter(
                ChunkRecord.file_path.like(f"{prefix}%")
            ).delete(synchronize_session=False)
            s.commit()

    def get_file_mtime(self, file_path: str) -> float:
        with self.Session() as s:
            record = (
                s.query(ChunkRecord.file_mtime)
                .filter_by(file_path=file_path)
                .order_by(ChunkRecord.file_mtime.desc())
                .first()
            )
            return record[0] if record else 0.0

    def get_indexed_files(self) -> set[str]:
        with self.Session() as s:
            rows = s.query(ChunkRecord.file_path).distinct().all()
            return {row[0] for row in rows}

    def get_all_chunks(self) -> list[CodeChunk]:
        with self.Session() as s:
            records = s.query(ChunkRecord).all()
            return [
                CodeChunk(
                    file_path=r.file_path,
                    start_line=r.start_line,
                    end_line=r.end_line,
                    content=r.content,
                    language=r.language,
                )
                for r in records
            ]

    def get_chunks_for_file(self, file_path: str) -> list[CodeChunk]:
        with self.Session() as s:
            records = (
                s.query(ChunkRecord)
                .filter_by(file_path=file_path)
                .order_by(ChunkRecord.start_line)
                .all()
            )
            return [
                CodeChunk(
                    file_path=r.file_path,
                    start_line=r.start_line,
                    end_line=r.end_line,
                    content=r.content,
                    language=r.language,
                )
                for r in records
            ]

    def chunk_count(self) -> int:
        with self.Session() as s:
            return s.query(ChunkRecord).count()

    def file_count(self) -> int:
        with self.Session() as s:
            return s.query(ChunkRecord.file_path).distinct().count()

    def clear_all(self) -> None:
        with self.Session() as s:
            s.query(ChunkRecord).delete()
            s.commit()
