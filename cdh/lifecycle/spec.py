from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Spec:
    title: str = ""
    content: str = ""
    acceptance_criteria: list[str] = field(default_factory=list)
    version: int = 1

    def generate(self, description: str) -> str:
        self.content = f"""# Specification

## Overview
{description}

## Requirements

- Functional requirements
- Non-functional requirements

## Acceptance Criteria

"""
        for i, ac in enumerate(self.acceptance_criteria, 1):
            self.content += f"{i}. {ac}\n"
        return self.content
