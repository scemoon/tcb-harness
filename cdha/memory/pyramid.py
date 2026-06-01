from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class MemoryLayer(Enum):
    L0_CONVERSATION = "l0_conversation"
    L1_ATOM = "l1_atom"
    L2_SCENARIO = "l2_scenario"
    L3_PERSONA = "l3_persona"


@dataclass
class MemoryEntry:
    id: str
    layer: MemoryLayer
    content: str
    timestamp: str
    metadata: dict = field(default_factory=dict)
    parent_id: Optional[str] = None
    result_ref: Optional[str] = None

    @classmethod
    def create(
        cls,
        layer: MemoryLayer,
        content: str,
        metadata: Optional[dict] = None,
        parent_id: Optional[str] = None,
    ) -> "MemoryEntry":
        return cls(
            id=str(uuid.uuid4())[:16],
            layer=layer,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
            parent_id=parent_id,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "parent_id": self.parent_id,
            "result_ref": self.result_ref,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            id=data["id"],
            layer=MemoryLayer(data["layer"]),
            content=data["content"],
            timestamp=data["timestamp"],
            metadata=data.get("metadata", {}),
            parent_id=data.get("parent_id"),
            result_ref=data.get("result_ref"),
        )


class MemoryPyramid:
    def __init__(self, storage_path: Optional[Path] = None):
        from cdha.config import CLOUD_DEV_HARNESS_DIR
        self.storage_path = storage_path or (CLOUD_DEV_HARNESS_DIR / "memory")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._layers = {layer: [] for layer in MemoryLayer}
        self._load_index()

    def _layer_dir(self, layer: MemoryLayer) -> Path:
        return self.storage_path / layer.value

    def _load_index(self) -> None:
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                for layer_str, entries in data.items():
                    layer = MemoryLayer(layer_str)
                    self._layers[layer] = [MemoryEntry.from_dict(e) for e in entries]
            except Exception:
                pass

    def _save_index(self) -> None:
        index_file = self.storage_path / "index.json"
        data = {layer.value: [e.to_dict() for e in entries] for layer, entries in self._layers.items()}
        index_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(
        self,
        layer: MemoryLayer,
        content: str,
        metadata: Optional[dict] = None,
        parent_id: Optional[str] = None,
        result_ref: Optional[str] = None,
    ) -> MemoryEntry:
        entry = MemoryEntry.create(layer, content, metadata, parent_id)
        entry.result_ref = result_ref
        self._layers[layer].append(entry)
        self._save_index()
        self._write_content(layer, entry)
        return entry

    def _write_content(self, layer: MemoryLayer, entry: MemoryEntry) -> None:
        layer_dir = self._layer_dir(layer)
        layer_dir.mkdir(parents=True, exist_ok=True)
        content_file = layer_dir / f"{entry.id}.md"
        content_file.write_text(entry.content, encoding="utf-8")

    def get(self, layer: MemoryLayer, entry_id: str) -> Optional[MemoryEntry]:
        for entry in self._layers[layer]:
            if entry.id == entry_id:
                return entry
        return None

    def get_content(self, entry: MemoryEntry) -> str:
        layer_dir = self._layer_dir(entry.layer)
        content_file = layer_dir / f"{entry.id}.md"
        if content_file.exists():
            return content_file.read_text(encoding="utf-8")
        return entry.content

    def list_by_layer(self, layer: MemoryLayer) -> list[MemoryEntry]:
        return list(self._layers.get(layer, []))

    def list_recent(self, layer: MemoryLayer, limit: int = 10) -> list[MemoryEntry]:
        entries = self._layers.get(layer, [])
        return sorted(entries, key=lambda e: e.timestamp, reverse=True)[:limit]

    def drill_down(self, entry_id: str) -> list[MemoryEntry]:
        chain = []
        current = self._find_entry_anywhere(entry_id)
        while current:
            chain.append(current)
            if current.parent_id:
                current = self._find_entry_anywhere(current.parent_id)
            else:
                current = None
        return list(reversed(chain))

    def _find_entry_anywhere(self, entry_id: str) -> Optional[MemoryEntry]:
        for entries in self._layers.values():
            for entry in entries:
                if entry.id == entry_id:
                    return entry
        return None

    def extract_atoms_from_conversation(
        self, conversation_id: str, max_atoms: int = 20
    ) -> list[MemoryEntry]:
        l0_entries = [e for e in self._layers[MemoryLayer.L0_CONVERSATION] if e.parent_id == conversation_id]
        atoms = []
        for l0 in l0_entries:
            content = self.get_content(l0)
            if len(content) > 100:
                atom_content = content[:200] + "..."
            else:
                atom_content = content
            atom = self.add(
                MemoryLayer.L1_ATOM,
                atom_content,
                metadata={"source": "auto_extract", "source_id": l0.id},
                parent_id=l0.id,
            )
            atoms.append(atom)
            if len(atoms) >= max_atoms:
                break
        return atoms

    def build_scenario_from_atoms(self, atom_ids: list[str], name: str) -> MemoryEntry:
        atom_contents = []
        for atom_id in atom_ids:
            atom = self._find_entry_anywhere(atom_id)
            if atom:
                atom_contents.append(f"- {atom.content}")
        content = f"## {name}\n\n" + "\n".join(atom_contents)
        return self.add(
            MemoryLayer.L2_SCENARIO,
            content,
            metadata={"atom_count": len(atom_ids)},
        )

    def build_persona_from_scenarios(self, scenario_ids: list[str], name: str) -> MemoryEntry:
        scenario_contents = []
        for sc_id in scenario_ids:
            sc = self._find_entry_anywhere(sc_id)
            if sc:
                scenario_contents.append(f"### {sc.content[:100]}...\n{sc.content}")
        content = f"# {name}\n\n" + "\n".join(scenario_contents)
        return self.add(
            MemoryLayer.L3_PERSONA,
            content,
            metadata={"scenario_count": len(scenario_ids)},
        )