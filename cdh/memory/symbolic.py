from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class NodeType(Enum):
    TASK = "task"
    ACTION = "action"
    RESULT = "result"
    ERROR = "error"
    CHECKPOINT = "checkpoint"


@dataclass
class MermaidNode:
    node_id: str
    node_type: NodeType
    label: str
    metadata: dict = field(default_factory=dict)

    def to_mermaid(self) -> str:
        type_styles = {
            NodeType.TASK: "([,shape=ellipse",
            NodeType.ACTION: "[,shape=box",
            NodeType.RESULT: "[(,shape=cylinder",
            NodeType.ERROR: "([,shape=ellipse,color=red",
            NodeType.CHECKPOINT: "[,shape=diamond",
        }
        style = type_styles.get(self.node_type, "[")
        return f"    {self.node_id}{style} {self.label}])"


@dataclass
class MermaidEdge:
    from_node: str
    to_node: str
    label: Optional[str] = None
    style: str = ""

    def to_mermaid(self) -> str:
        edge_str = f"    {self.from_node} --> {self.to_node}"
        if self.label:
            edge_str = f"    {self.from_node} -->|{self.label}| {self.to_node}"
        if self.style:
            edge_str += f" -. {self.style} .-> {self.to_node}"
        return edge_str


class MermaidCanvas:
    def __init__(self, task_id: Optional[str] = None):
        self.task_id = task_id or str(uuid.uuid4())[:8]
        self.nodes: list[MermaidNode] = []
        self.edges: list[MermaidEdge] = []
        self.refs: dict[str, str] = {}

    def add_node(
        self,
        node_type: NodeType,
        label: str,
        metadata: Optional[dict] = None,
    ) -> str:
        node_id = f"N{len(self.nodes):03d}"
        node = MermaidNode(node_id, node_type, label, metadata or {})
        self.nodes.append(node)
        return node_id

    def add_edge(
        self,
        from_node: str,
        to_node: str,
        label: Optional[str] = None,
        style: str = "",
    ) -> None:
        edge = MermaidEdge(from_node, to_node, label, style)
        self.edges.append(edge)

    def add_ref(self, node_id: str, content: str) -> None:
        self.refs[node_id] = content

    def get_ref(self, node_id: str) -> Optional[str]:
        return self.refs.get(node_id)

    def to_mermaid(self) -> str:
        if not self.nodes:
            return "graph LR\n    empty((empty))"

        lines = ["graph LR"]
        for node in self.nodes:
            lines.append(node.to_mermaid())
        for edge in self.edges:
            lines.append(edge.to_mermaid())
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [f"## Task Canvas: {self.task_id}\n"]
        lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}\n")
        lines.append("### Mermaid Diagram\n```mermaid")
        lines.append(self.to_mermaid())
        lines.append("```\n")
        if self.refs:
            lines.append("### References\n")
            for node_id, content in self.refs.items():
                lines.append(f"**{node_id}**: {content[:200]}...\n")
        return "\n".join(lines)

    @classmethod
    def from_mermaid(cls, mermaid_text: str) -> Optional["MermaidCanvas"]:
        try:
            canvas = cls()
            node_pattern = re.compile(r"(\w+)\[(.*?)\]")
            for match in node_pattern.finditer(mermaid_text):
                node_id, label = match.groups()
                if node_id.startswith("N"):
                    canvas.add_node(NodeType.ACTION, label)
            return canvas
        except Exception:
            return None


class SymbolicMemory:
    def __init__(self, canvas: Optional[MermaidCanvas] = None):
        self.canvas = canvas or MermaidCanvas()
        self._verbose_cache: dict[str, str] = {}

    def offload_log(self, node_id: str, verbose_content: str) -> str:
        self._verbose_cache[node_id] = verbose_content
        self.canvas.add_ref(node_id, f"See ref: {node_id}")
        return f"[{node_id}]"

    def recall_log(self, node_id: str) -> Optional[str]:
        return self._verbose_cache.get(node_id)

    def create_task_node(self, label: str, metadata: Optional[dict] = None) -> str:
        return self.canvas.add_node(NodeType.TASK, label, metadata)

    def create_action_node(self, label: str, metadata: Optional[dict] = None) -> str:
        return self.canvas.add_node(NodeType.ACTION, label, metadata)

    def create_result_node(self, label: str, result_content: str, metadata: Optional[dict] = None) -> str:
        node_id = self.canvas.add_node(NodeType.RESULT, label, metadata)
        self.offload_log(node_id, result_content)
        return node_id

    def create_error_node(self, label: str, error_content: str, metadata: Optional[dict] = None) -> str:
        node_id = self.canvas.add_node(NodeType.ERROR, label, metadata)
        self.offload_log(node_id, error_content)
        return node_id

    def link(self, from_id: str, to_id: str, label: Optional[str] = None) -> None:
        self.canvas.add_edge(from_id, to_id, label)

    def get_canvas_markdown(self) -> str:
        return self.canvas.to_markdown()

    def get_canvas_mermaid(self) -> str:
        return self.canvas.to_mermaid()

    def get_ref_content(self, node_id: str) -> Optional[str]:
        return self._verbose_cache.get(node_id)