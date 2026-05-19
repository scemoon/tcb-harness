from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Design:
    content: str = ""
    architecture: str = ""
    interfaces: list[str] = field(default_factory=list)

    def generate(self, spec_content: str) -> str:
        self.content = f"""# Technical Design

## Architecture
{self.architecture}

## Interfaces

"""
        for iface in self.interfaces:
            self.content += f"- {iface}\n"
        return self.content
